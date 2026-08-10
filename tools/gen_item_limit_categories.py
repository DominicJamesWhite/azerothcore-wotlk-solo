#!/usr/bin/env python3
"""
Unique-Equipped Family Generator

Closes a dupe that the item upgrade system would otherwise open.

Player::CanEquipUniqueItem enforces ITEM_FLAG_UNIQUE_EQUIPPABLE by *entry ID*:

    if (itemProto->HasFlag(ITEM_FLAG_UNIQUE_EQUIPPABLE))
        if (HasItemOrGemWithIdEquipped(itemProto->ItemId, 1, except_slot))
            return EQUIP_ERR_ITEM_UNIQUE_EQUIPABLE;      // Player.cpp:13975-13979

An upgraded variant has a different entry, so base + variant of the same unique
trinket would both be equippable -- two copies of an item designed to be worn
once.  The second check in that function is family-based:

    HasItemOrGemWithLimitCategoryEquipped(itemProto->ItemLimitCategory, ...)

...and counts every equipped item sharing the category (PlayerStorage.cpp:769),
so giving a base item and all its variants one shared category with Quantity = 1
restores the intended behaviour.

The mode must be EQUIP, not HAVE -- see ILC_MODE_EQUIP.

Category IDs are allocated sequentially, but only ever for items that do not
already have one: existing assignments are read back and frozen.  Deriving the
id from the item entry would be preferable -- ids would then need no state at
all -- but item_template.ItemLimitCategory is a signed SMALLINT and entries
reach ~70k, so they simply do not fit.

Run this BEFORE tools/gen_item_variants.py.  Variants inherit ItemLimitCategory
from their base row via INSERT ... SELECT *, and the generator's exclusion of
unique items is written as "unique AND ItemLimitCategory = 0" -- so once these
items have a category they are picked up automatically.  For an existing variant
band the emitted propagate-UPDATE does the same job without a regeneration.

Usage:
    python tools/gen_item_limit_categories.py                    # write the SQL
    python tools/gen_item_limit_categories.py --include-maxcount # + MaxCount = 1
    python tools/gen_item_limit_categories.py --dry-run          # summary only
    python tools/gen_item_limit_categories.py --stdout           # print SQL
"""

import argparse
import datetime
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "modules", "world_of_alonecraft", "dbc"))
import config  # noqa: E402

MODULE_SQL = os.path.join(
    REPO_ROOT, "modules", "world_of_alonecraft", "data", "sql", "db-world"
)

ITEM_FLAG_UNIQUE_EQUIPPABLE = 0x00080000

# item_template.ItemLimitCategory is a SIGNED SMALLINT, so ids must fit in
# 32767.  That rules out deriving the id from the item entry (entries reach
# ~70k) -- ids are allocated sequentially from ILC_BASE instead.
#
# Ids already in use are read back from the database and never reissued (see
# load_existing).  The first version of this script renumbered from scratch on
# every run, so one item entering scope shifted every id after it and, worse,
# a run that found only a handful of new items would DELETE all 593 rows and
# re-INSERT only those few.  Live characters wear items carrying these ids.
#
# Retail ids stop at 85, so 1000+ is clear.
ILC_BASE = 1000

# 0 = HAVE (carry limit), 1 = EQUIP (equip limit).  DBCEnums.h:379,
# DBCStructure.h:1240.
#
# It must be EQUIP, and getting this wrong broke every upgrade of a tagged item.
# CanTakeMoreSimilarItems (PlayerStorage.cpp:832-852) applies the category only
# in HAVE mode -- but it has no swap or except-slot parameter, and CanEquipItem
# calls it at :1918, BEFORE the swap-aware CanEquipUniqueItem at :2005.  So in
# HAVE mode a base item counts against its own replacement and the upgrade fails
# with "You can only carry 1 <family>".  In EQUIP mode that block is skipped
# entirely, while CanEquipUniqueItem (Player.cpp:13985-13999) still enforces the
# family -- deliberately without checking mode, per its own comment -- and does
# respect except_slot.  Dupe closed, upgrade unblocked.
#
# EQUIP is also what retail uses for this exact shape.  Death's Choice /
# Death's Verdict, Reign of the Dead / Reign of the Unliving and Solace of the
# Defeated / Solace of the Fallen are all "one trinket, two entries at different
# item levels", and all are mode 1.  Only the consumable-ish families
# (Healthstone, Mana Gem) are mode 0.
ILC_MODE_EQUIP = 1

# Variants live at/above this entry; they inherit their base item's category
# rather than getting one of their own.
VARIANT_ENTRY_BASE = 1_000_000

