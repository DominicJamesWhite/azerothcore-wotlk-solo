#!/usr/bin/env python3
"""
Alonecraft Script Consistency Checker

Cross-references C++ SpellScriptLoader names, SQL spell_script_names registrations,
and MP_loader.cpp declarations to catch silent registration mismatches.

Usage:
    python tools/verify_scripts.py            # file-based checks only
    python tools/verify_scripts.py --db       # also query live database
"""

import argparse
import glob
import os
import re
import sys

# Paths relative to repo root
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODULE_SRC = os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "src")
MODULE_SQL = os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "data", "sql", "db-world")
LOADER_FILE = os.path.join(MODULE_SRC, "MP_loader.cpp")

# Scripts implemented in core (src/server/scripts/) but registered via module SQL.
# These are intentional cross-boundary registrations — not typos.
CORE_SCRIPT_WHITELIST = {
    "spell_mage_burning_determination",
    "spell_dk_death_strike",  # restored core script, 2026_04_01_00.sql
}

# Temporary diagnostics: LOG_*("alonecraft.debug", ...). Listing them on every
# build is the point — debug logging that nobody is reminded about is how ~21
# LOG_ERROR calls ended up committed in MiscHandler.cpp and boss_razorscale.cpp
# and then fired for every player on every gossip click.
DEBUG_LOG_CATEGORY = "alonecraft.debug"
DEBUG_LOG_RE = re.compile(r'LOG_(?:TRACE|DEBUG|INFO|WARN|ERROR|FATAL)\(\s*"alonecraft\.debug"')

# Directories scanned for stray diagnostics. Core is included deliberately: that
# is where the debt landed last time.
DEBUG_SCAN_DIRS = [
    os.path.join(REPO_ROOT, "src", "server"),
    os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "src"),
]


def find_debug_log_sites():
    """Return [(relpath, lineno, stripped_line)] for every alonecraft.debug call."""
    sites = []
    for root_dir in DEBUG_SCAN_DIRS:
        if not os.path.isdir(root_dir):
            continue
        for dirpath, _dirnames, filenames in os.walk(root_dir):
            for fn in filenames:
                if not fn.endswith((".cpp", ".h")):
                    continue
                path = os.path.join(dirpath, fn)
                try:
                    with open(path, "r", encoding="utf-8", errors="replace") as fh:
                        for lineno, line in enumerate(fh, 1):
                            if DEBUG_LOG_RE.search(line):
                                rel = os.path.relpath(path, REPO_ROOT)
                                sites.append((rel, lineno, line.strip()[:110]))
                except OSError:
                    continue
    return sites


