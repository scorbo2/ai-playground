# SuperAsteroids 2!

A clone of the classic "Asteroids" arcade game, but with some cool improvements and new features.

This directory contains the spec and the dev plan that was given to Qwen 3.8 27B as part
of my evaluation of that model. Watch it on YouTube: https://www.youtube.com/watch?v=5boaj8ncLSM

## The spec and the dev plan

You can find it in the parent directory: [SuperAsteroids2.md](../SuperAsteroids2.md)

## Weapons (six, not four)

The spec ships four weapons; this build adds **Gravity Wells** and **Homing
Missiles**. Every weapon runs power levels 1-5, and picking up a matching
powerup icon bumps the current weapon one level (a different type switches at
power 1).

| Weapon | Icon | What it does |
| --- | --- | --- |
| Cannon | white **C** on yellow | press-based square shots, in-flight caps, 20-degree fan from level 2 |
| Laser | white **L** on light blue | a charged beam that stops at the first thing it touches |
| Ramming shield | white **S** on red | a charged ring that destroys and bounces, and blocks enemy shots |
| Shrapnel mines | white **M** on brown | one proximity-fused mine per press, 8-way shrapnel burst |
| Gravity wells | white **G** on magenta | plants a singularity that drags the field into it |
| **Homing missiles** | white **H** on dodger blue | fire-and-forget rockets that hunt the nearest rock or saucer and detonate on it |

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

Space lights a rocket. It leaves from your tip carrying your velocity, locks
onto the **nearest asteroid or UFO** (nearest is wrap-aware: the rock on the
other side of the seam is the nearest one), and steers into it at *your* ship's
rotation rate, acceleration, and top speed - the missile has no physics of its
own to tune, it borrows yours. Whatever it touches dies outright: asteroids do
**not** split, saucers pop, mines detonate, and the missile dies with them.

| Level | Rockets per launch | Reload | Own-ship immunity |
| --- | --- | --- | --- |
| 1 | 1 | every 90 frames | no |
| 2 | 1 | every 30 frames | no |
| 3 | 2 (nearest + next-nearest) | every 30 frames | no |
| 4 | 2 | every 15 frames | no |
| 5 | 2 | every 15 frames | **yes - they pass through you** |

All of it lives in `MISSILE_LEVEL_SPECS` in `game_constants.py`. The reload is
the only press gate: there is **no in-play cap**, so a patient player can fill
the field with ordnance. A two-rocket launch is one "Shot" and one sound; only
the asteroids a missile kills count as "Hits".

Gotchas worth knowing:

- **they are hostile to you**. For 30 frames after launch a missile cannot touch
  your ship; after that, catching up with your own rocket is an instant
  `FRIENDLY FIRE!` game over. Level 5 is the only immunity, and it is keyed on
  your *current* weapon: switch away and your old missiles get their teeth
  back;
- **you can shoot them down**, which is how you clean up after yourself: a
  cannon shot (any level), the laser beam, a raised ramming shield, a mine (or
  one of its shrapnel), or a gravity well's event horizon all kill a missile -
  and a UFO bullet will do it for you. Nothing about a missile is immune to
  gravity-well pull, either;
- **a missile with a dead target re-locks**. If the rock it was chasing
  explodes first, it takes the next nearest hazard the same way (ranked from
  *your* ship, so two rockets can genuinely swap attention); if the field has
  nothing left to hunt, it keeps burning in a straight line until the level
  ends - unlimited fuel, unlimited range, no distance budget;
- **missiles ignore each other** (they pass through), so a salvo does not
  degenerate into a demolition derby of its own making;
- a missile that clips a powerup icon or fuel pod destroys it (once the icon's
  own grace period is spent) and scores nothing. Grab the icon before you
  fire over there;
- the missile body is light gray; **dodger blue is only the icon and the HUD**.
  If you see a blue cylinder, that is a bug.

### Try one right now

The `--debug` hotkeys spawn powerup icons anywhere on the field (never within
200 px of the craft):

```bash
python3 main.py --debug   # then press H in Game Mode, and Space to launch
```

`C`/`L`/`S`/`M`/`G`/`H` spawn Cannon/Laser/Shield/Mines/Wells/Missile icons,
`F` spawns a fuel pod, `U` spawns an enemy UFO.

To see the friendly-fire rule the way it is meant to be seen: grab the `H`
icon, hold still, fire, and then do not move for a second.

## Tests

The homing-missile rules (lock-on and re-lock, the reload cadence per power
level, wrap-aware targeting, shoot-downs, friendly fire and the level-5
immunity, scoring, and the shared thruster loop) are covered by a unit suite:

```bash
python3 -m unittest discover -s tests -v
```

It needs no window and no audio device (it asks SDL for the dummy drivers),
only `pygame-ce`.

