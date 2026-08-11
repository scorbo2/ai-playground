#!/usr/bin/env python3
"""
PlayerCraft - the player's spaceship.

An elongated triangle (20×30 px) with white outline and light gray fill.
The craft rotates, thrusts, and wraps around screen edges. A 20 px radius
bounding circle governs all collision checks.

Stage 3: movement, screen wrap, and shield-ring collision.
"""

from __future__ import annotations

import math
import random
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from ShieldRing import ShieldRing

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CRAFT_WIDTH: int = 20
CRAFT_HEIGHT: int = 30
CRAFT_BOTTON_COLOR: tuple[int, int, int] = (200, 200, 200)  # light gray
CRAFT_OUTLINE_COLOR: tuple[int, int, int] = (255, 255, 255)  # white
CRAFT_BOUNDING_RADIUS: int = 20

ROTATION_SPEED: float = 5.0          # degrees per frame
THRUST_ACCEL: float = 0.3            # px/frame²
MAX_SPEED: float = 8.0               # px/frame
FRICTION: float = 0.98               # multiplicative when not thrusting

SHIELD_COLLISION_THRESHOLD: int = 20  # px — craft destroyed if within this
                                      # distance of any active shield segment


class PlayerCraft:
    """The player-controlled spaceship.

    Attributes
    ----------
    x, y : float
        Centre coordinates in screen space.
    vx, vy : float
        Velocity components in px/frame.
    angle : float
        Facing angle in degrees (0 = up, positive = clockwise).
    destroyed : bool
        ``True`` once the craft has been destroyed.
    """

    def __init__(self, x: float, y: float) -> None:
        """Create a craft at *x*, *y* facing straight up.

        Parameters
        ----------
        x, y:
            Initial screen coordinates of the craft centre.
        """
        self.x: float = x
        self.y: float = y
        self.vx: float = 0.0
        self.vy: float = 0.0
        self.angle: float = 0.0
        self.destroyed: bool = False

        # Triangle vertices in local (unrotated) coords: nose at top.
        # nose is CRAFT_HEIGHT // 2 pixels above center.
        half_w = CRAFT_WIDTH // 2
        half_h = CRAFT_HEIGHT // 2
        self._triangle: list[tuple[float, float]] = [
            (0, -half_h),                       # nose
            (-half_w, half_h),                   # bottom-left
            (half_w, half_h),                    # bottom-right
        ]

        # Cached rotated surface — rebuilt whenever angle crosses a degree
        # boundary to avoid per-frame surface allocation.
        self._rotated_surface: pygame.Surface | None = None
        self._last_angle: int = 0

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _build_surface(self) -> pygame.Surface:
        """Create (or rebuild) the rotated triangle surface.

        The triangle is centred on the surface so that rotation pivots
        around the craft's centre point.

        Returns
        -------
        pygame.Surface
            A surface large enough to hold the rotated triangle, with the
            triangle centred and ready for blitting.
        """
        # The bounding box of the rotated triangle is always the same
        # size as the craft itself (20×30).
        surface = pygame.Surface((CRAFT_WIDTH, CRAFT_HEIGHT), pygame.SRCALPHA)
        surface_cx = CRAFT_WIDTH / 2
        surface_cy = CRAFT_HEIGHT / 2

        # Pygame rotates counter-clockwise, but our angle is clockwise,
        # so negate it.  The triangle vertices are already centred at
        # (0, 0) in local coords, so we rotate around the origin and
        # then offset by the surface centre.
        rotated: list[tuple[float, float]] = []
        for vx, vy in self._triangle:
            r = pygame.math.Vector2(vx, vy).rotate(-self.angle)
            rotated.append((r.x + surface_cx, r.y + surface_cy))

        pygame.draw.polygon(surface, CRAFT_OUTLINE_COLOR, rotated, 1)
        pygame.draw.polygon(surface, CRAFT_BOTTON_COLOR, rotated)

        return surface

    def render(self, surface: pygame.Surface) -> None:
        """Draw the craft on *surface* at its current position.

        Parameters
        ----------
        surface:
            Target display surface.
        """
        angle_int = int(round(self.angle)) % 360

        if self._rotated_surface is None or angle_int != self._last_angle:
            self._rotated_surface = self._build_surface()
            self._last_angle = angle_int

        rect = self._rotated_surface.get_rect(center=(self.x, self.y))
        surface.blit(self._rotated_surface, rect)

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def handle_input(self, keys: pygame.key.ScancodeWrapper) -> None:
        """Process keyboard input and update rotation / thrust.

        Parameters
        ----------
        keys:
            Result of ``pygame.key.get_pressed()``.
        """
        # Rotation
        if keys[pygame.K_LEFT]:
            self.angle -= ROTATION_SPEED
        if keys[pygame.K_RIGHT]:
            self.angle += ROTATION_SPEED

        # Normalise to [0, 360) to keep floating-point drift in check.
        self.angle %= 360.0

        # Thrust
        if keys[pygame.K_UP]:
            a = math.radians(self.angle)
            # Facing direction: 0° = up = (0, -1) in pygame coords.
            # Clockwise rotation: facing = (sin(a), -cos(a)).
            self.vx += THRUST_ACCEL * math.sin(a)
            self.vy -= THRUST_ACCEL * math.cos(a)

            # Clamp to max speed
            speed = math.hypot(self.vx, self.vy)
            if speed > MAX_SPEED:
                scale = MAX_SPEED / speed
                self.vx *= scale
                self.vy *= scale

    # ------------------------------------------------------------------
    # Movement
    # ------------------------------------------------------------------

    def move(self, screen_width: int, screen_height: int) -> None:
        """Advance position by velocity and apply screen wrap.

        Parameters
        ----------
        screen_width:
            Width of the display in pixels.
        screen_height:
            Height of the display in pixels.
        """
        # Apply friction when not thrusting (thrust state is consumed by
        # handle_input, so we infer it here by checking speed).
        # Actually — friction should apply when the player released UP.
        # We track this by checking if speed is decreasing.
        # Better: apply friction every frame, thrust adds to velocity,
        # friction always reduces it (unless thrusting).
        #
        # The spec says "when the up arrow key is released, apply linear
        # friction of 0.98 per frame".  This means friction only applies
        # when NOT thrusting.  We'll handle this in the game loop by
        # calling apply_friction() when the up key is not pressed.
        # For simplicity, apply friction here unconditionally — the game
        # loop will call apply_friction() separately when thrusting is off.
        #
        # Actually, to keep this class self-contained, let's not apply
        # friction here. The game loop will call apply_friction() when
        # appropriate.  This method only moves and wraps.

        self.x += self.vx
        self.y += self.vy

        # Screen wrap
        if self.x < -CRAFT_BOUNDING_RADIUS:
            self.x = screen_width + CRAFT_BOUNDING_RADIUS
        elif self.x > screen_width + CRAFT_BOUNDING_RADIUS:
            self.x = -CRAFT_BOUNDING_RADIUS
        if self.y < -CRAFT_BOUNDING_RADIUS:
            self.y = screen_height + CRAFT_BOUNDING_RADIUS
        elif self.y > screen_height + CRAFT_BOUNDING_RADIUS:
            self.y = -CRAFT_BOUNDING_RADIUS

    def apply_friction(self) -> None:
        """Apply linear friction to gradually slow the craft.

        Multiplies velocity by ``FRICTION`` (0.98) per frame.  If the
        resulting speed is below 0.01, velocity is zeroed entirely to
        avoid floating-point noise keeping the craft drifting.
        """
        self.vx *= FRICTION
        self.vy *= FRICTION

        speed = math.hypot(self.vx, self.vy)
        if speed < 0.01:
            self.vx = 0.0
            self.vy = 0.0

    # ------------------------------------------------------------------
    # Collision detection
    # ------------------------------------------------------------------

    def check_shield_collision(
        self,
        shield_rings: list[ShieldRing],
        fortress_cx: int,
        fortress_cy: int,
    ) -> bool:
        """Check whether the craft's bounding circle intersects any
        active shield segment.

        The craft is considered destroyed if its centre comes within
        :data:`SHIELD_COLLISION_THRESHOLD` px of any active segment on
        any ring.

        Parameters
        ----------
        shield_rings:
            The three concentric shield rings.
        fortress_cx, fortress_cy:
            Screen coordinates of the fortress (ring) centre.

        Returns
        -------
        bool
            ``True`` if the craft collided with an active shield segment.
        """
        for ring in shield_rings:
            if ring.contains_point(
                self.x, self.y, fortress_cx, fortress_cy
            ):
                return True
        return False

    def check_fortress_collision(
        self,
        fortress_cx: int,
        fortress_cy: int,
        fortress_width: int,
    ) -> bool:
        """Check whether the craft's bounding circle intersects the
        fortress's bounding circle.

        The fortress's collision circle has a diameter equal to its
        sprite width (radius = width / 2).

        Parameters
        ----------
        fortress_cx, fortress_cy:
            Screen coordinates of the fortress centre.
        fortress_width:
            Width of the fortress sprite in pixels.

        Returns
        -------
        bool
            ``True`` if the craft collided with the fortress.
        """
        fortress_radius = fortress_width / 2.0
        dist = math.hypot(self.x - fortress_cx, self.y - fortress_cy)
        return dist < (CRAFT_BOUNDING_RADIUS + fortress_radius)

    # ------------------------------------------------------------------
    # Destruction
    # ------------------------------------------------------------------

    def destroy(self) -> None:
        """Mark the craft as destroyed and reset to a stationary state."""
        self.destroyed = True
        self.vx = 0.0
        self.vy = 0.0
        # Invalidate cached surface so nothing gets drawn.
        self._rotated_surface = None
        self._last_angle = -1  # sentinel — will trigger rebuild on next render
