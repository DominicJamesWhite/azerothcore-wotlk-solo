#!/usr/bin/env python3
"""Drive the Alonecraft offline combat simulator.

The simulator is a real worldserver launched with ``--sim``: it boots normally,
detaches GameTime from the wall clock, logs one playerbot in, fights a dummy for
N virtual seconds and writes a result JSON.  This script is what makes that
runnable without a page of environment variables.

    python tools/sim.py --char Deleona --spec "shadow pve" --target 2000100
    python tools/sim.py --char Deleona --spec "shadow pve" --iterations 5
    python tools/sim.py --print-env            # what would be set, and why

Why a launcher rather than a batch file
---------------------------------------
Two things must be true of every run and neither is visible at the call site:

1. **It must not touch the live characters database.**  The sim logs a character
   in, re-specs it, re-gears it and saves it.  Pointed at ``acore_characters``
   that is destructive.  ``--db`` defaults to ``acore_characters_sim`` and this
   script *refuses* to run against a database whose name does not end in
   ``_sim`` unless ``--i-know-what-im-doing`` is passed.

2. **A dozen settings have to be neutralised.**  Anything on a timer runs at
   whatever multiple of realtime the sim achieves, so an auction-house bot
   floods the database and mod-llm-chatter fires real HTTP requests thousands of
   times faster than intended.  Each override below is annotated with what it
   prevents; ``--print-env`` prints the lot without launching anything.

Overrides go through ``AC_*`` environment variables rather than an edited
config, because ``ConfigMgr::GetValueDefault`` consults the environment on every
lookup -- including module configs -- so a run leaves no trace in the deployed
config tree that the next ``sync_configs.py --write`` would have to reconcile.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_wowsims_gear  # noqa: E402
import sim_specs  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
DEFAULT_BIN = Path(r"C:\Build\bin\RelWithDebInfo\worldserver.exe")

# Each entry: env var -> (value, why).  The "why" is printed by --print-env and
# is the only documentation of these that exists; keep it accurate.
def build_env(db_info: str, tick_ms: int, stock: bool = False,
              autobalance: bool = False,
              seal_mana_pct: int | None = None) -> dict[str, tuple[str, str]]:
    env = {
        "AC_CHARACTER_DATABASE_INFO": (
            db_info,
            "the sim re-specs, re-gears and saves the actor -- it must never be "
            "pointed at the live characters database",
        ),
        "AC_ALONECRAFT_SIM_TICK_MS": (
            str(tick_ms),
            "virtual milliseconds advanced per world tick; smaller is more "
            "faithful to a live server's 50ms cadence, larger is faster",
        ),
        # -- things that would run at speed --------------------------------
        "AC_PLAYER_SAVE_INTERVAL": (
            "86400000",
            "autosave is on game time, so the actor would otherwise be written "
            "to the database constantly. NOT larger: PlayerStorage.cpp computes "
            "m_nextSave * 3 / 2 on a uint32, and above ~1.43e9 that overflows "
            "and asserts on every character login",
        ),
        "AC_AUCTION_HOUSE_BOT_ENABLE_SELLER": (
            "0", "an AH bot posting under a fast clock floods the database"),
        "AC_AUCTION_HOUSE_BOT_BUYER_ENABLED": (
            "0", "as above, on the buying side"),
        "AC_LOG_DB_OPT_CLEAR_TIME": (
            "0", "time-keyed log cleanup, guarded by an early-out in the tick"),
        "AC_DUNGEON_RESPAWN_ENABLE": (
            "0", "timer-driven, and irrelevant to an arena fight"),
        "AC_MYTHIC_PLUS_ENABLE": (
            "0", "timer-driven, and irrelevant to an arena fight"),
        "AC_TRANSMOGRIFICATION_ENABLE": (
            "0", "not needed, and it queries on login"),
        # -- determinism and quiet ------------------------------------------
        "AC_MAP_UPDATE_THREADS": (
            "0",
            "the MapUpdater pool makes map update order nondeterministic; the "
            "sim runs one map anyway (MapMgr::SetSimArenaMapId)",
        ),
        "AC_THREAD_POOL": ("1", "one worker, so ordering is stable"),
        "AC_MAX_PING_TIME": ("30", "no live sessions to ping"),
        "AC_CONSOLE_ENABLE": (
            "0", "no CLI thread: the sim is not interactive and exits on its own"),
        # -- keep the bot AI, drop the bot population ------------------------
        "AC_AI_PLAYERBOT_RANDOM_BOT_AUTOLOGIN": (
            "0",
            "disables the random-bot spawn/despawn loop while leaving "
            "AiPlayerbot.Enabled on, so our actor still gets a rotation",
        ),
        "AC_AI_PLAYERBOT_MIN_RANDOM_BOTS": ("0", "as above"),
        "AC_AI_PLAYERBOT_MAX_RANDOM_BOTS": ("0", "as above"),
    }

    # --stock: the other half of an A/B. One switch reverts both halves of the
    # Alonecraft solo path -- PlayerbotAIConfig::SpecLinkOrder falls back from
    # WoaSoloSpecLink to PremadeSpecLink, and AiFactory stops substituting the
    # "woa *" strategies -- so a paired run isolates exactly that change and
    # nothing else. A generic --env passthrough would do the same job while
    # hollowing out the --print-env table, which is the only documentation
    # these overrides have.
    if stock:
        env["AC_AI_PLAYERBOT_ALONECRAFT_SOLO_ROTATIONS"] = (
            "0",
            "A/B control: revert to upstream's premade build and rotation, so "
            "the paired run measures the Alonecraft solo spec and nothing else",
        )

    # Named rather than a generic passthrough, for the reason above: an override
    # with no entry in this table is an override nobody can find again.
    if seal_mana_pct is not None:
        env["AC_AI_PLAYERBOT_ALONECRAFT_SEAL_MANA_PCT"] = (
            str(seal_mana_pct),
            "mana %% at which a solo holy paladin trades its damage seal for "
            "Seal of Wisdom. 0 disables the swap, restoring upstream's "
            "permanent Wisdom -- the baseline this dial is measured against",
        )

    # AutoBalance: off by default, because a scaled boss is a different boss and
    # the default has to be the one whose numbers are comparable between runs.
    #
    # On is the more *realistic* setting -- a solo player in Alonecraft meets
    # autobalanced bosses, not raid-tuned ones -- which is why it is a flag
    # rather than a hard disable.
    #
    # NOTE: it only bites on an instance map. Every scaling path in
    # ABAllCreatureScript is gated on map->IsDungeon(), and the sim arena is GM
    # Island on map 1, a continent. So --autobalance without an instance arena
    # changes nothing, and that is a property of where the arena is rather than
    # a decision anyone made.
    env["AC_AUTO_BALANCE_ENABLE_GLOBAL"] = (
        "1" if autobalance else "0",
        "scale creature health and damage to party size, as a solo player "
        "actually meets them" if autobalance else
        "a scaled boss is a different boss; the default keeps raid-tuned "
        "numbers comparable between runs",
    )

    return env


def theck_meloree_index(incoming: list, max_health: int, fight_s: float,
                        window_s: float = 6.0, f: float = 10.0,
                        t_ref_s: float = 450.0) -> float:
    """Theck-Meloree Index: a spike-risk metric, not an average-mitigation one.

        TMI = (T_ref / T_fight) * (1/f) * ln( mean( exp(f * D_i) ) ) * 10000

    where D_i is damage taken in the trailing `window_s` at damage event i, as a
    fraction of max health. The exp/ln pair is a soft maximum, so the result is
    dominated by the *worst* windows: ~10000 means the worst windows took about a
    full health bar.

    Computed via log-sum-exp. At f = 10 a spec taking more than ~7x its health in
    a window overflows exp() and would silently return inf, which is precisely
    the case anyone reading a survivability number cares most about.
    """
    if not incoming or not max_health or fight_s <= 0:
        return 0.0

    # Trailing-window sums, two pointers over an already time-ordered series.
    windows, start, running = [], 0, 0
    for i, (t, amount) in enumerate(incoming):
        running += amount
        # <=, not <. A hit exactly window_s old is outside a trailing window of
        # that length. With < it stays in, so a series of one full-health hit
        # every 6s put two hits in every 6s window and doubled every TMI --
        # caught only because the anchor test below pins a value the definition
        # fixes exactly.
        while incoming[start][0] <= t - window_s * 1000:
            running -= incoming[start][1]
            start += 1
        windows.append(running / max_health)

    # log-sum-exp: ln(mean(exp(f*D))) = m + ln(mean(exp(f*D - m)))
    scaled = [f * d for d in windows]
    m = max(scaled)
    total = sum(math.exp(s - m) for s in scaled) / len(scaled)
    lse = m + math.log(total)

    return (t_ref_s / fight_s) * (1.0 / f) * lse * 10000.0


def print_mitigation(result: dict, iters: list) -> None:
    """What stopped incoming damage, as distinct from how much got through.

    Damage taken is a net number and a net number cannot be tuned: a spec that
    ends a fight on 60% health by dodging a third of the swings and one that
    does it by absorbing them want opposite changes. This splits the gross
    incoming swing into the mechanisms that removed parts of it.

    Two of the four sections are measured and two are not, and the difference is
    marked rather than smoothed over:

      avoidance   measured exactly -- every swing resolved against the actor is
                  one SMSG_ATTACKERSTATEUPDATE, including the ones that dealt
                  nothing and are therefore invisible to damage_taken.
      block/absorb/resist
                  measured exactly, in damage, off the same packets.
      avoided damage
                  ESTIMATED, as avoided swings x the mean landing swing. The
                  server never computes what a dodged swing would have hit for,
                  so no exact figure exists to report.
      reduction auras
                  a statement of what was ACTIVE, not of what it prevented. The
                  core applies these as a multiplier inside the damage
                  calculation and never reports the difference, so attributing
                  damage to them would be invention.
    """
    mits = [it.get("mitigation") for it in iters if it.get("mitigation")]
    mits = [m for m in mits if m.get("swings")]

    if not mits:
        print()
        print("mitigation    the actor was never meleed, so there is nothing to "
              "attribute. Ranged specs behind a pet holding aggro read this way, "
              "and it is a positioning result rather than a defensive one.")
        return

    n = len(mits)
    tot = lambda k: sum(m.get(k, 0) for m in mits)

    swings = tot("swings")
    avoided = tot("misses") + tot("dodges") + tot("parries") + \
        tot("deflects") + tot("immune")
    landed_swings = swings - avoided

    landed = tot("landed")
    blocked, absorbed, resisted = tot("blocked"), tot("absorbed"), tot("resisted")

    # The mean LANDING swing, gross -- what a swing is worth when it connects.
    # Avoided swings are excluded from the denominator on purpose: including
    # them would divide by the very thing being estimated and halve the answer.
    gross_landed = landed + blocked + absorbed + resisted
    mean_swing = gross_landed / landed_swings if landed_swings else 0
    avoided_est = avoided * mean_swing

    gross_est = gross_landed + avoided_est
    pct = lambda v: (100 * v / gross_est) if gross_est else 0

    print()
    print("mitigation and avoidance      (per fight, mean of "
          f"{n} iteration{'s' if n > 1 else ''})")
    print(f"  swings taken  {swings / n:.0f}   of which {avoided / n:.0f} were "
          f"avoided outright ({100 * avoided / swings:.0f}%)")
    print()
    print(f"  {'mechanism':<16}{'count':>8}{'rate':>8}{'damage':>12}{'share':>8}")
    print("  " + "-" * 52)

    rows = [
        ("miss",    tot("misses"),   None),
        ("dodge",   tot("dodges"),   None),
        ("parry",   tot("parries"),  None),
        ("deflect", tot("deflects"), None),
        ("immune",  tot("immune"),   None),
    ]
    for label, count, _ in rows:
        if not count:
            continue
        share = count * mean_swing
        print(f"  {label:<16}{count / n:>8.0f}{100 * count / swings:>7.0f}%"
              f"{share / n:>12.0f}{pct(share):>7.0f}%   estimated")

    for label, count, dmg in (("block", tot("blocks"), blocked),
                              ("absorb", None, absorbed),
                              ("resist", None, resisted)):
        if not dmg:
            continue
        cnt = f"{count / n:>8.0f}" if count is not None else " " * 8
        rate = f"{100 * count / swings:>7.0f}%" if count is not None else " " * 8
        print(f"  {label:<16}{cnt}{rate}{dmg / n:>12.0f}{pct(dmg):>7.0f}%   measured")

    print(f"  {'REACHED HP':<16}{landed_swings / n:>8.0f}"
          f"{100 * landed_swings / swings:>7.0f}%{landed / n:>12.0f}"
          f"{pct(landed):>7.0f}%   measured")

    # Absorb is the one mechanism whose per-source split the core does report,
    # because a shield aura's remaining amount IS the ledger. Worth printing
    # separately: "absorbed 40k" is not actionable, "Power Word: Shield absorbed
    # 40k across 12 applications" is.
    # Per iteration, as [spell, name, absorbed, applications, consumed,
    # expiredWithShield]; summed here because the run-level table does not carry
    # the split.
    shields: dict = {}
    for it in iters:
        for row in it.get("absorb", []):
            spell, name, absorbed, applications = row[0], row[1], row[2], row[3]
            if not absorbed:
                continue
            cur = shields.setdefault(spell, {"name": name, "absorbed": 0, "applied": 0})
            cur["absorbed"] += absorbed
            cur["applied"] += applications

    if shields:
        print()
        print(f"  {'absorb source':<34}{'absorbed':>10}{'applied':>9}")
        print("  " + "-" * 53)
        for spell, s in sorted(shields.items(), key=lambda kv: -kv[1]["absorbed"]):
            label = f"{s['name']} ({spell})"
            print(f"  {label[:33]:<34}{s['absorbed'] / n:>10.0f}"
                  f"{s['applied'] / n:>9.1f}")

    # Chance versus outcome, side by side. Either alone is uninterpretable: 34%
    # dodge next to 33% dodged says the roll works, 34% next to 4% says the
    # swings are not arriving the way the stat assumes.
    d = iters[0].get("defense") or {}
    if d:
        obs = lambda k: 100 * tot(k) / swings
        print()
        print(f"  {'defence':<16}{'rated':>9}{'observed':>10}")
        print("  " + "-" * 37)
        print(f"  {'dodge':<16}{d.get('dodge_pct', 0):>8.1f}%{obs('dodges'):>9.1f}%")
        print(f"  {'parry':<16}{d.get('parry_pct', 0):>8.1f}%{obs('parries'):>9.1f}%")
        print(f"  {'block':<16}{d.get('block_pct', 0):>8.1f}%{obs('blocks'):>9.1f}%")
        print(f"  {'armor':<16}{d.get('armor', 0):>9}")

        # Deliberately not given a damage column. See the docstring.
        auras = d.get("reduction_auras", [])
        if auras:
            print()
            print("  damage-reduction auras active at pull (amount is the aura's "
                  "own value, not damage prevented -- the core never reports that):")
            for a in auras:
                print(f"    {a['amount']:>5}  {a['name']} ({a['spell']})")


def run_once(args, out_path: Path, log_path: Path) -> dict:
    """One worldserver process, which runs args.iterations fights inside it.

    Iterations are in-process deliberately: booting the world costs ~28 wall
    seconds and a 60-virtual-second fight costs ~1.5, so a process per iteration
    would spend 95% of its life loading maps it is about to freeze.
    """
    env = dict(os.environ)
    for key, (value, _why) in build_env(args.db_info, args.tick_ms,
                                        getattr(args, "stock", False),
                                        getattr(args, "autobalance", False),
                                        getattr(args, "seal_mana_pct", None)).items():
        env[key] = value

    cmd = [
        str(args.binary),
        "--sim",
        "--sim-char", args.char,
        "--sim-target", str(args.target),
        "--sim-map", str(args.arena_map),
        "--sim-x", f"{args.arena_x}",
        "--sim-y", f"{args.arena_y}",
        "--sim-z", f"{args.arena_z}",
        "--sim-seconds", str(args.seconds),
        "--sim-seed", str(args.seed),
        "--sim-iterations", str(args.iterations),
        "--sim-out", str(out_path),
    ]
    if args.spec:
        cmd += ["--sim-spec", args.spec]
    if args.level:
        cmd += ["--sim-level", str(args.level)]
    if args.gear_arg:
        cmd += ["--sim-gear", args.gear_arg]
    if args.range:
        cmd += ["--sim-range", str(args.range)]

    started = time.time()
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        subprocess.run(cmd, env=env, cwd=str(args.binary.parent),
                       stdout=log, stderr=subprocess.STDOUT)
    wall = time.time() - started

    if not out_path.exists():
        raise SystemExit(
            f"sim produced no result file. Last lines of {log_path}:\n"
            + "\n".join(log_path.read_text(errors="replace").splitlines()[-25:])
        )

    result = json.loads(out_path.read_text())

    # A stale result in a matrix directory should degrade to blank views, not
    # abort a thirty-spec run; an unknown *major* is a different thing and stops.
    schema = result.get("schema", "alonecraft.sim.result/0")
    if schema.rsplit("/", 1)[0] != "alonecraft.sim.result":
        raise SystemExit(f"unknown result schema {schema!r} in {out_path}")
    if schema != "alonecraft.sim.result/1":
        print(f"  note: result is {schema}, this tool expects "
              f"alonecraft.sim.result/1; newer views will be empty")

    result["process_wall_s"] = round(wall, 1)
    return result


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--report", action="store_true",
                   help="also write a self-contained HTML report next to the "
                        "result (see tools/sim_report.py)")
    p.add_argument("--char", help="character name to sim (a SIMBOT-account character)")
    p.add_argument("--spec", default="",
                   help="playerbots premade spec name, e.g. 'shadow pve'. Without it "
                        "the character is simmed exactly as stored -- which for a "
                        "fresh sim character means naked.")
    p.add_argument("--level", type=int, default=0, help="level to configure (0 = keep)")
    p.add_argument("--gear", default="",
                   help="a spec key from sims/gear (e.g. 'priest_shadow'), or a path to "
                        "a gear json. Without it the actor wears whatever "
                        "PlayerbotFactory rolled, which differs between runs and "
                        "between specs -- fine for one spec, useless for a comparison.")
    p.add_argument("--target", default=str(sim_specs.DUMMY_TARGET),
                   help="creature to fight: an entry id, or a name -- "
                        "'dummy' (inert, the DPS reference), 'sparring' (fights "
                        "back and can die), or a real boss such as 'patchwerk'. "
                        "See BOSS_TARGETS in tools/sim_specs.py.")
    p.add_argument("--seconds", type=int, default=60, help="virtual seconds per fight")
    p.add_argument("--iterations", type=int, default=1,
                   help="fights per run, all inside one worldserver process")
    p.add_argument("--seed", type=int, default=1, help="base seed; iteration i uses seed+i")
    p.add_argument("--range", type=float, default=0.0,
                   help="yards between actor and target at the start of a fight "
                        "(0 = the server default of 5). Five is inside a hunter's "
                        "minimum range, so hunters need this.")
    p.add_argument("--tick-ms", type=int, default=25)
    p.add_argument("--db", default="acore_characters_sim")
    p.add_argument("--db-host", default="127.0.0.1;3306;acore;acore")
    p.add_argument("--binary", type=Path, default=DEFAULT_BIN)
    p.add_argument("--out-dir", type=Path, default=REPO / "sims" / "runs")
    p.add_argument("--tag", default="",
                   help="fixed basename for the result and log, instead of a timestamped "
                        "one. sim_matrix.py uses it so it knows where the file landed.")
    p.add_argument("--arena", choices=sorted(sim_specs.ARENAS), default="gm",
                   help="where the fight happens. 'gm' is GM Island, a "
                        "continent (default). 'instance' is an empty raid "
                        "instance, which is the only place mod-autobalance can "
                        "apply. See ARENAS in tools/sim_specs.py.")
    p.add_argument("--autobalance", action="store_true",
                   help="leave mod-autobalance on, so the target is scaled to a "
                        "party of one -- what a solo player actually meets. "
                        "Only has an effect on an instance map; the default "
                        "arena is a continent.")
    p.add_argument("--stock", action="store_true",
                   help="run with the Alonecraft solo build and rotation OFF, "
                        "i.e. upstream's premade spec. The control half of an "
                        "A/B; see sim_matrix.py --ab.")
    p.add_argument("--seal-mana-pct", type=int, default=None,
                   help="override AiPlayerbot.AlonecraftSealManaPct for this run: "
                        "the mana %% at which a solo holy paladin trades its "
                        "damage seal for Seal of Wisdom. 0 disables the swap. "
                        "Sweep it to see the damage/sustain trade.")
    p.add_argument("--print-env", action="store_true",
                   help="print the environment overrides and exit")
    p.add_argument("--i-know-what-im-doing", action="store_true",
                   help="permit a characters database not named *_sim")
    args = p.parse_args()

    # Names resolve to entry ids here, once, so everything downstream -- the
    # command line, the result JSON, the tag -- carries the id that was actually
    # fought rather than a label that has to be resolved again to be trusted.
    args.target = sim_specs.resolve_target(args.target, sim_specs.DUMMY_TARGET)

    # --autobalance on a continent is a no-op, and a flag that silently does
    # nothing is worse than no flag. Say so rather than produce raid-tuned
    # numbers under a label that claims otherwise.
    if args.autobalance and args.arena == "gm":
        print("--autobalance has no effect on the GM Island arena: "
              "mod-autobalance only scales creatures on instance maps "
              "(ABAllCreatureScript gates every path on map->IsDungeon()). "
              "Add --arena instance.", file=sys.stderr)
        return 2

    args.arena_map, args.arena_x, args.arena_y, args.arena_z, _why =         sim_specs.ARENAS[args.arena]

    args.db_info = f"{args.db_host};{args.db}"

    args.gear_arg = ""
    if args.gear:
        path = Path(args.gear) if args.gear.endswith(".json") \
            else REPO / "sims" / "gear" / f"{args.gear}.json"
        if not path.exists():
            print(f"no gear set at {path}. Run tools/fetch_wowsims_gear.py.", file=sys.stderr)
            return 2
        items = json.loads(path.read_text())["items"]
        items = sim_specs.apply_gear_swaps(args.gear, items)
        args.gear_arg = fetch_wowsims_gear.to_arg(items)

    if args.print_env:
        for key, (value, why) in build_env(args.db_info, args.tick_ms,
                                       getattr(args, "stock", False),
                                        getattr(args, "autobalance", False),
                                        getattr(args, "seal_mana_pct", None)).items():
            print(f"{key} = {value}\n    {why}\n")
        return 0

    if not args.char:
        p.error("--char is required")

    # The one guard that matters. A sim run re-specs, re-gears and saves the
    # actor; against the live database that is destructive and irreversible.
    if not args.db.endswith("_sim") and not args.i_know_what_im_doing:
        print(f"refusing to run against characters database '{args.db}': the sim "
              f"rewrites and saves the actor. Use a *_sim clone, or pass "
              f"--i-know-what-im-doing.", file=sys.stderr)
        return 2

    if not args.binary.exists():
        print(f"worldserver not found at {args.binary}", file=sys.stderr)
        return 2

    # Absolute, always. The worldserver runs with cwd set to its own bin
    # directory, so a relative --out-dir resolves there instead of here: the
    # sim runs to completion and then cannot write its result, losing the whole
    # run to a path that looked fine on the command line.
    args.out_dir = args.out_dir.resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    tag = args.tag or f"{args.char}-{args.spec.replace(' ', '_') or 'asis'}-{stamp}"

    out = args.out_dir / f"{tag}.json"
    log = args.out_dir / f"{tag}.log"
    print(f"running {args.iterations} x {args.seconds}s ...", flush=True)
    result = run_once(args, out, log)

    iters = result.get("iterations", [])
    for it in iters:
        print(f"  [{it['i'] + 1}/{len(iters)}] seed {it['seed']}: {it['dps']:8.1f} DPS "
              f"({it['damage']} damage, {it['damage_events_from_actor']} events)")

    dps = [it["dps"] for it in iters]
    print()
    print(f"character   {result['character']}  spec '{result.get('spec', '')}'  "
          f"level {result.get('level', '?')}")
    print(f"target      {result['target_entry']}")
    if args.gear:
        print(f"gear        {args.gear}: {result.get('gear_equipped', 0)} equipped, "
              f"{result.get('gear_failed', 0)} failed, mean ilvl "
              f"{result.get('gear_ilvl', 0)}")
    print(f"stats       AP {result.get('attack_power', 0)}  SP "
          f"{result.get('spell_power', 0)}  crit {result.get('crit_pct', 0):.1f}%")
    print(f"iterations  {len(dps)}")
    print(f"speed       {result['realtime_factor']:.0f}x realtime "
          f"({result['process_wall_s']}s wall for {result['duration_s']}s of combat)")
    if dps:
        print(f"mean DPS    {statistics.mean(dps):.1f}")
    if len(dps) > 1:
        sd = statistics.stdev(dps)
        # Reported rather than a confidence interval because runs are not
        # paired: the sim is not byte-deterministic (see the plan), so a
        # same-seed rerun is not a repeat of the same fight.
        print(f"stdev       {sd:.1f}  ({100 * sd / statistics.mean(dps):.1f}%)")
        print(f"range       {min(dps):.1f} .. {max(dps):.1f}")

    # -- Survivability -----------------------------------------------------
    # Only meaningful against a real creature; the simulator's own dummies never
    # fight back, so every iteration times out and every number here is zero.
    outcomes = [it.get("outcome", "timeout") for it in iters]
    if any(o != "timeout" for o in outcomes) or any(it.get("damage_taken") for it in iters):
        deaths = [it for it in iters if it.get("outcome") == "actor_died"]
        kills = [it for it in iters if it.get("outcome") == "target_died"]
        max_hp = result.get("actor_max_health", 0)

        print()
        print(f"survivability")
        print(f"  outcomes    {len(kills)} killed / {len(deaths)} died / "
              f"{len(iters) - len(kills) - len(deaths)} timed out")

        # TTD is censored, never averaged. A run that survived contributes "at
        # least this long", and treating ">300s" as "300s" would quietly report
        # a spec that never dies as one that dies at exactly the time limit.
        if deaths:
            ttds = sorted(it["duration_s"] for it in deaths)
            median = ttds[len(ttds) // 2]
            print(f"  median TTD  {median:.1f}s  (over {len(deaths)} death(s); "
                  f"{len(iters) - len(deaths)} survived and are censored, not averaged)")
        else:
            print(f"  median TTD  survived all {len(iters)} iteration(s) — no TTD to report")

        # TMI needs a fight long enough to contain the windows it averages over.
        # Its T_ref / T_fight term is 450/T, so a 0.8-second death multiplies by
        # 562 and reports 6,175,800 -- arithmetically correct and completely
        # meaningless. Below one window there is nothing to take a soft maximum
        # of, so say so rather than print a number that invites belief.
        WINDOW_S = 6.0
        scoreable = [it for it in iters if it["duration_s"] >= WINDOW_S]

        if not max_hp:
            print(f"  TMI         unavailable (actor max health not reported)")
        elif not scoreable:
            longest = max(it["duration_s"] for it in iters)
            print(f"  TMI         not meaningful — longest fight was {longest:.1f}s, "
                  f"shorter than the {WINDOW_S:.0f}s window TMI averages over. "
                  f"The actor dies too fast to have a spike profile.")
        else:
            tmis = [theck_meloree_index(it.get("incoming", []), max_hp, it["duration_s"])
                    for it in scoreable]
            note = "" if len(scoreable) == len(iters) else \
                f"  ({len(iters) - len(scoreable)} fight(s) too short to score, excluded)"
            print(f"  TMI         {statistics.mean(tmis):.0f}"
                  f"   (~10000 = worst 6s windows took about a full health bar){note}")

        # Solo clear: killed it AND lived. The margin says how close it was, which
        # is what turns a pass/fail into something tunable.
        cleared = [it for it in kills]
        print(f"  solo clear  {len(cleared)}/{len(iters)}")
        if cleared:
            print(f"    margin    actor ended on "
                  f"{statistics.mean(it['actor_hp_pct'] for it in cleared):.0f}% health")
        if deaths:
            print(f"    margin    boss survived on "
                  f"{statistics.mean(it['target_hp_pct'] for it in deaths):.0f}% health")

        # The plan's own caveat, printed rather than remembered: TMI assumes an
        # idealised healer keeping the tank alive, and there is no healer here.
        print(f"  NOTE        no healer in the sim, so TMI's idealised-healer premise "
              f"is stretched; read it alongside TTD, never alone.")

        print_mitigation(result, iters)

    abilities = result.get("abilities", [])
    if abilities:
        print()
        print(f"{'ability':<34}{'src':<5}{'kind':<10}{'hits':>7}{'damage':>10}"
              f"{'share':>8}{'avg':>9}")
        print("-" * 83)
        for a in abilities:
            avg = a["damage"] / a["count"] if a["count"] else 0
            label = a["name"] if a["spell"] == 0 else f"{a['name']} ({a['spell']})"
            print(f"{label[:33]:<34}{'pet' if a['pet'] else 'you':<5}{a['kind']:<10}"
                  f"{a['count']:>7}{a['damage']:>10}{100 * a['share']:>7.1f}%{avg:>9.0f}")

        # Only one damage hook carries a SpellInfo, and it fires before absorb
        # and resist while the authoritative amount arrives later without one.
        # Anything the two could not be matched up lands here. A large figure
        # means the table below is not trustworthy, and saying so is the point.
        unattributed = result.get("unattributed_damage", 0)
        if unattributed:
            pct = 100 * unattributed / result["damage"] if result["damage"] else 0
            print(f"\n  {unattributed} damage ({pct:.1f}%) could not be attributed "
                  f"to a spell.")

            # Why, not only how much. All-spell with no latch at all is the
            # damage shield signature: Thorns and its kin reach DealDamage on a
            # path that never calls CalculateSpellDamageTaken, and no hook
            # exists there to name the spell.
            miss = result.get("latch_miss", {})
            by_type = result.get("unattributed_by_type", {})
            if by_type.get("spell") == unattributed and not miss.get("attacker_mismatch"):
                print("  All of it is spell damage with no hook at all, which is "
                      "what a damage shield (Thorns, Retribution Aura) looks "
                      "like: the core deals it without a nameable spell.")

    if args.report:
        try:
            import sim_report
            data = sim_report.summarise(result, out)
            icons, _missing = sim_report.inline_icons(sim_report.spell_ids_in(data))
            html = sim_report.render_report(
                data, icons, out.with_name(out.stem + ".report.html"))
            print(f"\n  report: {html}")
        except Exception as exc:
            print(f"\n  (report failed: {exc})")

    # An actor that cannot cast its own spells measures a floor, not a spec.
    # This is loud and fails the run, because averaged into a balance matrix it
    # would read as a genuine result -- which is exactly how a shadow priest
    # came to report 574 DPS instead of 1171.
    # A spec wearing fewer pieces than the set specifies is not comparable with
    # one wearing all of them, and the difference is invisible in a DPS number.
    if result.get("gear_failed", 0):
        print(f"\nWARNING: {result['gear_failed']} gear slot(s) could not be equipped, so "
              f"this actor is under-geared relative to any spec that equipped its full "
              f"set. See {log} for which items and why.")
        return 1

    uncastable = result.get("uncastable_spells", 0)
    if uncastable:
        print(f"\nWARNING: {uncastable} spell(s) the actor knows are not castable "
              f"and could not be repaired (specMask 0). Treat this run as a floor, "
              f"not a measurement; see {log}.")
        return 1

    # Pet drift: the same test as the DPS one below, but categorical, so it has
    # no statistical-power problem and fires correctly at two iterations.
    #
    # A pet is a second actor with its own stats and its own way of silently
    # changing between fights, and the DPS drift check cannot see it: the pet is
    # a minority of the damage, so a 4x change in it moves the total by well
    # under the noise the drift test needs to clear.
    #
    # That is not hypothetical either. ResetActor called RemoveAllAuras on the
    # pet, which deleted Hunter Pet Scaling (34902-34904, 61017) permanently --
    # pet passives are applied by one CastSpell at learn time and nothing
    # re-applies them. Pet melee then landed 104-138 per hit instead of 570-725,
    # flat for a whole iteration, in a different iteration for each hunter spec.
    # It read as "hunters are noisy" (CV 17-47% against <=8% for every petless
    # spec) for an entire balance pass before anything named it.
    pets = [it.get("pet") for it in iters]
    if any(p and p.get("entry") for p in pets):
        FIELDS = ("entry", "level", "attack_power", "max_health", "passives")
        first = pets[0] or {}
        changed = sorted({
            f for p in pets[1:]
            for f in FIELDS
            if (p or {}).get(f) != first.get(f)
        })

        if changed:
            print(f"\nWARNING: the pet changed between iterations "
                  f"({', '.join(changed)}), so these fights are not samples of "
                  f"one actor. Per-iteration pet state:")
            for n, p in enumerate(pets, 1):
                p = p or {}
                print(f"  iter {n}: " + "  ".join(
                    f"{f}={p.get(f, 0)}" for f in FIELDS))
            return 1

    # Drift check: iterations must be samples of one process, not a decaying
    # one. Compare the first and last thirds; a mean that moves more than the
    # spread can explain means state is leaking between fights and no amount of
    # extra iterations will help, because they are not independent.
    #
    # This is not hypothetical. A 5 x 300s run read 824 -> 773 -> 687 -> 685 ->
    # 706 because the actor did not start each fight with full mana or a fresh
    # Shadowfiend, and the mean of that sequence is not a measurement of
    # anything. It is also why a *visual* check is not enough: an earlier 3 x 60s
    # run looked like it declined and did not.
    # Only meaningful when every iteration ran the same length. Fights that end
    # in a death end at different times by definition, so their DPS varies for a
    # legitimate reason and comparing thirds would flag every lethal encounter as
    # broken -- as it did on the first Patchwerk run, where 5 sub-second deaths
    # produced a confident "-95.1% drift" from pure noise.
    comparable = [it for it in iters if it.get("outcome", "timeout") == "timeout"]

    # 12 is the point at which this test has the power to be worth running.
    #
    # Below it the head and tail are 2-3 samples each and the standard error of
    # their difference is comparable to the effect being looked for: the genuine
    # 14% collapse that the reset fixes cured registers at only 1.73 sigma over 6
    # iterations, while two pure-noise runs registered 1.79 and 1.13. A threshold
    # low enough to catch the first fires constantly on the others, and Spearman
    # over all points does no better -- real drift and noise both scored -0.543.
    # So the check does not guess; it says it cannot tell.
    DRIFT_MIN_ITERATIONS = 12

    if 0 < len(comparable) < DRIFT_MIN_ITERATIONS:
        print(f"\nnote: {len(comparable)} comparable iteration(s) is too few to test "
              f"for drift between fights ({DRIFT_MIN_ITERATIONS}+ needed). Run more "
              f"if the mean matters.")

    if len(comparable) >= DRIFT_MIN_ITERATIONS:
        cdps = [it["dps"] for it in comparable]
        third = max(1, len(cdps) // 3)
        head, tail = cdps[:third], cdps[-third:]
        head_mean, tail_mean = statistics.mean(head), statistics.mean(tail)
        drift_pct = 100 * (tail_mean - head_mean) / statistics.mean(cdps)

        # Judged against the run's own noise, not a fixed percentage.
        #
        # The first version flagged anything over 5%, chosen by eye. At n = 6 the
        # head and tail are two samples each, so the standard error of their
        # difference is sd * sqrt(2/2) = sd -- and with sd around 5% of the mean,
        # a 5% threshold fires on almost every run. It duly reported "6.1% drift"
        # on two consecutive runs that were 1.79 and 1.13 sigma: pure noise. One
        # of them had its minimum in the middle, which no monotonic decay can
        # produce.
        #
        # 2.5 sigma is roughly a 1-in-80 false alarm under normality, which is
        # the right trade for a check that exits non-zero.
        sd = statistics.stdev(cdps)
        se_diff = sd * math.sqrt(2.0 / third) if sd > 0 else 0.0
        sigmas = abs(tail_mean - head_mean) / se_diff if se_diff > 0 else 0.0

        if sigmas > 2.5:
            direction = "rose" if drift_pct > 0 else "fell"
            print(f"\nWARNING: DPS {direction} {abs(drift_pct):.1f}% from the first "
                  f"third ({head_mean:.0f}) to the last ({tail_mean:.0f}) — "
                  f"{sigmas:.1f} sigma, beyond what this run's spread explains. "
                  f"State is leaking between fights; the mean is not trustworthy "
                  f"and more iterations will not fix it.")
            return 1

    # A run in which the actor never acted is a broken run, not a slow spec, and
    # averaging it in would report the breakage as a balance result.
    # Restricted to timeout fights for the same reason as the drift check: an
    # actor that died in 0.8s without landing a hit did not fail to fight, it
    # was killed before it could. Flagging that as a broken run buries the real
    # signal (which is the TTD) under a warning about the wrong thing.
    dead = [it["i"] for it in iters
            if it["damage_events_from_actor"] == 0
            and it.get("outcome", "timeout") == "timeout"]
    if dead:
        print(f"\nWARNING: iterations {dead} recorded zero damage events from the "
              f"actor -- the bot did not fight. Do not treat the mean as a "
              f"measurement; check {log}.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
