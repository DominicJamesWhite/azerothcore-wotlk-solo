# AzerothCore Alonecraft Project - Agent Guide

This guide provides coding agents and colleagues with essential information to understand and contribute to the Alonecraft project - a modification of AzerothCore designed to enhance solo and small group gameplay.

## Project Overview

**See [TODO.md](TODO.md) for the complete project state, goals, and progress tracking.**

Alonecraft aims to make World of Warcraft better for solo play and small groups by:
- Removing casting pushback from enemy damage
- Adding Diablo-like potions for all classes
- Boosting talents for more impactful leveling
- Redesigning class abilities to address holy trinity weaknesses
- Retuning encounters for solo progression

## Understanding Default Spell Scripts

To understand how AzerothCore handles spell mechanics, examine the default spell scripts in:

**`src/server/scripts/Spells/`**

Example files to study:
- `spell_mage.cpp` - Comprehensive mage spell implementations
- `spell_druid.cpp` - Druid spell mechanics
- `spell_priest.cpp` - Priest healing and damage spells
- `spell_generic.cpp` - Cross-class spell effects

## Custom Script Development

### Working Directory: `modules/world_of_alonecraft/`

This module contains all custom Alonecraft modifications:

**Directory Structure:**
```
modules/world_of_alonecraft/
├── src/                    # Custom spell scripts and mechanics
├── conf/                   # Configuration files
├── data/sql/              # Database modifications
└── README.md              # Module documentation
```

### Building Custom Scripts

Use the scaffolder to generate all required files automatically:

```bash
python tools/new_spell_script.py --name spell_example --spell-ids 200100 --type SpellScript --addsc AddSC_example
```

This creates the C++ file, SQL registration, and updates `MP_loader.cpp` in one step. See `--dry-run` to preview. For manual creation:

1. **Create your script file** in `modules/world_of_alonecraft/src/`
2. **Follow naming convention**: `YourFeatureName.cpp`
3. **Follow header patterns**
4. **Register your scripts**

## Key API References

### SpellScript.h - Core Spell Scripting

**Location:** `src/server/game/Spells/SpellScript.h`

**Key Classes:**
- `SpellScript` - For spell cast handling
- `AuraScript` - For persistent aura effects
- `SpellScriptLoader` - For registering scripts

**Common Hooks:**

See practical implementations in:
- `src/server/scripts/Spells/spell_mage.cpp` - `spell_mage_burnout::HandleProc` for aura proc handling
- `src/server/scripts/Spells/spell_mage.cpp` - `spell_mage_ice_barrier::CalculateAmount` for effect calculation
- `modules/world_of_alonecraft/src/MoltenArmor.cpp` - `spell_ember_scars_AuraScript::OnPeriodicTick` for periodic effects

### Unit.h - Unit Manipulation

**Location:** `src/server/game/Entities/Unit/Unit.h`

**Key Methods for Custom Scripts:**

See usage examples in:
- **Aura Management**: `src/server/scripts/Spells/spell_mage.cpp` - `spell_mage_focus_magic::HandleProc`
- **Spell Casting**: `src/server/scripts/Spells/spell_mage.cpp` - `spell_mage_burnout::HandleProc`

### Player.h - Player-Specific Operations

**Location:** `src/server/game/Entities/Player/Player.h`

### SpellAuraEffects.h - Aura Effect Types

**Location:** `src/server/game/Spells/SpellAuraEffects.h`

**Common Aura Types:**
- `SPELL_AURA_MOD_DAMAGE_DONE` - Modify damage output
- `SPELL_AURA_MOD_HEALING_DONE` - Modify healing output  
- `SPELL_AURA_MOD_STAT` - Modify character stats
- `SPELL_AURA_PERIODIC_DAMAGE` - Damage over time
- `SPELL_AURA_PERIODIC_HEAL` - Healing over time
- `SPELL_AURA_MOD_SPEED` - Movement speed changes

### 5. Database Changes

When a new script requires database changes (e.g., adding a `spell_script_names` entry), **create a SQL file** in:

```
modules/world_of_alonecraft/data/sql/db-world/
```

**Naming convention:** `YYYY_MM_DD_XX.sql` (e.g. `2026_03_29_00.sql`). The `XX` is a zero-padded sequence number for multiple files on the same day.

**Files must be idempotent** — always `DELETE` before `INSERT` so the file is safe to re-apply:

```sql
DELETE FROM `spell_script_names` WHERE `spell_id` = 12345;
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES (12345, 'my_new_script_name');
```

These files are auto-applied at server startup and tracked by filename + hash in the `updates` table. Do **not** apply SQL manually without also committing the corresponding file.

