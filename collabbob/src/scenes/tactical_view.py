"""Tactical game-view scene (Stage 4).

Renders the left-hand game area: a black background, a procedurally drawn and
rotated blocky cargo shuttle centred on the player's ship, the system planet at
the world origin, and a recycling starfield that scrolls with player movement.
The right-hand HUD region is filled in by Stage 6.

The tactical display fills the whole screen; the game view occupies the left two
thirds (683 px) and the window's centre of mass sits on the planet. The scene
clears the entire surface each frame, so it correctly layers over any scene
beneath it in the stack.
"""

from __future__ import annotations

import math

import pygame

from src.camera import world_to_screen
from src.input import Action, InputLayer
from src.model.game_state import GameState
from src.model.starfield import Starfield
from src.scene_manager import Scene

SCREEN_SIZE = (1024, 768)
# The game view is the left two thirds of a 1024-wide window; HUD takes the rest.
VIEW_WIDTH = 683
_VIEW_CENTER = (VIEW_WIDTH / 2.0, SCREEN_SIZE[1] / 2.0)

_BG = (0, 0, 0)
_PLANET_COLORS = [(90, 160, 90), (150, 110, 70), (110, 90, 140)]


class TacticalView(Scene):
    """Full-screen tactical display with game view + planet + starfield."""

    def __init__(self, manager: "SceneManager") -> None:
        """Build the tactical view with its game state and cached ship sprite."""
        super().__init__()
        self._manager = manager
        # The input layer sits between raw pygame events and the simulation.
        self.input = InputLayer()
        self.configs = manager.configs["config_easy.json"]
        self.game_state = GameState(self.configs)
        self.starfield = Starfield(
            count=int(self.configs["tactical"]["stars"]["count"]),
            half_extent=VIEW_WIDTH / 2.0,
            rng=self.game_state.rng,
        )
        # Cached, unrotated blocky shuttle drawn at the ship's length/width.
        self._ship_surface = self._build_ship_surface()

    def on_enter(self, manager) -> None:
        super().on_enter(manager)

    def on_exit(self) -> None:
        super().on_exit()

    # ------------------------------------------------------------------
    # Event + update plumbing (Stage 5 input layer)
    # ------------------------------------------------------------------
    def handle_event(self, event) -> None:
        """Route every pygame event into the input layer for later draining."""
        self.input.feed_event(event)

    def update(self) -> None:
        """Drain one frame: feed ship controls and advance the simulation."""
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
        for action in actions:
            self.on_action(action)

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
        surface.fill(_BG)
        self._draw_game_view(surface)

    def _draw_game_view(self, surface: "pygame.Surface") -> None:
        self._draw_stars(surface)
        self._draw_planet(surface)
        self._draw_ship(surface)

    def _draw_stars(self, surface: "pygame.Surface") -> None:
        for star in self.starfield.stars:
            screen_pos = world_to_screen(star.x, star.y, _VIEW_CENTER)
            sx, sy = int(round(screen_pos[0])), int(round(screen_pos[1]))
            if 0 <= sx < VIEW_WIDTH and 0 <= sy < SCREEN_SIZE[1]:
                surface.set_at((sx, sy), star.color)

    def _draw_planet(self, surface: "pygame.Surface") -> None:
        """Planet sits at the world origin, i.e. the centre of the game view."""
        diameter = float(self.configs["tactical"]["planet_diameter"])
        # Deterministic colour pick so the planet looks consistent within a game.
        color = _PLANET_COLORS[int(diameter) % len(_PLANET_COLORS)]
        center = _VIEW_CENTER
        radius = diameter / 2.0
        pygame.draw.circle(surface, color, (int(round(center[0])), int(round(center[1]))), int(radius))

    def _draw_ship(self, surface: "pygame.Surface") -> None:
        wx, wy = self.game_state.position
        screen_pos = world_to_screen(wx, wy, _VIEW_CENTER)
        rotated = pygame.transform.rotate(
            self._ship_surface, math.radians(self.game_state.heading_degrees)
        )
        rect = rotated.get_rect(center=screen_pos)
        surface.blit(rotated, rect)

    # ------------------------------------------------------------------
    # Ship sprite construction
    # ------------------------------------------------------------------
    def _build_ship_surface(self) -> "pygame.Surface":
        """Procedurally draw a blocky cargo shuttle centred on its body."""
        length = float(self.configs["player_ship"]["length"])
        width = float(self.configs["player_ship"]["width"])
        surface = pygame.Surface((int(length), int(width)), pygame.SRCALPHA)

        # Main fuselage (blocky, rectangular-ish).
        pygame.draw.rect(surface, (180, 180, 190),
                         (0, int(width) // 4, int(length), int(width) // 2))
        # Nose cone / cockpit block.
        nose = max(6, int(length) // 4)
        pygame.draw.rect(surface, (150, 210, 230), (int(length) - nose, 0, nose, int(width)))
        # Rear wings.
        wing_h = max(4, int(width) // 2)
        pygame.draw.rect(surface, (120, 120, 130), (int(length) * 3 // 4, 0, wing_h, wing_h))
        pygame.draw.rect(surface, (120, 120, 130), (int(length) * 3 // 4, int(width) - wing_h, wing_h, wing_h))
        return surface
