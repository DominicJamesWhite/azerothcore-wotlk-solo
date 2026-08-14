#!/usr/bin/env python3
"""Render one matrix run as a single interactive HTML page.

    python tools/matrix_report.py                       # newest run
    python tools/matrix_report.py sims/runs/matrix-...  # a specific one
    python tools/matrix_report.py --all                 # every run on disk

WHY THIS EXISTS, given tools/sim_report.py already writes per-spec pages.

A per-spec page answers "what did this spec do". The question a balance pass
actually asks is comparative -- who is out of line, and by which mechanism --
and 31 separate pages cannot answer it. The terminal table can, but it is a
fixed set of columns in a fixed order, printed once and gone, and the numbers
that matter shift every run: one week it is damage parity, the next it is who
gets meleed at all.

So this is deliberately NOT a prettier version of the terminal table. It is the
same data with the sorting, filtering and drill-down left to the reader, because
which cut matters is not knowable when the run is written.

Self-contained by construction: no CDN, no fetch, no external CSS. The data is
inlined as JSON and the page is a file you can mail to someone. That also means
it keeps working after the run directory is moved, which the per-spec reports
already assume.

DERIVED COLUMNS ARE COMPUTED HERE, NOT IN THE PAGE, with one exception. Anything
that needs the whole set to be meaningful -- vs-median especially -- is computed
in Python where it can be tested, and shipped as a value. The exception is
sorting and filtering, which have to be live.
"""

from __future__ import annotations

import argparse
import html
import json
import statistics
import sys
import time
from pathlib import Path

SIMS = Path(__file__).resolve().parent.parent / "sims"
RUNS = SIMS / "runs"


# ---------------------------------------------------------------------------
#  Data
# ---------------------------------------------------------------------------

def _mitigation_totals(iterations):
    """Sum the incoming-swing ledger across a spec's fights.

    Returns None when the actor was never meleed, which is a real and important
    state rather than a zero: hunter_bm and hunter_mm recorded exactly 0 swings
    at 300s fights, so their 0% damage taken carried no durability information
    at all. A caller that sees None must say "never meleed", not "0%".
    """
    mits = [it.get("mitigation") for it in iterations if it.get("mitigation")]
    mits = [m for m in mits if m.get("swings")]
    if not mits:
        return None

    n = len(mits)
    tot = lambda k: sum(m.get(k, 0) for m in mits)

    swings = tot("swings")
    avoided = sum(tot(k) for k in
                  ("misses", "dodges", "parries", "deflects", "immune"))
    landed = tot("landed")
    stopped = sum(tot(k) for k in ("blocked", "absorbed", "resisted"))

    landing = swings - avoided
    # Mean GROSS landing swing, used to price the avoided ones. Avoided swings
    # are excluded from this denominator deliberately: including them would
    # divide by the quantity being estimated and roughly halve the answer.
    mean_swing = (landed + stopped) / landing if landing else 0
    gross = landed + stopped + avoided * mean_swing

    return {
        "n": n,
        "swings": swings / n,
        "per": {k: tot(k) / n for k in
                ("misses", "dodges", "parries", "deflects", "immune",
                 "blocks", "crits", "glancing", "crushing")},
        "blocked": tot("blocked") / n,
        "absorbed": tot("absorbed") / n,
        "resisted": tot("resisted") / n,
        "landed": landed / n,
        "avoid_pct": 100 * avoided / swings,
        # Share of estimated gross incoming stopped by any mechanism. Partly
        # estimated, because the avoided component is.
        "mitigated_pct": 100 * (1 - landed / gross) if gross else 0,
        "avoided_est": avoided * mean_swing / n,
    }


def _absorb_sources(iterations):
    """Per-shield absorb, summed. Rows are
    [spell, name, absorbed, applications, consumed, expiredWithShield].

    Reported next to the packet-level absorb total so the shortfall is visible.
    That shortfall is large and structural: the shield ledger samples absorb
    auras' remaining amounts at intervals, so a shield created and fully
    consumed between two samples is never seen. Persistent shields (Power Word:
    Shield, Ice Barrier) attribute at 62-88%; proc-driven ones (Savage Defense,
    warlock wards) at 0%. druid_bear absorbed ~42k a fight with 47 attributed.
    """
    out = {}
    for it in iterations:
        for row in it.get("absorb", []):
            if len(row) < 4 or not row[2]:
                continue
            cur = out.setdefault(row[0], {"name": row[1], "absorbed": 0,
                                          "applied": 0})
            cur["absorbed"] += row[2]
            cur["applied"] += row[3]

    n = max(1, len(iterations))
    return sorted(
        ({"spell": k, "name": v["name"], "absorbed": v["absorbed"] / n,
          "applied": v["applied"] / n} for k, v in out.items()),
        key=lambda r: -r["absorbed"])


