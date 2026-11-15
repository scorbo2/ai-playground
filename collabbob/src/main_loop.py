"""Fixed-timestep main loop (stage 1 skeleton).

The simulation is locked to a fixed 1/60 step with a bounded accumulator;
real dt is ignored. The step body is a no-op until later stages add the
game logic, and the window is created before the loop starts.
"""

import pygame

# Chicken-and-egg exception per the spec: these are fixed before the game
# config is loaded, so they live in code rather than in the config files.
SCREEN_SIZE = (1024, 768)
FIXED_DT = 1 / 60
ACCUMULATOR_LIMIT = 5 / 60


class FixedTimestepLoop:
    """Minimal fixed-timestep loop around a no-op step body."""

    def __init__(self, on_step, screen_size=SCREEN_SIZE):
        pygame.init()
        pygame.display.set_mode(screen_size, 0, pygame.SWSURFACE, 0, 0)
        self._on_step = on_step
        self._accumulator = 0.0

    def step(self):
        """Perform one fixed-timestep (1/60s) simulation update."""
        if self._on_step is not None:
            self._on_step()

    def run(self):
        """Run the loop forever, advancing a bounded accumulator per step."""
        while True:
            self._accumulator = min(self._accumulator + FIXED_DT, ACCUMULATOR_LIMIT)
            if self._accumulator >= FIXED_DT:
                self._accumulator -= FIXED_DT
                self.step()
            pygame.display.flip()
