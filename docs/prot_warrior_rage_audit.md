# Protection Warrior Rage Audit

Every source and sink of rage available to a level 80 Protection warrior as the
tree currently stands, with the arithmetic behind each one. This is a **model
built from the DBC and the core code**, not a measurement — see
[Caveats](#caveats) before treating any number as fact.

Written 2026-08-09 against the working tree (`Rage.Normalized = 1`,
`Rage.FromDamageTaken = 0`, Shield Slam and Revenge as generators, Barricade as
a dump).

---

## 1. The engine layer

Rage arrives through exactly two mechanisms, and they obey different rules:

| Mechanism | Code path | Affected by `Rage.Normalized` / `Rage.FromDamageTaken` | Affected by `Rate.Rage.Income` |
|---|---|---|---|
| `Unit::RewardRage` | [Unit.cpp:16115](../src/server/game/Entities/Unit/Unit.cpp#L16115) | **Yes** | **Yes** ([Unit.cpp:16158](../src/server/game/Entities/Unit/Unit.cpp#L16158)) |
| `SPELL_EFFECT_ENERGIZE` / `PERIODIC_ENERGIZE` | `SpellEffects.cpp` | No | No |

That split is the single most important fact in this document. Every talent and
ability listed in §3 is an **energize effect**, so none of them were reduced when
`Rage.FromDamageTaken` was switched off, and none of them can be dialled back
with `Rate.Rage.Income`. The only lever that touches them is their own base
points.

### Effective config

```
Rate.Rage.Income           = 1
Rate.Rage.Loss             = 1
Rage.Normalized            = 1
Rage.Normalized.Multiplier = 1.5
Rage.FromDamageTaken       = 0
```

### `RewardRage` under normalization

```
weaponSpeedHitFactor = attackTime_sec * 3.5      (main hand; 1.75 off hand)
if crit:               weaponSpeedHitFactor *= 2
addRage              = weaponSpeedHitFactor * Rage.Normalized.Multiplier
addRage             += AddPct(SPELL_AURA_MOD_RAGE_FROM_DAMAGE_DEALT)
addRage             *= Rate.Rage.Income
```

`GetAttackTime` already includes haste, so **rage per second from auto-attack is
independent of both weapon speed and haste**: `3.5 × 1.5 = 5.25 rage/sec` flat.
A 1.6s weapon pays 8.4 per swing, a 2.6s weapon 13.65 — the same rate.

The `attacker` branch is reached from two places:

- [Unit.cpp:1136](../src/server/game/Entities/Unit/Unit.cpp#L1136) — a landed
  white swing (gated on `!spellProto`, so abilities pay nothing).
- [Unit.cpp:2112](../src/server/game/Entities/Unit/Unit.cpp#L2112) — a swing that
  was **fully blocked, dodged or parried by the target**, which pays the *same*
  full weapon-speed rage as a landed hit.

Only an outright **miss** yields nothing. That matters: an avoidance-heavy target
does not reduce your income at all.

The `victim` (damage taken) branch returns immediately —
`Rage.FromDamageTaken = 0`. Berserker Rage's ×3 multiplier lived in that branch
and is dead with it, which is why 18499 was given a
`SPELL_AURA_MOD_RAGE_FROM_DAMAGE_DEALT +100%` effect instead.

---

## 2. Auto-attack income

| Term | Value |
|---|---|
| Base | 5.25 rage/sec |
| × (1 + melee crit), crit doubles the factor | 15% crit → 6.04 |
| × (1 − miss); dodge/parry/block still pay | 5% miss → **5.74 rage/sec** |
| × 2 while Berserker Rage is up (10s / 30s CD) | +~1.9 rage/sec averaged |

No off-hand term — Protection holds a shield.

---

## 3. Ability and talent income

Every row below is a `SPELL_EFFECT_ENERGIZE`, verified against the built
`Spell.dbc` at `C:\Build\bin\RelWithDebInfo\Data\dbc`. "Δ vs retail" is the
swing in the warrior's favour: cost removed plus rage granted.

| Source | Spell | Retail | Now | Δ vs retail | Cadence |
|---|---|---|---|---|---|
| **Shield Slam** | 47488 | costs 20 | **0 cost, +15 rage** | **+35** | 6s category CD |
| **Sword and Board** (buff 50227) | 46953 | SS costs −100% | **SS Effect3 +100% → 30 rage** | **+30 on top** | 30% off Devastate/Revenge |
| **Revenge** | 57823 | costs 5 | **0 cost, +10 rage** | **+15** | 5s category CD |
| **Shield Specialization** 5/5 | 12727 → 23602 | 5 rage @ 100% | **3 rage @ 100%** | −2 | every block/dodge/parry |
| **Bloodrage** | 2687 + 29131 | 20 + 10 over 10s | unchanged | — | 60s CD |
| **Berserker Rage** | 18499 | ×3 rage from damage *taken* | **+100% rage from damage dealt** | rewrite | 30s CD, 10s |
| **Improved Bloodrage** | 12301/12818 | +25/50% Bloodrage rage | **redesigned — no rage at all** | −10/20 | — |
| **Barricade** | 200651 | (replaces Concussion Blow) | **spends 20–80** | sink | 10s CD |

Not rage sources despite appearances: Improved Defensive Stance (grants Enrage,
a damage buff), Damage Shield (redesigned into an absorb), Incite, Vigilance,
Warbringer, Devastate, Improved Revenge.

**Indirect sources** — these do not energize, but they buy extra casts of
something that does:

| Talent | Effect | Worth |
|---|---|---|
| Sword and Board 3/3 | 30% chance to **refresh Shield Slam's cooldown** | extra 40-rage casts |
| Incite 3/3 | Mocked enemies **reset Revenge's cooldown** when they attack you | extra 15-rage casts (not vs bosses/players — taunt does not land) |
| Intensify Rage 3/3 | −33% Bloodrage / Berserker Rage cooldowns | +0.25 rage/sec, plus more Berserker Rage uptime |

---

## 4. The ledger

Single target, level 80, Defensive Stance, 15% melee crit, 5% miss, boss swinging
every 2.0s, 60% combined block+dodge+parry, full Protection tree.

### Income

| Source | rage/sec | Share | Before the `woa_2026_08_09_38.sql` trim |
|---|---:|---:|---:|
| **Shield Slam (blended, incl. Sword and Board)** | **10.3** | **53%** | 13.7 |
| Auto-attack | 5.7 | 29% | 5.7 |
| Revenge | 2.0 | 10% | 3.0 |
| Shield Specialization | 0.9 | 5% | 1.5 |
| Bloodrage | 0.5 | 3% | 0.5 |
| **Total** | **~19.5** | | ~24.4 |

Shield Slam is still over half of all income. The derivation:

```
SnB proc opportunities = 1/1.5s (Devastate) + 1/5s (Revenge) = 0.867/sec
SnB procs              = 0.867 * 0.30                        = 0.260/sec  (1 per 3.85s)
effective SS interval  = 1 / (1/6 + 0.260)                   = 2.34s
empowered fraction     = 0.260 * 2.34                        = 61%
rage/sec               = (15*0.39 + 30*0.61) / 2.34          = 10.3
```

Against three attackers, Shield Specialization goes to 2.7 rage/sec and the total
to ~21.3.

### Spend

| Ability | Cost after Focused Rage 3/3 (−3), Puncture 3/3 (−3), Imp. Thunder Clap 3/3 (−4), Imp. Heroic Strike 3/3 (−5) | rage/sec |
|---|---:|---:|
| Devastate (GCD filler) | 9 / 1.5s | 6.0 |
| Heroic Strike (off GCD, 3s CD) | 22 / 3.0s | 7.3 |
| Thunder Clap | 13 / 6.0s | 2.2 |
| Barricade (full dump) | 80 / 10s | 8.0 |
| **Total** | | **~23.5** |

Before the trim, income (24.4) and full spend (23.5) balanced only when Heroic
Strike was on cooldown permanently *and* Barricade dumped its maximum every 10
seconds; drop either and you capped within seconds. After the trim income is
~19.5 against the same 23.5, so the full rotation is now genuinely
rage-constrained, and dropping Barricade (15.5 spend) leaves ~4 rage/sec of
headroom rather than ~9.

The remaining structural point stands regardless of the numbers: income is
**unconditional and flat** — cooldown-driven, not coupled to the fight — while
the sinks are opt-in.

---

## 5. Why it runs hot

Ranked by contribution, most to least.

1. **Sword and Board is a double-dip it never was on retail.** Retail's buff was
   `SPELLMOD_COST −100%` — worth exactly the 20 rage Shield Slam cost. Once
   Shield Slam became free that modifier had nothing to reduce, so it was
   repointed to `SPELLMOD_EFFECT3 +100%`, which lands on the new energize effect.
   The talent now grants **both** an extra Shield Slam cast *and* double rage on
   it. Retail gave one 20-rage benefit; this gives roughly 45 even after the
   trim. **This is the largest lever still untouched.**

2. **Shield Slam's swing is +35 rage per cast** before Sword and Board touches
   it — the largest single change in the rework, and it is on a 6s cooldown that
   a talent routinely resets.

3. **Income no longer depends on being hit.** `Rage.FromDamageTaken = 0` replaced
   a variable, threat-coupled income with cooldown-driven generators. A prot
   warrior standing in front of a training dummy now generates the same ~19.5
   rage/sec as one tanking a boss. The old model at least scaled with the fight.

4. **Cost reductions were quietly buffed.** Focused Rage, Puncture, Improved
   Thunder Clap and Improved Heroic Strike still cut costs that are now much
   smaller relative to income — and Focused Rage's −3 no longer applies to Shield
   Slam or Revenge at all, since they cost nothing, so those 3 points buy less
   than the tooltip implies.

5. **Shield Specialization** was retail-stock at 5 rage per avoidance event —
   designed as a *supplement* to damage-taken rage, not as an addition on top of
   two large generators. Now 3, which is small single-target (0.9) but still
   scales linearly with the number of things hitting you (2.7 on three).

6. **Auto-attack rage is flat 5.25/sec at every gear level.** Intended, and it is
   the fix for levelling — but for Protection specifically it means the floor
   never drops.

### Levers

Applied in `woa_2026_08_09_38.sql`:

| Lever | Where | Effect |
|---|---|---|
| ✅ Shield Slam 20 → 15 rage | `47488` `EffectBasePoints3` (+ 7 lower ranks) | −3.4 rage/sec |
| ✅ Revenge 15 → 10 rage | `57823` `EffectBasePoints2` (+ 8 lower ranks) | −1.0 rage/sec |
| ✅ Shield Specialization 5 → 3 rage | `23602` `EffectBasePoints1` | −0.6 single target, −1.8 on three |

Still on the table:

| Lever | Where | Effect |
|---|---|---|
| Sword and Board buff → +50% instead of +100% | `50227` `EffectBasePoints1` | −2.6 rage/sec |
| Sword and Board buff → drop the rage bonus, keep the reset | `50227` | −3.9 rage/sec |
| `Rage.Normalized.Multiplier` 1.5 → 1.2 | `worldserver.overrides.conf` | −1.1 rage/sec, **but hits Arms, Fury and bears too** |

The multiplier is the only global dial, and it is the wrong one — it cannot see
Protection's generators at all (§1), so it taxes the specs that are already
correctly tuned.

---

## Caveats

- **This is a model.** Nothing here was measured in-game. The Shield Slam figure
  is the least trustworthy: it assumes Shield Slam is cast the instant it is
  available, which consumes GCDs that would otherwise be Devastate, which in turn
  reduces the Sword and Board proc rate. That feedback loop is not modelled, so
  10.3 rage/sec is an **upper bound**; the true figure is likely 8–10, which
  would put total income around 17–19 rather than 19.5.
- Crit (15%), miss (5%), boss swing speed (2.0s) and avoidance (60%) are
  assumptions, not observations. Crit is the one worth checking — it multiplies
  the auto-attack term directly.
- The built `Spell.dbc` this was read from **predates `woa_2026_08_09_31.sql`**
  (the Barricade redesign — it still carries the 5 rage/sec toggle version at
  `ManaCost 50`) **and `woa_2026_08_09_38.sql`** (the trim in §5, applied to
  MySQL but not yet packed). §3 and §4 describe the SQL as written, not what is
  currently in the MPQ. Rebuild before testing.
- Improved Charge, Second Wind, Endless Rage, Unbridled Wrath, Anger Management
  and Improved Berserker Rage are all rage sources, but sit in Arms or Fury and
  are out of reach of a full Protection build. They are excluded.
