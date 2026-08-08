#!/usr/bin/env python3
"""
Upgrade Tool Icon Generator

The 16 upgrade tools sold by Artificer Volen all shared displayid 6533, which
belongs to item 12870 "Monster - Item, Potion Red Offhand" -- an NPC prop whose
icon is INV_Potion_07.  One off-theme red potion for the whole ladder, with no
visual signal of tier.

This recolours four enchanting-reagent icons along a single cool-to-warm ramp,
giving one distinct icon per level: cold blue at 5, through violet and ember,
to near-white gold at 80.  The shape says which material family a tool belongs
to (Mote / Shard / Prism / Sigil, matching TOOL_NAMES); the colour says where in
the ladder it sits.

Three artefacts have to agree, so all three come from this one script:

  * Interface/custom/Icons/woa_upgrade_<level>.blp -- the art, packed into
    patch-4.mpq by Interface/build_interface.py.
  * itemdisplayinfo_dbc rows 69000+ -- pointing at those icon names.  Read by
    the server and, via build_dbc.py, patched into the client's
    ItemDisplayInfo.dbc.
  * item_template.displayid / item_dbc.DisplayInfoID for 200100-200115.

The item side is UPDATEd rather than re-INSERTed: a full-row INSERT would
revert RequiredLevel (woa_2026_08_06_17.sql) and the prices
(woa_2026_08_06_24.sql).  gen_upgrade_tools.py carries display_id() too, so
regenerating it from scratch produces the same ids.

Why the recolour is a hue *replacement* and not a hue rotation: the four source
icons start at four different hues (321, 171, 234 and 209 degrees), so rotating
each by the same amount would put the same ladder position at four different
colours.  Value is left completely untouched apart from a deliberate per-step
gain, which is what keeps the original shading and highlights instead of
flattening the icon into a colour swatch.

Usage:
    python tools/gen_upgrade_icons.py                # write BLPs + SQL
    python tools/gen_upgrade_icons.py --preview DIR  # also dump PNGs to review
    python tools/gen_upgrade_icons.py --dry-run      # summary only
"""

import argparse
import io
import os
import struct
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, "tools"))

from extract_icons import ARCHIVES, CLIENT_DATA, read_from_mpq  # noqa: E402
from gen_upgrade_tools import (  # noqa: E402
    MODULE_SQL, STEP_SIZE, TOOL_NAMES, display_id, item_id, next_sql_path,
    sql_str,
)

ICON_OUT = os.path.join(REPO_ROOT, "Interface", "custom", "Icons")
ICON_PREFIX = "woa_upgrade_"

# One source icon per material family, chosen to match the noun in TOOL_NAMES so
# the art and the name agree: a "Mote" looks like dust, a "Shard" like a shard.
# Keyed by the first level of the family.
SOURCE_ICONS = {
    5:  "INV_Enchant_DustArcane",
    25: "INV_Enchant_ShardGlimmeringSmall",
    45: "INV_Enchant_PrismaticSphere",
    65: "INV_Enchant_EssenceEternalLarge",
}

# The ladder, one entry per level 5..80 in order.
#
#   hue  -- absolute, degrees.  Monotone 205 -> 410 (= 50), so it never doubles
#           back: blue, indigo, violet, magenta, rose, red, ember, gold.
#   sat  -- multiplier on the source saturation.  Falls away at the top so the
#           last few read as heat rather than as a stronger orange.
#   val  -- multiplier on the source value.  Climbs within each family, which is
#           what separates the four steps of one family from each other when
#           their hues are only ~13 degrees apart.
#
# Tune here and nowhere else; everything downstream is derived.
RAMP = [
    # level  hue   sat   val
    (5,      205, 0.85, 1.00),
    (10,     215, 0.90, 1.02),
    (15,     228, 0.92, 1.06),
    (20,     242, 0.94, 1.10),
    (25,     258, 0.95, 1.00),
    (30,     272, 0.95, 1.03),
    (35,     288, 0.94, 1.07),
    (40,     305, 0.93, 1.11),
    (45,     322, 0.92, 1.00),
    (50,     338, 0.92, 1.03),
    (55,     352, 0.92, 1.07),
    (60,     366, 0.90, 1.12),
    # The Sigil source (EssenceEternalLarge) is already a near-white flare, so
    # this family climbs in saturation rather than value.  Carrying the other
    # families' value gain here just clipped it: 75 and 80 came out as the same
    # blown-out white, and the ladder lost its top two rungs.
    (65,     380, 0.90, 1.00),
    (70,     392, 0.98, 1.02),
    (75,     402, 1.06, 1.05),
    (80,     410, 1.15, 1.09),
]


