# Adding an Alonecraft solo spec

One talent build and one rotation per tree, spent only while the bot is
ungrouped. Five healing specs and all three mage trees have one; the rest of the
30 do not. This is the checklist for adding the next class.

Grouped behaviour is never touched. The gate is `!player->GetGroup()`, so a bot
with a party gets upstream's build and upstream's rotation whichever way
`AiPlayerbot.AlonecraftSoloRotations` is set.

## 0. Scope

Confirm the tree is `[x]` in [TODO.md](../TODO.md)'s redesign checklist. A tree
whose redesign is unfinished gets no row — its solo build would be a
near-copy of the premade one, and its rotation would have nothing to drive.

## 1. Read the redesign

The class section of `TODO.md`, then the module implementation of each
redesigned talent under `modules/world_of_alonecraft/src/`. Resolve every name
and id against the built DBC, because names have changed:

```bash
python tools/gen_sql.py talent --name "Firebreak" --source live
python tools/gen_sql.py lookup --spell-id 200037 --source live
python tools/verify_bot_spells.py --class mage
```

`verify_bot_spells.py`'s UNCOVERED bucket is the review list of Alonecraft
spells no bot action names. Read its DEAD bucket first: a renamed spell breaks
stock actions silently, and fixing one is cheaper than writing a new one.

## 2. Author the solo build

Write it **name-keyed**, in `modules/world_of_alonecraft/deploy/builds/`, with
the reasoning in `_why`. Then encode:

```bash
python tools/bot_talents.py encode --build modules/world_of_alonecraft/deploy/builds/mage_fire_solo.json
```

Paste the emitted `AiPlayerbot.WoaSoloSpecLink.<cls>.<specNo>.80` line into
`modules/world_of_alonecraft/deploy/configs/modules/playerbots.overrides.conf`
with a short summary comment, then:

```bash
python tools/bot_talents.py audit --class mage --verbose
python tools/sync_configs.py --write --accept-changes
```

Three things to know:

- **`<specNo>` is the premade spec index, not the tab.** They coincide except
  for druid.
- **A link is a wire format.** One digit per `(tier, col)` slot, so moving a
  talent silently re-points every digit after it. That is why the build file is
  the source and the link is generated — re-encode after any tree change rather
  than editing digits.
- **`sync_configs.py` is not optional.** The sim and the server read the
  *deployed* config. Skipping it means running the old build against the new
  rotation, which produces a plausible and wrong number.

## 3. Write the rotation

`modules/mod-playerbots/src/Ai/Class/<Class>/Strategy/Alonecraft<Class>Strategy.{h,cpp}`,
one class per tree, `getName()` returning `"woa <spec> <class>"`.

**Subclass the stock spec strategy** and call its `InitTriggers` first.
`WoaFireMageStrategy : FireMageStrategy` inherits the `STRATEGY_TYPE_RANGED |
STRATEGY_TYPE_DPS` bits that drive auto-attack mode and positioning, the filler
chain, and the interrupt/armor/mana upkeep — none of which the redesign wants to
re-author. This is the difference from the healer rotations, where the `woa`
list is an *extra* damage priority beside the heal strategy.

> **The relevance band is load-bearing and fails silently.** The healer
> rotations are written in the `ACTION_DEFAULT + 0.x` band (5.0–5.9), which is
> correct beside a heal list. Stock DPS strategies are not: procs sit at 15–25,
> defensives at 29–90, fillers at 5.0–5.6. A DPS `woa` list written in the
> healer band ranks every action below every inherited trigger and barely above
> the wand. Nothing errors. The trigger fires, the action is never chosen, and
> `sim_actions.py` reports it as evaluated but never run.

Comment each `TriggerNode` with *why* its relevance sits where it does relative
to the stock nodes it is competing with.

New triggers and actions go in `<Class>Triggers.{h,cpp}` / `<Class>Actions.{h,cpp}`.
Reuse the primitives: `HasAuraStackTrigger`, `BuffTrigger`, `TwoTriggers` (which
ANDs two named triggers — the right tool whenever a rotation needs two
conditions at once, since relevance numbers cannot express one).

## 4. Register

`<Class>AiObjectContext.cpp`:

- the strategy in the **combat** factory (`*CombatStrategyFactoryInternal`) when
  it replaces the exclusive spec strategy, in the plain factory when it is
  additive;
- new triggers and actions in their creator maps.

## 5. Add the AiFactory row

One line in `WoaSoloSpecs[]` in
`modules/mod-playerbots/src/Bot/Factory/AiFactory.cpp`:

| field | means |
|---|---|
| `added` | added in place of `"healer dps"`. Healers only. |
| `replaces` | substituted for the class switch's spec strategy. Damage specs always; healers only when the replacement is MELEE-typed. |
| `buff` | substituted for the self-buff strategy, when the redesign is written against a specific buff. |

AoE strategies are left alone unless the redesign changes the AoE buttons
themselves — and note that the simulator is single-target, so a replaced AoE
list cannot be verified by it.

A **melee type swap** is only for a redesign that needs to stand in melee. Two
things change together: `GetType()` drops `STRATEGY_TYPE_RANGED`, *and* the
flee-on-contact reflex is suppressed. Then update `yards` in `tools/sim_specs.py`.

## 6. Build

New `.cpp` files are globbed at CMake configure time, so the first build after
adding one must **not** use `--skip-cmake`.

```bash
python tools/verify_scripts.py
build_and_run.bat --skip-dbc --skip-ui --skip-server
```

## 7. Verify

Stop the live worldserver first — the sim launches its own on the same port.

```bash
# did the AI press the right buttons at all?
python tools/sim_actions.py --char Apold --spec "fire pve" --gear mage_fire --seconds 30

# did the build apply, and did any of it help?
python tools/sim_matrix.py --specs mage --ab
```

Pass criteria: no `wrong_spec`, no uncastable spells, no empty gear slots, every
redesigned button appears in the `sim_actions` OK column at least once, and the
`--ab` delta is *resolved* and positive on at least one of burst / sustain /
clear with nothing badly regressed. An unresolved delta means run more
iterations, not that the change did nothing.
