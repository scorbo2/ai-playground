# Code Review: `collabbob`

**Reviewed against:** `localhost-challenge-tweaked.md`, with `DECISIONS.md` treated as the
authority on intentional deviations.
**Repo state:** 14 stage commits (HEAD `Stage 14 - final verification`), 27,123 lines of
`src/` + `tests/`, 827 tests green in 8.9s.
**Method:** read the spec, the whole config/model/view layer, and the decision log; ran the
suite; drove a real `GameScene` headless for 60,000 frames with random + scripted input;
wrote probe scripts to *prove* each candidate finding rather than assert it from reading.

---

## Overall impression

This is not the usual "LLM wrote a game" crime scene. 827 tests green in 8.9s, a
60,000-frame monkey-patch soak with zero exceptions, zero NaNs, zero out-of-bounds
positions, and a full `step_once()` costing **0.49 ms/frame** (33× headroom on the
16.67 ms budget). The pure-model / view split is disciplined, blocker ordering in
`JumpController` is documented as load-bearing and *is* load-bearing, and `DECISIONS.md` is
a 131 KB confession booth that admits its own earlier screw-ups (the frozen HUD, the
`.convert()` glyph slabs, `PYTHONHASHSEED` leaking into the world graph). Genuinely
impressive engineering discipline.

Which is exactly why the last mile is so irritating. Someone declared "Stage 14 — final
verification", committed it, and then shipped **six committed `.wav` files in a repo whose
spec demands generated audio**, **no `test_stage14.py`**, **no Stage 14 entry in
DECISIONS.md**, and a **spec rule broken in half a dozen lines of code** that a single test
would have caught. You did 95% of the hard work and phoned in the walk to the mailbox.

---

## 🐛 Bugs & Edge Cases

### 1. Jumping makes you invulnerable and deletes the fleet — the spec says the opposite (highest severity)

Spec lines 398–399, verbatim:

> The player is not immune to damage during the jump animation!
> Projectiles in flight can still impact the player craft and do damage!

`GameScene._advance_gunfight()` (`src/scenes/game_scene.py:464-465`) does:

```python
if self.jumps.is_active:
    self.gunfight.clear()
    return
```

`jumps.is_active` is true from the **first frame of the 180-frame burn**, not at the system
gate. And `_advance_encounter()` (`:439`) early-returns with `self.pending_shots = []`, so
nothing new is fired either. Net effect: press `J` and every incoming round vanishes, the
whole system freezes, and you get 3–4 seconds of guaranteed free passage followed by a
freshly-dealt fleet.

Measured with the repo's own test helpers (pirate 100 px away, one 40-damage round 30 px off
the bow):

```
J pressed: False | rounds alive after that frame: 1 | damage absorbed: 60
J pressed: True  | rounds alive after that frame: 0 | damage absorbed:  0
```

