#!/usr/bin/env python3
"""PlayerProjectile class for Solar Fortress.

Player-fired cannon projectiles spawn from the ship's nose and travel
forward.  They screen-wrap on all edges and are removed after travelling
1000 pixels of cumulative distance.
"""

from __future__ import annotations

import math
from typing import Tuple

import pygame

# ---------------------------------------------------------------------------
# Player projectile constants
# ---------------------------------------------------------------------------

# Projectile radius in pixels
PROJECTILE_RADIUS: int = 6

# Bonus forward speed added to ship's velocity
BONUS_SPEED: float = 6.0

# Maximum cumulative travel distance before removal
MAX_TRAVEL_DISTANCE: float = 1000.0

# Frames of invulnerability to the player's own craft after spawning
INVULNERABILITY_FRAMES: int = 30

# Max projectiles in flight on level 1
BASE_PROJECTILE_CAP: int = 3

# Level at which the projectile cap is removed entirely
UNLIMITED_CAP_LEVEL: int = 5

# Visual colour
COLOR_PROJECTILE: Tuple[int, int, int] = (255, 255, 0)


def compute_projectile_cap(level: int) -> int | None:
    """Return the maximum number of player projectiles for a given level.

    Level 1 allows 3. Each subsequent level adds 1. Starting at level 5,
    the cap is removed entirely (returns ``None``).

    Parameters
    ----------
    level:
        The 1-based level number.

    Returns
    -------
    The cap, or ``None`` if unlimited.
    """
    if level >= UNLIMITED_CAP_LEVEL:
        return None
    return BASE_PROJECTILE_CAP + (level - 1)


class PlayerProjectile:
    """A small yellow projectile fired by the player's craft.

    Travels at the ship's velocity plus a fixed bonus in the ship's
    facing direction.  Screen-wraps on all edges and self-destructs
    after travelling *MAX_TRAVEL_DISTANCE* pixels cumulatively.
    """

    def __init__(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
    ) -> None:
        """Create a projectile at (*x*, *y*) with initial velocity.

        Parameters
        ----------
        x, y:
            Spawn position (nose of the ship).
        vx, vy:
            Initial velocity components (ship velocity + bonus).
        """
        self.x: float = x
        self.y: float = y
        self.vx: float = vx
        self.vy: float = vy
        self._distance_traveled: float = 0.0
        self._age: int = 0  # frames since spawn

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def age(self) -> int:
        """Frames since this projectile was spawned."""
        return self._age

    @property
    def expired(self) -> bool:
        """True when the projectile has exceeded its travel range."""
        return self._distance_traveled >= MAX_TRAVEL_DISTANCE

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, width: int, height: int) -> None:
        """Advance position, accumulate distance, and apply screen wrap.

        Parameters
        ----------
        width, height:
            Current display dimensions (needed for wrap).
        """
        step = math.hypot(self.vx, self.vy)
        self.x += self.vx
        self.y += self.vy
        self._distance_traveled += step
        self._age += 1

        # Screen wrap on all edges
        if self.x < -PROJECTILE_RADIUS:
            self.x = width + PROJECTILE_RADIUS
        elif self.x > width + PROJECTILE_RADIUS:
            self.x = -PROJECTILE_RADIUS
        if self.y < -PROJECTILE_RADIUS:
            self.y = height + PROJECTILE_RADIUS
        elif self.y > height + PROJECTILE_RADIUS:
            self.y = -PROJECTILE_RADIUS

    def collides_with_point(
        self,
        px: float,
        py: float,
        hit_radius: float,
    ) -> bool:
        """Check if this projectile overlaps a circular target.

        Parameters
        ----------
        px, py:
            Target centre.
        hit_radius:
            Target radius (added to projectile radius for overlap check).

        Returns
        -------
        ``True`` if the projectile overlaps the target.
        """
        dx = self.x - px
        dy = self.y - py
        return math.hypot(dx, dy) <= (PROJECTILE_RADIUS + hit_radius)

    def render(self, surface: pygame.Surface) -> None:
        """Draw the projectile as a small yellow circle."""
        center = (round(self.x), round(self.y))
        pygame.draw.circle(
            surface, COLOR_PROJECTILE, center, PROJECTILE_RADIUS,
        )