# Every retail row carries this locale mask.
NAME_LANG_MASK = 16712190


def get_db_connection():
    import mysql.connector
    return mysql.connector.connect(
        host=config.MYSQL_HOST,
        user=config.MYSQL_USER,
        password=config.MYSQL_PASS,
        database=config.MYSQL_DB,
    )


def fetch_candidates(conn, include_maxcount):
    """Items in variant scope that need a family and have no category yet.

    Scope mirrors gen_item_variants.fetch_candidates so an item cannot be given
    a family it will never use, or -- worse -- gain variants without one.

    With --include-maxcount, MaxCount = 1 equippables join the unique-equipped
    ones.  MaxCount is enforced per entry (GetItemCount, PlayerStorage.cpp:822),
    so base and variant never collide and both can currently be worn: 1786 base
    items, four times as many as the unique-equipped hole.  Only MaxCount = 1
    qualifies -- a family caps the whole set at one, which is wrong for an item
    retail lets you carry several of.
    """
    where = "(`Flags` & %s)"
    params = [ITEM_FLAG_UNIQUE_EQUIPPABLE]
    if include_maxcount:
        where = "((`Flags` & %s) OR `MaxCount` = 1)"

    cur = conn.cursor(dictionary=True)
    cur.execute(
        f"""
        SELECT entry, name, Quality, InventoryType
        FROM item_template
        WHERE {where}
          AND ItemLimitCategory = 0
          AND Quality BETWEEN 2 AND 5
          AND InventoryType NOT IN (0, 24, 27, 28)
          AND class IN (2, 4)
          AND entry < %s
        ORDER BY entry
        """,
        (*params, VARIANT_ENTRY_BASE),
    )
    rows = cur.fetchall()
    cur.close()
    return rows


def load_existing(conn):
    """Category ids already issued, and the items already carrying them.

    Returns (next_id, tagged_count).  Raises if an item points at a synthetic
    category that does not exist -- that means a previous run was applied
    partially, and allocating on top of it would compound the damage.
    """
    cur = conn.cursor()
    cur.execute(f"SELECT `ID` FROM `itemlimitcategory_dbc` WHERE `ID` >= {ILC_BASE}")
    known = {r[0] for r in cur.fetchall()}

    cur.execute(
        "SELECT DISTINCT `ItemLimitCategory` FROM `item_template` "
        f"WHERE `ItemLimitCategory` >= {ILC_BASE} AND `entry` < {VARIANT_ENTRY_BASE}"
    )
    used = {r[0] for r in cur.fetchall()}
    cur.close()

    orphans = sorted(used - known)
    if orphans:
        raise SystemExit(
            f"ERROR: {len(orphans)} item(s) reference missing categories "
            f"{orphans[:10]}{'...' if len(orphans) > 10 else ''}. "
            "Apply the previous generated file before re-running."
        )

    return (max(known) + 1 if known else ILC_BASE), len(used)


def sql_str(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "''") + "'"


