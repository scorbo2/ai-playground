# Code Review: Match3-gemma.html vs Match3-qwen.html

Both files are implementations of the same "Match 3" game, each produced by a different LLM from the same prompt (`Match3.md`). They are evaluated on two axes: **code cleanliness & structure** and **adherence to the original prompt**.

---

## Match3-gemma.html (Gemma)

### Code Cleanliness & Structure: C+

| Observation | Detail |
|---|---|
| ✅ Class-based design | `class Match3` encapsulates state well |
| ✅ CSS custom properties | Variables for colors and borders improve maintainability |
| ❌ Dead method | `renderTokens()` is empty with a "bit inefficient" comment; `initTokens()` is used instead, meaning tokens can desync from board state |
| ❌ Triple-duplicate logic | `processMatches()` builds the same set of matched cells three separate times (`matchedCells`, `cellsToExplode`, `matchedSet`) |
| ❌ Misleading match objects | `findMatches()` always sets `r: 0` for horizontal matches and `c: 0` for vertical matches; real values are in `startC`/`startR` — works only by convention, not by design |
| ❌ No animation cancellation | `resetGame()` resets state but doesn't cancel pending `setTimeout`/`requestAnimationFrame` calls — orphaned timers can fire after reset and corrupt state |
| ❌ Fragile init order | `init()` and `initTokens()` are separate calls at startup and in `resetGame()`, with no guarantee of correct ordering |
| ❌ Overlay not over board | `#overlay-text` is a sibling of `#main-area`, not a child of the board container — positioning is relative to the wrong element |

---

### Adherence to Prompt: C+

| Feature | Status |
|---|---|
| Board 8×8, 60px cells, correct layout | ✅ |
| Title bar / sidebar layout | ✅ |
| No initial match-3 on board fill | ✅ |
| Select cell, highlight neighbors | ✅ |
| Swap animation, invalid flash (300ms) | ✅ |
| **Selected cell preserved after invalid move** | ✅ — selected state is not cleared on invalid swap |
| **Re-clicking selected cell should deselect** | ❌ — the `else` branch in `handleCellClick` re-selects the same cell instead of deselecting |
| Particle explosion (40 per matched cell) | ✅ (CSS-based) |
| Score formula (1pt/token + length−3 bonus) | ✅ |
| Red token penalty, negative score coloring | ✅ |
| Chain multiplier doubles (1→2→4→8…) | ✅ |
| Chain text escalation (VERY NICE!, AMAZING!!, HOLY COW!) | ❌ — only ever shows "NICE!" for any chain depth |
| MULTI-MATCH! and BONUS! text | ✅ |
| LEVEL COMPLETE / BEGIN LEVEL N text | ✅ |
| Game over on no valid moves | ✅ |
| **Reset button never blocked** | ⚠️ — button is always clickable, but no animation cancellation means orphaned timers can fire after reset |
| **Token colors are not pastel** | ❌ — pink uses `#ffc0cb`, which is CSS "pink" and is distinctly pastel |
| Floating text rises at ~40px/sec | ✅ (via CSS keyframe) |

---

## Match3-qwen.html (Qwen)

### Code Cleanliness & Structure: B+

| Observation | Detail |
|---|---|
| ✅ Clear section comments | `// CONSTANTS`, `// GAME STATE`, `// SWAP LOGIC`, etc. — the file is easy to navigate |
| ✅ `cancelAllAnimations()` | Tracks every `setTimeout` and `requestAnimationFrame` ID; reset is fully robust |
| ✅ Canvas-based particles | Uses a `<canvas>` with a per-frame loop — far more performant than 40 DOM nodes per matched cell |
| ✅ `normalizeTokenParentage()` | Defensive safety net to keep token DOM state consistent |
| ✅ `swapTokensInDOM()` | Cleanly separated from animation; correctly snaps positions using `transition: none` + forced reflow |
| ✅ `wouldCreateMatch()` | Checks all four directions (not just left/up), more robust for mid-board fill |
| ✅ `findContiguousGroups()` | BFS-based grouping for accurate multi-match and bonus scoring |
| ⚠️ Procedural style | Global state is acceptable for a single-file game, but all state is module-level globals with no encapsulation |
| ⚠️ `normalizeTokenParentage()` on every gravity pass | Conservative but adds minor overhead on each match resolution |

---

### Adherence to Prompt: B-

| Feature | Status |
|---|---|
| Board 8×8, 60px cells, correct layout | ✅ |
| Title bar / sidebar with dividers | ✅ (sidebar presentation is cleaner than Gemma's) |
| No initial match-3 on board fill | ✅ |
| Select/deselect, highlight neighbors | ✅ |
| **Re-clicking selected cell deselects it** | ✅ |
| Swap animation, invalid flash (300ms) | ✅ |
| **Selected cell preserved after invalid move** | ❌ — `attemptSwap` calls `deselectAll()` on invalid moves, violating the spec |
| Particle explosion via canvas | ✅ (with simulated gravity on particles — a nice touch) |
| Score formula (1pt/token + bonus) | ✅ |
| Red token penalty, negative score coloring | ✅ |
| Chain multiplier — exponential doubling | ❌ — uses linear `chainLevel` as multiplier (1→2→3→4…) instead of the exponential doubling (1→2→4→8…) specified |
| Chain text escalation (VERY NICE!, AMAZING!!, HOLY COW!) | ❌ — always shows only "NICE!" for any chain depth beyond 1 |
| MULTI-MATCH! and BONUS! text | ✅ |
| LEVEL COMPLETE / BEGIN LEVEL N text | ✅ |
| Game over on no valid moves | ✅ |
| **Reset button never blocked** | ✅ — `cancelAllAnimations()` makes this solid |
| **Token colors are not pastel** | ✅ — hot pink (`#FF00CC`) is vibrant, not pastel |
| Floating text rises using rAF | ✅ (smooth, ~40px/sec) |

---

## Summary

| Dimension | Gemma | Qwen |
|---|---|---|
| **Code Cleanliness & Structure** | C+ | B+ |
| **Prompt Adherence** | C+ | B- |
| **Overall** | C+ | B |

**Qwen** is the stronger implementation overall. Its code is better organized, animation state is properly managed (making reset robust at all times), particles use a canvas instead of flooding the DOM, and the selection/deselection logic is mostly sound. Its two main prompt failures are the invalid-move deselection bug (selected cell should remain selected per spec) and the missing chain text escalation.

**Gemma** has more numerous bugs — dead code, duplicate logic, confusing data structures, no animation cancellation on reset, a pastel token color, and a failure to deselect on re-click. The areas where Gemma does better than Qwen are correctly preserving selection state after an invalid move, and correctly implementing the exponential chain multiplier (1→2→4→8…).

**Shared failure across both implementations:** Neither escalates the chain feedback text beyond "NICE!" — both are missing "VERY NICE!", "AMAZING!!", and "HOLY COW!" for deeper chain levels.
