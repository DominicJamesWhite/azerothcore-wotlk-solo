#!/usr/bin/env python3
"""
Mythic Plus Dungeon Mythification Tool

Analyzes all dungeons registered in ether_capable_dungeon and generates:
  1. mythic_plus_spell_override — per-spell damage multipliers for flat-damage
     spells that don't auto-scale with creature level
  2. mythic_plus_map_scale — per-dungeon melee damage multipliers to compensate
     for low DamageModifier values on old-world creatures

Usage:
    python tools/gen_spell_overrides.py                    # all dungeons, both tables
    python tools/gen_spell_overrides.py --map 209          # Zul'Farrak only
    python tools/gen_spell_overrides.py --sector 1         # Kalimdor only
    python tools/gen_spell_overrides.py --dry-run          # preview, no file
    python tools/gen_spell_overrides.py --stdout           # print SQL to stdout
    python tools/gen_spell_overrides.py --skip-existing    # skip maps that already have overrides
    python tools/gen_spell_overrides.py --spells-only      # only spell overrides
    python tools/gen_spell_overrides.py --map-scale-only   # only map scale
"""

import argparse
import math
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc"))
import config  # noqa: E402
from spell_dbc import load_spell_index  # noqa: E402

# ── Effect / Aura constants ──────────────────────────────────────────────────
SPELL_EFFECT_SCHOOL_DAMAGE = 2
SPELL_EFFECT_APPLY_AURA = 6
SPELL_EFFECT_HEALTH_LEECH = 9
SPELL_EFFECT_HEAL = 10
SPELL_EFFECT_WEAPON_PERCENT_DAMAGE = 31
SPELL_EFFECT_WEAPON_DAMAGE = 58
SPELL_EFFECT_NORMALIZED_WEAPON_DAMAGE = 121
SPELL_EFFECT_HEAL_PCT = 136

SPELL_AURA_PERIODIC_DAMAGE = 3
SPELL_AURA_PERIODIC_HEAL = 8
SPELL_AURA_DAMAGE_SHIELD = 15
SPELL_AURA_PERIODIC_LEECH = 53

# Effects that deal flat damage and need scaling
DIRECT_DAMAGE_EFFECTS = {SPELL_EFFECT_SCHOOL_DAMAGE, SPELL_EFFECT_HEALTH_LEECH}
# Effects that heal for flat amounts and need scaling
DIRECT_HEAL_EFFECTS = {SPELL_EFFECT_HEAL}
# Heal effects that are %-based (auto-scale, skip)
PCT_HEAL_EFFECTS = {SPELL_EFFECT_HEAL_PCT}
# Effects that use weapon damage as base (auto-scale, skip)
WEAPON_BASED_EFFECTS = {
    SPELL_EFFECT_WEAPON_PERCENT_DAMAGE, SPELL_EFFECT_WEAPON_DAMAGE,
    SPELL_EFFECT_NORMALIZED_WEAPON_DAMAGE,
}
# Auras that deal flat periodic damage
PERIODIC_DAMAGE_AURAS = {
    SPELL_AURA_PERIODIC_DAMAGE, SPELL_AURA_DAMAGE_SHIELD,
    SPELL_AURA_PERIODIC_LEECH,
}
# Auras that heal periodically for flat amounts
PERIODIC_HEAL_AURAS = {SPELL_AURA_PERIODIC_HEAL}

# ── Baseline reference values ────────────────────────────────────────────────
# Empirically derived from comparing actual spell damage values across
# dungeon tiers vs WOTLK heroic equivalents.
#
# Data points (comparing equivalent spell types):
#   ZF Shadow Bolt (lvl 44):      ~112 dmg
#   UK Shadow Bolt (lvl 72 HC):   ~3500 dmg  → ratio ~31x
#   ZF Chain Lightning (lvl 46):  ~200 dmg
#   UK Lightning Bolt (lvl 70):   ~2000 dmg  → ratio ~10x
#   RFC Lightning Bolt (lvl 15):  ~30 dmg    → ratio ~100x (with 3.75x override)
#
# Spell damage scales exponentially across WoW's level range, much steeper
# than melee base damage.  We use empirical anchor points:
#
#   Level 15 → ~80x   (Classic low)
#   Level 25 → ~45x   (Classic mid)
#   Level 35 → ~25x   (Classic mid-high)
#   Level 45 → ~15x   (Classic high / ZF tier)
#   Level 55 → ~8x    (Classic endgame)
#   Level 60 → ~5x    (Classic max / vanilla raids)
#   Level 65 → ~3x    (TBC normal)
#   Level 70 → ~2x    (TBC heroic)
#   Level 73 → ~1.5x  (WOTLK normal)
#   Level 78+ → ~1.0x (WOTLK heroic — baseline)
#
# Fitted as an exponential decay: ratio = exp(a * (80 - L))
# From anchor: level 45 → 15x → a = ln(15) / 35 ≈ 0.0774
# Validated: level 60 → exp(0.0774 * 20) ≈ 4.7x ✓
#            level 70 → exp(0.0774 * 10) ≈ 2.2x ✓
#            level 15 → exp(0.0774 * 65) ≈ 153x (cap to ~80x for sanity)

