# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AzerothCore is an open-source MMORPG server emulator for World of Warcraft patch 3.3.5a (Wrath of the Lich King). It's a C++ project built with CMake, using MySQL for data storage. Licensed under GNU GPL v2.

## Build Commands

### Configure and build (out-of-source build required)

- Skip building unless explicitly requested.

```bash
# Create build directory and configure
mkdir -p build && cd build
cmake .. -DCMAKE_INSTALL_PREFIX=$HOME/azeroth-server -DCMAKE_BUILD_TYPE=RelWithDebInfo \
  -DSCRIPTS=static -DMODULES=static

# Build (use appropriate core count)
make -j$(nproc)
make install
```

### Key CMake options

- `SCRIPTS`: none, static, dynamic, minimal-static, minimal-dynamic (default: static)
- `MODULES`: none, static, dynamic (default: static)
- `APPS_BUILD`: none, all, auth-only, world-only (default: all)
- `TOOLS_BUILD`: none, all, db-only, maps-only (default: none)
- `BUILD_TESTING`: Enable unit tests (default: OFF)
- `USE_COREPCH` / `USE_SCRIPTPCH`: Precompiled headers (default: ON)

### Build, deploy, and run (Windows)

```bat
REM Full cycle: stop servers, verify, build C++, build DBC, build UI, copy MPQ, start servers, verify DB
build_and_run.bat

REM Common shortcuts
build_and_run.bat --skip-cmake           # Rebuild C++ without re-running CMake
build_and_run.bat --skip-build           # DBC/SQL changes only (no C++ recompile)
build_and_run.bat --skip-dbc --skip-copy  # C++ changes only (no DBC rebuild)
build_and_run.bat --skip-ui              # Skip Interface UI build step
build_and_run.bat --skip-server           # Build everything but don't start servers
build_and_run.bat --skip-verify          # Skip pre-build and post-start verification
build_and_run.bat --help                 # Show all flags
```

- Build directory: `C:\Build` (VS2022, RelWithDebInfo, x64)
- Server executables: `C:\Build\bin\RelWithDebInfo\`
- WoW client: `C:\Users\Shadow\Desktop\WoW Solo\WoW Solo\Data\`

### Unit tests

```bash
# Configure with testing enabled
cmake .. -DBUILD_TESTING=ON
make -j$(nproc)

