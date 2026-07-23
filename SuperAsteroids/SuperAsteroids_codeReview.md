# SuperAsteroids — Code Review

**Reviewer:** Ranger 1
**Date:** 2026-07-22
**File reviewed:** `SuperAsteroids-Qwen36-27B.py` (~2,950 lines)
**Specs reviewed:** `SuperAsteroids.txt`, `SuperAsteroids-implementationPlan.md`, `README.md`

---

## Overall Impression

Credit where it's due: this is a genuinely well-structured single-file game. The constant organization, class separation, docstrings, and method naming are all above what you'd typically expect from an AI-generated code dump. The spec-driven, staged development approach is solid and it shows — the code is coherent rather than the usual spaghetti-with-extras you get from one-shot LLM prompting.

That said, there are some real problems lurking in here. Some are spec deviations, some are performance gotchas, and a couple are genuine bugs that will bite you at runtime.

---

## Bugs & Edge Cases

### 1. Shield collision: index invalidation when popping from list mid-iteration

**Severity: HIGH — will cause incorrect behavior**

In `_check_shield_asteroid_collisions` (line 1809), you iterate over `enumerate(self.asteroids)` and call `_destroy_asteroid(asteroid, ai)` or `_hit_asteroid_from_shield(asteroid, ai)` — both of which do `self.asteroids.pop(asteroid_index)`.

After the first pop, all subsequent indices are off by one. The second asteroid hit will either destroy the wrong asteroid or skip one entirely.

The projectile collision handler (`_check_projectile_asteroid_collisions`) gets this right — it collects indices to remove, then removes them in a separate pass. The shield handler should do the same thing.

**Fix:** Collect asteroids-to-remove and new asteroids in sets/lists, then apply the mutations after the loop, exactly like `_check_projectile_asteroid_collisions` does.

### 2. Laser beam wrapping: doesn't handle diagonal wrapping (both X and Y simultaneously)

**Severity: MEDIUM — visual glitch on certain angles**

In `_draw_laser_beam` (line 1678), the wrapping logic uses:

```python
if wraps_x:
    # draw X-wrapped segments
if wraps_y:
    # draw Y-wrapped segments
```

These are two independent `if` blocks. If the beam wraps across both axes (diagonal), you end up drawing four segments from the same origin point instead of the correct two segments.

**Fix:** Use `if wraps_x: ... elif wraps_y: ...` — or better yet, implement a proper parametric line-clipping approach that handles all wrap cases uniformly.

### 3. Title screen says "Super Asteroids" instead of "SuperAsteroids"

**Severity: LOW — spec deviation**

Line 2807:

```python
title = title_font.render("Super Asteroids", True, COLOR_WHITE)
```

The spec explicitly says: *"The name of the game ("SuperAsteroids", one word)"*. It's a tiny thing, but if you're doing spec-driven development, you're not doing it if you can't spell the title right.

### 4. Star twinkle rate is 15-40× faster than the spec

**Severity: MEDIUM — spec deviation**

The spec says: *"star brightness changes at 0.1% per frame"*. The constants define:

```python
STAR_TWINKLE_RATE_MIN = 0.015  # 1.5%
STAR_TWINKLE_RATE_MAX = 0.04   # 4.0%
```

That's 15× to 40× faster than specified. At 0.1%, a star takes 2550 frames (~42 seconds) to go from black to white. At 4%, it takes 64 frames (~1 second). That's the difference between "subtle twinkle" and "disco strobe."

**Fix:** Use `0.001` for the twinkle rate (0.1% of 255 per frame). But then you'll hit the next problem...

### 5. Star brightness update truncates to int, making slow twinkles invisible

**Severity: HIGH — stars won't twinkle if you fix the rate**

In `Star.update()`:

```python
self.brightness += int(self.twinkle_rate * 255) * self.direction
```

If `twinkle_rate` is `0.001` (the correct spec value), then `int(0.001 * 255)` = `int(0.255)` = `0`. The stars don't twinkle at all.

**Fix:** Accumulate a floating-point delta and only apply it when it crosses a threshold, or use per-star fractional brightness that accumulates over frames.

### 6. Multiple collision checks don't account for screen wrapping

**Severity: HIGH — missed collisions on wide windows**

The following methods compute distance with raw `dx/dy` and `math.hypot`, with no wrap-aware correction:

- `_check_ship_asteroid_collision` (line 2496)
- `_check_shield_asteroid_collisions` (line 1809)
- `_check_projectile_asteroid_collisions` (line 2520)
- `_check_ship_powerup_collision` (line 2025)
- `_check_asteroid_powerup_collision` (line 2063)

The laser collision check *does* have wrap-aware distance logic (lines 1523-1527). The rest don't. On a wide window, a ship at x=10 and an asteroid at x=790 are 10 pixels apart (wrapping), but the code sees 780 pixels and misses the collision entirely.

**Fix:** Extract the wrap-aware distance calculation (which already exists in the laser code) into a utility method and use it everywhere.

### 7. `_handle_title_input` calls `pygame.quit()` + `sys.exit()` directly

**Severity: LOW — cleanup risk**

Line 1297: When pressing ESC on the title screen, the handler calls `pygame.quit()` and `sys.exit(0)` directly. Meanwhile, `Game.run()` also calls `pygame.quit()` on exit. If something changes the flow, you could get double-quit or skip cleanup.

**Fix:** Set `self.running = False` and let the main loop handle teardown.

### 8. `_spawn_thruster_particles` calls `pygame.key.get_pressed()` redundantly

