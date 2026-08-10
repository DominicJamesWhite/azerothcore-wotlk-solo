#!/usr/bin/env python3
"""
Item Spell Scaling -- upgrade paths for items whose power is entirely a spell.

gen_item_variants.py used to give up on any item with no stats, no armour and no
weapon damage:

    if not any(stat_value1..10) and not armor and not dmg_max1:
        return None          # end of chain, zero variants

That was right at the time -- a variant identical to its base but with a higher
RequiredLevel is strictly worse -- but it wrote off 759 uncommon+ equippables,
305 of them trinkets.  Gnomeregan Auto-Blocker 600 (29387) is the type case: no
stats at all, everything in spells 42038 (on-equip) and 35169 (on-use).

This module scales those spells instead.  Each item spell is cloned into a
reserved Spell.dbc band with its base points multiplied by the same
RandPropPoints ratio the stat path would have used, and the variant's spellid_N
is pointed at the clone.  The item keeps its identity; only the numbers move.

WHAT IS DELIBERATELY NOT SCALED
    A clone gets a NEW spell id, and anything keyed to the OLD id stops
    applying.  Two things are keyed that way and neither can be carried across:

      * C++ that switches on m_spellInfo->Id -- SPELL_EFFECT_DUMMY (3),
        SPELL_EFFECT_SCRIPT_EFFECT (77) and SPELL_AURA_DUMMY (4) are all
        implemented that way, so a clone of one silently does nothing.
      * spell_script_names rows.  37 of the 402 spells in scope have one.

    Both are rejected outright.  spell_proc rows (51 of 402) are the opposite
    case -- plain declarative data -- so those are cloned alongside the spell.

    Values that are percentages, durations or milliseconds are passed through
    unchanged.  Tripling a 15% movement-speed trinket to 45% is the obvious
    catastrophe; SPELLMOD_COOLDOWN and SPELLMOD_ACTIVATION_TIME (aura 107, unit
    chosen by EffectMiscValue) are the subtle one.

    Classification is a WHITELIST.  An effect or aura nobody has classified
    rejects the spell rather than being guessed at -- see census() for how to
    review what is currently being turned away.

Imported by gen_item_variants.py rather than run standalone: the cloned spell
ids and the item_template.spellid_N values pointing at them have to be allocated
in one pass and land in one SQL file, or a partial apply leaves items referring
to spells that do not exist.

    python tools/item_spell_scaling.py --census    # what would be rejected, and why
"""

import hashlib
import re

# ── Spell id band ───────────────────────────────────────────────────────────
# Dense sequential allocation, NOT an arithmetic encoding of the item entry.
#
# The tempting encoding -- SPELL_VARIANT_BASE + (variantEntry - 1e6) * K -- runs
# to ~11.4 million, and DBCFileLoader::AutoProduceData allocates
# indexTable[maxId + 1] (DBCFileLoader.cpp:201-215).  That is 91 MB of mostly
# null pointers on the server AND again in the 32-bit client, bought for nothing:
# unlike item entries, no code ever decodes a spell id back to its item.
#
# alonecraft_spell_dbc runs 71..210338 today (customs at 200000+, upgrade tool
# spells at 201000..201015), so 300000 is clear and keeps the index array small.
SPELL_VARIANT_BASE = 300_000
SPELL_VARIANT_LIMIT = 350_000

# How deep a trigger chain is followed.  Measured maximum in this data is 1;
# three is slack, and hitting it is logged rather than silently truncated.
MAX_TRIGGER_DEPTH = 3

# ── Effects ─────────────────────────────────────────────────────────────────
# Effects whose EffectBasePoints IS the payload magnitude.
SCALE_EFFECTS = {
    2,    # SCHOOL_DAMAGE
    9,    # HEALTH_LEECH
    10,   # HEAL
    30,   # ENERGIZE
    58,   # WEAPON_DAMAGE      (flat bonus, not a percentage)
    63,   # THREAT
}

