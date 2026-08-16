"""Cannon weapon: discrete square projectiles from the craft's tip.

Per the spec (Weapons -> Cannon):
  - each PRESS of the space bar spawns the level's shot set (holding does
    nothing - the owning state only fires on KEYDOWN);
  - an in-flight cap blocks presses that would exceed it (level 1: 3,
    level 2: 9, level 3: unlimited); a blocked press is NOT a successful
    activation and scores no shot;
  - level 2 fans three shots in a 20-degree arc; level 3 goes 4x4 white at
    8 px/frame.
"""

import math

from entities.projectile import CannonProjectile
from game_constants import (
    CANNON_LEVEL_SPECS,
    PLAYER_SHAPE_HEIGHT,
    YELLOW,
)
from weapons.base import Weapon


class Cannon(Weapon):

    NAME = "Cannon"
    # HUD label color (spec: Cannon yellow / Laser light blue / Shield red).
    LABEL_COLOR = YELLOW

    def on_press(self, craft, active_projectiles) -> bool:
        (shots_per_press, arc_degrees, size,
         speed, color, max_in_flight) = CANNON_LEVEL_SPECS[self.index()]
        if (max_in_flight is not None
                and len(active_projectiles) + shots_per_press > max_in_flight):
            return False  # blocked by the in-flight cap: NOT a shot (spec)
        active_projectiles.extend(
            self._projectiles_for(craft, shots_per_press, arc_degrees,
                                  size, speed, color))
        return True

    @staticmethod
    def _projectiles_for(craft, shots: int, arc_degrees: float,
                         size: int, speed: float, color) -> list:
        """The shot set for one press: a fan centered on the craft's facing
        direction, so the middle shot of the arc (when any) goes straight."""
        rad = math.radians(craft.angle)
        step = math.radians(arc_degrees) / (shots - 1) if shots > 1 else 0.0
        # TIP of the triangle: PLAYER_SHAPE_HEIGHT/2 along the heading.
        tip = PLAYER_SHAPE_HEIGHT / 2
        projectiles = []
        for i in range(shots):
            angle = rad + (i - (shots - 1) / 2) * step
            dir_x, dir_y = math.cos(angle), math.sin(angle)
            projectiles.append(CannonProjectile(
                x=craft.x + tip * dir_x,
                y=craft.y + tip * dir_y,
                vx=craft.vx + speed * dir_x,
                vy=craft.vy + speed * dir_y,
                size=size,
                color=color,
            ))
        return projectiles
