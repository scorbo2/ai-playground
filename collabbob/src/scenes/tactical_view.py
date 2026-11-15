"""Tactical game-view scene (Stage 4+).

Renders the left-hand game area: a black background, a procedurally drawn and
rotated blocky cargo shuttle, the system planet, and a starfield that scrolls
with player movement. The right-hand third of the window belongs to the HUD
component (see :mod:`src.hud`), so this scene deliberately clears only its own
region — and it never draws beneath the HUD.

The camera is locked to the player's ship: the ship is pinned to the centre of
the game view and the world (planet, stars) slides past it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from src.camera import world_to_screen
from src.hud import landing_prompt_text
from src.input import Action, InputLayer
from src.model.game_state import GameState
from src.model.starfield import Starfield
from src.overlays import MessageOverlay
from src.scene_manager import Scene

if TYPE_CHECKING:
    from src.scene_manager import SceneManager

SCREEN_SIZE = (1024, 768)
# The game view is the left two thirds of a 1024-wide window; HUD takes the rest.
VIEW_WIDTH = 683
_VIEW_CENTER = (VIEW_WIDTH / 2.0, SCREEN_SIZE[1] / 2.0)

# Only the left game-view region is cleared here each frame. The right-hand HUD
# is drawn by a sibling component of GameScene, which owns that region; wiping
# the whole surface would clobber it.
_GAME_VIEW_RECT = pygame.Rect(0, 0, VIEW_WIDTH, SCREEN_SIZE[1])

# Each system's planet sits at the world origin (see src.model.game_state).
PLANET_WORLD_POSITION = (0.0, 0.0)

_BG = (0, 0, 0)
_PLANET_COLORS = [(90, 160, 90), (150, 110, 70), (110, 90, 140)]


class TacticalView:
    """Game view + planet + starfield + message overlay for one solar system.

    This is a component of :class:`~src.scenes.game_scene.GameScene`, not a
    scene-stack entry: GameScene owns the single :class:`GameState` and forwards
    input here, so a passive component (the HUD) can never sit on top of the
    stack and swallow the player's keystrokes.
    """

    def __init__(self, manager: "SceneManager", game_state: GameState) -> None:
        """Build the tactical view with its ship state and cached ship sprite."""
        if game_state is None:
            raise ValueError("TacticalView requires the GameState it will simulate")
        self._manager = manager
        # The input layer sits between raw pygame events and the simulation.
        self.input = InputLayer()
        # Difficulty comes from the player's selection, never a fixed filename.
        self.configs = manager.game_config()
        self.game_state = game_state
        self.overlays = MessageOverlay(_GAME_VIEW_RECT)
        # Stars live in view space and are scrolled by the ship's velocity, so
        # the box must cover the taller axis of the view or the top and bottom
        # of the game view would be star-free.
        self.starfield = Starfield(
            count=int(self.configs["tactical"]["stars"]["count"]),
            half_extent=max(VIEW_WIDTH, SCREEN_SIZE[1]) / 2.0,
            rng=self.game_state.rng,
        )
        # Cached, unrotated blocky shuttle drawn at the ship's length/width.
        self._ship_surface = self._build_ship_surface()

    # ------------------------------------------------------------------
    # Event + update plumbing (Stage 5 input layer)
    # ------------------------------------------------------------------
    def handle_event(self, event) -> None:
        """Route every pygame event into the input layer for later draining."""
        self.input.feed_event(event)

    def update(self) -> "list[Action]":
        """Drain one frame: feed ship controls and advance the simulation.

        Returns the discrete actions produced this frame (empty when none fired)
        so the owning scene can react to them - an ``open_map`` action raises the
        system map. Callers that ignore actions may discard the result.
        """
        control_frame, actions = self.input.drain_frame()
        if control_frame is not None:
            self.game_state.feed_input(
                thrust=control_frame.thrust,
                left=control_frame.left,
                right=control_frame.right,
                reverse_edge=control_frame.reverse_edge,
            )
        # Advance the pure model by exactly one fixed timestep.
        self.game_state.advance_frame()

        # The camera is pinned to the ship, so the background must be scrolled
        # by the ship's velocity each frame (spec: rightward flight moves the
        # stars left at the same rate).
        vx, vy = self.game_state.velocity
        self.starfield.update(vx, vy)

        self._update_landing_prompt()
        self.overlays.update()

        for action in actions:
            self.on_action(action)

        return actions

    def show_message(self, text: str, duration_frames: int = 180) -> None:
        """Overlay a transient message on the game view (Stages 8/11 use this)."""
        self.overlays.show(text, duration_frames)

    def _update_landing_prompt(self) -> None:
        """Keep the landing prompt visible while the ship is in landing range."""
        planet_x, planet_y = PLANET_WORLD_POSITION
        distance = self.game_state.distance_from_point(planet_x, planet_y)
        prompt = landing_prompt_text(distance, self.game_state.landing_range)
        self.overlays.set_sticky(prompt)

    def on_action(self, action: Action) -> None:
        """Dispatch a discrete action from the input layer.

        Stage 5 registers the bindings here. Firing produces no projectile yet;
        the other bindings are accepted so later stages can wire handlers
        without re-registering them.
        """
        if action.kind == "fire":
            self._on_fire()
        else:
            # open_map / jump / land / scan / exit_game are registered but
            # handled in their owning stages; nothing to do yet.
            pass

    def _on_fire(self) -> None:
        """Record a fired shot. Projectile generation is added in Stage 11."""
        # Intentionally empty for now: space fires without creating a projectile.
        pass

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self, surface: "pygame.Surface") -> None:
        # Only clear the left game-view region so the sibling HudView component's
        # right-third HUD is not wiped each frame.
        surface.fill(_BG, _GAME_VIEW_RECT)
        self._draw_game_view(surface)

    def _draw_game_view(self, surface: "pygame.Surface") -> None:
        self._draw_stars(surface)
        self._draw_planet(surface)
        self._draw_ship(surface)
        self.overlays.draw(surface)

    def _draw_stars(self, surface: "pygame.Surface") -> None:
        """Stars are single pixels in view space, culled to the game-view rect."""
        for star in self.starfield.stars:
            sx = int(round(_VIEW_CENTER[0] + star.x))
            sy = int(round(_VIEW_CENTER[1] + star.y))
            if 0 <= sx < VIEW_WIDTH and 0 <= sy < SCREEN_SIZE[1]:
                surface.set_at((sx, sy), star.color)

    def _draw_planet(self, surface: "pygame.Surface") -> None:
        """Planet sits at the world origin, so the camera slides it around."""
        diameter = float(self.configs["tactical"]["planet_diameter"])
        # Deterministic colour pick so the planet looks consistent within a game.
        color = _PLANET_COLORS[int(diameter) % len(_PLANET_COLORS)]
        screen_pos = world_to_screen(
            PLANET_WORLD_POSITION[0], PLANET_WORLD_POSITION[1],
            self.game_state.position, _VIEW_CENTER,
        )
        pygame.draw.circle(surface, color, (int(round(screen_pos[0])), int(round(screen_pos[1]))),
                           int(diameter / 2.0))

    def _draw_ship(self, surface: "pygame.Surface") -> None:
        """The player's ship is always drawn at the centre of the game view."""
        rotated = pygame.transform.rotate(self._ship_surface, -self.game_state.heading_degrees)
        rect = rotated.get_rect(center=_VIEW_CENTER)
        surface.blit(rotated, rect)

    # ------------------------------------------------------------------
    # Ship sprite construction
    # ------------------------------------------------------------------
    def _build_ship_surface(self) -> "pygame.Surface":
        """Procedurally draw a blocky cargo shuttle centred on its body.

        The nose must stay visible: it is the only cue the player has that the
        ship is facing a given way. An earlier revision drew the rear wings at
        ``3 * length / 4``, which is exactly where the nose block started, so the
        wings painted the nose out completely and every heading looked identical.
        """
        length = int(self.configs["player_ship"]["length"])
        width = int(self.configs["player_ship"]["width"])
        surface = pygame.Surface((length, width), pygame.SRCALPHA)

        # Main fuselage (blocky, rectangular-ish).
        pygame.draw.rect(surface, (180, 180, 190), (0, width // 4, length, width // 2))
        # Rear wings, aft quarter: one block above and one below the fuselage.
        wing_w = max(4, length // 8)
        wing_h = max(4, width // 2)
        wing_x = length // 4
        pygame.draw.rect(surface, (120, 120, 130), (wing_x, 0, wing_w, wing_h))
        pygame.draw.rect(surface, (120, 120, 130), (wing_x, width - wing_h, wing_w, wing_h))
        # Nose cone / cockpit block, drawn last so it is never occluded
        # (the nose points along +x == heading 0).
        nose = max(6, length // 4)
        pygame.draw.rect(surface, (150, 210, 230), (length - nose, 0, nose, width))
        return surface
