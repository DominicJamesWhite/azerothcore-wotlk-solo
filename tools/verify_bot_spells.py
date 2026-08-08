#!/usr/bin/env python3
"""
Playerbot Spell-Name Consistency Checker

mod-playerbots addresses spells by *name*, not by id.  SpellIdValue::Calculate
(src/Ai/Base/Value/SpellIdValue.cpp) scans the bot's spellbook for an exact,
case-insensitive, equal-length match on SpellInfo->SpellName[LOCALE_enUS].
When Alonecraft renames a spell in the DBC, the bot action silently resolves
to 0 and never fires -- no log line, no error, no crash.  The bot just stands
there.

This tool finds those dead actions statically, by extracting every spell-name
literal from the playerbots source and resolving it against the live Spell.dbc
using the same matching rule.  When a name is dead but *did* exist in retail,
it diffs retail against live to name the spell that replaced it, so the fix is
spelled out rather than guessed at.

Four buckets are reported:

  DEAD / ALONECRAFT REGRESSION  existed in retail, gone now -- our bug, and the
                                only bucket --check fails on
  DEAD / PRE-EXISTING UPSTREAM  absent from retail 3.3.5a too, mostly abilities
                                removed in patch 3.0.2 -- upstream debt
  CHANGED                       still resolves, but the spell's effects differ
                                from retail, so the rotation's assumptions may
                                no longer hold
  UNCOVERED                     custom spells no action mentions -- the reverse
                                gap, abilities bots were never taught

The last one matters most after a redesign: a bot cannot fail to cast Bladework
by name, it simply never tries, so no name-matching check would ever see it.

Usage:
    python tools/verify_bot_spells.py                 # full report
    python tools/verify_bot_spells.py --class warlock # one class
    python tools/verify_bot_spells.py --check         # non-zero exit if dead
    python tools/verify_bot_spells.py --json          # machine-readable

Exit codes:
    0  no dead actions (or --check not given)
    1  dead actions found and --check was given
    2  could not run (missing DBC, missing playerbots module)
"""

import argparse
import contextlib
import json
import os
import re
import sys
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLAYERBOTS = os.path.join(REPO_ROOT, "modules", "mod-playerbots")
PB_SRC = os.path.join(PLAYERBOTS, "src")
AI_OBJECT_H = os.path.join(PB_SRC, "Bot", "Engine", "AiObject.h")
CLASS_DIR = os.path.join(PB_SRC, "Ai", "Class")

