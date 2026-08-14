#!/usr/bin/env python3
"""Pin the simulator's metric definitions.

    python tools/test_sim_metrics.py

TMI is the reason this file exists. It is a soft maximum over trailing windows
with three constants baked in -- window 6s, risk aversion f = 10, reference
fight 450s -- and getting any of them wrong produces a number that still looks
plausible. These cases pin values the definition fixes exactly:

    TMI = (T_ref / T_fight) * (1/f) * ln( mean( exp(f * D_i) ) ) * 10000

so if every trailing window takes exactly one full health bar (D_i = 1) over a
fight of exactly T_ref, the whole expression collapses to 1 * 1 * 10000.

This is not hypothetical rigour. The first implementation kept a hit that was
exactly `window` old inside the window, so every window held two hits and every
TMI came out doubled -- invisible against real data, obvious against an anchor.
"""

import importlib.util
import sys
from pathlib import Path

spec = importlib.util.spec_from_file_location("sim", Path(__file__).parent / "sim.py")
sim = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sim)

sys.path.insert(0, str(Path(__file__).parent))
import sim_matrix  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
import sim_matrix  # noqa: E402

HP = 1000


def check(name, got, expect, tol=None):
    tol = tol if tol is not None else max(5.0, abs(expect) * 0.002)
    ok = abs(got - expect) <= tol
    print(f"{'PASS' if ok else 'FAIL'}  {name:32} got {got:10.1f}  expect {expect}")
    return ok


