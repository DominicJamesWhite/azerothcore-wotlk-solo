# Warrior implementation notes

Implementation detail for the Warrior changes listed in [TODO.md](../TODO.md).
TODO.md records *what* each change is; this file records *how* it was built and
what bit during the build. See also
[prot_warrior_rage_audit.md](prot_warrior_rage_audit.md) for the rage numbers.

## Lessons that generalise

Read these before touching another talent — each one cost a debugging session.

**`EffectSpellClassMask<letter><digit>`: the letter is the effect index, the
digit is the word.** Improved Bloodrage shipped with Shield Slam's family bit in
`B1` — word 0 of a nonexistent Effect2 — leaving Effect1's own mask all-zero.
`SpellInfo::IsAffected` treats an empty mask as "no filter", so a +5/10%-per-stack
Shield Slam buff silently applied to the entire warrior kit. The bit belonged in
`A2`. Fixed in `woa_2026_08_09_28.sql`.

Corollary: **never disable a modifier by zeroing its class mask.** Change the
aura *type* instead. A cleared mask matches everything, not nothing. (Incite's
old Mocking Blow modifier.)

**When cloning a custom spell, clear `SpellFamilyFlags`** unless it is meant to
inherit the donor's talent support. Barricade was cloned from Shield Block and
inherited `SpellFamilyFlags = 4096`, so every modifier written for Shield Block
claimed it too: Shield Mastery's `SPELLMOD_COOLDOWN` of −10/−20 sec erased the
whole 10 sec cooldown (clamped to zero in `AddSpellAndCategoryCooldowns`,
silently), the T9 tank 4-piece did it again, and Spirits of the Lost halved the
rage floor. `SpellFamilyName = 4` was kept. Fixed in `woa_2026_08_09_34.sql`.
The first, toggle version of Barricade had zeroed the flags for exactly this
reason and the rewrite lost the line.

**The DBC `Stances` field has broken three talents in this fork.** Victory Rush
shipped with `Stances = 327680` (Battle and Berserker only), which is why Small
Victories, Improved Disciplines and Safeguard all appeared not to work — the
buffs applied and the button they enable stayed greyed out in Defensive Stance.
Shield Block's `Stances = 131072` had to be cleared on the Barricade clone for
the same reason. Prefer a script `GetShapeshiftForm()` check: reading zero out of
stance is cheaper than unapplying an aura on every stance dance.

**Rating → rating and stat → stat have no aura.**
`SPELL_AURA_MOD_RATING_FROM_STAT` (220) is 3.3.5's only conversion aura and it
reads base *stats*. So Improved Disciplines carries `SPELL_AURA_MOD_RATING`
(189) with `EffectMiscValue = 1 << CR_HASTE_MELEE = 131072` and computes the
amount in `WarriorProtConversions.cpp`; Puncture carries `SPELL_AURA_MOD_STAT`
(29) with `EffectMiscValue = 0 = STAT_STRENGTH` and applies the percentage in
`DoEffectCalcAmount`. Both run on a shared 2 sec heartbeat, because
`HandleModRating` and `SPELL_AURA_MOD_ATTACK_POWER` (99) both answer
`AURA_EFFECT_HANDLE_CHANGE_AMOUNT_MASK`, so `RecalculateAmount()` genuinely
re-applies. Nothing in core re-evaluates an aura amount when an *unrelated* aura
changes — that heartbeat is also what makes pressing Shield Block land for
Improved Disciplines' doubling.

**Bloodrage's aura is 29131, not 2687.** 2687 is instantaneous. Both the old and
new Improved Bloodrage designs turn on this.

**`ProcCharges` alone does not consume a buff on the melee damage path.**
`MeleeDamageBonusDone` applies `SPELLMOD_DAMAGE` with no `Spell*`, so
`ApplyModToSpell` never records it and `RemoveSpellMods` never charges it. Add a
`spell_proc` row on the buff and let the proc system manage charges — the path
core itself defers to. (Anticipation.)

**Talent and ability rage is `SPELL_EFFECT_ENERGIZE`, which never passes through
`Unit::RewardRage`.** `Rage.Normalized.Multiplier` and `Rate.Rage.Income` cannot
see any of it, so turning them down taxes only Arms, Fury and bears.

**`Player::ApplySpellMod` sums PCT mods additively** for every op except
`SPELLMOD_DAMAGE`/`SPELLMOD_DOT`. Sword and Board's +100% `SPELLMOD_EFFECT3`
would have cancelled a −100% exactly and silently returned full rage. Also note
Shield Slam carries its rage energize on Effect3 and Revenge on Effect2, so no
single `SPELLMOD` reaches both.

