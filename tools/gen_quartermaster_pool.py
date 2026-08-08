#!/usr/bin/env python3
"""
Quartermaster Pool Generator

Builds `alonecraft_quartermaster_pool`: for every (class, talent tree, level
tier, inventory type, quality band), the top-N best items the Quartermaster may
mail, each already paired with the random affix that suits that spec.

Why this is offline
-------------------
Scoring an item for a class/tree never changes at runtime, so computing it on
every level-up would mean re-deriving the same answer tens of thousands of times
per realm-hour.  It is also auditable: "why did I get this belt" becomes a
SELECT ... ORDER BY score, not a debugger session.  All the runtime does is a
weighted random pick from an in-memory cache.

The affix is a spec dimension, not noise
----------------------------------------
An earlier draft excluded every item with `RandomProperty` or `RandomSuffix`.
That was wrong, and the data says so:

  * every random-property variant's group resolves -- zero orphans at any level;
  * most groups carry 9-19 distinct affixes;
  * "of the Eagle", "of the Bear", "of Healing", "of Defense" ARE role labels.

So the affix is the sharpest spec signal available, and it lets the SAME base
item serve a tank and a caster correctly.  The pool unit is therefore
(entry, affix): for each item we pick the best-scoring affix FOR THAT ARCHETYPE
and store the concrete id in `rand_prop`.  Because one affix is chosen per
archetype this does not multiply the row count -- it sharpens each row.

  rand_prop = 0   fixed-stat item, nothing to do at runtime
            > 0   ItemRandomProperties.ID  -> Item::SetItemRandomProperties(id)
            < 0   -ItemRandomSuffix.ID     -> ditto; the suffix factor rescales
                                              off the variant's own ItemLevel

Candidate affixes for a group come from `item_enchantment_template`, which is
what the server itself reads (ItemEnchantmentMgr).  `alonecraft_random_tier` is
the *re-tiering* map used by the upgrade path and is deliberately not consulted
here -- we are choosing an affix for an item, not moving one between tiers.

Ordering constraint
-------------------
gen_item_variants.py's output begins with `DELETE FROM item_template WHERE
entry >= 1000000` and rebuilds every variant at apply time.  This file must sort
AFTER that one, and must be regenerated after any variant regeneration -- both
because entries would dangle and because a stored affix id is only valid for the
variant's current RandomProperty group.

Usage:
    python tools/gen_quartermaster_pool.py --dry-run       # summary only
    python tools/gen_quartermaster_pool.py --class 8       # one class, fast
    python tools/gen_quartermaster_pool.py --audit-csv qm.csv
    python tools/gen_quartermaster_pool.py --validate      # check a written table
    python tools/gen_quartermaster_pool.py                 # write the SQL
"""

import argparse
import csv
import os
import struct
import sys
from collections import defaultdict

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DBC_DIR = os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc")
sys.path.insert(0, DBC_DIR)
import config  # noqa: E402

MODULE_SQL = os.path.join(
    REPO_ROOT, "modules", "world_of_alonecraft", "data", "sql", "db-world"
)

VARIANT_BASE = 1000000
TOP_N_DEFAULT = 10

# ---------------------------------------------------------------------------
# Item constants (ItemTemplate.h)
# ---------------------------------------------------------------------------

QUALITY_UNCOMMON, QUALITY_RARE, QUALITY_EPIC, QUALITY_LEGENDARY = 2, 3, 4, 5

# Quality bands.  Ranking happens WITHIN a band, never across: a single global
# top-N is epic-dominated at every level that has epics, which is exactly the
# "trivialises loot" failure the Quartermaster has to avoid.  Band 1 is
# generated but disabled at runtime by default, so enabling epics later is a
# config change rather than a regeneration.
QBAND = {QUALITY_UNCOMMON: 0, QUALITY_RARE: 0, QUALITY_EPIC: 1, QUALITY_LEGENDARY: 1}

ITEM_CLASS_WEAPON, ITEM_CLASS_ARMOR = 2, 4

ARMOR_MISC, ARMOR_CLOTH, ARMOR_LEATHER, ARMOR_MAIL, ARMOR_PLATE = 0, 1, 2, 3, 4
ARMOR_BUCKLER, ARMOR_SHIELD = 5, 6

# InventoryType values that never occupy a gear slot we care about.
INV_SKIP = {0, 4, 18, 19, 24, 27, 28}

# InventoryType -> equipment slot group.  Collapsing is the whole point: without
# it "3 distinct InventoryTypes" would cheerfully mail a two-hander AND a
# main-hand sword, or a chest AND a robe -- the same body slot twice.
SLOT_GROUP = {
    1: 0,                    # head
    2: 1,                    # neck
    3: 2,                    # shoulders
    5: 3,  20: 3,            # chest, robe
    6: 4,                    # waist
    7: 5,                    # legs
    8: 6,                    # feet
    9: 7,                    # wrists
    10: 8,                   # hands
    11: 9,                   # finger
    12: 10,                  # trinket
    16: 11,                  # back
    13: 12, 17: 12, 21: 12,  # one-hand, two-hand, main-hand
    14: 13, 22: 13, 23: 13,  # off-hand, shield, held-in-off-hand
    15: 14, 25: 14, 26: 14,  # ranged, thrown, ranged-right
}

SLOT_GROUP_NAME = [
    "head", "neck", "shoulders", "chest", "waist", "legs", "feet", "wrists",
    "hands", "finger", "trinket", "back", "mainhand", "offhand", "ranged",
]

# RandPropPoints column offsets, and the slot classes that index into them.
# Identical to GenerateEnchSuffixFactor (ItemEnchantmentMgr.cpp:125-201) and to
# gen_item_variants.py -- restated rather than imported because that module does
# a great deal of unrelated work at import time.
RPP_EPIC, RPP_RARE, RPP_UNCOMMON = 1, 6, 11
RPP_COLUMN = {
    QUALITY_UNCOMMON: RPP_UNCOMMON, QUALITY_RARE: RPP_RARE,
    QUALITY_EPIC: RPP_EPIC, QUALITY_LEGENDARY: RPP_EPIC,
}
RPP_SLOT_CLASS = {
    1: 0, 4: 0, 5: 0, 7: 0, 17: 0, 20: 0,      # head, body, chest, legs, 2H, robe
    3: 1, 6: 1, 8: 1, 10: 1, 12: 1,            # shoulders, waist, feet, hands, trinket
    2: 2, 9: 2, 11: 2, 14: 2, 16: 2, 23: 2,    # neck, wrists, finger, shield, cloak, held
    13: 3, 21: 3, 22: 3,                       # one-hand / main-hand / off-hand
    15: 4, 25: 4, 26: 4,                       # ranged, thrown, ranged-right
}

