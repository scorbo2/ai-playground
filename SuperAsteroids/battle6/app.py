"""Application shell for SuperAsteroids.

This module owns the window, the clock, the sound system, and the state
machine. Game mode states stay focused on their own behavior and ask the
app for transitions, so the full state graph lives here in one readable
place.

Window-wide concerns (quit, F11 fullscreen toggle, resize clamping, F2
sound toggle) are handled globally in the main loop - they apply identically
in every mode. The starfield is handled the same way: it is displayed in
ALL modes and "never stops", so the app advances it every frame regardless
of the current mode (spec: Starfield background).
"""

import sys
import time
from typing import Optional

import pygame

from effects.starfield import Starfield
from game_constants import (
    FPS,
    FRIENDLY_FIRE_MESSAGE,
    INITIAL_WINDOW_SIZE,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    SFX_MIXER_BUFFER,
    SFX_MIXER_CHANNELS,
    SFX_SAMPLE_RATE,
    SFX_SAMPLE_SIZE,
    TEST_MODE_DURATION_SECONDS,
)
from sound import (
    SFX_SHIP_DESTROYED_ASTEROID,
    SFX_SHIP_DESTROYED_FRIENDLY_FIRE,
    SoundManager,
)
from states import GameModeState, GameOverState, GameState, PauseState, TitleScreenState


