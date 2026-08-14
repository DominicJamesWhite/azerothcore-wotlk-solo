#!/usr/bin/env python3
"""The specs the balance matrix covers, and what each one needs to run.

One row per playable talent tree, thirty-one in all (druid has four PvE trees
because bear and cat are separate rotations sharing one tab). Everything that
differs between specs lives here so that sim_matrix.py, fetch_wowsims_gear.py
and sim.py cannot disagree about what "shadow priest" means.

Fields
------
key       stable identifier; names the gear file and the result file
premade   the playerbots spec name (AiPlayerbot.PremadeSpecName.<class>.<n>),
          passed through to --sim-spec. Matched case-insensitively by
          SimRunner::ResolveSpec, so it must be the name and not the index.
role      dps / tank / healer. A healer measured on a damage test is not
          broken because it does little damage, and the report says so rather
          than ranking it last.
wowsims   path in github.com/wowsims/wotlk to the tier-7 (P1) gear set used as
          this spec's fixed equipment.
actor     a level-80 character of the right class in acore_characters_sim.
yards     how far from the target the fight starts. Melee close the gap
          themselves; ranged specs are placed where they actually fight, which
          for a hunter is not optional -- five yards is inside the minimum
          range of every shot it has, and all three hunter specs measured
          63-92 DPS with every point of it coming from the pet.
tab       the talent tab (0/1/2) this spec must end up with most of its points
          in. Checked against what the run actually produced: PlayerbotFactory
          applies its talent template without resetting first, so a character
          stored in another tree silently keeps it, and every paladin in the
          first full matrix measured a holy rotation whatever spec was asked
          for. The simulator resets talents now; this is what proves it.

Why P1 and not "ilvl 200" exactly
---------------------------------
There is no single ilvl-200 set: Naxxramas-10 drops 200, Naxxramas-25 drops
213, and the P1 lists mix in 226 from Malygos and Sartharion. What matters for
a balance matrix is that every spec is equally geared, not that the number is
round -- so the runner reports the mean item level it actually equipped, per
spec, and the comparison can be checked instead of trusted.

Some sets are shared, and that is deliberate rather than an omission:
wowsims models demonology and destruction on one gear list, and has no
beast-mastery list at all (BM and MM wear the same hunter gear).
"""

CLASS_NAMES = {
    1: "Warrior", 2: "Paladin", 3: "Hunter", 4: "Rogue", 5: "Priest",
    6: "Death Knight", 7: "Shaman", 8: "Mage", 9: "Warlock", 11: "Druid",
}

# Actors: one level-80 character per class, taken from acore_characters_sim
# with
#   SELECT class, MIN(name) FROM characters WHERE level = 80 GROUP BY class;
# They are ordinary random-bot characters. Pinned rather than re-queried so a
# rerun measures the same body -- race matters for a few percent of stats, and
# a spec whose actor changed between runs is not a comparison.
ACTORS = {
    1: "Adlass", 2: "Aelelda", 3: "Bloliwe", 4: "Aleidel", 5: "Ahedrimus",
    6: "Aralteren", 7: "Akdiir", 8: "Apold", 9: "Alenleron", 11: "Ceros",
}

# Targets, by what the pass is asking.
#
# DUMMY_TARGET is inert: it holds 13.9M health and hits for 0.01x, so it can
# neither die nor kill. That is exactly right for a damage number and useless
# for anything else -- the solo-clear fraction has been structurally 0 for as
# long as it has existed, because there was no fight to win or lose.
#
# CLEAR_TARGET is the sparring dummy added in woa_2026_08_14_00.sql: the same
# level and armour, but 363k health and 2.0x damage, so both sides can win.
# Pinned here for the same reason ACTORS is pinned -- a target that changed
# between runs is not a comparison -- and its two numbers are the difficulty
# dial for the whole fork.
DUMMY_TARGET = 2000100
CLEAR_TARGET = 2000110

# Real creatures, by name, for `--target` and `--clear-target`.
#
# Anything that is not one of the simulator's own dummies keeps its own AI,
# script, abilities and aggression -- that already worked by entry id, and this
# is only so nobody has to remember that Patchwerk is 16028.
#
# These are Naxxramas-25 bosses at level 83, HealthModifier 200-480 and
# DamageModifier 35. That is 17x the sparring dummy's damage and roughly 10x its
# health, so expect a solo spec in P1 gear to lose, and to lose quickly. That is
# the point of having them: the sparring dummy answers "how much does this build
# reduce damage taken", a real boss answers "is this survivable at all", and the
# second question needs a real answer before the fork claims solo raids work.
#
# Chosen for being mechanically simple enough that the number means something:
#
#   patchwerk   the standard tank-and-spank. Pure melee, no adds, no phases --
#               the closest thing to a pure survivability test in the game.
#   thaddius    highest health of the four, and hits hardest.
#   loatheb     480 health modifier, the longest fight.
#   gluth       a decurse/enrage check rather than pure damage.
#
# Deliberately NOT included: Kel'Thuzad, Sapphiron, Gothik, Flame Leviathan and
# anything else whose script summons adds, changes phase or requires a vehicle.
# Those measure the script, not the spec, and a solo actor cannot satisfy them.
BOSS_TARGETS = {
    "patchwerk": 16028,
    "thaddius":  15928,
    "loatheb":   16011,
    "gluth":     15932,
}