# Run tests
./src/test/unit_tests
# or
ctest
```

Tests use Google Test and live in `src/test/`. The test binary links against the `game` library.

## Architecture

### Two server executables
- **authserver** (`src/server/apps/authserver/`): Handles authentication and realm selection (port 3724)
- **worldserver** (`src/server/apps/worldserver/`): Main game server handling all gameplay (port 8085)

### Source layout (`src/`)

- **`src/common/`** - Shared libraries: networking (Asio), cryptography, configuration, logging, threading, collision detection, utilities
- **`src/server/game/`** - Core game logic (~52 subsystems), the heart of the worldserver
- **`src/server/scripts/`** - Content scripts (bosses, spells, commands, instances)
- **`src/server/database/`** - Database abstraction layer and schema updater
- **`src/server/shared/`** - Code shared between auth and world servers (packets, network, realm definitions)
- **`src/test/`** - Unit tests (Google Test)

### Key game subsystems (`src/server/game/`)

- **Entities/** - Core game objects: `Player`, `Creature`, `Unit`, `Item`, `GameObject`
- **Spells/** - Spell mechanics, aura system, spell effects
- **Maps/** - Map management, grid system, instancing
- **Handlers/** - Client packet handlers (one file per system: `MovementHandler.cpp`, `SpellHandler.cpp`, etc.). These are methods on `WorldSession`
- **AI/** - Creature AI framework
- **Scripting/** - Script system with typed base classes (`ScriptObject` subclasses: `CreatureScript`, `SpellScript`, `InstanceMapScript`, `GameObjectScript`, `CommandScript`, etc.)
- **Server/** - `WorldSession` (per-player connection), `World` (global state), opcode definitions

### Scripting system

Scripts follow a registration pattern:
1. Define a class inheriting from `SpellScript`, `CreatureScript`, etc.
2. Implement an `AddSC_*()` function that calls `RegisterSpellScript(ClassName)` (or similar)
3. The `AddSC_*()` is declared and called from the regional `*_script_loader.cpp`
4. Script loaders per region: `spells_script_loader.cpp`, `eastern_kingdoms_script_loader.cpp`, `northrend_script_loader.cpp`, etc.
5. Spell script files are organized by class: `spell_dk.cpp`, `spell_mage.cpp`, `spell_generic.cpp`, etc.

### Three databases
- **acore_auth** - Accounts, realm list, bans (`data/sql/base/db_auth/`)
- **acore_characters** - Character data, inventories, progress (`data/sql/base/db_characters/`)
- **acore_world** - Game content: creatures, items, quests, spells, loot (`data/sql/base/db_world/`)

- SQL updates go in `data/sql/updates/pending_*` with separate subdirectories per database until pull request is merged. Pending SQL files are assigned random names.
- SQL updates go in `data/sql/updates/` with separate subdirectories per database after their pull request is merged.
- SQL files outside the `data/sql/updates/pending_*` folders should never be updated.

### Module system

External modules are loaded from the `modules/` directory. Each module is a subdirectory with its own `CMakeLists.txt`. Disable specific modules with `-DDISABLED_AC_MODULES="mod1;mod2"`. Module skeleton: https://github.com/azerothcore/skeleton-module/

### Dependencies

Bundled in `deps/`: boost, MySQL client, OpenSSL, zlib, recastnavigation (pathfinding), g3dlite (geometry), fmt, argon2, jemalloc, and others.

## Commit Message Format

Uses Conventional Commits:
```
Type(Scope/Subscope): Short description (max 50 chars)
```

- **Types**: feat, fix, refactor, style, docs, test, chore
- **Scopes**: Core (C++ changes), DB (SQL changes)
- **Examples**: `fix(Core/Spells): Fix damage calculation for Fireball`, `fix(DB/SAI): Missing spell to NPC Hogger`

## Code Style

- 4-space indentation for C++ (no tabs)
- 2-space indentation for JSON, YAML, shell scripts
- UTF-8 encoding, LF line endings
- Max 80 character line length
- No braces around single-line statements
- Use {} to parse variables into output instead of %u etc.
- CI enforces code style checks and compiles with `-Werror`

## Logging

### Temporary diagnostics: use `alonecraft.debug`, never `LOG_ERROR`

The old habit was "`LOG_INFO`/`LOG_DEBUG` are filtered out, so use `LOG_ERROR` for
temporary diagnostics." That is how ~21 debug `LOG_ERROR` calls ended up committed in
`MiscHandler.cpp` (firing on *every* gossip click, for every player and every bot) and
`boss_razorscale.cpp`. Debug logging at ERROR is invisible as debt: it looks like a real
error, so nobody removes it.

Instead, use the dedicated category:

```cpp
LOG_DEBUG("alonecraft.debug", "Razorscale: evade reason={}", (int)why);
```

`worldserver.conf` defines `Logger.alonecraft.debug=4,Console Server`, so these appear
without being promoted to ERROR. `tools/verify_scripts.py` lists every
`alonecraft.debug` call site on each build — a visible reminder, not a blocker.

Remove them when the investigation ends. Anything in a per-tick, per-bot, or
per-packet path must be gated by a config option, not left on.

### Log noise is budgeted

`tools/audit_logs.py` buckets log lines by *signature* (the line with ids, names,
numbers and timestamps normalised away), so 1192 repetitions of one problem read as one
row with a count instead of a wall of text.

```bash
python tools/audit_logs.py                 # what did this run log?
python tools/audit_logs.py --check         # regressions vs tools/log_budget.json
python tools/audit_logs.py --baseline      # rewrite the budget from this run
```

`tools/log_budget.json` records the accepted count for each known signature, each with a
written reason. `build_and_run.bat` runs `--check` after startup (step 5.6, skip with
`--skip-audit`). It reports loudly but does not fail the build.

**When you fix a noise source, ratchet its budget down to 0.** That is what stops it
coming back.

### Deployed configs are generated, not hand-edited

The live server configs at `C:\Build\bin\RelWithDebInfo\configs\` are **generated**.
Do not hand-edit them — the next `sync_configs.py --write` overwrites them.

```bash
python tools/sync_configs.py                        # report drift
python tools/sync_configs.py --write                # preview the diff only
python tools/sync_configs.py --write --accept-changes
```

Each deployed `.conf` = its `.conf.dist` template + a small tracked override layer in
`modules/world_of_alonecraft/deploy/configs/`. Only keys where Alonecraft deliberately
differs live in the override files; everything else comes from the template, so new
upstream settings arrive automatically instead of silently falling back to compiled-in
defaults. **To change a setting permanently, edit the override file and re-run
`--write`.**

Secrets and machine-specific values go in `*.overrides.local.conf` next to them, which is
gitignored. Never put an API key in a tracked `.overrides.conf`.

`--write` refuses to act without `--accept-changes` and prints an effective-value diff
first, because adopting template defaults can switch on features that have never run.
`build_and_run.bat` runs the check pre-build (step 1.6, skip with `--skip-config-check`).

Why an override layer rather than a tracked copy of each config: a full copy is a
snapshot that rots the moment a template gains a key. That is precisely how the deployed
tree ended up missing 23 keys in `worldserver.conf`, ~80 in `playerbots.conf` and ~85 in
`mod_llm_chatter.conf` — and mod-llm-chatter reads its config with
`sConfigMgr->GetOption(..., showLogs=false)`, so its drift produced no warning at all.

### Logs are rotated, not truncated

The file appenders run in append mode with flags `7` (timestamp | level | category) so
`audit_logs.py` can attribute lines. `build_and_run.bat` rotates `Server.log`,
`Errors.log`, `Playerbots.log` and `Auth.log` into `logs\archive\` before each start and
keeps the newest 30. Servers are stopped via `tools/stop_server.ps1`, which raises a real
`CTRL_BREAK` so `World::StopNow` runs, flushing logs and saving players — plain
`taskkill` (with or without `/F`) does neither.

## Alonecraft Project

This fork is the **Alonecraft** project — a modification of AzerothCore designed for solo and small group gameplay. Goals include removing casting pushback, adding Diablo-like potions, boosting talents, redesigning class abilities, and retuning encounters for solo progression.

**See [TODO.md](TODO.md) for the complete project state, goals, and progress tracking.**

### Custom module: `modules/world_of_alonecraft/`

All Alonecraft modifications live in this module:
- `src/` — Custom spell scripts and mechanics
- `conf/` — Configuration files
- `data/sql/db-world/` — Database modifications

### Design philosophy: DBC-first, minimal C++

When implementing talent redesigns or new mechanics, prefer this architecture:

1. **Do as much as possible in the DBC/SQL layer.** Use `alonecraft_spell_dbc` overrides to change spell effects, aura types, proc flags, descriptions, and values. Use `spell_proc` entries to control proc behavior (flags, ICD, chance) without C++.
2. **Never modify core files** (`src/server/scripts/`, `src/server/game/`) when a module-only approach exists. All Alonecraft changes should live in `modules/world_of_alonecraft/`.

### Module SQL conventions

- **Naming:** `woa_YYYY_MM_DD_XX.sql` (e.g., `woa_2026_03_29_00.sql`). `XX` is a zero-padded sequence number for multiple files on the same day.
- **Always use the `woa_` prefix on new files.** The updater orders *all* updates — core and module alike — by filename alone, and a single duplicate name aborts the entire world DB update with "Duplicate filename ... occurred". Core `data/sql/updates/db_world/` uses bare `YYYY_MM_DD_XX.sql`, so an unprefixed module file will eventually collide with an upstream file created the same day. (mod-mythic-plus uses `u_mp_` for the same reason.)
- Existing unprefixed files are left as-is: renaming one makes the updater re-apply it, and its old `updates` row is orphaned. That is harmless — orphan cleanup skips `MODULE`-state rows — but only rename when a real collision forces it.
- **Files must be idempotent** — always `DELETE` before `INSERT`:
  ```sql
  DELETE FROM `spell_script_names` WHERE `spell_id` = 12345;
  INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES (12345, 'my_new_script_name');
  ```
- SQL files are auto-applied at server startup and tracked by filename + hash in the `updates` table.
- **Custom spell IDs** use the **200000+** range.
- **Negative spell IDs** in `spell_script_names` apply to all ranks of a spell (e.g., `-5176` matches all ranks of Wrath).

### DBC spell field pitfalls

**Tooltip variables:** Both `$s1` and `$m1` add 1 to BasePoints (CalcValue = BasePoints + max(1, DieSides)). To display a value of N in the tooltip, set BasePoints to **N-1**. There is no tooltip variable that shows raw BasePoints without adding 1.

**SpellClassMask inheritance:** When cloning a spell via `gen_sql.py dbc --base`, ALL fields are copied including SpellClassMask for unused effects. If you add a new effect (e.g., Effect2), explicitly zero out its SpellClassMaskB/C if the base spell had values there, or the mask will silently fail to match target spells.

**The buff bar renders `SpellToolTip`, NOT `SpellDescription`.** This is the single most common cause of "my custom buff has no tooltip" and "my custom buff shows the wrong text":

- `SpellDescription` is what the **spellbook and talent pane** show.
- `SpellToolTip` is what the **buff/debuff bar** shows on hover.

Setting only the description leaves the buff with no hover text at all. Worse, a spell cloned via `--base` inherits the base spell's tooltip verbatim — Wailing Soul (200402), cloned from Nether Protection (54370), showed *"Holy spell damage reduced by $s1%"* on the buff bar while its description was perfectly correct. **When adding or cloning any player-visible aura, set both fields.**

**Aura tooltips DO scale by stack count — prefer `$sN` over hardcoded numbers.** The client multiplies `$sN` in an aura tooltip by that aura's current stack count, so a 1%-per-stack buff at 17 stacks displays "17%" on its own. Blizzard depends on this: Sunder Armor (7386, 5 stacks) is `'Armor decreased by $s1%.'` and Deadly Poison (2818, 5 stacks) is `'Target takes $s1 Nature damage every $t1 seconds.'` — neither says "per stack". There is no current-stack tooltip variable in the DBC (`$u` is *max* stacks) because none is needed.

Corollary: writing a literal "1% per stack" into a `SpellToolTip` is a bug, not a safe fallback — it defeats scaling the client would have done for free.

Use plain text only when the amount is written by C++ at aura-apply time — base points are 0 in those rows, so a variable renders "0%".

Note the split: the **spellbook/talent description** is shown out of context with no stack count to scale against, so a flat "1% per Soul Shard" explanation belongs there. The **tooltip** should use variables.

To audit for this, diff `alonecraft_spell_dbc` against base `Spell.dbc` for rows that apply an aura (`Effect = 6`), are not `PASSIVE` (0x40) or `DO_NOT_DISPLAY` (0x80), and have an empty `SpellToolTip0`.

**Aura MiscValue semantics change per aura type.** When swapping `EffectApplyAuraName`, check the handler — MiscValue may go from unused to load-bearing. `SPELL_AURA_MOD_SPELL_CRIT_CHANCE` (57) ignores MiscValue; `SPELL_AURA_MOD_CRIT_DAMAGE_BONUS` (163) reads it as a **school mask** via `GetTotalAuraModifierByMiscMask` (`Unit.cpp:9421`), so leaving it at 0 means the bonus matches no school and silently applies to nothing. Use 127 for all schools.

**Stack scaling is automatic and unconditional.** `AuraEffect::CalculateAmount` ends with `amount *= GetBase()->GetStackAmount()` (`SpellAuraEffects.cpp:580`) for *every* aura type. Per-stack designs only need the per-stack value in base points.

**Single-column changes to custom spells: use `UPDATE`, not `DELETE` + 234-column `INSERT`.** A full-row re-INSERT silently reverts every other column to whatever the generating tool thought they were, and will clobber a field another SQL file set. Files are applied in filename order, so a later full-row INSERT beats an earlier UPDATE.

### spell_proc pitfalls

**SpellPhaseMask must be non-zero.** A `spell_proc` entry with `SpellPhaseMask = 0` silently never triggers — no error, no warning. Always set it to **2** (`PROC_SPELL_PHASE_HIT`) for standard proc behavior. Reference patterns:
- Positive magic heals: `ProcFlags = 0x4000` (`DONE_SPELL_MAGIC_DMG_CLASS_POS`), `SpellPhaseMask = 2` (e.g., Serendipity -63730)
- Negative magic spells: `ProcFlags = 0x10000` (`DONE_SPELL_MAGIC_DMG_CLASS_NEG`), `SpellPhaseMask = 2` (e.g., Empowered Touch -33879)

**Procs off a *triggered* spell need `AttributesMask = 2`.** `Aura::IsProcTriggeredOnEvent` (`SpellAuras.cpp:2152`) drops any proc whose triggering spell was itself cast as triggered, unless the aura has `SPELL_ATTR3_CAN_PROC_FROM_PROCS` or the `spell_proc` row sets `PROC_ATTR_TRIGGERED_CAN_PROC` (`0x2`). No error is logged — the proc simply never fires.

This bites whenever the "damage" you want to proc from is actually a child spell. Rain of Fire (5740) is `PERIODIC_TRIGGER_SPELL` casting 42223, so Molten Rain matched on family mask and phase and still never fired until `AttributesMask = 2` was added. ~74 core `spell_proc` rows already use this flag.

Diagnostic: if a proc looks correctly configured but never fires, check whether the triggering spell is a real player cast or a triggered child (`EffectTriggerSpell*` on a periodic aura). Note that `SPELL_AURA_PERIODIC_DAMAGE` ticks have **no** `Spell` object, so they skip this check entirely — which is why sibling talents procing off plain DoT ticks (Aftermath) work without the flag.

### SummonProperties.dbc

The binary DBC at `Azerothcore Vanilla Data/dbc/SummonProperties.dbc` has 6 fields: ID, Control (Category), Faction, Title (Type), Slot, Flags. See `docs/wiki/docs/summonproperties_dbc.md` for field documentation.

Key rules:
- **Slot > 0** limits summons to one per slot — additional casts replace the existing summon, not add more.
- Only specific SummonProperties IDs support multi-summon (`numSummons = damage`) — whitelisted in `SpellEffects.cpp:2373`. Use **713** (Bloodworms pattern) for guardian multi-summon with no slot limit.
- **ImplicitTarget matters for summons:** Spells using `TARGET_DEST_DEST` (87) require a pre-set destination via `SpellCastTargets::SetDst()`. Use `TARGET_DEST_CASTER` (18) for self-resolving summon positioning.

### Spell modifier MiscValues (ADD_FLAT/PCT_MODIFIER auras)

The MiscValue field maps to `SpellModOp` in `SpellDefines.h`:

| Value | Enum | What it modifies |
|-------|------|-----------------|
| 0 | SPELLMOD_DAMAGE | Direct damage |
| 1 | SPELLMOD_DURATION | Spell/aura duration |
| 10 | SPELLMOD_CASTING_TIME | Cast time |
| 11 | SPELLMOD_COOLDOWN | Spell cooldown |
| 14 | SPELLMOD_COST | Mana/resource cost |
| 19 | SPELLMOD_ACTIVATION_TIME | **Periodic tick amplitude** |
| 22 | SPELLMOD_DOT | Periodic damage |

To modify a channeled spell's tick rate, use **ADD_FLAT_MODIFIER** (not PCT) with MiscValue=**19** (SPELLMOD_ACTIVATION_TIME). Value is in milliseconds (e.g., -250 to reduce 500ms ticks to 250ms). This is how Missile Barrage (44401) speeds up Arcane Missiles. `ADD_PCT_MODIFIER` does NOT work for SPELLMOD_ACTIVATION_TIME — use FLAT only.

### "Next spell" consumption buffs (ProcCharges pattern)

To create a buff that modifies the next cast of a specific spell and then is consumed, use `ADD_FLAT_MODIFIER` or `ADD_PCT_MODIFIER` (aura 107/108) with:
- **SpellClassMask** targeting the desired spells (e.g., Lightning Bolt, Wrath)
- **SpellFamilyName** matching the class (e.g., 11 = Shaman, 7 = Druid)
- **ProcCharges = 1**

The engine auto-consumes the charge when the modifier matches a cast. No `spell_proc` entry or C++ needed.

**Do NOT use** `SPELL_AURA_MOD_SPELL_CRIT_CHANCE` (aura 57) or other global stat auras for this pattern — they have no SpellClassMask, so the engine never "matches" them against a cast and charges are never consumed.

Reference implementations: Gift of Nature buff (200004), Ancestral Fury (200210).

### Script type capabilities

| Script Type | Damage Handling | Spell Handling | Validation |
|-------------|----------------|----------------|------------|
| **PlayerScript** | No `OnTakeDamage` | `OnPlayerSpellCast` | No `Validate()` |
| **AuraScript** | Proc handling | Aura effects | `Validate()` |
| **SpellScript** | Damage modification | Spell effects | `Validate()` |

## DBC Data

To look up spell data, use `gen_sql.py lookup` which reads the binary Spell.dbc directly (all ~50,000 spells, 234 columns). The canonical column names and format constants live in `modules/world_of_alonecraft/dbc/spell_dbc.py`.

```bash
python tools/gen_sql.py lookup --spell-id <id>        # key fields
python tools/gen_sql.py lookup --spell-id <id> --all   # all 234 columns
python tools/gen_sql.py lookup --name "Fireball"       # search by spell name
python tools/gen_sql.py talent --name "Subversion"     # find talent entry by name
```

> **Do NOT query the `spell_dbc` MySQL table for spell lookups.** That table only contains server-side custom spells not found in the client DBC files — it is a tiny override table, not a comprehensive spell database. The binary Spell.dbc is the authoritative source for all spell data.
>
> **DBC lookups vs. database queries for research:** When investigating spells, talents, or class mechanics, always start with `gen_sql.py lookup`/`talent`/`classmask`/`enum` — these read the binary DBC files which contain the complete, authoritative spell data. The live MySQL database is useful for *verifying* that SQL was applied correctly (script registrations, proc entries, updates table), but is not the right tool for *discovering* spell data or researching mechanics.

### DBC Build Pipeline

Custom/modified spells for the WoW client are managed via the `alonecraft_spell_dbc` MySQL table and built into a patched `Spell.dbc` + `patch-4.mpq` using a Python script.

**Location:** `modules/world_of_alonecraft/dbc/`

```bash
# Build patched Spell.dbc and MPQ (run from the dbc/ directory)
cd modules/world_of_alonecraft/dbc
python build_dbc.py
```

> **Ordering trap:** `build_dbc.py` reads `alonecraft_spell_dbc` from **MySQL**, not from the `.sql` files on disk. But `build_and_run.bat` builds the DBC *before* starting the server, and the server is what auto-applies pending SQL. So a brand-new SQL file will NOT be in the DBC after a single run — the build reads the pre-change table, then the server applies the file afterwards.
>
> Apply the SQL directly first, then build:
> ```bash
> mysql -h 127.0.0.1 -u acore -pacore acore_world < modules/world_of_alonecraft/data/sql/db-world/woa_YYYY_MM_DD_XX.sql
> build_and_run.bat --skip-build --skip-ui
> ```
> The server re-applying it at startup is harmless because module SQL is idempotent. When applying several files by hand, run them in **filename order** — that is the order the updater uses, and a later full-row `INSERT` will overwrite an earlier `UPDATE`.

**Workflow:**
1. Define custom/modified spells as SQL INSERTs into `alonecraft_spell_dbc` (234 columns matching `SPELL_COLUMNS` in `spell_dbc.py`)
2. Run `python build_dbc.py` — reads base `Spell.dbc`, applies SQL overrides, writes patched DBC + MPQ
3. Copy `output/patch-4.mpq` to the WoW client `Data/` folder

**Key files:**
- `modules/world_of_alonecraft/dbc/build_dbc.py` — Main build script
- `modules/world_of_alonecraft/dbc/spell_dbc.py` — Shared DBC constants, column names, read/write utilities
- `modules/world_of_alonecraft/dbc/config.py` — Paths (base DBC, MySQL connection)
- `modules/world_of_alonecraft/dbc/mpqcli.exe` — MPQ packing tool (StormLib-based, gitignored)
- `modules/world_of_alonecraft/data/sql/db-world/2026_03_29_09.sql` — `alonecraft_spell_dbc` table schema

**MPQ packing** uses `mpqcli.exe` (downloaded from [TheGrayDot/mpqcli](https://github.com/TheGrayDot/mpqcli/releases)) placed next to `build_dbc.py`. If `patch-4.mpq` already exists, the script updates `Spell.dbc` in-place (preserving all other DBC files in the patch). Otherwise it creates a fresh MPQ. If mpqcli is missing, the script still writes the patched DBC — you just pack it manually.

**Field types** are derived from `SpellEntryfmt` in `src/server/shared/DataStores/DBCfmt.h`, with SpellDescription and SpellToolTip locale slots corrected from `x` (server-skipped) to `s` (string) for client use. See `SPELL_COLUMNS` in `spell_dbc.py` for column names and ordering.

### Talent.dbc Patching

New talents (not just redesigns of existing ones) require a new entry in Talent.dbc. The build pipeline (`build_dbc.py`) also handles this:

1. Add an INSERT into `talent_dbc` SQL table (23 integer columns: ID, TabID, TierID, ColumnIndex, SpellRank_1-9, PrereqTalent_1-3, PrereqRank_1-3, Flags, RequiredSpellID, CategoryMask_1-2)
2. `build_dbc.py` reads overrides from `talent_dbc` and patches the binary Talent.dbc into the MPQ alongside Spell.dbc
3. Config: `BASE_TALENT_DBC_PATH` in `config.py` points to the base Talent.dbc

**CRITICAL: Talent.dbc record ordering.** The WoW client requires Talent.dbc records to be sorted by **(TabID, TierID, ColumnIndex) ascending** — NOT by talent ID. If a new talent record is appended at the end of the file (e.g., sorted by ID), the client will fail to display the entire talent tree for that class. The build script handles this automatically, but be aware of it if ever manually editing the binary DBC.

**Priest TalentTabIDs:** 201 = Discipline (tabpage 0), 202 = Holy (tabpage 1), 203 = Shadow (tabpage 2).

### SpellShapeshiftForm.dbc Patching

Custom shapeshift forms need correct flags in `SpellShapeshiftForm.dbc`. The build pipeline reads the base DBC, patches form entries, and packs the result into `patch-4.mpq`.

- Config: `BASE_SHAPESHIFT_DBC_PATH` in `config.py` points to `base/SpellShapeshiftForm.dbc`
- Patching is hard-coded in `build_dbc.py` (currently just form 23/Lightform)
- Server-side overrides go in the `spellshapeshiftform_dbc` MySQL table

Key flags (`flags1` field, index 19):
- `SHAPESHIFT_FLAG_STANCE` (0x01) — acts as stance, not full shapeshift (allows normal spell casting)
- `SHAPESHIFT_FLAG_CAN_NPC_INTERACT` (0x08) — can interact with NPCs
- `SHAPESHIFT_FLAG_DONT_AUTO_UNSHIFT` (0x100) — client won't auto-cancel the form on spell cast

**Shadowform** (form 28) uses `flags=0x9` (STANCE + NPC_INTERACT). **Lightform** (form 23) uses `flags=0x109` (STANCE + NPC_INTERACT + DONT_AUTO_UNSHIFT) with server-side C++ logic to cancel on non-Holy spell cast.

### Interface UI Pipeline

Custom WoW client UI modifications (Lua/XML) live in `Interface/` at the repo root and are packed into `patch-4.mpq` alongside DBC files.

**Directory structure:**
```
Interface/
  base/           # 3.3.5a FrameXML + Blizzard AddOns reference (committed, read-only)
  custom/         # Our new/modified UI files (committed, this is what we edit)
    AddOns/       # Custom addon-style UI panels (ALWAYS use this for new UI)
  screenshots/    # Screenshot captures from watcher daemon (gitignored)
  output/         # Build staging area (gitignored)
  build_interface.py   # Packs custom/ files into patch-4.mpq
  watch_screenshots.py # Screenshot watcher daemon
