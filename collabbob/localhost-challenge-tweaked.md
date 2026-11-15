# Game, ethos, and mission

Your task is to build a space exploration game with both real-time and strategy elements.

Players will brave dangerous solar systems with Asteroids-style combat, and
navigate a bustling in-game economy while upgrading their ships.

The player controls a small craft shaped like a cargo shuttle (blocky and
rectangular-ish, not sleek and angular). It has a weak projectile weapon
but it is not designed for combat. The ship has cargo and passenger space
so that the player can ferry passengers and carry cargo from system to system
to earn money (credits).

The ship has limited fuel (1000 units). Tactical movement (thrusting around
in tactical mode) costs a small amount of fuel, jumping from system to system costs
a large amount of fuel. The player can refuel at any system, for a cost.

The player starts with 20000 credits. The goal is to reach 1 million credits.

There are two warring factions: The Localhosters and The Bobbers. The player
is initially neutral, and neither faction is initially hostile to the players.
Additionally, a third faction named Pirates are always hostile to everyone, including
the player.

## Technical constraints

This is a Python project:
- only dependencies are `pygame-ce`, `pygame_gui`, `pydantic`, and `loguru`
  (recommend pinning `pygame_gui` version `0.6.11` from June 2024 to avoid
  API drift introduced in `0.6.12`, but this is up to the implementor).
  Pytest is a permitted additional dev dependency.
  Implementation note: `pygame.init()` / `display.set_mode()` must come before
  `UIManager` construction.
- the game is split into modules in the `src` subdirectory, with a small
  `main.py` shim in the game's root directory. `src` is a package, the root
  should be on `sys.path`, tests import `src.*`.
- the game is driven from `config_*.json` configuration files which must exist in
  the same directory as the `main.py` shim. If any of these files (`config_easy.json`,
  `config_medium.json`, or `config_hard.json`) are missing, unreadable,
  or do not contain valid Json, the game should exit immediately with
  an error printed to stderr.
- game resources (audio, images, etc) should be stored in the `resources`
  subdirectory (sibling of `src`).
- a root-level `README.md` with basic setup/run instructions (creating a venv
  and activating it) should be provided. This README should also outline
  game controls and general usage information.
- The game loads in a non-resizable 1024x768 window. There is no fullscreen option.
  All co-ordinates and pixel dimensions listed in this spec assume a 1024x768 game window.
- The game is locked to 60FPS via a fixed timestep of 1/60 with a bounded accumulator;
  ignore real dt for simulation. (This also assists the unit test suite).
- The game title is "The velocity of escape".

## The title screen

When started, the game displays the title screen, with options allowing the
player to start a new game or to exit.

The title screen's background is loaded from `resources/title_screen.png`, if it
exists and is a valid, readable image. Otherwise, the title screen's background
is plain black. If an image is successfully read, it should be scaled/stretched
as needed to fill the background.

The game title should be displayed in large text centered in the upper half of the
window. The user choices "New game" and "Exit" should be buttons centered
(vertically stacked) in the bottom half of the screen.

## Configuration

The game code should avoid the use of constants or hard-coding for game parameters.
As much as possible, make use of the game configuration file that is read once on
startup. Good things to place in the game config file: all tunable numbers, geometry,
palette, probabilities, fare formulas, and lore text. Bad things to place in
the config file (overengineering): keybindings, enum-like IDs, colors-as-defaults -
these things can live in code. Chicken-and-egg exceptions are: window size, window
dimensions, and game title. These can live in code, to avoid problems caused by needing
them at startup before the game config is loaded.

The following structure is an illustrative sketch, and is not meant to
be exhaustive. Add keys here as needed during implementation, and try to keep their
naming/grouping structure self-descriptive:

