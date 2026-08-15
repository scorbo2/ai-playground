# Objective

Produce a complete, runnable Python program using only `pygame-ce` and the Python standard library.
The game is a derivative of the classic "Asteroids" arcade game, but with many improvements and
enhancements described in this document. The frame rate will be locked at 60 FPS via `clock.tick(60)`.

## Window and setup

The game starts in a resizable 800x600 window. The `F11` key should act as a full-screen mode toggle.
Entering full-screen mode should use the current display's native resolution to show the game on the
entire display. Hitting `F11` again should return to a window with the same position and dimensions
that were in effect before full-screen mode was activated.

## Game modes

The game has the following modes:

- Title Screen Mode. Player can press `Enter` to start Game Mode or press `ESC` to exit.
- Game Mode. Player can play the game and advance through progressively difficult levels. Player can 
  press `ESC` to pause the game. Losing the game moves to Game Over mode.
- Pause Mode. Can only be entered from Game Mode. The game in progress is frozen in place until the player
  deactivates pause mode. Player can press `ESC` to return to Game Mode, or press `x` to abandon the 
  game and exit to Title Screen Mode.
- Game Over Mode. The player has lost the game. Player can press `r` to restart Game Mode from
  the beginning, or press `ESC` to return to Title Screen Mode.
- Test Mode. Activate via the `--test` command-line argument. For testing purposes only.

### Title Screen Mode

The name of the game ("SuperAsteroids", one word) should be displayed in very large red lettering,
centered in the upper half of the screen. The background should display a subtle starfield. 
A random number of asteroids (3-6) should be animated gently tumbling with screen wrap. 
The title screen asteroids are cosmetic - they do not collide or split, and they are removed when
starting a new game. They have the same movement and screen wrapping behavior as Game Mode asteroids.

Smaller text in white lettering should appear at the center of the screen, describing the
controls used in Game Mode:

```
Left/Right: rotate  |  Up: thrust  |  Space: weapon
F11: full screen  |  F2: sound on/off
ESC: exit
```

Then, lower down: "Press Enter to start".

Pressing `Enter` begins Game Mode at level 1. Pressing `ESC` exits the game with exit code 0 (normal termination).

### Game Mode

Game mode can be accessed from the Title screen by pressing `Enter`, or from Game Over mode by pressing `r`. 
Game mode begins on level 1. 

At the start of each level, the text "BEGIN LEVEL N" should appear in the center of the screen (where N is
the current 1-based level number). Hold for 90 frames, then fade out over 30 frames.
The player's ship then appears in the center of the screen, and the game begins.

On each level advancement, all explosion particles, powerup icons, thruster exhaust circles, projectiles, 
and enemy UFOs are removed from play. The player's craft is returned to the center of the screen facing up,
with velocity reset to 0. If the laser or shield were active at the end of the previous level, they are
deactivated. Their charge is restored to 100%.

#### Ship physics and controls

The player's ship is represented as an elongated triangle, 20 pixels wide and 30 pixels tall. The ship has
a white outline and a light gray fill. The ship initially points upwards and has a starting velocity of 0.

Holding the left or right arrow keys rotates the ship continuously at 5 degrees per frame. 
Releasing the left or right arrow key stops rotation immediately.

Holding the up arrow key applies acceleration of 0.3 pixels per frame squared in the ship's facing direction.
The ship has a maximum speed of 8 pixels per frame. When the up arrow key is released, apply linear friction
of 0.98 per frame to slow the ship gradually back to 0. If calculated speed drops below 0.05px/frame,
set speed to 0.

Screen wrapping is applied at all screen edges.

Pressing or holding the space bar activates the ship's current weapon. See the "Weapons" section for details.

#### Asteroids

