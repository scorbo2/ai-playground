"""Pause Mode.

Stage 1 notes: there are no game objects to hide yet, so the screen is just
black plus the PAUSE heading and hints. ESC resumes Game Mode; the ``x`` key
abandons the current game and returns to Title Screen Mode.
"""

import pygame

from font_manager import blit_centered, draw_centered_lines, render_text
from game_constants import BLACK, BODY_FONT_SIZE, HEADING_FONT_SIZE, WHITE
from states.base import GameModeState


class PauseState(GameModeState):

    HEADING = "PAUSE"
    RESUME_HINT = "Press ESC to resume"
    EXIT_HINT = "Press X to exit"

    # Vertical offsets relative to screen center, so the layout holds up on
    # resized windows rather than being anchored to a 600px-tall screen.
    HEADING_OFFSET = -45
    HINTS_OFFSET = 45

    def handle_events(self, events: list) -> None:
        for event in events:
            if event.type != pygame.KEYDOWN:
                continue
            if event.key == pygame.K_ESCAPE:
                self.app.to_game()
            elif event.key == pygame.K_x:  # K_x covers both 'x' and 'X'
                self.app.to_title()

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(BLACK)
        width, height = screen.get_size()

        blit_centered(screen, render_text(self.HEADING, HEADING_FONT_SIZE, WHITE),
                      (width // 2, height // 2 + self.HEADING_OFFSET))

        draw_centered_lines(screen, width // 2, height // 2 + self.HINTS_OFFSET, [
            (self.RESUME_HINT, BODY_FONT_SIZE, WHITE),
            (self.EXIT_HINT, BODY_FONT_SIZE, WHITE),
        ])