**Repointing a talent's `SpellRank_N` needs a `db-characters` companion
migration in the same batch.** Orphaned `character_talent` rows are not a soft
failure: `Player::_LoadTalents` asserts on `GetTalentSpellPos`, so the
worldserver aborted on startup as soon as a playerbot holding the old spell
loaded. Deleting the rows is not sufficient either — dependants are left with an
unmet prerequisite (Vigilance lists 152) and a loose point, and hand-deleting
strands the talent-granted spells in `character_spell`. Set
`AT_LOGIN_RESET_TALENTS` and let the engine do a proper reset; the talent point
refunds itself because `m_usedTalentCount` is recomputed from the talent map each
load. **Capture the affected GUIDs before deleting** — not doing so is why the
Barricade reset had to cover 64 warriors instead of 15.
(`woa_2026_08_09_29.sql`, `woa_2026_08_09_30.sql`.)

**A buff whose magnitude is only known at cast time follows Execute's shape:**
core has already taken the base cost by the time the DUMMY effect handler runs,
so `GetPower(POWER_RAGE)` there is the overspend available, and `CastCustomSpell`
carries the result into the buff. Its base points are 0, so the tooltip must be
plain prose — `$s1` renders 0%.

## Per-change notes

**Shield Specialization** — its first `alonecraft_spell_dbc` row. 23602 is the
trigger shared by all five ranks, so one row covers the talent, and the rank
tooltips re-render themselves because they reference it cross-spell as
`$/10;23602s1`.

**Mocking Blow** — only rank 1 ever dealt weapon damage; ranks 2–7 were flat
`SCHOOL_DAMAGE` that stopped scaling. Even rank 1 dealt none against a
taunt-immune target, which is everything a Protection warrior fights. Core's
`spell_warr_mocking_blow` gate is unregistered.

**Defensive Stance** — the damage numbers live on the passive 7376, not on 71.
Effect2 is blanked rather than zeroed so core never builds the AuraEffect.

**Vigilance** — one bit, `SPELL_ATTR1_EXCLUDE_CASTER`.

**Last Stand** — the cooldown is a *category* cooldown (1251), so `RecoveryTime`
would have done nothing.

**Intervene** — Charge is Battle Stance only and Intercept Berserker only, so the
one spec required to stand in Defensive Stance had no gap closer. Flipping the
target type was not enough: the "intercept the next attack against this unit"
effect had to be blanked (on an enemy it redirects *their* incoming attacks) and
`SPELL_ATTR5_IMPLIED_TARGETING` removed, or the client retargets to the enemy's
target — usually you. Core's `spell_warr_intervene` is unregistered.

The 4.67 friend-or-foe rebuild is copied from Holy Shock (20473), core's one
such spell: a single `SPELL_EFFECT_DUMMY` on `TARGET_UNIT_TARGET_ANY` plus a
script branching on `IsFriendlyTo`. Implicit targets are validated for the spell
as a whole, so an ally-targeted effect beside an enemy-targeted one is a cast
that satisfies neither, not "whichever applies". Side effect: target 25 makes
the spell count as *positive*, and `EffectCharge` only tracks a moving target for
non-positive spells, so an enemy charge lands where they stood at cast time.
Aggro comes from Staggered, so it is unaffected.

A second charge is deliberately not implemented: 3.3.5a has no spell-charge
system, and faking one needs a marker aura plus cooldown bookkeeping in C++.
Halving the cooldown is the cheap approximation if it is wanted.

**Juggernaut** — the in-combat half did not work in play, so in 4.65 the combat
attribute was removed from Charge and the gate moved into
`spell_warr_charge_in_combat`.

**Sword and Board** — worth revisiting. It both refreshes Shield Slam's cooldown
*and* doubles its energize, so it is worth ~45 rage where retail's version was
worth 20.

**Unaffected by normalisation, and verified so:** Anger Management, Unbridled
Wrath, Shield Specialization, Improved Bloodrage, Improved Berserker Rage,
Improved Charge and Second Wind are all separate energize effects rather than
`RewardRage` paths, so none care about `Rage.FromDamageTaken`. Quietly buffed:
every rage *cost* reduction (Improved Heroic Strike, Improved Execute, Improved
Thunder Clap, ~~Puncture~~, Sudden Death), since income is now a fixed ceiling
and buying more actions per minute is the only lever left. Intensify Rage too.

