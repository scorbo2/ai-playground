# Asteroids LLM Showdown: Code Review

## Overall Impressions

Three LLMs, one spec, wildly different results. One of them reads like it was written by a developer who's actually shipped a game, one reads like a solid undergraduate project, and one... well, let's get to that.

---

## 🏆 Ranking (Best to Worst Code Style)

### 1️⃣ **Qwen3-27B** — The Professional
### 2️⃣ **Gemma4-12B** — The Solid Workhorse
### 3️⃣ **Ornith-35B** — The One Who Didn't Read The Spec

---

## Detailed Breakdown

---

### 🥇 Qwen3-27B (622 lines) — Clean Architecture, Minor Issues

**What's good:**
- Proper `Game` class with a real **state machine** (`playing` / `gameover` / `levelclear`). This is how you actually structure a game.
- Separated `handle_event()`, `update()`, `draw()` — clean separation of concerns.
- Nice HUD with level, bullet count, and bonus status.
- Twinkling starfield with per-star phase and frequency — actually looks good.
- `FlameParticle` class for thrust effects, not just a static triangle.
- `math.hypot()` instead of manual `sqrt(dx**2 + dy**2)` — cleaner.
- Semi-transparent overlay on game over screens — nice polish.
- Docstring with controls at the top.
- No globals mutated at runtime.

**🐛 Bugs & Issues:**

- **Ship dimensions are wrong.** The spec says "20px wide, 30px tall." Qwen's wing base is at `-SHIP_HEIGHT/4 = -7.5` from center, and the nose is at `+SHIP_HEIGHT/2 = +15`. That gives a total length of **22.5px**, not 30. The width is correct at 20px. The ship is noticeably shorter than spec.

- **Minor inconsistency in collision radii.** Ship-asteroid uses `ast.radius + SHIP_WIDTH / 2` (which is `ast.radius + 10`), while friendly fire uses `SHIP_WIDTH / 2 + proj.radius` (which is `10 + 3 = 13`). Not a functional bug, but the collision radius for the ship should be consistent across all checks.

- **`draw()` calls `pygame.key.get_pressed()` again** (line 548-549) to check thrusting. This was already computed in `update()`. Redundant call — not a bug, just wasteful.

- **Asteroid rotation is applied but vertices are generated at `(0,0)`** (line 311: `make_asteroid_vertices(0, 0, radius)`). This is actually fine since the rotation math in `draw()` (lines 326-329) correctly rotates around the asteroid center. Just a subtle thing worth noting.

**Verdict on Qwen:** This is the one I'd merge. Clean architecture, good polish, and the bugs are cosmetic. The state machine pattern alone puts it ahead of the others.

---

### 🥈 Gemma4-12B (362 lines) — Simple, Correct, Boring

**What's good:**
- **Ship dimensions are exactly right.** Tip at +15, wings at center (0), back of wings at -15. Length = 30px, width = 20px. Matches spec perfectly.
- Correct asteroid split radius: `a.radius / 1.5`.
- Correct asteroid speed range: `random.uniform(1.5, 2.5)`.
- Clean, readable, flat structure. Easy to follow.
- Proper projectile velocity calculation (ship velocity + 6 in facing direction).
- Children only spawned if `new_radius >= MIN_ASTEROID_RADIUS` — avoids spawning doomed asteroids.

**🐛 Bugs & Issues:**

- **Debug `print()` left in the code** (line 254): `print(f"Hyper-fire: {hyper_fire}")`. This is the kind of thing that makes me question whether the LLM was roleplaying a developer who forgot to clean up before pushing. Ship it without the print.

- **Friendly fire uses a magic number `20`** (line 279): `if dist_to_ship < 20`. Should be derived from ship dimensions. It happens to work but it's the kind of thing that bit you at 2 AM.

- **No HUD.** No level display, no score, no indication of what state the game is in. The spec doesn't explicitly require a HUD, but it's a quality-of-life omission.

- **Flat function structure.** Everything lives in `main()` with nested `init_level()`. Works fine for a simple game, but doesn't scale. If you wanted to add a pause menu or a high score system, you'd be refactoring the whole thing.

- **`game_over_reason` is set but the game over message for asteroid collision says "GAME OVER" and for friendly fire says "FRIENDLY FIRE!"** — correct per spec.

- **The `init_level` nested function uses `nonlocal asteroids`** but not `nonlocal level_speed_mod` — works because `level_speed_mod` is only read, not written in `init_level`. Technically correct but could confuse a reader.

**Verdict on Gemma:** This is the "it works and I can read it at 3 AM" implementation. No fancy architecture, no polish, but it's correct. Like a well-commented C program from 1997.

---

### 🥉 Ornith-35B (571 lines) — The Bug Magnet

**What's good:**
- Has a `Game` class with nice separation of concerns.
- Docstring with controls.
- `Starfield` as a proper class with brightness variation.
- `Particle` system with multiple colors, size variation, and alpha fade.
- Asteroids have rotation animation.
- `random_spawn_away_from()` has a fallback to corners if it can't find a safe spot.

**🐛 Bugs & Issues:**