Level 1 begins with 5 large asteroids (radius 40 pixels) in random starting positions (but away from the 
player's ship - fall back to any screen corner if no open starting location can be found. Never start an asteroid
within 200 pixels of the player's ship). Asteroids have an initial randomly-chosen direction, and an initial
randomly-chosen speed from 1.5 to 2.5 pixels/frame.

Asteroids should have an irregular shape. They should NOT be simple circles. Asteroids should "tumble"
(slowly rotate) as they move. Rotation rate should scale inversely with asteroid size. Large asteroids
(40px radius or higher) rotate slowly, at 1 degree per frame. Small asteroids (20px radius or smaller)
rotate more rapidly, at 10 degrees per frame. Interpolate between those two rotations speeds based on the
radius of the asteroid. Rotation direction (clockwise or counter-clockwise) is randomly selected per asteroid.

There is NO collision detection between asteroids - they simply pass through each other.

Screen wrapping is applied at all screen edges.

Asteroids should have a white outline, and each should have a randomly-chosen fill color in the brown or beige range.

When an asteroid is hit by any player weapon, it splits into 2-3 (randomly selected) smaller asteroids.
The radius of the smaller asteroids is the parent's radius / 1.5. Their speed is the parent asteroid's speed multiplied by 1.2,
and their direction is completely random. If an asteroid with a radius smaller than 20 pixels is impacted, 
it is destroyed - do not split further. Child asteroids do not need to inherit their parent's rotation
direction or color - these can be chosen randomly per child by the same rules as for parent asteroids.

Asteroid splits are accompanied by a colorful particle explosion. The particle color is randomly selected
for each particle from bright yellow, red, and orange. 

Asteroid destruction events are accompanied by a monochromatic particle explosion (plain gray particles).
The brightness of each particle is randomly selected from mid-gray (128) to white (255). 

Explosion particles should spread out from the point where the collision occurred, and fade by gradually adjusting
their alpha values until they are invisible. Particle velocity is random between 5 and 15 pixels per frame, 
direction is random, and alpha adjustment should be random between 3% and 10% per frame. Particle count is
the asteroid's radius * 3. For example, if a 40 pixel "large" asteroid is hit, it should spawn 40 * 3 = 120 
particles.

When all asteroids are destroyed, increment the current level by 1 and begin that new level. On each
new level, the starting asteroid count increases by 1 or 2 (chosen randomly per level advancement), 
and their starting speed increases by 0.3 pixels/frame. So, if level 1 selects a random initial speed in
the 1.5 to 2.5 pixels/frame range, then level 2 would select a random initial speed in the 1.8 to 2.8 pixels/frame
range, and so on, increasing by 0.3 pixels/frame per level, with no cap.

The same asteroid split and destruction rules apply on all levels.
There is no "last level" - Game Mode continues until the player exits Game Mode or is defeated.

If the player's ship collides with an asteroid of any radius, or with any weapon (even the player's own weapons, 
which can happen due to screen wrapping), switch immediately to Game Over mode. The only exception is if the
shield is raised at the time of impact.

Suggested asteroid "irregular shape" generation:

- choose vertex_count = random.randint(8, 14)
- for each vertex:
  - `angle = 2*pi * i / vertex_count`
  - `radius_factor = random.uniform(0.75, 1.25)`
  - `vertex_radius = asteroid_radius * radius_factor`
  - `x = cos(angle) * vertex_radius`
  - `y = sin(angle) * vertex_radius`
- draw polygon with white outline and random brown/beige fill
- rotate the whole asteroid over time

### Pause Mode

During game mode, the player can hit the `ESC` key at any time to temporarily suspend Game Mode and enter
Pause Mode. Hide all asteroids, particles, projectiles, crafts, and the HUD. All timers are suspended.
Display "PAUSE" in large white letters in the center of the screen. Underneath that, on separate
lines, display the smaller text "Press ESC to resume" and "Press X to exit".

Pressing `ESC` in Pause Mode resumes Game Mode.

Pressing `x` in Pause Mode abandons the current game and returns to Title Screen Mode.

### Game Over Mode

All animation stops (except starfield background animation, which never stops). 
Display the text "GAME OVER" in red in the center of the screen. Directly beneath that text,
display "Press R to restart" and "Press ESC to exit" on separate lines in smaller white text.
If a special additional message is provided (example: "FRIENDLY FIRE!" or "HOSTILE FIRE!"), 
display the additional message between "GAME OVER" and "Press ESC to exit". 
The additional message should be in green text.

