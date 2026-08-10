#!/usr/bin/env python3
"""Pack custom Interface files into patch-4.mpq.

Scans Interface/custom/ for Lua/XML/TOC files and adds them to the
existing patch-4.mpq (shared with DBC builds) using mpqcli.

Files in custom/ map to MPQ archive paths:
  custom/FrameXML/Foo.lua   -> Interface/FrameXML/Foo.lua
  custom/AddOns/Bar/Bar.lua -> Interface/AddOns/Bar/Bar.lua

Only files that differ from Interface/base/ (or don't exist there) are packed.

Nothing in base/ is a .blp and none of our AddOns are there either, so that
filter alone says "pack" for every file we own -- which meant ~28 mpqcli
subprocesses on every build, including builds that changed nothing.  So a
content cache next to patch-4.mpq records the sha256 last packed for each
archive path, and a file is skipped only when its hash still matches AND the
archive still lists that path.  Use --force to repack regardless.
"""

import os
import sys
import json
import hashlib
import filecmp
import subprocess

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CUSTOM_DIR = os.path.join(SCRIPT_DIR, "custom")
BASE_DIR = os.path.join(SCRIPT_DIR, "base")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")

# patch-4.mpq lives in the DBC output directory (shared with build_dbc.py)
DBC_OUTPUT_DIR = os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc", "output")
MPQ_PATH = os.path.join(DBC_OUTPUT_DIR, "patch-4.mpq")

# Cache lives next to the MPQ it describes, so the documented "delete
# patch-4.mpq and rebuild" recovery also discards the cache.
CACHE_PATH = os.path.join(DBC_OUTPUT_DIR, "interface_pack_cache.json")

# mpqcli.exe lives next to build_dbc.py
MPQCLI_DIR = os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc")
MPQCLI = os.path.join(MPQCLI_DIR, "mpqcli.exe")


def find_custom_files():
    """Find all packable files in custom/, return list of relative paths."""
    # .blp so custom art can ship too -- custom/Icons/foo.blp lands at
    # Interface\Icons\foo.blp, which is where the client resolves an
    # ItemDisplayInfo InventoryIcon name.  Nothing in base/ is a .blp, so
    # is_modified() always says yes for these.
    extensions = {".lua", ".xml", ".toc", ".xsd", ".blp"}
    files = []
    for root, _dirs, filenames in os.walk(CUSTOM_DIR):
        for fname in filenames:
            if os.path.splitext(fname)[1].lower() in extensions:
                full = os.path.join(root, fname)
                rel = os.path.relpath(full, CUSTOM_DIR)
                files.append(rel)
    return sorted(files)


def is_modified(rel_path):
    """Check if custom file differs from base (or doesn't exist in base).

    The base repo has a flat FrameXML layout (files at root) plus Blizzard_*
    addon dirs. We map our structured paths accordingly:
      FrameXML/Foo.lua  -> base/Foo.lua
      AddOns/Bar/Bar.lua -> base/Bar/Bar.lua  (Blizzard addons are at root too)
    """
    custom_file = os.path.join(CUSTOM_DIR, rel_path)

    # Try direct match first (handles AddOns/Blizzard_Foo/...)
    base_file = os.path.join(BASE_DIR, rel_path)
    if os.path.isfile(base_file):
        return not filecmp.cmp(custom_file, base_file, shallow=False)

    # FrameXML/Foo.lua -> base/Foo.lua (flat layout in base repo)
    parts = rel_path.replace("\\", "/").split("/")
    if parts[0] == "FrameXML" and len(parts) == 2:
        base_file = os.path.join(BASE_DIR, parts[1])
        if os.path.isfile(base_file):
            return not filecmp.cmp(custom_file, base_file, shallow=False)

    # AddOns/Blizzard_Foo/... -> base/Blizzard_Foo/...
    if parts[0] == "AddOns" and len(parts) > 2:
        base_file = os.path.join(BASE_DIR, *parts[1:])
        if os.path.isfile(base_file):
            return not filecmp.cmp(custom_file, base_file, shallow=False)

    # Not in base = new file, always pack
    return True


