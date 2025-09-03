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

## CRITICAL: Safe Scripting Practices - MANDATORY RULES

**⚠️ THESE RULES ARE NON-NEGOTIABLE - FOLLOW THEM TO PREVENT SEGMENTATION FAULTS ⚠️**

### **NEVER DO - Memory Safety Violations**

#### **❌ NEVER access objects without validation:**
```cpp
// DANGEROUS
Player* player = victim->ToPlayer();
float critChance = player->GetFloatValue(...); // CRASH IF PLAYER IS NULL
```

### **ALWAYS DO - Safe Patterns from Core AzerothCore**

#### **✅ ALWAYS use GetAuraEffect() methods when appropriate:**
```cpp
// SAFE - Core AzerothCore pattern
if (AuraEffect const* aurEff = unit->GetAuraEffect(SPELL_AURA_MANA_SHIELD, SPELLFAMILY_MAGE, 
    flag0, flag1, flag2))
{
    // Safe access to aura data
}

// For ranked spells
if (AuraEffect const* aurEff = unit->GetAuraEffectOfRankedSpell(spellId, effectIndex))
{
    // Safe access
}
```

#### **✅ ALWAYS use AuraScript for spell effects:**
```cpp
// SAFE - Proper AuraScript pattern
class spell_my_effect : public AuraScript
{
    PrepareAuraScript(spell_my_effect);

    bool Validate(SpellInfo const* /*spellInfo*/) override
    {
        return ValidateSpellInfo({ SPELL_ID_1, SPELL_ID_2 }); // MANDATORY
    }

    bool CheckProc(ProcEventInfo& eventInfo)
    {
        // ALWAYS validate event info first
        if (!eventInfo.GetSpellInfo() || !eventInfo.GetActionTarget())
            return false;
        
        return true;
    }

    void HandleProc(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction(); // MANDATORY for custom proc handling
        
        Unit* target = GetTarget();
        if (!target) // ALWAYS validate
            return;
            
        // Your safe logic here
    }

    void Register() override
    {
        DoCheckProc += AuraCheckProcFn(spell_my_effect::CheckProc);
        OnEffectProc += AuraEffectProcFn(spell_my_effect::HandleProc, EFFECT_0, SPELL_AURA_DUMMY);
    }
};
```

#### **✅ ALWAYS validate everything:**
```cpp
// MANDATORY validation pattern
bool Validate(SpellInfo const* /*spellInfo*/) override
{
    return ValidateSpellInfo({ SPELL_ID_1, SPELL_ID_2, SPELL_ID_3 });
}

// MANDATORY null checks
Unit* target = GetTarget();
if (!target)
    return;

Player* player = target->ToPlayer();
if (!player)
    return;
```

#### **✅ ALWAYS use safe PlayerScript patterns:**
```cpp
// SAFE PlayerScript pattern
void OnPlayerSpellCast(Player* player, Spell* spell, bool skipCheck) override
{
    if (!player || !spell) // MANDATORY validation
        return;

    SpellInfo const* spellInfo = spell->GetSpellInfo();
    if (!spellInfo) // MANDATORY validation
        return;

    // Use GetAuraEffectOfRankedSpell for talents
    AuraEffect const* talentAurEff = player->GetAuraEffectOfRankedSpell(TALENT_SPELL_ID, EFFECT_0);
    if (!talentAurEff)
        return;

    // Safe logic here
}
```

### **MANDATORY Script Structure**

#### **Every AuraScript MUST have:**
```cpp
class spell_my_script : public AuraScript
{
    PrepareAuraScript(spell_my_script); // MANDATORY

    bool Validate(SpellInfo const* /*spellInfo*/) override // MANDATORY
    {
        return ValidateSpellInfo({ ALL_SPELL_IDS_USED });
    }

    // If using procs
    bool CheckProc(ProcEventInfo& eventInfo) // MANDATORY for procs
    {
        if (!eventInfo.GetSpellInfo() || !eventInfo.GetActionTarget())
            return false;
        return true;
    }

    void HandleEffect(AuraEffect const* aurEff, ProcEventInfo& eventInfo)
    {
        PreventDefaultAction(); // MANDATORY for custom handling
        
        Unit* target = GetTarget();
        if (!target) // MANDATORY validation
            return;
            
        // Safe implementation
    }

    void Register() override // MANDATORY
    {
        // Register your hooks
    }
};
```

#### **Every SpellScriptLoader MUST have:**
```cpp
class spell_my_script_loader : public SpellScriptLoader
{
public:
    spell_my_script_loader() : SpellScriptLoader("script_name_for_db") { }

    AuraScript* GetAuraScript() const override
    {
        return new spell_my_script();
    }
};
```

### **MANDATORY Testing Checklist**

Before deploying ANY script:

- [ ] **Memory Safety**: No manual aura iteration
- [ ] **Validation**: All objects validated before use
- [ ] **Core Patterns**: Following established AzerothCore patterns
- [ ] **Null Checks**: Every pointer checked before dereferencing
- [ ] **ValidateSpellInfo**: All spell IDs validated
- [ ] **PreventDefaultAction**: Used for custom proc handling
- [ ] **Error Handling**: Graceful failure on invalid data
- [ ] **Performance**: No expensive operations in hot paths

### **Reference Examples - STUDY THESE**

**Safe Core Examples:**
- `src/server/scripts/Spells/spell_mage.cpp` - `spell_mage_fire_frost_ward`
- `src/server/scripts/Spells/spell_mage.cpp` - `spell_mage_molten_armor`
- `src/server/scripts/Spells/spell_generic.cpp` - `spell_gen_profession_research`

**Fixed Custom Examples:**
- `modules/world_of_alonecraft/src/MagicAbsorption.cpp` - Safe AuraScript pattern
- `modules/world_of_alonecraft/src/MagicAttunement.cpp` - Safe PlayerScript pattern

### **Emergency Debugging - If You Get Segfaults**

1. **Check aura iteration** - Replace with `GetAuraEffect()`
2. **Check null validation** - Add null checks everywhere
3. **Check script type** - Use AuraScript for spell effects
4. **Check ValidateSpellInfo** - Validate all spell IDs
5. **Check PreventDefaultAction** - Use for custom procs

**Remember: SAFETY OVER CREATIVITY - Always use proven core patterns**

### **CRITICAL LESSON: Always Verify Method Signatures Before Implementation**

**⚠️ COMPILATION ERROR PREVENTION - MANDATORY VERIFICATION STEPS ⚠️**

#### **What Went Wrong:**
During the Magic Absorption/Attunement script fixes, I made critical assumptions about available methods without verifying the actual class definitions:

1. **Assumed `OnTakeDamage()` existed in PlayerScript** - This method doesn't exist
2. **Used `Validate()` method in PlayerScript** - Only available in SpellScript/AuraScript
3. **Called `ValidateSpellInfo()` in PlayerScript context** - Not available in PlayerScript
4. **Assumed method signatures without checking** - Led to compilation failures

#### **How to Avoid This:**

**ALWAYS DO THESE STEPS BEFORE WRITING SCRIPT CODE:**

1. **Read the actual header file** for the script class you're inheriting from:
   ```cpp
   // ALWAYS check these files first:
   src/server/game/Scripting/ScriptDefines/PlayerScript.h
   src/server/game/Scripting/ScriptDefines/UnitScript.h
   src/server/game/Scripting/ScriptDefines/SpellScript.h
   ```

2. **Verify method signatures exist** before using override:
   ```cpp
   // WRONG - assuming methods exist
   void OnTakeDamage(Player* player, uint32& damage) override // DOESN'T EXIST
   
   // RIGHT - verify in header first, then use correct signature
   void OnDamage(Unit* attacker, Unit* victim, uint32& damage) override // EXISTS IN UnitScript
   ```

3. **Check which methods are available in each script type:**
   - **PlayerScript**: `OnPlayerSpellCast()`, `OnPlayerLogin()`, etc.
   - **UnitScript**: `OnDamage()`, `OnHeal()`, etc.
   - **SpellScript/AuraScript**: `Validate()`, `CheckProc()`, etc.

4. **Use search_files or read_file to verify before coding:**
   ```bash
   # Always verify method existence first
   search_files "OnTakeDamage" in "*.h"  # Check if method exists
   read_file "src/server/game/Scripting/ScriptDefines/PlayerScript.h"  # Read actual definition
   ```

#### **Correct Verification Workflow:**

```cpp
// STEP 1: Verify the script type has the method you need
// Read the header file first!

// STEP 2: Use the correct method signature
class MyScript : public PlayerScript  // Check PlayerScript.h for available methods
{
    // STEP 3: Only use methods that actually exist
    void OnPlayerSpellCast(Player* player, Spell* spell, bool skipCheck) override  // ✅ EXISTS
    // void OnTakeDamage(Player* player, uint32& damage) override  // ❌ DOESN'T EXIST
};
```

#### **Quick Reference - Method Availability:**

| Script Type | Damage Handling | Spell Handling | Validation |
|-------------|----------------|----------------|------------|
| **PlayerScript** | ❌ No `OnTakeDamage` | ✅ `OnPlayerSpellCast` | ❌ No `Validate()` |
| **UnitScript** | ✅ `OnDamage` | ❌ No spell methods | ❌ No `Validate()` |
| **AuraScript** | ✅ Proc handling | ✅ Aura effects | ✅ `Validate()` |
| **SpellScript** | ✅ Damage modification | ✅ Spell effects | ✅ `Validate()` |

**NEVER ASSUME - ALWAYS VERIFY METHOD SIGNATURES IN THE ACTUAL HEADER FILES**

### **CRITICAL LESSON 2: GetAuraEffect() with Invalid Parameters Causes Crashes**