# Effects that carry an aura; whether they scale is decided by the aura name.
AURA_EFFECTS = {
    6,    # APPLY_AURA
    27,   # PERSISTENT_AREA_AURA
    35,   # APPLY_AREA_AURA_PARTY
    65,   # APPLY_AREA_AURA_RAID
}

# Effects whose payload lives in another spell.  The child is cloned and scaled
# and EffectTriggerSpellN is repointed; the parent's own base points are left
# alone (for a trigger they are usually a chance or unused).
RECURSE_EFFECTS = {
    64,   # TRIGGER_SPELL
}

# Effects that are real and safe to keep verbatim, but have nothing meaningful
# to multiply.  Empty today -- every such case in this data set turned out to be
# aura-carrying, so it is decided by PASSTHROUGH_AURAS instead.  The hook stays
# because the next census will almost certainly need it.
PASSTHROUGH_EFFECTS = {
    31,   # WEAPON_PERCENT_DAMAGE  (a percentage of weapon damage, which the
          #                         stat path already scales)
    54,   # ENCHANT_ITEM_TEMPORARY (MiscValue is an enchant id; the enchant
          #                         itself is what would have to scale)
    98,   # KNOCK_BACK             (base points is a speed)
}

# Effects that force the whole spell to be rejected, with the reason.
REJECT_EFFECTS = {
    16:  "SPELL_EFFECT_QUEST_COMPLETE (no magnitude)",
    34:  "SPELL_EFFECT_SUMMON_CHANGE_ITEM (MiscValue is an item id)",
    3:   "SPELL_EFFECT_DUMMY (payload is C++ keyed to the spell id)",
    77:  "SPELL_EFFECT_SCRIPT_EFFECT (payload is C++ keyed to the spell id)",
    28:  "SPELL_EFFECT_SUMMON (power lives in creature_template)",
    5:   "SPELL_EFFECT_TELEPORT_UNITS (no magnitude)",
    24:  "SPELL_EFFECT_CREATE_ITEM (no magnitude)",
    38:  "SPELL_EFFECT_DISPEL (no magnitude)",
    100: "SPELL_EFFECT_INEBRIATE (no magnitude)",
    108: "SPELL_EFFECT_DISPEL_MECHANIC (no magnitude)",
    19:  "SPELL_EFFECT_ADD_EXTRA_ATTACKS (no magnitude)",
}

# ── Auras ───────────────────────────────────────────────────────────────────
# Auras whose amount is an absolute magnitude on the item's power budget.
SCALE_AURAS = {
    3,    # PERIODIC_DAMAGE
    8,    # PERIODIC_HEAL
    13,   # MOD_DAMAGE_DONE
    14,   # MOD_DAMAGE_TAKEN                 (flat, and negative on gear)
    15,   # DAMAGE_SHIELD
    22,   # MOD_RESISTANCE
    24,   # PERIODIC_ENERGIZE
    29,   # MOD_STAT
    34,   # MOD_INCREASE_HEALTH              (flat health)
    53,   # PERIODIC_LEECH                   (flat damage per tick)
    69,   # SCHOOL_ABSORB
    85,   # MOD_POWER_REGEN
    99,   # MOD_ATTACK_POWER
    102,  # MOD_MELEE_ATTACK_POWER_VERSUS    (flat AP vs a creature type)
    103,  # MOD_TOTAL_THREAT                 (flat threat reduction)
    115,  # MOD_HEALING                      (flat healing power)
    123,  # MOD_TARGET_RESISTANCE            (flat spell penetration)
    124,  # MOD_RANGED_ATTACK_POWER
    131,  # MOD_RANGED_ATTACK_POWER_VERSUS   (flat RAP vs a creature type)
    135,  # MOD_HEALING_DONE
    158,  # MOD_SHIELD_BLOCKVALUE
    161,  # MOD_HEALTH_REGEN_IN_COMBAT
    180,  # MOD_FLAT_SPELL_DAMAGE_VERSUS
    189,  # MOD_RATING
    250,  # MOD_INCREASE_HEALTH_2            (flat health)
}

