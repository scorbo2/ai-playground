# Mobile Layout Proposal — Issue #143

## 1. Executive Summary

Issue #143 requests a mobile-friendly layout for TalkWithMe. The app is currently built as a **desktop-first, fixed-width sidebar layout** with no responsive breakpoints. On phones and small tablets, the 310px sidebar crowds the chat panel, the top bar's nine buttons overflow, and the modals are too wide for narrow screens.

This proposal outlines a **responsive retrofit** that keeps the existing desktop layout intact above the tablet breakpoint, while reflowing to a single-column, stacked layout on mobile. The approach is **CSS-driven with minimal JavaScript changes**, preserving all existing functionality (personas, chat rooms, TTS/STT, settings modals, audio playback, message deletion).

## 2. Current Layout — Mobile-Unfriendly Aspects

| Area | Problem on Mobile |
|------|-------------------|
| **Layout** (`#main-layout`) | `display: flex` with a fixed 310px sidebar. On a 375px-wide phone, the sidebar consumes ~83% of the width, leaving the chat panel squashed. |
| **Top bar** | Nine buttons + theme dropdown + title. No wrapping; they overflow and get clipped on small screens. |
| **Sidebar** | Always visible, fixed width. No way to hide it on mobile to give the chat panel more room. |
| **Chat panel** | `flex: 1` but squeezed by the sidebar. Bubbles have `max-width: 80%`, which is too narrow on mobile. |
| **Input bar** | Textarea + mic + send button side by side. On mobile, the textarea should take the full width with buttons stacked or compact. |
| **Modals** | `max-width: 680px` / `400px`, centered. On a 375px screen these still leave small margins, but the inner forms (especially the Persona Editor with 12+ fields) are cramped and require excessive scrolling. |
| **Chat bubbles** | 64px avatars are large relative to bubble width on mobile; bubble text is small. |
| **No breakpoints** | No `@media` queries exist in `style.css`. |

## 3. Design Goals

1. **Preserve the desktop experience** exactly as-is above the tablet breakpoint (no regressions).
2. **Stack layout on mobile**: sidebar hides or slides under the chat panel; chat panel becomes full-width.
3. **Top bar adapts**: title + essential actions on mobile; secondary actions move into a overflow menu or are hidden.
4. **Modals become full-width / full-height on mobile** with scrollable inner content.
5. **Touch-friendly targets**: minimum 44px tap targets, larger spacing.
6. **No new dependencies**: pure CSS + vanilla JS, no frameworks, no bundler.
7. **Accessibility**: maintain ARIA attributes, focus management, and keyboard navigation.

## 4. Responsive Strategy

### Breakpoints

| Breakpoint | Name | Behavior |
|------------|------|----------|
| `< 768px` | Mobile | Single-column: sidebar hidden behind a menu button, chat panel full-width, modals full-screen. |
| `768px – 1023px` | Tablet | Sidebar collapsible (slide-out drawer) or visible if space allows; top bar may wrap. |
| `≥ 1024px` | Desktop | Current layout unchanged. |

### Layout approach

**Mobile (< 768px)**:
- `#main-layout` becomes `flex-direction: column` (sidebar under chat panel, or sidebar hidden).
- Sidebar is hidden by default; a **menu button** (hamburger) in the top bar toggles it. When open, the sidebar overlays the chat panel (or pushes it, depending on implementation choice — overlay is simpler and avoids reflow).
- Chat panel takes `100% width`, `flex: 1`.
- Bubbles expand to `max-width: 90%` (wider on mobile).
- Input bar: textarea full-width, mic + send buttons compact/stacked.

**Tablet (768px – 1023px)**:
- Sidebar visible but narrower (e.g., 240px) or collapsible.
- Top bar buttons may wrap to two lines.

### CSS custom properties for mobile

Add mobile-specific overrides in `:root` (or a `[data-theme]`-agnostic block) and a media query block:

```css
:root {
    /* Mobile overrides */
    --mobile-sidebar-width: 85vw;   /* sidebar when open, as a percentage of viewport width */
    --mobile-topbar-height: 56px;   /* slightly taller for touch */
    --mobile-bubble-max-width: 90%;
    --mobile-input-bar-padding: 12px;
}
```

## 5. Specific Component Changes

