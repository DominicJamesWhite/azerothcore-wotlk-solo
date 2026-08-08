#!/usr/bin/env python3
"""
Item Upgrade Variant Generator

Generates level-stepped variants of uncommon+ equippable items, so the upgrade
vendor (npc_item_upgrade_vendor) can swap a player's equipped item for a version
scaled to their level.  One variant per 5-level step from the item's own base
level up to 80.

Two rows are emitted per variant, and BOTH are mandatory:

  * `item_dbc`      -- without a matching Item.dbc entry the item_template row is
                       silently discarded at load (ObjectMgr.cpp:3487).  This
                       table also feeds the client's patched Item.dbc via
                       build_dbc.py, which is what makes the bag icon resolve.
  * `item_template` -- the actual stats.

Scaling uses Blizzard's own per-item-level stat budget from RandPropPoints.dbc
rather than an invented one -- the same table the random-suffix system is priced
from -- with armor and weapon damage on their own curves fitted from the item
census, since neither is stat points.  Target item level comes first and the
stats follow from it (see derive_item_level), so upgraded gear inherits the real
expansion inflections at levels 58 and 68 instead of a fitted straight line.

Usage:
    python tools/gen_item_variants.py                  # generate everything
    python tools/gen_item_variants.py --limit 20       # small sample first (do this!)
    python tools/gen_item_variants.py --dry-run        # summary only, no file
    python tools/gen_item_variants.py --validate       # check invariants, write nothing on failure
    python tools/gen_item_variants.py --stdout         # print SQL instead of writing
    python tools/gen_item_variants.py --audit-csv out.csv
"""

import argparse
import csv
import os
import sys
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBC_DIR = os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc")
sys.path.insert(0, DBC_DIR)
import config  # noqa: E402
from build_dbc import read_int_dbc  # noqa: E402

# The single source of truth for which tool reforges to which level.  Imported
# rather than restated so the variant's name prefix and the tool that produces
# it cannot drift apart.
from gen_upgrade_tools import TOOL_NAMES, TOOL_ALT_PREFIX  # noqa: E402

MODULE_SQL = os.path.join(
    REPO_ROOT, "modules", "world_of_alonecraft", "data", "sql", "db-world"
)


def build_name_prefix_case():
    """SQL CASE mapping a variant's req_level to its tool's leading adjective.

    A variant is named for the tool that made it -- "Woven Arcanite Reaper"
    rather than "Arcanite Reaper (65)".  The adjective is the first word of the
    tool name, and each is unique across the 16 tools, so the mapping stays
    reversible: "Woven" means level 65 and nothing else.

    A prefix reads as part of the item's name the way Blizzard's own affixes do,
    where a trailing "(65)" always looked like debug output.  The cost is
    alphabetical: variants no longer sort next to their base item, which is a
    real loss when searching a bank and the reason the suffix was chosen first.
    """
    whens = " ".join(
        # Fall back to the alternate adjective when the primary is already the
        # item's first word, or "Brilliant Gold Ring" becomes "Brilliant
        # Brilliant Gold Ring".  Four of the sixteen collide in the 3.3.5a set.
        "WHEN {} THEN IF(SUBSTRING_INDEX(c.`name`, ' ', 1) = {}, {}, {})".format(
            level,
            sql_str(name.split()[0]),
            sql_str(TOOL_ALT_PREFIX[level]),
            sql_str(name.split()[0]),
        )
        for level, name in sorted(TOOL_NAMES.items())
    )
    # No ELSE: a req_level with no tool would yield NULL and CONCAT would blank
    # the whole name, so it must be impossible rather than merely unlikely.
    # gen_upgrade_tools builds one tool per multiple of 5 and this generator
    # snaps every target level to the same grid, which --validate re-checks.
    return f"CASE d.`req_level` {whens} END"

# ── Entry-ID encoding ───────────────────────────────────────────────────────
# variantEntry = VARIANT_BASE + baseEntry*STRIDE + step   (step 1..16)
#
# Arithmetic rather than a mapping table, so the runtime needs no lookup: the
# C++ decodes an entry directly and tests existence with GetItemTemplate().
# It is also stable under regeneration -- retuning changes a variant's stats but
# never its entry, so an equipped item can never silently become a different
# item.  A retune that must not disturb live clients emits into the next band
# (VARIANT_BASE + 3_000_000) instead; see the plan's ItemCache.wdb note.
VARIANT_BASE = 1_000_000
STRIDE = 20
MAX_LEVEL = 80
STEP_SIZE = 5

# ── Quality ─────────────────────────────────────────────────────────────────
QUALITY_UNCOMMON, QUALITY_RARE, QUALITY_EPIC, QUALITY_LEGENDARY = 2, 3, 4, 5

# "Split the difference": rarer items scale faster, so an upgraded legendary
# lands near 70% of native endgame gear rather than ~45%.  Applied as an
# exponent on the level multiplier, so greens are untouched (^1.0).  Safe only
# because the native-equivalent cap below stops it running away.
QUALITY_EXPONENT = {
    QUALITY_UNCOMMON: 1.0,
    QUALITY_RARE: 1.3,
    QUALITY_EPIC: 1.8,
    QUALITY_LEGENDARY: 2.0,
}

# ── item_template flags we care about ───────────────────────────────────────
ITEM_FLAG_UNIQUE_EQUIPPABLE = 0x00080000

# InventoryType values that do not occupy an equipment slot.
NON_EQUIP_INVTYPES = {0, 24, 27, 28}

