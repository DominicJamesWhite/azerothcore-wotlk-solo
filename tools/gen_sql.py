#!/usr/bin/env python3
"""
Alonecraft SQL Generator

Generates idempotent SQL files for alonecraft_spell_dbc, spell_proc, and
spell_script_names from high-level change descriptions.  Specify only the
columns you want to change; the tool fetches the full base spell from the
binary Spell.dbc, layers any existing database overrides, applies your
changes, and outputs a complete DELETE+INSERT file.

Usage:
    python tools/gen_sql.py lookup --spell-id 133
    python tools/gen_sql.py lookup --spell-id 133 --all
    python tools/gen_sql.py lookup --name "Fireball"
    python tools/gen_sql.py talent --name "Subversion"
    python tools/gen_sql.py dbc --spell-id 33186 --set EffectBasePoints1=50
    python tools/gen_sql.py dbc --spell-ids 48997,49490,49491 --set EffectBasePoints1=50
    python tools/gen_sql.py dbc --input changes.csv
    python tools/gen_sql.py proc --spell-id 200100 --set ProcFlags=65536 --set Chance=100
    python tools/gen_sql.py script --spell-id "200100,-5176" --script-name spell_example
    python tools/gen_sql.py classmask --family 15 --spells 55078,55095
    python tools/gen_sql.py enum --aura MOD_PARRY
    python tools/gen_sql.py enum --effect APPLY_AURA
    python tools/gen_sql.py talent-link --class priest --link "05032031-235050032302152530000331351"

Options:
    --dry-run         Show what would be generated without writing files
    --stdout          Print SQL to stdout instead of writing a file
    --comment         Add a description to the SQL file header
    --append-to       Append SQL to an existing file instead of creating a new one
    --group-comment   Section comment header when appending to a grouped file
"""

import argparse
import csv
import datetime
import difflib
import glob
import os
import re
import struct
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_SQL = os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "data", "sql", "db-world")

