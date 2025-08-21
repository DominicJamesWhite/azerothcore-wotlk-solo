# Alonecraft

An attempt to make WOW better to play alone or in very small groups.

> **Note:** I do not, have never, and never will care about PVP - so the balance there is totally dead, I’m sorry. Probably duels will take 3000 years to complete, and BGs & Arenas are unplayable. Best of luck.

---

## Key Changes

- [ ] All classes get a Diablo-like potion that can be used to refill X% of health and mana every X seconds. Other potions all provide temporary combat bonuses as well as their healing and mana restoration.
- [x] mod-autobalance is used to allow solo play in dungeons and raids, and scale their difficulty with more players. 
- [ ] Casting pushback from enemy damage is reduced by 90%.
- [ ] Talents are boosted to provide more impact in levelling and solo play.
- [ ] More NPCs in major cities and towns, and between them doing courier or transport work.
- [ ] Each tree now has changed talents relating to holy trinity specs’ inherent weaknesses while retaining class character.
- [ ] Retuned and redesigned dungeon and raid encounters with lots of new difficulty settings to allow solo progression.

---

## Spell Changing Process Note

Modifying or adding spells in AzerothCore 3.3.5 generally involves these steps:

1. **Spell Database Editing:**  
   - Most spell attributes, effects, and parameters are controlled in the database tables, primarily `spell_template` and related tables.  
   - Changes here affect how the spell behaves in-game (damage, healing, cooldowns, proc chances, durations, etc.).

2. **Spell Scripts / Custom Spell Handlers:**  
   - For complex spell behaviors or custom mechanics, spells are often scripted using the core’s scripting system (`SpellScript`, `AuraScript`, or even custom C++ handlers).  
   - This allows overriding default behavior, adding custom effects, or altering spell logic dynamically.

3. **Talent and Class Integration:**  
   - Talents often modify spell effects or add new procs. These are either handled in the talent database or via scripts attached to the talent/spell.  
   - Ensure talents properly hook into spell effects and scale correctly with player stats.

4. **Client-Side Considerations:**  
   - Some visual or client-side changes (like model swaps or spell icons) may require client modifications or custom addons.

5. **Testing & Balancing:**  
   - After changes, extensive in-game testing is necessary to ensure spells behave as intended, especially for unusual or heavily redesigned abilities.

---

## Class Changes

### Death Knight

