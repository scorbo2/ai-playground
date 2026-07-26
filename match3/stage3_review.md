# Code Review: Magical Token Feature

**Feature spec**: `NewFeature.md`  
**Implementations reviewed**: `Match3-gemma.py` (Gemma) and `Match3-qwen.py` (Qwen)

---

## Verdict: Match3-gemma.py is the better implementation

Gemma's code is cleaner, better structured, and has fewer architectural problems. Qwen's implementation has a fundamentally broken design that undermines an otherwise reasonable attempt at the feature.

---

## Architecture

### Gemma — Clean state machine ✅

Gemma uses a single `Match3Game` class driven by an explicit state machine with well-named states (`STATE_IDLE`, `STATE_SWAP_ANIM`, `STATE_MATCH`, `STATE_REMOVE_ANIM`, `STATE_GRAVITY_ANIM`, etc.). Each state transition is handled by a dedicated `_update_*` method. There is no code duplication, no hacks, and the main loop is simple and readable.

### Qwen — Broken async class with duplicate sequential subclass ❌

Qwen defines a `Game` class using `async`/`await` with `asyncio.sleep()` for delays, then acknowledges this is broken in a comment (`# loop.stop() - This is tricky in a game loop`) and creates a `GameSequential(Game)` subclass that reimplements virtually every core method (`attempt_swap_seq`, `process_matches_seq`, `apply_gravity_seq`, `fill_empty_seq`, `show_level_complete_seq`, `advance_level_seq`). The parent `Game` class's `run()` method is non-functional. This means nearly all game logic is written twice, and the two copies have diverging bugs.

---

## Token State Management

### Gemma — Single source of truth ✅

All token data lives in the `Token` object: `color`, `magical_type`, position, opacity, animation state. The `board` 2D array holds `Token` objects or `None`. One array, complete information.

### Qwen — Three parallel arrays, sync risks ❌

Qwen maintains three separate 2D arrays that must always be kept in sync: `self.board` (color index), `self.tokens` (Token objects, which also have `magical_type`), and `self.magical_board` (magical type string, redundantly). This is error-prone and results in a real bug: the parent class's `Game.attempt_swap()` swaps `board` and `tokens` but not `magical_board`. The subclass `GameSequential.attempt_swap_seq()` fixes this, but the parent class remains broken — illustrating exactly the maintenance risk of this pattern.

---

## Magical Token Spawning

Both implementations correctly implement the spawn mechanic:
- 0.5% base chance per token spawn
- Chance increases by 0.5% per successful match
- Resets to 0.5% after a magical token spawns or at level completion

**Gemma** encapsulates this in `_determine_token_type()`. Clean.

**Qwen** encapsulates it in `_roll_magical_spawn()`. Also clean, and adds a defensible cap of `min(..., 1.0)` on the spawn chance. One edge case: new tokens spawned in `fill_empty_seq` call `_roll_magical_spawn()` and correctly update both `Token.magical_type` and `self.magical_board[r][c]`. However, the `fill_empty()` method in the parent `Game` class does **not** assign a magical type at all (`Token(r, c, color)` with no `magical_type`), which is another divergence bug.

---

## Magical Token Rendering

Both correctly draw an 8px horizontal or vertical white stripe centered on the token circle. Gemma uses inline coordinates; Qwen defines `MAGICAL_STRIPE_WIDTH = 8` as a named constant, which is the better practice. Both correctly propagate the token's `opacity` to the stripe for a clean fade-out animation.

---

## Magical Clearing and Chaining

### Gemma — BFS queue approach ✅ (with caveats)

`_process_magical_clears()` uses a queue (BFS) to expand the set of cells to clear. Starting from the initially matched cells, it finds any magical tokens, adds their entire row or column to `cells_to_clear`, then looks for *more* magical tokens in those newly added cells and queues them too. A `processed_magical` set prevents infinite loops.

**Caveat**: Gemma's chaining does not differentiate by magical type — it chains any magical token found in a cleared row or column, including same-type ones. Per the spec, only *opposite* types should chain (horizontal magical triggers vertical magicals in the same row, and vice versa). This results in slightly over-eager chaining (e.g., two horizontal magicals in the same row would each "clear" the same row again, which is harmless but not per spec).

### Qwen — Correct opposite-type chaining ✅

`process_magical_chain()` correctly implements the spec's chaining rule: `clear_row()` returns only *vertical* magicals found in the row, and `clear_column()` returns only *horizontal* magicals found in the column. These are then processed in the next batch, creating a proper alternating chain. This is more faithful to the spec than Gemma's approach.

---

## "MAGICAL POWER!" Text

### Spec requirement
> *"MAGICAL POWER!" should appear briefly on the screen in large semi-transparent dark red font*

### Gemma — Correct color, wrong transparency ⚠️

Gemma creates a `FloatingText("MAGICAL POWER!", (139, 0, 0), ...)` which renders the text at **full opacity** and then fades it out. It is never semi-transparent at the moment it first appears — it starts opaque. The color is correct (dark red: `#8b0000`).

### Qwen — Correct color and correct semi-transparency ✅

Qwen calls `self.show_overlay_text("MAGICAL POWER!", (139, 0, 0), 2.0, alpha=180)` and the draw code applies `opacity = int((1 - progress) * o.alpha)`, so at `progress=0` (initial display), opacity is 180 out of 255 — genuinely semi-transparent. This matches the spec more accurately.

---

## Magical Scoring

Both implementations score magical clears as `+1` per non-red token and `-1` per red token in the cleared row/column, as specified.

**Shared issue (both implementations)**: The original matched cells that triggered the magical effect are scored once by the regular match scoring, and then scored again when the row/column is swept. The spec says "in addition to the usual scoring rules" and "for each token in the row or column" without explicitly excluding the matched cells, so this may be intentional. Neither implementation stands out here.

---

## Gravity and Refill

Gemma's `_apply_gravity()` compacts survivors to the bottom of each column and creates new tokens starting above the visible board, correctly calling `_determine_token_type()` for each new token. Logic is clean and readable.

Qwen's `apply_gravity_seq()` does the same, and also keeps `self.magical_board` in sync. The `fill_empty_seq()` also correctly assigns magical types and keeps all three arrays in sync. However, the equivalent methods in the parent `Game` class are inconsistent (magical_board not updated).

---

## Summary Table

| Criterion | Gemma | Qwen |
|---|---|---|
| Architecture | ✅ Clean state machine | ❌ Broken async + duplicated sequential subclass |
| Token state management | ✅ Single source of truth | ❌ Three parallel arrays, sync bugs |
| Magical spawning | ✅ Correct | ✅ Correct (+ caps at 100%) |
| Stripe rendering | ✅ Correct | ✅ Correct (+ named constant) |
| Magical row/col clearing | ✅ Correct | ✅ Correct |
| Chaining (spec fidelity) | ⚠️ Chains same-type too | ✅ Opposite-type only (per spec) |
| "MAGICAL POWER!" color | ✅ Dark red | ✅ Dark red |
| "MAGICAL POWER!" transparency | ❌ Starts opaque | ✅ Semi-transparent (alpha=180) |
| Code duplication | ✅ None | ❌ Extensive |
| Documentation/comments | ✅ Thorough | ⚠️ Partial |

**Gemma wins** on architecture, maintainability, and correctness of overall design. Qwen has two specific spec-compliance wins (semi-transparent text, opposite-type chaining) but these are minor compared to the structural problems: the broken async parent class, the three-array synchronization approach, and the massive code duplication between `Game` and `GameSequential`.
