# Sound assets for SuperAsteroids

These aren't mine! All credit goes to https://ci.itch.io/arcade-sound-effects-pack

## Sound details

|Original filename|SuperAsteroids filename|Purpose|
| --- | --- | --- |
|mystery\_1|title\_screen|Played when starting a new game (title screen to game mode transition) - NOT played when advancing between levels|
|door\_closed|cannon\_lvl1|Cannon fires at power level 1 (play once per space bar press)|
|hurt\_2|cannon\_lvl2|Cannon fires at power level 2 (play once per space bar press)|
|shrink|cannon\_lvl3|Cannon fires at power level 3 (play once per space bar press)|
|animal\_bird\_tweet|laser\_lvl1|Laser beam fired at power level 1 (play once per space bar press)|
|laser\_5|laser\_lvl2|Laser beam fired at power level 2 (play once per space bar press)|
|laser\_6|laser\_lvl3|Laser beam fired at power level 3 (play once per space bar press)|
|laser\_3|shield\_activated|The shield is activated at any power level (play once per space bar press)|
|fire_3|shield\_ram|The player collides with any asteroid while the shield is active.|
|explosion\_2|asteroid\_split|An asteroid splits into smaller asteroids|
|explosion\_5|asteroid\_destroyed|A small asteroid is destroyed (no further split)|
|bubble|powerup\_spawn|A powerup icon or fuel pod has appeared!|
|disappear|powerup\_destroyed|A powerup icon or fuel pod has been destroyed (by any means)|
|powerup\_2|powerup\_collected|The player successfully collects a powerup icon or fuel pod|
|earthquake|ship\_destroyed\_asteroid|The player's ship is destroyed by an asteroid impact|
|lose\_1|ship\_destroyed\_friendly\_fire|The player's ship is destroyed by friendly fire|
|fire\_1|thrusters|Played in a continuous loop while thrusters are firing - stops playing when thrusters are deactivated|
|animal\_cow|ufo|Played in a continuous loop while at least one UFO is active - stops playing when a UFO is destroyed|
|harsh\_destruction|ufo\_destroyed|Played when a UFO is destroyed|
|animal\_bird\_tweet|mine\_activated|A mine has been activated|
|collect\_7|mine\_pulse|A non-activated mine "pulses" (scanning for targets)|
|explosion\_4|mine\_detonate|A mine detonates|

## The gravity well cues (added with the fifth weapon)

The arcade pack above has nothing that sounds like "spacetime", so the two
cues for the Gravity Wells weapon were synthesized in-project (stdlib `wave`)
instead of being borrowed. They match the pack's format exactly: mono, 44100
Hz, signed 16-bit PCM, peak amplitude ~7000, so the mixer levels sit in the
same range as everything else in this folder.

|Source|SuperAsteroids filename|Purpose|
| --- | --- | --- |
|synthesized (falling sweep + rising hiss)|gravity\_well\_activated|A gravity well is deployed at any power level (play once per space bar press)|
|synthesized (sub-bass glide + low-passed crack)|gravity\_well\_collapsed|A gravity well reaches the end of its lifetime and collapses|