sys.path.insert(0, os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc"))
import config  # noqa: E402
from spell_dbc import load_spell_index  # noqa: E402

LIVE_DBC_DIR = r"C:\Build\bin\RelWithDebInfo\Data\dbc"

# Columns that change how a spell *behaves*, as opposed to how it reads.  A
# rotation entry pointing at a spell whose effects moved still fires, but it no
# longer does what the strategy author assumed -- worth a look, not an error.
# Mirrors DIFF_COLUMNS in tools/export_talents.py minus the pure-text ones.
BEHAVIOUR_COLUMNS = (
    ["ProcChance", "StackAmount", "DurationIndex", "RangeIndex",
     "CastingTimeIndex", "ManaCost", "RecoveryTime", "CategoryRecoveryTime"]
    + [f"{c}{i}"
       for c in ("EffectBasePoints", "EffectDieSides", "EffectAmplitude",
                 "Effect", "EffectApplyAuraName", "EffectChainTarget",
                 "EffectTriggerSpell")
       for i in (1, 2, 3)]
)

# SpellFamilyName -> the Ai/Class directory that owns it.  Used to attribute a
# custom spell to a class so "which of our new abilities do bots not know?" can
# be answered per class.
SPELL_FAMILY_TO_CLASS = {
    3: "mage", 4: "warrior", 5: "warlock", 6: "priest", 7: "druid",
    8: "rogue", 9: "hunter", 10: "paladin", 11: "shaman", 15: "dk",
}

CUSTOM_SPELL_MIN = 200000        # Alonecraft's reserved id range
SPELL_ATTR0_PASSIVE = 0x40
SPELL_ATTR0_HIDDEN_CLIENTSIDE = 0x80   # DO_NOT_DISPLAY

# Strategy strings that name an engine behaviour rather than a spell.  These
# are the ones NextAction() legitimately references without a creators[] entry
# in a *class* context -- they are registered in the shared Ai/Base contexts.
# Kept short on purpose: anything else unregistered is a real finding.
NON_SPELL_ACTION_HINTS = {
    "melee", "flee", "reach spell", "reach melee", "attack anything",
    "shoot", "add aura trigger", "drop target", "stay", "follow",
}


# ---------------------------------------------------------------------------
# Source extraction
# ---------------------------------------------------------------------------

DEFINE_RE = re.compile(
    r"^#define\s+([A-Z_0-9]+)\(\s*clazz\s*,\s*(\w+)[^)]*\)(.*?)(?=^#define|\Z)",
    re.MULTILINE | re.DOTALL)


def discover_spell_carriers(path):
    """Return (macro names, base class names) that carry a spell name.

    Both are read out of AiObject.h rather than hardcoded, so a macro added
    upstream is covered automatically instead of silently going unchecked.

    Each macro body looks like

        clazz(PlayerbotAI* botAI) : SomeBase(botAI, spell) {}

    so the same parse yields the macro name *and* the base class it forwards
    to.  The base classes matter because much of the codebase does not use the
    macros at all -- it hand-writes the class when it needs an extra override,
    and every Alonecraft customisation so far is hand-written:

        CastAegisOfAntonidasAction(PlayerbotAI* botAI)
            : CastBuffSpellAction(botAI, "aegis of antonidas") {}

    A macro-only scan misses all of those.
    """
    if not os.path.isfile(path):
        return set(), set()
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    macros, bases = set(), set()
    for macro, arg, body in DEFINE_RE.findall(text):
        # The body must actually forward that argument to a base constructor;
        # BEGIN_TRIGGER(clazz, super) takes a class, not a spell name.
        m = re.search(r":\s*(\w+)\(\s*botAI\s*,\s*" + re.escape(arg) + r"\b", body)
        if not m:
            continue
        macros.add(macro)
        bases.add(m.group(1))
    return macros, bases


def strip_comments(text):
    """Remove /* */ and // comments so commented-out code is not reported."""
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//[^\n]*", "", text)


def iter_sources(root):
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in sorted(filenames):
            if fn.endswith((".cpp", ".h")):
                yield os.path.join(dirpath, fn)


def class_of(path):
    """'…/src/Ai/Class/Warlock/Strategy/Foo.cpp' -> 'warlock'; else 'shared'."""
    rel = os.path.relpath(path, PB_SRC).replace("\\", "/")
    parts = rel.split("/")
    if len(parts) > 2 and parts[0] == "Ai" and parts[1] == "Class":
        return parts[2].lower()
    return "shared"


def extract(macros, bases):
    """Scan the playerbots source once.

    Returns (declared, registered, referenced):
      declared   [{name, via, file, line, cls}]  spell-name literals
      registered {action-or-trigger name -> [(file, line)]}   creators[...]
      referenced [{name, file, line, cls}]       NextAction("...")

    Matching runs over whole-file text, not line by line: these invocations are
    routinely wrapped across lines by the formatter.
    """
    macro_re = re.compile(
        r"\b(" + "|".join(sorted(macros)) + r")\s*\(\s*\w+\s*,\s*\"([^\"]+)\""
    ) if macros else None
    # The constructor parameter is not always called botAI -- the Warlock and
    # Rogue files use 'ai' -- so match any identifier. Anchoring on the base
    # class name keeps this from matching unrelated constructor calls.
    base_re = re.compile(
        r":\s*(" + "|".join(sorted(bases)) + r")\s*\(\s*\w+\s*,\s*\"([^\"]+)\""
    ) if bases else None
    creators_re = re.compile(r'creators\[\s*"([^"]+)"\s*\]')
    nextaction_re = re.compile(r'NextAction\(\s*"([^"]+)"')

    declared, referenced = [], []
    registered = defaultdict(list)

    for path in iter_sources(PB_SRC):
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            text = strip_comments(fh.read())
        rel = os.path.relpath(path, REPO_ROOT)
        cls = class_of(path)

        def lineno_at(pos):
            return text.count("\n", 0, pos) + 1

        for rx in (r for r in (macro_re, base_re) if r):
            for m in rx.finditer(text):
                declared.append({"name": m.group(2), "via": m.group(1),
                                 "file": rel, "line": lineno_at(m.start()),
                                 "cls": cls})
        for m in creators_re.finditer(text):
            registered[m.group(1)].append((rel, lineno_at(m.start())))
        for m in nextaction_re.finditer(text):
            referenced.append({"name": m.group(1), "file": rel,
                               "line": lineno_at(m.start()), "cls": cls})

    return declared, registered, referenced


# ---------------------------------------------------------------------------
# DBC resolution
# ---------------------------------------------------------------------------

def load_names(path):
    """Return ({casefolded name -> [spell ids]}, {spell id -> row}).

    read_base_dbc chatters on stdout; send that to stderr so --json stays
    machine-readable.
    """
    with contextlib.redirect_stdout(sys.stderr):
        index = load_spell_index(path)
    by_name = defaultdict(list)
    for sid, row in index.items():
        name = row.get("SpellName0")
        if name:
            by_name[name.casefold()].append(sid)
    return by_name, index


def resolve_live_dbc():
    spell = os.path.join(LIVE_DBC_DIR, "Spell.dbc")
    if os.path.exists(spell):
        return spell, "live"
    fallback = os.path.join(REPO_ROOT, "modules", "world_of_alonecraft",
                            "dbc", "output", "Spell.dbc")
    if os.path.exists(fallback):
        return fallback, "output"
    return None, None


def behaviour_changed(retail_row, live_row):
    if retail_row is None or live_row is None:
        return []
    return [c for c in BEHAVIOUR_COLUMNS
            if retail_row.get(c) != live_row.get(c)]


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def analyse(declared, registered, referenced, live_by_name, live_index,
            retail_by_name, retail_index):
    """Bucket every extracted name into dead / changed / unregistered."""
    dead, changed = [], []

    # One entry per distinct (class, name); a name declared in several files is
    # one finding with several sites, not several findings.
    sites = defaultdict(list)
    for d in declared:
        sites[(d["cls"], d["name"])].append(d)

    for (cls, name), entries in sorted(sites.items()):
        key = name.casefold()
        if key in live_by_name:
            ids = live_by_name[key]
            detail = []
            for sid in ids:
                cols = behaviour_changed(retail_index.get(sid),
                                         live_index.get(sid))
                if cols:
                    detail.append((sid, cols))
            # A name that only exists post-Alonecraft is new, not "changed".
            brand_new = key not in retail_by_name
            if detail or brand_new:
                changed.append({
                    "cls": cls, "name": name, "ids": sorted(ids),
                    "new": brand_new,
                    "columns": sorted({c for _, cols in detail for c in cols}),
                    "sites": [(e["file"], e["line"]) for e in entries],
                })
            continue

        # Dead. If retail knew the name, say what those ids are called now.
        renamed_to = []
        for sid in retail_by_name.get(key, []):
            live_row = live_index.get(sid)
            if live_row and live_row.get("SpellName0"):
                renamed_to.append((sid, live_row["SpellName0"]))
        dead.append({
            "cls": cls, "name": name,
            "via": entries[0]["via"],
            "existed_in_retail": key in retail_by_name,
            "renamed_to": sorted(set(renamed_to), key=lambda t: t[0]),
            "sites": [(e["file"], e["line"]) for e in entries],
        })

    # A NextAction naming an action nobody registers can never run.
    unregistered = []
    seen = set()
    for r in referenced:
        name = r["name"]
        if name in registered or name in NON_SPELL_ACTION_HINTS:
            continue
        # "spellname::target" and "emote::helpme" style qualifiers.
        if "::" in name and name.split("::", 1)[0] in registered:
            continue
        if (r["cls"], name) in seen:
            continue
        seen.add((r["cls"], name))
        unregistered.append(r)

    return dead, changed, unregistered


SITE_DATA = os.path.join(REPO_ROOT, "site", "data")


def load_talent_spells():
    """Return {spell id -> class key} for every talent rank.

    Two uses.  First, attribution: most custom spells carry SpellFamilyName 0,
    so the family map alone dumps them in "unknown".  Second, and more
    important, exclusion: a talent's own rank ids are the passive aura the
    talent applies, not a button.  Gnosticism and Chillblains are talents, and
    reporting them as abilities the bots should press is noise.

    An active ability *granted* by a talent keeps a separate spell id that does
    not appear in the talent's spellIds, so it survives this filter -- which is
    the behaviour we want (Infernal Bargain the talent is 63349; Infernal
    Bargain the castable is 200405, and only the latter is a button).
    """
    mapping = {}
    if not os.path.isdir(SITE_DATA):
        return mapping
    for fn in sorted(os.listdir(SITE_DATA)):
        if not fn.endswith(".json") or fn == "index.json":
            continue
        with open(os.path.join(SITE_DATA, fn), "r", encoding="utf-8") as fh:
            data = json.load(fh)
        key = data.get("key", os.path.splitext(fn)[0])
        # 'death-knight' in the export, 'Dk' as the Ai/Class directory.
        cls = "dk" if key == "death-knight" else key
        for tree in data.get("trees", []):
            for talent in tree.get("talents", []):
                for sid in talent.get("spellIds", []):
                    mapping[sid] = cls
    return mapping


def find_uncovered(declared, live_index, talent_spells):
    """Alonecraft abilities that no bot action mentions.

    The dead/changed buckets can only judge names the bots already use, so they
    are blind to the opposite failure: an ability shipped for players that the
    bots were simply never taught.  That is the larger gap after a redesign --
    a bot cannot fail to cast Bladework by name, it just never tries.

    Approach the other way round: walk the custom id range, keep the spells a
    player could actually press, and report the ones with no matching literal.
    """
    known = {d["name"].casefold() for d in declared}
    uncovered = defaultdict(list)

    for sid, row in live_index.items():
        if sid < CUSTOM_SPELL_MIN:
            continue
        name = row.get("SpellName0")
        if not name:
            continue
        attrs = row.get("Attributes") or 0
        # Passive and client-hidden rows are plumbing (proc carriers, aura
        # holders), not buttons -- a bot has nothing to press.
        if attrs & (SPELL_ATTR0_PASSIVE | SPELL_ATTR0_HIDDEN_CLIENTSIDE):
            continue
        if sid in talent_spells:      # a talent rank, not a button
            continue
        if name.casefold() in known:
            continue
        cls = (SPELL_FAMILY_TO_CLASS.get(row.get("SpellFamilyName"))
               or talent_spells.get(sid)
               or "unattributed")
        uncovered[cls].append((sid, name))

    for cls in uncovered:
        # One row per name: ranks share a name and are one ability to teach.
        seen, rows = set(), []
        for sid, name in sorted(uncovered[cls]):
            if name.casefold() in seen:
                continue
            seen.add(name.casefold())
            rows.append((sid, name))
        uncovered[cls] = rows
    return dict(uncovered)


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def report(dead, changed, unregistered, uncovered, only_class, source_label):
    def keep(item):
        return not only_class or item["cls"] == only_class

    dead = [d for d in dead if keep(d)]
    changed = [c for c in changed if keep(c)]
    unregistered = [u for u in unregistered if keep(u)]

    print("Playerbot spell-name audit")
    print(f"  Spell.dbc source: {source_label}")
    print(f"  Baseline:         retail ({config.RETAIL_DBC_PATH})")
    print()

    # Two very different problems share the "name resolves to nothing" symptom.
    # Only the first is ours, and only the first should ever fail --check.
    regressions = [d for d in dead if d["existed_in_retail"]]
    preexisting = [d for d in dead if not d["existed_in_retail"]]

    print(f"DEAD -- ALONECRAFT REGRESSION ({len(regressions)})")
    print("  Existed in retail 3.3.5a, gone now. The bot will never cast it.")
    if not regressions:
        print("  none")
    for d in sorted(regressions, key=lambda x: (x["cls"], x["name"])):
        print(f"  [{d['cls']}] \"{d['name']}\"  ({d['via']})")
        if d["renamed_to"]:
            for sid, newname in d["renamed_to"]:
                print(f"      spell {sid} is now named \"{newname}\" -- rename the literal")
        else:
            print("      no live spell carries that id -- the spell was removed outright")
        for f, ln in d["sites"]:
            print(f"      {f}:{ln}")
    print()

    print(f"DEAD -- PRE-EXISTING UPSTREAM ({len(preexisting)})")
    print("  Absent from retail 3.3.5a too (mostly abilities removed in 3.0.2).")
    print("  Upstream debt, not caused by Alonecraft. Does not fail --check.")
    if not preexisting:
        print("  none")
    for d in sorted(preexisting, key=lambda x: (x["cls"], x["name"])):
        sites = ", ".join(f"{f}:{ln}" for f, ln in d["sites"])
        print(f"  [{d['cls']}] \"{d['name']}\"  ({d['via']})  {sites}")
    print()

    print(f"CHANGED ({len(changed)}) -- resolves, but the spell is not retail's")
    if not changed:
        print("  none")
    for c in sorted(changed, key=lambda x: (x["cls"], x["name"])):
        tag = "NEW" if c["new"] else "modified"
        cols = ", ".join(c["columns"][:6])
        more = f" (+{len(c['columns']) - 6} more)" if len(c["columns"]) > 6 else ""
        print(f"  [{c['cls']}] \"{c['name']}\"  {tag}  ids={c['ids'][:4]}")
        if cols:
            print(f"      differs: {cols}{more}")
    print()

    print(f"UNREGISTERED ({len(unregistered)}) -- NextAction with no creators[] entry")
    if not unregistered:
        print("  none")
    for u in sorted(unregistered, key=lambda x: (x["cls"], x["name"])):
        print(f"  [{u['cls']}] \"{u['name']}\"   {u['file']}:{u['line']}")
    print()

    total_uncovered = sum(len(v) for c, v in uncovered.items()
                          if not only_class or c == only_class)
    print(f"UNCOVERED ({total_uncovered}) -- Alonecraft custom spells no bot action names")
    print("  Abilities the bots were never taught, rather than broken ones. This is")
    print("  a review list, not a to-do list: the DBC cannot reliably distinguish a")
    print("  button from a passive carrier (none of these set ATTR0_PASSIVE), so")
    print("  proc carriers and talent auras appear here too. Skim it per class.")
    if not total_uncovered:
        print("  none")
    for cls in sorted(uncovered):
        if only_class and cls != only_class:
            continue
        print(f"  [{cls}]")
        for sid, name in uncovered[cls]:
            print(f"      {sid:>6}  {name}")
    print()

    return len(regressions)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--class", dest="only_class",
                    help="restrict the report to one class (warlock, rogue, ...)")
    ap.add_argument("--check", action="store_true",
                    help="exit non-zero when dead actions are found")
    ap.add_argument("--json", action="store_true",
                    help="emit machine-readable JSON instead of a report")
    args = ap.parse_args()

    if not os.path.isdir(PB_SRC):
        print(f"ERROR: mod-playerbots not found at {PLAYERBOTS}", file=sys.stderr)
        print("       Is the submodule checked out?", file=sys.stderr)
        return 2

    live_path, kind = resolve_live_dbc()
    if not live_path:
        print("ERROR: no live Spell.dbc found.", file=sys.stderr)
        print(f"       Looked in {LIVE_DBC_DIR} and dbc/output/.", file=sys.stderr)
        print("       Build the DBC first: build_and_run.bat --skip-build", file=sys.stderr)
        return 2
    if not os.path.exists(config.RETAIL_DBC_PATH):
        print(f"ERROR: retail baseline missing at {config.RETAIL_DBC_PATH}",
              file=sys.stderr)
        return 2

    macros, bases = discover_spell_carriers(AI_OBJECT_H)
    if not macros:
        print(f"ERROR: no spell macros discovered in {AI_OBJECT_H}", file=sys.stderr)
        return 2

    declared, registered, referenced = extract(macros, bases)
    live_by_name, live_index = load_names(live_path)
    retail_by_name, retail_index = load_names(config.RETAIL_DBC_PATH)

    dead, changed, unregistered = analyse(
        declared, registered, referenced,
        live_by_name, live_index, retail_by_name, retail_index)
    uncovered = find_uncovered(declared, live_index, load_talent_spells())

    only = args.only_class.lower() if args.only_class else None

    if args.json:
        json.dump({"macros": sorted(macros), "bases": sorted(bases),
                   "declaredCount": len(declared),
                   "dead": dead, "changed": changed,
                   "unregistered": unregistered, "uncovered": uncovered},
                  sys.stdout, indent=2)
        print()
        dead_count = len([d for d in dead
                          if d["existed_in_retail"]
                          and (not only or d["cls"] == only)])
    else:
        print(f"  {len(macros)} macros / {len(bases)} base classes, "
              f"{len(declared)} name literals, "
              f"{len(registered)} registered creators")
        dead_count = report(dead, changed, unregistered, uncovered, only,
                            f"{kind} ({live_path})")

    if args.check and dead_count:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
