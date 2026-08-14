# Hunter implementation notes

Implementation detail for the Hunter changes listed in [TODO.md](../TODO.md).
TODO.md records *what* each change is; this file records *how* it was built and
what bit during the build.

Everything here lands in `modules/world_of_alonecraft/data/sql/db-world/`,
files `woa_2026_08_11_00.sql` through `woa_2026_08_11_22.sql`, plus five C++
files in `modules/world_of_alonecraft/src/`.

## Lessons that generalise

Read these before touching another talent — each one cost real time.

**`$h` in a tooltip reads the DBC `ProcChance`, not `spell_proc.Chance`.**
Retail ships `ProcChance = 101` on essentially every talent (a "not applicable"
marker, since a talent aura does not proc on its own), so four redesigned talents
here shipped reading **"101%"** while behaving perfectly. The two numbers are
independent: `SpellMgr.cpp:2065` loads `spell_proc.Chance` and
`Aura::CalcProcChance` (`SpellAuras.cpp:2267`) uses it as-is, falling back to
`spellInfo->ProcChance` only when `Chance` is 0 (`SpellMgr.cpp:2083`). So a wrong
`ProcChance` produces no error, no log line and no gameplay difference — nothing
catches it but reading the tooltip in game. Fixed in `woa_2026_08_11_20.sql`.

Corollary: if the chance lives on a *pet-side carrier* aura, `$h` in the talent
description still reads the **talent's** `ProcChance`, so the talent has to
mirror a number it does not itself use. Superior Training does exactly this;
keep 19572/19573 in step with 200750/200751.

**A proc-triggered cast ignores the target spell's cooldown in both
directions.** `AuraEffect::HandleProcTriggerSpellAuraProc`
(`SpellAuraEffects.cpp:6914`) casts with `triggered = true`, which is
`TRIGGERED_FULL_MASK` (`0x0007FFFF`) and therefore includes
`TRIGGERED_IGNORE_SPELL_AND_CATEGORY_CD`. The cooldown check at
`Spell.cpp:5657` is gated on that flag, and `Spell::SendSpellCooldown`
(`Spell.cpp:4358`) returns before `AddSpellAndCategoryCooldowns`. So the proc
fires while the ability is on cooldown *and* never puts it on cooldown. This is
what makes "X% chance to trigger `<long-cooldown ability>`" work with no clone
and no C++ — Animal Handler → Bestial Wrath, Against the Odds → Beast Cleave.

Two caveats. A proc landing while the aura is already up only **refreshes** the
duration, so procs inside an active window are partly wasted. And a triggered
cast skips `CheckCast`, so a `SpellScript` guard there does not run — Beast
Cleave's `SPELL_FAILED_NO_PET` is silently bypassed by the Against the Odds
proc, which is acceptable only because a petless hunter then simply gets
nothing.

**A triggered cast does not check `HasSpell`.** Consequence: "chance to trigger
`<talent ability>`" is available to anyone who can reach the talent, whether or
not they own the ability. Animal Handler was reachable by a Marksmanship hunter
dipping 25 points into Beast Mastery, who would proc free Bestial Wraths without
the button. Fixed with a talent prerequisite (`woa_2026_08_11_22.sql`) rather
than a `HasSpell` guard in script — the prerequisite fixes the design and shows
up in the client UI.

**`SPELL_AURA_MOD_THREAT` is 10.** 35 is `SPELL_AURA_MOD_INCREASE_ENERGY`, and
getting it wrong fails in the worst possible way: no error, no threat change, and
a silent +100 to a power type instead. Use the symbolic names in
`gen_sql.py dbc --set`, which resolves them, rather than writing integers by
hand. (`SPELL_AURA_MOD_TOTAL_THREAT` is 103 and would not have worked here
either — `SpellAuraEffects.cpp:3570` early-outs for non-players.)

**Talent build links are a wire format, and moving a talent silently rewrites
every existing link.** Links encode one digit per `(tier, col)` slot, so moving a
talent hands its digit to whatever moves into that cell. This pass did it twice:

| Swap | Positions | Caught by the audit? |
|---|---|---|
| Animal Handler ↔ Catlike Reflexes (`_19`) | 14, 18 | **Yes** — decoded to 3 points in Animal Handler, which caps at 2 |
| Taste for Blood ↔ Bestial Discipline (`_23`) | 3, 13 | **No** — 2 points is legal against either talent |