def icon_name(level):
    return f"{ICON_PREFIX}{level}"


def family_of(level):
    """First level of the four-step material family `level` belongs to."""
    return ((level - 1) // (4 * STEP_SIZE)) * (4 * STEP_SIZE) + STEP_SIZE


def load_source(name):
    """Read one Interface\\Icons BLP out of the client, most-recent archive first."""
    member = "Interface\\Icons\\" + name + ".blp"
    for archive in ARCHIVES:
        data = read_from_mpq(os.path.join(CLIENT_DATA, archive), member)
        if data:
            return data
    sys.exit(f"ERROR: {member} not found in any of {ARCHIVES}")


def recolour(blp_bytes, hue, sat, val):
    """Replace hue wholesale, scale saturation and value, keep the shading."""
    from PIL import Image

    source = Image.open(io.BytesIO(blp_bytes))
    source.load()
    hsv = source.convert("RGB").convert("HSV")
    _, s_band, v_band = hsv.split()

    # PIL's H band is 0-255 over the full circle, not 0-359.
    h8 = int(round((hue % 360) / 360.0 * 255)) % 256
    h_band = Image.new("L", source.size, h8)
    s_band = s_band.point(lambda x: min(255, int(x * sat)))
    v_band = v_band.point(lambda x: min(255, int(x * val)))

    return Image.merge("HSV", (h_band, s_band, v_band)).convert("RGB")


# ── BLP2 encoding ───────────────────────────────────────────────────────────
# Pillow's own BLP writer is not usable here.  It emits a palettised image with
# a single mipmap level and hasMips = 0, and the 3.3.5a client renders that as a
# flat neon-green square -- the documented symptom of a BLP with no mipmap
# chain.  Every one of 59 sampled retail icons is DXT with hasMips = 17 and all
# seven levels present (64, 32, 16, 8, 4, 2, 1); none is palettised.  So this
# writes the header by hand and matches retail's shape.
#
# Pillow is still doing the hard part: it has a DXT1 encoder behind its DDS
# writer, so each mip is saved as a DDS and the 128-byte DDS header sliced off,
# leaving raw DXT1 blocks in exactly the layout BLP2 wants.
BLP_MAGIC = b"BLP2"
BLP_TYPE = 1               # always 1
BLP_ENC_DXT = 2            # 1 = palettised, 2 = DXT
BLP_ALPHA_DEPTH = 0        # opaque icons; with alphaEnc 0 this means DXT1
BLP_ALPHA_ENC = 0          # 0 = DXT1, 1 = DXT3, 7 = DXT5
BLP_HAS_MIPS = 17          # what every retail icon carries; the client wants != 0
BLP_MAX_MIPS = 16          # the header always has 16 offset and 16 size slots
BLP_PALETTE_BYTES = 1024   # 256 BGRA entries, unused by DXT but still present
DDS_HEADER_BYTES = 128


def _dxt1_blocks(image):
    """Raw DXT1 block data for one mip level, via Pillow's DDS encoder."""
    from PIL import Image

    # DXT works in 4x4 blocks, so the 2x2 and 1x1 mips have to be padded up to
    # one full block.  Retail does the same: its last three mip levels are all
    # the same size on disk.
    w, h = image.size
    if w < 4 or h < 4:
        padded = Image.new("RGBA", (max(4, w), max(4, h)))
        padded.paste(image.convert("RGBA").resize((max(4, w), max(4, h)),
                                                  Image.NEAREST))
        image = padded

    buf = io.BytesIO()
    image.convert("RGBA").save(buf, "DDS", pixel_format="DXT1")
    return buf.getvalue()[DDS_HEADER_BYTES:]


def to_blp(image):
    """Encode an RGB image as a DXT1 BLP2 with a full mipmap chain."""
    from PIL import Image

    width, height = image.size
    mips = []
    size = width
    while size >= 1:
        level = image if size == width else image.resize((size, size), Image.LANCZOS)
        mips.append(_dxt1_blocks(level))
        if size == 1:
            break
        size //= 2

    header_bytes = 20 + BLP_MAX_MIPS * 4 * 2 + BLP_PALETTE_BYTES
    offsets, sizes, cursor = [0] * BLP_MAX_MIPS, [0] * BLP_MAX_MIPS, header_bytes
    for i, data in enumerate(mips):
        offsets[i], sizes[i] = cursor, len(data)
        cursor += len(data)

    out = bytearray()
    out += BLP_MAGIC
    out += struct.pack("<I", BLP_TYPE)
    out += struct.pack("<4B", BLP_ENC_DXT, BLP_ALPHA_DEPTH, BLP_ALPHA_ENC,
                       BLP_HAS_MIPS)
    out += struct.pack("<2I", width, height)
    out += struct.pack(f"<{BLP_MAX_MIPS}I", *offsets)
    out += struct.pack(f"<{BLP_MAX_MIPS}I", *sizes)
    out += b"\x00" * BLP_PALETTE_BYTES
    assert len(out) == header_bytes, (len(out), header_bytes)
    for data in mips:
        out += data
    return bytes(out)


# ── SQL ─────────────────────────────────────────────────────────────────────
# ItemDisplayInfo columns, in binary field order.  Field 5 (InventoryIcon_1) is
# the only one that matters here; the rest are zeroed rather than cloned from
# 6533, because copying that row would bring its potion model along and these
# tools are never held in hand.
IDI_COLUMNS = (
    "ID", "ModelName_1", "ModelName_2", "ModelTexture_1", "ModelTexture_2",
    "InventoryIcon_1", "InventoryIcon_2", "GeosetGroup_1", "GeosetGroup_2",
    "GeosetGroup_3", "Flags", "SpellVisualID", "GroupSoundIndex",
    "HelmetGeosetVis_1", "HelmetGeosetVis_2", "Texture_1", "Texture_2",
    "Texture_3", "Texture_4", "Texture_5", "Texture_6", "Texture_7",
    "Texture_8", "ItemVisual", "ParticleColorID",
)
IDI_STRING_COLUMNS = frozenset((
    "ModelName_1", "ModelName_2", "ModelTexture_1", "ModelTexture_2",
    "InventoryIcon_1", "InventoryIcon_2",
    "Texture_1", "Texture_2", "Texture_3", "Texture_4",
    "Texture_5", "Texture_6", "Texture_7", "Texture_8",
))


def display_row(level):
    values = []
    for col in IDI_COLUMNS:
        if col == "ID":
            values.append(str(display_id(level)))
        elif col == "InventoryIcon_1":
            values.append(sql_str(icon_name(level)))
        elif col in IDI_STRING_COLUMNS:
            values.append("''")
        else:
            values.append("0")
    return "(" + ", ".join(values) + ")"


def format_sql():
    levels = sorted(TOOL_NAMES)
    ids = ", ".join(str(display_id(l)) for l in levels)
    L = []
    A = L.append

    A("-- Recoloured icons for the 16 gear upgrade tools.")
    A("--")
    A("-- Generated by tools/gen_upgrade_icons.py -- do not hand-edit; edit RAMP")
    A("-- there and regenerate, or the SQL and the art in")
    A("-- Interface/custom/Icons/ drift apart.")
    A("--")
    A("-- The tools shared displayid 6533 (INV_Potion_07, an NPC prop off item")
    A("-- 12870 'Monster - Item, Potion Red Offhand'), so all sixteen looked")
    A("-- like the same red potion.  Each now gets a display row of its own")
    A("-- pointing at Interface\\Icons\\woa_upgrade_<level>.blp, packed into")
    A("-- patch-4.mpq.  Retail's ItemDisplayInfo ends at 68742, so 69000+ is free.")
    A("")

    A("-- -- display rows -----------------------------------------------------")
    A("-- Read by the server (DBCStores.cpp) and patched into the client's")
    A("-- ItemDisplayInfo.dbc by modules/world_of_alonecraft/dbc/build_dbc.py.")
    A("-- Model fields are left empty on purpose: cloning 6533's int fields")
    A("-- would carry Misc_1H_Potion_B_01.mdx along with them.")
    A(f"DELETE FROM `itemdisplayinfo_dbc` WHERE `ID` IN ({ids});")
    A("INSERT INTO `itemdisplayinfo_dbc`")
    A("  (" + ", ".join(f"`{c}`" for c in IDI_COLUMNS) + ")")
    A("VALUES")
    A(",\n".join(display_row(l) for l in levels) + ";")
    A("")

    A("-- -- point the tools at them ------------------------------------------")
    A("-- UPDATE, not a full-row re-INSERT: these rows already carry")
    A("-- RequiredLevel from woa_2026_08_06_17.sql and prices from")
    A("-- woa_2026_08_06_24.sql, and a re-INSERT would revert both.")
    for level in levels:
        A(f"UPDATE `item_template` SET `displayid` = {display_id(level)} "
          f"WHERE `entry` = {item_id(level)};")
    A("")
    for level in levels:
        A(f"UPDATE `item_dbc` SET `DisplayInfoID` = {display_id(level)} "
          f"WHERE `ID` = {item_id(level)};")
    return "\n".join(L) + "\n"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--preview", metavar="DIR",
                   help="also write PNGs here for eyeballing the ramp")
    p.add_argument("--dry-run", action="store_true",
                   help="print the ladder, write nothing")
    p.add_argument("--stdout", action="store_true", help="print SQL")
    args = p.parse_args()

    if len(RAMP) != len(TOOL_NAMES):
        sys.exit(f"ERROR: RAMP has {len(RAMP)} entries, "
                 f"TOOL_NAMES has {len(TOOL_NAMES)}")

    print(f"{'lvl':>4} {'name':30} {'source':34} {'hue':>4} "
          f"{'sat':>5} {'val':>5}  display", file=sys.stderr)
    for level, hue, sat, val in RAMP:
        print(f"{level:>4} {TOOL_NAMES[level]:30} "
              f"{SOURCE_ICONS[family_of(level)]:34} {hue % 360:>4} "
              f"{sat:>5.2f} {val:>5.2f}  {display_id(level)}", file=sys.stderr)

    if args.dry_run:
        return

    sources = {lvl: load_source(name) for lvl, name in SOURCE_ICONS.items()}
    os.makedirs(ICON_OUT, exist_ok=True)
    if args.preview:
        os.makedirs(args.preview, exist_ok=True)

    for level, hue, sat, val in RAMP:
        image = recolour(sources[family_of(level)], hue, sat, val)
        path = os.path.join(ICON_OUT, icon_name(level) + ".blp")
        with open(path, "wb") as f:
            f.write(to_blp(image))
        if args.preview:
            image.save(os.path.join(args.preview, icon_name(level) + ".png"))
    print(f"Wrote {len(RAMP)} icons to {ICON_OUT}", file=sys.stderr)

    sql = format_sql()
    if args.stdout:
        sys.stdout.write(sql)
        return
    path = next_sql_path()
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(sql)
    print(f"Wrote {path} ({len(sql) / 1024:.0f} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
