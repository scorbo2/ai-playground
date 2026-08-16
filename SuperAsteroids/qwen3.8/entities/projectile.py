"""Cannon projectile: a small square block with a fixed travel budget.

Per the spec (Weapons -> Cannon):
  - initial velocity = craft velocity plus the level's projectile speed in
    the craft's facing direction (set by the weapon that spawns it);
  - travels CANNON_PROJECTILE_DISTANCE pixels CUMULATIVELY - screen wraps
    are transparent to the counter, exactly N px of flight always count
    (the budget is an instance field, which is how the shorter-range 500px
    UFO projectiles reuse this class);
  - has a CANNON_SELF_GRACE frame window during which it can trigger every
    impact EXCEPT the one with its own craft (self-immunity only, spec);
  - impacts use the projectile's EXACT square shape, not a bounding circle.
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

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 size: int = CANNON_PROJECTILE_SIZE, color=YELLOW,
                 distance_limit: float = CANNON_PROJECTILE_DISTANCE,
                 grace_frames: int = CANNON_SELF_GRACE):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.size = size
        self.color = color
        self.distance_traveled = 0.0
        self.distance_limit = distance_limit
        # Enemy (UFO) shots pass 0 here: they pass through enemy crew, so
        # their only kill threat is the player craft and it is live from
        # frame one - no self-kill window is needed.
        self.grace_frames = grace_frames

    @property
    def half_size(self) -> float:
        return self.size / 2

    @property
    def can_hit_player(self) -> bool:
        """Only false during the spawn grace window (spec: prevents
        immediate self-kills while still allowing asteroid impacts)."""
        return self.grace_frames <= 0

    @property
    def expired(self) -> bool:
        return self.distance_traveled >= self.distance_limit

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
            screen, self.color,
            (int(self.x - self.half_size), int(self.y - self.half_size),
             self.size, self.size),
        )