# Add the DBC module to path so we can import config and spell_dbc
sys.path.insert(0, os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc"))
import config  # noqa: E402
from spell_dbc import SPELL_COLUMNS, FLOAT_COLUMNS, TEXT_COLUMNS, load_spell_index  # noqa: E402
from build_dbc import (  # noqa: E402
    TALENT_COLUMNS, TALENT_FIELD_COUNT, TALENT_RECORD_SIZE, read_int_dbc,
)

# ---------------------------------------------------------------------------
# DBC source resolution (--source base|live)
# ---------------------------------------------------------------------------

LIVE_DBC_DIR = r"C:\Build\bin\RelWithDebInfo\Data\dbc"


def resolve_dbc_paths(source):
    """Return (spell_dbc_path, talent_dbc_path) for the given source.

    'base' = safe backup DBCs (default, never edited by build pipeline)
    'live' = built DBCs with all alonecraft_spell_dbc overrides baked in
    """
    if source == "live":
        spell_path = os.path.join(LIVE_DBC_DIR, "Spell.dbc")
        talent_path = os.path.join(LIVE_DBC_DIR, "Talent.dbc")
        if not os.path.exists(spell_path):
            print(f"  ERROR: Live Spell.dbc not found at {spell_path}")
            print(f"  Have you built the server? Try --source base instead.")
            sys.exit(1)
        if not os.path.exists(talent_path):
            print(f"  ERROR: Live Talent.dbc not found at {talent_path}")
            sys.exit(1)
        return spell_path, talent_path
    else:
        return config.BASE_DBC_PATH, getattr(config, "BASE_TALENT_DBC_PATH", None)

SPELL_PROC_COLUMNS = (
    "SpellId", "SchoolMask", "SpellFamilyName",
    "SpellFamilyMask0", "SpellFamilyMask1", "SpellFamilyMask2",
    "ProcFlags", "SpellTypeMask", "SpellPhaseMask", "HitMask",
    "AttributesMask", "DisableEffectsMask", "ProcsPerMinute",
    "Chance", "Cooldown", "Charges",
)

# Enum columns that can accept symbolic names
AURA_COLUMNS = {"EffectApplyAuraName1", "EffectApplyAuraName2", "EffectApplyAuraName3"}
EFFECT_COLUMNS = {"Effect1", "Effect2", "Effect3"}


# ---------------------------------------------------------------------------
# Enum parsing (lazy-loaded from C++ headers)
# ---------------------------------------------------------------------------

_AURA_ENUM = None       # name -> value
_AURA_REVERSE = None    # value -> name
_EFFECT_ENUM = None
_EFFECT_REVERSE = None


def _parse_cpp_enum(file_path, prefix):
    """Parse SPELL_AURA_* or SPELL_EFFECT_* entries from a C++ header."""
    name_to_val = {}
    val_to_name = {}
    pattern = re.compile(r'^\s*(' + re.escape(prefix) + r'\w+)\s*=\s*(\d+)')
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                m = pattern.match(line)
                if m:
                    name, val = m.group(1), int(m.group(2))
                    name_to_val[name] = val
                    val_to_name[val] = name
    except FileNotFoundError:
        print(f"  Warning: Could not find enum header: {file_path}")
    return name_to_val, val_to_name


def get_aura_enum():
    global _AURA_ENUM, _AURA_REVERSE
    if _AURA_ENUM is None:
        path = os.path.join(REPO_ROOT, "src", "server", "game", "Spells", "Auras", "SpellAuraDefines.h")
        _AURA_ENUM, _AURA_REVERSE = _parse_cpp_enum(path, "SPELL_AURA_")
    return _AURA_ENUM, _AURA_REVERSE


def get_effect_enum():
    global _EFFECT_ENUM, _EFFECT_REVERSE
    if _EFFECT_ENUM is None:
        path = os.path.join(REPO_ROOT, "src", "server", "shared", "SharedDefines.h")
        _EFFECT_ENUM, _EFFECT_REVERSE = _parse_cpp_enum(path, "SPELL_EFFECT_")
    return _EFFECT_ENUM, _EFFECT_REVERSE


def resolve_enum_value(col_name, value_str):
    """If value_str is a symbolic enum name, resolve it to an integer string."""
    if not value_str or value_str.lstrip("-").isdigit():
        return value_str

    if col_name in AURA_COLUMNS and value_str.startswith("SPELL_AURA_"):
        name_to_val, _ = get_aura_enum()
        if value_str in name_to_val:
            return str(name_to_val[value_str])
        matches = difflib.get_close_matches(value_str, name_to_val.keys(), n=3, cutoff=0.6)
        hint = f" Did you mean: {', '.join(matches)}?" if matches else ""
        print(f"  Warning: Unknown aura enum '{value_str}'.{hint}")
        return value_str

    if col_name in EFFECT_COLUMNS and value_str.startswith("SPELL_EFFECT_"):
        name_to_val, _ = get_effect_enum()
        if value_str in name_to_val:
            return str(name_to_val[value_str])
        matches = difflib.get_close_matches(value_str, name_to_val.keys(), n=3, cutoff=0.6)
        hint = f" Did you mean: {', '.join(matches)}?" if matches else ""
        print(f"  Warning: Unknown effect enum '{value_str}'.{hint}")
        return value_str

    return value_str


def _enum_annotation(col_name, value):
    """Return a parenthesized enum name for display, or empty string."""
    try:
        int_val = int(float(value))
    except (ValueError, TypeError):
        return ""
    if col_name in AURA_COLUMNS:
        _, reverse = get_aura_enum()
        name = reverse.get(int_val)
        if name:
            return f"  ({name})"
    if col_name in EFFECT_COLUMNS:
        _, reverse = get_effect_enum()
        name = reverse.get(int_val)
        if name:
            return f"  ({name})"
    return ""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def get_next_sql_sequence(sql_dir):
    """Find the next YYYY_MM_DD_XX.sql sequence number for today."""
    today = datetime.date.today().strftime("%Y_%m_%d")
    existing = glob.glob(os.path.join(sql_dir, f"{today}_*.sql"))
    max_seq = -1
    for f in existing:
        basename = os.path.basename(f)
        match = re.match(r"\d{4}_\d{2}_\d{2}_(\d+)\.sql", basename)
        if match:
            max_seq = max(max_seq, int(match.group(1)))
    return today, max_seq + 1


def get_db_connection():
    """Connect to MySQL using the DBC config."""
    try:
        import mysql.connector
        conn = mysql.connector.connect(
            host=config.MYSQL_HOST,
            user=config.MYSQL_USER,
            password=config.MYSQL_PASS,
            database=config.MYSQL_DB,
        )
        return conn
    except Exception as e:
        print(f"ERROR: Could not connect to MySQL at {config.MYSQL_HOST}/{config.MYSQL_DB}: {e}")
        print("Check that the server is running and config.py is correct.")
        sys.exit(1)


def validate_column(col, valid_columns):
    """Validate a single column name. Exit with fuzzy suggestions on failure."""
    if col not in valid_columns:
        matches = difflib.get_close_matches(col, valid_columns, n=3, cutoff=0.6)
        hint = f" Did you mean: {', '.join(matches)}?" if matches else ""
        print(f"ERROR: Unknown column '{col}'.{hint}")
        sys.exit(1)


def parse_set_args(set_args, valid_columns):
    """Parse --set COL=VAL arguments into a dict, validating column names."""
    if not set_args:
        return {}
    overrides = {}
    for arg in set_args:
        eq_pos = arg.find("=")
        if eq_pos == -1:
            print(f"ERROR: Invalid --set format '{arg}'. Expected COL=VAL")
            sys.exit(1)
        col = arg[:eq_pos]
        val = arg[eq_pos + 1:]
        validate_column(col, valid_columns)
        val = resolve_enum_value(col, val)
        overrides[col] = val
    return overrides


def format_sql_value(value, col_name):
    """Format a value for SQL output based on column type."""
    if value is None:
        if col_name in TEXT_COLUMNS:
            return "''"
        return "0"

    if col_name in TEXT_COLUMNS:
        s = str(value).replace("'", "''")
        return f"'{s}'"

    if col_name in FLOAT_COLUMNS:
        try:
            f = float(value)
            # Use integer representation when the value is a whole number (matches existing SQL style)
            if f == int(f):
                return str(int(f))
            return str(f)
        except (ValueError, TypeError):
            return "0"

    # INT column
    try:
        return str(int(float(value)))
    except (ValueError, TypeError):
        return "0"


def fetch_override(conn, spell_id):
    """Fetch an existing override from alonecraft_spell_dbc. Returns dict or None."""
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM alonecraft_spell_dbc WHERE ID = %s", (spell_id,))
    row = cursor.fetchone()
    cursor.close()
    return row


def build_dbc_row(conn, spell_id, base_id, overrides, field_names, dbc_index):
    """Build the final row dict by layering: DBC base -> existing override -> user overrides."""
    source_id = base_id if base_id is not None else spell_id

    base = dbc_index.get(source_id)
    if base is None:
        if base_id is not None:
            print(f"ERROR: Base spell {source_id} not found in Spell.dbc.")
        else:
            print(f"ERROR: Spell {source_id} not found in Spell.dbc.")
            print("Use --base to specify a source spell to copy from.")
        sys.exit(1)

    # Start with a copy of the DBC row
    row = dict(base)

    # Layer existing alonecraft_spell_dbc override if present
    if base_id is None or base_id == spell_id:
        existing = fetch_override(conn, spell_id)
        if existing:
            print(f"  Note: Spell {spell_id} already has an override in alonecraft_spell_dbc. Layering changes on top.")
            existing_lower = {k.lower(): v for k, v in existing.items()}
            for col in field_names:
                val = existing_lower.get(col.lower())
                if val is not None:
                    row[col] = val

    # Record old values before applying user overrides (for diff summary)
    old_values = {}
    for col, val in overrides.items():
        old_values[col] = row.get(col)
        row[col] = val

    # Force the target spell ID
    row["ID"] = spell_id

    return row, old_values


# ---------------------------------------------------------------------------
# SQL generators
# ---------------------------------------------------------------------------

def generate_dbc_sql(spell_id, row, field_names, comment, overrides, old_values):
    """Generate DELETE+INSERT SQL for alonecraft_spell_dbc."""
    today = datetime.date.today().strftime("%Y-%m-%d")
    lines = []

    # Header comment
    if comment:
        lines.append(f"-- {comment}")
    lines.append(f"-- Generated by gen_sql.py on {today}")

    # Diff summary
    if overrides:
        diff_parts = []
        for col, new_val in overrides.items():
            old = old_values.get(col)
            old_display = f"'{old}'" if col in TEXT_COLUMNS else str(old)
            new_display = f"'{new_val}'" if col in TEXT_COLUMNS else str(new_val)
            diff_parts.append(f"{col}: {old_display} -> {new_display}")
        lines.append(f"-- Overrides: {', '.join(diff_parts)}")

    lines.append("")
    lines.append(f"DELETE FROM `alonecraft_spell_dbc` WHERE `ID` = {spell_id};")

    # Column list
    col_list = ", ".join(f"`{c}`" for c in field_names)
    lines.append(f"INSERT INTO `alonecraft_spell_dbc` ({col_list}) VALUES")

    # Value list
    vals = []
    for col in field_names:
        vals.append(format_sql_value(row[col], col))
    lines.append(f"({', '.join(vals)});")

    return "\n".join(lines) + "\n"


def generate_proc_sql(spell_id, overrides, comment):
    """Generate DELETE+INSERT SQL for spell_proc."""
    today = datetime.date.today().strftime("%Y-%m-%d")
    lines = []

    if comment:
        lines.append(f"-- {comment}")
    lines.append(f"-- Generated by gen_sql.py on {today}")
    lines.append("")

    lines.append(f"DELETE FROM `spell_proc` WHERE `SpellId` = {spell_id};")

    # Build row with defaults of 0
    row = {col: 0 for col in SPELL_PROC_COLUMNS}
    row["SpellId"] = spell_id
    for col, val in overrides.items():
        row[col] = int(float(val))

    col_list = ", ".join(f"`{c}`" for c in SPELL_PROC_COLUMNS)
    val_list = ", ".join(str(row[c]) for c in SPELL_PROC_COLUMNS)
    lines.append(f"INSERT INTO `spell_proc` ({col_list}) VALUES")
    lines.append(f"({val_list});")

    return "\n".join(lines) + "\n"


def generate_script_sql(spell_ids, script_name, comment):
    """Generate DELETE+INSERT SQL for spell_script_names."""
    today = datetime.date.today().strftime("%Y-%m-%d")
    lines = []

    if comment:
        lines.append(f"-- {comment}")
    lines.append(f"-- Generated by gen_sql.py on {today}")
    lines.append("")

    safe_name = script_name.replace("'", "''")
    lines.append(f"DELETE FROM `spell_script_names` WHERE `ScriptName` = '{safe_name}';")
    lines.append(f"INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES")

    value_lines = []
    for sid in spell_ids:
        value_lines.append(f"    ({sid}, '{safe_name}')")
    lines.append(",\n".join(value_lines) + ";")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------

def write_or_print(sql_content, args):
    """Output SQL based on mode: --stdout, --dry-run, --append-to, or write to file."""
    if args.stdout:
        print(sql_content)
        return

    # Prepend group comment section divider if requested
    if getattr(args, "group_comment", None):
        divider = (
            f"\n-- {'=' * 60}\n"
            f"-- {args.group_comment}\n"
            f"-- {'=' * 60}\n"
        )
        sql_content = divider + sql_content

    # Append mode
    if getattr(args, "append_to", None):
        # Resolve path: if just a filename, put it in MODULE_SQL
        append_path = args.append_to
        if not os.path.isabs(append_path):
            append_path = os.path.join(MODULE_SQL, append_path)

        if args.dry_run:
            print(f"[DRY RUN] Would append to: {append_path}")
            print("-" * 60)
            print(sql_content)
            return

        with open(append_path, "a", encoding="utf-8", newline="\n") as f:
            f.write("\n" + sql_content)
        print(f"  Appended to: {append_path}")
        return

    # Default: write new file
    today, seq = get_next_sql_sequence(MODULE_SQL)
    filename = f"{today}_{seq:02d}.sql"
    filepath = os.path.join(MODULE_SQL, filename)

    if args.dry_run:
        print(f"[DRY RUN] Would write to: {filename}")
        print("-" * 60)
        print(sql_content)
        return

    with open(filepath, "w", encoding="utf-8", newline="\n") as f:
        f.write(sql_content)
    print(f"Wrote: {filepath}")


# ---------------------------------------------------------------------------
# Spell name search
# ---------------------------------------------------------------------------

def search_spells_by_name(dbc_index, query, exact=False):
    """Search Spell.dbc for spells matching a name query on SpellName0.
    Returns list of (spell_id, row_dict) sorted by ID.
    """
    results = []
    q = query if exact else query.lower()
    for spell_id, row in dbc_index.items():
        name = row.get("SpellName0", "")
        if not name:
            continue
        if exact:
            if name == q:
                results.append((spell_id, row))
        else:
            if q in name.lower():
                results.append((spell_id, row))
    results.sort(key=lambda x: x[0])
    return results


# ---------------------------------------------------------------------------
# Talent index
# ---------------------------------------------------------------------------

def load_talent_index(talent_path=None):
    """Load Talent.dbc and build lookup structures.
    Returns (talent_records, spell_to_talent) where:
      talent_records: {talent_id: dict with TALENT_COLUMNS keys}
      spell_to_talent: {spell_id: talent_dict} for all non-zero SpellRank slots
    """
    if talent_path is None:
        talent_path = getattr(config, "BASE_TALENT_DBC_PATH", None)
    if not talent_path or not os.path.exists(talent_path):
        print("  ERROR: Talent.dbc not found. Check BASE_TALENT_DBC_PATH in config.py.")
        sys.exit(1)

    raw_records, _ = read_int_dbc(talent_path, TALENT_FIELD_COUNT, TALENT_RECORD_SIZE)

    talent_records = {}
    spell_to_talent = {}

    for tid, values in raw_records.items():
        row = dict(zip(TALENT_COLUMNS, values))
        talent_records[tid] = row
        for i in range(1, 10):
            sid = row.get(f"SpellRank_{i}", 0)
            if sid:
                spell_to_talent[sid] = row

    return talent_records, spell_to_talent


# ---------------------------------------------------------------------------
# Batch CSV parsing
# ---------------------------------------------------------------------------

def parse_batch_csv(csv_path, valid_columns):
    """Parse a batch CSV file. Expected format: spell_id,column,value
    Returns dict[int, dict[str, str]] mapping spell_id -> {column: value}.
    """
    if not os.path.exists(csv_path):
        print(f"ERROR: CSV file not found: {csv_path}")
        sys.exit(1)

    result = {}
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader, None)
        if not header or len(header) < 3:
            print("ERROR: CSV must have header: spell_id,column,value")
            sys.exit(1)

        # Normalize header
        h = [h.strip().lower() for h in header]
        if h[:3] != ["spell_id", "column", "value"]:
            print(f"ERROR: CSV header must be 'spell_id,column,value', got: {header}")
            sys.exit(1)

        for row_num, row in enumerate(reader, start=2):
            if len(row) < 3:
                print(f"ERROR: CSV row {row_num} has fewer than 3 columns: {row}")
                sys.exit(1)
            try:
                spell_id = int(row[0].strip())
            except ValueError:
                print(f"ERROR: CSV row {row_num}: invalid spell_id '{row[0]}'")
                sys.exit(1)
            col = row[1].strip()
            val = row[2].strip()
            validate_column(col, valid_columns)
            val = resolve_enum_value(col, val)
            if spell_id not in result:
                result[spell_id] = {}
            result[spell_id][col] = val

    return result


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_lookup(args):
    """Handle the 'lookup' subcommand -- display spell data from binary Spell.dbc."""
    field_names = list(SPELL_COLUMNS)

    source = getattr(args, "source", "base") or "base"
    spell_path, _ = resolve_dbc_paths(source)
    print(f"  Source: {source} ({spell_path})")
    print(f"  Loading Spell.dbc...")
    dbc_index = load_spell_index(spell_path)
    print(f"  Loaded {len(dbc_index)} spells from Spell.dbc")

    # Name search mode
    if args.name:
        results = search_spells_by_name(dbc_index, args.name, exact=args.exact)
        if not results:
            print(f"  No spells found matching '{args.name}'")
            return

        limit = args.limit
        total = len(results)
        if total > limit:
            print(f"  Found {total} matches (showing first {limit}, use --limit to see more):\n")
            results = results[:limit]
        else:
            print(f"  Found {total} match(es):\n")

        # Print table
        print(f"  {'ID':>8}  {'SpellName0':<45}  {'SpellRank0'}")
        print(f"  {'--------':>8}  {'---------------------------------------------':<45}  {'----------'}")
        for spell_id, row in results:
            name = row.get("SpellName0", "")[:45]
            rank = row.get("SpellRank0", "")
            print(f"  {spell_id:>8}  {name:<45}  {rank}")
        return

    # Single spell ID mode
    row = dbc_index.get(args.spell_id)
    if row is None:
        print(f"  ERROR: Spell {args.spell_id} not found in Spell.dbc.")
        sys.exit(1)

    # Layer alonecraft_spell_dbc override if available
    try:
        conn = get_db_connection()
        existing = fetch_override(conn, args.spell_id)
        conn.close()
        if existing:
            print(f"  Note: Spell {args.spell_id} has an override in alonecraft_spell_dbc (layered below).")
            row = dict(row)
            existing_lower = {k.lower(): v for k, v in existing.items()}
            for col in field_names:
                val = existing_lower.get(col.lower())
                if val is not None:
                    row[col] = val
    except SystemExit:
        print("  Warning: Could not connect to MySQL. Showing base DBC values only.")

    # Key fields shown by default (names match SPELL_COLUMNS in spell_dbc.py)
    KEY_FIELDS = [
        "ID", "SpellName0", "SpellRank0", "SpellDescription0", "SpellToolTip0",
        "Category", "Dispel", "Mechanic",
        "Attributes", "AttributesEx", "AttributesEx2", "AttributesEx3",
        "AttributesEx4", "AttributesEx5", "AttributesEx6", "AttributesEx7",
        "CastingTimeIndex", "RecoveryTime", "CategoryRecoveryTime",
        "ProcFlags", "ProcChance", "ProcCharges",
        "MaximumLevel", "BaseLevel", "SpellLevel",
        "DurationIndex", "PowerType", "ManaCost", "ManaCostPercentage",
        "RangeIndex", "Speed", "StackAmount",
        "Effect1", "Effect2", "Effect3",
        "EffectDieSides1", "EffectDieSides2", "EffectDieSides3",
        "EffectBasePoints1", "EffectBasePoints2", "EffectBasePoints3",
        "EffectApplyAuraName1", "EffectApplyAuraName2", "EffectApplyAuraName3",
        "EffectAmplitude1", "EffectAmplitude2", "EffectAmplitude3",
        "EffectImplicitTargetA1", "EffectImplicitTargetA2", "EffectImplicitTargetA3",
        "EffectImplicitTargetB1", "EffectImplicitTargetB2", "EffectImplicitTargetB3",
        "EffectMiscValue1", "EffectMiscValue2", "EffectMiscValue3",
        "EffectMiscValueB1", "EffectMiscValueB2", "EffectMiscValueB3",
        "EffectTriggerSpell1", "EffectTriggerSpell2", "EffectTriggerSpell3",
        "EffectMultipleValue1", "EffectMultipleValue2", "EffectMultipleValue3",
        "EffectDamageMultiplier1", "EffectDamageMultiplier2", "EffectDamageMultiplier3",
        "EffectBonusMultiplier1", "EffectBonusMultiplier2", "EffectBonusMultiplier3",
        "EffectSpellClassMaskA1", "EffectSpellClassMaskA2", "EffectSpellClassMaskA3",
        "EffectSpellClassMaskB1", "EffectSpellClassMaskB2", "EffectSpellClassMaskB3",
        "EffectSpellClassMaskC1", "EffectSpellClassMaskC2", "EffectSpellClassMaskC3",
        "SpellFamilyName", "SpellFamilyFlags", "SpellFamilyFlags1", "SpellFamilyFlags2",
        "MaximumAffectedTargets", "DamageClass", "PreventionType", "SchoolMask",
        "SpellIconID", "ActiveIconID",
        "SpellVisual1", "SpellVisual2",
        "EquippedItemClass", "EquippedItemSubClassMask", "EquippedItemInventoryTypeMask",
    ]

    print()
    if args.all:
        max_col = max(len(c) for c in field_names)
        for col in field_names:
            val = row.get(col, "")
            if val is None:
                val = ""
            annotation = _enum_annotation(col, val)
            print(f"  {col:<{max_col}}  {val}{annotation}")
    else:
        cols_to_show = [c for c in KEY_FIELDS if c in row]
        max_col = max(len(c) for c in cols_to_show) if cols_to_show else 30
        for col in cols_to_show:
            val = row.get(col, "")
            if val is None:
                val = ""
            annotation = _enum_annotation(col, val)
            print(f"  {col:<{max_col}}  {val}{annotation}")
        print(f"\n  ({len(field_names)} total columns -- use --all to see everything)")


