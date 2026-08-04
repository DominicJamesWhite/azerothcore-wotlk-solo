#!/usr/bin/env python3
"""
Alonecraft Post-Build Database Verifier

Runs standard verification queries against the live database to confirm
spell data, script registrations, proc configs, and SQL file application.

Usage:
    python tools/verify_db.py                    # auto-detect from recent git changes
    python tools/verify_db.py --spell-ids 200000 200006
    python tools/verify_db.py --scripts spell_bloomstrike spell_firebreak
    python tools/verify_db.py --sql-files 2026_03_29_04.sql
"""

import argparse
import os
import re
import subprocess
import sys

# Add DBC config to path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc"))

MODULE_SQL = os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "data", "sql", "db-world")


def get_db_connection():
    import config
    import mysql.connector
    return mysql.connector.connect(
        host=config.MYSQL_HOST,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASS,
        database=config.MYSQL_DB,
    )


def auto_detect_from_git():
    """Parse recent git changes to find spell IDs and SQL files."""
    spell_ids = set()
    sql_files = set()
    script_names = set()

    try:
        # Get changed files (staged + unstaged + untracked in module)
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        changed = result.stdout.strip().split("\n") if result.stdout.strip() else []

        result2 = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True, text=True, cwd=REPO_ROOT
        )
        staged = result2.stdout.strip().split("\n") if result2.stdout.strip() else []

        all_changed = set(changed + staged)

        for f in all_changed:
            if f.endswith(".sql") and "world_of_alonecraft" in f:
                sql_files.add(os.path.basename(f))
                # Read the file and extract spell IDs and script names
                full_path = os.path.join(REPO_ROOT, f)
                if os.path.exists(full_path):
                    with open(full_path, "r", encoding="utf-8", errors="replace") as fh:
                        content = fh.read()
                    # Extract numeric spell IDs from VALUES clauses
                    for m in re.finditer(r'\(\s*(-?\d+)\s*,\s*\'', content):
                        spell_ids.add(int(m.group(1)))
                    # Extract script names
                    for m in re.finditer(r"'([a-z_]+)'\s*\)", content):
                        name = m.group(1)
                        if not name.replace(".", "").isdigit():
                            script_names.add(name)

    except Exception as e:
        print(f"  (auto-detect skipped: {e})")

    return spell_ids, script_names, sql_files


# SpellAttr0 bits that silently make an aura invisible.  Getting these wrong
# is indistinguishable in-game from "the script never ran", so they are
# called out explicitly rather than left for the reader to decode.
SPELL_ATTR0_PASSIVE = 0x40
SPELL_ATTR0_DO_NOT_DISPLAY = 0x80


def verify_spell_data(conn, spell_ids):
    """Check that spells exist in alonecraft_spell_dbc (or core spell_dbc)."""
    if not spell_ids:
        return

    cursor = conn.cursor()
    positive_ids = [sid for sid in spell_ids if sid > 0]

    if not positive_ids:
        return

    print("-" * 60)
    print("  Spell Data (alonecraft_spell_dbc)")
    print("-" * 60)

    placeholders = ",".join(["%s"] * len(positive_ids))

    # alonecraft_spell_dbc is the module's source of truth: build_dbc.py bakes
    # it into the Spell.dbc the worldserver loads.  The core `spell_dbc` table
    # is a small override table that never holds 200000+ custom spells, so
    # checking it alone reports every custom spell as missing.
    cursor.execute(
        f"SELECT ID, SpellName0, Attributes, StackAmount, Effect1, "
        f"EffectBasePoints1, EffectApplyAuraName1 "
        f"FROM alonecraft_spell_dbc WHERE ID IN ({placeholders})",
        positive_ids,
    )
    rows = cursor.fetchall()
    found_ids = set()

    for sid, name, attrs, stacks, effect1, base1, aura1 in rows:
        found_ids.add(sid)
        stack_note = f" stacks={stacks}" if stacks else ""
        print(
            f"  [{sid}] {name}  Effect1={effect1} Base1={base1} "
            f"Aura1={aura1} Attributes={attrs}{stack_note}"
        )

        hidden = []
        if attrs & SPELL_ATTR0_PASSIVE:
            hidden.append("PASSIVE (0x40) -- never sent to the client at all")
        if attrs & SPELL_ATTR0_DO_NOT_DISPLAY:
            hidden.append("DO_NOT_DISPLAY (0x80) -- client hides it in the buff bar")
        for reason in hidden:
            print(f"        ! hidden aura: {reason}")

    missing = set(positive_ids) - found_ids
    if missing:
        # Fall back to the core table: a modified stock spell may legitimately
        # live there instead.
        # Note the different column naming: the core table is generated from
        # the DBC field names (Effect_1, Name_Lang_enUS), not the flattened
        # names alonecraft_spell_dbc uses.
        placeholders = ",".join(["%s"] * len(missing))
        cursor.execute(
            f"SELECT ID, Name_Lang_enUS, Effect_1, EffectBasePoints_1, EffectAura_1 "
            f"FROM spell_dbc WHERE ID IN ({placeholders})",
            sorted(missing),
        )
        for sid, name, effect1, base1, aura1 in cursor.fetchall():
            found_ids.add(sid)
            print(
                f"  [{sid}] {name}  Effect1={effect1} Base1={base1} "
                f"Aura1={aura1}   (core spell_dbc)"
            )

        for sid in sorted(set(positive_ids) - found_ids):
            print(
                f"  [{sid}] NOT FOUND in alonecraft_spell_dbc or spell_dbc "
                f"-- if this is a stock spell, look it up with "
                f"`gen_sql.py lookup --spell-id {sid} --source live` instead"
            )
    elif rows:
        print(f"  All {len(rows)} spell(s) found.")

    print()
    cursor.close()