```json
{
  "rng": { "seed": null },
  "new_game": {
    "starting_credits": 20000
  },
  "player_ship": {
    "fuel_capacity": 1000,
    "passenger_space": 5,
    "cargo_room": 20,
    "shields": 50,
    "armor": 100,
    "weapon_power": 10,
    "weapon_fire_rate": 1,
    "turn_rate_deg_per_sec": 180,
    "weapon_range": 1200,
    "acceleration_rate": 0.2,
    "top_speed": 5,
    "length": 40,
    "width": 20
  },
  "upgrade_steps": {
    "shields": 50,
    "armor": 100,
    "engine_percent": 20,
    "weapon_damage": 15,
    "fuel": 250,
    "cargo": 20,
    "passenger": 5
  },
  "tactical": {
    "system_pixel_size": 2000,
    "fuel_burn_per_frame": 0.2,
    "landing_range": 100,
    "planet_diameter": 40,
    "launch_immunity_frames": 120,
    "jump": {
      "fuel_cost": 250,
      "frames": 180,
      "acceleration": 1.2
    },
    "stars": {
      "count": 150,
      "grey_min": 128,
      "grey_max": 255
    }
  },
  "combat": {
    "projectile_speed_bonus": 8,
    "projectile_radius": 3,
    "pirate_bounty": 10000,
    "bobber_bounty": 5000,
    "localhoster_bounty": 5000
  },
  "economy": {
    "win_credits": 1000000,
    "fuel_cost_per_unit": 2, "repair_cost_per_point": 4,
    "upgrade_base_cost": 1000, "upgrade_cost_multiplier": 2, "upgrade_max_level": 5,
    "upgrade_offers_min": 2, "upgrade_offers_max": 5,
    "missions_min": 4, "missions_max": 8,
    "cargo_fare_per_unit": [150, 400], "passenger_fare_each": [800, 2000],
    "far_destination_bonus": 1.5,
    "cargo_types": ["iron ore", "wine", "textiles", "computer parts", "colony supplies", "machine parts"]
  }
}
```

There should be THREE configuration files: `config_easy.json`, `config_medium.json`,
and `config_hard.json`. All three files have identical key sets. These files should
be tuned accordingly. That is, the "easy" config file should have a generous economy,
light fuel usage, better starting player ship stats, and so on. The "hard" file should
make the game more difficult to win, by offering missions that pay smaller fares,
causing the player's ship to burn fuel more rapidly, making upgrades more expensive,
and so on.

### Validation

- Unrecognized keys are fatal.
- Missing expected keys are fatal.
- Empty/invalid/unparseable/missing Json files are fatal.

Json detection and parsing for ALL THREE files should be performed at startup,
with an explanatory message output to stderr if anything goes wrong.

These files are not monitored! They are read and parsed once at startup.
If the user or some other process makes changes to these files while the game
is running, those changes do not take effect until the next time the game is started.

## New game

Clicking "New game" from the title screen should show a question dialog asking
the user to select a difficulty level: Easy, Medium, or Hard.
Their response decides which of the three game configuration files to use. Canceling
the question dialog returns to the title screen and does not begin a new game.

Starting a new game resets the visibility of the system map such that only Alpha,
Bravo, Charlie, and Delta are visible. The player is given a starting balance of
`new_game.starting_credits`, and a ship with starting stats provided by `player_ship`.
The player's ship is initially empty (no cargo, no passengers) and they start
in the Alpha system with no other system selected.

## The system map

The player starts in the Alpha solar system. There are 26 solar systems in total,
but only those nearest to Alpha are visible on the System Map at the start of the game.
The systems are named after the NATO phonetic alphabet: Alpha, Bravo, Charlie, Delta,
and so on, up to Xray, Yankee, and Zulu. 

The system map can be brought up at any time during play by pressing M. The system
map is displayed as a node graph. Each system has at least one and at most three connections
to other systems. At the start of the game, the Alpha system is visible in the center
of the map. Systems are represented by a filled white circle with a small text label
next to it. A thin gray connecting line connects to other systems. At the start of the game,
the Alpha system is visible, as are the Bravo, Charlie, and Delta systems. These are the only
visible systems initially. Bravo, Charlie, and Delta are visible because they are each
directly connected to the Alpha system, where the player starts.

While the System Map is visible, the user can click any visible system to select it,
provided that it is directly connected to the current system. For example, if Alpha
connects to Bravo and Bravo connects to Golf, and the player is currently in Alpha,
then the player cannot select Golf. They must first select/jump to Bravo, and THEN Golf.
The current system cannot be selected, because the player is already there. The selected
system is indicated by light gray `[`, `]` markers on either side. Clicking an already-selected
system unselects it, leaving the player with no system selected. When a system
is selected, exiting the system map screen (ESC) and pressing J will initiate a jump
to the selected system, assuming the player has enough fuel to initiate a jump.

Upon arriving in the destination system, its connecting systems are now permanently
made visible on the map screen if they weren't already visible. For example, traveling
to the Bravo system for the first time may reveal that it also has a connection
to the Golf system. Remember that each system has at least one connection and at most
three connections to other systems. It is therefore possible to travel to a "leaf" node
that has no other connections. In that case, the player's only jump option is to
travel back to the system where they were previously.

The connections between systems are randomly generated at the start of each new game,
with the only exception being that Alpha always has a direct connection to Bravo, Charlie,
and Delta.

In this way, the player can gradually reveal the entire node map of all 26 connected systems.

