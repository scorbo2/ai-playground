#!/usr/bin/env python3
"""
SuperAsteroids — Stage 1: Window + State Machine (Text-Only Placeholders)

A derivative of the classic Asteroids arcade game, built with pygame-ce.
Stage 1 establishes the window infrastructure, fullscreen toggle, resize
handling, and the core state machine with text-only placeholder screens.
"""

import sys
import pygame

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Window dimensions
INITIAL_WINDOW_WIDTH = 800
INITIAL_WINDOW_HEIGHT = 600
MIN_WINDOW_WIDTH = 640
MIN_WINDOW_HEIGHT = 480

# Framerate
TARGET_FPS = 60

# Colors
COLOR_BLACK = (0, 0, 0)
COLOR_WHITE = (255, 255, 255)

# Game modes (state machine states)
MODE_TITLE = "TITLE"
MODE_GAME = "GAME"
MODE_PAUSE = "PAUSE"
MODE_GAMEOVER = "GAMEOVER"

# Test mode duration in milliseconds
TEST_MODE_DELAY_MS = 100

# Font sizes (None = default pygame font)
FONT_SIZE_LARGE = 72
FONT_SIZE_MEDIUM = 48
FONT_SIZE_SMALL = 36


# ─────────────────────────────────────────────────────────────────────────────
# GAME CLASS
# ─────────────────────────────────────────────────────────────────────────────