**Talent Changes:**
- [ ] **Subversion:** Threat no longer affected. Instead increases parry.
- [ ] **Improved Rune Tap:** Additionally Rune Tap increases your Heart Strike and Death Strike damage by X% for Ys.
- [ ] **Vendetta (Renamed to Bloody Lesions):** Redesigned. Blood Boil now leaves your enemies with bleeding lesions, dealing X damage over Ys, and refreshes the duration of diseases on affected enemies.
- [ ] **Mark of Blood:** Redesigned. Place a Mark of Blood on the enemy. X% of the healing you do to yourself is done to the marked enemy. Parrying an attack from a marked enemy opens them up for a counter-attack, increasing your armour penetration by X% for Ys.
- [ ] **Improved Blood Presence:** Swapping presences no longer costs runes. While in Blood Presence you do an additional X% damage, and you retain your healing bonus in other presences.
- [ ] **Will of the Necropolis:** Additionally, doing damage with Heart Strike increases your parry chance by X%. Stacks Y times.
- [ ] **Runic Power Mastery:** Spending Runic Power has a chance to restore X% of your health. Additionally increases your maximum runic power by Y.
- [ ] **Chillblains:** Victims of your Frost Fever disease are Chilled, reducing movement speed by X% for 10 sec. When Frost Fever does damage to a Chilled target, there is a chance to drain X health from the target and transfer it to the Death Knight.
- [ ] **Hungering Cold:** Purges the earth around the Death Knight of all heat. Enemies within 10 yards are trapped in ice, preventing them from performing any action for 10 sec and infecting them with Frost Fever. After they thaw, X health is drained from them and transferred to the Death Knight.
- [ ] **Improved Frost Presence:** Swapping presences no longer costs runes. While in Frost Presence you take X% less damage, and you retain your armour bonus in other presences.
- [ ] **Acclimation:** When you are hit by a spell, you have an X% chance to reduce the damage of spells from that school by Y% for Zs.
- [ ] **Virulence:** Increases your chance to hit with spells by X% and increases the duration of your diseases by X seconds.
- [ ] **Anticipation:** Increases your dodge chance and disease damage by X%.
- [ ] **Master of Ghouls:** Raise Dead summons Y additional ghouls and Army of the Dead raises twice as many undead soldiers.
- [ ] **Hungry Dead:** Redesigned. Ghouls do X% more damage for each of your diseases on the target.
- [ ] **Crypt Fever:** Your diseases cause Crypt Fever, increasing disease damage done to the target by X% and dealing Y damage over Zs.
- [ ] **Ebon Plaguebringer:** Your diseases also cause Ebon Plague, increasing magical damage taken by X% and dealing Y damage over Zs.
- [ ] **Epidemic:** For each of your diseases on an enemy, increase your shadow damage against them by X%.
- [ ] **Unholy Blight:** Dispel protection is removed. Instead targets affected by Unholy Blight have a reduced chance to hit you.
- [ ] **Unholy Command:** Reduces the cooldown on Death Grip by X%, and SOMETHING ELSE.
- [ ] **Corpse Explosion (Renamed to Grim Prophecy):** Redesigned. Using Scourge Strike or Death Strike with a two-handed weapon has an X% chance to increase your parry chance by Y%.
- [ ] **On a Pale Horse (Renamed to Harvest of Souls):** Redesigned. Your Unholy Presence now drains life from diseased enemies, draining X life every Y seconds for each disease and transferring it to you.
- [ ] **Desecration:** Your Blood Strikes and Blood Boil desecrate the ground under you. Targets in the area are slowed by X% by the grasping arms of the dead, and they take Y% more damage from your diseases. Lasts Zs.
- [ ] **Magic Suppression (Renamed to Magic Siphon):** Redesigned. Your Anti-Magic Shell absorbs X% more damage from spells, and Y% of damage absorbed is returned to you as health.
- [ ] **Anti-Magic Zone:** Max absorb removed. Reduction reduced to 50%.
- [ ] **Improved Unholy Presence:** Swapping presences no longer costs runes. While in Unholy Presence your attack speed is increased by X%, and you retain your attack speed bonus in other presences.
- [ ] **Bone Shield:** Redesigned. Auto-attacks have a chance to chip away enemy bones and add a charge. This effect can only occur once every three seconds.
- [ ] **Summon Gargoyle (Renamed to Summon Abomination):** It’s an Abomination instead of a gargoyle because I hate that fucking thing.

**Class Signature Skill:**
- [ ] **Ossification:** Increases armour and parry by X% for Y seconds, and spending a rune with Ossification active heals you for X% of your health.

### Druid

**Class Changes:**
- [x] Tree form now uses a cool-as-fuck arakkoa instead of a lame treant. (4.1) Also can use Balance spells. (4.2)

**Spec Passives:**
- [ ] **Balance:** Summons healing trees.
- [ ] **Feral:** Dodging restores rage and energy; swapping between forms increases Armour (Bear) or Dodge (Cat).