`tools/bot_talents.py audit` validates **rank caps, not intent**. It only fires
when the receiving talent has *fewer* ranks than the digit it inherits. A swap
between talents of equal or larger rank count is completely invisible to it — the
second swap would have silently traded 2 points of Bestial Discipline for 2
points of Taste for Blood in every premade build, and reported clean.

So after any layout change, check the affected digits by hand rather than
trusting a clean audit. Our own override is re-authored each time (digits swapped
alongside the talents, preserving intent). The five Beast Mastery builds in
mod-playerbots' own `conf.dist` have now had their meaning changed twice and
remain legal, so they are left alone — forking all of them into the override
layer to defend against our own layout churn is a decision worth taking
deliberately, not as a side effect. If premade BM bots start looking wrong, that
is the first place to look.

**`tools/export_talents.py` runs one build behind.** `build_and_run.bat` exports
`site/data` *before* copying the new DBCs, so a fresh change needs the export
re-run by hand afterwards — otherwise `bot_talents.py audit` validates against
the previous layout and reports clean. That is exactly what hid the broken build
on the first pass.

## The pet damage/threat trade

TODO.md asks for "20% LESS DAMAGE but 60% MORE THREAT". Those two cannot be
authored independently, because **threat is generated 1:1 from post-mitigation
damage** — `Unit::DealDamage` (`Unit.cpp:1297`) calls
`victim->AddThreat(attacker, float(damage), ...)`. Cutting damage 20% cuts threat
20% as a side effect, so reaching 1.6× the *pre-change* threat needs a **×2.00**
multiplier:

```
damage  0.80 · D
threat  0.80 · D × 2.00 = 1.60 · D
```

Both factors live on one aura (**200743**, `Beastmaster's Bond`) so they cannot
drift apart in a later retune. `Alonecraft.HunterPet.DamagePct` /
`.ThreatPct` expose them; the effective threat is the product of the two, which
is why setting `ThreatPct = 60` would give 1.28× rather than 1.60×.

### One aura reaches white melee *and* every special

Worth proving, because the two travel completely different code paths:

- **White melee** — `Guardian::UpdateDamagePhysical` (`StatSystem.cpp:1352`)
  multiplies by `UNIT_MOD_DAMAGE_MAINHAND TOTAL_PCT`, which
  `Unit::UpdateDamagePctDoneMods` (`Unit.cpp:12203`) sets from
  `SPELL_AURA_MOD_DAMAGE_PERCENT_DONE` filtered on `SPELL_SCHOOL_MASK_NORMAL`.
- **Claw / Bite / Gore** — `SPELL_EFFECT_SCHOOL_DAMAGE`, so they route through
  `SpellDamageBonusDone` → `SpellPctDamageModsDone` (`Unit.cpp:8455`), which
  reads the **same** aura filtered on the spell's own school.
- **No double-dip** — `Unit::MeleeDamageBonusDone` (`Unit.cpp:10276`)
  deliberately skips `MOD_DAMAGE_PERCENT_DONE` for `SPELL_SCHOOL_MASK_NORMAL`,
  because it is already folded into base melee damage.

`EffectMiscValue = 127` is therefore load-bearing on both effects. A MiscValue of
1 covers physical only and silently misses every elemental pet ability
(Lightning Breath, Fire Breath, Scorpid Poison). Threat has the same
requirement: `ThreatManager::UpdateMySpellSchoolModifiers`
(`ThreatManager.cpp:824`) fills `_singleSchoolModifiers[i]` from
`GetTotalAuraMultiplierByMiscMask(SPELL_AURA_MOD_THREAT, 1 << i)` read off the
threat **generator** — the pet — so 127 populates every school slot.

No companion `SpellScript` is needed for `SPELL_EFFECT_THREAT`, unlike
`spell_warl_demon_brutality_threat` (`WarlockDemonPets.cpp:317`). That workaround
exists because `Spell::EffectThreat` passes `ignoreModifiers = true`; no hunter
pet ability carries the effect. Growl (2649) is `SPELL_EFFECT_ATTACK_ME`.

### Delivery is a `PetScript`, not `spell_pet_auras`

`spell_pet_auras` is driven by a `SPELL_AURA_DUMMY` effect on an owner aura
(`AuraEffect::HandleAuraDummy` → `Unit::AddPetAura`, `Unit.cpp:13753`), and a
hunter has no always-on aura to hang one off. `PetScript::OnPetAddToWorld`
(`Pet.cpp:118`) covers summon-from-stable, login and a fresh tame — the same hook
and the same reasoning as `HunterPetLevelSync.cpp`.

Gated on `getPetType() == HUNTER_PET`. Warlock demons already carry their own
balance pass, and a blanket change would silently retune Demonology.