**Severity: LOW — unnecessary overhead**

Line 2130: This method calls `pygame.key.get_pressed()` to check if the player is thrusting. But `_update_game` already calls `pygame.key.get_pressed()` and stores it in `keys`. Just pass `keys` as a parameter. Calling `get_pressed()` multiple times per frame is wasteful.

---

## Performance

### 1. `Particle.draw()` allocates a new Surface every frame per particle

**Impact: HIGH during heavy combat**

Lines 472-481:

```python
surf = pygame.Surface((size, size), pygame.SRCALPHA)
pygame.draw.circle(surf, alpha_color, ...)
screen.blit(surf, ...)
```

For a 40-pixel asteroid split, that's 120 particles. Each one allocates a surface every frame. That's 120 small allocations × 60 FPS = 7,200 allocations per second per explosion. The garbage collector is going to have a field day.

**Fix:** Pre-render particle surfaces at startup for each (radius, color) combination, or use a single offscreen surface and blit with alpha.

### 2. `Powerup.draw()` creates a new Font every frame

**Impact: LOW-MEDIUM — powerup is on screen most of the time**

Line 564:

```python
font = pygame.font.Font(None, 24)
```

Font creation is expensive. This fires every frame while a powerup is on screen.

**Fix:** Cache the font. You already have `self._fonts` — add a `"hud"` entry and reuse it.

### 3. `_draw_hud()` creates a new Font every frame

**Impact: LOW-MEDIUM — HUD is drawn every single frame**

Line 2253:

```python
font = pygame.font.Font(None, HUD_FONT_SIZE)
```

Same problem. The HUD is drawn every single frame.

**Fix:** Cache this font in `self._fonts`.

### 4. `_draw_level_text()` creates a new Surface copy every frame

**Impact: LOW — only active for 2 seconds per level**

Lines 2867-2872: Creates a copy of the rendered text and sets alpha on it, every frame during the 2-second fade. Minor, but easy to fix by pre-rendering and using `Surface.set_alpha()`.

---

## Security

Not much to say here — it's a local game with no network, no file I/O beyond sound loading, and no user input beyond keyboard. One note:

- **Sound loading failure is fatal** (line 1043): `sys.exit(1)` if any WAV file is missing. That's fine for a shipped product, but it means if you add a new sound effect name to `SFX_FILES` and forget the file, the entire game crashes at startup with no graceful degradation. Consider making missing sounds a warning, not a fatal error.

---

## Quality & Style

### 1. Duplicate asteroid hit logic in three places

**Severity: MEDIUM — maintenance burden**

`_hit_asteroid_from_laser`, `_hit_asteroid_from_shield`, and the inline code in `_check_asteroid_powerup_collision` all contain essentially the same split/destroy logic:

1. Check if radius < destruction threshold
2. If yes: increment hit count, spawn destruction explosion, play destroyed sound, pop asteroid
3. If no: spawn split explosion, play split sound, pop asteroid, spawn 2-3 children

This is the single biggest code smell in the file.

**Fix:** Extract a single `_apply_asteroid_hit(asteroid, index, destroy_instead_of_split=False, new_list=None)` method and call it from all three locations.

### 2. Unused UFO sound effects loaded at startup

**Severity: LOW — wasted memory / potential crash**

Lines 300-301:

```python
"ufo":                         "ufo.wav",
"ufo_destroyed":               "ufo_destroyed.wav",
```

These are in the README's "Future ideas" section. They're loaded into memory at startup, never played, and will crash the game if the files aren't present.

**Fix:** Either gate them behind a feature flag or remove them until the UFO feature is implemented.

### 3. `_destroy_asteroid` takes both an asteroid object and its index

**Severity: LOW — design smell**

```python
def _destroy_asteroid(self, asteroid, asteroid_index):
```

You pass both the object and its index. The method only uses the object for `x`, `y`, `radius`, and `hit_count` — the index is only used for `pop()`. This is a classic sign of the index invalidation problem.

**Fix:** Use the deferred-removal pattern (collect indices, remove after loop) consistently, or use `self.asteroids.remove(asteroid)` (O(n) but correct).

### 4. Things worth praising

- The constant organization at the top of the file is genuinely good. Tuning game balance is a matter of editing the top 350 lines.
- The `Ship.tip` property is a clean abstraction.
- The state machine mode transitions are clean and well-segmented.
- The `--test` flag is a smart addition for CI/iterative development.
- The asteroid shape generation (perturbed circle with random vertex angles) produces nice organic-looking rocks.
- The level text fade and ship hide-during-intro is a nice touch not in the original Asteroids.
- The docstrings are thorough and actually useful.
- The `force_wrap` method on asteroids is a correct solution to the resize problem.

---

## Summary of Required Fixes

| # | Issue | Severity | Effort |
|---|-------|----------|--------|
| 1 | Shield collision index invalidation | **HIGH** | Medium |
| 6 | Missing wrap-aware distance in collision checks | **HIGH** | Medium |
| 5 | Star twinkle int truncation | **HIGH** | Small |
| 2 | Laser beam diagonal wrapping | MEDIUM | Medium |
| 4 | Star twinkle rate wrong | MEDIUM | Small |
| 1 | Particle Surface allocation per frame | MEDIUM | Medium |
| 3 | Title screen spelling | LOW | Trivial |
| 7 | Direct sys.exit in title handler | LOW | Trivial |
| 8 | Redundant get_pressed() call | LOW | Trivial |
