"""Base class for the game's mode states."""

from abc import ABC, abstractmethod

import pygame


class GameModeState(ABC):
    """One mode in the SuperAsteroids state machine
    (Title Screen, Game, Pause, Game Over).

    A mode never references other states directly. Transitions are requested
    through the app (``self.app.to_title()`` and friends), which owns the
    display and knows the current mode - this keeps the state graph explicit
    in a single place and avoids circular imports between state modules.
    """

    def __init__(self, app):
        self.app = app

    @abstractmethod
    def handle_events(self, events: list) -> None:
        """Process pygame events for this mode. May trigger a mode change
        or terminate the application."""

    def on_pause(self) -> None:
        """Hook the app calls the moment this state is frozen by
        ``to_pause()`` - whichever path froze it (ESC key or programmatic).
        States must leave themselves safely restorable here, e.g. by
        dropping transient input state that could resume stale."""

    def update(self) -> None:
        """Per-frame simulation step. The default is a no-op; states that
        own game objects (asteroids, later the ship and weapons) override
        it to advance the simulation."""

    @abstractmethod
    def draw(self, screen: pygame.Surface) -> None:
        """Render this mode onto ``screen``."""
