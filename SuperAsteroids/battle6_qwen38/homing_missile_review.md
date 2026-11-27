# Code Review: `homing_missiles_qfn` (QFN) vs `homing_missiles_ink` (INK)

**Spec:** `homing_missiles.md`
**Baseline:** `master` @ `2f6d808`
**Branches reviewed:** `homing_missiles_qfn` (`f9e7fb6`), `homing_missiles_ink` (`dd17f9f`)
`homing_missiles_dr` ignored (generated no output).

Both branches were read in full, run headless (`SDL_VIDEODRIVER=dummy`, `main.py --test`),
soaked for thousands of frames of real `GameState.update()` with missiles, mines, wells and
UFOs in play, and probed against every spec bullet with a single independent harness driving
both branches through the same checks (i.e. not trusting either author's own tests).

**Overall impression:** Both of you clearly *read* the spec and both understood the codebase's
odd, prose-heavy house style. That's more than `homing_missiles_dr` managed (congrats, that one
contributed a git ref and nothing else). But they solved different problems: **QFN wrote the
sixth weapon this codebase was expecting; INK wrote a homing missile that happens to be adjacent
to this codebase.** INK's version is tighter and more readable — and it lets your own missile kill
you through a raised ramming shield, which is the one interaction the spec spelled out in a
bullet list.

### Verification summary

| Check | QFN | INK |
|---|---|---|
| Raised shield absorbs own missile (ring range, 40px) | ✅ | ✅ |
| Raised shield absorbs own missile (craft contact, 25px) | ✅ | ❌ **`FRIENDLY FIRE!`** |
| 30-frame launch grace / post-grace friendly fire / P5 immunity | ✅ | ✅ |
| Asteroid destroyed outright, no split, scored as a hit | ✅ | ✅ |
| Shot down by: cannon / laser (beam spent) / shield / mine (+detonates) / shrapnel / UFO bullet / well core (well unharmed) | ✅ | ✅ |
| Shot-down scores no hit/shot; UFO kills score no hit; icon kills score no hit | ✅ | ✅ |
| Dual launch = 1 shot, 1 `missile_launch` cue | ✅ | ✅ |
| Not immune to gravity-well pull; cleared at level end; pass through each other | ✅ | ✅ |
| Well **collapse kick** reaches missiles | ❌ (nit) | ✅ |
| Mine proximity fuse armed by a passing missile | ✅ | ❌ |
| Drawn silhouette (spec: 20×6) | 21×7 ✅ | **29×8** ❌ |
| Cannon shot reach vs missile / vs 40px asteroid | 26 / 56 px (consistent-ish) | **11 / 56 px** (two physics) |
| Shipped tests | 49, all pass | none |

Diff size (excluding the committed spec file and the WAV): QFN ~1,840 insertions (of which 917
are tests) → ~923 lines of production code; INK ~675 lines of production code.

---

## 🐛 Bugs & Edge Cases

### INK — the ramming shield is a polite doormat (real bug)

`states/game.py`, `_resolve_missile_hits`: friendly fire is the **first** check in the loop, the
shield absorb is the **ninth**. So:

```
shield up, missile at 40px (ring only)   -> missile destroyed
shield up, missile at 25px (ring+craft)  -> game_over=FRIENDLY FIRE!, missile alive
```

Your shield intercepts the missile when it's still 45 px out, and then politely stands aside the
instant it's close enough to matter. The spec lists "an impact against the ramming shield at any
power level" as a missile killer, and this codebase treats the ring as impenetrable everywhere
else (UFO bullets, mine bursts, wells all absorb/ram ahead of the craft check). **Fix:** hoist the
`shield_up` absorb above the craft check — which is exactly what QFN did (`_resolve_missile_hits`,
shield branch before the grace-gated craft branch).

### INK — the minefield forgot the missile exists

`_mine_in_activation_radius` (untouched) doesn't include `self._missiles`, but the mine's rule is
"ANY object entering it arms the mine". Verified: a missile 100 px from an armed mine flies past
without waking it; it then usually body-slams it, which masks the bug in casual play. QFN added
missiles to the activation set.

### INK — collision convention drift

You wrote `missile.touching(p.x, p.y, p.half_size, ...)`, i.e. missile circle + a *1 px* bullet
radius. Every other bullet test in this file goes through `projectile.hits_circle(target…)`, whose
`octo_size` gives a size-2 shot a **56 px** reach against an asteroid. Same bullet, same frame: it
shreds a rock at 50 px and phases through a 20 px missile at 12 px. Measured reach vs a missile:
**yours 11 px, QFN's 26 px**. Whatever you think of that inflated baseline hitbox (and I have
opinions — it's a 2×2 pixel "block" with a 32×32 hitbox), *inventing a second, stricter physics
for your new object* is how "why didn't my shot connect" tickets get filed. Reuse
`projectile.hits_circle(missile.x, missile.y, missile.radius, …)`.