def collect(run_dir: Path) -> dict:
    """One run directory -> the page's whole data model."""
    matrix_path = run_dir / "matrix.json"
    matrix = {}
    if matrix_path.is_file():
        try:
            matrix = json.load(open(matrix_path, encoding="utf-8"))
        except Exception:
            matrix = {}

    # Keyed by spec so the per-spec files can be joined onto the matrix rows.
    # The matrix row is authoritative for anything it carries, because it is
    # what the terminal table printed and the two must not disagree.
    #
    # Two shapes in the wild: older runs wrote a bare list of rows, current ones
    # write {"woa": [...], "stock": [...]} for the A/B mode. Both are read
    # rather than the older one being declared unsupported -- the whole point of
    # this page is comparing runs, including ones made before it existed.
    by_key = {}
    if isinstance(matrix, list):
        for row in matrix:
            if isinstance(row, dict):
                by_key.setdefault(row.get("key"), {})["woa"] = row
    elif isinstance(matrix, dict):
        for variant in ("woa", "stock"):
            for row in matrix.get(variant) or []:
                if isinstance(row, dict):
                    by_key.setdefault(row.get("key"), {})[variant] = row

    specs = []
    for path in sorted(run_dir.glob("*.json")):
        if path.name == "matrix.json":
            continue

        try:
            d = json.load(open(path, encoding="utf-8"))
        except Exception:
            continue

        # "<spec>.<pass>.json"
        stem = path.name[:-len(".json")]
        key, _, pass_name = stem.partition(".")
        iterations = d.get("iterations") or []
        if not iterations:
            continue

        row = (by_key.get(key) or {}).get("woa") or {}
        mit = _mitigation_totals(iterations)
        max_hp = d.get("actor_max_health") or 0

        dps = [it["dps"] for it in iterations]
        durations = [it["duration_s"] for it in iterations]
        taken = [it.get("damage_taken", 0) for it in iterations]
        deaths = sum(1 for it in iterations
                     if it.get("outcome") == "actor_died")

        mean_dur = statistics.mean(durations)
        mean_taken = statistics.mean(taken)
        taken_pct = 100 * mean_taken / max_hp if max_hp else None

        report = path.with_name(stem + ".report.html")

        specs.append({
            "key": key,
            "pass": pass_name or "?",
            "class_name": row.get("class_name", ""),
            "role": row.get("role", ""),
            "spec_label": d.get("spec", ""),
            "actor": d.get("character", row.get("actor", "")),
            "ilvl": d.get("gear_ilvl", row.get("ilvl", 0)),
            "tabs": d.get("talent_tabs", row.get("tabs", [])),
            "wrong_spec": bool(row.get("wrong_spec")),
            "flags": row.get("flags", []),

            "dps": statistics.mean(dps),
            "dps_samples": dps,
            # Reported, never turned into a confidence interval: the sim is not
            # byte-deterministic, so a same-seed rerun is not a repeat.
            "cv_pct": (100 * statistics.stdev(dps) / statistics.mean(dps)
                       if len(dps) > 1 and statistics.mean(dps) else 0.0),
            "fight_s": mean_dur,
            "iterations": len(iterations),
            "deaths": deaths,
            "kills": sum(1 for it in iterations
                         if it.get("outcome") == "target_died"),
            "taken_pct": taken_pct,
            # Damage taken normalised by time under fire. taken_pct alone is
            # mostly a function of how fast the spec kills, so it re-reports DPS
            # under another name; this does not.
            "taken_per_s": (taken_pct / mean_dur
                            if taken_pct is not None and mean_dur else None),
            "max_health": max_hp,
            "attack_power": d.get("attack_power", 0),
            "spell_power": d.get("spell_power", 0),
            "crit_pct": d.get("crit_pct", 0),
            "gear_failed": d.get("gear_failed", 0),
            "uncastable": d.get("uncastable_spells", 0),

            "melee": mit is not None,
            "swings": mit["swings"] if mit else 0,
            "avoid_pct": mit["avoid_pct"] if mit else None,
            "mitigated_pct": mit["mitigated_pct"] if mit else None,
            "mit": mit,
            "absorb": _absorb_sources(iterations),
            "defense": (iterations[0].get("defense") or {}),
            "pet": (iterations[0].get("pet") or {}),
            "abilities": d.get("abilities", [])[:14],
            "report": (report.name if report.is_file() else None),
        })

    # vs-median needs the whole set, so it is computed here rather than in the
    # page. Median not mean: one 2x outlier should not move the yardstick every
    # other spec is measured against.
    live = [s["dps"] for s in specs if s["dps"]]
    median = statistics.median(live) if live else 0
    for s in specs:
        s["vs_median"] = (s["dps"] / median) if median else None

    specs.sort(key=lambda s: -s["dps"])

    return {
        "run": run_dir.name,
        "when": time.strftime("%Y-%m-%d %H:%M",
                              time.localtime(run_dir.stat().st_mtime)),
        "median_dps": median,
        "specs": specs,
    }


