"""
export_talents.py - Export Alonecraft's talent trees to JSON for the web
talent calculator in site/.

Why this exists: Alonecraft has redesigned talents across most specs, but
Wowhead only knows base 3.3.5a, so no third-party calculator can render our
trees.  This reads the same DBCs that ship to the client and emits the data a
static site needs.

Why the output is COMMITTED rather than generated in CI: the post-override
DBCs live in the server's build directory and the override tables live in
local MySQL.  GitHub Actions can reach neither, and the base DBCs are in a
submodule.  So the export runs locally and CI only publishes site/.

Schema: we follow wowsims/wotlk's talent tree format (fieldName, location,
spellIds, maxPoints, prereqLocation) and add what it lacks -- names, resolved
per-rank descriptions, icons, and the modified-vs-retail diff.  wowsims gets
all of that from Wowhead at runtime, which is exactly what cannot work here.

Usage:
    python tools/export_talents.py                 # write site/data/
    python tools/export_talents.py --source base   # no server build needed
    python tools/export_talents.py --validate      # structural assertions
    python tools/export_talents.py --check         # fail if committed data is stale
    python tools/export_talents.py --report-tokens # tooltip token census
"""

import argparse
import collections
import hashlib
import json
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc"))

import gen_sql  # noqa: E402
import spell_dbc as S  # noqa: E402
import tooltip_vars as T  # noqa: E402
import config  # noqa: E402
from build_dbc import (  # noqa: E402
    TALENT_COLUMNS, TALENT_FIELD_COUNT, TALENT_RECORD_SIZE, read_int_dbc,
)

SITE_DATA = os.path.join(REPO_ROOT, "site", "data")
SCHEMA_VERSION = 1
MAX_TALENT_POINTS = 71

# Columns whose change means the talent was meaningfully altered.  A full
# 234-column diff would fire on incidental differences, because build_dbc.py
# rewrites whole rows from the DB rather than patching fields in place.
DIFF_COLUMNS = (
    ["SpellName0", "SpellRank0", "SpellDescription0", "SpellToolTip0",
     "ProcChance", "StackAmount", "DurationIndex", "RangeIndex",
     "CastingTimeIndex", "SpellIconID"]
    + [f"{c}{i}"
       for c in ("EffectBasePoints", "EffectDieSides", "EffectAmplitude",
                 "Effect", "EffectApplyAuraName", "EffectChainTarget")
       for i in (1, 2, 3)]
)

NAME_COLUMNS = {"SpellName0", "SpellRank0"}
TEXT_COLUMNS = {"SpellDescription0", "SpellToolTip0"}

# Higher wins when a talent trips several categories at once.
KIND_PRIORITY = {"new": 4, "structure": 3, "renamed": 2, "values": 1,
                 "description": 0}


def class_key(name):
    """'Death Knight' -> 'death-knight'."""
    return name.lower().replace(" ", "-")


def field_name(spell_name):
    """'Arcane Subtlety' -> 'arcaneSubtlety', matching wowsims' convention."""
    parts = re.sub(r"[^A-Za-z0-9 ]", "", spell_name or "").split()
    if not parts:
        return ""
    return parts[0].lower() + "".join(p.capitalize() for p in parts[1:])


# ── Loading ────────────────────────────────────────────────────────────────