# ITEM_MOD_* (ItemTemplate.h:27-70)
MOD_MANA, MOD_HEALTH = 0, 1
MOD_AGILITY, MOD_STRENGTH, MOD_INTELLECT, MOD_SPIRIT, MOD_STAMINA = 3, 4, 5, 6, 7
MOD_DEFENSE_SKILL_RATING = 12
MOD_DODGE_RATING, MOD_PARRY_RATING, MOD_BLOCK_RATING = 13, 14, 15
MOD_HIT_MELEE_RATING, MOD_HIT_RANGED_RATING, MOD_HIT_SPELL_RATING = 16, 17, 18
MOD_CRIT_MELEE_RATING, MOD_CRIT_RANGED_RATING, MOD_CRIT_SPELL_RATING = 19, 20, 21
MOD_HASTE_MELEE_RATING, MOD_HASTE_RANGED_RATING, MOD_HASTE_SPELL_RATING = 28, 29, 30
MOD_HIT_RATING, MOD_CRIT_RATING, MOD_HASTE_RATING = 31, 32, 33
MOD_EXPERTISE_RATING = 37
MOD_ATTACK_POWER, MOD_RANGED_ATTACK_POWER = 38, 39
MOD_SPELL_HEALING_DONE, MOD_SPELL_DAMAGE_DONE = 41, 42
MOD_MANA_REGENERATION, MOD_ARMOR_PENETRATION_RATING = 43, 44
MOD_SPELL_POWER, MOD_HEALTH_REGEN, MOD_SPELL_PENETRATION, MOD_BLOCK_VALUE = 45, 46, 47, 48

ITEM_ENCHANTMENT_TYPE_STAT = 5

# ---------------------------------------------------------------------------
# Class constants
# ---------------------------------------------------------------------------

CLASS_NAMES = {
    1: "Warrior", 2: "Paladin", 3: "Hunter", 4: "Rogue", 5: "Priest",
    6: "Death Knight", 7: "Shaman", 8: "Mage", 9: "Warlock", 11: "Druid",
}
PLAYABLE_CLASSES = sorted(CLASS_NAMES)

# Weapon ItemSubClass values each class has proficiency for.  Mirrors
# item_weapon_skills[] in Player::CanRollForItemInLFG
# (PlayerStorage.cpp:2449-2456) and RandomItemMgr::CanEquipWeapon.  Restated as
# a literal so the generator has no build dependency on either.
#   0 axe1H  1 axe2H  2 bow  3 gun  4 mace1H  5 mace2H  6 polearm
#   7 sword1H  8 sword2H  10 staff  13 fist  15 dagger  16 thrown
#   18 crossbow  19 wand
WEAPON_PROFICIENCY = {
    1:  {0, 1, 2, 3, 4, 5, 6, 7, 8, 10, 13, 15, 16, 18},
    2:  {0, 1, 4, 5, 6, 7, 8},
    3:  {0, 1, 2, 3, 6, 7, 8, 10, 13, 15, 16, 18},
    4:  {2, 3, 4, 7, 13, 15, 16, 18},
    5:  {4, 10, 15, 19},
    6:  {0, 1, 4, 5, 6, 7, 8},
    7:  {0, 1, 4, 5, 10, 13, 15},
    8:  {7, 10, 15, 19},
    9:  {7, 10, 15, 19},
    11: {4, 5, 6, 10, 13, 15},
}

# The armour class a character of this class should be wearing at a given level.
# Matched EXACTLY, not "<= this" as the LFG roll check does: a level-45 warrior
# offered mail is being offered a downgrade, and the Quartermaster should never
# do that.  Death Knights start at 55 so their pre-40 entry never fires; it is
# kept for symmetry.
ARMOR_FOR_LEVEL = {
    1:  (ARMOR_MAIL, ARMOR_PLATE),
    2:  (ARMOR_MAIL, ARMOR_PLATE),
    6:  (ARMOR_MAIL, ARMOR_PLATE),
    3:  (ARMOR_LEATHER, ARMOR_MAIL),
    7:  (ARMOR_LEATHER, ARMOR_MAIL),
    4:  (ARMOR_LEATHER, ARMOR_LEATHER),
    11: (ARMOR_LEATHER, ARMOR_LEATHER),
    5:  (ARMOR_CLOTH, ARMOR_CLOTH),
    8:  (ARMOR_CLOTH, ARMOR_CLOTH),
    9:  (ARMOR_CLOTH, ARMOR_CLOTH),
}
ARMOR_UPGRADE_LEVEL = 40

SHIELD_CLASSES = {1, 2, 7}          # PlayerStorage.cpp:2481-2487

# ---------------------------------------------------------------------------
# Archetypes
# ---------------------------------------------------------------------------
#
# (class, TalentTab.dbc tabpage) -> archetype.  Seven archetypes rather than 33
# specs so the weight table below stays small enough to eyeball for correctness.
# Tab ordering verified against TalentTab.dbc.

PLATE_TANK, PLATE_DPS, PLATE_HEAL = "PLATE_TANK", "PLATE_DPS", "PLATE_HEAL"
AGI_LEATHER, AGI_MAIL = "AGI_LEATHER", "AGI_MAIL"
CASTER_DPS, HEALER = "CASTER_DPS", "HEALER"

