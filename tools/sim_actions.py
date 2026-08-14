#!/usr/bin/env python3
"""What the bot AI tried to do, and what happened to each attempt.

    python tools/sim_actions.py --char Aelelda --spec "ret pve" --gear paladin_ret
    python tools/sim_actions.py --log sims/runs/paladin_ret.log     # re-read a log

The damage table in a sim result says which abilities *landed*. It cannot say
why the others did not, and that is usually the interesting half: an ability
missing from the table might be on cooldown, out of mana, refused by the
engine, or never even considered.

mod-playerbots already logs the answer. Its engine emits one line per action it
evaluates each tick:

    <Bot> A:crusader strike - OK          it ran
    <Bot> A:crusader strike - IMPOSSIBLE  isPossible() said no (cooldown, mana,
                                          range, missing spell)
    <Bot> A:crusader strike - USELESS     isUseful() said no (already applied,
                                          wrong target, better option)
    <Bot> A:crusader strike - PREREQ      a prerequisite action ran instead
    <Bot> A:crusader strike - FAILED      it ran and the cast was rejected

plus `T:<trigger>` for every trigger that fired, and `Can cast spell failed`
lines naming a spell id and a reason. Those lines are `LOG_DEBUG("playerbots")`
and are gated behind `logInGroupOnly`, so they only appear when both are
switched on -- which this script does.

Reading the ratio is the whole skill. A rotation that is *running* shows its
signature ability mostly OK with the occasional IMPOSSIBLE while it is on
cooldown. A rotation that has *broken down* shows one of two shapes:

  - the ability is evaluated constantly and is always IMPOSSIBLE or USELESS,
    which means a condition the bot checks is never satisfied; or
  - the ability never appears at all, which means no trigger ever pushed it and
    the problem is in the strategy rather than in the spell.
"""

from __future__ import annotations

import argparse
import collections
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

ACTION_RE = re.compile(r"A:(?P<action>[^-]+?) - (?P<outcome>OK|FAILED|IMPOSSIBLE|USELESS|PREREQ|UNKNOWN)")
TRIGGER_RE = re.compile(r"\bT:(?P<trigger>[\w \-']+)")
CANCAST_RE = re.compile(r"Can cast spell failed\. (?P<why>[^-]+)- .*spellid: (?P<spell>\d+)")

OUTCOMES = ["OK", "PREREQ", "FAILED", "IMPOSSIBLE", "USELESS", "UNKNOWN"]


def analyse(text: str) -> None:
    actions = collections.defaultdict(collections.Counter)
    triggers = collections.Counter()
    cancast = collections.Counter()

    for line in text.splitlines():
        if m := ACTION_RE.search(line):
            actions[m.group("action").strip()][m.group("outcome")] += 1
        if m := TRIGGER_RE.search(line):
            triggers[m.group("trigger").strip()] += 1
        if m := CANCAST_RE.search(line):
            cancast[(m.group("spell"), m.group("why").strip())] += 1

    if not actions:
        print("no engine action lines in this log.\n"
              "The bot log is LOG_DEBUG on the 'playerbots' logger and is also gated by\n"
              "AiPlayerbot.LogInGroupOnly, so both have to be off/verbose. Run this script\n"
              "without --log and it sets them for you.")
        return

    print(f"{'action':<34}{'OK':>7}{'PREREQ':>8}{'FAILED':>8}{'IMPOSS':>8}"
          f"{'USELESS':>9}{'total':>8}")
    print("-" * 82)

    rows = sorted(actions.items(), key=lambda kv: -sum(kv[1].values()))
    for name, counts in rows:
        total = sum(counts.values())
        print(f"{name[:33]:<34}{counts['OK']:>7}{counts['PREREQ']:>8}"
              f"{counts['FAILED']:>8}{counts['IMPOSSIBLE']:>8}"
              f"{counts['USELESS']:>9}{total:>8}")

    # The two shapes worth naming out loud, so the table does not have to be
    # read carefully to spot them.
    print()
    stuck = [(n, c) for n, c in rows
             if sum(c.values()) >= 20 and c["OK"] == 0]
    if stuck:
        print("never once ran, though the engine kept evaluating them")
        for name, counts in stuck:
            worst = max(("IMPOSSIBLE", "USELESS"), key=lambda o: counts[o])
            print(f"  {name:<32} {sum(counts.values()):>5} attempts, all "
                  f"{worst.lower()}")

    if cancast:
        print()
        print("cast refusals by reason")
        for (spell, why), n in cancast.most_common(15):
            print(f"  {n:>5}x  spell {spell:<8} {why}")

    if triggers:
        print()
        print("triggers that fired")
        for name, n in triggers.most_common(20):
            print(f"  {n:>6}x  {name}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--log", type=Path, help="analyse an existing log instead of running")
    p.add_argument("--char")
    p.add_argument("--spec", default="")
    p.add_argument("--gear", default="")
    p.add_argument("--seconds", type=int, default=30,
                   help="short by default: these logs are one block per tick and "
                        "a 120s fight produces hundreds of thousands of lines")
    p.add_argument("--range", type=float, default=0.0)
    # Half of Alonecraft's redesigns are driven by damage *taken* -- Ember
    # Scars, Convective Currents' Ice Lance heal, Fiery Payback. Against the
    # default dummy, which hits for 0.01x, their triggers can never fire and
    # this tool reports a working rotation as a dead one. Point it at the
    # sparring dummy (2000110) to diagnose those.
    p.add_argument("--target", type=int, default=None,
                   help="creature entry to fight; 2000110 is the sparring "
                        "dummy, which hits back")
    p.add_argument("--level", type=int, default=80)
    args = p.parse_args()

    if args.log:
        analyse(args.log.read_text(errors="replace"))
        return 0

    if not args.char:
        p.error("--char is required unless --log is given")

    out_dir = REPO / "sims" / "runs" / "actions"
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = f"{args.char}-{args.spec.replace(' ', '_') or 'asis'}"
    if args.target:
        tag += f"-t{args.target}"

    env = dict(os.environ)
    # Both are needed. The logger has to be at DEBUG (5) for LOG_DEBUG to
    # survive Log::ShouldLog, and LogInGroupOnly has to be off or Engine::
    # LogAction returns before it writes anything -- the sim actor has no group
    # and no real player master.
    env["AC_LOGGER_PLAYERBOTS"] = "5,Console"
    env["AC_APPENDER_CONSOLE"] = "1,5,7"
    env["AC_AI_PLAYERBOT_LOG_IN_GROUP_ONLY"] = "0"

    cmd = [sys.executable, str(REPO / "tools" / "sim.py"),
           "--char", args.char, "--level", str(args.level),
           "--seconds", str(args.seconds), "--iterations", "1",
           "--out-dir", str(out_dir), "--tag", tag]
    if args.spec:
        cmd += ["--spec", args.spec]
    if args.gear:
        cmd += ["--gear", args.gear]
    if args.range:
        cmd += ["--range", str(args.range)]
    if args.target:
        cmd += ["--target", str(args.target)]

    print(f"running {args.seconds}s with bot decision logging ...", flush=True)
    subprocess.run(cmd, env=env, capture_output=True, text=True)

    log = out_dir / f"{tag}.log"
    if not log.exists():
        print(f"no log at {log}", file=sys.stderr)
        return 2

    print(f"{log}  ({log.stat().st_size // 1024} KiB)\n")
    analyse(log.read_text(errors="replace"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
