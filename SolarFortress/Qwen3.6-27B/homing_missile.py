#!/usr/bin/env python3
"""HomingMissile class for Solar Fortress.

Enemy homing missiles spawn from the fortress and relentlessly
pursue the player's craft.  Also includes the particle explosion
effect triggered when a homing missile is destroyed.
"""

from __future__ import annotations

import math
import random
from typing import List, Tuple

import pygame

# ---------------------------------------------------------------------------
# Homing missile constants
# ---------------------------------------------------------------------------

# Diameter of the missile sprite
MISSILE_DIAMETER: int = 16
MISSILE_RADIUS: float = MISSILE_DIAMETER / 2  # 8 px

# Constant forward speed in pixels per frame
MISSILE_SPEED: float = 2.0

# Spawn interval in frames
MISSILE_SPAWN_INTERVAL: int = 180

# Visual colours
COLOR_MISSILE_FILL: Tuple[int, int, int] = (192, 192, 192)
COLOR_MISSILE_BORDER: Tuple[int, int, int] = (255, 255, 255)
MISSILE_BORDER_WIDTH: int = 1

# Explosion particle constants
EXPLOSION_PARTICLE_COUNT: int = 100
EXPLOSION_PARTICLE_MIN_RADIUS: int = 2   # diameter 4 → radius 2
EXPLOSION_PARTICLE_MAX_RADIUS: int = 4   # diameter 8 → radius 4
EXPLOSION_PARTICLE_MIN_SPEED: float = 5.0
EXPLOSION_PARTICLE_MAX_SPEED: float = 15.0
EXPLOSION_ALPHA_MIN_DECAY: float = 0.04  # 4 % per frame
EXPLOSION_ALPHA_MAX_DECAY: float = 0.08  # 8 % per frame


class _HomingMissileParticle:
    """A single cosmetic particle from a homing missile explosion.

    These particles have no collision detection with any game object.
    They exist purely as a visual effect and self-destruct when their
    alpha reaches zero.
    """

    __slots__ = (
        "x", "y", "vx", "vy", "radius", "alpha", "alpha_decay",
    )

    def __init__(self, x: float, y: float) -> None:
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(
            EXPLOSION_PARTICLE_MIN_SPEED,
            EXPLOSION_PARTICLE_MAX_SPEED,
        )
        self.x: float = x
        self.y: float = y
        self.vx: float = speed * math.cos(angle)
        self.vy: float = speed * math.sin(angle)
        self.radius: float = random.uniform(
            EXPLOSION_PARTICLE_MIN_RADIUS,
            EXPLOSION_PARTICLE_MAX_RADIUS,
        )
        self.alpha: float = 255.0
        self.alpha_decay: float = random.uniform(
            EXPLOSION_ALPHA_MIN_DECAY,
            EXPLOSION_ALPHA_MAX_DECAY,
        )

    def update(self) -> bool:
        """Advance position and fade alpha. Returns True if still alive."""
        self.x += self.vx
        self.y += self.vy
        self.alpha -= self.alpha_decay * 255.0
        if self.alpha <= 0:
            self.alpha = 0.0
            return False
        return True

    def render(self, surface: pygame.Surface) -> None:
        """Draw the particle as a semi-transparent white circle."""
        # pygame.draw.circle doesn't support alpha directly, so we create
        # a per-particle surface with per-pixel alpha.
        size = int(self.radius * 2) + 2
        img = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size // 2, size // 2)
        r = self.radius + 0.5  # +0.5 to avoid hairline gaps
        pygame.draw.circle(img, (255, 255, 255, int(self.alpha)), center, r)
        rect = img.get_rect(center=(round(self.x), round(self.y)))
        surface.blit(img, rect)


class HomingMissile:
    """An enemy homing missile that relentlessly pursues the player.

    Spawned from the fortress center, the missile moves at a constant
    speed toward the player's current position, recomputing its heading
    every frame with no turn-rate limit.
    """

    def __init__(self, x: float, y: float) -> None:
        """Create a homing missile at (*x*, *y*)."""
        self.x: float = x
        self.y: float = y
        self._destroyed: bool = False
        self.explosion_particles: List[_HomingMissileParticle] = []

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def destroyed(self) -> bool:
        """True once the missile has been destroyed."""
        return self._destroyed

    @property
    def explosion_done(self) -> bool:
        """True when all explosion particles have faded out."""
        return len(self.explosion_particles) == 0

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, target_x: float, target_y: float) -> None:
        """Advance the missile one frame toward (*target_x*, *target_y*).

        The heading is recomputed every frame so the missile always
        points directly at the player's current position.
        """
        if self._destroyed:
            # Only update explosion particles
            self.explosion_particles = [
                p for p in self.explosion_particles if p.update()
            ]
            return

        dx = target_x - self.x
        dy = target_y - self.y
        dist = math.hypot(dx, dy)

        if dist > 0:
            self.x += (dx / dist) * MISSILE_SPEED
            self.y += (dy / dist) * MISSILE_SPEED

    def collides_with_craft(
        self, craft_x: float, craft_y: float, craft_radius: float,
    ) -> bool:
        """Check if this missile is within the craft's collision radius.

        Parameters
        ----------
        craft_x, craft_y:
            Position of the player's craft.
        craft_radius:
            The craft's bounding-circle radius.

        Returns
        -------
        ``True`` if the missile has made contact with the craft.
        """
        if self._destroyed:
            return False
        dx = self.x - craft_x
        dy = self.y - craft_y
        return math.hypot(dx, dy) <= craft_radius

    def destroy(self) -> None:
        """Mark the missile as destroyed and spawn an explosion."""
        if self._destroyed:
            return
        self._destroyed = True
        self.explosion_particles = [
            _HomingMissileParticle(self.x, self.y)
            for _ in range(EXPLOSION_PARTICLE_COUNT)
        ]

    def render(self, surface: pygame.Surface) -> None:
        """Draw the missile or its explosion particles."""
        if not self._destroyed:
            # Draw the missile: filled circle first (width=0), then the border
            center = (round(self.x), round(self.y))
            pygame.draw.circle(
                surface, COLOR_MISSILE_FILL, center,
                int(MISSILE_RADIUS), 0,  # width=0 → filled circle
            )
            pygame.draw.circle(
                surface, COLOR_MISSILE_BORDER, center,
                int(MISSILE_RADIUS), MISSILE_BORDER_WIDTH,
            )
        else:
            for particle in self.explosion_particles:
                particle.render(surface)
