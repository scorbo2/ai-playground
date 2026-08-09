# Solar Fortress

Objective: a playable arcade-style game with simple vector graphics, built in Python with `pygame-ce` as the only dependency. The frame rate is fixed at 60fps via `clock.tick(60)`.

Implementation is broken into stages, where each stage produces a runnable, testable increment. At the end of the final stage, the complete game is ready.

## Game overview

At the start of each level, an unmoving enemy "fortress" is placed at the center of the screen. The player controls a small spaceship, represented as a simple elongated triangle. The player can rotate left or right, thrust forward, and shoot small projectiles in the craft's facing direction. The object of the game is to destroy the fortress by hitting it with a projectile. The fortress is protected by three concentric roughly circular rotating force fields, each divided into multiple line segments. The player can destroy these force fields one segment at a time by shooting them with projectiles. The enemy fortress can launch small homing devices which seek to collide with the player's craft, resulting in in defeat for the player. Additionally, the fortress can occasionally fire a large fast-moving projectile of its own in the player's direction. The player must evade or destroy the homing devices, and must evade the enemy projectiles in order to survive. If the player penetrates the shield rings and destroys the fortress, a new level begins with a higher difficulty level (more homing devices, more frequent enemy projectiles). There is no final level - game play continues until the player exits or is defeated.

## Game elements

### The enemy fortress

The enemy fortress is drawn at the center of the screen using the `enemy_neutral.png` sprite at its native size (do not rescale or stretch the sprite). When the enemy fortress is preparing to fire a projectile, its appearance changes by instead rendering the `enemy_charging.png` sprite for 60 frames (1 second). Then, the fortress is drawn using the `enemy_firing.png` sprite for 30 frames, as the enemy projectile is released. After the enemy has completed firing its projectile, it is once again rendered using `enemy_neutral.png`.

The enemy fortress cannot move. It remains at the center of the display, even as the display is resized. It must therefore respond both to video resize events and also to the full screen mode toggle (F11).

If the enemy fortress is hit by any of the player's projectiles, it is destroyed, resulting in an explosion of 120 particles with colors chosen randomly from bright yellow, red, or orange. These particles are represented as solid-color circles with random diameters from 6 to 12 pixels. They radiate outwards from the fortress in random directions, at speeds randomly chosen between 5 and 15 pixels per frame. Their alpha values are adjusted by between 2% and 6% per frame, starting fully opaque, and becoming fully invisible. All other animation stops while the enemy fortress is exploding. The fortress sprite's alpha is also reduced by 1% per frame during this explosion, until it is invisible. When the fortress is completely invisible, the text "LEVEL CLEARED" should appear in large white text in the center of the screen for 120 frames, before advancing to the next level.

Collision detection for the enemy fortress is a simple bounding circle with a diameter equal to the width of the fortress sprite.

### The shield rings

The enemy fortress is protected by three concentric "force fields", represented as 16-sided roughly circular polygons. The inner shield has a diameter of 150 pixels. The second shield has a diameter of 200 pixels. The outer shield has a diameter of 250 pixels. All three shield rings are centered around the enemy fortress. They stay centered around the fortress even as the display is resized or full-screen mode is toggled.

The inner shield rotates clockwise at 1 degree per frame. The second shield rotates counter-clockwise at 0.6 degrees per frame. The outer shield rotates clockwise at 0.3 degrees per frame. If a player-fired projectile impacts a shield segment, that segment is disabled for 300 frames. During the time that a segment is disabled, it is not rendered, and player projectiles can pass through it. The disabled shield segment still rotates with the rest of the shield ring. It is therefore possible to shoot moving "holes" in the enemy force fields, and shoot through them. After 300 frames, a disabled shield segment is reactivated. Enemy projectiles do not have collision detection with the enemy force field - they pass through. Enemy homing missiles also have no collision detection with the enemy force field. If a player projectile impacts an active shield segment, that projectile is removed from play. A single player projectile cannot disable more than 1 shield segment.

The inner shield's line segments are 3px wide and are bright red. The second shield's line segments are 2px wide and are bright yellow. The outer shield's line segments are 1px wide and are bright green.

### Enemy homing missiles