class Game:
    """Main game controller. Manages the window, state machine, and rendering."""

    def __init__(self):
        """Initialize pygame and set up the window."""
        pygame.init()

        # Window state tracking
        self.window_width = INITIAL_WINDOW_WIDTH
        self.window_height = INITIAL_WINDOW_HEIGHT
        self.is_fullscreen = False
        self.saved_window_rect = None  # Saved before entering fullscreen

        # Create the initial resizable window
        self.screen = pygame.display.set_mode(
            (self.window_width, self.window_height),
            pygame.RESIZABLE,
        )
        pygame.display.set_caption("SuperAsteroids")

        # State machine
        self.current_mode = MODE_TITLE
        self.level = 1

        # Timing
        self.clock = pygame.time.Clock()
        self.running = True

        # Fonts (initialized after pygame.init)
        self._fonts = {}
        self._init_fonts()

    # ── Font management ──────────────────────────────────────────────────

    def _init_fonts(self):
        """Create cached font objects for reuse across screens."""
        self._fonts["large"] = pygame.font.Font(None, FONT_SIZE_LARGE)
        self._fonts["medium"] = pygame.font.Font(None, FONT_SIZE_MEDIUM)
        self._fonts["small"] = pygame.font.Font(None, FONT_SIZE_SMALL)

    # ── Main loop ────────────────────────────────────────────────────────

    def run(self):
        """Execute the main game loop until the player quits."""
        while self.running:
            self.running = self._handle_events()
            self._update()
            self._draw()
            pygame.display.flip()
            self.clock.tick(TARGET_FPS)

        pygame.quit()
        sys.exit(0)

    # ── Event handling ───────────────────────────────────────────────────

    def _handle_events(self):
        """Process all pending pygame events. Returns True if game should continue."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.VIDEORESIZE:
                self._handle_resize(event)
                continue

            if event.type == pygame.KEYDOWN:
                self._handle_keydown(event.key)

        return True

    def _handle_resize(self, event):
        """Handle window resize events, enforcing minimum dimensions."""
        new_width = max(event.w, MIN_WINDOW_WIDTH)
        new_height = max(event.h, MIN_WINDOW_HEIGHT)

        self.window_width = new_width
        self.window_height = new_height

        self.screen = pygame.display.set_mode(
            (new_width, new_height),
            pygame.RESIZABLE,
        )

    def _handle_keydown(self, key):
        """Route key presses to the appropriate handler based on current mode."""
        # F11 is global — toggles fullscreen from any mode
        if key == pygame.K_F11:
            self._toggle_fullscreen()
            return

        if self.current_mode == MODE_TITLE:
            self._handle_title_input(key)
        elif self.current_mode == MODE_GAME:
            self._handle_game_input(key)
        elif self.current_mode == MODE_PAUSE:
            self._handle_pause_input(key)
        elif self.current_mode == MODE_GAMEOVER:
            self._handle_gameover_input(key)

    # ── Mode-specific input handlers ─────────────────────────────────────

    def _handle_title_input(self, key):
        """Handle input while on the Title Screen."""
        if key == pygame.K_RETURN:
            # Enter Game Mode at level 1
            self.current_mode = MODE_GAME
            self.level = 1
        elif key == pygame.K_ESCAPE:
            # Exit the game immediately
            pygame.quit()
            sys.exit(0)

    def _handle_game_input(self, key):
        """Handle input while in Game Mode."""
        if key == pygame.K_ESCAPE:
            # Pause the game
            self.current_mode = MODE_PAUSE

    def _handle_pause_input(self, key):
        """Handle input while in Pause Mode."""
        if key == pygame.K_ESCAPE:
            # Resume the game
            self.current_mode = MODE_GAME
        elif key == pygame.K_x:
            # Abandon game, return to Title Screen
            self.current_mode = MODE_TITLE

    def _handle_gameover_input(self, key):
        """Handle input while in Game Over Mode."""
        if key == pygame.K_r:
            # Restart from level 1
            self.current_mode = MODE_GAME
            self.level = 1
        elif key == pygame.K_ESCAPE:
            # Return to Title Screen
            self.current_mode = MODE_TITLE

    # ── Fullscreen toggle ────────────────────────────────────────────────

    def _toggle_fullscreen(self):
        """Toggle between windowed and fullscreen mode, preserving window state."""
        if self.is_fullscreen:
            # Restore previous windowed state
            if self.saved_window_rect is not None:
                self.screen = pygame.display.set_mode(
                    (self.saved_window_rect.width, self.saved_window_rect.height),
                    pygame.RESIZABLE,
                )
                pygame.display.set_window_position(
                    self.saved_window_rect.x,
                    self.saved_window_rect.y,
                )
                self.window_width = self.saved_window_rect.width
                self.window_height = self.saved_window_rect.height
            else:
                # Fallback to defaults if we couldn't save the rect
                self.screen = pygame.display.set_mode(
                    (INITIAL_WINDOW_WIDTH, INITIAL_WINDOW_HEIGHT),
                    pygame.RESIZABLE,
                )
                self.window_width = INITIAL_WINDOW_WIDTH
                self.window_height = INITIAL_WINDOW_HEIGHT

            self.is_fullscreen = False
        else:
            # Save current window position and size, then go fullscreen
            try:
                self.saved_window_rect = pygame.display.get_window_rect()
            except Exception:
                self.saved_window_rect = None

            # (0, 0) with FULLSCREEN flag uses the display's native resolution
            self.screen = pygame.display.set_mode(
                (0, 0),
                pygame.FULLSCREEN,
            )
            self.window_width = self.screen.get_width()
            self.window_height = self.screen.get_height()
            self.is_fullscreen = True

    # ── Update ───────────────────────────────────────────────────────────

    def _update(self):
        """Update game state. (No-op in Stage 1 — no gameplay yet.)"""
        pass

    # ── Rendering ────────────────────────────────────────────────────────

    def _draw(self):
        """Render the current screen based on the active game mode."""
        self.screen.fill(COLOR_BLACK)

        if self.current_mode == MODE_TITLE:
            self._draw_title_screen()
        elif self.current_mode == MODE_GAME:
            self._draw_game_screen()
        elif self.current_mode == MODE_PAUSE:
            self._draw_pause_screen()
        elif self.current_mode == MODE_GAMEOVER:
            self._draw_gameover_screen()

    def _draw_title_screen(self):
        """Render the Title Screen placeholder."""
        title = self._fonts["large"].render("Title Screen", True, COLOR_WHITE)
        subtitle = self._fonts["small"].render("Press Enter / ESC", True, COLOR_WHITE)

        self._blit_centered(title, vertical_ratio=0.35)
        self._blit_centered(subtitle, vertical_ratio=0.6)

    def _draw_game_screen(self):
        """Render the Game Mode placeholder."""
        level_text = self._fonts["medium"].render(
            f"Game Mode (Level {self.level})", True, COLOR_WHITE
        )
        hint = self._fonts["small"].render("Press ESC to pause", True, COLOR_WHITE)

        self._blit_centered(level_text, vertical_ratio=0.35)
        self._blit_centered(hint, vertical_ratio=0.6)

    def _draw_pause_screen(self):
        """Render the Pause Mode placeholder."""
        title = self._fonts["large"].render("PAUSED", True, COLOR_WHITE)
        resume = self._fonts["small"].render("ESC to resume", True, COLOR_WHITE)
        exit_text = self._fonts["small"].render("X to exit", True, COLOR_WHITE)

        self._blit_centered(title, vertical_ratio=0.3)
        self._blit_centered(resume, vertical_ratio=0.55)
        self._blit_centered(exit_text, vertical_ratio=0.65)

    def _draw_gameover_screen(self):
        """Render the Game Over placeholder."""
        title = self._fonts["large"].render("GAME OVER", True, COLOR_WHITE)
        restart = self._fonts["small"].render("R to restart", True, COLOR_WHITE)
        exit_text = self._fonts["small"].render("ESC to exit", True, COLOR_WHITE)

        self._blit_centered(title, vertical_ratio=0.3)
        self._blit_centered(restart, vertical_ratio=0.55)
        self._blit_centered(exit_text, vertical_ratio=0.65)

    # ── Rendering helpers ────────────────────────────────────────────────

    def _blit_centered(self, surface, vertical_ratio):
        """Blit a surface centered horizontally at a given vertical ratio of the screen.

        Args:
            surface: The pygame Surface to render.
            vertical_ratio: A float between 0.0 (top) and 1.0 (bottom)
                            specifying the vertical center position.
        """
        center_x = self.window_width // 2
        center_y = int(self.window_height * vertical_ratio)
        rect = surface.get_rect(center=(center_x, center_y))
        self.screen.blit(surface, rect)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Application entry point. Handles --test mode flag."""
    test_mode = "--test" in sys.argv

    game = Game()

    if test_mode:
        # Test mode: render the title screen briefly, then exit cleanly
        game._draw()
        pygame.display.flip()
        pygame.time.wait(TEST_MODE_DELAY_MS)
        pygame.quit()
        sys.exit(0)
    else:
        # Normal mode: run the full game loop
        game.run()


if __name__ == "__main__":
    main()