# Auras whose amount is a percentage, a duration, a millisecond count or a
# flag -- real, but not a power budget.  Copied through untouched.
#
# 107/108 ADD_FLAT/PCT_MODIFIER are here on purpose: for 107 the UNIT depends
# entirely on EffectMiscValue (SPELLMOD_COOLDOWN and SPELLMOD_ACTIVATION_TIME
# are milliseconds), so a linear scale turns a cooldown reduction into nonsense.
PASSTHROUGH_AURAS = {
    0,    # NONE                             (an unused aura slot)
    12,   # MOD_STUN
    17,   # MOD_STEALTH_DETECT               (a level, not an amount)
    18,   # MOD_INVISIBILITY                 (a level, not an amount)
    19,   # MOD_INVISIBILITY_DETECT
    25,   # MOD_PACIFY                       (no amount)
    26,   # MOD_ROOT                         (no amount)
    27,   # MOD_SILENCE                      (no amount)
    30,   # MOD_SKILL                        (skill is capped at 5 x level)
    31,   # MOD_INCREASE_SPEED
    33,   # MOD_DECREASE_SPEED               (percent)
    36,   # MOD_SHAPESHIFT                   (a form id)
    41,   # DISPEL_IMMUNITY                  (a dispel type in MiscValue)
    52,   # MOD_WEAPON_CRIT_PERCENT          (percent)
    56,   # TRANSFORM
    57,   # MOD_SPELL_CRIT_CHANCE            (percent)
    58,   # MOD_INCREASE_SWIM_SPEED          (percent)
    67,   # MOD_DISARM                       (no amount)
    72,   # MOD_POWER_COST_SCHOOL_PCT        (percent)
    73,   # MOD_POWER_COST_SCHOOL
    74,   # REFLECT_SPELLS_SCHOOL
    76,   # FAR_SIGHT
    77,   # MECHANIC_IMMUNITY                (a mechanic id in MiscValue)
    82,   # WATER_BREATHING
    87,   # MOD_DAMAGE_PERCENT_TAKEN         (percent)
    105,  # FEATHER_FALL
    117,  # MOD_MECHANIC_RESISTANCE          (percent)
    107,  # ADD_FLAT_MODIFIER                (unit chosen by EffectMiscValue)
    108,  # ADD_PCT_MODIFIER
    125,  # MOD_MELEE_DAMAGE_TAKEN
    134,  # MOD_MANA_REGEN_INTERRUPT         (percent)
    138,  # MOD_MELEE_HASTE                  (percent)
    139,  # FORCE_REACTION                   (faction and reaction ids)
    154,  # MOD_STEALTH_LEVEL
    234,  # MECHANIC_DURATION_MOD_NOT_STACK  (percent)
    273,  # X_RAY
}

# Auras whose payload is another spell.
RECURSE_AURAS = {
    23,   # PERIODIC_TRIGGER_SPELL
    42,   # PROC_TRIGGER_SPELL
    109,  # ADD_TARGET_TRIGGER
}

REJECT_AURAS = {
    4: "SPELL_AURA_DUMMY (payload is C++ keyed to the spell id)",
}

# ── Tooltip cross-references ────────────────────────────────────────────────
# "$14181s1" reads effect 1 off spell 14181, and "$@spellname12345" its name.  A
# clone that keeps such a reference shows the ORIGINAL spell's number beside its
# own scaled effect.
#
# The grammar is tooltip_vars._TOKEN rather than a fresh regex.  A naive
# r"\$(\d+)\w" both over- and under-matches: it misses the "$/1000;12536s1"
# form, where the id does not follow the dollar directly, and it has no idea
# which trailing letters are real tokens.  tools/tooltip_vars.py already encodes
# all of that and is exercised by the talent exporter.
from tooltip_vars import _TOKEN as _TOOLTIP_TOKEN  # noqa: E402

# Groups inside _TOKEN that hold a spell id.
_XREF_GROUPS = ("ref", "atnid", "atdid")

TEXT_FIELDS = ("SpellDescription0", "SpellToolTip0")

