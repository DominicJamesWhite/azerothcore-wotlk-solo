#!/usr/bin/env python3
"""
Alonecraft Log Noise Auditor

Buckets worldserver log lines by *signature* -- the line with its timestamps,
ids, guids, names and quoted strings normalised away -- so that repeated noise
collapses into one row with a count.

That collapse is the whole point. A run that looks like "1192 errors" is
usually one problem happening 1192 times, and until you can see that you cannot
tell a new regression from the existing backlog.

Two modes:

    report   (default)  Human-readable breakdown of what a run logged.
    --check             Compare against tools/log_budget.json and report
                        regressions. Exits non-zero only with --strict.

Usage:
    python tools/audit_logs.py                      # report on the live logs
    python tools/audit_logs.py --top 40
    python tools/audit_logs.py --archive            # include logs\\archive\\*
    python tools/audit_logs.py --baseline           # rewrite log_budget.json
    python tools/audit_logs.py --check              # regressions vs the budget
    python tools/audit_logs.py --check --strict     # ...and fail the build
    python tools/audit_logs.py --json-history PATH  # append one summary line
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BUDGET_PATH = os.path.join(REPO_ROOT, "tools", "log_budget.json")

DEFAULT_SERVER_DIR = r"C:\Build\bin\RelWithDebInfo"

# Files we know how to read. The bridge log only exists once the mod-llm-chatter
# bridge is given a --log-file (see build_and_run.bat).
LOG_FILENAMES = [
    "Server.log",
    "Errors.log",
    "Playerbots.log",
    os.path.join("logs", "llm_chatter_bridge.log"),
]

# Appender flags 7 = timestamp | loglevel | logfiltertype, so lines look like:
#   2026-08-05 14:03:11 ERROR [sql.sql] Duplicate entry '1685-2662' for key ...
LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"(?P<level>FATAL|ERROR|WARN|INFO|DEBUG|TRACE)\s+"
    r"\[(?P<category>[^\]]*)\]\s?"
    r"(?P<message>.*)$"
)

# The Python bridge uses its own logging.basicConfig format.
BRIDGE_LINE_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+"
    r"\[(?P<level>CRITICAL|ERROR|WARNING|INFO|DEBUG)\]\s+"
    r"(?P<message>.*)$"
)

# Some messages carry their own level marker in the text regardless of appender
# flags -- notably the database layer's " [ERROR]: [1062] Duplicate entry ...".
INLINE_LEVEL_RE = re.compile(
    r"^\s*\[(?P<level>FATAL|ERROR|WARN|WARNING|INFO|DEBUG|TRACE)\]:?\s*"
)

LEVEL_ALIASES = {"WARNING": "WARN", "CRITICAL": "FATAL"}
LEVEL_ORDER = ["FATAL", "ERROR", "WARN", "INFO", "DEBUG", "TRACE"]

# Problems worth naming explicitly, so they stay visible even when their count is
# small enough to fall outside the top-N. Each is something we have decided we
# care about; see log_budget.json for the accepted count of each.
NAMED_CHECKS = [
    ("config-missing-property", re.compile(r"Config: Missing property")),
    ("config-duplicate-key", re.compile(r"Config::LoadFile: Duplicate key name")),
    ("sql-duplicate-entry", re.compile(r"Duplicate entry .* for key")),
    ("sql-transaction-aborted", re.compile(r"Transaction aborted")),
    ("creature-invalid-unit-class", re.compile(r"invalid unit_class")),
    ("playerbot-no-ai", re.compile(r"has no bot AI")),
    ("teleport-invalid-map", re.compile(r"TeleportTo: invalid map")),
    ("leftover-debug-gossip", re.compile(r"GOSSIP_SELECT:")),
    ("leftover-debug-razorscale", re.compile(r"Razorscale:")),
]

# Substitutions are ordered: the specific must run before the general, or the
# bare-number rule eats the insides of guids and timestamps first.
NORMALISERS = [
    (re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}"), "<TS>"),
    (re.compile(r"0x[0-9A-Fa-f]+"), "<HEX>"),
    (re.compile(r"GUID Full: [^,)]+"), "GUID Full: <GUID>"),
    (re.compile(r"'[^']*'"), "'<S>'"),
    (re.compile(r'"[^"]*"'), '"<S>"'),
    (re.compile(r"\b\d+\.\d+\b"), "<F>"),
    (re.compile(r"\b\d+\b"), "<N>"),
    (re.compile(r"\s+"), " "),
]


def normalise(message):
    """Collapse a log message down to its signature template."""
    sig = message
    for pattern, replacement in NORMALISERS:
        sig = pattern.sub(replacement, sig)
    return sig.strip()


def parse_line(raw):
    """Return (timestamp, level, category, message, prefixed).

    Never returns None. A line without a recognised prefix is still real log
    content -- archived logs predate the appender flags change, and Errors.log
    entries from the DB layer carry their own ad-hoc " [ERROR]: " marker. If we
    dropped those we would report zero occurrences of problems the file plainly
    contains, which is worse than reporting them without a category.
    """
    m = LINE_RE.match(raw)
    if m:
        return (
            m.group("ts"),
            m.group("level"),
            m.group("category") or "?",
            m.group("message"),
            True,
        )

    m = BRIDGE_LINE_RE.match(raw)
    if m:
        level = LEVEL_ALIASES.get(m.group("level"), m.group("level"))
        return (m.group("ts"), level, "bridge", m.group("message"), True)

    # Unprefixed. Salvage a level from an inline marker if there is one.
    message = raw.strip()
    level = "INFO"
    inline = INLINE_LEVEL_RE.match(message)
    if inline:
        level = LEVEL_ALIASES.get(inline.group("level"), inline.group("level"))
        message = message[inline.end():].strip()

    return (None, level, "unprefixed", message, False)


class Bucket:
    __slots__ = (
        "signature", "category", "count", "level", "sample",
        "first_ts", "last_ts", "startup_only",
    )

    def __init__(self, signature, level, category, sample, ts):
        self.signature = signature
        self.category = category
        self.count = 0
        self.level = level
        self.sample = sample
        self.first_ts = ts
        self.last_ts = ts
        # Assume ongoing until split_startup proves otherwise; a log with no
        # usable timestamps should not silently look like it was all startup.
        self.startup_only = False

    def add(self, level, ts):
        self.count += 1
        # Keep the most severe level seen for this signature.
        if LEVEL_ORDER.index(level) < LEVEL_ORDER.index(self.level):
            self.level = level
        if ts:
            if not self.first_ts or ts < self.first_ts:
                self.first_ts = ts
            if not self.last_ts or ts > self.last_ts:
                self.last_ts = ts


def collect_files(server_dir, include_archive, explicit):
    if explicit:
        return [p for p in explicit if os.path.isfile(p)]

    paths = []
    for name in LOG_FILENAMES:
        p = os.path.join(server_dir, name)
        if os.path.isfile(p):
            paths.append(p)

    if include_archive:
        archive = os.path.join(server_dir, "logs", "archive")
        if os.path.isdir(archive):
            paths.extend(
                os.path.join(archive, f)
                for f in sorted(os.listdir(archive))
                if f.endswith(".log")
            )

    return paths


def scan(paths, startup_seconds):
    """Read every file and return buckets plus per-run statistics."""
    buckets = {}
    by_level = defaultdict(int)
    by_category = defaultdict(int)
    named = defaultdict(int)
    unparsed = 0
    total = 0
    timestamps = []

    for path in paths:
        # Server.log carries embedded NULs from the "Loading Waypoints" progress
        # line, so decode leniently rather than dying on one bad byte.
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for raw in fh:
                raw = raw.replace("\x00", "").rstrip("\r\n")
                if not raw.strip():
                    continue

                total += 1
                ts, level, category, message, prefixed = parse_line(raw)
                if not prefixed:
                    unparsed += 1

                by_level[level] += 1
                by_category[category] += 1
                if ts:
                    timestamps.append(ts)

                for name, pattern in NAMED_CHECKS:
                    if pattern.search(message):
                        named[name] += 1

                sig = normalise(message)
                key = (category, sig)
                bucket = buckets.get(key)
                if bucket is None:
                    bucket = Bucket(sig, level, category, message, ts)
                    buckets[key] = bucket
                bucket.add(level, ts)

    stats = {
        "total_lines": total,
        "unparsed_lines": unparsed,
        "by_level": dict(by_level),
        "by_category": dict(by_category),
        "named": dict(named),
        "first_ts": min(timestamps) if timestamps else None,
        "last_ts": max(timestamps) if timestamps else None,
    }
    split_startup(buckets, stats, startup_seconds)
    return buckets, stats


def _parse_ts(ts):
    try:
        return datetime.strptime(ts, "%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


def split_startup(buckets, stats, startup_seconds):
    """Classify each bucket as startup-only or ongoing.

    A one-time burst during boot and a message that repeats forever need
    completely different responses, and a raw count cannot tell them apart.
    """
    start = _parse_ts(stats["first_ts"])
    end = _parse_ts(stats["last_ts"])
    if not start or not end:
        stats["run_seconds"] = 0
        stats["steady_seconds"] = 0
        return

    stats["run_seconds"] = int((end - start).total_seconds())
    stats["steady_seconds"] = max(0, stats["run_seconds"] - startup_seconds)

    for bucket in buckets.values():
        last = _parse_ts(bucket.last_ts)
        bucket.startup_only = (
            last is not None and (last - start).total_seconds() <= startup_seconds
        )


def rate_per_min(bucket, stats):
    """Occurrences per minute during steady state, or None for startup-only."""
    if bucket.startup_only:
        return None
    steady = stats.get("steady_seconds") or 0
    if steady <= 0:
        return None
    return bucket.count / (steady / 60.0)


def load_budget():
    if not os.path.isfile(BUDGET_PATH):
        return None
    with open(BUDGET_PATH, "r", encoding="utf-8") as fh:
        return json.load(fh)


def print_report(buckets, stats, top, paths):
    print("=" * 72)
    print("  Alonecraft Log Audit")
    print("=" * 72)
    for p in paths:
        try:
            size = os.path.getsize(p)
        except OSError:
            size = 0
        print(f"  {p}  ({size:,} bytes)")
    print()

    print("-" * 72)
    print("  Totals")
    print("-" * 72)
    print(f"  Lines read:        {stats['total_lines']:,}")
    print(f"  No prefix:         {stats['unparsed_lines']:,}", end="")
    if stats["unparsed_lines"] and stats["total_lines"]:
        pct = 100.0 * stats["unparsed_lines"] / stats["total_lines"]
        print(f"  ({pct:.1f}%)", end="")
        if pct > 20:
            print("  <- still bucketed, but with no level/category/time.", end="")
    print()
    if stats["unparsed_lines"] and stats["total_lines"]:
        if 100.0 * stats["unparsed_lines"] / stats["total_lines"] > 20:
            print("                     Set the file appender flags to 7 in "
                  "worldserver.conf")
            print("                     (or this is an archived log from before "
                  "that change).")
    print(f"  Distinct signatures: {len(buckets):,}")
    if stats.get("run_seconds"):
        print(
            f"  Run span:          {stats['run_seconds']}s "
            f"({stats['first_ts']} -> {stats['last_ts']})"
        )
    print()

    print("  By level:    ", end="")
    parts = [
        f"{lvl}={stats['by_level'][lvl]:,}"
        for lvl in LEVEL_ORDER
        if stats["by_level"].get(lvl)
    ]
    print("  ".join(parts) if parts else "(none)")

    top_cats = sorted(stats["by_category"].items(), key=lambda kv: -kv[1])[:8]
    print("  By category: ", end="")
    print("  ".join(f"{c}={n:,}" for c, n in top_cats) if top_cats else "(none)")
    print()

    print("-" * 72)
    print(f"  Top {top} signatures by count")
    print("-" * 72)
    ranked = sorted(buckets.values(), key=lambda b: -b.count)[:top]
    if not ranked:
        print("  (nothing parsed -- check the appender flags in worldserver.conf)")
    for b in ranked:
        rate = rate_per_min(b, stats)
        when = "startup" if b.startup_only else "ongoing"
        rate_str = f", {rate:.1f}/min" if rate else ""
        print(f"  {b.count:>6}x  {b.level:<5} [{b.category}]  ({when}{rate_str})")
        print(f"          {b.sample[:150]}")
    print()

    print("-" * 72)
    print("  Named checks")
    print("-" * 72)
    for name, _ in NAMED_CHECKS:
        count = stats["named"].get(name, 0)
        flag = "   " if count == 0 else " ! "
        print(f" {flag}{name:<32} {count:,}")
    print()


def signature_key(bucket):
    return f"{bucket.category}|{bucket.signature}"


def do_baseline(buckets, stats, min_count):
    """Write a fresh budget file from the current run."""
    entries = {}
    for b in sorted(buckets.values(), key=lambda b: -b.count):
        if b.count < min_count:
            continue
        entries[signature_key(b)] = {
            "max": b.count,
            "level": b.level,
            "note": "baselined - not yet triaged",
            "sample": b.sample[:200],
        }

    budget = {
        "_comment": (
            "Accepted log noise. Every entry is a deliberate decision with a "
            "reason: either it is expected, or it is known debt with a plan. "
            "audit_logs.py --check reports anything above its max, and any new "
            "signature above new_signature_threshold. Ratchet these down as "
            "each fix lands -- that is what stops the noise re-accreting."
        ),
        "new_signature_threshold": 25,
        "named_checks": {
            name: stats["named"].get(name, 0) for name, _ in NAMED_CHECKS
        },
        "signatures": entries,
    }

    with open(BUDGET_PATH, "w", encoding="utf-8") as fh:
        json.dump(budget, fh, indent=2)
        fh.write("\n")

    print(f"  Wrote {len(entries)} signatures to {BUDGET_PATH}")
    print("  Now go through it and replace each 'not yet triaged' note.")


def do_check(buckets, stats, budget):
    """Compare the run against the budget. Returns the number of regressions."""
    print("-" * 72)
    print("  Budget check")
    print("-" * 72)

    threshold = budget.get("new_signature_threshold", 25)
    accepted = budget.get("signatures", {})
    named_budget = budget.get("named_checks", {})
    regressions = 0

    for b in sorted(buckets.values(), key=lambda b: -b.count):
        key = signature_key(b)
        if key in accepted:
            allowed = accepted[key].get("max", 0)
            if b.count > allowed:
                regressions += 1
                print(f"  OVER BUDGET  {b.count} > {allowed}  [{b.category}]")
                print(f"               {b.sample[:140]}")
        elif b.count >= threshold:
            regressions += 1
            print(f"  NEW          {b.count}x (threshold {threshold})  [{b.category}]")
            print(f"               {b.sample[:140]}")

    for name, _ in NAMED_CHECKS:
        count = stats["named"].get(name, 0)
        allowed = named_budget.get(name)
        if allowed is not None and count > allowed:
            regressions += 1
            print(f"  OVER BUDGET  named check '{name}': {count} > {allowed}")

    if regressions == 0:
        print("  No regressions against the budget.")
    else:
        print()
        print(f"  {regressions} regression(s). Fix them, or if the new volume is")
        print(f"  genuinely acceptable, raise the entry in {BUDGET_PATH} with a note.")
    print()
    return regressions


def append_history(path, stats, buckets):
    """Append one summary line for trend data. Never fails the run."""
    record = {
        "at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_lines": stats["total_lines"],
        "distinct_signatures": len(buckets),
        "by_level": stats["by_level"],
        "named": stats["named"],
    }
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")
    except OSError as e:
        print(f"  (history not written: {e})")


def main():
    parser = argparse.ArgumentParser(
        description="Bucket worldserver log noise by signature."
    )
    parser.add_argument(
        "--server-dir", default=DEFAULT_SERVER_DIR,
        help=f"Server directory holding the logs (default: {DEFAULT_SERVER_DIR})",
    )
    parser.add_argument(
        "files", nargs="*",
        help="Explicit log files to read instead of the server directory.",
    )
    parser.add_argument("--top", type=int, default=25, help="Signatures to list (default 25)")
    parser.add_argument(
        "--archive", action="store_true",
        help="Also read logs\\archive\\*.log (aggregates across runs)",
    )
    parser.add_argument(
        "--startup-seconds", type=int, default=90,
        help="Seconds from the first line treated as startup (default 90)",
    )
    parser.add_argument("--baseline", action="store_true", help="Rewrite log_budget.json")
    parser.add_argument(
        "--baseline-min-count", type=int, default=3,
        help="Skip signatures rarer than this when baselining (default 3)",
    )
    parser.add_argument("--check", action="store_true", help="Check against log_budget.json")
    parser.add_argument(
        "--strict", action="store_true",
        help="With --check, exit non-zero on regressions. Off by default so a "
             "noisy run reports loudly without becoming a build gate you ignore.",
    )
    parser.add_argument("--quiet", action="store_true", help="Skip the report body")
    parser.add_argument("--json-history", help="Append a one-line JSON summary here")
    args = parser.parse_args()

    paths = collect_files(args.server_dir, args.archive, args.files)
    if not paths:
        print(f"  No log files found under {args.server_dir}")
        print("  (Has the server been started since the appenders were configured?)")
        return 0

    buckets, stats = scan(paths, args.startup_seconds)

    if not args.quiet:
        print_report(buckets, stats, args.top, paths)

    if args.json_history:
        append_history(args.json_history, stats, buckets)

    if args.baseline:
        do_baseline(buckets, stats, args.baseline_min_count)
        return 0

    if args.check:
        budget = load_budget()
        if budget is None:
            print(f"  No budget at {BUDGET_PATH}. Run with --baseline first.")
            return 0
        regressions = do_check(buckets, stats, budget)
        if regressions and args.strict:
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