# Maximum multiplier cap — prevents absurd values for very low level dungeons
MAX_SPELL_RATIO = 80.0

# ── Map Scale (melee) baseline ───────────────────────────────────────────────
# WOTLK heroic elite DamageModifier is consistently 7.5.  Old-world creatures
# have lower values (1.7-3.5 for Classic, 3.4-7.0 for TBC).
#
# The M+ system recalculates base damage to level 80 via CreatureBaseStats,
# but the creature_template DamageModifier is still applied by the engine.
# mythic_plus_map_scale compensates for the DamageModifier gap.
#
# Raids have DamageModifiers intentionally higher than 7.5 (11-58x).
# Those need a different baseline — we use the actual average rather than
# forcing them down to 7.5.
WOTLK_HEROIC_DMG_MOD = 7.5

# Minimum map scale — don't generate entries for dungeons close to baseline
MIN_MAP_SCALE_THRESHOLD = 1.15

def level_damage_ratio(creature_level):
    """
    Compute the multiplier needed to scale a spell from creature_level
    to level-80 equivalent damage.

    Returns a float multiplier (e.g., 15.0 means the spell needs to do
    15x its current damage to be level-80 appropriate).
    """
    if creature_level >= 78:
        return 1.0

    # Exponential decay fitted to empirical spell damage data
    # ratio = exp(0.0774 * (80 - level))
    gap = 80 - max(creature_level, 1)
    ratio = math.exp(0.0774 * gap)
    return min(ratio, MAX_SPELL_RATIO)


def get_db_connection():
    import mysql.connector
    return mysql.connector.connect(
        host=config.MYSQL_HOST,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASS,
        database=config.MYSQL_DB,
    )


def get_dungeon_list(conn, map_filter=None, sector_filter=None):
    """Get list of dungeons from ether_capable_dungeon."""
    cursor = conn.cursor(dictionary=True)
    query = "SELECT map, display_name, sector_id FROM ether_capable_dungeon"
    conditions = []
    params = []
    if map_filter is not None:
        conditions.append("map = %s")
        params.append(map_filter)
    if sector_filter is not None:
        conditions.append("sector_id = %s")
        params.append(sector_filter)
    if conditions:
        query += " WHERE " + " AND ".join(conditions)
    query += " ORDER BY sector_id, sort_order"
    cursor.execute(query, params)
    return cursor.fetchall()


def get_existing_overrides(conn):
    """Get set of (spellid, map) that already have overrides."""
    cursor = conn.cursor()
    cursor.execute("SELECT spellid, map FROM mythic_plus_spell_override")
    return {(row[0], row[1]) for row in cursor.fetchall()}


def get_existing_override_maps(conn):
    """Get set of maps that already have any overrides."""
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT map FROM mythic_plus_spell_override")
    return {row[0] for row in cursor.fetchall()}


