#!/usr/bin/env python3
"""
Random-property tier extension.

Vanilla items carry their "of the Eagle" bonus as an ItemRandomProperty: a fixed
enchantment, chosen from a per-slot ladder of tiers.  Blizzard retired the
mechanism at the vanilla/TBC boundary -- NO item above required level 60 uses
RandomProperty at all -- so an upgraded green hits a wall:

    GenerateEnchSuffixFactor (ItemEnchantmentMgr.cpp:131) returns 0 for anything
    without RandomSuffix, so the bonus cannot scale with ItemLevel the way a
    RandomSuffix item's does.  The variant reaches level 80 still wearing +5
    Intellect.

1701 of the 22927 upgrade candidates are affected -- exactly the low-level
greens.  Converting them to RandomSuffix was the obvious fix and is wrong: 23 of
the 45 property affix names have no suffix counterpart ("of Healing" alone
covers 1006 items), so 1509 items would silently change affix.

So instead this extends the ladder.  The structure is highly regular and the
extension is mechanical:

  * item_template.RandomProperty names a GROUP in item_enchantment_template.
  * Each group is a rolling window of ~4 consecutive tiers per affix, and each
    ladder is per (class, subclass, InventoryType) -- a cloth chest at level 20
    uses group 459, a cloth belt uses 879.  53 families, 773 groups in play.
  * Successive tiers step the enchantment amount by ~1 (of the Eagle on a cloth
    chest runs +1/+1 at group 454 up to +19/+19 at group 472, level 60).

For every family, each target level above where its native ladder stops gets a
synthesised group whose tiers are the family's strongest native tier scaled by
the ScalingStatValues ssdMultiplier ratio -- the same curve the item's own stats
are scaled by in gen_item_variants.py, so an affix keeps its share of the item's
budget instead of being frozen at its level-60 value.

Enchantment effect types are NOT interchangeable and are handled separately:

  * 5 STAT, 4 RESISTANCE, 2 DAMAGE -- the amount is the value.  Scale it.
  * 3 EQUIP_SPELL -- the amount is unused and the value lives in a SPELL
    ("of Arcane Wrath" points at spell 17849, +54 Arcane Spell Damage).  There
    is no stronger spell to point at, so one is cloned into alonecraft_spell_dbc
    with scaled base points.  Scaling the amount here would do nothing at all,
    silently.

Outputs (all additive; every DBC involved has a DB override table, the same
mechanism as item_dbc and itemlimitcategory_dbc):

  * spellitemenchantment_dbc   new enchantment rows
  * itemrandomproperties_dbc   new tier rows
  * item_enchantment_template  new groups
  * alonecraft_spell_dbc       cloned spells for type-3 affixes
  * alonecraft_random_affix    property -> affix id            (runtime lookup)
  * alonecraft_random_tier     (affix id, group) -> property   (runtime lookup)

The last two exist because ItemEnchantmentMgr keeps its group table in a file
static with no accessor, and reaching it would mean editing core.  The module
loads these instead, and the generator does all the name matching offline.

Usage:
    python tools/gen_random_property_tiers.py
    python tools/gen_random_property_tiers.py --dry-run
"""

import argparse
import collections
import os
import struct
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBC_DIR = os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc")
sys.path.insert(0, DBC_DIR)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config  # noqa: E402
import spell_dbc as S  # noqa: E402
from gen_item_variants import (  # noqa: E402
    MODULE_SQL, STEP_SIZE, MAX_LEVEL, SSV_SSD_MULT,
    get_db_connection, load_ssv, sql_str, next_sql_path,
)

# ── ID bands ────────────────────────────────────────────────────────────────
# Native maxima at time of writing: enchantment 3883, property 2164, group 8675.
# Generous gaps so a later Blizzard-data refresh cannot collide.
NEW_ENCH_BASE = 20000
NEW_PROP_BASE = 20000
NEW_GROUP_BASE = 30000
NEW_SPELL_BASE = 210000