def cmd_talent(args):
    """Handle the 'talent' subcommand -- look up talent entries by spell name."""
    source = getattr(args, "source", "base") or "base"
    spell_path, talent_path = resolve_dbc_paths(source)
    print(f"  Source: {source} ({spell_path})")
    print("  Loading Spell.dbc...")
    dbc_index = load_spell_index(spell_path)
    print(f"  Loaded {len(dbc_index)} spells")

    print("  Loading Talent.dbc...")
    talent_records, spell_to_talent = load_talent_index(talent_path)
    print(f"  Loaded {len(talent_records)} talents")

    # Search by name in Spell.dbc
    results = search_spells_by_name(dbc_index, args.name, exact=args.exact)
    if not results:
        print(f"  No spells found matching '{args.name}'")
        return

    # Cross-reference with talent entries
    seen_talents = set()
    found_any = False

    for spell_id, spell_row in results:
        talent = spell_to_talent.get(spell_id)
        if not talent:
            continue
        tid = talent["ID"]
        if tid in seen_talents:
            continue
        seen_talents.add(tid)
        found_any = True

        print(f"\n  Talent ID:     {tid}")
        print(f"  TabID:         {talent['TabID']}")
        print(f"  TierID:        {talent['TierID']}  (row in talent tree)")
        print(f"  ColumnIndex:   {talent['ColumnIndex']}  (column in talent tree)")
        print(f"  Flags:         {talent['Flags']}")
        if talent.get("RequiredSpellID"):
            print(f"  RequiredSpell: {talent['RequiredSpellID']}")
        for pi in range(1, 4):
            prereq = talent.get(f"PrereqTalent_{pi}", 0)
            if prereq:
                prereq_rank = talent.get(f"PrereqRank_{pi}", 0)
                print(f"  PrereqTalent:  {prereq} (rank {prereq_rank})")

        print(f"  Ranks:")
        for ri in range(1, 10):
            sid = talent.get(f"SpellRank_{ri}", 0)
            if not sid:
                continue
            srow = dbc_index.get(sid)
            if srow:
                sname = srow.get("SpellName0", "?")
                srank = srow.get("SpellRank0", "")
                sdesc = srow.get("SpellDescription0", "")
                if len(sdesc) > 80:
                    sdesc = sdesc[:77] + "..."
                print(f"    Rank {ri}: spell {sid:>6}  {sname} {srank}")
                if sdesc:
                    print(f"             {sdesc}")
            else:
                print(f"    Rank {ri}: spell {sid:>6}  (not found in Spell.dbc)")

    if not found_any:
        # Show spell matches that aren't talents
        print(f"\n  Found {len(results)} spell(s) matching '{args.name}', but none are talent spells.")
        print(f"  Spell matches:")
        for spell_id, row in results[:20]:
            name = row.get("SpellName0", "")
            rank = row.get("SpellRank0", "")
            print(f"    {spell_id:>8}  {name}  {rank}")


