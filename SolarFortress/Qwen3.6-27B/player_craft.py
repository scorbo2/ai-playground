#!/usr/bin/env python3
"""PlayerCraft class for Solar Fortress.

Manages the player-controlled spaceship: rendering as an elongated
triangle, keyboard-driven rotation and thrust, screen wrapping,
and collision detection via a bounding circle.
"""

from __future__ import annotations

import math
import random
from typing import List
from typing import Tuple

import pygame

# ---------------------------------------------------------------------------
# Craft constants
# ---------------------------------------------------------------------------

# Elongated triangle: 20px wide (base), 30px tall (nose to base centre)
CRAFT_WIDTH: int = 20
CRAFT_HEIGHT: int = 30

# Rotation speed in degrees per frame
ROTATION_SPEED: float = 5.0

# Thrust acceleration in pixels per frame squared
THRUST_ACCELERATION: float = 0.3

# Maximum forward speed in pixels per frame
MAX_SPEED: float = 8.0

# Linear friction multiplier applied each frame when not thrusting
FRICTION: float = 0.98

# Bounding-circle radius for collision detection
CRAFT_COLLISION_RADIUS: float = 20.0

# Visual colours
COLOR_CRAFT_FILL: Tuple[int, int, int] = (192, 192, 192)
COLOR_CRAFT_OUTLINE: Tuple[int, int, int] = (255, 255, 255)
OUTLINE_WIDTH: int = 2

# ---------------------------------------------------------------------------
# Thruster exhaust particle constants
# ---------------------------------------------------------------------------

# Random radius range for exhaust particles (pixels)
THRUSTER_MIN_RADIUS: float = 3.0
THRUSTER_MAX_RADIUS: float = 8.0

# Random initial speed range (pixels per frame)
THRUSTER_MIN_SPEED: float = 6.0
THRUSTER_MAX_SPEED: float = 10.0

# Alpha decay: 5% of full alpha per frame
THRUSTER_ALPHA_DECAY: float = 0.05

# Angular spread of exhaust particles from ship's rearward direction (degrees)
THRUSTER_SPREAD_DEG: float = 30.0

# Colour transition keyframes: yellow → orange → red
COLOR_YELLOW: Tuple[int, int, int] = (255, 255, 0)
COLOR_ORANGE: Tuple[int, int, int] = (255, 165, 0)
COLOR_RED_EXHAUST: Tuple[int, int, int] = (255, 0, 0)


class _ThrusterParticle:
    """A single cosmetic exhaust particle ejected from the player's thrusters.

    Particles fade from yellow → orange → red as their alpha decays.
    They have no collision detection and self-destruct when fully transparent.
    """

    __slots__ = ("x", "y", "vx", "vy", "radius", "alpha")

    def __init__(self, x: float, y: float, vx: float, vy: float) -> None:
        self.x: float = x
        self.y: float = y
        self.vx: float = vx
        self.vy: float = vy
        self.radius: float = random.uniform(
            THRUSTER_MIN_RADIUS, THRUSTER_MAX_RADIUS,
        )
        self.alpha: float = 255.0

    def update(self) -> bool:
        """Advance position and fade alpha. Returns True if still alive."""
        self.x += self.vx
        self.y += self.vy
        self.alpha -= THRUSTER_ALPHA_DECAY * 255.0
        if self.alpha <= 0:
            self.alpha = 0.0
            return False
        return True

    def render(self, surface: pygame.Surface) -> None:
        """Draw the particle as a fading coloured circle."""
        color = self._exhaust_color()
        color_with_alpha = (*color, int(self.alpha))
        size = int(self.radius * 2) + 2
        img = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size // 2, size // 2)
        pygame.draw.circle(img, color_with_alpha, center, self.radius + 0.5)
        rect = img.get_rect(center=(round(self.x), round(self.y)))
        surface.blit(img, rect)

    def _exhaust_color(self) -> Tuple[int, int, int]:
        """Return the colour for this exhaust particle based on its alpha.

        Interpolates yellow → orange → red as alpha decreases from 255 to 0.
        """
        ratio = self.alpha / 255.0
        if ratio > 0.5:
            t = (ratio - 0.5) * 2  # 0→1 as ratio goes 0.5→1.0
            return _lerp_color(COLOR_ORANGE, COLOR_YELLOW, t)
        else:
            t = ratio * 2  # 0→1 as ratio goes 0.0→0.5
            return _lerp_color(COLOR_RED_EXHAUST, COLOR_ORANGE, t)


def _lerp_color(
    c1: Tuple[int, int, int],
    c2: Tuple[int, int, int],
    t: float,
) -> Tuple[int, int, int]:
    """Linearly interpolate between two RGB colours."""
    return (
        int(c1[0] + (c2[0] - c1[0]) * t),
        int(c1[1] + (c2[1] - c1[1]) * t),
        int(c1[2] + (c2[2] - c1[2]) * t),
    )