**Custom spell IDs** for Alonecraft use the 200000+ range (e.g., 200035 for Magic Absorption Absorb R1).

**Negative spell IDs** in `spell_script_names` apply to all ranks of a spell (e.g., `-5176` would match all ranks of Wrath). Use this when a script should handle every rank.

## Common Problem Solutions

### 1. Modifying Spell Damage/Healing

**Reference Implementation:** `src/server/scripts/Spells/spell_mage.cpp`
- See `spell_mage_ignite::HandleProc` for damage calculation and modification
- See `spell_mage_ice_barrier_aura::CalculateAmount` for spell power scaling

### 2. Creating Proc Effects

**Reference Implementation:** `src/server/scripts/Spells/spell_mage.cpp`
- See `spell_mage_molten_armor::CheckProc` for proc condition checking
- See `spell_mage_burnout::HandleProc` for proc effect execution
- See `spell_mage_master_of_elements::HandleProc` for complex proc logic

### 3. Player Event Handling

**Reference Implementation:** `modules/world_of_alonecraft/src/MoltenArmor.cpp`
- See `spell_molten_armor_spell_cast_handler::OnPlayerSpellCast` for spell cast interception
- See `IsFireSpell` method for spell school checking
- See `RemoveEmberScarsStack` for player-triggered aura modifications

## Development Workflow

1. **Study existing implementations** in `src/server/scripts/Spells/`
2. **Examine custom examples** in `modules/world_of_alonecraft/src/`
3. **Scaffold your script** using `python tools/new_spell_script.py` (or create manually)
4. **Verify consistency** with `python tools/verify_scripts.py`
5. **Build and deploy** using `build_and_run.bat` (see below)
6. **Test thoroughly** with different scenarios
7. **Verify database** with `python tools/verify_db.py` (or check build_and_run.bat output)

### Development Tools (`tools/`)

| Tool | Purpose | When to use |
|------|---------|-------------|
| `tools/gen_sql.py` | Spell/talent lookup, DBC research, SQL generation | **First stop for all spell/talent research** -- reads binary DBC files |
| `tools/verify_scripts.py` | Cross-references C++ ScriptLoader names, SQL registrations, and MP_loader.cpp | Before building -- catches silent registration mismatches |
| `tools/new_spell_script.py` | Scaffolds C++ file + SQL file + MP_loader.cpp update | When creating a new spell script |
| `tools/verify_db.py` | Queries live DB to confirm spells, registrations, procs, SQL applied | After server starts -- replaces manual SQL queries |

#### gen_sql.py — Research & SQL Generation

This is the primary tool for **discovering** spell data and generating SQL. It reads the binary Spell.dbc and Talent.dbc files directly — these contain the complete, authoritative spell data (all ~50,000 spells). **Always use gen_sql.py for research; only use live database queries for verification.**

```bash
# Research: look up spell data
python tools/gen_sql.py lookup --spell-id 133          # by ID (key fields)
python tools/gen_sql.py lookup --spell-id 133 --all    # by ID (all 234 columns)
python tools/gen_sql.py lookup --name "Fireball"       # search by name (substring)

# Research: find talent entries
python tools/gen_sql.py talent --name "Subversion"     # talent name -> IDs, tree position, ranks

# Research: compute spell family masks
python tools/gen_sql.py classmask --family 15 --spells 55078,55095  # AND/OR masks for DK diseases

# Research: look up aura/effect enum values
python tools/gen_sql.py enum --aura MOD_PARRY          # SPELL_AURA_MOD_PARRY_PERCENT = 47
python tools/gen_sql.py enum --effect APPLY_AURA       # SPELL_EFFECT_APPLY_AURA = 6

# Generate: single spell DBC override
python tools/gen_sql.py dbc --spell-id 33186 --set EffectBasePoints1=50

# Generate: batch DBC overrides (single DBC load, one output file)
python tools/gen_sql.py dbc --spell-ids 48997,49490,49491 --set EffectBasePoints1=5
python tools/gen_sql.py dbc --input changes.csv        # CSV: spell_id,column,value

# Generate: use symbolic enum names (auto-resolved)
python tools/gen_sql.py dbc --spell-id 200100 --set EffectApplyAuraName1=SPELL_AURA_MOD_PARRY_PERCENT

# Generate: group outputs into one file
python tools/gen_sql.py dbc --spell-id 48997 --set EffectBasePoints1=5 --append-to 2026_03_31_00.sql --group-comment "Subversion R1"

# Generate: spell_proc and spell_script_names
python tools/gen_sql.py proc --spell-id 200100 --set ProcFlags=65536 --set Chance=100
python tools/gen_sql.py script --spell-id "200100,-5176" --script-name spell_example
```