### INK — missiles are 45% longer than the spec

The spec is unusually concrete: *"light gray cylinders, 20px long by 6x wide."* Your
`_capsule_shape()` puts rounded caps at `half_len + half_w*cos(θ)`, so the body measures 26 px,
plus a 4 px nozzle. Measured drawn bbox: **29×8**. QFN's chamfered cylinder measures 21×7 (20×6
plus a 1 px outline). Also your exhaust spawns at `MISSILE_LENGTH / 2` = 10 px aft — *inside* your
13 px half-body. QFN passed the launcher's own `rear_offset` into the puff factory precisely so
this couldn't drift.

### INK — latent trap: `surviving` is committed only at the end

`_resolve_missile_hits` accumulates `surviving` and assigns `self._missiles = surviving` after the
loop, but `return False` on friendly fire exits mid-loop — silently resurrecting every missile
already destroyed *that frame*. Harmless today (we're going to Game Over), lethal the first time
someone calls this pass for a non-terminal reason. Assign as you go, or `try/finally`.

### QFN — the well grabs the rocket but won't push it out

`_apply_gravity_well_pull` drags missiles (spec-mandated), but `_evict_gravity_well` doesn't kick
them. So a missile parked inside a dying field is pulled for 400 frames and then simply… released,
un-shoved, while every other object gets the eviction kick. INK did both. One-line fix: mirror the
`_well_kicks` loop.

### QFN — cooldown survives the level boundary (nit)

`HomingMissiles.reset_active()` is inherited as a no-op, so
`HomingMissiles._frames_until_reloaded` carries into the next level. INK overrode `reset_active()`
to re-arm the cadence. Not in the spec; INK is nicer.

### Both — deliberate design divergence worth a decision, not a shrug

Re-lock anchor: QFN re-ranks **from the craft** (same anchor as the launch lock, one rule, one
place). INK re-ranks **from the missile** — defensible gameplay, but it means one feature contains
two different definitions of "nearest", and the spec's *"locks onto the next nearest"* reads as the
next entry of the *same* ranking. If you want missile-anchored re-locking (INK), say so in the
spec-adjacent docs and accept the divergence — don't leave it as an accident of which object held
the list.

---

## ⚡ Performance

Both are comfortably inside a 16.6 ms frame. Measured (400-iteration medians, same box):

| Scenario | QFN | INK |
|---|---|---|
| 20 missiles + 20 rocks, full missile pass | 13.5 µs/f | 14.7 µs/f |
| 40 missiles + 20 rocks | 85 µs/f | 81 µs/f |
| Laser L5 firing + 40 missiles + 10 shots | **820 µs/f** | **1140 µs/f** |

The only interesting number is the last one, and it's INK's fault: `_beam_hits_missile` re-samples
the **entire 250 px beam, per missile, per frame** — *after* `_resolve_laser_hits` already walked
that beam in the same frame. You built `beam_samples()` (a genuinely good extraction) and then used
it to do the same work twice. Fold the missile test into the existing per-sample loop like QFN did,
or cache the sampled points once per frame.

Second-order nit for both: lock-liveness is `O(missiles × (asteroids + ufos))` per frame;
irrelevant at these counts, worth a set if you ever raise the caps.

---

## 🧼 Quality & Style & Architecture

**QFN — this is what "send a PR to someone else's codebase" looks like.** The missile holds a
*reference*, not coordinates; the weapon spawns unlocked rockets and never sees an asteroid list;
the state owns arbitration — that is *verbatim* the split `entities/mine.py` and
`entities/gravity_well.py` document in their module headers. It added a `MISSILE_LEVEL_SPECS` table
row-per-level, a `MISSILE_LABEL_COLOR` alias so the icon and HUD colours can't drift (the trick
weapon five introduced), `MISSILE_SELF_IMMUNE_POWER` instead of a bare `5`, updated the frame-order
docstring (steps renumbered, insertions justified), and — the tell — **refactored
`spawn_thruster_puffs(launcher, back_offset)` instead of copy-pasting it**, which is the only way
"same visual effects as the player's ship" stays true after the next person touches the exhaust.
It also left 49 unit tests that map one-to-one onto spec bullets, and they pass unmodified. Ship it.

**INK — better code hygiene, worse contract discipline.** Credit where due: `Laser.beam_samples()`
is a real dedup and the two dead imports (`wrap_around`, `LASER_SAMPLE_STEP`) were cleaned out of
`game.py`; `reset_active()` re-arming is a nice touch; the missile pass reads as a checklist;
pyflakes is clean; the README table is good. But:

- **`MissileLaunchContext` is the wrong shape.** To let the *weapon* sort the asteroid and UFO
  lists, you had to (a) rewrite the `Weapon.on_press` contract docstring to admit a DTO, (b) make
  `states/game.py` import from `weapons.missile` directly, bypassing the `weapons` façade, and
  (c) split one targeting rule across **three modules** (weapon sorts at launch, entity sorts at
  re-lock, state decides when). That's the cost of the whole context object: ~50 lines of plumbing
  to move responsibility to a place the codebase explicitly says doesn't own it.