def get_creatures_for_map(conn, map_id):
    """
    Get all creatures spawned in a map with their template data.
    Returns list of dicts with entry, name, minlevel, maxlevel, rank, etc.
    """
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT ct.entry, ct.name, ct.minlevel, ct.maxlevel, ct.rank,
               ct.unit_class, ct.DamageModifier
        FROM creature_template ct
        INNER JOIN creature c ON ct.entry = c.id1
        WHERE c.map = %s
        GROUP BY ct.entry
        ORDER BY ct.rank DESC, ct.maxlevel DESC
    """, (map_id,))
    return cursor.fetchall()


def get_creature_spells(conn, map_id):
    """
    Get all spells used by creatures on a map, from three sources:
    1. SmartAI scripts (smart_scripts table)
    2. creature_template_spell table
    3. C++ boss/npc scripts (parsed from source files)

    Returns dict: {creature_entry: set(spell_ids)}
    """
    result = {}
    cursor = conn.cursor(dictionary=True)

    # Source 1: SmartAI spells (action_type 11 = SMART_ACTION_CAST)
    cursor.execute("""
        SELECT ct.entry, s.action_param1 AS spell_id
        FROM creature_template ct
        INNER JOIN creature c ON ct.entry = c.id1
        INNER JOIN smart_scripts s ON s.entryorguid = ct.entry AND s.source_type = 0
        WHERE c.map = %s AND s.action_type = 11
        GROUP BY ct.entry, s.action_param1
    """, (map_id,))
    for row in cursor.fetchall():
        result.setdefault(row["entry"], set()).add(row["spell_id"])

    # Source 2: creature_template_spell
    cursor.execute("""
        SELECT ct.entry, cts.spell AS spell_id
        FROM creature_template ct
        INNER JOIN creature c ON ct.entry = c.id1
        INNER JOIN creature_template_spell cts ON cts.CreatureID = ct.entry
        WHERE c.map = %s
        GROUP BY ct.entry, cts.spell
    """, (map_id,))
    for row in cursor.fetchall():
        result.setdefault(row["entry"], set()).add(row["spell_id"])

    # Source 3: C++ boss/npc scripts
    cpp_spells = get_cpp_creature_spells(conn, map_id)
    for entry, spells in cpp_spells.items():
        result.setdefault(entry, set()).update(spells)

    return result


# ── C++ Boss Script Spell Extraction ─────────────────────────────────────────

# Cache: ScriptName -> set of spell IDs extracted from C++ source
_cpp_spell_cache = {}
# Cache: ScriptName -> .cpp file path
_script_file_cache = None

# Regex to match SPELL_FOO = 12345 in enums
_SPELL_ENUM_RE = re.compile(r'SPELL_[A-Z0-9_]+\s*=\s*(\d+)')


def _build_script_file_index():
    """
    Build a map of ScriptName -> .cpp file path by scanning all .cpp files
    under src/server/scripts/.

    Script registration uses two patterns:
    1. Old style: new CreatureScript("boss_name") — quoted string
    2. New style: RegisterCreatureAI(boss_name) or Register*CreatureAI(boss_name)
       The macro stringifies the class name: #ai_name -> "boss_name"

    Both produce a ScriptName matching the class/string name.
    """
    global _script_file_cache
    if _script_file_cache is not None:
        return _script_file_cache

    _script_file_cache = {}
    scripts_dir = os.path.join(REPO_ROOT, "src", "server", "scripts")

    if not os.path.isdir(scripts_dir):
        return _script_file_cache

    # Patterns that register creature scripts
    patterns = [
        # Old style: CreatureScript("boss_foo") or ("npc_foo")
        re.compile(r'"((?:boss|npc)_[a-z0-9_]+)"'),
        # New style: Register*CreatureAI(boss_foo) — macro stringifies class name
        re.compile(r'Register\w*CreatureAI\(\s*((?:boss|npc)_[a-z0-9_]+)\s*\)'),
    ]

    for root, dirs, files in os.walk(scripts_dir):
        for fname in files:
            if not fname.endswith(".cpp"):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except OSError:
                continue

            for pattern in patterns:
                for m in pattern.finditer(content):
                    script_name = m.group(1)
                    _script_file_cache[script_name] = fpath

    return _script_file_cache


def _extract_spells_from_cpp(file_path):
    """
    Extract all SPELL_* = <id> values from a C++ source file.
    Returns set of spell IDs (ints).
    """
    if file_path in _cpp_spell_cache:
        return _cpp_spell_cache[file_path]

    spells = set()
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except OSError:
        _cpp_spell_cache[file_path] = spells
        return spells

    for m in _SPELL_ENUM_RE.finditer(content):
        spell_id = int(m.group(1))
        if spell_id > 0:
            spells.add(spell_id)

    _cpp_spell_cache[file_path] = spells
    return spells


def get_cpp_creature_spells(conn, map_id):
    """
    Find spells used by C++ scripted creatures on a map.
    Returns dict: {creature_entry: set(spell_ids)}

    Works by:
    1. Querying creature_template for ScriptName entries on this map
    2. Finding the corresponding .cpp file
    3. Extracting SPELL_* enum values from that file
    """
    result = {}
    cursor = conn.cursor(dictionary=True)

    cursor.execute("""
        SELECT ct.entry, ct.name, ct.ScriptName
        FROM creature_template ct
        INNER JOIN creature c ON ct.entry = c.id1
        WHERE c.map = %s AND ct.ScriptName != ''
        GROUP BY ct.entry
    """, (map_id,))

    script_index = _build_script_file_index()
    rows = cursor.fetchall()

    for row in rows:
        script_name = row["ScriptName"]
        cpp_file = script_index.get(script_name)
        if not cpp_file:
            continue

        spells = _extract_spells_from_cpp(cpp_file)
        if spells:
            result[row["entry"]] = spells

    return result


def get_existing_map_scales(conn):
    """Get set of (map, mapdifficulty) that already have map scale entries."""
    cursor = conn.cursor()
    cursor.execute("SELECT map, mapdifficulty FROM mythic_plus_map_scale")
    return {(row[0], row[1]) for row in cursor.fetchall()}


def get_damage_modifiers_for_map(conn, map_id):
    """
    Get average DamageModifier for trash elites and bosses on a map.
    Returns (trash_elite_avg, boss_avg, trash_count, boss_count).

    The M+ code splits creatures into "boss" (IsDungeonBoss or final boss)
    and "trash" (everything else).  The map_scale trash multiplier applies to
    all non-boss creatures, including both elite and non-elite.

    We use the ELITE average (rank 1) for the trash scale calculation,
    because:
      - Non-elite adds (rank 0) intentionally have DamageModifier=1.0
      - Scaling their damage 7x would make weak fodder mobs hit like elites
      - The map_scale is meant to compensate for elite trash being undertuned

    For boss scale, we use dungeon boss entries (flagged via creature_template
    flags or creature_template_addon).  Since we can't easily determine
    IsDungeonBoss from SQL alone, we use rank 3 (world boss) + rank 1 with
    high DamageModifier as a proxy, but fall back to the overall elite average.
    """
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT
            AVG(CASE WHEN ct.rank = 1 THEN ct.DamageModifier END) AS elite_dmgmod,
            AVG(CASE WHEN ct.rank = 0 THEN ct.DamageModifier END) AS normal_dmgmod,
            AVG(CASE WHEN ct.rank >= 2 THEN ct.DamageModifier END) AS rareboss_dmgmod,
            SUM(CASE WHEN ct.rank = 1 THEN 1 ELSE 0 END) AS elite_count,
            SUM(CASE WHEN ct.rank = 0 THEN 1 ELSE 0 END) AS normal_count,
            SUM(CASE WHEN ct.rank >= 2 THEN 1 ELSE 0 END) AS rareboss_count
        FROM creature_template ct
        INNER JOIN creature c ON ct.entry = c.id1
        WHERE c.map = %s AND ct.maxlevel >= 5
        GROUP BY c.map
    """, (map_id,))
    row = cursor.fetchone()
    if not row:
        return None, None, 0, 0

    elite_avg = float(row["elite_dmgmod"]) if row["elite_dmgmod"] else None
    normal_avg = float(row["normal_dmgmod"]) if row["normal_dmgmod"] else None
    rareboss_avg = float(row["rareboss_dmgmod"]) if row["rareboss_dmgmod"] else None

    # Trash scale: use elite average (the threatening trash mobs).
    # If no elites, fall back to normal mobs.
    trash_dmgmod = elite_avg if elite_avg else normal_avg

    # Boss scale: use elite average as well (since most "bosses" in Classic
    # dungeons are rank 1 elite, not rank 3).  The elite average covers both
    # boss and elite trash.  For dungeons where bosses have distinctly higher
    # DamageModifier, this still works because we want all elites including
    # bosses to feel properly scaled.
    boss_dmgmod = elite_avg if elite_avg else rareboss_avg

    elite_count = int(row["elite_count"] or 0)
    boss_count = int(row["rareboss_count"] or 0)

    return (trash_dmgmod, boss_dmgmod, elite_count, boss_count)