EFFECT_SLOTS = (1, 2, 3)


class Rejected(Exception):
    """A spell that must not be cloned.  Carries the human-readable reason."""


# Columns the scaling actually writes.  Everything else in a clone is copied
# verbatim from its base spell, so base_spell plus these is a complete identity
# for a cloned payload.
PAYLOAD_COLUMNS = tuple(
    f"{stem}{i}" for stem in
    ("EffectBasePoints", "EffectDieSides", "EffectTriggerSpell")
    for i in EFFECT_SLOTS
)


def payload_key(base_spell, row):
    """Identity of a cloned payload: what it came from, and what it became."""
    return (base_spell,) + tuple(row[c] for c in PAYLOAD_COLUMNS)


def payload_hash(key):
    """Stable short digest of a payload key, for the frozen mapping table.

    repr() of a tuple of ints is stable across Python versions and platforms,
    which is the whole requirement -- this only ever has to match itself.
    """
    return hashlib.blake2b(repr(key).encode("ascii"), digest_size=8).hexdigest()


class Allocator:
    """Hands out spell ids, keyed by PAYLOAD rather than by item.

    Two things are going on here.

    Dedup: the same base spell scaled by the same ratio is the same spell, no
    matter which item asked for it.  Cloning per (item, step) instead produced
    34,433 rows where 11,130 distinct payloads exist -- 32 MB of duplicate
    Spell.dbc against 10 MB.  Since every unscaled column is copied from the
    base spell, base_spell plus PAYLOAD_COLUMNS is a complete identity.

    Freeze: ids are reloaded from alonecraft_item_upgrade_spell and never
    reissued, because live characters carry character_aura and
    character_spell_cooldown rows keyed by spell id.  A rerun with unchanged
    input reproduces every id exactly.

    The freeze is weaker than the per-item version it replaced, and the trade is
    deliberate: a RETUNE changes a payload, which allocates a new id and orphans
    the old one, so a character mid-buff loses it at next login.  These are item
    on-use and proc effects measured in seconds, and the alternative was 22 MB
    of duplicate rows in a file the 32-bit client memory-maps.
    """

    def __init__(self, existing=None, base=SPELL_VARIANT_BASE):
        # {payload_hash: clone_spell_id}, seeded from the frozen mapping table.
        self._map = dict(existing or {})
        # Payloads seen in THIS run.  Deliberately separate from _map -- see get.
        self._seen = set()
        self._next = max(self._map.values()) + 1 if self._map else base
        self.issued = 0

    def get(self, key):
        """Returns (clone_id, emit_row).

        `emit_row` means "first sighting in THIS run", NOT "newly allocated id".
        Conflating the two is a data-loss bug and it got as far as --validate:
        on a rerun every payload is already in the frozen map, so nothing would
        be emitted -- while the generated file still DELETEs the whole id band.
        Every clone would be dropped with 80,000 items still pointing at them.

        The generated SQL has to be self-contained and re-appliable to an empty
        database, so a reused id still needs its row written.
        """
        digest = payload_hash(key)
        if digest not in self._map:
            if self._next >= SPELL_VARIANT_LIMIT:
                raise SystemExit(
                    f"ERROR: spell id band {SPELL_VARIANT_BASE}.."
                    f"{SPELL_VARIANT_LIMIT} is exhausted.")
            self._map[digest] = self._next
            self._next += 1
            self.issued += 1

        emit = digest not in self._seen
        self._seen.add(digest)
        return self._map[digest], emit


def scale_amount(base_points, die_sides, m):
    """Scale an effect's COMPUTED value, not its stored base points.

    CalcValue = BasePoints + max(1, DieSides), so scaling BasePoints alone
    drifts the displayed number by one on every DieSides = 0 spell -- and $s1
    in the tooltip shows the computed value, not the stored one.

    A real random range (DieSides > 1) is preserved rather than scaled: the
    spread is a design property of the spell, the same reasoning that leaves
    weapon `delay` alone in gen_item_variants.
    """
    value = base_points + max(1, die_sides)
    if value == 0:
        return base_points, die_sides

    scaled = round(value * m)
    scaled = max(1, scaled) if value > 0 else min(-1, scaled)

    new_ds = die_sides if die_sides > 1 else 0
    return scaled - max(1, new_ds), new_ds


