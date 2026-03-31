# Death Knight — Alonecraft Implementation Plan

## Context
All 3 DK specs (Blood, Frost, Unholy) need talent reworks for solo play. This is the largest class rework yet — 29 talents + 1 class signature skill. Many existing DK scripts in `spell_dk.cpp` already handle the base versions of these talents, so we'll be overriding/extending rather than starting from scratch.

## Key Technical Facts
- DK SpellFamilyName = 15 (`SPELLFAMILY_DEATHKNIGHT`)
- Disease detection: `SpellFamilyFlags[2] & 0x2` matches Blood Plague (55078) + Frost Fever (55095)
- Presence handler: unified `spell_dk_presence` handles all 3 (Blood 48266, Frost 48263, Unholy 48265)
- Existing scripts we'll override/extend: `spell_dk_vendetta`, `spell_dk_mark_of_blood`, `spell_dk_will_of_the_necropolis`, `spell_dk_bone_shield`, `spell_dk_anti_magic_zone`, `spell_dk_hungering_cold`, `spell_dk_unholy_blight`, `spell_dk_presence`, `spell_dk_improved_blood/frost/unholy_presence`
- Custom spell IDs: 200105–200130 range
- SQL files start at `2026_03_30_09.sql`

## Shared Utility: Disease Counter
Multiple talents need to count diseases on a target. Create a shared inline helper:
```cpp
// In a shared header or at top of files that need it
inline uint8 CountDiseases(Unit* target, ObjectGuid casterGuid) {
    uint8 count = 0;
    // Blood Plague, Frost Fever, Crypt Fever, Ebon Plague
    for (uint32 id : {55078u, 55095u, 50508u, 51726u})
        if (target->GetAura(id, casterGuid)) ++count;
    return count;
}
```

---

## Phase 1 — SQL-Only Talent Overrides ✅
*No C++ needed. Pure `alonecraft_spell_dbc` overrides.*

| Talent | Spell IDs | Change |
|--------|-----------|--------|
| **Subversion** | 48997/49490/49491 | Replace threat reduction (Effect1) with `SPELL_AURA_MOD_PARRY_PERCENT` (2/4/6%) |
| **Virulence** | 48962/49567/49568 | Add Effect3: `ADD_FLAT_MODIFIER` + `SPELLMOD_DURATION` on diseases (+2/4/6 sec) |
| **Anticipation** | 55129–55133 | Add Effect2: `ADD_PCT_MODIFIER` + `SPELLMOD_DAMAGE` on diseases (2/4/6/8/10%) |
| **Anti-Magic Zone** | 50461 + 51052 | Reduce absorption 75%→37%, remove absorb pool cap |
| **Unholy Command** | 49588/49589 | Increase Death Grip cooldown reduction to -10/-20 sec |

**SQL files:** `2026_03_31_00.sql` through `2026_03_31_04.sql`

**Tools:** `python tools/gen_sql.py lookup` to inspect current talent spell data, then `python tools/gen_sql.py dbc` to generate overrides.

---

## Phase 2 — Blood Tree (C++ + SQL)

### 2a. Runic Power Mastery (49455/50147) — 2 ranks only
- **Script type:** AuraScript (proc on runic power spend)
- **Pattern:** `Gnosticism.cpp` — proc handler that heals on resource spend
- **Custom spells:** 200105 (heal spell)
- **File:** `RunicPowerMastery.cpp`
- **SQL:** DBC override to add max RP increase + DUMMY effect for heal chance

### 2b. Improved Rune Tap (48985/49488/49489)
- **Script type:** SpellScript on Rune Tap (48982)
- **Pattern:** `Martyrdom.cpp` — apply buff after spell cast
- **Custom spells:** 200106 (damage buff: +X% Heart Strike/Death Strike for Ys)
- **File:** `ImprovedRuneTap.cpp`
- **How:** AfterCast checks for talent, applies damage buff aura

### 2c. Bloody Lesions (replacing Vendetta 49015/50154/55136)
- **Script type:** SpellScript on Blood Boil (-48721)
- **Pattern:** `FocusedPower.cpp` (DoT spreading) + `PriestRefreshDots.cpp` (disease refresh)
- **Custom spells:** 200107 (bleed DoT)
- **File:** `BloodyLesions.cpp`
- **How:** Override existing `spell_dk_vendetta`. Blood Boil AfterHit applies bleed DoT + refreshes diseases on each target hit. Existing `spell_dk_blood_boil` already has an AfterHit — we add to it or replace.
- **Existing script:** `spell_dk_vendetta` (registered to -49015) — will be replaced in `spell_script_names`

