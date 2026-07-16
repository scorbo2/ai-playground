You will write a complete, runnable Python program using only Pygame and the Python standard library. The program must implement a version of the classic "Asteroids" game with the following specifications. Do not use external assets, images, or third-party libraries, other than Pygame.

[CONSTRAINT 1] WINDOW & SETUP
- Create a non-resizable 800x600 window using pygame.display.set_mode((800, 600))
- Title: "Asteroids"
- No sound or music are required.
- Graphics consist mainly of polygons drawn programmatically.
- The background should be a subtle starfield.

[CONSTRAINT 2] SHIP PHYSICS & CONTROLS
- Ship: elongated triangle, 20px wide, 30px tall, centered at start
- Rotation: Left/Right arrow keys rotate continuously at 5 degrees/frame
- Thrust: Up arrow applies acceleration of 0.3 px/frame² in the ship's facing direction
- Max speed: 8 px/frame. Apply linear friction of 0.98/frame when no thrust is pressed
- Screen wrapping: Ship wraps around all edges

[CONSTRAINT 3] PROJECTILES
- Space bar fires a projectile from the ship's tip
- Projectile initial velocity = ship's current velocity + (6 px/frame) in ship's facing direction
- Max 3 projectiles on screen at once. Ignore space presses if limit reached.
- Projectiles travel exactly 1000 px from spawn point, then disappear.
- Draw as small circles or squares.
- Due to screen wrap, a projectile might hit the player's own ship: Game Over. Display "FRIENDLY FIRE! - Press R to Restart"

[CONSTRAINT 4] ASTEROIDS
- Start with 5 large asteroids (radius 40px), random positions (away from ship), random directions, speed 1.5-2.5 px/frame
- On projectile hit: asteroid splits into 2-3 smaller asteroids (radius = parent/1.5), speed multiplied by 1.2, random directions
- Asteroids smaller than radius 15px are destroyed on hit (do not split further)
- Asteroids wrap around screen edges
- NO collision detection between asteroids. They pass through each other.

[CONSTRAINT 5] COLLISIONS & GAME FLOW
- Ship-asteroid collision: Game Over. Display "GAME OVER - Press R to Restart"
- Level complete: When all asteroids are destroyed, wait 2 seconds, then start next level
- Next level: +2 starting asteroids, base speed +0.3 px/frame, same split rules
- Restart resets to Level 1 with original settings

[CONSTRAINT 6] OUTPUT FORMAT
- Output a single Python source file
- The code must run with `python game.py`
- Assume pygame is already installed

[CONSTRAINT 7] GRAPHICS
- Asteroids should have an irregular shape, not just simple circles
- Asteroid splits should be displayed with an explosion with colourful particle effects
- When the player applies thrust, a small red triangle should appear behind the ship as a visual representation of the thruster firing.

[CONSTRAINT 8] CREATIVE BONUS FEATURE
- Add ONE optional bonus feature of your choosing that enhances gameplay.
- The feature must be togglable at runtime using the 'B' key (press once to enable, press again to disable).
- It must not require external assets or additional dependencies.
- The bonus feature should deliberately violate at least one of the other constraints.
- Example bonus features: 
  - player can fire more than 3 projectiles at a time
  - disable "friendly fire" damage
  - enable collision detection between asteroids with same split rules
  - disable screen wrapping (hard bounce when encountering a screen edge)
  - add occasional enemy ships that fire projectiles at the player
  - player's ship fires three projectiles at once in a 20 degree arc; no reload wait time
- You are not limited to the examples above. These are just suggestions. Try to be creative, and make it fun!

Begin implementation now.