# ScalingStatValues field layout (24 uint32 fields, verified against the DBC).
SSV_LEVEL = 1
SSV_SSD_MULT = 2          # ssdMultiplier[0..3] at 2..5
SSV_DPS_MOD = 10          # dpsMod[0..5] at 10..15
SSV_ARMOR_MOD2 = 19       # armorMod2[0..4] at 19..23: cloak, cloth, leather, mail, plate

# armorMod2 index by armor subclass (item_template.subclass for class=4).
# 1 cloth, 2 leather, 3 mail, 4 plate; 0 misc and 6 shield fall back to cloak.
ARMOR_SUBCLASS_TO_MOD2 = {1: 1, 2: 2, 3: 3, 4: 4}

# dpsMod index by weapon subclass (item_template.subclass for class=2).
# 0 1H melee, 1 2H melee, 2 caster 1H, 3 caster 2H/staff, 4 ranged, 5 wand.
WEAPON_SUBCLASS_TO_DPS = {
    0: 1, 1: 1, 4: 1, 5: 1, 6: 1, 8: 1, 10: 3,     # axes/maces/swords/polearms 2H, staff
    7: 0, 13: 0, 15: 0,                             # 1H sword, fist, dagger
    2: 4, 3: 4, 18: 4,                              # bow, gun, crossbow
    19: 5,                                          # wand
}

# RandPropPoints: ItemLevel, Epic[5], Rare[5], Uncommon[5]
RPP_EPIC, RPP_RARE, RPP_UNCOMMON = 1, 6, 11


def load_ssv():
    """level -> raw ScalingStatValues record (list of 24 ints)."""
    path = os.path.join(DBC_DIR, "base", "ScalingStatValues.dbc")
    records, _ = read_int_dbc(path, 24, 96)
    return {r[SSV_LEVEL]: r for r in records.values()}


def load_rpp():
    """ItemLevel -> raw RandPropPoints record (list of 16 ints)."""
    path = os.path.join(DBC_DIR, "base", "RandPropPoints.dbc")
    records, _ = read_int_dbc(path, 16, 64)
    return {r[0]: r for r in records.values()}


def get_db_connection():
    import mysql.connector
    return mysql.connector.connect(
        host=config.MYSQL_HOST,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASS,
        database=config.MYSQL_DB,
    )


def fetch_candidates(conn):
    """Uncommon+ equippable items eligible for variant generation.

    Exclusions and why:
      * ITEM_FLAG_UNIQUE_EQUIPPABLE with no ItemLimitCategory -- uniqueness is
        enforced by entry (Player.cpp:13978), so base + variant of the same
        trinket could both be equipped.  Deferred to Phase 3, which assigns
        synthetic limit categories.
      * duration > 0 -- temporary items.
      * ItemLevel 0 or > 284 -- outside the RandPropPoints budget table, so the
        target item level cannot be derived.
      * class not in (2 weapon, 4 armor) -- belt-and-braces alongside
        InventoryType; some datasets have odd class 0 rows with a slot.
    """
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT entry, name, class, subclass, Quality, InventoryType, ItemLevel,
               RequiredLevel, armor, block, delay, bonding, Flags, itemset,
               displayid, Material, sheath, SoundOverrideSubclass,
               dmg_min1, dmg_max1, dmg_min2, dmg_max2,
               stat_type1, stat_value1, stat_type2, stat_value2,
               stat_type3, stat_value3, stat_type4, stat_value4,
               stat_type5, stat_value5, stat_type6, stat_value6,
               stat_type7, stat_value7, stat_type8, stat_value8,
               stat_type9, stat_value9, stat_type10, stat_value10,
               holy_res, fire_res, nature_res, frost_res, shadow_res, arcane_res
        FROM item_template
        WHERE Quality BETWEEN %s AND %s
          AND InventoryType NOT IN (0, 24, 27, 28)
          AND class IN (2, 4)
          AND entry < %s
          AND duration = 0
          AND ItemLevel > 0 AND ItemLevel <= 284
          AND NOT (Flags & %s AND ItemLimitCategory = 0)
        ORDER BY entry
        """,
        (QUALITY_UNCOMMON, QUALITY_LEGENDARY, VARIANT_BASE, ITEM_FLAG_UNIQUE_EQUIPPABLE),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def infer_base_level(row, tiers):
    """L0: the item's own level, i.e. what it should be balanced against.

    ~4,000 candidates carry RequiredLevel = 0, mostly TBC quest rewards, so the
    level has to be inferred from the one thing they do declare: ItemLevel.

    Read fit_tier_curve BACKWARDS to do it.  That curve is already the exact
    relationship wanted here -- typical ItemLevel at each required level, per
    quality -- and it is the only version of it with a sample-count guard.  The
    first level whose typical item is as good as this one is the level this item
    belongs to.

    This used to scan the raw (ItemLevel, RequiredLevel) scatter for the nearest
    declared item level instead, which had no such guard, and the stray rows
    MIN_SAMPLES exists to discard are precisely what it locked onto: two
    uncommons at ItemLevel 105 / RequiredLevel 1 put every ilvl-105 green at
    base level 1.  `Talbuk Cape` (25636) is one, which is how a level-10 upgrade
    tool produced an ilvl 110 cloak.  Off the curve it now reads level 65.
    """
    if row["RequiredLevel"] > 0:
        return min(row["RequiredLevel"], MAX_LEVEL)

    # Legendaries share epic's curve, so .get is enough; uncommon is the floor
    # for anything whose quality was too thin to fit at all.
    curve = tiers.get(row["Quality"]) or tiers.get(QUALITY_UNCOMMON)
    if not curve:
        return 1

    target = row["ItemLevel"]
    for level in sorted(curve):
        if curve[level] >= target:
            return max(1, min(level, MAX_LEVEL))

    # Better than anything the curve knows about.  MAX_LEVEL rather than a
    # guess: scale_item then finds no target level left and emits no variants,
    # which is the right answer for an item already past the end of the game.
    return MAX_LEVEL


# ── the budget model ────────────────────────────────────────────────────────
# RandPropPoints slot classes, mirroring GenerateEnchSuffixFactor's switch
# (ItemEnchantmentMgr.cpp:139).  Note that Blizzard puts INVTYPE_WEAPON,
# WEAPONMAINHAND and WEAPONOFFHAND in ONE class: the game itself does not
# believe a main-hand-only sword has a different budget from a one-hander.
# Measuring them separately is what rated the Warglaives against 41 odd items
# averaging 110 dps while their peers were measured against 109 averaging 169.
RPP_SLOT_CLASS = {
    1: 0, 4: 0, 5: 0, 7: 0, 17: 0, 20: 0,      # head, body, chest, legs, 2H, robe
    3: 1, 6: 1, 8: 1, 10: 1, 12: 1,            # shoulders, waist, feet, hands, trinket
    2: 2, 9: 2, 11: 2, 14: 2, 16: 2, 23: 2,    # neck, wrists, finger, shield, cloak, held
    13: 3, 21: 3, 22: 3,                       # one-hand / main-hand / off-hand
    15: 4, 25: 4, 26: 4,                       # ranged, thrown, ranged-right
}

# Column offsets into a RandPropPoints record, by quality.  Legendary has no
# column of its own and shares epic's, which is Blizzard's own arrangement.
RPP_COLUMN = {
    QUALITY_UNCOMMON: RPP_UNCOMMON, QUALITY_RARE: RPP_RARE,
    QUALITY_EPIC: RPP_EPIC, QUALITY_LEGENDARY: RPP_EPIC,
}


def rpp_points(rpp, ilvl, quality, slot_class):
    """Blizzard's stat-point budget for an item level.  0 when off the table."""
    rec = rpp.get(int(ilvl))
    if not rec or slot_class is None:
        return 0
    return rec[RPP_COLUMN.get(quality, RPP_UNCOMMON) + slot_class]