**Talent Changes:**
- [x] **Nature’s Reach:** Threat no longer affected. Instead increases spell crit. (4.2)
- [ ] **Nature’s Focus:** Redesigned. After using a Restoration spell your attack speed is increased by X%.
- [x] **Subtlety:** Redesigned. Your chance to be hit by enemies is reduced by X%. (4.2)
- [ ] **Naturalist:** Also reduces the mana cost of all healing spells by X% (from Tranquil Spirit).
- [ ] **Master Shapeshifter:** Grants an effect which lasts while the Druid is within the respective shapeshift form. Bear Form increases physical damage and armour by X%. Cat Form increases critical strike chance and dodge by X%.Moonkin Form increases spell damage by X%. Arakkoa Form increases nature damage and healing by X%. When not shapeshifted your spell haste is increased by X%.
- [x] **Improved Rejuvenation (Renamed Bloomstrike):** For each of your own healing effects on yourself, your melee attacks are boosted by natural energy, causing X% additional nature damage per effect (4.3)
- [x] **Tranquil Spirit (Renamed to Spirit of the Storm):** Redesigned. As you cast healing spells you build up charges of living energy, increasing the damage and reducing the cast time of Starfire by 10%. Stacks 10 times. (4.6)
- [x] **Improved Tranquility (Renamed to Lunar Storm):** Redesigned. Casting Hurricane on a target affected by your Moonfire unleashes explosive natural energies, damaging targets within 8 yards for $200015s1 each second. (4.7)
- [x] **Gift of Nature:** Redesigned. When you are healed by one of your own heal over time spells, your next Wrath has an X% chance to be instant cast and cost no mana. Additionally increases the damage and healing of your spells by X%. (4.5)
- [ ] **Swiftmend:** Using Swiftmend on yourself creates an explosion of natural energy, damaging enemies for X damage.
- [ ] **Living Spirit:** Additionally gain X% armour contribution from items in Arakkoa or Travel Form or when not shapeshifted.
- [X] **Empowered Touch:** Redesigned. After using Healing Touch, Regrowth or Nourish, your weapon is imbued with living energy, damaging the next enemy you strike in melee for X nature damage over Y seconds or increasing the healing of your next spell by 5%. (4.4) 
- [ ] **Nature’s Bounty:** Increases your critical strike chance by X%.
- [ ] **Vengeance of Eonar:** Redesigned. When 
- [ ] **Natural Perfection:** Amend to hits against you, instead of crits.
- [ ] **Living Seed:** Additionally, the seed also does damage to nearby enemies equal to the amount healed.
- [ ] **Empowered Rejuvenation:** When you are healed by your own heal-over-time spells, there is an X% chance to reduce the cost of your next healing spell and guarantee a critical heal. 
- [X] **Arakkoa:** Reduces the mana cost and cast time of your healing over time spells by X% and grants the ability to shapeshift into the Arakkoa. While in this form you increase healing received by X% for all party and raid members within 100 yards and your nature damage is increased by Y%. (4.1)
- [ ] **Improved Arakkoa:** Your melee attack speed and spellpower in Arakkoa form is increased by X%.
- [ ] **Improved Barkskin:** As your skin turns to thick bark, roots grow rapidly beneath you, reaching out and damaging nearby enemies for X damage for Ys.
- [ ] **Gift of the Earthmother:** Also increases melee haste.
- [ ] **Wild Growth:** Heals up to 5 party members for X or damages up to 5 enemies for Y within 15 yards of the target for Zs. The amount is applied quickly at first then slows down as the Wild Growth reaches its full duration.

**Class Signature Skill:**
- [ ] **Shifting Balance:** Moving to a different form buffs the form temporarily - bears get X% more armour, cats get X% more damage and dodge, moonkin / tree / no form gets X% spell damage and healing.

### Hunter

**Spec Passives:**
- [ ] **Beast Mastery:** Pet armour and health is boosted.
- [ ] **Marksmanship:** Your attacks reduce the damage taken by pets.
- [ ] **Survival:** Traps reduce enemy damage.

**Class Signature Skill:**
- [ ] **Primal Bond:** Damage you do heals your pet and damage your pet does increases your armour.

### Mage

**Spec Passives:**
- [ ] **Arcane:** Mana shield also reduces damage taken.
- [ ] **Fire:** Burning enemies heals you.
- [ ] **Frost:** Hitting chilled or frozen enemies heals you.

**Talent Changes:**
- [ ] **Frost Channeling:** Threat no longer affected. Instead reduces damage taken when using Ice Barrier.
- [ ] **Burning Soul:** Threat no longer affected. Instead Dragon’s Breath doubles your armour.
- [ ] **Arcane Subtlety:** Threat and dispel chance no longer affected. Instead reduces your chance to be hit.

**Class Signature Skill:**
- [ ] **Chronomancy:** Swaps your corporeal form for one from before you started fighting, bringing you back to full health and mana and temporarily boosting damage.

### Paladin

