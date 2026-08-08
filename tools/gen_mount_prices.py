#!/usr/bin/env python3
"""
Mount Price Generator

Cuts riding skill training and gold-priced mount items by a factor of 10, to
match Alonecraft's 10x XP rate.

Why this exists at all: XP runs at 10x but gold income is still 1x, so a
character arrives at level 40 with roughly a tenth of the gold retail assumed
they would have.  The riding gates (50g, 250g, 5000g) were paced against the
retail levelling curve, and at 10x they land as walls that never existed in the
original game.  Dividing them by 10 restores the *original* ratio of
gold-earned to gold-owed rather than removing the gate.

Two things this generator is careful about:

1.  SELLPRICE MUST BE SCALED TOO.  131 of the 236 gold-priced mounts have a
    SellPrice above a tenth of their BuyPrice -- Horn of the Timber Wolf buys
    at 10000c and vendors back at 2500c.  Cut BuyPrice alone and it sells for
    2.5x what it costs, which is an infinite gold loop with no cooldown.
    Scaling both preserves the original buy/sell ratio exactly.

2.  ABSOLUTE VALUES, NOT ARITHMETIC.  `SET BuyPrice = BuyPrice / 10` is not
    idempotent, and module SQL is re-applied by the server at startup on top of
    any manual pre-application (see the ordering trap in CLAUDE.md) -- a second
    pass would divide twice.  So every row's new price is precomputed and
    emitted as a literal, matching the precedent in woa_2026_08_06_24.sql.
    DIVISOR lives here, so regenerating reproduces these prices instead of
    reducing them again.

Scope notes:

  * Riding is selected by `trainer_spell.ReqSkillLine = 762`, which also picks
    up the druid Swift Flight Form (40120).  That is intended -- it is a riding
    cost like any other.  `npc_trainer` is deliberately untouched: it is legacy
    and no C++ in src/ reads it.
  * Mount items are `item_template.class = 15 AND subclass = 5`.  Rows with
    BuyPrice = 0 are skipped entirely; they cannot be bought, so there is no
    cost to cut and no exploit to create.
  * The 19 priced mounts that also sit on an ExtendedCost vendor are emitted
    anyway but are no-ops in practice: CreatureData.h::IsGoldRequired makes the
    core ignore BuyPrice when ExtendedCost is set.  Honor/arena/badge costs
    live in ItemExtendedCost.dbc and are out of scope -- changing them
    server-side without a client DBC patch would make the tooltip disagree with
    what the player is actually charged.
  * Player::GetReputationPriceDiscount still applies up to 20% on top of these
    prices at Exalted.  Unchanged and intended.

Usage:
    python tools/gen_mount_prices.py            # write both SQL files
    python tools/gen_mount_prices.py --dry-run  # summary only
    python tools/gen_mount_prices.py --stdout   # print SQL
"""

import argparse
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc"))

MODULE_SQL = os.path.join(
    REPO_ROOT, "modules", "world_of_alonecraft", "data", "sql", "db-world"
)

# The single coefficient.  Everything else in this file derives from it.
DIVISOR = 10

RIDING_SKILL_LINE = 762
ITEM_CLASS_MISC = 15
ITEM_SUBCLASS_MOUNT = 5

RIDING_SQL = "woa_2026_08_07_00.sql"
MOUNT_SQL = "woa_2026_08_07_01.sql"

GOLD = 10000


def get_db_connection():
    import config
    import mysql.connector
    return mysql.connector.connect(
        host=config.MYSQL_HOST,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASS,
        database=config.MYSQL_DB,
    )