def _interp(curve, x):
    """Value of a sparse {x: y} map at x, interpolating and holding the ends."""
    if not curve:
        return None
    if x in curve:
        return curve[x]
    below = [k for k in curve if k < x]
    above = [k for k in curve if k > x]
    if not below:
        return curve[min(above)]
    if not above:
        return curve[max(below)]
    lo, hi = max(below), min(above)
    t = (x - lo) / float(hi - lo)
    return curve[lo] + t * (curve[hi] - curve[lo])


def fit_tier_curve(rows):
    """quality -> {required level: typical native ItemLevel}.

    Fitted over EVERY native item of a quality, so each level has hundreds of
    samples rather than the handful a (quality, slot, subclass) bucket holds.
    This is the one place the old model's thin-bucket problem cannot arise.
    """
    buckets = defaultdict(lambda: defaultdict(list))
    for r in rows:
        lvl, ilvl = r["RequiredLevel"], r["ItemLevel"]
        if 0 < lvl <= MAX_LEVEL and ilvl > 0:
            buckets[r["Quality"]][lvl].append(ilvl)
    # Levels with almost no items are not evidence.  Two stray uncommons at
    # required level 1 carrying ItemLevel 105 were enough to flatten the entire
    # uncommon curve at 105 from level 20 to 60 once the monotonic pass below
    # propagated them forward -- and a flat curve means no upgrade exists.
    # Sparse levels are dropped and _interp fills the gap from its neighbours.
    MIN_SAMPLES = 8

    curves = {}
    for q, by_level in buckets.items():
        curve = {}
        for lvl, vals in by_level.items():
            if len(vals) < MIN_SAMPLES:
                continue
            vals.sort()
            curve[lvl] = vals[len(vals) // 2]          # median
        # Monotonic: a later level must never be worth less than an earlier one.
        # Sparse high levels otherwise produce dips that would read as downgrades.
        running = 0
        for lvl in sorted(curve):
            running = max(running, curve[lvl])
            curve[lvl] = running
        curves[q] = curve

    # Legendaries share epic's curve, exactly as they share epic's column in
    # RandPropPoints.  There are ~30 of them in the whole game, so nearly every
    # level falls below MIN_SAMPLES and their own curve collapses to a single
    # flat value -- which is the thin-data trap again, one layer up.  Their
    # standing above the tier is preserved by the offset, not by the curve.
    if QUALITY_EPIC in curves:
        curves[QUALITY_LEGENDARY] = curves[QUALITY_EPIC]
    return curves


def fit_value_curve(rows, key_of, value_of):
    """key -> {ItemLevel: median value}, for fields RandPropPoints does not cover.

    Armor and weapon damage are not stat points, so they need their own shape.
    Keyed only by what genuinely changes the shape -- armor class, weapon class --
    and fitted across ALL levels and qualities at once, because item level already
    encodes power.  That is what keeps these dense.
    """
    buckets = defaultdict(lambda: defaultdict(list))
    for r in rows:
        v = value_of(r)
        if v and r["ItemLevel"] > 0:
            buckets[key_of(r)][r["ItemLevel"]].append(v)
    # Same guards as the tier curve, for the same reason.  Without them a single
    # sparsely-populated item level produces a wild ratio: Tempest of Chaos, a
    # caster sword, came out at 5.0x its damage while the Warglaives of the same
    # subclass and almost the same item level came out at 1.9x -- not a real
    # difference, just two different amounts of noise.
    MIN_SAMPLES = 5

    out = {}
    for key, by_ilvl in buckets.items():
        curve = {}
        for ilvl, vals in by_ilvl.items():
            if len(vals) < MIN_SAMPLES:
                continue
            vals.sort()
            curve[ilvl] = vals[len(vals) // 2]
        # Monotonic: damage and armor never fall as item level rises.
        running = 0
        for ilvl in sorted(curve):
            running = max(running, curve[ilvl])
            curve[ilvl] = running
        if len(curve) >= 2:
            out[key] = curve
    return out


def curve_ratio(curves, key, from_ilvl, to_ilvl, fallback):
    """Growth between two item levels along a fitted curve."""
    curve = curves.get(key)
    a = _interp(curve, from_ilvl) if curve else None
    b = _interp(curve, to_ilvl) if curve else None
    if not a or not b:
        return fallback
    return b / float(a)


def derive_item_level(row, quality, base_level, target_level, tiers):
    """The variant's ItemLevel: the item's own standing, carried up the curve.

    Item level is the currency everything else is priced in, so it is derived
    first and the stats follow from it -- the reverse of the old model, which
    measured stats against native peers and left item level as a label to be
    guessed at.

    The item keeps its OFFSET from its tier.  A Warglaive sits ~16 above the
    typical level-70 item; it sits ~16 above the typical level-80 item too.  That
    is what makes an upgraded legendary come out ahead of an upgraded epic of the
    same raid tier without a single special case for legendaries -- and it is
    also why nothing here consults native peers by slot, which is where every
    thin-bucket artefact came from.

    Preserving the RAW offset rather than the ilvl-to-required-level gap matters:
    ilvl inflation is strongly non-linear across vanilla -> TBC -> WotLK, so a
    gap-preserving level-80 green lands near ilvl 85 and reads as worthless.
    """
    base_tier = _interp(tiers.get(quality), base_level)
    target_tier = _interp(tiers.get(quality), target_level)
    if not base_tier or not target_tier:
        return min(284, max(1, row["ItemLevel"]))

    offset = row["ItemLevel"] - base_tier
    return int(min(284, max(1, round(target_tier + offset), row["ItemLevel"])))


def scale_item(row, step, rpp, tiers, armor_curves, dps_curves):
    """Compute one variant. Returns a delta dict, or None if not applicable."""
    base_level = infer_base_level(row, tiers)

    # Target levels snap to absolute multiples of 5, not base_level + 5n.
    #
    # This exists so the upgrade tools sold by the vendor can be per-level: a
    # "level 45" tool has to be usable on every item, and with relative steps a
    # level-23 item's chain runs 28/33/38 and would never see 45.  Only 39% of
    # variants landed on a round level under the old scheme.
    #
    # The first step goes to the next multiple of 5 above the item's own level,
    # so it can be a short hop (a level-23 item's first upgrade is to 25).
    first = ((base_level // STEP_SIZE) + 1) * STEP_SIZE
    target_level = first + (step - 1) * STEP_SIZE
    if target_level > MAX_LEVEL:
        return None

    # Nothing to scale: tabards, shirts, cosmetic trinkets and the like derive
    # all their value from procs or flavour, so a variant would be an identical
    # copy at a higher required level -- strictly worse than the original.
    if not any(row[f"stat_value{i}"] for i in range(1, 11))             and not row["armor"] and not row["dmg_max1"]:
        return None

    quality = row["Quality"]
    invtype, subclass = row["InventoryType"], row["subclass"]
    base_ilvl = row["ItemLevel"]
    target_ilvl = derive_item_level(row, quality, base_level, target_level, tiers)
    # Deliberately NOT "return None" when the item level does not move.  generate()
    # reads None as end-of-chain, so a flat spot in the tier curve -- levels where
    # Blizzard shipped nothing new -- would truncate every chain that crossed it,
    # and uncommons lost 90% of their steps that way.  A step that gains nothing
    # is already detected and skipped downstream, without ending the chain.

    # Stats ride RandPropPoints, which IS Blizzard's per-item-level, per-quality
    # stat budget -- the same table the random-suffix system is priced from.  No
    # cap is needed because the budget is the cap: a level-80 variant is given
    # exactly what a native level-80 item of its quality and slot is given.
    slot_class = RPP_SLOT_CLASS.get(invtype)
    src_pts = rpp_points(rpp, base_ilvl, quality, slot_class)
    dst_pts = rpp_points(rpp, target_ilvl, quality, slot_class)
    m_stat = (dst_pts / float(src_pts)) if (src_pts and dst_pts) else         (target_ilvl / float(base_ilvl))

    # Armor and weapon damage are not stat points, so they get their own fitted
    # shape against item level.  Keyed only by what changes that shape, and
    # fitted across all levels and qualities at once, so they stay dense.
    m_armor = curve_ratio(armor_curves, (row["class"], subclass, invtype),
                          base_ilvl, target_ilvl, m_stat)
    m_dps = curve_ratio(dps_curves, subclass, base_ilvl, target_ilvl, m_stat)

    stats = [(row[f"stat_type{i}"], row[f"stat_value{i}"]) for i in range(1, 11)]
    new_stats = []
    for stat_type, value in stats:
        if value == 0:
            new_stats.append(0)
        else:
            scaled = int(round(value * m_stat))
            # Never let rounding zero out a stat the item actually had.
            new_stats.append(max(1, scaled) if value > 0 else min(-1, scaled))

    new_armor = max(int(round(row["armor"] * m_armor)), row["armor"])         if row["armor"] else 0

    # Weapon damage: multiply both ends by the same factor so the min/max spread
    # ratio is preserved exactly.  `delay` is deliberately untouched -- weapon
    # speed is an identity property, and changing it would break Slam, Windfury,
    # seal PPM and normalized weapon damage.
    dmg = {}
    for i in (1, 2):
        dmin, dmax = row[f"dmg_min{i}"], row[f"dmg_max{i}"]
        dmg[f"dmg_min{i}"] = round(dmin * m_dps, 2) if dmin else 0.0
        dmg[f"dmg_max{i}"] = round(dmax * m_dps, 2) if dmax else 0.0

    return {
        "entry": VARIANT_BASE + row["entry"] * STRIDE + step,
        "base_entry": row["entry"],
        "step": step,
        "name": row["name"],
        "quality": quality,
        "base_level": base_level,
        # Whether base_level was read off the item or inferred from the tier
        # curve.  validate() holds the inferred population to a hard standard
        # and can only report on the declared one -- see the guard there.
        "declared": row["RequiredLevel"] > 0,
        "req_level": target_level,
        "item_level": target_ilvl,
        "mult": round(m_stat, 3),
        "armor": new_armor,
        "block": int(round(row["block"] * m_armor)) if row["block"] else 0,
        "stats": new_stats,
        "res": [int(round(row[f"{n}_res"] * m_stat)) if row[f"{n}_res"] else 0
                for n in ("holy", "fire", "nature", "frost", "shadow", "arcane")],
        # The mandatory item_dbc row, taken verbatim from the base item so the
        # enforceDBCAttributes fixups are no-ops.  Without it the item_template
        # row is silently discarded at load (ObjectMgr.cpp:3487).
        "dbc": (row["class"], row["subclass"], row["SoundOverrideSubclass"],
                row["Material"], row["displayid"], row["InventoryType"],
                row["sheath"]),
        **dmg,
    }


def _power(v):
    """Comparable power tuple, for detecting steps that gain nothing."""
    return (sum(s for s in v["stats"] if s > 0), v["armor"], v["dmg_max1"])


def generate(rows, rpp, tiers, armor_curves, dps_curves, limit=None):
    """Emit variants, dropping steps that are no better than the step before.

    A no-op step is worse than useless: the vendor would charge gold for an
    identical item.  They happen where the native cap binds hard for several
    consecutive levels.

    Dropping them leaves gaps in the step sequence, so the vendor must scan
    forward for the next existing variant rather than assuming step+1.
    """
    variants = []
    skipped_noop = 0
    for row in rows:
        prev = (
            sum(row[f"stat_value{i}"] for i in range(1, 11) if row[f"stat_value{i}"] > 0),
            row["armor"],
            row["dmg_max1"],
        )
        for step in range(1, (MAX_LEVEL // STEP_SIZE) + 1):
            v = scale_item(row, step, rpp, tiers, armor_curves, dps_curves)
            if v is None:
                break
            cur = _power(v)
            if all(c <= p for c, p in zip(cur, prev)):
                skipped_noop += 1
                continue
            prev = cur
            variants.append(v)
        if limit and len(variants) >= limit:
            print(f"Skipped {skipped_noop} no-op step(s)")
            return variants[:limit]
    print(f"Skipped {skipped_noop} no-op step(s) that gained nothing over the previous step")
    return variants


def sql_str(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def format_sql(variants, conn):
    L = []
    A = L.append
    A("-- ==========================================================================")
    A("-- Item Upgrade Variants — auto-generated by tools/gen_item_variants.py")
    A("-- ==========================================================================")
    A("--")
    A(f"-- {len(variants)} variants. entry = {VARIANT_BASE} + baseEntry*{STRIDE} + step.")
    A("--")
    A("-- Both tables are required.  Without the item_dbc row the item_template")
    A("-- row is silently discarded at load (ObjectMgr.cpp:3487) and the item")
    A("-- simply does not exist; build_dbc.py also reads item_dbc to patch the")
    A("-- client's Item.dbc, which is what makes the bag icon resolve.")
    A("--")
    A("-- The 138-column item_template list is deliberately never written out:")
    A("-- rows are cloned with INSERT ... SELECT * and then patched by a JOIN")
    A("-- against the compact delta table, so this file survives schema changes.")
    A("--")
    A("-- ORDERING: this file clones base rows AT APPLY TIME, so it must sort")
    A("-- AFTER the gen_item_limit_categories.py output.  Applied first, variants")
    A("-- of unique-equipped items would clone ItemLimitCategory = 0 and stay")
    A("-- equippable alongside their own base item -- the exact dupe that file")
    A("-- exists to close.  Rename this file if the sequence numbers say otherwise.")
    A("")
    A(f"DELETE FROM `item_template` WHERE `entry` >= {VARIANT_BASE};")
    A(f"DELETE FROM `item_dbc`      WHERE `ID`    >= {VARIANT_BASE};")
    A("DROP TABLE IF EXISTS `alonecraft_item_upgrade_variant`;")
    A("CREATE TABLE `alonecraft_item_upgrade_variant` (")
    A("  `entry` INT UNSIGNED NOT NULL PRIMARY KEY,")
    A("  `base_entry` INT UNSIGNED NOT NULL,")
    A("  `step` TINYINT UNSIGNED NOT NULL,")
    A("  `base_level` TINYINT UNSIGNED NOT NULL,")
    A("  `target_level` TINYINT UNSIGNED NOT NULL,")
    A("  `target_ilvl` SMALLINT UNSIGNED NOT NULL,")
    A("  `stat_mult` FLOAT NOT NULL,")
    A("  KEY `idx_base` (`base_entry`)")
    A(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;")
    A("-- Audit only. The runtime never reads this table; it exists so a human")
    A("-- can answer \"why does this item have these stats\", and so a future")
    A("-- retune can write a migration.")
    A("")

    def batched(rows_, header, chunk=500):
        for i in range(0, len(rows_), chunk):
            A(header)
            A(",\n".join(rows_[i:i + chunk]) + ";")
            A("")

    A("-- -- item_dbc -----")
    dbc_rows = [
        "({}, {}, {}, {}, {}, {}, {}, {})".format(
            v["entry"], v["dbc"][0], v["dbc"][1], v["dbc"][2],
            v["dbc"][3], v["dbc"][4], v["dbc"][5], v["dbc"][6])
        for v in variants
    ]
    batched(dbc_rows,
            "INSERT INTO `item_dbc` (`ID`, `ClassID`, `SubclassID`, "
            "`Sound_Override_Subclassid`, `Material`, `DisplayInfoID`, "
            "`InventoryType`, `SheatheType`) VALUES")

    A("-- -- audit table -----")
    audit_rows = [
        "({}, {}, {}, {}, {}, {}, {})".format(
            v["entry"], v["base_entry"], v["step"], v["base_level"],
            v["req_level"], v["item_level"], v["mult"])
        for v in variants
    ]
    batched(audit_rows,
            "INSERT INTO `alonecraft_item_upgrade_variant` (`entry`, `base_entry`, "
            "`step`, `base_level`, `target_level`, `target_ilvl`, `stat_mult`) VALUES")

    A("-- -- delta table -----")
    A("DROP TEMPORARY TABLE IF EXISTS `_woa_delta`;")
    A("CREATE TEMPORARY TABLE `_woa_delta` (")
    A("  `entry` INT UNSIGNED NOT NULL PRIMARY KEY,")
    A("  `base_entry` INT UNSIGNED NOT NULL,")
    A("  `step` TINYINT UNSIGNED NOT NULL,")
    A("  `req_level` TINYINT UNSIGNED NOT NULL,")
    A("  `item_level` SMALLINT UNSIGNED NOT NULL,")
    A("  `armor` INT UNSIGNED NOT NULL, `block` INT UNSIGNED NOT NULL,")
    A("  `dmin1` FLOAT NOT NULL, `dmax1` FLOAT NOT NULL,")
    A("  `dmin2` FLOAT NOT NULL, `dmax2` FLOAT NOT NULL,")
    A("  " + ", ".join(f"`sv{i}` INT NOT NULL" for i in range(1, 11)) + ",")
    A("  " + ", ".join(f"`r{i}` INT NOT NULL" for i in range(1, 7)) + ",")
    A("  KEY `idx_step` (`step`)")
    A(") ENGINE=MEMORY;")
    A("")

    delta_rows = []
    for v in variants:
        delta_rows.append(
            "({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})".format(
                v["entry"], v["base_entry"], v["step"], v["req_level"],
                v["item_level"], v["armor"], v["block"],
                v["dmg_min1"], v["dmg_max1"], v["dmg_min2"], v["dmg_max2"],
                ", ".join(str(s) for s in v["stats"]),
                ", ".join(str(r) for r in v["res"]),
            )
        )
    cols = ("`entry`, `base_entry`, `step`, `req_level`, `item_level`, `armor`, "
            "`block`, `dmin1`, `dmax1`, `dmin2`, `dmax2`, "
            + ", ".join(f"`sv{i}`" for i in range(1, 11)) + ", "
            + ", ".join(f"`r{i}`" for i in range(1, 7)))
    batched(delta_rows, f"INSERT INTO `_woa_delta` ({cols}) VALUES")

    A("-- -- clone + patch, one pass per step -----")
    A("DROP TEMPORARY TABLE IF EXISTS `_woa_clone`;")
    A("CREATE TEMPORARY TABLE `_woa_clone` LIKE `item_template`;")
    A("")

    # Affix ladder.  A vanilla item's "of the Eagle" is a fixed enchantment
    # chosen from a per-slot ladder of tiers, NOT a scaling suffix -- so unless
    # the variant also moves up the ladder it reaches level 80 still wearing its
    # level-20 bonus.  gen_random_property_tiers.py owns the ladder (including
    # the tiers it synthesises above level 60, where Blizzard's data stops);
    # this only has to look the group up for the variant's target level.
    #
    # Imported here rather than at module scope: gen_random_property_tiers
    # imports from this file, so a top-level import would be circular.
    from gen_random_property_tiers import build_group_map
    group_map = build_group_map(conn)
    A("DROP TEMPORARY TABLE IF EXISTS `_woa_rndgrp`;")
    A("CREATE TEMPORARY TABLE `_woa_rndgrp` (")
    A("  `cls` TINYINT UNSIGNED NOT NULL, `sub` TINYINT UNSIGNED NOT NULL,")
    A("  `inv` TINYINT UNSIGNED NOT NULL, `lvl` TINYINT UNSIGNED NOT NULL,")
    A("  `grp` INT UNSIGNED NOT NULL,")
    A("  PRIMARY KEY (`cls`, `sub`, `inv`, `lvl`)) ENGINE=MEMORY;")
    batched([f"({c}, {sb}, {iv}, {lv}, {g})"
             for (c, sb, iv, lv), g in sorted(group_map.items())],
            "INSERT INTO `_woa_rndgrp` (`cls`, `sub`, `inv`, `lvl`, `grp`) VALUES")
    A("")

    max_step = max(v["step"] for v in variants)
    stat_set = ", ".join(f"c.`stat_value{i}` = d.`sv{i}`" for i in range(1, 11))
    res_names = ("holy", "fire", "nature", "frost", "shadow", "arcane")
    res_set = ", ".join(f"c.`{n}_res` = d.`r{i+1}`" for i, n in enumerate(res_names))
    name_prefix_case = build_name_prefix_case()

    for step in range(1, max_step + 1):
        A(f"-- step {step}  (+{step * STEP_SIZE} levels)")
        A("TRUNCATE `_woa_clone`;")
        A("INSERT INTO `_woa_clone` SELECT * FROM `item_template` WHERE `entry` IN "
          f"(SELECT `base_entry` FROM `_woa_delta` WHERE `step` = {step});")
        A("UPDATE `_woa_clone` c "
          f"JOIN `_woa_delta` d ON d.`base_entry` = c.`entry` AND d.`step` = {step} "
          "LEFT JOIN `_woa_rndgrp` g ON g.`cls` = c.`class` AND g.`sub` = c.`subclass` "
          "AND g.`inv` = c.`InventoryType` AND g.`lvl` = d.`req_level` SET")
        A("  c.`entry` = d.`entry`,")
        A(f"  c.`name` = CONCAT({name_prefix_case}, ' ', c.`name`),")
        A("  c.`RequiredLevel` = d.`req_level`,")
        # IF, not COALESCE alone: an item with no random property must keep 0,
        # or every plain green would sprout an affix it never had.
        A("  c.`RandomProperty` = IF(c.`RandomProperty` = 0, 0, "
          "COALESCE(g.`grp`, c.`RandomProperty`)),")
        A("  c.`ItemLevel` = d.`item_level`,")
        A("  -- Force BoP: without this an level-80 could upgrade cheap greens")
        A("  -- and sell them, creating a laundering and twink-gear market.")
        A("  c.`bonding` = 1,")
        A("  c.`armor` = d.`armor`, c.`block` = d.`block`,")
        A("  c.`dmg_min1` = d.`dmin1`, c.`dmg_max1` = d.`dmax1`,")
        A("  c.`dmg_min2` = d.`dmin2`, c.`dmg_max2` = d.`dmax2`,")
        A(f"  {stat_set},")
        A(f"  {res_set};")
        A("INSERT INTO `item_template` SELECT * FROM `_woa_clone`;")
        A("")

    A("DROP TEMPORARY TABLE `_woa_clone`;")
    A("DROP TEMPORARY TABLE `_woa_rndgrp`;")
    A("DROP TEMPORARY TABLE `_woa_delta`;")
    return "\n".join(L) + "\n"


def validate(variants):
    """Structural invariants. True if every one holds; prints each failure.

    Cheap to run and worth running: the whole batch is 78k rows that the updater
    applies unattended, so a malformed one is discovered in-game.
    """
    failures = []

    def check(label, bad, limit=5):
        if not bad:
            return
        sample = ", ".join(str(b) for b in bad[:limit])
        more = f" (+{len(bad) - limit} more)" if len(bad) > limit else ""
        failures.append(f"{label}: {len(bad)} -- {sample}{more}")

    # The naming CASE (build_name_prefix_case) has no ELSE, so a level with no
    # tool yields NULL and CONCAT blanks the entire item name.
    check("req_level off the 5-level grid",
          [f"{v['entry']}@{v['req_level']}" for v in variants
           if v["req_level"] % STEP_SIZE or not 0 < v["req_level"] <= MAX_LEVEL])

    # Outside this range RandPropPoints has no row, so stats cannot be priced.
    check("item_level out of 1..284",
          [f"{v['entry']}@{v['item_level']}" for v in variants
           if not 0 < v["item_level"] <= 284])

    # The regression guard for the RequiredLevel = 0 inference bug: a base item
    # that declared no level used to inherit base level 1 and carry its original
    # item level down to the bottom of the game.  `Talbuk Cape` (25636) at ilvl
    # 105 became a level-10 ilvl-110 cloak.  353 variants looked like this
    # before the tier-curve inversion in infer_base_level; 0 after.
    #
    # Deliberately scoped to the INFERRED population.  A handful of items really
    # do declare RequiredLevel 1 while carrying endgame item levels -- the four
    # Ashen Verdict rings are reputation-gated rather than level-gated at ilvl
    # 251-277, plus two dev test items -- and honouring the source data there is
    # the documented contract: RequiredLevel is not a promise about power, and
    # the Quartermaster is where that gets capped (gen_quartermaster_pool.py,
    # build_ilvl_caps).  Overriding them would mean either moving every declared
    # level onto the curve -- which shifts 2,460 ordinary items by a level or two
    # of pure median-rounding noise, and mis-places low-level epics like Fiery
    # War Axe because the epic curve is too thin below 60 -- or inventing a
    # threshold.  Reported below instead.
    suspicious = [v for v in variants
                  if v["req_level"] <= 30 and v["item_level"] > 60]
    check("low-level variant carrying endgame item level",
          [f"{v['name']} {v['entry']} req{v['req_level']} ilvl{v['item_level']}"
           for v in suspicious if not v["declared"]])

    seen = set()
    dupes = [v["entry"] for v in variants
             if v["entry"] in seen or seen.add(v["entry"])]
    check("duplicate entry", dupes)
    check("entry below VARIANT_BASE",
          [v["entry"] for v in variants if v["entry"] < VARIANT_BASE])

    declared_odd = sorted({(v["name"], v["base_entry"]) for v in suspicious
                           if v["declared"]})
    if declared_odd:
        print(f"  note  {len(declared_odd)} base item(s) declare a low "
              f"RequiredLevel at a high ItemLevel; their ladders start low by "
              f"design, not by inference:")
        for name, entry in declared_odd:
            print(f"          {name} ({entry})")

    for f in failures:
        print(f"  FAIL  {f}")
    print("Validation: " + ("FAILED" if failures else f"OK ({len(variants)} variants)"))
    return not failures


def write_audit_csv(path, variants):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["entry", "base_entry", "name", "quality", "step",
                    "base_level", "target_level", "target_ilvl", "stat_mult",
                    "armor", "dmg_min1", "dmg_max1", "stat_sum"])
        for v in variants:
            w.writerow([v["entry"], v["base_entry"], v["name"], v["quality"],
                        v["step"], v["base_level"], v["req_level"],
                        v["item_level"], v["mult"], v["armor"],
                        v["dmg_min1"], v["dmg_max1"], sum(v["stats"])])


def next_sql_path():
    import datetime
    today = datetime.date.today().strftime("%Y_%m_%d")
    # The woa_ prefix is load-bearing: the updater orders ALL updates by bare
    # filename, and a duplicate aborts the entire world DB update.
    seq = 0
    while os.path.exists(os.path.join(MODULE_SQL, f"woa_{today}_{seq:02d}.sql")):
        seq += 1
    return os.path.join(MODULE_SQL, f"woa_{today}_{seq:02d}.sql")


def main():
    # Progress goes to stderr so `--stdout` emits SQL and nothing else -- it is
    # meant to be redirected into a file or piped straight into mysql.  The
    # redirect also captures read_int_dbc's own prints from build_dbc.
    import contextlib
    with contextlib.redirect_stdout(sys.stderr):
        args, payload = _run()
    if payload is not None:
        sys.stdout.write(payload)


def _run():
    p = argparse.ArgumentParser(description="Generate item upgrade variants")
    p.add_argument("--limit", type=int, help="cap variant count (sample runs)")
    p.add_argument("--dry-run", action="store_true", help="summary only")
    p.add_argument("--stdout", action="store_true", help="print SQL")
    p.add_argument("--audit-csv", help="write an audit CSV here")
    p.add_argument("--validate", action="store_true",
                   help="check invariants; exit non-zero and write nothing on failure")
    args = p.parse_args()

    rpp = load_rpp()
    conn = get_db_connection()
    rows = fetch_candidates(conn)
    conn.close()
    print(f"Candidate items: {len(rows)}")

    # Fitted first because infer_base_level reads it backwards to place items
    # that declare no RequiredLevel.
    tiers = fit_tier_curve(rows)
    # Armor shape depends on the armor class and the slot; weapon damage on the
    # weapon class alone.  Both are fitted against ItemLevel, never against
    # required level, so the census quirks that skewed the old buckets -- 41
    # main-hand-only swords averaging 110 dps against 109 one-handers averaging
    # 169 -- cannot reach them.
    armor_curves = fit_value_curve(
        rows, lambda r: (r["class"], r["subclass"], r["InventoryType"]),
        lambda r: r["armor"])
    dps_curves = fit_value_curve(
        rows, lambda r: r["subclass"],
        lambda r: ((r["dmg_min1"] + r["dmg_max1"]) / 2.0 / (r["delay"] / 1000.0))
        if (r["delay"] and r["dmg_max1"]) else 0)
    print(f"Tier curves: {len(tiers)} qualities, "
          f"{len(armor_curves)} armor shapes, {len(dps_curves)} weapon shapes")

    variants = generate(rows, rpp, tiers, armor_curves, dps_curves,
                        limit=args.limit)
    print(f"Variants generated: {len(variants)}")

    # Before anything is written: a bad batch should fail the run, not land in
    # the module's SQL directory where the updater will happily apply it.
    if args.validate and not validate(variants):
        sys.exit(1)

    by_quality = defaultdict(int)
    for v in variants:
        by_quality[v["quality"]] += 1
    for q in sorted(by_quality):
        print(f"  quality {q}: {by_quality[q]}")
    if variants:
        top = sorted(variants, key=lambda v: v["mult"], reverse=True)[:5]
        print("Highest multipliers (review these by hand):")
        for v in top:
            print(f"  {v['mult']:6.2f}x  {v['name']} ({v['base_level']} -> {v['req_level']})")

    if args.audit_csv:
        write_audit_csv(args.audit_csv, variants)
        print(f"Audit CSV: {args.audit_csv}")

    if args.dry_run or not variants:
        return args, None

    conn = get_db_connection()
    try:
        sql = format_sql(variants, conn)
    finally:
        conn.close()
    if args.stdout:
        return args, sql

    path = next_sql_path()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(sql)
    print(f"Wrote {path} ({len(sql) / 1_048_576:.1f} MB)")
    return args, None


if __name__ == "__main__":
    main()
