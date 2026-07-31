# SuperAsteroids — Implementation Plan

## Constraints

- **File structure:** Single `superasteroids.py`
- **Dependencies:** `pygame-ce` + Python standard library only
- **Framerate:** Locked at 60 FPS via `clock.tick(60)`
- **Cosmetic effects:** Deferred to Stage 10 (particles, starfield, thruster exhaust)
- **Stage discipline:** Every stage ends with a runnable, error-free program
- **Heavy use of well-named and well-documented constants:** all important parameters
  should ideally be adjustable in one location, without having to hunt through code
  to find and update all places the parameter in question is used.

---

## Stage 1: Window + State Machine (Text-Only Placeholders)

**Goal:** Runnable window with mode switching, no gameplay.

- `requirements.txt` with `pygame-ce`
- Main `superasteroids.py` entry point with `pygame.init()` / game loop / `clock.tick(60)`
- Window: 800×600 initial, min 640×480, no max, no forced aspect ratio
- `VIDEORESIZE` event handling; track current window dimensions
- `F11` fullscreen toggle: save/restore window position + size before/after toggle
- State machine with 4 modes: `TITLE`, `GAME`, `PAUSE`, `GAMEOVER`
- Text-only placeholder screens:
  - **Title:** "Title Screen" + "Press Enter / ESC"
  - **Game:** "Game Mode (Level 1)"
  - **Pause:** "PAUSED" + "ESC to resume, X to exit"
  - **Game Over:** "GAME OVER" + "R to restart, ESC to exit"
- Mode transitions:
  - `Enter` → Game (from Title)
  - `ESC` → Pause (from Game)
  - `ESC` → Resume (from Pause)
  - `X` → Title (from Pause)
  - `R` → Game (from Game Over)
  - `ESC` → Title (from Game Over)
  - `ESC` → exit code 0 (from Title)
- `--test` command line flag: if set show title screen for 100 ms, then exit code 0 (confirms the game starts)

---

## Stage 2: Ship Rendering + Physics

**Goal:** Player ship moves, rotates, wraps on screen.

- Ship class: elongated triangle (20 px wide, 30 px tall), white outline, light gray fill
- Rotation: left/right arrow at 5°/frame, stops immediately on release
- Thrust: up arrow, 0.3 px/frame² acceleration in facing direction, max speed 8 px/frame
- Friction: 0.98 multiplier per frame when up arrow is released
- Screen wrapping on all edges
- Ship centered at window center on level start / restart
- "Begin level N" centered text that fades out over ~2 seconds
- The player's ship is neither displayed nor controllable during "Begin level N" fadeout

---

## Stage 3: Asteroid Spawning + Movement

**Goal:** Asteroids appear, tumble, and wrap — no collision yet.

- Asteroid class: irregular polygon shape, white outline, random brown-ish or beige-ish fill
- Tumbling: rotation scales inversely with size (large = 1°/frame, small = 10°/frame)
  - "large" = 40 pixel radius, "small" = 15 pixel radius, this is the max size range for asteroids
  - interpolate a rotation speed between these two sizes using the numbers above
- Random initial direction, speed 1.5–2.5 px/frame
- Spawning: random positions, never within 200 px of ship; fallback to screen corners if necessary
- Level 1: 5 large asteroids (radius 40 px)
- Screen wrapping on all edges
- Respond to window resize events to ensure all asteroids screen wrap instantly if they are no longer visible after resize
- No asteroid-asteroid collision (they pass through each other)

---

## Stage 4: Asteroid Collision + Splitting + Level Progression

**Goal:** Ship death, asteroid splitting, level advancement.

- Ship-asteroid collision → immediate Game Over mode
- Asteroid hit logic:
  - Splits into 2–3 smaller asteroids (radius = parent / 1.5)
  - Split asteroids: speed × 1.2, random direction
  - Asteroids < 20 px radius are destroyed on hit (no further split)
