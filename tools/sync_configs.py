#!/usr/bin/env python3
"""
Alonecraft Config Sync

Keeps the deployed server configs in step with the `.conf.dist` templates that
ship with the core and each module, applying a small tracked set of Alonecraft
overrides on top.

The problem this solves: the deployed `configs/` tree is untracked and was
hand-edited. Over time it drifted badly from the templates -- 25 missing keys in
worldserver.conf (23 of which warn on every startup), ~200 missing in
mod_llm_chatter.conf, ~40 in playerbots.conf, plus a hand-added duplicate key.
Missing keys silently fall back to compiled-in defaults, and mod-llm-chatter
reads its config with warnings suppressed, so its drift was completely invisible.

The fix is deliberately an *override layer*, not a tracked full copy. A full copy
is exactly what rotted: it becomes a stale snapshot the moment a template gains a
key. Here the `.dist` remains the source of every key and the override file is a
short, reviewable statement of what Alonecraft does differently.

Overrides live in:
    modules/world_of_alonecraft/deploy/configs/<name>.overrides.conf
Secrets (DB credentials, API keys) go next to them in:
    modules/world_of_alonecraft/deploy/configs/<name>.overrides.local.conf
which is gitignored.

Usage:
    python tools/sync_configs.py                       # --check (default)
    python tools/sync_configs.py --check --verbose     # list every missing key
    python tools/sync_configs.py --write               # show the diff, do nothing
    python tools/sync_configs.py --write --accept-changes
    python tools/sync_configs.py --only worldserver
"""

import argparse
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SERVER_DIR = r"C:\Build\bin\RelWithDebInfo"
OVERRIDE_DIR = os.path.join(
    REPO_ROOT, "modules", "world_of_alonecraft", "deploy", "configs"
)

# (name, dist path relative to repo root, deployed path relative to server dir)
PAIRS = [
    ("worldserver",
     "src/server/apps/worldserver/worldserver.conf.dist",
     "configs/worldserver.conf"),
    ("authserver",
     "src/server/apps/authserver/authserver.conf.dist",
     "configs/authserver.conf"),
    ("playerbots",
     "modules/mod-playerbots/conf/playerbots.conf.dist",
     "configs/modules/playerbots.conf"),
    ("mod_llm_chatter",
     "modules/mod-llm-chatter/conf/mod_llm_chatter.conf.dist",
     "configs/modules/mod_llm_chatter.conf"),
    ("AutoBalance",
     "modules/mod-autobalance/conf/AutoBalance.conf.dist",
     "configs/modules/AutoBalance.conf"),
    ("dungeonrespawn",
     "modules/mod-dungeon-respawn/conf/dungeonrespawn.conf.dist",
     "configs/modules/dungeonrespawn.conf"),
    ("mod_learnspells",
     "modules/mod-learn-spells/conf/mod_learnspells.conf.dist",
     "configs/modules/mod_learnspells.conf"),
    ("mod_mythic_plus",
     "modules/mod-mythic-plus/conf/mod_mythic_plus.conf.dist",
     "configs/modules/mod_mythic_plus.conf"),
    ("transmog",
     "modules/mod-transmog/conf/transmog.conf.dist",
     "configs/modules/transmog.conf"),
    ("mod_ahbot",
     "modules/mod-ah-bot-plus/conf/mod_ahbot.conf.dist",
     "configs/modules/mod_ahbot.conf"),
    ("my_custom",
     "modules/world_of_alonecraft/conf/my_custom.conf.dist",
     "configs/modules/my_custom.conf"),
]

# `Key = Value`, allowing the key characters AzerothCore actually uses.
SETTING_RE = re.compile(r"^(?P<key>[A-Za-z0-9_.\-]+)\s*=(?P<value>.*)$")


def read_settings(path):
    """Return (ordered [(key, value)], {key: [linenos]}) for a conf file."""
    settings = []
    seen = {}
    if not os.path.isfile(path):
        return settings, seen

    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for lineno, raw in enumerate(fh, 1):
            stripped = raw.strip()
            if not stripped or stripped.startswith("#"):
                continue
            m = SETTING_RE.match(stripped)
            if not m:
                continue
            key = m.group("key")
            settings.append((key, m.group("value").strip()))
            seen.setdefault(key, []).append(lineno)

    return settings, seen


def load_overrides(name):
    """Merge <name>.overrides.conf and its .local sibling. Local wins.

    Module overrides sit in a modules/ subdirectory mirroring the deployed
    layout, so both locations are searched.
    """
    values = {}
    sources = {}
    for directory in (OVERRIDE_DIR, os.path.join(OVERRIDE_DIR, "modules")):
        for suffix in (".overrides.conf", ".overrides.local.conf"):
            path = os.path.join(directory, name + suffix)
            settings, _ = read_settings(path)
            for key, value in settings:
                values[key] = value
                sources[key] = os.path.relpath(path, OVERRIDE_DIR)
    return values, sources