### 2d. Mark of Blood Rework (49005)
- **Script type:** AuraScript (replacing existing `spell_dk_mark_of_blood`)
- **Pattern:** Reverse `FireLeech.cpp` — self-healing reflects to marked enemy
- **Custom spells:** 200108 (armor pen buff on parry)
- **File:** `MarkOfBloodRework.cpp`
- **How:** When DK heals self, X% dealt as damage to marked target. On parry of marked enemy's attack, gain armor pen buff. Replace existing `spell_dk_mark_of_blood` registration.
- **Complexity note:** Parry detection needs UnitScript `OnDamage` or similar hook

### 2e. Will of the Necropolis Extension (52284/52285/52286)
- **Script type:** SpellScript on Heart Strike (-55050)
- **Pattern:** `Firebreak.cpp` (stacking buff on hit)
- **Custom spells:** 200109 (stacking parry buff)
- **File:** `WillOfTheNecropolis.cpp`
- **How:** Heart Strike AfterHit checks for Will talent, applies/refreshes stacking parry buff

### 2f. Improved Blood Presence (50365/50371)
- **Script type:** AuraScript extending existing `spell_dk_improved_blood_presence`
- **Pattern:** `Lightform.cpp` (linked aura management)
- **Custom spells:** 200110 (retained healing aura for other presences), 200111 (bonus damage aura)
- **File:** `PresenceImprovements.cpp` (shared with Frost/Unholy)
- **How:** Override presence talent DBC to remove rune cost. Apply retained-benefit aura when switching away from Blood. All 3 improved presence talents share one file.

---

## Phase 3 — Frost Tree (C++ + SQL)

### 3a. Chillblains (50040/50041)
- **Script type:** AuraScript on Frost Fever (55095)
- **Pattern:** `FireLeech.cpp` (periodic health drain)
- **Custom spells:** 200112 (health drain periodic)
- **File:** `Chillblains.cpp`
- **How:** When Frost Fever ticks on a Chilled target, drain X health and transfer to DK

### 3b. Hungering Cold Rework (49203)
- **Script type:** SpellScript + AuraScript
- **Pattern:** `Martyrdom.cpp` (on-remove trigger)
- **Custom spells:** 200113 (health drain on thaw)
- **File:** `HungeringColdRework.cpp`
- **How:** On cast, apply Frost Fever to all frozen targets. On freeze removal, drain health. Existing `spell_dk_hungering_cold` only blocks disease dispel procs — extend it.

### 3c. Improved Frost Presence (50384/50385)
- **Part of:** `PresenceImprovements.cpp` (Phase 2f)
- **Custom spells:** 200114 (retained armor aura), 200115 (damage reduction aura)

### 3d. Acclimation (49200/49201/49202)
- **Existing script:** `spell_dk_acclimation` already applies school-specific resistance buffs (50490, 50362, 50485, 50486, 50489, 50488)
- **Change:** DBC override to increase resistance values. Likely SQL-only unless we want to add additional damage reduction %.

### 3e. Magic Siphon (replacing Magic Suppression 49224/49610/49611)
- **Script type:** AuraScript on AMS (48707)
- **Pattern:** `PermafrostAbsorb.cpp` (absorb + heal)
- **Custom spells:** 200116 (heal-on-absorb)
- **File:** `MagicSiphon.cpp`
- **How:** Extend existing `spell_dk_anti_magic_shell_self`. After absorb, heal for Y% of absorbed amount. DBC override increases AMS absorb %.

---

## Phase 4 — Unholy Tree Core (C++ + SQL)

### 4a. Epidemic (49036/49562)
- **Script type:** AuraScript (proc on shadow damage)
- **Pattern:** `Firebreak.cpp` (count-based scaling)
- **File:** `EpidemicRework.cpp`
- **How:** On shadow damage dealt, count diseases on target, multiply damage by X% per disease

