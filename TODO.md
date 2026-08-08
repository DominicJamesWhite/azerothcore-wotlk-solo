# Alonecraft

An attempt to make WOW better to play alone or in very small groups.

> **Note:** I do not, have never, and never will care about PVP - so the balance there is totally dead, I’m sorry. Probably duels will take 3000 years to complete, and BGs & Arenas are unplayable. Best of luck.

---

## Key Changes

- [x] All classes get a Diablo-like potion that can be used to refill 50% of health and mana every 30 seconds. 
- [ ] Other potions all provide temporary combat bonuses as well as their healing and mana restoration.
- [x] mod-autobalance is used to allow solo play in dungeons and raids, and scale their difficulty with more players. 
- [x] Casting pushback from enemy damage is removed entirely. (4.11)
- [x] Talents are boosted to provide more impact in levelling and solo play.
- [x] More NPCs in major cities and towns, and between them doing courier or transport work.
- [ ] Each tree now has changed talents relating to holy trinity specs’ inherent weaknesses while retaining class character.
- [ ] Retuned and redesigned dungeon and raid encounters with lots of new difficulty settings to allow solo progression.
- [x] A living auction house — `mod-ah-bot-plus` both stocks it and buys from it, so loot is worth something and professions have a supply chain without other players.
- [x] 10x levelling XP, with the low-level XP *range* widened to match so a zone keeps paying while you finish it.
- [x] Gear upgrades — any uncommon+ item can be reforged to your level, so a piece you like is never outlevelled.
- [x] A Quartermaster who mails you spec-appropriate gear each level, and 8x quest gold, so income keeps pace with 10x XP.

## Levelling XP

Quests grant 10x XP and 8x gold for markedly quicker leveling.

## Item Upgrades

Solo, you cannot farm a drop on demand, so an item you like is outlevelled and gone.
Any uncommon-or-better equippable item can instead be **reforged to your level**.

**Artificer Volen** (creature 200011) sells 16 consumable upgrade tools, one per
target level (5, 10 … 80) — items 200100–200115, spells 201000+. Using one gives the
item-targeting cursor (the sharpening-stone interaction) and clicking an item
upgrades it.

## The Quartermaster

10x XP without 10x loot means you level roughly ten times faster than equipment
and money arrive, so you outrun your gear and cannot afford what the game still
charges. Two separate fixes.

**Gear.** On each level-up **The Quartermaster** (creature 200012, a mail sender
with no spawn) mails **3 items, each in a different equipment slot**, chosen for
your class and your *active* spec. Items come from the upgrade variants that
already exist for the reforge system, so nothing new is generated.

## Economy

Solo play breaks the auction house: nobody is selling, so nothing you need is ever
listed, and nobody is buying, so your loot is vendor-trash. `mod-ah-bot-plus`
supplies both sides. Its money is fiat — gold spent on a bot listing is destroyed,
gold the buyer bot pays you is created — so the two halves are a sink and a faucet
rather than a closed economy.

## Class Changes
- [x] Resto druid 
    - [ ]  Tuning
- [ ] Balance druid 
    - [ ]  Tuning
- [ ] Feral druid 
    - [ ]  Tuning
- [x] Resto Shaman 
    - [ ]  Tuning
- [x] Enh shaman 
    - [ ]  Tuning
- [ ] Ele shaman 
    - [ ]  Tuning
- [x] Holy priest 
    - [ ]  Tuning
- [x] Disc priest
    - [ ]  Tuning
- [x] Shadow priest
    - [ ]  Tuning
- [x] Holy paladin 
    - [ ]  Tuning
- [ ] Prot paladin
    - [ ]  Tuning
- [ ] Retri paladin
    - [ ]  Tuning
- [x] Affli lock 
    - [ ]  Tuning
- [ ] Demo lock
    - [ ]  Tuning
- [x] Destro lock
    - [ ]  Tuning
- [x] Fire mage 
    - [ ]  Tuning
- [x] Arcane mage
    - [ ]  Tuning
- [x] Frost mage
    - [ ]  Tuning
- [x] Sub rogue 
    - [ ]  Tuning
- [ ] Ass rogue
    - [ ]  Tuning
- [ ] Combat rogue
    - [ ]  Tuning
- [x] Unholy dk 
    - [ ]  Tuning
- [x] Blood dk
    - [ ]  Tuning
- [x] Frost dk
    - [ ]  Tuning
- [ ] MM hunter
    - [ ]  Tuning
- [ ] BM hunter
    - [ ]  Tuning
- [ ] Surv hunter
    - [ ]  Tuning

### Death Knight