Worse, `tests/test_stage11.py:1608-1629` *asserts* this behaviour ("a round crossed the
hyperspace gate" — it never had the chance), so the bug is welded in. And
`src/model/jump.py:309` `request()`'s own docstring says *"the player is not immune to damage
during the burn"* — the model documents the correct rule while the scene contradicts it.
`DECISIONS.md` never mentions spec line 398 at all, so this isn't a documented tweak; it's an
oversight.

**Fix:** keep the despawn at the *gate*, not at the trigger. `_enter_system()` already calls
`self.gunfight.clear()` (`:423`) — that is the correct place. In `_advance_gunfight`, run the
fight normally during `PHASE_BURN` (only the player is unreachable-ish, and even that isn't
true — the ship is visible and moving at terminal jump speed), and skip/clear only once
`jumps.phase == PHASE_TRANSITION` where the world is white-out. Freezing the *fleet's* AI
during hyperspace is a defensible choice; deleting other people's ammunition is not.

### 2. `pygame.Rect.bottomleft` does not mean what this code thinks it means

`src/effects.py:161-162`:

```python
left, top = self._region.topleft
right, bottom = self._region.bottomleft[0], self._region.bottomleft[1]
```

`bottomleft` is `(left, bottom)`. So `right` is holding `left`. The four "corners" the reach
is measured against are `((0,0), (0,0), (0,768), (0,768))` — the right-hand side of the
window is never considered:

```
code reach = 513.6px   true farthest corner = 783.5px   shortfall = 270.0px
```

The comment three lines up says the point is *"so the ring sweeps off the screen edge instead
of petering out in the middle of the view."* It peters out 270 px short of the right edge.
Ah yes, the classic `bottomleft`-is-`bottomright` dance — a bug the pixel-pushers in me would
have found in one screenshot, which is ironic given this codebase has screenshots committed
for *other* bugs.

**Fix:** `right, bottom = self._region.bottomright`.

### 3. Any framerate below 60 FPS turns the game into slow motion (known, documented, never fixed)

`src/main_loop.py:77-79`:

```python
self._accumulator = min(self._accumulator + dt, ACCUMULATOR_LIMIT)
if self._accumulator >= FIXED_DT:
    self._accumulator -= FIXED_DT
    self.step()
```

One `if`, so **at most one simulation step per real frame**, ever. The bounded accumulator
therefore never drains anything — it just hides the debt. Measured:

```
real 120 fps | wall  5.0s | sim steps  600 | game runs at 100.0% of real time
real  60 fps | wall 10.0s | sim steps  600 | game runs at 100.0% of real time
real  50 fps | wall 12.0s | sim steps  600 | game runs at  83.3% of real time
real  30 fps | wall 20.0s | sim steps  600 | game runs at  50.0% of real time
real  20 fps | wall 30.0s | sim steps  600 | game runs at  33.3% of real time
```

Every timer in this game is in frames — the 180-frame jump, the 120-frame launch immunity,
the 300-frame boundary cooldown, the fire rate. On a 30 FPS laptop the "three second" jump
takes six seconds and the "2 second" immunity grace lasts four. No test in the suite ever
passes a real `dt` to `step_once()` (`grep 'step_once(.*dt=' tests/` → nothing), so this is
invisible to CI.

`DECISIONS.md` (Stage 6 backlog) *already knows*: "The accumulator drains at most one step
per frame … a frame slower than 1/60 s silently loses simulation time." It was deferred, then
Stage 11 shipped combat on top of it. It is a one-keyword fix.

**Fix:**

```python
steps = 0
while self._accumulator >= FIXED_DT and steps < 5:
    self._accumulator -= FIXED_DT
    self.step()
    steps += 1
```

### 4. Three RNG streams seeded with the identical integer

When `rng.seed` is configured, one new game constructs **five** `random.Random` objects;
three of them get the same number:

```
#1: seed=12345  first two draws=(0.416620, 0.010169)   <- GameState.rng
#2: seed=12345  first two draws=(0.416620, 0.010169)   <- system graph
#3: seed=12345  first two draws=(0.416620, 0.010169)   <- lore assignment
#4: seed='12345:Alpha:1'        first two draws=(0.995497, 0.872532)   <- port_rng ✅ namespaced
#5: seed='12345:Alpha:1:npc'    first two draws=(0.891386, 0.828202)   <- encounter_rng ✅ namespaced
```

`src/scenes/game_scene.py:95`, `:273`, `:299` each call `Random(seed)` on the raw int. So the
world topology, the per-system lore, and the gameplay rolls (star layout, NPC stat rolls, aim
jitter) are driven by **the same number sequence** — the k-th draw of the graph generator *is*
the k-th draw of the lore picker. Invisible in production (configs ship `"seed": null`), but
it quietly defeats the independence the reproducibility feature exists to provide, and it
means the "seeded determinism" tests are measuring a correlated world.

**Fix:** you already wrote the pattern — `port_rng`/`encounter_rng` namespace with strings. Do
the same: `_random_lib.Random(f"{seed}:gameplay")`, `f"{seed}:graph"`, `f"{seed}:lore"`.

### 5. `tactical.stars.grey_min` / `grey_max` are dead config keys, and `config_hard.json` is silently ignoring a difficulty tweak

I swept all 77 leaf keys of `config_medium.json` against every file under `src/`. Exactly two
are never read:

```
tactical.stars.grey_min    src=NONE
tactical.stars.grey_max    src=NONE
```

`src/model/starfield.py:65` hard-codes it instead:

```python
grey = self._rng.randint(128, 255)
```

`config_hard.json` sets `"grey_min": 100` — presumably a dimmer, meaner hard-mode sky.
Measured actual output: `128..255`, zero pixels below 128. The tuning is thrown away, and
it's a direct failure of the spec's "no hard-coding for game parameters / geometry / palette"
rule. Two of 77 keys is a *very* good hit rate, which is precisely why this one sticks out.

**Fix:** `grey = self._rng.randint(grey_min, grey_max)`, thread it into
`Starfield.__init__`, and add a cross-field check that `grey_min <= grey_max` (currently
`{grey_min: 250, grey_max: 10}` validates clean).

### 6. `VIEW_WIDTH` is imported and then immediately shadowed by a literal

```python
# src/scenes/tactical_view.py:23
from src.hud import VIEW_WIDTH, landing_prompt_text
# src/scenes/tactical_view.py:44
VIEW_WIDTH = 683
```

The import is dead; the magic number is duplicated. `hud.py` uses it for `HUD_ORIGIN_X` /
`HUD_WIDTH`, `tactical_view.py` uses it for the game-view clip rect and camera centre. If one
of those two literals ever drifts, the HUD and the tactical view overlap and the "HUD
components fit in 341px" test only checks one of them. Delete line 44.

### 7. The graph docstring lies about the shipped configs

`src/map_systems/graph.py:263-264`:

> With the shipped configs (`connections_min == 1`) the third phase is a no-op, so a
> 26-system world has exactly 25 edges

The shipped configs all use `connections_min: 2`. Measured over 400 seeds: edge counts
**31–35**, degree histogram `{2: 4752, 3: 5648}`. Separately, `base_config()` (the test
fixture) still ships `connections_min: 1`, so a chunk of the test suite exercises a topology
the game never actually builds — including the "third phase is a no-op" path, which is *not* a
no-op in production. That's a coverage hole disguised by a comment.

### 8. Exact-fuel game over: faithful to the spec, fragile in practice

`src/model/jump.py:301-304` uses bit-exact float equality, which *is* what spec line 403
mandates, and the blocker ordering (illegal-for-other-reasons first, then insufficient, then
exact) is correct and well argued. But measure it:

```
fuel_capacity 1000, burn 0.2/frame: never lands on 250.0 — lands on 249.999999999904
```

So the trap only arms on the "clean" chain (1000 → 750 → 500 → 250 → press `J` → dead) or
after buying whole fuel units. Any thrust in between and the rule is unreachable. That's
arguably *fine* — it's the spec's rule, and the reachable path is the one a player notices —
but it deserves a comment and a `math.isclose` guard, because a future change to
`fuel_burn_per_frame` (hard: 0.4) silently re-tunes how often the ending is reachable at all.

---

## ⚡ Performance

Measured headless (dummy SDL driver): `update()` 0.014 ms, `draw()` 0.474 ms, full
`step_once()` **0.492 ms/frame**. Stage 14's "performance sanity at 60 FPS" is satisfied with
room to spare — though note the dummy driver's `display.flip()` is nearly free, so real blit
cost is not represented in that number.

Two things I'd watch:

- `FlashOverlay.draw` allocates a fresh full-window `SRCALPHA` Surface **every frame** of the
  transition, and `_draw_shockwave` allocates two more ring Surfaces per frame. At 45–60
  frames of transition that's ~180 large allocations per jump. Cache the veil at max alpha and
  `set_alpha()` it.
- `src/effects.py:268`: `import pygame` **inside** `WarpTunnel.draw`, while the module already
  imports pygame at line 29. It's a `sys.modules` lookup per frame; it's also just noise.
- Unbounded config → silent perf cliff: `{"count": 5000000}` for `tactical.stars.count`
  validates clean (see below), and 150 → 15000 is a one-character typo away.

---

## 🔒 Robustness / input validation

There's no network, no untrusted input, so there's no classic attack surface. But the config
is treated as trusted even though the spec makes a *missing* key fatal — so
malformed-but-parseable values are not:

```
ACCEPTED: 5,000,000 stars
ACCEPTED: 100,000 mission offers
ACCEPTED: negative fuel capacity
ACCEPTED: grey_min > grey_max
```

`fuel_capacity: -1` gets through, and `GameState.__init__` writes `self._fuel = -1.0`
**directly to the attribute**, bypassing the `fuel` property's `max(0.0, ...)` clamp
(`src/model/game_state.py:166` vs `:218`). Result: a run that is born out-of-fuel with no
diagnostic. `DECISIONS.md` even flags this itself — "the pydantic schema has no numeric bounds
at all, so no config range violation is currently detectable" — and it still wasn't addressed
by the stage whose job was a config sweep.

**Fix:** `Field(ge=…, le=…)` on the dangerous ones (`stars.count`, `ships_min/max`,
`missions_min/max`, `fuel_capacity`, `system_pixel_size`, all frame counts) plus a
`grey_min <= grey_max` validator.

---

## 🧼 Quality & Style

**Stage 14 is a commit message, not a stage.** The last commit is
`Stage 14 - final verification`, but `DECISIONS.md` ends at Stage 13 (no Stage 14 heading) and
there is no `tests/test_stage14.py`. The spec's Stage 14 gate is explicit:

- *"the scripted playthrough reaches the victory screen"* — no test drives title → difficulty →
  fly → trade → fight → jump → `EndScreenScene` with the victory copy. Victory is only
  asserted as a predicate (`test_stage13.py:471`) and via `scene.end_of_run.ending` (`:1182`).
- *"config sweep proving no hard-coding (jump cost, top speed, fare range, upgrade multiplier,
  spawn chance each change behaviour in a test)"* — `jump.fuel_cost` ✅ and `spawn_chance` ✅
  are varied in tests. `top_speed`, `cargo_fare_per_unit`, and `upgrade_cost_multiplier` are
  **never varied in any test**.
