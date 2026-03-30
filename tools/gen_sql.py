#!/usr/bin/env python3
"""
Alonecraft SQL Generator

Generates idempotent SQL files for alonecraft_spell_dbc, spell_proc, and
spell_script_names from high-level change descriptions.  Specify only the
columns you want to change; the tool fetches the full base row from the live
database and produces a complete DELETE+INSERT file.

Usage:
    python tools/gen_sql.py dbc --spell-id 33186 --set EffectBasePoints1=50 --set SpellName0="New Name"
    python tools/gen_sql.py dbc --spell-id 200100 --base 12345 --set SpellName0="Custom Spell"
    python tools/gen_sql.py proc --spell-id 200100 --set ProcFlags=65536 --set Chance=100
    python tools/gen_sql.py script --spell-id 200100,-5176 --script-name spell_example

Options:
    --dry-run     Show what would be generated without writing files
    --stdout      Print SQL to stdout instead of writing a file
    --comment     Add a description to the SQL file header
"""

import argparse
import csv
import datetime
import difflib
import glob
import os
import re
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_SQL = os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "data", "sql", "db-world")
DBC_CSV = os.path.join(REPO_ROOT, "DBC_data", "Spell.csv")

# Add the DBC module to path so we can import config
sys.path.insert(0, os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc"))
import config  # noqa: E402

# Column type sets -- derived from the CREATE TABLE DDL in 2026_03_29_09.sql.
# WoW 3.3.5a DBC format is frozen, so these are stable.
FLOAT_COLUMNS = {
    "Speed",
    "EffectRealPointsPerLevel1", "EffectRealPointsPerLevel2", "EffectRealPointsPerLevel3",
    "EffectMultipleValue1", "EffectMultipleValue2", "EffectMultipleValue3",
    "EffectPointsPerComboPoint1", "EffectPointsPerComboPoint2", "EffectPointsPerComboPoint3",
    "EffectDamageMultiplier1", "EffectDamageMultiplier2", "EffectDamageMultiplier3",
    "EffectBonusMultiplier1", "EffectBonusMultiplier2", "EffectBonusMultiplier3",
}

# TEXT columns in the DDL.  Note: SpellNameFlag7, SpellRankFlags7,
# SpellDescriptionFlags0-7, and SpellToolTipFlags0-7 are INT, not TEXT.
TEXT_COLUMNS = set()
for _prefix in ("SpellName", "SpellRank", "SpellDescription", "SpellToolTip"):
    for _i in range(9):
        TEXT_COLUMNS.add(f"{_prefix}{_i}")
for _prefix in ("SpellNameFlag", "SpellRankFlags"):
    for _i in range(7):  # 0-6 are TEXT; 7 is INT
        TEXT_COLUMNS.add(f"{_prefix}{_i}")

SPELL_PROC_COLUMNS = (
    "SpellId", "SchoolMask", "SpellFamilyName",
    "SpellFamilyMask0", "SpellFamilyMask1", "SpellFamilyMask2",
    "ProcFlags", "SpellTypeMask", "SpellPhaseMask", "HitMask",
    "AttributesMask", "DisableEffectsMask", "ProcsPerMinute",
    "Chance", "Cooldown", "Charges",
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_field_names():
    """Read the 234 column names from DBC_data/Spell.csv header."""
    with open(DBC_CSV, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
    if len(header) != 234:
        print(f"WARNING: Expected 234 columns in Spell.csv, got {len(header)}")
    return header


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
        if col not in valid_columns:
            matches = difflib.get_close_matches(col, valid_columns, n=3, cutoff=0.6)
            hint = f" Did you mean: {', '.join(matches)}?" if matches else ""
            print(f"ERROR: Unknown column '{col}'.{hint}")
            sys.exit(1)
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


def load_spell_csv_index(field_names):
    """Build an index of spell ID -> row dict from DBC_data/Spell.csv.

    Reads the full CSV once and returns a dict keyed by integer spell ID.
    Each value is a dict mapping field_name -> raw string value.
    """
    index = {}
    with open(DBC_CSV, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for row in reader:
            if len(row) < len(field_names):
                continue
            spell_id = int(row[0])
            index[spell_id] = {field_names[i]: row[i] for i in range(len(field_names))}
    return index


def fetch_override(conn, spell_id):
    """Fetch an existing override from alonecraft_spell_dbc. Returns dict or None."""
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM alonecraft_spell_dbc WHERE ID = %s", (spell_id,))
    row = cursor.fetchone()
    cursor.close()
    return row


def build_dbc_row(conn, spell_id, base_id, overrides, field_names, csv_index):
    """Build the final row dict by layering: CSV base -> existing override -> user overrides."""
    source_id = base_id if base_id is not None else spell_id

    base = csv_index.get(source_id)
    if base is None:
        if base_id is not None:
            print(f"ERROR: Base spell {source_id} not found in Spell.csv.")
        else:
            print(f"ERROR: Spell {source_id} not found in Spell.csv.")
            print("Use --base to specify a source spell to copy from.")
        sys.exit(1)

    # Start with a copy of the CSV row (all values are strings at this point)
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


def write_or_print(sql_content, args):
    """Output SQL based on mode: --stdout, --dry-run, or write to file."""
    if args.stdout:
        print(sql_content)
        return

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
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_dbc(args):
    """Handle the 'dbc' subcommand."""
    field_names = load_field_names()
    valid_set = set(field_names)

    overrides = parse_set_args(args.set, valid_set)
    if not overrides:
        print("ERROR: No --set overrides specified. Nothing to do.")
        sys.exit(1)

    print(f"  Spell ID: {args.spell_id}")
    if args.base is not None:
        print(f"  Base spell: {args.base}")
    print(f"  Overrides: {len(overrides)} column(s)")
    print("  Loading Spell.csv...")
    csv_index = load_spell_csv_index(field_names)
    print(f"  Loaded {len(csv_index)} spells from Spell.csv")

    conn = get_db_connection()
    row, old_values = build_dbc_row(conn, args.spell_id, args.base, overrides, field_names, csv_index)
    conn.close()

    sql = generate_dbc_sql(args.spell_id, row, field_names, args.comment, overrides, old_values)
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


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def add_common_args(p):
    """Add --dry-run, --stdout, --comment to a subparser."""
    p.add_argument("--dry-run", action="store_true", help="Preview without writing files")
    p.add_argument("--stdout", action="store_true", help="Print SQL to stdout instead of writing a file")
    p.add_argument("--comment", default=None, help="Description for the SQL file header")


def main():
    parser = argparse.ArgumentParser(
        description="Alonecraft SQL Generator -- produce idempotent SQL from column overrides",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # dbc subcommand
    p_dbc = subparsers.add_parser("dbc", help="Generate alonecraft_spell_dbc SQL")
    p_dbc.add_argument("--spell-id", type=int, required=True, help="Target spell ID")
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

    args = parser.parse_args()

    print("=" * 60)
    print("  Alonecraft SQL Generator")
    print("=" * 60)

    args.func(args)


if __name__ == "__main__":
    main()
