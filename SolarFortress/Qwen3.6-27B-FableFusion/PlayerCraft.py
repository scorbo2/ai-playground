#!/usr/bin/env python3
"""
PlayerCraft — the player-controlled spaceship.

Handles rendering (elongated triangle), rotation, thrust physics,
screen wrapping, and exposes its position for collision detection.
"""

from __future__ import annotations

import math
import logging
import random

import pygame

logger = logging.getLogger("solar_fortress.playercraft")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Rotation speed in degrees per frame (left/right arrow keys)
ROTATION_SPEED_DEG: float = 5.0

# Thrust acceleration in pixels/frame² when up arrow is held
THRUST_ACCELERATION: float = 0.3

# Maximum speed in pixels/frame
MAX_SPEED: float = 8.0

# Friction factor applied each frame when thrust is released
# (0.98 = lose 2% of velocity per frame)
FRICTION_FACTOR: float = 0.98

# Bounding circle radius for collision detection
COLLISION_RADIUS: int = 20

# Distance from center to the ship's tip (projectile spawn point)
SHIP_TIP_OFFSET: float = 15.0

# Colors
COLOR_WHITE: tuple[int, int, int] = (255, 255, 255)
COLOR_LIGHT_GRAY: tuple[int, int, int] = (192, 192, 192)