Enemy homing missiles are spawned from the center of the fortress. This spawning does not trigger the enemy "firing" animation sequence. Homing missiles are small circles, 16px wide. They have a white 1px border and a light gray fill. They move at a constant rate of 2px/frame in the direction of the player's craft, and they adjust their direction as the player moves so that they are always approaching the player's craft (recompute heading toward player every frame, no turn-rate limit). If a homing missile makes contact with the player's craft, the craft is destroyed. If a player projectile impacts a homing missile, the homing missile is destroyed. This triggers a small explosion of 100 white particles that radiate outward from the homing missile's last location. These particles are represented as solid-color circles with random diameters from 4 to 8 pixels. They radiate outwards in random directions, at speeds randomly chosen between 5 and 15 pixels per frame. Their alpha values are adjusted by between 4% and 8% per frame, starting fully opaque, and becoming fully invisible. These particles have no collision detection with any other game object - it is a purely cosmetic visual effect.

A new homing missile spawns from the center of the fortress sprite every 180 frames until the cap is reached. On level 1, up to 3 homing missiles can be in flight at a time. Every subsequent level increases this cap by 1. This 180 frame timer keeps running even after the cap is reached. So, if the player shoots one down when all homing missiles are in flight, it may be less than 180 frames until the next one launches (it could in fact happen on the very next frame, depending on the state of the timer).

### Enemy projectiles

Every 600 frames, the enemy fortress undergoes a charging/firing sequence as described in `The enemy fortress`. This launches an enemy projectile, represented as a circle with a radius of 32px. This projectile spawns at the center of the enemy fortress sprite, and it has a bright red 2px border and a dark red fill. Enemy projectiles move in a straight line at 8px/frame in the direction of the player's position at the time of firing. Enemy projectiles cannot change course once launched, and are removed from play when they reach any screen edge. Enemy projectiles have no collision detection with enemy homing missiles or enemy shield rings. If a player projectile impacts an enemy projectile, the player projectile is removed from play, and the enemy projectile is unaffected. If the enemy projectile impacts the player's craft, the craft is destroyed.

Enemy projectiles do NOT screen wrap.

### The player's craft

The player's ship is represented as an elongated triangle, 20 pixels wide and 30 pixels tall. The ship has a white outline and a light gray fill.

Holding the left or right arrow keys rotates the ship continuously at 5 degrees per frame. Releasing the left or right arrow key stops rotation immediately.

Holding the up arrow key applies acceleration of 0.3 pixels per frame squared in the ship's facing direction. The ship has a maximum speed of 8 pixels per frame. When the up arrow key is released, apply linear friction of 0.98 per frame to slow the ship gradually back to 0.

Screen wrapping is applied at all screen edges. Collision detection is a simple bounding circle with a radius of 20px from the center of the player's craft. If an enemy homing missile or projectile enters this bounding circle, the craft is destroyed. If the craft comes within 20px of any active shield segment, the craft is destroyed. If the craft's bounding circle impacts the fortress's bounding circle, the craft is destroyed.

If the player's craft is destroyed by any means, the game transitions to Game Over mode. Large red text reading "GAME OVER" is displayed on a plain black background. Pressing ESC in game over mode transitions the user back to the title screen.

### Player projectiles

Pressing the space bar launches a single projectile fires from the tip of the ship (15px forward along facing direction from center). Its initial velocity is the ship's current velocity plus 6 pixels/frame in the ship's facing direction. Cannon projectiles travel 1000 pixels from the spawn point, respecting screen wrap on all screen edges. If the projectile travels 1000 pixels without impacting anything, the projectile is removed from play. This 1000px range is cumulative distance traveled, unaffected by screen-wrap teleportation. 

Holding space has no effect - only one projectile is spawned for each press of the space bar. Cannon projectiles are very small yellow circles with radius 6px. Player projectiles can pass through disabled shield segments. If a player projectile comes within 6px of any active shield segment, the nearest active shield segment is disabled, and the projectile is removed from play.

Only three player projectiles can be in flight at a time. Pressing space bar when three player projectiles are already in play does nothing. This cap is raised by one for each subsequent level, and is removed entirely starting on level 5.

Due to screen wrap, it is possible for a player projectile to impact the player's own craft. This triggers craft destruction and Game Over mode. To prevent instant self-kills on launch, player projectiles have NO collision detection with the player's craft for the first 30 frames after spawning. There is no such delay in collision detection between player projectiles and any enemy asset.

## Thrusters

When the player is thrusting, small yellow circles should be ejected from the rear of the ship. These circles should have a random radius between 3 and 8 pixels. They fade from yellow to orange, and then to red, and their alpha is adjusted so that they become fully transparent as they travel from the ship. This simulates thruster exhaust. These circles do not cause asteroid impact events and have no effect on powerup icons. It is a purely cosmetic visual effect. Initial velocity is random between 6 and 10 pixels per frame. Alpha adjustment is 5% per frame, starting from fully opaque and ending with fully invisible.

