"""Game Mode.

Stage 3: the player's craft has landed at the center of the screen and flies
per the classic Asteroids model - held-arrow rotation, thrust, friction,
max speed, screen wrap. Contact with ANY asteroid is instant Game Over
(the shield exception lands in Stage 5). Weapons, the "BEGIN LEVEL N"
intro, scoring, and level advancement still land in Stage 4. ESC pauses.
"""

import pygame

from entities import PlayerCraft, player_hits_asteroid, spawn_level_asteroids
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
        # The craft has not landed at level start in the spec's final form,
        # but Stage 4 owns the "BEGIN LEVEL" intro; it simply appears at
        # screen center, where the spawn logic keeps asteroids 200px clear.
        self._craft = PlayerCraft(width // 2, height // 2)
        self._asteroids = spawn_level_asteroids(
            self.level, self._next_level_asteroid_count,
            width, height,
            ship_position=(self._craft.x, self._craft.y),
        )
        # Keys physically held right now. Decoded into intents in update();
        # dropped in on_pause() (called by app.to_pause() on every pause
        # path) and on focus loss, so stale presses can't leak in. pygame
        # has no key-repeat unless set_repeat() is called, so a key still
        # physically held after resume stays "released" until it is
        # pressed again - safer than the alternative of a stuck thrust.
        self._held_keys: set = set()

    def handle_events(self, events: list) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.app.to_pause()
                else:
                    self._held_keys.add(event.key)
            elif event.type == pygame.KEYUP:
                self._held_keys.discard(event.key)
            elif event.type == pygame.WINDOWFOCUSLOST:
                # Keys released while we had no focus never produced
                # KEYUP events; drop them rather than thrash forever.
                self._held_keys.clear()

    def on_pause(self) -> None:
        # The craft must not wake up still "thrusting" because the pause
        # key happened to be held.
        self._held_keys.clear()

    def _craft_intents(self) -> tuple:
        """Decode held keys into (thrusting, turning) for the craft.

        Both rotation keys held = straight (cancel each other); the craft
        itself only ever sees booleans and an integer, never key codes.
        """
        turning = 0
        if pygame.K_LEFT in self._held_keys:
            turning -= 1
        if pygame.K_RIGHT in self._held_keys:
            turning += 1
        return (pygame.K_UP in self._held_keys, turning)

    def update(self) -> None:
        # The live window size keeps wrapping correct immediately after a
        # resize (the spec's "forced screen wrap" requirement).
        width, height = self.app.screen.get_size()
        thrusting, turning = self._craft_intents()
        self._craft.update(thrusting, turning, width, height)
        for asteroid in self._asteroids:
            asteroid.update(width, height)
        # Spec: contact with an asteroid of any radius is instant game over.
        if any(player_hits_asteroid(self._craft, a, width, height)
               for a in self._asteroids):
            self.app.to_game_over()

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(BLACK)
        for asteroid in self._asteroids:
            asteroid.draw(screen)
        self._craft.draw(screen)
