# SuperAsteroids 2!

A clone of the classic "Asteroids" arcade game, but with some cool improvements and new features.

This directory contains the spec and the dev plan that was given to Qwen 3.8 27B as part
of my evaluation of that model. Watch it on YouTube: https://www.youtube.com/watch?v=5boaj8ncLSM

## The spec and the dev plan

You can find it in the parent directory: [SuperAsteroids2.md](../SuperAsteroids2.md)

## Weapons (five, not four)

The spec ships four weapons; this build adds a fifth, **Gravity Wells**. Every
weapon runs power levels 1-5, and picking up a matching powerup icon bumps the
current weapon one level (a different type switches at power 1).

| Weapon | Icon | What it does |
| --- | --- | --- |
| Cannon | white **C** on yellow | press-based square shots, in-flight caps, 20-degree fan from level 2 |
| Laser | white **L** on light blue | a charged beam that stops at the first thing it touches |
| Ramming shield | white **S** on red | a charged ring that destroys and bounces, and blocks enemy shots |
| Shrapnel mines | white **M** on brown | one proximity-fused mine per press, 8-way shrapnel burst |
| **Gravity wells** | white **G** on magenta | plants a singularity that drags the field into it |
| **Homing missiles** | white **H** on dodger blue | fire-and-forget missiles that lock on and fly themselves into targets |

### Gravity wells, in play

Space plants a singularity 200 px **behind your tail**. Like a shrapnel mine,
you lay it and run: the well does not travel, explode, or protect you, it just
holds that spot and bends everything nearby toward its crush core. Rocks,
saucers, and mines that reach the core are consumed (rocks whole, mines
detonated, saucers deleted). It pulls *you* too - a well is a slingshot and a
hazard in the same keypress. When its lifetime runs out it collapses and
flings whatever is still inside the field **outward**, so the well itself can
never be what finally kills you; it kills you by dragging a rock into you
instead.

| Level | In-play cap | Pull radius | Pull | Core | Lifetime | Color |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | 1 | 120 px | 0.08 | 14 px | 240 f | magenta |
| 2 | 2 | 150 px | 0.11 | 16 px | 300 f | magenta |
| 3 | 3 | 180 px | 0.15 | 18 px | 360 f | white |
| 4 | unlimited | 220 px | 0.20 | 20 px | 420 f | cyan |
| 5 | unlimited | 300 px | 0.30 | 24 px | 600 f | orange |

Level 5 is the overpowered one: the player's own wells no longer pull or crush
their own ship, the cap is gone, and the field is 300 px across. Every number
above lives in `GRAVITY_WELL_LEVEL_SPECS` in `game_constants.py` - one table
row per level, no code changes needed to tune it.

Gotchas worth knowing:

- the faint ring drawn around a well *is* the pull radius. If you cannot see
  the ring (window too small, or the well straddles a screen edge), the pull
  is still wrap-aware and reaching you from the other side of the seam;
- projectiles and pickups (powerup icons, fuel pods) are deliberately immune to
  the pull, so no shot ever lies about how far it has travelled and no fuel pod
  gets flung out of reach;
- the well is only a hazard to *you* from level 4 up: at 215 px of launch
  stand-off, the 120/150/180 px fields of levels 1-3 cannot reach the ship that
  cast them. A level-4 field does reach back, and a parked ship eats its own
  core in about a second (drag tops out at ~3.9 px/frame against your 8
  px/frame top speed, so thrusting away always wins - and since wells now drop
  astern, "away" is simply forward thrust, exactly what you are already doing).
  Level 5 is exempt entirely;
- what *will* kill you at every level is what the well drags into you. Rocks,
  saucers and mines all end up at the core - and if that is where you are
  standing, they arrive at speed;
- the pull strength has a floor (`GRAVITY_WELL_MIN_CRAFT_PULL` /
  `GRAVITY_WELL_STRENGTH_MIN`) for an un-obvious reason: the ship and the mines
  apply friction before they move, and both snap sub-stall speeds to zero. A
  pull weaker than the stall threshold doesn't make them drift slowly, it makes
  them stand perfectly still - an invisible weapon.

### Homing missiles, in play

Space launches the level's missile set from the craft's tail. Every missile
locks onto the asteroid or UFO nearest the craft at launch (dual launches take
nearest + next-nearest; they may both lock onto the same object if only one
exists), turns toward its target at the craft's rotation rate, and thrusts
continuously at the craft's acceleration/max speed - with the same thruster
puffs. If the locked target dies first, the missile re-locks onto the nearest
live asteroid or UFO to itself (torus distance). Missiles have unlimited fuel
and unlimited travel distance, never expire, wrap the screen, and leave play
when the level ends.

| Level | Missiles per launch | Launch cadence | Notes |
| --- | --- | --- | --- |
| 1 | 1 | every 90 frames | |
| 2 | 1 | every 30 frames | |
| 3 | 2 | every 30 frames | dual launch, one "shot" for scoring |
| 4 | 2 | every 15 frames | |
| 5 | 2 | every 15 frames | player gains immunity to their own missiles |

Missiles have a 30-frame launch grace (no impact with the craft); after grace,
a missile impact on the craft is an immediate "FRIENDLY FIRE!" game over.
Impacts destroy the asteroid outright (no split) or the UFO - the usual
destruction animation fires - and asteroid hits count as "hits" (a dual
launch is one "shot"). Missiles are shot down by cannon projectiles, laser
beams, the shield ring, mine burst shots, UFO projectiles, and gravity well
cores (the well is unaffected), and they are NOT immune to gravity well pull.
They pass through each other and through the player's own craft (level 5).
`sfx/missile_launch.wav` plays once per launch; the thruster loop runs while
the craft or any missile is thrusting.

### Try one right now

The `--debug` hotkeys spawn powerup icons anywhere on the field (never within
200 px of the craft). `G` is the gravity-well one and `H` is the missile one:

```bash
python3 main.py --debug   # then press H in Game Mode, and Space to launch
```

`C`/`L`/`S`/`M`/`G`/`H` spawn Cannon/Laser/Shield/Mines/Wells/Homing-missile
icons, `F` spawns a fuel pod, `U` spawns an enemy UFO.