### 5.1 HTML — `templates/index.html`

1. **Add a mobile menu button** in the top bar (hidden on desktop, shown on mobile via CSS):
   ```html
   <button id="btn-sidebar-toggle" title="Open menu" class="icon-btn" aria-label="Open menu">
       &#9776;
   </button>
   ```

2. **Wrap the sidebar** so it can be toggled. The sidebar already lives in `#main-layout` alongside `#chat-panel`. No HTML change needed — CSS handles the flex-direction switch.

3. **Top bar actions**: split into two groups:
   - `.topbar-actions-primary` — always visible (theme, new chat, stop audio, TTS toggle).
   - `.topbar-actions-secondary` — hidden on mobile, shown via the menu toggle on desktop (personas, chat rooms, settings, servers). Actually, a simpler approach: on mobile, show only the most-used buttons and hide the rest behind the menu toggle.

   Given the single-user nature of the app, the most-used topbar actions are: theme, new chat, stop audio, TTS toggle. Personas/chat rooms/settings/servers are configuration-level and less frequently accessed. On mobile, hide the secondary ones and reveal them when the menu button is tapped.

### 5.2 CSS — `static/style.css`

#### 5.2.1 Base layout (desktop, unchanged)

No changes to the desktop rules. The existing `#main-layout { display: flex; }` and `#sidebar { width: 310px; }` remain for `≥ 768px`.

#### 5.2.2 Mobile media query (`@media (max-width: 767px)`)

```css
/* ==========================================================================
   Mobile layout (< 768px)
   ========================================================================== */

#main-layout {
    flex-direction: column;
    height: 100vh; /* full height, topbar occupies its fixed height */
}

/* Sidebar: hidden by default on mobile, slides over the chat panel */
#sidebar {
    position: fixed;
    inset: var(--topbar-height) 0 auto 0; /* below the topbar, full height */
    width: var(--mobile-sidebar-width);
    z-index: 20;
    display: none; /* hidden by default */
    transform: translateX(-100%);
    transition: transform 0.2s ease;
}

#sidebar.open {
    transform: translateX(0);
    display: flex;
}

/* Chat panel: full width on mobile */
#chat-panel {
    width: 100%;
    min-width: 0; /* needed for flex children to shrink */
}

/* Messages area: bubbles wider on mobile */
#messages {
    padding: 12px; /* less padding on mobile */
    gap: 8px;
}

.message-row {
    max-width: var(--mobile-bubble-max-width);
}

/* Avatar: smaller on mobile */
.bubble-avatar {
    width: 44px;
    height: 44px;
    font-size: 1.2rem;
}

/* Input bar: textarea full-width, buttons compact */
#input-bar {
    flex-direction: column;
    gap: 8px;
    padding: 12px var(--mobile-input-bar-padding);
}

#message-input {
    width: 100%;
    min-height: 44px; /* touch-friendly */
}

#btn-send, #btn-mic {
    width: 44px;
    height: 44px;
    font-size: 1.2rem;
}

/* When the sidebar is open, push the chat panel (optional: overlay instead) */
body.sidebar-open #main-layout {
    /* overlay approach: sidebar is fixed-positioned, chat panel stays full width */
}

/* Top bar: allow wrapping on mobile */
#topbar {
    flex-wrap: wrap;
    gap: 8px;
    padding: 0 12px;
}

#topbar h1 {
    font-size: 1rem;
    margin-right: auto; /* push buttons to the right */
}

.topbar-actions {
    flex-wrap: wrap;
    gap: 6px;
}

/* Mobile menu button */
#btn-sidebar-toggle {
    display: flex;
    align-items: center;
    justify-content: center;
    /* hidden on desktop by default */
}

/* Desktop: hide the toggle, show all topbar buttons */
@media (min-width: 768px) {
    #btn-sidebar-toggle { display: none; }
    #sidebar { display: flex; position: static; transform: none; }
    #main-layout { flex-direction: row; height: calc(100vh - var(--topbar-height)); }
    #sidebar { position: static; width: var(--sidebar-width); z-index: auto; }
    #chat-panel { width: auto; }
    #messages { padding: 20px; gap: 12px; }
    .message-row { max-width: 80%; }
    .bubble-avatar { width: 64px; height: 64px; font-size: 1.5rem; }
    #input-bar { flex-direction: row; padding: 14px 20px; }
    #message-input { width: auto; min-height: auto; }
    #btn-send, #btn-mic { width: 40px; height: 40px; font-size: 1rem; }
}
```