def format_sql(items, first_id):
    L = []
    A = L.append
    last_id = first_id + len(items) - 1
    A("-- ==========================================================================")
    A("-- Unique-Equipped Families -- auto-generated by tools/gen_item_limit_categories.py")
    A("-- ==========================================================================")
    A("--")
    if items:
        A(f"-- {len(items)} new synthetic ItemLimitCategory rows, ids {first_id}..{last_id}.")
        A("-- Ids below that range were issued by an earlier run and are left alone.")
    else:
        A("-- No new families; this file only corrects the mode of existing ones.")
    A("--")
    A("-- ITEM_FLAG_UNIQUE_EQUIPPABLE is enforced by entry id (Player.cpp:13978), so")
    A("-- an upgraded variant would be equippable alongside its own base item.")
    A("-- A shared limit category with Quantity = 1 is the family-based check that")
    A("-- does cover variants (PlayerStorage.cpp:769).")
    A("--")
    A("-- Must be applied BEFORE regenerating variants: the variant generator skips")
    A("-- unique items only while ItemLimitCategory = 0, and variants inherit the")
    A("-- category from their base row.  For a variant band that already exists,")
    A("-- the propagate-UPDATE at the end of this file does the same job.")
    A("")

    A("-- -- mode: EQUIP, not HAVE --------------------------------------------")
    A("-- HAVE mode routes the family through CanTakeMoreSimilarItems")
    A("-- (PlayerStorage.cpp:832-852), which has no swap or except-slot parameter")
    A("-- and is called at CanEquipItem:1918 -- BEFORE the swap-aware")
    A("-- CanEquipUniqueItem at :2005.  A base item therefore counted against its")
    A("-- own replacement and every upgrade of a tagged item failed with")
    A("-- \"You can only carry 1 <family>\".  EQUIP mode skips that block; the")
    A("-- family is still enforced on equip, and there with except_slot honoured.")
    A("-- Retail agrees: Death's Choice / Death's Verdict and the other")
    A("-- one-trinket-two-entries families are all mode 1.")
    A(f"UPDATE `itemlimitcategory_dbc` SET `Flags` = {ILC_MODE_EQUIP} "
      f"WHERE `ID` >= {ILC_BASE};")
    A("")

    if items:
        ids = {it["entry"]: first_id + n for n, it in enumerate(items)}

        A("-- -- categories ------------------------------------------------------")
        A(f"DELETE FROM `itemlimitcategory_dbc` WHERE `ID` BETWEEN {first_id} AND {last_id};")
        A("")
        rows = [
            "({}, {}, {}, 1, {})".format(
                ids[i["entry"]], sql_str(i["name"]), NAME_LANG_MASK, ILC_MODE_EQUIP
            )
            for i in items
        ]
        for i in range(0, len(rows), 500):
            A("INSERT INTO `itemlimitcategory_dbc` "
              "(`ID`, `Name_Lang_enUS`, `Name_Lang_Mask`, `Quantity`, `Flags`) VALUES")
            A(",\n".join(rows[i:i + 500]) + ";")
            A("")

        A("-- -- tag the base items ----------------------------------------------")
        for i in range(0, len(items), 500):
            chunk = items[i:i + 500]
            cases = " ".join(
                f"WHEN {it['entry']} THEN {ids[it['entry']]}" for it in chunk
            )
            entries = ", ".join(str(it["entry"]) for it in chunk)
            A(f"UPDATE `item_template` SET `ItemLimitCategory` = CASE `entry` {cases} END "
              f"WHERE `entry` IN ({entries});")
            A("")

    A("-- -- propagate to existing variants -----------------------------------")
    A("-- Variants inherit the category through INSERT ... SELECT * only when they")
    A("-- are regenerated.  The entry encodes the base (ItemUpgrade.h), so one")
    A("-- statement brings an existing band up to date instead -- far cheaper than")
    A("-- regenerating ~78k rows to move one column.")
    A("UPDATE `item_template` v")
    A(f"  JOIN `item_template` b ON b.`entry` = (v.`entry` - {VARIANT_ENTRY_BASE}) DIV 20")
    A("  SET v.`ItemLimitCategory` = b.`ItemLimitCategory`")
    A(f"WHERE v.`entry` >= {VARIANT_ENTRY_BASE};")
    A("")

    return "\n".join(L) + "\n"


def next_sql_path():
    # Highest + 1, not the first free number: filling a gap would make this file
    # sort before updates written after the gap appeared, and this one has to be
    # applied before the variant generator's output.
    import glob
    today = datetime.date.today().strftime("%Y_%m_%d")
    used = [int(os.path.basename(p)[-6:-4])
            for p in glob.glob(os.path.join(MODULE_SQL, f"woa_{today}_*.sql"))
            if os.path.basename(p)[-6:-4].isdigit()]
    seq = max(used) + 1 if used else 0
    return os.path.join(MODULE_SQL, f"woa_{today}_{seq:02d}.sql")


def main():
    p = argparse.ArgumentParser(description="Generate unique-equipped families")
    p.add_argument("--include-maxcount", action="store_true",
                   help="also give MaxCount = 1 equippables a family")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--stdout", action="store_true")
    args = p.parse_args()

    conn = get_db_connection()
    first_id, already = load_existing(conn)
    items = fetch_candidates(conn, args.include_maxcount)
    conn.close()

    print(f"Items already carrying a family: {already}", file=sys.stderr)
    print(f"Items needing a new family:      {len(items)} "
          f"(ids from {first_id})", file=sys.stderr)
    if items:
        by_slot = {}
        for it in items:
            by_slot[it["InventoryType"]] = by_slot.get(it["InventoryType"], 0) + 1
        top = sorted(by_slot.items(), key=lambda kv: -kv[1])[:5]
        print("  by slot: " + ", ".join(f"invtype {k}: {v}" for k, v in top), file=sys.stderr)

    # ItemLimitCategory is a signed SMALLINT.
    if items and first_id + len(items) - 1 > 32767:
        raise SystemExit("ERROR: category ids would exceed the SMALLINT column.")

    if args.dry_run:
        return

    sql = format_sql(items, first_id)
    if args.stdout:
        sys.stdout.write(sql)
        return

    path = next_sql_path()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(sql)
    print(f"Wrote {path} ({len(sql) / 1024:.0f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
