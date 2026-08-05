"""
extract_icons.py - Extract the talent icons the web calculator needs from the
WoW client MPQs and convert them to PNG.

The icons are NOT in common.MPQ; they live in enUS/locale-enUS.MPQ (4625 of
them) with a handful overridden in enUS/patch-enUS-3.MPQ.  They are also
absent from the archives' listfiles, so they cannot be enumerated -- each one
has to be read out by explicit name, which is why this walks SpellIcon.dbc
rather than globbing.

Pillow decodes BLP2 (DXT and palettised) natively, so no BLP decoder is
needed here.

Usage:
    python tools/extract_icons.py                 # only what is missing
    python tools/extract_icons.py --force         # re-extract everything
    python tools/extract_icons.py --check         # report gaps, write nothing
"""

import argparse
import io
import json
import os
import subprocess
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc"))

import config  # noqa: E402
import spell_dbc as S  # noqa: E402

MPQCLI = os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc", "mpqcli.exe")
CLIENT_DATA = r"C:\Users\Shadow\Desktop\WoW Solo\WoW Solo\Data"
SITE_DATA = os.path.join(REPO_ROOT, "site", "data")
ICON_DIR = os.path.join(REPO_ROOT, "site", "assets", "icons")

# Later archives win: patch-enUS-3 overrides locale-enUS for the 67 icons it
# replaces.  Ordered most-recent-first so the first hit is the right one.
ARCHIVES = [
    os.path.join("enUS", "patch-enUS-3.MPQ"),
    os.path.join("enUS", "patch-enUS-2.MPQ"),
    os.path.join("enUS", "patch-enUS.MPQ"),
    os.path.join("enUS", "locale-enUS.MPQ"),
]


def wanted_icons():
    """Icon names referenced by the exported talent data.

    Driven by site/data/*.json rather than by SpellIcon.dbc as a whole: we
    want the ~400 icons the calculator actually renders, not all 3226.
    """
    if not os.path.isdir(SITE_DATA):
        sys.exit(f"ERROR: {SITE_DATA} not found. Run tools/export_talents.py first.")
    names = set()
    for fn in sorted(os.listdir(SITE_DATA)):
        if not fn.endswith(".json") or fn == "index.json":
            continue
        with open(os.path.join(SITE_DATA, fn), encoding="utf-8") as f:
            data = json.load(f)
        for tree in data.get("trees", []):
            for talent in tree.get("talents", []):
                if talent.get("icon"):
                    names.add(talent["icon"])
    return names


def icon_paths():
    """lowercase icon name -> the archive path to read, from SpellIcon.dbc."""
    rows = S.read_dbc(config.BASE_SPELLICON_DBC_PATH,
                      S.SPELLICON_COLUMNS, S.SPELLICON_FMT, quiet=True)
    # Several basenames appear twice: once under Interface\Icons (the real
    # file) and once under a legacy Spells\Icon path that no longer exists in
    # the archives.  Prefer Interface\Icons, or the vanilla path wins and the
    # read fails -- this is what made spell_fire_fire unextractable.
    out = {}
    for row in rows.values():
        texture = row["TextureFilename"]
        if not texture:
            continue
        normalised = texture.replace("/", "\\")
        name = normalised.rsplit("\\", 1)[-1].lower()
        preferred = normalised.lower().startswith("interface\\icons")
        if name in out and not preferred:
            continue
        out[name] = normalised + ".blp"
    return out