def generate_map_scales(dungeons, conn, existing_scales, skip_existing=False):
    """
    For each dungeon, compute melee damage scale factors by comparing
    DamageModifier to the WOTLK heroic baseline (7.5).

    Returns list of dicts ready for SQL generation.
    """
    scales = []

    for dungeon in dungeons:
        map_id = dungeon["map"]
        dungeon_name = dungeon["display_name"]
        sector = dungeon["sector_id"]

        # Check if this map already has a scale entry (difficulty 0)
        if skip_existing and (map_id, 0) in existing_scales:
            print(f"  [map_scale] Skipping {dungeon_name} (map {map_id}) — already has entry")
            continue

        trash_avg, boss_avg, trash_count, boss_count = \
            get_damage_modifiers_for_map(conn, map_id)

        if boss_avg is None and trash_avg is None:
            continue

        # For raids (sector 4), the DamageModifier is intentionally high.
        # Don't scale them down — raids should feel punishing.
        # Only generate map_scale if the modifier is BELOW the heroic baseline.
        # (Some raid trash has low DamageModifier even though bosses are high.)
        if sector == 4:
            # Raids: only scale if boss DamageModifier is below baseline
            if boss_avg and boss_avg >= WOTLK_HEROIC_DMG_MOD:
                print(f"  [map_scale] {dungeon_name} (map {map_id}): "
                      f"raid with boss DmgMod {boss_avg:.1f} >= {WOTLK_HEROIC_DMG_MOD} — skipping")
                continue

        # Compute scale factors
        # Use the boss DamageModifier as reference for boss scale,
        # and trash DamageModifier for trash scale.
        # If a category has no creatures, use the other category's value.
        boss_dmgmod = boss_avg if boss_avg else trash_avg
        trash_dmgmod = trash_avg if trash_avg else boss_avg

        trash_scale = round(WOTLK_HEROIC_DMG_MOD / trash_dmgmod, 1)
        boss_scale = round(WOTLK_HEROIC_DMG_MOD / boss_dmgmod, 1)

        # Skip if both scales are close to 1.0
        if trash_scale < MIN_MAP_SCALE_THRESHOLD and boss_scale < MIN_MAP_SCALE_THRESHOLD:
            print(f"  [map_scale] {dungeon_name} (map {map_id}): "
                  f"DmgMod trash={trash_dmgmod:.1f} boss={boss_dmgmod:.1f} — "
                  f"already near baseline, skipping")
            continue

        # Clamp to minimum 1.0 (don't reduce damage)
        trash_scale = max(1.0, trash_scale)
        boss_scale = max(1.0, boss_scale)

        scales.append({
            "map": map_id,
            "mapdifficulty": 0,
            "dmg_scale_trash": trash_scale,
            "dmg_scale_boss": boss_scale,
            "dungeon_name": dungeon_name,
            "trash_dmgmod": trash_dmgmod,
            "boss_dmgmod": boss_dmgmod,
            "sector": sector,
        })

        print(f"  [map_scale] {dungeon_name} (map {map_id}): "
              f"DmgMod trash={trash_dmgmod:.1f} boss={boss_dmgmod:.1f} -> "
              f"scale trash={trash_scale:.1f}x boss={boss_scale:.1f}x")

    return scales