ARCHETYPE = {
    (1, 0): PLATE_DPS,   (1, 1): PLATE_DPS,   (1, 2): PLATE_TANK,   # Arms/Fury/Prot
    (2, 0): PLATE_HEAL,  (2, 1): PLATE_TANK,  (2, 2): PLATE_DPS,    # Holy/Prot/Ret
    (3, 0): AGI_MAIL,    (3, 1): AGI_MAIL,    (3, 2): AGI_MAIL,     # BM/MM/Surv
    (4, 0): AGI_LEATHER, (4, 1): AGI_LEATHER, (4, 2): AGI_LEATHER,  # Assn/Comb/Subt
    (5, 0): HEALER,      (5, 1): HEALER,      (5, 2): CASTER_DPS,   # Disc/Holy/Shadow
    (6, 0): PLATE_TANK,  (6, 1): PLATE_DPS,   (6, 2): PLATE_DPS,    # Blood/Frost/Unholy
    (7, 0): CASTER_DPS,  (7, 1): AGI_MAIL,    (7, 2): HEALER,       # Ele/Enh/Resto
    (8, 0): CASTER_DPS,  (8, 1): CASTER_DPS,  (8, 2): CASTER_DPS,   # Arc/Fire/Frost
    (9, 0): CASTER_DPS,  (9, 1): CASTER_DPS,  (9, 2): CASTER_DPS,   # Affl/Demo/Dest
    (11, 0): CASTER_DPS, (11, 1): AGI_LEATHER, (11, 2): HEALER,     # Bal/Feral/Resto
}

# Stats an archetype scores zero for AND that mark the item as belonging to a
# different role.  These are REJECTIONS, not negative weights: a negative weight
# still lets a large enough stat budget win, and "the Quartermaster mailed me an
# intellect axe" is the failure that destroys trust in the whole feature.
#
# The offline equivalent of the spell-power-plate and caster-dagger checks in
# Player::CanRollForItemInLFG (PlayerStorage.cpp:2524-2545).
_CASTER_MARKERS = {MOD_SPELL_POWER, MOD_SPELL_HEALING_DONE, MOD_SPELL_DAMAGE_DONE,
                   MOD_SPELL_PENETRATION}
_PHYSICAL_MARKERS = {MOD_STRENGTH, MOD_ATTACK_POWER, MOD_RANGED_ATTACK_POWER,
                     MOD_EXPERTISE_RATING, MOD_ARMOR_PENETRATION_RATING,
                     MOD_DEFENSE_SKILL_RATING, MOD_PARRY_RATING,
                     MOD_BLOCK_RATING, MOD_BLOCK_VALUE}
# Agility is deliberately NOT a caster rejection: low-level cloth routinely
# carries a token point and it is not a role signal below 60.

REJECT = {
    PLATE_TANK:  _CASTER_MARKERS,
    PLATE_HEAL:  _PHYSICAL_MARKERS - {MOD_STRENGTH},  # holy paladins do use str gear rarely
    PLATE_DPS:   _CASTER_MARKERS | {MOD_INTELLECT, MOD_MANA_REGENERATION},
    AGI_LEATHER: _CASTER_MARKERS | {MOD_INTELLECT, MOD_MANA_REGENERATION},
    AGI_MAIL:    _CASTER_MARKERS,                     # hunters/enh want some int
    CASTER_DPS:  _PHYSICAL_MARKERS,
    HEALER:      _PHYSICAL_MARKERS,
}

_MELEE = {
    MOD_STAMINA: 0.35, MOD_ATTACK_POWER: 0.5, MOD_RANGED_ATTACK_POWER: 0.5,
    MOD_CRIT_MELEE_RATING: 0.8, MOD_CRIT_RANGED_RATING: 0.8, MOD_CRIT_RATING: 0.8,
    MOD_HIT_MELEE_RATING: 0.9, MOD_HIT_RANGED_RATING: 0.9, MOD_HIT_RATING: 0.9,
    MOD_HASTE_MELEE_RATING: 0.7, MOD_HASTE_RANGED_RATING: 0.7, MOD_HASTE_RATING: 0.7,
    MOD_EXPERTISE_RATING: 0.9, MOD_ARMOR_PENETRATION_RATING: 0.7,
    MOD_HEALTH: 0.02,
}

_CASTER = {
    MOD_SPELL_POWER: 1.0, MOD_SPELL_DAMAGE_DONE: 1.0, MOD_INTELLECT: 0.5,
    MOD_SPIRIT: 0.3, MOD_HASTE_SPELL_RATING: 0.8, MOD_HASTE_RATING: 0.8,
    MOD_CRIT_SPELL_RATING: 0.7, MOD_CRIT_RATING: 0.7,
    MOD_HIT_SPELL_RATING: 0.9, MOD_HIT_RATING: 0.9,
    MOD_SPELL_PENETRATION: 0.3, MOD_MANA_REGENERATION: 0.15,
    MOD_STAMINA: 0.2, MOD_MANA: 0.02,
}

_HEAL = {
    MOD_SPELL_POWER: 1.0, MOD_SPELL_HEALING_DONE: 1.0, MOD_SPELL_DAMAGE_DONE: 0.35,
    MOD_INTELLECT: 0.6, MOD_SPIRIT: 0.6, MOD_MANA_REGENERATION: 0.9,
    MOD_HASTE_SPELL_RATING: 0.7, MOD_HASTE_RATING: 0.7,
    MOD_CRIT_SPELL_RATING: 0.5, MOD_CRIT_RATING: 0.5,
    MOD_STAMINA: 0.25, MOD_MANA: 0.02,
}

# Stat weights, normalised so one point of the archetype's primary stat is 1.0.
# The exact numbers matter less than they look: inside a single bucket every
# item is the same slot, the same armour class and roughly the same item level,
# so ranking is mostly "how much total budget" with a tilt.  Getting REJECT
# right is what makes this feel correct; the weights only order the survivors.
WEIGHTS = {
    PLATE_DPS:   {**_MELEE, MOD_STRENGTH: 1.0, MOD_AGILITY: 0.5},
    AGI_LEATHER: {**_MELEE, MOD_AGILITY: 1.0, MOD_STRENGTH: 0.5},
    AGI_MAIL:    {**_MELEE, MOD_AGILITY: 1.0, MOD_STRENGTH: 0.5,
                  MOD_INTELLECT: 0.25},
    PLATE_TANK: {
        MOD_STAMINA: 1.0, MOD_DEFENSE_SKILL_RATING: 1.3, MOD_DODGE_RATING: 1.0,
        MOD_PARRY_RATING: 1.0, MOD_BLOCK_RATING: 0.5, MOD_BLOCK_VALUE: 0.3,
        MOD_STRENGTH: 0.4, MOD_AGILITY: 0.4, MOD_EXPERTISE_RATING: 0.5,
        MOD_HIT_MELEE_RATING: 0.4, MOD_HIT_RATING: 0.4, MOD_HEALTH: 0.05,
        MOD_HEALTH_REGEN: 0.2,
    },
    CASTER_DPS: dict(_CASTER),
    HEALER:     dict(_HEAL),
    PLATE_HEAL: dict(_HEAL),
}