def check_pair(name, dist_path, deployed_path, verbose):
    """Report drift for one config. Returns the number of findings."""
    findings = 0

    if not os.path.isfile(dist_path):
        print(f"  [{name}] template missing: {dist_path}")
        return 1
    if not os.path.isfile(deployed_path):
        print(f"  [{name}] deployed config missing: {deployed_path}")
        print(f"           run --write to create it from the template")
        return 1

    dist_settings, _ = read_settings(dist_path)
    _deployed_settings, deployed_seen = read_settings(deployed_path)
    overrides, override_sources = load_overrides(name)

    dist_keys = [k for k, _ in dist_settings]
    dist_key_set = set(dist_keys)
    deployed_key_set = set(deployed_seen)

    missing = [k for k in dist_keys if k not in deployed_key_set]
    extra = sorted(deployed_key_set - dist_key_set)
    # A key written twice in one file: the core warns and the last one wins,
    # which is a silent behaviour change waiting to happen.
    duplicates = {k: v for k, v in deployed_seen.items() if len(v) > 1}
    # Overrides for keys the template does not define. Either a deliberate
    # Alonecraft addition (Logger.alonecraft.debug) or a typo / a key upstream
    # renamed on a submodule bump. We cannot tell which, so surface them every
    # time rather than guessing -- the list should stay short enough to read.
    unknown_overrides = sorted(set(overrides) - dist_key_set)
    # Deployed keys that exist only because an override added them are accounted
    # for, so they must not also be reported as stale.
    extra = [k for k in extra if k not in overrides]

    if not (missing or extra or duplicates):
        print(f"  [{name}] OK ({len(dist_keys)} keys, "
              f"{len(overrides)} override(s))")
        report_additions(name, unknown_overrides, override_sources)
        return 0

    print(f"  [{name}]")
    report_additions(name, unknown_overrides, override_sources)
    if missing:
        findings += 1
        print(f"      {len(missing)} key(s) in the template but not deployed "
              f"-- running on compiled-in defaults")
        shown = missing if verbose else missing[:8]
        for k in shown:
            print(f"        - {k}")
        if len(missing) > len(shown):
            print(f"        ... and {len(missing) - len(shown)} more "
                  f"(--verbose to list)")
    if duplicates:
        findings += 1
        print(f"      {len(duplicates)} duplicate key(s) -- the core warns and "
              f"the last value wins")
        for k, lines in sorted(duplicates.items()):
            print(f"        ! {k} at lines {', '.join(map(str, lines))}")
    if extra:
        findings += 1
        print(f"      {len(extra)} deployed key(s) not in the template "
              f"-- stale, renamed, or from a removed module")
        shown = extra if verbose else extra[:8]
        for k in shown:
            print(f"        ? {k}")
        if len(extra) > len(shown):
            print(f"        ... and {len(extra) - len(shown)} more")
    return findings


def report_additions(name, unknown_overrides, override_sources):
    """Overrides that add keys absent from the template. Informational."""
    if not unknown_overrides:
        return
    print(f"  [{name}] {len(unknown_overrides)} key(s) added by override "
          f"(not in the template) -- confirm these are intentional, not typos:")
    for k in unknown_overrides:
        print(f"        + {k}  (from {override_sources.get(k, '?')})")


