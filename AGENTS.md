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

Key files to study:
- `spell_mage.cpp` - Comprehensive mage spell implementations
- `spell_druid.cpp` - Druid spell mechanics
- `spell_priest.cpp` - Priest healing and damage spells
- `spell_generic.cpp` - Cross-class spell effects

### Example Script Structure

Study the structure in `src/server/scripts/Spells/spell_mage.cpp` - look at classes like:
- `spell_mage_arcane_blast` - Basic SpellScript implementation
- `spell_mage_molten_armor` - AuraScript with proc checking
- `spell_mage_ice_barrier` - Spell validation and effect calculation

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

1. **Create your script file** in `modules/world_of_alonecraft/src/`
2. **Follow naming convention**: `YourFeatureName.cpp`
3. **Follow header patterns** from existing files like `MoltenArmor.cpp` or `AegisOfAntonidas.cpp`
4. **Register your scripts** following the pattern in `MoltenArmor.cpp` (see `AddSC_molten_armor_mechanic()`)

### Example Custom Implementation

See `modules/world_of_alonecraft/src/MoltenArmor.cpp` for a complete example of:
- Damage interception using `UnitScript`
- Aura management and stacking
- Player event handling with `PlayerScript`
- Custom DoT mechanics with `AuraScript`

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
- **Health/Power Management**: `modules/world_of_alonecraft/src/MoltenArmor.cpp` - `AddOrUpdateEmberScars` method
- **Aura Management**: `src/server/scripts/Spells/spell_mage.cpp` - `spell_mage_focus_magic::HandleProc`
- **Damage Dealing**: `modules/world_of_alonecraft/src/MoltenArmor.cpp` - `Unit::DealDamage` usage in `OnPeriodicTick`
- **Spell Casting**: `src/server/scripts/Spells/spell_mage.cpp` - `spell_mage_burnout::HandleProc`
- **State Checks**: `modules/world_of_alonecraft/src/MoltenArmor.cpp` - `HasAura` checks throughout

### Player.h - Player-Specific Operations

**Location:** `src/server/game/Entities/Player/Player.h`

**Key Methods:**

See Player-specific implementations in:
- **Player Casting**: `modules/world_of_alonecraft/src/MoltenArmor.cpp` - `OnPlayerSpellCast` method
- **Player State Checks**: `modules/world_of_alonecraft/src/MoltenArmor.cpp` - `ToPlayer()` conversions and validation
- **Spell Cooldowns**: `modules/world_of_alonecraft/src/MoltenArmor.cpp` - `AddSpellCooldown` usage

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

When a new script requires changes to the database (e.g., adding a `spell_script_names` entry), provide the SQL query directly. Do not create `.sql` files. This allows for manual review and application of database changes.

Example Query:
```sql
DELETE FROM `spell_script_names` WHERE `spell_id` = 12345;
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES (12345, 'my_new_script_name');
```

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

### 3. Intercepting Damage (Like Molten Armor)

**Reference Implementation:** `modules/world_of_alonecraft/src/MoltenArmor.cpp`
- See `spell_molten_armor_damage_handler::OnDamage` for damage interception
- See `AddOrUpdateEmberScars` for complex damage storage and DoT mechanics
- See `spell_ember_scars_AuraScript::OnPeriodicTick` for periodic damage application

### 4. Player Event Handling

**Reference Implementation:** `modules/world_of_alonecraft/src/MoltenArmor.cpp`
- See `spell_molten_armor_spell_cast_handler::OnPlayerSpellCast` for spell cast interception
- See `IsFireSpell` method for spell school checking
- See `RemoveEmberScarsStack` for player-triggered aura modifications

## Development Workflow

1. **Study existing implementations** in `src/server/scripts/Spells/`
2. **Examine custom examples** in `modules/world_of_alonecraft/src/`
3. **Create your script** following the established patterns
4. **Test thoroughly** with different scenarios
5. **Document your changes** in the appropriate files

#### **Quick Reference - Method Availability:**

| Script Type | Damage Handling | Spell Handling | Validation |
|-------------|----------------|----------------|------------|
| **PlayerScript** | ❌ No `OnTakeDamage` | ✅ `OnPlayerSpellCast` | ❌ No `Validate()` |
| **UnitScript** | ✅ `OnDamage` | ❌ No spell methods | ❌ No `Validate()` |
| **AuraScript** | ✅ Proc handling | ✅ Aura effects | ✅ `Validate()` |
| **SpellScript** | ✅ Damage modification | ✅ Spell effects | ✅ `Validate()` |


## Debugging Tips

- Use `LOG_ERROR("scripts", "Debug message: {}", value);` for logging (not LOG_INFO in production)
- Check spell IDs in the database or DBC files
- ALWAYS validate spell info exists before using it
- Test edge cases like spell immunity, line of sight, and range
- Consider performance impact of frequently called hooks
- Use Valgrind or similar tools to detect memory issues
- Test with multiple players and combat scenarios

## Additional Resources

- **AzerothCore Documentation:** https://www.azerothcore.org/wiki/
- **Spell DBC Reference:** Use database tools to find spell IDs and effects
- **WoW Dev Wiki:** Historical reference for spell mechanics
- **Module Examples:** Study other AzerothCore modules for patterns

### MySQL MCP Server

A MySQL Model Context Protocol (MCP) server has been connected, providing direct access to the project's database. This can be incredibly useful for:
- **Schema Inspection:** Quickly listing databases, tables, and describing table schemas without needing to open a separate database client.
- **Data Exploration:** Executing read-only SQL queries to understand existing data, verify changes, or debug issues.

**Available Tools:**
- `list_databases`: List all accessible databases.
- `list_tables`: List all tables in a specified database.
- `describe_table`: Show the schema for a specific table.
- `execute_query`: Execute read-only SQL queries (SELECT, SHOW, DESCRIBE, EXPLAIN).

---

*This guide covers the essential information needed to understand and contribute to the Alonecraft project. For specific implementation questions, refer to the existing codebase examples and AzerothCore documentation.*
