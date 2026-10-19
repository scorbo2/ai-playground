# Proposal: Mobile-Friendly Layout (issue #143)

**Status:** proposal for review — no code written yet.
**Scope:** frontend only (`templates/index.html`, `static/style.css`, a small amount of JS). **Zero backend changes.**

> **Author's note on the mockup:** the reporter attached a portrait screenshot to
> issue #143 ("an example I whipped up as a demo… I use this on my tailscaled
> spark"). This proposal was authored in a terminal that cannot render images,
> so the mockup itself was not inspected. The design below is derived from the
> issue text and a full survey of the current frontend; the reporter's mockup
> should be treated as the *visual acceptance target* during implementation.

---

## 1. Current state

The app is a single-page vanilla-JS app (`templates/index.html` + `static/*.js`
+ one 1,751-line `static/style.css`). The layout is hard-wired for desktop:

| What | Where | Why it breaks on a phone |
|------|-------|--------------------------|
| `#main-layout` is a fixed flex row: a 310px sidebar (`--sidebar-width`, line 29) plus the chat panel | `style.css` L191–209 | On a 390px-wide phone the chat column gets ~80px. Unusable. |
| `#main-layout { height: calc(100vh - var(--topbar-height)) }`, `html, body { overflow: hidden }` | `style.css` L85–91, L193 | `100vh` ignores the on-screen keyboard and browser chrome: when the keyboard opens, the input bar is pushed off-screen or buried. |
| Top bar with 7 labeled buttons + theme select (≈600px of controls) | `index.html` L17–40 | Overflows a phone viewport; buttons wrap or clip. |
| Modals: `max-width: 680px`, `max-height: 90vh`, `.settings-body { max-height: 65vh }`, `.pe-list { max-height: 45vh }` | `style.css` L748–762, L864, L1141 | Fixed `vh` caps + 20px overlay padding waste vertical space and fight the keyboard. |
| Touch targets: 40px send/mic buttons, ~24px delete "×" buttons, hover-revealed controls | `style.css` L644–687, L1696+ | Below the 44px minimum; hover-only affordances are invisible on touch. |
| `@media` queries: exactly **one** — `(hover: none)` for the message-delete button | `style.css` L1746 | The only concession to touch devices in the entire stylesheet. |

The good news, sir: the groundwork is already in place.

- `<meta name="viewport" content="width=device-width, initial-scale=1.0">` exists (`index.html` L5).
- The entire UI is driven by **ID selectors and shared globals** — no JS measures or positions layout elements (no `offsetWidth`, no inline geometry). A pure-CSS reflow is therefore safe.
- A PWA manifest and icons already ship (`static/site.webmanifest`), so "Add to Home Screen" already works — it just looks like a shrunken desktop.
- The sidebar's contents (room dropdown, echo toggle, who-chooser, persona cards) are already full-width vertical stacks — they survive a drawer reflow unchanged.

## 2. Goals / non-goals

**Goals**

1. A phone in portrait (≥ 320px wide) shows a full-width, readable, tappable chat: messages, input bar, mic, send, stop, TTS toggle.
2. Every sidebar control (room, echo chamber, who-answers, persona list) remains reachable.
3. Every modal (persona editor, chat rooms, picker, servers, general settings) is usable full-screen.
4. The keyboard never buries the input bar.
5. Desktop rendering is **pixel-identical** to today.

**Non-goals**

- No new framework, no bundler, no separate mobile template/SPA. This stays vanilla CSS + a pinch of JS.
- No backend, API, or model changes — `GET /api/*` payloads already fit any screen.
- No landscape/tablet-specific redesign beyond what the single breakpoint gives for free (a 1024px iPad keeps the desktop layout, which is fine).
- No offline/PWA expansion beyond fixing the existing manifest.

## 3. Proposed design

### 3.1 The one structural change: sidebar → off-canvas drawer

Below a single breakpoint (**≤ 768px**), the sidebar stops being a column and
becomes a slide-in drawer over the chat. This matches the reporter's portrait
mockup (a full-width chat column) and is the only sane pattern for a 310px
sidebar on a 390px screen.

```
 desktop (> 768px)                mobile (≤ 768px)
┌──────────────────────────┐     ┌────────────────────┐
│ topbar (full controls)   │     │ ☰ TalkWithMe ⏹ 🔊 │
├────────┬─────────────────┤     ├────────────────────┤
│ side-  │                 │     │                    │
│ bar    │  chat panel     │     │   chat panel       │  ← full width
│ 310px  │  (flex: 1)      │     │   (100%)           │
│        │                 │     │                    │
├────────┴─────────────────┤     ├────────────────────┤
│ input bar                │     │ input bar          │
└──────────────────────────┘     └────────────────────┘

            drawer open (mobile only)
        ┌──────────────┬░░░░░░░░░░░┐
        │  sidebar     │  scrim    │   ← sidebar slides in,
        │  (drawer)    │  over chat│      chat stays put underneath
        └──────────────┴░░░░░░░░░░░┘
```