- *"dead-code/TODO sweep"* — no TODOs, but see the unused-import list below.

**Committed binary junk that contradicts the spec's resource rules.** `git ls-files` shows six
WAVs added in the Stage 12 commit and never removed:

```
collabbob/audio_wav/confirm_beep.wav
collabbob/audio_wav/jump_spinup.wav
collabbob/audio_wav/jump_thunderclap.wav
collabbob/audio_wav/scan_klaxon.wav
collabbob/audio_wav/ship_destruction.wav
collabbob/audio_wav/ship_impact.wav
```

The spec requires *generated* audio (`array` + `Sound(buffer=...)`) and says resources live in
`resources/`. These are debug dumps from `scripts/render_audio_buffers.py`, sitting in a
root-level `audio_wav/`, and the README (`:759`) cheerfully tells the reader how to regenerate
them. Plus five `stage*.png` dev screenshots at the project root. And there is **no
`.gitignore`** — with `__pycache__/` and `.pytest_cache/` sitting untracked next to them.

**Hard-coded UI geometry that the spec explicitly wants in config.** Spec line 72: good config
material = "all tunable numbers, **geometry**, palette, probabilities…". `spaceport_view.py`
has ~20 layout constants (`MARGIN`, `BODY_TOP`, `LEFT_WIDTH`, `RIGHT_X`,
`CONTRACT_ROW_HEIGHT`, …) and 7 font sizes; `end_screen.py`, `exit_confirm.py`, `map_view.py`,
`effects.py` (`FLASH_HOLD_FRAMES`, `_IMPACT_PARTICLES`, `_DESTRUCTION_SPEED`, …) follow suit.
`DECISIONS.md:79` justifies `VIEW_WIDTH` under the window-size chicken-and-egg exception — but
`VIEW_WIDTH = 683` is not the window size, it's a layout split *derived* from it. The
palette-in-code decision (`DECISIONS.md:94`) is well argued against the spec's own
"colors-as-defaults" exception and I'll grudgingly accept it. The geometry one isn't recorded
as a deviation at all.