def classify_effect(row, i):
    """('skip'|'scale'|'pass'|'recurse') for one effect slot. Raises Rejected."""
    effect = row[f"Effect{i}"]
    if effect == 0:
        return "skip"

    if effect in REJECT_EFFECTS:
        raise Rejected(f"Effect{i}={effect}: {REJECT_EFFECTS[effect]}")

    if effect in RECURSE_EFFECTS:
        return "recurse"

    if effect in SCALE_EFFECTS:
        return "scale"

    if effect in AURA_EFFECTS:
        aura = row[f"EffectApplyAuraName{i}"]
        if aura in REJECT_AURAS:
            raise Rejected(f"EffectApplyAuraName{i}={aura}: {REJECT_AURAS[aura]}")
        if aura in RECURSE_AURAS:
            return "recurse"
        if aura in SCALE_AURAS:
            return "scale"
        if aura in PASSTHROUGH_AURAS:
            return "pass"
        raise Rejected(f"EffectApplyAuraName{i}={aura}: unclassified aura")

    if effect in PASSTHROUGH_EFFECTS:
        return "pass"

    raise Rejected(f"Effect{i}={effect}: unclassified effect")


def _rewrite_xrefs(text, id_map):
    """Repoint $<spellid> tooltip references at their clones.

    A reference to a spell that was NOT cloned is left alone and reported, so
    the caller can reject rather than ship a tooltip whose number contradicts
    the effect beside it.
    """
    unresolved = []
    text = text or ""
    edits = []

    for match in _TOOLTIP_TOKEN.finditer(text):
        for group in _XREF_GROUPS:
            raw = match.group(group)
            if not raw:
                continue
            sid = int(raw)
            if sid in id_map:
                edits.append((match.span(group), str(id_map[sid])))
            else:
                unresolved.append(sid)

    # Right to left, so an earlier edit cannot shift a later span.
    for (start, end), replacement in sorted(edits, reverse=True):
        text = text[:start] + replacement + text[end:]

    return text, unresolved


def _plan(sid, idx, scripted_ids, depth, seen):
    """Walk the trigger tree, classifying as it goes.  Raises Rejected.

    Separated from emission because ids cannot be assigned until the payload is
    final, and a parent's payload includes the ids of the children it triggers.
    """
    if depth > MAX_TRIGGER_DEPTH:
        raise Rejected(f"trigger chain exceeds depth {MAX_TRIGGER_DEPTH} at {sid}")
    if sid in seen:
        raise Rejected(f"trigger cycle through spell {sid}")

    src = idx.get(sid)
    if src is None:
        raise Rejected(f"spell {sid} is not in Spell.dbc")
    if sid in scripted_ids:
        raise Rejected(f"spell {sid} has a spell_script_names row, which is "
                       "keyed to the original id")

    kinds = {i: classify_effect(src, i) for i in EFFECT_SLOTS}
    children = {}
    for i, kind in kinds.items():
        if kind != "recurse":
            continue
        child = src[f"EffectTriggerSpell{i}"]
        if child:
            children[i] = _plan(child, idx, scripted_ids, depth + 1, seen | {sid})

    return {"sid": sid, "src": src, "kinds": kinds, "children": children,
            "depth": depth}


