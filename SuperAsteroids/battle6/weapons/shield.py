"""Ramming shield: a red ring around the craft that rams obstacles.

Per the spec (Weapons -> Ramming Shield): activated by holding the space
bar, it destroys/splits anything it touches and "bounces" the craft away
from the impact point at speed = asteroid radius / (level divisor), always
clamped to max craft speed. Charge rules match the laser's (100 units,
can't activate below 20, drain continues while held after a hit/depletion).
At power 3 shield impacts destroy asteroids outright, and UFOs touch the
ring at ANY power level: destroyed instantly, with the same bounce rules
using the UFO's 30 px bounding radius in place of the rock's (the
collision itself is resolved by the game state, which owns the bounce).
"""

import pygame

from game_constants import (
    SHIELD_BORDER_WIDTHS,
    SHIELD_BOUNCE_DIVISORS,
    SHIELD_DRAIN,
    SHIELD_RADII,
    SHIELD_RECHARGE,
    RED,
)
from weapons.base import ChargedWeapon


class RammingShield(ChargedWeapon):

    NAME = "Shield"
    LABEL_COLOR = RED

    @property
    def drain_rate(self) -> float:
        return SHIELD_DRAIN[self.index()]

    @property
    def recharge_rate(self) -> float:
        return SHIELD_RECHARGE[self.index()]

    @property
    def shield_radius(self) -> float:
        return float(SHIELD_RADII[self.index()])

    @property
    def border_width(self) -> int:
        return SHIELD_BORDER_WIDTHS[self.index()]

    @property
    def bounce_divisor(self) -> float:
        return float(SHIELD_BOUNCE_DIVISORS[self.index()])

    def destroys_on_hit(self) -> bool:
        """Power 3 bypasses the usual split rules (spec)."""
        return self.power() >= 3

    def draw(self, screen: pygame.Surface, craft) -> None:
        if not self.firing:
            return
        pygame.draw.circle(screen, RED,
                           (int(round(craft.x)), int(round(craft.y))),
                           int(self.shield_radius), width=self.border_width)
