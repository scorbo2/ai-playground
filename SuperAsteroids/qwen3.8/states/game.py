"""Game Mode.

Stage 2: the asteroid field is real - level 1 starts with 5 large asteroids
spawning safely away from where the player's ship will appear (the screen
center). The ship itself, the "BEGIN LEVEL N" intro, weapons, collision and
level advancement land in Stages 3-4. ESC pauses.
"""

import pygame

from entities import spawn_level_asteroids
from game_constants import BLACK, LEVEL_1_ASTEROID_COUNT
from states.base import GameModeState


class GameState(GameModeState):

    LEVEL_1 = 1

    def __init__(self, app):
        super().__init__(app)
        self.level = self.LEVEL_1
        # Asteroids to spawn on the NEXT level. Level 1 is fixed at 5; each
        # later advancement rolls +1 or +2 (Stage 4 owns that roll).
        self._next_level_asteroid_count = LEVEL_1_ASTEROID_COUNT
        width, height = app.screen.get_size()
        # The ship has not landed yet (Stage 3), but the spec keeps level
        # spawns 200px clear of it - and it will appear at screen center.
        ship_position = (width // 2, height // 2)
        self._asteroids = spawn_level_asteroids(
            self.level, self._next_level_asteroid_count,
            width, height, ship_position,
        )

    def handle_events(self, events: list) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                self.app.to_pause()

    def update(self) -> None:
        # The live window size keeps wrapping correct immediately after a
        # resize (the spec's "forced screen wrap" requirement).
        width, height = self.app.screen.get_size()
        for asteroid in self._asteroids:
            asteroid.update(width, height)

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(BLACK)
        for asteroid in self._asteroids:
            asteroid.draw(screen)
