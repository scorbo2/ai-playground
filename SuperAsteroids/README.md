# SuperAsteroids!

A clone of the classic "Asteroids" arcade game, but with some cool improvements and new features.

The point here is to employ proper spec-driven development instead of YOLO one-shotting a prompt and hoping for the best.

## The process

I started by outlining the requirements in painful detail: [SuperAsteroids.txt](SuperAsteroids.txt)

Then I took those requirements to Qwen 3.6 27B Q6 and asked it to come up with an
implementation plan broken into discrete stages. Each stage should produce a runnable
program that I can manually test. I also requested the addition of a `--test` flag
that Qwen could use to verify that the game at least starts up okay (this minimizes
the copy+pasting of error messages from the console that I might otherwise have to do).

[SuperAsteroids-implementationPlan.md](SuperAsteroids-implementationPlan.md)

## The result

A complete, playable game, coded up in one evening! 

Manual testing revealed minor problems here and there that were reported back to Qwen and
addressed before moving on to the next development stage. But by having clear stage boundaries
with clear testing goals, we were able to lock down each stage one by one until the whole
game was complete.

TODO insert YouTube link once it's up.

## Post-completion changes

A few things didn't sit right with me after playing the game. So, even though these weren't
in the original requirements, made the following changes anyway:

- added a game time indicator in the HUD
- dynamically reduce the time between powerup spawns depending on levels (higher levels spawn powerups more frequently)
- Ramming shield at level 3 should instantly destroy asteroids with no splitting, similar to the laser level 3.
- Downloaded some sound effect assets into `sfx` subdirectory and wired them up. Backported this into the spec and the implementation plan (added Stage 11)
- Asteroids have a small random chance of spawning a powerup icon when they split or are destroyed. The chance decreases as levels advance.

## Future ideas

- Once per level, an alien ship should appear and shoot projectiles at the player.
- Cannon projectiles need to be larger and have a bigger hit radius. Maybe also move faster?
- Package up a downloadable installer to make it easier for non-python devs to grab and play.
- Add a cheat mode (but call it `--debug`) with keyboard shortcuts for switching weapons and power levels.
- laser beam length increases from lvl1 to lvl2, but not again at lvl3? That seems weak.