**Talent Changes:**
- [x] **Subversion:** Threat no longer affected. Instead increases parry.
- [x] **Improved Rune Tap:** Additionally Rune Tap increases your Heart Strike and Death Strike damage by X% for Ys. (4.46)
- [x] **Vendetta (Renamed to Bloody Lesions):** Redesigned. Blood Boil now leaves your enemies with bleeding lesions, dealing X damage over Ys, and refreshes the duration of diseases on affected enemies. (4.46)
- [x] **Mark of Blood:** Redesigned. Place a Mark of Blood on the enemy. X% of the healing you do to yourself is done to the marked enemy. Parrying an attack from a marked enemy opens them up for a counter-attack, increasing your armor penetration by X% for Ys. (4.46)
- [x] **Improved Blood Presence:** Swapping presences no longer costs runes. While in Blood Presence you do an additional X% damage, and you retain your healing bonus in other presences. (4.46)
- [x] **Will of the Necropolis:** Additionally, doing damage with Heart Strike increases your parry chance by X%. Stacks Y times. (4.46)
- [x] **Runic Power Mastery:** Spending Runic Power has a chance to restore X% of your health. Additionally increases your maximum runic power by Y. (4.46)
- [x] **Chillblains:** Victims of your Frost Fever disease are Chilled, reducing movement speed by X% for 10 sec. When Frost Fever does damage to a Chilled target, there is a chance to drain X health from the target and transfer it to the Death Knight.
- [x] **Hungering Cold:** Purges the earth around the Death Knight of all heat. Enemies within 10 yards are trapped in ice, preventing them from performing any action for 10 sec and infecting them with Frost Fever. After they thaw, X health is drained from them and transferred to the Death Knight.
- [x] **Improved Frost Presence:** Swapping presences no longer costs runes. While in Frost Presence you take X% less damage, and you retain your armor bonus in other presences. (4.49)
- [x] **Acclimation:** When you are hit by a spell, you have an X% chance to reduce the damage of spells from that school by Y% for Zs.
- [x] **Virulence:** Increases your chance to hit with spells by X% and increases the duration of your diseases by X seconds.
- [x] **Anticipation:** Increases your dodge chance and disease damage by X%.
- [x] **Master of Ghouls:** Redesigned. Raise Dead summons 3 additional ghouls and Army of the Dead raises twice as many undead soldiers. (4.55)
- [x] **Hungry Dead:** Redesigned. Ghouls do 4/7/10% more damage for each of your diseases on the target. (4.55)
- [x] **Ghoul Frenzy:** Removed. (4.55)
- [x] **Crypt Fever:** Your diseases cause Crypt Fever, increasing disease damage done to the target by X% and dealing Y damage (50% of Blood Plague) every 3 seconds.
- [x] **Ebon Plaguebringer:** Your diseases also cause Ebon Plague, increasing magical damage taken by X% and dealing Y damage (50% of Frost Fever) every 3 seconds.
- [x] **Epidemic:** For each of your diseases on an enemy, increase your shadow damage against them by 8/15%.
- [x] **Unholy Blight:** Dispel protection is removed. Instead targets affected by Unholy Blight have a reduced chance to hit (shared with Imp Faerie Fire, etc.) (4.57)
- [x] **Unholy Command:** Reduces the cooldown on Death Grip by X%, and SOMETHING ELSE.
- [x] **Corpse Explosion (Renamed to Grim Prophecy):** Redesigned. Using Scourge Strike or Death Strike with a two-handed weapon has a 30% chance to increase your dodge chance by 5%.
- [x] **On a Pale Horse (Renamed to Harvest of Souls):** Redesigned. Your Death Strike now drains life from diseased enemies within 15 yards, draining (~blood plague damage per tick) life every 5 seconds for each disease and transferring it to you. (This should be a new disease applied when Death Strike hits, added to nearby enemies)
- [x] **Desecration:** Your Blood Strikes and Blood Boil desecrate the ground under you. Targets in the area are slowed by X% by the grasping arms of the dead, and they take Y% more damage from your diseases. Lasts Zs. (4.57)
- [x] **Magic Suppression (Renamed to Magic Siphon):** Redesigned. Your Anti-Magic Shell absorbs an additional 8/16/25% of spell damage, and 10/20/30% of damage absorbed is returned to you as health.
- [x] **Anti-Magic Zone:** Max absorb removed. Reduction reduced by 50%.
- [x] **Improved Unholy Presence:** Swapping presences no longer costs runes. While in Unholy Presence your attack speed is increased by X%, and you retain your attack speed bonus in other presences. (4.57)
- [x] **Bone Shield:**  Also your auto-attacks chip away enemy bones and add a charge. This effect can only occur once every second.
- [x] **Summon Gargoyle (Renamed to Summon Reanimated Sorceror):** It’s an necromancer model (NPC ID 31155) instead of a gargoyle because I hate that fucking thing.


### Druid

**Class Changes:**
- [x] Tree form now uses a cool-as-fuck arakkoa instead of a lame treant. (4.1) Also can use Balance spells. (4.2)

**Spec Themes:**
- [ ] **Balance:** Summons healing trees.
- [ ] **Feral:** Dodging restores rage and energy; swapping between forms increases armor (Bear) or Dodge (Cat).