**Undocumented spec deviations** (the ones DECISIONS *does* record — `connections_min: 2`,
`missions_min/max`, the white-out transition, per-entry market rolls — are fine and I'm not
touching them):

- Spec: NPC stats "**always** quadruple the player ship's starting stats, plus or minus … 50%".
  `config_easy` ships `stat_multiple: 3.0, stat_variance: 0.4`; `config_hard` ships `5.0`.
  Only medium honours the word "always". Reasonable difficulty knob, but write it down.
- `turn_rate_deg_per_sec`: easy 120 / medium 180 / hard 140. Non-monotonic — **hard gives worse
  rotation than medium**, and easy takes 3.00 s for a full circle against the spec's "about 360
  degrees in 2 seconds". If that's deliberate ("easy = slow and tanky"), say so; if it's a
  typo, hard should be ≥ easy.

**Nits, sorted by how much they'll bite you:**

- Unused imports: `brake` (`src/model/ai.py:33` — imported, never called; the `brake` you see
  everywhere there is a *field name*), `ShipStats` (`src/model/game_state.py:29`), `Optional`
  (`src/model/weapons.py:22`), `Sequence` (`src/effects.py:27`).
- `main.py:34` and `src/main_loop.py:38`:
  `pygame.display.set_mode(SCREEN_SIZE, 0, pygame.SWSURFACE, 0, 0)` puts a **flag constant in
  the `depth` positional slot**. It works only because `pygame.SWSURFACE == 0` in pygame-ce
  2.5.8 — so `depth=0`, which is what you wanted anyway. If anyone ever "improves" that to
  `DOUBLEBUF`, you'll be requesting a 3-bit colour depth instead of double buffering. Write
  `pygame.display.set_mode(SCREEN_SIZE, vsync=1)` or at least use keywords.