### 4b. Crypt Fever Rework (49032/49631/49632)
- **Script type:** AuraScript on disease application
- **Pattern:** `MarkOfPenitence.cpp` (DoT with extra effects)
- **Custom spells:** 200117 (Crypt Fever DoT component)
- **File:** `CryptFeverRework.cpp`
- **How:** When diseases applied, also apply Crypt Fever debuff that increases disease damage taken + deals periodic damage. Existing Crypt Fever (50508) already exists as a debuff — extend it with DoT.

### 4c. Ebon Plaguebringer Rework (51099/51160/51161)
- **Script type:** Same pattern as Crypt Fever
- **Custom spells:** 200118 (Ebon Plague DoT component)
- **File:** `EbonPlaguebringerRework.cpp`
- **How:** Extend Ebon Plague (51726) with periodic damage component

### 4d. Hungry Dead (replaces existing Master of Ghouls behavior)
- **Script type:** AuraScript on ghoul attacks
- **Pattern:** `Firebreak.cpp` (count-based damage scaling)
- **Custom spells:** 200119 (pet damage buff per disease)
- **File:** `HungryDead.cpp`
- **How:** Ghoul damage modified by owner's disease count on target. Apply via owner aura that procs on pet damage.

### 4e. Desecration Rework (55666/55667/55668)
- **Script type:** DBC override to change proc trigger + AuraScript
- **Custom spells:** 200120 (disease damage boost area aura)
- **File:** `DesecrationRework.cpp`
- **How:** Change trigger from Plague/Scourge Strike to Blood Strike/Blood Boil via SpellClassMask DBC change. Add disease damage boost to ground effect.

---

## Phase 5 — Complex Unholy + Replacements (C++ + SQL)

### 5a. Unholy Blight Modification (49194)
- **DBC change:** Remove dispel protection attribute flag
- **Custom spells:** 200121 (hit reduction debuff)
- **File:** `UnholyBlightMod.cpp`
- **How:** Extend existing `spell_dk_unholy_blight` — when DoT applied, also apply hit reduction

### 5b. Grim Prophecy (replacing Corpse Explosion 49158/51325/51326)
- **Script type:** AuraScript (proc on Scourge/Death Strike with 2H weapon)
- **Pattern:** `Firebreak.cpp`
- **Custom spells:** 200122 (parry chance buff)
- **File:** `GrimProphecy.cpp`
- **How:** CheckProc verifies 2H weapon equipped + correct spell, HandleProc applies parry buff

### 5c. Harvest of Souls (replacing On a Pale Horse 51986/51988)
- **Script type:** Periodic AuraScript (area scan while in Unholy Presence)
- **Pattern:** `FocusedPower.cpp` (cell visitor) + `FireLeech.cpp` (drain)
- **Custom spells:** 200123 (life drain spell)
- **File:** `HarvestOfSouls.cpp`
- **How:** Periodic tick scans nearby enemies, drains health from diseased ones. Only active in Unholy Presence.

### 5d. Improved Unholy Presence (50391/50392)
- **Part of:** `PresenceImprovements.cpp` (Phase 2f)
- **Custom spells:** 200124 (retained haste aura), 200125 (attack speed aura)

### 5e. Bone Shield Rework (49222)
- **Script type:** Extend existing `spell_dk_bone_shield`
- **File:** `BoneShieldRework.cpp`
- **How:** Add proc: on melee hit dealt, chance to gain a charge. 1s ICD. Use `GetAura()->SetCharges(current + 1)`.

### 5f. Master of Ghouls (52143)
- **Script type:** SpellScript on Raise Dead (46584) + Army (42650)
- **File:** `MasterOfGhoulsRework.cpp`
- **How:** After Raise Dead cast, summon additional ghoul(s). After Army cast, double summon count. Most complex pet manipulation.

### 5g. Summon Abomination (replacing Gargoyle 49206)
- **Mostly SQL:** Change creature_template to use abomination model for gargoyle summon entry
- **DBC:** Override spell name/description

---

## Custom Spell ID Allocation