```

**How it works:** Files in `custom/` map to MPQ archive paths — `custom/AddOns/Foo/Foo.lua` becomes `Interface\AddOns\Foo\Foo.lua` in the MPQ. WoW's patch loading overlays files by path.

**CRITICAL: Use AddOns, NEVER modify FrameXML.** The WoW client digitally signs `FrameXML.toc` via `FRAMEXML.TOC.SIG`. If a modified `FrameXML.toc` is packed into the MPQ (even accidentally), the client will crash on login with "Your game interface files are corrupt." This applies to ANY file in `Interface\FrameXML\` that the client signature-checks. Always create new UI as an addon in `custom/AddOns/YourAddon/` with its own `.toc` file — addon TOCs are not signature-checked.

**If the MPQ gets corrupted with FrameXML files:** Delete `patch-4.mpq` from `modules/world_of_alonecraft/dbc/output/`, re-run `build_dbc.py` to create a fresh MPQ, then re-run `build_interface.py` to pack only addon files.

**Creating a new UI addon:**
```
Interface/custom/AddOns/YourAddon/
  YourAddon.toc         # Must have: ## Interface: 30300
  YourAddon.lua         # Lua code
  YourAddon.xml         # XML frame definitions (optional)
```

**Build:** Integrated into `build_and_run.bat` as step 3.5 (after DBC, before copy). Skip with `--skip-ui`. Can also run standalone:
```bash
python Interface/build_interface.py          # pack modified files
python Interface/build_interface.py --dry-run # preview without packing
```

**Screenshot watcher:** Monitors WoW's Screenshots folder, copies new screenshots (resized to max 1920px wide, converted to JPEG) to `Interface/screenshots/` for visual review:
```bash
python Interface/watch_screenshots.py              # interactive (prompts for names)
python Interface/watch_screenshots.py --auto       # auto-name with timestamps
python Interface/watch_screenshots.py --prefix mythic-hud  # auto with prefix
```

**Base reference:** `Interface/base/` contains the vanilla 3.3.5a FrameXML source (from [wowgaming/3.3.5-interface-files](https://github.com/wowgaming/3.3.5-interface-files)). Use this to understand existing frames before modifying them. The base has a flat layout: FrameXML files at root, Blizzard_* addon dirs at root.

## Database Query Reference

**Connection:** `mysql -h 127.0.0.1 -u acore -pacore <database> -e "QUERY"`

| Purpose | Query |
|---------|-------|
| Look up spell by ID | `python tools/gen_sql.py lookup --spell-id <id>` (reads binary Spell.dbc) |
| Look up spell (all columns) | `python tools/gen_sql.py lookup --spell-id <id> --all` |
| Search spells by name | `python tools/gen_sql.py lookup --name "Fireball"` |
| Find talent by name | `python tools/gen_sql.py talent --name "Subversion"` |
| Compute spell family mask | `python tools/gen_sql.py classmask --family 15 --spells 55078,55095` |
| Look up aura/effect enum | `python tools/gen_sql.py enum --aura MOD_PARRY` |
| Verify script registration | `SELECT * FROM spell_script_names WHERE spell_id = <id>` |
| Check all-rank mappings | `SELECT * FROM spell_script_names WHERE spell_id < 0 AND ScriptName LIKE '%name%'` |
| Verify proc config | `SELECT * FROM spell_proc WHERE SpellId = <id>` |
| Confirm SQL was applied | `SELECT name, hash FROM updates WHERE name LIKE '<filename>%'` |

## Development Tools (`tools/`)

### Script Consistency Checker (`tools/verify_scripts.py`)

Cross-references C++ `SpellScriptLoader` names, SQL `spell_script_names` registrations, and `MP_loader.cpp` declarations to catch silent registration mismatches before building.

```bash
python tools/verify_scripts.py        # file-based checks only
python tools/verify_scripts.py --db   # also query live database
```

Catches: scripts with no SQL registration, SQL entries with no C++ code, `AddSC_*` missing from `MP_loader.cpp`, and declaration/call mismatches. Integrated into `build_and_run.bat` as a pre-build step.

### New Script Scaffolder (`tools/new_spell_script.py`)

Generates a C++ spell script, SQL registration file, and `MP_loader.cpp` update from a single command:

```bash
python tools/new_spell_script.py --name spell_example --spell-ids 200100,-12345 --type AuraScript --addsc AddSC_example
python tools/new_spell_script.py --name spell_example --spell-ids 200100 --type SpellScript --dry-run
```

- `--name`: Script name (used in `SpellScriptLoader` and `spell_script_names`)
- `--spell-ids`: Comma-separated spell IDs (negative = all ranks)
- `--type`: `SpellScript` or `AuraScript` (default: `SpellScript`)
- `--addsc`: `AddSC_*` function name (default: `AddSC_<name>`)
- `--dry-run`: Preview output without writing files

### SQL Generator (`tools/gen_sql.py`)

Looks up spell data and generates idempotent SQL files. Reads the binary `Spell.dbc` and `Talent.dbc` directly (the authoritative source for all spell/talent data), layers any existing `alonecraft_spell_dbc` overrides, and outputs results or SQL files.

```bash
# Look up a spell's data (key fields)
python tools/gen_sql.py lookup --spell-id 133
python tools/gen_sql.py lookup --spell-id 133 --all