def format_map_scale_sql(scales):
    """Format map scale entries as SQL INSERT statements."""
    if not scales:
        return ""

    lines = []
    lines.append("")
    lines.append("-- ==========================================================================")
    lines.append("-- Mythic Plus Map Scale — Auto-generated by gen_spell_overrides.py")
    lines.append("-- ==========================================================================")
    lines.append("--")
    lines.append("-- Compensates for low DamageModifier on old-world creatures.")
    lines.append("-- WOTLK heroic baseline DamageModifier = 7.5.")
    lines.append("-- Scale = 7.5 / avg_DamageModifier_for_dungeon.")
    lines.append("--")
    lines.append("")

    sector_names = {0: "Eastern Kingdoms", 1: "Kalimdor", 2: "Outland",
                    3: "Northrend", 4: "Raids"}
    current_sector = None

    for s in scales:
        if s["sector"] != current_sector:
            current_sector = s["sector"]
            lines.append(f"\n-- {sector_names.get(current_sector, 'Unknown')} --")

        lines.append(
            f"INSERT INTO `mythic_plus_map_scale` "
            f"(`map`, `mapdifficulty`, `dmg_scale_trash`, `dmg_scale_boss`) VALUES "
            f"({s['map']},{s['mapdifficulty']},{s['dmg_scale_trash']},{s['dmg_scale_boss']}); "
            f"-- {s['dungeon_name']} (DmgMod: trash={s['trash_dmgmod']:.1f}, boss={s['boss_dmgmod']:.1f})"
        )

    lines.append("")
    return "\n".join(lines)


def print_map_scale_summary(scales):
    """Print a summary table of map scale entries."""
    if not scales:
        return

    print(f"\n{'='*80}")
    print(f"MAP SCALE SUMMARY: {len(scales)} dungeon entries")
    print(f"{'='*80}")
    print(f"  {'Map':<6} {'Dungeon':<30} {'DmgMod(T)':<10} {'DmgMod(B)':<10} "
          f"{'Scale(T)':<10} {'Scale(B)':<10}")
    print(f"  {'---':<6} {'-------':<30} {'--------':<10} {'--------':<10} "
          f"{'--------':<10} {'--------':<10}")
    for s in scales:
        print(f"  {s['map']:<6} {s['dungeon_name']:<30} "
              f"{s['trash_dmgmod']:<10.1f} {s['boss_dmgmod']:<10.1f} "
              f"{s['dmg_scale_trash']:<10.1f} {s['dmg_scale_boss']:<10.1f}")


