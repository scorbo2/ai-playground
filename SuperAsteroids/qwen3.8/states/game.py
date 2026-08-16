"""Game Mode.

Stage 1 notes: placeholder screen only ("GAME MODE" in large white letters,
centered). ESC pauses. Asteroids, the player craft, weapons, and the path
to Game Over mode all land in Stages 2-4.
"""

import pygame

from font_manager import blit_centered, render_text
from game_constants import BLACK, HEADING_FONT_SIZE, WHITE
from states.base import GameModeState


class GameState(GameModeState):

    PLACEHOLDER_HEADING = "GAME MODE"

    def handle_events(self, events: list) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.app.to_pause()

    def update(self) -> None:
        # Stage 2+ fills this in: level intro, asteroids, player craft, weapons.
        pass

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(BLACK)
        width, height = screen.get_size()
        blit_centered(screen,
                      render_text(self.PLACEHOLDER_HEADING, HEADING_FONT_SIZE, WHITE),
                      (width // 2, height // 2))