# Where the fight happens. (map, x, y, z, why).
#
# This is not cosmetic: mod-autobalance gates every scaling path on
# map->IsDungeon(), so the arena decides whether --autobalance does anything at
# all. GM Island is a continent and can never be scaled.
#
# Emerald Dream is the empty instance. InstanceType 2 (raid, so IsDungeon is
# true), zero creature spawns in the whole map, 256 terrain tiles extracted, and
# Verdant Fields is open ground. Alternatives were rejected on data: the
# "<unused> Monastery" (44) is a party dungeon with no spawns but *no extracted
# terrain at all*, exactly like Development Land (451), and Onyxia's Lair (249)
# has none either. Every battleground and arena map is InstanceType 3 or 4, which
# IsDungeon() does not cover.
#
# Emerald Dream has no mmaps, so creature movement falls back to straight lines.
# In an empty open field that is a feature rather than a limitation -- there is
# nothing to path around, and one less source of run-to-run variation.
#
# A real boss room is NOT an option and the temptation should be resisted:
# Patchwerk summons his adds the instant he is attacked in his own chamber, and
# every other encounter has its own version of that. Measuring a spec against a
# script is not measuring the spec.
#
# Autobalancing an empty map needs one row of LFG data (woa_2026_08_14_01.sql):
# AutoBalance reads the level band from LFGDungeons, not from resident
# creatures, and a map with no entry has band (0,0) and is never scaled.
ARENAS = {
    "gm": (1, 16226.6, 16257.0, 13.2,
           "GM Island. A continent, so mod-autobalance never applies -- the "
           "default, and the one every existing number was measured on."),
    "instance": (169, -2128.12, -1005.89, 132.213,
                 "Emerald Dream, Verdant Fields. An empty raid instance, so "
                 "creatures can be autobalanced as a solo player meets them."),
}


def resolve_target(value, default=None):
    """A target name or entry id -> entry id.

    Accepts 'patchwerk', '16028', 'dummy', 'sparring'. Raises on an unknown
    name rather than guessing, because a typo silently fighting the wrong
    creature is exactly the class of error this file exists to prevent.
    """
    if value is None:
        return default
    key = str(value).strip().lower()
    if key in ("dummy", "inert"):
        return DUMMY_TARGET
    if key in ("sparring", "spar"):
        return CLEAR_TARGET
    if key in BOSS_TARGETS:
        return BOSS_TARGETS[key]
    if key.isdigit():
        return int(key)
    raise SystemExit(
        f"unknown target '{value}'. Use an entry id, or one of: "
        f"dummy, sparring, {', '.join(sorted(BOSS_TARGETS))}")


def _WS(sim, set_name):
    return f"ui/{sim}/gear_sets/{set_name}.gear.json"


def _spec(key, cls, premade, role, wowsims, tab, yards):
    return {
        "key": key,
        "tab": tab,
        "range": yards,
        "class": cls,
        "class_name": CLASS_NAMES[cls],
        "premade": premade,
        "role": role,
        "wowsims": wowsims,
        "actor": ACTORS[cls],
    }