def read_from_mpq(archive_path, member):
    """Read one file out of an MPQ to bytes, or None if it isn't there."""
    result = subprocess.run(
        [MPQCLI, "read", member, archive_path],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        return None
    if result.stdout.startswith(b"[!]"):
        return None
    return result.stdout


def convert(blp_bytes):
    from PIL import Image
    image = Image.open(io.BytesIO(blp_bytes))
    image.load()
    buf = io.BytesIO()
    image.convert("RGBA").save(buf, "PNG", optimize=True)
    return buf.getvalue()


# ── Talent tree backgrounds ────────────────────────────────────────────────
# Each tree's art is four unevenly-sized quadrants that tile into one 320x384
# image. The base name comes from TalentTab.dbc's BackgroundFile and is not
# guessable: Warlock Demonology is "WarlockSummoning", Warrior Arms is
# "WarriorArms", and Paladin Retribution is "PaladinCombat".
QUADRANTS = [
    ("TopLeft", (0, 0)),
    ("TopRight", (256, 0)),
    ("BottomLeft", (0, 256)),
    ("BottomRight", (256, 256)),
]
BACKGROUND_SIZE = (320, 384)

FONTS = ["FRIZQT__.TTF", "MORPHEUS.TTF"]


def wanted_backgrounds():
    """Background base names referenced by the exported tree data."""
    names = set()
    for fn in sorted(os.listdir(SITE_DATA)):
        if not fn.endswith(".json") or fn == "index.json":
            continue
        with open(os.path.join(SITE_DATA, fn), encoding="utf-8") as f:
            data = json.load(f)
        for tree in data.get("trees", []):
            if tree.get("background"):
                names.add(tree["background"])
    return names


def extract_backgrounds(archives, out_dir, force):
    from PIL import Image

    os.makedirs(out_dir, exist_ok=True)
    names = wanted_backgrounds()
    have = {f[:-4] for f in os.listdir(out_dir) if f.endswith(".png")}
    todo = sorted(names if force else names - have)
    print(f"  Tree backgrounds referenced: {len(names)}, to extract: {len(todo)}")

    written = failed = 0
    for name in todo:
        canvas = Image.new("RGBA", BACKGROUND_SIZE, (0, 0, 0, 0))
        ok = True
        for quadrant, position in QUADRANTS:
            member = f"Interface\\TalentFrame\\{name}-{quadrant}.blp"
            blob = None
            for archive in archives:
                blob = read_from_mpq(archive, member)
                if blob:
                    break
            if not blob:
                print(f"    ! {name}-{quadrant}: not found")
                ok = False
                break
            piece = Image.open(io.BytesIO(blob))
            piece.load()
            canvas.paste(piece.convert("RGBA"), position)
        if not ok:
            failed += 1
            continue
        canvas.save(os.path.join(out_dir, name + ".png"), "PNG", optimize=True)
        written += 1

    print(f"  Wrote {written} tree background(s)"
          + (f", {failed} failed" if failed else ""))


def extract_fonts(archives, out_dir, force):
    """FRIZQT__ is WoW's UI face; MORPHEUS is the quest/heading face."""
    os.makedirs(out_dir, exist_ok=True)
    written = 0
    for font in FONTS:
        target = os.path.join(out_dir, font)
        if os.path.exists(target) and not force:
            continue
        blob = None
        for archive in archives:
            blob = read_from_mpq(archive, f"Fonts\\{font}")
            if blob:
                break
        if not blob:
            print(f"    ! {font}: not found in any client archive")
            continue
        with open(target, "wb") as f:
            f.write(blob)
        written += 1
    print(f"  Wrote {written} font(s)")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--force", action="store_true",
                   help="re-extract icons that already exist")
    p.add_argument("--check", action="store_true",
                   help="report missing icons; write nothing")
    p.add_argument("--client-data", default=CLIENT_DATA,
                   help="WoW client Data directory")
    p.add_argument("--out", default=ICON_DIR)
    args = p.parse_args()

    print("=" * 60)
    print("  Alonecraft Talent Icon Extraction")
    print("=" * 60)

    names = wanted_icons()
    print(f"  Talent icons referenced: {len(names)}")

    have = set()
    if os.path.isdir(args.out):
        have = {f[:-4] for f in os.listdir(args.out) if f.endswith(".png")}

    if args.check:
        missing = sorted(names - have)
        extra = sorted(have - names)
        print(f"  Present: {len(names & have)}   Missing: {len(missing)}"
              f"   Unreferenced: {len(extra)}")
        for n in missing[:20]:
            print(f"    missing: {n}")
        return 1 if missing else 0

    todo = sorted(names if args.force else names - have)

    if not os.path.exists(MPQCLI):
        sys.exit(f"ERROR: mpqcli not found at {MPQCLI}")

    archives = [os.path.join(args.client_data, a) for a in ARCHIVES]
    archives = [a for a in archives if os.path.exists(a)]
    if not archives:
        sys.exit(f"ERROR: no client MPQs found under {args.client_data}")

    site_assets = os.path.dirname(args.out)
    extract_backgrounds(archives, os.path.join(site_assets, "trees"), args.force)
    extract_fonts(archives, os.path.join(site_assets, "fonts"), args.force)

    if not todo:
        print("  Nothing to do -- all icons already extracted.")
        return 0

    paths = icon_paths()

    os.makedirs(args.out, exist_ok=True)
    written = failed = 0
    total_bytes = 0
    for name in todo:
        member = paths.get(name)
        if not member:
            print(f"    ! {name}: not in SpellIcon.dbc")
            failed += 1
            continue
        blob = None
        for archive in archives:
            blob = read_from_mpq(archive, member)
            if blob:
                break
        if not blob:
            print(f"    ! {name}: not found in any client archive")
            failed += 1
            continue
        try:
            png = convert(blob)
        except Exception as exc:  # noqa: BLE001 - report and continue
            print(f"    ! {name}: BLP decode failed ({exc})")
            failed += 1
            continue
        with open(os.path.join(args.out, name + ".png"), "wb") as f:
            f.write(png)
        written += 1
        total_bytes += len(png)
        if written % 50 == 0:
            print(f"    ... {written}/{len(todo)}")

    print(f"\n  Wrote {written} PNG(s), {total_bytes / 1024:.0f} KB total")
    if failed:
        print(f"  {failed} icon(s) could not be extracted -- the site falls "
              f"back to assets/icon-fallback.svg for these")
    return 0


if __name__ == "__main__":
    sys.exit(main())
