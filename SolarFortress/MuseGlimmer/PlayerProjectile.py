#!/usr/bin/env python3
"""
PlayerProjectile - player cannon projectile for Solar Fortress.

Stage 6 implementation: small yellow projectile with screen wrap,
cumulative distance limit, and age-based self-collision immunity.
"""

from __future__ import annotations

import math
import pygame


class PlayerProjectile:
    """Player-fired projectile with screen wrap and travel limit."""

    def __init__(self, x: float, y: float, vx: float, vy: float) -> None:
        """Create projectile at (*x*, *y*) with velocity (*vx*, *vy*).

        Parameters
        ----------
        x, y:
            Spawn position, typically at ship tip.
        vx, vy:
            Velocity in pixels per frame.
        """
        self.x: float = float(x)
        self.y: float = float(y)
        self.vx: float = float(vx)
        self.vy: float = float(vy)
        self.radius: int = 6
        self.color: tuple[int, int, int] = (255, 255, 0)  # bright yellow
        self.age: int = 0
        self.distance_traveled: float = 0.0
        self.max_distance: float = 1000.0
        self.alive: bool = True

    def update(self, screen_width: int, screen_height: int) -> None:
        """Advance projectile one frame with screen wrap."""
        if not self.alive:
            return

        self.age += 1

        # Integrate position
        self.x += self.vx
        self.y += self.vy

        # Cumulative distance traveled (unaffected by wrap)
        step_dist = math.hypot(self.vx, self.vy)
        self.distance_traveled += step_dist

        # Screen wrap
        if self.x < 0:
            self.x = float(screen_width)
        elif self.x > screen_width:
            self.x = 0.0
        if self.y < 0:
            self.y = float(screen_height)
        elif self.y > screen_height:
            self.y = 0.0

        # Remove if travel limit exceeded
        if self.distance_traveled >= self.max_distance:
            self.alive = False

    def draw(self, surface: pygame.Surface) -> None:
        """Render as a small yellow circle."""
        if not self.alive:
            return
        pos = (int(self.x), int(self.y))
        pygame.draw.circle(surface, self.color, pos, self.radius)

    def kill(self) -> None:
        """Mark projectile for removal."""
        self.alive = False

    def can_collide_with_player(self) -> bool:
        """Projectiles ignore player for first 30 frames after spawn."""
        return self.age > 30
