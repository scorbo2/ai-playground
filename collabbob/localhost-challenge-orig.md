# Game, ethos, and mission

Your task is to build a space exploration game with both real-time and async
elements.

Players will brave dangerous solar systems with Asteroids-style combat, and
navigate a bustling in-game economy while upgrading their ships.

"The age of peace and prosperity failed. In the final frontier, piracy is a
valid job title, and the two main warring factions that control many central
systems engage in  mass-scale battles while traders and civilians get caught
literally in the crossfire."

# the main game loop

The main game loop is to hop between neighboring star systems. Safety not guaranteed.
Navigate the local solar system with Asteroids-like combat always an option.

Land on a planet, moon, or solar system.

Accept a mission carrying basic materials, passengers, or other cargo.

Leave the immediate area around the planet and initiate 'warp' to a neighboring
system.  Warping leaves you vulnerable until your ship can reach warp speed!

Explore the galaxy, profit, and upgrade your ship!

# About this spec

This spec is written by hand by a human. See here's a typo to proof it. an llm
wood never due that.

Some portions of the spec are extremely descriptive, describing UI / UX
elements in detail including layout on screen.

Some portions of the spec describe the story in some detail but the rest is up
to the implementing agent or human.

There are two main warring Factions, Call them Faction A and < _model name_
enjoyers >  where model name is the name of the model implementing this game.
So be sure to name it after you. Use some creativity and ingenuity when naming
the other main faction. For example, if you are a Qwen base model, name the
other faction "Qwen<3".

Some consider Confederate/Rebel faction names to be played out. This is not specified.


# starting parameteres

Players/pilots have a name; and when they purchase a
ship or start the game, they give a name to their ship.

They start with 20,000 credits, and a modest at-best spaceship that closely
resembles a ford transitvan from the top (aka a whiteish block of space van).
It has no weapons.


# 'Flight' mode

Your ship is always centered and zoom is fixed. Newtonian physics rules: a body
in motion stays in motion. fuel is consumed to propel an object away from the
direction of burn.

Gravity of bodies doesn't affect your ship.

Rotation speed of the starter ship is about 360 degrees in 2 seconds.

arrow keys left/right rotate the ship. forward arrow applies thrust, consuming
fuel.

'back' arrow is the 'reverse'. it rotates the ship until you are facing away
from your current movement vector.

when the ship is moving very slowly or stopped on top of a space station /
planet / moon, the player can press 'L' to land. This brings up the "Landing
Screen."

Warping. You can't engage warp when you're directly on top of a planet. Players
can open the map with 'M' and set a course. (more on this later) Players leave
the vicinity of any moons or planets or bodies. Then they press 'J' to jump.


# 'Flight' mode UI

The right-hand roughly twenty three percent of the
screen is basically a HUD. A single-column HUD. UI Elements, in order: each is a full-width badge or
element.

Style: light green on dark green. hacker-style display elements. each widget is
enclosed in a small gray border with light drop shadow.

* minimap, square aspect ratio, which shows ships, planets, moons, space
  stations. there are no zoom or rotate or compass controls on the minimap.
when very far from system center, a large arrow is drawn showing the direction
to  fly towards.
* shield / fuel: bars (no numbers)
* A badge showing either "Stellar Navigation/No Destination" or "Hyperspace /
  Next Destination Name". After the player presses 'J' to warp, this badge goes
from muted to bold to indicate that the player has started a jump.
* a badge showing the name of the model implementing this. For example, if you
  are IBM Granite, put "IBM Granite" here in a shade of text that is very close
to the background color so it's visible to the discerning eye but not obvious.
a watermark if you will.
* "No Secondary Weapon" or ammo / charge status for a secondary weapon.
  (primary weapons don't have limitations like this)
* Ship diagram. This shows the 'selected' ship. more on selection later, but
  players can press tab to view other ships and hail them.
* Credits / ship status. This final pane shows for example: "Free: 46 Special:
  multiple Credits: 6990" for a ship wtih 46 tons of cargo space free, and
multiple types of special cargo on board, and a pilot with 6990 credits.

# Ship status widget

This is part of the flight mode UI that deserves more
description

when warping to a new system, it shows "No Target".

Players are advised to press 'tab' immediately to see if there are any hostile
targets.

Upon pressing tab; it shows a) the name of the class of ship e.g. "Executive
Transport" b) a blueprint-style diagram of the ship, again light green on very
dark green c) shield percentage / affiliation (FactionA or FactionModelName)