def load_aux(spells):
    """Load the index DBCs the tooltip resolver needs.

    Missing files degrade the dependent tokens rather than aborting, so a
    fresh clone that has not extracted them still produces a usable export.
    """
    def maybe(path, columns, fmt, label):
        if not os.path.exists(path):
            print(f"  WARNING: {label} not found at {path} -- "
                  f"dependent tooltip variables will be left unresolved")
            return {}
        return S.read_dbc(path, columns, fmt, quiet=True)

    return T.AuxTables(
        spells=spells,
        durations=maybe(config.BASE_SPELLDURATION_DBC_PATH,
                        S.SPELLDURATION_COLUMNS, S.SPELLDURATION_FMT,
                        "SpellDuration.dbc"),
        radii=maybe(config.BASE_SPELLRADIUS_DBC_PATH,
                    S.SPELLRADIUS_COLUMNS, S.SPELLRADIUS_FMT,
                    "SpellRadius.dbc"),
        ranges=maybe(config.BASE_SPELLRANGE_DBC_PATH,
                     S.SPELLRANGE_COLUMNS, S.SPELLRANGE_FMT,
                     "SpellRange.dbc"),
        cast_times=maybe(config.BASE_SPELLCASTTIMES_DBC_PATH,
                         S.SPELLCASTTIMES_COLUMNS, S.SPELLCASTTIMES_FMT,
                         "SpellCastTimes.dbc"),
    )


CLASS_BY_MASK = {
    1: "Warrior", 2: "Paladin", 4: "Hunter", 8: "Rogue", 16: "Priest",
    32: "Death Knight", 64: "Shaman", 128: "Mage", 256: "Warlock",
    1024: "Druid",
}


def load_tabs():
    """Talent tabs from TalentTab.dbc: (tab_id, class, name, order, background).

    Preferred over gen_sql.TALENT_TAB_INFO, whose hardcoded names and page
    order are wrong for five trees -- it has Paladin 381 as Holy when the tab
    actually holds Benediction and Conviction (Retribution), and swaps
    Warrior's Fury and Protection. Reading the DBC is both correct and
    self-maintaining.

    Pet talent tabs (Ferocity/Cunning/Tenacity) have ClassMask 0 and are
    excluded, which is why 33 rows yield 30 trees.
    """
    path = getattr(config, "BASE_TALENTTAB_DBC_PATH", None)
    if not path or not os.path.exists(path):
        print("  WARNING: TalentTab.dbc not found; falling back to "
              "gen_sql.TALENT_TAB_INFO, which mislabels Paladin and Warrior "
              "and has no tree background art.")
        return [
            {"tabId": t, "class": c, "name": s, "order": p, "background": None}
            for t, (c, s, p) in gen_sql.TALENT_TAB_INFO.items()
        ]

    rows = S.read_dbc(path, S.TALENTTAB_COLUMNS, S.TALENTTAB_FMT, quiet=True)
    tabs = []
    for tab_id, row in rows.items():
        cls = CLASS_BY_MASK.get(row["ClassMask"])
        if not cls:
            continue
        tabs.append({
            "tabId": tab_id,
            "class": cls,
            "name": row["Name0"],
            "order": row["OrderIndex"],
            "background": (row["BackgroundFile"] or "").lower() or None,
        })
    return tabs


def load_icons():
    path = config.BASE_SPELLICON_DBC_PATH
    if not os.path.exists(path):
        print(f"  WARNING: SpellIcon.dbc not found at {path} -- "
              f"talents will export without icons")
        return {}
    rows = S.read_dbc(path, S.SPELLICON_COLUMNS, S.SPELLICON_FMT, quiet=True)
    # "Interface\Icons\Spell_Fire_Fireball02" -> "spell_fire_fireball02"
    return {i: r["TextureFilename"].replace("\\", "/").rsplit("/", 1)[-1].lower()
            for i, r in rows.items() if r["TextureFilename"]}


def load_baseline():
    """Pristine retail 3.3.5a DBCs, for the 'modified' diff.

    config.BASE_DBC_PATH is NOT pristine -- it carries pre-tooling manual
    edits -- so diffing against it under-reports.  Measured: 89 modified
    talents against base, 177 against retail.
    """
    spell_path = getattr(config, "RETAIL_DBC_PATH", None)
    talent_path = getattr(config, "RETAIL_TALENT_DBC_PATH", None)
    if not spell_path or not os.path.exists(spell_path):
        print("  WARNING: retail baseline not found; falling back to "
              "dbc/base/, which already contains pre-tooling edits. "
              "The 'modified' counts will UNDER-report.")
        spell_path = config.BASE_DBC_PATH
        talent_path = config.BASE_TALENT_DBC_PATH
    spells = S.load_spell_index(spell_path)
    talents, _ = read_int_dbc(talent_path, TALENT_FIELD_COUNT,
                              TALENT_RECORD_SIZE)
    return spells, {t: dict(zip(TALENT_COLUMNS, v)) for t, v in talents.items()}