**CSS** (appended to `style.css`; the drawer reuses the existing `#sidebar`
markup — no DOM move, no JS re-render):

```css
/* ---- Mobile layout (issue #143): one breakpoint, one drawer ---- */
@media (max-width: 768px) {
    #btn-drawer-toggle { display: inline-flex; }   /* hamburger, hidden on desktop */

    #main-layout { height: calc(100dvh - var(--topbar-height)); }

    #sidebar {
        position: fixed;
        top: var(--topbar-height);
        bottom: 0;
        left: 0;
        z-index: 40;
        width: min(85vw, 340px);
        min-width: 0;
        transform: translateX(-100%);
        transition: transform 0.2s ease;
        box-shadow: 4px 0 24px rgba(0, 0, 0, 0.4);
    }
    body.drawer-open #sidebar { transform: translateX(0); }

    #drawer-scrim { display: none; }
    body.drawer-open #drawer-scrim {
        display: block;
        position: fixed;
        inset: var(--topbar-height) 0 0 0;
        background: rgba(0, 0, 0, 0.5);
        z-index: 39;
    }
}
```

**JS** — a new `static/drawer.js` (~40 lines, loaded before `chat.js`/`persona.js`/`chatrooms.js` so their hooks can call it):

```js
// static/drawer.js — off-canvas sidebar for narrow screens (issue #143).
// The open/closed state lives in ONE place: the `drawer-open` class on <body>.
// No inline styles, no matchMedia listeners — CSS owns the presentation,
// this module only flips the class.

function isCompactViewport() {
    return window.matchMedia("(max-width: 768px)").matches;
}

function toggleDrawer(open) {
    document.body.classList.toggle("drawer-open", !!open);
}

// Auto-close is MOBILE-ONLY on purpose: on desktop the sidebar is not a
// drawer at all, so "closing" it would be a regression, not a convenience.
function closeDrawerIfCompact() {
    if (isCompactViewport()) toggleDrawer(false);
}
```

Wiring (all additive, one line each):

- `app.js::setupEventListeners()` — hamburger click toggles the drawer; scrim click and `Escape` close it.
- `persona.js::renderPersonaList()` card click handler — append `closeDrawerIfCompact()` after the existing who-chooser switch (the user just picked a responder; the drawer has done its job).
- `chatrooms.js` room-dropdown `change` handler — same.
- The existing `document` keydown handler in `app.js` gains an `Escape` branch.

**Why not auto-close on desktop too?** Because the sidebar is the only copy of
those controls there; hiding it would strand the user. The `isCompactViewport()`
guard is the invariant the Node test locks in (see §5).

### 3.2 Top bar: icon-only, not a hamburger menu

The top bar keeps every button it has today — labels are simply hidden below
the breakpoint. This avoids inventing a dropdown-menu component (new focus
management, new click-outside logic, new test surface) for zero user gain.

Markup change in `index.html`: wrap each topbar button's text in a span so CSS
can hide it without touching JS (all buttons are wired by ID, so their inner
markup is free):

```html
<button id="btn-persona-editor" title="Open persona editor">&#9998; <span class="btn-label">Personas</span></button>
```

```css
#btn-drawer-toggle { display: none; }        /* desktop: no hamburger */
@media (max-width: 768px) {
    #topbar { padding: 0 10px; }
    .topbar-actions { gap: 6px; }
    .topbar-actions .btn-label { display: none; }
    .topbar-actions button { padding: 8px 10px; min-width: 40px; }
    #topbar h1 { font-size: 1rem; }
}
```

