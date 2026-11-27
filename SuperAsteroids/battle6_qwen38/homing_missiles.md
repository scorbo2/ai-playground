# Homing missiles

Your task is to add a new weapon type to this game: Homing Missiles. These missiles launch from the player craft and "lock on" to whatever asteroid or UFO is nearest the player craft at the time of launch. Homing missiles are light gray cylinders, 20px long by 6x wide. They have a thruster on the back with the same visual effects and acceleration/max speed characteristics as the player's ship. Missiles have the same rotation rate as the player's craft. They turn and thrust and try to steer themselves into the target. If the target is destroyed before the missile impacts it, the missile automatically locks onto the next nearest asteroid or UFO. Missiles have unlimited fuel (they do NOT draw from the player's fuel supply) and unlimited travel distance. When a level ends, all homing missiles in play are removed from play. When a homing missile impacts an asteroid or UFO (either the "locked on" target or any other asteroid/UFO that gets in the way), that asteroid/UFO is destroyed, ignoring the usual asteroid splitting rules (the missile is also destroyed). The usual asteroid/UFO destruction animation should be triggered.

Homing missiles have a grace period of 30 frames after launch, during which time they cannot impact the player craft. After this grace period, if a homing missile impacts the player's craft, this triggers an immediate "FRIENDLY FIRE!" game over.

## Power levels

1. At power level 1, the player can launch 1 homing missile every 90 frames.
2. At power level 2, the player can launch 1 homing missile every 30 frames.
3. At power level 3, two missiles launch simultaneously (one launch per 30 frames). One missile locks onto the nearest asteroid or UFO, and the other locks onto the next-nearest asteroid or UFO. (They may lock onto the same object if there is only one asteroid or UFO in play).
4. At power level 4, the reload delay is lowered to 15 frames.
5. At power level 5, the player gains immunity to their own missiles (they pass through the player craft harmlessly).

## Audio

A new `sfx/missile_launch.wav` sound effect has been added. This sound effect should play on every missile launch (dual-missile launches count as one launch - don't play the effect twice per launch at power level 3 or higher). When a missile is thrusting, re-use the existing thruster sound effect (same as the player craft).

Implementation note: the current "thrust" sound effect plays on a loop that terminates when the player releases the up arrow. Homing missiles will require a bit of refactoring such that the thruster effect plays on loop when EITHER the player is currently thrusting OR when any homing missile is thrusting.

## Color

Add a new `DODGER_BLUE (30,144,255)` constant. We will use this for homing missile powerup icons and HUD elements. Note that the missiles themselves remain light gray.

### Powerup icons

Add a new type of powerup icon with the same rules as the existing ones. The new icon should be a dodger blue circle with a white "H" label. Add a hotkey "H" to debug mode to allow the player to spawn a missile powerup icon at will.

### HUD

Update the HUD, following the pattern of existing weapons. Homing missiles should use the dodger blue color for HUD display.

## Score

A missile that impacts and destroys any asteroid ("locked on" or not) counts as a "hit" for scoring purposes. Note: dual-missile launches count as one "shot" for scoring purposes. (This is similar to the cannon, which can launch more than one projectile in a single "shot").

UFO hits do not count as "hits" for scoring purposes.

The player destroying one of their own missiles by any means does not count as a "hit" for scoring purposes.

A homing missile impacting a powerup icon does not count as a "hit" for scoring purposes.

## Projectiles and homing missiles

Homing missiles can be shot down! If the player launches a homing missile and then switches to any other weapon type, the player can shoot down their own missile. Also, UFO projectiles will destroy a homing missile on contact.

Homing missiles can be destroyed by:

- a cannon projectile at any power level. The projectile is removed from play.
- a laser beam at any power level. The laser beam deactivates.
- an impact against the ramming shield at any power level.
- impacting a shrapnel mine at any power level OR any projectile launched from a shrapnel mine. If a mine is hit, it detonates. If a mine's projectile is hit, the projectile is removed from play.
- impacting the event horizon of a gravity well at any power level. The gravity well is unaffected.
- impacting a powerup icon outside of the icon's grace period. The icon is removed from play.

Note: homing missiles are not immune to gravity well pull!

Homing missiles cannot impact other homing missiles (they pass through each other).

## Defining the "nearest" target

Targeting should be wrap-aware, based on the `torus_distance`.