### A latent bug the trade exposed

Beast Cleave's splash **200739** carried `SPELL_ATTR3_SUPPRESS_CASTER_PROCS` but
not `SPELL_ATTR3_IGNORE_CASTER_MODIFIERS`. The `DmgClass`-NONE early return in
`Unit::SpellDamageBonusDone` (`Unit.cpp:8901`) still applies `DoneTotalMod`:

```cpp
return uint32(std::max((float(pdamage) + DoneTotal) * DoneTotalMod, 0.0f));
```

`HunterBeastCleave.cpp` hands it 75% of an already-mitigated, already −20%-ed
hit, so the splash would have landed at 0.8 × 0.8 × 0.75 = **0.48** of baseline
instead of 0.60. Every payload spell in this pass that is fed a pre-computed
amount now carries `0x20000000`.

## Per-talent notes

Only the ones with something to say.

**Endurance Training** — both stat halves were already exactly right in retail
(+2/4/6/8/10% pet health, +1/2/3/4/5% own) and are untouched; only the unused
Effect3 was added. The proc row is shaped like core's own `-19572`, the identical
trigger. `AttributesMask` stays 0 because a `SPELL_AURA_PERIODIC_HEAL` tick
carries no `Spell` object (`SpellAuraEffects.cpp:6704` passes `nullptr`), so
`Aura::IsProcTriggeredOnEvent` never runs its triggered-spell filter. Uses
`GetHeal()` rather than `GetEffectiveHeal()`, so a pet near full health does not
quietly halve the return.

**Taste for Blood** — the bleed must be the **owner's**; `CheckProc` looks up
Lacerating Shot by the owner's GUID, so a second hunter's bleed on the same
target does not feed this pet. Lacerating Shot's `SpellFamilyFlags` are all zero
after its own rework, so family-mask matching is impossible and the three ranks
are listed explicitly. 1s ICD is not caution — a cat at 1.0s swing speed under
Beast Cleave would otherwise turn a percentage of RAP into most of the hunter's
damage.

**Retuned 20/40/60% → 10/20/30% in `woa_2026_08_12_08.sql`**, having measured at
roughly double the intended damage in play. The lesson generalises: a talent
paid out per *pet swing* but scaled off the *hunter's* attack power has its
throughput set by pet attack speed, which no number in the tooltip mentions. The
1s ICD bounds the worst case but does nothing about the sustained rate at swing
speeds slower than 1s, which is where most pets actually sit. Budget these
against pet swings per second, not against the hunter's rotation.

The first tooltip read *"When you attack a target affected by your Lacerating
Shot..."*, which names the wrong attacker: the aura sits on the pet and its proc
flags are `DONE_*`, so the **pet** is the actor and the hunter's own attacks are
irrelevant. Wording came from TODO.md's "When attacking targets affected by
Lacerating Shot", which never says who is attacking. Fixed in
`woa_2026_08_11_21.sql`. Note the name now collides with the Warrior talent
(56636) — harmless in game, but `gen_sql.py talent --name "Taste for Blood"`
returns the Warrior one first.

**Thick Hide** — `spell_warl_demon_dodge` (`WarlockDemonPets.cpp:161`) with three
substitutions: `STAT_AGILITY`, the hunter's `crit_to_dodge` coefficient
(1.11/1.15), and the hunter row in `gtChanceToMeleeCrit`.
`Player::GetDodgeFromAgility` cannot be called directly — it reads the owner's
class off the player it is a method on, and both `dodge_base[]` and
`crit_to_dodge[]` are file-local arrays with no accessor. Keeps the 2s heartbeat,
since owner Agility moves with gear.

**Share the Spoils** — the amplifier is a `SpellScript` on the **energize
payload 34075**, not on the aspect 34074. Core's
`spell_hun_ascpect_of_the_viper` (`spell_hunter.cpp:388`) computes the mana
itself and hands it to 34075 via `CastCustomSpell(SPELLVALUE_BASE_POINT0)`,
consulting exactly one modifier on the way — glyph 56851. An aura on 34074 is
invisible to it and could only energize a *second* time, stacking additively with
the glyph instead of multiplying. Scaling 34075's own effect value composes
correctly and needs no core change.

**Against the Odds** — the empowerment is a **marker** (200749) the splash reads,
not a second "empowered Beast Cleave" spell. A parallel aura would sit alongside
the first, pass `spell_hun_beast_cleave::CheckProc` too, and splash twice on
every swing. The marker also means a manually-cast Beast Cleave inside the window
benefits, which is the intended feel. Both proc-trigger effects live on one aura
and both fire on the same proc, so the trigger side needs no C++ at all. Marker
duration is index 8 (15s) to match Beast Cleave's retuned window — index 35 (4s)
was the pre-retune value and would have left 11 seconds unempowered.

