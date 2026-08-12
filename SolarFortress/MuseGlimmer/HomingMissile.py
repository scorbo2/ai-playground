#!/usr/bin/env python3
"""
HomingMissile - enemy seeking projectile for Solar Fortress.

Stage 4 implementation: spawns from fortress center, homes toward player
at constant speed, renders as small white-bordered circle.
"""

from __future__ import annotations

import math
import pygame


class HomingMissile:
    """Enemy homing missile that constantly tracks the player's craft."""

    def __init__(self, x: float, y: float) -> None:
        """Create a homing missile at (*x*, *y*).

        Parameters
        ----------
        x, y:
            Spawn position, typically the fortress center.
        """
        self.x: float = float(x)
        self.y: float = float(y)
        # 16px wide => radius 8
        self.radius: int = 8
        self.speed: float = 2.0  # pixels per frame

        # Visuals
        self.fill_color: tuple[int, int, int] = (200, 200, 200)  # light gray
        self.border_color: tuple[int, int, int] = (255, 255, 255)  # white

    def update(self, target_x: float, target_y: float) -> None:
        """Move one step toward *target_x*, *target_y*.

        Heading is recomputed every frame with no turn-rate limit.
        """
        dx = target_x - self.x
        dy = target_y - self.y
        dist = math.hypot(dx, dy)
        if dist == 0:
            # Already on target; avoid division by zero
            return

        # Normalize direction and advance at constant speed
        self.x += (dx / dist) * self.speed
        self.y += (dy / dist) * self.speed

    def draw(self, surface: pygame.Surface) -> None:
        """Render the missile as a filled circle with a 1px white border."""
        pos = (int(self.x), int(self.y))
        pygame.draw.circle(surface, self.fill_color, pos, self.radius)
        pygame.draw.circle(surface, self.border_color, pos, self.radius, 1)

    def collides_with_player(self, player_x: float, player_y: float, player_radius: float) -> bool:
        """Return True if missile overlaps player's bounding circle."""
        dist = math.hypot(self.x - player_x, self.y - player_y)
        # Spec uses a simple bounding circle around the craft; missile center entering
        # that circle constitutes a hit.
        return dist < player_radius
