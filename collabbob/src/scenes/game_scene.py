"""The single top-level scene for one play session: tactical view + HUD + world map.

Stage 6 originally modelled the HUD as a second scene pushed onto the stack
above the tactical view. ``SceneManager`` only routes ``handle_event()`` and
``update()`` to the *top* scene, so a passive, input-free overlay on top of the
stack silently swallowed every keystroke and froze the simulation — the whole
game became a screenshot. The HUD draws into a region the tactical view
deliberately never touches, so it is a component of this scene rather than a
scene of its own.

GameScene also owns the session's single :class:`GameState` and hands the same
object to both children, so the HUD can never render a phantom ship while the
simulation runs somewhere else. And it owns the world: the system graph and its
screen layout are generated **once** here, from config, and cached for the rest
of the run — the map modal is a window onto that state, never a source of it.

Modals that take over input (system map, spaceport, game over) are pushed on top
of this scene by their own stages.
"""

from __future__ import annotations

import random as _random_lib
import sys
from typing import TYPE_CHECKING, Tuple

from src.fonts import game_font
from src.hud import HudView
from src.input import Action
from src.map_systems.graph import GraphGenerationError, SystemGraphGenerator
from src.map_systems.layout import build_map_layout
from src.map_systems.system_map import SystemMapState
from src.main_loop import SCREEN_SIZE
from src.model.game_state import GameState
from src.scene_manager import Scene
from src.scenes.map_view import MapView
from src.scenes.tactical_view import TacticalView

if TYPE_CHECKING:
    import pygame

    from src.scene_manager import SceneManager


class GameScene(Scene):
    """Owns the tactical view, the HUD and the world graph for one game."""

    def __init__(self, manager: "SceneManager") -> None:
        super().__init__()
        # The stack also hands us the manager in ``on_enter()``; holding onto the
        # constructor's reference keeps a directly-constructed GameScene (as many
        # unit tests do) able to open modals without a full stack round-trip.
        self._manager = manager
        config = manager.game_config()
        # One ship state, shared by the view that simulates it and the HUD that
        # reports it. Created from the difficulty the player actually picked.
        self.game_state = GameState(config)
        self.tactical = TacticalView(manager, self.game_state)
        self.hud = HudView(manager, self.game_state)
        self.system_map = self._build_system_map(config)

    # ------------------------------------------------------------------
    # The world: generated once per game, then cached
    # ------------------------------------------------------------------
    def _build_system_map(self, config: dict) -> SystemMapState:
        """Generate the world graph and its screen layout exactly once.

        The layout is built here rather than in the modal so "layout computed
        once per game and cached" is a fact about the world, not about how often
        the player presses M.

        The graph gets its **own** seeded :class:`random.Random`, separate from
        ``game_state.rng``: the world topology is a *world seed* (same seed must
        give the same 26 systems and the same connections), and sharing one RNG
        with the starfield/AI draws would make the map depend on how many frames
        of thrust the player happened to log before opening it.
        """
        try:
            generator = SystemGraphGenerator.from_config(
                config["map"], rng=_random_lib.Random(config.get("rng", {}).get("seed"))
            )
            graph = generator.generate()
            layout = build_map_layout(
                graph, SCREEN_SIZE, measure=lambda text, size: game_font(size).size(text)
            )
        except (GraphGenerationError, KeyError, TypeError) as exc:
            # A bad `map` config section is a data error, not a crash to debug at
            # runtime: report it the way a config failure is reported everywhere
            # else (stderr + exit) rather than opening a half-built world.
            print(f"error: cannot build the system map from config: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        return SystemMapState(graph=graph, layout=layout)

    # ------------------------------------------------------------------
    # Events / update
    # ------------------------------------------------------------------
    def handle_event(self, event) -> None:
        """All gameplay input belongs to the tactical view; the HUD is read-only."""
        self.tactical.handle_event(event)

    def update(self) -> Tuple[Action, ...]:
        """Advance the simulation and return any discrete actions produced.

        ``open_map`` (pressing M) raises the system-map modal, unless a jump is
        animating — the spec blocks the map during a jump. Returning the actions
        keeps this scene's reaction to discrete input testable without driving
        the whole stack.
        """
        actions = self.tactical.update()
        for action in actions:
            if action.kind == "open_map":
                self._open_system_map()
        return tuple(actions)

    def draw(self, surface: "pygame.Surface") -> None:
        """Draw the tactical view and HUD, after syncing the HUD's nav seam.

        The sync lives here rather than in ``update()`` because ``update()`` is
        not called while a modal is on top of the stack, yet ``draw()`` always is
        — so a destination chosen on the map would otherwise only appear on the
        HUD after the modal closed.
        """
        self.hud.nav_selected_name = self.system_map.selected_system
        self.tactical.draw(surface)
        self.hud.draw(surface)

    def _open_system_map(self) -> None:
        """Push the system-map modal, except while a jump is in progress.

        No "is the map already open" guard is needed: only the top scene of the
        stack is updated, so this method cannot run while the modal is up.
        """
        if self.game_state.is_jumping:
            return
        self._manager.push(MapView(self.system_map))