Pressing `r` returns to level 1 and begins a new game. The player craft returns to its default starting state,
losing any weapons upgrades that the player had collected.

Pressing `ESC` in Game Over mode returns to Title Screen Mode.

### Test Mode

This mode can only be accessed by passing the `--test` argument on the command line. Start Title Screen Mode
and then exit the application with exit code 0 (normal termination) after 250ms. This mode simply confirms that
the game starts up correctly.

## Heads-up display (HUD)

During Game Mode, a HUD is displayed in the upper-right corner of the display. The HUD border and contents 
should be displayed with 60% opacity so that it does not completely obscure the player's view of the game area.
The HUD has a rounded cyan border with width 4 pixels. The HUD displays the following data:

- Current 1-based level number (label "Level:"). Font color: white.
- The player's current scoring information is displayed next (see "Scoring the game").
- Current weapon (label "Weapon:"). Display "Cannon", "Laser", or "Shield". Font color depends on weapon: Cannon is displayed
  in yellow, Laser is displayed in light blue, and Shield is displayed in red.
- Current 1-based weapon power level (label "Power:"). Font color: matches weapon label color.
- Weapon reload indicator (if applicable... see Weapons section). Label ("Charge:") in white text.
- Sound status (label "Sound:"). "On" or "Off" depending on current sound state. White text.
- Game time (label "Game time:"). Elapsed game time in minutes:seconds. This reflects active game time,
  not elapsed wall-clock time. Time spent in Pause Mode and time spent between levels does not count towards this.
  Green text.

The HUD is ONLY displayed in Game Mode. In Pause Mode, Game Over Mode, and Title Screen Mode, the HUD is hidden.

HUD characteristics:

- size: 250px wide, 300px tall
- position: upper right, 10px margin from screen edge
- corner radius: 12
- border color: cyan
- border width: 4
- alpha (border and contents): 153 (approximately 60%)
- font size: scale to fit. Suggestion: 18pt
- line spacing: 18px

### Scoring the game

The game should keep track of the following stats and display them in the HUD. Stats carry over from
level to level. All stats reset to 0 at the start of level 1.

- "Shots fired": the total cumulative count of successful weapon activations of any type.
- Count of asteroids destroyed (label "Hits:"). This does NOT include asteroid splits, only asteroid destruction 
  events. Only asteroids destroyed by player weapons count towards this stat. Font color: white.
- "Hit rate": this is count of asteroid destruction events / count of successful weapon activations * 100.
  Note that asteroid splits do NOT count towards the hit rate. Only asteroids destroyed by player
  weapons count towards this stat. Round to one decimal place. If the player has not yet fired any
  weapon or caused any asteroid destructions yet, display "0.0%". Font color: white.
- "Nickname": the player's "nickname" is derived from their hit rate. Use the following guide:
  - 0%: "New recruit" (this is the default starting nickname when beginning level 1)
  - between 0% and 10%: choose randomly from "Blind woodsman", "One-eyed Pete", "Unlucky Larry",
    "No-hit wonder", or "Terrible Tom"
  - between 10% and 50%: choose randomly from "Amateur", "Wannabe", "Poser", "Good Enough Gary".
  - between 50% and 80%: choose randomly from "Great!", "Sharpshooter", "Combat pilot", "Veteran"
  - between 80% and 100%: choose randomly from "Ace!", "Combat master", "Top gun", "Hunter"
  - Font color: white.
  - The nickname is randomly chosen only once when moving between percentage categories.
    For example, if the hit rate is 100% and "Ace!" is selected, that nickname remains displayed 
    until the hit rate drops below 80%.

## Weapons

Pressing and/or holding the space bar activates the player's current weapon. The player can only
have one weapon at a time.

The following weapons are available in the game:
- Cannon (default weapon)
- Laser beam
- Ramming shield

Each weapon has three levels of power, which affects its abilities.
Level 1 always begins with the Cannon on power level 1.
Advancing to subsequent levels carries over the current weapon and power level.

### Powerups

