"""Fuel pod entity.

Spec (Fuel): 20px square with 6px rounded corners, white 4px border,
green fill that pulses between (0,128,0) and (0,255,0). Drifts at 2px/frame,
90-frame grace, same collision rules as powerup icons. Collision radius 12px.
"""

import math
import random

import pygame

from game_constants import (
    FUEL_POD_BORDER_WIDTH,
    FUEL_POD_COLLISION_RADIUS,
    FUEL_POD_CORNER_RADIUS,
    FUEL_POD_GRACE,
    FUEL_POD_SIZE,
    FUEL_POD_SPEED,
    WHITE,
)
from position_utils import wrap_around


class FuelPod:
    """A drifting fuel pod with pulsing green fill."""

    def __init__(self, x: float, y: float, grace_frames: int = FUEL_POD_GRACE):
        self.x = float(x)
        self.y = float(y)
        self.grace_frames = grace_frames
        self.radius = FUEL_POD_COLLISION_RADIUS
        # Drift velocity
        heading = random.uniform(0.0, 2.0 * math.pi)
        self.vx = math.cos(heading) * FUEL_POD_SPEED
        self.vy = math.sin(heading) * FUEL_POD_SPEED
        # Pulsing green fill: green channel oscillates 128 <-> 255
        self._green = 128
        self._green_dir = 1  # 1 up, -1 down

    @property
    def in_grace(self) -> bool:
        return self.grace_frames > 0

    def update(self, width: int, height: int) -> None:
        self.x += self.vx
        self.y += self.vy
        self.x, self.y = wrap_around(self.x, self.y, self.radius, width, height)
        if self.grace_frames > 0:
            self.grace_frames -= 1
        # Pulse green channel
        if self._green_dir == 1:
            self._green += 1
            if self._green >= 255:
                self._green = 255
                self._green_dir = -1
        else:
            self._green -= 1
            if self._green <= 128:
                self._green = 128
                self._green_dir = 1

    def overlaps_circle(self, cx: float, cy: float, radius: float,
                        width: int, height: int) -> bool:
        # Use torus distance for wrap-aware collision
        from position_utils import torus_distance
        return torus_distance(self.x, self.y, cx, cy, width, height) <= self.radius + radius

    def draw(self, screen: pygame.Surface) -> None:
        # Draw rounded square with white border and pulsing green fill
        size = FUEL_POD_SIZE
        rect = pygame.Rect(0, 0, size, size)
        rect.center = (int(round(self.x)), int(round(self.y)))
        fill_color = (0, self._green, 0)
        # Pygame's draw.rect supports border_radius in pygame-ce
        pygame.draw.rect(screen, fill_color, rect, border_radius=FUEL_POD_CORNER_RADIUS)
        pygame.draw.rect(screen, WHITE, rect, width=FUEL_POD_BORDER_WIDTH,
                         border_radius=FUEL_POD_CORNER_RADIUS)