# Search spells by name (substring match)
python tools/gen_sql.py lookup --name "Fireball"
python tools/gen_sql.py lookup --name "Fireball" --exact --limit 100

# Look up talent entries by spell name (cross-references Talent.dbc + Spell.dbc)
python tools/gen_sql.py talent --name "Subversion"

# Modify a spell's DBC entry (only specify changed columns)
python tools/gen_sql.py dbc --spell-id 33186 --set EffectBasePoints1=50 --set SpellName0="New Name"

# Batch mode: modify multiple spells at once (single DBC load)
python tools/gen_sql.py dbc --spell-ids 48997,49490,49491 --set EffectBasePoints1=5
python tools/gen_sql.py dbc --input changes.csv    # CSV: spell_id,column,value

# Create new custom spell based on an existing one
python tools/gen_sql.py dbc --spell-id 200100 --base 12345 --set SpellName0="Custom Spell"

# Generate spell_proc entry (unspecified columns default to 0)
python tools/gen_sql.py proc --spell-id 200100 --set ProcFlags=65536 --set Chance=100

# Generate spell_script_names entry
python tools/gen_sql.py script --spell-id "200100,-5176" --script-name spell_example

# Compute SpellFamilyFlags mask for a set of spells
python tools/gen_sql.py classmask --family 15 --spells 55078,55095

