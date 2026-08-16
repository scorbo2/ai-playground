"""Application shell for SuperAsteroids.

This module owns the window, the clock, and the state machine. Game mode
states stay focused on their own behavior and ask the app for transitions,
so the full state graph lives here in one readable place.

Window-wide concerns (quit, F11 fullscreen toggle, resize clamping) are
handled globally in the main loop - they apply identically in every mode.
"""

import sys
import time
from typing import Optional

import pygame

from game_constants import (
    FPS,
    INITIAL_WINDOW_SIZE,
    MIN_WINDOW_HEIGHT,
    MIN_WINDOW_WIDTH,
    TEST_MODE_DURATION_SECONDS,
)
from states import GameModeState, GameOverState, GameState, PauseState, TitleScreenState


class SuperAsteroidsApp:
    """Owns the display, clock, and current mode, and runs the main loop."""

    def __init__(self, test_mode: bool = False):
        self.test_mode = test_mode
        pygame.init()
        self.screen = pygame.display.set_mode(INITIAL_WINDOW_SIZE, pygame.RESIZABLE)
        pygame.display.set_caption("SuperAsteroids")
        self.clock = pygame.time.Clock()

        self._running = True
        self._state = TitleScreenState(self)

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

    def to_title(self) -> None:
        self._state = TitleScreenState(self)

    def to_game(self) -> None:
        # Stage 1: placeholder screen. Later stages build the real game here.
        self._state = GameState(self)

    def to_pause(self) -> None:
        self._state = PauseState(self)

    def to_game_over(self, special_message: str | None = None) -> None:
        # Not reachable in Stage 1; later stages call this on player death.
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
                self._clamp_window_size(event.size)
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_F11:
                self._toggle_fullscreen()
        return False

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
        self._is_fullscreen = True

    def _exit_fullscreen(self) -> None:
        try:
            self.screen = pygame.display.set_mode(self._window_size,
                                                  pygame.RESIZABLE)
        except pygame.error as err:
            print(f"Warning: could not exit full screen: {err}",
                  file=sys.stderr)
            return
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