**Spell Changes:**
- [ ] Holy Light and Flash of Light can now be cast on enemies.
- [ ] Lay on Hands cooldown reduced to 5 mins.
- [ ] Forbearance now only lasts 1 min.
- [ ] Concentration Aura no longer affects pushback. Now increases spell crit by X%.

**Spec Passives:**
- [ ] **Holy:** Casting heals stacks a damage buff to be consumed, consecration goes nuts.
- [ ] **Prot:** Cast different blessings for different benefits.
- [ ] **Retribution:** Thorns but holy.

**Talent Changes:**
- [ ] **Fanaticism:** Threat no longer affected. Instead Righteous Fury increases your armour by X%.
- [ ] **Unyielding Faith:** No longer has any effect on fear or disorient effects. Instead gives a chance when hit to make your next Holy Light instant cast.
- [ ] **Spiritual Focus:** Increases your mp5 after casting Flash of Light.
- [ ] **Healing Light (Renamed to Pure Light):** Now increases the damage and healing of the affected spells.
- [ ] **Improved Concentration Aura:** Now simply increases spell crit in concentration aura.
- [ ] **Pure of Heart:** Increases spell critical % after healing yourself, lasts 7 seconds.
- [ ] **Sacred Cleansing:** Healing with Holy Light increases the damage of your next Holy cast by X%. Can only occur once every 20 seconds.
- [ ] **Beacon of Light:** Redesigned. A friendly target becomes a beacon of light, dealing Holy damage each time they are struck and being healed each time another player is healed. 

**Class Signature Skill:**
- [ ] **Confession:** Ignore damage for 5 seconds - each hit you take boosts your damage by X% for 10 seconds after confession is over.

### Priest

**New Spells:**
- [ ] **Holy Lance (Reskinned Ice Lance):** Fire a holy lance at the target, dealing damage. Does more damage to targets affected by Holy Fire and Penitent Mark. Instant cast.
- [ ] **Penitent Mark:** Brand foes with the mark of the penitent, dealing X damage over Ys and slowing their movement speed by Z%.

**Spec Passives:**
- [ ] **Discipline:** Lots of shields, fast GCD (a kind of twitchy, argumentative gnostic).
- [ ] **Holy:** Heals and Prayers boost damage, normal GCD (patient, slow monk who hits hard).
- [ ] **Shadow:** Leech leech leech baby.