def analyze_spell(spell_row):
    """
    Analyze a spell from the DBC and determine if it has flat damage or
    heal effects that need scaling.

    Returns list of dicts:
        [{"slot": 1|2|3, "type": "direct"|"dot"|"heal", "avg_damage": float}, ...]
    Empty list means no scalable effects — skip this spell.
    """
    if spell_row is None:
        return []

    effects = []

    for slot in (1, 2, 3):
        effect = spell_row.get(f"Effect{slot}", 0)
        base = spell_row.get(f"EffectBasePoints{slot}", 0)
        dice = spell_row.get(f"EffectDieSides{slot}", 0)
        aura = spell_row.get(f"EffectApplyAuraName{slot}", 0)

        # Skip weapon-based effects (they auto-scale)
        if effect in WEAPON_BASED_EFFECTS:
            return []  # If ANY effect is weapon-based, skip entirely

        # Skip %-based heals (they auto-scale with HP pool)
        if effect in PCT_HEAL_EFFECTS:
            continue

        avg = base + max(1, dice) / 2.0 if dice > 0 else base + 1

        # Direct damage (SCHOOL_DAMAGE, HEALTH_LEECH)
        if effect in DIRECT_DAMAGE_EFFECTS:
            if avg > 0:
                effects.append({
                    "slot": slot, "type": "direct", "avg_damage": avg
                })

        # Direct heal (HEAL)
        if effect in DIRECT_HEAL_EFFECTS:
            if avg > 0:
                effects.append({
                    "slot": slot, "type": "heal", "avg_damage": avg
                })

        # Periodic damage via APPLY_AURA
        if effect == SPELL_EFFECT_APPLY_AURA and aura in PERIODIC_DAMAGE_AURAS:
            if avg > 0:
                effects.append({
                    "slot": slot, "type": "dot", "avg_damage": avg
                })

        # Periodic heal via APPLY_AURA
        if effect == SPELL_EFFECT_APPLY_AURA and aura in PERIODIC_HEAL_AURAS:
            if avg > 0:
                effects.append({
                    "slot": slot, "type": "heal", "avg_damage": avg
                })

    return effects


def generate_overrides(dungeons, conn, dbc_index, existing_overrides,
                       skip_existing_maps=False, existing_maps=None):
    """
    For each dungeon, find all creature spells that need scaling and
    compute override multipliers.

    Returns list of dicts ready for SQL generation.
    """
    overrides = []

    for dungeon in dungeons:
        map_id = dungeon["map"]
        dungeon_name = dungeon["display_name"]

        if skip_existing_maps and existing_maps and map_id in existing_maps:
            print(f"  Skipping {dungeon_name} (map {map_id}) — already has overrides")
            continue

        creatures = get_creatures_for_map(conn, map_id)
        creature_spells = get_creature_spells(conn, map_id)

        if not creatures:
            continue

        # Build creature lookup
        creature_map = {c["entry"]: c for c in creatures}

        # Deduplicate by (spellid, map) — same spell used by multiple creatures.
        # Keep the highest-level creature's ratio (most conservative multiplier)
        # and collect all creature names for the comment.
        spell_candidates = {}  # (spell_id) -> {data}

        for entry, spell_ids in sorted(creature_spells.items()):
            creature = creature_map.get(entry)
            if creature is None:
                continue

            # Skip non-combat creatures (level < 5)
            if creature["maxlevel"] < 5:
                continue

            creature_level = creature["maxlevel"]
            ratio = level_damage_ratio(creature_level)

            # Skip if ratio is ~1.0 (already at level)
            if ratio < 1.05:
                continue

            for spell_id in sorted(spell_ids):
                # Skip if already has an override in the DB
                if (spell_id, map_id) in existing_overrides:
                    continue

                spell_row = dbc_index.get(spell_id)
                damage_info = analyze_spell(spell_row)

                if not damage_info:
                    continue

                spell_name = spell_row.get("SpellName0", "Unknown") if spell_row else "Unknown"

                has_direct = any(d["type"] == "direct" for d in damage_info)
                has_dot = any(d["type"] == "dot" for d in damage_info)
                has_heal = any(d["type"] == "heal" for d in damage_info)

                # Round to 1 decimal
                # modpct is used for both direct damage AND heals
                # (the C++ heal hook reads modPct)
                modpct = round(ratio, 1) if (has_direct or has_heal) else -1
                dotmodpct = round(ratio, 1) if has_dot else -1

                if spell_id in spell_candidates:
                    existing = spell_candidates[spell_id]
                    # Use the lowest ratio (highest-level creature = most conservative)
                    if ratio < existing["ratio"]:
                        existing["ratio"] = ratio
                        existing["modpct"] = modpct
                        existing["dotmodpct"] = dotmodpct
                        existing["creature_level"] = creature_level
                    # Append creature name
                    if creature["name"] not in existing["creatures"]:
                        existing["creatures"].append(creature["name"])
                else:
                    spell_candidates[spell_id] = {
                        "spellid": spell_id,
                        "map": map_id,
                        "modpct": modpct,
                        "dotmodpct": dotmodpct,
                        "spell_name": spell_name,
                        "creatures": [creature["name"]],
                        "creature_level": creature_level,
                        "ratio": ratio,
                        "dungeon_name": dungeon_name,
                    }

        dungeon_overrides = []
        for spell_id in sorted(spell_candidates):
            c = spell_candidates[spell_id]
            # Truncate creature list for comment if too many
            cnames = c["creatures"]
            if len(cnames) > 3:
                comment = f"{', '.join(cnames[:3])} +{len(cnames)-3} more - {c['spell_name']}"
            else:
                comment = f"{', '.join(cnames)} - {c['spell_name']}"

            dungeon_overrides.append({
                "spellid": c["spellid"],
                "map": c["map"],
                "modpct": c["modpct"],
                "dotmodpct": c["dotmodpct"],
                "comment": comment,
                "creature_level": c["creature_level"],
                "ratio": c["ratio"],
                "dungeon_name": c["dungeon_name"],
            })

        if dungeon_overrides:
            overrides.extend(dungeon_overrides)
            print(f"  {dungeon_name} (map {map_id}): {len(dungeon_overrides)} spell overrides, "
                  f"level range {min(c['maxlevel'] for c in creatures if c['maxlevel'] >= 5)}-"
                  f"{max(c['maxlevel'] for c in creatures)}, "
                  f"ratio ~{dungeon_overrides[0]['ratio']:.1f}x")
        else:
            creature_levels = [c['maxlevel'] for c in creatures if c['maxlevel'] >= 5]
            if creature_levels and max(creature_levels) < 78:
                print(f"  {dungeon_name} (map {map_id}): no spells need overrides "
                      f"(no flat damage spells found)")
            elif creature_levels:
                print(f"  {dungeon_name} (map {map_id}): creatures already level 78+ — skipping")

    return overrides