The entire graph must be connected! There are no "island" nodes that are unreachable.
The graph must be displayed in such a way that systems and their labels do not overlap in the
map display. The length of connecting lines can vary as needed to satisfy the display requirements.
The map connections and display should be decided once at the start of a new game.
Do not re-layout the map each time the map display is brought up (that would be visually
confusing to the player).

Jumping to a new system clears the system selection. There never a system selected
after a jump. The player must bring the map view back up and select a new destination.

## System characteristics

Each solar system has exactly one planet where the player can land. The planet is represented
by a colored circle at the exact center of the tactical map. The planet is represented at roughly the
same size as the player's ship. The player's ship cannot "collide" with the planet - it passes
straight through. (Draw the player's ship after the planet so that the ship never appears
to move "behind" the planet). However, when the player's ship is within `tactical.landing_range` pixels
of the planet's center, a message "Press L to land here" appears near the top of the tactical display.
Pressing L will bring up the spaceport interface (a full-display modal).

Note: when entering a system, the player never starts near the planet! They must always travel
by thrusting towards the planet, using the minimap to guide them (see Minimap section).

Each solar system has a small random chance to contain other ships which may attack the
player's ship. The farther away the system is from the Alpha system, the larger this chance
becomes. (Implementation note: we will use the system's alphabetic name to determine this
distance, ignoring the physical layout of the System Map. For example, the Zulu system always
has the highest chance of spawning other ships, and the Bravo system always has the lowest
nonzero chance). The Alpha system is always safe and never spawns ships (0% spawn chance).

Because the player's ship is not a combat vessel, it is usually no match for hostile ships.
The player must either initiate a jump to escape the system, or land on the system's planet.
The player cannot take damage while landed on a planet. But a hostile ship can wait for the player
to launch again, and resume their attack.

## Spaceports

Each system's planet has a spaceport interface which appears after pressing L to land there.
The spaceport interface is a full-display modal. The simulation is paused while the spaceport
interface is displayed.

This interface is where the player can accept cargo to be hauled to a specific destination
system, and/or passengers who wish to travel to a specific destination system. The destination
system in question is randomly selected (but never the current system). Note that the destination
system may not yet have been discovered by the player - this is fine. For example, the player can
accept cargo destined for the Zulu system even before they know how to get to Zulu. Each such
mission has a "fare", which is an amount of credits that the player will earn for successfully
delivering the cargo and/or passengers. For example, a possible mission would be "2 passengers
destined for Yankee. Fare: 500 credits", or "10 units of iron ore, destined for the Lima system.
Fare: 250 credits". Possible cargo types should be randomly selected. Suggestions include:
iron ore, wine, computer parts, colony supplies, machine parts, etc. The larger the unit count
of the cargo, the larger fare the player should earn for accepting the mission. Likewise,
the higher the passenger count, the higher the fare. Each spaceport offers between 4 and 8
possible missions, randomly selected when entering the system. The fare for cargo and passengers
can earn a "far bonus" based on the minimum number of jumps required to reach the destination -
longer trips should earn higher rewards. The "far bonus" is calculated and displayed in the
spaceport interface even if the player does not yet know how many jumps are required to
reach the distance, because they have not yet discovered the destination.

If the player is already carrying cargo and/or passengers destined for the current system,
that cargo and/or those passengers are automatically unloaded as soon as the player lands.
A message appears to indicate this, and their credit balance is increased according to the
agreed-upon fare.

The player's ship has limited room! The player cannot take on more passengers and/or cargo
if their ship is already at or too near capacity to accept the new mission. For example, if
the player is currently carrying 6 passengers with a passenger capacity of 8, and a mission
is available to transport 4 passengers, the player cannot accept that mission, because they
do not have enough room for all 4 passengers. The player can upgrade their ship to allow
additional room to accept larger fares.

A mission cannot be "canceled" once accepted. The cargo and/or passengers are loaded immediately
and can only be unloaded by landing at the destination system in question.

Spaceports also offer an option to refuel the player's ship, if the player has enough credits,
and to repair any damage to the player's armor. These cost credits at a rate that
should be specified in game configuration. Note: the player's shields automatically recharge
to full at no cost when landing at a spaceport. There is no explicit "repair shield" option.

The spaceport interface has a "Launch!" button, which will leave the spaceport and re-enter
tactical mode.

### Leaving spaceport

The player craft is immune to all damage for 120 frames (2 seconds at 60FPS) after leaving
spaceport. The player craft's position is remembered from where it was when the player
pressed "L", but its velocity is reduced to 0.

### World lore

The spaceport view should clearly display the current system name and one line
of random lore decided at the start of a new game.

Example system lore:

- "(System) was first visited by the colony ship Marathon."
- "(System) is a peaceful world with lush jungles and peaceful landscapes".
- "(System) is a rocky world with many active volcanoes."
- "The conditions on (System) are largely Earthlike, save for the somewhat lower gravity."