# ---------------------------------------------------------------------------
# TalentTab -> class/spec mapping (from TalentTab.dbc)
# ---------------------------------------------------------------------------

# TabID -> (ClassName, SpecName, tabpage)
TALENT_TAB_INFO = {
    # Warrior
    161: ("Warrior", "Arms", 0),
    163: ("Warrior", "Fury", 1),
    164: ("Warrior", "Protection", 2),
    # Paladin
    381: ("Paladin", "Holy", 0),
    382: ("Paladin", "Protection", 1),
    383: ("Paladin", "Retribution", 2),
    # Hunter
    361: ("Hunter", "Beast Mastery", 0),
    363: ("Hunter", "Marksmanship", 1),
    362: ("Hunter", "Survival", 2),
    # Rogue
    182: ("Rogue", "Assassination", 0),
    181: ("Rogue", "Combat", 1),
    183: ("Rogue", "Subtlety", 2),
    # Priest
    201: ("Priest", "Discipline", 0),
    202: ("Priest", "Holy", 1),
    203: ("Priest", "Shadow", 2),
    # Death Knight
    398: ("Death Knight", "Blood", 0),
    399: ("Death Knight", "Frost", 1),
    400: ("Death Knight", "Unholy", 2),
    # Shaman
    261: ("Shaman", "Elemental", 0),
    263: ("Shaman", "Enhancement", 1),
    262: ("Shaman", "Restoration", 2),
    # Mage
    81: ("Mage", "Arcane", 0),
    41: ("Mage", "Fire", 1),
    61: ("Mage", "Frost", 2),
    # Warlock
    302: ("Warlock", "Affliction", 0),
    303: ("Warlock", "Demonology", 1),
    301: ("Warlock", "Destruction", 2),
    # Druid
    283: ("Druid", "Balance", 0),
    281: ("Druid", "Feral", 1),
    282: ("Druid", "Restoration", 2),
}