#### 5.2.3 Modals on mobile

Modals should become full-width and full-height on mobile, with scrollable inner content:

```css
@media (max-width: 767px) {
    .modal-overlay {
        padding: 0; /* full-screen overlay */
        align-items: flex-start;
        justify-content: flex-start;
    }
    .modal-box {
        width: 100%;
        max-width: 100%;
        max-height: 100vh;
        border-radius: 0;
        border: none;
        margin: 0;
    }
    .modal-header {
        padding: 12px 16px;
    }
    .modal-header h2 { font-size: 1.1rem; }
    #pe-form, #settings-form, #gen-settings-form {
        padding: 12px 16px;
        gap: 10px;
    }
    .form-row input[type="text"],
    .form-row textarea,
    .form-row select {
        width: 100%;
        box-sizing: border-box;
    }
    .form-row-inline {
        flex-direction: column;
        gap: 8px;
    }
    .form-col { width: 100%; }
    .form-actions {
        flex-direction: column-reverse;
        gap: 8px;
        padding: 10px 16px;
    }
    .form-actions button {
        width: 100%;
    }
    /* TTS dynamic params: stack label above input */
    .tts-slider-row { flex-direction: column; align-items: flex-start; }
    .tts-slider-readout { min-width: auto; text-align: left; margin-top: 4px; }
    /* Array parameter rows stack */
    .tts-array-item { flex-direction: column; align-items: flex-start; gap: 4px; }
    .tts-array-item-label { width: 100%; white-space: normal; }
}
```

#### 5.2.4 Touch targets

Ensure all interactive elements are at least 44px:

```css
button, input[type="button"], input[type="submit"], .icon-btn, .btn-accent, .btn-secondary, .btn-danger {
    min-height: 44px;
    min-width: 44px;
}

.audio-play-btn, .message-delete-btn {
    min-height: 44px;
    min-width: 44px;
}

.pp-checkbox, .settings-toggle {
    width: 24px;
    height: 24px;
}
```

### 5.3 JavaScript — minimal changes

#### 5.3.1 `static/app.js` — sidebar toggle

Add a function to toggle the sidebar on mobile:

```javascript
const sidebarToggle = document.getElementById("btn-sidebar-toggle");
const sidebarEl = document.getElementById("sidebar");

function toggleSidebar() {
    sidebarEl.classList.toggle("open");
    // Trap focus: when opening, move focus to the first focusable element
    // in the sidebar; when closing, return focus to the toggle button.
}

sidebarToggle.addEventListener("click", toggleSidebar);

// Close sidebar when clicking the backdrop (overlay). Add a backdrop div
// in HTML or use CSS ::before on #sidebar.
```

Also, close any open modal when the sidebar toggle is clicked (avoid overlapping modals).

#### 5.3.2 `static/chat.js` — scroll on mobile

The `scrollToBottom()` function and bubble rendering are already mobile-friendly. No changes needed beyond ensuring `max-width` is respected.

#### 5.3.3 `static/persona.js`, `static/chatrooms.js`, `static/settings.js`, `static/gen-settings.js`

No JS changes required for the modal layout — the CSS media queries handle the reflow. However, the Persona Editor form has many fields; on mobile, the form should scroll within the modal (it already does via `overflow-y: auto` on `#pe-form`).

#### 5.3.4 `static/state.js`

Add DOM reference for the sidebar toggle button:

```javascript
const sidebarToggleEl = document.getElementById("btn-sidebar-toggle");
```

### 5.4 HTML additions

Add a backdrop for the sidebar so clicking outside closes it. The simplest approach is a CSS-only solution using the `:target` pseudo-class or a JS-driven backdrop div. Given the project's pattern of JS-managed classes, add a backdrop div in the HTML:

```html
<!-- Sidebar backdrop (mobile only) -->
<div id="sidebar-backdrop" class="hidden"></div>
```

And in JS, toggle the backdrop's `hidden` class alongside the sidebar's `open` class.

## 6. Implementation Phases