**Superior Training** — core's own `spell_proc -19572` row is **deleted**; the
talent no longer procs on the hunter. Two carriers rather than one because the
50/100% split lives in `spell_proc.Chance`, which is keyed by spell id. The
1.5s ICD is load-bearing: a tank pet holding six mobs takes roughly six swings a
second, and an unthrottled 8-yard retaliation on each is a damage *and* — with
the ×2.00 threat aura — a threat explosion. The idle timer rides the proc handler
rather than `UnitScript::OnDamage`, because the proc already fires on every
incoming hit while a global hook would run for every unit on every map.
Well-Trained's +10% multiplies against the global −20%, giving 0.88× baseline.

**Spirit Bond** — entirely DBC. The retail plumbing is already the right shape
(`APPLY_AREA_AURA_PET` payloads reaching hunter and pet from one cast) and is left
alone. The Mend Pet modifier needs **`SPELLMOD_DOT` (22)**, not `SPELLMOD_DAMAGE`
— Mend Pet is a periodic heal, and `Unit.cpp:9688` picks
`damagetype == DOT ? SPELLMOD_DOT : SPELLMOD_DAMAGE`. The obvious value does
nothing at all. `SpellFamilyName` also had to be set to 9 on both talent ranks;
retail left it 0, and `IsAffectedBySpellMod` requires the families to match.

**Bestial Discipline** — `TARGET_UNIT_PET` is safe here because the caster is the
**hunter**. This is the mirror of the trap at `WarlockDemonPets.cpp:534`, where
32554 broke precisely because the demon was the caster and `Spell.cpp:1794`
resolved `m_caster->GetGuardianPet()` — a pet has no pet.

**Animal Handler** — the +10% pet attack power already worked through
`spell_pet_auras` keyed on **effectId 1**. That effect looks like an inert dummy;
touching it silently deletes the bonus. Retuned from 1/2% to 10/20%: at roughly
one ranged attack every 2 seconds, 2% is one proc per ~100 seconds of sustained
shooting, invisible against a 120s cooldown the hunter also presses manually.