SPECS = [
    _spec("warrior_arms",    1, "arms pve",    "dps",    _WS("warrior", "p1_arms"), 0, 5),
    _spec("warrior_fury",    1, "fury pve",    "dps",    _WS("warrior", "p1_fury"), 1, 5),
    _spec("warrior_prot",    1, "prot pve",    "tank",   _WS("protection_warrior", "p1_balanced"), 2, 5),

    _spec("paladin_holy",    2, "holy pve",    "healer", _WS("holy_paladin", "p1"), 0, 5),
    _spec("paladin_prot",    2, "prot pve",    "tank",   _WS("protection_paladin", "p1"), 1, 5),
    _spec("paladin_ret",     2, "ret pve",     "dps",    _WS("retribution_paladin", "p1"), 2, 5),

    # No BM list upstream; BM and MM wear the same hunter gear.
    _spec("hunter_bm",       3, "bm pve",      "dps",    _WS("hunter", "p1_mm"), 0, 30),
    _spec("hunter_mm",       3, "mm pve",      "dps",    _WS("hunter", "p1_mm"), 1, 30),
    _spec("hunter_surv",     3, "surv pve",    "dps",    _WS("hunter", "p1_sv"), 2, 30),

    _spec("rogue_assn",      4, "as pve",      "dps",    _WS("rogue", "p1_assassination"), 0, 5),
    _spec("rogue_combat",    4, "combat pve",  "dps",    _WS("rogue", "p1_combat"), 1, 5),
    _spec("rogue_sub",       4, "subtlety pve", "dps",   _WS("rogue", "p1_hemosub"), 2, 5),

    _spec("priest_disc",     5, "disc pve",    "healer", _WS("healing_priest", "p1_disc"), 0, 30),
    _spec("priest_holy",     5, "holy pve",    "healer", _WS("healing_priest", "p1_holy"), 1, 30),
    _spec("priest_shadow",   5, "shadow pve",  "dps",    _WS("shadow_priest", "p1"), 2, 30),

    _spec("dk_blood",        6, "blood pve",   "dps",    _WS("deathknight", "p1_blood"), 0, 5),
    _spec("dk_frost",        6, "frost pve",   "dps",    _WS("deathknight", "p1_frost"), 1, 5),
    _spec("dk_unholy",       6, "unholy pve",  "dps",    _WS("deathknight", "p1_uh_2h"), 2, 5),

    _spec("shaman_ele",      7, "ele pve",     "dps",    _WS("elemental_shaman", "p1"), 0, 30),
    _spec("shaman_enh",      7, "enh pve",     "dps",    _WS("enhancement_shaman", "p1"), 1, 5),
    _spec("shaman_resto",    7, "resto pve",   "healer", _WS("restoration_shaman", "p1"), 2, 30),

    _spec("mage_arcane",     8, "arcane pve",  "dps",    _WS("mage", "p1_arcane"), 0, 30),
    _spec("mage_fire",       8, "fire pve",    "dps",    _WS("mage", "p1_fire"), 1, 30),
    _spec("mage_frost",      8, "frost pve",   "dps",    _WS("mage", "p1_frost"), 2, 30),

    _spec("warlock_affli",   9, "affli pve",   "dps",    _WS("warlock", "p1_affliction"), 0, 30),
    # One list upstream for demonology and destruction.
    _spec("warlock_demo",    9, "demo pve",    "dps",    _WS("warlock", "p1_demodestro"), 1, 30),
    _spec("warlock_destro",  9, "destro pve",  "dps",    _WS("warlock", "p1_demodestro"), 2, 30),

    _spec("druid_balance",  11, "balance pve", "dps",    _WS("balance_druid", "p1"), 0, 30),
    _spec("druid_cat",      11, "cat pve",     "dps",    _WS("feral_druid", "p1"), 1, 5),
    _spec("druid_bear",     11, "bear pve",    "tank",   _WS("feral_tank_druid", "p1"), 1, 5),
    # Five yards, not thirty, and that is an Alonecraft deviation rather than an
    # oversight. Restoration's redesign is a melee hybrid: Bloomstrike (200000)
    # procs off auto-attacks and scales with the druid's own HoTs on itself, and
    # Living Spores (200001) is a weapon imbue applied by melee hits. Measured
    # from thirty yards none of that can happen, and the spec reads as a weak
    # caster -- the same failure the hunters had in reverse.
    _spec("druid_resto",    11, "resto pve",   "healer", _WS("restoration_druid", "p1"), 2, 5),
]

# Alonecraft deviations from the imported wowsims sets, applied after the import
# rather than baked into sims/gear/*.json -- fetch_wowsims_gear.py --check keeps
# validating the pristine upstream list, and the reason for each change stays
# here next to the spec it belongs to.
GEAR_SWAPS = {
    # Empty, and worth keeping the mechanism for the next time it is needed.
    #
    # Tried and rejected for druid_resto: swapping the wowsims 1.8s one-hander
    # plus off-hand holdable for Damnation (40348), the fast tier-213 caster
    # staff, on the theory that Bloomstrike's flat component scales with spell
    # power as its DBC row implies (EffectBonusMultiplier2 = 1.0).
    #
    # It does not. Spell power went 660 -> 1121 and Bloomstrike's average hit
    # went 3142 -> 3052, while melee swing damage rose 427 -> 487, proving the
    # gear applied. The coefficient is inert because Bloomstrike is
    # SPELL_EFFECT_WEAPON_PERCENT_DAMAGE -- weapon damage class -- and spell
    # power coefficients only apply to magic-class damage. Net result was 1827
    # -> 1688 DPS, losing procs to the slower swing for nothing in return.
    #
    # The lesson for gearing this spec: attack power, weapon damage and weapon
    # SPEED matter to Bloomstrike; spell power does not.
}


def apply_gear_swaps(key, items):
    """The spec's equipment list with any Alonecraft swap applied."""
    swap = GEAR_SWAPS.get(key)
    if not swap:
        return items

    out = [i for i in items if i["id"] not in swap.get("remove", ())]
    out.extend(swap.get("add", ()))
    return out


BY_KEY = {s["key"]: s for s in SPECS}


def resolve(names):
    """Spec rows for a list of keys, class names or roles; all of them if empty."""
    if not names:
        return list(SPECS)

    out, seen = [], set()
    for name in names:
        needle = name.lower()
        matched = [s for s in SPECS
                   if s["key"] == needle
                   or s["role"] == needle
                   or s["key"].startswith(needle + "_")
                   or s["class_name"].lower() == needle]
        if not matched:
            raise SystemExit(f"no spec matching '{name}'. Known keys: "
                             + ", ".join(s["key"] for s in SPECS))
        for s in matched:
            if s["key"] not in seen:
                seen.add(s["key"])
                out.append(s)
    return out