This quantity of lore is sufficient to set tone.

Implementation note: consider using a `resources/lore.txt` file with the game randomly
selecting from the pool of lore descriptions there (one per line) rather than
cluttering the game configuration files with this. Make it a fatal error if the
file is missing, unreadable, or empty. It is not an error if a lore entry does
not contain the replaceable tag "(System)", nor is it an error if this tag appears
more than once. Replace any instance of "(System)" (case insensitive) with the name
of the system to which this lore is assigned.

Lore should be randomly selected for each system once at the start of each game!
Don't randomly select lore for a system each time the player enters it (confusing).
Note: if there are fewer than 26 lore entries, some systems will have duplicate lore.
This is acceptable. If there are 26 or more lore entries, the code should randomly
select lore that has not already been assigned, to avoid duplicate lore across systems.

## Ship upgrades

Ship upgrades can be purchased at any spaceport, for a price. The availability of ship
upgrades is determined randomly upon entering each system. The upgrade types are:

- shields. Absorbs damage from enemy projectiles without harming the player craft.
- armor. Increases the amount of damage the player's ship can suffer before being destroyed.
- engines. Increases the player ship's acceleration and top speed.
- weapons. Increases the damage of the player ship's projectile weapon.
- fuel. Increases the player ship's fuel capacity.
- cargo room. Allows the player ship to expand their cargo capacity.
- passenger space. Allows the player ship to accept more passengers.

The more a particular stat is upgraded, the more expensive further upgrades become.
Stats have a max upgrade level, at which they cannot be upgraded further.

## The tactical display

The majority of the game takes place in the tactical display. The left two thirds of the
display are the game view. This is a top-down view of the player's ship and surrounding
area. The player's ship is always centered and zoom is fixed. Newtonian physics rules: a body
in motion stays in motion. fuel is consumed to propel the ship away from the
direction of burn. The background of the game view is a starfield on a black background.
The stars scroll based on player movement. For example, if the player's ship is moving
directly right at a speed of 5 pixels per frame, then the stars should indicate this movement
by moving left at a rate of 5 pixels per frame. There is no parallax scrolling - all stars
scroll at the same rate. Stars don't need to persist once falling offscreen. They can randomly
spawn as needed. There should be 150 stars on screen at any time. Stars are single-pixel
grayscale (not small squares or circles, just single pixels) with a randomly-selected
RGB between (128,128,128) and (255,255,255).

Gravity of bodies (planets, other ships) doesn't affect the player ship.

Rotation speed of the player's ship is about 360 degrees in 2 seconds.

Pressing M at any point during tactical play (except when a jump has been initiated)
pauses the game and brings up the System Map view, which is a modal that fills the
entire screen. Pressing ESC exits the map view and returns to the tactical display.

Arrow keys left/right rotate the ship (hold to rotate continuously, release to immediately
stop rotating). Up arrow applies thrust, consuming fuel and applying thrust as long as the
key is held. Down arrow means 'reverse course'. Press once to automatically rotate the ship 180
degrees and then stop. It does not apply thrust. Holding down has no effect - the key must be
released and pressed again to initiate another 'reverse course'. Pressing down arrow while
a 'reverse course' rotation is in progress begins a new one, using the ship's current facing
direction as the start of a new 180 degree rotation.

The player's ship accelerates at a rate of `player_ship.acceleration_rate` pixels per frame
squared in the ship's facing direction while Up is held, up to a maximum speed of
`player_ship.top_speed` pixels per frame.

Pressing J when in tactical mode will initiate a jump to the selected system, if one was
selected in the map screen. If no system is selected, J does nothing. The player can't
initiate a jump when they are within landing range of a planet. The jump should be animated,
with the player's craft accelerating greatly in the facing direction for three seconds (180
frames at 60FPS). This jump acceleration may exceed the player craft's usual top speed.
A jump cannot be canceled after initiation. All user input is ignored during the jump animation.
Fuel for the jump is deducted at the start of the jump. If the player lacks fuel for the jump,
the jump cannot be initiated (briefly overlay an "insufficient fuel" message in the tactical display).
The player is not immune to damage during the jump animation!
Projectiles in flight can still impact the player craft and do damage!
The player is exempted from the system boundary when a jump is initiated. That is, if the player's
ship reaches any boundary edge during a jump acceleration, they do NOT stop, but rather keep going.
**Special case**: pressing J to initiate a jump when the player has the *exact* fuel amount
required to jump triggers an immediate game over. Do not animate the jump, just go to the game over screen.

