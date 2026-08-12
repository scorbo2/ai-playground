#!/usr/bin/env python3
"""
EnemyProjectile - enemy fortress projectile for Solar Fortress.

Stage 5 implementation: straight-line projectile fired at player position
at time of firing. No homing, removed on screen edge.
"""

from __future__ import annotations

import math
import pygame


class EnemyProjectile:
    """Straight-line enemy projectile fired from the fortress."""

    def __init__(self, x: float, y: float, target_x: float, target_y: float) -> None:
        """Create projectile at (*x*, *y*) heading toward (*target_x*, *target_y*).

        Parameters
        ----------
        x, y:
            Spawn position, typically fortress center.
        target_x, target_y:
            Player position at time of firing; direction is fixed.
        """
        self.x: float = float(x)
        self.y: float = float(y)
        self.radius: int = 32
        self.speed: float = 8.0  # pixels per frame

        dx = target_x - x
        dy = target_y - y
        dist = math.hypot(dx, dy)
        if dist == 0:
            self.vx = 0.0
            self.vy = 0.0
        else:
            self.vx = (dx / dist) * self.speed
            self.vy = (dy / dist) * self.speed

        # Visuals
        self.fill_color: tuple[int, int, int] = (120, 0, 0)  # dark red
        self.border_color: tuple[int, int, int] = (255, 0, 0)  # bright red
        self.border_width: int = 2

    def update(self) -> None:
        """Advance projectile one step along its fixed trajectory."""
        self.x += self.vx
        self.y += self.vy

    def draw(self, surface: pygame.Surface) -> None:
        """Render as filled circle with bright red border."""
        pos = (int(self.x), int(self.y))
        pygame.draw.circle(surface, self.fill_color, pos, self.radius)
        pygame.draw.circle(surface, self.border_color, pos, self.radius, self.border_width)

    def is_off_screen(self, width: int, height: int) -> bool:
        """Return True if projectile has left the visible play area."""
        return (
            self.x < -self.radius
            or self.x > width + self.radius
            or self.y < -self.radius
            or self.y > height + self.radius
        )

    def collides_with_player(self, player_x: float, player_y: float, player_radius: float) -> bool:
        """Return True if player's center enters projectile's radius.

        Collision triggers when the player's center is within 32px of the
        projectile's center to prevent visual tunneling with the large
        projectile sprite.
        """
        dist = math.hypot(self.x - player_x, self.y - player_y)
        # Use projectile radius as hitbox per bug report to avoid tunneling
        return dist < self.radius
