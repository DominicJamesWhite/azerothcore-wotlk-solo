#!/usr/bin/env python3
"""
Mount Price Generator

Restores riding skill training and gold-priced mount items to their retail
values, undoing the 10x cut that used to live here.

Why the cut existed, and why it is gone: XP runs at 10x, so a character used to
arrive at level 40 with roughly a tenth of the gold retail assumed they would
have, and the riding gates (50g, 250g, 5000g) landed as walls that never
existed in the original game.  Dividing every mount price by 10 fixed that.
Then the *income* side was fixed too -- `Rate.RewardQuestMoney = 8` in
worldserver.overrides.conf -- and the two compensations stack: gold per level
is back near the retail ratio while mounts still cost a tenth of retail.  One
correction for one problem, so the price cut is the one that goes.

`Rate.RewardQuestMoney` is the better half of the pair to keep: it is a single
config key that scales with the whole levelling curve, whereas the price cut
was 242 hardcoded rows that had to be regenerated whenever the world DB moved,
and it silently disagreed with every wiki, guide and player expectation about
what a mount costs.

Where the retail numbers come from: `data/sql/base/db_world/`, the world DB dump
this fork is built on -- not the live database, which still holds the cut values,
and not the previous version of these SQL files, which would make the generator
unable to run twice.  The dump is queried with the same predicates the cut used,
so it reproduces exactly the same row set.

That equivalence was proved rather than assumed: before this revert was written,
all 242 rows were cross-checked and floor(retail / 10) matched the cut value the
module SQL carried in every single case.  ROW_COUNTS below pins the counts so a
world DB that gains or loses a mount is a loud failure, not a silent partial
revert.

Scope notes (unchanged from the cut this reverts, since it must cover exactly
the same rows):

  * Riding is `trainer_spell.ReqSkillLine = 762`, which also picks up the druid
    Swift Flight Form (40120) -- a riding cost like any other.  `npc_trainer` is
    untouched: it is legacy and no C++ in src/ reads it.
  * Mount items are `item_template.class = 15 AND subclass = 5` with
    BuyPrice > 0.  SellPrice is restored alongside BuyPrice, because the cut
    scaled both to keep the buy/sell ratio intact; restoring BuyPrice alone
    would leave 131 mounts vendoring for 2.5x their cost.
  * The 19 priced mounts that also sit on an ExtendedCost vendor are emitted
    anyway but are no-ops in practice: CreatureData.h::IsGoldRequired makes the
    core ignore BuyPrice when ExtendedCost is set.
  * Player::GetReputationPriceDiscount still applies up to 20% at Exalted.
    Unchanged and intended, exactly as at retail.

Usage:
    python tools/gen_mount_prices.py            # write both SQL files
    python tools/gen_mount_prices.py --dry-run  # verify only, write nothing
    python tools/gen_mount_prices.py --stdout   # print SQL
"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BASE_SQL = os.path.join(REPO_ROOT, "data", "sql", "base", "db_world")
MODULE_SQL = os.path.join(
    REPO_ROOT, "modules", "world_of_alonecraft", "data", "sql", "db-world"
)

RIDING_SKILL_LINE = 762
ITEM_CLASS_MISC = 15
ITEM_SUBCLASS_MOUNT = 5

# The row set the 10x cut covered, and therefore the row set this revert must
# cover.  A mismatch means the base dump moved under us; fail rather than write
# a partial revert that leaves some mounts at a tenth of their price.
ROW_COUNTS = {"riding": 6, "mounts": 236}

RIDING_SQL = "woa_2026_08_07_00.sql"
MOUNT_SQL = "woa_2026_08_07_01.sql"

GOLD = 10000

RIDING_NAMES = {
    33388: "Apprentice Riding",
    33391: "Journeyman Riding",
    34090: "Expert Riding",
    34091: "Artisan Riding",
    54197: "Cold Weather Flying",
    40120: "Swift Flight Form",
}


# --------------------------------------------------------------------------
# mysqldump parsing
# --------------------------------------------------------------------------

def _split_row(row):
    """Split one `(...)` VALUES tuple into fields, respecting quoted strings."""
    out, cur, i, n = [], [], 0, len(row)
    while i < n:
        c = row[i]
        if c == "'":
            cur.append(c)
            i += 1
            while i < n:
                if row[i] == "\\":
                    cur.append(row[i:i + 2])
                    i += 2
                    continue
                cur.append(row[i])
                if row[i] == "'":
                    i += 1
                    break
                i += 1
            continue
        if c == ",":
            out.append("".join(cur).strip())
            cur = []
            i += 1
            continue
        cur.append(c)
        i += 1
    out.append("".join(cur).strip())
    return out


def iter_dump_rows(path, table):
    """Yield field lists for every row of every `INSERT INTO <table>`.

    mysqldump puts `INSERT INTO ... VALUES` on its own line with the tuples on
    the lines after it, so a statement has to be accumulated to its `;` rather
    than read a line at a time.
    """
    marker = f"INSERT INTO `{table}` VALUES"
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        text = fh.read()

    pos = 0
    while True:
        stmt = text.find(marker, pos)
        if stmt < 0:
            return
        cursor = stmt + len(marker)

        # Statement terminator, ignoring semicolons inside string literals.
        j, in_str, end = cursor, False, len(text)
        while j < end:
            c = text[j]
            if in_str:
                if c == "\\":
                    j += 2
                    continue
                if c == "'":
                    in_str = False
            elif c == "'":
                in_str = True
            elif c == ";":
                break
            j += 1
        body = text[cursor:j]
        pos = j + 1

        depth, start, i, n = 0, None, 0, len(body)
        in_str = False
        while i < n:
            c = body[i]
            if in_str:
                if c == "\\":
                    i += 2
                    continue
                if c == "'":
                    in_str = False
            elif c == "'":
                in_str = True
            elif c == "(":
                if depth == 0:
                    start = i + 1
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    yield _split_row(body[start:i])
            i += 1


# --------------------------------------------------------------------------
# selecting the rows to restore, straight out of the base dump
# --------------------------------------------------------------------------

def fetch_riding():
    """Riding ranks, deduplicated -- the same spell sits on many trainers.

    trainer_spell columns: TrainerId, SpellId, MoneyCost, ReqSkillLine,
    ReqSkillRank, ReqAbility1-3, ReqLevel, VerifiedBuild.
    """
    seen, conflicts = {}, {}
    path = os.path.join(BASE_SQL, "trainer_spell.sql")
    for f in iter_dump_rows(path, "trainer_spell"):
        if int(f[3]) != RIDING_SKILL_LINE:
            continue
        cost = int(f[2])
        if cost <= 0:
            continue
        spell_id, level = int(f[1]), int(f[8])
        if spell_id in seen and seen[spell_id] != (cost, level):
            conflicts.setdefault(spell_id, {seen[spell_id]}).add((cost, level))
        seen[spell_id] = (cost, level)
    return (
        sorted((sid, c, lvl) for sid, (c, lvl) in seen.items()),
        conflicts,
    )


def fetch_mounts():
    """Gold-priced mount items.

    item_template columns: entry, class, subclass, SoundOverrideSubclass, name,
    displayid, Quality, Flags, FlagsExtra, BuyCount, BuyPrice, SellPrice.
    """
    rows = []
    path = os.path.join(BASE_SQL, "item_template.sql")
    for f in iter_dump_rows(path, "item_template"):
        if int(f[1]) != ITEM_CLASS_MISC or int(f[2]) != ITEM_SUBCLASS_MOUNT:
            continue
        buy = int(f[10])
        if buy <= 0:
            continue
        name = f[4].strip()
        if name.startswith("'") and name.endswith("'"):
            name = name[1:-1]
        name = name.replace("\\'", "'").replace('\\"', '"').replace("\n", " ")
        rows.append((int(f[0]), name, buy, int(f[11])))
    rows.sort()
    return rows


def money(copper):
    """Render copper as a human-readable g/s/c string for SQL comments."""
    g, rem = divmod(copper, GOLD)
    s, c = divmod(rem, 100)
    parts = []
    if g:
        parts.append(f"{g}g")
    if s:
        parts.append(f"{s}s")
    if c or not parts:
        parts.append(f"{c}c")
    return "".join(parts)


RIDING_HEADER = """\
-- ==========================================================================
-- Riding skill costs: restored to retail
-- ==========================================================================
--
-- This file used to divide every riding cost by 10, on the reasoning that XP
-- ran at 10x while gold income ran at 1x.  That reasoning was sound at the
-- time and is not any more: the income side was fixed too, by
-- `Rate.RewardQuestMoney = 8` in worldserver.overrides.conf.  Two corrections
-- for one problem stack, leaving gold per level near the retail ratio while
-- mounts still cost a tenth of retail.  The config key is the half worth
-- keeping -- it scales with the whole levelling curve instead of pinning 242
-- rows that have to be regenerated whenever the world DB moves.
--
-- Values come from data/sql/base/db_world/trainer_spell.sql, the dump this
-- fork is built on.  When the cut was reverted every one of them was checked
-- against the price this file used to carry: floor(retail / 10) matched in all
-- 6 cases, so the dump is provably the thing that was divided.
--
-- Kept as explicit UPDATEs rather than deleting the file: the cut is already
-- applied to live databases, and a deleted update never runs.  On a fresh DB
-- these are no-ops, which is the correct outcome.
--
-- Selected by trainer_spell.ReqSkillLine = 762 (Riding), which also covers the
-- druid Swift Flight Form -- that is a riding cost like any other.  Keyed on
-- SpellId, not TrainerId, because each rank sits on every riding trainer.
--
-- npc_trainer is deliberately untouched: it is legacy, and no C++ in src/
-- reads it (the live path is trainer / trainer_spell / creature_default_trainer).
--
-- Player::GetReputationPriceDiscount still takes up to 20% off these at
-- Exalted.  Unchanged and intended, exactly as at retail.
--
-- Regenerate with tools/gen_mount_prices.py.
"""

MOUNT_HEADER = """\
-- ==========================================================================
-- Mount item prices: restored to retail
-- ==========================================================================
--
-- Companion to woa_2026_08_07_00.sql (riding skill).  Same reasoning: this
-- file used to cut every gold-priced mount by 10 to offset the 10x XP rate,
-- and `Rate.RewardQuestMoney = 8` now corrects the same imbalance from the
-- income side.  Keeping both over-corrects, so the price cut is reverted.
--
-- SELLPRICE IS RESTORED ALONGSIDE BUYPRICE, AND THAT IS NOT OPTIONAL.  131 of
-- these 236 mounts have a SellPrice above a tenth of their BuyPrice -- Horn of
-- the Timber Wolf buys at 1g and vendors back at 25s.  Restoring BuyPrice
-- alone would leave them vendoring for 2.5x their cost: an infinite gold loop
-- with no cooldown.  Restoring both preserves the retail buy/sell ratio.
--
-- Values come from data/sql/base/db_world/item_template.sql, the dump this
-- fork is built on.  When the cut was reverted every one of them was checked
-- against the price this file used to carry: floor(retail / 10) matched in all
-- 236 cases, so the dump is provably the thing that was divided.
--
-- Scope: item_template class 15 / subclass 5, BuyPrice > 0 -- exactly the rows
-- the cut touched.  The 19 rows here that also sit on an ExtendedCost vendor
-- are no-ops in practice (CreatureData.h::IsGoldRequired ignores BuyPrice when
-- ExtendedCost is set); honor/arena/badge costs live in ItemExtendedCost.dbc
-- and were never in scope.
--
-- Regenerate with tools/gen_mount_prices.py.
"""


def build_riding_sql(rows):
    lines = [RIDING_HEADER, ""]
    for spell_id, cost, level in rows:
        name = RIDING_NAMES.get(spell_id, f"spell {spell_id}")
        lines.append(
            f"UPDATE `trainer_spell` SET `MoneyCost` = {cost} "
            f"WHERE `SpellId` = {spell_id};"
            f"   -- {name} (lvl {level}): {money(cost)}"
        )
    lines.append("")
    return "\n".join(lines)


def build_mount_sql(rows):
    lines = [MOUNT_HEADER, ""]
    for entry, name, buy, sell in rows:
        lines.append(
            f"UPDATE `item_template` SET `BuyPrice` = {buy}, "
            f"`SellPrice` = {sell} WHERE `entry` = {entry};"
            f"   -- {name}: {money(buy)}"
        )
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="verify only, write nothing")
    parser.add_argument("--stdout", action="store_true", help="print SQL")
    args = parser.parse_args()

    riding_rows, conflicts = fetch_riding()
    mount_rows = fetch_mounts()

    if conflicts:
        print("ERROR: a riding rank is priced differently on different trainers, "
              "so a single UPDATE keyed on SpellId would be wrong:")
        for spell_id, variants in sorted(conflicts.items()):
            name = RIDING_NAMES.get(spell_id, f"spell {spell_id}")
            print(f"  {name} ({spell_id}): {sorted(variants)}")
        return 1

    for label, rows in (("riding", riding_rows), ("mounts", mount_rows)):
        if len(rows) != ROW_COUNTS[label]:
            print(f"ERROR: found {len(rows)} {label} rows, expected "
                  f"{ROW_COUNTS[label]}.  The base world DB moved -- re-verify "
                  f"the scope before updating ROW_COUNTS, or this writes a "
                  f"partial revert.")
            return 1

    # The exploit the original cut had to design around, checked from the other
    # direction: retail should never vendor a mount for at least what it costs.
    bad = [r for r in mount_rows if r[3] >= r[2]]
    if bad:
        print(f"ERROR: {len(bad)} mount(s) would vendor for >= their cost.")
        for entry, name, buy, sell in bad[:10]:
            print(f"  {entry} {name}: buy {buy}, sell {sell}")
        return 1

    print(f"Riding ranks:  {len(riding_rows)}")
    for spell_id, cost, level in riding_rows:
        name = RIDING_NAMES.get(spell_id, f"spell {spell_id}")
        print(f"  {name:<22} lvl {level:<3} {money(cost):>8}")
    print(f"Mount items:   {len(mount_rows)}")

    riding_sql = build_riding_sql(riding_rows)
    mount_sql = build_mount_sql(mount_rows)

    if args.stdout:
        print()
        print(riding_sql)
        print(mount_sql)

    if args.dry_run:
        print("\n(dry run -- no files written)")
        return 0

    for filename, content in ((RIDING_SQL, riding_sql), (MOUNT_SQL, mount_sql)):
        path = os.path.join(MODULE_SQL, filename)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(content)
        print(f"Wrote {path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