# Class name (lowercase) -> list of TabIDs in tabpage order [0, 1, 2]
CLASS_TABS = {}
for _tab_id, (_cls, _spec, _page) in TALENT_TAB_INFO.items():
    _cls_lower = _cls.lower()
    if _cls_lower not in CLASS_TABS:
        CLASS_TABS[_cls_lower] = [None, None, None]
    CLASS_TABS[_cls_lower][_page] = _tab_id


def _build_talent_tree(talent_records, tab_id, dbc_index):
    """Build sorted list of talents for a talent tab.
    Returns list of dicts with talent info, sorted by (TierID, ColumnIndex).
    """
    talents = []
    for tid, row in talent_records.items():
        if row["TabID"] != tab_id:
            continue
        # Count max ranks
        max_rank = 0
        for ri in range(1, 10):
            if row.get(f"SpellRank_{ri}", 0):
                max_rank = ri
        # Get spell name from rank 1
        spell_id = row.get("SpellRank_1", 0)
        spell_name = "?"
        spell_desc = ""
        if spell_id and spell_id in dbc_index:
            spell_name = dbc_index[spell_id].get("SpellName0", "?")
            spell_desc = dbc_index[spell_id].get("SpellDescription0", "")
        talents.append({
            "talent_id": tid,
            "tier": row["TierID"],
            "col": row["ColumnIndex"],
            "max_rank": max_rank,
            "spell_id": spell_id,
            "name": spell_name,
            "desc": spell_desc,
        })
    talents.sort(key=lambda t: (t["tier"], t["col"]))
    return talents