- **🚨 ASTEROID SPLIT RADIUS IS WRONG.** Line 416: `new_radius = asteroid.radius / ASTEROID_SPLIT_COUNT`. `ASTEROID_SPLIT_COUNT` is `2` (line 48). The spec says radius = `parent / 1.5`. This means child asteroids are radius 20 instead of 26.67, and the chain terminates one level earlier than it should. **This is a real gameplay bug.** Looks like someone confused "split count" with "split factor."

- **🚨 SHIP DIMENSIONS ARE WRONG.** `SHIP_WIDTH = 10` and `SHIP_HEIGHT = 35` (lines 30-31). The spec says 20px wide, 30px tall. The ship is half as wide and 5px too tall. The nose is at `SHIP_HEIGHT / 2 = 17.5` from center, giving a total length of 35px instead of 30.

- **🚨 ASTEROID SPEED RANGE IS WRONG.** Line 71: `random.uniform(base_speed * 0.6, base_speed * 1.4)` with `base_speed = 2.0`. This produces speeds in range [1.2, 2.8], not the spec's [1.5, 2.5]. Asteroids can spawn noticeably faster or slower than intended.

- **PARTICLES ARE UPDATED TWICE PER FRAME.** Lines 487-489:
  ```python
  self.particles = [p for p in self.particles if not p.is_dead()]  # filters
  for p in self.particles:
      p.update()  # updates
  ```
  But `is_dead()` checks `self.life <= 0`, and `update()` does `self.life -= 1`. The filter runs *before* update, so particles that would die this frame survive an extra frame. Wait — actually, re-reading this: the filter removes dead particles, then the remaining particles are updated. That's correct order. But there's no bug here — my initial read was wrong. Let me re-examine...

  Actually, the real issue is subtler: `is_dead()` is called on the *old* state, then `update()` is called. This is fine. **No bug here.** My bad.

- **Ship-asteroid collision doesn't account for ship radius.** Line 434: `asteroid.contains_point(ship_center[0], ship_center[1])` checks if the ship's center is within the asteroid's radius. But the ship has a width of 10 (per its own constants), so the collision radius should be `asteroid.radius + ship_radius`. This makes it harder to die than the spec intends — the ship effectively has zero collision radius.

- **`NO_FRIENDLY_FIRE` is a module-level global** (line 61) mutated with `global` in the event handler (line 555). This is a design anti-pattern. It should be an instance variable on `Game`. Bonus state persists across `reset_game()` calls... actually, it doesn't, since `reset_game()` doesn't reset it. The bonus toggle state carries over between games, which could be confusing.

- **`friendly_fire` is a Game instance variable** (line 376) that shadows/conflicts with the module-level `NO_FRIENDLY_FIRE`. The naming is confusing — `self.friendly_fire` tracks whether the current game over was caused by friendly fire, while `NO_FRIENDLY_FIRE` is the bonus toggle. Two different concepts with overlapping names.

- **Level transition timing is off.** Line 498: `self.level += 1` happens *before* the transition timer starts. So the "Level 2 Starting..." text displays correctly, but the level counter is already incremented during the 2-second wait. This means if the player looks at the HUD during the transition, it already shows the new level number. Minor, but the Gemma and Qwen implementations handle this more cleanly.

**Verdict on Ornith:** This one has the most bugs of the three, including a spec violation in the asteroid split math that affects core gameplay. The code structure is decent, but the substance is wrong. It's the LLM equivalent of a developer who writes great class hierarchies but can't get the math right.

---

## Summary Table

| Criteria | Qwen3-27B | Gemma4-12B | Ornith-35B |
|---|---|---|---|
| Ship dimensions (20×30) | ❌ 20×22.5 | ✅ 20×30 | ❌ 10×35 |
| Asteroid split (÷1.5) | ✅ | ✅ | ❌ ÷2 |
| Asteroid speed (1.5-2.5) | ✅ | ✅ | ❌ 1.2-2.8 |
| Max projectiles (3) | ✅ | ✅ | ✅ |
| Projectile lifetime (1000px) | ✅ | ✅ | ✅ |
| Friendly fire | ✅ | ✅ | ✅ |
| Ship-asteroid collision radius | ⚠️ consistent | ⚠️ magic # | ❌ no ship radius |
| Bonus feature toggle | ✅ | ✅ | ✅ (global anti-pattern) |
| Code architecture | ✅ state machine | ⚠️ flat function | ✅ class-based |
| Polish / HUD | ✅✅ | ❌ none | ✅ |
| Debug code left in | ✅ clean | ❌ print() | ✅ clean |
| Particle system | ✅✅ (twinkle + flame) | ✅ basic | ✅ good |

---

## Final Verdict

**Qwen3-27B wins.** Despite the ship being slightly shorter than spec, it's the most professionally structured piece of code. The state machine, the HUD, the twinkling starfield, the flame particles — this one feels like it was written by someone who cares about the player's experience. Fix the ship dimensions and it's golden.

**Gemma4-12B** is the safe choice. It's correct, readable, and gets the physics right. It's just... plain. Delete the debug print and it's production-ready.

**Ornith-35B** needs a full rewrite of its math. Three spec violations in core game mechanics (split radius, ship size, speed range) and a collision detection bug. The class structure is nice, but what good is a beautiful class hierarchy when the asteroids don't split correctly?

**🔧 Fix these and I'll sign off** — for Qwen (ship dimensions) and Gemma (delete the print). Ornith needs more than a patch.

---

(Generated by Qwen 3.6 27B - no conflict of interest here, lol)