# Look up aura/effect enum values by name
python tools/gen_sql.py enum --aura MOD_PARRY
python tools/gen_sql.py enum --effect APPLY_AURA

# Decode a wowhead-style talent link string into human-readable talent names
python tools/gen_sql.py talent-link --class priest --link "05032031-235050032302152530000331351"
python tools/gen_sql.py talent-link --class priest --link "05032031-235050032302152530000331351" --all
python tools/gen_sql.py talent-link --class priest --link "05032031-235050032302152530000331351" --source live

# Use --source live on lookup/talent/talent-link to read built DBCs with overrides
python tools/gen_sql.py lookup --spell-id 14750 --source live    # shows "Gnosticism" not "Improved Mana Burn"
python tools/gen_sql.py talent --name "Gnosticism" --source live  # finds renamed talent

# Use symbolic enum names in --set (auto-resolved to integers)
python tools/gen_sql.py dbc --spell-id 200100 --set EffectApplyAuraName1=SPELL_AURA_MOD_PARRY_PERCENT

# Preview or print to stdout
python tools/gen_sql.py dbc --spell-id 33186 --set Effect1=6 --dry-run
python tools/gen_sql.py dbc --spell-id 33186 --set Effect1=6 --stdout
python tools/gen_sql.py dbc --spell-id 33186 --set Effect1=6 --comment "Change to dummy effect"

