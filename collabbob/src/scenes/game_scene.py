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

import pygame

from src.effects import FlashOverlay
from src.fonts import game_font
from src.hud import VIEW_WIDTH, HudView
from src.input import Action
from src.map_systems.graph import GraphGenerationError, SystemGraphGenerator
from src.map_systems.layout import build_map_layout
from src.map_systems.system_map import SystemMapState
from src.main_loop import SCREEN_SIZE
from src.model.game_state import GameState
from src.model.jump import (
    BLOCKED_EXACT_FUEL,
    EVENT_ARRIVED,
    EVENT_JUMP_ENDED,
    EVENT_TRANSITION_STARTED,
    JumpController,
    JumpParams,
)
from src.scene_manager import Scene
from src.scenes.map_view import MapView
from src.scenes.tactical_view import TacticalView

if TYPE_CHECKING:
    from src.scene_manager import SceneManager

# "briefly overlay an 'insufficient fuel' message" — two seconds, no more.
JUMP_DENIED_MESSAGE_FRAMES = 120


def _gameplay_rng(config: dict) -> "_random_lib.Random | None":
    """The session's gameplay RNG: starfields, jump arrival bearings, and soon NPCs.

    Seeded from ``rng.seed`` when one is set, so a seeded run reproduces its skies
    and its arrival points as well as its map. Deliberately a *separate* generator
    from the world-graph one: the topology must come out identical no matter how
    many frames of flight or how many jumps the player burns through first, so the
    two streams can never share a cursor. Same seed, two independent streams — the
    Stage 7 note about threading a single RNG through the whole game is still open.

    Returns None (GameState then makes an unseeded RNG of its own) when no seed is
    configured, which is how the game ships.
    """
    seed = config.get("rng", {}).get("seed")
    return None if seed is None else _random_lib.Random(seed)


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
        self.game_state = GameState(config, rng=_gameplay_rng(config))
        self.tactical = TacticalView(manager, self.game_state)
        self.hud = HudView(manager, self.game_state)
        self.system_map = self._build_system_map(config)
        # The jump sequence is owned here because it is the only thing that
        # needs the ship *and* the world at the same time.
        self.jumps = JumpController(
            game_state=self.game_state,
            map_state=self.system_map,
            params=JumpParams.from_config(config["tactical"]),
        )
        # The flash covers the whole window, HUD included, so it is drawn by the
        # scene that draws last — a flash that politely skipped the right-hand
        # third would read as a rendering bug, not as drama. The shockwave does
        # start at the ship, though: the centre of the game view.
        self.screen_flash = FlashOverlay(
            pygame.Rect(0, 0, *SCREEN_SIZE),
            origin=(VIEW_WIDTH / 2.0, SCREEN_SIZE[1] / 2.0),
        )
        # Stage 13 seam: see _request_jump. Public so the flow tests can assert
        # on it without reaching into private state.
        self.pending_game_over = False

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
        """Advance the simulation, drive the jump, return this frame's actions.

        ``open_map`` (pressing M) raises the system-map modal, unless a jump is
        animating — the spec blocks the map during a jump. ``jump`` (pressing J)
        runs the eligibility rules. Returning the actions keeps this scene's
        reaction to discrete input testable without driving the whole stack.
        """
        actions = self.tactical.update()
        for action in actions:
            if action.kind == "open_map":
                self._open_system_map()
            elif action.kind == "jump":
                self._request_jump()
        self._advance_jump()
        self._sync_jump_presentation()
        return tuple(actions)

    def _sync_jump_presentation(self) -> None:
        """Hand the current jump phase to the view and the HUD.

        This lives with ``update()`` rather than with ``draw()`` (unlike the HUD's
        nav line) because the jump sequence only advances in ``update()`` — and
        the tactical view *consumes* the presentation during its own update, to
        drive the warp tunnel's intensity. Syncing at draw time would leave every
        consumer one frame stale; syncing the nav line at draw time is correct for
        the opposite reason, since it changes while ``update()`` is not running
        (the map modal is on top of the stack). Each seam syncs where its state
        actually changes.
        """
        self.hud.is_jumping = self.jumps.is_active
        self.tactical.jump = self.jumps.presentation()

    # ------------------------------------------------------------------
    # Jumping (Stage 8)
    # ------------------------------------------------------------------
    def _request_jump(self) -> None:
        """Handle J: start the sequence, or show why it cannot start.

        Silence is a valid answer: the spec says J "does nothing" when no
        system is selected, so only the blockers that carry copy say anything.
        """
        outcome = self.jumps.request()
        if outcome.started:
            # Two locks, on purpose: the input layer stops the player steering,
            # and ``GameState.is_jumping`` blocks the map and lets the ship
            # ignore the system boundary.
            self.tactical.input.lock_input()
            self._manager.audio.play_jump_spinup()
            return

        if outcome.blocker == BLOCKED_EXACT_FUEL:
            # Spec special case: J with *exactly* the jump's fuel cost is an
            # immediate game over, with no animation. Stage 8 owns the half it
            # can see (no jump, no fuel spent); Stage 13 turns this flag into
            # the game-over screen. Flagged rather than silently implemented so
            # the seam is not mistaken for the whole rule.
            self.pending_game_over = True
        if outcome.message:
            self.tactical.show_message(outcome.message, JUMP_DENIED_MESSAGE_FRAMES)

    def _advance_jump(self) -> None:
        """Tick the jump sequence and the flash, reacting to phase boundaries.

        The flash is advanced *before* the controller so the frame a phase
        begins on is frame 1 for both counters. Ticking them in the other order
        offsets the white-out from the world swap by a frame, and the player
        watches the universe teleport instead of arriving.
        """
        self.screen_flash.advance()
        event = self.jumps.advance()
        if event is None:
            return

        if event.kind == EVENT_TRANSITION_STARTED:
            self.screen_flash.begin(self.jumps.params.transition_frames)
            self._manager.audio.play_thunderclap()
        elif event.kind == EVENT_ARRIVED:
            # Stage 10's NPC despawn hooks in here too: every ship in the system
            # the player just left is gone, and the new system rolls its own.
            self.tactical.notify_system_changed(event.system)
        elif event.kind == EVENT_JUMP_ENDED:
            self.tactical.input.unlock_input()

    def draw(self, surface: "pygame.Surface") -> None:
        """Draw the tactical view, the HUD, then the screen flash over both.

        The HUD's nav sync lives here rather than in ``update()`` because
        ``update()`` is not called while a modal is on top of the stack, yet
        ``draw()`` always is — so a destination chosen on the map would
        otherwise only appear on the HUD after the modal closed. The jump
        presentation syncs in ``update()`` instead: see
        :meth:`_sync_jump_presentation`.
        """
        self.hud.nav_selected_name = self.system_map.selected_system
        self.tactical.draw(surface)
        self.hud.draw(surface)
        self.screen_flash.draw(surface)

    def _open_system_map(self) -> None:
        """Push the system-map modal, except while a jump is in progress.

        Mid-jump the player has already paid for the trip and cannot steer, so a
        map would offer them a destination they cannot act on.

        No "is the map already open" guard is needed: only the top scene of the
        stack is updated, so this method cannot run while the modal is up.
        """
        if self.game_state.is_jumping:
            return
        self._manager.push(MapView(self.system_map))