> **DBC tools vs. database queries:** The binary DBC files (Spell.dbc, Talent.dbc) are the authoritative source for spell/talent data. The live MySQL database only contains server-side *overrides* and *registrations* — it is not a comprehensive spell database. Use `gen_sql.py` subcommands (`lookup`, `talent`, `classmask`, `enum`) for research and discovery. Use database queries (`verify_db.py` or direct MySQL) only to verify that your SQL changes were applied correctly after a server restart.

#### Other tools

```bash
# Check for registration mismatches (also runs as pre-build step in build_and_run.bat)
python tools/verify_scripts.py
python tools/verify_scripts.py --db     # also check live database

# Scaffold a new script (generates all 3 files)
python tools/new_spell_script.py --name spell_example --spell-ids 200100,-5176 --type AuraScript
python tools/new_spell_script.py --name spell_example --spell-ids 200100 --dry-run

# Verify database state (also runs as post-start step in build_and_run.bat)
python tools/verify_db.py                             # auto-detect from git changes
python tools/verify_db.py --spell-ids 200000 200006   # check specific spells
python tools/verify_db.py --scripts spell_bloomstrike  # check specific scripts
```

### Build & Run Script

`build_and_run.bat` in the repo root automates the full build-test cycle:

```bat
build_and_run.bat                        # Full cycle (with verification)
build_and_run.bat --skip-build           # DBC/SQL changes only (no C++ recompile)
build_and_run.bat --skip-dbc --skip-copy # C++ changes only (no DBC rebuild)
build_and_run.bat --skip-server          # Build everything but don't start servers
build_and_run.bat --skip-verify          # Skip pre-build and post-start verification
build_and_run.bat --help                 # Show all flags
```

**What it does (in order):**
1. Stops `authserver.exe` and `worldserver.exe` if running
1.5. Runs `verify_scripts.py` to check for registration mismatches (prompts to continue if issues found)
2. Builds C++ via MSBuild (VS2022, RelWithDebInfo, x64) from `C:\Build\AzerothCore.sln`
3. Runs `build_dbc.py` to generate patched `Spell.dbc` + `patch-4.mpq`
4. Copies `patch-4.mpq` to the WoW client `Data/` folder
5. Launches authserver and worldserver in separate windows
5.5. Runs `verify_db.py` to confirm database state after SQL auto-apply

#### **Quick Reference - Method Availability:**

| Script Type | Damage Handling | Spell Handling | Validation |
|-------------|----------------|----------------|------------|
| **PlayerScript** | ❌ No `OnTakeDamage` | ✅ `OnPlayerSpellCast` | ❌ No `Validate()` |
| **AuraScript** | ✅ Proc handling | ✅ Aura effects | ✅ `Validate()` |
| **SpellScript** | ✅ Damage modification | ✅ Spell effects | ✅ `Validate()` |


## Verification Workflow

After making C++ or SQL changes, verify everything is wired up correctly. The fastest path is the automated tools:

```bash
python tools/verify_scripts.py    # pre-build: catch C++/SQL/loader mismatches
python tools/verify_db.py         # post-start: confirm DB state (auto-detects from git)
```

For manual verification or debugging specific issues:

### 1. Verify spell data exists
```bash
python tools/gen_sql.py lookup --spell-id <your_spell_id>
```
Confirm the spell ID exists in the binary Spell.dbc and the effect/aura types match your script's expectations. Do NOT query the `spell_dbc` MySQL table — it only contains server-side override spells, not the full spell database.

### 2. Verify spell_script_names mapping
```bash
mysql -h 127.0.0.1 -u acore -pacore acore_world -e "SELECT * FROM spell_script_names WHERE spell_id = <your_spell_id>"
```
The `ScriptName` column must exactly match the string passed to the `SpellScriptLoader` constructor in your C++ code. A mismatch means the script silently never runs.

### 3. Verify spell_proc (if applicable)
```bash
mysql -h 127.0.0.1 -u acore -pacore acore_world -e "SELECT * FROM spell_proc WHERE SpellId = <your_spell_id>"
```
If your script uses proc hooks (`OnProc`, `CheckProc`, `HandleProc`), verify the proc flags and trigger conditions are correct.

### 4. Verify SQL file was applied
```bash
mysql -h 127.0.0.1 -u acore -pacore acore_world -e "SELECT name, hash FROM updates WHERE name LIKE '<your_sql_filename>%'"
```
If the file does not appear, the server has not processed it yet (restart required).

### 5. Cross-reference with documentation
Use the wiki links in the Documentation Links section below to confirm field meanings, especially for `EffectAura`, `Effect`, and `ProcFlags` columns which use enum values.