### Misc

There is no heads-up display and no indication of score.

## Audio

If audio is enabled, the following game events are supported:

- `startup`: played once when the game launches.
- `newGame`: played when starting level 1.
- `pause`: played when the player pauses the game.
- `unpause`: played when the player unpauses the game.
- `playerShoot`: played when the player fires a projectile.
- `homingSpawn`: played when an enemy homing missile spawns.
- `homingDown`: played when a player projectile impacts a homing missile.
- `enemyShoot`: played when an enemy projectile is spawned.
- `playerDown`: played when the player's craft is destroyed by any means.
- `shieldDown`: played when any active shield segment is disabled.
- `shieldUp`: played when a disabled shield segment reactivates.
- `fortressDown`: played when the enemy fortress is destroyed.

Audio file locations can be found in the `audio.json` mapping file. It is not an error if this file does not exist. It is not an error if any of the above game events are not listed in the mapping file. Any unmapped game event will simply have no audio.

## Level progression

Each level begins with a plain black screen and large text reading "BEGIN LEVEL N", where N is the 1-based level number. This text remains on screen for 120 frames, then fades out. The fortress and its shield rings are rendered at the center of the screen, and the player's craft spawns at a random location within 100px of any screen edge. There are no homing missiles or enemy projectiles in play at the start of a level.

Destroying the enemy fortress freezes all animation except for the fortress destruction animation. The player cannot move, shoot, or be destroyed while this animation is in progress. Large white text reading "LEVEL CLEARED" appear centered in the screen for 120 frames, and then the entire screen fades to black, and the player advances to the next level. There is no final level.

Level difficulty increases: each level after level 1 increases the enemy homing missile cap by 1, with no upper limit. Each level also decreases the enemy fortress projectile launching interval by 50 frames, with a minimum interval of 300 frames. (The starting value is every 600 frames on level 1).

Pressing ESC in game mode takes the player to the pause screen. From there, the player can either exit back to the title screen, or resume game play.

## Development stages

- Stage 1: copy the `ArcadeTemplate.py` file from `../arcade-template/` and rename it to `SolarFortress.py`. Edit this file to change the placeholder title screen text with "Solar Fortress", and update comments and docstrings as needed to remove references to the arcade template and replace them with the proper name of this game. The template provides a basic state machine with the following states: Title Screen, Game Mode (simple placeholder text), Pause Mode, Game Over Mode, and Test Mode.
- Stage 2: begin implementing Game Mode by rendering the fortress and the shield rings. There are no homing missiles or enemy projectiles yet, and the player craft is also not rendered yet. The end result of this development stage is that the enemy fortress and shield rings should be rendered, with the shield rings being animated correctly. The player can only press ESC to enter Pause Mode and then exit the game. There is no way to reach Game Over mode or advance levels. Create separate Python files for the Fortress and ShieldRing classes.
- Stage 3: implement the player craft and basic movement controls. Implement screen wrap for the player's craft, and collision detection with the shield rings. Impacting any shield segment with the craft instantly destroys the craft and transitions to Game Over Mode. Create a separate Python file for the PlayerCraft class.
- Stage 4: implement the enemy homing missiles. They should spawn at the correct rate with the correct cap, and should follow the player's craft as the craft moves. Implement collision detection between homing missiles and the player's craft. Create a separate Python file for the HomingMissile class.
- Stage 5: implement the fortress firing sequence and projectile spawn. This sequence should happen at the correct interval. Implement collision detection between enemy projectiles and the player's craft. Ensure that enemy projectiles are removed from play upon reaching any screen edge. Create a separate Python file for the EnemyProjectile class.
- Stage 6: implement player projectiles. Implement collision detection between player projectiles and enemy homing missiles, ensuring that homing missiles can be destroyed. Implement collision detection between player projectiles and shield ring segments, ensuring shield segments can be disabled. Implement collision detection between player projectiles and the enemy fortress, ensuring levels can be completed. Implement the level advancement difficulty changes and increased caps. Implement screen wrapping for player projectiles on all screen edges. Create a separate Python file for the PlayerProjectile class.
- Stage 7: implement the thruster visual effect for the player craft. implement full audio support using the game event to audio file location mapping provided by `audio.json`, if present. Ensure all game events are wired up to their associated audio file.

At the conclusion of each stage, launch the game in Test Mode (`--test` command-line argument) and ensure it exits with code 0 and no error messages on stdout or stderr. A warning about missing `audio.json` does not constitute an error message.

