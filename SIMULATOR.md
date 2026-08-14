# Alonecraft Combat Simulator

Headless combat measurement for balancing Alonecraft's class changes, without
logging in.

Given a character, a spec, a level and a target, it reports DPS with a
per-ability breakdown, and against a real boss it reports time-to-die, the
Theck-Meloree Index, and solo-clear pass/fail with margins. A 60-second fight
takes about a second of wall clock.

```bash
# DPS against the level-83 dummy, 12 fights
python tools/sim.py --char Deleona --spec "shadow pve" --level 80 --iterations 12

# Survivability against a real boss
python tools/sim.py --char Deleona --level 80 --target 16028 --iterations 5 --seconds 300
```

---

## Where this is up to — 2026-08-14

Four harness bugs were found and fixed in one session, and **each one silently
invalidated every number measured before it**. That is the headline: the
simulator's own defects, not the specs, were the largest source of error.

| fixed | what it did |
|---|---|
| pet auras stripped between fights | `ResetActor` called `RemoveAllAuras` on the pet. Pet passives *are* pet scaling and are applied once by `Pet::addSpell`, so Hunter Pet Scaling 01-04 was deleted permanently. Pet melee fell 570-725 → 104-138 per hit. |
| permanent pet despawned | `Pet` derives from `TempSummon`, so the "unsummon temporary guardians" sweep ate the hunter's own pet whenever `GetPet()` returned null. Combined with the above this made the damage **bimodal** rather than merely wrong. |
| previous spec's talents resurrected | `RepairSpecMask` treated `specMask == 0` as a tombstone. On a single-spec actor, deactivation *produces* 0, so each run re-learned the last spec's tree — 42-53 spells. A warrior at 18/53/**0** carried six Protection passives. **Median DPS fell 5248 → 2500 once fixed: the whole damage baseline had been ~2x inflated.** |
| avoidance invisible | An avoided swing deals nothing and fires no damage hook, so "took 0 damage" and "was never attacked" were indistinguishable. The incoming-swing ledger now reads `TargetState` and `blocked_amount` off `SMSG_ATTACKERSTATEUPDATE`. |

**Every number in this document predating that work should be treated as
suspect** unless it was re-measured after.

### What is trustworthy now

`tools/matrix_report.py` renders each matrix run as one sortable, filterable
page with per-spec drill-down, written automatically at the end of every run and
indexed in `sims/matrix.html`. Read that rather than scrollback.

Latest clean run — 31 specs, 3 iterations, autobalanced Patchwerk:
**21 kill it 3/3, 8 die 3/3, 2 split.** The boss discriminates without tuning;
the sparring dummy needed two calibration passes and still does not.

### Open — measurement

- [ ] **Absorb per-source attribution is 0% for short-lived shields.** The
      ledger samples absorb auras at intervals, so a shield consumed between
      samples is invisible. Persistent shields (Power Word: Shield, Ice Barrier)
      attribute at 62-88%; Savage Defense and the warlock wards at **0%** —
      druid_bear absorbs ~42k a fight with 47 attributed. Totals are exact; the
      breakdown is not. Coverage is shown per spec on the report page.
- [ ] **Rated defence is sampled at pull only**, so any stat that moves in
      combat reads low. Snapshot at fight end as well.
- [ ] **Residual talent leak**: spells *taught by* a talent (via
      `SPELL_EFFECT_LEARN_SPELL`) are not talent spells themselves, so they pass
      the tombstone test. `Defiance Expertise Passive` survives on a 0-point
      Protection warrior. Expertise, not avoidance, so it does not move these
      numbers — but it is the same class of bug.
- [ ] Sparring dummy is at `DamageModifier` 8.0 / `HealthModifier` 78, which
      kills 20 of 31. **~3.0 is the recommendation** — 8.0 was set before the
      health tripled, and the two multiply. Possibly moot now that Patchwerk
      works.

### Open — balance

- [ ] **`hunter_bm` is the worst spec measured**: 849 DPS, dies 3/3. Its pet
      contributes 3-15% against `hunter_mm`'s 5-10%, but its *own* damage is
      44-87k against MM's 325-344k. Failing on both halves.
- [ ] **Pack Hunting only fires for Marksmanship.** BM's node is written at
      relevance **39.0**, above `ACTION_MOVE`; MM's at 18.6 in the combat band.
      Survival has no node at all. Classic relevance-band trap — nothing errors.
- [ ] **Misdirection onto the pet is not implemented.** The only wiring is
      `MisdirectionOnMainTankTrigger`, gated on `"low tank threat"` and targeting
      a group's main tank, so it can never fire solo. For a solo hunter this is
      the most valuable threat tool in the kit.
- [ ] **`warrior_prot` is the highest-DPS spec in the game** on both fixtures,
      at 1% damage taken and 99% mitigated.
- [ ] `rogue_combat` and `rogue_assn` die 3/3 with the highest avoidance of any
      dying spec (61-62%). Not a defensive problem.
- [ ] `shaman_resto` and `druid_resto` have **no defensive layer at all**
      (mitig% equals avoid%) and survive purely by outhealing.
- [ ] Drop the dead single-target Pestilence node from unholy — it never fires.

### Two traps worth not repeating

**Read the `*_dbc` override table, not the binary DBC.** Every `*_dbc` table in
`acore_world` is layered over the file at load (`LOAD_DBC`, `DBCStores.cpp:353`).
A binary read tells you what the file says, never what the server uses — this
produced a confident, wrong "the arena has been autobalancing from 40-man"
when `woa_2026_08_14_02.sql` had pinned it to 25 all along.

**`count` in an ability row is damage events, not casts.** Buff-shaped abilities
produce no row of their own; check `attempts`, `heal_count`, or the aura list
before concluding a button is never pressed.

---

## Why it exists

Alonecraft has overridden **722 spell IDs** (213 of them new), modified **232
talents**, and added ~26 C++ files of bespoke damage arithmetic. None of it is
tuned — every "Tuning" checkbox in [TODO.md](TODO.md) is unchecked, across all 30
specs.

Tuning by playing is not viable at that scale, and the one existing balance
document, [docs/prot_warrior_rage_audit.md](docs/prot_warrior_rage_audit.md),
says so in its own header: it is "a model built from the DBC and the core code,
**not a measurement**".

## Why not a wowsims-style reimplementation

A standalone model would have to re-derive 722 overridden spells and 26 files of
custom arithmetic, and would drift from the server on every commit.

**The simulator is the real worldserver.** It boots normally — real DBC, real
`spell_proc`, every `alonecraft_spell_dbc` override, every module script — and
`--sim` swaps the realtime update loop for a fixed-diff one with the clock
detached from the wall. Combat maths is not reimplemented anywhere.

This is cheap because the game already reads a virtual clock:
`GameTime.cpp` caches `GameTime`, `GameMSTime`, `GameTimeSystemPoint` and
`GameTimeSteadyPoint`, refreshed only in `UpdateGameTimers()` once per tick.
Cooldowns, GCDs, aura durations, swing timers and proc ICDs all read through it.
Only **three call sites in the entire combat path** bypassed it.

Rotations, gear and talents come from mod-playerbots, which already has per-spec
strategies and a gearing factory — and which hard-requires a live `Player`,
`WorldSession` and `Map` that a booted worldserver provides for free.

---

## Setup

**The simulator must never touch the live characters database.** It re-specs,
re-gears and saves the actor; pointed at `acore_characters` that is destructive.

```sql
CREATE DATABASE IF NOT EXISTS `acore_characters_sim`
    DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON `acore_characters_sim`.* TO 'acore'@'localhost';
FLUSH PRIVILEGES;
```

Then clone the live characters database into it:

```bash
mysqldump -h 127.0.0.1 -u acore -pacore acore_characters \
  | mysql -h 127.0.0.1 -u acore -pacore acore_characters_sim
```

`tools/sim.py` **refuses to run** against a database whose name does not end in
`_sim` unless `--i-know-what-im-doing` is passed. That guard is the single most
important line in the tool.

---

## Usage

```
python tools/sim.py --char <name> [options]

  --char NAME          character to sim (required)
  --spec NAME          playerbots premade spec, e.g. "shadow pve".
                       Omit to sim the character exactly as stored.
  --level N            level to configure (0 = keep current)
  --gear KEY           fixed equipment set from sims/gear (e.g. priest_shadow)
  --range N            yards between actor and target at the start of a fight
                       (0 = the server default of 5; hunters need ~30)
  --target NAME|ENTRY  what to fight (default: the inert level-83 dummy).
                       Names: dummy, sparring, patchwerk, thaddius, loatheb,
                       gluth. An entry id also works.
  --seconds N          virtual seconds per fight (default 60)
  --iterations N       fights per run, all inside one process (default 1)
  --seed N             base seed; iteration i uses seed+i
  --tick-ms N          virtual ms per world tick (default 25)
  --db NAME            characters database (default acore_characters_sim)
  --stock              run with the Alonecraft solo build and rotation OFF,
                       i.e. upstream's premade spec. The control half of an A/B
  --print-env          print the AC_* overrides and why each exists, then exit
```

`--spec` runs the actor through `PlayerbotFactory::Randomize`, which assigns
talents, gear, glyphs, enchants, gems, ammo, consumables and a pet — the same
code path that configures a live random bot. Spec names come from
`AiPlayerbot.PremadeSpecName.*` in `playerbots.conf`; a typo lists the
alternatives rather than silently simming the wrong tree.

### Gear

`PlayerbotFactory` gears by score out of whatever the loot tables yield, which
is right for a random bot and wrong for a comparison: two specs measured in two
different sets differ by the gear as much as by the spec, and the roll is not
even stable between runs of the same spec.

`--gear KEY` replaces the whole equipped set with a fixed one, including
enchants, gems and socket bonuses. The sets are tier-7 (P1) lists imported from
[wowsims/wotlk](https://github.com/wowsims/wotlk) — maintained by people who
play the spec, per-spec already, and a *fixed external reference*, so if
Alonecraft's numbers move the gear does not move with them.

```bash
python tools/fetch_wowsims_gear.py          # (re)import into sims/gear/
python tools/fetch_wowsims_gear.py --check  # validate the committed files
```

The files are committed rather than fetched per run: a run that silently
downloaded different gear than last time would report a balance change that was
really a gear change. The import validates every id against `item_template`,
and all 31 sets currently resolve completely.

There is no such thing as an exactly-ilvl-200 set — Naxxramas-10 drops 200,
Naxxramas-25 drops 213, and the lists mix in 226 from Malygos and Sartharion. The
sets land at a **mean item level of 208–220**, and the runner reports what it
actually equipped per spec, so parity is checked rather than assumed. Two sets
are deliberately shared: wowsims models demonology and destruction on one list,
and has no beast-mastery list because BM and MM wear the same hunter gear.

A slot that cannot be equipped is left empty, counted, and **fails the run** —
a spec wearing 15 of 17 pieces is not comparable with one wearing all 17, and
that difference is invisible in a DPS number.

### The balance matrix

```bash
python tools/sim_matrix.py                       # all 31 specs, all 3 passes
python tools/sim_matrix.py --specs priest mage   # by class
python tools/sim_matrix.py --specs dps           # by role
python tools/sim_matrix.py --specs mage --passes burst   # the quick inner loop
python tools/sim_matrix.py --specs mage --ab     # against the stock spec
python tools/sim_matrix.py --report sims/runs/matrix-20260813-140000
```

One worldserver per spec per pass, sequentially — parallel runs would contend
for port 8085 and the same database.

Measured, not estimated: **~63 seconds of wall clock per pass**, fairly flat
across the three, because roughly 28s of it is worldserver boot rather than
combat. A 60-second burst pass therefore costs ~42s and a 300-second sustain
pass ~91s — the fight length matters much less than the process count.

| Command | Passes | Wall clock |
|---|---|---|
| `--specs mage --passes burst` | 3 | ~2 min |
| `--specs mage --ab` | 18 | **~19 min** |
| all 31 specs, `--passes burst` | 31 | ~33 min |
| all 31 specs, all three | 93 | ~1h 40m |
| all 31 specs, `--ab` | 186 | ~3h 15m |

So the full paired matrix is an overnight job and the per-class `--ab` is the
one to run while authoring a spec. Boot dominating the cost is also the argument
against splitting passes any finer than this.

**Stop the live worldserver first.** The sim launches its own on the same port,
from the same binary: `tools/stop_server.ps1`, or build with `--skip-server`.

It is deliberately **not** a "which spec is strongest" table. With one dummy, no
raid buffs, no movement and a bot rotation, the absolute numbers are not raid
DPS. What it is good at is the question with no other cheap answer: *is each
spec's rotation running at all?* The columns exist for that —

| Column | Reads |
|---|---|
| `burst` / `sust` | DPS over the short and long passes |
| `s/b` | sustain as a share of burst; below 60% the spec runs out of something |
| `clear` | how often it killed the sparring dummy and lived |
| `TTD` | median time to death, over lost fights only — survivors are censored |
| `abil` | distinct damage sources used in the fight |
| `top` | the largest single ability and its share |

and the flags underneath name the symptom: a spec with three damage sources, or
80% of its damage on one button, or a caster wanding for a tenth of the fight,
is broken in a way that no number tuning fixes and that will poison any tuning
done on top of it.

`tools/sim_specs.py` is the single definition of what each spec is — its
playerbots spec name, its role, its gear list, its level-80 actor, its starting
distance and the talent tab it must end up in. The actors are pinned rather
than re-queried, because race changes stats by a few percent and a spec whose
body changed between runs is not a comparison.

### Diagnosing a rotation

The matrix says a spec's numbers look wrong. `sim_actions.py` says *why*, by
turning on the playerbot engine's own decision logging and counting what the AI
tried:

```bash
python tools/sim_actions.py --char Apold --spec "fire pve" --gear mage_fire --seconds 30
python tools/sim_actions.py --char Apold --spec "fire pve" --gear mage_fire \
    --seconds 30 --target 2000110      # for anything driven by damage taken
python tools/sim_actions.py --log sims/runs/actions/Apold-fire_pve.log
```

Two failure shapes, and they want opposite fixes:

- **evaluated constantly, always IMPOSSIBLE or USELESS** — a condition the bot
  checks is never satisfied; the spell or its prerequisites are the problem.
- **never appears at all** — no trigger ever pushed it; the strategy is the
  problem.

**Use `--target 2000110` for any rotation driven by damage taken.** The default
dummy hits for 0.01×, so Ember Scars, Fiery Payback and the Convective Currents
self-heal can never reach their thresholds and the tool reports a working
rotation as a dead one. That is not hypothetical: the fire mage's Ember Scars
trigger showed zero fires against the inert dummy and thirteen against the
sparring one.

Keep the runs short. These logs are one block per tick, and a 120-second fight
produces hundreds of thousands of lines.

#### The virtual clock disabled almost every talent proc

This one was worth more than all the others combined, and it hid behind a
single spell for most of a day.

`GameTime` initialises its cached points to `TimePoint::min()` upstream, relying
on the first `UpdateGameTimers()` to overwrite them from the real clock. The
virtual branch only ever *adds* a step, so it never primed them: `GameTime::Now()`
returned `min()` plus elapsed — about **nine billion seconds before the epoch**.

`Aura::m_procCooldown` has no initialiser. It default-constructs to epoch 0,
which under that clock is nine billion seconds in the *future*, so
`Aura::GetProcEffectMask` read every untouched aura as permanently on proc
cooldown and dropped it. **Every talent proc that had never had a cooldown
written explicitly simply never fired.**

Item and enchant procs kept working, because `Player.cpp:11858` writes their
cooldown from `GameTime::Now()`. That asymmetry is what made it so hard to see:
a rogue's poisons proccing 269 times per fight looked like proof that the proc
system was fine.

The symptom that finally exposed it: a fire mage cast **Scorch 157 times in two
minutes and Fireball not once**, because its bot rotation re-Scorches until the
target carries Improved Scorch (22959) — a debuff applied by a proc that could
never fire. Every one of the mage's own numbers looked correct: the talent was
3/3, the aura was applied, the `spell_proc` row was stock, `ProcChance` was 100.

`EnableVirtualClock` now primes all four cached points from the real clock.

| | before | after |
|---|---|---|
| `mage_fire` | 424 → 1914 | **3604** |
| `paladin_ret` | 60 → 1548 | **4292** |
| `priest_shadow` | 1112 → 1914 | **3134** |

**Lesson for the next anomaly**: the wrongness was three layers below where it
showed. Reading the spell data, the proc row, the rank chain and the bot
strategy all produced plausible-and-wrong theories, in that order. What settled
it in one run was logging every gate's value at the decision point —
`Alonecraft.ProcDebug = 1` (env `AC_ALONECRAFT_PROC_DEBUG=1`) makes
`Aura::GetProcEffectMask` print charges, cooldown, `canTrigger`, masks and both
raw timestamps for every aura on every proc event. Reach for it early.

#### Two things the first full matrix got wrong

Both were silent, both produced confident numbers, and both are now checked
rather than assumed. They are recorded here because the shape of the failure —
*a plausible DPS figure for something other than what was asked for* — is the
one this tool is most likely to repeat.

**The spec did not take.** `PlayerbotFactory::InitTalentsTree` applies its
talent template with `reset = false`, so the template's points are spent out of
whatever is *free* on top of the talents the character already has. A character
stored as holy stays holy: the retribution template has nothing left to spend.
Pinning `randomClassSpecProb` — which is what `--sim-spec` does — chooses the
template and does nothing about this.

The result was not subtle and was still nearly missed. Every paladin measured a
holy rotation, with "retribution" reporting 60 DPS topped by Holy Shock; every
druid measured balance, *including cat and bear*, casting Starfire in caster
form; both healing priests measured shadow. Three specs per class, three
different sets of gear, one stored talent tree.

`actor->resetTalents(true)` before `Randomize` is the fix, and it must come
before rather than after because gear is chosen to suit the talents. The
simulator now reports **talent points per tab** in its result, and the matrix
fails any spec whose dominant tab is not the one `sim_specs.py` declares — so
the evidence is in every run rather than in a rotation that looks odd.

| | before | after |
|---|---|---|
| `druid_cat` | 265 (Starfire) | **1380** (melee) |
| `paladin_ret` | 60 (Holy Shock) | **439** |

**Five yards is inside a hunter's minimum range.** The target used to spawn
five yards away, which suits melee and casters equally. A hunter there cannot
use a single one of its shots — and does not fall back to melee either. All
three hunter specs measured 63–92 DPS with *every point of it* coming from the
pet, which reads exactly like a broken talent tree.

Each spec now names the distance it fights at: melee close the gap themselves,
ranged start at 30 yards. Moving the casters out made no measurable difference
(shadow priest 1596 → 1580), which is the check that the change is about
hunters and not about everyone.

| | at 5 yards | at 30 yards |
|---|---|---|
| `hunter_mm` | 63, all pet | **995** |

#### Three faults that made every earlier number void

Found while asking why the fire mage's rotation looked broken. Each one on its
own would have produced a confident, plausible, wrong balance matrix — and the
third would have produced a *specific* wrong conclusion, which is worse than
noise.

**Passive talent auras were stripped between fights.** `ResetActor` called
`RemoveAllAuras()`, which removes passives too, and nothing re-applies them. A
talent tree is mostly passives — Ignite, Fire Power, Critical Mass, Master of
Elements — so every actor fought with the active half of its spec and none of
the scaling. Now filtered to non-passive auras only.

| | auras before | auras after | DPS before | DPS after |
|---|---|---|---|---|
| mage fire | 3 | 53 | 424 | 1291 |
| paladin ret | 4 | 46 | 425 | 649 |
| priest shadow | 19 | 50 | 1112 | 3001 |

It survived earlier runs unnoticed because form-dependent passives *are*
re-applied when the form is re-entered — so the shadow priest, the spec being
used to sanity-check everything, looked the healthiest of the lot.

**Talents were taken but their spells never granted.** `character_talent` held
Improved Scorch rank 3; `character_spell` had no row for 12873 at all. 21 of the
mage's 27 talents were in that state. `RepairSpecMask` could not see it — it
walks the *spell* map, and a spell that was never added is not in it — so
`uncastable_spells` read 0 and the run looked clean. `RepairTalentSpells` now
walks the talent map instead and learns whatever is missing.

**Spell cooldowns ran on the wall clock.** `Player::HasSpellCooldown` compares
against `getMSTime()`, which reads `steady_clock` directly and never went
through `GameTime`. With fights running at 10–40× realtime, *every cooldown
lasted 10–40× longer in game terms*. The bot's own log named it — `Can cast
spell failed. Spell not has cooldown.`, 32 times for Crusader Strike in a
30-second fight — and it fit every anomaly in the matrix: Crusader Strike (4s)
cast once per fight, Divine Storm (10s) once, Mind Blast (8s) once in 120
seconds, Chimera Shot once, Aimed Shot once.

`getMSTime()` now consults a `VirtualMSTime` atomic that
`GameTime::UpdateGameTimers` publishes under the virtual clock; it is zero on
every non-`--sim` build, so normal play takes the original branch. It shares an
origin with `GetApplicationStartTime`, so the value is continuous across the
handover.

| retribution paladin, 60s | before | after |
|---|---|---|
| Crusader Strike | 1 | 9 |
| Divine Storm | 1 | 5 |
| Judgement | 1 | 7 |
| white damage share | 81% | 38% |
| DPS | 649 | 1548 |

This is the one to remember, because of the *shape* of its error. It left
spammable casters almost untouched and crippled everything cooldown-driven, so
a balance pass built on it would have concluded that melee needs buffing —
confidently, reproducibly, and entirely as an artefact of the measuring
instrument. Note the cost of the fix: `getMSTime()` is an inline in a header
that nearly every translation unit includes, so changing it is a full rebuild.

#### Bag conflicts eat trinkets

Alonecraft's item upgrade variants share an `ItemLimitCategory` with their base
item — that is what stops a player carrying the same trinket at five upgrade
tiers. It also means a variant *sitting in a bag* blocks the base item from
being equipped with `EQUIP_ERR_CANT_CARRY_MORE_OF_THIS`, and `PlayerbotFactory`
fills the bags with spare gear. Ten of the first thirty-one runs lost a trinket
this way.

Spare weapons and armour are now destroyed before the fixed set goes on
(consumables and ammo are left, since the rotation uses them), and each piece
that fails is retried once after everything else is settled — a fury warrior's
off-hand two-hander is refused until Titan's Grip is actually on.

### Targets

| Entry | What |
|---|---|
| 2000100 | Level 83 boss-level dummy — the standard DPS reference |
| 2000101–2000104 | Levels 20 / 40 / 60 / 70, for the levelling ladder |
| 2000110 | Sparring dummy — fights back and can die. The solo-clear target |
| anything else | A real creature, with its own AI, script and aggression |

Targets can be named instead of numbered, for the ones worth naming:

```bash
python tools/sim.py --char Apold --spec "fire pve" --gear mage_fire --target patchwerk
python tools/sim_matrix.py --specs mage --clear-target patchwerk
```

`dummy`, `sparring`, and the bosses in `BOSS_TARGETS` (`tools/sim_specs.py`):
**patchwerk, thaddius, loatheb, gluth**. An entry id still works, and an
unrecognised name is an error rather than a guess. The list is deliberately
short — Naxxramas-25 bosses with no adds, no phases and no vehicle, because
anything else measures the script rather than the spec, and a solo actor cannot
satisfy those scripts anyway.

**`--clear-target` is the one to reach for**, since it swaps only the pass that
is about surviving. `--target` changes all three, which alters what burst and
sustain mean and silently breaks comparison with every other run.

The two are answering different questions and the gap between them is enormous —
the sparring dummy is `DamageModifier 2.0`, Patchwerk is `35`:

| Target | Question |
|---|---|
| sparring dummy | how much does this build reduce damage taken? |
| a real boss | is this survivable at all? |

Measured, so the scale is concrete: a P1-geared solo fire mage dies to Patchwerk
at **64 seconds**, having taken it to 94% health, TMI 42986. Nothing in the fork
solos Naxxramas yet, and the boss targets are how that claim gets checked rather
than assumed.

### Autobalanced targets, in an empty instance

```bash
python tools/sim.py --char Apold --spec "fire pve" --gear mage_fire \
    --target patchwerk --arena instance --autobalance

python tools/sim_matrix.py --specs mage --clear-target patchwerk \
    --arena instance --autobalance
```

Solo players meet autobalanced bosses, so the sim can measure them. Two things
have to be true and neither is obvious:

**The fight must be in an instance.** Every scaling path in mod-autobalance is
gated on `map->IsDungeon()` *and* a non-zero instance id. The default arena is GM
Island, a continent, where scaling can never apply -- so `--autobalance` without
`--arena instance` is refused rather than silently doing nothing.

**The instance must have an LFG level band, and it does not need creatures.**
AutoBalance reads `lfgMinLevel`/`lfgMaxLevel` from the map's LFGDungeons entry,
then refuses to touch anything below 85% of the minimum or above 115% of the
maximum. Emerald Dream had no entry, so its band was `(0 to 0)` and the module
said exactly that:

> `Creature Patchwerk (83) | is a creature outside of the expected NPC level range for the map (0 to 0), not modified.`

Reading that line at all needed `Logger.module.AutoBalance` to exist in a config
file: `Log::LoadFromConfig` discovers loggers by scanning files for the `Logger.`
prefix, so an `AC_*` variable can override a declared key's value but cannot
create one, and mod-autobalance ships without a `Logger` line. It is now declared
at `1,Console` (silent) in the Alonecraft override layer, so a single run can
raise it:

```bash
AC_LOGGER_MODULE_AUTO_BALANCE="5,Console" AC_APPENDER_CONSOLE="1,5,7" \
    python tools/sim.py --char Apold --target patchwerk --arena instance --autobalance
```

The module writes a distinct rejection message for each of its eight gates. Every
hour spent guessing why `--autobalance` changed nothing was an hour it had
already written down.

`woa_2026_08_14_01.sql` adds one row to `lfgdungeons_dbc` (id 900, map 169,
levels 80-83) and the map stays completely empty.

**Do not use a real boss room instead.** Patchwerk summons his adds the instant
he is attacked in his own chamber, and every other encounter has its own version
of that. An empty arena measures the spec; a boss room measures the script. This
is the reason the arena is empty, and it is not negotiable for a number that is
supposed to be about the spec.

**The arena is pinned to 25 players** (`woa_2026_08_14_02.sql`, overriding
MapDifficulty row 21). AutoBalance scales by the ratio of players present to the
map's nominal size, and Emerald Dream is declared a 40-player raid, so the arena
was scaling 40 -> 1 against the 25 -> 1 the fork's content actually presents.
Naxxramas-25 is the tier balanced against; change `MaxPlayers` there to model a
different one, and say so in the commit, because it moves every autobalanced
number.

Measured on Patchwerk, same actor, autobalance on:

| | HP |
|---|---|
| unscaled | 4,322,950 |
| arena as 40-player | 340,959 |
| **arena as 25-player** (current) | **361,982** |
| real Naxxramas-25 | 467,293 |

**An empty arena does not reproduce a populated one, and the raid-size pin is
only a small part of why.** Pinning 40 -> 25 moved the number 6%, not the ~27%
the size ratio alone suggests. Some of AutoBalance's inputs are accumulated from
the creatures resident in the map -- average creature level and the per-map
statistics built as creatures are added -- and an empty map has none of them. So
an autobalanced boss in the arena is roughly **23% weaker** than the same boss in
Naxxramas-25.

That is a deliberate trade, and it bounds what these numbers can be used for:

- **Valid**: comparing specs against each other, and A/B-ing a build or rotation
  change. Every spec meets the same arena.
- **Optimistic**: any absolute claim of the form "this spec can solo
  Naxxramas-25". The arena boss is **weaker** than the real one — 361,982 hp
  against 467,293 — so clearing here does not show a spec would clear there,
  while failing here does show it would fail there.

  This bullet used to say the opposite, and drew the opposite conclusion, three
  lines under the table that disproves it. Read the table.

**Which kind a target is comes from its `ScriptName`, not its entry number.**
The 2000100–2000199 band means "a simulator fixture", which is not the same
claim as "inert" — 2000110 is a fixture that fights. `SimRunner` used to test the
entry range, which silently rooted and pacified the sparring dummy the moment it
was added to the band: three 75-second fights, actor on 100% health, damage taken
of exactly 0, against a template that said 2.0× damage.

- `sim_target_dummy` → `NullCreatureAI`. Rooted and passive. Its no-op
  `EnterEvadeMode` is what stops a target that is attacked but never attacks back
  from resetting the fight halfway through. This is what a clean DPS number needs.
- `sim_sparring_dummy` → `AggressorAI` with `EnterEvadeMode` suppressed. It must
  fight back *and* still never reset: a solo caster breaks distance and line of
  sight constantly (Frost Nova, back up, keep casting), and stock evade behaviour
  turned one measured iteration into a target restored to full health with zero
  damage events recorded across 120 seconds.

Both keep real health and real armour, so damage is computed exactly as against
any other creature — unlike core's `npc_training_dummy`, which zeroes damage
taken and would report every spec at 0 DPS.

Anything else keeps its own behaviour, because TTD and TMI are meaningless
against something that does not fight back.

### Metrics

**DPS** — total damage over active combat time, with a per-ability table:
count, total, average hit, and share. Pet damage counts toward the actor and is
listed separately, which matters enormously for BM hunters, demonology and
unholy DKs.

**TTD** — time from combat start to actor death. **Censored, never averaged**: a
run that survived reports "survived all N iterations", not a mean that quietly
treats ">300s" as "300s".

**TMI** — Theck-Meloree Index, a spike-risk metric:

```
TMI = (T_ref / T_fight) · (1/f) · ln( mean( exp(f · D_i) ) ) · 10000
```

with `D_i` the damage taken in the trailing 6s window at damage event *i* as a
fraction of max health, `f = 10`, and `T_ref = 450s`. The exp/ln pair is a soft
maximum, so it is dominated by the **worst** windows: ~10000 means the worst
windows took about a full health bar. Computed with log-sum-exp, because at
`f = 10` a spec taking >7× its health in a window overflows `exp` silently.

Suppressed for fights shorter than one 6s window, where the `T_ref / T_fight`
term makes it meaningless — a 0.8-second death otherwise reports 6,175,800.

**Solo clear** — fraction of iterations where the target died and the actor
lived, plus the margin (health remaining on whichever side won).

> TMI assumes an idealised healer, and there is no healer in the sim. Read it
> alongside TTD, never alone. The tool prints this caveat with every result.

---

## What it will refuse to do

A simulator that silently measures a broken actor is worse than useless. These
all exit non-zero:

- **Uncastable spells.** The actor knows a spell it cannot cast (see specMask
  below).
- **A silent engagement failure** — an iteration where the actor dealt no damage
  at all, in a fight that ran its full length.
- **Drift between fights**, when there are enough iterations to tell.

And it prints, rather than hides:

- **`unattributed_damage`** — damage the per-ability attribution could not file.
  Currently 0%.
- **A note when drift cannot be assessed** because there are too few iterations.

---

## How it works

```
worldserver --sim --sim-char <name> --sim-target <entry>
            [--sim-spec "shadow pve"] [--sim-level 80]
            [--sim-seconds 60] [--sim-iterations 1]
            [--sim-seed 1] [--sim-buff-seconds 30] [--sim-out <path>]
```

`tools/sim.py` is a launcher. It exists because two things must be true of every
run and neither is visible at the call site: the database guard above, and ~15
`AC_*` environment overrides that neutralise everything which would otherwise
run at 40× realtime — an auction-house bot flooding the database, mod-llm-chatter
firing real HTTP requests thousands of times faster than intended. Run
`--print-env` to see all of them with the reason each is there.

Overrides go through `AC_*` environment variables rather than an edited config,
because `ConfigMgr::GetValueDefault` consults the environment on every lookup —
including module configs — so a run leaves nothing behind for the next
`sync_configs.py --write` to reconcile.

### The loop

```cpp
while (!World::IsStopped()) {
    ++World::m_worldLoopCounter;
    sWorld->Update(tickMs);      // GameTime advances by tickMs, not by the OS clock
}
```

Driving `World::Update` rather than a single `Map` is deliberate:
`OnPlayerbotUpdate` is the only path to the bot AI, `UpdateSessions` drives the
bots' fake sessions, and `ProcessQueryCallbacks` is what completes bot login.
The sim controller hangs off `OnWorldUpdate`, the last statement in the tick.

### Per iteration

```
PrepareIteration   despawn target, resurrect if dead, reset auras/cooldowns,
                   despawn temporary guardians, hand the bot to its non-combat
                   engine
   ↓ buff window (30 virtual seconds, ~0.4s wall)
TopUpForFight      full resources, cleared cooldowns, repaired durability
   ↓
StartIteration     summon target, reseed RNG, engage, zero counters
   ↓
RUNNING            until the clock runs out or someone dies
```

The buff window is after the reset and the top-up is after the window, in that
order, because the bot spends mana casting its own buffs — see "Iteration state"
below.

### Core changes

Four, all inert unless `--sim` is passed, totalling ~150 additive lines:

| File | Change |
|---|---|
| `Time/GameTime.{h,cpp}` | `EnableVirtualClock(stepMs)` — `UpdateGameTimers` advances cached values instead of reading the OS, and publishes `VirtualMSTime` |
| `Utilities/Timer.{h,cpp}` | `getMSTime()` consults `VirtualMSTime` — without this, spell cooldowns run on the wall clock |
| `Player.cpp:11857`, `Unit.cpp:12903`, `SpellAuras.cpp:2105` | three proc-timing sites switched to `GameTime::Now()` |
| `Utilities/Random.{h,cpp}`, `SFMTRand.{h,cpp}` | seeded constructor and `SetRandomSeed` |
| `Maps/MapMgr.{h,cpp}` | `SetSimArenaMapId` — update only the arena map |

A **runtime flag, not `#ifdef`**: a compile-time switch would produce a different
binary from the one that ships, defeating the entire "reuse the real core"
premise. The cost is one load-and-branch per world tick.

Everything else lives in `modules/world_of_alonecraft/src/sim/`.

---

## Things that were not obvious

Each of these cost real time to find, and each would have silently corrupted a
balance matrix.

### `specMask = 0` — the actor knows spells it cannot cast

`character_spell.specMask` is a bitmask of the talent specs a spell is active in,
and **0 is a deliberate tombstone**: `Player.cpp:3381` keeps talent spells in the
table "when not available in any spec" rather than deleting them. A tombstoned
spell fails `HasSpell`, so the bot genuinely does not have it — while the row
still sits in the database looking learned.

`PlayerbotFactory::Randomize` creates these. It calls `resetTalents()` first,
which tombstones each talent's rank-1 spell, and the trainer pass that follows
cannot teach rank 2 of anything whose rank 1 is tombstoned, so an entire rank
chain stays dead.

Measured on a shadow priest: **17 of 239 spell rows at specMask 0** — every rank
of Mind Flay and Vampiric Touch, plus Vampiric Embrace, Shadowform and
Dispersion. The bot fell through its rotation's fallback chain to **Smite**, a
Holy spell, and measured **574 DPS instead of 1163**.

The simulator now repairs this and fails the run if it cannot.

> **This affects the live server too.** `acore_characters` has 73 zero-specMask
> rows across 25 characters. Any bot it hits fights at a fraction of its
> strength, silently.

### Durability — the most dangerous bug found

Dying breaks equipment, and broken equipment gives **no stats at all**. Five
deaths to Patchwerk left **16 of 19 equipped items at zero durability**, and
because the actor is saved to the database it stayed broken. A later dummy run
measured **855 DPS where the same actor had measured 1191**.

This is the worst failure mode a simulator can have: it corrupts silently,
permanently, and *across runs*. Nothing in the output said "your gear is broken";
the number was simply lower, and plausibly so.

Fixed with `DurabilityRepairAll` per iteration — free, because a simulator has no
economy. **The general lesson: anything the game persists about the actor is a
potential leak between runs.**

### Iteration state was most of the measured variance

Three causes, all in the per-iteration reset: resources topped up *before* the
buff window rather than after (so each fight began with different, never-full
mana), cooldowns not cleared afterwards (Shadowfiend restores mana on a 5-minute
timer — available for fight one, not fight two), and temporary guardians
surviving the teardown because they are not `GetPet()`.

| | σ before | σ after |
|---|---|---|
| 60s fights | 11.5% | **2.3%** |
| 300s fights | 8.4% | **1.4%** |

The 9–12% previously assumed to be "ordinary combat variance" was almost
entirely this. Genuine per-fight combat variance is 1–2%.

### Determinism is not achievable, and does not matter

Seeded runs are not reproducible: the same seed gives no tighter agreement than
a different one. Causes include foreign damage events on the arena map, a
variable tick count before the *asynchronous* bot login completes, and bot AI
sensitivity to tick alignment. Removing them means eliminating all other activity
in the process.

Keep the seeding — it costs nothing and helps when debugging one fight — but
report means with spread rather than expecting reproducible runs. This is
affordable because the map isolation took the simulator from 4.4× to 40–80×
realtime; at the old speed it would not have been.

### Fight length is a design decision, not a parameter

| | 60s | 300s |
|---|---|---|
| mean DPS | 1191 | 716 |
| Mind Flay | 21.6% | 31.2% |
| **Shoot (wand)** | **absent** | **27.7%** |
| Mind Blast | 6 casts | 3 casts |

At 300 seconds the priest runs dry and wands for **more than a quarter of its
damage**. The gap survives every variance fix, so it is real. For a solo fork,
sustain decides long boss fights and burst decides trash, and quoting one alone
would rank specs differently and silently.

**This is now implemented.** `sim_matrix.py` runs three passes per spec rather
than one 120-second pass that sat between the two regimes and reported neither:

| pass | length | target | what it answers |
|---|---|---|---|
| `burst` | 60s × 3 | dummy 2000100 | does the opener work |
| `sustain` | 300s × 3 | dummy 2000100 | does it hold up |
| `clear` | 300s × 3 | **sparring** dummy 2000110 | can it win alone |

The table gains `sust`, `s/b` and `clear%` columns, and a `sustain/burst < 0.60`
flag. The wand-share check moved from the 120-second pass to the sustain pass,
because 300 seconds is where running dry shows and 120 was the worst place to
look for it.

`--passes burst` restores the old speed for day-to-day work. All three cost
roughly 2–3× a single-length matrix.

Whether the priest's cliff is an Alonecraft balance problem or playerbot mana
management is still open, and is exactly the kind of question this tool exists
to answer.

### Solo clear needed a target that fights back

`sim.py` has computed a solo-clear fraction — target died **and** actor lived —
since it was written, and it always reported 0. The only target available was
2000100, which holds 13.9M health and hits for 0.01×: nothing can kill it and
nothing can lose to it, so the metric that decides solo viability had no fight
to measure.

`woa_2026_08_14_00.sql` adds **2000110, the sparring dummy** — same level and
armour, 363k health, 2.0× damage. Both numbers are deliberately dials rather
than measurements, and they are the fork's difficulty knob. A retail elite was
rejected for the opposite reason: its numbers are incidental, several carry
scripts, and re-tuning would mean picking a different creature and losing
comparability with every earlier run.

**Both numbers are provisional** until the first matrix run calibrates them. If
every spec clears at 100% the dummy is too weak to separate anything; if none
does, the run is measuring the dummy. Changing either invalidates comparison
with earlier clear runs — say so in the commit and re-baseline.

### `--ab` answers "did the change help?"

`sim_matrix.py --ab` runs every pass a second time with
`AC_AI_PLAYERBOT_ALONECRAFT_SOLO_ROTATIONS=0` (`sim.py --stock`), which reverts
*both* halves of the Alonecraft solo path at once — `SpecLinkOrder` falls back
from `WoaSoloSpecLink` to `PremadeSpecLink`, and `AiFactory` stops substituting
the `woa *` strategies. So the pair isolates exactly that change.

**Deltas smaller than 2× the pooled run-to-run deviation are printed as "not
resolved by these iterations", never ranked.** The sim is not deterministic
(see above); a 1% difference over 3 iterations is noise wearing a number, and
this file's own history is five separate bugs that each produced confident,
plausible, wrong output. `tools/test_sim_metrics.py` pins the gate — 1.5%
against 2% noise must not resolve, 40% must.

The A/B also checks the switch itself: identical talent tabs in both halves of a
spec that *has* a `WoaSoloSpecLink` row means the config never reached the sim,
which is almost always a skipped `tools/sync_configs.py --write`.

### Statistical checks need power, not just thresholds

The drift check originally compared the first and last thirds and warned above
5%. It fired on two consecutive clean runs (1.79σ and 1.13σ), one of which had
its **minimum in the middle** — which no monotonic decay produces.

Raising the bar to 2.5σ then exposed the real problem: a *genuine* 14% collapse
reaches only **1.73σ over six iterations**, below any threshold that would not
also flag the noise. Spearman rank correlation over all points does no better —
real drift and noise both scored **−0.543**.

At 5–6 iterations, drift of this size is simply not resolvable by any statistic.
The check now requires **12 comparable iterations** and says it cannot tell below
that. `tools/test_sim_metrics.py` pins this, including the non-detection at
n = 6, so the threshold is not quietly lowered later.

### The repair layer was undoing the talent reset

`RepairSpecMask` existed for a real defect: `resetTalents` tombstones rank-1
spells, the factory's trainer pass then cannot teach rank 2, and the actor ends
up with spells at **specMask 0** that no spec can cast. Its comment says
"specMask 0". Its code tested `!(specMask & activeSpec)`, which is a much larger
set.

The difference is the whole of the talent reset. `resetTalents` removes a
passive talent's aura but deliberately **keeps the spell** in `m_spells`, merely
clearing the active bit from its specMask (`Player.cpp:3779` — `removeSpell` runs
only for spells that go in the spell book and are not passive). A cleared bit is
the core saying "this belongs to a spec you are not in". `RepairSpecMask`
selected exactly those rows and re-learned them, and `learnSpell` on a passive
re-applies its aura.

So the core switched the old tree off and the repair switched it back on, every
run, on a character that is saved between runs. Measured: a fire mage at talent
tabs **13/58/0** — no points in frost — carrying Ice Shards, Shatter, Arctic
Winds, Piercing Ice, Improved Frostbolt, Convection and Catabatic Winds. Beyond
inflating every number, `AiFactory` branches the mage rotation on
`HasAura(SPELL_ICE_SHARDS)`, so the bot cast **Frostfire Bolt for 45% of its
damage** on a build that cannot support it.

The test is now `specMask != 0 → skip`. Repaired counts fell from 67 to 32-37,
and the remainder are genuine tombstones.

**The contamination is also on disk.** The fix stops new accumulation; it cannot
undo what was saved. Re-clone the sim database (the Setup section above) before
trusting any number, and note that `RepairTalentSpells` still reports ~22 learned
talent spells per run on a *freshly cloned* character — that one is covering a
real factory defect, not its own mess.

### Meta gems were inert, and the socket bonus was hand-rolled

Two separate gaps in `EquipFixedGear`, both making simulated gear differ from
worn gear:

- The socket bonus was decided by counting coloured sockets and bitwise-ANDing
  gem colours. The core has `Item::GemsFitSockets()`, which is what
  `HandleSocketOpcode` uses, and which additionally rejects an unresolvable
  enchantment row and handles prismatic and meta colours. The hand-rolled version
  also only ever *set* the bonus, never cleared a stale one.
- `ToggleMetaGemsActive` was never called. A meta gem's enchantment is
  conditional — "requires at least N blue gems" — and that condition is only
  evaluated there. Every P1 set has a meta gem, so every run to date granted
  nothing for it. Confirmed by the fix: fire mage crit **12.86% → 13.3%**, which
  is Chaotic Skyflare Diamond's +21 crit rating arriving.

The general lesson for anything added here: **a repair that fires on every single
run is reporting its own bug, not the system's.**

### The rotation is a good one, not an optimal one

Playerbot AI measures the *practical* ceiling, which is arguably the right target
for a solo fork since it is what players and bots actually do. It should not be
quoted as a theoretical maximum. **Where a spec looks bad, rule out rotation
quality before redesigning it** — the per-ability table is how.

---

## HTML reports

The fixed-width tables rank specs. They cannot say *why* a spec ranks where it
does, and `matrix.json` throws away everything that could: the ability table,
the aura lists and the per-event series all collapse to three DPS samples.

`tools/sim_report.py` renders a self-contained HTML report per run, in
Warcraft Logs' vocabulary because that is the language this is already thought
about in.

```bash
python tools/sim_report.py sims/runs/matrix-20260814-130123   # a whole matrix
python tools/sim_report.py sims/runs/Apold-arcane-....json     # one run
python tools/sim_report.py --index                             # rebuild the index
python tools/sim.py --char Alenleron --spec "fire pve" --report
```

`sim_matrix.py` writes them automatically at the end of a run (`--no-html` to
skip). The index lands at `sims/index.html`, newest first.

| Tab | Answers |
|---|---|
| Summary | Fight list, and every reason to distrust the numbers, stated up front |
| Damage done | Which button carried the spec: damage, share, hits, misses, min/avg/max |
| Healing | Effective versus overheal, per spell |
| Damage taken | What reached the health bar, and what a shield ate, per shield |
| Buffs | Uptime, applications and mean/max stacks for each proc and self-buff |
| Graphs | Damage/healing per second, health and power, stacks, death markers |

No build step, no CDN, no charting library, no third-party Python — the same
constraints `site/` runs under, and the charts are inline SVG built in vanilla
JS as `site/js/tree.js` already does. The result JSON is embedded and icons are
inlined as data URIs, so a report is one file that survives being moved.

### Read the combat log, not the hooks

The script hooks are lossy. None of them carries a crit flag: every damage hook
fires *before* the roll — `ModifyMeleeDamage` at `Unit.cpp:1798` precedes
`RollMeleeOutcomeAgainst` at `1815` — and `OnDamage` receives only
`(attacker, victim, damage)`. There is no `DamageInfo` anywhere in
`src/server/game/Scripting/`. `OnDamage` also fires at `Unit.cpp:1028`, *after*
`CalcAbsorbResist` at `1669`, so a shielded actor looks like it was never
attacked. And a damage shield reaches `DealDamage` at `Unit.cpp:2218` without
ever passing the one hook that carries a spell id, so Thorns damage could not
be named at all.

All three dissolve at once by reading what Warcraft Logs reads: **the server's
own combat-log packets**. `SimCombatLog` (a `PlayerbotScript`) decodes four of
them, and they carry the crit flag, the exact absorb and resist, and the spell
id, uniformly across melee, spells, periodic ticks and heals:

| Packet | Builder | Crit |
|---|---|---|
| `SMSG_ATTACKERSTATEUPDATE` | `Unit.cpp:6916` | `HITINFO_CRITICALHIT` |
| `SMSG_SPELLNONMELEEDAMAGELOG` | `Unit.cpp:6725` | `SPELL_HIT_TYPE_CRIT` |
| `SMSG_PERIODICAURALOG` | `Unit.cpp:6826` | explicit byte |
| `SMSG_SPELLHEALLOG` | `Unit.cpp:8371` | explicit byte |
| `SMSG_SPELLDAMAGESHIELD` | `Unit.cpp:2207` | none — shields cannot crit |

The fifth is easy to forget and was: a mage has no damage shield, so a mage run
reads zero unattributed damage whether or not that packet is handled. Only a
spec running Thorns exposes it. It is also the only one of the five built with
**full** GUIDs rather than packed ones.

Two facts make this work, and both are load-bearing:

- **`ScriptMgr::OnPlayerbotPacketSent` fires at `WorldSession.cpp:300`, before
  the `if (!m_Socket) return;` at `:302`.** The ordinary
  `ServerScript::CanPacketSend` sits *after* that return, so it never fires for
  a socketless playerbot — which is every actor this simulator runs.
- **The log is sent before the damage is dealt.** `SendAttackStateUpdate` at
  `Unit.cpp:2847` precedes `DealMeleeDamage` at `:2851`;
  `SendSpellNonMeleeDamageLog` at `Spell.cpp:2859` precedes `DealSpellDamage` at
  `:2866`. So the record is always waiting when `OnDamage` arrives, and
  correlation is a lookup rather than a guess.

Measured across all eight built specs: **every damage event matched, none
unmatched**, and `unattributed_damage` is **zero** everywhere — the log names
spells the `Modify*` hooks never see. On the resto druid that recovered Thorns
as a named ability: 564 hits for 117,109 damage, **10.7% of its total output**,
which every earlier run had filed as unattributable.

The `Modify*` latch is kept as a fallback and the two are cross-checked. Crit
rates are reported out of `logged`, never out of `count`: if a packet layout
changes upstream and the decode stops matching, that must read as *missing*
data, not as "this ability never crits". `log_matched` and `log_unmatched` are
in every result for the same reason.

Absorb is measured **twice, independently** — from the log, and by watching each
absorb aura's own amount fall between samples. On the same frost run those came
to 19,167 and 18,829, 1.8% apart, which is within one sample interval. The
report says so when they diverge by more than 5%.

One heuristic this retired: min/max was going to stand in for crit, on the
theory that a max/min near 1.5 is the crit multiplier. Real data killed it —
Frostfire Bolt's ratio was **447**, because its minimum hit was a heavily
resisted 44. Inferred crit would have been fiction.

### Aura uptime is sampled, not hooked

There is no hook for a stack *decrement* — `Aura::ModStackAmount` only fires
`OnAuraApply` on the way up — and stacks are exactly what the redesigned proc
buttons are about. So auras are polled every `Alonecraft.Sim.AuraSampleMs`
(default 100 ms, written into the result as `aura_sample_ms` so the reader knows
the quantum). Permanent passives are filtered out: they are 100% by construction
and say nothing about whether a button was pressed. `Aura::IsPermanent()` cuts
the right way on both sides — Molten/Frost/Mage Armor carry a 30-minute
duration, not −1, so they stay in the table at 100%, which is precisely the "is
it being maintained" question.

`applications` (rising edges) is often more informative than uptime: 100% uptime
with three applications is a long buff, 40% with sixty is a rotation spamming
it.

## Files

| Path | What |
|---|---|
| `tools/sim.py` | Launcher, database guard, metrics, reporting |
| `tools/sim_report.py` | The HTML reports and their index |
| `tools/sim_specs.py` | The 31 specs: playerbots name, role, gear set, actor |
| `tools/sim_matrix.py` | Runs every spec across burst/sustain/clear, and the `--ab` pairing |
| `tools/sim_actions.py` | What the bot AI tried, and why each attempt failed |
| `tools/fetch_wowsims_gear.py` | Imports and validates the tier-7 gear sets |
| `sims/gear/*.json` | The imported sets, committed |
| `tools/test_sim_metrics.py` | Anchor tests for TMI, the drift check, the matrix flags and the A/B gate |
| `modules/world_of_alonecraft/src/sim/SimRunner.{h,cpp}` | Controller, damage collection, dummy AI |
| `modules/world_of_alonecraft/data/sql/db-world/woa_2026_08_13_00.sql` | Dummy creature templates |
| `modules/world_of_alonecraft/data/sql/db-world/woa_2026_08_13_01.sql` | `sim_target_dummy` script binding |
| `modules/world_of_alonecraft/data/sql/db-world/woa_2026_08_14_00.sql` | Sparring dummy 2000110, template and `sim_sparring_dummy` binding |
| `modules/world_of_alonecraft/data/sql/db-world/woa_2026_08_14_01.sql` | LFG level band for the empty arena, so it can be autobalanced |
| `modules/world_of_alonecraft/data/sql/db-world/woa_2026_08_14_02.sql` | Pins the arena to 25 players |
| `sims/runs/` | Result JSON + worldserver log per run (gitignored) |

Run the metric tests after touching `sim.py`:

```bash
python tools/test_sim_metrics.py
```

---

## Not yet done

- **The level-ladder matrix.** Entries 2000101–2000104 exist and nothing drives
  them; every pass so far is level 80. The paired A/B half of this is done —
  `sim_matrix.py --ab`.
- **Validation against the live server.** The in-game `.woatest` harness should
  be the oracle: run one spec in-game, capture the trace, assert the sim
  reproduces it within tolerance. Until then the numbers are internally
  consistent but not externally confirmed.
- **Trash packs / multi-target.**
- **A rotation-coverage gate.** `tools/verify_bot_spells.py` already measures
  which Alonecraft spells no bot strategy references; a spec whose redesigned
  talents the bot never casts will sim artificially low. Note the specMask bug
  was invisible to that check — the spell was known, correctly named, and in the
  priority list, and still never landed.
- **Baselines under `sims/baseline/` with a `--check` mode**, mirroring
  `export_talents.py --check`, to turn the sim into a regression test for future
  talent edits.
- **Tick-size sensitivity.** Everything so far uses 25 ms; 50 and 100 are
  untested.

---

## Debugging a run

Every run writes a worldserver log next to its JSON in `sims/runs/`. Useful
greps:

```bash
grep "Simulator:" <run>.log        # configuration, per-iteration results, contamination
grep "repaired"   <run>.log        # specMask repairs
```

To see what the bot AI actually decided, which is how the specMask bug was
found:

```bash
AC_AI_PLAYERBOT_LOG_IN_GROUP_ONLY=0 AC_LOGGER_PLAYERBOTS="5,Console" \
  python tools/sim.py --char <name> --iterations 1 --seconds 20
```

Then look for `A:<action> - OK | IMPOSSIBLE | USELESS | PREREQ | FAILED`, and for
`Can cast spell failed` lines naming the spell id and reason.