## DBC Data

To look up spell data, use `gen_sql.py` which reads the binary Spell.dbc and Talent.dbc directly (all ~50,000 spells, 234 columns; ~900 talents). The canonical column names and format constants live in `modules/world_of_alonecraft/dbc/spell_dbc.py`.

```bash
python tools/gen_sql.py lookup --spell-id <id>        # key fields
python tools/gen_sql.py lookup --spell-id <id> --all   # all 234 columns
python tools/gen_sql.py lookup --name "Fireball"       # search by name
python tools/gen_sql.py talent --name "Subversion"     # talent name -> spell IDs
python tools/gen_sql.py classmask --family 15 --spells 55078,55095  # spell family masks
python tools/gen_sql.py enum --aura MOD_PARRY          # aura/effect enum values
```

> **Do NOT query the `spell_dbc` MySQL table for spell lookups.** That table only contains server-side custom spells not found in the client DBC files — it is a tiny override table, not a comprehensive spell database. The binary Spell.dbc is the authoritative source for all spell data.
>
> **DBC tools first, database queries second.** For discovering and researching spell/talent data, always use `gen_sql.py` subcommands (`lookup`, `talent`, `classmask`, `enum`) which read the complete binary DBC files. The live MySQL database is only useful for *verifying* that SQL changes were applied correctly (script registrations, proc entries, updates table) — not for research.

### DBC Build Pipeline

Client-side spell modifications (new spells, changed names/descriptions/effects visible to the client) require patching the `Spell.dbc` file. This is automated via a Python build script.

**Location:** `modules/world_of_alonecraft/dbc/`

**How it works:**
1. The `alonecraft_spell_dbc` MySQL table holds custom/modified spell definitions (all 234 DBC columns)
2. `build_dbc.py` reads the base `Spell.dbc`, applies overrides from the table, and writes a patched DBC + `patch-4.mpq`
3. The MPQ goes into the WoW client `Data/` folder

**Adding a new client-side spell (200000+ range):**
1. Find a similar spell using `python tools/gen_sql.py lookup --spell-id <id>` or using `gen_sql.py dbc --base`
2. Write SQL: `DELETE FROM alonecraft_spell_dbc WHERE ID = <id>; INSERT INTO alonecraft_spell_dbc (...) VALUES (...);`
3. Save as `modules/world_of_alonecraft/data/sql/db-world/YYYY_MM_DD_XX.sql`
4. Also add server-side entries (`spell_script_names`, `spell_proc`) as needed
5. Run: `cd modules/world_of_alonecraft/dbc && python build_dbc.py`

**Modifying an existing spell for the client:**
1. Use `gen_sql.py dbc --spell-id <id> --set ...` to look up and modify spell values (reads binary Spell.dbc)
2. INSERT the full row into `alonecraft_spell_dbc` with your modifications
3. The build script replaces the base DBC record with your version