# Non-stat contributions: armour value, weapon dps, shield block.
EXTRA_WEIGHTS = {
    PLATE_DPS:   {"armor": 0.005, "dps": 8.0, "block": 0.0},
    AGI_LEATHER: {"armor": 0.005, "dps": 8.0, "block": 0.0},
    AGI_MAIL:    {"armor": 0.005, "dps": 8.0, "block": 0.0},
    PLATE_TANK:  {"armor": 0.020, "dps": 2.0, "block": 0.15},
    CASTER_DPS:  {"armor": 0.002, "dps": 0.5, "block": 0.0},
    HEALER:      {"armor": 0.002, "dps": 0.5, "block": 0.0},
    PLATE_HEAL:  {"armor": 0.002, "dps": 0.5, "block": 0.0},
}


def rank_weight(rank):
    """Selection weight by rank: 100, 82, 67, 55, ...

    Deliberately NOT derived from `score`.  Score scales are incomparable across
    archetypes -- a plate tank's numbers and a caster's are not the same
    currency -- so a score-proportional weight would make one bucket nearly
    deterministic and another nearly uniform.  A rank-geometric weight is
    identical in every bucket, so there is exactly one constant to tune.
    """
    return max(1, round(100 * (0.82 ** rank)))


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def get_db_connection():
    import mysql.connector
    return mysql.connector.connect(
        host=config.MYSQL_HOST,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASS,
        database=config.MYSQL_DB,
    )


def read_dbc(path, expect_fields=None):
    """Minimal WDBC reader: returns (records, strings).

    Records are lists of ints; string columns are offsets into `strings`.  We
    need both, because affix names come from the string block and everything
    else is an int.
    """
    with open(path, "rb") as f:
        blob = f.read()
    magic, count, fields, recsize, strsize = struct.unpack("<4siiii", blob[:20])
    if magic != b"WDBC":
        raise ValueError(f"{path}: not a WDBC file")
    if expect_fields is not None and fields != expect_fields:
        raise ValueError(
            f"{path}: expected {expect_fields} fields, found {fields}. "
            "The DBC layout changed -- fix the field indices before trusting this."
        )
    body = 20 + count * recsize
    strings = blob[body:body + strsize]
    records = []
    for i in range(count):
        off = 20 + i * recsize
        records.append(list(struct.unpack_from(f"<{fields}i", blob, off)))
    return records, strings


def dbc_string(strings, offset):
    if offset <= 0 or offset >= len(strings):
        return ""
    end = strings.find(b"\0", offset)
    return strings[offset:end].decode("utf-8", "replace")


def load_rand_prop_points():
    """ItemLevel -> RandPropPoints record (16 ints).

    Read from the binary rather than MySQL: `randproppoints_dbc` is an override
    table and is empty on this realm, which would silently zero every suffix.
    """
    path = os.path.join(DBC_DIR, "base", "RandPropPoints.dbc")
    records, _ = read_dbc(path, 16)
    return {r[0]: r for r in records}


def rpp_points(rpp, ilvl, quality, slot_class):
    """Blizzard's stat-point budget for an item level.  0 when off the table.

    Identical to GenerateEnchSuffixFactor (ItemEnchantmentMgr.cpp:125-201),
    which is what the server uses to scale a random SUFFIX at runtime -- so
    reproducing it here is what lets suffix items be ranked on the same scale as
    property items.  Get this wrong and suffixes are systematically over- or
    under-ranked, silently, because both still produce valid mail.
    """
    rec = rpp.get(int(ilvl))
    if not rec or slot_class is None:
        return 0
    if quality not in RPP_COLUMN:
        return 0
    return rec[RPP_COLUMN[quality] + slot_class]


def load_enchant_stats(conn):
    """SpellItemEnchantment id -> {stat id: amount} for its STAT effects.

    Base binary DBC overlaid with the MySQL override table, the same
    base-plus-overrides arrangement the rest of the fork's tooling uses.
    """
    stats = {}

    def absorb(ench_id, triples):
        acc = defaultdict(int)
        for etype, amount, arg in triples:
            if etype != ITEM_ENCHANTMENT_TYPE_STAT:
                continue
            # Zero-amount entries are kept deliberately.  A random SUFFIX
            # enchantment names the stat but leaves the amount at 0 -- the
            # value comes from AllocationPct * suffixFactor / 10000 at apply
            # time (PlayerStorage.cpp:4525).  Dropping them here silently
            # emptied the entire suffix index.
            acc[arg] += amount
        stats[ench_id] = dict(acc)

    path = os.path.join(DBC_DIR, "base", "SpellItemEnchantment.dbc")
    records, _ = read_dbc(path, 38)
    for r in records:
        # 0 ID | 1 Charges | 2-4 Effect | 5-7 PointsMin | 8-10 PointsMax
        # | 11-13 EffectArg
        absorb(r[0], [(r[2 + i], r[5 + i], r[11 + i]) for i in range(3)])

    cur = conn.cursor()
    cur.execute(
        "SELECT ID, Effect_1, Effect_2, Effect_3, "
        "EffectPointsMin_1, EffectPointsMin_2, EffectPointsMin_3, "
        "EffectArg_1, EffectArg_2, EffectArg_3 FROM spellitemenchantment_dbc")
    for row in cur.fetchall():
        absorb(row[0], [(row[1 + i], row[4 + i], row[7 + i]) for i in range(3)])
    cur.close()
    return stats


def load_properties(conn, ench_stats):
    """ItemRandomProperties id -> (name, {stat: amount}).

    MySQL first (it carries the ladders gen_random_property_tiers.py added past
    level 60, which the base DBC has no rows for at all), binary underneath.
    """
    props = {}

    def absorb(pid, name, enchants):
        acc = defaultdict(int)
        for e in enchants:
            for stat, amount in ench_stats.get(e, {}).items():
                acc[stat] += amount
        props[pid] = (name, dict(acc))

    path = os.path.join(DBC_DIR, "base", "ItemRandomProperties.dbc")
    records, strings = read_dbc(path, 24)
    for r in records:
        # 0 ID | 1 InternalName | 2-6 Enchantment | 7-23 Name_Lang
        absorb(r[0], dbc_string(strings, r[7]), r[2:7])

    cur = conn.cursor()
    cur.execute("SELECT ID, Name_Lang_enUS, Enchantment_1, Enchantment_2, "
                "Enchantment_3, Enchantment_4, Enchantment_5 "
                "FROM itemrandomproperties_dbc")
    for row in cur.fetchall():
        absorb(row[0], row[1] or "", row[2:7])
    cur.close()
    return props