# ---------------------------------------------------------------------------
#  Page
# ---------------------------------------------------------------------------

def render(data: dict, out_path: Path) -> Path:
    payload = json.dumps(data, separators=(",", ":"), allow_nan=False,
                         default=lambda o: None)
    page = (PAGE
            .replace("__TITLE__", html.escape(data["run"]))
            .replace("__DATA__", payload.replace("</", "<\\/")))
    out_path.write_text(page, encoding="utf-8")
    return out_path


def build_for(run_dir: Path) -> Path | None:
    data = collect(run_dir)
    if not data["specs"]:
        return None
    return render(data, run_dir / "matrix.report.html")


def build_runs_index() -> Path:
    """sims/matrix.html -- every matrix run, newest first.

    Separate from sims/index.html, which lists per-spec reports. Mixing them
    would bury the 31 comparative pages under several hundred per-spec ones,
    and the two are read for different reasons.
    """
    rows = []
    for page in sorted(RUNS.glob("matrix-*/matrix.report.html"),
                       key=lambda p: p.stat().st_mtime, reverse=True):
        run = page.parent
        # Cheap: read the run's own JSONs only for the count, not the contents.
        n = len([p for p in run.glob("*.json") if p.name != "matrix.json"])
        rows.append(
            f'<tr><td><a href="{html.escape(_rel(page))}">'
            f'{html.escape(run.name)}</a></td>'
            f'<td class="num">{n}</td>'
            f'<td class="muted">'
            f'{time.strftime("%Y-%m-%d %H:%M", time.localtime(run.stat().st_mtime))}'
            f'</td></tr>')

    out = SIMS / "matrix.html"
    out.write_text(
        RUNS_INDEX.replace("__ROWS__", "\n".join(rows) or
                           '<tr><td colspan="3" class="muted">No matrix runs yet.</td></tr>')
                   .replace("__COUNT__", str(len(rows))),
        encoding="utf-8")
    return out


def _rel(p: Path) -> str:
    import os
    return os.path.relpath(p, SIMS).replace("\\", "/")


def newest_run() -> Path | None:
    runs = [p for p in RUNS.glob("matrix-*") if p.is_dir()]
    return max(runs, key=lambda p: p.stat().st_mtime) if runs else None


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("run", nargs="?", type=Path,
                   help="matrix run directory (default: newest)")
    p.add_argument("--all", action="store_true",
                   help="rebuild the page for every matrix run on disk")
    args = p.parse_args()

    if args.all:
        targets = sorted(p for p in RUNS.glob("matrix-*") if p.is_dir())
    elif args.run:
        targets = [args.run]
    else:
        newest = newest_run()
        if not newest:
            print("no matrix runs found under sims/runs/")
            return 1
        targets = [newest]

    written = 0
    for run_dir in targets:
        if not run_dir.is_dir():
            print(f"not a directory: {run_dir}")
            continue
        out = build_for(run_dir)
        if out:
            written += 1
            print(f"  {out}")
        else:
            print(f"  (no usable results in {run_dir.name})")

    if written:
        print(f"  index: {build_runs_index()}")

    return 0 if written else 1