Each system is a large square with side length `tactical.system_pixel_size`. The player's
ship cannot leave the system boundaries (except by jumping). When at any edge of the system,
the player's ship cannot move any further in that direction (except by jumping). The system
has no visible border - briefly overlay a message "System boundary reached"
in the tactical display at most once every five seconds when the player's ship is in contact with any
edge. Note that the player can continue to thrust and consume fuel when faced up against a boundary
edge - they just can't move further in that direction.

Pressing ESC in the tactical display brings up an "Exit game?" question modal. If the user
confirms, abandon current game and return to title screen.

## HUD

The right third of the screen is used for the HUD. This is a single-column view of
the following components, from top to bottom:

- minimap, always square. There are no zoom or rotate or compass controls on the minimap.
  See Minimap section for more details.
- Ship status. This shows "shield", "armor", and "fuel" labels on one row each, with a simple
  bar display next to each (no numbers).
- Navigation status. This is a single-line control that either reads "No destination"
  if no system is currently selected, or "Hyperspace / (selected system name)" if a system
  is selected. During a jump animation, this text should go from muted to bold to indicate
  that a jump is in progress.
- Nearest ship readout. Upon entering a new system, this display reads "no target".
  See "Nearest ship readout" section for more details.
- Credits and cargo status. This section shows the player ship's current passenger and
  cargo used/capacity, and their current credit balance, each on a separate line. For example,
  "Cargo: 16/50", "Passengers: 4/10", "Credits: 2500" would indicate that the player is carrying
  16 units of cargo out of 50 cargo space, and 4 passengers out of 10 passenger space, and 
  that the player has a balance of 2500 credits.

No part of the HUD is directly interactive. It is a read-only display.

The styling of the HUD should be generally light green on dark screen, hacker-style.
Each HUD component should be enclosed in a 2px gray border.

### Minimap

The player's ship is always a white 2x2 square at the center of the minimap. Pirate ships
are represented as red 2x2 squares, if present. Localhoster ships are 2x2 cyan squares,
and Bobber ships are 2x2 yellow squares. The system's planet is represented as a
green 4x4 square. If the player's ship is too far away from the planet for both to be
present on the minimap at once, a large arrow should appear in the minimap showing the
player which way to fly to reach the planet.

The minimap is scaled to fit its display area. That is, if the world map is 10x the size
of the minimap's display area, then minimap pixel represents 10x10 real world pixels.
This scaling may result in ship indicators that overlap, if the ships are in close
proximity - this is acceptable. 

### Nearest ship readout

When entering a new system, the nearest ship readout component in the HUD should
always show "No target".

The player can press T to scan for ships in the current system. If any are present,
the nearest is displayed here, with the following information:

- alignment. One of "Localhoster" (in cyan text), "Bobber" (in yellow text), or
  "Pirate" (in red text).
- shield. A shield label and bar for the ship, displayed similarly to the
  bar in the player's own Ship Status component.
- armor. An armor label and bar for the ship, in the same style again.

The currently-displayed ship remains displayed here even if it is no longer
the currently-nearest ship.

If the currently-displayed ship is destroyed, this component reverts to "No target".

Pressing T again when a ship is already displayed will switch the component to
displaying stats for the currently-nearest ship (this is a no-op if the currently-shown
ship is still the currently-nearest ship).

## Political relations

When starting a new game, Localhoster ships and Bobber ships will ignore the player's ship.
If the player hits a ship of either faction, that faction will become hostile to the player
for the remainder of the game. Pirate ships are always hostile to all other ships.
Localhoster and Bobber ships are always hostile to each other. Localhoster and Bobber
ships are always hostile towards Pirate ships.

Entering each system (except Alpha, which always has a spawn chance of 0) has a small chance
to spawn a random number of between 1 and 4 ships of randomly-selected alignments. Those
ships have random starting positions within the system. All of these ships are aware
of each other, and of the player, and will react according to current political relations
as described above.

Other ships have unlimited fuel but cannot initiate jumps. They remain active in the
system until the player jumps to another system, or until they are destroyed through combat.
All ships have projectile weapons. Other ships have randomly-selected stats for shields,
armor, and weapon power. These stats should always be quadruple the player ship's
starting stats, plus or minus a randomly chosen margin of up to 50%. For example, if
the player's ship starts with 50 shield, 100 armor, and 20 weapon power, then other ships should have
shield of 200 plus or minus 100, armor of 400 plus or minus 200, and weapon power of 80
plus or minus 40. Always use the STARTING stats for these calculations, not the current stats, with
upgrades that the player has purchased. With enough upgrades, combat should become
a viable option for the player. Other ships have a firing rate and projectile range
equal to the player's starting stats. Their projectile colors should match their faction
colors (Localhoster projectiles = cyan, Bobber = yellow, Pirate = red). All projectiles
are solid 3px diameter circles.

