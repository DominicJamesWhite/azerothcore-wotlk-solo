#!/usr/bin/env python3
"""Turn a simulator result into a Warcraft-Logs-style HTML report.

    python tools/sim_report.py sims/runs/matrix-20260814-125119   # a whole matrix
    python tools/sim_report.py sims/runs/Apold-arcane-....json     # one run
    python tools/sim_report.py --index                             # rebuild the index
    python tools/sim_report.py <path> --no-icons                   # skip the DBC read

Why this exists
---------------
The simulator answers "what DPS did this spec do?" well and every other question
badly. Balancing a solo spec means asking *why* a number is what it is: which
button carried the damage, whether the redesigned proc was ever pressed, whether
mana ran out at 200s, whether a shield ate the incoming damage or the boss simply
ignored the caster. Those are the questions Warcraft Logs was built to answer for
raids, and they are the same questions here.

So the vocabulary is deliberately WCL's -- a fight list, a damage-done
breakdown, buff uptimes, a time axis -- because that is the language this is
already thought about in.

What it is not
--------------
Not a ranking. With one target, no raid buffs, no movement and a bot rotation,
the absolute numbers are not raid DPS. Every view here exists to make a
*mechanism* visible, not to crown a spec.

Design constraints, matching site/
----------------------------------
No build step, no CDN, no charting library, no third-party Python. Charts are
inline SVG built in vanilla JS, exactly as site/js/tree.js already does it. The
result JSON is embedded in the page and icons are inlined as data URIs, so a
report is one file that still works after being moved or emailed.
"""

import argparse
import base64
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SIMS = REPO / "sims"
RUNS = SIMS / "runs"
ICON_DIR = REPO / "site" / "assets" / "icons"

SCHEMA = "alonecraft.sim.result/1"

# Mirrors DamageKind in SimRunner.cpp.
KINDS = ("unknown", "melee", "spell", "periodic")

# Mirrors DeathRole in SimRunner.cpp.
DEATH_ROLES = ("actor", "target", "pet")

# Mirrors EventFlags in SimRunner.cpp.
EF_FROM_PET, EF_INCOMING, EF_UNATTRIBUTED, EF_SELF = 1, 2, 4, 8

# Mirrors Powers in SharedDefines.h; only the ones a level-80 actor can show.
POWER_NAMES = {0: "Mana", 1: "Rage", 2: "Focus", 3: "Energy",
               5: "Runes", 6: "Runic Power"}

CLASS_BY_TAB_HINT = {
    "paladin": "paladin", "priest": "priest", "shaman": "shaman",
    "druid": "druid", "mage": "mage", "warlock": "warlock",
    "warrior": "warrior", "rogue": "rogue", "hunter": "hunter",
    "death": "death-knight", "dk": "death-knight",
}


# ---------------------------------------------------------------------------
#  Loading
# ---------------------------------------------------------------------------

def check_schema(result, path):
    """Warn on a minor mismatch, refuse a major one.

    A stale result file sitting in a matrix directory should degrade to blank
    views, not abort a run over thirty specs.
    """
    got = result.get("schema", "alonecraft.sim.result/0")
    want_major = SCHEMA.rsplit("/", 1)[0]

    if got.rsplit("/", 1)[0] != want_major:
        sys.exit(f"ERROR: {path}: unknown result schema {got!r}")

    if got != SCHEMA:
        print(f"  note: {path.name} is {got}, expected {SCHEMA}; "
              f"views needing newer fields will be empty", file=sys.stderr)

    return result


def load_result(path: Path):
    with open(path, encoding="utf-8") as f:
        return check_schema(json.load(f), path)


def find_results(target: Path):
    """Result JSONs under a path, whether it is one file or a matrix directory."""
    if target.is_file():
        return [target]

    if not target.is_dir():
        sys.exit(f"ERROR: {target} not found")

    return sorted(p for p in target.glob("*.json") if p.name != "matrix.json")


# ---------------------------------------------------------------------------
#  Icons
# ---------------------------------------------------------------------------

def icon_names_for(spell_ids):
    """spell id -> lowercase icon basename, via SpellIconID in Spell.dbc.

    site/assets/icons/ is keyed by the SpellIcon.dbc texture basename, not by
    spell id, so this is the join. Reuses the same DBC readers the talent export
    and tools/extract_icons.py use rather than re-deriving the format.
    """
    sys.path.insert(0, str(REPO / "modules" / "world_of_alonecraft" / "dbc"))
    try:
        import config          # noqa: E402
        import spell_dbc as S  # noqa: E402
    except Exception as exc:                                   # pragma: no cover
        print(f"  icons: DBC modules unavailable ({exc}); rendering without them")
        return {}

    try:
        icons = S.read_dbc(config.BASE_SPELLICON_DBC_PATH,
                           S.SPELLICON_COLUMNS, S.SPELLICON_FMT, quiet=True)
        spells = S.read_dbc(config.BASE_DBC_PATH,
                            S.SPELL_COLUMNS, S.SPELL_FMT, quiet=True)
    except Exception as exc:                                   # pragma: no cover
        print(f"  icons: could not read DBCs ({exc}); rendering without them")
        return {}

    by_id = {}
    for spell_id in spell_ids:
        row = spells.get(spell_id)
        if not row:
            continue

        icon = icons.get(row.get("SpellIconID"))
        texture = icon.get("TextureFilename") if icon else None
        if not texture:
            continue

        by_id[spell_id] = texture.replace("/", "\\").rsplit("\\", 1)[-1].lower()

    return by_id


def inline_icons(spell_ids, enabled=True):
    """spell id -> data: URI, for the icons we actually have on disk."""
    if not enabled:
        return {}, []

    names = icon_names_for(spell_ids)
    out, missing = {}, []

    for spell_id, name in names.items():
        png = ICON_DIR / f"{name}.png"
        if not png.is_file():
            missing.append(name)
            continue

        data = base64.b64encode(png.read_bytes()).decode("ascii")
        out[spell_id] = f"data:image/png;base64,{data}"

    return out, sorted(set(missing))


# ---------------------------------------------------------------------------
#  Shaping
# ---------------------------------------------------------------------------

def class_slug(result, path=None):
    """The class accent colour to theme the page with.

    The result carries no class field, and the spec name alone will not do it:
    a premade spec is called "resto pve", which names the tree and not the
    class. The matrix writes files as <class>_<spec>.<pass>.json, so the
    filename is the reliable hint and the spec name is the fallback for a bare
    sim.py run.
    """
    hay = ((path.name.lower() + " ") if path else "") + (result.get("spec") or "").lower()

    for needle, slug in CLASS_BY_TAB_HINT.items():
        if needle in hay:
            return slug

    return ""