- `TitleScene.on_exit()` (`src/scenes/title_screen.py:70-71`) calls `self._ui.clear_and_reset()`
  with no guard; `_ui` is only created in `on_enter`. Not reachable today, but
  `SceneManager.clear()`/`replace()` will happily `on_exit()` a scene that never entered.
- `loguru` is pinned in `requirements.txt` and never imported anywhere. `pytest` is in the same
  file as the runtime deps. Either use the logger you're shipping or drop it, and split dev
  deps out.
- `GameState._consume_fuel()` (`:858-862`) does a read-modify-write through the clamping
  property and *then* clamps again by hand. One of those clamps is redundant; pick one owner.
- README is 43 KB. The spec asked for "basic setup/run instructions … outline game controls and
  general usage". It's excellent reference material and also a maintenance liability — it
  currently instructs the reader to create the `audio_wav/` files the spec doesn't want.

---

## What I'd genuinely praise

- `JumpController.blocker()`'s ordering being documented as load-bearing, with the exact
  "parked inside landing range with 250 fuel must be told about the planet, not killed for the
  fuel" counter-example. That's how you write a rules engine.
- `endgame.py` — the four endings as pure predicates, the once-only guarantee correctly pushed
  into `EndOfRun`, `can_jump_the_price` deliberately matching the jump rules' strictness rather
  than inventing its own epsilon, and `escape_options()` making the anti-softlock argument
  *answerable*. Textbook.
- `assign_lore`'s with/without-replacement split matching the spec's "≥26 entries → no
  duplicates" rule exactly, plus the `(System)` tag substitution documented with the
  *swapped-argument* failure mode spelled out.
- `SceneManager.on_resume` existing at all — the phantom-key rising-edge trap it fixes is the
  kind of bug that eats a day.
