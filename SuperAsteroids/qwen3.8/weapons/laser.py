"""Laser weapon: a wrap-aware beam projecting from the craft's tip.

Per the spec (Weapons -> Laser): the beam tracks the craft, respects screen
wrap, deactivates on the FIRST impact (it does not pass through), drains a
charge while the space bar is held, and at power 3 destroys asteroids
outright. One activation = one shot fired, however long the beam stays lit.
"""

import math

import pygame

from game_constants import (
    LASER_DRAIN,
    LASER_LENGTHS,
    LASER_RECHARGE,
    LASER_SAMPLE_STEP,
    LASER_WIDTHS,
    LIGHT_BLUE,
    PLAYER_SHAPE_HEIGHT,
    WHITE,
)
from position_utils import wrap_around
from weapons.base import ChargedWeapon


class Laser(ChargedWeapon):

    NAME = "Laser"
    LABEL_COLOR = LIGHT_BLUE

    @property
    def drain_rate(self) -> float:
        return LASER_DRAIN[self.index()]

    @property
    def recharge_rate(self) -> float:
        return LASER_RECHARGE[self.index()]

    @property
    def beam_length(self) -> float:
        return float(LASER_LENGTHS[self.index()])

    @property
    def beam_width(self) -> int:
        return LASER_WIDTHS[self.index()]

    @property
    def beam_color(self) -> tuple:
        # Spec: white only at power 3.
        return WHITE if self.power() >= 3 else LIGHT_BLUE

    def destroys_on_hit(self) -> bool:
        """Power 3 bypasses the usual split rules (spec)."""
        return self.power() >= 3

    def beam_geometry(self, craft) -> tuple:
        """(tip_x, tip_y, dir_x, dir_y) in raw, unwrapped coordinates -
        usable for both the beam draw and the state's collision sampling."""
        rad = math.radians(craft.angle)
        dir_x, dir_y = math.cos(rad), math.sin(rad)
        tip = PLAYER_SHAPE_HEIGHT / 2
        return (craft.x + tip * dir_x, craft.y + tip * dir_y, dir_x, dir_y)

    def draw(self, screen: pygame.Surface, craft) -> None:
        if not self.firing:
            return
        x, y, dir_x, dir_y = self.beam_geometry(craft)
        width, height = screen.get_size()
        prev = wrap_around(x, y, 0.0, width, height)
        travelled = 0.0
        # Draw and collide at the SAME step (LASER_SAMPLE_STEP) so the beam
        # the player sees and the beam that can hit things are identical.
        while travelled < self.beam_length:
            travelled += LASER_SAMPLE_STEP
            x += LASER_SAMPLE_STEP * dir_x
            y += LASER_SAMPLE_STEP * dir_y
            cur = wrap_around(x, y, 0.0, width, height)
            self._draw_segment(screen, prev, cur, width, height)
            prev = cur

    def _draw_segment(self, screen: pygame.Surface, start: tuple,
                      end: tuple, width: int, height: int) -> None:
        """One 2px piece of the beam; split at the screen edge when a wrap
        happened between the samples (a plain line would otherwise slash
        across the whole window). Sub-2px edge-interpolation error: none
        needed - each piece is already 2px long."""
        if abs(end[0] - start[0]) > width / 2 or abs(end[1] - start[1]) > height / 2:
            if abs(end[0] - start[0]) > width / 2:
                if end[0] < start[0]:  # crossed the right edge going +x
                    edge_a, edge_b = (width - 1, start[1]), (0, end[1])
                else:                  # crossed the left edge going -x
                    edge_a, edge_b = (0, start[1]), (width - 1, end[1])
            else:                      # vertical wrap
                if end[1] < start[1]:  # crossed the bottom edge going +y
                    edge_a, edge_b = (start[0], height - 1), (end[0], 0)
                else:                  # crossed the top edge going -y
                    edge_a, edge_b = (start[0], 0), (end[0], height - 1)
            pygame.draw.line(screen, self.beam_color, start, edge_a, self.beam_width)
            pygame.draw.line(screen, self.beam_color, edge_b, end, self.beam_width)
        else:
            pygame.draw.line(screen, self.beam_color, start, end, self.beam_width)