**⚠️ RUNTIME CRASH PREVENTION - DANGEROUS API USAGE ⚠️**

#### **What Went Wrong:**
After fixing compilation errors, the server immediately crashed on player login with ACCESS_VIOLATION in `Unit::GetAuraEffect()`:

```cpp
// DANGEROUS CODE THAT CAUSED CRASH:
return player->GetAuraEffect(static_cast<AuraType>(SPELL_AURA_ANY), SPELLFAMILY_MAGE, 
    SPELL_FAMILY_FLAG_INVOCATION_0, SPELL_FAMILY_FLAG_INVOCATION_1, SPELL_FAMILY_FLAG_INVOCATION_2);
```

**Problem**: `SPELL_AURA_ANY` is not a valid AuraType enum value, causing memory corruption when cast.

#### **How to Avoid This:**

**NEVER use invalid enum values or casts:**
```cpp
// DANGEROUS - Invalid enum cast
static_cast<AuraType>(SPELL_AURA_ANY)  // CAUSES CRASH

// SAFE - Use specific AuraType values or HasAura()
player->HasAura(spellId)  // Simple and safe
```

**ALWAYS use the simplest, safest approach:**
```cpp
// WRONG - Complex GetAuraEffect with family flags
if (player->GetAuraEffect(SPELL_AURA_SOME_TYPE, SPELLFAMILY_MAGE, flag0, flag1, flag2))

// RIGHT - Simple HasAura checks
if (player->HasAura(12051) || player->HasAura(12052))  // Specific spell IDs
```

#### **Safe Aura Checking Patterns:**

```cpp
// ✅ SAFEST - Direct spell ID checking
bool HasEvocation(Player* player)
{
    return player->HasAura(12051) || // Evocation Rank 1
           player->HasAura(12052) || // Evocation Rank 2
           player->HasAura(13043) || // Evocation Rank 3
           player->HasAura(13044);   // Evocation Rank 4
}

// ✅ SAFE - GetAuraEffectOfRankedSpell for talents
AuraEffect const* talentAurEff = player->GetAuraEffectOfRankedSpell(TALENT_SPELL_ID, EFFECT_0);

// ❌ DANGEROUS - Complex GetAuraEffect calls with family flags
player->GetAuraEffect(invalidAuraType, family, flags...)  // CRASH RISK
```

**RULE: When in doubt, use HasAura() with specific spell IDs - it's always safer**

### **CRITICAL LESSON 3: Aura Iteration Still Causes Crashes Even After Fixes**

**⚠️ PERSISTENT CRASH PATTERN - ELIMINATE ALL AURA ITERATION ⚠️**

#### **What Went Wrong:**
Even after fixing the Magic Absorption and Magic Attunement scripts, the ArcaneStability script crashed with the same dangerous aura iteration pattern:

```cpp
// DANGEROUS CODE IN IsArcaneMissilesDamage():
Unit::AuraApplicationMap const& auras = player->GetAppliedAuras();
for (Unit::AuraApplicationMap::const_iterator itr = auras.begin(); itr != auras.end(); ++itr)
{
    if (Aura* aura = itr->second->GetBase()) // NULL DEREFERENCE RISK
    {
        if (IsArcaneMissiles(aura->GetSpellInfo())) // CRASH RISK
            return true;
    }
}
```

**Problem**: This is the EXACT same pattern that caused the original segfaults - manual aura iteration with unsafe pointer dereferencing.

#### **The Pattern That ALWAYS Crashes:**
```cpp
// ❌ NEVER DO THIS - GUARANTEED CRASH EVENTUALLY
Unit::AuraApplicationMap const& auras = unit->GetAppliedAuras();
for (auto const& auraPair : auras) // or any iterator pattern
{
    Aura* aura = auraPair.second->GetBase(); // DANGEROUS
    SpellInfo const* spellInfo = aura->GetSpellInfo(); // CRASH
}
```

#### **Safe Replacement Pattern:**
```cpp
// ✅ ALWAYS DO THIS INSTEAD
bool HasArcaneMissiles(Player* player)
{
    // Direct spell ID checks - simple and safe
    return player->HasAura(5143) ||  // Arcane Missiles R1
           player->HasAura(5144) ||  // Arcane Missiles R2
           player->HasAura(5145) ||  // Arcane Missiles R3
           // ... etc for all ranks
}
```

#### **MANDATORY RULE:**
**NEVER iterate over aura collections manually - ALWAYS use HasAura() with specific spell IDs**

This pattern has now caused crashes in THREE different scripts:
1. Magic Absorption (original)
2. Magic Attunement (original) 
3. Arcane Stability (after fixes)

**ALL aura iteration must be eliminated from custom scripts.**

## Debugging Tips

- Use `LOG_DEBUG("scripts", "Debug message: {}", value);` for logging (not LOG_INFO in production)
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

---

*This guide covers the essential information needed to understand and contribute to the Alonecraft project. For specific implementation questions, refer to the existing codebase examples and AzerothCore documentation.*
