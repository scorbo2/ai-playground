"""The single top-level scene for one play session: tactical view + HUD.

Stage 6 originally modelled the HUD as a second scene pushed onto the stack
above the tactical view. ``SceneManager`` only routes ``handle_event()`` and
``update()`` to the *top* scene, so a passive, input-free overlay on top of the
stack silently swallowed every keystroke and froze the simulation — the whole
game became a screenshot. The HUD draws into a region the tactical view
deliberately never touches, so it is a component of this scene rather than a
scene of its own.

GameScene also owns the one :class:`GameState` for the session and hands the same
object to both children, so the HUD can never render a phantom ship while the
simulation runs somewhere else. Modals that take over input (system map,
spaceport, game over) are pushed on top of this scene by their own stages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.hud import HudView
from src.model.game_state import GameState
from src.scene_manager import Scene
from src.scenes.tactical_view import TacticalView

if TYPE_CHECKING:
    import pygame

    from src.scene_manager import SceneManager


class GameScene(Scene):
    """Owns the tactical view and the HUD for the duration of one game."""

    def __init__(self, manager: "SceneManager") -> None:
        super().__init__()
        # One ship state, shared by the view that simulates it and the HUD that
        # reports it. Created from the difficulty the player actually picked.
        self.game_state = GameState(manager.game_config())
        self.tactical = TacticalView(manager, self.game_state)
        self.hud = HudView(manager, self.game_state)

    def handle_event(self, event) -> None:
        """All gameplay input belongs to the tactical view; the HUD is read-only."""
        self.tactical.handle_event(event)

    def update(self) -> None:
        """Advance the simulation exactly one fixed timestep."""
        self.tactical.update()

    def draw(self, surface: "pygame.Surface") -> None:
        """Draw the game view, then the HUD on top of the cleared right third."""
        self.tactical.draw(surface)
        self.hud.draw(surface)