The theme select stays (it's compact and already styled); the stop and TTS
buttons are already icon-only.

### 3.3 Viewport height: kill the `100vh` bug class before it bites

The iOS/Android keyboard is the classic mobile chat killer. Fixes:

1. `#main-layout` and the modal caps switch to `dvh` with a `vh` fallback
   (one extra declaration; browsers that don't know `dvh` keep the old value):

   ```css
   #main-layout {
       height: calc(100vh - var(--topbar-height)); /* fallback */
       height: calc(100dvh - var(--topbar-height));
   }
   ```

2. Extend the existing viewport meta so Chrome/Android resizes the *layout*
   viewport under the keyboard, and notched devices get safe-area data:

   ```html
   <meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover, interactive-widget=resizes-content">
   ```

3. Safe-area padding for home-induction/notches (harmless where there is none):

   ```css
   #topbar    { padding-top: env(safe-area-inset-top); }
   #input-bar { padding-bottom: calc(14px + env(safe-area-inset-bottom)); }
   ```

### 3.4 Modals: full-bleed sheets

Below the breakpoint, modals become full-screen sheets — no overlay padding,
no border radius, and the scrollable regions flex instead of using fixed `vh`
caps:

```css
@media (max-width: 768px) {
    .modal-overlay { padding: 0; }
    .modal-box, .modal-box-sm {
        max-width: 100%;
        height: 100dvh;
        max-height: 100dvh;
        border-radius: 0;
        border-left: none;
        border-right: none;
    }
    /* Replace the fixed vh caps with flex fill, so the form/list scrolls
       within the sheet instead of leaving dead space under the keyboard. */
    .settings-body { max-height: none; flex: 1; min-height: 0; }
    .pe-list       { max-height: none; }
    #pe-form-view  { overflow-y: auto; flex: 1; min-height: 0; }
    .form-row-inline { flex-direction: column; gap: 12px; }
}
```

⚠️ **Gotcha (documented at `style.css` L93–102):** `.hidden` uses
`display: none !important` *because* ID rules like `#pe-list-view` out-specify
class rules. Any new mobile rule targeting those ID'd containers must not
accidentally out-specify `.hidden` — set `display` only on non-hidden states,
or match the specificity deliberately. The Node test suite's DOM stub already
guards the `.hidden` behavior for the persona form; the new drawer test
(§5) covers the rest.

### 3.5 Touch ergonomics

- Send/mic buttons: 40px → **44px** on mobile.
- Persona-card remove "×" and message-delete buttons: enlarge the hit area
  (padding) without enlarging the glyph.
- The existing `@media (hover: none)` rule (L1746) already keeps delete buttons
  visible on touch — keep it, and add `:active` feedback where hover styling
  currently does all the work (`.persona-card`, `.chooser-option`).
- Chat bubbles: `max-width: 80%` → `88%` on mobile (more text per line on a
  narrow screen); assistant avatar 64px → 48px to reclaim width.

### 3.6 PWA manifest polish (one line, free win)

`static/site.webmanifest` currently declares `"theme_color": "#ffffff"` while
the default theme is dark — Android shows a white app bar and a white splash
flash. Fix:

```json
"theme_color": "#1a1a2e", "background_color": "#1a1a2e"
```

(`display: "standalone"` and the icons are already correct.)

## 4. Files touched

| File | Change |
|------|--------|
| `templates/index.html` | viewport meta (1 line); hamburger button + scrim div (2 lines); `<span class="btn-label">` wraps in topbar buttons |
| `static/style.css` | one `@media (max-width: 768px)` block (~80 lines) + `dvh` fallbacks on 3 existing rules |
| `static/drawer.js` | **new**, ~40 lines |
| `static/app.js` | hamburger/scrim/Escape wiring in `setupEventListeners()` (~6 lines) |
| `static/persona.js` | `closeDrawerIfCompact()` in the card click handler (1 line) |
| `static/chatrooms.js` | `closeDrawerIfCompact()` in the room-dropdown change handler (1 line) |
| `static/site.webmanifest` | theme/background color fix |
| `tests/test_mobile_drawer.js` | **new** Node test (see §5) |
| `AGENTS.md` | frontend-module table row for `drawer.js`; coverage-map entry for the new test |

No changes to: any `app/` Python, any router, any model, `tests/factories.py`,
the pytest suite, or the API endpoints table (the `test_docs.py` invariant is
untouched — no endpoints added or removed).

## 5. Testing plan

Per the repo's testing rules, this is frontend work → **plain Node, kept out
of pytest** (pytest must stay runnable with nothing but Python installed):

**`tests/test_mobile_drawer.js`** — same harness as `test_persona_form.js`
(fresh `vm.Context` per test, minimal DOM stub, no fetch): loads the real
`static/utils.js` + `state.js` + `drawer.js` + `persona.js` + `chatrooms.js`
and locks in:

1. `toggleDrawer(true)` / `(false)` flips exactly the `drawer-open` class on
   `<body>` and touches nothing else.
2. `closeDrawerIfCompact()` with `matchMedia` matching (mobile) removes the
   class; with `matchMedia` **not** matching (desktop) it is a no-op — the
   desktop-never-closes invariant.
3. Driving the real persona-card click handler (as `test_persona_form.js`
   drives real listeners) closes the drawer on mobile and leaves it open on
   desktop, while still setting `selectedPersona` and flipping the
   who-answers radio exactly as today.
4. The room-dropdown change handler likewise closes the drawer without
   altering room-switch behavior.

**CSS poison guard** (same file, no DOM needed): read `static/style.css` and
assert (a) no `100vh` appears inside any `@media` block — the iOS-keyboard bug
class this proposal exists to prevent — and (b) exactly one
`@media (max-width: 768px)` block exists, so nobody quietly forks a second,
drifting breakpoint.

**Manual acceptance:** the reporter's mockup is the target. Checklist: iPhone
SE (375px) and Pixel-class (412px) portrait; keyboard open with a long message;
every modal opened and saved; drawer opened → persona picked → drawer closed
→ reply streams with TTS; stop button reachable mid-playback; landscape phone
(≤ 768px tall but wide — still compact by width, drawer pattern still applies).

Regression gates per AGENTS.md: full `.venv/bin/python -m pytest` (must stay
green — it only proves nothing backend-side broke), plus the existing Node
suites if any shared file is touched (`persona.js` → `test_persona_form.js`;
`chatrooms.js` → `test_persona_picker.js`).

## 6. Edge cases & risks

| Edge case | Handling |
|-----------|----------|
| On-screen keyboard | `dvh` + `interactive-widget=resizes-content`; input bar stays visible. Safari ignores the meta flag — `dvh` covers it there. |
| `dvh` unsupported (old browsers) | The `vh` fallback declaration keeps today's behavior — degrades, never breaks. |
| Landscape phone (e.g. 844×390) | Breakpoint is width-based; 844px > 768px keeps the desktop layout, which is genuinely fine in landscape. If field reports disagree, a `(orientation: landscape) and (max-height: 500px)` refinement can be added later — deliberately not in v1 (premature). |
| Tablet (768–1024px) | Desktop layout, sidebar visible. Correct for iPads at both sizes. |
| Modal `.hidden` specificity trap | Called out in §3.4; the CSS comment at L93–102 must be updated in the same commit. |
| Drawer left open while a modal opens | Acceptable: the modal overlay (`z-index: 100`) already covers the drawer (`z-index: 40`). Closing the drawer underneath is invisible either way. |
| `Ctrl+Space` mic shortcut | Desktop keyboards only; untouched. |
| Mic over plain HTTP | Unchanged by this proposal — phones reach the app via Tailscale (the reporter's "tailscaled spark"); if that's `http://` on a non-localhost origin, `getUserMedia` is blocked by the browser regardless of layout. Worth a README note, out of scope here. |
| Desktop regression | The entire change lives inside one media query plus additive JS guarded by `isCompactViewport()`. The Node tests pin the guard. |

## 7. Alternatives considered

1. **Separate mobile template** (`index_mobile.html` + user-agent sniffing):
   forks 474 lines of markup and every modal — a drift machine. Rejected.
2. **Bottom tab bar redesign** (Chat / Personas / Rooms / Settings tabs):
   a different app, not a reflow. Bigger JS surface, no test harness for tab
   state, and the reporter's mockup shows a drawer-style stacked layout.
   Rejected for v1; can evolve later if users want it.
3. **Top-bar "More" overflow menu**: saves ~100px but adds a new interactive
   component (focus trap, click-outside, ARIA) with its own bug class. The
   icon-only topbar fits 320px without it. Rejected as unnecessary.
4. **Container queries instead of a viewport breakpoint**: tempting, but the
   drawer needs viewport knowledge in JS anyway (the auto-close guard), so
   mixing two sources of truth for "is compact" is worse than one media query
   plus one `matchMedia` mirror of it. Rejected.

## 8. Implementation phases

| Phase | Content | Est. |
|-------|---------|------|
| 1 | Viewport meta, `dvh` fallbacks, safe-area padding, manifest colors | ½ day |
| 2 | Drawer CSS + `drawer.js` + hamburger/scrim markup + wiring | 1 day |
| 3 | Topbar icon-only, modal sheets, touch targets, bubble/avatar sizing | ½ day |
| 4 | `tests/test_mobile_drawer.js`, AGENTS.md coverage map + module table, manual device pass against the mockup | 1 day |

Each phase ends with a green pytest run plus the relevant Node suites, per
repo rules.

## 9. Summary

One breakpoint, one drawer, one new 40-line JS module, zero backend changes.
The app already ships a PWA manifest and a viewport meta — it is one media
query away from being genuinely usable on the "tailscaled spark" the reporter
is already running it on. Recommend proceeding with phases 1–4 as scoped.