def format_sql(overrides, include_drop=False):
    """Format overrides as SQL INSERT statements."""
    if not overrides:
        return "-- No overrides generated.\n"

    lines = []
    lines.append("-- ==========================================================================")
    lines.append("-- Mythic Plus Spell Overrides — Auto-generated by gen_spell_overrides.py")
    lines.append("-- ==========================================================================")
    lines.append("--")
    lines.append("-- Scales flat-damage creature spells to level-80 equivalents.")
    lines.append("-- Weapon%-based spells are excluded (they auto-scale with creature melee).")
    lines.append("-- Multipliers are computed from a level-based power curve ratio.")
    lines.append("--")
    lines.append("")

    if include_drop:
        lines.append("DROP TABLE IF EXISTS `mythic_plus_spell_override`;")
        lines.append("CREATE TABLE `mythic_plus_spell_override`(")
        lines.append("    `spellid` int unsigned NOT NULL,")
        lines.append("    `map` int unsigned NOT NULL,")
        lines.append("    `modpct` float default '-1',")
        lines.append("    `dotmodpct` float default '-1',")
        lines.append("    `comment` varchar(255),")
        lines.append("    PRIMARY KEY (`spellid`, `map`)")
        lines.append(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;")
        lines.append("")

    current_dungeon = None
    for o in overrides:
        if o["dungeon_name"] != current_dungeon:
            current_dungeon = o["dungeon_name"]
            lines.append("")
            lines.append(f"-- {current_dungeon} (map {o['map']}) — "
                         f"level {o['creature_level']} creatures, "
                         f"~{o['ratio']:.1f}x scaling ratio")

        modpct_str = f"{o['modpct']}" if o['modpct'] >= 0 else "-1"
        dotmodpct_str = f"{o['dotmodpct']}" if o['dotmodpct'] >= 0 else "-1"
        comment = o['comment'].replace("'", "\\'")

        lines.append(
            f"INSERT INTO `mythic_plus_spell_override` "
            f"(`spellid`, `map`, `modpct`, `dotmodpct`, `comment`) VALUES "
            f"({o['spellid']},{o['map']},{modpct_str},{dotmodpct_str},'{comment}');"
        )

    lines.append("")
    return "\n".join(lines)


def print_summary_table(overrides):
    """Print a summary table of generated overrides grouped by dungeon."""
    if not overrides:
        print("\nNo overrides generated.")
        return

    print(f"\n{'='*80}")
    print(f"SUMMARY: {len(overrides)} spell overrides across "
          f"{len(set(o['map'] for o in overrides))} dungeons")
    print(f"{'='*80}")

    current_dungeon = None
    for o in overrides:
        if o["dungeon_name"] != current_dungeon:
            current_dungeon = o["dungeon_name"]
            print(f"\n  {current_dungeon} (map {o['map']}, "
                  f"~{o['ratio']:.1f}x ratio):")
            print(f"    {'Spell ID':<10} {'modpct':<8} {'dotpct':<8} {'Creature - Spell'}")
            print(f"    {'--------':<10} {'------':<8} {'------':<8} {'----------------'}")

        mod = f"{o['modpct']:.1f}" if o['modpct'] >= 0 else "-"
        dot = f"{o['dotmodpct']:.1f}" if o['dotmodpct'] >= 0 else "-"
        print(f"    {o['spellid']:<10} {mod:<8} {dot:<8} {o['comment']}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate mythic_plus_spell_override and mythic_plus_map_scale SQL"
    )
    parser.add_argument("--map", type=int, help="Only process this map ID")
    parser.add_argument("--sector", type=int, help="Only process this sector (0-4)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview without writing files")
    parser.add_argument("--stdout", action="store_true",
                        help="Print SQL to stdout instead of writing a file")
    parser.add_argument("--skip-existing", action="store_true",
                        help="Skip maps that already have overrides in the DB")
    parser.add_argument("--include-drop", action="store_true",
                        help="Include DROP/CREATE TABLE in output (full rebuild)")
    parser.add_argument("--spells-only", action="store_true",
                        help="Only generate spell overrides (no map scale)")
    parser.add_argument("--map-scale-only", action="store_true",
                        help="Only generate map scale (no spell overrides)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output file path (default: auto-named in mod-mythic-plus SQL dir)")

    args = parser.parse_args()

    do_spells = not args.map_scale_only
    do_map_scale = not args.spells_only

    print("=" * 60)
    print("  Mythic Plus Dungeon Mythification Tool")
    print("=" * 60)

    mode_parts = []
    if do_spells:
        mode_parts.append("spell overrides")
    if do_map_scale:
        mode_parts.append("map scale")
    print(f"  Mode: {' + '.join(mode_parts)}")

    # Load Spell.dbc (only needed for spell overrides)
    dbc_index = None
    if do_spells:
        print("\n  Loading Spell.dbc...")
        dbc_index = load_spell_index(config.BASE_DBC_PATH)
        print(f"  Loaded {len(dbc_index)} spells")

    # Connect to DB
    print("  Connecting to database...")
    conn = get_db_connection()

    # Get dungeon list
    dungeons = get_dungeon_list(conn, map_filter=args.map, sector_filter=args.sector)
    print(f"  Found {len(dungeons)} dungeons to process\n")

    # ── Spell overrides ──────────────────────────────────────────────────
    overrides = []
    if do_spells:
        # When --include-drop is set, we're rebuilding the table from scratch
        # so ignore existing DB entries
        if args.include_drop:
            existing_overrides = set()
            existing_maps = set()
            print("  Full rebuild mode — ignoring existing DB overrides\n")
        else:
            existing_overrides = get_existing_overrides(conn)
            existing_maps = get_existing_override_maps(conn)
            if existing_overrides:
                print(f"  {len(existing_overrides)} existing spell overrides in "
                      f"{len(existing_maps)} maps will be preserved\n")

        print("  Analyzing spell overrides...")
        overrides = generate_overrides(
            dungeons, conn, dbc_index, existing_overrides,
            skip_existing_maps=args.skip_existing,
            existing_maps=existing_maps,
        )
        print_summary_table(overrides)

    # ── Map scale ────────────────────────────────────────────────────────
    scales = []
    if do_map_scale:
        existing_scales = get_existing_map_scales(conn)
        if existing_scales:
            print(f"\n  {len(existing_scales)} existing map scale entries will be preserved\n")

        print("  Analyzing map scale...")
        scales = generate_map_scales(
            dungeons, conn, existing_scales,
            skip_existing=args.skip_existing,
        )
        print_map_scale_summary(scales)

    conn.close()

    if not overrides and not scales:
        print("\nNothing to generate.")
        return

    # ── Generate SQL ─────────────────────────────────────────────────────
    sql_parts = []
    if overrides:
        sql_parts.append(format_sql(overrides, include_drop=args.include_drop))
    if scales:
        sql_parts.append(format_map_scale_sql(scales))
    sql = "\n".join(sql_parts)

    if args.stdout or args.dry_run:
        print(f"\n{'='*80}")
        print("SQL OUTPUT:")
        print(f"{'='*80}")
        print(sql)
        if args.dry_run:
            print("(dry run — no file written)")
        return

    # Write SQL file(s)
    output_dir = os.path.join(
        REPO_ROOT, "modules", "mod-mythic-plus", "data", "sql", "db-world"
    )

    if args.output:
        # Single output file
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(sql)
        print(f"\n  Written to: {args.output}")
    else:
        # Separate files per table
        if overrides:
            path = os.path.join(output_dir, "b_mythic_plus_spell_override.sql")
            with open(path, "w", encoding="utf-8") as f:
                f.write(format_sql(overrides, include_drop=args.include_drop))
            print(f"\n  Spell overrides: {path} ({len(overrides)} entries)")

        if scales:
            path = os.path.join(output_dir, "b_mythic_plus_map_scale.sql")
            with open(path, "w", encoding="utf-8") as f:
                f.write(format_map_scale_sql(scales))
            print(f"  Map scale: {path} ({len(scales)} entries)")


if __name__ == "__main__":
    main()