def cmd_talent_link(args):
    """Decode a wowhead-style talent link into human-readable talent names."""
    # Resolve class
    cls = args.class_name.lower()
    if cls == "dk":
        cls = "death knight"
    if cls not in CLASS_TABS:
        print(f"  ERROR: Unknown class '{args.class_name}'.")
        print(f"  Valid classes: {', '.join(sorted(CLASS_TABS.keys()))}")
        sys.exit(1)

    tab_ids = CLASS_TABS[cls]
    class_name = TALENT_TAB_INFO[tab_ids[0]][0]

    # Parse the link: "digits-digits-digits" for each tree
    link = args.link
    parts = link.split("-")
    # Handle leading/trailing dashes (empty trees)
    # e.g. "-235050032302152530000331351" means tree 0 is empty
    # Split on '-' gives ['', '2350...'] — pad to 3 parts
    while len(parts) < 3:
        parts.append("")

    source = getattr(args, "source", "base") or "base"
    spell_path, talent_path = resolve_dbc_paths(source)

    print(f"  Source: {source} ({spell_path})")
    print(f"  Loading Spell.dbc...")
    dbc_index = load_spell_index(spell_path)
    print(f"  Loaded {len(dbc_index)} spells")

    print(f"  Loading Talent.dbc...")
    talent_records_raw, _ = load_talent_index(talent_path)
    # Convert to dict-of-dicts if needed
    talent_records = {}
    for tid, val in talent_records_raw.items():
        if isinstance(val, dict):
            talent_records[tid] = val
        else:
            talent_records[tid] = dict(zip(TALENT_COLUMNS, val))
    print(f"  Loaded {len(talent_records)} talents")

    total_points = 0
    all_unspent = []  # collect talents with 0 points for summary

    for tree_idx in range(3):
        tab_id = tab_ids[tree_idx]
        spec_name = TALENT_TAB_INFO[tab_id][1]
        link_str = parts[tree_idx]
        tree_talents = _build_talent_tree(talent_records, tab_id, dbc_index)

        if not tree_talents:
            print(f"\n  {spec_name} (TabID {tab_id}): no talents found")
            continue

        # Map link characters to talents
        tree_points = 0
        rows = []
        for i, talent in enumerate(tree_talents):
            if i < len(link_str):
                pts = int(link_str[i])
            else:
                pts = 0
            tree_points += pts
            total_points += pts

            flag = ""
            if pts == 0 and talent["max_rank"] > 0:
                all_unspent.append((spec_name, talent))
            if pts > 0 and pts < talent["max_rank"]:
                flag = " (partial)"
            rows.append((talent, pts, flag))

        print(f"\n  === {spec_name} ({tree_points} points) ===")
        if tree_points == 0 and not link_str:
            print(f"  (no points spent)")
            continue

        # Print header
        print(f"  {'Tier':<5} {'Col':<4} {'Pts':<8} {'Talent Name':<30} {'Description'}")
        print(f"  {'-'*4}  {'-'*3} {'-'*7} {'-'*29} {'-'*50}")

        for talent, pts, flag in rows:
            pts_str = f"{pts}/{talent['max_rank']}{flag}"
            desc = talent["desc"]
            if len(desc) > 50:
                desc = desc[:47] + "..."
            if pts > 0:
                print(f"  {talent['tier']:<5} {talent['col']:<4} {pts_str:<8} {talent['name']:<30} {desc}")
            elif args.show_all:
                print(f"  {talent['tier']:<5} {talent['col']:<4} {pts_str:<8} {talent['name']:<30} {desc}")

        # Check for link overflow
        if len(link_str) > len(tree_talents):
            print(f"  WARNING: Link has {len(link_str)} chars but tree only has {len(tree_talents)} talents")

    print(f"\n  Total: {total_points} points")

    if not args.show_all and all_unspent:
        print(f"\n  Skipped talents (0 points, use --all to show):")
        for spec_name, t in all_unspent:
            desc = t["desc"]
            if len(desc) > 60:
                desc = desc[:57] + "..."
            print(f"    [{spec_name}] T{t['tier']}.{t['col']} {t['name']}: {desc}")


def cmd_dbc(args):
    """Handle the 'dbc' subcommand (single or batch)."""
    field_names = list(SPELL_COLUMNS)
    valid_set = set(field_names)

    # Determine mode: single, multi, or CSV
    if args.input:
        batch_overrides = parse_batch_csv(args.input, valid_set)
        spell_ids = sorted(batch_overrides.keys())
        shared_overrides = parse_set_args(args.set, valid_set)
        print(f"  CSV batch mode: {len(spell_ids)} spell(s) from {args.input}")
    elif args.spell_ids:
        spell_ids = [int(x.strip()) for x in args.spell_ids.split(",")]
        shared_overrides = parse_set_args(args.set, valid_set)
        if not shared_overrides:
            print("ERROR: No --set overrides specified. Nothing to do.")
            sys.exit(1)
        batch_overrides = None
        print(f"  Batch mode: {len(spell_ids)} spell(s)")
    else:
        # Single spell mode (original behavior)
        overrides = parse_set_args(args.set, valid_set)
        if not overrides:
            print("ERROR: No --set overrides specified. Nothing to do.")
            sys.exit(1)

        print(f"  Spell ID: {args.spell_id}")
        if args.base is not None:
            print(f"  Base spell: {args.base}")
        print(f"  Overrides: {len(overrides)} column(s)")
        print("  Loading Spell.dbc...")
        dbc_index = load_spell_index(config.BASE_DBC_PATH)
        print(f"  Loaded {len(dbc_index)} spells from Spell.dbc")

        conn = get_db_connection()
        row, old_values = build_dbc_row(conn, args.spell_id, args.base, overrides, field_names, dbc_index)
        conn.close()

        sql = generate_dbc_sql(args.spell_id, row, field_names, args.comment, overrides, old_values)
        write_or_print(sql, args)
        return

    # Batch mode (--spell-ids or --input)
    print(f"  Overrides: {len(shared_overrides)} shared column(s)")
    print("  Loading Spell.dbc...")
    dbc_index = load_spell_index(config.BASE_DBC_PATH)
    print(f"  Loaded {len(dbc_index)} spells from Spell.dbc")

    conn = get_db_connection()
    sql_blocks = []

    for sid in spell_ids:
        # Merge shared overrides with per-spell CSV overrides
        overrides = dict(shared_overrides)
        if batch_overrides and sid in batch_overrides:
            overrides.update(batch_overrides[sid])

        if not overrides:
            print(f"  Warning: No overrides for spell {sid}, skipping.")
            continue

        row, old_values = build_dbc_row(conn, sid, args.base, overrides, field_names, dbc_index)
        block = generate_dbc_sql(sid, row, field_names, None, overrides, old_values)
        sql_blocks.append(f"-- Spell ID: {sid}")
        sql_blocks.append(block)

    conn.close()

    if not sql_blocks:
        print("ERROR: No SQL generated.")
        sys.exit(1)

    # Assemble with header
    today = datetime.date.today().strftime("%Y-%m-%d")
    header = ""
    if args.comment:
        header += f"-- {args.comment}\n"
    header += f"-- Generated by gen_sql.py on {today} (batch: {len(spell_ids)} spells)\n\n"

    sql = header + "\n".join(sql_blocks)
    write_or_print(sql, args)