class SuperAsteroidsApp:
    """Owns the display, clock, and current mode, and runs the main loop."""

    def __init__(self, test_mode: bool = False, debug_mode: bool = False,
                 sound_on: bool = True):
        self.test_mode = test_mode
        # --debug (spec: "Debug option"): enables cheat hotkeys in Game
        # Mode (C/L/S powerups, U for a UFO).
        self.debug_mode = debug_mode
        # Mixer config made explicit, pre_init BEFORE pygame.init(). The
        # values match pygame's defaults and the shipped WAV format (see
        # game_constants for the rationale).
        pygame.mixer.pre_init(SFX_SAMPLE_RATE, SFX_SAMPLE_SIZE,
                              SFX_MIXER_CHANNELS, SFX_MIXER_BUFFER)
        pygame.init()
        self.screen = pygame.display.set_mode(INITIAL_WINDOW_SIZE, pygame.RESIZABLE)
        pygame.display.set_caption("SuperAsteroids")
        self.clock = pygame.time.Clock()

        # Starfield background (spec: Starfield background): one field for
        # the whole app, regenerated whenever the window size changes.
        self._starfield_size = self.screen.get_size()
        self._starfield = Starfield(*self._starfield_size)

        # Global sound system (spec: Sound): all effects load into memory
        # on startup; a per-file load failure is a warning, not a crash.
        # sound_on=False is what --nosound passes at startup (F2 can still
        # turn it back on).
        self._sound = SoundManager(sound_on=sound_on)

        self._running = True
        self._state = TitleScreenState(self)
        # The GameState frozen by to_pause(), restored by resume().
        self._paused_state: Optional[GameModeState] = None

        # F11 state: _is_fullscreen mirrors the real window state, and the
        # windowed geometry is saved on enter so we can restore it exactly on
        # exit (see _enter_fullscreen / _exit_fullscreen).
        self._is_fullscreen = False
        self._window_size = INITIAL_WINDOW_SIZE
        self._window_position: Optional[tuple] = None

        # --test mode: start the title screen, then terminate normally
        # after 250 ms to confirm the game boots cleanly.
        self._test_deadline = (
            time.monotonic() + TEST_MODE_DURATION_SECONDS if test_mode else None
        )

    # ---------------------------------------------------------- state machine

    @property
    def state(self) -> GameModeState:
        return self._state

    @property
    def sound(self) -> SoundManager:
        return self._sound

    @property
    def sound_on(self) -> bool:
        # The HUD's "Sound:" line reads this; the manager is the source of
        # truth (one global switch, unaffected by mode - spec: Sound).
        return self._sound.sound_on

    @property
    def starfield(self) -> Starfield:
        # Every mode draws it behind its own content (spec: all modes).
        return self._starfield

    def to_title(self) -> None:
        self._paused_state = None
        self._sound.stop_loops()
        self._state = TitleScreenState(self)

    def to_game(self) -> None:
        # Always a NEW game: any paused state is discarded and a fresh
        # GameState is built. The new state's craft is centered and its
        # spawn timers reset (spec: Timers); no loop can be active yet.
        self._paused_state = None
        self._sound.stop_loops()
        self._state = GameState(self)

    def to_pause(self) -> None:
        # Freeze: the running GameState is saved and restored AS-IS on
        # resume (spec: "the game in progress is frozen in place" - a
        # resume must NOT rebuild the level). The outgoing state gets a
        # say in the freeze first (on_pause), so transient state like
        # held keys is dropped on EVERY pause path, not just the ESC one.
        self._state.on_pause()
        self._paused_state = self._state
        # A frozen game makes no sound: the loops stop now and the game
        # state re-establishes them per-frame on resume.
        self._sound.stop_loops()
        self._state = PauseState(self)

    def resume(self) -> None:
        """Restore the frozen GameState exactly as it was when paused."""
        if self._paused_state is not None:
            self._state = self._paused_state
            self._paused_state = None

    def to_game_over(self, special_message: str | None = None) -> None:
        # Reached from Game Mode: the craft flying into an asteroid (Stage 3),
        # weapon deaths later (Stages 4-6, with their green special messages).
        # Death SFX (sfx/README.md): the friendly-fire sound is reserved for
        # exactly that; EVERY other death (asteroid contact, UFO contact,
        # hostile fire) uses the generic one.
        if special_message == FRIENDLY_FIRE_MESSAGE:
            self._sound.play(SFX_SHIP_DESTROYED_FRIENDLY_FIRE)
        else:
            self._sound.play(SFX_SHIP_DESTROYED_ASTEROID)
        self._sound.stop_loops()
        self._state = GameOverState(self, special_message)

    def quit(self) -> None:
        """Stop the main loop with exit code 0 (normal termination)."""
        self._running = False

    # ---------------------------------------------------------------- main loop

    def run(self) -> int:
        """Run until the app quits; the return value is the process exit code."""
        while self._running:
            events = pygame.event.get()
            if self._handle_window_events(events):
                # A terminal window event (e.g. the close button) arrived;
                # stop before giving the current state its view of the frame.
                break
            self._state.handle_events(events)
            # The starfield advances in EVERY mode - pause and game over
            # freeze gameplay, but the sky keeps twinkling (spec).
            self._starfield.update()
            self._state.update()
            self._state.draw(self.screen)
            pygame.display.flip()
            self.clock.tick(FPS)
            if self._test_deadline is not None and time.monotonic() >= self._test_deadline:
                self.quit()
        return 0

    # -------------------------------------------------------- window management

    def _handle_window_events(self, events: list) -> bool:
        """Handle window-wide events. Returns True if the app must shut down."""
        for event in events:
            if event.type == pygame.QUIT:
                self._running = False
                return True
            if event.type == pygame.VIDEORESIZE:
                self._on_video_resize(event.size)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                self._toggle_fullscreen()
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F2:
                # Spec (Sound): F2 toggles sound in ANY mode; the state
                # persists across modes until toggled again.
                self._sound.toggle()
        return False

    def _on_video_resize(self, size: tuple) -> None:
        self._clamp_window_size(size)
        # Whichever path we took - pygame resized the surface itself for a
        # valid size, or we forced it back to the minimum - the drawing
        # area changed, and the spec explicitly allows regenerating the
        # whole starfield to cover any newly exposed area.
        self._rebuild_starfield()

    def _rebuild_starfield(self) -> None:
        size = self.screen.get_size()
        if size == self._starfield_size:
            # A no-op size change (e.g. repeated VIDEORESIZE events while
            # the user is dragging the window edge): re-scattering the
            # whole sky on every one of those would make it shimmer.
            return
        self._starfield = Starfield(*size)
        self._starfield_size = size

    def _clamp_window_size(self, size: tuple) -> None:
        """Enforce the 400x300 minimum window size on resize requests.

        Implementation warning honored here (see SuperAsteroids2.md): for a
        VIDEORESIZE that stays at or above the minimum, pygame has ALREADY
        resized the drawing surface - so do nothing. Calling set_mode() in
        response to a valid resize fights the window manager's in-progress
        resize gesture and the window snaps back, making it unresizable.
        set_mode() is called in exactly one case: to push the window back up
        to the minimum when the requested size falls below it.
        """
        width, height = size
        if width >= MIN_WINDOW_WIDTH and height >= MIN_WINDOW_HEIGHT:
            return
        clamped_size = (max(width, MIN_WINDOW_WIDTH), max(height, MIN_WINDOW_HEIGHT))
        self.screen = pygame.display.set_mode(clamped_size, pygame.RESIZABLE)

    def _toggle_fullscreen(self) -> None:
        """F11 handler: toggle desktop-style (borderless) full-screen mode."""
        if self._is_fullscreen:
            self._exit_fullscreen()
        else:
            self._enter_fullscreen()

    def _enter_fullscreen(self) -> None:
        # Save the windowed geometry before switching. The window manager
        # only restores it approximately on exit (offsets of a few pixels do
        # happen), and the spec requires the SAME position and dimensions.
        self._window_size = self.screen.get_size()
        self._window_position = self._get_window_position()
        try:
            self.screen = pygame.display.set_mode(
                self._full_screen_resolution(), pygame.FULLSCREEN
            )
        except pygame.error as err:
            # The dummy video driver (and some headless setups) cannot go
            # full screen. Not fatal: warn and keep playing windowed.
            print(f"Warning: could not enter full screen: {err}",
                  file=sys.stderr)
            return
        # The display is now the whole desktop: give the starfield the new
        # area to work with. Fullscreen set_mode emits no VIDEORESIZE, so
        # this call is the rebuild trigger on the way in.
        self._rebuild_starfield()
        self._is_fullscreen = True

    def _exit_fullscreen(self) -> None:
        try:
            self.screen = pygame.display.set_mode(self._window_size,
                                                  pygame.RESIZABLE)
        except pygame.error as err:
            print(f"Warning: could not exit full screen: {err}",
                  file=sys.stderr)
            return
        self._rebuild_starfield()
        # Re-apply the saved position explicitly: after leaving full screen
        # the window is back at its old size, but not necessarily its old
        # spot. (set_window_position needs pygame-ce >= 2.5; older builds
        # simply keep the approximately-restored position.)
        if self._window_position is not None and hasattr(
                pygame.display, "set_window_position"):
            try:
                pygame.display.set_window_position(self._window_position)
            except pygame.error:
                pass  # not supported by every video driver
        self._is_fullscreen = False

    def _full_screen_resolution(self) -> tuple:
        """Native resolution of the display our window currently sits on.

        Requesting set_mode() at EXACTLY the desktop resolution is the one
        case pygame implements as desktop-style full screen (borderless,
        covering the display, NO physical mode change). Any other size makes
        pygame perform an exclusive video-mode switch - which on a 1080p
        desktop with an 800x600 window would literally reconfigure the
        monitor to 800x600. So the exact size matters.

        pygame does not expose a window's display index, so it is inferred
        from the window's global x coordinate, assuming monitors are laid
        out left-to-right (the common case; unresolvable positions fall
        back to the primary display).
        """
        try:
            sizes = pygame.display.get_desktop_sizes()
        except pygame.error:
            return self.screen.get_size()  # legacy fall-back behavior
        if not sizes:
            return self.screen.get_size()
        window_x = self._window_position[0] if self._window_position else 0
        x_offset = 0
        for i, (width, _height) in enumerate(sizes):
            if x_offset <= window_x < x_offset + width:
                return sizes[i]
            x_offset += width
        return sizes[0]

    @staticmethod
    def _get_window_position() -> Optional[tuple]:
        """Top-left corner of the window, or None if the platform can't
        report it (e.g. the dummy video driver)."""
        try:
            return pygame.display.get_window_position()
        except pygame.error:
            return None
