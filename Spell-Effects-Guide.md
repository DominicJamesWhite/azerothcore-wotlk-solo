This will be an ongoing list to provide info found in spell.dbc to make spells and understand misc values and how some undocumented things work.

If you have any info to provide, please help add to this list to increase the functionality of the WoW Spell Editor.

Apply Aura Name:
2- Aura Mod Possess
Base Points + Die Points = up to level that can be charmed

Apply Aura Name:
6- Aura Mod Possess
Base Points + Die Points = up to level that can be charmed

Apply Aura Name:
22 - Spell_Aura_Mod_Resistance
Misc Value A:
1 = Armor
2 = Holy
4 = Fire
8 = Nature
16 = Frost
32 = Shadow
64 = Arcane

Apply Aura Name:
23 - Spell_Aura_Periodic_Trigger_Spell
Misc Value A:
Trigger Spell : SpellID To be triggered
Amplitude : the time in MS that the trigger will land.

Spell Effect:
28 - Summon
Misc Value A:
entryID within creature_template table
Misc Value B:
"ID" Column inside summonproperties.dbc The properties preset that handles how your summon works, could be a pet, guardian, smart, dumb, faction, and more.

Apply Aura Name:
29 - Spell_Aura_Mod_Stat
Misc Value A:
0 = Strength
1 = Agility
2 = Stamina
3 = Intelligence
4 = Spirit

Spell Effect
30 - Energize
Power Resource to target
Misc Value A:
0 = Mana
1= Rage
2= Focus
3 = Energy
4= happiness
5 = rune
6 = Runic
7 = max powers
127= All powers
-2= HP

Apply Aura Name:
36 - Spell_Aura_Mod_Shapeshift
Misc Value A:
This value is in the core, inside Unit.h normally around line 173 is an Enum. If you mouse over and hold you will get a bitmask for THAT form to input into Misc Value A
Base Points -1
Die Sides 1

Spell Effect
30 - Dispel
0 = None
1= magic
2= curse
3= disease
4= poison
5= stealth
6= invis
7= ALL
8= SPE_NPC_ONLY
9=enrage
10=ZG ticket
11= old unused

Spell Effect:
50 - Trans Door
Misc Value A:
Summons an object from gameobject_template via EntryID
Gameobject summoned Column "Data0" is linked to a 2nd spell Which is the Effect spell that teleports the units upon clicking on the object summoned.
Inside Table spell_target_position(acore) ID = spell effect spellID and the rest of the position/map info is for the destination the object clickers will teleport to.

Spell Aura
69 Absorb
Misc Value A
1= armor
2= holy
4= fire
8= nature
16= frost
32= shadow
64= arcane

Combine bitmasks to total which school you want or
127 for ALL

Spell aura
79 Damage percent done
misc val A
1= armor
2= holy
4= fire
8= nature
16= frost
32= shadow
64= arcane

Spell Aura
85 Mod Power Regen
-2= HP
0 = Mana
1= Rage
2= Focus
3 = Energy
4= happiness
5 = rune
6 = Runic
7 = max powers
127= All powers

Spell Aura
107 Flat Modifier / 108 Percent Modifier
0=damage
1=duration
2=threat
3=effect1(On another spell Effects<Effects2<SpellEffect1)
4=charges
5=range
6=radius
7=crit chance
8=all effects(On another spell Effects<Effects2<SpellEffect1+2+3)
9=not lose cast time(taking damage while casting, not slowing down cast)
10=cast time
11=CD
12=effect2(On another spell Effects<Effects2<SpellEffect2)
13=ignore armor
14=cost (powers mana energy etc)
15=crit damage bonus
16=resist miss chance
17=jump targets
18=Chance of success
19=Amplitude
20=Dmg multiplier
21=GCD
22=DoT
23=effect3 (On another spell Effects<Effects2<SpellEffect3)
24=bonus multiplier
26= PPM
27=value multipler
28=resist dispel chance
29=drit damage bonus 2
30=Spell cost refund on fail

Spell Effect
108 dispel MECHANICS
0=none
1=charm
2=disorient
3=disarm
4=distract
5=fear
6=grip
7=root
8=slow
9=silence
10=sleep
11=snare
12=stun
13=freeze
14=knockout
15=bleed
16=bandage
17=polymorph
18=banish
19=shield
20=shackle
21=mount
22=infected
23=turn
24=horror
25=invul
26=interrupt
27=daze
28=discovery
29=immunity shield (paladin bubbles)
30=sap
31=enrage

Applu aura
110 Mod Power Regen Percentage
Misc Value A
-2= HP
0 = Mana
1= Rage
2= Focus
3 = Energy
4= happiness
5 = rune
6 = Runic

Aura name
137 total stat percentage
Misc Value A
0 = Strength
1 = Agility
2 = Stamina
3 = Intelligence
4 = Spirit

Aura Name
142 Aura Mod Base Resist % (Apply resist to your BASE)
Misc Value A
1= armor
2= holy
4= fire
8= nature
16= frost
32= shadow
64= arcane

Aura Name
199 Increase Spell % to Hit (Base+DIE = Hit chance, MiscValA = vs School)
Misc Value A
1= armor
2= holy
4= fire
8= nature
16= frost
32= shadow
64= arcane

Spell Aura
234 Mechanic Duration Mod Not Stack
Misc Value A
0=damage
1=duration
2=threat
3=effect1(On another spell Effects<Effects2<SpellEffect1)
4=charges
5=range
6=radius
7=crit chance
8=all effects(On another spell Effects<Effects2<SpellEffect1+2+3)
9=not lose cast time(taking damage while casting, not slowing down cast)
10=cast time
11=CD
12=effect2(On another spell Effects<Effects2<SpellEffect2)
13=ignore armor
14=cost (powers mana energy etc)
15=crit damage bonus
16=resist miss chance
17=jump targets
18=Chance of success
19=Amplitude
20=Dmg multiplier
21=GCD
22=DoT
23=effect3 (On another spell Effects<Effects2<SpellEffect3)
24=bonus multiplier
26= PPM
27=value multipler
28=resist dispel chance
29=drit damage bonus 2
30=Spell cost refund on fail

Aura Name
232 Mechanic Duration Mod
Misc Value A
0=none
1=charm
2=disorient
3=disarm
4=distract
5=fear
6=grip
7=root
8=slow
9=silence
10=sleep
11=snare
12=stun
13=freeze
14=knockout
15=bleed
16=bandage
17=polymorph
18=banish
19=shield
20=shackle
21=mount
22=infected
23=turn
24=horror
25=invul
26=interrupt
27=daze
28=discovery
29=immunity shield (paladin bubbles)
30=sap
31=enrage

Aura name
255 Mod MEchanic damage taken percent(Like a debuff on a player so they take more damage from this mechanic)
Misc Value A
0=none
1=charm
2=disorient
3=disarm
4=distract
5=fear
6=grip
7=root
8=slow
9=silence
10=sleep
11=snare
12=stun
13=freeze
14=knockout
15=bleed
16=bandage
17=polymorph
18=banish
19=shield
20=shackle
21=mount
22=infected
23=turn
24=horror
25=invul
26=interrupt
27=daze
28=discovery
29=immunity shield (paladin bubbles)
30=sap
31=enrage