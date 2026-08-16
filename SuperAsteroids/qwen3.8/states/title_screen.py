"""Title Screen Mode.

The background shows a subtle field of 3-6 large asteroids gently tumbling
with screen wrap - cosmetic only: they do not collide or split, and they are
discarded whenever a new game starts (a fresh Game Mode state spawns its own
field). Enter starts Game Mode at level 1; ESC exits the application with
exit code 0 (normal termination). The starfield background arrives in Stage 8.
"""

import pygame

from entities import spawn_title_screen_asteroids
from font_manager import blit_centered, draw_centered_lines, render_text
from game_constants import (
    BLACK,
    BODY_FONT_SIZE,
    GAME_TITLE,
    RED,
    TITLE_FONT_SIZE,
    TITLE_SCREEN_CONTROL_LINES,
    TITLE_SCREEN_START_PROMPT,
    WHITE,
)
from states.base import GameModeState


class TitleScreenState(GameModeState):

    def __init__(self, app):
        super().__init__(app)
        width, height = app.screen.get_size()
        self._asteroids = spawn_title_screen_asteroids(width, height)

    def handle_events(self, events: list) -> None:
        for event in events:
            if event.type != pygame.KEYDOWN:
                continue
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                self.app.to_game()
            elif event.key == pygame.K_ESCAPE:
                self.app.quit()  # spec: exit with code 0

    def update(self) -> None:
        # The live window size is read each frame so a resize mid-frames
        # keeps wrapping correct with no extra bookkeeping.
        width, height = self.app.screen.get_size()
        for asteroid in self._asteroids:
            asteroid.update(width, height)

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(BLACK)
        for asteroid in self._asteroids:
            asteroid.draw(screen)

        width, height = screen.get_size()

        # Spec: title "centered in the upper half" - the vertical center of
        # the upper half of the screen is at height // 4.
        blit_centered(screen, render_text(GAME_TITLE, TITLE_FONT_SIZE, RED),
                      (width // 2, height // 4))

        # Control instructions centered on the screen.
        draw_centered_lines(
            screen, width // 2, height // 2,
            [(line, BODY_FONT_SIZE, WHITE) for line in TITLE_SCREEN_CONTROL_LINES],
        )

        # Start prompt lower down.
        blit_centered(screen,
                      render_text(TITLE_SCREEN_START_PROMPT, BODY_FONT_SIZE, WHITE),
                      (width // 2, height * 3 // 4))