**Talent Changes:**
- [x] **Nature’s Reach:** Threat no longer affected. Instead increases spell crit. (4.2)
- [x] **Nature’s Focus:** Casting Wrath refreshes rejuvenation on yourself to its full duration. (4.12)
- [x] **Subtlety:** Redesigned. Your chance to be hit by enemies is reduced by X%. (4.2)
- [x] **Naturalist:** Also reduces the mana cost of all healing spells by X% (from Tranquil Spirit).
- [x] **Master Shapeshifter:** Grants an effect which lasts while the Druid is within the respective shapeshift form. Bear Form increases physical damage and armor by X%. Cat Form increases critical strike chance and dodge by X%.Moonkin Form increases spell damage by X%. Arakkoa Form increases spirt by X%. 
- [x] **Improved Rejuvenation (Renamed Bloomstrike):** For each of your own healing effects on yourself, your melee attacks are boosted by natural energy, causing X% additional nature damage per effect (4.3)
- [x] **Tranquil Spirit (Renamed to Spirit of the Storm):** Redesigned. As you cast healing spells you build up charges of living energy, increasing the damage and reducing the cast time of Starfire by 10%. Stacks 10 times. (4.6)
- [x] **Improved Tranquility (Renamed to Lunar Storm):** Redesigned. Casting Hurricane on a target affected by your Moonfire unleashes explosive natural energies, damaging targets within 8 yards for $200015s1 each second. (4.7)
- [x] **Gift of Nature:** Redesigned. When you are healed by one of your own heal over time spells, your next Wrath has an X% chance to be instant cast and cost no mana. Additionally increases the damage and healing of your spells by X%. (4.5)
- [x] **Swiftmend:** Using Swiftmend on yourself creates an explosion of natural energy, damaging enemies for X damage. (4.8)
- [x] **Living Spirit:** Spellpower increased by 100% of spirit and int
- [X] **Empowered Touch:** Redesigned. After using Healing Touch, Regrowth or Nourish, your weapon is imbued with living energy, damaging the next enemy you strike in melee for X nature damage over Y seconds or increasing the healing of your next spell by 5%. (4.4) 
- [x] **Nature’s Bounty:** Also increases your Bloomstrike critical strike chance by X%. (4.9)
- [x] **Natural Perfection (Renamed to Grace of Elune):** Your critical strike chance with all spells is increased by $s2%. When you take damage you have a chance to gain the Grace of Elune effect reducing all damage taken by X%.  Stacks up to 5 times.  Lasts Z seconds. (4.13)
- [x] **Living Seed:** More powerful to account for all the stuff I've taken away (4.13)
- [X] **Arakkoa:** Reduces the mana cost and cast time of your healing over time spells by X% and grants the ability to shapeshift into the Arakkoa. While in this form you increase healing received by X% for all party and raid members within 100 yards and your nature damage is increased by Y%. (4.1)
- [x] **Improved Arakkoa:** Spell power increased by spirit (4.12)
- [x] **Improved Barkskin:**: Increases the damage reduction provided by Barkskin by X%, and reduces the cooldown by Y s.(4.14)
- [x] **Gift of the Earthmother:** When you are healed by your Lifebloom after it has completed its duration or been dispelled, you do damage to all enemies within 10 yards for 100% of the healing done. Additionally Increases your total spell haste by X% and reduces the base cooldown of your Lifebloom spell by Y%. (4.12)

**Class Signature Skill:**
- [ ] **Shifting Balance:** Moving to a different form buffs the form temporarily - bears get X% more armor, cats get X% more damage and dodge, moonkin / tree / no form gets X% spell damage and healing.

### Hunter

**Spec Themes:**
- [ ] **Beast Mastery:** Pet armor and health is boosted.
- [ ] **Marksmanship:** Your attacks reduce the damage taken by pets.
- [ ] **Survival:** Traps reduce enemy damage.

**Class Signature Skill:**
- [ ] **Primal Bond:** Damage you do heals your pet and damage your pet does increases your armor.

### Mage

**Skill changes**
- [x] **Mage Armor:** Reduces your chance to be hit by your intellect and spirit * 2 / level. (4.15)
- [x] **Molten Armor:** 50% of damage taken is converted to Ember Scars that deal their damage periodically. Embers can be removed by spell critical hits. (4.16) (Full functionality in 4.30)
- [x] **Ice Armor:** Increase armor by (2x each rank), modified by your spellpower. (4.18)
- [x] **Amplify Magic (Renamed to Aegis of Antonidas)**: You focus your magical power on building a mystical bulwark, increasing healing taken by $s2 and boosting your armor's power for 10 seconds. Mage Armor reduces your chance to be hit by 50% and regenerates mana each second. Molten Armor reduces damage taken by 40% and increases your chance to critically hit with spells by 20%. Frost and Ice Armor increases armor by 40% and spell casting speed by 30%. (4.17)
- [x] **Dampen Magic (Renamed to Invocation)**: For 12 seconds your spells' mana cost is reduced by 50% and your spellpower is increased by X. (4.18)

**Talent Changes:**
- [x] **Arcane Subtlety:** Threat and dispel chance no longer affected. Instead reduces your chance to be hit. (4.19)
- [x] **Arcane Fortitude:** Increases armor by X% of Int and increases Mana Shield spellpower boost by X%. (4.19)
- [x] **Arcane Shielding (Renamed to Prismatic Shielding):** Mana Shield reduces damage taken by x%. (4.19)
- [x] **Arcane Stability:** Casting Arcane Missiles has an $s1% chance to reset the cooldown on Invocation. (4.20) (Revised in 4.22) 
- [x] **Magic Absorbtion:** Attacks taken while protected by Mana Shield also have a chance equal to your critical strike chance to only do 50% damage. (4.21) (Fixed in 4.28)
- [x] **Magic Attunement (Renamed to Arcane Attunement):** Spells cast during Invocation refund double their cost in mana. (4.21)
- [x] **Prismatic Cloak:** Reduces all damage taken by 18% (from 6%) (4.21)
- [x] **Improved Counterspell (Renamed to Practiced Silence):** Silence and Interrupt effects reduces by 90%. (4.22)