def dbc_fingerprint(paths):
    """Hash the source DBCs so --check can detect a stale export."""
    h = hashlib.sha256()
    for p in paths:
        if os.path.exists(p):
            h.update(os.path.basename(p).encode())
            h.update(str(os.path.getsize(p)).encode())
            with open(p, "rb") as f:
                h.update(f.read(1 << 20))
    return h.hexdigest()[:16]


# ── Diffing ────────────────────────────────────────────────────────────────


def diff_talent(talent_row, base_talent, live_spells, base_spells):
    """Return (modified, kind, detail, base_name) for one talent."""
    detail = []
    kind = None

    def bump(k):
        nonlocal kind
        if kind is None or KIND_PRIORITY[k] > KIND_PRIORITY[kind]:
            kind = k

    if base_talent is None:
        return True, "new", ["talent"], None

    structural = [c for c in TALENT_COLUMNS
                  if c != "ID" and talent_row.get(c) != base_talent.get(c)]
    if structural:
        bump("structure")
        detail.extend(structural)

    base_name = None
    for i in range(1, 10):
        sid = talent_row.get(f"SpellRank_{i}", 0)
        if not sid:
            continue
        live = live_spells.get(sid)
        base = base_spells.get(sid)
        if live is None:
            continue
        if base is None:
            bump("new")
            continue
        changed = [c for c in DIFF_COLUMNS if base.get(c) != live.get(c)]
        if not changed:
            continue
        detail.extend(changed)
        if NAME_COLUMNS & set(changed):
            bump("renamed")
            if base_name is None and base.get("SpellName0") != live.get("SpellName0"):
                base_name = base.get("SpellName0")
        elif TEXT_COLUMNS & set(changed):
            bump("description")
        else:
            bump("values")

    if kind is None:
        return False, None, [], None
    # Preserve first-seen order while removing duplicates across ranks.
    return True, kind, list(dict.fromkeys(detail)), base_name


# ── Export ─────────────────────────────────────────────────────────────────