# SpellItemEnchantment effect types (SharedDefines.h ItemEnchantmentType).
ENCH_TYPE_DAMAGE = 2
ENCH_TYPE_EQUIP_SPELL = 3
ENCH_TYPE_RESISTANCE = 4
ENCH_TYPE_STAT = 5
SCALABLE_AMOUNT = {ENCH_TYPE_DAMAGE, ENCH_TYPE_RESISTANCE, ENCH_TYPE_STAT}

CLIENT_DBC = os.path.join(config.BUILD_DBC_DIR) if hasattr(config, "BUILD_DBC_DIR") \
    else r"C:\Build\bin\RelWithDebInfo\Data\dbc"


# ── raw DBC reading ─────────────────────────────────────────────────────────
def read_raw(path):
    """(rows as int tuples, string accessor).  These two DBCs have no helper in
    spell_dbc.py, and only the id/effect/name columns are needed."""
    d = open(path, "rb").read()
    _, rec, fields, rsz, _ = struct.unpack("<4sIIII", d[:20])
    body, sb = d[20:20 + rec * rsz], d[20 + rec * rsz:]
    rows = [struct.unpack("<%dI" % fields, body[i * rsz:(i + 1) * rsz])
            for i in range(rec)]

    def s(off):
        if not off or off >= len(sb):
            return ""
        return sb[off:sb.index(b"\0", off)].decode("utf-8", "replace")
    return rows, s


def load_properties():
    """property id -> {name, enchants[]}.  Layout: ID, InternalName, Ench[5],
    Name[16], NameMask -- see ItemRandomPropertiesfmt in DBCfmt.h."""
    rows, s = read_raw(os.path.join(CLIENT_DBC, "ItemRandomProperties.dbc"))
    return {r[0]: {"name": s(r[7]), "ench": [e for e in r[2:7] if e]} for r in rows}


def load_enchants():
    """enchantment id -> raw tuple + decoded description.  Layout per
    SpellItemEnchantmentfmt: ID, charges, type[3], amountMin[3], amountMax[3],
    spellid[3], name[16], ..."""
    rows, s = read_raw(os.path.join(CLIENT_DBC, "SpellItemEnchantment.dbc"))
    out = {}
    for r in rows:
        out[r[0]] = {
            "raw": r,
            "type": list(r[2:5]),
            "amount": list(r[5:8]),
            "spellid": list(r[11:14]),
            "desc": s(r[14]),
        }
    return out