def cmd_proc(args):
    """Handle the 'proc' subcommand."""
    overrides = parse_set_args(args.set, set(SPELL_PROC_COLUMNS) - {"SpellId"})
    if not overrides:
        print("ERROR: No --set overrides specified. Nothing to do.")
        sys.exit(1)

    print(f"  Spell ID: {args.spell_id}")
    print(f"  Overrides: {len(overrides)} column(s)")

    sql = generate_proc_sql(args.spell_id, overrides, args.comment)
    write_or_print(sql, args)


def cmd_script(args):
    """Handle the 'script' subcommand."""
    spell_ids = [int(x.strip()) for x in args.spell_id.split(",")]

    print(f"  Spell IDs: {spell_ids}")
    print(f"  Script name: {args.script_name}")

    sql = generate_script_sql(spell_ids, args.script_name, args.comment)
    write_or_print(sql, args)


def cmd_classmask(args):
    """Handle the 'classmask' subcommand -- compute SpellFamilyFlags masks."""
    spell_ids = [int(x.strip()) for x in args.spells.split(",")]

    print(f"  Loading Spell.dbc...")
    dbc_index = load_spell_index(config.BASE_DBC_PATH)
    print(f"  Loaded {len(dbc_index)} spells")

    # Collect masks
    masks = []  # list of (spell_id, name, [flags0, flags1, flags2])
    for sid in spell_ids:
        row = dbc_index.get(sid)
        if row is None:
            print(f"  ERROR: Spell {sid} not found in Spell.dbc.")
            sys.exit(1)

        family = int(row.get("SpellFamilyName", 0))
        if family != args.family:
            print(f"  Warning: Spell {sid} has SpellFamilyName={family}, expected {args.family}")

        f0 = int(row.get("SpellFamilyFlags", 0)) & 0xFFFFFFFF
        f1 = int(row.get("SpellFamilyFlags1", 0)) & 0xFFFFFFFF
        f2 = int(row.get("SpellFamilyFlags2", 0)) & 0xFFFFFFFF
        name = row.get("SpellName0", "?")
        masks.append((sid, name, [f0, f1, f2]))

    # Print per-spell breakdown
    print()
    for sid, name, (f0, f1, f2) in masks:
        print(f"  Spell {sid} \"{name}\":")
        print(f"    SpellFamilyFlags   = 0x{f0:08X}  ({f0})")
        print(f"    SpellFamilyFlags1  = 0x{f1:08X}  ({f1})")
        print(f"    SpellFamilyFlags2  = 0x{f2:08X}  ({f2})")
        # Show individual bit positions
        for word_idx, (label, val) in enumerate([("Flags", f0), ("Flags1", f1), ("Flags2", f2)]):
            if val:
                bits = [str(b) for b in range(32) if val & (1 << b)]
                print(f"    {label} bits: {', '.join(bits)}")
        print()

    if len(masks) < 2:
        # Single spell, just show it
        f0, f1, f2 = masks[0][2]
        print(f"  Paste for --set:")
        print(f"    --set SpellFamilyMask0={f0} --set SpellFamilyMask1={f1} --set SpellFamilyMask2={f2}")
        return

    # Compute AND and OR
    and_result = [0xFFFFFFFF, 0xFFFFFFFF, 0xFFFFFFFF]
    or_result = [0, 0, 0]
    for _, _, m in masks:
        for i in range(3):
            and_result[i] &= m[i]
            or_result[i] |= m[i]

    labels = ["SpellFamilyFlags ", "SpellFamilyFlags1", "SpellFamilyFlags2"]

    print(f"  AND result (bits common to ALL spells):")
    for i in range(3):
        print(f"    {labels[i]}  = 0x{and_result[i]:08X}  ({and_result[i]})")

    print(f"\n  OR result (bits matching ANY spell):")
    for i in range(3):
        print(f"    {labels[i]}  = 0x{or_result[i]:08X}  ({or_result[i]})")

    # Paste-ready output for both
    print(f"\n  Paste for --set (AND - match ALL):")
    print(f"    --set SpellFamilyMask0={and_result[0]} --set SpellFamilyMask1={and_result[1]} --set SpellFamilyMask2={and_result[2]}")
    print(f"\n  Paste for --set (OR - match ANY):")
    print(f"    --set SpellFamilyMask0={or_result[0]} --set SpellFamilyMask1={or_result[1]} --set SpellFamilyMask2={or_result[2]}")