Every 30 seconds of gameplay, a circular "powerup" icon of radius 20 pixels will appear randomly on the screen. The 
icon should not spawn directly on the player's ship or directly in contact with any asteroid, unless the icon was spawned
from an asteroid split or destruction event. The icon is indestructible for the first 90 frames of its existence 
to avoid accidental instant collision with nearby asteroids or projectiles. 

The icon's color and label are randomly selected from the following list:

- White letter "C" on a yellow circle: this represents a Cannon powerup.
- White letter "L" on a light blue circle: this represents a Laser powerup.
- White letter "S" on a red circle: this represents a Shield powerup.

The icon drifts at a speed of 2 pixels per frame in a randomly chosen direction. 
If the icon impacts an asteroid of any size outside of its grace period, the powerup icon is destroyed and removed from play.
The asteroid that impacted it will be split or destroyed according to the usual asteroid impact rules. This does not
update the player's score. If the icon impacts an enemy UFO, the icon is removed from play, even if this occurs
during the grace period. The enemy UFO is unaffected by this collision.

If the player's ship impacts the icon (even during the icon's grace period), the icon is removed from the screen,
and the player's current weapon is adjusted according to the following rules:

- if the icon was the same type as the player's current weapon, the player's weapon power increases by 1, to a
  maximum of 3.
- if the icon was of a different type than the player's current weapon, the player's current weapon type switches
  to the icon's type, and the player's weapon power level resets to 1.

Current weapon and power level are maintained when advancing levels. 
When restarting a game at level 1, the player is always reset to the Cannon at power level 1.

Additionally, asteroids have a small random chance of spawning a new random powerup icon on every asteroid split
or asteroid destruction event. The chance of this decreases as the level advances:

- level 1: 8% chance
- level 2: 6% chance
- level 3: 4% chance
- level 4: 2% chance
- level 5 and up: 1% chance

Remember that powerup icons are indestructible for the first 90 frames of their existence. During this
"grace period" time, they do NOT cause impact events with asteroids or weapons. They CAN be collected
by the player's craft or collide with enemy UFOs during the grace period.

The 30 second spawn timer does NOT reset between levels. For example: if level 1 ends with 5 seconds remaining
until the next powerup icon spawn, then a powerup icon should spawn 5 seconds after starting level 2. The timer
always resets at the beginning of level 1.

There is no upper limit for powerup icons in play at a time.

### Cannon

Level 1: a single projectile fires from the tip of the ship. Its initial velocity is the ship's current velocity
plus 6 pixels/frame in the ship's facing direction. Cannon projectiles travel 1000 pixels from the spawn point,
respecting screen wrap on all screen edges (this 1000px is cumulative travel distance, not including screen wrap events).
If the projectile travels 1000 pixels without impacting anything, the projectile simply disappears and is removed from play. 
If a projectile impacts an asteroid, the projectile is removed from play, and an asteroid impact event is triggered.
If a projectile impacts a powerup icon outside of the icon's grace period, the projectile is removed from play,
and the icon is destroyed. If a projectile impacts an enemy UFO, the enemy UFO is destroyed. At this power level,
only three projectiles can be in flight at a time. Pressing space when three projectiles are already in place 
does NOT spawn a new projectile - the cap has been reached, so the player must wait until at least one projectile 
has been removed from play. Holding space has no effect - only one projectile is spawned for each press of the space bar. 
Cannon projectiles at this power level are yellow, represented as small 2x2 pixel blocks.

Level 2: three projectiles fire from the tip of the ship in a 20 degree arc. The same direction, velocity, distance,
and impact rules apply to these projectiles. The player can now have 9 projectiles in flight at a time. Pressing
the space bar when more than 6 projectiles are in flight does nothing. Each press of the space bar spawns three 
projectiles. Cannon projectiles at this power level are orange with the same size as level 1 projectiles.

Level 3: Increase projectile size to 4x4 pixels. Projectile color is now white. Increase projectile initial speed 
to 8 pixels per frame. The player is allowed an unlimited number of projectiles in flight at this power level.
Holding space does nothing - every press of the space bar spawns three projectiles.

No reload indicator is displayed in the HUD for this weapon.