### Combat

The player's craft has a projectile weapon with unlimited ammunition. The player
can press "space" to fire a projectile in the craft's facing direction. Player projectiles
are solid green 3px diameter circles that travel in the ship's facing direction with an initial
velocity equal to the ship's velocity plus 8 px/frame in the ship's facing direction.
The player can fire `player_ship.weapon_fire_rate` projectiles per second (per 60
frames at 60FPS). Pressing space while the weapon is "reloading" does nothing.
Holding space will release the configured number of projectiles per second.
Projectiles have a max cumulative travel distance of `player_ship.weapon_range` pixels.
If they reach this distance without hitting any other ship, they are harmlessly
removed from play.

If a projectile impacts a ship, damage is done first by subtracting the weapon's power
rating from the target ship's shields, and then from its armor. If the target ship's armor
is reduced to 0 or below, that ship is destroyed.

The player's shields refill to their capacity after each jump. The player's armor
does not regenerate - it must be repaired at a spaceport. If the player ship's armor
drops to 0 or below, the game is over.

If a player projectile impacts a Localhoster or Bobber ship, that faction becomes
permanently hostile to the player.

Ships cannot collide - they pass through each other.

Colorful particle effects should accompany all projectile impacts, and larger
particle effects should accompany ship destruction events.

The system's planet is immune to projectiles - they pass through.

Ships do not "respawn" when destroyed. Ships only spawn once when the player
enters the system. Leaving the system via a jump, and then returning to that
system via another jump does not "remember" the quantity or types of ships
that were there when the player was there earlier. Every jump to any system
(except Alpha, which has a spawn chance of 0) has a chance to spawn a new
random selection of ships.

Other ships have random starting positions within the system when spawning.
Other ships have a starting velocity of 0 and a random initial facing direction.

Other ships do not have shield or armor regeneration.

Destroying a Pirate ship earns the player a 10000 credit bonus. Briefly overlay
the message "10K bounty paid! Pirates destroyed." in the tactical display. Note:
the Pirate ship in question must have been destroyed by a player projectile,
not from any other ship's projectile.

Destroying a Localhost ship earns the player a 5000 credit bonus from the Bobber
faction, and vice versa. Briefly overlay the message "(Faction) sends their thanks!
5K bounty paid." in the tactical display. This ONLY applies if the paying faction
is not hostile to the player. If the player has made enemies of both factions,
then no reward is offered for destroying ships from either side.

There is no friendly-fire. Projectiles can pass harmlessly through the ship
that fired them. Projectiles fired from any faction ship pass harmlessly
through other ships of the same faction.

Ship hitboxes are simple circles with a diameter equal to the longest measurement
of the ship in question. For example, if a ship is 40 pixels long and 20 pixels wide,
then the hitbox is a circle with diameter 40 pixels centered on the ship. Any projectile
that enters that circle counts as a hit.

### AI

Other ship AI can be quite basic:
- thrust towards the nearest hostile ship.
- when within weapon range, stop thrusting and fire at max
  firing rate with a configurable aim "jitter".
- if there are no hostile ships in the current system, hold position.

The player does not earn any points when other ships destroy each other in combat.

### Other ship designs

Localhoster ships should be long and angular, like an arrow.

Bobber ships should have more of a rounded shape, like a flying saucer.

Pirate ships should have a multi-pronged design (sharp nose with forward-swept wings).

All ships should be roughly the same size as the player's ship.

## Game over

There are several ways the game should end. Each leads to an "end screen"
which summarizes the outcome of the game:

- the player's ship runs out of fuel outside of landing range
  of any spaceport: "Stranded! Lost in space!". Note that due to Newtonian
  drift, an out-of-fuel ship could theoretically still reach the landing
  zone, but the game deliberately does NOT respect this. Hitting fuel 0
  outside of the landing zone is an instant game over. Note: this also
  includes the special case of initiating a jump with the exact amount
  of fuel required for a jump.
- the player's ship armor reaches 0 or negative: "Ship lost with all hands!"
- the player does not have enough fuel to jump and cannot afford to refuel
  their ship at a spaceport: "Bankrupt!" Be careful to evaluate this one
  only after arriving at a spaceport, because the auto-unload of cargo and/or
  passengers may increase the player's credit balance to the point where
  they can afford to refuel their ship once again. If the balance is still too
  low after auto-unload to refuel the ship, trigger this ending.