| ID | Spell | Phase |
|----|-------|-------|
| 200105 | Runic Power Mastery heal | 2a |
| 200106 | Improved Rune Tap damage buff | 2b |
| 200107 | Bloody Lesions bleed DoT | 2c |
| 200108 | Mark of Blood armor pen buff | 2d |
| 200109 | Will of the Necropolis parry stack | 2e |
| 200110 | Blood Presence retained healing | 2f |
| 200111 | Blood Presence bonus damage | 2f |
| 200112 | Chillblains health drain | 3a |
| 200113 | Hungering Cold thaw drain | 3b |
| 200114 | Frost Presence retained armor | 3c |
| 200115 | Frost Presence damage reduction | 3c |
| 200116 | Magic Siphon heal-on-absorb | 3e |
| 200117 | Crypt Fever DoT | 4b |
| 200118 | Ebon Plague DoT | 4c |
| 200119 | Hungry Dead pet buff | 4d |
| 200120 | Desecration disease damage boost | 4e |
| 200121 | Unholy Blight hit reduction | 5a |
| 200122 | Grim Prophecy parry buff | 5b |
| 200123 | Harvest of Souls drain | 5c |
| 200124 | Unholy Presence retained haste | 5d |
| 200125 | Unholy Presence attack speed | 5d |

---

## SQL File Sequence

| File | Content |
|------|---------|
| `2026_03_30_09.sql` | Phase 1 SQL-only talent overrides (Subversion, Virulence, etc.) |
| `2026_03_30_10.sql` | Custom helper spells in `alonecraft_spell_dbc` (200105–200129) |
| `2026_03_30_11.sql` | `spell_proc` entries for DK talent procs |
| `2026_03_30_12.sql` | `spell_script_names` bindings |
| Later files as needed per phase |

---

## New C++ Files (14 total)

| File | Talents Covered |
|------|----------------|
| `RunicPowerMastery.cpp` | Runic Power Mastery |
| `ImprovedRuneTap.cpp` | Improved Rune Tap |
| `BloodyLesions.cpp` | Bloody Lesions (Vendetta replacement) |
| `MarkOfBloodRework.cpp` | Mark of Blood |
| `WillOfTheNecropolis.cpp` | Will of the Necropolis extension |
| `PresenceImprovements.cpp` | All 3 Improved Presence talents |
| `Chillblains.cpp` | Chillblains |
| `HungeringColdRework.cpp` | Hungering Cold |
| `MagicSiphon.cpp` | Magic Siphon (Magic Suppression) |
| `EpidemicRework.cpp` | Epidemic |
| `CryptFeverRework.cpp` | Crypt Fever |
| `EbonPlaguebringerRework.cpp` | Ebon Plaguebringer |
| `HungryDead.cpp` | Hungry Dead |
| `DesecrationRework.cpp` | Desecration |
| `UnholyBlightMod.cpp` | Unholy Blight |
| `GrimProphecy.cpp` | Grim Prophecy (Corpse Explosion) |
| `HarvestOfSouls.cpp` | Harvest of Souls (On a Pale Horse) |
| `BoneShieldRework.cpp` | Bone Shield |
| `MasterOfGhoulsRework.cpp` | Master of Ghouls |

---

## Verification — Automated (Every Phase)

After each phase, before going in-game:
1. `python tools/verify_scripts.py` — check C++ ↔ SQL ↔ loader consistency
2. `python tools/verify_db.py --spell-ids <ids>` — confirm SQL applied
3. `python tools/gen_sql.py lookup --spell-id <id>` — verify DBC overrides

---

## In-Game Test Plan

### Setup
- `.tele moonglade` (quiet area, no random aggro)
- `.modify hp 99999` on self so you survive testing
- `.npc add temp 31146` to spawn a target dummy (or any melee-capable mob)
- `.aura <talent_id>` to apply talents without respeccing between tests
- `.unaura <id>` to remove
- `.damage <amount>` to simulate incoming damage when needed
- Combat log addon (or `/combatlog`) to verify proc/heal/damage values

### GM Commands Reference
| Command | Purpose |
|---------|---------|
| `.aura <id>` | Apply a talent/buff aura |
| `.unaura <id>` | Remove an aura |
| `.cast <id>` | Cast a spell |
| `.damage <amt>` | Deal damage to selected target |
| `.die` | Kill selected target |
| `.revive` | Revive self |
| `.modify hp <n>` | Set max HP |
| `.npc add temp <entry>` | Spawn temporary NPC |
| `.talent learn all` / `.talent reset` | Fast respec |
| `.combatlog` | Toggle combat logging |

