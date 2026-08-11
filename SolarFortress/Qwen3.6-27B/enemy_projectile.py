#!/usr/bin/env python3
"""EnemyProjectile class for Solar Fortress.

The enemy fortress fires large fast-moving projectiles toward the
player's position at the moment of launch.  These projectiles travel
in a straight line and are removed once they leave the screen.
"""

from __future__ import annotations

import math
from typing import Tuple

import pygame

# ---------------------------------------------------------------------------
# Enemy projectile constants
# ---------------------------------------------------------------------------

# Projectile radius in pixels
PROJECTILE_RADIUS: int = 32

# Constant forward speed in pixels per frame
PROJECTILE_SPEED: float = 8.0

# Base spawn interval in frames (level 1)
BASE_SPAWN_INTERVAL: int = 600

# Per-level interval reduction (frames)
INTERVAL_REDUCTION_PER_LEVEL: int = 50

# Absolute minimum spawn interval (frames)
MIN_SPAWN_INTERVAL: int = 300

# Fortress firing animation timing (frames)
CHARGING_DURATION: int = 60
FIRING_DURATION: int = 30

# Visual colours
COLOR_PROJECTILE_FILL: Tuple[int, int, int] = (128, 0, 0)
COLOR_PROJECTILE_BORDER: Tuple[int, int, int] = (255, 0, 0)
PROJECTILE_BORDER_WIDTH: int = 2


class EnemyProjectile:
    """A large enemy projectile fired from the fortress.

    Moves in a straight line at constant speed toward the player's
    position at the moment of launch.  Removed automatically when it
    crosses any screen edge.
    """

    def __init__(self, x: float, y: float, angle_rad: float) -> None:
        """Create an enemy projectile at (*x*, *y*) with a fixed heading.

        Parameters
        ----------
        x, y:
            Spawn position (typically the fortress center).
        angle_rad:
            Launch angle in radians (0 = right, increasing clockwise).
        """
        self.x: float = x
        self.y: float = y
        # Pre-compute velocity components — heading never changes
        self.vx: float = PROJECTILE_SPEED * math.cos(angle_rad)
        self.vy: float = PROJECTILE_SPEED * math.sin(angle_rad)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self) -> None:
        """Advance the projectile one frame along its fixed trajectory."""
        self.x += self.vx
        self.y += self.vy

    def off_screen(self, width: int, height: int) -> bool:
        """Return True if the projectile has left the screen bounds.

        Enemy projectiles do NOT screen-wrap.  Once any part of the
        projectile is fully beyond an edge, it should be removed.
        """
        return (
            self.x + PROJECTILE_RADIUS < 0
            or self.x - PROJECTILE_RADIUS > width
            or self.y + PROJECTILE_RADIUS < 0
            or self.y - PROJECTILE_RADIUS > height
        )

    def collides_with_craft(
        self, craft_x: float, craft_y: float, craft_radius: float,
    ) -> bool:
        """Check if the projectile overlaps the craft's collision circle.

        Parameters
        ----------
        craft_x, craft_y:
            Position of the player's craft.
        craft_radius:
            The craft's bounding-circle radius.

        Returns
        -------
        ``True`` if the projectile has made contact with the craft.
        """
        dx = self.x - craft_x
        dy = self.y - craft_y
        return math.hypot(dx, dy) <= (PROJECTILE_RADIUS + craft_radius)

    def render(self, surface: pygame.Surface) -> None:
        """Draw the projectile as a filled circle with a bright border."""
        center = (round(self.x), round(self.y))
        pygame.draw.circle(
            surface, COLOR_PROJECTILE_FILL, center,
            PROJECTILE_RADIUS, 0,  # width=0 → filled circle
        )
        pygame.draw.circle(
            surface, COLOR_PROJECTILE_BORDER, center,
            PROJECTILE_RADIUS, PROJECTILE_BORDER_WIDTH,
        )


def compute_spawn_interval(level: int) -> int:
    """Return the fortress firing interval for a given level.

    Level 1 fires every 600 frames.  Each subsequent level reduces
    the interval by 50 frames, with a floor of 300 frames.

    Parameters
    ----------
    level:
        The 1-based level number.

    Returns
    -------
    The interval in frames.
    """
    return max(MIN_SPAWN_INTERVAL, BASE_SPAWN_INTERVAL - (level - 1) * INTERVAL_REDUCTION_PER_LEVEL)