def build_tree(tab, talent_records, live_spells,
               base_spells, base_talents, icons, aux, stats):
    tab_id, tree_name, page = tab["tabId"], tab["name"], tab["order"]
    # _build_talent_tree defines the canonical (tier, col) ordering, and that
    # ordering IS the talent-link wire format -- digit i of a build string
    # addresses talents[i].  Anything that reorders it silently invalidates
    # every shared link, so we take the order from there rather than re-sorting.
    ordered = gen_sql._build_talent_tree(talent_records, tab_id, live_spells)

    by_location = {}
    for entry in ordered:
        by_location[entry["talent_id"]] = (entry["tier"], entry["col"])

    talents = []
    for i, entry in enumerate(ordered):
        tid = entry["talent_id"]
        row = talent_records[tid]

        spell_ids = [row[f"SpellRank_{r}"] for r in range(1, 10)
                     if row.get(f"SpellRank_{r}", 0)]

        ranks = []
        for r, sid in enumerate(spell_ids, start=1):
            spell = live_spells.get(sid)
            if spell is None:
                stats["dangling_ranks"].append((tid, r, sid))
                continue
            raw = spell.get("SpellDescription0", "") or ""
            desc, unresolved = T.resolve(raw, spell, aux)
            stats["descriptions"] += 1
            if unresolved:
                stats["with_unresolved"] += 1
                for tok in unresolved:
                    stats["tokens"][re.sub(r"\d+", "#", tok)] += 1
            rank = {"r": r, "spell": sid, "desc": desc}
            if raw != desc:
                rank["raw"] = raw
            if unresolved:
                rank["unresolved"] = sorted(set(unresolved))
            ranks.append(rank)

        first = live_spells.get(spell_ids[0]) if spell_ids else None
        icon_id = first.get("SpellIconID", 0) if first else 0
        # Retail ships a few empty talent rows (e.g. 2085, DK Unholy 6/3).
        # Keep the array slot -- dropping it would shift every later index and
        # silently invalidate build links -- but mark it so the UI hides it.
        placeholder = not spell_ids

        modified, kind, detail, base_name = diff_talent(
            row, base_talents.get(tid), live_spells, base_spells)

        talent = {
            "i": i,
            "id": tid,
            "fieldName": field_name(entry["name"]),
            "location": {"rowIdx": entry["tier"], "colIdx": entry["col"]},
            "spellIds": spell_ids,
            "maxPoints": entry["max_rank"],
            "name": entry["name"],
            "icon": icons.get(icon_id),
            "ranks": ranks,
        }
        if placeholder:
            talent["placeholder"] = True

        prereq_id = row.get("PrereqTalent_1", 0)
        if prereq_id and prereq_id in by_location:
            tier, col = by_location[prereq_id]
            talent["prereqLocation"] = {"rowIdx": tier, "colIdx": col}
            talent["prereqRank"] = row.get("PrereqRank_1", 0) + 1
        elif prereq_id:
            stats["bad_prereqs"].append((tid, prereq_id))

        if modified:
            talent["modified"] = True
            talent["modKind"] = kind
            talent["modDetail"] = detail
            if base_name:
                talent["baseName"] = base_name
            stats["modified_kinds"][kind] += 1

        talents.append(talent)

    return {
        "tabId": tab_id,
        "name": tree_name,
        "page": page,
        "background": tab.get("background"),
        "talents": talents,
    }


def export(args):
    spell_path, talent_path = gen_sql.resolve_dbc_paths(args.source)
    print(f"  Source: {args.source} ({spell_path})")

    live_spells = S.load_spell_index(spell_path)
    live_talents_raw, _ = read_int_dbc(talent_path, TALENT_FIELD_COUNT,
                                       TALENT_RECORD_SIZE)
    live_talents = {t: dict(zip(TALENT_COLUMNS, v))
                    for t, v in live_talents_raw.items()}

    base_spells, base_talents = load_baseline()
    icons = load_icons()
    aux = load_aux(live_spells)

    stats = {
        "descriptions": 0,
        "with_unresolved": 0,
        "tokens": collections.Counter(),
        "modified_kinds": collections.Counter(),
        "dangling_ranks": [],
        "bad_prereqs": [],
    }

    # Group the 30 tabs by class, in the DBC's own tab order.
    by_class = collections.OrderedDict()
    for tab in sorted(load_tabs(), key=lambda t: (t["class"], t["order"])):
        by_class.setdefault(tab["class"], []).append(tab)

    files = {}
    class_index = []
    for cls, tabs in by_class.items():
        trees = [
            build_tree(tab, live_talents, live_spells, base_spells,
                       base_talents, icons, aux, stats)
            for tab in sorted(tabs, key=lambda t: t["order"])
        ]
        key = class_key(cls)
        modified = sum(1 for tree in trees for t in tree["talents"]
                       if t.get("modified"))
        files[f"{key}.json"] = {
            "schema": SCHEMA_VERSION,
            "key": key,
            "name": cls,
            "trees": trees,
        }
        class_index.append({
            "key": key,
            "name": cls,
            "file": f"{key}.json",
            "trees": [t["name"] for t in sorted(tabs, key=lambda t: t["order"])],
            "talents": sum(len(tree["talents"]) for tree in trees),
            "modified": modified,
        })

    total_talents = sum(c["talents"] for c in class_index)
    total_modified = sum(c["modified"] for c in class_index)

    files["index.json"] = {
        "schema": SCHEMA_VERSION,
        "generated": args.stamp,
        "source": args.source,
        "fingerprint": dbc_fingerprint([spell_path, talent_path]),
        "iconBase": "./assets/icons/",
        "maxPoints": MAX_TALENT_POINTS,
        "classes": class_index,
        "degraded": aux.missing(),
        "stats": {
            "talents": total_talents,
            "talentsModified": total_modified,
            "descriptions": stats["descriptions"],
            "descriptionsWithUnresolved": stats["with_unresolved"],
            "modifiedKinds": dict(sorted(stats["modified_kinds"].items())),
        },
    }

    return files, stats


