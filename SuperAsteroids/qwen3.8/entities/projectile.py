"""Cannon projectile: a 2x2 px yellow block with a fixed travel budget.

Per the spec (Weapons -> Cannon):
  - initial velocity = craft velocity + CANNON_PROJECTILE_SPEED in the
    craft's facing direction (set by the weapon that spawns it);
  - travels CANNON_PROJECTILE_DISTANCE pixels CUMULATIVELY - screen wraps
    are transparent to the counter, exactly N px of flight always count;
  - has a CANNON_SELF_GRACE frame window during which it can trigger every
    impact EXCEPT the one with its own craft (self-immunity only, spec);
  - impacts use the projectile's EXACT 2x2 shape, not a bounding circle.
"""

import math

import pygame

from game_constants import (
    CANNON_PROJECTILE_DISTANCE,
    CANNON_PROJECTILE_SIZE,
    CANNON_SELF_GRACE,
    YELLOW,
)
from position_utils import wrap_around, wrapped_circle_hits_box


class CannonProjectile:

    def __init__(self, x: float, y: float, vx: float, vy: float):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.distance_traveled = 0.0
        self.grace_frames = CANNON_SELF_GRACE

    @property
    def half_size(self) -> float:
        return CANNON_PROJECTILE_SIZE / 2

    @property
    def can_hit_player(self) -> bool:
        """Only false during the spawn grace window (spec: prevents
        immediate self-kills while still allowing asteroid impacts)."""
        return self.grace_frames <= 0

    @property
    def expired(self) -> bool:
        return self.distance_traveled >= CANNON_PROJECTILE_DISTANCE

    def update(self, width: int, height: int) -> None:
        self.x += self.vx
        self.y += self.vy
        self.x, self.y = wrap_around(self.x, self.y, self.half_size,
                                     width, height)
        # Wraps do NOT reset or skip the travel budget (spec: cumulative).
        self.distance_traveled += math.hypot(self.vx, self.vy)
        if self.grace_frames > 0:
            self.grace_frames -= 1

    def hits_circle(self, cx: float, cy: float, radius: float,
                    width: int, height: int) -> bool:
        """Does this block intersect a bounding circle (asteroid, craft)?"""
        return wrapped_circle_hits_box(cx, cy, radius, self.x, self.y,
                                       self.half_size, self.half_size,
                                       width, height)

    def draw(self, screen: pygame.Surface) -> None:
        pygame.draw.rect(
            screen, YELLOW,
            (int(self.x - self.half_size), int(self.y - self.half_size),
             CANNON_PROJECTILE_SIZE, CANNON_PROJECTILE_SIZE),
        )