def _emit(node, m, alloc, out):
    """Scale one node, allocate its id, append it.  Returns the clone id.

    DEPTH-FIRST, children before parents.  A parent's EffectTriggerSpell holds
    its children's CLONE ids, and that column is part of the payload identity --
    so the children have to be resolved before the parent can be deduplicated
    against anything.
    """
    src, row = node["src"], dict(node["src"])

    for i, kind in node["kinds"].items():
        if kind == "scale":
            bp, ds = scale_amount(src[f"EffectBasePoints{i}"],
                                  src[f"EffectDieSides{i}"], m)
            row[f"EffectBasePoints{i}"] = bp
            row[f"EffectDieSides{i}"] = ds

    id_map = {}
    for i, child in node["children"].items():
        child_id = _emit(child, m, alloc, out)
        row[f"EffectTriggerSpell{i}"] = child_id
        id_map[child["sid"]] = child_id

    for field in TEXT_FIELDS:
        if field not in row:
            continue
        new_text, unresolved = _rewrite_xrefs(row[field], id_map)
        if unresolved:
            raise Rejected(
                f"{field} references spell(s) {sorted(set(unresolved))} that "
                "were not cloned; the tooltip would contradict the effect")
        row[field] = new_text

    key = payload_key(node["sid"], row)
    clone_id, is_new = alloc.get(key)
    row["ID"] = clone_id

    # Only the first sighting is emitted.  A repeat is the same payload by
    # definition, so re-emitting it would just be a duplicate INSERT.
    if is_new:
        out.append({"row": row, "base_spell": node["sid"],
                    "depth": node["depth"], "hash": payload_hash(key)})
    return clone_id


def clone_tree(base_spell, m, alloc, idx, scripted_ids=frozenset()):
    """Clone a spell and everything it triggers, scaled by `m`.

    Returns (root_clone_id, newly_emitted_rows).  The row list is empty when
    every payload in the tree already existed -- the ids are still valid.

    All or nothing: a Rejected anywhere in the tree aborts the whole clone,
    because a half-cloned tree is a parent pointing at an unscaled child.  Ids
    consumed before the exception are simply never persisted.
    """
    node = _plan(base_spell, idx, scripted_ids, 0, frozenset())
    out = []
    root = _emit(node, m, alloc, out)
    return root, out


def scale_item_spells(item, m, alloc, idx, scripted_ids=frozenset(),
                      reasons=None):
    """Clone every scalable spell on one item variant.

    Returns (spell_ids, new_rows, power):

      spell_ids  {1..5: clone_id} for the slots that were cloned.  An absent
                 slot means "leave the base item's spellid_N alone", which is
                 what lets an item with one scalable and one unscalable spell
                 still get a variant.
      new_rows   only payloads not already allocated -- deduplication means most
                 calls return few or none.
      power      summed magnitude of the TOP-LEVEL spells, for the no-op-step
                 test.  Computed here rather than from new_rows, because a
                 deduplicated clone emits no row but still counts.

    A rejected spell is recorded in `reasons` and skipped; it does not reject
    the item.  Whether the item is worth generating at all is the caller's call
    (gen_item_variants asks "did anything gain?").
    """
    spell_ids = {}
    rows = []
    power = 0

    for i in range(1, 6):
        sid = item.get(f"spellid_{i}") or 0
        if sid <= 0:
            continue
        try:
            root, emitted = clone_tree(sid, m, alloc, idx, scripted_ids)
        except Rejected as why:
            if reasons is not None:
                reasons.setdefault(sid, str(why))
            continue
        spell_ids[i] = root
        rows.extend(emitted)
        # Recompute rather than read off `emitted`: a deduplicated root
        # contributes no row, and dropping its magnitude would make the step
        # look like it gained nothing.
        src = idx[sid]
        for slot in EFFECT_SLOTS:
            if not src[f"Effect{slot}"]:
                continue
            bp, ds = scale_amount(src[f"EffectBasePoints{slot}"],
                                  src[f"EffectDieSides{slot}"], m) \
                if classify_effect(src, slot) == "scale" \
                else (src[f"EffectBasePoints{slot}"], src[f"EffectDieSides{slot}"])
            power += bp + max(1, ds)

    return spell_ids, rows, power