RUNS_INDEX = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alonecraft sim matrix runs</title>
<style>
:root { --gold:#ffd100; --gold-dim:#b8912f; --border:#4a3a22;
        --text:#f0e6d2; --muted:#9d8e75; --panel:#171208; }
* { box-sizing:border-box; }
body { margin:0; color:var(--text); font:14px/1.5 "Segoe UI",system-ui,sans-serif;
  background: radial-gradient(circle at 50% -10%,#2a2115 0%,transparent 60%),
              linear-gradient(#100c08,#0a0705 70%);
  background-attachment:fixed; min-height:100vh; }
a { color:var(--gold); }
.muted { color:var(--muted); }
.wrap { max-width:900px; margin:0 auto; padding:0 16px 64px; }
.topbar { border-bottom:1px solid var(--border); background:rgba(0,0,0,.35); }
.topbar .wrap { padding:14px 16px; display:flex; align-items:baseline; gap:14px; }
h1 { font-size:18px; margin:0; color:var(--gold); }
table { border-collapse:collapse; width:100%; margin-top:20px;
        border:1px solid var(--border); border-radius:6px; background:var(--panel); }
th,td { padding:8px 11px; text-align:left; border-bottom:1px solid rgba(74,58,34,.5); }
th { font-size:11px; text-transform:uppercase; letter-spacing:.06em;
     color:var(--gold-dim); }
td.num, th.num { text-align:right; font-variant-numeric:tabular-nums; }
tbody tr:hover { background:rgba(255,209,0,.05); }
p.note { color:var(--muted); font-size:12px; margin-top:18px; }
</style>
</head>
<body>
<div class="topbar"><div class="wrap">
  <h1>Alonecraft sim matrix runs</h1>
  <span class="muted">__COUNT__ run(s)</span>
</div></div>
<div class="wrap">
  <table>
    <thead><tr><th>run</th><th class="num">specs</th><th>when</th></tr></thead>
    <tbody>__ROWS__</tbody>
  </table>
  <p class="note">Each run is a sortable, filterable table with per-spec
  drill-down. Per-spec single-fight reports are indexed separately in
  <a href="index.html">index.html</a>.</p>
</div>
</body>
</html>
"""


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<style>
:root {
  --gold: #ffd100; --gold-dim: #b8912f; --parchment: #f8e6c0;
  --green: #1eff00; --red: #fe2e2e; --amber: #ffa500; --border: #4a3a22;
  --text: #f0e6d2; --muted: #9d8e75;
  --panel: #171208; --panel-2: #1f1810;
}
* { box-sizing: border-box; }
body {
  margin: 0; color: var(--text);
  font: 14px/1.5 "Segoe UI", system-ui, sans-serif;
  background:
    radial-gradient(circle at 50% -10%, #2a2115 0%, transparent 60%),
    linear-gradient(#100c08, #0a0705 70%);
  background-attachment: fixed; min-height: 100vh;
}
a { color: var(--gold); }
.muted { color: var(--muted); }
.wrap { max-width: 1500px; margin: 0 auto; padding: 0 16px 64px; }
.topbar { border-bottom: 1px solid var(--border); background: rgba(0,0,0,.35); }
.topbar .wrap { padding: 14px 16px; display:flex; align-items:baseline;
                gap:14px; flex-wrap:wrap; }
h1 { font-size: 18px; margin: 0; color: var(--gold); letter-spacing:.02em; }
h2 { font-size: 15px; color: var(--gold-dim); margin: 26px 0 8px;
     text-transform: uppercase; letter-spacing:.08em; }

.controls { display:flex; gap:10px; flex-wrap:wrap; align-items:center;
            margin: 18px 0 10px; }
.controls input, .controls select {
  background: var(--panel-2); color: var(--text);
  border: 1px solid var(--border); border-radius: 4px;
  padding: 6px 9px; font: inherit;
}
.controls input:focus, .controls select:focus { outline:1px solid var(--gold-dim); }
.chip { border:1px solid var(--border); background:var(--panel);
        border-radius:999px; padding:4px 11px; cursor:pointer;
        color:var(--muted); user-select:none; }
.chip.on { color:#120d05; background:var(--gold); border-color:var(--gold); }

.tablewrap { overflow-x: auto; border:1px solid var(--border);
             border-radius:6px; background: var(--panel); }
table { border-collapse: collapse; width:100%; font-variant-numeric: tabular-nums; }
th, td { padding: 6px 9px; text-align: right; white-space: nowrap;
         border-bottom: 1px solid rgba(74,58,34,.5); }
th:first-child, td:first-child,
th.left, td.left { text-align: left; }
thead th { position: sticky; top: 0; z-index: 2;
           background: #100c08; color: var(--gold-dim);
           font-size: 11px; text-transform: uppercase; letter-spacing:.06em;
           cursor: pointer; user-select:none; }
thead th:hover { color: var(--gold); }
thead th .dir { color: var(--gold); }
tbody tr:hover { background: rgba(255,209,0,.05); }
tbody tr.open { background: rgba(255,209,0,.08); }
tr.spec { cursor: pointer; }
.bad  { color: var(--red); }
.good { color: var(--green); }
.warn { color: var(--amber); }
.pill { font-size:11px; padding:1px 7px; border-radius:999px;
        border:1px solid var(--border); color:var(--muted); }

/* A number and its share of the row, so the eye can scan without reading. */
.bar { position:relative; display:block; }
.bar::before {
  content:""; position:absolute; right:0; top:50%; transform:translateY(-50%);
  height:15px; background:rgba(255,209,0,.16); width:var(--w,0%);
  border-radius:2px; z-index:-1;
}
td.barcell { position:relative; z-index:0; }

.detail td { background: #0d0a06; padding: 0; }
.detail .inner { padding: 14px 18px 20px; display:grid; gap:22px;
                 grid-template-columns: repeat(auto-fit,minmax(290px,1fr)); }
.detail h3 { font-size:12px; margin:0 0 7px; color:var(--gold-dim);
             text-transform:uppercase; letter-spacing:.07em; }
.detail table { font-size:13px; }
.detail td, .detail th { border-bottom:1px solid rgba(74,58,34,.35); }
.note { font-size:12px; color:var(--muted); margin-top:6px; }
.empty { padding:26px; text-align:center; color:var(--muted); }
footer { margin-top:30px; font-size:12px; color:var(--muted);
         border-top:1px solid var(--border); padding-top:14px; }
code { background:var(--panel-2); padding:1px 5px; border-radius:3px; }
</style>
</head>
<body>
<div class="topbar"><div class="wrap">
  <h1>Alonecraft sim matrix</h1>
  <span class="muted" id="runline"></span>
</div></div>

<div class="wrap">
  <div class="controls">
    <input id="q" type="search" placeholder="filter spec, class, role..." size="26">
    <select id="rolesel"><option value="">all roles</option></select>
    <select id="classsel"><option value="">all classes</option></select>
    <span class="chip" data-flt="died">died at least once</span>
    <span class="chip" data-flt="nomelee">never meleed</span>
    <span class="chip" data-flt="flagged">flagged</span>
    <span class="muted" id="count"></span>
  </div>

  <div class="tablewrap">
    <table id="t">
      <thead><tr id="head"></tr></thead>
      <tbody id="body"></tbody>
    </table>
  </div>
  <div class="note">
    Click any row to expand it. Columns sort on click; click again to reverse.
    <b>avoid</b> and <b>mitig</b> are blank where the actor was never meleed &mdash;
    that is not 0%, it is no data, and reading it as durability is how a spec
    behind a pet gets mistaken for a tough one.
  </div>

  <footer>
    <b>mitig%</b> is the share of <i>estimated</i> gross incoming damage that never
    reached the health bar. Avoided damage has to be estimated &mdash; the server
    never computes what a dodged swing would have hit for &mdash; so it is priced at
    the mean <i>landing</i> swing. Block, absorb, resist and every swing count are
    exact, off <code>SMSG_ATTACKERSTATEUPDATE</code>.
    <br><br>
    <b>Per-source absorb is incomplete by construction.</b> The shield ledger samples
    absorb auras' remaining amounts at intervals, so a shield created and fully
    consumed between samples is invisible. Persistent shields attribute at 62&ndash;88%;
    proc-driven ones (Savage Defense, warlock wards) at 0%. Each spec shows its own
    coverage, and a low figure means the absorb breakdown for that spec is not to be
    trusted &mdash; the total still is.
    <br><br>
    <b>Rated defence is sampled at pull.</b> Any stat that moves in combat reads low:
    the warrior crit&rarr;parry talent recalculates every 2s off live crit, so its
    observed parry legitimately exceeds its rated value once crit cooldowns are up.
  </footer>
</div>

<script>
const DATA = __DATA__;

const f0 = v => v == null ? "" : Math.round(v).toLocaleString();
const f1 = v => v == null ? "" : v.toFixed(1);
const f2 = v => v == null ? "" : v.toFixed(2);
const pct = v => v == null ? "" : Math.round(v) + "%";

/* Columns are declared, not hand-written into the markup, so adding one is a
   single entry and sorting/filtering pick it up for free. */
const COLS = [
  {k:"key",        t:"spec",   left:1, fmt:s=>s.key,
                   cls:s=>s.wrong_spec?"bad":""},
  {k:"role",       t:"role",   left:1, fmt:s=>s.role||""},
  {k:"dps",        t:"dps",    fmt:s=>f0(s.dps), bar:"dps"},
  {k:"vs_median",  t:"vs med", fmt:s=>s.vs_median==null?"":f2(s.vs_median)+"x",
                   cls:s=>s.vs_median==null?"":(s.vs_median>=1.5?"warn":
                        s.vs_median<=0.66?"bad":"")},
  {k:"cv_pct",     t:"cv",     fmt:s=>pct(s.cv_pct),
                   cls:s=>s.cv_pct>15?"warn":""},
  {k:"fight_s",    t:"fight",  fmt:s=>f0(s.fight_s)+"s"},
  {k:"deaths",     t:"died",   fmt:s=>s.deaths+"/"+s.iterations,
                   cls:s=>s.deaths===s.iterations?"bad":s.deaths?"warn":"good"},
  {k:"taken_pct",  t:"taken",  fmt:s=>pct(s.taken_pct)},
  {k:"taken_per_s",t:"taken/s",fmt:s=>f2(s.taken_per_s),
                   cls:s=>s.taken_per_s==null?"":(s.taken_per_s>5?"bad":
                        s.taken_per_s<0.5?"good":"")},
  {k:"swings",     t:"swings", fmt:s=>s.melee?f0(s.swings):"—",
                   cls:s=>s.melee?"":"muted"},
  {k:"avoid_pct",  t:"avoid",  fmt:s=>s.melee?pct(s.avoid_pct):"",  bar:"avoid_pct"},
  {k:"mitigated_pct",t:"mitig",fmt:s=>s.melee?pct(s.mitigated_pct):"",bar:"mitigated_pct"},
  {k:"ilvl",       t:"ilvl",   fmt:s=>s.ilvl||""},
  {k:"top",        t:"top ability", left:1,
                   fmt:s=>s.abilities.length
                     ? s.abilities[0].name+" ("+Math.round(100*s.abilities[0].share)+"%)"
                     : ""},
];

/* Bars are scaled against the visible maximum, so a filtered view rescales
   rather than showing everything squashed against one outlier. */
const BARMAX = {};
function rescale(rows){
  for (const c of COLS) if (c.bar) {
    BARMAX[c.bar] = Math.max(1, ...rows.map(s => s[c.bar] || 0));
  }
}

let sortKey = "dps", sortDir = -1;
const filters = new Set();

function visible(){
  const q = document.getElementById("q").value.trim().toLowerCase();
  const role = document.getElementById("rolesel").value;
  const klass = document.getElementById("classsel").value;

  return DATA.specs.filter(s => {
    if (role && s.role !== role) return false;
    if (klass && s.class_name !== klass) return false;
    if (filters.has("died") && !s.deaths) return false;
    if (filters.has("nomelee") && s.melee) return false;
    if (filters.has("flagged") && !(s.flags||[]).length && !s.wrong_spec) return false;
    if (q) {
      const hay = [s.key, s.role, s.class_name, s.spec_label, s.actor]
        .join(" ").toLowerCase();
      if (!hay.includes(q)) return false;
    }
    return true;
  });
}

function sorted(rows){
  const c = COLS.find(c => c.k === sortKey);
  return rows.slice().sort((a,b) => {
    let x = a[sortKey], y = b[sortKey];
    if (sortKey === "top") { x = (a.abilities[0]||{}).name||""; y = (b.abilities[0]||{}).name||""; }
    // Nulls always sort last, whichever direction: "no data" is not a small
    // number and must not lead an ascending sort.
    if (x == null && y == null) return 0;
    if (x == null) return 1;
    if (y == null) return -1;
    if (typeof x === "string") return sortDir * x.localeCompare(y);
    return sortDir * (x - y);
  });
}

function head(){
  document.getElementById("head").innerHTML = COLS.map(c =>
    `<th class="${c.left?'left':''}" data-k="${c.k}">${c.t}` +
    (sortKey===c.k ? ` <span class="dir">${sortDir<0?"▼":"▲"}</span>` : "") +
    `</th>`).join("");
  document.querySelectorAll("#head th").forEach(th =>
    th.onclick = () => {
      const k = th.dataset.k;
      if (sortKey === k) sortDir = -sortDir;
      else { sortKey = k; sortDir = (k==="key"||k==="role"||k==="top") ? 1 : -1; }
      draw();
    });
}

function detail(s){
  const m = s.mit;
  let mitHtml = `<p class="muted">This actor was never meleed, so there is
    nothing to attribute. A ranged spec behind a pet holding aggro reads this
    way; it is a positioning result, not a defensive one.</p>`;

  if (m) {
    const rows = [];
    const est = m.avoided_est;
    const gross = m.landed + m.blocked + m.absorbed + m.resisted + est;
    const share = v => gross ? Math.round(100*v/gross)+"%" : "";
    const mean = (m.swings - Object.entries(m.per)
        .filter(([k]) => ["misses","dodges","parries","deflects","immune"].includes(k))
        .reduce((a,[,v]) => a+v, 0));
    const perSwing = mean ? (m.landed+m.blocked+m.absorbed+m.resisted)/mean : 0;

    for (const [k,label] of [["misses","miss"],["dodges","dodge"],
                             ["parries","parry"],["deflects","deflect"],
                             ["immune","immune"]]) {
      const c = m.per[k];
      if (!c) continue;
      rows.push(`<tr><td class="left">${label}</td><td>${f1(c)}</td>
        <td>${pct(100*c/m.swings)}</td><td>${f0(c*perSwing)}</td>
        <td>${share(c*perSwing)}</td><td class="muted">estimated</td></tr>`);
    }
    for (const [label,cnt,dmg] of [["block", m.per.blocks, m.blocked],
                                   ["absorb", null, m.absorbed],
                                   ["resist", null, m.resisted]]) {
      if (!dmg) continue;
      rows.push(`<tr><td class="left">${label}</td>
        <td>${cnt!=null?f1(cnt):""}</td>
        <td>${cnt!=null?pct(100*cnt/m.swings):""}</td>
        <td>${f0(dmg)}</td><td>${share(dmg)}</td>
        <td class="good">measured</td></tr>`);
    }
    rows.push(`<tr><td class="left"><b>reached hp</b></td><td>${f1(mean)}</td>
      <td>${pct(100*mean/m.swings)}</td><td>${f0(m.landed)}</td>
      <td>${share(m.landed)}</td><td class="good">measured</td></tr>`);

    mitHtml = `<table><thead><tr><th class="left">mechanism</th><th>count</th>
      <th>rate</th><th>damage</th><th>share</th><th></th></tr></thead>
      <tbody>${rows.join("")}</tbody></table>
      <p class="note">${f1(m.swings)} swings per fight, mean of ${m.n}.</p>`;
  }

  const d = s.defense || {};
  const obs = k => (m && m.swings) ? 100*m.per[k]/m.swings : null;
  const defHtml = !m ? "" : `<table>
    <thead><tr><th class="left">defence</th><th>rated</th><th>observed</th></tr></thead>
    <tbody>
      <tr><td class="left">dodge</td><td>${f1(d.dodge_pct)}%</td><td>${f1(obs("dodges"))}%</td></tr>
      <tr><td class="left">parry</td><td>${f1(d.parry_pct)}%</td><td>${f1(obs("parries"))}%</td></tr>
      <tr><td class="left">block</td><td>${f1(d.block_pct)}%</td><td>${f1(obs("blocks"))}%</td></tr>
      <tr><td class="left">armor</td><td>${f0(d.armor)}</td><td></td></tr>
    </tbody></table>`;

  const auras = (d.reduction_auras||[]);
  const auraHtml = !auras.length ? "" : `<h3>damage-reduction auras at pull</h3>
    <table><tbody>${auras.map(a =>
      `<tr><td class="left">${a.name}</td><td>${a.amount}</td></tr>`).join("")}
    </tbody></table>
    <p class="note">The aura's own value, not damage prevented. The core applies
    these inside the damage calculation and never reports the difference, so any
    damage number here would be invented.</p>`;

  const totalAbs = m ? m.absorbed : 0;
  const attributed = s.absorb.reduce((a,r) => a + r.absorbed, 0);
  const cov = totalAbs ? Math.round(100*attributed/totalAbs) : null;
  const absHtml = !s.absorb.length && !totalAbs ? "" : `<h3>absorb by source</h3>
    <table><thead><tr><th class="left">shield</th><th>absorbed</th>
      <th>applied</th></tr></thead><tbody>
      ${s.absorb.map(r => `<tr><td class="left">${r.name} (${r.spell})</td>
        <td>${f0(r.absorbed)}</td><td>${f1(r.applied)}</td></tr>`).join("")
        || `<tr><td colspan="3" class="muted">nothing attributed</td></tr>`}
    </tbody></table>
    ${cov==null ? "" : `<p class="note ${cov<50?'warn':''}">
      ${f0(attributed)} of ${f0(totalAbs)} attributed (${cov}% coverage).
      ${cov<50 ? "Most of this spec's absorb comes from shields consumed between \
samples, so the breakdown is not representative — the total is." : ""}</p>`}`;

  const pet = s.pet || {};
  const petHtml = !pet.entry ? "" : `<h3>pet</h3><table><tbody>
    <tr><td class="left">entry</td><td>${pet.entry}</td></tr>
    <tr><td class="left">level</td><td>${pet.level}</td></tr>
    <tr><td class="left">attack power</td><td>${f0(pet.attack_power)}</td></tr>
    <tr><td class="left">auras (passive)</td><td>${pet.auras} (${pet.passives})</td></tr>
  </tbody></table>`;

  const abil = `<h3>damage sources</h3><table>
    <thead><tr><th class="left">ability</th><th>src</th><th>hits</th>
      <th>damage</th><th>share</th></tr></thead><tbody>
    ${s.abilities.map(a => `<tr><td class="left">${a.name}</td>
      <td class="muted">${a.pet?"pet":"you"}</td><td>${f0(a.count)}</td>
      <td>${f0(a.damage)}</td><td>${pct(100*a.share)}</td></tr>`).join("")}
    </tbody></table>`;

  const flags = (s.flags||[]).length
    ? `<p class="note bad">${s.flags.map(x=>"⚑ "+x).join("<br>")}</p>` : "";

  const meta = `<h3>actor</h3><table><tbody>
    <tr><td class="left">character</td><td>${s.actor||""}</td></tr>
    <tr><td class="left">premade spec</td><td>${s.spec_label||""}</td></tr>
    <tr><td class="left">talent tabs</td><td>${(s.tabs||[]).join(" / ")}</td></tr>
    <tr><td class="left">ilvl</td><td>${s.ilvl||""}</td></tr>
    <tr><td class="left">AP / SP</td><td>${f0(s.attack_power)} / ${f0(s.spell_power)}</td></tr>
    <tr><td class="left">crit</td><td>${f1(s.crit_pct)}%</td></tr>
    <tr><td class="left">max health</td><td>${f0(s.max_health)}</td></tr>
    <tr><td class="left">dps samples</td><td>${s.dps_samples.map(f0).join(", ")}</td></tr>
    </tbody></table>${flags}
    ${s.report?`<p class="note"><a href="${s.report}">full per-fight report →</a></p>`:""}`;

  return `<div class="inner">
    <div><h3>mitigation and avoidance</h3>${mitHtml}${defHtml}</div>
    <div>${absHtml}${auraHtml}${petHtml}</div>
    <div>${abil}</div>
    <div>${meta}</div>
  </div>`;
}

const open = new Set();

function draw(){
  const rows = sorted(visible());
  rescale(rows);
  head();

  const body = document.getElementById("body");
  if (!rows.length) {
    body.innerHTML = `<tr><td colspan="${COLS.length}" class="empty">
      Nothing matches that filter.</td></tr>`;
  } else {
    body.innerHTML = rows.map(s => {
      const tds = COLS.map(c => {
        const cls = [c.left?"left":"", c.cls?c.cls(s):""].filter(Boolean).join(" ");
        if (c.bar) {
          const w = BARMAX[c.bar] ? 100*(s[c.bar]||0)/BARMAX[c.bar] : 0;
          return `<td class="barcell ${cls}"><span class="bar"
            style="--w:${w.toFixed(1)}%">${c.fmt(s)}</span></td>`;
        }
        return `<td class="${cls}">${c.fmt(s)}</td>`;
      }).join("");
      const det = open.has(s.key)
        ? `<tr class="detail"><td colspan="${COLS.length}">${detail(s)}</td></tr>`
        : "";
      return `<tr class="spec ${open.has(s.key)?'open':''}"
        data-key="${s.key}">${tds}</tr>${det}`;
    }).join("");
  }

  document.querySelectorAll("tr.spec").forEach(tr => tr.onclick = () => {
    const k = tr.dataset.key;
    open.has(k) ? open.delete(k) : open.add(k);
    draw();
  });

  document.getElementById("count").textContent =
    `${rows.length} of ${DATA.specs.length} specs`;
}

function init(){
  document.getElementById("runline").textContent =
    `${DATA.run} — ${DATA.when} — median ${Math.round(DATA.median_dps).toLocaleString()} DPS`;

  const roles = [...new Set(DATA.specs.map(s=>s.role).filter(Boolean))].sort();
  const classes = [...new Set(DATA.specs.map(s=>s.class_name).filter(Boolean))].sort();
  for (const r of roles)
    document.getElementById("rolesel").insertAdjacentHTML("beforeend",
      `<option value="${r}">${r}</option>`);
  for (const c of classes)
    document.getElementById("classsel").insertAdjacentHTML("beforeend",
      `<option value="${c}">${c}</option>`);

  document.getElementById("q").oninput = draw;
  document.getElementById("rolesel").onchange = draw;
  document.getElementById("classsel").onchange = draw;
  document.querySelectorAll(".chip").forEach(ch => ch.onclick = () => {
    const f = ch.dataset.flt;
    filters.has(f) ? filters.delete(f) : filters.add(f);
    ch.classList.toggle("on");
    draw();
  });

  draw();
}
init();
</script>
</body>
</html>
"""


if __name__ == "__main__":
    sys.exit(main())