def drift_sigmas(dps):
    """Mirror of the drift test in sim.py, so its threshold can be exercised.

    Kept as a copy rather than imported because sim.py's version is embedded in
    the reporting path; if the two ever disagree, that is worth knowing.
    """
    import math
    import statistics
    third = max(1, len(dps) // 3)
    head, tail = dps[:third], dps[-third:]
    sd = statistics.stdev(dps)
    se = sd * math.sqrt(2.0 / third) if sd > 0 else 0.0
    return abs(statistics.mean(tail) - statistics.mean(head)) / se if se else 0.0


def _pass(dps, **kw):
    """A minimal present pass, with sane defaults for every rule's inputs."""
    sub = {
        "present": True, "error": "", "dps": dps, "dps_samples": [dps],
        "sd_pct": 0.0, "ilvl": 200, "gear_failed": 0, "uncastable": 0,
        "attack_power": 100, "spell_power": 2000, "n_abilities": 8,
        "top": "Fireball", "top_share": 0.3, "filler_share": 0.0,
        "unattributed": 0, "tabs": [10, 55, 6], "n_iterations": 3,
        "kills": 0, "deaths": 0, "clear_pct": 0.0, "clear_margin": None,
        "ttd_median": None,
    }
    sub.update(kw)
    return sub


def _row(passes, **kw):
    row = {"key": "mage_fire", "role": "dps", "tab": 1,
           "passes_requested": list(passes), "passes": passes,
           "tabs": [10, 55, 6], "wrong_spec": False}
    row.update(kw)
    return row


def check_flags() -> bool:
    """The flag rules, which is where silent wrongness will live next.

    Two of these encode decisions rather than arithmetic, and both are the
    reason this section exists: a missing pass must never read as a zero, and
    the caster-wand rule must be asked of the pass where running dry shows.
    """
    ok = True

    def case(name, row, want_substr, want_present=True):
        nonlocal ok
        flags = sim_matrix.flags_for(row)
        hit = any(want_substr in f for f in flags)
        good = hit == want_present
        print(f"{'PASS' if good else 'FAIL'}  {name:44} "
              f"{'flagged' if hit else 'clean'}  {flags if not good else ''}")
        ok &= good

    # A missing pass is a missing measurement. Reporting it as 0 DPS would read
    # identically to a rotation that never fired, which is a different fault.
    case("missing pass says missing",
         _row({"burst": _pass(5000), "sustain": {"present": False, "error": "absent"}}),
         "sustain pass missing")
    case("missing pass is not 'no damage at all'",
         _row({"burst": _pass(5000), "sustain": {"present": False, "error": "absent"}}),
         "no damage at all", want_present=False)

    # The resource cliff, either side of the line.
    case("sustain at 50% of burst is flagged",
         _row({"burst": _pass(5000), "sustain": _pass(2500)}, sustain_ratio=0.5),
         "runs out of resources")
    case("sustain at 70% of burst is not",
         _row({"burst": _pass(5000), "sustain": _pass(3500)}, sustain_ratio=0.7),
         "runs out of resources", want_present=False)

    # The wand rule reads the sustain pass only. A caster wanding for 20% of a
    # 60-second opener is a different claim from one wanding at 300 seconds,
    # and it is the second that means "out of mana".
    case("wanding in sustain is flagged",
         _row({"burst": _pass(5000), "sustain": _pass(3000, filler_share=0.25)}),
         "sustain damage from wanding"),
    case("wanding in burst alone is not",
         _row({"burst": _pass(5000, filler_share=0.25), "sustain": _pass(3000)}),
         "wanding", want_present=False)

    # A stalemate and a loss are different results and want different fixes.
    case("nothing died either way",
         _row({"clear": _pass(4000, kills=0, deaths=0)}),
         "never resolved")
    case("died every time",
         _row({"clear": _pass(4000, kills=0, deaths=3)}),
         "never cleared")
    case("cleared is clean",
         _row({"clear": _pass(4000, kills=3, deaths=0, clear_pct=100.0)}),
         "never", want_present=False)

    return ok


def check_ab() -> bool:
    """The A/B significance gate.

    Its whole job is to refuse to answer. The sim's own history is five separate
    bugs that each produced confident, plausible, wrong numbers, and a delta
    smaller than the noise is the cheapest way to produce a sixth.
    """
    ok = True

    def case(name, woa, stock, want_resolved):
        nonlocal ok
        delta, resolved, pooled = sim_matrix.ab_delta(woa, stock)
        good = resolved == want_resolved
        print(f"{'PASS' if good else 'FAIL'}  {name:44} "
              f"delta {delta if delta is None else round(delta, 1)}%  "
              f"+/-{pooled if pooled is None else round(pooled, 1)}%  "
              f"resolved={resolved}")
        ok &= good

    noisy = dict(sd_pct=2.0, dps_samples=[1, 2, 3])
    case("1.5% delta against 2% noise: unresolved",
         _pass(1015, **noisy), _pass(1000, **noisy), False)
    case("40% delta against 2% noise: resolved",
         _pass(1400, **noisy), _pass(1000, **noisy), True)
    case("a missing half is never resolved",
         _pass(1400, **noisy), {"present": False}, False)
    case("a single iteration has no deviation, so nothing is resolved",
         _pass(1400, dps_samples=[1400]), _pass(1000, dps_samples=[1000]), False)

    return ok


def main():
    tmi = sim.theck_meloree_index
    ok = True

    # Two real runs that the original fixed-5% threshold flagged as drifting.
    # Both are noise -- the second has its minimum in the middle, which no
    # monotonic decay produces -- so neither may exceed the 2.5 sigma bar.
    for name, series in [
        ("noise, declining-looking", [1266.5, 1305.8, 1272.2, 1286.1, 1232.8, 1185.8]),
        ("noise, dip in the middle", [1340.3, 1317.2, 1191.2, 1172.9, 1269.5, 1235.9]),
    ]:
        s = drift_sigmas(series)
        good = s <= 2.5
        print(f"{'PASS' if good else 'FAIL'}  {name:32} {s:5.2f} sigma  (want <= 2.5)")
        ok &= good

    # The same genuine collapse over 6 iterations reaches only 1.73 sigma, which
    # is why sim.py refuses to run this test below 12 iterations rather than
    # picking a threshold that would catch it at the cost of constant false
    # alarms. Pinned so nobody "fixes" the threshold downwards later.
    s = drift_sigmas([824.3, 772.9, 686.8, 684.6, 706.3, 690.0])
    good = s < 2.5
    print(f"{'PASS' if good else 'FAIL'}  {'real drift, n=6: NOT resolvable':32} "
          f"{s:5.2f} sigma  (documented limitation)")
    ok &= good

    # With 12 iterations the same effect is resolvable, which is the threshold
    # sim.py uses. A linear decline of the observed magnitude with the observed
    # noise on top.
    drifting = [800 - 12 * i + (20 if i % 2 else -20) for i in range(12)]
    s = drift_sigmas(drifting)
    good = s > 2.5
    print(f"{'PASS' if good else 'FAIL'}  {'real drift, n=12: caught':32} {s:5.2f} sigma  (want > 2.5)")
    ok &= good

    # ...and a flat run of the same length and noise must not trip it.
    flat = [800 + (20 if i % 2 else -20) for i in range(12)]
    s = drift_sigmas(flat)
    good = s <= 2.5
    print(f"{'PASS' if good else 'FAIL'}  {'flat run, n=12: no alarm':32} {s:5.2f} sigma  (want <= 2.5)")
    ok &= good

    # One full health bar per trailing window, over exactly T_ref.
    inc = [(t * 1000, HP) for t in range(0, 450, 6)]
    ok &= check("full bar per window, 450s", tmi(inc, HP, 450.0), 10000)

    # Halving the damage halves the exponent, so it halves the index.
    inc = [(t * 1000, HP // 2) for t in range(0, 450, 6)]
    ok &= check("half bar per window, 450s", tmi(inc, HP, 450.0), 5000)

    # T_ref / T_fight normalisation: the same windows in half the time double it.
    inc = [(t * 1000, HP) for t in range(0, 225, 6)]
    ok &= check("full bar per window, 225s", tmi(inc, HP, 225.0), 20000)

    ok &= check("no damage taken", tmi([], HP, 450.0), 0)
    ok &= check("zero max health is not a crash", tmi([(0, 100)], 0, 450.0), 0)

    # log-sum-exp: a naive mean(exp(f*D)) overflows well before this and returns
    # inf, and an infinite survivability metric is worse than none.
    v = tmi([(0, HP * 100)], HP, 450.0)
    finite = v == v and v not in (float("inf"), float("-inf"))
    print(f"{'PASS' if finite else 'FAIL'}  {'100x health stays finite':32} got {v:10.1f}")
    ok &= finite

    ok &= check_flags()
    ok &= check_ab()

    print("ALL OK" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
