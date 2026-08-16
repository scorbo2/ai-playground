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

    def update(self) -> None:
        """Per-frame simulation step. Stage 1 has no game objects yet, so
        later stages will override this."""

    @abstractmethod
    def draw(self, screen: pygame.Surface) -> None:
        """Render this mode onto ``screen``."""