- The Stage 6 review fixes reading like a post-mortem written by someone who *liked* being
  wrong: measuring `1765 of 2178 pixels had alpha == 0`, retracting their own earlier
  `.convert()` decision in writing, and recording the test-stride gotcha that made their own
  regression test lie.
- Three RNG layers (world / gameplay / namespaced per-entry) with a docstring explaining *why*
  they're namespaced — even if three of them currently aren't.

---

## Verdict

**🔧 Fix these and I'll sign off.**

Blocking, in order:

1. Jump immunity + fleet/round deletion (`game_scene.py:439`, `:464-465`) — direct violation of
   an emphatic spec rule, and locked in by a test.
2. The `if`→`while` accumulator (`main_loop.py:78`) — one keyword; DECISIONS has known about it
   for seven stages.
3. `grey_min`/`grey_max` (starfield `:65`) — dead config + ignored difficulty knob + a Stage 14
   "no hard-coding" gate failure.
4. `bottomleft` → `bottomright` in `effects.py:162` — two words, and the jump's money shot stops
   being cut off.
5. Delete `audio_wav/` + the `stage*.png` files from git, add a `.gitignore`, fix README `:759`.
6. Actually *do* Stage 14: a scripted playthrough test that reaches the victory screen, plus
   config-sweep tests for `top_speed`, `cargo_fare_per_unit`, `upgrade_cost_multiplier`; and
   write the Stage 14 entry in DECISIONS.md, because right now the log says you stopped at 13.

Everything else is polish. The bones are good — surprisingly good. You just stopped one sweep
short of done, and the parts you missed are the parts a reviewer notices first.

---

## Appendix: how the findings were verified

| Finding | Evidence |
|---|---|
| Jump immunity | Real `GameScene` via `tests/test_stage11.py` helpers; one 40-damage round 30 px off the bow. No jump → 60 damage absorbed, round survives. Jump → 0 damage, round count 0 on the first burn frame. |
| Shockwave reach | `Rect(0,0,1024,768)`, origin `(341,384)` (the game-view centre `GameScene` wires in). Code's corner list = `((0,0),(0,0),(0,768),(0,768))`; reach 513.6 px vs true 783.5 px. |
| Slow motion | 600 calls to `step_once([], dt)` at dt = 1/120, 1/60, 1/50, 1/30, 1/20 → step counts 300, 600, 600, 600, 600 (sim time always 10 s regardless of 5–30 s wall time). |
| RNG collision | Subclassed `random.Random` to log construction; one `GameScene` with `rng.seed = 12345` builds 5 instances, 3 of them seeded `12345` and emitting the identical sequence. |
| Dead config keys | Enumerated all 77 leaf keys of `config_medium.json`, word-boundary-grepped each against every file under `src/` excluding `src/config.py`. Only `tactical.stars.grey_min`/`grey_max` had zero hits. `Starfield(count=20000)` output range: 128..255. |
| Graph edge count | 400 seeds at `connections_min=1` → always 25 edges; at `= 2` (the shipped value) → 31–35 edges, degrees {2,3} only. |
| Exact fuel | Repeated `-0.2` from 1000.0: 3750 subtractions → 249.999999999904; equality with 250.0 never reached. |
| Config bounds | `ConfigRoot(**cfg)` with 5,000,000 stars / 100,000 offers / `fuel_capacity: -1` / `grey_min=250, grey_max=10` → all accepted. `jump.fuel_cost: -500` and `stat_multiple: 0.0` → rejected. |
| Soak | 60,000 frames of randomised input + 120 scripted jump requests: 0 exceptions, 0 non-finite positions, 0 out-of-system-without-jumping, 0 fuel over-capacity/negative. |
| Perf | 1200 `GameScene.update()`, 300 `SceneManager.draw()`, 900 `FixedTimestepLoop.step_once([])` on the dummy driver: 0.014 / 0.474 / 0.492 ms per frame. |