- **22 lines of copy-pasted exhaust code.** `spawn_missile_thruster_puffs` is
  `spawn_thruster_puffs` with `craft` renamed and `base_offset` swapped. That's not a new function,
  it's a parameter — and it's already not exported through `effects/__init__` like every sibling.
- A dual salvo spawns **both missiles at the identical point with identical state**, so they fly in
  lockstep forever; QFN split them across the launch axis.
- Magic `5` for the immunity power level; `DODGER_BLUE` hard-coded in both `POWERUP_TYPES` and
  `LABEL_COLOR` (the drift hazard weapon five's naming convention exists to prevent).
- Shot-down missiles vanish silently — no debris, nothing. QFN scatters light-gray wreckage and
  documents why there's no SFX. The spec is silent; "invisible interception" is still a worse game
  feel.
- **Docs lie about the build.** `README.md` still says *"Weapons (five, not four)"* and *"this build
  adds a fifth, **Gravity Wells**"* while a sixth row sits in the table underneath. QFN renumbered
  the heading and wrote a "Homing missiles, in play" section with the gotchas it actually
  discovered.

**Both:** neither added a HUD reload indicator. That's fine — "follow the pattern of existing
weapons" and the cannon has no bar either. Both correctly reserved dodger blue for the icon/HUD and
kept the body light gray. Both added `H` to debug, `DODGER_BLUE (30,144,255)`, the
`sfx/missile_launch` name + `ALL_SOUNDS` entry, and neither touched the fuel tank. (Security:
nothing to attack — no untrusted input, no I/O, no persistence. Nobody committed an API key to an
arcade clone, so we're even.)

---

## Verdict

**QFN did the better job**, and not by a hair. It implemented every spec rule I could construct a
failing test for, matched the existing architecture instead of bending the architecture to fit its
design, respected the spec's literal geometry, kept one collision convention, and backed all of it
with 49 passing tests and a README that documents the *gotchas* rather than just the table. Its
misses are nits: the missing well-collapse kick and an un-armed cooldown across a level boundary.

INK is the prettier *individual* module and it lost on integration: a spec-explicit shield
interaction that ends the game instead of saving it, a second collision physics, a 45%-oversized
missile, a triple-split targeting rule, and no tests to catch any of it.

- **QFN:** ✅ **Ship it** — fix the `_evict_gravity_well` missile kick in the follow-up, and
  consider re-arming the reload in `reset_active()`.
- **INK:** 🔧 **Fix these and I'll sign off** — (1) shield absorb before the friendly-fire check,
  (2) use `projectile.hits_circle` for shoot-downs, (3) draw 20×6 and emit exhaust from the real
  tail, (4) add missiles to the mine activation set, (5) fold the beam test into the laser's sample
  loop instead of re-walking it per missile, (6) collapse the DTO and keep targeting in the state,
  (7) delete the duplicated puff factory, (8) update the README heading — and then write the tests
  you skipped.

---

## Appendix — how the claims were verified

Both worktrees (`~/tmp/homing_missiles_qfn`, `~/tmp/homing_missiles_ink`) were driven from the same
scratch harness so the numbers are apples-to-apples. To reproduce:

```bash
# both branches start clean
for b in homing_missiles_qfn homing_missiles_ink; do
  (cd ~/tmp/$b/SuperAsteroids/battle6_qwen38 \
   && SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python3 main.py --test --nosound)
done

# QFN's own suite (49 tests, all pass as committed)
(cd ~/tmp/homing_missiles_qfn/SuperAsteroids/battle6_qwen38 \
 && SDL_VIDEODRIVER=dummy SDL_AUDIODRIVER=dummy python3 -m unittest discover -s tests -v)

# both are pyflakes-clean over the changed modules
(cd ~/tmp/<branch>/SuperAsteroids/battle6_qwen38 \
 && python3 -m pyflakes entities/missile.py weapons/missile*.py states/game.py \
      game_constants.py sound.py effects/particles.py weapons/base.py weapons/laser.py)
```

The behavioural table, the 11/26/56 px collision-reach telemetry, the 29×8 vs 21×7 drawn-size
measurements (a pixel bbox scan of a `pygame.Surface` the entity drew onto) and the µs/frame
benchmarks came from throwaway scripts that fake the app/sound/screen and call the state's own
private passes (`_resolve_missile_hits`, `_resolve_projectile_hits`, `_resolve_laser_hits`,
`_resolve_mine_interactions`, `_resolve_gravity_well_contacts`, `_sync_sound_loops`,
`_advance_level`) plus a 4,000-frame `update()` soak with mines, wells and UFOs injected. They live
in `/tmp` rather than in the repo; if any of this code gets merged, port QFN's `tests/` file and add
the shield-at-craft-contact case, which is the one neither author covered on their own.