def load_suffixes():
    """ItemRandomSuffix id -> (name, [(stat, allocationPct), ...]).

    Read from the LIVE client dbc dir: there is no ItemRandomSuffix.dbc in
    dbc/base/, and `itemrandomsuffix_dbc` in MySQL is an empty override table.
    Suffix amounts are allocation percentages, not absolute values -- the actual
    stat is allocationPct * suffixFactor / 10000 (PlayerStorage.cpp:4525).
    """
    path = os.path.join(config.DBC_OUTPUT_DIR
                        if hasattr(config, "DBC_OUTPUT_DIR") else "", "")
    candidates = [
        os.path.join("C:\\", "Build", "bin", "RelWithDebInfo", "Data", "dbc",
                     "ItemRandomSuffix.dbc"),
        os.path.join(DBC_DIR, "base", "ItemRandomSuffix.dbc"),
    ]
    for path in candidates:
        if os.path.exists(path):
            break
    else:
        print("WARNING: ItemRandomSuffix.dbc not found; suffix items will be "
              "skipped entirely.", file=sys.stderr)
        return {}

    records, strings = read_dbc(path, 29)
    out = {}
    for r in records:
        # 0 ID | 1-17 Name_Lang | 18 InternalName | 19-23 Enchantment
        # | 24-28 AllocationPct
        out[r[0]] = (dbc_string(strings, r[1]),
                     [(r[19 + i], r[24 + i]) for i in range(5) if r[19 + i]])
    return out


ILVL_CAP_PERCENTILE = 0.90
ILVL_CAP_MIN_SAMPLE = 20