**Berserker Rage** — all three DBC effect slots were mechanic immunities, so the
Sap immunity (mechanic 30) was dropped; nothing in Alonecraft saps you. Fear and
Incapacitate immunity are unchanged, as is Improved Berserker Rage (23691,
instant 20 rage).

**Improved Bloodrage / Talent swap** — swapping Improved Bloodrage (0, 0) with
Toughness (3, 2) is safe: no talent in the game lists 140 or 142 as a
prerequisite.

**Shield Mastery** — retuned from −30/60 sec during implementation. Shield Block
is a 60 sec cooldown with a 10 sec duration, so −60 would leave it with no
cooldown at all: permanent uptime and a permanently doubled block-value cap on
Shield Slam. The block damage reuses core's `spell_warr_damage_shield`,
re-pointed here, so the talent needed no new C++.

**Improved Thunder Clap** — the only talent in the tree that needed all three
effect slots, so the retail rage cost reduction and slow bonus were dropped
rather than squeezed. The radius is an `ADD_FLAT_MODIFIER` of `SPELLMOD_RADIUS`
(+2/+4/+7 on Thunder Clap's base 8), applied in `SpellInfo::Effect::CalcRadius`
— a per-rank radius cannot live on Thunder Clap's own row, and `build_dbc.py`
does not write `SpellRadius.dbc`, so re-pointing `EffectRadiusIndex` was not an
option either. Retail left the +damage modifier with **no** SpellClassMask,
i.e. family-wide; harmless at +30%, not harmless at +100%, so it is now masked
to 128. The bleed (`WarriorImprovedThunderClap.cpp`, payload 200661) is the
Unholy Blight pattern: `CastDelayedSpellWithPeriodicAmount`, family 0 so it
cannot re-proc anything, and `ALWAYS_HIT` / `IGNORE_DAMAGE_TAKEN_MODIFIERS` /
`CANT_CRIT` so the ticks do not re-roll what the seeding Thunder Clap already
rolled.

**Improved Thunder Clap / Shield Mastery swap** — same prerequisite check as the
Toughness pair above: nothing in the game lists 141 or 1654 as a prerequisite.
Shield Mastery is the block-value talent, so it belongs in front of the talent
that scales off block value. Note this reorders the Protection tree's
`(tier, col)` indices, which are the wire format for talent-calculator build
links, so previously shared Protection links now decode differently.

**Spellshield** — no shield equipped means no block chance means no absorb, for
free.

**Blood and Thunder** — one roll per cast, not per victim. Crowd-controlled
enemies are skipped.

**Damage Shield** — bleeds deliberately do not feed it; with Blood and Thunder
spreading Rend that would mean a cast per tick per target. The absorb helper
Fortify (200649) was cloned from Last Stand and inherited its `SpellVisual1`,
so re-casting it on every damage event replayed a self-buff cast visual that
interrupted the melee swing animation; `woa_2026_08_10_00.sql` zeroes it. A
clone inherits every column it was not told to change — check `SpellVisual` on
any helper that is re-cast at melee frequency.

**Barricade** (replaces Concussion Blow) — shipped first as a toggle:
permanent, 5 rage/sec upkeep, +50% Shield Slam and Revenge damage with their
rage suppressed. It worked but never *felt* like spending anything, so it was
rebuilt in `woa_2026_08_09_31.sql` as a second Shield Block that scales with the
dump. Because the floor is 20 rage for 10%, the conversion is a flat 1% per 2
rage with no special case: the bonus is rage spent ÷ 2 (halved from 1% per rage
in 4.69, with the floor and cap unchanged, so the same dump buys half as much).
The divisor is the one Barricade number that cannot live in the DBC — it
multiplies rage actually spent, which is only known once the effect handler
runs. Three spells, following
Execute's shape (above). The heal needs no scaling code —
`Player::GetShieldBlockValue` multiplies by `m_auraBasePctMod[SHIELD_BLOCK_VALUE]`,
which is what aura 150 feeds, so an 80-rage Barricade heals 80% more per block
*and* blocks more often. Shield Block's shield requirement was kept.

**Anticipation** — pure DBC plus a `spell_proc` row for charge management (see
above). White swings are excluded by design.

**One- and Two-Handed Weapon Specialization** — they share a script file and can
never feed each other: both carry `EquippedItemClass 2` with mutually exclusive
`EquippedItemSubClassMask`s (41105 one-handed, 354 two-handed), so core unapplies
one whenever the other applies and there is no crit → parry → crit loop. Uses
`SPELL_AURA_MOD_WEAPON_CRIT_PERCENT` (52) rather than `SPELL_AURA_MOD_CRIT_PCT`
(290), because 52 is summed behind a `CheckAttackFitToAuraRequirement` predicate
and so honours the weapon gate per slot, while 290 has no item requirement at
all. It converts the **character-sheet** dodge and parry, not
`GetRealDodge()`/`GetRealParry()` — those are the post-diminishing-returns
numbers the avoidance rolls use, and are lower; the tooltip promises a share of
what the player can read off their own sheet.

**Improved Disciplines** (4.68 redesign) — replaces the 4.66 Shield
Wall/Victorious proc, whose `spell_proc` row is deleted in
`woa_2026_08_09_39.sql`. Defense rating is dead weight past the cap; paying it
back as haste turns overcapped avoidance gear into rage income, which the rage
audit prices off swing frequency. The doubling window is Shield Block or Shield
Wall; Barricade (200652) is deliberately excluded — 10 sec up on a 10 sec
cooldown would make the doubling permanent. The per-rank percentage stays in base
points because that is what the script reads *before* doubling, so the doubled
clause is plain tooltip text.

**The 4.69 halving pass** — One-Handed Weapon Specialization (10/20/30/40/50 →
5/10/15/20/25), Improved Disciplines (50/100 → 25/50), Puncture (10/20/30 →
5/10/15) and Controlled Aggression (50/100 → 12/25), in
`woa_2026_08_10_02.sql` and `woa_2026_08_10_03.sql`. All four read a
character-sheet field that the rest of the tree already inflates, so a 1:1
max-rank conversion compounded rather than added. Every one is a plain
`EffectBasePoints` `UPDATE`: the descriptions are written with `$sN` and the
scripts take the percentage off the aura effect amount in `DoEffectCalcAmount`,
so tooltip and effect move together and no C++ change is involved. That is the
point of keeping the number in the DBC — retuning these should never need a
rebuild of anything but the DBC.

**Controlled Aggression** (ex-Improved Bloodrage) — block value was the tree's
central number with no offensive outlet (Toughness feeds it, Shield Mastery
multiplies it, Spellshield and Barricade convert it), so this makes a rage
cooldown a damage decision too. Block value is neither a stat nor a rating, so
aura 220 cannot see it from either end. Non-circular: block value reads Strength,
and flat AP feeds neither. Retiring the old proc meant deleting the `spell_proc`
row on −12301 **and** the orphaned payload buffs 200647/200648, which exist only
as Alonecraft overrides and so vanish from the built DBC entirely. This emptied
`WarriorProtGates.cpp`, which was deleted rather than left as a shell.

**Incite** (4.68 redesign) — the 4.66 version's Revenge half was inert against
players, which are taunt-immune, so there was no Mocking Blow aura to find.
Retail Incite buffed exactly Heroic Strike, Thunder Clap and Cleave, so its own
`EffectSpellClassMaskA1 = 4194496` (`0x40`, `0x80`, `0x400000`) was restored into
the `spell_proc` row rather than computed. The DBC mask on the new DUMMY effect
is deliberately left at 0: a DUMMY has no modifier semantics, and a mask there
would read as the filter when the `spell_proc` row is. Chance is not expressible
in SQL — no `spell_proc` column can reference a character stat — so the roll is
C++ against `PLAYER_BLOCK_PERCENTAGE`, the same field Spellshield uses and for
the same reason: it is the figure the melee attack table itself uses, and it is 0
with no shield, so the weapon check is free. Payload 200660 is cloned from Mark
of Blood's damage helper with `SpellFamilyName` cleared to 0, which also means it
cannot match Incite's own proc filter and feed itself. Self-limiting rate:
Heroic Strike and Cleave share a 3 sec cooldown since the Cataclysm rebuild.

**Puncture** — was −1/−2/−3 rage on Sunder Armor and Devastate, which the rage
audit flagged as overtuned: income was raised and the flat cuts were never
rescaled, so 3 points bought a larger share of a smaller cost than intended.
Removing the reduction fixes the economy and the replacement makes Stamina, which
Protection stacks anyway, its throughput scaling. Converts **total** Stamina, not
the base value aura 220 would have read, because on a Protection warrior almost
all of it is gear and buffs.