- [x] **Fiery Payback**: Redesigned. Damage taken at <35% health reduced by 12/25% 
- [x] **Burning Soul (Renamed Cleansing Flame):** Threat no longer affected. Instead fire spells heal you for 50% of they damage they cause when using Molten Armor, and fire critical hits are twice as effective at removing Ember Scars. (4.23)
- [x] **Molten Shields**: Redesigned. Fire Ward restores mana when it absorbs fire damage. 
- [x] **Burning Determination:** Silence immunity lasts the duration, not just for the next silence. (4.23)
- [x] **Impact (Renamed to Firebreak):** Redesigned. Fire Blast does 20% more damage for each stack of Ember Scars, and removes a stack of Ember Scars when cast. (4.22)
- [x] **Playing With Fire (Renamed to Spark of Al'ar):** Redesigned. Damage that would otherwise kill you instead causes you to be healed by up to 30% of your maximum health and clears all stacks of Ember Scars. (4.23)

- [x] **Frozen Core:** Redesigned. Increases the bonus armor from Ice Armor by 400% of your spell power. (4.25)
- [x] **Frost Warding (Renamed to Glacier Armor):** Ice Block gradually restores 50% of your health when used. (4.30)
- [x] **Improved Blizzard (Renamed to Catabatic Winds):** Increases the damage of Cone of Cold by 50/100% and adds a chill effect to your Blizzard spell, lowering the target's movement speed by 25% for 1.50 sec.
- [x] **Improved Cone of Cold (Renamed to Convection):** Redesigned. Each time you deal damage with Frostbolt or Blizzard, you gain a stack of Convective Currents, empowering your spells. Max 5 stacks. Cone of Cold: Freezes the aira around you, dealing $200037s2% more damage per stack. Ice Lance: Transfers heat from the target, healing you for 300% of the damage done per stack. Frostfire Bolt: Increases periodic damage by $200037s1% per stack. (4.29)
- [x] **Frost Channeling (Renamed to Ablative Armor):** Threat no longer affected. Ice Armor increases your stamina by your intellect and spirit. (4.25)
- [x] **Permafrost (Renamed to Sublimation):** Frost and Ice Armor have a chance to reduce damage taken by 90%. Spellpower / level (4.27)
- [x] **Shattered Barrier:** Redesigned. When Ice Barrier breaks your Aegis of Antonidas has its cooldown reset. (4.27)
- [x] **Frostbite:** Effect also heals for 5% health. (4.25)


### Paladin

**Spell Changes:**
- [x] Concentration Aura no longer affects pushback. Now increases spell haste by X%. (4.31).

**Talent Changes:**
- [x] **Binding Oaths (NEW):** Casting FoL makes Exorcism instant cast. Casting Exorcism makes FoL instant cast and damages nearby enemies. (4.32) 
- [x] **Defender of the Faith (NEW):** Shield of Righteousness returns 2% of max mana, and deals 100% of spell power as damage. (4.32)
- [x] **Gift of Prophecy (NEW):** Melee hits have a chance to grant you Prophecy, increasing Holy damage by 10% and increasing the critical effect chance of Holy Shock by 100%.  (4.33)
- [x] **Spiritual Focus (Renamed to Anaphora):** Consecration and Exorcism do more damage based on spell power. (4.31)


### Priest

**Spell Changes:**
- [x] **Desperate Prayer (replaced with Holy Bolt):** Fire a holy bolt at the target, dealing X Holy damage. 6s cooldown. (4.33) 
- [x] **Shadow Protection (replaced with Mark of Penitence):** Brand foes with the mark of the penitent, dealing damage over 12 seconds. (4.34)
- [x] **Lightform (NEW):** Holy damage and healing increased. Shadow damage reduced by 95%. (4.35)

**Talent Changes:**s
- [x] **Shadow Affinity:** Threat and dispel effect no longer affected. Instead increases healing and restores X% mana. (4.43)

- [x] **Healing Focus (Renamed to Monasticism):** The cost of your Holy damaging spells is reduced by X% (4.36)
- [x] **Improved Renew (Renamed to Light of Prophecy):** Increase the amount healed by renew and the damage done by Penitent Mark by X%. (4.36)
- [x] **Spell Warding (Renamed to Theophanic Light):** Also increases holy damage done. (4.36)
- [x] **Blessed Recovery:** Change to ‘hit’ rather than ‘critically hit’. (4.36)
- [x] **Improved Healing (Renamed to Exegesis):** Reduce the mana cost of your Holy spells by X%. (4.36)
- [x] **Healing Prayers (Renamed to Liturgy):** Casting Prayer of Healing causes you to regain 20% of your max mana over 10 seconds. Effects can only occur every 30s. 
- [x] **Spiritual Healing (Renamed to Sacraments):** Increase the damage and healing of your Holy spells by X%. (4.36)
- [x] **Holy Concentration:** Your mana regeneration from spirit is increased by X% for Ys after you critically hit with a Holy spell. (4.37)
- [x] **Lightwell:** Replaced with Lightform (4.38)
- [x] **Blessed Resilience:** Changed to Hit and 3s effect
- [x] **Empowered Renew (Renamed to Impact of Faith):** Renew and Mark of Penitence both gain an additional bonus % of spellpower, and instantly do X% of their full effect instantly. (4.37)
- [x] **Empowered Healing (Renamed to Light’s Hope):** Your Holy Fire and Greater Heal gain an additional X% of spell power, and Flash Heal, Holy Bolt and Smite gain X/2% of spell power.(4.37)
- [x] **Serendipity:** When you heal with Flash Heal or do damage with Smite, the cast time of your next Greater Heal, Prayer of Healing or Holy Fire is reduced by X%. Stacks 3 times. (4.37)

- [x] **Unbreakable Will:** Taking damage reduces the duration of Weakened Soul by Xs. This effect can only occur once per second.
- [x] **Silent Resolve (Renamed to Killing Word):** Threat and dispel resistance no longer affected. Shadow Word: Death does X% more damage for each of your periodic damage effects on the target. (4.39)
- [x] **Martyrdom:** When your Power Word: Shield ends, your damage taken is reduced by 40% for 5 seconds.  
- [x] **Improved Power Word: Shield:** Reduces the cooldown of your Power Word: Shield ability by X seconds, reduces the mana cost of your Power Word: Shield by Y%, and increases the damage absorbed by Z%. (Merge with Soul Warding)
- [x] **Absolution:** Redesigned. Casting a Shadow spell increases the damage of your next Holy spell by X%. (4.41)
- [x] **Improved Mana Burn (Renamed to Gnosticism):** You are healed for X% of holy damage. Shadow damage restores mana equal to Y% of damage. 
- [x] **Soul Warding:** Redesigned. While protected by Power Word: Shield, you take no damage from Shadow Word: Death.
- [x] **Focused Power:** Casting Mind Sear on an enemy with Shadow Word: Pain applies it to all nearby enemies. Casting Holy Nova on an enemy with Mark of Penitence applies it to all nearby enemies.
- [x] **Focused Will:** Smite refreshes the duration of Mark of Penitence. Mind Blast refreshes the duration of Devouring Plague. Additionally increases your spell critical effect chance by X% at all times.
- [x] **Syncretism (NEW):** For X seconds after using a shadow damage spell, your next Holy spell does shadow damage equal to 50% of your spellpower. For Xs after using a Holy spell, your next shadow spell deals additional Holy damage equal to 50% of your spellpower. 
- [x] **Divine Aegis:** Additionally, when your spells critically hit an enemy, you gain a shield equal to X% of the damage done. Both effects last Xs.
- [x] **Borrowed Time:** Grants X% spell haste for your next spell after casting Power Word: Shield or Smite, and increases the amount absorbed by your Power Word: Shield and the damage done by Mark of Penitence equal to X% of your spell power. (4.42)


### Rogue

**Spec Themes:**
- [ ] **Assassination:** Poisons debilitate reducing damage done by enemies to the rogue.
- [ ] **Combat:** Lots of parries and dodges.
- [ ] **Subtlety:** Bloodlust!

**Spell Changes:**
- [x] **Feint:** Threat no longer affected. Instead increases your chance to parry (basically a spare Evasion). (4.61)
- [x] **Tricks of the Trade:** Can be self-cast. When self-cast it also increases dodge chance by 20% of your crit chance and doubles threat. (4.61)

**Talent Changes:**
- [x] **Shadowstep:** Threat no longer affected. Instead reduces your chance to be hit. (4.61)
- [x] **Master of Deception:** Your agility is 33/66/100% more effective at increasing your dodge chance, and (as today). (4.61)
- [x] **Sleight of Hand:** Reduces your chance to be hit by melee and ranged attacks by 3/6% and increases the parry chance of your Feint ability by 20/40%. (4.61)
- [x] **Dirty Tricks:** Redesigned. Ambush and Backstab no longer require you to be behind the target. (4.61)
- [x] **Camouflage:** Also reduces the cooldown of Shadowstep and Shadow Dance by 4/7/10 sec. (4.61)
- [x] **Elusiveness:** Also reduces the cooldown on Evasion by 15/30 sec (sharing the Cloak of Shadows effect) and on Shadow Dance by 5/10 sec. (4.61)
- [x] **Ghostly Strike:** A strike that deals 125% weapon damage (180% if a dagger is equipped) and increases your chance to dodge by 15% for 20 sec. Awards 1 combo point. 20s cooldown. (4.61)
- [x] **Heightened Senses:** Redesigned. When you dodge an attack, you restore 2/4% of your maximum health. (4.61)
- [x] **Preparation (Renamed to Bladework):** Redesigned. AOE combo point spender, 30 energy. Nearby enemies are marked for rapid counterattack, causing their next attacks on you — one per combo point spent, including attacks you dodge or parry — to be immediately countered for 125% weapon damage (180% if a dagger is equipped). 30s debuff duration. (4.61)
- [x] **Dirty Deeds:** Also reduces the energy cost of Bladework. (4.61)
- [x] **Hemorrhage:** Physical damage increase no longer has charges and is increased by attack power. (4.61)
- [x] **Enveloping Shadows:** Your finishing moves have a 6/12/20% chance per combo point spent to also cast Slice and Dice on yourself and Expose Armor on nearby enemies. (4.61)
- [x] **Waylay:** Your Ambush and Backstab hits unbalance your target, reducing their chance to hit you by 2/4% and increasing your chance to critically strike against them by 2/4%. (4.61)
- [x] **Filthy Tricks:** Preparation cooldown reduction removed, replaced with Evasion and Feint cooldown reduction. (4.61)

**Class Signature Skill:**
- [ ] **Trickery:** Reveal that your injuries were faked, restoring X% health and boosting energy regeneration for 5 seconds.


### Shaman

**Spec Themes:**
- [ ] **Elemental:** Healing stream totem converts 10% of damage to healing.
- [ ] **Enhancement:** Heal after dodging or parrying.

**Talent Changes:**
- [x] **Elemental Precision:** Threat no longer affected. Instead increases your critical chance.
- [x] **Healing Grace:** Threat no longer affected. Instead gives your healing spells an additional X% chance to crit.
- [x] **Spirit Weapons:** Threat no longer affected. Instead increases your parry chance by X% of your agility (like the DK equivalent with strength)
- [x] **Tidal Focus:** Reduces the mana cost of your healing spells by X%, and reduces their casting time by Xs.
- [x] **Focused Mind:** Casting Healing Wave, Lesser Healing Wave or Chain Heal clears your mind, making your next Lightning Bolt or Chain Lightning deal X% more damage and cost Y% less mana.
- [x] **Healing Focus:** Your shock spells have an X% chance to make Healing Wave free and instant cast. Additionally, casting a heal on a target with your Earth Shield, Water Shield or Lightning Shield, increases the damage of your next cast by 25%.
- [x] **Improved Reincarnation (Renamed to Defence of Nature):** Your Water Shield, Earth Shield and Lightning Shield have a X% chance to cleanse the earth around you, dealing X damage over Y seconds to all enemies within 15 yards.
- [x] **Ancestral Awakening:** Additionally the Ancestral spirit increases the critical strike chance of your next damaging spell by 100%.
- [x] **Natures Guardian:** Redesigned. All your totems summon lesser elemental guardians to aid and protect you. Additionally the cooldowns on your Earth Elemental totem and Fire Elemental totem are reduced by X%, and their damage is increased by X%.
- [x] **Healing Way:** Your Healing Wave and Lesser Healing Wave spells chances to critically hit are increased by 3/6/9% and all spell damage is increased by 10%. Additionally, casting Healing Wave or Lesser Healing Wave on yourself reduces the cooldown on Chain Lightning by 3 sec.
- [x] **Purification:** Additionally, when Earthliving Weapon heals you have an X% chance to reset the cooldown on your shock spells.
- [x] **Nature’s Blessing:** Increases damage and healing by an amount equal to 5% of your intellect.
- [x] **Improved Chain Heal (Renamed to Spiritsurge):** When Earthliving Weapon heals, your shock spells are empowered by the elements. Earth Shock summons elemental guardians, Flame Shock apples to all enemies within 15 yards of the target, and Frost Shock freezes enemies in place. Can only occur once every 8 seconds.
- [x] **Tidal Waves:** Casting Chain Lightning, Lightning Bolt or Lava Burst increases the critical strike chance of Healing Wave, Lesser Healing Wave and Chain Heal by X%. In addition, your damage and healing spells permanently gain an additional 20% of your spellpower.
- [x] **Riptide:** Heals a friendly target or damages an enemy target for 639 to 691 and another 665 over 15 sec. Your next Chain Heal or Chain Lightning cast on that primary target within 15 sec will consume the over time effect and increase the amount of the Chain Heal or Chain Lightning by 25%.

### Warlock

**Spell changes**
- [x] Soulstone now just applies the soulstone effect to whoever you've targeted, no intermediate step of creating an item.
- [x] Soul shards stack but you have a max of 32. (4.50)
- [] Voidwalker torment should be an actual taunt, like warrior taunt
- [] Succubus Seduction works more like 'Fear' - usable in combat, broken by damage (but not _instantly_ by _any_ damage)

**Talent changes** 
- [x] **Improved Healthstone:** Healthstone also restores 10/20% max mana
- [x] **Improved Imp (Renamed to Imperious Flames):** Redesigned. Your Imp's firebolt does 2x damage against targets affected by your Immolate. Your Felguard also learns Immolation Aura (spell from Metamorphosis to give it even better AOE and give you a reason to care about this talent)
- [x] **Demonic Embrace:** (As today plus) and your Voidwalker and Felguard chance to dodge is increased by your intellect (same rate as bear agi conversion?).
- [x] **Fel Synergy:** (As today plus) and 20/40% of the damage done by your pet heals you.
- [x] **Improved Health Funnel (Renamed to Sacrifice of Blood):** Redesigned. Health Funnel transfers 25/50% more health, and while channelling it the targeted demon takes 15/30% less damage and deals 25/50% more damage. Pure DBC — core's `spell_warl_health_funnel` already casts buff 60955/60956 on the demon gated on the talent, so the demon half is a rewrite of those two rows; the transfer bonus is an `ADD_PCT_MODIFIER` / `SPELLMOD_DOT` on the talent, class-masked to Health Funnel so it touches nothing else. No script. The old 40/80% health-cost cut was dropped: Health Funnel charges health in three places and only one honours `SPELLMOD_COST`, so it required a per-tick refund hack; the healing bonus delivers the same relief as throughput instead (the tick self-damage is capped at `ManaPerSecond`, so a bigger heal costs no more).
- [x] **Demonic Brutality:** Redesigned. Your Voidwalker's and Felguard's attacks — and your Voidwalker's Torment and Suffering — generate 67/134/200% additional threat, and the cooldown on Suffering is reduced by 30/60/90s. Damage-derived threat (melee, Cleave, Intercept) comes from the 200412 `MOD_THREAT` carrier; Torment and Suffering need `spell_warl_demon_brutality_threat` because `SPELL_EFFECT_THREAT` ignores threat modifiers.
- [x] **Demonic Lash:** Redesigned. Your Succubus' Lash of Pain leaves a Nether Scar, increasing your shadow damage on affected enemies by 5/10/15%. Your Felguard also does 5/10/15% weapon damage as additional shadow damage.
- [x] **Fel Domination:** For 30 seconds your demons do 10% more damage for each of your DoT effects on your target.
- [x] **Demonic Aegis:** Your Demon Armor increases your armor by 200/400/600% and reduces your and your pet's chance to be critically hit by 2/4/6%.
- [x] **Master Summoner:** Reduces the casting time of your Imp, Voidwalker, Succubus, Incubus, Felhunter and Fel Guard Summoning spells by 4/8 sec and the Mana cost by 40/80%. 
- [x] **Mana Feed:** When your demons deal damage they return 5% to you as mana. Health Funnel also restores 5% of your max mana of your summoned demon per tick.
- [x] **Master Conjuror (Renamed to Fel Attunement):** Redesigned. Your demons gain 75/150% of your haste. (Crit inheritance dropped — haste has a working precedent on the DK ghoul, crit has none anywhere in the core; the haste share was raised from 50/100% to compensate.)
- [x] **Molten Core:** Can also apply to Shadow Bolt, adding a stacking DoT for 3/6/10% of damage done like Unholy Blight does for Death Coil for DKs
- [x] **Demonic Resilience:** Hit instead of critically hit
- [x] **Nemesis:** (as today plus) your and your demon's attacks have a chance to generate a soul shard (2/4/6 PPM each half). 
- [x] **Metamorphosis:** Redesigned. No cooldown or duration. Costs 1 Soul Shard to transform, and then one more every 6s. (All defensive benefits removed and put in Demonic Aegis). 


- [x] SWAP Emberstorm and Molten Skin positions (4.50)
- [x] **Ruin:** No longer afffects Imp. Instead critical hits on an targets with Immolate active spread Immolate to nearby targets (so long as those targets aren't CCed with something that breaks on damage)
- [x] **Backlash:** Damage that would otherwise kill you instead consumes your Soulstone and heals you for 20% of your maximum health. 
- [x] **Intensity (Renamed to Burning Soul):** Critical hits from your fire spells have an X% chance to generate a Soul Shard. 
- [x] **Shadowburn:** Doesn't cost a Soul Shard anymore. Instead generates one, and another if the target dies. Longer cooldown.
- [x] **Aftermath:** Increases the periodic damage on your Immolate by X%, and Immolate periodic damage has a chance equal to your critical strike chance to generate a Soul Shard. 
- [x] **Molten Skin (Renamed to Infernal Bargain):** Channel souls to the nether in exchange for power and protection. The void doubles its price every second — 1, then 2, 4, 8 and 16 Soul Shards — and the pact ends the instant you cannot pay. Each payment grants stacks equal to the shards spent, each increasing your damage by X% and the critical effect chance of your spells by X% for 10 seconds. While committing to the pact you are immune to all damage. Going all the way costs 31 of the 32 shards you can carry — i.e. the whole of Nathrezim Foresight — so the panic button and the burst button are the same button. 
- [x] **Demonic Power (Renamed to Molten Rain):** Rain of Fire has an X% chance to generate a Soul Shard from each enemy hit.  
- [x] **Destructive Reach:** Threat no longer reduced. Fire damage increased by X%. 
- [x] **Nether Protection:** Casting Searing Pain transforms a Soul Shard into a Wailing Soul. Wailing Souls reduce damage taken by 15% for 10 seconds. Max 3 stacks. 
- [x] **Soul Leech:** Gives your Shadow Bolt, Shadowburn, Chaos Bolt, Soul Fire, Incinerate, Searing Pain and Conflagrate spells a 15% chance to return health equal to 200% of the damage caused. 
- [x] **Empowered Imp (Renamed to Sacrifice the Weak):** Redesigned. Sacrifice your demon to a new master in the Twisting Nether. In return they grant you Nathrezim Foresight, reducing damage taken and increasing the critical effect damage bonus of your spells by 1% for each Soul Shard in your possession. 

- [x] **Siphon Life:** Heals for a percentage of *all* Shadow damage done, not just Corruption. The rate drops from 40% to 15% to pay for the wider trigger — 40% of Corruption alone is a fraction of Affliction's output, 40% of all Shadow damage would be most of it. The +5% Corruption/Seed/Unstable Affliction DoT bonus is unchanged. Pure DBC + `spell_proc`: core's `spell_warl_siphon_life` is already generic, the Corruption restriction lived entirely in the proc row's family mask. (4.62)
- [x] **Improved Howl of Terror (Renamed to Fel Interdiction):** Redesigned, and moved to the slot right of Malediction. While Fel Armor is up, 50% of damage taken is converted to a Mark of Gul'dan, dealing the deferred damage over 10 seconds. Each hit adds a stack, up to 10; dealing damage with Drain Soul, Drain Life or Haunt clears one, and casting Soulshatter clears 2. (The Ember Scars mechanic for Fire Mages, with Fel Armor as the gate, the drains and Haunt as the steady bleed and Soulshatter as the panic dump. Collapsed to 1 point — the ability has no per-rank scaling.) (4.62)
- [x] **Malfeasance (NEW):** Your periodic damage has a 20/40% chance to clear a stack of Mark of Gul'dan, and your Soulshatter clears 4 stacks instead of 2 and has its cooldown reduced by 60/120 sec — 3 minutes base down to 1 minute at full rank, so the panic dump comes back about as often as the pool becomes dangerous. (4.62)
- [x] **Improved Drain Soul:** No longer affects threat. In its place, Drain Soul's Soul Shard generation rate increases by 50/100% — core's flat 20% per-tick roll becomes an effective 30/40%. (4.62)
- [x] **Fel Concentration:** Redesigned. Reduces damage taken by 10/20/30% while channelling Drain Soul or Drain Life. (All three ranks were pure pushback resistance, which Alonecraft removed outright, so the talent did literally nothing. The new version pays out exactly when the warlock is standing still and least able to react. "While channelling" has no DBC representation, so the script hangs off the drain aura itself — that aura lives on the target, so interrupt, target death and range break all drop the buff for free.) (4.62)

### Warrior

**Spell Changes:**
- [x] **Victory Rush:** Restore the healing component (missing in 3.3.5, added in Cataclysm). Now heals for 20% of maximum health. (Pure DBC -- effects 2 and 3 were empty. `SPELL_EFFECT_HEAL_PCT` (136), the Rune Tap 48982 shape.) (4.63)

**Talents:**
- [x] **Deflection (Renamed to Small Victories) (1, 0):** Increases your Parry chance by 1/2/3/4/5%, and each parry has a 20/40/60/80/100% chance to grant you Victorious, allowing you to use Victory Rush. (5 ranks) (Pure DBC + `spell_proc`, the Glyph of Overpower 58386 shape. The per-rank chance lives in DBC `ProcChance` so `$h` renders it. Victorious 32216 also had `DO_NOT_DISPLAY` cleared -- stock hides it because it fired once per kill; driven by parry it is a window worth seeing.) (4.63)
- [x] **Improved Charge (0, 1):** Increases the amount of rage generated by your Charge ability by 10. Killing an enemy has a 50/100% chance to reset the cooldown on Charge. (2 ranks) (`PROC_FLAG_KILL` is stock; the reset is not -- `SPELL_EFFECT_RESET_COOLDOWN` does not exist in 3.3.5. Charge's 15s is entirely a *category* cooldown, so `RemoveCategoryCooldown` is the load-bearing call.) (4.63)
- [x] **Iron Will (Renamed to Riposte):** Redesigned. Parrying an attack immediately counter-attacks every enemy within 8 yards for 40/70/100% weapon damage. Cannot occur more than once every second. Requires 5 points in Deflection. (Only affects enemies where CC wouldn't be broken) (**Shipped with a 2 sec ICD, not 1** -- with this tree's parry rates a 1 sec uncapped 8-yard counter is close to a free weapon swing per second per target. DBC + `spell_proc`; the script only filters CC. Cloned from Whirlwind off-hand 44949, whose `REQUIRES_OFF_HAND_WEAPON` attribute and 4-target cap both had to be undone.) (4.63)
- [x] **Tactical Mastery (2, 1):** Redesigned. Parrying an attack grants you 3/6/10% critical strike chance for 10 seconds. Landing a critical strike grants you 3/6/10% parry chance for 10 seconds. (3 ranks) (Needs C++ only for routing: `spell_proc` is per-spell, not per-effect, so one row cannot say "effect 0 on parry, effect 1 on crit". The script also checks *direction* -- being crit **by** an enemy carries the same hit mask as your own crit. Costs Arms its stance-change rage retention and Defensive Stance threat bonus, which needed all three effect slots.) (4.63)
- [x] **Two-Handed Weapon Specialization (1, 3):** Increases the damage you deal with two-handed melee weapons by 6%, and while using a 2h weapon your chance to parry is increased by 33/66/100% of your critical strike chance. (3 ranks) (**The one mechanic in the batch with no prior art anywhere in 3.3.5** -- aura 220 `MOD_RATING_FROM_STAT` reads base stats only, and no aura scales one rating off another. Script modelled on the module's own agility->dodge conversion in `RogueMasterOfDeception.cpp`. Shipped at the full value by decision; this is the dominant term in the tree's parry total and compounds with Tactical Mastery.) (4.63)
- [x] **Sword Specialization (3, 4):** Remove the "This effect cannot occur more than once every 6 seconds." bit, it should be able to proc whenever it procs. (**Shipped at 1 sec, not 0** -- the trigger is `ADD_EXTRA_ATTACKS`, and extra attacks are auto-attacks that can re-proc it, so a true 0 chains into itself. One integer in one `spell_proc` row.) (4.63)
- [x] **Weapon Mastery (0, 5):** Reduces the chance for your attacks to be dodged by 2/4% and while using a two-handed weapon your parry chance is increased by your strength. (2 ranks) (Same effect as DK strength -> parry conversion) (**12/25% of Strength per rank**, matching the DK's 25% at full rank rather than a literal 100%, which would have been ~+36% parry alone. Effect 1 is aura 248 `MOD_COMBAT_RESULT_CHANCE`, added flat -- not aura 251, and not a multiplier. The 2H gate is in C++ because `EquippedItemClass` is a whole-spell gate and the dodge reduction must stay unconditional; `spell_linked_spell` cannot substitute, as core never re-adds a linked passive after a weapon swap.) (4.63)
- [x] **Improved Hamstring (Renamed to Hobble) (2, 5):** Using Hamstring with a two-handed weapon equipped increases your chance to parry by 3/6/10% for 10s. (3 ranks) (Pure DBC -- core already ships the right `spell_proc` row, and `EquippedItemClass` on a *passive* is re-checked at proc time, so the 2H gate needs no code and re-arms on weapon swap.) (4.63)
- [x] **Second Wind (0, 6):** Being hit by while you are below 35% health generates 20 rage and 10% of your total health over 10 sec. (2 ranks) (Rank 1 is half -- which is exactly stock 29841 vs 29842, so both payloads are reused untouched. Pure DBC: `CasterAuraState = 13` genuinely gates the *proc*, because `ModifyAuraState` unapplies the aura's effects above 35% health. Core's `spell_warr_second_wind` registration is deleted, as it owned the stun/root gate.) (4.63)
- [x] **Improved Slam (3, 6):** Decreases the swing time of your Slam ability by 0.75/1.5 sec. (2 ranks) (Base points only. Stock's `$/1000;S1` renders the new values with no text edit. Rank 2 makes Slam instant.) (4.63)
- [x] **Juggernaut (0, 7):** Your Charge ability is now usable while in combat. Following a Charge, your next Slam or Mortal Strike has an additional 25% chance to critically hit if used within 10 sec. (1 rank) (This is stock Juggernaut *minus* the +5 sec Charge cooldown, so the change is one effect zeroed -- and the `${$m3/1000}` clause removed with it, or it would render as "0 sec".) (4.63)
- [x] **Bladestorm (1, 10):** Instantly Whirlwind up to $50622i nearby targets and for the next 6 sec you will perform a whirlwind attack every 1 sec. While under the effects of Bladestorm, you can move but cannot perform any other abilities, but you do not feel pity or remorse or fear, your parry chance is increased by 50% and you cannot be stopped unless killed. (1 rank) (Everything but the parry was already stock, flavour text included. All three effect slots on 46924 are load-bearing, so the parry rides along via `spell_linked_spell` type 2. The trigger id is written plain -- the loader applies the type multiplier itself.) (4.63)