Note: due to screen wrapping, it is possible for a player's Cannon projectile to impact the player's own ship.
This instantly transitions to Game Over Mode with the special additional message "FRIENDLY FIRE!". 
Cannon projectiles cannot cause an impact with the player's ship immediately after spawning -
they have a 30 frame grace period to prevent immediate self-kills. They CAN cause asteroid and other impact events
during this grace period. The projectile grace period only applies to collision detection with the player's
own craft.

### Laser

Level 1: A light blue beam is rendered in a straight line of width 1 pixel from the tip of the player's ship, 
extending 100 pixels in the ship's facing direction. The beam moves with the ship, such that it is always 
projecting from the tip of the ship in the ship's facing direction, even as the ship moves or rotates. 
The laser beam is subject to screen wrap. The beam is rendered for as long as the user holds the space bar,
or until its charge is depleted. The laser has a charge of 100 units, which depletes at a rate of 3 units 
per frame for as long as the space bar is held. When the weapon's charge reaches 0, the beam is discontinued. 
While the space bar is not held, the weapon's charge recovers at a rate of 1 unit per frame. 
The weapon cannot be activated if the current charge is below 20. If the beam impacts any asteroid, this 
triggers an asteroid impact event and immediately deactivates the laser. The player must release the space 
bar and press it again to reactivate the laser. The laser does not pass through asteroids! The first asteroid
it impacts triggers ONE impact event. If the beam impacts a powerup icon outside of the icon's grace period, 
the powerup icon is destroyed. The laser beam respects screen wrap on all screen edges.

Level 2: Increase beam width to 2 pixels, and beam length to 125 pixels. Weapon charge now depletes at a rate
of 2 units per frame and recharge rate increases to 2 units per frame. Otherwise, the same rules apply here
as in level 1.

Level 3: Increase beam width to 3 pixels and beam length to 150 pixels, and change beam color to white.
Weapon discharge and recharge rates remain the same as level 2. Any asteroid impacted by this beam is
immediately destroyed. This bypasses the usual asteroid split rules.

A recharge indicator should be displayed in the HUD showing the laser's current charge as a light blue bar
on a dark gray background, similar to a progress bar. 

The laser beam at any power level instantly destroys an enemy UFO upon impact.

Each laser activation counts as one "shot fired", regardless of how long the space bar is held.

If the laser successfully impacts any game object, the laser beam is deactivated, even if the user continues
to hold the space bar. The laser does not recharge until the user releases the space bar. The current drain
rate continues to apply for as long as the user holds the space bar, even after the beam deactivates.

### Ramming Shield

Level 1: Holding the space bar activates a circular shield around the player's ship, which should be represented
as a red circle with border width 1 pixel and radius of 35 pixels. The player's ship is centered within this circle.
Any asteroid that impacts the shield causes an asteroid impact event. This impact should cause the player's ship
to "bounce" away from the point of impact. This imparts velocity to the player's ship directly proportional to the
radius of the asteroid, using the formula velocity = radius/5. Impacting an asteroid of radius 40 therefore 
immediately accelerates the player's ship to 8 pixels/frame in a direction directly away from the point of impact. 
This discards and replaces any current direction/velocity the player's ship had before impact. If the shield 
impacts a powerup icon outside of the powerup's grace period, the icon is destroyed - the player must lower the shield to 
pick up a powerup icon. The exception is during the powerup icon's grace period - the player can collect a powerup
icon during the grace period, even if the shield is raised.

The shield has a charge of 100 units, which discharges at a rate of 5 units per frame. 
If the charge reaches 0, the shield is deactivated even if the player continues holding the space bar. The shield 
recharges at a rate of 1 unit per frame. The shield cannot be activated if the charge is below 20 units.

Level 2: Increase shield border width to 2 pixels. The "bounce" formula changes to velocity = radius/8, so that
the bounce is less violent. Discharge rate changes to 3 units per frame, and recharge rate increases to 3 units
per frame.