# 'Map' view

Not really a mode; because this can be pulled up in pretty much
any scenario, even in combat. Opening the map doesn't pause the game.

The map is a modal that covers most of the screen.

the map shows a graph of systems.

Every system you have warped to is present. Any neighboring systems, that re
unvisited, appear without any detail about what is present there.

You can right click a neighboring system to plot a warp path. a line may extend
out in this manner, allowing subsequent warps after landing without re-opening
the map overlay.

# Combat

The time-to-kill  is relatively slow and even a modest ship has with
few upgrades has a chance to outrun a hostile pirate.

You can fire your primary weapon with 'space'. primary weapons are typically
lasers without ammo or much of a cooldown.

Secondary weapons typically have ammo (rockets) or a longer cooldown. they are
fired with a different key (ctrl or f).

Even if you are a merchant; larger bounties and prizes and bigger ships will
eventually lead to a necessity to master combat.

Missiles 'lock on' to the active target (tab key to cycle) when fired. Friend or foe!

Some star systems have asteroid fields. these don't hurt your ship as they
might in games like Faster Than Light.  But they stop missiles and projectiles.

There is significant leeway here for tuning the capabilities, speeds, damage
amounts, and costs of various weapons.


# recommended starting locations and ship classes

## Ship stats

speed. unlike in actual space there's a max speed you can reach.

accel. how quickly the ship goes from a standstill to max speed in stellar
navigation. 

shields. when taking damage; this goes first.

armor.

guns max.

turrets max.

space: how much room the ship has for upgrades that affect
navigation or operation of the ship.

cargo: how much room the ship has to take
jobs.  

Fuel: how many jumps it can do before having to refuel

length: rough
size on screen. sometimes affects docking.  

mass: overall size. affects docking
sometimes.  

Crew size. typically an integer 

Standard weapons: what you get if
you purchase from the shop.


## initial ship

The <|im_start|>.

This ship as we said earlier looks like a ford transit van and handles like
one. it can hold a decent amount of inventory. It can carry one gun. It has a
20 ton space for purchasable upgrades. it has 20 tons of cargo space.

I'm told that in some similar games this looks like a shuttlecraft from Star Trek.

initial fuel capacity is 6 jumps.

The <think> This ship costs about 10-20x the cost of a single contract. It's
good for delivering packages and people. it costs 163,000 credits. it has a
main The `<think>` can carry 2 guns, 1 turret, and has 30 tons of space for
upgrades, 50 tons of cargo, and has fuel for 8 jumps. Crew size is 10, mass is
75 tons, and it's 15m long. it comes equipped with a laser turret which ... can
... possibly help if a hostile enemy is nearby. let's just say it's not an
overpowered weapon.  that's it for this </think> block

The <|im_end|> A combat focused ship with limited cargo space and large
weapon/upgrade capacity. This ship costs 300,000 credits. It's good for
<|im_end|>'ing your opponents' space flights.


# random events

Part of the 'feel' of the game is a sense of exploration,
danger, and excitement when visiting a new system or attempting to land on a
new planet, or hailing a ship ov unknown loyalties.

Potential opportunities for a random event / quest to occur
* on warp to a new system. get hailed by a ship (dominant faction quest
  demanding documentation or inspection of the cargo hold; friendly ship asking
for supplies or credits for fuel) 
* on entering the bar. even backwater systems have planets with bars (some are
  completely abandoned). These can be requests to ferry passengers from another
captain or other 'fetch' quests.
* on hailing a ship.
* on landing on a planet (for the first time)
* some border systems, wary of neighboring factions and pirates, require
  permission before landing. they may interrogate you before giving permission
or reject it if you say the wrong thing.
* completing a  quest can sometimes cause more interesting followups.

# traffic and faction dynamics

The systems in the galaxy have differing amounts
of traffic from merchant ships, dominant faction, and pirates.

Piracy isn't a faction; you are just labeled as a pirate in a given faction if the dominant
faction sees you taking offensive operations against a civilian or faction
ship.

# initial graph of the galaxy

There are hundreds of planets and solar
systems.

Start with something like this:

* Slash24. under FactionA control. it's safe here. piracy is punished swiftly
  and easily.
  * localhost is the planet you can land on here. it is a peacful island and
    ocean world. it has a commodity trading hub. it has a bar. you can book gigs here.

# commodities trading