class PlayerCraft:
    """The player-controlled spaceship.

    The craft is rendered as an elongated triangle with a white outline
    and light gray fill. It rotates with left/right arrows, thrusts
    forward with up arrow, and wraps around screen edges.

    Angle convention: 0° = pointing up (negative Y), positive = clockwise.
    """

    def __init__(self, width: int, height: int) -> None:
        """Create a new player craft at a random spawn location.

        The craft spawns within 100px of a random screen edge to ensure
        it starts away from the central fortress.

        Parameters
        ----------
        width :
            Current display width (for spawn position and screen wrap).
        height :
            Current display height.
        """
        self._width = width
        self._height = height

        # Spawn position: random point within 100px of a screen edge
        self._x, self._y = self._random_edge_position()

        # Facing angle in degrees: 0 = up, increases clockwise
        self._angle_deg: float = random.uniform(0.0, 360.0)

        # Velocity components (pixels/frame)
        self._vx: float = 0.0
        self._vy: float = 0.0

    # -------------------------------------------------------------------
    # Properties
    # -------------------------------------------------------------------

    @property
    def x(self) -> float:
        """Current X position."""
        return self._x

    @property
    def y(self) -> float:
        """Current Y position."""
        return self._y

    @property
    def angle_deg(self) -> float:
        """Current facing angle in degrees (0 = up, clockwise)."""
        return self._angle_deg

    @property
    def collision_radius(self) -> int:
        """Bounding circle radius for collision checks."""
        return COLLISION_RADIUS

    # -------------------------------------------------------------------
    # Spawn logic
    # -------------------------------------------------------------------

    def _random_edge_position(self) -> tuple[float, float]:
        """Return a random position within 100px of a screen edge.

        This keeps the player away from the central fortress at level start.
        """
        edge = random.choice(["top", "bottom", "left", "right"])
        margin = 100

        if edge == "top":
            x = random.uniform(0, self._width)
            y = random.uniform(0, margin)
        elif edge == "bottom":
            x = random.uniform(0, self._width)
            y = random.uniform(self._height - margin, self._height)
        elif edge == "left":
            x = random.uniform(0, margin)
            y = random.uniform(0, self._height)
        else:  # right
            x = random.uniform(self._width - margin, self._width)
            y = random.uniform(0, self._height)

        return x, y

    # -------------------------------------------------------------------
    # Update
    # -------------------------------------------------------------------

    def update(
        self,
        rotating_left: bool,
        rotating_right: bool,
        thrusting: bool,
    ) -> None:
        """Advance the craft's state by one frame.

        Applies rotation, thrust/friction, movement, and screen wrapping.

        Parameters
        ----------
        rotating_left :
            True if left arrow key is held.
        rotating_right :
            True if right arrow key is held.
        thrusting :
            True if up arrow key is held.
        """
        # Rotation
        if rotating_left and rotating_right:
            # Both pressed: cancel out (no rotation)
            pass
        elif rotating_left:
            self._angle_deg -= ROTATION_SPEED_DEG
        elif rotating_right:
            self._angle_deg += ROTATION_SPEED_DEG

        # Normalise angle to [0, 360)
        self._angle_deg %= 360.0

        # Thrust or friction
        if thrusting:
            self._apply_thrust()
        else:
            self._apply_friction()

        # Apply velocity
        self._x += self._vx
        self._y += self._vy

        # Clamp speed to MAX_SPEED (safety net in case of rounding drift)
        self._clamp_speed()

        # Screen wrapping
        self._wrap_position()

    def _apply_thrust(self) -> None:
        """Apply thrust acceleration in the ship's facing direction."""
        angle_rad = math.radians(self._angle_deg)

        # In pygame, Y increases downward. Angle 0° = up = negative Y.
        # thrust_dx = sin(angle), thrust_dy = -cos(angle)
        thrust_dx = math.sin(angle_rad) * THRUST_ACCELERATION
        thrust_dy = -math.cos(angle_rad) * THRUST_ACCELERATION

        self._vx += thrust_dx
        self._vy += thrust_dy

    def _apply_friction(self) -> None:
        """Apply linear friction when thrust is released."""
        self._vx *= FRICTION_FACTOR
        self._vy *= FRICTION_FACTOR

        # Snap very small velocities to zero to avoid floating-point drift
        if abs(self._vx) < 0.01:
            self._vx = 0.0
        if abs(self._vy) < 0.01:
            self._vy = 0.0

    def _clamp_speed(self) -> None:
        """Ensure the craft's speed does not exceed MAX_SPEED."""
        speed = math.hypot(self._vx, self._vy)
        if speed > MAX_SPEED:
            scale = MAX_SPEED / speed
            self._vx *= scale
            self._vy *= scale

    def _wrap_position(self) -> None:
        """Wrap the craft's position when it crosses any screen edge.

        Uses the collision radius as a margin so the craft doesn't
        visually half-teleport across the screen.
        """
        if self._x - COLLISION_RADIUS < 0:
            self._x = self._width + COLLISION_RADIUS
        elif self._x + COLLISION_RADIUS > self._width:
            self._x = -COLLISION_RADIUS

        if self._y - COLLISION_RADIUS < 0:
            self._y = self._height + COLLISION_RADIUS
        elif self._y + COLLISION_RADIUS > self._height:
            self._y = -COLLISION_RADIUS

    # -------------------------------------------------------------------
    # Display size changes
    # -------------------------------------------------------------------

    def set_display_size(self, width: int, height: int) -> None:
        """Update tracked display dimensions (for screen wrap).

        Called on VIDEORESIZE or fullscreen toggle. Does not move the
        craft; only updates wrap boundaries.
        """
        self._width = width
        self._height = height

    # -------------------------------------------------------------------
    # Rendering
    # -------------------------------------------------------------------

    def render(self, surface: pygame.Surface) -> None:
        """Draw the ship as an elongated triangle.

        The triangle is 20px wide and 30px tall, with the tip pointing
        in the ship's facing direction. White outline, light gray fill.
        """
        # Local vertices: tip at (0, -15), base corners at (±10, 15)
        # This gives a 20px-wide, 30px-tall triangle.
        local_vertices = [
            (0.0, -15.0),   # tip (forward)
            (-10.0, 15.0),  # left rear
            (10.0, 15.0),   # right rear
        ]

        angle_rad = math.radians(self._angle_deg)

        # Transform local vertices to world space.
        # Angle convention: 0° = up (negative Y), positive = clockwise.
        #
        # Derivation: the ship's forward direction in world space is
        # (sin(θ), -cos(θ)), and its right direction is (cos(θ), sin(θ)).
        # A local point (lx, ly) maps to:
        #   world = center + (-ly) * forward + lx * right
        #
        # Sanity checks for the tip at local (0, -15):
        #   θ=0°:   (0, -15) → up     ✓
        #   θ=90°:  (15, 0)  → right  ✓
        #   θ=-90°: (-15, 0) → left   ✓
        world_vertices = []
        for lx, ly in local_vertices:
            rx = lx * math.cos(angle_rad) - ly * math.sin(angle_rad)
            ry = lx * math.sin(angle_rad) + ly * math.cos(angle_rad)
            world_vertices.append((self._x + rx, self._y + ry))

        pygame.draw.polygon(surface, COLOR_LIGHT_GRAY, world_vertices)
        pygame.draw.polygon(surface, COLOR_WHITE, world_vertices, 1)