---

### Phase 1 — SQL-Only Talents

**1. Subversion (threat → parry)**
- `.talent reset` then spec into Subversion (all ranks)
- Open character sheet, note parry %
- `.unaura` the talent, confirm parry % drops
- **Pass:** Parry increases per rank. No threat reduction tooltip/effect.

**2. Virulence (spell hit + disease duration)**
- Spec into Virulence
- Apply Frost Fever (Icy Touch) and Blood Plague (Plague Strike) to a target
- Note disease durations in debuff tooltip
- `.unaura` talent, reapply diseases, compare durations
- **Pass:** Disease durations are longer with talent. Spell hit still works (check character sheet).

**3. Anticipation (dodge + disease damage)**
- Spec into Anticipation
- Note dodge % in character sheet — confirm increase per rank
- Apply diseases to target, note tick damage
- Remove talent, reapply diseases, compare tick damage
- **Pass:** Dodge increases. Disease ticks hit harder with talent.

**4. Anti-Magic Zone (reduced absorption)**
- Cast Anti-Magic Zone
- Have a caster mob (`.npc add temp` a caster) attack you inside the zone
- Compare damage taken inside vs outside
- **Pass:** Reduction is noticeably less than vanilla 75% (should be ~37.5%). No absorb cap (zone doesn't expire from absorbing too much).

**5. Unholy Command (Death Grip cooldown)**
- Spec into Unholy Command
- Use Death Grip, check cooldown timer
- Remove talent, use Death Grip again, compare cooldown
- **Pass:** Cooldown is shorter with talent.

---

### Phase 2 — Blood Tree

**2a. Runic Power Mastery (RP spend → heal chance + max RP)**
- Spec into talent
- Check max RP in character sheet — should be increased
- Build up RP on a target, then spend it (Death Coil, Frost Strike, etc.)
- Watch for heal procs in combat log
- Spam RP spenders ~20 times, count heal procs
- **Pass:** Max RP is higher. Heals proc at expected rate when spending RP. No heal procs when NOT spending RP.

**2b. Improved Rune Tap (damage buff after Rune Tap)**
- Spec into Improved Rune Tap
- Note Heart Strike / Death Strike damage on a target (hit a few times, average)
- Use Rune Tap
- Immediately check for buff aura (200106) — should appear
- Hit with Heart Strike / Death Strike again, note damage increase
- Wait for buff to expire, confirm damage returns to normal
- **Pass:** Buff appears after Rune Tap. Heart Strike and Death Strike hit harder during buff. Buff has correct duration. Other strikes (e.g., Obliterate) are NOT buffed.

**2c. Bloody Lesions (Blood Boil → bleed + disease refresh)**
- Spec into talent (replaces Vendetta)
- Apply diseases to 2+ mobs (Plague Strike + Icy Touch)
- Wait ~10s so diseases have partially ticked down
- Cast Blood Boil
- Check: (1) bleed DoT (200107) appears on all targets hit, (2) diseases refreshed to full duration
- **Pass:** All Blood Boil targets get the bleed DoT. Disease durations reset. Bleed ticks for expected damage. No bleed without the talent.

**2d. Mark of Blood Rework (self-heal → enemy damage + parry → armor pen)**
- Spec into Mark of Blood
- Apply Mark of Blood to a target mob
- Use Death Strike (self-heal) — watch combat log for damage dealt to marked enemy
- Let the marked mob attack you — watch for parry events
- On parry: check for armor pen buff (200108)
- **Pass:** Self-healing causes proportional damage to marked target. Parrying marked enemy's attack grants armor pen buff. Healing from OTHER sources (potion, bandage) also triggers damage. No effect on unmarked enemies.

**2e. Will of the Necropolis Extension (Heart Strike → parry stacks)**
- Spec into Will of the Necropolis
- Note parry % before combat
- Hit a target with Heart Strike 3-5 times
- Check for stacking parry buff (200109) — note stack count and parry % increase
- Stop attacking — confirm buff eventually expires
- **Pass:** Each Heart Strike adds a stack. Parry % increases per stack. Stacks cap at expected maximum. Buff expires after expected duration. Other strikes don't add stacks.

**2f. Improved Blood Presence (no rune cost swap + damage + retained healing)**
- Spec into Improved Blood Presence
- Start in Frost Presence
- Switch to Blood Presence — note: NO rune cost consumed
- Check for bonus damage aura (200111)
- Switch to Frost Presence — check for retained healing aura (200110)
- Heal from Death Strike in Frost Presence — confirm healing still works
- **Pass:** Presence swap costs no runes. Bonus damage in Blood. Healing retained in Frost/Unholy. Without talent, swapping DOES cost runes.

---

### Phase 3 — Frost Tree

**3a. Chillblains (Frost Fever → slow + health drain)**
- Spec into Chillblains
- Apply Frost Fever to a mob (Icy Touch)
- Watch combat log as Frost Fever ticks
- Confirm: (1) mob is slowed, (2) health drain ticks appear, (3) you are healed for the drained amount
- **Pass:** Slowed targets take periodic drain. DK receives healing equal to drain. No drain without talent. Drain scales with talent rank.

**3b. Hungering Cold Rework (freeze + Frost Fever + drain on thaw)**
- Gather 3+ mobs near you
- Cast Hungering Cold
- Check all frozen mobs: (1) frozen in place, (2) Frost Fever applied to all
- Wait for freeze to expire (or `.unaura` the freeze)
- Watch combat log for health drain on thaw (200113)
- **Pass:** All targets get Frost Fever. Health is drained when freeze ends. Drain amount transferred to DK as healing.

**3c. Improved Frost Presence (no rune cost + DR + retained armor)**
- Same test pattern as 2f but for Frost
- Switch presences — no rune cost
- In Frost: check damage reduction aura (200115)
- In Blood/Unholy: check retained armor aura (200114)
- Take hits in Blood Presence — confirm armor is still boosted
- **Pass:** Same criteria as 2f adapted for Frost bonuses.

**3d. Acclimation (spell hit → school DR)**
- Spec into Acclimation
- Spawn a caster mob, let it hit you with a fire spell
- Check for fire resistance buff (existing buff, but verify increased values)
- Get hit by frost spell — check for frost resistance buff
- Confirm they're separate buffs and can coexist
- **Pass:** Getting hit by a spell school triggers school-specific DR. Multiple schools can be active. Values are higher than vanilla.

**3e. Magic Siphon (AMS absorbs more + heals)**
- Spec into Magic Siphon
- Note AMS absorb total (cast AMS, hover tooltip or check aura)
- Confirm absorb amount is larger than base
- Cast AMS, get hit by spells
- Watch combat log for healing (200116) proportional to absorbed damage
- **Pass:** AMS absorbs more total damage. Heals you for Y% of damage absorbed. No heal without talent.

---

### Phase 4 — Unholy Tree

**4a. Epidemic (per-disease shadow damage boost)**
- Spec into Epidemic
- Hit target with a shadow spell (Death Coil), note damage — NO diseases
- Apply 1 disease, hit with Death Coil, note damage increase
- Apply 2 diseases, hit with Death Coil, note further increase
- **Pass:** Shadow damage scales linearly with disease count. 0 diseases = no bonus. Formula matches expected X% per disease per talent rank.

**4b. Crypt Fever Rework (disease damage taken + DoT)**
- Spec into Crypt Fever
- Apply diseases to target
- Confirm Crypt Fever debuff appears on target
- Note disease tick damage WITH Crypt Fever vs without (test on two identical mobs)
- Check for additional periodic damage from Crypt Fever DoT (200117)
- **Pass:** Crypt Fever auto-applies when diseases land. Disease ticks hit harder on debuffed target. Extra DoT ticks visible in combat log.

**4c. Ebon Plaguebringer Rework (magic damage taken + DoT)**
- Same test as 4b but for magic damage
- Apply diseases → Ebon Plague appears
- Hit with Death Coil (shadow/magic) — note damage increase vs non-debuffed target
- Check for Ebon Plague DoT ticks (200118)
- **Pass:** Magic damage increased on debuffed target. Extra DoT ticking. Stacks with Crypt Fever for massive disease pressure.

**4d. Hungry Dead (ghoul damage per disease)**
- Spec into Hungry Dead
- Summon ghoul (Raise Dead)
- Set ghoul on a target with 0 diseases — note ghoul damage per hit
- Apply 1 disease, watch ghoul damage
- Apply 2 diseases, watch ghoul damage
- **Pass:** Ghoul damage increases per disease on target. Scales linearly. No bonus with 0 diseases.

**4e. Desecration Rework (Blood Strike/Boil triggers + disease damage boost)**
- Spec into Desecration
- Use Blood Strike or Blood Boil near enemies
- Confirm Desecration ground effect appears under you
- Check: (1) enemies in area are slowed, (2) disease damage on slowed targets is boosted
- Use Plague Strike — confirm it does NOT trigger Desecration (old trigger removed)
- **Pass:** Blood Strike/Boil triggers ground effect. Enemies slowed. Disease ticks harder in the zone. Plague/Scourge Strike no longer triggers it.

---

### Phase 5 — Complex Unholy

**5a. Unholy Blight Mod (no dispel protection + hit reduction)**
- Cast Unholy Blight
- Check: DoT is now dispellable (have a friendly NPC try to cleanse, or check attributes)
- Check target for hit reduction debuff (200121)
- Note if target's attacks miss more often
- **Pass:** Unholy Blight DoT can be dispelled. Targets under the DoT have reduced hit chance.

**5b. Grim Prophecy (2H Scourge/Death Strike → parry)**
- Equip a 2H weapon
- Spec into Grim Prophecy (replaces Corpse Explosion)
- Use Scourge Strike or Death Strike
- Check for parry buff (200122) — note parry % increase
- Equip dual wield — repeat Scourge Strike
- **Pass:** Parry buff appears with 2H weapon. Does NOT appear with dual wield. Proc chance matches expected X%.

**5c. Harvest of Souls (Unholy Presence life drain)**
- Spec into talent (replaces On a Pale Horse)
- Switch to Unholy Presence
- Stand near diseased enemies (apply diseases first)
- Watch combat log for periodic health drain (200123) every Y seconds
- Switch to Blood Presence — confirm drain STOPS
- Stand near non-diseased enemies in Unholy Presence — confirm NO drain
- **Pass:** Only drains in Unholy Presence. Only drains diseased enemies. Drain scales with disease count. Heals DK for drained amount.

**5d. Improved Unholy Presence**
- Same test pattern as 2f/3c for Unholy
- No rune cost to swap. Attack speed buff in Unholy. Retained haste in other presences.

**5e. Bone Shield Rework (attacks can add charges)**
- Cast Bone Shield, note starting charges (usually 3-4)
- Attack a target continuously in melee
- Watch Bone Shield charge count — should occasionally tick UP
- Count hits vs charge gains over ~30 seconds to estimate proc rate
- **Pass:** Charges increase on melee hit at expected rate. 1s ICD prevents rapid stacking. Still loses charges on damage taken (vanilla behavior preserved).

**5f. Master of Ghouls (extra summons)**
- Spec into Master of Ghouls
- Cast Raise Dead — count ghouls summoned (should be more than 1)
- Cast Army of the Dead — count soldiers (should be ~2x normal)
- Without talent: cast both again, confirm normal counts
- **Pass:** Extra ghouls from Raise Dead. Double army count. Ghouls behave normally (attack, respond to commands).

**5g. Summon Abomination (visual swap)**
- Cast Summon Gargoyle (now Abomination)
- Confirm: (1) creature model is an abomination, not a gargoyle, (2) spell name/tooltip updated, (3) damage/duration unchanged
- **Pass:** It's an abomination. It does damage. It despawns normally.

---

### Regression Tests (Run After All Phases)

These ensure we haven't broken existing DK functionality:

1. **Disease spreading:** Pestilence still spreads Blood Plague + Frost Fever + Crypt Fever + Ebon Plague correctly
2. **Death Strike healing:** Still heals based on damage taken (base behavior intact)
3. **Dancing Rune Weapon:** Still functions, doesn't try to cast new custom spells
4. **Icebound Fortitude:** DR still works, defense scaling intact
5. **Killing Machine:** Still procs guaranteed crits
6. **Sudden Doom:** Still procs free Death Coils
7. **Presence switching:** All 3 presences switch cleanly, no stuck auras
8. **Gargoyle/Army timing:** Summons still despawn at correct time
9. **Rune regeneration:** Normal rune regen unaffected by changes
10. **PvP set bonuses:** T10 bonuses still apply (low priority but worth a quick check)