Level 3: Increase shield border width to 4 pixels and increase shield radius to 40 pixels. The "bounce" formula
changes to velocity = radius/10. Discharge rate and recharge rate remains the same as level 2. Any asteroid
impacted by the shield at level 3 is immediately destroyed. This bypasses the usual asteroid split rules.

A recharge indicator should be displayed in the HUD showing the shield's current charge as a red bar on a dark
gray background, similar to a progress bar.

The shield at any power level instantly destroys an enemy UFO upon impact. The same "bounce" rules apply as
for an asteroid collision.

Each shield activation counts as one "shot fired", regardless of how long the space bar is held.

After shield bounce, always clamp player craft's speed to max speed of 8 pixels/frame.

### Weapon activation

"Weapon activation" refers only to successful activations:

- Cannon: spawns at least one new projectile.
- Laser: beam activates because charge is at least 20.
- Shield: shield activates because charge is at least 20.

Unsuccessful attempts do not count as activations:

- Cannon: blocked by projectile cap
- Laser: attempted activation blocked by insufficient charge
- Shield: attempted activation blocked by insufficient charge

## Enemy UFOs

Every 3 minutes of gameplay, spawn an enemy UFO:

- horizontal oval shape, 40 px wide, 15 px tall
- white outline, light red fill
- random starting location, never within 200px of player's craft
- random direction, 2px/frame speed, straight line course
- changes direction by up to 30 degrees randomly left/right every 300 frames
- UFOs respect screen wrapping on all screen edges.
- no collision detection with asteroids (passes through them)
- can "steal" powerups by destroying them on contact, even within their grace period
- every 120 frames, fire a level 1 cannon projectile in the direction of player's ship.
- UFO cannon projectiles have the same visual characteristic's as player's level 1 cannon projectiles, but half
  the travel distance (expire after 500px cumulative travel distance).
- UFO cannon projectiles are subject to screen wrapping.
- Enemy UFOs cannot friendly-fire. Their projectiles pass through enemy UFOs.
- UFO cannon projectiles CAN cause asteroid split and destruction events. This does NOT update
  the player's score.
- UFO cannon projectiles CAN destroy powerup icons, outside of the icon's grace period.
- UFO projectile collides with player's ship: instant game over with "HOSTILE FIRE!" special message.
  - exception: UFO projectiles cannot penetrate the ramming shield
- Player weapon of any type collides with UFO: UFO is destroyed
- Player craft collides with enemy UFO: instant game over.
  - exception: if the shield is active, the enemy UFO is destroyed.

**UFO destruction:** 100 light red particles

- Particle velocity 5–15 px/frame, random direction
- Particle alpha decay 3–10%/frame, random per particle

The three minute UFO timer does NOT reset between levels. For example: if level 1 ends with 10 seconds
remaining until next UFO spawn, then a UFO should spawn 10s after the start of level 2. The timer always
resets when beginning level 1.

Up to 3 enemy UFOs can be active at any one time. If the timer expires while three UFOs are already in play,
do not spawn another. Just reset the timer.

If all asteroids are cleared, the level ends, even if one or more enemy UFOs are still in play. Those UFOs
are simply removed from play at the end of the level.

## Collision detection

All game objects have simple bounding circles whose size is derived from the game object in question:

- Asteroids: use a bounding circle with radius equal to the asteroid's radius (even though the asteroid is 
  depicted with an irregular shape - the irregular shape is ignored for collision detection purposes).
- Player craft: a simple 20x radius circle extending from the center of the craft.
- Cannon projectiles: use the exact shape and size of the projectile for collision detection.
- Enemy UFOs: a simple 30px radius circle extending from the center of the UFO (ignoring the oval shape).
- Powerup icons: a simple bounding circle whose radius matches the icon's radius.

Example: the center of the player's craft comes within 60px of the center of a 40px radius asteroid. This
counts as a collision, because the craft's 20px bounding circle now intersects the asteroids 40px bounding circle.
Game over.

Collision detection must respect screen wrapping! For example: if the center of the player's craft is 5 pixels from the left
edge of the screen, and a 40px radius asteroid has its center 5 pixels away from the right edge of the screen at
the same Y value, this should count as a collision.

### Special cases for collision detection

