"""Fuel pod: a drifting rounded green square that refills the craft's tank.

Per the spec (SuperAsteroids2.md -> "Fuel"):
  - released at the event point by an asteroid split or destruction roll
    (FUEL_POD_DROP_CHANCE);
  - drifts at POWERUP_SPEED in a random direction and wraps the screen;
  - carries the SAME POWERUP_GRACE grace period as a powerup icon;
  - shares the powerup icon's whole collision matrix (projectiles, the
    laser, the shield, drifting-onto-asteroid, and UFO stealing all treat
    it exactly like an icon - stealing works even during grace);
  - the ONE difference: craft pickup adds FUEL_POD_PICKUP to the tank
    (always allowed, even during grace) instead of upgrading a weapon.

FuelPod and Powerup intentionally share a duck-typed interface (x, y,
radius, in_grace, update, overlaps_circle, draw) so the game state's
collision passes can handle both lists uniformly without isinstance
bushwhacking.
"""

import math
import random

import pygame

from game_constants import (
    FUEL_POD_BORDER_WIDTH,
    FUEL_POD_CORNER_RADIUS,
    FUEL_POD_GREEN_MAX,
    FUEL_POD_GREEN_MIN,
    FUEL_POD_RADIUS,
    FUEL_POD_SIZE,
    POWERUP_GRACE,
    POWERUP_SPEED,
    WHITE,
)
from position_utils import torus_distance, wrap_around


def spawn_fuel_pod(x: float, y: float) -> "FuelPod":
    """Releases a fuel pod AT an asteroid split/destruction event's
    location (spec: Fuel)."""
    return FuelPod(x, y)


class FuelPod:

    def __init__(self, x: float, y: float,
                 grace_frames: int = POWERUP_GRACE):
        self.x = float(x)
        self.y = float(y)
        # The drawn square is 20px, but collision uses the spec's 12px
        # bounding circle (spec: "Collision detection").
        self.radius = FUEL_POD_RADIUS
        self.grace_frames = grace_frames
        heading = random.uniform(0.0, 2.0 * math.pi)
        self.vx = math.cos(heading) * POWERUP_SPEED
        self.vy = math.sin(heading) * POWERUP_SPEED
        # Fill green channel ping-pongs FUEL_POD_GREEN_MIN -> FUEL_POD_GREEN_MAX
        # -> FUEL_POD_GREEN_MIN, one unit per frame, starting low and rising
        # (spec: Fuel).
        self._green = FUEL_POD_GREEN_MIN
        self._green_direction = 1

    @property
    def in_grace(self) -> bool:
        return self.grace_frames > 0

    @property
    def fill(self) -> tuple:
        return (0, self._green, 0)

    def update(self, width: int, height: int) -> None:
        self.x += self.vx
        self.y += self.vy
        self.x, self.y = wrap_around(self.x, self.y, self.radius,
                                     width, height)
        if self.grace_frames > 0:
            self.grace_frames -= 1
        self._advance_fill_green()

    def overlaps_circle(self, cx: float, cy: float, radius: float,
                        width: int, height: int) -> bool:
        return (torus_distance(self.x, self.y, cx, cy, width, height)
                <= self.radius + radius)

    def draw(self, screen: pygame.Surface) -> None:
        rect = pygame.Rect(0, 0, FUEL_POD_SIZE, FUEL_POD_SIZE)
        rect.center = (int(round(self.x)), int(round(self.y)))
        pygame.draw.rect(screen, self.fill, rect,
                         border_radius=FUEL_POD_CORNER_RADIUS)
        pygame.draw.rect(screen, WHITE, rect,
                         width=FUEL_POD_BORDER_WIDTH,
                         border_radius=FUEL_POD_CORNER_RADIUS)

    # ------------------------------------------------------------- internals

    def _advance_fill_green(self) -> None:
        self._green += self._green_direction
        if self._green >= FUEL_POD_GREEN_MAX:
            self._green = FUEL_POD_GREEN_MAX
            self._green_direction = -1
        elif self._green <= FUEL_POD_GREEN_MIN:
            self._green = FUEL_POD_GREEN_MIN
            self._green_direction = 1
