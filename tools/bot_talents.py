#!/usr/bin/env python3
"""
Playerbot Talent Build Tool

mod-playerbots stores each premade spec as a Wowhead-style talent link -- one
digit per talent, trees separated by '-', row-major within each tree:

    AiPlayerbot.PremadeSpecLink.5.1.80 = 05032031-235050032302152530000331351

Those strings are positional, so a talent tree that gains, loses or re-tiers a
talent silently re-points every digit after the change.  Nothing validates
them: PlayerbotFactory just walks the digits and learns what it can, so an
invalid build produces a bot with a quietly wrong spec rather than an error.

site/data/<class>.json (written by tools/export_talents.py) models exactly that
wire format -- each talent carries 'i' (its row-major index, asserted to equal
its array position by --validate), 'maxPoints', and 'prereqLocation'/
'prereqRank'.  So links can be checked and generated straight from it, without
a DBC load or a Wowhead lookup.

Usage:
    python tools/bot_talents.py audit                    # check every conf link
    python tools/bot_talents.py decode --class priest --link 0503...
    python tools/bot_talents.py encode --build path/to/build.json

Build files are keyed by talent *name*, not by position, so a tree edit is
re-encoded rather than re-typed:

    {"class": "priest", "spec": "shadow", "level": 80,
     "talents": {"Twin Disciplines": 5, "Shadow Affinity": 3}}

Exit codes:
    0  clean
    1  audit found invalid builds
    2  could not run
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE_DATA = os.path.join(REPO_ROOT, "site", "data")
CONF_DIST = os.path.join(REPO_ROOT, "modules", "mod-playerbots", "conf",
                         "playerbots.conf.dist")
OVERRIDES = os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "deploy",
                         "configs", "modules", "playerbots.overrides.conf")

# ClassId as used in the config key -> site/data file key.
CLASS_BY_ID = {
    1: "warrior", 2: "paladin", 3: "hunter", 4: "rogue", 5: "priest",
    6: "death-knight", 7: "shaman", 8: "mage", 9: "warlock", 11: "druid",
}
ID_BY_CLASS = {v: k for k, v in CLASS_BY_ID.items()}

# Talent points available at a given character level: one per level from 10.
# Death knights are not a special case -- they start at 55 already holding the
# points for those levels, and reach the same 71 at 80 as everyone else, which
# is what index.json records as maxPoints.
def points_at_level(level, class_key):
    return max(0, level - 9)


# ---------------------------------------------------------------------------
# Tree model
# ---------------------------------------------------------------------------

def load_class(class_key):
    path = os.path.join(SITE_DATA, f"{class_key}.json")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def talent_at(tree, row_idx, col_idx):
    for t in tree["talents"]:
        loc = t.get("location") or {}
        if loc.get("rowIdx") == row_idx and loc.get("colIdx") == col_idx:
            return t
    return None


def parse_link(link):
    """'050-23-' -> ['050', '23', ''] padded to three trees."""
    parts = link.strip().split("-")
    while len(parts) < 3:
        parts.append("")
    return parts[:3]


def validate(class_key, link, level=None):
    """Return (spend, problems).

    spend    [(tree name, talent, points)] for every non-zero digit
    problems [str] every way the link disagrees with the current tree
    """
    data = load_class(class_key)
    if data is None:
        return [], [f"no talent data for class '{class_key}'"]

    problems, spend = [], []
    parts = parse_link(link)
    total = 0

    for page, (tree, digits) in enumerate(zip(data["trees"], parts)):
        talents = tree["talents"]
        if digits and len(digits) > len(talents):
            problems.append(
                f"{tree['name']}: link has {len(digits)} digits but the tree "
                f"has {len(talents)} talents -- everything after the extra "
                f"digit is misaligned")

        # The usual root cause, and the one worth naming explicitly.  A link is
        # positional, so a talent *inserted* ahead of the last supplied digit
        # shifts every digit after it by one.
        #
        # The tell is the digit count: a link exactly as long as the retail tree
        # in a tree that has since grown was written against retail.  Testing
        # "was a talent added before the end" instead would also fire on a
        # correctly re-authored link, which merely carries a 0 in the new slot.
        old_len = len(retail_view(tree, class_key, page))
        inserted = [t["i"] for t in talents if t.get("modKind") == "new"]
        if inserted and old_len != len(talents) and len(digits) == old_len:
            problems.append(
                f"{tree['name']}: this link is {len(digits)} digits, exactly the "
                f"retail tree size, but the tree now has {len(talents)} talents "
                f"({len(inserted)} added at position(s) "
                f"{', '.join(map(str, inserted))}). Every digit from "
                f"{min(inserted)} onward lands on the wrong talent. "
                f"Re-author with: bot_talents.py migrate")
        for pos, ch in enumerate(digits):
            if not ch.isdigit():
                problems.append(f"{tree['name']}: non-digit {ch!r} at position {pos}")
                continue
            pts = int(ch)
            if pts == 0:
                continue
            if pos >= len(talents):
                problems.append(
                    f"{tree['name']}: {pts} point(s) at position {pos}, past the "
                    f"end of the tree")
                continue
            t = talents[pos]
            total += pts
            spend.append((tree["name"], t, pts))

            if t.get("placeholder"):
                problems.append(
                    f"{tree['name']}: {pts} point(s) on an empty slot at "
                    f"position {pos}")
                continue
            if pts > t["maxPoints"]:
                problems.append(
                    f"{tree['name']}: {t['name']} has {pts} point(s) but caps "
                    f"at {t['maxPoints']}")

    # Prerequisites are checked after the full spend is known: a prereq may sit
    # anywhere in the same tree, including after its dependant in link order.
    by_tree = defaultdict(dict)
    for tree, digits in zip(data["trees"], parts):
        for pos, ch in enumerate(digits):
            if ch.isdigit() and pos < len(tree["talents"]):
                by_tree[tree["name"]][pos] = int(ch)

    for tree, digits in zip(data["trees"], parts):
        spent = by_tree[tree["name"]]
        for pos, pts in spent.items():
            if not pts:
                continue
            t = tree["talents"][pos]
            loc = t.get("prereqLocation")
            if not loc:
                continue
            parent = talent_at(tree, loc["rowIdx"], loc["colIdx"])
            if parent is None:
                problems.append(
                    f"{tree['name']}: {t['name']} requires a talent at "
                    f"row {loc['rowIdx']} col {loc['colIdx']} that no longer exists")
                continue
            have = spent.get(parent["i"], 0)
            need = t.get("prereqRank", parent["maxPoints"])
            if have < need:
                problems.append(
                    f"{tree['name']}: {t['name']} needs {need} point(s) in "
                    f"{parent['name']} but the build spends {have}")

    if level is not None:
        budget = points_at_level(level, class_key)
        if total > budget:
            problems.append(
                f"spends {total} points, but only {budget} are available at "
                f"level {level}")

    return spend, problems


# ---------------------------------------------------------------------------
# Config parsing
# ---------------------------------------------------------------------------

LINK_RE = re.compile(
    r"^\s*AiPlayerbot\.PremadeSpecLink\.(\d+)\.(\d+)\.(\d+)\s*=\s*(\S+)",
    re.MULTILINE)
NAME_RE = re.compile(
    r"^\s*AiPlayerbot\.PremadeSpecName\.(\d+)\.(\d+)\s*=\s*(.+?)\s*$",
    re.MULTILINE)


def read_conf(path):
    """Return ({(cls, spec, level): link}, {(cls, spec): name})."""
    if not os.path.isfile(path):
        return {}, {}
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()
    links = {(int(c), int(s), int(l)): v for c, s, l, v in LINK_RE.findall(text)}
    names = {(int(c), int(s)): n for c, s, n in NAME_RE.findall(text)}
    return links, names


def collect_links():
    """Merge conf.dist with the Alonecraft overrides, overrides winning.

    That is the same layering sync_configs.py applies, so the audit sees the
    values the server will actually run with rather than the template's.
    """
    links, names = read_conf(CONF_DIST)
    o_links, o_names = read_conf(OVERRIDES)
    source = {k: "conf.dist" for k in links}
    source.update({k: "overrides" for k in o_links})
    links.update(o_links)
    names.update(o_names)
    return links, names, source


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

def cmd_audit(args):
    links, names, source = collect_links()
    if not links:
        print(f"ERROR: no PremadeSpecLink entries found.", file=sys.stderr)
        print(f"       Looked in {CONF_DIST}", file=sys.stderr)
        print(f"                 {OVERRIDES}", file=sys.stderr)
        return 2

    only = args.only_class
    if only and only not in ID_BY_CLASS:
        print(f"ERROR: unknown class '{only}'. "
              f"Try one of: {', '.join(sorted(ID_BY_CLASS))}", file=sys.stderr)
        return 2

    print("Playerbot premade talent build audit")
    print(f"  template:  {CONF_DIST}")
    print(f"  overrides: {OVERRIDES}")
    print(f"  trees:     {SITE_DATA}")
    print()

    bad = 0
    for (cls_id, spec, level), link in sorted(links.items()):
        class_key = CLASS_BY_ID.get(cls_id)
        if not class_key or (only and class_key != only):
            continue
        spend, problems = validate(class_key, link, level)
        label = names.get((cls_id, spec), f"spec {spec}")
        head = (f"[{class_key} {cls_id}.{spec}.{level}] {label}"
                f"  ({source[(cls_id, spec, level)]})")
        if problems:
            bad += 1
            print(head)
            for p in problems:
                print(f"    {p}")
            print()
        elif args.verbose:
            total = sum(p for _, _, p in spend)
            print(f"{head}  OK, {total} points")

    print(f"{bad} invalid build(s) out of {len(links)} checked")
    return 1 if bad else 0


def cmd_decode(args):
    class_key = args.class_name.lower().replace(" ", "-")
    if class_key == "dk":
        class_key = "death-knight"
    data = load_class(class_key)
    if data is None:
        print(f"ERROR: unknown class '{args.class_name}'", file=sys.stderr)
        return 2

    spend, problems = validate(class_key, args.link, args.level)
    by_tree = defaultdict(list)
    for tree_name, t, pts in spend:
        by_tree[tree_name].append((t, pts))

    total = 0
    for tree in data["trees"]:
        rows = by_tree.get(tree["name"], [])
        if not rows:
            continue
        subtotal = sum(p for _, p in rows)
        total += subtotal
        print(f"{tree['name']} ({subtotal})")
        for t, pts in rows:
            flag = ""
            if t.get("modified"):
                flag = f"  [{t.get('modKind')}"
                if t.get("baseName"):
                    flag += f", was \"{t['baseName']}\""
                flag += "]"
            print(f"  {pts}/{t['maxPoints']}  {t['name']}{flag}")
    print(f"total {total}")

    if problems:
        print()
        print("problems:")
        for p in problems:
            print(f"  {p}")
    return 1 if problems else 0


_RETAIL_CACHE = {}


def retail_trees(class_key):
    """Read the real retail Talent.dbc: [[talent, ...] per tree in page order].

    Reconstructing retail by dropping talents the export marks 'new' is not
    good enough.  It reproduces the ordering but keeps *Alonecraft's* rank
    counts, so a talent whose ranks were collapsed (Molten Skin's 5 became
    Infernal Bargain's 1) reads as though retail only ever had 1 -- and the old
    link, which legitimately spends 5, looks unreadable.  The retail DBC is
    shipped in the repo, so use it.
    """
    if class_key in _RETAIL_CACHE:
        return _RETAIL_CACHE[class_key]

    sys.path.insert(0, os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc"))
    import config
    from build_dbc import TALENT_COLUMNS, TALENT_FIELD_COUNT, TALENT_RECORD_SIZE, read_int_dbc
    from spell_dbc import load_spell_index

    if not (os.path.exists(config.RETAIL_TALENT_DBC_PATH)
            and os.path.exists(config.RETAIL_DBC_PATH)):
        return None

    import contextlib
    with contextlib.redirect_stdout(sys.stderr):
        raw, _strings = read_int_dbc(config.RETAIL_TALENT_DBC_PATH,
                                     TALENT_FIELD_COUNT, TALENT_RECORD_SIZE)
        spells = load_spell_index(config.RETAIL_DBC_PATH)

    # tabId -> ordered talents, matching _build_talent_tree in gen_sql.py
    by_tab = defaultdict(list)
    for tid, values in raw.items():
        row = dict(zip(TALENT_COLUMNS, values))
        ranks = [row[f"SpellRank_{i}"] for i in range(1, 10)]
        max_points = sum(1 for r in ranks if r)
        first = ranks[0]
        name = spells.get(first, {}).get("SpellName0", f"#{tid}")
        by_tab[row["TabID"]].append({
            "tier": row["TierID"], "col": row["ColumnIndex"],
            "name": name, "maxPoints": max_points,
        })
    for tab in by_tab:
        by_tab[tab].sort(key=lambda t: (t["tier"], t["col"]))

    data = load_class(class_key)
    trees = [by_tab.get(tree["tabId"], []) for tree in data["trees"]]
    _RETAIL_CACHE[class_key] = trees
    return trees


def retail_view(tree, class_key, page):
    """Retail ordering for one tree, falling back to the modKind heuristic."""
    trees = retail_trees(class_key)
    if trees is not None:
        return trees[page]
    return [t for t in tree["talents"] if t.get("modKind") != "new"]


def current_name(class_key, retail_name):
    """Follow a rename: 'Molten Skin' -> 'Infernal Bargain'."""
    data = load_class(class_key)
    for tree in data["trees"]:
        for t in tree["talents"]:
            if t.get("baseName") == retail_name:
                return t["name"]
    return retail_name


def migrate(class_key, link):
    """Read a link against the retail tree, return {current talent name: points}.

    Renames are followed via baseName, so a build asking for Molten Skin comes
    back as Infernal Bargain without anyone hand-editing it.
    """
    data = load_class(class_key)
    wanted, problems = {}, []

    for page, (tree, digits) in enumerate(zip(data["trees"], parse_link(link))):
        old = retail_view(tree, class_key, page)
        if len(digits) > len(old):
            problems.append(
                f"{tree['name']}: {len(digits)} digits against a "
                f"{len(old)}-talent retail tree -- cannot read this link")
            continue
        for pos, ch in enumerate(digits):
            pts = int(ch)
            if not pts:
                continue
            t = old[pos]
            if pts > t["maxPoints"]:
                # Disagrees with retail too, so the link was already wrong.
                # Guessing an intent here would silently invent a build.
                problems.append(
                    f"{tree['name']}: {t['name']} takes {pts} but capped at "
                    f"{t['maxPoints']} in retail too -- link was already broken")
            wanted[current_name(class_key, t["name"])] = pts
    return wanted, problems


def cap_to_tree(class_key, wanted):
    """Clamp a migrated build to the new ranks, reporting what moved.

    Alonecraft collapses rank counts (Molten Skin's 5 ranks became Infernal
    Bargain's 1), which frees points.  Those are handed back rather than
    silently dropped -- where they go is a design choice, not a mechanical one.
    """
    data = load_class(class_key)
    capped, freed = {}, []
    for tree in data["trees"]:
        for t in tree["talents"]:
            if t["name"] not in wanted:
                continue
            pts = wanted[t["name"]]
            if pts > t["maxPoints"]:
                freed.append((t["name"], pts, t["maxPoints"]))
                pts = t["maxPoints"]
            capped[t["name"]] = pts
    return capped, freed


def cmd_migrate(args):
    """Re-author every broken premade link against the current trees."""
    links, names, source = collect_links()
    only = args.only_class
    out = []
    skipped = 0

    for (cls_id, spec, level), link in sorted(links.items()):
        class_key = CLASS_BY_ID.get(cls_id)
        if not class_key or (only and class_key != only):
            continue
        _, problems = validate(class_key, link, level)
        if not problems:
            continue

        wanted, mig_problems = migrate(class_key, link)
        if mig_problems:
            skipped += 1
            print(f"[{class_key} {cls_id}.{spec}.{level}] SKIPPED -- cannot read "
                  f"the old link:")
            for p in mig_problems:
                print(f"    {p}")
            continue

        capped, freed = cap_to_tree(class_key, wanted)
        new_link = encode_from_names(class_key, capped)
        _, still = validate(class_key, new_link, level)
        if still:
            skipped += 1
            print(f"[{class_key} {cls_id}.{spec}.{level}] SKIPPED -- migrated "
                  f"build still invalid:")
            for p in still:
                print(f"    {p}")
            continue

        spent = sum(capped.values())
        budget = points_at_level(level, class_key)
        label = names.get((cls_id, spec), f"spec {spec}")
        out.append((cls_id, spec, level, label, new_link, freed, spent, budget))

    if not out:
        print("nothing to migrate")
        return 1 if skipped else 0

    print("# Generated by tools/bot_talents.py migrate")
    print("# Paste into modules/world_of_alonecraft/deploy/configs/modules/"
          "playerbots.overrides.conf,")
    print("# then: python tools/sync_configs.py --write --accept-changes")
    print()
    for cls_id, spec, level, label, link, freed, spent, budget in out:
        print(f"# {label} ({CLASS_BY_ID[cls_id]}) -- {spent}/{budget} points")
        for name, was, now in freed:
            print(f"#   {name}: {was} -> {now} ranks, "
                  f"{was - now} point(s) freed and NOT reassigned")
        print(f"AiPlayerbot.PremadeSpecLink.{cls_id}.{spec}.{level} = {link}")
    print()
    print(f"# {len(out)} rebuilt, {skipped} skipped")
    return 0


def encode_from_names(class_key, wanted):
    data = load_class(class_key)
    parts = []
    for tree in data["trees"]:
        digits = "".join(str(wanted.get(t["name"], 0)) for t in tree["talents"])
        parts.append(digits.rstrip("0"))
    return "-".join(parts).rstrip("-")


def cmd_encode(args):
    with open(args.build, "r", encoding="utf-8") as fh:
        build = json.load(fh)

    class_key = build["class"].lower().replace(" ", "-")
    if class_key == "dk":
        class_key = "death-knight"
    data = load_class(class_key)
    if data is None:
        print(f"ERROR: unknown class '{build['class']}'", file=sys.stderr)
        return 2

    wanted = dict(build.get("talents", {}))
    parts, unmatched = [], set(wanted)

    for tree in data["trees"]:
        digits = []
        for t in tree["talents"]:
            pts = wanted.get(t["name"], 0)
            unmatched.discard(t["name"])
            if pts > t["maxPoints"]:
                print(f"ERROR: {t['name']} capped at {t['maxPoints']}, "
                      f"build asks for {pts}", file=sys.stderr)
                return 2
            digits.append(str(pts))
        # Trailing zeros are noise; the client and the parser both stop early.
        parts.append("".join(digits).rstrip("0"))

    if unmatched:
        print(f"ERROR: no talent named: {', '.join(sorted(unmatched))}",
              file=sys.stderr)
        print("       Names must match site/data exactly (they are Alonecraft's,",
              file=sys.stderr)
        print("       not retail's -- check for a rename).", file=sys.stderr)
        return 2

    link = "-".join(parts).rstrip("-")
    level = build.get("level", 80)
    spend, problems = validate(class_key, link, level)
    if problems:
        print("ERROR: the encoded build is not valid:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 2

    cls_id = ID_BY_CLASS[class_key]
    spec_no = build.get("specNo")
    total = sum(p for _, _, p in spend)
    if spec_no is None:
        print(f"# {build['class']} {build.get('spec', '')} "
              f"-- {total} points at level {level}")
        print(link)
    else:
        print(f"# {build['class']} {build.get('spec', '')} -- {total} points")
        if build.get("spec"):
            print(f"AiPlayerbot.PremadeSpecName.{cls_id}.{spec_no} = {build['spec']}")
        print(f"AiPlayerbot.PremadeSpecLink.{cls_id}.{spec_no}.{level} = {link}")
    return 0


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("audit", help="validate every premade link in the configs")
    p.add_argument("--class", dest="only_class", help="restrict to one class")
    p.add_argument("--verbose", action="store_true", help="also list valid builds")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("decode", help="show what a link spends points on")
    p.add_argument("--class", dest="class_name", required=True)
    p.add_argument("--link", required=True)
    p.add_argument("--level", type=int, default=80)
    p.set_defaults(func=cmd_decode)

    p = sub.add_parser("migrate",
                       help="re-author broken links against the current trees")
    p.add_argument("--class", dest="only_class", help="restrict to one class")
    p.set_defaults(func=cmd_migrate)

    p = sub.add_parser("encode", help="turn a name-keyed build into a link")
    p.add_argument("--build", required=True, help="path to a build JSON file")
    p.set_defaults(func=cmd_encode)

    args = ap.parse_args()
    if not os.path.isdir(SITE_DATA):
        print(f"ERROR: {SITE_DATA} not found. Run tools/export_talents.py first.",
              file=sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