class PlayerCraft:
    """Player-controlled spaceship.

    Rendered as an elongated triangle.  Responds to arrow keys for
    rotation and thrust.  Wraps around screen edges and reports
    whether it has been destroyed.
    """

    def __init__(self, x: float, y: float) -> None:
        """Create a craft at (*x*, *y*).

        The craft starts facing right (0° = +X axis).
        """
        self.x: float = x
        self.y: float = y
        self.angle: float = 0.0  # degrees, 0 = right, clockwise
        self.vx: float = 0.0
        self.vy: float = 0.0
        self._destroyed: bool = False
        self.thruster_particles: List[_ThrusterParticle] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def destroyed(self) -> bool:
        """True once the craft has been struck."""
        return self._destroyed

    @property
    def collision_radius(self) -> float:
        """Bounding-circle radius for collision checks."""
        return CRAFT_COLLISION_RADIUS

    @property
    def is_thrusting(self) -> bool:
        """True while the up-arrow key is currently held."""
        return bool(pygame.key.get_pressed()[pygame.K_UP])

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, width: int, height: int) -> None:
        """Process input, apply physics, and wrap to screen bounds.

        Must be called every frame.  Reads keyboard state directly
        via ``pygame.key.get_pressed()``.
        """
        if self._destroyed:
            return

        self._handle_rotation()
        self._handle_thrust()
        self._apply_friction()
        self._clamp_speed()
        self._step_position()
        self._wrap_screen(width, height)

        # Thruster exhaust: spawn particles when thrusting
        if self.is_thrusting:
            self._spawn_thruster_particle()

        # Tick and cull exhaust particles
        self.thruster_particles = [
            p for p in self.thruster_particles if p.update()
        ]

    def render(self, surface: pygame.Surface) -> None:
        """Draw thruster exhaust and the craft triangle on *surface*."""
        # Exhaust renders first so it appears behind the craft
        for particle in self.thruster_particles:
            particle.render(surface)

        points = self._compute_vertices()
        pygame.draw.polygon(surface, COLOR_CRAFT_FILL, points)
        pygame.draw.polygon(surface, COLOR_CRAFT_OUTLINE, points, OUTLINE_WIDTH)

    def reset(self, x: float, y: float) -> None:
        """Reposition the craft and clear destruction state."""
        self.x = x
        self.y = y
        self.angle = 0.0
        self.vx = 0.0
        self.vy = 0.0
        self._destroyed = False
        self.thruster_particles = []

    def destroy(self) -> None:
        """Mark the craft as destroyed."""
        self._destroyed = True

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------

    def _handle_rotation(self) -> None:
        """Rotate left/right at *ROTATION_SPEED* degrees per frame."""
        keys = pygame.key.get_pressed()
        if keys[pygame.K_LEFT]:
            self.angle -= ROTATION_SPEED
        if keys[pygame.K_RIGHT]:
            self.angle += ROTATION_SPEED
        # Normalise to [0, 360) for consistency
        self.angle %= 360

    def _handle_thrust(self) -> None:
        """Apply forward acceleration when Up arrow is held."""
        if not self.is_thrusting:
            return

        angle_rad = math.radians(self.angle)
        self.vx += THRUST_ACCELERATION * math.cos(angle_rad)
        self.vy += THRUST_ACCELERATION * math.sin(angle_rad)

    def _apply_friction(self) -> None:
        """Dampen velocity when the player is not thrusting."""
        if self.is_thrusting:
            return
        self.vx *= FRICTION
        self.vy *= FRICTION
        # Snap near-zero velocities to exactly zero
        if math.hypot(self.vx, self.vy) < 0.01:
            self.vx = 0.0
            self.vy = 0.0

    def _spawn_thruster_particle(self) -> None:
        """Eject a single exhaust particle from the rear of the ship.

        The particle spawns at the base-centre of the craft triangle
        and flies backward relative to the craft's facing direction,
        with a random angular spread to simulate a cone of exhaust.
        """
        angle_rad = math.radians(self.angle)

        # Spawn point: 10px behind craft centre (the triangle base)
        spawn_x = self.x - 10 * math.cos(angle_rad)
        spawn_y = self.y - 10 * math.sin(angle_rad)

        # Eject opposite to facing direction, with random spread
        spread_rad = math.radians(
            random.uniform(-THRUSTER_SPREAD_DEG, THRUSTER_SPREAD_DEG)
        )
        eject_angle = angle_rad + math.pi + spread_rad
        speed = random.uniform(THRUSTER_MIN_SPEED, THRUSTER_MAX_SPEED)

        self.thruster_particles.append(
            _ThrusterParticle(
                spawn_x, spawn_y,
                speed * math.cos(eject_angle),
                speed * math.sin(eject_angle),
            )
        )

    def _clamp_speed(self) -> None:
        """Enforce the maximum speed cap."""
        speed = math.hypot(self.vx, self.vy)
        if speed > MAX_SPEED:
            scale = MAX_SPEED / speed
            self.vx *= scale
            self.vy *= scale

    # ------------------------------------------------------------------
    # Position & wrapping
    # ------------------------------------------------------------------

    def _step_position(self) -> None:
        """Advance position by current velocity."""
        self.x += self.vx
        self.y += self.vy

    def _wrap_screen(self, width: int, height: int) -> None:
        """Wrap the craft around all four screen edges.

        Uses the collision radius so the craft doesn't teleport
        while partially off-screen.
        """
        r = CRAFT_COLLISION_RADIUS
        if self.x < -r:
            self.x = width + r
        elif self.x > width + r:
            self.x = -r
        if self.y < -r:
            self.y = height + r
        elif self.y > height + r:
            self.y = -r

    # ------------------------------------------------------------------
    # Geometry
    # ------------------------------------------------------------------

    def _compute_vertices(self) -> list[Tuple[float, float]]:
        """Return the three triangle vertices in screen-space.

        The nose points in the craft's facing direction.
        """
        angle_rad = math.radians(self.angle)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)

        half_w = CRAFT_WIDTH / 2  # 10 px — half the base width

        # Nose: 20 px forward from centre along facing direction
        nose_x = self.x + 20 * cos_a
        nose_y = self.y + 20 * sin_a

        # Base corners: 10 px behind centre, ±10 px perpendicular
        base_cx = self.x - 10 * cos_a
        base_cy = self.y - 10 * sin_a
        left_x = base_cx - half_w * (-sin_a)
        left_y = base_cy - half_w * cos_a
        right_x = base_cx + half_w * (-sin_a)
        right_y = base_cy + half_w * cos_a

        return [(nose_x, nose_y), (left_x, left_y), (right_x, right_y)]