# ── Validation ─────────────────────────────────────────────────────────────


def validate(files, stats):
    """Structural assertions.

    Split into errors (the site will render wrongly) and warnings (odd data
    that retail 3.3.5a also ships, so it is not ours to fix).
    """
    errors = []
    warnings = []
    index = files["index.json"]

    if len(index["classes"]) != 10:
        errors.append(f"expected 10 classes, got {len(index['classes'])}")

    for entry in index["classes"]:
        data = files[entry["file"]]
        if len(data["trees"]) != 3:
            errors.append(f"{entry['key']}: {len(data['trees'])} trees, expected 3")
        for tree in data["trees"]:
            where = f"{entry['key']}/{tree['name']}"
            seen = set()
            locations = {(t["location"]["rowIdx"], t["location"]["colIdx"])
                         for t in tree["talents"]}
            for i, t in enumerate(tree["talents"]):
                # The link format addresses talents by array index; if `i`
                # ever disagrees with the position, every shared build URL
                # for this class decodes to a different build.
                if t["i"] != i:
                    errors.append(
                        f"{where}: talent {t['id']} has i={t['i']} at position {i}")
                loc = (t["location"]["rowIdx"], t["location"]["colIdx"])
                if loc in seen:
                    errors.append(f"{where}: duplicate location {loc}")
                seen.add(loc)
                if t["location"]["colIdx"] not in (0, 1, 2, 3):
                    errors.append(
                        f"{where}: talent {t['id']} colIdx "
                        f"{t['location']['colIdx']} out of range")

                if t.get("placeholder"):
                    warnings.append(
                        f"{where}: talent {t['id']} at {loc} has no spell ranks "
                        f"(present in retail too; hidden in the UI, index kept "
                        f"so build links stay stable)")
                elif len(t["spellIds"]) != t["maxPoints"]:
                    errors.append(
                        f"{where}: talent {t['id']} has {len(t['spellIds'])} "
                        f"spells but maxPoints {t['maxPoints']}")

                dupes = [s for s, n in collections.Counter(t["spellIds"]).items()
                         if n > 1]
                if dupes:
                    errors.append(
                        f"{where}: talent {t['id']} ({t['name']}) repeats spell "
                        f"{dupes} across ranks -- maxPoints {t['maxPoints']} is "
                        f"too high")

                pre = t.get("prereqLocation")
                if pre:
                    if (pre["rowIdx"], pre["colIdx"]) not in locations:
                        errors.append(
                            f"{where}: talent {t['id']} prereq {pre} not in this tree")
                    elif pre["rowIdx"] > t["location"]["rowIdx"]:
                        # Same-tier prereqs are legitimate: Warrior's Deep
                        # Wounds (tier 2 col 3) requires Impale (tier 2 col 2).
                        errors.append(
                            f"{where}: talent {t['id']} prereq is below it")

    for tid, rank, sid in stats["dangling_ranks"]:
        errors.append(f"talent {tid} rank {rank} references missing spell {sid}")
    for tid, pid in stats["bad_prereqs"]:
        warnings.append(
            f"talent {tid} names prereq {pid}, which is not a talent in its tree "
            f"(retail 3.3.5a ships the same dangling reference)")

    return errors, warnings


# ── Output ─────────────────────────────────────────────────────────────────


def serialize(payload):
    # Pretty-printed on purpose: a readable git diff is worth more than the
    # ~100 KB, and Pages gzips the response anyway.
    return json.dumps(payload, indent=1, ensure_ascii=False) + "\n"