def archive_path_of(rel_path):
    """custom/ relative path -> MPQ archive path (backslashes)."""
    return "Interface\\" + rel_path.replace("/", "\\")


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_cache():
    """Read the pack cache. A missing or corrupt cache just means repack."""
    try:
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            cache = json.load(f)
        return cache if isinstance(cache, dict) else {}
    except (OSError, ValueError):
        return {}


def save_cache(cache):
    try:
        os.makedirs(DBC_OUTPUT_DIR, exist_ok=True)
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, indent=2, sort_keys=True)
    except OSError as exc:
        print(f"  WARNING: could not write pack cache: {exc}")


def archive_entries():
    """Paths currently inside patch-4.mpq, or None if we can't tell.

    build_dbc.py creates a *fresh* patch-4.mpq whenever the file is missing,
    which silently drops every Interface\\ entry. Without this check a
    hash-only cache would skip everything and ship an MPQ with no addons and
    no icons. None means "unknown" -- pack everything, as before.
    """
    if not os.path.isfile(MPQCLI) or not os.path.isfile(MPQ_PATH):
        return None
    try:
        result = subprocess.run([MPQCLI, "list", MPQ_PATH],
                                capture_output=True, text=True)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def pack_files(files):
    """Add files to patch-4.mpq."""
    if not os.path.isfile(MPQCLI):
        print(f"ERROR: mpqcli not found at {MPQCLI}")
        print("Download from: https://github.com/TheGrayDot/mpqcli/releases")
        return False, []

    if not os.path.isfile(MPQ_PATH):
        print(f"ERROR: patch-4.mpq not found at {MPQ_PATH}")
        print("Run build_dbc.py first to create the base MPQ.")
        return False, []

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    success = True
    packed = []

    for rel_path in files:
        src_file = os.path.join(CUSTOM_DIR, rel_path)
        # MPQ archive path uses backslashes: Interface\FrameXML\Foo.lua
        archive_path = archive_path_of(rel_path)

        cmd = [
            MPQCLI, "add",
            "--overwrite",
            "--game", "wow-wotlk",
            "-p", archive_path,
            src_file,
            MPQ_PATH,
        ]

        print(f"  Packing: {archive_path}")
        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"    ERROR: {result.stderr.strip()}")
                success = False
            else:
                packed.append(rel_path)
                if result.stdout.strip():
                    print(f"    {result.stdout.strip()}")
        except FileNotFoundError:
            print(f"ERROR: mpqcli not found")
            return False, packed

    return success, packed


def main():
    print("=== Interface Build ===")

    files = find_custom_files()
    if not files:
        print("No custom Interface files found in Interface/custom/")
        print("Nothing to pack.")
        return 0

    force = "--force" in sys.argv
    dry_run = "--dry-run" in sys.argv

    # Filter to only modified/new files
    modified = [f for f in files if is_modified(f)]

    print(f"Found {len(files)} custom file(s), {len(modified)} modified/new.")

    if not modified:
        print("All custom files match base. Nothing to pack.")
        return 0

    # Then drop anything already in the archive with the same contents.
    cache = {} if force else load_cache()
    in_archive = archive_entries()
    hashes = {f: file_sha256(os.path.join(CUSTOM_DIR, f)) for f in modified}

    to_pack = []
    for rel_path in modified:
        archive_path = archive_path_of(rel_path)
        cached = cache.get(archive_path) == hashes[rel_path]
        present = in_archive is None or archive_path in in_archive
        if cached and present:
            continue
        to_pack.append(rel_path)

    skipped = len(modified) - len(to_pack)
    print(f"{skipped} unchanged (cached), {len(to_pack)} to pack.")
    for f in to_pack:
        print(f"  {f}")

    if not to_pack:
        return 0

    if dry_run:
        print("Dry run - no files packed.")
        return 0

    print(f"\nPacking into {MPQ_PATH}...")
    success, packed = pack_files(to_pack)

    # Record only what actually packed, so a failed add is retried next run.
    if packed:
        cache.update({archive_path_of(f): hashes[f] for f in packed})
        save_cache(cache)

    if success:
        print(f"\nDone! {len(packed)} file(s) packed into patch-4.mpq")
        return 0
    else:
        print("\nSome files failed to pack.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