def scale(value):
    """Divide by DIVISOR, never rounding a real price down to free."""
    if value <= 0:
        return 0
    return max(1, value // DIVISOR)


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


def fetch_riding(conn):
    """Riding skill ranks, deduplicated -- the same spell sits on many trainers."""
    cur = conn.cursor()
    cur.execute(
        "SELECT ts.SpellId, ts.MoneyCost, ts.ReqLevel "
        "FROM trainer_spell ts "
        "WHERE ts.ReqSkillLine = %s AND ts.MoneyCost > 0 "
        "GROUP BY ts.SpellId, ts.MoneyCost, ts.ReqLevel "
        "ORDER BY ts.ReqLevel, ts.MoneyCost",
        (RIDING_SKILL_LINE,),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def fetch_mounts(conn):
    cur = conn.cursor()
    cur.execute(
        "SELECT entry, name, BuyPrice, SellPrice "
        "FROM item_template "
        "WHERE class = %s AND subclass = %s AND BuyPrice > 0 "
        "ORDER BY entry",
        (ITEM_CLASS_MISC, ITEM_SUBCLASS_MOUNT),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def spell_names(conn, spell_ids):
    """Best-effort names for the SQL comments; falls back to the bare id."""
    if not spell_ids:
        return {}
    placeholders = ",".join(["%s"] * len(spell_ids))
    cur = conn.cursor()
    try:
        cur.execute(
            f"SELECT ID, SpellName0 FROM alonecraft_spell_dbc WHERE ID IN ({placeholders})",
            tuple(spell_ids),
        )
        found = {int(r[0]): r[1] for r in cur.fetchall()}
    except Exception:
        found = {}
    cur.close()
    return found


# Names for the riding ranks.  The client DBC is the authoritative source but
# these six ids are stable across 3.3.5a and hardcoding them keeps this
# generator free of a DBC dependency for what is only a comment.
RIDING_NAMES = {
    33388: "Apprentice Riding",
    33391: "Journeyman Riding",
    34090: "Expert Riding",
    34091: "Artisan Riding",
    54197: "Cold Weather Flying",
    40120: "Swift Flight Form",
}

RIDING_HEADER = """\
-- ==========================================================================
-- Riding skill costs: 10x cut to match the 10x XP rate
-- ==========================================================================
--
-- XP runs at 10x but gold income is still 1x, so a character reaches level 40
-- with about a tenth of the gold retail assumed.  The riding gates were paced
-- against the retail levelling curve; at 10x they are walls that never existed
-- in the original game.  Dividing by 10 restores the original ratio of
-- gold-earned to gold-owed rather than removing the gate.
--
-- Selected by trainer_spell.ReqSkillLine = 762 (Riding), which also covers the
-- druid Swift Flight Form -- that is a riding cost like any other.  Keyed on
-- SpellId, not TrainerId, because each rank sits on every riding trainer.
--
-- npc_trainer is deliberately untouched: it is legacy, and no C++ in src/
-- reads it (the live path is trainer / trainer_spell / creature_default_trainer).
--
-- Player::GetReputationPriceDiscount still takes up to 20% off these at
-- Exalted.  Unchanged and intended.
--
-- Absolute values, not `MoneyCost / 10`: module SQL is re-applied at startup on
-- top of any manual pre-application, and relative arithmetic would divide twice.
-- Regenerate with tools/gen_mount_prices.py, which carries the same divisor.
"""

MOUNT_HEADER = """\
-- ==========================================================================
-- Mount item prices: 10x cut to match the 10x XP rate
-- ==========================================================================
--
-- Companion to woa_2026_08_07_00.sql (riding skill).  Same reasoning: gold
-- income is 1x while XP is 10x, so mount prices are cut by the same factor to
-- restore the retail ratio of gold-earned to gold-owed.
--
-- SELLPRICE IS SCALED TOO, AND THAT IS NOT OPTIONAL.  131 of these 236 mounts
-- have a SellPrice above a tenth of their BuyPrice -- Horn of the Timber Wolf
-- buys at 1g and vendors back at 25s.  Cutting BuyPrice alone would let it sell
-- for 2.5x its cost: an infinite gold loop with no cooldown.  Scaling both
-- preserves the original buy/sell ratio exactly.
--
-- Scope: item_template class 15 / subclass 5, BuyPrice > 0.  Rows priced at 0
-- are skipped -- they cannot be bought, so there is no cost to cut and no
-- exploit to create.  The 19 rows here that also sit on an ExtendedCost vendor
-- are no-ops in practice (CreatureData.h::IsGoldRequired ignores BuyPrice when
-- ExtendedCost is set); honor/arena/badge costs live in ItemExtendedCost.dbc
-- and are out of scope, since changing them server-side without a client DBC
-- patch would make the tooltip disagree with what the player is charged.
--
-- Absolute values, not `BuyPrice / 10`: module SQL is re-applied at startup on
-- top of any manual pre-application, and relative arithmetic would divide twice.
-- Regenerate with tools/gen_mount_prices.py, which carries the same divisor.
"""


def build_riding_sql(rows):
    lines = [RIDING_HEADER, ""]
    for spell_id, cost, req_level in rows:
        new_cost = scale(int(cost))
        name = RIDING_NAMES.get(int(spell_id), f"spell {spell_id}")
        lines.append(
            f"UPDATE `trainer_spell` SET `MoneyCost` = {new_cost} "
            f"WHERE `SpellId` = {spell_id};"
            f"   -- {name} (lvl {req_level}): {money(int(cost))} -> {money(new_cost)}"
        )
    lines.append("")
    return "\n".join(lines)


def build_mount_sql(rows):
    lines = [MOUNT_HEADER, ""]
    for entry, name, buy, sell in rows:
        new_buy = scale(int(buy))
        new_sell = scale(int(sell))
        safe_name = (name or "").replace("\n", " ").strip()
        lines.append(
            f"UPDATE `item_template` SET `BuyPrice` = {new_buy}, `SellPrice` = {new_sell} "
            f"WHERE `entry` = {entry};"
            f"   -- {safe_name}: {money(int(buy))} -> {money(new_buy)}"
        )
    lines.append("")
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="summary only")
    parser.add_argument("--stdout", action="store_true", help="print SQL")
    args = parser.parse_args()

    conn = get_db_connection()
    try:
        riding = fetch_riding(conn)
        mounts = fetch_mounts(conn)
    finally:
        conn.close()

    if not riding:
        print("ERROR: no riding rows found -- is ReqSkillLine 762 still Riding?")
        return 1
    if not mounts:
        print("ERROR: no priced mount rows found -- check class 15 / subclass 5.")
        return 1

    # Guard the exploit this generator exists to avoid.  If any output row would
    # vendor for at least what it costs, refuse to write the file.
    bad = [
        (entry, name, buy, sell)
        for entry, name, buy, sell in mounts
        if scale(int(sell)) >= scale(int(buy))
    ]
    if bad:
        print(f"ERROR: {len(bad)} row(s) would sell for >= their cost. Refusing to write.")
        for entry, name, buy, sell in bad[:10]:
            print(f"  {entry} {name}: buy {buy} -> {scale(int(buy))}, "
                  f"sell {sell} -> {scale(int(sell))}")
        return 1

    riding_sql = build_riding_sql(riding)
    mount_sql = build_mount_sql(mounts)

    print(f"Riding ranks:  {len(riding)}  (divisor {DIVISOR})")
    for spell_id, cost, req_level in riding:
        name = RIDING_NAMES.get(int(spell_id), f"spell {spell_id}")
        print(f"  {name:<22} lvl {req_level:<3} "
              f"{money(int(cost)):>8} -> {money(scale(int(cost)))}")
    print(f"Mount items:   {len(mounts)}")

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