def write_files(files, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    for name, payload in files.items():
        # newline="\n" so the file on disk matches what git stores. The repo's
        # .gitattributes sets `* text eol=lf`, so letting Python write CRLF on
        # Windows would make a fresh checkout differ from a fresh export and
        # --check would cry "stale" every time.
        with open(os.path.join(out_dir, name), "w",
                  encoding="utf-8", newline="\n") as f:
            f.write(serialize(payload))


def check_files(files, out_dir):
    stale = []
    for name, payload in files.items():
        path = os.path.join(out_dir, name)
        if not os.path.exists(path):
            stale.append(f"{name} (missing)")
            continue
        with open(path, encoding="utf-8") as f:
            if f.read() != serialize(payload):
                stale.append(name)
    return stale


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", choices=("base", "live"), default="live",
                   help="which DBCs to read (default: live)")
    p.add_argument("--live-dir",
                   help="override the live DBC directory")
    p.add_argument("--out", default=SITE_DATA,
                   help=f"output directory (default: {SITE_DATA})")
    p.add_argument("--stamp", default="",
                   help="value for index.json 'generated' (default: file mtime of Spell.dbc)")
    p.add_argument("--validate", action="store_true",
                   help="run structural assertions and exit non-zero on failure")
    p.add_argument("--check", action="store_true",
                   help="do not write; exit non-zero if committed data is stale")
    p.add_argument("--report-tokens", action="store_true",
                   help="print a tooltip-token census")
    args = p.parse_args()

    if args.live_dir:
        gen_sql.LIVE_DBC_DIR = args.live_dir

    if not args.stamp:
        spell_path, _ = gen_sql.resolve_dbc_paths(args.source)
        import datetime
        args.stamp = datetime.datetime.utcfromtimestamp(
            os.path.getmtime(spell_path)).strftime("%Y-%m-%dT%H:%M:%SZ")

    print("=" * 60)
    print("  Alonecraft Talent Export")
    print("=" * 60)

    files, stats = export(args)
    index = files["index.json"]
    s = index["stats"]

    print(f"\n  Classes:   {len(index['classes'])}")
    print(f"  Talents:   {s['talents']}  ({s['talentsModified']} modified)")
    print(f"  Kinds:     {s['modifiedKinds']}")
    resolved = s["descriptions"] - s["descriptionsWithUnresolved"]
    pct = 100.0 * resolved / s["descriptions"] if s["descriptions"] else 0
    print(f"  Tooltips:  {resolved}/{s['descriptions']} fully resolved ({pct:.1f}%)")
    if index["degraded"]:
        print(f"  DEGRADED:  missing index DBCs for {index['degraded']}")

    print("\n  Modified talents per class:")
    for c in index["classes"]:
        print(f"    {c['name']:<14} {c['modified']:>3} / {c['talents']}")

    if args.report_tokens:
        print("\n  Unresolved token census:")
        for tok, n in stats["tokens"].most_common(30):
            print(f"    {tok:<20} {n}")

    errors, warnings = validate(files, stats)
    if warnings:
        print(f"\n  NOTES ({len(warnings)}):")
        for msg in warnings[:10]:
            print(f"    - {msg}")
        if len(warnings) > 10:
            print(f"    ... and {len(warnings) - 10} more")
    if errors:
        print(f"\n  VALIDATION FAILED: {len(errors)} error(s)")
        for msg in errors[:25]:
            print(f"    - {msg}")
        if len(errors) > 25:
            print(f"    ... and {len(errors) - 25} more")
    else:
        print("\n  VALIDATION: all checks passed")

    if args.validate and errors:
        return 1

    if args.check:
        stale = check_files(files, args.out)
        if stale:
            print(f"\n  STALE: {len(stale)} file(s) differ from a fresh export:")
            for name in stale:
                print(f"    - {name}")
            print("  Run: python tools/export_talents.py")
            return 1
        print("\n  Committed data is up to date.")
        return 0

    write_files(files, args.out)
    print(f"\n  Wrote {len(files)} files to {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