def summarise(result, path=None):
    """Everything the page needs, pre-shaped so the JS stays presentational."""
    iterations = result.get("iterations", [])
    duration = result.get("duration_s", 0.0) or 0.0

    fights = []
    for it in iterations:
        secs = it.get("duration_s", 0.0) or 0.0
        fights.append({
            "i": it.get("i", 0),
            "seed": it.get("seed", 0),
            "duration": secs,
            "damage": it.get("damage", 0),
            "dps": it.get("dps", 0.0),
            "healing": it.get("healing", 0),
            "overheal": it.get("overheal", 0),
            "taken": it.get("damage_taken", 0),
            "absorbedOnActor": it.get("absorbed_on_actor", 0),
            "resistedOnActor": it.get("resisted_on_actor", 0),
            "outcome": it.get("outcome", "timeout"),
            "actorHp": it.get("actor_hp_pct", 0),
            "targetHp": it.get("target_hp_pct", 0),
            "abilities": it.get("abilities", []),
            "events": it.get("events", []),
            "deaths": it.get("deaths", []),
            "resources": it.get("resources", []),
            "actorUptime": it.get("actor_uptime", []),
            "targetUptime": it.get("target_uptime", []),
            "auraStacks": it.get("aura_stacks", {}),
            "absorb": it.get("absorb", []),
            "auraSamples": it.get("aura_samples", 0),
            "aurasFiltered": it.get("auras_filtered", 0),
            "eventsDropped": it.get("events_dropped", 0),
            # End-of-fight snapshots, kept because they list *everything*
            # including the permanent passives the uptime table filters out.
            "actorAuras": it.get("actor_auras", []),
            "targetAuras": it.get("target_auras", []),
        })

    return {
        "schema": result.get("schema"),
        "ok": result.get("ok", False),
        "note": result.get("note", ""),
        "character": result.get("character", "?"),
        "spec": result.get("spec", "?"),
        "classSlug": class_slug(result, path),
        "level": result.get("level", 0),
        "ilvl": result.get("gear_ilvl", 0),
        "gearEquipped": result.get("gear_equipped", 0),
        "gearFailed": result.get("gear_failed", 0),
        "uncastable": result.get("uncastable_spells", 0),
        "attackPower": result.get("attack_power", 0),
        "spellPower": result.get("spell_power", 0),
        "critPct": result.get("crit_pct", 0.0),
        "talentTabs": result.get("talent_tabs", [0, 0, 0]),
        "maxHealth": result.get("actor_max_health", 0),
        "targetEntry": result.get("target_entry", 0),
        "duration": duration,
        "wall": result.get("wall_s", 0.0),
        "realtime": result.get("realtime_factor", 0.0),
        "damage": result.get("damage", 0),
        "dps": result.get("dps", 0.0),
        "healing": result.get("healing", 0),
        "overheal": result.get("overheal", 0),
        "abilities": result.get("abilities", []),
        "unattributed": result.get("unattributed_damage", 0),
        "unattributedByType": result.get("unattributed_by_type", {}),
        "latchMiss": result.get("latch_miss", {}),
        "latchOverflow": result.get("latch_overflow", 0),
        "critKnown": result.get("crit_known", False),
        "logMatched": result.get("log_matched", 0),
        "logUnmatched": result.get("log_unmatched", 0),
        "auraSampleMs": result.get("aura_sample_ms", 0),
        "resourceSampleMs": result.get("resource_sample_ms", 0),
        "tickMs": result.get("tick_ms", 25),
        "fights": fights,
    }


def spell_ids_in(data):
    """Every spell id the page will want an icon for."""
    ids = {a.get("spell", 0) for a in data["abilities"]}

    for f in data["fights"]:
        ids |= {row[0] for row in f["abilities"]}
        ids |= {row[0] for row in f["actorUptime"]}
        ids |= {row[0] for row in f["targetUptime"]}
        ids |= {row[0] for row in f["absorb"]}

    ids.discard(0)
    return ids


# ---------------------------------------------------------------------------
#  Rendering
# ---------------------------------------------------------------------------

def render_report(data, icons, out_path: Path):
    payload = json.dumps({"run": data, "icons": icons}, separators=(",", ":"))
    title = f"{data['character']} - {data['spec']}"

    html = REPORT_HTML.replace("__TITLE__", _esc(title))
    html = html.replace("__CLASS__", data["classSlug"])
    html = html.replace("__CSS__", REPORT_CSS)
    html = html.replace("__JS__", REPORT_JS)
    # Last, and via a function, so a "__JS__" inside the data cannot be
    # substituted into and a backslash in a spell name survives intact.
    html = html.replace("__DATA__", payload.replace("</", "<\\/"))

    out_path.write_text(html, encoding="utf-8")
    return out_path


