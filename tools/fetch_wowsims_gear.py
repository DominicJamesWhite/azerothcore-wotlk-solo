#!/usr/bin/env python3
"""Import tier-7 gear sets from wowsims/wotlk into sims/gear/.

    python tools/fetch_wowsims_gear.py            # download and validate
    python tools/fetch_wowsims_gear.py --check    # validate what is committed

Why import rather than generate
-------------------------------
A balance matrix needs every spec in gear of the same quality, chosen the way a
player would choose it. Generating that from item_template means writing a stat
weighting per spec -- which is exactly the thing under test, so the gear would
inherit whatever bias the tuning has. wowsims' lists are maintained by people
who play the spec, are already per-spec, and are a fixed external reference: if
Alonecraft's numbers move, the gear does not move with them.

The files are committed. The build machine is the only place with the database,
and a run that silently downloaded different gear than last time would report a
balance change that was really a gear change.

Format
------
wowsims stores `{"items": [{"id": 40562, "enchant": 3820, "gems": [41285, 39998]}, ...]}`
with slots implied by position. Nothing here depends on the position: the server
resolves each item's slot from its own item_template, so a reordered or partial
list still equips correctly. Enchant ids are SpellItemEnchantment ids and gems
are gem item ids -- both are what the server wants, untranslated.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sim_specs import SPECS  # noqa: E402

REPO = Path(__file__).resolve().parent.parent
GEAR_DIR = REPO / "sims" / "gear"
RAW = "https://raw.githubusercontent.com/wowsims/wotlk/master/{}"


def fetch(path: str) -> dict:
    with urllib.request.urlopen(RAW.format(path), timeout=30) as r:
        return json.loads(r.read().decode())


def item_levels(entries: list[int]) -> dict[int, tuple[int, str]]:
    """ItemLevel and name per entry, straight from the live world database.

    This is the validation that matters: an id wowsims knows and Alonecraft's
    item_template does not would be dropped at equip time, and the spec would be
    compared to the others while wearing one fewer piece.
    """
    if not entries:
        return {}

    ids = ",".join(str(e) for e in entries)
    out = subprocess.run(
        ["mysql", "-h", "127.0.0.1", "-u", "acore", "-pacore", "acore_world", "-N", "-B",
         "-e", f"SELECT entry, ItemLevel, name FROM item_template WHERE entry IN ({ids});"],
        capture_output=True, text=True)

    found = {}
    for line in out.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            found[int(parts[0])] = (int(parts[1]), parts[2])
    return found


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true",
                   help="validate the committed files instead of downloading")
    args = p.parse_args()

    GEAR_DIR.mkdir(parents=True, exist_ok=True)
    problems = 0

    for spec in SPECS:
        path = GEAR_DIR / f"{spec['key']}.json"

        if args.check:
            if not path.exists():
                print(f"{spec['key']:<16} MISSING {path}")
                problems += 1
                continue
            data = json.loads(path.read_text())
        else:
            try:
                data = fetch(spec["wowsims"])
            except Exception as exc:                      # noqa: BLE001
                print(f"{spec['key']:<16} download failed: {exc}")
                problems += 1
                continue
            # wowsims keeps positional slots, so an unused one -- an off-hand
            # under a two-hander, a relic a spec does not use -- is an empty
            # object. Slots are resolved server-side from item_template, so the
            # position carries nothing and the blanks are simply dropped.
            data = {
                "spec": spec["key"],
                "source": RAW.format(spec["wowsims"]),
                "items": [i for i in data["items"] if i.get("id")],
            }
            path.write_text(json.dumps(data, indent=2) + "\n")

        items = data["items"]
        levels = item_levels([i["id"] for i in items])
        missing = [i["id"] for i in items if i["id"] not in levels]
        known = [levels[i["id"]][0] for i in items if i["id"] in levels]
        mean = sum(known) / len(known) if known else 0

        note = ""
        if missing:
            note = f"  MISSING FROM item_template: {missing}"
            problems += 1

        print(f"{spec['key']:<16} {len(items):>2} items  mean ilvl {mean:6.1f}{note}")

    if problems:
        print(f"\n{problems} problem(s).", file=sys.stderr)
    return 1 if problems else 0


def load(key: str) -> list[dict]:
    """The item list for a spec, for sim.py."""
    return json.loads((GEAR_DIR / f"{key}.json").read_text())["items"]


def to_arg(items: list[dict]) -> str:
    """Compact form the server parses: item[:enchant[:gem,gem,gem]];..."""
    out = []
    for it in items:
        gems = ",".join(str(g) for g in it.get("gems", []))
        enchant = it.get("enchant", 0)
        if gems:
            out.append(f"{it['id']}:{enchant}:{gems}")
        elif enchant:
            out.append(f"{it['id']}:{enchant}")
        else:
            out.append(str(it["id"]))
    return ";".join(out)


if __name__ == "__main__":
    sys.exit(main())