**Talent Changes:**
- [ ] **Pain Suppression:** Threat no longer affected. Instead increases damage done by X%.
- [ ] **Shadowform:** Threat no longer affected. Instead reduces your chance to be hit by X%.
- [ ] **Silent Resolve:** Threat and dispel resistance no longer affected. Instead increases holy damage after PW:S is cast.
- [ ] **Shadow Affinity:** Threat and dispel effect no longer affected. Instead increases healing and restores X% mana.
- [ ] **Guardian Spirit:** Healing received no longer affected - instead damage done is increased by X%.
- [ ] **Divine Providence:** Increases the damage and healing of Holy Spells by X%.
- [ ] **Test of Faith:** Increase damage and healing against targets with less than 50% health.
- [ ] **Lightwell:** Creates a holy lightwell, which damages enemies and heals friendly units nearby over Xs. Click the Lightwell to instantly shatter it, dealing the damage instantly.
- [ ] **Circle of Healing (Renamed to Circle of Light):** Heals 5 friendly units or damages 5 enemy units within 15 yards of the target.
- [ ] **Empowered Renew (Renamed to Lasting Faith):** Renew and Penitence both gain an additional bonus % of spellpower, and instantly do X% of their full effect instantly.
- [ ] **Serendipity:** When you heal with Flash Heal or do damage with Smite, the cast time of your next Greater Heal, Prayer of Healing or Holy Fire is reduced by X%. Stacks 3 times.
- [ ] **Empowered Healing (Renamed to Light’s Hope):** Your Holy Fire and Greater Heal gain an additional X% of spell power, and Flash Heal, Holy Lance and Smite gain X/2% of spell power.
- [ ] **Body and Soul (Renamed to Evangelist):** Redesigned. When healed by your Renew, you have an X% chance to do Y% more damage with Holy Lance for Zs.
- [ ] **Holy Concentration:** Your mana regeneration from spirit is increased by X% for Ys after you critically hit with a Holy spell.
- [ ] **Blessed Resilience:** Falling below 75% health reduces damage taken by X% for Ys. Healing yourself extends this effect for Ys.
- [ ] **Spiritual Healing (Renamed to Spiritual Defence):** Increase the damage and healing of your Holy spells by X%.
- [ ] **Healing Prayers (Renamed to Liturgy):** Casting Prayer of Mending increases your spellpower by X% for Y. Casting Prayer of Healing causes you and 10 party and raid members to get X% of their max mana per 5 seconds.
- [ ] **Spirit of Redemption:** Redesigned. You are protected from death by a Guardian Spirit - attacks which would otherwise kill you cause you to be healed by up to 10% of your maximum health (amount healed based on spellpower). This healing effect cannot occur more often than once every 2 min.
- [ ] **Blessed Recovery:** Change to ‘hit’ rather than ‘critically hit’.
- [ ] **Improved Healing (Renamed to Exegesis):** Reduce the mana cost of your Holy spells by X%.
- [ ] **Desperate Prayer:** Also restores some mana.
- [ ] **Spell Warding:** Also increases spell damage done.
- [ ] **Healing Focus (Renamed to Monasticism):** You have a X% chance to add a charge of Inner Fire when you do damage.
- [ ] **Improved Renew (Renamed to Light of Prophecy):** Increase the amount healed by renew and the damage done by Penitent Mark by X%.
- [ ] **Unbreakable Will:** Taking damage reduces the duration of Weakened Soul by Xs. This effect can only occur once per second.
- [ ] **Martyrdom:** When your Power Word: Shield ends, your spell damage is increased by X%.
- [ ] **Absolution:** Redesigned. Casting Mind Blast increases the damage of your next Holy spell by X%.
- [ ] **Improved Mana Burn (Renamed to Gnosticism):** Your Holy spells have an X% chance to reset the cooldown on Mind Blast.
- [ ] **Improved Power Word: Shield:** Reduces the cooldown of your Power Word: Shield ability by X seconds, reduces the mana cost of your Power Word: Shield by Y%, and increases the damage absorbed by Z%.
- [ ] **Mental Agility:** Casting a shadow spell reduces the cast time of Smite by Xs for Ys. Additionally reduces the cost of your instant cast spells and Smite by Y%.
- [ ] **Soul Warding:** Redesigned. While protected by Power Word: Shield, you take no damage from Shadow Word: Death.
- [ ] **Mental Strength:** Additionally increases your Holy damage by X%.
- [ ] **Enlightenment:** Holy Lance increases the duration of Penitent Mark on the target by Y seconds. Additionally increases your Spirit by X% and Spell Haste by X%.
- [ ] **Focused Power:** Casting Mind Sear on a target affected by Shadow Word: Pain spreads the effect to all affected enemies. Casting Holy Nova on a target with Penitent Mark deals X% more damage, and spreads the Mark to all affected enemies. Additionally increases damage and healing done by your spells by X%.
- [ ] **Focused Will:** Casting Shadow Word: Death increases the critical effect chance of Holy Lance by X%. Additionally increases your spell critical effect chance by X%.
- [ ] **Improved Flash Heal (Renamed to Syncretism):** For Xs after healing yourself with Flash of Light, your next Holy spell does additional shadow damage equal to the amount healed.
- [ ] **Grace:** Redesigned. Your Flash Heal, Greater Heal, and Penance spells have an X% chance to bless the target with Grace, increasing all healing received from the Priest by X% for Ys, and to bless you with Clemency, increasing your spell haste by X% for Ys. Grace can only be active on one target at a time.
- [ ] **Borrowed Time:** Grants X% spell haste for your next spell after casting Power Word: Shield or Holy Lance, and increases the amount absorbed by your Power Word: Shield and the damage done by Holy Lance equal to X% of your spell power.
- [ ] **Divine Aegis:** Additionally, when your spells critically hit an enemy, you gain a shield equal to X% of the damage done. Both effects last Xs.