def verify_script_registrations(conn, script_names):
    """Check spell_script_names entries."""
    if not script_names:
        return

    cursor = conn.cursor()

    print("-" * 60)
    print("  Script Registrations (spell_script_names)")
    print("-" * 60)

    for name in sorted(script_names):
        cursor.execute(
            "SELECT spell_id, ScriptName FROM spell_script_names WHERE ScriptName = %s",
            (name,),
        )
        rows = cursor.fetchall()
        if rows:
            ids = ", ".join(str(r[0]) for r in rows)
            print(f"  '{name}' -> spell IDs: [{ids}]")
        else:
            print(f"  '{name}' -> NOT REGISTERED (no rows in spell_script_names)")

    print()
    cursor.close()


def verify_proc_config(conn, spell_ids):
    """Check spell_proc entries for relevant spell IDs."""
    if not spell_ids:
        return

    cursor = conn.cursor()
    positive_ids = [sid for sid in spell_ids if sid > 0]

    if not positive_ids:
        return

    print("-" * 60)
    print("  Proc Configuration (spell_proc)")
    print("-" * 60)

    placeholders = ",".join(["%s"] * len(positive_ids))
    cursor.execute(
        f"SELECT SpellId, SchoolMask, SpellFamilyName, ProcFlags, SpellTypeMask, "
        f"Cooldown FROM spell_proc WHERE SpellId IN ({placeholders})",
        positive_ids,
    )
    rows = cursor.fetchall()

    if rows:
        for row in rows:
            print(
                f"  [{row[0]}] Flags={row[3]} TypeMask={row[4]} "
                f"Cooldown={row[5]} School={row[1]} Family={row[2]}"
            )
    else:
        print("  No proc entries found (this may be expected for non-proc spells).")

    # Also check negative (all-rank) entries
    cursor.execute(
        f"SELECT SpellId, ProcFlags, SpellTypeMask, Cooldown "
        f"FROM spell_proc WHERE SpellId < 0"
    )
    neg_rows = cursor.fetchall()
    if neg_rows:
        # Only show ones relevant to our spell IDs (we can't easily match, so show all custom)
        shown = False
        for row in neg_rows:
            neg_id = abs(row[0])
            if neg_id in positive_ids or neg_id < 100000:
                if not shown:
                    print("  All-rank proc entries:")
                    shown = True
                print(f"    [{row[0]}] Flags={row[1]} TypeMask={row[2]} Cooldown={row[3]}")

    print()
    cursor.close()


def verify_sql_applied(conn, sql_files):
    """Check if SQL files were applied (in updates table)."""
    if not sql_files:
        return

    cursor = conn.cursor()

    print("-" * 60)
    print("  SQL File Application (updates table)")
    print("-" * 60)

    for filename in sorted(sql_files):
        name_prefix = filename.replace(".sql", "")
        cursor.execute(
            "SELECT name, hash FROM updates WHERE name LIKE %s",
            (f"%{name_prefix}%",),
        )
        rows = cursor.fetchall()
        if rows:
            for row in rows:
                print(f"  {row[0]} [hash: {row[1][:12]}...]")
        else:
            print(f"  {filename} -> NOT FOUND in updates table (not yet applied?)")

    print()
    cursor.close()


def main():
    parser = argparse.ArgumentParser(description="Alonecraft Post-Build Database Verifier")
    parser.add_argument("--spell-ids", nargs="*", type=int, help="Spell IDs to check")
    parser.add_argument("--scripts", nargs="*", help="Script names to check")
    parser.add_argument("--sql-files", nargs="*", help="SQL filenames to verify applied")
    args = parser.parse_args()

    print()
    print("=" * 60)
    print("  Alonecraft Post-Build Database Verifier")
    print("=" * 60)
    print()

    # Determine what to check
    spell_ids = set(args.spell_ids) if args.spell_ids else set()
    script_names = set(args.scripts) if args.scripts else set()
    sql_files = set(args.sql_files) if args.sql_files else set()

    # Auto-detect if no arguments given
    if not spell_ids and not script_names and not sql_files:
        print("  Auto-detecting from git changes...")
        spell_ids, script_names, sql_files = auto_detect_from_git()
        if not spell_ids and not script_names and not sql_files:
            print("  No recent changes detected. Use --spell-ids, --scripts, or --sql-files.")
            print()
            return 0
        print(f"  Found: {len(spell_ids)} spell ID(s), {len(script_names)} script(s), {len(sql_files)} SQL file(s)")
        print()

    try:
        conn = get_db_connection()
    except Exception as e:
        print(f"  ERROR: Cannot connect to database: {e}")
        print("  Is the worldserver running? Check modules/world_of_alonecraft/dbc/config.py")
        return 1

    try:
        verify_spell_data(conn, spell_ids)
        verify_script_registrations(conn, script_names)
        verify_proc_config(conn, spell_ids)
        verify_sql_applied(conn, sql_files)
    finally:
        conn.close()

    print("=" * 60)
    print("  Verification complete.")
    print("=" * 60)
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