- the player reaches one million credits: "You're a millionaire! You win!"
  Likewise, this ending condition is evaluated after arrival at any
  spaceport. (That is, winning a combat bonus that puts the player over
  the winning amount does not immediately end the game - they must land
  at any spaceport for this condition to be evaluated).

A button labeled "Return to title screen" should be presented.
Clicking that button or pressing ESC should return to the title screen.

## Audio

The game should use generated sound effects (stdlib `array` module and 
`pygame.mixer.Sound(buffer=...)`; no numpy):

- simple short confirmation beeps when the player selects something either
  in the map view or in the spaceport view.
- projectile noises when any ship fires (even ships currently offscreen)
- small explosion noises when any ship is hit; larger explosion noise on any ship destruction.
- an alarm klaxon upon pressing T in tactical view if a hostile ship is displayed.
- a "spinning up" sound effect when a jump is initiated

Audio mixer init failure must never be fatal! Skip audio if the mixer
cannot be initialized. (Tests use a dummy audio driver so audio must fail soft).

## Testing

The game should have a hermetic test suite. Suggestions: 
- never use the actual game config file: always provide a fabricated one. The fabricated
  configs may include a "fast-win" config to avoid very long test simulations to achieve
  victory.
- use a dummy display and audio driver.
- use a frame accumulator to help simulate events.
- for any tests involving randomness, use an injectable `random.Random` instance that
  is threaded through the game.

## Dev plan

The game is too large and complicated to implement in a single pass.
Implement exactly one stage below at a time. Don't commit or push when
done! Report stage completion and stop so that manual review can be
performed before committing and proceeding to next stage.

Implementation note: if the spec is silent or underspecified on any point,
make an implementation decision and append it to `DECISIONS.md` in the project
root directory. This provides a record of any area where the specification
needed work. Do not encode silent choices in code alone.

Implementation note: because unrecognized config keys are fatal, any stage that
adds keys must add the config files + fixture changes in the same commit as the new key(s).

- **Stage 1** — Walking skeleton + tooling. `main.py` shim, `src/` package, `config_*.json`, `README.md`,
  pinned `requirements.txt`, config loader with validation (missing/unreadable/invalid JSON → stderr + exit 1),
  1024×768 non-resizable window, headless pytest harness (`SDL_VIDEODRIVER=dummy`, `SDL_AUDIODRIVER=dummy`, 
  `config-factory` fixture, `pump_events`/`advance(frames)` helpers), generated `resources/title_screen.png`
  plus its generator script. Create `DECISIONS.md` if not exists. Gate: `python main.py` opens a window;
  four config-failure tests pass; suite runs headless in CI.
- **Stage 2** — Scene manager + title screen. Modal/scene stack (needed for map and spaceport later), title screen
  (background stretched, title centred in upper half, two stacked `pygame_gui` buttons centred in lower half),
  difficulty setting question dialog with cancel option, config-file selection based on difficulty selection,
  confirmation-beep plumbing with fail-soft audio, quit handling. Gate: synthetic mouse click on "New game" transitions to a
  placeholder scene; click "Exit" quits; no crash with dummy audio.
- **Stage 3** — Pure model core (no pygame). GameState, player ship, stat blocks, injectable RNG, fixed-timestep
  integrator with bounded accumulator, acceleration/top speed/Newtonian drift, turn rate, reverse-course 180° edge-trigger
  state machine, fuel accounting. Gate: unit tests — 60 frames of thrust from rest with acc 0.2/top 5 reaches exactly 5 px/frame;
  velocity persists with no input; Down rotates exactly 180° in exactly 60 frames (or per config); pressing Down mid-rotation restarts from current heading.
- **Stage 4** — Tactical view, camera, starfield. 683px view, ship centred, `world_to_screen` as a pure function, planet
  at world origin, procedurally drawn blocky shuttle (cached surface rotation), 150 world-anchored recycling stars, no ship/planet collision.
  Gate: star count invariant over 1000 frames; rightward movement shifts stars left by the same delta; `world_to_screen` golden tests.
- **Stage 5** — Input layer. Key handling separated from simulation; rotation/thrust/reverse semantics; space → fire (no projectile yet);
  bindings M/J/L/T/ESC registered; input-lock flag for jumps.
  Gate: event-pump tests for hold-vs-tap, reverse-course rules, and that a locked flag suppresses all controls.
- **Stage 6** — HUD + minimap + landing prompt. Right-third HUD with 2px grey borders and palette from config:
  shield/armor/fuel bars (no numbers), nav status ("No destination" / "Hyperspace / X", bold during jump), nearest-ship placeholder
  ("No target"), credits/cargo/passengers. Square minimap: white 2×2 ship, green 4×4 planet, red 2×2 enemies, large arrow when the
  planet is off-map. "Press L to land here" within landing range, drawn over the game view.
  Gate: pure functions for bar widths, status strings, and arrow direction (all four quadrants) are unit-tested;
  a layout test asserts HUD components don't overlap and fit in 341px.