def render(dist_path, overrides):
    """Return the .dist text with override values substituted in place.

    Substituting line-by-line rather than regenerating keeps every comment,
    section banner and key ordering from the template, so a later diff against a
    new .dist stays readable.
    """
    out = []
    applied = set()

    with open(dist_path, "r", encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                m = SETTING_RE.match(stripped)
                if m and m.group("key") in overrides:
                    key = m.group("key")
                    out.append(f"{key} = {overrides[key]}")
                    applied.add(key)
                    continue
            out.append(line)

    # Overrides for keys the template does not define are appended rather than
    # dropped. Alonecraft legitimately adds settings the core knows nothing
    # about -- Logger.alonecraft.debug being the obvious one -- and silently
    # discarding them on every regeneration would make the override file lie.
    additions = [k for k in overrides if k not in applied]
    if additions:
        out.append("")
        out.append("#" * 78)
        out.append("# Alonecraft additions: keys not present in the .dist template.")
        out.append("# Appended by tools/sync_configs.py from the override files.")
        out.append("#" * 78)
        for key in additions:
            out.append(f"{key} = {overrides[key]}")
            applied.add(key)
        out.append("")

    return "\n".join(out) + "\n", applied


def value_diff(dist_path, deployed_path, overrides):
    """[(key, current_deployed_value, new_value)] for every key that changes."""
    dist_settings, _ = read_settings(dist_path)
    deployed_settings, _ = read_settings(deployed_path)
    deployed_values = dict(deployed_settings)

    changes = []
    for key, dist_value in dist_settings:
        new_value = overrides.get(key, dist_value)
        old_value = deployed_values.get(key)
        if old_value is None:
            changes.append((key, None, new_value))
        elif old_value != new_value:
            changes.append((key, old_value, new_value))
    return changes


def write_pair(name, dist_path, deployed_path, accept, verbose):
    """Show the effective-value diff and, with accept, write the file."""
    if not os.path.isfile(dist_path):
        print(f"  [{name}] template missing: {dist_path}")
        return 1

    overrides, _ = load_overrides(name)
    changes = value_diff(dist_path, deployed_path, overrides) \
        if os.path.isfile(deployed_path) else None

    print(f"  [{name}] -> {deployed_path}")

    if changes is None:
        print("      deployed config does not exist yet; it will be created.")
    elif not changes:
        print("      no effective change.")
    else:
        added = [c for c in changes if c[1] is None]
        altered = [c for c in changes if c[1] is not None]
        print(f"      {len(added)} key(s) restored from the template, "
              f"{len(altered)} value(s) changed")
        for key, old, new in altered:
            print(f"        ~ {key}: {old!r} -> {new!r}")
        shown = added if verbose else added[:10]
        for key, _old, new in shown:
            print(f"        + {key} = {new!r}")
        if len(added) > len(shown):
            print(f"        ... and {len(added) - len(shown)} more restored "
                  f"(--verbose to list)")

    if not accept:
        return 0

    text, applied = render(dist_path, overrides)
    os.makedirs(os.path.dirname(deployed_path), exist_ok=True)
    if os.path.isfile(deployed_path):
        backup = deployed_path + ".bak"
        with open(deployed_path, "r", encoding="utf-8", errors="replace") as src:
            with open(backup, "w", encoding="utf-8") as dst:
                dst.write(src.read())
        print(f"      backed up to {os.path.basename(backup)}")

    with open(deployed_path, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"      written ({len(applied)} override(s) applied)")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Sync deployed configs with .dist templates + overrides."
    )
    parser.add_argument("--server-dir", default=DEFAULT_SERVER_DIR)
    parser.add_argument(
        "--check", action="store_true",
        help="Report drift (the default when neither mode is given)",
    )
    parser.add_argument(
        "--write", action="store_true",
        help="Regenerate deployed configs from template + overrides",
    )
    parser.add_argument(
        "--accept-changes", action="store_true",
        help="Required by --write. Without it the diff is printed and nothing "
             "is touched -- adopting template defaults can switch on features "
             "you have never run.",
    )
    parser.add_argument(
        "--only", help="Limit to one config by name (e.g. worldserver)",
    )
    parser.add_argument("--verbose", action="store_true", help="List every key")
    args = parser.parse_args()

    pairs = PAIRS
    if args.only:
        pairs = [p for p in PAIRS if p[0] == args.only]
        if not pairs:
            print(f"  Unknown config '{args.only}'. Known: "
                  f"{', '.join(p[0] for p in PAIRS)}")
            return 2

    print("=" * 72)
    print("  Alonecraft Config Sync")
    print("=" * 72)
    print(f"  Templates:  {REPO_ROOT}")
    print(f"  Deployed:   {args.server_dir}")
    print(f"  Overrides:  {OVERRIDE_DIR}")
    if not os.path.isdir(OVERRIDE_DIR):
        print("              (does not exist yet -- no overrides applied)")
    print()

    if args.write:
        findings = 0
        for name, dist_rel, deployed_rel in pairs:
            findings += write_pair(
                name,
                os.path.join(REPO_ROOT, dist_rel),
                os.path.join(args.server_dir, deployed_rel.replace("/", os.sep)),
                args.accept_changes,
                args.verbose,
            )
        print()
        if not args.accept_changes:
            print("  Nothing was written. Review the diff above, then re-run")
            print("  with --accept-changes.")
        return 1 if findings else 0

    total = 0
    for name, dist_rel, deployed_rel in pairs:
        total += check_pair(
            name,
            os.path.join(REPO_ROOT, dist_rel),
            os.path.join(args.server_dir, deployed_rel.replace("/", os.sep)),
            args.verbose,
        )

    print()
    if total == 0:
        print("  All configs in sync with their templates.")
        return 0
    print(f"  {total} finding(s). Run --write to preview the fix.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