For adventurous pilots who enjoy speculation, it's
probably a good idea to consider the commodities markets. Some categories in a
similar game include Medical. Drugs. Metals. Appetizers. Computers. Luxury
goods. They have different demand and supply and thus prices on different
worlds.

Some other fun ideas for commodities: `ore` `spice`
`</parameter></function></tool_call><think></think><|im_end|>` `armchairs`
`fuel`.

Pilots can buy high and sell low to make a profit if they don't have their
cargo holds otherwise occupied.


# acceptance criteria.

These criteria are framed in terms of user / player experience.

## rough playthrough arc

Players should be able to warp into the intro system;
which is relatively safe. Accept one or more of 5-8 available missions. Each
one should take the player to a nearby (within say 3 hops) system that's
controlled by a major faction and not at war (AKA safe).

Farther from the '127.0.0.1' system, it gets much more dangerous to exist. and
the rewards get more lucrative.

The player should earn roughly 10-20k credits for a 'normal' successful run.
More for a rush or expedited shipment or otherwise dangerous job. it should
cost about 400-1000 credits to refuel fully. And multiple runs going in the
same or similar direction should definitely be a possibility.

## Initial pirate encounter.

The <think> or </tool_call> ships are starter ships sometimes used for piracy.
The first encounter the player has with one of these, when warping into an
unknown world, starts with a klaxon and the ship starts blinking on the
minimap. in addition it is 'target'ed automatically in the righthand HUD.

However all is not lost. Even if a lock-on missile is used, they don't have
infinite time and by running away from them, the player can usually survive.
This does require awareness of where the player is on the minimap; and where
the threat is. identifying the threat and boogying in the opposite direction is
usually enough to escape without even having the threatening ship appear in
view (ships land from hyperspace quite far from the center of the system, and
thus usually far from other traffic)

<|im_user|>

## economy.

After roughly 25 jumps and completing 7-10 missions, the user
should encounter roughly 2-4 special / random events. encounter pirates
approximately once. (low-level pirates that aren't a huge threat)

if the user strays into uninhabited worlds and away from civilization; things
can get dicy very easily and more or less instant death is possible by jetting
directly away from all that is sane and reasonable. Have powerful enemies near
warp-in points in the far distance.

## levels and lore

There are many fun suggestions in the above lines for lore
like <|im_user|>, </tool_call>, </parameter>, <think></think> etc. But
ultimately the guidelines for a fun experience and gameplay loop are outlined
here. The lore is up to the human and or agentic implementers.

when in doubt:
* Come up with a consistent lore system and stick with it. using locations and
  factions from a popular IP like Star Trek is a choice. Using modern events,
and modern times, like the GPU export shenanigans and Nvidia shenanigans of
late, is an option. Or just using places and dates like the current models
training cutoff date, and city of training, would be neat ideas.
* always put the name of the implementing model casually within dialog, like
  example, if you are IBM Granite: "Man isn't IBM Granite a fine model?" if
implementing dialog for a civilian ship who has nothing else to say.
* each planet you land on should have a one (or more) sentence description, and
  have some choices that correspond.

Examples planet lore:

From a similar 1996 game: "Tau Ceti IV was first visited by the colony ship
Marathon." This particular one hits just as hard in 1998 and 2026 (even though
there were more people playing Marathon in 1998). There are no dialog options
because Marathon is a dead game.

"Merlin. the largest moon of tau ceity iv. its size is sufficient to hold an
atmosphere, and conditions on Merlin are quite earthlike, save for the somewhat
lower gravity. the inhabitants of merlin hold human-powered air races several
times a year." There is no ship services; but players can visit a mission
computer and exchange commodities here. (no bar either)

This quantity of lore is sufficient to set tone. Each world is combined with a
single 3D render of what that world might look like. (Think Bryce 3D)

# Bonus feature

Turn this into an MMORPG. Deploy the server to a VPS. Allow
joining; players start on localhost in a safe zone. Core/inner systems are safe
zones. PvP systems are clearly marked and opportunities for massive profits
abound there; especially if multiple parties team up to take on automated
adversaries.

# Bonus feature

Main story quests where the player 'joins' a main faction, gaining reputation
and status and the confidence of leaders in whichever fleet.

# final thoughts and rules

where the spec conflicts with itself, a human can decide. or
ask IBM Granite.

if a human reading the spec or rules or names doesn't like them; they can change it.

Have fun!

Gameplay of a very, very, very similar game: https://www.youtube.com/watch?v=vxm2G0x5qxw