def resolve_referenced(spell_id_sets, registry):
    """The clone rows actually reachable from the variants that were kept.

    Necessary because deduplication and no-op-step pruning interact badly if
    you just collect rows as they are emitted.  A payload is emitted the FIRST
    time it is allocated; if that step is then dropped for gaining nothing, the
    row goes with it -- but the allocator still remembers the id, so the next
    variant to want that payload is handed an id with no row behind it.  83
    variants referenced missing spells before this existed, and --validate is
    what caught it.

    So: emit nothing during generation, then walk out from the variants that
    survived.  Children are reached through EffectTriggerSpell, which is why
    this is a closure and not a filter.
    """
    referenced = set()
    queue = [sid for ids in spell_id_sets for sid in ids]
    while queue:
        sid = queue.pop()
        if sid in referenced or sid not in registry:
            continue
        referenced.add(sid)
        row = registry[sid]["row"]
        queue.extend(row[f"EffectTriggerSpell{i}"] for i in EFFECT_SLOTS
                     if row[f"EffectTriggerSpell{i}"])

    # Ascending id order keeps the generated SQL stable between runs.
    return [registry[sid] for sid in sorted(referenced)]


def base_spell_power(item, idx, scripted=frozenset()):
    """The item's own spell magnitude, before any scaling.

    generate() needs this to seed its no-op comparison.  Without it a step whose
    multiplier is 1.0 -- a flat spot in the tier curve -- would read as a gain
    and the player would be charged for an identical item.

    Runs the real cloner at m = 1.0 with a throwaway allocator, rather than a
    parallel "which spells would qualify" implementation that could drift from
    the classifier.
    """
    return scale_item_spells(item, 1.0, Allocator(), idx, scripted)[2]


# ── SQL ─────────────────────────────────────────────────────────────────────

def format_spell_sql(cloned, spell_columns, format_value, batch=200):
    """DELETE + batched INSERTs for alonecraft_spell_dbc, and the audit table.

    `format_value` is gen_sql.format_sql_value, passed in rather than imported
    so this module stays free of the SQL-quoting rules.
    """
    L = []
    A = L.append
    A("-- -- cloned item spells ------------------------------------------------")
    A("-- Items whose entire value is a proc or an on-use effect have no stats to")
    A("-- scale, so the spell itself is cloned per step with its base points")
    A("-- multiplied by the same RandPropPoints ratio the stat path uses.")
    A("--")
    A("-- Ids are dense in a reserved band, NOT derived from the item entry: an")
    A("-- arithmetic encoding reaches ~11.4M and DBCFileLoader allocates")
    A("-- indexTable[maxId + 1] (DBCFileLoader.cpp:201-215), which would cost 91 MB")
    A("-- of null pointers on both server and client for no benefit.")
    A(f"DELETE FROM `alonecraft_spell_dbc` WHERE `ID` BETWEEN {SPELL_VARIANT_BASE} "
      f"AND {SPELL_VARIANT_LIMIT - 1};")
    A("")

    cols = ", ".join(f"`{c}`" for c in spell_columns)
    values = [
        "(" + ", ".join(format_value(e["row"][c], c) for c in spell_columns) + ")"
        for e in cloned
    ]
    for i in range(0, len(values), batch):
        A(f"INSERT INTO `alonecraft_spell_dbc` ({cols}) VALUES")
        A(",\n".join(values[i:i + batch]) + ";")
        A("")

    return "\n".join(L)