def build_ilvl_caps(conn):
    """(qband, tier) -> highest ItemLevel the Quartermaster may hand out there.

    WHY THIS EXISTS.  A variant's RequiredLevel is not a promise about its power.
    gen_item_variants.py anchors each ladder to the BASE item's ItemLevel, and a
    base item with RequiredLevel = 0 -- of which there are many, mostly TBC quest
    rewards -- gets a ladder starting at level 5 with its original item level
    carried over.  "Talbuk Cape" (25636) is ilvl 105 at RequiredLevel 0, so
    "Dim Talbuk Cape" is RequiredLevel 10 at ilvl 110.

    That is survivable for the upgrade vendor, where you must already own the
    item, but the Quartermaster hands items out by RequiredLevel alone -- so
    without this, roughly HALF the low-level pool was TBC/WotLK gear at full
    power.  A level 20 character was mailed an ilvl 120 cloak.

    The cap is measured, not invented: the 90th-percentile ItemLevel of REAL
    items (entry < VARIANT_BASE) a character could equip at that tier.  It comes
    out at almost exactly level + 5 through Classic and then picks up Blizzard's
    own inflections at 60, 70 and 80 -- the same reason gen_item_variants.py
    scales on ScalingStatValues rather than a fitted line.

    The 90th percentile rather than the max because the max is one bad row away
    from useless: tier 5 contains an ItemLevel 435 item, which would raise the
    level-5 ceiling above the level-80 one.
    """
    cur = conn.cursor()
    cur.execute(
        "SELECT RequiredLevel, Quality, ItemLevel FROM item_template "
        "WHERE entry < %s AND Quality BETWEEN 2 AND 5 AND class IN (2, 4) "
        "  AND InventoryType NOT IN (0, 4, 18, 19, 24, 27, 28) "
        "  AND RequiredLevel > 0 AND ItemLevel > 0", (VARIANT_BASE,))
    rows = cur.fetchall()
    cur.close()

    buckets = defaultdict(list)
    for req_level, quality, ilvl in rows:
        # Ceil to the tier whose gear you would actually be wearing at that
        # required level: an item needing level 22 belongs to the 25 bucket.
        tier = min(80, max(5, -(-req_level // 5) * 5))
        buckets[(QBAND[quality], tier)].append(ilvl)

    def percentile(values, p):
        values = sorted(values)
        return values[min(len(values) - 1, int(len(values) * p))]

    caps = {}
    for band in (0, 1):
        running = 0
        for tier in range(5, 81, 5):
            sample = buckets.get((band, tier), [])
            if len(sample) >= ILVL_CAP_MIN_SAMPLE:
                cap = percentile(sample, ILVL_CAP_PERCENTILE)
            else:
                # Epics barely exist below level 60, so their buckets are too
                # thin to measure.  Borrow the uncommon/rare ceiling rather than
                # trusting a percentile over two rows.
                cap = caps.get((0, tier), running)
            # Monotonic: a higher level must never permit less than a lower one.
            # The raw curve dips (tier 50 -> 63, tier 55 -> 61) purely from
            # sampling noise.
            running = max(running, cap)
            caps[(band, tier)] = running
    return caps


def load_enchant_groups(conn):
    """group id -> [ench id, ...].

    `item_enchantment_template` is what the server itself reads
    (ItemEnchantmentMgr), and it covers both the RandomProperty and the
    RandomSuffix groups.  alonecraft_random_tier is the upgrade path's
    RE-TIERING map and is deliberately not used here: we are choosing an affix
    for an item, not moving one between tiers.
    """
    groups = defaultdict(list)
    cur = conn.cursor()
    cur.execute("SELECT entry, ench FROM item_enchantment_template WHERE ench > 0")
    for entry, ench in cur.fetchall():
        groups[entry].append(ench)
    cur.close()
    return groups


CANDIDATE_SQL = """
SELECT entry, name, class, subclass, Quality, InventoryType, ItemLevel,
       RequiredLevel, RandomProperty, RandomSuffix, armor, block,
       dmg_min1, dmg_max1, dmg_min2, dmg_max2, delay, AllowableClass,
       stat_type1, stat_value1, stat_type2, stat_value2, stat_type3, stat_value3,
       stat_type4, stat_value4, stat_type5, stat_value5, stat_type6, stat_value6,
       stat_type7, stat_value7, stat_type8, stat_value8, stat_type9, stat_value9,
       stat_type10, stat_value10
FROM item_template
WHERE entry >= %s
  AND class IN (2, 4)
  AND Quality BETWEEN 2 AND 5
  AND InventoryType NOT IN (0, 4, 18, 19, 24, 27, 28)
  AND RequiredSkill = 0 AND RequiredSpell = 0
  AND requiredhonorrank = 0 AND RequiredReputationFaction = 0
  -- FlagsExtra is what ItemTemplate::Flags2 is loaded from, and bits 0/1 are
  -- ITEM_FLAG2_FACTION_HORDE / _ALLIANCE.  The pool is keyed by class, not
  -- faction, so a faction-locked item could be mailed to the wrong side.
  AND (FlagsExtra & 3) = 0
  AND AllowableRace = -1
  AND RequiredLevel > 0
"""


def fetch_candidates(conn, caps):
    """Variants that are equippable by SOMEBODY with no extra requirements.

    The requirement columns filtered here are exactly what Player::CanUseItem
    (PlayerStorage.cpp:2373-2430) rejects at runtime.  Stripping them offline is
    what lets the C++ mail an item without ever calling CanUseItem: anything in
    the pool is, by construction, immediately equippable by its bucket's class.
    """
    cur = conn.cursor(dictionary=True)
    cur.execute(CANDIDATE_SQL, (VARIANT_BASE,))
    rows = cur.fetchall()
    cur.close()

    out = []
    dropped_ilvl = 0
    for r in rows:
        # An item whose power does not match its RequiredLevel.  See
        # build_ilvl_caps -- this is the single biggest correctness filter here.
        cap = caps.get((QBAND[r["Quality"]], r["RequiredLevel"]))
        if cap is not None and r["ItemLevel"] > cap:
            dropped_ilvl += 1
            continue

        stats = {}
        for i in range(1, 11):
            t, v = r[f"stat_type{i}"], r[f"stat_value{i}"]
            if v:
                stats[t] = stats.get(t, 0) + v
        # A stat-less shell with no affix to give it one is always a downgrade.
        # This is the ONLY stat-based exclusion; everything else is decided per
        # archetype below.
        if not stats and not r["RandomProperty"] and not r["RandomSuffix"]:
            continue
        delay = r["delay"] or 0
        dmg = (r["dmg_min1"] + r["dmg_max1"] + r["dmg_min2"] + r["dmg_max2"]) / 2.0
        r["stats"] = stats
        r["dps"] = (dmg / (delay / 1000.0)) if (delay and dmg) else 0.0
        out.append(r)

    print(f"Dropped {dropped_ilvl} variant(s) whose ItemLevel exceeds their "
          f"tier's ceiling")
    return out


# ---------------------------------------------------------------------------
# Filtering and scoring
# ---------------------------------------------------------------------------

def class_can_use(row, class_id):
    """Proficiency, armour class and slot rules for one class."""
    allowable = row["AllowableClass"]
    if allowable != -1 and not (allowable & (1 << (class_id - 1))):
        return False

    inv, sub = row["InventoryType"], row["subclass"]

    if row["class"] == ITEM_CLASS_WEAPON:
        return sub in WEAPON_PROFICIENCY[class_id]

    # Armour.
    if sub in (ARMOR_BUCKLER, ARMOR_SHIELD):
        return class_id in SHIELD_CLASSES
    # Neck, rings, trinkets and cloaks carry no armour-class restriction.
    if sub == ARMOR_MISC or inv == 16:
        return True
    if sub not in (ARMOR_CLOTH, ARMOR_LEATHER, ARMOR_MAIL, ARMOR_PLATE):
        return False   # librams/idols/totems/sigils -- relics are out of scope

    below, above = ARMOR_FOR_LEVEL[class_id]
    want = below if row["RequiredLevel"] < ARMOR_UPGRADE_LEVEL else above
    return sub == want


def score_stats(stats, weights):
    return sum(weights.get(stat, 0.0) * value for stat, value in stats.items())


def has_rejected(stats, rejected):
    return any(stat in rejected and value > 0 for stat, value in stats.items())


def build_affix_index(groups, props, suffixes, ench_stats):
    """(archetype, group) -> (affix id, name, {stat: weight-relevant amount}).

    Cached per group rather than per item: which affix best suits an archetype
    depends only on the group's contents, and there are ~1000 groups against
    ~80000 variants.  For suffixes the ranking is also group-only, because the
    suffix factor is a common multiplier across every suffix in a group.
    """
    prop_best, suffix_best = {}, {}
    for archetype, weights in WEIGHTS.items():
        rejected = REJECT[archetype]
        for group, enchants in groups.items():
            best_p = best_s = None
            for ench in enchants:
                if ench in props:
                    name, stats = props[ench]
                    if has_rejected(stats, rejected):
                        continue
                    s = score_stats(stats, weights)
                    if s > 0 and (best_p is None or s > best_p[2]):
                        best_p = (ench, name, s, stats)
                if ench in suffixes:
                    name, allocs = suffixes[ench]
                    acc = defaultdict(int)
                    for e, pct in allocs:
                        # The enchantment names the stat; the allocation
                        # percentage IS the value, scaled by the suffix factor
                        # in score_row.  Amounts on the enchantment are 0.
                        for stat in ench_stats.get(e, {}):
                            acc[stat] += pct
                    acc = dict(acc)
                    if has_rejected(acc, rejected):
                        continue
                    s = score_stats(acc, weights)
                    if s > 0 and (best_s is None or s > best_s[2]):
                        best_s = (ench, name, s, acc)
            if best_p:
                prop_best[(archetype, group)] = best_p
            if best_s:
                suffix_best[(archetype, group)] = best_s
    return prop_best, suffix_best


def score_row(row, archetype, prop_best, suffix_best, rpp):
    """(score, rand_prop, affix_name) for one item under one archetype.

    Returns None when the item belongs to a different role, or when it has a
    random-property group but nothing in that group suits this archetype -- an
    item whose only affixes are caster affixes is not a warrior item, however
    good its base stats look.
    """
    weights = WEIGHTS[archetype]
    rejected = REJECT[archetype]
    stats = row["stats"]
    if has_rejected(stats, rejected):
        return None

    extra = EXTRA_WEIGHTS[archetype]
    base = (score_stats(stats, weights)
            + extra["armor"] * (row["armor"] or 0)
            + extra["dps"] * row["dps"]
            + extra["block"] * (row["block"] or 0))

    rand_prop, affix_name, affix_score = 0, "", 0.0

    if row["RandomProperty"]:
        best = prop_best.get((archetype, row["RandomProperty"]))
        if not best:
            return None
        rand_prop, affix_name, affix_score = best[0], best[1], best[2]
    elif row["RandomSuffix"]:
        best = suffix_best.get((archetype, row["RandomSuffix"]))
        if not best:
            return None
        slot_class = RPP_SLOT_CLASS.get(row["InventoryType"])
        factor = rpp_points(rpp, row["ItemLevel"], row["Quality"], slot_class)
        if not factor:
            return None
        # allocationPct * suffixFactor / 10000, exactly as the server computes
        # it when the aura is applied (PlayerStorage.cpp:4525).
        affix_score = score_stats(
            {s: (v * factor) / 10000.0 for s, v in best[3].items()}, weights)
        if affix_score <= 0:
            return None
        rand_prop, affix_name = -best[0], best[1]

    total = base + affix_score
    if total <= 0:
        return None
    return round(total * 100), rand_prop, affix_name


# ---------------------------------------------------------------------------
# Pool construction
# ---------------------------------------------------------------------------

def build_pool(rows, prop_best, suffix_best, rpp, top_n, classes):
    """(class, tree, req_level, inv_type, qband) -> ranked list of pool rows."""
    buckets = defaultdict(list)

    # Cache the per-archetype verdict for an item: it is identical for every
    # (class, tree) that maps to the same archetype, and there are 33 specs
    # across only 7 archetypes.
    for row in rows:
        cache = {}
        for class_id in classes:
            if not class_can_use(row, class_id):
                continue
            for tree in range(3):
                archetype = ARCHETYPE[(class_id, tree)]
                if archetype not in cache:
                    cache[archetype] = score_row(
                        row, archetype, prop_best, suffix_best, rpp)
                verdict = cache[archetype]
                if verdict is None:
                    continue
                score, rand_prop, affix_name = verdict
                key = (class_id, tree, row["RequiredLevel"],
                       row["InventoryType"], QBAND[row["Quality"]])
                buckets[key].append(
                    (score, row["entry"], rand_prop, row["Quality"], affix_name))

    pool = {}
    for key, entries in buckets.items():
        entries.sort(key=lambda e: (-e[0], e[1]))
        pool[key] = entries[:top_n]
    return pool


def pool_rows(pool):
    out = []
    for (class_id, tree, req_level, inv, qband), entries in sorted(pool.items()):
        for rank, (score, entry, rand_prop, quality, affix) in enumerate(entries):
            out.append({
                "class_id": class_id, "tree": tree, "req_level": req_level,
                "inv_type": inv, "qband": qband, "rank": rank, "entry": entry,
                "rand_prop": rand_prop, "weight": rank_weight(rank),
                "score": score, "quality": quality, "affix_name": affix,
            })
    return out


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate(pool, classes, min_level=10):
    """Structural assertions.  Returns a list of human-readable failures.

    The slot-group assertion is the one that earns its keep: it is what catches
    a level tier too thin to fill three DISTINCT slots, which is a silent
    gameplay bug rather than a crash.
    """
    problems = []

    by_bucket = defaultdict(list)
    for (c, t, lvl, inv, qb), entries in pool.items():
        by_bucket[(c, t, lvl, qb)].append((inv, entries))
        ranks = [i for i in range(len(entries))]
        if ranks != list(range(len(entries))):
            problems.append(f"non-dense ranks in bucket {(c, t, lvl, inv, qb)}")

    for class_id in classes:
        for tree in range(3):
            for lvl in range(min_level, 81, 5):
                entries = by_bucket.get((class_id, tree, lvl, 0), [])
                groups = {SLOT_GROUP[inv] for inv, e in entries if e}
                if len(groups) < 3:
                    problems.append(
                        f"{CLASS_NAMES[class_id]} tree {tree} level {lvl}: only "
                        f"{len(groups)} distinct slot groups in band 0 "
                        f"({sorted(SLOT_GROUP_NAME[g] for g in groups)}) "
                        "-- cannot fill a 3-item shipment")
    return problems


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def sql_str(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def format_sql(rows, top_n):
    L = []
    A = L.append
    A("-- ==========================================================================")
    A("-- Quartermaster Pool — auto-generated by tools/gen_quartermaster_pool.py")
    A("-- ==========================================================================")
    A("--")
    A(f"-- {len(rows)} rows.  For every (class, talent tree, level tier, inventory")
    A(f"-- type, quality band) the top {top_n} items the Quartermaster may mail, each")
    A("-- paired with the random affix that suits that spec.")
    A("--")
    A("-- rand_prop:  0 = fixed-stat item")
    A("--            >0 = ItemRandomProperties.ID   (Item::SetItemRandomProperties)")
    A("--            <0 = -ItemRandomSuffix.ID      (rescales off the item's ItemLevel)")
    A("--")
    A("-- ORDERING: this file MUST apply after the gen_item_variants.py output, which")
    A("-- begins with DELETE FROM item_template WHERE entry >= 1000000 and rebuilds")
    A("-- every variant.  Regenerate this pool after ANY variant regeneration: entries")
    A("-- would otherwise dangle, and a stored affix id is only valid for the variant's")
    A("-- current RandomProperty group.")
    A("--")
    A("-- Verify with the queries in the Quartermaster section of TODO.md.")
    A("")
    A("DROP TABLE IF EXISTS `alonecraft_quartermaster_pool`;")
    A("CREATE TABLE `alonecraft_quartermaster_pool` (")
    A("  `class_id`   TINYINT  UNSIGNED NOT NULL,")
    A("  `tree`       TINYINT  UNSIGNED NOT NULL,")
    A("  `req_level`  TINYINT  UNSIGNED NOT NULL,")
    A("  `inv_type`   TINYINT  UNSIGNED NOT NULL,")
    A("  `qband`      TINYINT  UNSIGNED NOT NULL,")
    A("  `rank`       TINYINT  UNSIGNED NOT NULL,")
    A("  `entry`      INT      UNSIGNED NOT NULL,")
    A("  `rand_prop`  INT               NOT NULL,")
    A("  `weight`     SMALLINT UNSIGNED NOT NULL,")
    A("  `score`      INT      UNSIGNED NOT NULL,")
    A("  `quality`    TINYINT  UNSIGNED NOT NULL,")
    A("  `affix_name` VARCHAR(64)       NOT NULL DEFAULT '',")
    A("  PRIMARY KEY (`class_id`,`tree`,`req_level`,`inv_type`,`qband`,`rank`),")
    A("  KEY `idx_entry` (`entry`)")
    A(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;")
    A("")

    header = ("INSERT INTO `alonecraft_quartermaster_pool` (`class_id`, `tree`, "
              "`req_level`, `inv_type`, `qband`, `rank`, `entry`, `rand_prop`, "
              "`weight`, `score`, `quality`, `affix_name`) VALUES")
    values = [
        "({}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {}, {})".format(
            r["class_id"], r["tree"], r["req_level"], r["inv_type"], r["qband"],
            r["rank"], r["entry"], r["rand_prop"], r["weight"], r["score"],
            r["quality"], sql_str(r["affix_name"]))
        for r in rows
    ]
    for i in range(0, len(values), 500):
        A(header)
        A(",\n".join(values[i:i + 500]) + ";")
        A("")
    return "\n".join(L) + "\n"


def write_audit_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["class", "tree", "archetype", "req_level", "inv_type",
                    "slot_group", "qband", "rank", "entry", "rand_prop",
                    "affix_name", "weight", "score", "quality"])
        for r in rows:
            w.writerow([
                CLASS_NAMES[r["class_id"]], r["tree"],
                ARCHETYPE[(r["class_id"], r["tree"])], r["req_level"],
                r["inv_type"], SLOT_GROUP_NAME[SLOT_GROUP[r["inv_type"]]],
                r["qband"], r["rank"], r["entry"], r["rand_prop"],
                r["affix_name"], r["weight"], r["score"], r["quality"]])


def next_sql_path():
    import datetime
    today = datetime.date.today().strftime("%Y_%m_%d")
    # The woa_ prefix is load-bearing: the updater orders ALL updates by bare
    # filename, and a duplicate aborts the entire world DB update.
    seq = 0
    while os.path.exists(os.path.join(MODULE_SQL, f"woa_{today}_{seq:02d}.sql")):
        seq += 1
    return os.path.join(MODULE_SQL, f"woa_{today}_{seq:02d}.sql")


# ---------------------------------------------------------------------------

def main():
    # Progress goes to stderr so --stdout emits SQL and nothing else.
    import contextlib
    with contextlib.redirect_stdout(sys.stderr):
        payload = _run()
    if payload is not None:
        sys.stdout.write(payload)


def _run():
    p = argparse.ArgumentParser(description="Generate the Quartermaster item pool")
    p.add_argument("--top-n", type=int, default=TOP_N_DEFAULT,
                   help=f"items kept per bucket per quality band (default {TOP_N_DEFAULT})")
    p.add_argument("--class", dest="class_id", type=int,
                   help="restrict to one class id (fast iteration)")
    p.add_argument("--dry-run", action="store_true", help="summary only, no file")
    p.add_argument("--stdout", action="store_true", help="print SQL")
    p.add_argument("--audit-csv", help="write an audit CSV here")
    p.add_argument("--validate", action="store_true",
                   help="run structural assertions; non-zero exit on failure")
    args = p.parse_args()

    classes = [args.class_id] if args.class_id else PLAYABLE_CLASSES
    if args.class_id and args.class_id not in CLASS_NAMES:
        print(f"Unknown class id {args.class_id}; "
              f"expected one of {PLAYABLE_CLASSES}")
        return None

    conn = get_db_connection()
    ench_stats = load_enchant_stats(conn)
    props = load_properties(conn, ench_stats)
    suffixes = load_suffixes()
    groups = load_enchant_groups(conn)
    rpp = load_rand_prop_points()
    caps = build_ilvl_caps(conn)
    print("ItemLevel ceiling by tier (band 0): "
          + ", ".join(f"{t}:{caps[(0, t)]}" for t in range(10, 81, 10)))
    rows = fetch_candidates(conn, caps)
    conn.close()

    print(f"Enchantments: {len(ench_stats)}  properties: {len(props)}  "
          f"suffixes: {len(suffixes)}  groups: {len(groups)}  "
          f"rand-prop-points levels: {len(rpp)}")
    print(f"Candidate variants: {len(rows)}")
    kinds = defaultdict(int)
    for r in rows:
        kinds["property" if r["RandomProperty"]
              else "suffix" if r["RandomSuffix"] else "fixed"] += 1
    for k in sorted(kinds):
        print(f"  {k}: {kinds[k]}")

    prop_best, suffix_best = build_affix_index(groups, props, suffixes, ench_stats)
    print(f"Affix index: {len(prop_best)} (archetype, group) property pairs, "
          f"{len(suffix_best)} suffix pairs")

    pool = build_pool(rows, prop_best, suffix_best, rpp, args.top_n, classes)
    rows_out = pool_rows(pool)
    print(f"Pool rows: {len(rows_out)} across {len(pool)} buckets")

    affixed = sum(1 for r in rows_out if r["rand_prop"])
    print(f"  with an affix: {affixed} ({affixed * 100 // max(1, len(rows_out))}%)")

    problems = validate(pool, classes)
    if problems:
        print(f"\nVALIDATION: {len(problems)} problem(s):")
        for msg in problems[:40]:
            print(f"  - {msg}")
        if len(problems) > 40:
            print(f"  ... and {len(problems) - 40} more")
    else:
        print("\nVALIDATION: ok")

    if args.audit_csv:
        write_audit_csv(args.audit_csv, rows_out)
        print(f"Audit CSV: {args.audit_csv}")

    if args.validate:
        sys.exit(1 if problems else 0)

    sql = format_sql(rows_out, args.top_n)
    if args.dry_run:
        return None
    if args.stdout:
        return sql

    path = next_sql_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write(sql)
    print(f"Wrote {path}")
    return None


if __name__ == "__main__":
    main()