def extract_cpp_script_names(src_dir):
    """Extract script names from all .cpp files (excluding MP_loader.cpp).

    Detects both the older SpellScriptLoader("name") pattern and the newer
    RegisterSpellScript(ClassName) pattern (where class name = script name).
    """
    names = {}  # script_name -> [file_path, ...]
    loader_pattern = re.compile(r'SpellScriptLoader\("([^"]+)"\)')
    register_pattern = re.compile(r'RegisterSpellScript\((\w+)\)\s*;')

    for cpp_file in glob.glob(os.path.join(src_dir, "*.cpp")):
        if os.path.basename(cpp_file) == "MP_loader.cpp":
            continue
        with open(cpp_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        for pattern in [loader_pattern, register_pattern]:
            for match in pattern.finditer(content):
                name = match.group(1)
                names.setdefault(name, []).append(os.path.basename(cpp_file))

    return names


def extract_cpp_addsc_definitions(src_dir):
    """Extract AddSC_* function definitions from .cpp files (excluding MP_loader.cpp)."""
    funcs = {}  # func_name -> file_path
    pattern = re.compile(r'^void\s+(AddSC_\w+)\s*\(\s*\)', re.MULTILINE)

    for cpp_file in glob.glob(os.path.join(src_dir, "*.cpp")):
        if os.path.basename(cpp_file) == "MP_loader.cpp":
            continue
        with open(cpp_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()
        for match in pattern.finditer(content):
            func_name = match.group(1)
            funcs[func_name] = os.path.basename(cpp_file)

    return funcs


def extract_loader_declarations(loader_path):
    """Extract forward declarations from MP_loader.cpp."""
    decls = set()
    pattern = re.compile(r'^void\s+(AddSC_\w+|AddMyPlayerScripts)\s*\(\s*\)\s*;', re.MULTILINE)

    with open(loader_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    for match in pattern.finditer(content):
        decls.add(match.group(1))

    return decls


def extract_loader_calls(loader_path):
    """Extract AddSC_* calls from inside Addworld_of_alonecraftScripts()."""
    calls = set()
    pattern = re.compile(r'^\s+(AddSC_\w+|AddMyPlayerScripts)\s*\(\s*\)\s*;', re.MULTILINE)

    with open(loader_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    # Find the function body
    func_start = content.find("Addworld_of_alonecraftScripts()")
    if func_start == -1:
        print("WARNING: Could not find Addworld_of_alonecraftScripts() in MP_loader.cpp")
        return calls

    func_body = content[func_start:]
    for match in pattern.finditer(func_body):
        calls.add(match.group(1))

    return calls


def extract_sql_script_names(sql_dir):
    """Extract net ScriptName registrations across all SQL files (processed in order).

    Tracks both INSERTs and DELETEs to compute the final set of registered names.
    A name that is INSERTed in an early file but DELETEd (without re-INSERT) in a
    later file is NOT included in the result.
    """
    # Process files in chronological order
    sql_files = sorted(glob.glob(os.path.join(sql_dir, "*.sql")))

    insert_pattern = re.compile(
        r"INSERT\s+INTO\s+`?spell_script_names`?", re.IGNORECASE
    )
    value_pattern = re.compile(r"'([^']+)'\s*\)")

    # Track per-name: which files inserted it, and whether a later delete removed it
    # We process all files, tracking inserts and standalone deletes
    net_names = {}  # script_name -> [sql_file, ...]

    for sql_file in sql_files:
        with open(sql_file, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        basename = os.path.basename(sql_file)

        # First pass: find DELETE-only script names in this file
        # (DELETEs that are followed by INSERT of the same name in the same file
        # are just idempotent patterns and don't count as removals)
        file_inserts = set()
        file_deletes = set()

        # Collect inserts
        in_insert = False
        for line in content.split("\n"):
            if insert_pattern.search(line):
                in_insert = True
            if in_insert:
                for m in value_pattern.finditer(line):
                    name = m.group(1)
                    if not name.replace(".", "").isdigit():
                        file_inserts.add(name)
                if ";" in line:
                    in_insert = False

        # Collect deletes (by ScriptName)
        # Match: DELETE FROM spell_script_names WHERE ScriptName = 'xxx'
        delete_by_name = re.compile(
            r"DELETE\s+FROM\s+`?spell_script_names`?\s+WHERE\s+.*?`?ScriptName`?\s*=\s*'([^']+)'",
            re.IGNORECASE
        )
        for m in delete_by_name.finditer(content):
            name = m.group(1)
            if not name.replace(".", "").isdigit():
                file_deletes.add(name)

        # Match: DELETE FROM spell_script_names WHERE ... ScriptName IN ('a', 'b')
        # This is how a script is retired in favour of a renamed one, e.g.
        # 2026_04_02_12.sql (magic_attunement ranks -> _proc) and
        # woa_2026_08_04_07.sql (sacrifice_of_blood -> health_funnel_mana_feed).
        # DOTALL because both wrap the AND onto a second line.
        delete_by_name_list = re.compile(
            r"DELETE\s+FROM\s+`?spell_script_names`?\s+WHERE\s+.*?`?ScriptName`?\s+IN\s*\(([^)]*)\)",
            re.IGNORECASE | re.DOTALL
        )
        for m in delete_by_name_list.finditer(content):
            for name in re.findall(r"'([^']+)'", m.group(1)):
                if not name.replace(".", "").isdigit():
                    file_deletes.add(name)

        # Also catch deletes in IN-list format (spell_id, ScriptName) tuples
        # These appear as DELETE WHERE (spell_id, ScriptName) IN ((..., 'name'), ...)
        # For these, the name is already in the tuple and will be re-inserted if idempotent
        delete_tuple = re.compile(
            r"DELETE\s+FROM\s+`?spell_script_names`?\s+WHERE\s+\(`?spell_id`?\s*,\s*`?ScriptName`?\)\s+IN\s*\(",
            re.IGNORECASE
        )
        if delete_tuple.search(content):
            # Extract names from the DELETE tuple list
            for m in value_pattern.finditer(content.split("INSERT")[0] if "INSERT" in content else content):
                name = m.group(1)
                if not name.replace(".", "").isdigit():
                    file_deletes.add(name)

        # Net removals: deleted in this file but not re-inserted
        net_removals = file_deletes - file_inserts
        for name in net_removals:
            net_names.pop(name, None)

        # Add inserts
        for name in file_inserts:
            net_names.setdefault(name, []).append(basename)

    return net_names


def query_live_db():
    """Query live database for registered script names."""
    try:
        sys.path.insert(0, os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc"))
        import config
        import mysql.connector

        conn = mysql.connector.connect(
            host=config.MYSQL_HOST,
            user=config.MYSQL_USER,
            password=config.MYSQL_PASS,
            database=config.MYSQL_DB,
        )
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT ScriptName FROM spell_script_names ORDER BY ScriptName")
        names = {row[0] for row in cursor.fetchall()}
        cursor.close()
        conn.close()
        return names
    except Exception as e:
        print(f"WARNING: Could not query live database: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(description="Alonecraft Script Consistency Checker")
    parser.add_argument("--db", action="store_true", help="Also check against live database")
    args = parser.parse_args()

    issues = []
    warnings = []

    # Gather data from all sources
    cpp_script_names = extract_cpp_script_names(MODULE_SRC)
    cpp_addsc_defs = extract_cpp_addsc_definitions(MODULE_SRC)
    loader_decls = extract_loader_declarations(LOADER_FILE)
    loader_calls = extract_loader_calls(LOADER_FILE)
    sql_script_names = extract_sql_script_names(MODULE_SQL)

    print("=" * 60)
    print("  Alonecraft Script Consistency Checker")
    print("=" * 60)
    print()
    print(f"  C++ ScriptLoader names:  {len(cpp_script_names)}")
    print(f"  C++ AddSC_* definitions: {len(cpp_addsc_defs)}")
    print(f"  MP_loader declarations:  {len(loader_decls)}")
    print(f"  MP_loader calls:         {len(loader_calls)}")
    print(f"  SQL script_names:        {len(sql_script_names)}")
    print()

    # Check 1: C++ script names without SQL registration
    for name, files in sorted(cpp_script_names.items()):
        if name not in sql_script_names:
            issues.append(
                f"[C++ -> SQL] Script '{name}' in {', '.join(files)} "
                f"has no SQL registration -- script will compile but never fire"
            )

    # Check 2: SQL script names without C++ implementation
    for name, files in sorted(sql_script_names.items()):
        if name not in cpp_script_names:
            if name in CORE_SCRIPT_WHITELIST:
                continue  # Intentionally uses a core-provided script
            warnings.append(
                f"[SQL -> C++] Script '{name}' registered in {', '.join(files)} "
                f"has no SpellScriptLoader in module src/ -- may be a core script or typo"
            )

    # Check 3: AddSC_* defined in .cpp but missing from MP_loader.cpp
    for func, file in sorted(cpp_addsc_defs.items()):
        if func not in loader_decls:
            issues.append(
                f"[C++ -> Loader] {func}() defined in {file} "
                f"but not declared in MP_loader.cpp -- script will never load"
            )
        elif func not in loader_calls:
            issues.append(
                f"[C++ -> Loader] {func}() declared but not called "
                f"in MP_loader.cpp -- script will never load"
            )

    # Check 4: MP_loader references without C++ definition
    for func in sorted(loader_calls):
        if func not in cpp_addsc_defs and func != "AddMyPlayerScripts":
            issues.append(
                f"[Loader -> C++] {func}() called in MP_loader.cpp "
                f"but not defined in any .cpp file -- will cause linker error"
            )

    # Check 5: Declarations without calls (and vice versa)
    for func in sorted(loader_decls - loader_calls):
        if func not in cpp_addsc_defs:
            continue  # already caught above
        warnings.append(
            f"[Loader] {func}() declared but never called in MP_loader.cpp"
        )

    for func in sorted(loader_calls - loader_decls):
        issues.append(
            f"[Loader] {func}() called but not declared in MP_loader.cpp"
        )

    # Check 6: Live database (optional)
    if args.db:
        db_names = query_live_db()
        if db_names is not None:
            print(f"  Live DB script_names:    {len(db_names)}")
            print()

            for name in sorted(cpp_script_names.keys()):
                if name not in db_names:
                    warnings.append(
                        f"[C++ -> DB] Script '{name}' not found in live database "
                        f"-- SQL may not have been applied yet"
                    )

    # Check 7: temporary diagnostics still in the tree
    debug_sites = find_debug_log_sites()
    if debug_sites:
        print("-" * 60)
        print(f"  TEMPORARY DIAGNOSTICS ({len(debug_sites)}) -- '{DEBUG_LOG_CATEGORY}'")
        print("-" * 60)
        for rel, lineno, text in debug_sites:
            print(f"  * {rel}:{lineno}")
            print(f"      {text}")
        print()
        print("  Remove these once the investigation is done. They are listed, not")
        print("  blocked, so debugging is never gated on cleaning up first.")
        print()

    # Report results
    if issues:
        print("-" * 60)
        print(f"  ISSUES ({len(issues)}) -- these will cause problems:")
        print("-" * 60)
        for issue in issues:
            print(f"  ! {issue}")
        print()

    if warnings:
        print("-" * 60)
        print(f"  WARNINGS ({len(warnings)}) -- worth checking:")
        print("-" * 60)
        for warning in warnings:
            print(f"  ? {warning}")
        print()

    if not issues and not warnings:
        print("-" * 60)
        print("  ALL CHECKS PASSED -- no mismatches found")
        print("-" * 60)
        print()
        return 0

    total = len(issues) + len(warnings)
    print("=" * 60)
    print(f"  Summary: {len(issues)} issue(s), {len(warnings)} warning(s)")
    print("=" * 60)

    return 1 if issues else 0


if __name__ == "__main__":
    sys.exit(main())