def format_mapping_sql(cloned, batch=500):
    """The frozen id mapping.  REPLACE INTO, and never dropped -- see Allocator."""
    L = []
    A = L.append
    A("-- -- frozen spell id mapping -------------------------------------------")
    A("-- Read back by the generator on the next run so ids are never reissued.")
    A("-- Live characters carry character_aura and character_spell_cooldown rows")
    A("-- keyed by spell id; reallocating would silently repoint them.")
    A("-- REPLACE, not DELETE + INSERT: this table accumulates.")
    A("--")
    A("-- Keyed by payload, not by item: the same base spell scaled by the same")
    A("-- ratio is the same spell whoever asked for it, and cloning per item")
    A("-- instead produced 34,433 rows for 11,130 distinct payloads.  So one")
    A("-- clone_spell serves many variants -- ask item_template which:")
    A("--   SELECT entry FROM item_template WHERE spellid_1 = <clone> ...")
    A("CREATE TABLE IF NOT EXISTS `alonecraft_item_upgrade_spell` (")
    A("  `clone_spell`  INT UNSIGNED NOT NULL PRIMARY KEY,")
    A("  `base_spell`   INT UNSIGNED NOT NULL,")
    A("  `payload_hash` CHAR(16) NOT NULL,")
    A("  `depth`        TINYINT UNSIGNED NOT NULL,")
    A("  UNIQUE KEY `idx_payload` (`payload_hash`),")
    A("  KEY `idx_base` (`base_spell`)")
    A(") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;")
    A("")

    rows = [
        "({}, {}, '{}', {})".format(
            e["row"]["ID"], e["base_spell"], e["hash"], e["depth"])
        for e in cloned
    ]
    for i in range(0, len(rows), batch):
        A("REPLACE INTO `alonecraft_item_upgrade_spell` (`clone_spell`, "
          "`base_spell`, `payload_hash`, `depth`) VALUES")
        A(",\n".join(rows[i:i + batch]) + ";")
        A("")

    return "\n".join(L)


def format_proc_sql(proc_rows, proc_columns, batch=500):
    """Clone spell_proc rows onto the cloned spells.

    spell_proc is declarative, so unlike spell_script_names it carries across
    cleanly -- the row is copied verbatim with only SpellId repointed.  51 of
    the 402 spells in scope have one, and without this their procs would simply
    stop firing on an upgraded item.
    """
    if not proc_rows:
        return ""

    L = []
    A = L.append
    A("-- -- cloned spell_proc rows ---------------------------------------------")
    A(f"DELETE FROM `spell_proc` WHERE `SpellId` BETWEEN {SPELL_VARIANT_BASE} "
      f"AND {SPELL_VARIANT_LIMIT - 1};")
    A("")
    cols = ", ".join(f"`{c}`" for c in proc_columns)
    values = [
        "(" + ", ".join(str(r[c]) for c in proc_columns) + ")" for r in proc_rows
    ]
    for i in range(0, len(values), batch):
        A(f"INSERT INTO `spell_proc` ({cols}) VALUES")
        A(",\n".join(values[i:i + batch]) + ";")
        A("")

    return "\n".join(L)


# ── census ──────────────────────────────────────────────────────────────────

def _census():
    """Report what the whitelist currently turns away, and why.

    The whitelist fails closed, so an unclassified effect or aura costs an item
    its upgrade path silently.  This is how that stays visible: run it after any
    change to the tables above, and after any content import.
    """
    import os
    import sys
    from collections import Counter

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gen_item_variants as giv
    sys.path.insert(0, giv.DBC_DIR)
    import config
    import spell_dbc

    conn = giv.get_db_connection()
    rows = giv.fetch_candidates(conn)
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT ABS(spell_id) FROM spell_script_names")
    scripted = {r[0] for r in cur.fetchall()}
    cur.close()
    conn.close()

    idx = spell_dbc.load_spell_index(config.BASE_DBC_PATH)

    withspell = [r for r in rows
                 if any((r.get(f"spellid_{i}") or 0) > 0 for i in range(1, 6))]

    spells = sorted({r[f"spellid_{i}"] for r in withspell for i in range(1, 6)
                     if (r.get(f"spellid_{i}") or 0) > 0})

    ok, reasons = 0, Counter()
    for sid in spells:
        try:
            clone_tree(sid, 1.0, Allocator(), idx, scripted)
            ok += 1
        except Rejected as why:
            # Bucket by the classification, not the specific slot number.
            reasons[re.sub(r"^Effect(ApplyAuraName)?\d", r"Effect\1N", str(why))] += 1

    print(f"items carrying a spell : {len(withspell)}")
    print(f"distinct item spells : {len(spells)}")
    print(f"scalable             : {ok} ({100.0 * ok / max(1, len(spells)):.0f}%)")
    print("rejected:")
    for why, n in reasons.most_common():
        print(f"  {n:4d}  {why}")


if __name__ == "__main__":
    _census()