**Catlike Reflexes** — the Kill Command cooldown effect **already existed** in
retail at −10/−20/−30s, with `MiscValue 11` (`SPELLMOD_COOLDOWN`) and all three
class masks zero, so it had never matched anything. Only the mask needed
setting: **`EffectSpellClassMaskC2 = 2048`** — effect *three* (the cooldown
modifier), word *two* (Kill Command's `SpellFamilyFlags1`). An earlier draft of
this note said "B3"; that was written before the column convention was pinned
down, and the applied SQL also left a stray `B3 = 2048` on effect two, which is
inert (effect two is not a spellmod) but should be cleaned up if that file is
ever touched again. It reaches a **category** cooldown, which is worth checking before
trusting: Kill Command has `RecoveryTime 0`, `Category 1171`,
`CategoryRecoveryTime 60000`, and `Player::AddSpellAndCategoryCooldowns`
(`Player.cpp:10988`) applies `SPELLMOD_COOLDOWN` to `catrec` too, gated only on
`SPELL_ATTR6_NO_CATEGORY_COOLDOWN_MODS`, which 34026 lacks.

`HitMask 16` (`PROC_HIT_DODGE`) is the whole trigger mechanism — the proc flags
only say "the pet was attacked".

**Invigoration** — rebuilt from the pet side rather than patched. Core's
`spell_hun_invigoration` (`spell_hunter.cpp:561`) is a `SpellScript` on 53412,
and nothing anywhere in `src/server/` ever casts 53412; the id appears in that
comment and nowhere else, so the talent has never functioned on this core.

Core's 53398 is also not reused for the mana: it is `SPELL_EFFECT_ENERGIZE_PCT`
with an implicit **caster** target, and the caster here is the pet — it would
refill a mana bar the pet does not have. 200744 is cast by the owner on itself
with a computed flat amount.

Instinctive Fire needed a `SpellFamilyFlags` bit before *anything* could modify
it. 1462 was repurposed with `SpellFamilyName 9` but flags 0/0/0, and
`IsAffectedBySpellMod` matches `spellmod->mask & spellInfo->SpellFamilyFlags` —
so the free-cast buff's charge would never have been consumed, with no error to
say why. Bit 21 of the **third** mask word was picked by scanning every family-9
spell in `Spell.dbc`: words 0 and 1 are effectively exhausted (`0xffffffff` and
`0xffffffbf`), and no family-9 `EffectSpellClassMaskC` in the entire DBC sets bit
21, so nothing existing starts modifying Instinctive Fire as a side effect.

## Marksmanship

Files `woa_2026_08_12_00.sql` … `_07.sql`, plus `HunterMarksmanshipHunter.cpp`
and `HunterMarksmanshipPet.cpp`.

### Four of the seven needed no new mechanism

Worth stating first, because the instinct is to rewrite every column:

- **Go for the Throat's Focus half was already right.** 34952/34953 store 24/49,
  which the `$s1` +1 rule renders as **25 and 50** — exactly the agreed split.
  "Fixing" 24 to 50 would have displayed 51.
- **Focused Aim's hit half was already right** at 0/1/2 → 1/2/3%. Effect2 is not
  touched at all.
- **Concussive Barrage is Missile Barrage.** 44401 is the identical design —
  three spellmods on one aura, MiscValue 1 / 19 / 14, base points
  −2501 / −501 / −101, 15s. 200758 is a straight clone with the family moved to
  Hunter and every class mask moved from Arcane Missiles to Volley.
- **Improved Barrage is two columns.** `EffectMiscValue2` 9 → 14 and a sign flip.

### `gen_sql.py dbc --base` cannot clone a custom spell

`--base` reads the binary `Spell.dbc`, so it fails on anything that exists only
in `alonecraft_spell_dbc` — which is every custom spell this fork has made.
Cloning the Beast Mastery pet carriers needed
**`tools/clone_override_spell.py`**, which reads the row back out of the
generated SQL, rewrites named columns and re-emits it. Quoting is decided by
whether the *original* column was quoted, which is the only reliable signal.

### A spellmod buff must NOT have a `spell_proc` row

`Player::RemoveSpellMods` skips any spellmod whose spell has a proc entry
(`Player.cpp:10047`, commented as a temporary workaround), so a `spell_proc` row
on the buff means **the charge is never consumed** and the buff runs its full
duration across many casts. 200758 therefore takes its single charge from the
DBC `ProcCharges` and has no proc row.

Missile Barrage does it the other way round — `ProcCharges 0` in the DBC and
`Charges = 1` in `spell_proc`, dropping the charge through the proc system — so
copying half of each pattern is the failure mode to avoid.

Related: for a **channeled** spell the charge drops at `Spell::finish`, i.e. at
channel *end*. The buff icon visibly lingers for the whole Volley. Cosmetic.

### Two scripts on one spell id is supported, with two rules

`_spellScriptsStore` is a `multimap` (`ObjectMgr.h:390`) and
`Aura::CallScriptEffectProcHandlers` iterates every loaded script
(`SpellAuras.cpp:2723`), so `spell_hun_piercing_shots_lacerate` runs alongside
core's `spell_hun_piercing_shots` and the bleed keeps working. But:

- **No `DoCheckProc`.** `CallScriptCheckProcHandlers` **ANDs** results across
  scripts (`SpellAuras.cpp:2625`), so returning false suppresses the *other*
  script's proc too. The chance roll goes inside the proc handler instead.
- **No `PreventDefaultAction`.** Prevention is global (`SpellAuras.cpp:2734`).

### `spell_proc.Chance = 0` is not "100%"

Core's `-53234` row ships `Chance 0`, which falls back to the DBC `ProcChance`
(`SpellMgr.cpp:2083`). Piercing Shots now needs `ProcChance` 33/66/100 because
`$h` renders the *refresh* chance — so leaving the proc row alone would have
silently dropped the **bleed** to 33% at rank 1. Two numbers that look
redundant and are not: the bleed always happens, the refresh rolls.

### A heal generates threat unless you say otherwise

`Spell::EffectHeal` forwards **50% of the amount healed** as assist threat to
everything fighting the target — `ForwardThreatForAssistingMe(caster, gain *
0.5f, …)` at `Spell.cpp:2776`. `SPELL_ATTR1_NO_THREAT` (`0x400`) short-circuits
it at `ThreatManager.cpp:757`.

Improved Hunter's Mark heals the pet for a share of the hunter's damage, so
without that bit the talent would have handed the **hunter** threat in direct
proportion to their own damage — silently fighting Pack Hunting, Focused Aim and
the entire pet-tanking design, while looking like it worked.

Any Alonecraft heal that fires off the player's damage wants this attribute.

### Pre-computed *healing* is protected differently from pre-computed damage

Both need protecting from being re-scaled, but the early-outs are not
symmetrical, and assuming they are is how 200739 double-dipped:

- **Healing** — `Unit::SpellHealingBonusDone` returns `healamount` **raw** for a
  `SPELL_DAMAGE_CLASS_NONE` spell with no `spell_bonus_data` row
  (`Unit.cpp:9650`).
- **Damage** — the matching NONE early-return in `SpellDamageBonusDone` still
  applies `DoneTotalMod` (`Unit.cpp:8901`), which is why damage payloads also
  need `SPELL_ATTR3_IGNORE_CASTER_MODIFIERS`.

200762 sets `DamageClass 0`, has no bonus row, and carries
`IGNORE_CASTER_MODIFIERS` anyway — the belt-and-braces is cheap and survives
someone later adding a `spell_bonus_data` row.

### Conditional threat has no declarative path

`ThreatManager::CalculateModifiedThreat` (`ThreatManager.cpp:699-718`) exposes
`spell_threat.pctMod` (per **spell**) and `_singleSchoolModifiers` (per
**generator**). Neither can look at the victim, and a pet's white swing carries
no `spellProto` at all (`Unit.cpp:1297`). So Focused Aim's "only on Hunter's
Mark targets" is C++, calling `victim->AddThreat(pet, extra)` with
`spell = nullptr` so the bonus still runs through `CalculateModifiedThreat` and
composes with Beastmaster's Bond instead of sitting outside it.

Read that call carefully: `this` is the **mob** that owns the threat list and the
parameter is the unit **generating** threat (`Unit.cpp:11489`).

### Threat redirection is hard-capped at 100%

An earlier Rapid Killing design asked for "50%/100% more threat *transferred* to
your pet", which is unbuildable without touching core:
`ThreatManager::UpdateRedirectInfo` clamps the running total with
`std::min(100 - totalPct, …)` behind an `ASSERT(totalPct <= 100)`
(`ThreatManager.cpp:937-942`), and redirected threat is re-added with
`ignoreModifiers = true` (`ThreatManager.cpp:442`) so no aura can scale it
either. Worth keeping in mind before promising anything about redirection.

That design is gone (see below), but the ceiling is permanent.

### The class-mask column naming, settled — and a bug it exposed

`EffectSpellClassMask{A|B|C}{1|2|3}`: **the letter is the effect index, the
digit is the `flag96` word.** So `A3` is effect *one*, word *three*; `B1` is
effect *two*, word *one*.

Missile Barrage (44401) settles it beyond argument: three effects that each
modify Arcane Missiles, whose family flag is word0 `0x800`, and it carries
`A1 = B1 = C1 = 2048`. If the letter were the word, all three would be in `A`.

Getting this wrong is silent. **Instinctive Focus (200757)** — Invigoration's
"next Instinctive Fire is free" payload — had its mask in `C1` (effect three,
word one) when its `SPELLMOD_COST` modifier is on effect *one* and Instinctive
Fire's flag is word *three*. Effect1's mask was therefore `(0,0,0)`,
`IsAffectedBySpellMod` never matched, the mana was never refunded, and the
charge was never consumed so the buff just expired. Fixed in
`woa_2026_08_12_09.sql` by moving the value to `A3`.

That bug survived the whole Beast Mastery pass precisely because the failure
mode is nothing happening.

### A spellmod needs a family flag on the spell it modifies, not the one that casts it

Lethal Instincts extends **Instinctive Fire's buff** by 3/6 sec.
`Aura::CalcMaxDuration` (`SpellAuras.cpp:806`) applies `SPELLMOD_DURATION`
against the aura's *own* spell — 200742, the buff — not 1462, the shot that
triggers it. 200742 shipped with `SpellFamilyName 9` but all three flag words
zero, so no mask could ever have matched it and the extension would have done
nothing.

The Beast Mastery pass gave **1462** word2 bit 21 for exactly this reason and
stopped there, because nothing modified the buff yet. When adding a modifier,
check which spell actually owns the value being modified.

200742 was given word2 **bit 22**, deliberately not bit 21: sharing the shot's
bit would make Instinctive Focus's charge-limited cost modifier match the buff
as well, and a one-charge modifier matching two spells is consumed by whichever
the engine reaches first. Bit 22 was verified free by scanning every family-9
record in `Spell.dbc` — no spell carries it, no effect masks it.

**Lacerating Shot** hit the identical wall when Piercing Shots gained a
+2/4/6 sec extension, and for the identical reason: its three ranks were left
`SpellFamilyName 9` with all flag words zero by their own rework. They now share
word2 **bit 23**. The scripts that consume Lacerating Shot are unaffected — they
look it up by id, which is exactly *why* they have to name all three ranks.

Running tally of Alonecraft's word2 bits on family 9: **21** Instinctive Fire,
**22** its buff (200742), **23** Lacerating Shot. Bits 24-27 are free; 0-20 and
31 are retail's.

### Refreshing a duration is not a spell effect

Rapid Killing now has four shots refresh **Pack Hunting's duration**. There is
no "refresh aura" effect in 3.3.5, and the obvious substitute — triggering a
re-cast of 60192 — is wrong twice over: it re-runs
`SPELL_EFFECT_REDIRECT_THREAT` and re-registers the redirect, and it burns the
20s cooldown. `Aura::RefreshDuration` (`SpellAuras.cpp:822`) is the actual
operation, so the talent effect is a plain dummy and the script does the work.

Same shape as Improved Concussive Shot refreshing Instinctive Fire. Both are
"extend something already running", and both are C++ for the same reason.

Note the consequence: Pack Hunting's 20s cooldown and 10s window no longer bound
its uptime, only the gap after the hunter stops shooting.

### A tooltip whose amount comes from C++ cannot use `$sN`

Learned on the 30s pet threat buff that Rapid Killing used to cast: its base
points were 0 by design because the script supplied the amount via
`CastCustomSpell`, so `$s1` would have rendered **0%**. Plain prose only in that
situation. The clone also inherited `Attributes 192`
(`PASSIVE | DO_NOT_DISPLAY`) from Beastmaster's Bond, which would have hidden a
buff meant to be seen.

That spell (200762) was **deleted** rather than left orphaned when the design
changed, and its id returned to the free pool. An unreferenced custom spell
sitting in the DBC is a trap for whoever reads the range next.

### `spell_custom_attr` is keyed by `spell_id`, not `entry`

`spell_threat` uses `entry`, `spell_custom_attr` uses `spell_id`. Getting them
the wrong way round is an immediate SQL error rather than a silent one, which is
the good case.

### Per-talent notes

**Lethal Instincts** (renamed from Improved Concussive Shot, and given
Instinctive Fire's icon 5000) — "refresh" cannot be data. A DBC
`EffectTriggerSpell` of 200742 would *apply* the buff, and a `CasterAuraSpell`
gate does not help because a proc-triggered cast carries
`TRIGGERED_IGNORE_CASTER_AURASTATE` (`SpellDefines.h:145`), bypassing
`Spell.cpp:5756`. The talent aura is a plain dummy and the script refreshes only
what is already there. Its stale `EffectSpellClassMaskA1` (512, Concussive Shot)
is zeroed — a leftover mask on a dummy effect is the `--base` inheritance trap.

The +3/6 sec half is the opposite: a plain `SPELLMOD_DURATION` on Effect2,
deliberately *not* done in the refresh handler, because a spellmod applies to
every application of the buff — including a normal Instinctive Fire cast the
script never sees. `RefreshDuration` then resets to a max that already includes
it. See the two sections above for the family flag it needed and the mask column
it goes in.

**Piercing Shots** carries the same pairing — a scripted refresh of Lacerating
Shot plus a `SPELLMOD_DURATION` extension of it — and the pair composes for the
same reason. But note the asymmetry with Lethal Instincts: extending a *buff*
buys uptime, while extending a **DoT buys ticks**. An aura's tick count is its
max duration over its amplitude, fixed at creation, so +2/4/6 sec on a 10s /
2s-tick bleed is 6/7/8 ticks instead of 5 — a 20/40/60% damage increase, since
the per-tick amount is a fixed share of ranged attack power. Worth pricing
deliberately rather than reading "duration" as a utility change.

**Concussive Barrage** — the three spellmods were each verified rather than
assumed: `SPELLMOD_DURATION` reaches a channel via `Spell::handle_immediate`
(`Spell.cpp:4074-4092`, whose own comment cites Missile Barrage), flat
`SPELLMOD_ACTIVATION_TIME` reaches the tick rate via
`AuraEffect::CalculatePeriodic` (`SpellAuraEffects.cpp:646`), and one aura with
three mods drops exactly one charge (`Player.cpp:10062`). Volley reaches the
channel path despite `Speed 30.0` because `Spell::cast` only defers when
`Speed > 0 && !IsChanneled()` (`Spell.cpp:3941`).

**Go for the Throat** — two proc layers, and the crit belongs to exactly one of
them. The hunter's ranged crit (core's `spell_proc -34950`, `HitMask 2`,
untouched) fires the talent aura; **both** of its proc-trigger effects go off on
that one event — Effect1 sends Focus to the pet, Effect2 applies a 10s frenzy
(200760) to it. Inside that window **every** pet melee hit rends, so 200760's
own row has `HitMask 0`.

The first version required a crit in *both* places, which made the talent far
rarer than it reads. If a talent says "X causes Y to do Z", check which of X and
Y the conditions actually belong to.

Effect2 doubles as the rank store: a `PROC_TRIGGER_SPELL` effect still carries an
amount, so `OwnerTalentAmount(..., EFFECT_1)` reads 25/50 off it unchanged when
the effect stops being a dummy.

The frenzy reaches the pet the same way retail's Focus payload does:
`HandleProcTriggerSpellAuraProc` casts
`triggerCaster->CastSpell(triggerTarget, …)` (`SpellAuraEffects.cpp:6914`) with
the hunter as caster and the *mob* as explicit target, and 200760's own
`EffectImplicitTargetA1 = 5` (`TARGET_UNIT_PET`) resolves the pet for the effect.
Because the aura is now applied dynamically, there are **no `spell_pet_auras`
rows** for it — that table is only for auras a pet should always have.

`SPELL_ATTR3_SUPPRESS_TARGET_PROCS` is deliberately **not** set on the bleed
payload: it reads as "no initial aggro" and `ThreatManager::AddThreat`
early-returns on it before engagement (`ThreatManager.cpp:399`), which would kill
the threat half on exactly the pull the talent exists for.

## Files

| Area | Where |
|---|---|
| Pet damage/threat trade | `HunterPetTuning.cpp`, `woa_2026_08_11_07.sql` |
| Shared pet-talent plumbing | `PetTalentHelpers.h` |
| Pet-side talent auras | `HunterBeastMasteryPet.cpp`, `HunterMarksmanshipPet.cpp` |
| Hunter-side talent auras | `HunterBeastMasteryHunter.cpp`, `HunterMarksmanshipHunter.cpp` |
| Beast Cleave + Against the Odds | `HunterBeastCleave.cpp` |
| Beast Mastery talents, one file each | `woa_2026_08_11_08.sql` … `_18.sql` |
| BM grid swap / `$h` fixes / tooltip fix / prerequisite | `_19`, `_20`, `_21`, `_22`, `_23` |
| Marksmanship talents, one file each | `woa_2026_08_12_00.sql` … `_06.sql` |
| MM grid swap | `woa_2026_08_12_07.sql` |
| Taste for Blood retune | `woa_2026_08_12_08.sql` |
| Instinctive Focus mask fix | `woa_2026_08_12_09.sql` |
| Improved Hunter's Mark pet leech | `woa_2026_08_12_10.sql` |
| Cloning a custom spell | `tools/clone_override_spell.py` |

Custom spell ids **200743–200762**; next free is 200763.  (200762 was briefly
freed when the Rapid Killing threat buff was dropped, then reused for Improved
Hunter's Mark's pet heal.)

## Still unverified in game

Nothing in either pass has been confirmed on a live character.

Beast Mastery — highest-risk item: Multi-Shot must not put the hunter's own
Beast Cleave button on cooldown. The code path says it cannot (see the
triggered-cast lesson above), but that deserves a real pull.

Marksmanship — the SQL is applied to the live database and
`tools/verify_scripts.py --db` is clean, but **the C++ is not compiled and the
DBC/MPQ is not rebuilt**, so none of it is in a client yet. In particular:

- Piercing Shots at rank 1 must still bleed on **every** crit (100%), not 33%.
  That is the one change here that can quietly nerf an ability that already
  worked.
- Multi-Shot → next Volley should be free, 3.5s, and land **seven** ticks.
- The Instinctive Fire buff must never appear on a hunter who has not pressed
  the button.
- Focused Aim must not fire off another hunter's Hunter's Mark.
- Go for the Throat: one ranged crit should put a visible 10s buff on the pet,
  and **every** pet swing during it should rend — not just its crits. Watch the
  rate here; this is the same unbounded-per-swing shape that made Taste for
  Blood twice its intended damage.
- Rapid Killing: Pack Hunting should stay up indefinitely while shooting, and
  its 20s cooldown must **not** start over when the duration refreshes.

After the build: re-run `tools/export_talents.py` by hand (step 3.6 runs before
the DBCs are copied), commit `site/data/`, then diff digits 0 and 6 of the
Marksmanship link — `bot_talents.py audit` cannot see this swap.