- **Stage 7** — System graph + map view + fog of war. Graph generator (26 NATO names, connected, degree ∈ [1,3],
  Alpha↔Bravo/Charlie/Delta guaranteed, Alpha degree exactly 3), layout computed once per game and cached, M modal
  over the whole screen, ESC back, white circles + labels + thin grey edges, neighbour-only click selection with [ ] brackets,
  toggle-off, current system unselectable, reveal-on-arrival permanently, map blocked during a jump.
  Gate: property tests over ≥200 seeds for all graph invariants; select/unselect/gating/visibility transitions; node+label overlap check; determinism per seed.
- **Stage 8** — Jumping. J with a selection → fuel check with visible feedback → 180-frame animation at high
  acceleration exceeding top speed, input locked, no cancel → new system entered (NPCs despawn/respawn, shields refilled, selection
  cleared, spawn away from planet, velocity reset). Jump blocked inside landing range. Jump spin-up sound.
  Gate: frame-exact animation length; fuel deducted exactly once; blocked cases verified; shields full after arrival;
  spawn distance within config bounds.
- **Stage 9** — Spaceport + economy (vertical slice complete). Land/launch (no damage while landed), `pygame_gui` spaceport screen showing system name + lore,
  4–8 generated offers (cargo-only / passenger-only / mixed) with destination never the current system and fares monotonic in size
  and distance (monotonic within a generated mission: `fare = units * rolled rate * distance_multiplier`), capacity gating with
  rejection message, auto-unload + payout exactly once on landing, refuel and repair at config rates,
  per-system random upgrade offers with an escalating per-stat cost curve and a hard wall past level 5, purchases never taking credits
  below the floor; upgrade magnitudes driven from config. Gate: seeded generation invariants; capacity rejection; unload crediting once and only once; upgrade cost curve table;
  no purchase path producing credits ≤ 0. Checkpoint: the core exploration loop is playable — stop and review here.
- **Stage 10** — NPCs, factions, AI. NPC entity stats (≥ player's per config formula,
  seeded spawn chance by alphabetic index with Alpha at 0, 1–4 ships at random positions, unlimited fuel / no jumping, steering controller
  (face, close to range band, aim with jitter, cooldown fire), faction hostility matrix (Pirate always hostile; L/B mutually hostile;
  neutral to player until hit), hostility permanent, despawn on jump.
  Gate: matrix unit tests; Alpha never spawns anything across N seeds; spawn chance increases with alphabet; AI invariants
  (closes distance, holds band, converges on bearing); despawn on jump.
- **Stage 11** — Combat + T scan. Projectiles (3px circles, ship_velocity + 8·facing, world coords, lifetime),
  shield→armour damage order, destruction, player death → game over, NPC-vs-NPC combat with zero player reward, hit on L/B flips that
  faction permanently hostile, T scan with sticky display, re-scan nearest (no-op when already nearest), revert to "No target" on destruction,
  alignment coloured cyan/yellow/red, matching bar styling. Gate: velocity-composition math; damage order; destruction; hostility-on-hit;
  scan stickiness and reversion; projectiles can't hit their owner.
- **Stage 12** — Audio. Generated buffers via `array` + `Sound(buffer=...)` (no numpy), volumes from config; events: UI confirm beep
  (map + spaceport), fire (all ships, including offscreen), impact, destroyed, T klaxon only when the displayed ship is hostile,
  jump spin-up. Never crash if the mixer is unavailable.
  Gate: buffer generation tests; spy-based "event X plays sound Y" tests; game runs fully with audio disabled.
- **Stage 13** — End states, flow, and anti-softlock. Game over (armour ≤ 0; and the resolved credits condition),
  victory at win_credits, result screens with run stats, return-to-title / new game with complete state reset (only Alpha–Delta visible,
  fresh balance, empty hold), the stranded-fuel rule, optional pause-to-title.
  Gate: win/lose triggers fire exactly once; a second new game has no leaked state from the first (explicit test);
  no reachable state where the player can neither jump, land, nor lose.
- **Stage 14** — Integration, sweep, polish, docs. Headless scripted playthrough spanning every screen;
  performance sanity at 60 FPS; config sweep proving no hard-coding (jump cost, top speed, fare range, upgrade multiplier,
  spawn chance each change behaviour in a test); README accuracy pass (venv create/activate per OS, run command, full controls table);
  dead-code/TODO sweep. Gate: the scripted playthrough reaches the victory screen; every requirement maps to code + test.

