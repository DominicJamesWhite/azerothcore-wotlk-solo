#!/usr/bin/env python3
"""Run every spec through the simulator in identical gear, and compare them.

    python tools/sim_matrix.py                        # all 31 specs, all passes
    python tools/sim_matrix.py --specs priest mage    # only those classes
    python tools/sim_matrix.py --specs dps            # only the damage specs
    python tools/sim_matrix.py --specs mage --passes burst   # the quick loop
    python tools/sim_matrix.py --specs mage --ab      # against the stock spec
    python tools/sim_matrix.py --report sims/runs/matrix-20260813-1200

Three passes, because one fight length answers one question
-----------------------------------------------------------
A single 120-second pass sits between the two regimes that matter and reports
neither. The shadow priest measured 1191 DPS at 60s and 716 at 300s, wanding
for 27.7% of its damage in the second: for a solo fork, burst decides trash and
sustain decides long fights, and quoting one alone ranks specs differently and
silently.

  burst    60s on the inert dummy. Cooldowns are up for most of it, so this
           flatters a 2-minute-cooldown spec. It is the right length for "does
           the opener work", not for "what is this spec worth".
  sustain  300s on the same dummy. The length at which the mana cliff shows.
  clear    300s cap against the SPARRING dummy, which fights back and can die.
           Solo-clear fraction, TTD and TMI only mean anything here; against the
           inert dummy nothing can win or lose and the fraction is always 0.

--ab runs every pass twice, the second time with the Alonecraft solo build and
rotation switched off, and reports the delta. That is the question a solo fork
actually has -- "did this help?" -- and it is the regression guard for every
spec added later. Deltas smaller than twice the pooled run-to-run deviation are
reported as unresolved rather than ranked; the sim is not deterministic, and a
1% difference over 3 iterations is noise wearing a number.

What this is for
----------------
Not "which spec is strongest". With one target dummy, no raid buffs, no
movement and a bot rotation, the absolute numbers are not raid DPS. What the
matrix is good at is the question that has no other cheap answer: *is each
spec's rotation actually running?* A spec whose damage comes 80% from one
button, or that spends a fifth of a two-minute fight wanding, or that never
casts its signature ability, is broken in a way no amount of number tuning
fixes -- and it will silently poison any tuning done on top of it.

So every column here exists to make that visible:

  burst       DPS over the short pass
  sust        DPS over the long one
  s/b         sustain as a share of burst. Below 60% the spec is running out of
              something, and the wand share in the sustain pass says what.
  clear       how often it killed the sparring dummy and lived. Pass/fail, and
              it saturates -- read `taken` alongside it, never alone
  taken       mean damage taken per clear fight, as a share of the health bar.
              This is the survivability number that actually discriminates
  TTD         median time to death, over the fights it lost only -- a survivor
              contributes "at least this long" and is censored, never averaged
  abil        how many distinct sources of damage the fight used
  top         the largest single one, and its share
  flags       machine-checkable symptoms, listed under the table

Gear is pinned per spec (see tools/sim_specs.py) so the comparison is between
rotations rather than between loot rolls, and the mean item level actually
equipped is reported per spec so that can be checked rather than assumed.

Runs are sequential: one worldserver at a time, because they would otherwise
contend for the same port and the same database.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim_specs import resolve, resolve_target, DUMMY_TARGET, CLEAR_TARGET  # noqa: E402

REPO = Path(__file__).resolve().parent.parent

# Damage that is not part of any rotation: what a character does when it has
# nothing else to do. Named by spell id so a renamed Alonecraft spell does not
# slip through -- 5019 Shoot (wands), 75 Auto Shot, 0 melee auto-attack.
FILLER_SPELLS = {0, 5019, 75}

# name -> (seconds, iterations, target). See the module docstring for why these
# three and not one.
PASSES = {
    "burst":   (60,  3, DUMMY_TARGET),
    "sustain": (300, 3, DUMMY_TARGET),
    # 600s, not 300. woa_2026_08_14_05.sql tripled the sparring dummy's health
    # so fights are long enough to characterise avoidance (17 swings gave a
    # 12-point standard error on a 40% rate). At 3x health the slowest spec
    # measured -- druid_bear at 2179 DPS -- needs ~500s, and at the old limit it
    # would have timed out and reported a censored fight as a survival.
    "clear":   (600, 3, CLEAR_TARGET),
}

# A delta must exceed this many pooled standard deviations to be called at all.
# Two is deliberately not three: the cost of missing a real regression here is
# higher than the cost of looking twice at a borderline one.
AB_SIGMA = 2.0


def pass_settings(pass_name, args):
    """(seconds, iterations, target) for a pass, honouring explicit overrides.

    An explicit --seconds/--iterations/--target applies to every pass, which is
    only sensible with a single --passes. It is kept because the one-off "run
    this spec for 600 seconds" case is common and predates the passes.
    """
    seconds, iterations, target = PASSES[pass_name]
    if args.seconds is not None:
        seconds = args.seconds
    if args.iterations is not None:
        iterations = args.iterations
    if args.target is not None:
        target = resolve_target(args.target)
    # --clear-target is deliberately narrower than --target: it swaps only the
    # pass that is about surviving, leaving burst and sustain on the inert dummy
    # where the damage numbers stay comparable with every other run. Pointing all
    # three at a boss would change what burst and sustain mean and silently
    # invalidate the comparison they exist for.
    if pass_name == "clear" and args.clear_target is not None:
        target = resolve_target(args.clear_target)
    return seconds, iterations, target


def tag_for(key, pass_name, stock):
    return f"{key}.{pass_name}.stock" if stock else f"{key}.{pass_name}"


def run_spec(spec, args, out_dir: Path, pass_name: str, stock: bool = False) -> dict:
    seconds, iterations, target = pass_settings(pass_name, args)
    tag = tag_for(spec["key"], pass_name, stock)
    cmd = [
        sys.executable, str(REPO / "tools" / "sim.py"),
        "--char", spec["actor"],
        "--spec", spec["premade"],
        "--level", str(args.level),
        "--gear", spec["key"],
        "--target", str(target),
        "--range", str(spec["range"]),
        "--seconds", str(seconds),
        "--iterations", str(iterations),
        "--out-dir", str(out_dir),
        "--tag", tag,
    ]
    if stock:
        cmd.append("--stock")
    if args.arena != "gm":
        cmd += ["--arena", args.arena]
    if args.autobalance:
        cmd.append("--autobalance")
    if args.seal_mana_pct is not None:
        cmd += ["--seal-mana-pct", str(args.seal_mana_pct)]

    started = time.time()
    proc = subprocess.run(cmd, capture_output=True, text=True)
    wall = time.time() - started

    path = out_dir / f"{tag}.json"
    if not path.exists():
        # Keep BOTH streams and the exit code. sim.py reports a bad spec name, a
        # refused database and a worldserver that died on startup on stderr, and
        # a failure here used to surface as the four words "no result file" with
        # every one of those explanations captured and then discarded.
        return {"key": spec["key"], "error": "no result file",
                "exit_code": proc.returncode,
                "stdout": proc.stdout[-4000:], "stderr": proc.stderr[-4000:],
                "wall_s": wall}

    result = json.loads(path.read_text())
    result["exit_code"] = proc.returncode
    result["wall_s"] = round(wall, 1)
    return result


def summarise_pass(result) -> dict:
    """The numbers from one pass of one spec.

    Missing is not zero. A pass whose result file never appeared reports
    present=False, and every consumer below has to say "missing" rather than
    print a 0 that reads identically to a rotation that did no damage.
    """
    sub = {"present": False, "error": result.get("error", "") if result else "absent"}
    if result is None or result.get("error"):
        return sub

    iters = result.get("iterations", [])
    dps = [it["dps"] for it in iters]
    abilities = result.get("abilities", [])
    total = result.get("damage", 0)

    sub["present"] = True
    sub["error"] = ""
    sub["dps"] = statistics.mean(dps) if dps else 0.0
    sub["dps_samples"] = dps
    sub["sd_pct"] = (100 * statistics.stdev(dps) / sub["dps"]
                     if len(dps) > 1 and sub["dps"] else 0.0)
    sub["ilvl"] = result.get("gear_ilvl", 0)
    sub["gear_failed"] = result.get("gear_failed", 0)
    sub["uncastable"] = result.get("uncastable_spells", 0)
    sub["attack_power"] = result.get("attack_power", 0)
    sub["spell_power"] = result.get("spell_power", 0)
    sub["n_abilities"] = len(abilities)
    sub["top"] = abilities[0]["name"] if abilities else "-"
    sub["top_share"] = abilities[0]["share"] if abilities else 0.0
    sub["filler_share"] = (sum(a["damage"] for a in abilities
                               if a["spell"] in FILLER_SPELLS and not a["pet"]) / total
                           if total else 0.0)
    sub["unattributed"] = result.get("unattributed_damage", 0)
    sub["tabs"] = result.get("talent_tabs", [])

    # Outcomes. Only the clear pass fights something that can win or lose, but
    # the arithmetic is the same wherever it is asked.
    outcomes = [it.get("outcome", "timeout") for it in iters]
    kills = [it for it, o in zip(iters, outcomes) if o == "target_died"]
    deaths = [it for it, o in zip(iters, outcomes) if o == "actor_died"]
    sub["n_iterations"] = len(iters)
    sub["kills"] = len(kills)
    sub["deaths"] = len(deaths)
    sub["clear_pct"] = (100.0 * len(kills) / len(iters)) if iters else 0.0
    sub["clear_margin"] = (statistics.mean(it["actor_hp_pct"] for it in kills)
                           if kills else None)
    # TTD stays censored: a survivor contributes "at least this long", and
    # averaging it in would report a spec that never dies as dying on the bell.
    sub["ttd_median"] = (sorted(it["duration_s"] for it in deaths)[len(deaths) // 2]
                         if deaths else None)

    # Damage taken per fight, as a share of the actor's health bar.
    #
    # This is the survivability number, and clear% is not. clear% is pass/fail
    # and it saturates: measured on the mage solo builds, fire cleared 3/3 both
    # with and without its Alonecraft build, so the column read "no difference"
    # while the same fights recorded 26% of a health bar taken against 52%. The
    # build halved incoming damage and the metric could not see it.
    #
    # A share of max health rather than a raw number, because the comparison is
    # across specs with different health pools. Means, not medians -- an
    # iteration that nearly killed the actor is the interesting one and should
    # pull the number.
    max_hp = result.get("actor_max_health", 0)
    taken = [it.get("damage_taken", 0) for it in iters]
    sub["taken_pct"] = (100.0 * statistics.mean(taken) / max_hp
                        if iters and max_hp else None)

    # How much was thrown, and how much of it the spec turned away.
    #
    # taken_pct alone cannot tell "nothing reached me" from "nothing was aimed
    # at me", and those want opposite responses: the first is a spec that
    # mitigates too well, the second is a fixture that cannot reach the spec.
    # Both read as a small number in every column that existed before this.
    #
    # warrior_prot is the case that forced it. It read ~0 damage taken and was
    # written off in two SQL headers as "never attacked"; the swing ledger shows
    # 24 swings in 48 seconds with 79% avoided outright and 96% of the gross
    # damage turned away. It was being hit exactly as often as anything else.
    swings = sum(m.get("swings", 0) for it in iters
                 if (m := it.get("mitigation")))
    if swings:
        avoided = sum(m.get(k, 0) for it in iters if (m := it.get("mitigation"))
                      for k in ("misses", "dodges", "parries", "deflects", "immune"))
        landed = sum(m.get("landed", 0) for it in iters if (m := it.get("mitigation")))
        stopped = sum(m.get(k, 0) for it in iters if (m := it.get("mitigation"))
                      for k in ("blocked", "absorbed", "resisted"))

        landing_swings = swings - avoided
        # Mean GROSS landing swing, used to price the avoided ones. Avoided
        # swings are out of this denominator deliberately -- including them
        # would divide by the quantity being estimated.
        mean_swing = (landed + stopped) / landing_swings if landing_swings else 0
        gross = landed + stopped + avoided * mean_swing

        sub["swings"] = swings / len(iters) if iters else 0
        sub["avoid_pct"] = 100.0 * avoided / swings
        # Share of estimated gross incoming that never reached the health bar,
        # by any mechanism. Partly estimated, because the avoided component is.
        sub["mitigated_pct"] = 100.0 * (1 - landed / gross) if gross else None
    else:
        sub["swings"] = 0
        sub["avoid_pct"] = None
        sub["mitigated_pct"] = None

    return sub


def flags_for(row) -> list:
    """Machine-checkable symptoms. Pure, so tools/test_sim_metrics.py can pin it.

    Each rule names the pass it reads, because the same rule asked of the wrong
    pass is misleading rather than merely useless: the wand check at 120s sat
    between the two regimes, which is the worst place to look for it.
    """
    flags = []
    passes = row.get("passes", {})
    burst = passes.get("burst", {})
    sustain = passes.get("sustain", {})
    clear = passes.get("clear", {})

    for name in row.get("passes_requested", []):
        if not passes.get(name, {}).get("present"):
            flags.append(f"{name} pass missing - no number, not a zero")

    if row.get("wrong_spec"):
        flags.append(f"WRONG SPEC: talents {'/'.join(str(t) for t in row.get('tabs', []))}, "
                     f"expected most in tab {row['tab']}")

    ref = burst if burst.get("present") else sustain
    if ref.get("present"):
        if ref["uncastable"]:
            flags.append(f"{ref['uncastable']} spells known but uncastable")
        if ref["gear_failed"]:
            flags.append(f"{ref['gear_failed']} gear slots empty")
        if not ref["dps"]:
            flags.append("no damage at all")
        if ref["n_abilities"] <= 3 and row["role"] != "healer":
            flags.append(f"only {ref['n_abilities']} damage source(s) - rotation not running")
        if ref["top_share"] > 0.60:
            flags.append(f"{100 * ref['top_share']:.0f}% of damage from one ability")

    # A melee spec is *supposed* to auto-attack; a caster is not. Asked of the
    # sustain pass, where running dry is what produces it.
    if sustain.get("present") and sustain["filler_share"] > 0.10 \
            and sustain["spell_power"] > sustain["attack_power"]:
        flags.append(f"{100 * sustain['filler_share']:.0f}% of sustain damage from "
                     f"wanding/auto-shot")

    ratio = row.get("sustain_ratio")
    if ratio is not None and ratio < 0.60:
        flags.append(f"runs out of resources: sustain is {100 * ratio:.0f}% of burst")

    # A stalemate is not a loss. Neither side dying means the fight is not
    # measuring solo viability at all, and the dummy's two dials are the fix.
    if clear.get("present") and clear["n_iterations"]:
        if not clear["kills"] and not clear["deaths"]:
            flags.append("clear pass never resolved - nothing died either way")
        elif not clear["kills"]:
            flags.append(f"never cleared ({clear['deaths']}/{clear['n_iterations']} deaths)")

    return flags


def summarise(spec, by_pass, passes_requested) -> dict:
    """One row: the numbers from every pass, plus the flags that say not to
    trust them."""
    row = dict(spec)
    row["passes_requested"] = list(passes_requested)
    row["passes"] = {name: summarise_pass(by_pass.get(name))
                     for name in passes_requested}

    present = [p for p in row["passes"].values() if p["present"]]
    row["error"] = "" if present else "no pass produced a result"
    if not present:
        row["flags"] = [row["error"]]
        return row

    burst = row["passes"].get("burst", {})
    sustain = row["passes"].get("sustain", {})
    clear = row["passes"].get("clear", {})

    # Headline numbers, defaulting to whatever pass did run so a --passes burst
    # run still reports something in every column it can fill.
    row["burst"] = burst.get("dps") if burst.get("present") else None
    row["sustain"] = sustain.get("dps") if sustain.get("present") else None
    row["sustain_ratio"] = (row["sustain"] / row["burst"]
                            if row["burst"] and row["sustain"] else None)
    row["clear_pct"] = clear.get("clear_pct") if clear.get("present") else None
    row["ttd_median"] = clear.get("ttd_median") if clear.get("present") else None
    row["taken_pct"] = clear.get("taken_pct") if clear.get("present") else None
    row["swings"] = clear.get("swings") if clear.get("present") else None
    row["avoid_pct"] = clear.get("avoid_pct") if clear.get("present") else None
    row["mitigated_pct"] = clear.get("mitigated_pct") if clear.get("present") else None

    ref = burst if burst.get("present") else present[0]
    row["dps"] = ref.get("dps", 0.0)          # kept: the sort key and the median
    row["sd_pct"] = ref.get("sd_pct", 0.0)
    row["ilvl"] = ref.get("ilvl", 0)
    row["attack_power"] = ref.get("attack_power", 0)
    row["spell_power"] = ref.get("spell_power", 0)
    row["n_abilities"] = ref.get("n_abilities", 0)
    row["top"] = ref.get("top", "-")
    row["top_share"] = ref.get("top_share", 0.0)
    row["filler_share"] = ref.get("filler_share", 0.0)

    # The spec that was measured, not the spec that was asked for. A tab that
    # does not match is not a slow rotation -- it is a different spec's rotation
    # wearing this one's gear, and its DPS means nothing at all.
    tabs = ref.get("tabs", [])
    row["tabs"] = tabs
    row["wrong_spec"] = bool(tabs) and max(range(len(tabs)), key=lambda i: tabs[i]) != spec["tab"]

    row["flags"] = flags_for(row)
    return row


def ab_delta(woa_sub, stock_sub):
    """(delta_pct, resolved, pooled_sd_pct) for one pass of one spec.

    resolved is False when the difference is inside the noise the sim produces
    between identical runs. Reporting an unresolved delta as a number is how a
    tool starts manufacturing answers.
    """
    if not (woa_sub.get("present") and stock_sub.get("present")):
        return None, False, None
    a, b = woa_sub.get("dps", 0.0), stock_sub.get("dps", 0.0)
    if not b:
        return None, False, None
    delta = 100.0 * (a - b) / b

    sds = [sub["sd_pct"] for sub in (woa_sub, stock_sub)
           if len(sub.get("dps_samples", [])) > 1]
    pooled = (sum(x * x for x in sds) / len(sds)) ** 0.5 if sds else None
    if pooled is None:
        return delta, False, None
    return delta, abs(delta) > AB_SIGMA * pooled, pooled


def _fmt(v, width, prec=0, suffix=""):
    """A missing number prints as '-', never as 0."""
    if v is None:
        return f"{'-':>{width}}"
    return f"{v:>{width}.{prec}f}{suffix}"


def report(rows, args) -> int:
    rows = sorted(rows, key=lambda r: (-(r.get("burst") or r.get("dps") or 0)))

    print()
    # swings/avoid/mitig sit next to taken because they are what make taken
    # readable: a low taken next to 0 swings is a spec nothing reached, and a
    # low taken next to many swings is a spec that turned them away. Those are
    # different findings and the column set used to conflate them.
    print(f"{'spec':<16}{'role':<8}{'ilvl':>5}"
          f"{'burst':>8}{'sust':>8}{'s/b':>6}{'clear':>7}{'taken':>7}"
          f"{'swings':>7}{'avoid':>7}{'mitig':>7}{'TTD':>7}"
          f"{'abil':>6}  top ability")
    print("-" * 132)

    for r in rows:
        if r.get("error"):
            print(f"{r['key']:<16}{r['role']:<8}  FAILED: {r['error']}")
            continue
        mark = "!" if r["flags"] else " "
        ratio = r.get("sustain_ratio")
        print(f"{r['key']:<16}{r['role']:<8}{r['ilvl']:>5}"
              f"{_fmt(r.get('burst'), 8)}{_fmt(r.get('sustain'), 8)}"
              f"{_fmt(ratio * 100 if ratio is not None else None, 5)}%"
              f"{_fmt(r.get('clear_pct'), 6)}%"
              f"{_fmt(r.get('taken_pct'), 6)}%"
              f"{_fmt(r.get('swings'), 7)}"
              f"{_fmt(r.get('avoid_pct'), 6)}%"
              f"{_fmt(r.get('mitigated_pct'), 6)}%"
              f"{_fmt(r.get('ttd_median'), 7, 1)}"
              f"{r['n_abilities']:>6}  {mark}"
              f"{r['top'][:26]} ({100 * r['top_share']:.0f}%)")

    flagged = [r for r in rows if r.get("flags")]
    if flagged:
        print()
        print("rotations that look broken")
        print("-" * 111)
        for r in flagged:
            print(f"  {r['key']:<16} {'; '.join(r['flags'])}")

    # Within a role, specs should land in the same neighbourhood. A DPS spec at
    # half the median of the other DPS specs is either badly tuned or not
    # running its rotation, and the two are told apart by the flags above.
    # A wrong-spec run poisons the median it would otherwise be compared against,
    # so it is excluded rather than merely flagged.
    #
    # Taken from the burst column, which is the one comparable with every
    # earlier single-length run.
    dps_rows = [r for r in rows if r.get("role") == "dps" and not r.get("error")
                and not r.get("wrong_spec") and r.get("burst")]
    if len(dps_rows) >= 3:
        median = statistics.median(r["burst"] for r in dps_rows)
        print()
        print(f"median damage spec: {median:.0f} DPS burst")
        for r in dps_rows:
            ratio = r["burst"] / median if median else 0
            if ratio < 0.6 or ratio > 1.6:
                print(f"  {r['key']:<16} {r['burst']:>7.0f}  "
                      f"{ratio:.2f}x the median")

    print()
    print(f"{len(rows)} spec(s); results in {args.out_dir}")
    # The footer states what was actually fought. It used to hardcode "the
    # sparring dummy", which quietly became a lie the moment --clear-target
    # existed: a table headed by a real boss, footnoted as a dummy.
    clear_target = resolve_target(args.clear_target or args.target, CLEAR_TARGET)
    if clear_target == CLEAR_TARGET:
        clear_note = ("clear is the sparring dummy, whose health and damage are "
                      "a dial, not a\n      measurement")
    else:
        clear_note = (f"clear is creature {clear_target}"
                      + (f", autobalanced to a party of one" if args.autobalance
                         else ", at its raid-tuned numbers"))

    print("NOTE: no raid buffs, no consumables beyond the bot's own, no movement.\n"
          f"      burst and sustain are one dummy that cannot fight back; {clear_note}.\n"
          f"      arena: {args.arena}.\n"
          "      These are rotation-health numbers, not raid DPS.")
    return 1 if flagged else 0


def report_ab(rows, stock_rows, args) -> int:
    """The paired table: did the Alonecraft solo build and rotation help?"""
    by_key = {r["key"]: r for r in stock_rows}

    print()
    print("A/B: Alonecraft solo spec vs upstream premade")
    print(f"{'spec':<16}{'pass':<9}{'woa':>9}{'stock':>9}{'delta':>9}{'+/-':>8}  verdict")
    print("-" * 88)

    unresolved = 0
    for r in sorted(rows, key=lambda r: r["key"]):
        ctrl = by_key.get(r["key"])
        if not ctrl:
            print(f"{r['key']:<16}  no control run")
            continue
        for name in r.get("passes_requested", []):
            woa = r["passes"].get(name, {})
            stk = ctrl["passes"].get(name, {})
            delta, resolved, pooled = ab_delta(woa, stk)
            if delta is None:
                print(f"{r['key']:<16}{name:<9}{'-':>9}{'-':>9}{'-':>9}{'-':>8}  "
                      f"missing a half")
                continue
            verdict = ("better" if delta > 0 else "worse") if resolved else \
                      "not resolved by these iterations"
            if not resolved:
                unresolved += 1
            print(f"{r['key']:<16}{name:<9}{woa['dps']:>9.0f}{stk['dps']:>9.0f}"
                  f"{delta:>8.1f}%{(pooled or 0):>7.1f}%  {verdict}")

        # Clear is pass/fail, not a mean, so it gets its own line -- and it is
        # reported next to damage taken, because on its own it saturates. Fire's
        # solo build cleared 3/3 either way while halving the damage it took;
        # quoting clear% alone would have called that "no difference".
        wc, sc = r["passes"].get("clear", {}), ctrl["passes"].get("clear", {})
        if wc.get("present") and sc.get("present"):
            print(f"{r['key']:<16}{'clear%':<9}{wc['clear_pct']:>8.0f}%"
                  f"{sc['clear_pct']:>8.0f}%{'':>9}{'':>8}  "
                  f"{wc['kills']}/{wc['n_iterations']} vs "
                  f"{sc['kills']}/{sc['n_iterations']} kills")

            wt, st = wc.get("taken_pct"), sc.get("taken_pct")
            if wt is not None and st is not None:
                # Lower is better here, so the delta is inverted relative to the
                # DPS rows above: a negative number means less damage taken.
                delta = (100.0 * (wt - st) / st) if st else None
                print(f"{r['key']:<16}{'taken%':<9}{wt:>8.0f}%{st:>8.0f}%"
                      f"{(f'{delta:>8.1f}%' if delta is not None else f'{chr(45):>9}')}"
                      f"{'':>8}  share of health bar, lower is better")

        # The A/B also checks the switch itself. Identical talent tabs on a spec
        # that has a WoaSoloSpecLink row means the config never reached the sim,
        # which is almost always a skipped sync_configs.py.
        if r.get("tabs") and r["tabs"] == ctrl.get("tabs"):
            print(f"{r['key']:<16}  WARNING: identical talent tabs in both halves -- "
                  f"either this spec has no WoaSoloSpecLink row, or the deployed "
                  f"config is stale (run tools/sync_configs.py --write)")

    print()
    print(f"'+/-' is the pooled run-to-run deviation of the two halves. A delta "
          f"under {AB_SIGMA:.0f}x that\nis reported as unresolved rather than "
          f"ranked -- the sim is not deterministic.")
    if unresolved:
        print(f"{unresolved} comparison(s) unresolved; re-run with more --iterations "
              f"to decide them.")
    return 0


def load_rows(out_dir: Path, specs, passes, stock=False):
    rows = []
    for spec in specs:
        by_pass = {}
        for name in passes:
            path = out_dir / f"{tag_for(spec['key'], name, stock)}.json"
            if path.exists():
                by_pass[name] = json.loads(path.read_text())
        if by_pass:
            rows.append(summarise(spec, by_pass, passes))
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--specs", nargs="*", default=[],
                   help="spec keys, class names or roles; all of them if omitted")
    p.add_argument("--passes", nargs="*", default=list(PASSES),
                   choices=list(PASSES),
                   help="which fight lengths to run; all three if omitted. "
                        "'--passes burst' is the quick inner loop.")
    p.add_argument("--ab", action="store_true",
                   help="run every pass a second time with the Alonecraft solo "
                        "build and rotation off, and report the delta")
    p.add_argument("--seconds", type=int, default=None,
                   help="override the pass length for every pass")
    p.add_argument("--iterations", type=int, default=None,
                   help="override the iteration count for every pass")
    p.add_argument("--level", type=int, default=80)
    p.add_argument("--target", default=None,
                   help="override the target for EVERY pass; an entry id or a "
                        "name (dummy, sparring, patchwerk, thaddius, ...)")
    p.add_argument("--clear-target", default=None,
                   help="override the target for the clear pass only, leaving "
                        "burst and sustain on the dummy. This is the one to use "
                        "for a real boss: --clear-target patchwerk")
    p.add_argument("--arena", default="gm",
                   help="where fights happen: 'gm' (continent, default) or "
                        "'instance' (empty raid map, required for --autobalance)")
    p.add_argument("--autobalance", action="store_true",
                   help="scale creatures to a party of one, as a solo player "
                        "meets them. Requires --arena instance.")
    p.add_argument("--seal-mana-pct", type=int, default=None,
                   help="override the holy paladin seal-swap threshold for every "
                        "run in this matrix; 0 restores permanent Seal of Wisdom")
    p.add_argument("--no-html", action="store_true",
                   help="skip the per-spec HTML reports (see tools/sim_report.py)")
    p.add_argument("--out-dir", type=Path, default=None)
    p.add_argument("--report", type=Path, default=None,
                   help="re-print the table from a finished run's directory, "
                        "without simulating anything")
    args = p.parse_args()

    specs = resolve(args.specs)

    if args.report:
        args.out_dir = args.report
        rows = load_rows(args.report, specs, args.passes)
        rc = report(rows, args)
        stock_rows = load_rows(args.report, specs, args.passes, stock=True)
        if stock_rows:
            report_ab(rows, stock_rows, args)
        return rc

    if args.out_dir is None:
        args.out_dir = REPO / "sims" / "runs" / f"matrix-{time.strftime('%Y%m%d-%H%M%S')}"
    args.out_dir = args.out_dir.resolve()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    halves = [False, True] if args.ab else [False]
    rows, stock_rows = [], []
    total = len(specs) * len(args.passes) * len(halves)
    done = 0

    for spec in specs:
        for stock in halves:
            by_pass = {}
            for name in args.passes:
                done += 1
                label = f"{spec['key']}{' (stock)' if stock else ''}"
                print(f"[{done}/{total}] {label:<24}{name:<9}", end="", flush=True)
                result = run_spec(spec, args, args.out_dir, name, stock)
                by_pass[name] = result
                if result.get("error"):
                    print(f"FAILED: {result['error']} "
                          f"(exit {result.get('exit_code')})")
                    # Printed immediately rather than saved for the summary: a
                    # matrix is long, and a failure whose cause is only visible
                    # 40 minutes later has usually been re-run blind by then.
                    for stream in ("stderr", "stdout"):
                        tail = (result.get(stream) or "").strip()
                        if tail:
                            last = tail.splitlines()[-6:]
                            print(f"    {stream}:")
                            for line in last:
                                print(f"      {line}")
                else:
                    iters = result.get("iterations", [])
                    dps = statistics.mean([it["dps"] for it in iters]) if iters else 0
                    print(f"{dps:>8.0f} DPS   ({result['wall_s']}s wall)")
            (stock_rows if stock else rows).append(
                summarise(spec, by_pass, args.passes))

    (args.out_dir / "matrix.json").write_text(
        json.dumps({"woa": rows, "stock": stock_rows}, indent=2, default=str) + "\n")
    rc = report(rows, args)
    if stock_rows:
        report_ab(rows, stock_rows, args)

    # The table above ranks; the HTML says why. Generated by default because a
    # report nobody remembers to ask for is a report nobody reads, and it costs
    # a couple of seconds against a run measured in hours.
    if not args.no_html:
        write_html_reports(args.out_dir)

    return rc


def write_html_reports(out_dir: Path):
    """Render a per-spec HTML report for everything just simulated."""
    try:
        import sim_report
    except ImportError as exc:                                 # pragma: no cover
        print(f"  (no HTML report: {exc})")
        return

    written = []
    for path in sorted(out_dir.glob("*.json")):
        if path.name == "matrix.json":
            continue
        try:
            data = sim_report.summarise(sim_report.load_result(path), path)
            icons, _missing = sim_report.inline_icons(
                sim_report.spell_ids_in(data))
            written.append(sim_report.render_report(
                data, icons,
                path.with_name(path.name[:-len(".json")] + ".report.html")))
        except Exception as exc:                               # pragma: no cover
            print(f"  (report failed for {path.name}: {exc})")

    if written:
        index = sim_report.build_index()
        print()
        print(f"  {len(written)} HTML report(s) written. Index: {index}")

    # The comparative page, which is the one a balance pass actually reads: a
    # per-spec report answers "what did this spec do", and 31 of them cannot
    # answer "who is out of line, and by which mechanism". Written even when the
    # per-spec reports failed, because it reads the result JSON directly and
    # does not depend on them.
    try:
        import matrix_report
        page = matrix_report.build_for(out_dir)
        if page:
            print(f"  matrix: {page}")
            print(f"  runs:   {matrix_report.build_runs_index()}")
    except Exception as exc:                                   # pragma: no cover
        print(f"  (matrix report failed: {exc})")


if __name__ == "__main__":
    sys.exit(main())