- Implement asteroid "hit" count persisted as levels advance.
  - Only asteroid destruction events count as a "hit" (splits don't count)
  - Restarting the game resets the hit count to 0
- All asteroids destroyed → increment level, spawn new asteroids
  - Each level: +1–2 starting asteroids, +0.3 px/frame base speed
- Game Over screen: "GAME OVER" in red, smaller white text underneath reads "Press R to restart, ESC to exit"
- Restart resets to level 1
- ESC returns to title screen

---

## Stage 5: Cannon Weapon

**Goal:** Player can shoot and destroy asteroids.

- Cannon with 3 power levels
- **Level 1:** Single yellow projectile from ship tip, initial velocity = ship velocity + 6 px/frame forward, max 3 in flight, 1000 px travel distance, screen wrapping
- **Level 2:** 3 projectiles in 20° arc, orange, max 9 in flight
- **Level 3:** 4×4 px white projectiles, 8 px/frame speed, unlimited number in flight
- Space bar: one press = one shot (holding has no effect)
- Projectile-asteroid collision → asteroid split/destruction
- Projectile-ship collision → Game Over with "Friendly fire!" message
- Brief invulnerability after spawn to prevent instant self-hit:
  - For the first 10 frames after spawn, a projectile cannot impact the player's ship
  - Projectiles can, however, impact asteroids and powerup icons immediately after spawn

---

## Stage 6: Laser Weapon

**Goal:** Secondary weapon with charge mechanics.

- Laser beam: straight line from ship tip in facing direction
- **Level 1:** 1 px wide, 100 px long, light blue, charge 100, drain 3/frame, recharge 1/frame, min 20 charge to activate
- **Level 2:** 2 px wide, 125 px long, light blue, drain 2/frame, recharge 2/frame
- **Level 3:** 3 px wide, 150 px long, white, any hit = instant destroy (bypasses split)
- Beam follows ship movement/rotation while active
- Screen wrapping awareness:
  - this may involve rendering the laser beam in multiple disconnected segments if it crosses a screen edge
- First asteroid hit = one impact event, then beam deactivates (must re-press space)
- HUD: light blue charge bar on dark gray background

---

## Stage 7: Ramming Shield Weapon

**Goal:** Third weapon — defensive shield with bounce physics.

- Shield: red circle around ship, centered
- **Level 1:** 1 px border, radius 35 px, charge 100, drain 5/frame, recharge 1/frame, min 20 to activate, bounce velocity = radius / 5
- **Level 2:** 2 px border, bounce = radius / 8, drain 3/frame, recharge 3/frame
- **Level 3:** 3 px border, radius 40 px, bounce = radius / 10
- Asteroid-shield collision → asteroid impact event + ship bounce (replaces current velocity)
- Shield-powerup collision → powerup destroyed (must lower shield to collect)
- HUD: red charge bar on dark gray background

---

## Stage 8: Weapon Switching + Powerups

**Goal:** Powerup spawning, collection, and weapon management.

- Powerup icon: 20 px radius circle, labeled "C" (yellow fill), "L" (light blue fill), or "S" (red fill), white letter
- Spawns every 30 seconds of gameplay at random position (not on ship or asteroids)
- Icon is indestructible for the first 60 frames of its existence (can be collected by player's ship but is immune to all other collisions)
- Drifts at 2 px/frame in random direction
- Multiple powerups can appear onscreen at a time
- Asteroid collision with powerup → powerup destroyed, asteroid is split or destroyed
  following the usual asteroid hit rules. Update the asteroid "hit" count if the asteroid is destroyed.
- Ship collision with powerup:
  - Same weapon type → power level +1 (max 3)
  - Different weapon type → switch to that type, power resets to 1
- Weapon state persists across levels, resets on game restart (Cannon power 1)
- HUD updates: weapon name in appropriate color, power level in matching color
- Asteroid splits and destruction events have a small random chance of spawning a new powerup icon at the point of impact:
  - Chance starts at 8% at level 1 and decreases by 2% for every subsequent level, with a minimum chance of 1%
- Implement support for `--debug` command line argument:
  - if specified, hotkeys `l`, `c`, and `s` should spawn an immediate powerup icon of that type (laser, cannon, or shield)
  - if not specified, those keys do nothing.

---

## Stage 9: Enemy UFOs

Every 3 minutes of gameplay, spawn an enemy UFO:

- horizontal oval shape, 40 px wide, 15 px tall
- white outline, light red fill
- random starting location, not on top of player's ship
- random direction, 2px/s speed, straight line course
- changes direction by up to 30 degrees randomly left/right every 300 frames
- no collision detection with asteroids (passes through them)
- can "steal" powerups by destroying them on contact
- every 120 frames, fire a level 1 cannon projectile in the direction of player's ship
- UFO cannon projectiles have the same collision rules as player's, but half the travel distance (expire after 500 px)
- UFO projectile collides with player's ship: instant game over with "Hostile fire!" message
  - exception: UFO projectiles cannot penetrate the ramming shield
- Player weapon of any type collides with UFO: UFO is destroyed

---

## Stage 10: Full HUD

**Goal:** Complete in-game heads-up display.

- Rounded cyan border, dark gray fill, 4 px width, 60% opacity
- Upper-right corner placement
- Displays:
  - "Level: N" (white text)
  - "Hits: N" (white — destructions only, not splits)
  - "Weapon: [name]" (color-coded: Cannon = yellow, Laser = light blue, Shield = red)
  - "Power: N" (color-coded, matches weapon)
  - "Charge: [bar]" (when applicable — laser or shield)
- HUD only visible in Game Mode (hidden in Pause, Game Over, Title)

---

## Stage 11: Title Screen Polish + Cosmetic Effects (Final Stage)

**Goal:** All visual polish, animated title screen, thruster effects.

### Title Screen
- "SuperAsteroids" in large centered white text (upper half of screen)
- Subtle starfield background (random grayscale dots, varying brightness, "twinkle" effect)
- 4–7 asteroids tumbling gently with screen wrap
- "Press Enter to start" in smaller white text below title
- keyboard instructions in small light gray text centered in bottom third of screen:
  - "Left/Right: Rotate  |  Up: Thrust"
  - "Space: activate weapon"
  - "ESC: pause  |  F11: full screen"

### Thruster Exhaust
- Yellow circles (3–8 px radius) ejected from ship rear when thrusting
- Color fade: yellow → orange → red
- Alpha fade: opaque → transparent at 5%/frame
- Initial velocity: ships velocity plus 6–10 px/frame in the opposite of the ship's facing direction
  - apply slight randomness to this direction such that the particles emit within a 10 degree arc
- No collision effects (purely cosmetic)

### Particle Explosions
- **Split:** colorful (yellow, red, orange), count = radius × 3
- **Destruction:** monochromatic gray, count = radius × 3
- **UFO destruction:** 100 light red particles
- Particle velocity 5–15 px/frame, random direction
- Particle alpha decay 3–10%/frame, random per particle

### Subtle starfield background
- applies to all game modes
- random 100-200 single-pixel "stars" in random grayscale colors
- apply "twinkle" effect by slowly oscillating brightness:
  - stars are always grayscale, such that their red, green, and blue components are always equal to each other
  - each star starts with a random twinkle direction: increase brightness or decrease brightness
  - when max or min brightness is achieved, reverse the direction and continue
  - star brightness changes at 0.1% per frame
  - max brightness = pure white, min brightness = black
- starfield must respond to resize events! Making the window larger must fill the new area with random stars
- toggling fullscreen mode must also handle filling the new screen real estate with stars

---

## Stage 11: Sound effects

**Goal:** Full sound support (sound effects only, no game music)

- Load `sfx/*.wav` on startup and cache each sound effect in memory
- `sfx/README.md` contains a table indicating which effects map to which in-game events
- Add a `--quiet` command line option. If set, disable all sound.

---

## Per-Stage Verification

Each stage ends with:
- `python3 superasteroids.py --test` runs without errors and exits cleanly in 100 ms
- Report completion to user so that all mode transitions and new features can be tested manually