### Phase 1 — CSS media queries (no JS)
Add the mobile media query block to `style.css`:
- Layout: `#main-layout` flex-direction column, sidebar fixed-position hidden.
- Top bar: wrapping, smaller title.
- Bubbles: wider, smaller avatars.
- Input bar: stacked, full-width textarea.
- Modals: full-screen on mobile.

### Phase 2 — Sidebar toggle JS
- Add the hamburger button to the top bar.
- Wire up the toggle in `app.js` (or a new `mobile.js` module).
- Add the backdrop div and its click-to-close handler.

### Phase 3 — Touch target audit
- Verify all buttons meet the 44px minimum on mobile.
- Adjust padding/font sizes where needed.

### Phase 4 — Test on real devices
- Test on iOS Safari and Android Chrome (the primary targets, since the reporter uses a Tailscaled device — likely Linux-based, but the layout should be device-agnostic).
- Verify that the sidebar toggle works, modals are usable, and the input bar is comfortable.

## 7. What Stays the Same

- **Desktop layout**: unchanged above 768px.
- **All functionality**: personas, chat rooms, TTS/STT, settings, MCP, memories, echo chamber, message deletion, audio replay, speaking highlight — all work identically; only layout changes.
- **Theme support**: dark/light/matrix/blues themes continue to work via CSS custom properties.
- **SSE chat flow**: unchanged — the backend and frontend message handling is layout-agnostic.
- **Audio playback**: Web Audio queue and speaking highlight are unaffected by layout changes.

## 8. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Sidebar toggle conflicts with modal overlays | Close all modals when opening the sidebar; the sidebar has a higher z-index (20) than modals (100) — actually modals should stay on top. Solution: sidebar z-index = 15 (below modals at 100), so modals still overlay the sidebar. |
| Form fields cramped on mobile | Media queries stack form rows, make inputs full-width, reduce padding. |
| Long persona names truncate | Already handled with `text-overflow: ellipsis`; on mobile, ensure containers have `min-width: 0` so flex items can shrink. |
| Scrollbar overlap on mobile | Use `box-sizing: border-box` everywhere (already set). Ensure `overflow-y: auto` containers don't hide content. |
| The `html, body { overflow: hidden; }` rule | On mobile, the body should allow scrolling when a modal is open. The modals already handle their own scrolling via `max-height` and `overflow-y: auto`. Keep `overflow: hidden` on body to prevent background scroll when modals are open (standard pattern). |

## 9. Files to Modify

1. **`templates/index.html`** — Add sidebar toggle button + backdrop div; split topbar actions if desired.
2. **`static/style.css`** — Add mobile media query block (`@media (max-width: 767px)`) and the desktop counterpart (`@media (min-width: 768px)`) to re-assert desktop values.
3. **`static/state.js`** — Add DOM reference for `#btn-sidebar-toggle` and `#sidebar-backdrop`.
4. **`static/app.js`** — Add sidebar toggle event listener and backdrop click handler.

## 10. Files NOT to Modify (by design)

- `app/` (backend) — no changes needed; the API is layout-agnostic.
- `static/chat.js`, `static/tts.js`, `static/stt.js` — no layout logic.
- `static/persona.js`, `static/chatrooms.js`, `static/settings.js`, `static/gen-settings.js` — modal JS is layout-agnostic; CSS handles the mobile reflow.
- `static/utils.js`, `static/theme.js` — no layout logic.

## 11. Acceptance Criteria

- On a 375px-wide screen, the sidebar is hidden by default and accessible via a toggle button.
- The chat panel occupies the full width; bubbles are readable without horizontal scrolling.
- The input bar's textarea is full-width with a comfortable min-height for touch.
- All modals are full-screen on mobile with scrollable inner content.
- The desktop layout (≥ 768px) is pixel-for-pixel unchanged.
- All existing pytest and Node tests continue to pass (no JS API changes that break tests).

---

*Proposal for GitHub issue #143 — "Add mobile friendly layout". The reporter uses this app on a Tailscaled device and wants a usable mobile interface. This proposal reflows the existing desktop layout into a mobile-friendly stacked layout with a toggleable sidebar, responsive modals, and touch-friendly targets, all via CSS media queries with minimal JavaScript additions.*