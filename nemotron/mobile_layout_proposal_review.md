# Review: Mobile Layout Proposals (issue #143)

**Reviewed:** `mobile_layout_nemotron_bolt.md` vs `mobile_layout_qwen_flash.md`
**Date:** 2026-10-19
**Verdict:** Adopt `mobile_layout_qwen_flash.md` as the master plan, with two
amendments folded in from the nemotron proposal (see "Salvage items"). Archive
the nemotron document with a pointer to the merged plan so its broken CSS is
never implemented by mistake.

Both proposals were fact-checked against the actual codebase before judging
them. A proposal that cites line numbers is only as good as those line numbers.

---

## Fact-check results

| Claim | Source | Reality | Status |
|-------|--------|---------|--------|
| `--sidebar-width: 310px` at `style.css` L29 | qwen_flash | Confirmed (L29) | ✅ |
| `height: calc(100vh - var(--topbar-height))` at L193 | qwen_flash | Confirmed (L193) | ✅ |
| Modal caps `680px` / `90vh` / `65vh` / `45vh` | qwen_flash | Confirmed (L753, L754/851/958, L1141, L864) | ✅ |
| `.hidden` specificity comment at L93–102 | qwen_flash | Confirmed — the `!important` comment is there verbatim | ✅ |
| Exactly one `@media` query: `(hover: none)` at L1746 | qwen_flash | Confirmed (L1746) | ✅ |
| 1,751-line `style.css`, 474-line `index.html` | qwen_flash | Confirmed | ✅ |
| Viewport meta already present (`index.html` L5) | qwen_flash | Confirmed | ✅ |
| Manifest ships `"theme_color": "#ffffff"` while default theme is dark | qwen_flash | Confirmed — `--bg-primary: #1a1a2e`; Android shows a white splash flash today | ✅ |
| "No `@media` queries exist in `style.css`" | nemotron §2 | **False** — one exists at L1746 | ❌ |

One fabricated fact in a two-page survey of a 1,751-line stylesheet is a red
flag, and it happens to be the exact fact the other proposal builds on.

---

## Why `mobile_layout_qwen_flash.md` wins

1. **Its facts check out.** Every line-number citation verified on the spot
   (table above). The nemotron proposal contains at least one factual error
   about the stylesheet it proposes to modify.

2. **It solves the problems that actually kill mobile chat apps.** The
   on-screen-keyboard / `100vh` burial, `dvh` with a `vh` fallback,
   `interactive-widget=resizes-content`, safe-area insets, and the PWA
   manifest color bug are all absent from the nemotron proposal. A mobile chat
   UI where the keyboard eats the input bar is a paperweight no matter how
   tidy the media queries are. qwen_flash also catches the
   `getUserMedia`-over-plain-HTTP gotcha, directly relevant to the reporter's
   "tailscaled spark" use case.

3. **It respects this repo's testing culture.** AGENTS.md is emphatic: new
   functionality requires new tests; frontend tests are plain Node with the
   `vm.Context` harness; the coverage map gets updated. qwen_flash specifies
   `tests/test_mobile_drawer.js`, CSS poison guards (no `100vh` inside any
   `@media` block; exactly one breakpoint block), and the AGENTS.md updates.
   nemotron's entire test story is "all existing tests continue to pass" —
   non-compliant for a change that adds new interactive behavior.

4. **nemotron has internal contradictions and CSS that wouldn't behave as
   advertised:**
   - Promises a three-tier breakpoint table (mobile / tablet / desktop), then
     its own CSS implements only two. The tablet tier is vaporware.
   - `display: none` → `display: flex` with a `transform` transition does not
     animate. The drawer would pop, not slide.
   - The `@media (min-width: 768px)` block re-asserts values the base rules
     already set — a second source of truth begging to drift.
   - The risk table claims the sidebar's z-index of 20 is *higher* than the
     modals' 100, then corrects itself mid-row.
   - The top-bar plan contradicts itself in a single paragraph ("hide the
     secondary ones… Actually, a simpler approach…").

5. **Engineering hygiene.** qwen_flash has an alternatives-considered section
   with rejection rationale, an edge-case table, effort estimates, and an
   honest disclosure that the author never saw the reporter's mockup.
   nemotron has none of that.

---

## Salvage items from `mobile_layout_nemotron_bolt.md`

Only two things in nemotron are worth folding into the merged plan:

1. **Accessibility / focus management** (nemotron design goal #7). qwen_flash's
   drawer handles Escape and scrim-clicks but says nothing about focus.
   Required amendments:
   - Move focus into the drawer on open; return focus to the hamburger on close.
   - `aria-expanded` / `aria-controls` on the hamburger toggle.
   - `inert` (or `aria-hidden`) on the closed drawer so tab order never wanders
     into an off-screen panel.

2. **Full-width stacked `.form-actions` buttons on mobile** (nemotron §5.2.3).
   qwen_flash restacks form rows but leaves the Save/Cancel row unspecified.
   Stacked full-width buttons are the right touch call.

## Explicitly NOT merged

- **Three-tier breakpoints** — qwen_flash's single `max-width: 768px`
  breakpoint is simpler and actually implemented; nemotron's tablet tier has
  no CSS behind it. qwen_flash rejects tablet-specific design explicitly,
  with rationale.
- **Primary/secondary topbar split** — qwen_flash's icon-only topbar (hide
  `.btn-label` spans) beats inventing an overflow-menu component with its own
  focus-trap and click-outside bug class.
- **Mobile CSS custom properties** — marginal benefit; qwen_flash's literal
  values inside the single media block are adequate.

---

## Recommendation

Adopt `mobile_layout_qwen_flash.md` as the master plan, phases 1–4 as scoped,
plus the two amendments above. Archive `mobile_layout_nemotron_bolt.md` with a
note pointing at the merged document.

### Improvement suggestion for the merged plan

The breakpoint number `768` will exist in three places: the CSS media query,
the `matchMedia` string in `drawer.js`, and the poison-guard test. Pin it
once: have the Node test assert that the `matchMedia` string and the CSS query
contain the identical `max-width: 768px` literal, so the two sources of truth
can never drift apart silently — the exact "two drifting breakpoints" bug
class the proposal already worries about.