The laser beam samples along the beam's length looking for the first impacted game object. The laser beam respects
screen wrap on all edges. Suggestion for implementation: sample the beam in small steps, perhaps at 2px increments,
starting from the tip of the player's craft and moving along the facing direction. Wrap the sample point to screen
bounds, check for collisions, and stop at the first hit.

The ramming shield has a simple circular bounding circle with a radius equal to the shield's own radius.

## Thrusters

When the player is thrusting, small solid-fill circles should be ejected from the rear of the ship at a rate of 2-3
per frame (count chosen randomly per frame). These circles should have a random radius between 3 and 8 pixels. 
Their starting velocity is the ship's velocity plus backwards random speed of 6-10 pixels/frame. Their color 
is randomly selected from yellow, orange, and red. Their alpha value starts at fully opaque and is adjusted by 
3-6% per frame (randomly chosen per circle) until they are completely invisible, at which point they are 
removed from play. This simulates thruster exhaust. 

Thruster exhaust circles do not have collision detection with any other game object. The thruster effect is a
purely cosmetic visual effect.

## Starfield background

In all modes, a subtle starfield is displayed in the background. This consists of a random number between 150 and 300 of
single pixel "stars" in grayscale colors. These stars do not move, but they do slowly shift color
by increasing their RGB values at a rate of 0.1% per frame until they reach max brightness of 192, then by decreasing their
brightness by the same rate until they reach minimum brightness of 0, and then repeating the cycle. The red, green, and blue components
of each star must always be adjusted together, such that the stars are only ever rendered in grayscale.

## Window resize handling

Resizing the window during Game Mode may cause the positions of game objects to be fully off-screen, if the window size
is reduced. This should trigger an immediate forced screen wrap so that the object reappears as soon as the resize completes.

Expanding the window (either by manual resize, or by toggling into full-screen mode) may require changes to the
starfield background to fill in the newly-expanded areas of the window. It is acceptable to completely regenerate
the starfield on each resize event, rather than trying to dynamically "fill in" the newly expanded areas.

There is no scaling required! All game objects remain at their current size when expanding or shrinking the window.

Resizing the window below 400px width OR below 300px height should be rejected - enforce minimum window size of 400x300.

The HUD is always in the upper right of the screen. Adjust its position as needed on resize events. Its size does not change.
If the new window size is too small to render the HUD, the HUD should be hidden.

## Timers

The spawning timers (powerup icons, enemy UFOs) should be based on frames, not wall-clock time. That is, during
Pause Mode, and during the "BEGIN LEVEL N" text fade-out, the timers are NOT running.

Suggested constants:

```
FPS = 60
POWERUP_INTERVAL = 30 * 60      # 1800 frames
UFO_INTERVAL = 3 * 60 * 60      # 10800 frames
POWERUP_GRACE = 90
CANNON_SELF_GRACE = 30
UFO_DIRECTION_CHANGE_INTERVAL = 300
UFO_FIRE_INTERVAL = 120
```

## Sound

The game has no background music, but it does have sound effects. There are several wav audio files in the `sfx` subdirectory.
These will be packaged with the game. Load them into memory on startup.
There is a README.md in the sfx subdirectory that contains instructions as to which sound
effects are associated with which game events.

Audio load errors or I/O errors are not fatal. Log a warning for each audio file that fails to load, and proceed
without that sound.

Pressing `F2` at any time toggles sound on/off. This setting is global and is unaffected by the current mode.
For example: toggling sound off in Game Mode will keep it off even when returning to the title screen and starting
a new game. Sound must manually be toggled back on via `F2`.

Sound defaults to on.

## "Debug" option (for cheating)

If the `--debug` argument is specified on the command line, then additional hotkeys are available to
spawn an immediate powerup at a random screen location (never within 200px of the player craft):

- press 'C' to spawn a Cannon powerup
- press 'L' to spawn a Laser powerup
- press 'S' to spawn a shield powerup

There are no limits to the number of powerup icons you can spawn at any time. 

If `--debug` is not specified, these keys do nothing.

## Development stages:

