"""Cannon weapon (power level 1; levels 2-3 arrive with powerups in Stage 5).

Per the spec (Weapons -> Cannon, level 1):
  - one 2x2 yellow projectile per PRESS of the space bar (holding does
    nothing - the owning state only fires on KEYDOWN);
  - at most CANNON_MAX_PROJECTILES_L1 in flight; a blocked press is NOT a
    successful activation and scores no shot;
  - the projectile spawns at the craft's TIP with the craft's current
    velocity plus CANNON_PROJECTILE_SPEED in the facing direction.
"""

import math

from entities.projectile import CannonProjectile
from game_constants import (
    CANNON_MAX_PROJECTILES_L1,
    CANNON_PROJECTILE_SPEED,
    PLAYER_SHAPE_HEIGHT,
    YELLOW,
)


class Cannon:

    NAME = "Cannon"
    # HUD label colors (spec: Cannon yellow / Laser light blue / Shield red).
    LABEL_COLOR = YELLOW

    def __init__(self, power_level: int = 1):
        self.power_level = power_level

    def max_projectiles_in_flight(self) -> int:
        # Level 1 cap. Stage 5 extends this for power levels 2-3.
        return CANNON_MAX_PROJECTILES_L1

    def fire(self, craft, active_projectiles) -> list:
        """Spawn one projectile from the craft's tip.

        Returns [] when the in-flight cap is reached (a BLOCKED press -
        the spec counts only successful activations as shots fired).
        """
        if len(active_projectiles) >= self.max_projectiles_in_flight():
            return []
        rad = math.radians(craft.angle)
        dir_x, dir_y = math.cos(rad), math.sin(rad)
        # TIP of the triangle: PLAYER_SHAPE_HEIGHT/2 along the heading.
        tip = PLAYER_SHAPE_HEIGHT / 2
        return [CannonProjectile(
            x=craft.x + tip * dir_x,
            y=craft.y + tip * dir_y,
            vx=craft.vx + CANNON_PROJECTILE_SPEED * dir_x,
            vy=craft.vy + CANNON_PROJECTILE_SPEED * dir_y,
        )]
