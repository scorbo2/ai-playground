"""Fixed-timestep main loop.

Drives a SceneManager (or a plain on_step callback, for backward
compatibility with stage-1 unit tests) at a fixed 1/60 s step with a
bounded accumulator. Real dt is ignored for simulation.
"""

import pygame

# Chicken-and-egg exception per the spec: window size lives in code, not
# in config, to avoid a chicken-and-egg dependency at startup.
SCREEN_SIZE = (1024, 768)
FIXED_DT = 1 / 60
ACCUMULATOR_LIMIT = 5 / 60


class FixedTimestepLoop:
    """Fixed-timestep loop that can drive either a SceneManager or a bare callback."""

    def __init__(self, on_step=None, scene_manager=None, screen=None, screen_size=SCREEN_SIZE):
        """
        Parameters
        ----------
        on_step:
            Optional callable invoked once per fixed step (stage-1 compat).
        scene_manager:
            Optional SceneManager; if supplied, events are routed to it and
            it is updated/drawn each frame.
        screen:
            Existing pygame Surface to use as the display. When omitted a new
            1024×768 surface is created (required for stage-1 unit tests that
            construct the loop directly).
        """
        pygame.init()
        if screen is not None:
            self._screen = screen
        else:
            self._screen = pygame.display.set_mode(screen_size, 0, pygame.SWSURFACE, 0, 0)
        self._on_step = on_step
        self._scene_manager = scene_manager
        self._accumulator = 0.0

    def step(self):
        """Perform one fixed-timestep (1/60 s) simulation update."""
        if self._on_step is not None:
            self._on_step()
        if self._scene_manager is not None:
            self._scene_manager.update()

    def run(self):
        """Run the loop until the window is closed or the scene manager quits."""
        clock = pygame.time.Clock()
        running = True
        while running:
            dt = clock.tick(60) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    if self._scene_manager is not None:
                        self._scene_manager.quit()
                elif self._scene_manager is not None:
                    self._scene_manager.handle_event(event)

            if self._scene_manager is not None and not self._scene_manager.running:
                running = False

            self._accumulator = min(self._accumulator + dt, ACCUMULATOR_LIMIT)
            if self._accumulator >= FIXED_DT:
                self._accumulator -= FIXED_DT
                self.step()

            if self._scene_manager is not None:
                self._scene_manager.draw()

            pygame.display.flip()