def cmd_enum(args):
    """Handle the 'enum' subcommand -- search aura/effect enum values."""
    if args.aura:
        query = args.aura.upper()
        name_to_val, _ = get_aura_enum()
        if not name_to_val:
            print("  ERROR: Could not load aura enum.")
            return

        matches = []
        for name, val in sorted(name_to_val.items(), key=lambda x: x[1]):
            # Match substring after SPELL_AURA_ prefix
            short = name.replace("SPELL_AURA_", "")
            if query in short or query in name:
                matches.append((name, val))

        if matches:
            print(f"\n  Matching auras for \"{args.aura}\":")
            for name, val in matches:
                print(f"    {name:<55} = {val}")
        else:
            print(f"  No aura enums matching \"{args.aura}\"")
            # Fuzzy suggest
            all_shorts = [n.replace("SPELL_AURA_", "") for n in name_to_val]
            close = difflib.get_close_matches(query, all_shorts, n=5, cutoff=0.5)
            if close:
                print(f"  Did you mean: {', '.join(close)}?")

    if args.effect:
        query = args.effect.upper()
        name_to_val, _ = get_effect_enum()
        if not name_to_val:
            print("  ERROR: Could not load effect enum.")
            return

        matches = []
        for name, val in sorted(name_to_val.items(), key=lambda x: x[1]):
            short = name.replace("SPELL_EFFECT_", "")
            if query in short or query in name:
                matches.append((name, val))

        if matches:
            print(f"\n  Matching effects for \"{args.effect}\":")
            for name, val in matches:
                print(f"    {name:<55} = {val}")
        else:
            print(f"  No effect enums matching \"{args.effect}\"")
            all_shorts = [n.replace("SPELL_EFFECT_", "") for n in name_to_val]
            close = difflib.get_close_matches(query, all_shorts, n=5, cutoff=0.5)
            if close:
                print(f"  Did you mean: {', '.join(close)}?")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def add_common_args(p):
    """Add --dry-run, --stdout, --comment, --append-to, --group-comment to a subparser."""
    p.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    p.add_argument("--stdout", action="store_true", help="Print SQL to stdout instead of writing a file")
    p.add_argument("--comment", default=None, help="Description for the SQL file header")
    p.add_argument("--append-to", default=None,
                   help="Append SQL to an existing file instead of creating a new one")
    p.add_argument("--group-comment", default=None,
                   help="Section comment header when appending to a grouped file")


def main():
    parser = argparse.ArgumentParser(
        description="Alonecraft SQL Generator -- produce idempotent SQL from column overrides",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # lookup subcommand
    p_lookup = subparsers.add_parser("lookup", help="Look up spell data from binary Spell.dbc")
    lookup_id = p_lookup.add_mutually_exclusive_group(required=True)
    lookup_id.add_argument("--spell-id", type=int, help="Spell ID to look up")
    lookup_id.add_argument("--name", type=str, help="Search spells by name (substring match)")
    p_lookup.add_argument("--all", action="store_true", help="Show all 234 columns (default: key fields only)")
    p_lookup.add_argument("--exact", action="store_true", help="Require exact name match (with --name)")
    p_lookup.add_argument("--limit", type=int, default=50, help="Max results for name search (default: 50)")
    p_lookup.add_argument("--source", choices=["base", "live"], default="base",
                          help="DBC source: 'base' (safe backup) or 'live' (built with overrides)")
    p_lookup.set_defaults(func=cmd_lookup)

    # talent subcommand
    p_talent = subparsers.add_parser("talent", help="Look up talent entries by spell name")
    p_talent.add_argument("--name", required=True, help="Talent/spell name to search for")
    p_talent.add_argument("--exact", action="store_true", help="Require exact name match")
    p_talent.add_argument("--source", choices=["base", "live"], default="base",
                          help="DBC source: 'base' (safe backup) or 'live' (built with overrides)")
    p_talent.set_defaults(func=cmd_talent)

    # talent-link subcommand
    p_tlink = subparsers.add_parser("talent-link", help="Decode a wowhead-style talent link string")
    p_tlink.add_argument("--class", dest="class_name", required=True,
                         help="Class name (e.g. priest, warrior, dk)")
    p_tlink.add_argument("--link", required=True,
                         help="Talent link string (e.g. '05032031-235050032302152530000331351')")
    p_tlink.add_argument("--all", dest="show_all", action="store_true",
                         help="Show all talents including those with 0 points")
    p_tlink.add_argument("--source", choices=["base", "live"], default="base",
                         help="DBC source: 'base' (safe backup) or 'live' (built with overrides)")
    p_tlink.set_defaults(func=cmd_talent_link)

    # dbc subcommand
    p_dbc = subparsers.add_parser("dbc", help="Generate alonecraft_spell_dbc SQL")
    dbc_target = p_dbc.add_mutually_exclusive_group(required=True)
    dbc_target.add_argument("--spell-id", type=int, help="Target spell ID (single)")
    dbc_target.add_argument("--spell-ids", type=str, help="Comma-separated spell IDs (batch)")
    dbc_target.add_argument("--input", type=str, help="CSV file for batch changes (spell_id,column,value)")
    p_dbc.add_argument("--base", type=int, default=None, help="Source spell ID to copy from (for new custom spells)")
    p_dbc.add_argument("--set", action="append", metavar="COL=VAL", help="Column override (repeatable)")
    add_common_args(p_dbc)
    p_dbc.set_defaults(func=cmd_dbc)

    # proc subcommand
    p_proc = subparsers.add_parser("proc", help="Generate spell_proc SQL")
    p_proc.add_argument("--spell-id", type=int, required=True, help="SpellId value")
    p_proc.add_argument("--set", action="append", metavar="COL=VAL", help="Column override (repeatable)")
    add_common_args(p_proc)
    p_proc.set_defaults(func=cmd_proc)

    # script subcommand
    p_script = subparsers.add_parser("script", help="Generate spell_script_names SQL")
    p_script.add_argument("--spell-id", required=True, help="Comma-separated spell IDs (negative = all ranks)")
    p_script.add_argument("--script-name", required=True, help="ScriptName value")
    add_common_args(p_script)
    p_script.set_defaults(func=cmd_script)

    # classmask subcommand
    p_mask = subparsers.add_parser("classmask", help="Compute SpellFamilyFlags mask for spells")
    p_mask.add_argument("--family", type=int, required=True, help="SpellFamilyName value (e.g. 15 for DK)")
    p_mask.add_argument("--spells", required=True, help="Comma-separated spell IDs")
    p_mask.set_defaults(func=cmd_classmask)

    # enum subcommand
    p_enum = subparsers.add_parser("enum", help="Look up spell aura/effect enum values")
    p_enum.add_argument("--aura", type=str, help="Search AuraType enum (e.g. MOD_PARRY)")
    p_enum.add_argument("--effect", type=str, help="Search SpellEffects enum (e.g. APPLY_AURA)")
    p_enum.set_defaults(func=cmd_enum)

    args = parser.parse_args()

    print("=" * 60)
    print("  Alonecraft SQL Generator")
    print("=" * 60)

    args.func(args)


if __name__ == "__main__":
    main()
