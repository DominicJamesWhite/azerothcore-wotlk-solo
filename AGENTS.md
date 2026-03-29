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
3. **Create your script** following the established patterns
4. **Test thoroughly** with different scenarios
5. **Document your changes** in the appropriate files

#### **Quick Reference - Method Availability:**

| Script Type | Damage Handling | Spell Handling | Validation |
|-------------|----------------|----------------|------------|
| **PlayerScript** | ❌ No `OnTakeDamage` | ✅ `OnPlayerSpellCast` | ❌ No `Validate()` |
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

*This guide covers the essential information needed to understand and contribute to the Alonecraft project. For specific implementation questions, refer to the existing codebase examples and AzerothCore documentation.*