# Group multiple outputs into one file
python tools/gen_sql.py dbc --spell-id 48997 --set EffectBasePoints1=5 --append-to 2026_03_31_00.sql --group-comment "Subversion rank 1"
python tools/gen_sql.py dbc --spell-id 49490 --set EffectBasePoints1=7 --append-to 2026_03_31_00.sql --group-comment "Subversion rank 2"
```

Subcommands: `lookup` (spell viewer + name search), `talent` (talent lookup by name), `talent-link` (decode wowhead talent link strings), `dbc` (alonecraft_spell_dbc, single or batch), `proc` (spell_proc), `script` (spell_script_names), `classmask` (SpellFamilyFlags computation), `enum` (aura/effect enum lookup). Validates column names with fuzzy "did you mean?" suggestions on typos. Enum names (`SPELL_AURA_*`, `SPELL_EFFECT_*`) are auto-resolved in `--set` arguments.

### Post-Build DB Verifier (`tools/verify_db.py`)

Runs the 4 standard verification queries (spell_dbc, spell_script_names, spell_proc, updates) against the live database. Auto-detects what to check from `git diff` when run with no arguments.

```bash
python tools/verify_db.py                              # auto-detect from git changes
python tools/verify_db.py --spell-ids 200000 200006    # check specific spells
python tools/verify_db.py --scripts spell_bloomstrike   # check specific scripts
python tools/verify_db.py --sql-files 2026_03_29_04.sql # check if SQL was applied
```

Integrated into `build_and_run.bat` as a post-start step (runs after 8s delay for SQL auto-apply).

## Web Talent Calculator (`site/`)

A static talent calculator published to GitHub Pages, showing Alonecraft's
trees rather than retail's. Wowhead cannot render our talents, so the whole
data layer — names, per-rank descriptions, icons — is generated from the same
DBCs that ship to the client.

```bash
python tools/export_talents.py                  # write site/data/*.json
python tools/export_talents.py --validate       # structural assertions, non-zero on failure
python tools/export_talents.py --check          # non-zero if committed data is stale
python tools/export_talents.py --report-tokens  # tooltip token census
python tools/extract_icons.py                   # BLP -> PNG into site/assets/icons/
python tools/extract_icons.py --check           # report missing icons
python -m http.server 8000 --directory site     # preview (file:// will NOT work)
```

**The exported JSON is committed, and CI only publishes it.** This is not
laziness: the post-override DBCs live in `C:\Build\bin\RelWithDebInfo\Data\dbc`,
the override tables live in local MySQL, and the base DBCs are in the
`world_of_alonecraft` **submodule**. GitHub Actions can reach none of them.
`build_and_run.bat` step 3.6 runs the export after the DBC build (skip with
`--skip-talent-export`), so the data tracks the MPQ you just built — but you
still have to **commit `site/data/`**, or the site silently serves stale
talents. `index.json` carries a `generated` timestamp, rendered in the page
footer, so staleness is visible.

`.github/workflows/talent-calculator.yml` is **deliberately not** guarded by
`if: github.repository == 'azerothcore/azerothcore-wotlk'`. Every other
workflow is, so forks don't run upstream CI; this one only makes sense on the
fork, and adding the guard would silently stop all deploys.

### The "modified" badge diffs against retail, not `dbc/base/`

`dbc/base/Spell.dbc` already contains pre-tooling manual edits (the 4.45 era),
so diffing against it under-reports: 89 modified talents versus **177** against
a pristine baseline. The real 3.3.5a DBCs are extracted from the client's
locale MPQ chain into `dbc/base/retail/`. Note `Spell.dbc` comes from
`enUS/patch-enUS-3.MPQ` but `Talent.dbc` from `enUS/patch-enUS-2.MPQ` — the
later patch does not contain one.

### Tooltip variables are resolved at export time

`tools/tooltip_vars.py` turns `"Reduces cast time by $s1 sec"` into real
numbers. It is a pure function, so it can be tested without touching a DBC.
Currently 98.6% of talent descriptions resolve fully.

Traps worth knowing:

- **`$s1`/`$m1` add 1 to BasePoints** (`CalcValue = BasePoints + max(1, DieSides)`),
  and prose shows the **magnitude** — a debuff stores BasePoints −11 and prints
  "10%". But inside a `${...}` expression the **sign is load-bearing**:
  Empowered Frostbolt's `${$m2/-1000}` needs −100 / −1000 to reach 0.1.
- **`${...}` takes a `.N` precision suffix** — `${$m2/-1000}.1` means one decimal.
- **`$<spellid><token><n>`** reads an effect off *another* spell (`$14181s1`),
  and combines with the `$/N;` prefix (`$/10;12536s1`).
- **`$h`, `$h1`** are both ProcChance; the trailing digit is ignored.
- Anything character-dependent (`$AP`, `$SPH`, `$mw`) is **left raw and listed
  in `unresolved[]`**, never stripped. "Increases damage by ." is a silent lie;
  "Increases damage by $AP." is self-diagnosing.
- `$b` is deliberately **not** resolved — its meaning is unconfirmed, and a
  plausible-but-wrong number is worse than a visible token.

### Talent array order is a wire format

Build links are one digit per talent in `(tier, col)` order — the ordering
`_build_talent_tree` (`tools/gen_sql.py:832`) produces, stored as each talent's
`i`. A link made on the site decodes identically via
`gen_sql.py talent-link`. **Change that ordering and every previously shared
link silently decodes to a different build**, which is why `--validate` asserts
`i` equals array position, and why retail's empty talent rows (e.g. 2085) keep
their slot with `"placeholder": true` instead of being dropped.

## Verification Workflow

After making C++ or SQL changes, verify with database queries (or run `python tools/verify_db.py`):
1. **Spell data exists** — run `python tools/gen_sql.py lookup --spell-id <id>` to confirm the spell exists in the binary Spell.dbc
2. **Script registration matches** — `spell_script_names.ScriptName` must exactly match the `SpellScriptLoader` constructor string (mismatch = script silently never runs)
3. **Proc config** (if applicable) — check `spell_proc` flags and trigger conditions
4. **SQL file was applied** — check the `updates` table for your filename

## Local Wiki Reference

A local clone of the [AzerothCore wiki](https://github.com/azerothcore/wiki) is available at `docs/wiki/docs/` for offline reference. This contains 400+ pages covering every database table, system guide, and development reference.

### When to consult the wiki

- **Before writing SQL** that touches a table you haven't worked with before — look up column definitions, types, and allowed values
- **When you see an unfamiliar database column** in existing SQL or C++ code — the wiki documents every column's purpose and valid values
- **When working with spell effects, auras, or proc flags** — the wiki has enum value references
- **When working with SmartAI, conditions, or loot templates** — these systems have complex flag/type enums documented in the wiki

### How to find the right page

Wiki files are in `docs/wiki/docs/`. The naming convention is predictable:

| You need docs for... | Read this file |
|----------------------|----------------|
| A world DB table (e.g., `creature_template`) | `docs/wiki/docs/creature_template.md` |
| A characters DB table (e.g., `characters`) | `docs/wiki/docs/characters.md` |
| An auth DB table (e.g., `account`) | `docs/wiki/docs/account.md` |
| List of all world DB tables | `docs/wiki/docs/database-world.md` |
| List of all characters DB tables | `docs/wiki/docs/database-characters.md` |
| List of all auth DB tables | `docs/wiki/docs/database-auth.md` |
| Spell effect enum values | `docs/wiki/docs/spell-effects-reference.md` |
| SmartAI scripting | `docs/wiki/docs/smart_scripts.md` |
| Conditions system | `docs/wiki/docs/conditions.md` |
| Loot tables (all types) | `docs/wiki/docs/loot_template.md` |
| GM commands | `docs/wiki/docs/gm-commands.md` |

**Rule of thumb:** The filename is the table name + `.md`. If the table is `spell_proc`, the file is `docs/wiki/docs/spell_proc.md`. For non-table topics, try hyphens: `core-installation.md`.

### Setup / Update

```bash
# First-time clone (from repo root)
git clone https://github.com/azerothcore/wiki.git docs/wiki

# Update to latest
cd docs/wiki && git pull
```

If `docs/wiki/` does not exist, the wiki has not been cloned yet — tell the user to run the clone command above.

## Documentation Links (external fallback)

- [AzerothCore Wiki](https://www.azerothcore.org/wiki/home)
- [World Database Tables](https://www.azerothcore.org/wiki/database-world)
- [spell_dbc Table](https://www.azerothcore.org/wiki/spell_dbc) — server-side override table only, not the full spell database
- [spell_script_names Table](https://www.azerothcore.org/wiki/spell_script_names)
- [creature_template Table](https://www.azerothcore.org/wiki/creature_template)

## PR Requirements

- AI tool usage must be disclosed in PRs
- In-game testing expected
- Changes to generic code require regression testing of related systems