- Stage 1: Initial window creation. Implement window resize and the `F11` full screen toggle. Implement
  the `--test` mode. Game Mode is a simple placeholder screen for now (display "GAME MODE" in large
  white lettering in the center of the screen). User can pause and unpause, or exit the current game via
  the `x` key in Pause Mode. There is no way to reach Game Over mode yet. There is no audio yet.
  There are no asteroids or other game objects yet (even on the title screen). Just placeholder text.
  Implement the state machine for the different game modes. Implement the 60fps clock tick.
  Defer cosmetic effects (starfield background, thruster effects, particle explosions) to later stages.
- Stage 2: implement asteroids. The title screen should now show asteroids gently tumbling.
  Entering Game Mode no longer displays the placeholder text. Instead, spawn asteroids as described
  in the Asteroids section. Implement asteroid rotation, movement, and screen wrapping.
  There is no player craft yet. Asteroid impacts are not possible yet.
  There are no powerup icons or enemy UFOs yet. There is still no way to reach Game Over mode yet.
- Stage 3: implement the player craft and movement controls. There are no weapons yet.
  Implement acceleration, max speed, and friction effects. Handle screen wrapping for the craft.
  It is not yet possible to cause an asteroid split or destruction event, but it is now possible to
  reach Game Over mode by flying into an asteroid - this will verify that collision detection works.
- Stage 4: implement the Cannon (level 1 only at this stage). There are no powerup icons yet.
  There are no enemy UFOs yet. The player can shoot projectiles and cause asteroid split and
  destruction events. This allows the player to test level advancement, by clearing all asteroids.
  Game scoring and the HUD should be implemented at this stage.
  Implement the "BEGIN LEVEL N" fade-out text at the start of each level.
  Implement level advancement (adjusting asteroid specs per level advancement rules).
- Stage 5: implement remaining weapon types and powerup icon spawning. The player should be able
  to switch and upgrade weapons by collecting powerup icons. Implement `--debug` mode now to
  make testing easier. Implement weapon collision detection for the laser and the shield.
- Stage 6: implement enemy UFOs and UFO projectiles. Update collision detection code accordingly.
- Stage 7: implement audio using the contents of the `sfx` subdirectory. Implement the `F2` toggle.
  Add a `--nosound` command line option that overrides the default audio state on startup.
- Stage 8: cosmetic effects, such as the starfield background, thruster flame effect, and
  particle explosions can be implemented now.

### Per-stage verification

A stage is not complete until the game can be run with the `--test` parameter with a successful
exit code 0, indicating normal termination. Errors must be addressed before advancing to the
next stage! Once `--test` passes, report successful stage completion to the user so that
manual testing can be performed.

### Code structure

Split classes into separate modules where needed, to keep the code structure clean and readable.

Try to re-use code where possible. Example: generic handling for explosion particles, which are
needed for asteroid splits, asteroid destruction events, and enemy UFO destruction events.

Prefer good code structure over clever hacks. The code should be readable and maintainable.

All important game parameters should be represented as constants near the top of the module
that defines them. This makes it easier to adjust game mechanics without searching through
thousands of lines of code. Consider having a "game_constants" module for this purpose,
to keep them all in one location.

Fonts are expensive to create! Suggestion: create them once and re-use them.

Color values such as "cyan", "red", "orange", and so on should be represented as constants
rather than hard-coded. Suggested constants:

```
WHITE = (255, 255, 255)
RED = (255, 0, 0)
YELLOW = (255, 255, 0)
ORANGE = (255, 165, 0)
LIGHT_BLUE = (173, 216, 230)
CYAN = (0, 255, 255)
LIGHT_RED = (255, 127, 127)
LIGHT_GRAY = (200, 200, 200)
DARK_GRAY = (64, 64, 64)
GRAY = (128, 128, 128)
# And so on...
```

Brown and beige asteroid colors can be random ranges:

```
brown = (
    random.randint(130, 180),
    random.randint(70, 120),
    random.randint(30, 80)
)

beige = (
    random.randint(220, 250),
    random.randint(200, 240),
    random.randint(150, 200)
)
```

But these should be calculated per-asteroid, not stored in constants.