**MPQ packing:** The script uses `mpqcli.exe` (placed next to `build_dbc.py`, gitignored). If `patch-4.mpq` already exists, it updates `Spell.dbc` in-place (preserving all other DBC files). Otherwise it creates a fresh MPQ. Download from [TheGrayDot/mpqcli releases](https://github.com/TheGrayDot/mpqcli/releases) if missing. The script still writes the patched DBC even if mpqcli is unavailable.

**Configuration:** Edit `modules/world_of_alonecraft/dbc/config.py` for base DBC path and MySQL connection.

**Column reference:** The 234 columns are defined in `SPELL_COLUMNS` in `modules/world_of_alonecraft/dbc/spell_dbc.py`. Field types (int/float/string) are derived from `SpellEntryfmt` in `src/server/shared/DataStores/DBCfmt.h`.

### Talent.dbc Patching

Adding a brand new talent (not just redesigning an existing one) requires a new Talent.dbc entry. The build pipeline handles this alongside Spell.dbc:

1. INSERT into `talent_dbc` SQL table (23 integer columns: ID, TabID, TierID, ColumnIndex, SpellRank_1-9, PrereqTalent_1-3, PrereqRank_1-3, Flags, RequiredSpellID, CategoryMask_1-2)
2. `build_dbc.py` reads overrides from `talent_dbc`, patches the binary Talent.dbc, and packs it into the MPQ
3. Config: `BASE_TALENT_DBC_PATH` in `config.py`

**CRITICAL: Talent.dbc record ordering.** The WoW client requires Talent.dbc records sorted by **(TabID, TierID, ColumnIndex) ascending** — NOT by talent ID. If a new talent is appended at the end (sorted by ID), the client will fail to render the entire talent tree for that class. The build script handles this automatically.

**Priest TalentTabIDs:** 201 = Discipline, 202 = Holy, 203 = Shadow.

**Buff tooltip field:** When creating buff spells (visible in the player's buff bar), set `SpellToolTip0` — not just `SpellDescription0`. The description shows in the spellbook/talent tree, but the tooltip shows when hovering over the buff icon in-game.

## Debugging Tips

- Use `LOG_ERROR("scripts", "Debug message: {}", value);` for logging (not LOG_INFO in production)
- Check spell IDs with `python tools/gen_sql.py lookup --spell-id <id>` (reads binary Spell.dbc)
- Search by name with `python tools/gen_sql.py lookup --name "spell name"` or `talent --name "talent name"`
- Look up aura/effect enums with `python tools/gen_sql.py enum --aura MOD_PARRY`
- Compute spell family masks with `python tools/gen_sql.py classmask --family <N> --spells <ids>`
- ALWAYS validate spell info exists before using it
- Test edge cases like spell immunity, line of sight, and range
- Consider performance impact of frequently called hooks
- Use Valgrind or similar tools to detect memory issues
- Test with multiple players and combat scenarios
- Use `gen_sql.py` for spell/talent research (DBC tools first), database queries only for verification — see "Database Query Reference" above

## Database Query Reference

### Research (DBC tools -- use these first)

For discovering and researching spell/talent data, always use `gen_sql.py` which reads the complete binary DBC files. These are faster, more comprehensive, and don't require the server to be running.

| Purpose | Command |
|---------|---------|
| Look up spell by ID | `python tools/gen_sql.py lookup --spell-id 200035` |
| Look up spell (all columns) | `python tools/gen_sql.py lookup --spell-id 200035 --all` |
| Search spells by name | `python tools/gen_sql.py lookup --name "Fireball"` |
| Find talent by name | `python tools/gen_sql.py talent --name "Subversion"` |
| Compute spell family mask | `python tools/gen_sql.py classmask --family 15 --spells 55078,55095` |
| Look up aura/effect enum | `python tools/gen_sql.py enum --aura MOD_PARRY` |

### Verification (live database -- use after server restart)

The live MySQL database is for *verifying* that SQL changes were applied correctly. It is NOT a comprehensive spell database.

**Connection:** `mysql -h 127.0.0.1 -u acore -pacore <database> -e "QUERY"`

| Purpose | Query |
|---------|-------|
| Verify script registration | `SELECT * FROM spell_script_names WHERE spell_id = 200035` |
| Check all-rank mappings | `SELECT * FROM spell_script_names WHERE spell_id < 0 AND ScriptName LIKE '%ice_lance%'` |
| Verify proc config | `SELECT * FROM spell_proc WHERE SpellId = 200035` |
| Confirm SQL was applied | `SELECT name, hash FROM updates WHERE name LIKE '2026_03_29%'` |

**Notes:**
- Custom Alonecraft spell IDs use the **200000+** range
- **Negative** `spell_id` values in `spell_script_names` apply to all ranks of a spell
- Always query `acore_world` for spell and script data

## Local Wiki Reference

The AzerothCore wiki is cloned locally at `docs/wiki/docs/` (400+ pages). Use it to look up database table schemas and column documentation:

- **Table docs:** `docs/wiki/docs/<table_name>.md` (e.g., `spell_dbc.md`, `creature_template.md`, `spell_proc.md`)
- **DB indexes:** `database-world.md`, `database-characters.md`, `database-auth.md`
- **SmartAI/Conditions:** `smart_scripts.md`, `conditions.md`
- **Loot tables:** `loot_template.md`

Consult the wiki when writing SQL for unfamiliar tables or when you need to know valid column values/types. If `docs/wiki/` doesn't exist, clone it: `git clone https://github.com/azerothcore/wiki.git docs/wiki`

## Documentation Links (external fallback)

- **[AzerothCore Wiki — Home](https://www.azerothcore.org/wiki/home)** — Main documentation index
- **[World Database Tables](https://www.azerothcore.org/wiki/database-world)** — Reference for 200+ world DB tables
- **[spell_dbc Table](https://www.azerothcore.org/wiki/spell_dbc)** — Server-side override table only (use `gen_sql.py lookup` to read all spells from binary Spell.dbc)
- **[spell_script_names Table](https://www.azerothcore.org/wiki/spell_script_names)** — How C++ scripts bind to spell IDs
- **[creature_template Table](https://www.azerothcore.org/wiki/creature_template)** — NPC/creature definitions
- **Module Examples:** Study other AzerothCore modules in `modules/` for patterns
