"""Shrapnel Mines weapon: drops proximity-fused burst bombs from the craft.

Per the spec (Weapons -> Shrapnel Mines):
  - each PRESS releases exactly ONE mine from the craft's rear (holding the
    bar does nothing); the in-play cap is per power level (1/3/5), and a
    press while at the cap is BLOCKED - not a successful activation, so the
    owning state records no shot and plays no fire SFX;
  - each mine carries the weapon's power level AT LAUNCH, so its eventual
    detonation bursts the right projectiles even if the player has since
    switched to a different weapon;
  - the launch velocity is the craft's velocity plus a 2 px/frame BACKWARD
    kick along the craft's facing direction (spec).

Contract note: for projectile weapons the base ``on_press`` receives the
projectile list; a mine cap is over MINES, so the owning state passes the
live-mine list here instead (see Weapon.on_press).
"""

import math

from entities.mine import ShrapnelMine
from game_constants import (
    BROWN,
    MINE_BACK_LAUNCH_SPEED,
    MINE_LEVEL_SPECS,
    MINE_RADIUS,
    PLAYER_SHAPE_HEIGHT,
)
from weapons.base import Weapon


class ShrapnelMines(Weapon):

    NAME = "Shrapnel mines"
    # HUD label color (spec: Shrapnel Mines shown in brown).
    LABEL_COLOR = BROWN

    def on_press(self, craft, mines_in_play) -> bool:
        cap = MINE_LEVEL_SPECS[self.index()][0]
        if len(mines_in_play) >= cap:
            return False  # at the in-play cap: NOT a shot (spec: Weapons)
        mines_in_play.append(self._launch(craft))
        return True

    def _launch(self, craft) -> ShrapnelMine:
        """A fresh mine seeded with the craft's position/velocity, the
        BACKWARD launch kick, and this weapon's power level. The mine object
        owns all subsequent drifting, fusing, and drawing."""
        rad = math.radians(craft.angle)
        # The rear anchor mirrors the thrusters: half the craft's height
        # BEHIND its center, pushed out by the mine's own radius so it does
        # not spawn embedded in the ship's base.
        back_x, back_y = -math.cos(rad), -math.sin(rad)
        rear = MINE_RADIUS + PLAYER_SHAPE_HEIGHT / 2
        return ShrapnelMine(
            x=craft.x + back_x * rear,
            y=craft.y + back_y * rear,
            vx=craft.vx + back_x * MINE_BACK_LAUNCH_SPEED,
            vy=craft.vy + back_y * MINE_BACK_LAUNCH_SPEED,
            power_level=self.power(),
        )
