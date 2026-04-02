# Shaman Talent Changes - Implementation Plan

## Context

Implementing 13 shaman talent changes from TODO.md for the Alonecraft project (skipping Nature's Guardian and Healing Way; no spec themes). All changes live in `modules/world_of_alonecraft/`, no core modifications.

**Shaman Talent Tab IDs:** 261 = Elemental, 262 = Restoration, 263 = Enhancement  
**Custom spell ID range:** 200209–200221 (200208 is the current highest)

---

## Reference Data

### SpellFamilyName
- SPELLFAMILY_SHAMAN = 11

### SpellClassMask (OR) for Shaman Spell Groups
| Group | Mask0 | Mask1 | Mask2 | Spells |
|-------|-------|-------|-------|--------|
| Healing (HW+LHW+CH) | 448 | 0 | 0 | HW=0x40, LHW=0x80, CH=0x100 |
| Damage (LB+CL+LavaBurst) | 3 | 4096 | 0 | LB=0x01, CL=0x02, LavaBurst=0x1000 in Mask1 |
| Shocks (Earth+Flame+Frost) | 2416967680 | 0 | 0 | Earth=0x100000, Flame=0x10000000, Frost=0x80000000 |
| Riptide | 0 | 0 | 16 | SpellFamilyFlags2=0x10 |
| Water Shield | 0 | 32 | 0 | SpellFamilyFlags1=0x20 |
| Earth Shield | 0 | 1024 | 0 | SpellFamilyFlags1=0x400 |
| Lightning Shield | 0 | 16 | 0 | SpellFamilyFlags1=0x10 |

### Key Aura Enum Values
| Aura | ID | Notes |
|------|----|-------|
| SPELL_AURA_DUMMY | 4 | Generic proc hook for C++ |
| SPELL_AURA_MOD_THREAT | 10 | Threat modification |
| SPELL_AURA_MOD_DAMAGE_DONE | 13 | +damage (MiscValue = school mask) |
| SPELL_AURA_MOD_PARRY_PERCENT | 47 | Flat parry % |
| SPELL_AURA_MOD_SPELL_CRIT_CHANCE | 57 | Flat spell crit % |
| SPELL_AURA_MOD_SPELL_CRIT_CHANCE_SCHOOL | 71 | School-specific spell crit (MiscValue = school mask) |
| SPELL_AURA_ADD_FLAT_MODIFIER | 107 | Flat spell modifier (MiscValue = SpellModOp) |
| SPELL_AURA_ADD_PCT_MODIFIER | 108 | % spell modifier (MiscValue = SpellModOp) |
| SPELL_AURA_MOD_SPELL_HEALING_OF_STAT_PERCENT | 175 | Healing from stat % |
| SPELL_AURA_MOD_INCREASES_SPELL_PCT_TO_HIT | 199 | Spell hit % |
| SPELL_AURA_PROC_TRIGGER_SPELL | 42 | Proc trigger |

### Key SpellModOp Values (for ADD_FLAT/PCT_MODIFIER MiscValue)
| Value | Enum | Purpose |
|-------|------|---------|
| 0 | SPELLMOD_DAMAGE | Direct damage/healing amount |
| 2 | SPELLMOD_EFFECT2 | Threat (in original Healing Grace) |
| 9 | SPELLMOD_NOT_LOSE_CASTING_TIME | Pushback resist |
| 10 | SPELLMOD_CASTING_TIME | Cast time (ms) |
| 14 | SPELLMOD_COST | Mana cost |
| 28 | (school mask) | Used for school-specific threat |

### DBC Duration Indices
| Index | Duration |
|-------|----------|
| 0 | 0 (permanent/passive) |
| 1 | 10 seconds |
| 3 | 60 seconds |
| 18 | 20 seconds |
| 21 | 15 seconds (infinite) |
| 27 | 3 seconds |
| 28 | 6 seconds |
| 85 | 15 seconds |

### Common Attributes for Passive Talents
- `Attributes = 464` — standard passive talent (SPELL_ATTR0_PASSIVE | SPELL_ATTR0_HIDDEN_CLIENTSIDE | SPELL_ATTR0_ABILITY)
- `ProcChance = 101` — always (for passive auras)

### Common ProcFlags
| Value | Meaning |
|-------|---------|
| 4 | PROC_FLAG_DONE_MELEE_AUTO_ATTACK |
| 16 | PROC_FLAG_TAKEN_MELEE_AUTO_ATTACK |
| 16384 | PROC_FLAG_DONE_SPELL_MAGIC_DMG_CLASS_POS (healing spells) |
| 65536 | PROC_FLAG_DONE_SPELL_MAGIC_DMG_CLASS_NEG (damage spells) |
| 262144 | PROC_FLAG_DONE_PERIODIC |
| 524288 | PROC_FLAG_TAKEN_PERIODIC |
| 327680 | Combined: DONE_SPELL_MAGIC_DMG_CLASS_NEG | DONE_PERIODIC |

---

## Tier 1: DBC-Only Changes

### 1. Elemental Precision (talent 1685, Elemental tree tier 5)

**Current state (3 ranks):**
| Spell | Effect1 | Effect2 |
|-------|---------|---------|
| 30672 (R1) | Aura199 (spell hit), BP=0 (+1%), MiscValue=28 | Aura10 (threat), BP=-11 (-10%), MiscValue=28 |
| 30673 (R2) | Aura199, BP=1 (+2%), MiscValue=28 | Aura10, BP=-21 (-20%), MiscValue=28 |
| 30674 (R3) | Aura199, BP=2 (+3%), MiscValue=28 | Aura10, BP=-31 (-30%), MiscValue=28 |

**Change:** Replace Effect2 (threat reduction) with spell crit.

**gen_sql.py commands:**
```bash
python tools/gen_sql.py dbc --spell-id 30672 --set EffectApplyAuraName2=SPELL_AURA_MOD_SPELL_CRIT_CHANCE --set EffectBasePoints2=0 --set EffectMiscValue2=0 --set "SpellDescription0=Increases your chance to hit with Fire, Frost and Nature spells by \$s1% and increases your spell critical strike chance by \$s2%." --append-to 2026_04_01_00.sql --group-comment "Elemental Precision R1 - replace threat with crit"

python tools/gen_sql.py dbc --spell-id 30673 --set EffectApplyAuraName2=SPELL_AURA_MOD_SPELL_CRIT_CHANCE --set EffectBasePoints2=1 --set EffectMiscValue2=0 --set "SpellDescription0=Increases your chance to hit with Fire, Frost and Nature spells by \$s1% and increases your spell critical strike chance by \$s2%." --append-to 2026_04_01_00.sql --group-comment "Elemental Precision R2"

python tools/gen_sql.py dbc --spell-id 30674 --set EffectApplyAuraName2=SPELL_AURA_MOD_SPELL_CRIT_CHANCE --set EffectBasePoints2=2 --set EffectMiscValue2=0 --set "SpellDescription0=Increases your chance to hit with Fire, Frost and Nature spells by \$s1% and increases your spell critical strike chance by \$s2%." --append-to 2026_04_01_00.sql --group-comment "Elemental Precision R3"
```

### 2. Healing Grace (talent 1646, Resto tree tier 1)

**Current state (3 ranks):**
| Spell | Effect1 (threat reduction) | Effect2 (dispel resist) |
|-------|---------|---------|
| 29187 (R1) | Aura108 (ADD_PCT_MODIFIER), BP=-6, MiscValue=2, ClassMaskA=448/B=268438528 | Aura107 (ADD_FLAT_MODIFIER), BP=9, MiscValue=28, ClassMaskA2=524288/B2=67636452 |
| 29189 (R2) | Aura108, BP=-11 | Aura107, BP=19 |
| 29191 (R3) | Aura108, BP=-16 | Aura107, BP=29 |

**Change:** Replace both effects with spell crit chance for healing spells (+2/4/6%).

**gen_sql.py commands:**
```bash
# R1: +2% crit
python tools/gen_sql.py dbc --spell-id 29187 --set EffectApplyAuraName1=SPELL_AURA_MOD_SPELL_CRIT_CHANCE --set EffectBasePoints1=1 --set EffectMiscValue1=0 --set EffectSpellClassMaskA1=0 --set EffectSpellClassMaskB1=0 --set Effect2=0 --set EffectApplyAuraName2=SPELL_AURA_NONE --set EffectBasePoints2=0 --set EffectDieSides2=0 --set EffectMiscValue2=0 --set EffectSpellClassMaskA2=0 --set EffectSpellClassMaskB2=0 --set "SpellDescription0=Your healing spells gain an additional \$s1% chance to critically hit." --append-to 2026_04_01_00.sql --group-comment "Healing Grace R1 - replace threat/dispel with heal crit"

# R2: +4% crit
python tools/gen_sql.py dbc --spell-id 29189 --set EffectApplyAuraName1=SPELL_AURA_MOD_SPELL_CRIT_CHANCE --set EffectBasePoints1=3 --set EffectMiscValue1=0 --set EffectSpellClassMaskA1=0 --set EffectSpellClassMaskB1=0 --set Effect2=0 --set EffectApplyAuraName2=SPELL_AURA_NONE --set EffectBasePoints2=0 --set EffectDieSides2=0 --set EffectMiscValue2=0 --set EffectSpellClassMaskA2=0 --set EffectSpellClassMaskB2=0 --set "SpellDescription0=Your healing spells gain an additional \$s1% chance to critically hit." --append-to 2026_04_01_00.sql --group-comment "Healing Grace R2"

# R3: +6% crit
python tools/gen_sql.py dbc --spell-id 29191 --set EffectApplyAuraName1=SPELL_AURA_MOD_SPELL_CRIT_CHANCE --set EffectBasePoints1=5 --set EffectMiscValue1=0 --set EffectSpellClassMaskA1=0 --set EffectSpellClassMaskB1=0 --set Effect2=0 --set EffectApplyAuraName2=SPELL_AURA_NONE --set EffectBasePoints2=0 --set EffectDieSides2=0 --set EffectMiscValue2=0 --set EffectSpellClassMaskA2=0 --set EffectSpellClassMaskB2=0 --set "SpellDescription0=Your healing spells gain an additional \$s1% chance to critically hit." --append-to 2026_04_01_00.sql --group-comment "Healing Grace R3"
```

Note: BasePoints uses N-1 convention (DieSides=1), so BP=1 displays as 2%.

### 3. Tidal Focus (talent 593, spells 16179/16214/16215, Resto tree tier 1) — reduced to 3 ranks

**Current state (5 ranks):**
| Spell | Effect1 (mana cost reduction) | Effect2 |
|-------|---------|---------|
| 16179 (R1) | Aura108 (ADD_PCT_MODIFIER), BP=-2, MiscValue=14 (SPELLMOD_COST), ClassMaskA=448/B=0 | None |
| 16214 (R2) | BP=-3 | None |
| 16215 (R3) | BP=-4 | None |

**Change:** 3 ranks only. Effect1 = 3/6/10% mana cost reduction. Add Effect2 = 0.1/0.2/0.3s cast time reduction. talent_dbc override to cap at 3 ranks.

| Rank | Mana Cost (BP1) | Cast Time (BP2) |
|------|-----------------|-----------------|
| R1 (16179) | BP=-4 (3%) | BP=-101 (0.1s) |
| R2 (16214) | BP=-7 (6%) | BP=-201 (0.2s) |
| R3 (16215) | BP=-11 (10%) | BP=-301 (0.3s) |

Note: Cast time modifier values are in ms, negative = faster. BP + DieSides(1) = CalcValue.

### 4. Nature's Blessing (talent 1696, Resto tree tier 7)

**Current state (3 ranks):**
| Spell | Effect1 |
|-------|---------|
| 30867 (R1) | Aura175 (MOD_SPELL_HEALING_OF_STAT_PERCENT), BP=4 (+5%), MiscValue=3 (Intellect), ClassMaskA=448 |
| 30868 (R2) | Aura175, BP=9 (+10%) |
| 30869 (R3) | Aura175, BP=14 (+15%) |

**Change:** Add Effect2 for damage done scaling from intellect. Use SPELL_AURA_MOD_DAMAGE_DONE (13) with school mask, or duplicate with wider ClassMask. The cleanest approach: add Effect2 as SPELL_AURA_MOD_SPELL_HEALING_OF_STAT_PERCENT targeting damage spells too, or use a separate aura. Actually, Aura175 only boosts healing. For damage from stat%, use SPELL_AURA_MOD_DAMAGE_DONE (13) won't work directly with stat%. Need C++ or use a different approach.

**Alternative approach:** Use Effect2 = SPELL_AURA_DUMMY for a C++ handler that adds spell damage from intellect. OR simply widen the existing ClassMask to include all shaman spells (damage + healing). But Aura175 is specifically healing-only in the core.

**Decision:** This needs a small C++ script. Add Effect2 as SPELL_AURA_DUMMY, then C++ reads the aura value and applies bonus spell damage from intellect on stat recalculation.

**File:** `ShamanNaturesBlessing.cpp`

```bash
python tools/gen_sql.py dbc --spell-id 30867 --set Effect2=6 --set EffectApplyAuraName2=SPELL_AURA_DUMMY --set EffectBasePoints2=4 --set EffectDieSides2=1 --set EffectImplicitTargetA2=1 --set "SpellDescription0=Increases your spell damage and healing by an amount equal to \$s1% of your Intellect." --append-to 2026_04_01_00.sql --group-comment "Natures Blessing R1 - add damage from int"

python tools/gen_sql.py dbc --spell-id 30868 --set Effect2=6 --set EffectApplyAuraName2=SPELL_AURA_DUMMY --set EffectBasePoints2=9 --set EffectDieSides2=1 --set EffectImplicitTargetA2=1 --set "SpellDescription0=Increases your spell damage and healing by an amount equal to \$s1% of your Intellect." --append-to 2026_04_01_00.sql --group-comment "Natures Blessing R2"

python tools/gen_sql.py dbc --spell-id 30869 --set Effect2=6 --set EffectApplyAuraName2=SPELL_AURA_DUMMY --set EffectBasePoints2=14 --set EffectDieSides2=1 --set EffectImplicitTargetA2=1 --set "SpellDescription0=Increases your spell damage and healing by an amount equal to \$s1% of your Intellect." --append-to 2026_04_01_00.sql --group-comment "Natures Blessing R3"
```

---

## Tier 2: DBC + Simple C++

### 5. Spirit Weapons (talent 616, Enhancement tree tier 4)

**Current state:** Spell 16268 is a learner that teaches 18848 (SPELL_EFFECT_PARRY) + 36591 (SPELL_AURA_MOD_THREAT, BP=-31, -30%).

**Change:** Keep the parry from 18848. Change 36591 to give +5% flat parry instead of threat reduction. Add C++ for agility-to-parry scaling.

**DBC change on 36591:**
```bash
python tools/gen_sql.py dbc --spell-id 36591 --set EffectApplyAuraName2=SPELL_AURA_MOD_PARRY_PERCENT --set EffectBasePoints2=4 --set EffectMiscValue2=0 --append-to 2026_04_01_01.sql --group-comment "Spirit Weapons - replace threat with 5% parry"
```

Also update 16268 description:
```bash
python tools/gen_sql.py dbc --spell-id 16268 --set "SpellDescription0=Gives a chance to parry enemy melee attacks. Your parry chance is increased by 5% and additionally scales with your Agility." --append-to 2026_04_01_01.sql --group-comment "Spirit Weapons - update description"
```

**C++ (`ShamanSpiritWeapons.cpp`):**
- PlayerScript with `OnAfterUpdateMaxPower` or similar stat hook
- When player has aura 36591, calculate bonus parry from agility
- Pattern: like bear form dodge scaling — read player agility, multiply by scaling factor, apply as parry rating or flat parry
- Reference: look at how `Creature::UpdateArmor()` or druid bear dodge works in the core for the scaling formula

**Script registration:** No spell_script_names needed — this is a PlayerScript, registered directly in MP_loader.

### 6. Focused Mind (talent 1695, Resto tree tier 4)

**Current state (3 ranks):**
| Spell | Effect1 | Effect2 |
|-------|---------|---------|
| 30864 (R1) | Aura234, BP=-11, MiscValue=26 (silence) | Aura234, BP=-11, MiscValue=9 (interrupt) |
| 30865 (R2) | BP=-21 | BP=-21 |
| 30866 (R3) | BP=-31 | BP=-31 |

**Change:** Complete redesign — casting HW/LHW/CH makes next LB/CL deal 33/66/100% more damage and cost 33/66/100% less mana.

**DBC changes on existing spells (make them proc-triggering passives):**
```bash
# R1: SPELL_AURA_DUMMY, stores rank value (33%)
python tools/gen_sql.py dbc --spell-id 30864 --set EffectApplyAuraName1=SPELL_AURA_DUMMY --set EffectBasePoints1=32 --set EffectMiscValue1=0 --set Effect2=0 --set EffectApplyAuraName2=SPELL_AURA_NONE --set EffectBasePoints2=0 --set EffectMiscValue2=0 --set ProcFlags=16384 --set ProcChance=101 --set "SpellDescription0=Casting Healing Wave, Lesser Healing Wave or Chain Heal clears your mind, making your next Lightning Bolt or Chain Lightning deal \$s1% more damage and cost \$s1% less mana." --append-to 2026_04_01_01.sql --group-comment "Focused Mind R1 redesign"

# R2: 66%
python tools/gen_sql.py dbc --spell-id 30865 --set EffectApplyAuraName1=SPELL_AURA_DUMMY --set EffectBasePoints1=65 --set EffectMiscValue1=0 --set Effect2=0 --set EffectApplyAuraName2=SPELL_AURA_NONE --set EffectBasePoints2=0 --set EffectMiscValue2=0 --set ProcFlags=16384 --set ProcChance=101 --set "SpellDescription0=Casting Healing Wave, Lesser Healing Wave or Chain Heal clears your mind, making your next Lightning Bolt or Chain Lightning deal \$s1% more damage and cost \$s1% less mana." --append-to 2026_04_01_01.sql --group-comment "Focused Mind R2"

# R3: 100%
python tools/gen_sql.py dbc --spell-id 30866 --set EffectApplyAuraName1=SPELL_AURA_DUMMY --set EffectBasePoints1=99 --set EffectMiscValue1=0 --set Effect2=0 --set EffectApplyAuraName2=SPELL_AURA_NONE --set EffectBasePoints2=0 --set EffectMiscValue2=0 --set ProcFlags=16384 --set ProcChance=101 --set "SpellDescription0=Casting Healing Wave, Lesser Healing Wave or Chain Heal clears your mind, making your next Lightning Bolt or Chain Lightning deal \$s1% more damage and cost \$s1% less mana." --append-to 2026_04_01_01.sql --group-comment "Focused Mind R3"
```

**Custom spell 200209 (Cleared Mind buff):**
```bash
python tools/gen_sql.py dbc --spell-id 200209 --base 30864 --set SpellName0="Cleared Mind" --set Attributes=0 --set AttributesEx=0 --set DurationIndex=85 --set ProcFlags=0 --set ProcChance=101 --set StackAmount=0 --set Effect1=6 --set EffectApplyAuraName1=SPELL_AURA_DUMMY --set EffectBasePoints1=0 --set EffectImplicitTargetA1=1 --set EffectDieSides1=1 --set "SpellDescription0=Your next Lightning Bolt or Chain Lightning deals bonus damage and costs less mana." --append-to 2026_04_01_01.sql --group-comment "Cleared Mind buff spell"
```

**C++ (`ShamanFocusedMind.cpp`):**
- AuraScript on talent passive (30864/30865/30866 via negative ID -30864): `CheckProc` filters to HW/LHW/CH (SpellFamilyName=11, SpellFamilyFlags & 0x1C0). `HandleProc` on EFFECT_0 (SPELL_AURA_DUMMY): reads BP to get bonus %, applies buff 200209 with that value on self.
- SpellScript on LB/CL (registered via spell_script_names with negative IDs -403 and -421): `HandleOnHit` — if caster has aura 200209, multiply damage by (1 + bonus%), and `HandleOnCast` to reduce mana cost, then remove aura

**spell_script_names:**
```sql
DELETE FROM `spell_script_names` WHERE `spell_id` IN (-30864, -403, -421);
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES
(-30864, 'spell_sha_focused_mind'),
(-403, 'spell_sha_cleared_mind_consume'),
(-421, 'spell_sha_cleared_mind_consume');
```

### 7. Ancestral Awakening (talent 2061, Resto tree tier 8)

**Current state (3 ranks):**
| Spell | Effect1 |
|-------|---------|
| 51556 (R1) | Aura42 (PROC_TRIGGER_SPELL), BP=9 (+10%), triggers 52752 (ancestral awakening heal) |
| 51557 (R2) | BP=19 (+20%) |
| 51558 (R3) | BP=29 (+30%) |

**Change:** Keep existing. Additionally, when Ancestral Awakening procs (spell 52752/52759), also apply a guaranteed crit buff.

**Custom spell 200210 (Ancestral Fury buff):**
```bash
python tools/gen_sql.py dbc --spell-id 200210 --base 51556 --set SpellName0="Ancestral Fury" --set Attributes=0 --set DurationIndex=85 --set ProcFlags=65536 --set ProcChance=101 --set ProcCharges=1 --set Effect1=6 --set EffectApplyAuraName1=SPELL_AURA_MOD_SPELL_CRIT_CHANCE --set EffectBasePoints1=99 --set EffectImplicitTargetA1=1 --set EffectDieSides1=1 --set EffectMiscValue1=0 --set "SpellDescription0=Your next damaging spell is guaranteed to critically hit." --append-to 2026_04_01_01.sql --group-comment "Ancestral Fury - guaranteed crit buff"
```
Duration 85 = 15 seconds, 1 charge, consumed on damage spell cast.

**C++ (`ShamanAncestralAwakening.cpp`):**
- Hook into existing ancestral awakening proc (spell 52759). Create an AuraScript for 52759 that, after the heal effect, also casts 200210 on the original caster.
- OR: PlayerScript that listens for aura 52759 application and casts 200210.

**spell_script_names:**
```sql
DELETE FROM `spell_script_names` WHERE `spell_id` = 52759 AND `ScriptName` = 'spell_sha_ancestral_fury';
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES (52759, 'spell_sha_ancestral_fury');
```

### 8. Purification (talent 592, Resto tree tier 5)

**Current state (5 ranks):** Aura108 (ADD_PCT_MODIFIER), BP=-2/-4/-6/-8/-10 (increases healing by 2/4/6/8/10%), MiscValue=0 (SPELLMOD_DAMAGE), targeting healing spells (ClassMaskA=448).

**Change:** Keep existing. Add C++ proc: Earthliving Weapon heals have 4/8/12/16/20% chance to reset shock cooldowns.

**DBC changes:** Add Effect2 as SPELL_AURA_DUMMY (proc hook for C++) and ProcFlags=262144 (DONE_PERIODIC) so the engine fires procs on Earthliving periodic heals. Update descriptions:
```bash
python tools/gen_sql.py dbc --spell-id 16178 --set Effect2=6 --set EffectApplyAuraName2=SPELL_AURA_DUMMY --set EffectBasePoints2=3 --set EffectDieSides2=1 --set EffectImplicitTargetA2=1 --set ProcFlags=262144 --set ProcChance=101 --set "SpellDescription0=Increases the effectiveness of your healing spells by \$s1%. Additionally, when Earthliving Weapon heals you have a \$s2% chance to reset the cooldown on your shock spells." --append-to 2026_04_01_01.sql --group-comment "Purification R1 - add Earthliving shock reset proc"

python tools/gen_sql.py dbc --spell-id 16210 --set Effect2=6 --set EffectApplyAuraName2=SPELL_AURA_DUMMY --set EffectBasePoints2=7 --set EffectDieSides2=1 --set EffectImplicitTargetA2=1 --set ProcFlags=262144 --set ProcChance=101 --set "SpellDescription0=Increases the effectiveness of your healing spells by \$s1%. Additionally, when Earthliving Weapon heals you have a \$s2% chance to reset the cooldown on your shock spells." --append-to 2026_04_01_01.sql --group-comment "Purification R2"

python tools/gen_sql.py dbc --spell-id 16211 --set Effect2=6 --set EffectApplyAuraName2=SPELL_AURA_DUMMY --set EffectBasePoints2=11 --set EffectDieSides2=1 --set EffectImplicitTargetA2=1 --set ProcFlags=262144 --set ProcChance=101 --set "SpellDescription0=Increases the effectiveness of your healing spells by \$s1%. Additionally, when Earthliving Weapon heals you have a \$s2% chance to reset the cooldown on your shock spells." --append-to 2026_04_01_01.sql --group-comment "Purification R3"

python tools/gen_sql.py dbc --spell-id 16212 --set Effect2=6 --set EffectApplyAuraName2=SPELL_AURA_DUMMY --set EffectBasePoints2=15 --set EffectDieSides2=1 --set EffectImplicitTargetA2=1 --set ProcFlags=262144 --set ProcChance=101 --set "SpellDescription0=Increases the effectiveness of your healing spells by \$s1%. Additionally, when Earthliving Weapon heals you have a \$s2% chance to reset the cooldown on your shock spells." --append-to 2026_04_01_01.sql --group-comment "Purification R4"

python tools/gen_sql.py dbc --spell-id 16213 --set Effect2=6 --set EffectApplyAuraName2=SPELL_AURA_DUMMY --set EffectBasePoints2=19 --set EffectDieSides2=1 --set EffectImplicitTargetA2=1 --set ProcFlags=262144 --set ProcChance=101 --set "SpellDescription0=Increases the effectiveness of your healing spells by \$s1%. Additionally, when Earthliving Weapon heals you have a \$s2% chance to reset the cooldown on your shock spells." --append-to 2026_04_01_01.sql --group-comment "Purification R5"
```
Note: Effect2 BP uses N-1 convention (DieSides=1). R1=4%, R2=8%, R3=12%, R4=16%, R5=20%.

**C++ (`ShamanPurification.cpp`):**
- AuraScript on talent passive (16178 etc. via negative ID -16178): `CheckProc` filters to Earthliving heal proc spells (spell IDs 51945, 51990, 51997, 51998, 51999, 52000). `HandleProc` on EFFECT_1 (SPELL_AURA_DUMMY): reads BP to get chance %, rolls, if success resets shock cooldowns via `player->RemoveSpellCooldown(8042/8050/8056)`.

**spell_script_names:**
```sql
DELETE FROM `spell_script_names` WHERE `spell_id` = -16178 AND `ScriptName` = 'spell_sha_purification_proc';
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES (-16178, 'spell_sha_purification_proc');
```

---

## Tier 3: Complex C++

### 9. Healing Focus (talent 587, Resto tree tier 2)

**Current state (3 ranks):**
| Spell | Effect1 |
|-------|---------|
| 16181 (R1) | Aura108 (ADD_PCT_MODIFIER), BP=22, MiscValue=9 (SPELLMOD_NOT_LOSE_CASTING_TIME), ClassMaskA=448 |
| 16230 (R2) | BP=45 |
| 16232 (R3) | BP=69 |

**Change:** Complete redesign — two mechanics:
1. Shock spells have 33/66/100% chance to make HW free and instant
2. Casting heal on target with your Earth Shield, Water Shield or Lightning Shield boosts next cast's damage by 25%

**DBC changes (make passive DUMMY aura):**
```bash
python tools/gen_sql.py dbc --spell-id 16181 --set EffectApplyAuraName1=SPELL_AURA_DUMMY --set EffectBasePoints1=32 --set EffectMiscValue1=0 --set EffectSpellClassMaskA1=0 --set ProcFlags=81920 --set "SpellDescription0=Your shock spells have a \$s1% chance to make your next Healing Wave free and instant cast. Additionally, casting a heal on a target with your Earth Shield, Water Shield or Lightning Shield, increases the damage of your next cast by 25%." --append-to 2026_04_01_02.sql --group-comment "Healing Focus R1 redesign"

python tools/gen_sql.py dbc --spell-id 16230 --set EffectApplyAuraName1=SPELL_AURA_DUMMY --set EffectBasePoints1=65 --set EffectMiscValue1=0 --set EffectSpellClassMaskA1=0 --set ProcFlags=81920 --set "SpellDescription0=Your shock spells have a \$s1% chance to make your next Healing Wave free and instant cast. Additionally, casting a heal on a target with your Earth Shield, Water Shield or Lightning Shield, increases the damage of your next cast by 25%." --append-to 2026_04_01_02.sql --group-comment "Healing Focus R2"

python tools/gen_sql.py dbc --spell-id 16232 --set EffectApplyAuraName1=SPELL_AURA_DUMMY --set EffectBasePoints1=99 --set EffectMiscValue1=0 --set EffectSpellClassMaskA1=0 --set ProcFlags=81920 --set "SpellDescription0=Your shock spells have a \$s1% chance to make your next Healing Wave free and instant cast. Additionally, casting a heal on a target with your Earth Shield, Water Shield or Lightning Shield, increases the damage of your next cast by 25%." --append-to 2026_04_01_02.sql --group-comment "Healing Focus R3"
```

**Custom spell 200211 (Surging Focus - instant free HW):**
```bash
python tools/gen_sql.py dbc --spell-id 200211 --base 16181 --set SpellName0="Surging Focus" --set Attributes=0 --set DurationIndex=85 --set ProcCharges=1 --set Effect1=6 --set EffectApplyAuraName1=SPELL_AURA_ADD_FLAT_MODIFIER --set EffectBasePoints1=-99999 --set EffectMiscValue1=14 --set EffectSpellClassMaskA1=448 --set Effect2=6 --set EffectApplyAuraName2=SPELL_AURA_ADD_PCT_MODIFIER --set EffectBasePoints2=-100 --set EffectMiscValue2=10 --set EffectSpellClassMaskA2=64 --set EffectImplicitTargetA2=1 --set EffectDieSides2=0 --set "SpellDescription0=Your next Healing Wave is instant cast and costs no mana." --append-to 2026_04_01_02.sql --group-comment "Surging Focus buff"
```
Note: Effect1 = reduce mana cost to 0 (SPELLMOD_COST, large negative), Effect2 = reduce cast time to 0 (SPELLMOD_CASTING_TIME, -100%). Target ClassMask=64 (Healing Wave only). 1 charge.

**Custom spell 200212 (Focused Assault - damage buff):**
```bash
python tools/gen_sql.py dbc --spell-id 200212 --base 16181 --set SpellName0="Focused Assault" --set Attributes=0 --set DurationIndex=85 --set ProcCharges=1 --set ProcFlags=65536 --set ProcChance=101 --set Effect1=6 --set EffectApplyAuraName1=SPELL_AURA_MOD_DAMAGE_DONE --set EffectBasePoints1=24 --set EffectMiscValue1=126 --set EffectImplicitTargetA1=1 --set EffectDieSides1=1 --set EffectSpellClassMaskA1=0 --set SpellIconID=2248 --set "SpellDescription0=Your damage is increased by 25%." --append-to 2026_04_01_02.sql --group-comment "Focused Assault damage buff"
```
Note: MiscValue=126 (all magic schools). 1 charge, consumed on damage spell hit. Actually SPELL_AURA_MOD_DAMAGE_DONE uses MiscValue as school mask (126 = 0x7E = all schools except physical). However, this approach may need refinement — ADD_PCT_MODIFIER with SPELLMOD_DAMAGE might be more reliable.

**SQL: `spell_script_names` registration (negative ID = all ranks):**
```sql
(-16181, 'spell_sha_healing_focus')
```

**No `spell_proc` entries** — DBC ProcFlags=81920 is sufficient. The engine auto-generates a proc entry with SpellPhaseMask=HIT from the DBC. Do NOT add spell_proc rows with SpellPhaseMask=0, as that overrides the default and silently disables procs.

**C++ (`ShamanHealingFocus.cpp`):**
- AuraScript on 16181/16230/16232 (via `spell_script_names` negative ID)
- `CheckProc`: filter to Shaman family spells matching shock flags (0x90100000) or heal flags (0x1C0)
- `HandleProc` (EFFECT_0, SPELL_AURA_DUMMY):
  1. On shock cast: roll chance from aura BP, if success cast 200211 on self
  2. On heal cast: check if `GetActionTarget()` has Earth Shield, Water Shield or Lightning Shield cast by the healer (`GetAura(id, casterGUID)`), if so cast 200212 on self

### 10. Defence of Nature (replaces Improved Reincarnation, talent 589, Resto tree tier 1)

**Current state (2 ranks):**
| Spell | Effect1 | Effect2 |
|-------|---------|---------|
| 16184 (R1) | Aura108, BP=-300001 (CD reduction), MiscValue=10 | Aura107, BP=9 (+10% health), MiscValue=0 |
| 16209 (R2) | BP=-600001 | BP=19 (+20%) |

**Change:** Complete redesign. Shields proc instant AoE nature damage with 25/50% chance.

**Approach:** Since this is a complete redesign, override the existing spells via alonecraft_spell_dbc to become passive DUMMY auras, then use C++ to handle the proc.

**DBC changes:**
```bash
# R1: 25% chance
python tools/gen_sql.py dbc --spell-id 16184 --set EffectApplyAuraName1=SPELL_AURA_DUMMY --set EffectBasePoints1=24 --set EffectDieSides1=1 --set EffectMiscValue1=0 --set EffectSpellClassMaskA1=0 --set Effect2=0 --set EffectApplyAuraName2=SPELL_AURA_NONE --set EffectBasePoints2=0 --set EffectDieSides2=0 --set EffectSpellClassMaskA2=0 --set SpellName0="Defence of Nature" --set "SpellDescription0=Your Water Shield, Earth Shield and Lightning Shield have a \$s1% chance to cleanse the earth around you, dealing nature damage to all enemies within 15 yards." --append-to 2026_04_01_02.sql --group-comment "Defence of Nature R1"

# R2: 50% chance
python tools/gen_sql.py dbc --spell-id 16209 --set EffectApplyAuraName1=SPELL_AURA_DUMMY --set EffectBasePoints1=49 --set EffectDieSides1=1 --set EffectMiscValue1=0 --set EffectSpellClassMaskA1=0 --set Effect2=0 --set EffectApplyAuraName2=SPELL_AURA_NONE --set EffectBasePoints2=0 --set EffectDieSides2=0 --set EffectSpellClassMaskA2=0 --set SpellName0="Defence of Nature" --set "SpellDescription0=Your Water Shield, Earth Shield and Lightning Shield have a \$s1% chance to cleanse the earth around you, dealing nature damage to all enemies within 15 yards." --append-to 2026_04_01_02.sql --group-comment "Defence of Nature R2"
```

**Custom spell 200214 (AoE nature damage):**
```bash
python tools/gen_sql.py dbc --spell-id 200214 --base 16184 --set SpellName0="Cleansing Earth" --set Attributes=0 --set Effect1=2 --set EffectApplyAuraName1=SPELL_AURA_NONE --set EffectBasePoints1=149 --set EffectDieSides1=1 --set EffectImplicitTargetA1=22 --set EffectRadiusIndex1=14 --set EffectMiscValue1=0 --set SchoolMask=8 --set "SpellDescription0=Cleanses the earth around you, dealing nature damage to all enemies within 15 yards." --append-to 2026_04_01_02.sql --group-comment "Defence of Nature AoE damage spell"
```
Note: Effect=2 (SPELL_EFFECT_SCHOOL_DAMAGE), Target=22 (TARGET_SRC_CASTER_AREA_ENEMY), RadiusIndex=14 (15 yards), SchoolMask=8 (nature). BP=149 → 150 damage base (will need tuning — or scale from spellpower).

**C++ (`ShamanDefenceOfNature.cpp`):**
- PlayerScript: hook into shield proc events
- Water Shield procs when hit (mana restore), Earth Shield procs when target takes damage, Lightning Shield procs on hit
- On any shield proc, check for Defence of Nature aura (16184/16209), read chance from BP, roll, if success cast 200214 centered on self
- The damage amount could be dynamically scaled in the SpellScript for 200214 based on spellpower

**spell_script_names:** Not needed for the passive — it's a PlayerScript. But 200214 may need one if we want to scale damage.

**talent_dbc:** NOT needed — we're overriding the existing spells 16184/16209 directly, which the talent already teaches.

### 11. Spiritsurge (replaces Improved Chain Heal, talent 1697, Resto tree tier 7)

**Current state (2 ranks):**
| Spell | Effect1 |
|-------|---------|
| 30872 (R1) | Aura108 (ADD_PCT_MODIFIER), BP=9 (+10%), MiscValue=0, ClassMaskA=256 (Chain Heal) |
| 30873 (R2) | BP=19 (+20%) |

**Change:** When Earthliving heals, shocks are empowered for 15s (2 charges). Earth Shock summons earth elemental for 6s, Flame Shock AoEs 15yd, Frost Shock roots 3s. 8s ICD.

**DBC changes:**
```bash
# R1: passive DUMMY
python tools/gen_sql.py dbc --spell-id 30872 --set EffectApplyAuraName1=SPELL_AURA_DUMMY --set EffectBasePoints1=0 --set EffectMiscValue1=0 --set EffectSpellClassMaskA1=0 --set ProcFlags=262144 --set ProcChance=101 --set SpellName0="Spiritsurge" --set "SpellDescription0=When Earthliving Weapon heals, your shock spells are empowered by the elements for 15 sec. Earth Shock summons an elemental guardian, Flame Shock applies to all enemies within 15 yards, and Frost Shock freezes enemies in place for 3 sec. Can only occur once every 8 seconds." --append-to 2026_04_01_02.sql --group-comment "Spiritsurge R1"

# R2: same (both ranks get the effect, just requires 2 talent points)
python tools/gen_sql.py dbc --spell-id 30873 --set EffectApplyAuraName1=SPELL_AURA_DUMMY --set EffectBasePoints1=0 --set EffectMiscValue1=0 --set EffectSpellClassMaskA1=0 --set ProcFlags=262144 --set ProcChance=101 --set SpellName0="Spiritsurge" --set "SpellDescription0=When Earthliving Weapon heals, your shock spells are empowered by the elements for 15 sec. Earth Shock summons an elemental guardian, Flame Shock applies to all enemies within 15 yards, and Frost Shock freezes enemies in place for 3 sec. Can only occur once every 8 seconds." --append-to 2026_04_01_02.sql --group-comment "Spiritsurge R2"
```

**Custom spell 200217 (Spiritsurge buff):**
```bash
python tools/gen_sql.py dbc --spell-id 200217 --base 30872 --set SpellName0="Spiritsurge" --set Attributes=0 --set DurationIndex=85 --set ProcCharges=2 --set ProcFlags=65536 --set ProcChance=101 --set Effect1=6 --set EffectApplyAuraName1=SPELL_AURA_DUMMY --set EffectBasePoints1=0 --set EffectImplicitTargetA1=1 --set "SpellDescription0=Your shock spells are empowered by the elements. 2 charges." --append-to 2026_04_01_02.sql --group-comment "Spiritsurge buff (2 charges, 15s)"
```

**Custom spell 200218 (Earth Elemental summon, 6s):**
- Clone Earth Elemental Totem summon effect but with 6s duration
- Use SummonProperties ID 713 (guardian multi-summon) or look at existing earth elemental summon
- Duration index for 6s = 28

**Custom spell 200219 (Frost Shock root, 3s):**
```bash
python tools/gen_sql.py dbc --spell-id 200219 --base 8056 --set SpellName0="Elemental Freeze" --set Attributes=0 --set DurationIndex=27 --set Effect1=6 --set EffectApplyAuraName1=SPELL_AURA_MOD_ROOT --set EffectBasePoints1=0 --set EffectImplicitTargetA1=6 --set "SpellDescription0=Frozen in place for 3 sec." --set Mechanic=2 --append-to 2026_04_01_02.sql --group-comment "Spiritsurge Frost Shock root (3s)"
```

**C++ (`ShamanSpiritSurge.cpp`):**
Two AuraScripts in same file:
1. AuraScript on talent passive (30872/30873 via negative ID -30872): `CheckProc` filters to Earthliving heal proc spells (51945-52000). `HandleProc` on EFFECT_0: apply buff 200217 on self, with 8s ICD tracked via cooldown on 200217.
2. AuraScript on buff 200217: `CheckProc` filters to shock spells (SpellFamilyName=11, SpellFamilyFlags & 0x90100000). `HandleProc` on EFFECT_0: check which shock was cast — Earth Shock: also cast 200218 (summon elemental). Flame Shock: find enemies within 15yd of target and apply Flame Shock to each. Frost Shock: also cast 200219 (root) on target. Charge consumption is automatic (ProcCharges=2 on 200217).

**spell_script_names:**
```sql
DELETE FROM `spell_script_names` WHERE `ScriptName` IN ('spell_sha_spiritsurge_talent', 'spell_sha_spiritsurge_buff');
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES
(-30872, 'spell_sha_spiritsurge_talent'),
(200217, 'spell_sha_spiritsurge_buff');
```

### 12. Tidal Waves (talent 2063, Resto tree tier 9)

**Current state (5 ranks):**
| Spell | Effect1 | Effect2 | Effect3 |
|-------|---------|---------|---------|
| 51562 (R1) | Aura42 (PROC_TRIGGER), BP=19 (20%), triggers 53390 | BP=3 (4%), MiscValue=10 (cast time) | BP=1 (2%), MiscValue=17 (crit chance) |
| 51563-51566 | BP=39/59/79/99 | BP=7/11/15/19 | BP=3/5/7/9 |

**Change:** Passive 20% spellpower bonus (all ranks). Casting LB/CL/Lava Burst increases heal crit by 5/10/15/20/25%.

**DBC changes:**
```bash
# R1: Effect1 = 20% spellpower passive, Effect2 = DUMMY for C++ proc (stores 5% crit value)
python tools/gen_sql.py dbc --spell-id 51562 --set EffectApplyAuraName1=SPELL_AURA_MOD_DAMAGE_DONE --set EffectBasePoints1=19 --set EffectMiscValue1=126 --set EffectTriggerSpell1=0 --set Effect2=6 --set EffectApplyAuraName2=SPELL_AURA_DUMMY --set EffectBasePoints2=4 --set EffectDieSides2=1 --set EffectImplicitTargetA2=1 --set EffectMiscValue2=0 --set Effect3=0 --set EffectApplyAuraName3=SPELL_AURA_NONE --set EffectBasePoints3=0 --set ProcFlags=65536 --set ProcChance=101 --set "SpellDescription0=Your damage and healing spells gain an additional 20% of your spell power. Casting Lightning Bolt, Chain Lightning or Lava Burst increases the critical strike chance of your next healing spell by \$s2%." --append-to 2026_04_01_02.sql --group-comment "Tidal Waves R1 redesign"

# R2-R5: same Effect1 (20% SP), increasing Effect2 values
python tools/gen_sql.py dbc --spell-id 51563 --set EffectApplyAuraName1=SPELL_AURA_MOD_DAMAGE_DONE --set EffectBasePoints1=19 --set EffectMiscValue1=126 --set EffectTriggerSpell1=0 --set Effect2=6 --set EffectApplyAuraName2=SPELL_AURA_DUMMY --set EffectBasePoints2=9 --set EffectDieSides2=1 --set EffectImplicitTargetA2=1 --set EffectMiscValue2=0 --set Effect3=0 --set EffectApplyAuraName3=SPELL_AURA_NONE --set EffectBasePoints3=0 --set ProcFlags=65536 --set ProcChance=101 --set "SpellDescription0=Your damage and healing spells gain an additional 20% of your spell power. Casting Lightning Bolt, Chain Lightning or Lava Burst increases the critical strike chance of your next healing spell by \$s2%." --append-to 2026_04_01_02.sql --group-comment "Tidal Waves R2"

python tools/gen_sql.py dbc --spell-id 51564 --set EffectApplyAuraName1=SPELL_AURA_MOD_DAMAGE_DONE --set EffectBasePoints1=19 --set EffectMiscValue1=126 --set EffectTriggerSpell1=0 --set Effect2=6 --set EffectApplyAuraName2=SPELL_AURA_DUMMY --set EffectBasePoints2=14 --set EffectDieSides2=1 --set EffectImplicitTargetA2=1 --set EffectMiscValue2=0 --set Effect3=0 --set EffectApplyAuraName3=SPELL_AURA_NONE --set EffectBasePoints3=0 --set ProcFlags=65536 --set ProcChance=101 --set "SpellDescription0=Your damage and healing spells gain an additional 20% of your spell power. Casting Lightning Bolt, Chain Lightning or Lava Burst increases the critical strike chance of your next healing spell by \$s2%." --append-to 2026_04_01_02.sql --group-comment "Tidal Waves R3"

python tools/gen_sql.py dbc --spell-id 51565 --set EffectApplyAuraName1=SPELL_AURA_MOD_DAMAGE_DONE --set EffectBasePoints1=19 --set EffectMiscValue1=126 --set EffectTriggerSpell1=0 --set Effect2=6 --set EffectApplyAuraName2=SPELL_AURA_DUMMY --set EffectBasePoints2=19 --set EffectDieSides2=1 --set EffectImplicitTargetA2=1 --set EffectMiscValue2=0 --set Effect3=0 --set EffectApplyAuraName3=SPELL_AURA_NONE --set EffectBasePoints3=0 --set ProcFlags=65536 --set ProcChance=101 --set "SpellDescription0=Your damage and healing spells gain an additional 20% of your spell power. Casting Lightning Bolt, Chain Lightning or Lava Burst increases the critical strike chance of your next healing spell by \$s2%." --append-to 2026_04_01_02.sql --group-comment "Tidal Waves R4"

python tools/gen_sql.py dbc --spell-id 51566 --set EffectApplyAuraName1=SPELL_AURA_MOD_DAMAGE_DONE --set EffectBasePoints1=19 --set EffectMiscValue1=126 --set EffectTriggerSpell1=0 --set Effect2=6 --set EffectApplyAuraName2=SPELL_AURA_DUMMY --set EffectBasePoints2=24 --set EffectDieSides2=1 --set EffectImplicitTargetA2=1 --set EffectMiscValue2=0 --set Effect3=0 --set EffectApplyAuraName3=SPELL_AURA_NONE --set EffectBasePoints3=0 --set ProcFlags=65536 --set ProcChance=101 --set "SpellDescription0=Your damage and healing spells gain an additional 20% of your spell power. Casting Lightning Bolt, Chain Lightning or Lava Burst increases the critical strike chance of your next healing spell by \$s2%." --append-to 2026_04_01_02.sql --group-comment "Tidal Waves R5"
```

Note: SPELL_AURA_MOD_DAMAGE_DONE (13) with MiscValue=126 adds flat spell damage to all schools. For a % bonus, might need ADD_PCT_MODIFIER instead. Consider using SPELL_AURA_MOD_HEALING_DONE_PERCENT (135) for healing + SPELL_AURA_MOD_DAMAGE_DONE with flat values. The exact approach may need testing.

**Custom spell 200220 (Tidal Crit buff):**
```bash
python tools/gen_sql.py dbc --spell-id 200220 --base 51562 --set SpellName0="Tidal Surge" --set Attributes=0 --set DurationIndex=85 --set ProcCharges=1 --set Effect1=6 --set EffectApplyAuraName1=SPELL_AURA_MOD_SPELL_CRIT_CHANCE --set EffectBasePoints1=0 --set EffectImplicitTargetA1=1 --set EffectDieSides1=1 --set EffectMiscValue1=0 --set Effect2=0 --set Effect3=0 --set "SpellDescription0=Your next healing spell has an increased chance to critically hit." --append-to 2026_04_01_02.sql --group-comment "Tidal Surge heal crit buff"
```

**C++ (`ShamanTidalWaves.cpp`):**
- AuraScript on talent passive (51562-51566 via negative ID -51562): `CheckProc` filters to LB/CL/Lava Burst (SpellFamilyName=11, SpellFamilyFlags & 0x03 or SpellFamilyFlags1 & 0x1000). `HandleProc` on EFFECT_1 (SPELL_AURA_DUMMY): reads BP to get crit %, applies buff 200220 with that crit value on self.

**spell_script_names:**
```sql
DELETE FROM `spell_script_names` WHERE `spell_id` = -51562 AND `ScriptName` = 'spell_sha_tidal_waves_proc';
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES (-51562, 'spell_sha_tidal_waves_proc');
```

### 13. Riptide (talent 2064, Resto tree tier 10)

**Current state:** Spell 61295 — heals friendly target for X + HoT over 15s. Chain Heal consumes HoT for +25%.

**Change:** Works like Holy Shock — heals friendly OR damages hostile. Chain Lightning also consumes for +25%.

**DBC change (update description):**
```bash
python tools/gen_sql.py dbc --spell-id 61295 --set "SpellDescription0=Heals a friendly target for \$s1 and another \$o2 over \$d, or deals \$s1 Nature damage to an enemy and \$o2 over \$d. Your next Chain Heal or Chain Lightning cast on that target within 15 sec will consume the effect and increase the amount by 25%." --append-to 2026_04_01_02.sql --group-comment "Riptide - update desc for dual purpose"
```

Also update Riptide ranks 2-4 (61299, 61300, 61301) with same description pattern.

**C++ (`ShamanRiptide.cpp`):**
Two separate scripts needed:

1. **SpellScript on Riptide (61295 and ranks):** `HandleOnHit` — check if target is hostile. If hostile, convert the heal to damage (negate the heal, deal same amount as nature damage). For the HoT component, apply a nature DoT instead of HoT (or use custom spell 200221 for the DoT).

2. **SpellScript on Chain Lightning:** Similar to existing `spell_sha_chain_heal` pattern — on first hit, check if target has Riptide periodic effect (SPELL_AURA_PERIODIC_HEAL or periodic damage from 200221), consume it, boost Chain Lightning damage by 25%.

**Custom spell 200221 (Riptide damage DoT):** May be needed if we can't convert the HoT to a DoT on hostile targets. Create as a nature damage periodic spell with same tick rate and duration as Riptide HoT.

**spell_script_names:**
```sql
-- Register for all Riptide ranks
DELETE FROM `spell_script_names` WHERE `ScriptName` = 'spell_sha_riptide_dual';
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES
(-61295, 'spell_sha_riptide_dual');

-- Register for Chain Lightning (all ranks)
DELETE FROM `spell_script_names` WHERE `ScriptName` = 'spell_sha_chain_lightning_riptide';
INSERT INTO `spell_script_names` (`spell_id`, `ScriptName`) VALUES
(-421, 'spell_sha_chain_lightning_riptide');
```

Note: -421 for Chain Lightning may conflict with Focused Mind's -421 registration. Both scripts can be registered separately — AzerothCore supports multiple script names per spell ID.

---

## Files to Create/Modify

### New C++ Files (`modules/world_of_alonecraft/src/`)
1. `ShamanNaturesBlessing.cpp` - Damage from intellect (PlayerScript)
2. `ShamanSpiritWeapons.cpp` - Agility-to-parry scaling (PlayerScript)
3. `ShamanFocusedMind.cpp` - Heal->damage buff proc (AuraScript + SpellScript)
4. `ShamanAncestralAwakening.cpp` - Guaranteed crit on heal crit (AuraScript on 52759)
5. `ShamanPurification.cpp` - Earthliving resets shock CD (AuraScript)
6. `ShamanHealingFocus.cpp` - Shock->instant HW + shielded damage buff (AuraScript)
7. `ShamanDefenceOfNature.cpp` - Shield proc AoE damage (AuraScript)
8. `ShamanSpiritSurge.cpp` - Earthliving empowers shocks (AuraScript x2)
9. `ShamanTidalWaves.cpp` - Damage->heal crit + passive spellpower (AuraScript)
10. `ShamanRiptide.cpp` - Dual-purpose + Chain Lightning interaction (SpellScript)

### Modify
- `modules/world_of_alonecraft/src/MP_loader.cpp` - Register all new AddSC_ functions

### New SQL Files (`modules/world_of_alonecraft/data/sql/db-world/`)
- `2026_04_01_00.sql` - Tier 1 DBC overrides (Elemental Precision, Healing Grace, Tidal Focus, Nature's Blessing)
- `2026_04_01_01.sql` - Tier 2 custom spells + DBC overrides + spell_script_names + spell_proc
- `2026_04_01_02.sql` - Tier 3 custom spells + DBC overrides + spell_script_names + spell_proc

### Key Existing Files to Reference
- `src/server/scripts/Spells/spell_shaman.cpp` — chain_heal Riptide interaction (~line 497), ancestral_awakening proc (~line 170), nature_guardian (~line 1137)
- `src/server/game/Spells/SpellDefines.h` — SpellModOp enum
- `src/server/game/Spells/SpellAuraDefines.h` — AuraType enum
- `src/server/shared/SharedDefines.h` — SPELLFAMILY_SHAMAN = 11

---

## Custom Spell ID Allocation

| ID | Name | Purpose |
|----|------|---------|
| 200209 | Cleared Mind | Focused Mind buff (next LB/CL boosted) |
| 200210 | Ancestral Fury | Guaranteed crit buff (1 charge) |
| 200211 | Surging Focus | Instant free HW buff (1 charge) |
| 200212 | Focused Assault | +25% damage buff (1 charge) |
| 200214 | Cleansing Earth | Defence of Nature AoE damage |
| 200217 | Spiritsurge | Empowered shocks buff (2 charges, 15s) |
| 200218 | Earth Guardian | Mini earth elemental summon (6s) |
| 200219 | Elemental Freeze | Frost Shock root (3s) |
| 200220 | Tidal Surge | Heal crit buff from damage spells |
| 200221 | Riptide (Damage) | Damage DoT for hostile Riptide |

IDs 200213, 200215, 200216 reserved but not needed (Defence of Nature uses existing spell overrides instead of learner pattern).

---

## Implementation Order

1. **Tier 1** — DBC-only SQL (Elemental Precision, Healing Grace, Tidal Focus, Nature's Blessing)
2. **Tier 2** — C++ + SQL (Spirit Weapons, Focused Mind, Ancestral Awakening, Purification)
3. **Tier 3** — C++ + SQL (Healing Focus, Defence of Nature, Spiritsurge, Tidal Waves, Riptide)
4. **MP_loader.cpp** updates (incrementally as each file is created)
5. **Verification** pass

---

## Verification Plan

1. `python tools/verify_scripts.py` — Check C++/SQL/loader consistency
2. `build_and_run.bat` — Full build + DBC rebuild
3. `python tools/verify_db.py --spell-ids 200209 200210 200211 200212 200214 200217 200218 200219 200220 200221` — Verify custom spells

---

## In-Game Test Plan

Tests are ordered by check complexity (simplest first). Previously verified tests are at the bottom.

### Setup Commands

```
.modify hp 99999
.modify mana 99999
.aura <spell_id>        -- to apply talents manually
.unaura <spell_id>      -- to remove
.cooldown               -- reset all cooldowns
.damage <amount>        -- to take damage (for shield proc tests)
.npc add temp <npc_id>  -- spawn target dummies
```

---

### Needs Testing (ordered by complexity)

---

### 1. Focused Mind (30864/30865/30866) — NEEDS RECHECK

**What changed:** Complete redesign — heal cast buffs next LB/CL damage. Proc mechanism changed from PlayerScript to AuraScript + DBC ProcFlags.

| Step | Action | Expected |
|------|--------|----------|
| 1 | `.aura 30866` (R3, 100%) | Talent applied |
| 2 | Cast Lightning Bolt on a mob, note damage | Baseline LB damage (no buff active) |
| 3 | Cast Healing Wave on self | "Cleared Mind" buff (200209) should appear |
| 4 | Cast Lightning Bolt on mob | Damage should be ~2x baseline (100% bonus). Buff consumed. |
| 5 | Cast Lightning Bolt again without healing first | Normal damage (no buff) |
| 6 | Cast Lesser Healing Wave on self | Cleared Mind buff appears |
| 7 | Cast Chain Lightning | Bonus damage applied, buff consumed |
| 8 | Cast Chain Heal | Cleared Mind buff appears |
| 9 | `.unaura 30866`, `.aura 30864` (R1, 33%) | Heal, then LB — damage should be ~1.33x baseline |
| 10 | Verify buff expires after 15s without casting | Cast heal, wait 16s, LB should be normal damage |

CHECKED WORKING

---

### 2. Tidal Waves (51562-51566)

**What changed:** Complete redesign — passive spellpower + damage spells boost heal crit.

#### Part A: Passive Spellpower

| Step | Action | Expected |
|------|--------|----------|
| 1 | Note current spell damage and healing | Baseline |
| 2 | `.aura 51566` (R5) | Talent applied |
| 3 | Check character sheet or cast spells | Spell damage and healing should increase by ~20% of spellpower |

#### Part B: Damage -> Heal Crit

| Step | Action | Expected |
|------|--------|----------|
| 4 | Cast Lightning Bolt on a mob | "Tidal Surge" buff (200220) should appear |
| 5 | Check buff tooltip | Should show +25% crit chance (R5) |
| 6 | Cast Healing Wave | Should have massively increased crit chance. Buff consumed. |
| 7 | Cast Healing Wave again | Normal crit chance (no buff) |
| 8 | Cast Chain Lightning | Tidal Surge appears |
| 9 | Cast Lava Burst | Tidal Surge appears (overwrites/refreshes) |
| 10 | `.unaura 51566`, `.aura 51562` (R1) | After LB, buff should show +5% crit |


CHECKED WORKING 

---

### 3. Purification (16178/16210-16213) — NEEDS RECHECK

**What changed:** Earthliving heals can now reset shock cooldowns. Entirely new approach: added Effect2 DUMMY + ProcFlags, changed from PlayerScript to AuraScript.

| Step | Action | Expected |
|------|--------|----------|
| 1 | `.aura 16213` (R5, 20% chance) | Talent applied |
| 2 | Apply Earthliving Weapon to your weapon | Need the enchant active |
| 3 | Cast Earth Shock, note it goes on cooldown | Normal cooldown behavior |
| 4 | Spam heals (HW/LHW) on low-HP targets | Earthliving should proc periodically |
| 5 | Watch shock cooldowns after Earthliving procs | ~20% of the time, shock cooldowns should reset (Earth/Flame/Frost all reset together) |
| 6 | `.aura 16178` (R1, 4% chance) instead | Same test but much rarer resets |
| 7 | Without Purification talent | Earthliving procs should never reset shock cooldowns |

**Tip:** Use `.aura 51940` to force Earthliving procs for faster testing.

CHECKED WORKING

---

### 4. Defence of Nature (16184/16209)

**What changed:** Complete redesign — shield procs deal AoE damage. Recently refactored.

| Step | Action | Expected |
|------|--------|----------|
| 1 | `.aura 16209` (R2, 50% chance) | Talent applied |
| 2 | Apply Lightning Shield (`.aura 324`) | Shield active |
| 3 | Spawn 3-4 mobs around you (`.npc add temp 1` x4) | Need nearby enemies |
| 4 | Let mobs melee you to trigger Lightning Shield procs | ~50% of shield procs should cause AoE nature damage to all enemies within 15yd |
| 5 | Check combat log for "Cleansing Earth" (200214) | Should see AoE damage entries |
| 6 | Apply Water Shield instead | Let mobs hit you — Water Shield mana procs should also trigger Defence of Nature |
| 7 | Apply Earth Shield on self, take damage | Earth Shield heal procs should also trigger it |
| 8 | `.unaura 16209`, `.aura 16184` (R1, 25%) | Same tests but roughly half as many procs |

CHECKED WORKING

---

### 5. Riptide (61295)

**What changed:** Now heals friendly OR damages hostile. Chain Lightning also consumes for +25%.

#### Part A: Hostile Targeting (Damage Mode)

| Step | Action | Expected |
|------|--------|----------|
| 1 | Learn Riptide (or ensure it's available) | |
| 2 | Cast Riptide on a friendly target | Normal heal + HoT applied |
| 3 | Cast Riptide on a hostile mob | Should deal nature damage (same amount as heal) + apply periodic damage DoT |
| 4 | Check mob debuffs | Should see Riptide DoT ticking |

#### Part B: Chain Heal + Riptide (Existing Behavior)

| Step | Action | Expected |
|------|--------|----------|
| 5 | Cast Riptide on a friendly target | HoT applied |
| 6 | Cast Chain Heal on the same target | +25% healing, Riptide HoT consumed |

#### Part C: Chain Lightning + Riptide (New Behavior)

| Step | Action | Expected |
|------|--------|----------|
| 7 | Cast Riptide on a hostile mob | DoT applied |
| 8 | Note baseline Chain Lightning damage on that mob | |
| 9 | Cast Riptide on a different hostile mob | DoT applied |
| 10 | Cast Chain Lightning on that mob | +25% damage on all chain targets. Riptide DoT consumed. |
| 11 | Cast Chain Lightning on same mob again | Normal damage (no Riptide to consume) |

#### Part D: Edge Cases

| Step | Action | Expected |
|------|--------|----------|
| 12 | Cast Riptide on friendly target with Riptide HoT already | Should refresh the HoT |
| 13 | Cast Chain Lightning on a target WITHOUT Riptide | Normal damage, no bonus |

CHECKED WORKING

---

### 6. Spiritsurge (30872/30873)

**What changed:** Complete redesign — Earthliving empowers shocks with elemental effects.

#### Setup

| Step | Action | Expected |
|------|--------|----------|
| 1 | `.aura 30873` (R2) | Talent applied |
| 2 | Apply Earthliving Weapon | Need enchant active |
| 3 | Spawn several mobs clustered together | Need targets |

#### Earth Shock -> Summon Elemental

| Step | Action | Expected |
|------|--------|----------|
| 4 | Spam heals until Earthliving procs | "Spiritsurge" buff (200217) should appear with 2 charges |
| 5 | Cast Earth Shock on a mob | An earth elemental should appear for 6 seconds. Spiritsurge drops to 1 charge. |
| 6 | Wait 6 seconds | Elemental despawns |

#### Flame Shock -> AoE Spread

| Step | Action | Expected |
|------|--------|----------|
| 7 | Get Spiritsurge buff again (heal until proc) | 2 charges |
| 8 | Cast Flame Shock on one mob in a cluster | Flame Shock should also apply to all enemies within 15 yards. 1 charge consumed. |
| 9 | Check debuffs on surrounding mobs | All should have Flame Shock |

#### Frost Shock -> Root

| Step | Action | Expected |
|------|--------|----------|
| 10 | With remaining charge, cast Frost Shock | Target should be rooted for 3 seconds (plus normal slow). Charge consumed. |
| 11 | Check buff bar | Spiritsurge buff should be gone (0 charges) |

#### ICD Test

| Step | Action | Expected |
|------|--------|----------|
| 12 | Trigger Earthliving proc, get Spiritsurge | Buff appears |
| 13 | Immediately trigger another Earthliving proc | Spiritsurge should NOT refresh (8s ICD) |
| 14 | Wait 8+ seconds, trigger Earthliving again | Spiritsurge should now apply |

CHECKED WORKING

---

### Previously Verified (no recheck needed)

---

### 7. Elemental Precision (30672/30673/30674)

**What changed:** Threat reduction replaced with spell crit.

| Step | Action | Expected |
|------|--------|----------|
| 1 | `.aura 30674` (R3) | Talent applied |
| 2 | Open character sheet, note spell hit % and spell crit % | Should see +3% hit AND +3% crit |
| 3 | `.unaura 30674` | Both bonuses disappear |
| 4 | `.aura 30672` (R1) | +1% hit, +1% crit |
| 5 | Hover tooltip in talent tree | Should read "...increases your spell critical strike chance by $s2%" |

CHECKED WORKING

---

### 8. Healing Grace (29187/29189/29191)

**What changed:** Threat/dispel resistance replaced with healing crit (via ADD_FLAT_MODIFIER + SPELLMOD_CRIT_CHANCE targeting healing SpellClassMask).

| Step | Action | Expected |
|------|--------|----------|
| 1 | `.aura 29191` (R3) | Talent applied |
| 2 | Check spell crit in character sheet | +6% spell crit on healing spells only |
| 3 | Cast Healing Wave on self multiple times | Crit rate should be noticeably higher than without talent |
| 4 | Cast Lightning Bolt on a mob multiple times | Crit rate should NOT be increased (healing only) |
| 5 | `.unaura 29191`, `.aura 29187` (R1) | +2% healing crit |

CHECKED WORKING

---

### 9. Tidal Focus (16179/16214/16215) — 3 ranks

**What changed:** Reduced to 3 ranks. Mana cost reduction 3/6/10%, cast time reduction 0.1/0.2/0.3s.

| Step | Action | Expected |
|------|--------|----------|
| 1 | Note base Healing Wave cast time and mana cost | Should be ~2.5s, X mana |
| 2 | `.aura 16215` (R3) | Talent applied |
| 3 | Cast Healing Wave, observe cast bar | Cast time reduced by 0.3s (should be ~2.2s) |
| 4 | Check mana cost | Should be 10% less than base |
| 5 | `.unaura 16215`, `.aura 16179` (R1) | Cast time reduced by 0.1s (~2.4s), 3% mana reduction |
| 6 | Test Lesser Healing Wave and Chain Heal | Both should have reduced cast time and cost |
| 7 | Verify talent tree only shows 3 ranks | Should not be able to put more than 3 points in |

CHECKED WORKING - CLIENT DISPLAY ISSUE ON HEALING SPELL TOOLTIPS

---

### 10. Nature's Blessing (30867/30868/30869)

**What changed:** Now boosts spell DAMAGE in addition to healing from intellect (via SPELL_AURA_MOD_SPELL_DAMAGE_OF_STAT_PERCENT aura 174).

| Step | Action | Expected |
|------|--------|----------|
| 1 | Note current spell damage and healing amounts | Baseline |
| 2 | `.aura 30869` (R3, +15% of Int) | Talent applied |
| 3 | Cast Lightning Bolt on a mob, note damage | Should be higher than baseline (15% of your Int added as spell damage) |
| 4 | Cast Healing Wave on self, note healing | Should also be higher (existing healing-from-int effect) |
| 5 | `.unaura 30869` | Both bonuses disappear, damage and healing return to baseline |

CHECKED WORKING

---

### 11. Spirit Weapons (16268 -> teaches 18848 + 36591)

**What changed:** Threat reduction replaced with 25% of Agility as Parry Rating (via SPELL_AURA_MOD_RATING_FROM_STAT, same pattern as DK Forceful Deflection).

| Step | Action | Expected |
|------|--------|----------|
| 1 | Note parry % in character sheet | Baseline parry |
| 2 | Learn Spirit Weapons (or `.aura 18848` + `.aura 36591`) | Parry should jump (flat parry from 18848 + agi-to-parry from 36591) |
| 3 | `.modify agility 500` | Parry should increase proportionally |
| 4 | `.modify agility -500` | Parry drops back |
| 5 | Verify no threat reduction text in tooltip | Should say "Parry Rating by 25% of your Agility" |

CHECKED WORKING

---

### 12. Ancestral Awakening (51556/51557/51558)

**What changed:** After proc heal, also grants guaranteed crit on next damage spell.

| Step | Action | Expected |
|------|--------|----------|
| 1 | `.aura 51558` (R3) | Talent applied |
| 2 | Spawn a friendly NPC or be in a group | Ancestral Awakening needs an injured ally to proc on |
| 3 | `.modify hp 50` on ally (or self if possible) | Get a low-HP target |
| 4 | Spam Healing Wave until you get a critical heal | Ancestral Awakening should proc (heals nearby injured ally) |
| 5 | Check buffs | "Ancestral Fury" (200210) should appear on you — +100% crit |
| 6 | Cast Lightning Bolt on a mob | Should be a guaranteed critical hit |
| 7 | Check buffs again | Ancestral Fury consumed (gone) |
| 8 | Cast another Lightning Bolt | Normal crit chance (not guaranteed) |

CHECKED WORKING

---

### 13. Healing Focus (16181/16230/16232)

**What changed:** Complete redesign — shocks grant instant HW, heals on targets with your Earth/Water/Lightning Shield boost next cast's damage by 25%.

#### Part A: Shock -> Instant Healing Wave

| Step | Action | Expected |
|------|--------|----------|
| 1 | `.aura 16232` (R3, 100% chance) | Talent applied |
| 2 | Cast Earth Shock on a mob | "Surging Focus" buff (200211) should appear |
| 3 | Cast Healing Wave | Should be instant cast and free (0 mana cost) |
| 4 | Check buffs | Surging Focus consumed |
| 5 | Cast Healing Wave again | Normal cast time and mana cost |
| 6 | `.aura 16181` (R1, 33% chance) | Cast shocks repeatedly — only ~1/3 should grant the buff |

#### Part B: Heal on Shielded Target -> Damage Buff

| Step | Action | Expected |
|------|--------|----------|
| 1 | `.aura 16232` (R3) still active | |
| 2 | Cast Earth Shield on yourself (`.aura 974`) | Shield active |
| 3 | Cast Healing Wave on yourself | "Focused Assault" buff (200212) should appear |
| 4 | Check buff details | Should show 25% damage increase, 1 charge |
| 5 | Cast Lightning Bolt on a mob | Should deal +25% damage. After 1 cast, buff consumed. |
| 6 | Cast Healing Wave on a target WITHOUT any shield | Focused Assault should NOT appear |

CHECKED WORKING

---

### Regression Checks

After testing all new talents, verify these existing mechanics still work:

| Check | How |
|-------|-----|
| Existing Chain Heal + Riptide | Still +25% and consumes HoT |
| Lightning Overload | Still procs normally on LB/CL |
| Maelstrom Weapon | Still stacks and grants instant casts |
| Earth Shield | Still heals on damage taken |
| Water Shield | Still restores mana on hit |
| Earthliving Weapon | Base proc still heals (not broken by Purification/Spiritsurge hooks) |