**Class Signature Skill:**
- [ ] **Inspiration:** Channels full health and mana over 6 seconds, damage taken while channeling is ignored.

### Rogue

**Spec Passives:**
- [ ] **Assassination:** Poisons debilitate reducing damage done by enemies.
- [ ] **Combat:** Lots of parries.
- [ ] **Subtlety:** Lots of dodges and dummies.

**Talent Changes:**
- [ ] **Shadowstep:** Threat no longer affected. Instead reduces your chance to be hit.
- [ ] **Sleight of Hand:** Threat no longer affected. Instead increases your chance to dodge.

**Class Signature Skill:**
- [ ] **Trickery:** Reveal that your injuries were faked, restoring X% health and boosting energy regeneration for 5 seconds.

### Shaman

**Spec Passives:**
- [ ] **Elemental:** Healing stream totem converts 10% of damage to healing.
- [ ] **Enhancement:** Heal after dodging or parrying.

**Talent Changes:**
- [ ] **Elemental Precision:** Threat no longer affected. Instead increases your critical chance.
- [ ] **Healing Grace:** Threat no longer affected. Instead gives your healing spells an additional X% chance to crit.
- [ ] **Spirit Weapons:** Threat no longer affected. Instead increases your parry chance by X% of your agility.
- [ ] **Tidal Focus:** Reduces the mana cost of your healing spells by X%, and reduces their casting time by Xs.
- [ ] **Focused Mind:** Casting Healing Wave, Lesser Healing Wave or Chain Heal clears your mind, making your next Lightning Bolt or Chain Lightning deal X% more damage and cost Y% less mana.
- [ ] **Healing Focus:** Your shock spells have an X% chance to make Healing Wave free and instant cast. Additionally, casting a heal on a shielded target increases the damage of your next 5 casts by X%.
- [ ] **Improved Reincarnation (Renamed to Defence of Nature):** Your Water Shield, Earth Shield and Lightning Shield have a X% chance to deal Y% more damage and cleanse the earth around you, dealing X damage over Y seconds to all enemies within 15 yards.
- [ ] **Ancestral Awakening:** Additionally the Ancestral spirit increases the critical strike chance of your next damaging spell by 100%.
- [ ] **Natures Guardian:** Redesigned. All your totems summon lesser elemental guardians to aid and protect you. Additionally the cooldowns on your Earth Elemental totem and Fire Elemental totem are reduced by X%, and their damage is increased by X%.
- [ ] **Healing Way:** Your Healing Wave and Lesser Healing Wave spells chances to critically hit are increased by X%. Additionally, casting Healing Wave or Lesser Healing Wave on yourself increases your damage by X% and reduces the cooldown on Chain Lightning by Xs.
- [ ] **Purification:** Additionally, when Earthliving Weapon heals you have an X% chance to reset the cooldown on your shock spells.
- [ ] **Nature’s Blessing:** Increases damage and healing by an amount equal to 5% of your intellect.
- [ ] **Improved Chain Heal (Renamed to Spiritsurge):** When Earthliving Weapon heals, your shock spells are empowered by the elements. Earth Shock summons elemental guardians, Flame Shock apples to all enemies within 15 yards of the target, and Frost Shock freezes enemies in place. Can only occur once every 6 seconds.
- [ ] **Tidal Waves:** Casting Chain Lightning, Lightning Bolt or Lava Burst increases the critical strike chance of Healing Wave, Lesser Healing Wave and Chain Heal by X%. In addition, your damage and healing spells gain an additional 20% of your spellpower.
- [ ] **Riptide:** Heals a friendly target or damages an enemy target for 639 to 691 and another 665 over 15 sec. Your next Chain Heal or Chain Lightning cast on that primary target within 15 sec will consume the over time effect and increase the amount of the Chain Heal or Chain Lightning by 25%.

**Class Signature Skill:**
- [ ] **Blessing of the Ancestors:** Massively boost effects of totems temporarily.

### Warlock

**Spec Passives:**
- [ ] **Affliction:** Leech leech leech, vast amounts of HPS and stagger mechanic on Fel Armour.
- [ ] **Demonology:** Boosted demons.