# ── the native ladder ───────────────────────────────────────────────────────
def fetch_ladders(conn):
    """(class, subclass, InventoryType) -> {required level: group}.

    Built from live items rather than assumed: a family's ladder is exactly the
    set of groups its own native items use, which is what makes the extension
    slot-correct without a hand-written slot table.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT class, subclass, InventoryType, RequiredLevel, RandomProperty, COUNT(*) "
        "FROM item_template "
        "WHERE entry < 1000000 AND Quality >= 2 AND class IN (2, 4) "
        "  AND RandomProperty <> 0 AND RandomSuffix = 0 AND RequiredLevel > 0 "
        "GROUP BY class, subclass, InventoryType, RequiredLevel, RandomProperty")
    ladders = collections.defaultdict(dict)
    counts = collections.defaultdict(collections.Counter)
    for cls, sub, inv, lvl, grp, n in cur.fetchall():
        counts[(cls, sub, inv)][(lvl, grp)] += n
    cur.close()
    for fam, c in counts.items():
        # One group per level: where a level has several (a few items disagree),
        # the most-used wins, then the highest group -- ties should favour the
        # stronger ladder, never a stale low tier.
        by_level = collections.defaultdict(list)
        for (lvl, grp), n in c.items():
            by_level[lvl].append((n, grp))
        for lvl, cands in by_level.items():
            ladders[fam][lvl] = max(cands)[1]
    return dict(ladders)


def fetch_groups(conn):
    """group -> [(property id, chance)]."""
    cur = conn.cursor()
    cur.execute("SELECT entry, ench, chance FROM item_enchantment_template")
    groups = collections.defaultdict(list)
    for entry, ench, chance in cur.fetchall():
        groups[entry].append((ench, float(chance)))
    cur.close()
    return dict(groups)


def strongest_per_affix(group_rows, props, enchants):
    """affix name -> (property id, total chance) for the strongest tier present.

    "Strongest" is the largest summed scalable amount, falling back to the
    highest property id.  Tiers within an affix are consecutive ids in ascending
    power, so the fallback is correct for the equip-spell affixes where the
    amount columns are all zero.
    """
    best = {}
    chance = collections.defaultdict(float)
    for pid, ch in group_rows:
        p = props.get(pid)
        if not p or not p["name"]:
            continue
        chance[p["name"]] += ch
        score = 0
        for eid in p["ench"]:
            e = enchants.get(eid)
            if e:
                score += sum(a for t, a in zip(e["type"], e["amount"])
                             if t in SCALABLE_AMOUNT)
        key = (score, pid)
        if p["name"] not in best or key > best[p["name"]][0]:
            best[p["name"]] = (key, pid)
    return {n: (pid, chance[n]) for n, (_, pid) in best.items()}


def build_group_map(conn):
    """(class, subclass, InventoryType, level) -> RandomProperty group.

    Shared with gen_item_variants.py so a variant's affix ladder and the tier
    table can never disagree about which group belongs to a level.

    At or below where a family's native ladder reaches, the answer is Blizzard's
    own group for the highest ladder level <= target.  Above it, the synthesised
    group -- keyed by the same deterministic id the emitter uses.
    """
    ladders = fetch_ladders(conn)
    fam_index = {fam: i for i, fam in enumerate(sorted(ladders))}
    out = {}
    for fam, ladder in ladders.items():
        top = max(ladder)
        for target in range(STEP_SIZE, MAX_LEVEL + 1, STEP_SIZE):
            if target > top:
                out[fam + (target,)] = NEW_GROUP_BASE + fam_index[fam] * 32 \
                    + target // STEP_SIZE
            else:
                below = [lv for lv in ladder if lv <= target]
                if below:
                    out[fam + (target,)] = ladder[max(below)]
    return out


def rescale_text(text, factor):
    """Rewrite the leading number in an enchantment description.

    The client renders this string verbatim on the item tooltip, so a scaled
    "+19 Intellect" that still says 19 is a lie the player can see.  Only the
    first integer is touched: every native description in this set is of the
    form "+N Stat" or "+N health every 5 sec.", where any later number is a
    period, not a magnitude.
    """
    out, done = [], False
    i = 0
    while i < len(text):
        if not done and text[i].isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            out.append(str(max(1, int(round(int(text[i:j]) * factor)))))
            i, done = j, True
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def batched(lines, prefix, rows, size=500):
    for i in range(0, len(rows), size):
        lines.append(prefix)
        lines.append(",\n".join(rows[i:i + size]) + ";")
        lines.append("")


def format_sql(new_ench, new_props, new_group_rows, new_spells,
               affix_of, tier_rows, enchants, base_spells, base_sb):
    import gen_sql
    L = []
    A = L.append
    A("-- ==========================================================================")
    A("-- Random-property tiers above level 60 -- auto-generated by")
    A("-- tools/gen_random_property_tiers.py")
    A("-- ==========================================================================")
    A("--")
    A("-- No native item above required level 60 uses RandomProperty: Blizzard")
    A("-- retired the mechanism at the vanilla/TBC boundary.  An upgraded green")
    A("-- therefore reached level 80 still wearing its level-20 affix, because")
    A("-- GenerateEnchSuffixFactor (ItemEnchantmentMgr.cpp:131) returns 0 for")
    A("-- anything without RandomSuffix and the value cannot scale with ItemLevel.")
    A("--")
    A("-- These rows continue each per-slot ladder past where Blizzard stopped,")
    A("-- scaling by the ScalingStatValues ssdMultiplier ratio -- the same curve")
    A("-- the item's own stats follow.  Calibration: 'of the Eagle' on a cloth")
    A("-- chest is +19/+19 at the native level-60 ceiling and +50/+50 here at 80,")
    A("-- against +53/+80 for a native RandomSuffix green of the same item level.")
    A("-- Deliberately just under, consistent with the overshoot cap.")
    A("--")
    A("-- All three DBCs take DB overrides (DBCStores.cpp:344, 345, 377), so this")
    A("-- is purely additive; build_dbc.py packs the same rows into the client MPQ.")
    A("")

    A("DELETE FROM `spellitemenchantment_dbc`  WHERE `ID`    >= %d;" % NEW_ENCH_BASE)
    A("DELETE FROM `itemrandomproperties_dbc`  WHERE `ID`    >= %d;" % NEW_PROP_BASE)
    A("DELETE FROM `item_enchantment_template` WHERE `entry` >= %d;" % NEW_GROUP_BASE)
    A("DELETE FROM `alonecraft_spell_dbc`      WHERE `ID`    BETWEEN %d AND %d;"
      % (NEW_SPELL_BASE, NEW_SPELL_BASE + 99999))
    A("")

    # -- cloned spells for equip-spell affixes --------------------------------
    A("-- -- cloned spells (type 3 EQUIP_SPELL affixes) ----------------------")
    A("-- The value lives in the spell, not in the enchantment's amount column,")
    A("-- so scaling the amount would silently do nothing.  $s1 renders")
    A("-- BasePoints + 1, hence the -1 (see CLAUDE.md on tooltip variables).")
    cols = S.SPELL_COLUMNS
    spell_rows = []
    for (src_id, factor), new_id in sorted(new_spells.items(), key=lambda kv: kv[1]):
        raw = base_spells.get(src_id)
        if not raw:
            continue
        row = dict(S.decode_record(raw, base_sb))
        row["ID"] = new_id
        for i in (1, 2, 3):
            bp = row.get("EffectBasePoints%d" % i, 0)
            if bp:
                row["EffectBasePoints%d" % i] = \
                    max(0, int(round((bp + 1) * factor)) - 1)
        row["SpellName0"] = rescale_text(str(row.get("SpellName0", "")), factor)
        spell_rows.append("(%s)" % ", ".join(
            gen_sql.format_sql_value(row.get(c, 0), c) for c in cols))
    batched(L, "INSERT INTO `alonecraft_spell_dbc` VALUES", spell_rows, 50)

    # -- enchantments ---------------------------------------------------------
    A("-- -- enchantments ----------------------------------------------------")
    ench_cols = ("`ID`, `Charges`, `Effect_1`, `Effect_2`, `Effect_3`, "
                 "`EffectPointsMin_1`, `EffectPointsMin_2`, `EffectPointsMin_3`, "
                 "`EffectPointsMax_1`, `EffectPointsMax_2`, `EffectPointsMax_3`, "
                 "`EffectArg_1`, `EffectArg_2`, `EffectArg_3`, `Name_Lang_enUS`, "
                 "`Name_Lang_Mask`, `ItemVisual`, `Flags`, `Src_ItemID`, "
                 "`Condition_Id`, `RequiredSkillID`, `RequiredSkillRank`, `MinLevel`")
    rows = []
    for new_id, src_id, types, amounts, spellids, f in new_ench:
        src = enchants[src_id]
        raw = src["raw"]
        rows.append("(%d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %d, %s, "
                    "16712190, %d, %d, %d, %d, %d, %d, %d)" % (
                        new_id, raw[1], types[0], types[1], types[2],
                        amounts[0], amounts[1], amounts[2],
                        amounts[0], amounts[1], amounts[2],
                        spellids[0], spellids[1], spellids[2],
                        sql_str(rescale_text(src["desc"], f)),
                        raw[31], raw[32], raw[33], raw[34], raw[35], raw[36], raw[37]))
    batched(L, "INSERT INTO `spellitemenchantment_dbc` (%s) VALUES" % ench_cols, rows)

    # -- properties -----------------------------------------------------------
    A("-- -- property tiers --------------------------------------------------")
    rows = []
    for pid, name, enchs in new_props:
        e = (list(enchs) + [0, 0, 0, 0, 0])[:5]
        rows.append("(%d, %s, %d, %d, %d, %d, %d, %s, 16712190)" % (
            pid, sql_str(name.replace(" ", "_")), e[0], e[1], e[2], e[3], e[4],
            sql_str(name)))
    batched(L, "INSERT INTO `itemrandomproperties_dbc` "
               "(`ID`, `Name`, `Enchantment_1`, `Enchantment_2`, `Enchantment_3`, "
               "`Enchantment_4`, `Enchantment_5`, `Name_Lang_enUS`, `Name_Lang_Mask`) "
               "VALUES", rows)

    # -- groups ---------------------------------------------------------------
    A("-- -- groups ----------------------------------------------------------")
    rows = ["(%d, %d, %s)" % (g, p, repr(round(c, 6))) for g, p, c in new_group_rows]
    batched(L, "INSERT INTO `item_enchantment_template` (`entry`, `ench`, `chance`) VALUES",
            rows)

    # -- runtime lookup tables ------------------------------------------------
    A("-- -- runtime lookup --------------------------------------------------")
    A("-- ItemEnchantmentMgr keeps its group table in a file-scope static with no")
    A("-- accessor, so re-tiering an affix at runtime would mean editing core.")
    A("-- These two tables carry the answer instead; all the name matching is")
    A("-- done here, offline.")
    A("DROP TABLE IF EXISTS `alonecraft_random_affix`;")
    A("CREATE TABLE `alonecraft_random_affix` (")
    A("  `property` INT UNSIGNED NOT NULL PRIMARY KEY,")
    A("  `affix` SMALLINT UNSIGNED NOT NULL,")
    A("  KEY `idx_affix` (`affix`)")
    A(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;")
    A("DROP TABLE IF EXISTS `alonecraft_random_tier`;")
    A("CREATE TABLE `alonecraft_random_tier` (")
    A("  `affix` SMALLINT UNSIGNED NOT NULL,")
    A("  `group_id` INT UNSIGNED NOT NULL,")
    A("  `property` INT UNSIGNED NOT NULL,")
    A("  PRIMARY KEY (`affix`, `group_id`)")
    A(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;")
    A("")

    seen = {}
    for a, g, p in tier_rows:
        seen[(a, g)] = p
    rows = ["(%d, %d, %d)" % (a, g, p) for (a, g), p in sorted(seen.items())]
    batched(L, "INSERT INTO `alonecraft_random_tier` (`affix`, `group_id`, `property`) VALUES",
            rows)

    rows = ["(%d, %d)" % (p, a) for p, a in sorted(affix_of.items())]
    batched(L, "INSERT INTO `alonecraft_random_affix` (`property`, `affix`) VALUES", rows)
    return L


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    props = load_properties()
    enchants = load_enchants()
    ssv = load_ssv()
    conn = get_db_connection()
    ladders = fetch_ladders(conn)
    groups = fetch_groups(conn)
    conn.close()

    base_spells, base_sb = S.read_base_dbc(config.BASE_DBC_PATH)

    new_ench, new_props, new_group_rows, new_spells = [], [], [], {}
    tier_rows = []                       # (affix_id, group, property)
    affix_id = {}                        # affix name -> small int
    ench_seq = NEW_ENCH_BASE
    prop_seq = NEW_PROP_BASE
    spell_seq = NEW_SPELL_BASE
    # Identical (type, amount, spellid) triples recur constantly across families;
    # sharing one row keeps the new DBC small enough to ship in the MPQ.
    ench_cache = {}
    unclonable = set()

    def affix(name):
        if name not in affix_id:
            affix_id[name] = len(affix_id) + 1
        return affix_id[name]

    fam_index = {fam: i for i, fam in enumerate(sorted(ladders))}

    for fam in sorted(ladders):
        ladder = ladders[fam]
        top_level = max(ladder)
        top_group = ladder[top_level]
        rows = groups.get(top_group)
        if not rows:
            continue
        strongest = strongest_per_affix(rows, props, enchants)
        if not strongest:
            continue

        src_ssv = ssv.get(top_level)
        if not src_ssv or not src_ssv[SSV_SSD_MULT]:
            continue

        # Record the native ladder in the tier table too, so an upgrade from 20
        # to 50 re-tiers as well -- the wall at 60 is the visible half of the
        # problem, but standing still from 20 to 50 is the same bug.
        for lvl, grp in ladder.items():
            for name, (pid, _) in strongest_per_affix(
                    groups.get(grp, []), props, enchants).items():
                tier_rows.append((affix(name), grp, pid))

        for target in range(STEP_SIZE, MAX_LEVEL + 1, STEP_SIZE):
            if target <= top_level:
                continue
            dst_ssv = ssv.get(target)
            if not dst_ssv:
                continue
            factor = dst_ssv[SSV_SSD_MULT] / src_ssv[SSV_SSD_MULT]
            # Deterministic, so a regeneration keeps every group id stable: an
            # item already carrying one must not silently point somewhere else.
            gid = NEW_GROUP_BASE + fam_index[fam] * 32 + target // STEP_SIZE

            for name, (src_pid, chance) in sorted(strongest.items()):
                src = props[src_pid]
                out_ench = []
                for eid in src["ench"]:
                    e = enchants.get(eid)
                    if not e:
                        continue
                    types = list(e["type"])
                    amounts = list(e["amount"])
                    spellids = list(e["spellid"])
                    for i, t in enumerate(types):
                        if t in SCALABLE_AMOUNT and amounts[i]:
                            amounts[i] = max(1, int(round(amounts[i] * factor)))
                        elif t == ENCH_TYPE_EQUIP_SPELL and spellids[i]:
                            # Only remap when the source can actually be cloned.
                            # Spell 7545 (+4 Mace Skill, "of Proficiency") lives
                            # server-side only and is absent from Spell.dbc;
                            # pointing at a clone that was never emitted would
                            # leave a dangling id and the enchantment would
                            # silently do nothing.  Weapon skill is capped at
                            # 5*level anyway, so keeping it unscaled is also the
                            # semantically right answer.
                            if spellids[i] not in base_spells:
                                unclonable.add(spellids[i])
                                continue
                            key = (spellids[i], round(factor, 4))
                            if key not in new_spells:
                                new_spells[key] = spell_seq
                                spell_seq += 1
                            spellids[i] = new_spells[key]
                    key = (tuple(types), tuple(amounts), tuple(spellids))
                    if key not in ench_cache:
                        ench_cache[key] = ench_seq
                        new_ench.append((ench_seq, eid, types, amounts,
                                         spellids, factor))
                        ench_seq += 1
                    out_ench.append(ench_cache[key])

                new_props.append((prop_seq, name, out_ench))
                new_group_rows.append((gid, prop_seq, chance))
                tier_rows.append((affix(name), gid, prop_seq))
                prop_seq += 1

    print("families           : %d" % len(ladders))
    print("new groups         : %d" % len(set(g for g, _, _ in new_group_rows)))
    print("new properties     : %d" % len(new_props))
    print("new enchantments   : %d" % len(new_ench))
    print("cloned spells      : %d" % len(new_spells))
    print("affixes            : %d" % len(affix_id))
    print("tier map rows      : %d" % len(tier_rows))
    # Every native property, so an item carrying ANY tier can be re-tiered.
    affix_of = {pid: affix_id[p["name"]]
                for pid, p in props.items() if p["name"] in affix_id}
    for pid, name, _ in new_props:
        affix_of[pid] = affix_id[name]
    print("affix map rows     : %d" % len(affix_of))
    if unclonable:
        print("kept unscaled (no base spell): %s" % sorted(unclonable))
    if args.dry_run:
        return

    path = next_sql_path()
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(format_sql(
            new_ench, new_props, new_group_rows, new_spells,
            affix_of, tier_rows, enchants, base_spells, base_sb)) + "\n")
    print("Wrote %s (%.1f MB)" % (path, os.path.getsize(path) / 1048576.0))


if __name__ == "__main__":
    main()