def _esc(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def render_index(entries, out_path: Path):
    rows = []
    for e in entries:
        rows.append(
            f'<tr><td><a href="{_esc(e["href"])}">{_esc(e["name"])}</a></td>'
            f'<td>{_esc(e["spec"])}</td>'
            f'<td class="num">{e["dps"]:,.0f}</td>'
            f'<td class="num">{e["duration"]:,.0f}s</td>'
            f'<td class="num">{e["fights"]}</td>'
            f'<td class="muted">{_esc(e["when"])}</td></tr>')

    html = (INDEX_HTML
            .replace("__CSS__", REPORT_CSS)
            .replace("__ROWS__", "\n".join(rows) or
                     '<tr><td colspan="6" class="muted">No reports yet.</td></tr>')
            .replace("__COUNT__", str(len(entries))))

    out_path.write_text(html, encoding="utf-8")
    return out_path


# ---------------------------------------------------------------------------
#  Page assets
# ---------------------------------------------------------------------------

# Palette and type lifted from site/css/style.css so a report looks like the
# talent calculator rather than like a different project.
REPORT_CSS = """
:root {
  --gold: #ffd100; --gold-dim: #b8912f; --parchment: #f8e6c0;
  --green: #1eff00; --red: #fe2e2e; --border: #4a3a22;
  --text: #f0e6d2; --muted: #9d8e75; --class: var(--gold);
  --panel: #171208; --panel-2: #1f1810;
}
body[data-class="death-knight"] { --class: #c41f3b; }
body[data-class="druid"]        { --class: #ff7d0a; }
body[data-class="hunter"]       { --class: #abd473; }
body[data-class="mage"]         { --class: #69ccf0; }
body[data-class="paladin"]      { --class: #f58cba; }
body[data-class="priest"]       { --class: #ffffff; }
body[data-class="rogue"]        { --class: #fff569; }
body[data-class="shaman"]       { --class: #0070de; }
body[data-class="warlock"]      { --class: #9482c9; }
body[data-class="warrior"]      { --class: #c79c6e; }

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
.wrap { max-width: 1180px; margin: 0 auto; padding: 0 16px 64px; }

.topbar { border-bottom: 1px solid var(--border); background: rgba(0,0,0,.35); }
.topbar .wrap { padding: 14px 16px; display: flex; align-items: baseline;
                gap: 14px; flex-wrap: wrap; }
.brand { font-size: 20px; color: var(--class); letter-spacing: .5px; }
.tagline { color: var(--muted); font-size: 13px; }

.cards { display: flex; flex-wrap: wrap; gap: 10px; margin: 18px 0; }
.card { background: var(--panel); border: 1px solid var(--border);
        border-radius: 4px; padding: 10px 14px; min-width: 118px; }
.card .k { color: var(--muted); font-size: 11px; text-transform: uppercase;
           letter-spacing: .6px; }
.card .v { font-size: 20px; color: var(--parchment); }

.tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border);
        margin-top: 18px; flex-wrap: wrap; }
.tabs button {
  background: transparent; border: 1px solid transparent; border-bottom: none;
  color: var(--muted); padding: 8px 14px; cursor: pointer; font: inherit;
  border-radius: 4px 4px 0 0;
}
.tabs button[aria-selected="true"] {
  color: var(--class); border-color: var(--border);
  background: var(--panel); margin-bottom: -1px;
}
.panel { display: none; padding-top: 16px; }
.panel.active { display: block; }

.fightbar { display: flex; gap: 6px; flex-wrap: wrap; margin: 14px 0 4px; }
.fightbar button {
  background: var(--panel); border: 1px solid var(--border); color: var(--text);
  padding: 6px 12px; border-radius: 3px; cursor: pointer; font: inherit;
  font-size: 13px;
}
.fightbar button[aria-pressed="true"] {
  border-color: var(--class); color: var(--class);
}
.fightbar .kill { border-left: 3px solid var(--green); }
.fightbar .wipe { border-left: 3px solid var(--red); }
.fightbar .timeout { border-left: 3px solid var(--gold-dim); }

table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid #241c10; }
th { color: var(--muted); font-weight: normal; font-size: 11px;
     text-transform: uppercase; letter-spacing: .5px; cursor: pointer;
     white-space: nowrap; }
th.num, td.num { text-align: right; font-variant-numeric: tabular-nums; }
tbody tr:hover { background: rgba(255,209,0,.05); }
.name { display: flex; align-items: center; gap: 8px; }
.name img { width: 20px; height: 20px; border-radius: 3px;
            border: 1px solid #000; }
.noicon { width: 20px; height: 20px; border-radius: 3px;
          border: 1px solid #000; background: #2a2318; display: inline-block; }
.pet { color: var(--muted); font-size: 11px; border: 1px solid var(--border);
       border-radius: 2px; padding: 0 4px; }

/* The share bar sits *behind* the row's numbers, so relative size is readable
   without reading any of them -- WCL's single most useful visual habit. */
.bar { position: relative; }
.bar > span { position: relative; z-index: 1; }
.bar::before {
  content: ""; position: absolute; inset: 2px auto 2px 0; z-index: 0;
  width: var(--pct, 0%); background: var(--class); opacity: .16;
  border-radius: 2px;
}

.scroll { overflow-x: auto; }
.chart { width: 100%; height: 190px; display: block;
         background: var(--panel); border: 1px solid var(--border);
         border-radius: 4px; margin-bottom: 14px; }
.chart-title { color: var(--muted); font-size: 12px; margin: 0 0 4px; }
.legend { display: flex; gap: 14px; flex-wrap: wrap; font-size: 12px;
          color: var(--muted); margin-bottom: 10px; }
.legend i { display: inline-block; width: 10px; height: 10px; margin-right: 5px;
            border-radius: 2px; vertical-align: middle; }

.warn { border-left: 3px solid var(--gold); background: rgba(255,209,0,.06);
        padding: 10px 14px; margin: 14px 0; border-radius: 3px; }
.warn b { color: var(--gold); }
.err { border-left-color: var(--red); background: rgba(254,46,46,.07); }
.err b { color: var(--red); }
h2 { font-size: 15px; color: var(--class); margin: 22px 0 8px;
     font-weight: normal; letter-spacing: .4px; }
footer { color: var(--muted); font-size: 12px; margin-top: 40px;
         border-top: 1px solid var(--border); padding-top: 12px; }
"""

REPORT_JS = r"""
const RAW = JSON.parse(document.getElementById('sim-data').textContent);
const RUN = RAW.run, ICONS = RAW.icons || {};
const EF_FROM_PET = 1, EF_INCOMING = 2, EF_UNATTRIBUTED = 4;
const EF_SELF = 8, EF_CRIT = 16, EF_LOGGED = 32;

/* Event tuple layout, mirroring the emitter in SimRunner.cpp:
   [ms, spell, amount, absorb, resist, preMitigation, flags, kind, damageKind] */
const EV_MS = 0, EV_SPELL = 1, EV_AMOUNT = 2, EV_ABSORB = 3, EV_RESIST = 4,
      EV_PRE = 5, EV_FLAGS = 6, EV_KIND = 7, EV_DKIND = 8;
const EK_DAMAGE = 0, EK_HEAL = 1;
const KINDS = ['unknown', 'melee', 'spell', 'periodic'];
const POWERS = {0:'Mana',1:'Rage',2:'Focus',3:'Energy',5:'Runes',6:'Runic Power'};

let fight = -1;                      // -1 = all fights combined
const $ = (s, r) => (r || document).querySelector(s);
const $$ = (s, r) => Array.from((r || document).querySelectorAll(s));

const fmt = n => Math.round(n).toLocaleString();
const fmt1 = n => (Math.round(n * 10) / 10).toLocaleString();
const pct = n => (n * 100).toFixed(1) + '%';

function el(tag, attrs, kids) {
  const n = document.createElement(tag);
  for (const k in (attrs || {})) {
    if (k === 'style') n.setAttribute('style', attrs[k]);
    else if (k in n) n[k] = attrs[k];
    else n.setAttribute(k, attrs[k]);
  }
  (kids || []).forEach(c => n.appendChild(
    typeof c === 'string' ? document.createTextNode(c) : c));
  return n;
}

function icon(spellId) {
  const src = ICONS[spellId];
  return src ? el('img', {src, alt: '', loading: 'lazy'})
             : el('span', {className: 'noicon'});
}

/* ---------- selection ------------------------------------------------- */

function fights() { return fight < 0 ? RUN.fights : [RUN.fights[fight]]; }
function seconds() {
  return fights().reduce((a, f) => a + f.duration, 0) || 1;
}

/* Per-iteration ability rows are the compact array form emitted by
   SimRunner.cpp; the run-level table is objects. Both are folded here so the
   table code below only ever sees one shape. */
function abilityRows() {
  const acc = new Map();

  for (const f of fights()) {
    for (const r of f.abilities) {
      const [spell, pet, kind, count, attempts, damage, min, max,
             healCount, healing, overheal, crits, critDamage, logged,
             healCrits] = r;
      const key = spell + ':' + pet;
      let a = acc.get(key);
      if (!a) {
        a = {spell, pet: !!pet, kind, count: 0, attempts: 0, damage: 0,
             min: 0, max: 0, healCount: 0, healing: 0, overheal: 0,
             crits: 0, critDamage: 0, logged: 0, healCrits: 0};
        acc.set(key, a);
      }
      a.kind = kind || a.kind;
      a.count += count; a.attempts += attempts; a.damage += damage;
      a.healCount += healCount; a.healing += healing; a.overheal += overheal;
      a.crits += crits || 0; a.critDamage += critDamage || 0;
      a.logged += logged || 0; a.healCrits += healCrits || 0;
      if (min && (!a.min || min < a.min)) a.min = min;
      if (max > a.max) a.max = max;
    }
  }
  return Array.from(acc.values());
}

/* ---------- tables ---------------------------------------------------- */

function table(cols, rows, opts) {
  opts = opts || {};
  const t = el('table');
  const thead = el('thead');
  const tr = el('tr');
  cols.forEach((c, i) => {
    const th = el('th', {className: c.num ? 'num' : '', title: c.help || ''},
                 [c.label]);
    th.onclick = () => sortBy(t, i, c.num);
    tr.appendChild(th);
  });
  thead.appendChild(tr);
  t.appendChild(thead);

  const tb = el('tbody');
  rows.forEach(r => tb.appendChild(r));
  t.appendChild(tb);

  const box = el('div', {className: 'scroll'});
  box.appendChild(t);
  return box;
}

function sortBy(t, idx, numeric) {
  const tb = t.tBodies[0];
  const rows = Array.from(tb.rows);
  const dir = t.dataset.sortCol == idx && t.dataset.sortDir == 'desc' ? 1 : -1;
  rows.sort((a, b) => {
    const x = a.cells[idx], y = b.cells[idx];
    const av = numeric ? parseFloat(x.dataset.v || '0') : x.textContent.trim();
    const bv = numeric ? parseFloat(y.dataset.v || '0') : y.textContent.trim();
    return av < bv ? dir : av > bv ? -dir : 0;
  });
  rows.forEach(r => tb.appendChild(r));
  t.dataset.sortCol = idx;
  t.dataset.sortDir = dir === -1 ? 'desc' : 'asc';
}

function cell(text, opts) {
  opts = opts || {};
  const td = el('td', {className: opts.num ? 'num' : ''});
  if (opts.v !== undefined) td.dataset.v = opts.v;
  if (opts.bar !== undefined) {
    td.classList.add('bar');
    td.style.setProperty('--pct', (opts.bar * 100).toFixed(1) + '%');
    td.appendChild(el('span', {}, [text]));
  } else {
    td.textContent = text;
  }
  return td;
}

function nameCell(spell, name, pet) {
  const td = el('td');
  const box = el('div', {className: 'name'});
  box.appendChild(icon(spell));
  box.appendChild(el('span', {}, [name]));
  if (pet) box.appendChild(el('span', {className: 'pet'}, ['pet']));
  td.appendChild(box);
  return td;
}

function nameOf(spell) {
  for (const a of RUN.abilities) if (a.spell === spell) return a.name;
  for (const f of RUN.fights) {
    for (const r of f.actorUptime) if (r[0] === spell) return r[1];
    for (const r of f.targetUptime) if (r[0] === spell) return r[1];
    for (const r of f.absorb) if (r[0] === spell) return r[1];
  }
  return spell ? '#' + spell : 'melee';
}

/* ---------- panels ---------------------------------------------------- */

function renderDamage(root) {
  root.textContent = '';
  const secs = seconds();
  const rows = abilityRows().filter(a => a.damage > 0)
                            .sort((a, b) => b.damage - a.damage);
  const total = rows.reduce((a, r) => a + r.damage, 0) || 1;

  if (!rows.length) {
    root.appendChild(el('p', {className: 'muted'}, ['No damage recorded.']));
    return;
  }

  const trs = rows.map(a => {
    const tr = el('tr');
    tr.appendChild(nameCell(a.spell, nameOf(a.spell), a.pet));
    tr.appendChild(cell(KINDS[a.kind] || '?'));
    tr.appendChild(cell(fmt(a.damage), {num: true, v: a.damage,
                                        bar: a.damage / total}));
    tr.appendChild(cell(fmt(a.damage / secs), {num: true, v: a.damage / secs}));
    tr.appendChild(cell(pct(a.damage / total), {num: true,
                                                v: a.damage / total}));
    tr.appendChild(cell(fmt(a.count), {num: true, v: a.count}));
    // attempts - count is the miss/dodge/parry count, and is meaningful only
    // for melee: for spells the two are equal by construction.
    const missed = Math.max(0, a.attempts - a.count);
    tr.appendChild(cell(a.attempts ? fmt(missed) : '-', {num: true, v: missed}));
    // Out of `logged`, never out of `count`. If the combat-log decode stops
    // matching, this reads as a dash rather than as "never crits".
    const critRate = a.logged ? a.crits / a.logged : null;
    tr.appendChild(cell(critRate === null ? '-' : pct(critRate),
                        {num: true, v: critRate || 0,
                         bar: critRate === null ? undefined : critRate}));
    tr.appendChild(cell(a.count ? fmt(a.damage / a.count) : '-',
                        {num: true, v: a.count ? a.damage / a.count : 0}));
    tr.appendChild(cell(a.min ? fmt(a.min) : '-', {num: true, v: a.min}));
    tr.appendChild(cell(a.max ? fmt(a.max) : '-', {num: true, v: a.max}));
    return tr;
  });

  root.appendChild(table([
    {label: 'Ability'}, {label: 'Type'},
    {label: 'Damage', num: true}, {label: 'DPS', num: true},
    {label: 'Share', num: true}, {label: 'Hits', num: true},
    {label: 'Missed', num: true,
     help: 'Attempts that produced no damage: miss, dodge or parry. Melee only.'},
    {label: 'Crit', num: true,
     help: 'Real crits, read from the server combat log. Rate is out of the ' +
           'hits the log matched, not out of all hits.'},
    {label: 'Avg', num: true}, {label: 'Min', num: true}, {label: 'Max', num: true},
  ], trs));

  const matched = RUN.logMatched || 0, unmatched = RUN.logUnmatched || 0;
  if (unmatched && matched / Math.max(1, matched + unmatched) < 0.95) {
    root.appendChild(el('div', {className: 'warn'}, [
      el('b', {}, ['Crit data is incomplete. ']),
      `The combat log matched ${fmt(matched)} of ${fmt(matched + unmatched)} ` +
      'damage events. Crit rates are out of what matched, so they remain ' +
      'correct as rates, but they cover less than the whole fight. A packet ' +
      'layout that changed upstream is the usual cause.'
    ]));
  }
  root.appendChild(unattributedNote());
}

function unattributedNote() {
  const box = el('div', {});
  if (!RUN.unattributed) return box;

  const share = RUN.unattributed / (RUN.damage || 1);
  const by = RUN.unattributedByType || {};
  const parts = Object.keys(by).filter(k => by[k] > 0)
                      .map(k => `${k} ${fmt(by[k])}`).join(', ');
  const miss = RUN.latchMiss || {};

  // The known cause, named rather than left as a mystery. A damage shield
  // (Thorns, Retribution Aura, Lightning Shield's passive half) is dealt at
  // Unit.cpp:2218, which reaches DealDamage without ever calling
  // CalculateSpellDamageTaken -- the one hook that carries a spell id. There is
  // no hook on that path, so the damage is real, counted, and unnameable.
  const shieldLikely = (by.spell || 0) === RUN.unattributed &&
                       !(miss.attacker_mismatch || 0);

  box.appendChild(el('div', {className: 'warn'}, [
    el('b', {}, [`${pct(share)} of damage is unattributed. `]),
    `${fmt(RUN.unattributed)} damage reached the target without the hook that ` +
    `names the spell, so it is counted in the totals but cannot be split by ` +
    `ability. By type: ${parts || 'none'}. `,
    shieldLikely
      ? 'All of it is spell damage with no hook at all, which is the damage ' +
        'shield signature: Thorns and its kin are dealt on a core path that ' +
        'never calls CalculateSpellDamageTaken, and no hook exists there. ' +
        'If this actor has a damage shield up, this is it.'
      : `${fmt(miss.attacker_mismatch || 0)} event(s) had a latch naming a ` +
        `different attacker, ${fmt(miss.no_latch || 0)} had none at all.`
  ]));
  return box;
}

function renderHealing(root) {
  root.textContent = '';
  const secs = seconds();
  const rows = abilityRows().filter(a => a.healing > 0 || a.overheal > 0)
                            .sort((a, b) => b.healing - a.healing);

  if (!rows.length) {
    root.appendChild(el('p', {className: 'muted'},
      ['No healing recorded for this actor.']));
    return;
  }

  const total = rows.reduce((a, r) => a + r.healing, 0) || 1;
  const trs = rows.map(a => {
    const raw = a.healing + a.overheal;
    const tr = el('tr');
    tr.appendChild(nameCell(a.spell, nameOf(a.spell), a.pet));
    tr.appendChild(cell(fmt(a.healing), {num: true, v: a.healing,
                                         bar: a.healing / total}));
    tr.appendChild(cell(fmt(a.healing / secs), {num: true,
                                                v: a.healing / secs}));
    tr.appendChild(cell(pct(a.healing / total), {num: true,
                                                 v: a.healing / total}));
    tr.appendChild(cell(fmt(a.overheal), {num: true, v: a.overheal}));
    tr.appendChild(cell(raw ? pct(a.overheal / raw) : '-',
                        {num: true, v: raw ? a.overheal / raw : 0}));
    tr.appendChild(cell(fmt(a.healCount), {num: true, v: a.healCount}));
    const cr = a.healCount ? a.healCrits / a.healCount : 0;
    tr.appendChild(cell(a.healCount ? pct(cr) : '-', {num: true, v: cr}));
    return tr;
  });

  root.appendChild(table([
    {label: 'Ability'}, {label: 'Effective', num: true},
    {label: 'HPS', num: true}, {label: 'Share', num: true},
    {label: 'Overheal', num: true},
    {label: 'Overheal %', num: true,
     help: 'Healing that restored nothing because the target was already full.'},
    {label: 'Casts', num: true},
    {label: 'Crit', num: true, help: 'From the combat log.'},
  ], trs));

  const heal = fights().reduce((a, f) => a + f.healing, 0);
  const over = fights().reduce((a, f) => a + f.overheal, 0);
  if (over > heal) {
    root.appendChild(el('div', {className: 'warn'}, [
      el('b', {}, ['More healing was wasted than landed. ']),
      `${pct(over / (heal + over))} of this actor's healing was overheal. ` +
      'For a solo spec that is not automatically wrong -- a healer with nothing ' +
      'to heal will top itself off -- but it does mean the sustain shown here ' +
      'is not being tested by the fight.'
    ]));
  }
}

function renderTaken(root) {
  root.textContent = '';
  const secs = seconds();
  let total = 0, n = 0;

  for (const f of fights()) {
    for (const e of f.events) {
      if (!(e[EV_FLAGS] & EF_INCOMING)) continue;
      total += e[EV_AMOUNT]; n++;
    }
  }

  // Exact, from the combat log, not sampled from the shield's own amount.
  const absorbed = fights().reduce((a, f) => a + (f.absorbedOnActor || 0), 0);
  const resisted = fights().reduce((a, f) => a + (f.resistedOnActor || 0), 0);
  const gross = total + absorbed + resisted;

  const cards = el('div', {className: 'cards'});
  cards.appendChild(statCard('Reached health', fmt(total)));
  cards.appendChild(statCard('Absorbed', fmt(absorbed)));
  cards.appendChild(statCard('Resisted', fmt(resisted)));
  cards.appendChild(statCard('Thrown at you', fmt(gross)));
  cards.appendChild(statCard('Mitigated', gross ? pct((gross - total) / gross) : '-'));
  cards.appendChild(statCard('Per second', fmt(total / secs)));
  cards.appendChild(statCard('Events', fmt(n)));
  cards.appendChild(statCard('Of health bar',
    RUN.maxHealth ? pct(gross / (RUN.maxHealth * fights().length)) : '-'));
  root.appendChild(cards);

  if (absorbed > total) {
    root.appendChild(el('div', {className: 'warn'}, [
      el('b', {}, ['Most of the incoming damage never reached the health bar. ']),
      `${pct(absorbed / Math.max(1, gross))} of it was absorbed. A spec like ` +
      'this looks untouched if you read damage taken alone, because the core ' +
      'reports damage to the OnDamage hook *after* absorption has already ' +
      'reduced it. "Thrown at you" above is the number the encounter actually ' +
      'produced.'
    ]));
  }

  // The absorb ledger, which is the only honest answer to "did the shield do
  // anything". It is measured at the shield, not at the damage event.
  const shields = new Map();
  for (const f of fights()) {
    for (const r of f.absorb) {
      const [spell, name, absorbed, apps, consumed, expired] = r;
      const s = shields.get(spell) ||
                {name, absorbed: 0, apps: 0, consumed: 0, expired: 0};
      s.absorbed += absorbed; s.apps += apps;
      s.consumed += consumed; s.expired += expired;
      shields.set(spell, s);
    }
  }

  root.appendChild(el('h2', {}, ['Absorb, per shield']));
  if (!shields.size) {
    root.appendChild(el('p', {className: 'muted'}, [
      'No absorb shield was active on this actor.']));
  } else {
    const maxAbs = Math.max(...Array.from(shields.values(), s => s.absorbed)) || 1;
    const trs = Array.from(shields.entries())
      .sort((a, b) => b[1].absorbed - a[1].absorbed)
      .map(([spell, s]) => {
        const tr = el('tr');
        tr.appendChild(nameCell(spell, s.name, false));
        tr.appendChild(cell(fmt(s.absorbed), {num: true, v: s.absorbed,
                                              bar: s.absorbed / maxAbs}));
        tr.appendChild(cell(fmt(s.apps), {num: true, v: s.apps}));
        tr.appendChild(cell(fmt(s.consumed), {num: true, v: s.consumed}));
        tr.appendChild(cell(fmt(s.expired), {num: true, v: s.expired}));
        tr.appendChild(cell(s.apps ? fmt(s.absorbed / s.apps) : '-',
                            {num: true, v: s.apps ? s.absorbed / s.apps : 0}));
        return tr;
      });

    root.appendChild(table([
      {label: 'Shield'}, {label: 'Absorbed', num: true},
      {label: 'Casts', num: true},
      {label: 'Consumed', num: true,
       help: 'Dropped at zero: the shield was the right size or too small.'},
      {label: 'Expired full', num: true,
       help: 'Dropped with shield left: overcast for this fight.'},
      {label: 'Per cast', num: true},
    ], trs));

    // Two independent measurements of the same quantity. The per-shield figures
    // come from watching each absorb aura's own amount fall between samples;
    // the total above comes from the combat log. They should agree, and a gap
    // wider than one sample interval means one of them is wrong.
    const ledger = Array.from(shields.values())
                        .reduce((a, s) => a + s.absorbed, 0);
    const gap = Math.abs(ledger - absorbed) / Math.max(1, absorbed);
    if (gap > 0.05) {
      root.appendChild(el('div', {className: 'warn'}, [
        el('b', {}, ['The two absorb measurements disagree. ']),
        `Per-shield sampling totals ${fmt(ledger)}, the combat log totals ` +
        `${fmt(absorbed)} (${pct(gap)} apart). These are independent methods, ` +
        'so trust the combat-log figure and treat the split by shield as ' +
        'indicative. A shield consumed entirely between two samples is the ' +
        'usual cause.'
      ]));
    }
  }
}

function statCard(k, v) {
  return el('div', {className: 'card'}, [
    el('div', {className: 'k'}, [k]), el('div', {className: 'v'}, [String(v)])]);
}

function renderAuras(root) {
  root.textContent = '';

  for (const [label, key, who] of [['Your buffs', 'actorUptime', 'actor'],
                                   ['Target debuffs', 'targetUptime', 'target']]) {
    const acc = new Map();
    let samples = 0;

    for (const f of fights()) {
      samples += f.auraSamples;
      for (const r of f[key]) {
        const [spell, name, present, apps, meanStacks, maxStacks, first, last] = r;
        const a = acc.get(spell) ||
                  {name, present: 0, apps: 0, stackSum: 0, max: 0};
        a.present += present; a.apps += apps;
        a.stackSum += meanStacks * present;
        a.max = Math.max(a.max, maxStacks);
        acc.set(spell, a);
      }
    }

    root.appendChild(el('h2', {}, [label]));
    if (!acc.size) {
      root.appendChild(el('p', {className: 'muted'},
        ['Nothing tracked. Permanent passives are filtered out by design.']));
      continue;
    }

    const trs = Array.from(acc.entries())
      .sort((a, b) => b[1].present - a[1].present)
      .map(([spell, a]) => {
        const up = samples ? a.present / samples : 0;
        const tr = el('tr');
        tr.appendChild(nameCell(spell, a.name, false));
        tr.appendChild(cell(pct(up), {num: true, v: up, bar: Math.min(1, up)}));
        tr.appendChild(cell(fmt(a.apps), {num: true, v: a.apps}));
        tr.appendChild(cell(a.present ? fmt1(a.stackSum / a.present) : '-',
                            {num: true, v: a.present ? a.stackSum / a.present : 0}));
        tr.appendChild(cell(fmt(a.max), {num: true, v: a.max}));
        return tr;
      });

    root.appendChild(table([
      {label: who === 'actor' ? 'Buff' : 'Debuff'},
      {label: 'Uptime', num: true},
      {label: 'Applications', num: true,
       help: 'Rising edges. 100% uptime with 3 applications is a long buff; ' +
             '40% with 60 is a rotation spamming it.'},
      {label: 'Mean stacks', num: true}, {label: 'Max stacks', num: true},
    ], trs));
  }

  root.appendChild(el('div', {className: 'warn'}, [
    el('b', {}, [`Sampled every ${RUN.auraSampleMs}ms. `]),
    'Uptime is therefore quantised, not exact -- there is no hook for a stack ' +
    'decrement, so polling is the only way to see stacks fall at all. ' +
    'Permanent passive auras are excluded: they are 100% by construction and ' +
    'say nothing about whether a button was pressed. The end-of-fight snapshot ' +
    'still lists every aura.'
  ]));
}

/* ---------- charts ---------------------------------------------------- */

function svg(tag, attrs) {
  const n = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const k in (attrs || {})) n.setAttribute(k, attrs[k]);
  return n;
}

function chart(title, series, opts) {
  opts = opts || {};
  const W = 1000, H = 190, PAD = 30;
  const box = el('div', {});
  box.appendChild(el('p', {className: 'chart-title'}, [title]));

  const s = svg('svg', {class: 'chart', viewBox: `0 0 ${W} ${H}`,
                        preserveAspectRatio: 'none'});

  const maxX = opts.maxX || 1;
  const maxY = Math.max(1, ...series.flatMap(ser => ser.points.map(p => p[1])));

  for (let i = 0; i <= 4; i++) {
    const y = PAD + (H - PAD * 2) * i / 4;
    s.appendChild(svg('line', {x1: PAD, y1: y, x2: W - 4, y2: y,
                               stroke: '#241c10', 'stroke-width': 1}));
    const lab = svg('text', {x: 2, y: y + 3, fill: '#9d8e75', 'font-size': 9});
    lab.textContent = opts.fmtY ? opts.fmtY(maxY * (1 - i / 4))
                                : fmt(maxY * (1 - i / 4));
    s.appendChild(lab);
  }

  const X = t => PAD + (W - PAD - 4) * (t / maxX);
  const Y = v => PAD + (H - PAD * 2) * (1 - v / maxY);

  for (const ser of series) {
    if (!ser.points.length) continue;
    const d = ser.points.map((p, i) =>
      `${i ? 'L' : 'M'}${X(p[0]).toFixed(1)},${Y(p[1]).toFixed(1)}`).join('');
    s.appendChild(svg('path', {d, fill: 'none', stroke: ser.colour,
                               'stroke-width': ser.width || 1.5,
                               'stroke-linejoin': 'round'}));
  }

  for (const m of (opts.marks || [])) {
    s.appendChild(svg('line', {x1: X(m.t), y1: PAD - 6, x2: X(m.t), y2: H - PAD,
                               stroke: m.colour, 'stroke-width': 1,
                               'stroke-dasharray': '3 3'}));
    const lab = svg('text', {x: X(m.t) + 3, y: PAD - 8, fill: m.colour,
                             'font-size': 9});
    lab.textContent = m.label;
    s.appendChild(lab);
  }

  box.appendChild(s);
  return box;
}

function legend(items) {
  const l = el('div', {className: 'legend'});
  items.forEach(([colour, label]) => {
    const span = el('span', {});
    span.appendChild(el('i', {style: `background:${colour}`}));
    span.appendChild(document.createTextNode(label));
    l.appendChild(span);
  });
  return l;
}

/* One bucket per second. Finer than that is noise at these fight lengths, and
   coarser hides the opener, which is exactly what a burst pass is about. */
function bucketed(events, seconds, pick) {
  const out = new Array(Math.max(1, Math.ceil(seconds))).fill(0);
  for (const e of events) {
    const v = pick(e);
    if (!v) continue;
    const i = Math.min(out.length - 1, Math.floor(e[EV_MS] / 1000));
    out[i] += v;
  }
  return out.map((v, i) => [i, v]);
}

function renderGraphs(root) {
  root.textContent = '';
  const sel = fights();

  if (sel.length !== 1) {
    root.appendChild(el('div', {className: 'warn'}, [
      el('b', {}, ['Pick a single fight. ']),
      'Fights have different lengths and outcomes, so overlaying their ' +
      'timelines would average away the thing a timeline is for.'
    ]));
    return;
  }

  const f = sel[0];
  const secs = Math.max(1, f.duration);

  const outgoing = f.events.filter(
    e => !(e[EV_FLAGS] & EF_INCOMING) && e[EV_KIND] === EK_DAMAGE);
  const incoming = f.events.filter(e => (e[EV_FLAGS] & EF_INCOMING));
  const heals = f.events.filter(e => e[EV_KIND] === EK_HEAL);

  const marks = f.deaths.map(([ms, role]) => ({
    t: ms / 1000,
    label: ['actor died', 'target died', 'pet died'][role] || 'death',
    colour: role === 1 ? '#1eff00' : '#fe2e2e',
  }));

  root.appendChild(legend([['#ffd100', 'damage done'],
                           ['#fe2e2e', 'damage taken (reached health)'],
                           ['#c79c6e', 'absorbed'],
                           ['#1eff00', 'healing done']]));
  root.appendChild(chart('Damage and healing per second', [
    {points: bucketed(outgoing, secs, e => e[EV_AMOUNT]), colour: '#ffd100'},
    {points: bucketed(incoming, secs, e => e[EV_AMOUNT]), colour: '#fe2e2e'},
    {points: bucketed(incoming, secs, e => e[EV_ABSORB]), colour: '#c79c6e'},
    {points: bucketed(heals, secs, e => e[EV_AMOUNT]), colour: '#1eff00'},
  ], {maxX: secs, marks}));

  if (f.resources.length) {
    const powerName = POWERS[f.resources[0][4]] || 'Power';
    const maxHp = RUN.maxHealth || 1;
    const maxPower = Math.max(1, ...f.resources.map(r => r[2]));
    const maxTargetHp = Math.max(1, ...f.resources.map(r => r[3]));

    root.appendChild(legend([['#69ccf0', 'your health'],
                             ['#9482c9', 'your ' + powerName.toLowerCase()],
                             ['#c79c6e', 'target health']]));
    root.appendChild(chart('Health and ' + powerName.toLowerCase() + ' (%)', [
      {points: f.resources.map(r => [r[0] / 1000, 100 * r[1] / maxHp]),
       colour: '#69ccf0'},
      {points: f.resources.map(r => [r[0] / 1000, 100 * r[2] / maxPower]),
       colour: '#9482c9'},
      {points: f.resources.map(r => [r[0] / 1000, 100 * r[3] / maxTargetHp]),
       colour: '#c79c6e'},
    ], {maxX: secs, marks, fmtY: v => Math.round(v) + '%'}));
  }

  const stackIds = Object.keys(f.auraStacks || {});
  if (stackIds.length) {
    root.appendChild(el('h2', {}, ['Proc stacks']));
    root.appendChild(legend(stackIds.map((id, i) =>
      [STACK_COLOURS[i % STACK_COLOURS.length], nameOf(+id)])));
    root.appendChild(chart('Stacks over time', stackIds.map((id, i) => ({
      points: stepPoints(f.auraStacks[id], secs),
      colour: STACK_COLOURS[i % STACK_COLOURS.length],
    })), {maxX: secs, marks, fmtY: v => Math.round(v)}));
  }
}

const STACK_COLOURS = ['#ffd100', '#69ccf0', '#1eff00', '#f58cba',
                       '#ff7d0a', '#9482c9', '#abd473', '#c41f3b'];

/* The series is change-only, so it has to be drawn as a step function or it
   implies a smooth ramp the stacks never did. */
function stepPoints(series, secs) {
  const pts = [];
  let prev = 0;
  for (const [ms, stacks] of series) {
    const t = ms / 1000;
    pts.push([t, prev]);
    pts.push([t, stacks]);
    prev = stacks;
  }
  pts.push([secs, prev]);
  return pts;
}

function renderSummary(root) {
  root.textContent = '';
  const secs = seconds();
  const sel = fights();
  const dmg = sel.reduce((a, f) => a + f.damage, 0);
  const heal = sel.reduce((a, f) => a + f.healing, 0);
  const taken = sel.reduce((a, f) => a + f.taken, 0);
  const kills = sel.filter(f => f.outcome === 'target_died').length;
  const deaths = sel.filter(f => f.outcome === 'actor_died').length;

  const cards = el('div', {className: 'cards'});
  cards.appendChild(statCard('DPS', fmt(dmg / secs)));
  cards.appendChild(statCard('HPS', fmt(heal / secs)));
  cards.appendChild(statCard('DTPS', fmt(taken / secs)));
  cards.appendChild(statCard('Fight time', fmt1(secs) + 's'));
  cards.appendChild(statCard('Kills', `${kills}/${sel.length}`));
  cards.appendChild(statCard('Deaths', String(deaths)));
  cards.appendChild(statCard('Item level', RUN.ilvl));
  cards.appendChild(statCard('Spell power', RUN.spellPower));
  cards.appendChild(statCard('Attack power', RUN.attackPower));
  cards.appendChild(statCard('Talents', RUN.talentTabs.join('/')));
  root.appendChild(cards);

  const problems = [];
  if (RUN.gearFailed)
    problems.push(`${RUN.gearFailed} gear slot(s) failed to equip, so these ` +
                  `numbers are for a worse-geared character than intended.`);
  if (RUN.uncastable)
    problems.push(`${RUN.uncastable} known spell(s) could not be cast. The ` +
                  `damage below is a floor, not a result.`);
  if (RUN.latchOverflow)
    problems.push(`The attribution ring overflowed ${fmt(RUN.latchOverflow)} ` +
                  `time(s); some damage may be filed under the wrong ability.`);
  if (sel.some(f => f.eventsDropped))
    problems.push('The event cap was hit, so the timelines are truncated.');
  if (!RUN.ok)
    problems.push(`The run did not complete cleanly: ${RUN.note}`);

  if (problems.length) {
    const box = el('div', {className: 'warn err'});
    box.appendChild(el('b', {}, ['Read these numbers with care. ']));
    box.appendChild(el('ul', {}, problems.map(p => el('li', {}, [p]))));
    root.appendChild(box);
  }

  root.appendChild(el('h2', {}, ['Fights']));
  const trs = RUN.fights.map(f => {
    const tr = el('tr');
    tr.appendChild(cell('#' + (f.i + 1)));
    tr.appendChild(cell(f.outcome.replace('_', ' ')));
    tr.appendChild(cell(fmt1(f.duration) + 's', {num: true, v: f.duration}));
    tr.appendChild(cell(fmt(f.dps), {num: true, v: f.dps}));
    tr.appendChild(cell(fmt(f.damage), {num: true, v: f.damage}));
    tr.appendChild(cell(fmt(f.healing), {num: true, v: f.healing}));
    tr.appendChild(cell(fmt(f.taken), {num: true, v: f.taken}));
    tr.appendChild(cell(f.actorHp + '%', {num: true, v: f.actorHp}));
    return tr;
  });
  root.appendChild(table([
    {label: 'Fight'}, {label: 'Outcome'}, {label: 'Length', num: true},
    {label: 'DPS', num: true}, {label: 'Damage', num: true},
    {label: 'Healing', num: true}, {label: 'Taken', num: true},
    {label: 'HP left', num: true},
  ], trs));
}

/* ---------- shell ----------------------------------------------------- */

const PANELS = {
  summary: renderSummary, damage: renderDamage, healing: renderHealing,
  taken: renderTaken, auras: renderAuras, graphs: renderGraphs,
};

function draw() {
  const active = $('.tabs button[aria-selected="true"]').dataset.panel;
  PANELS[active]($('#panel-' + active));
}

function init() {
  document.body.dataset.class = RUN.classSlug || '';
  $('#brand').textContent = `${RUN.character} - ${RUN.spec}`;
  $('#tagline').textContent =
    `level ${RUN.level} - ilvl ${RUN.ilvl} - ${RUN.fights.length} fight(s) - ` +
    `${fmt1(RUN.duration)}s simulated in ${fmt1(RUN.wall)}s wall ` +
    `(${fmt1(RUN.realtime)}x realtime)`;

  const bar = $('#fights');
  const mk = (label, idx, cls) => {
    const b = el('button', {className: cls || ''}, [label]);
    b.setAttribute('aria-pressed', String(idx === fight));
    b.onclick = () => {
      fight = idx;
      $$('#fights button').forEach(x => x.setAttribute('aria-pressed', 'false'));
      b.setAttribute('aria-pressed', 'true');
      draw();
    };
    bar.appendChild(b);
  };

  mk('All fights', -1);
  RUN.fights.forEach((f, i) => mk(
    `#${i + 1} - ${fmt1(f.duration)}s`, i,
    f.outcome === 'target_died' ? 'kill'
      : f.outcome === 'actor_died' ? 'wipe' : 'timeout'));

  $$('.tabs button').forEach(b => {
    b.onclick = () => {
      $$('.tabs button').forEach(x => x.setAttribute('aria-selected', 'false'));
      $$('.panel').forEach(p => p.classList.remove('active'));
      b.setAttribute('aria-selected', 'true');
      $('#panel-' + b.dataset.panel).classList.add('active');
      draw();
    };
  });

  draw();
}

init();
"""

REPORT_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__ - Alonecraft sim report</title>
<style>__CSS__</style>
</head>
<body data-class="__CLASS__">
<div class="topbar"><div class="wrap">
  <span class="brand" id="brand"></span>
  <span class="tagline" id="tagline"></span>
</div></div>

<div class="wrap">
  <div class="fightbar" id="fights"></div>

  <div class="tabs" role="tablist">
    <button data-panel="summary" aria-selected="true">Summary</button>
    <button data-panel="damage" aria-selected="false">Damage done</button>
    <button data-panel="healing" aria-selected="false">Healing</button>
    <button data-panel="taken" aria-selected="false">Damage taken</button>
    <button data-panel="auras" aria-selected="false">Buffs</button>
    <button data-panel="graphs" aria-selected="false">Graphs</button>
  </div>

  <div class="panel active" id="panel-summary"></div>
  <div class="panel" id="panel-damage"></div>
  <div class="panel" id="panel-healing"></div>
  <div class="panel" id="panel-taken"></div>
  <div class="panel" id="panel-auras"></div>
  <div class="panel" id="panel-graphs"></div>

  <footer>
    Generated by <code>tools/sim_report.py</code> from a worldserver simulator
    run. Not raid DPS: one target, no raid buffs, no movement, a bot rotation.
    Every view here exists to show a mechanism, not to rank a spec.
  </footer>
</div>

<script type="application/json" id="sim-data">__DATA__</script>
<script>__JS__</script>
</body>
</html>
"""

INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Alonecraft sim reports</title>
<style>__CSS__</style>
</head>
<body>
<div class="topbar"><div class="wrap">
  <span class="brand">Alonecraft sim reports</span>
  <span class="tagline">__COUNT__ report(s), newest first</span>
</div></div>
<div class="wrap">
  <table>
    <thead><tr>
      <th>Run</th><th>Spec</th><th class="num">DPS</th>
      <th class="num">Simulated</th><th class="num">Fights</th><th>When</th>
    </tr></thead>
    <tbody>__ROWS__</tbody>
  </table>
  <footer>
    Rebuild with <code>python tools/sim_report.py --index</code>.
  </footer>
</div>
</body>
</html>
"""


# ---------------------------------------------------------------------------
#  Driver
# ---------------------------------------------------------------------------

def build_index():
    """Every report already on disk, newest first."""
    entries = []

    for html in RUNS.rglob("*.report.html"):
        # matrix.report.html is the comparative page for a whole run, indexed
        # separately in sims/matrix.html. Its sibling matrix.json is a different
        # shape entirely, so letting it through adds a row reading "? / 0 DPS".
        if html.name == "matrix.report.html":
            continue

        result = html.with_name(html.name[:-len(".report.html")] + ".json")
        if not result.is_file():
            continue

        try:
            data = json.load(open(result, encoding="utf-8"))
        except Exception:
            continue

        entries.append({
            "href": os.path.relpath(html, SIMS).replace("\\", "/"),
            "name": html.parent.name + "/" + html.name[:-len(".report.html")],
            "spec": data.get("spec", "?"),
            "dps": data.get("dps", 0.0),
            "duration": data.get("duration_s", 0.0),
            "fights": len(data.get("iterations", [])),
            "when": time.strftime("%Y-%m-%d %H:%M",
                                  time.localtime(html.stat().st_mtime)),
        })

    entries.sort(key=lambda e: e["when"], reverse=True)
    return render_index(entries, SIMS / "index.html")


def main() -> int:
    p = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("path", nargs="?",
                   help="a result JSON, or a matrix directory of them")
    p.add_argument("--index", action="store_true",
                   help="rebuild sims/index.html from the reports on disk")
    p.add_argument("--no-icons", action="store_true",
                   help="skip the DBC read; renders with placeholder icons")
    args = p.parse_args()

    if not args.path and not args.index:
        p.error("give a path, or --index")

    print("=" * 72)
    print("  Alonecraft Simulator Report")
    print("=" * 72)
    print()

    written = []

    if args.path:
        results = find_results(Path(args.path))
        if not results:
            print(f"  no result files under {args.path}")
            return 1

        print("-" * 72)
        print(f"  Rendering {len(results)} report(s)")
        print("-" * 72)

        for path in results:
            data = summarise(load_result(path), path)
            icons, missing = inline_icons(spell_ids_in(data),
                                          enabled=not args.no_icons)

            out = path.with_name(path.name[:-len(".json")] + ".report.html")
            render_report(data, icons, out)
            written.append(out)

            print(f"  {path.stem:<34} {len(data['fights'])} fight(s), "
                  f"{data['dps']:>9,.0f} DPS  ->  {out.name}")

            if missing:
                print(f"    {len(missing)} icon(s) not extracted yet: "
                      f"{', '.join(missing[:4])}"
                      f"{' ...' if len(missing) > 4 else ''}")
                print("    python tools/extract_icons.py   # to add them")

        print()

    index = build_index()
    print("-" * 72)
    print("  Index")
    print("-" * 72)
    print(f"  {index}")
    print()

    if written:
        print(f"  Open: {written[0]}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
