"""Game Over Mode.

Stage 1 notes: not reachable yet (nothing can kill the player before the
asteroids land in Stage 3), but the full state is implemented so later
stages only need to call ``app.to_game_over()`` with an optional green
special message such as "FRIENDLY FIRE!" or "HOSTILE FIRE!".
"""

import pygame

from font_manager import blit_centered, draw_centered_lines, render_text
from game_constants import BLACK, BODY_FONT_SIZE, GREEN, HEADING_FONT_SIZE, RED, WHITE
from states.base import GameModeState


class GameOverState(GameModeState):

    HEADING = "GAME OVER"
    RESTART_HINT = "Press R to restart"
    EXIT_HINT = "Press ESC to exit"

    HEADING_OFFSET = -60
    HINTS_OFFSET = 40

    def __init__(self, app, special_message: str | None = None):
        super().__init__(app)
        self.special_message = special_message

    def handle_events(self, events: list) -> None:
        for event in events:
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_r:  # K_r covers both 'r' and 'R'
                self.app.to_game()
            elif event.key == pygame.K_ESCAPE:
                self.app.to_title()

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(BLACK)
        width, height = screen.get_size()

        blit_centered(screen, render_text(self.HEADING, HEADING_FONT_SIZE, RED),
                      (width // 2, height // 2 + self.HEADING_OFFSET))

        lines: list = []
        if self.special_message:
            # Spec: the special message sits between the heading and the hints, in green.
            lines.append((self.special_message, BODY_FONT_SIZE, GREEN))
        lines.extend([
            (self.RESTART_HINT, BODY_FONT_SIZE, WHITE),
            (self.EXIT_HINT, BODY_FONT_SIZE, WHITE),
        ])
        draw_centered_lines(screen, width // 2, height // 2 + self.HINTS_OFFSET, lines)
