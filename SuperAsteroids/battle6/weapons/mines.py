"""Shrapnel Mines weapon.

Per spec (Weapons -> Shrapnel Mines):
- Press space to release a mine from the rear of the ship.
- Cap on active mines: 1 / 3 / 5 per power level.
- No charge indicator.
- Mine activation and detonation handled by the mine entity; weapon only
  spawns mines and enforces the cap.
"""

from game_constants import BROWN, MINE_MAX_IN_PLAY
from weapons.base import Weapon


class ShrapnelMines(Weapon):
    NAME = "Shrapnel mines"
    LABEL_COLOR = BROWN

    def __init__(self, power_level: int = 1):
        super().__init__(power_level)
        self._active_mines = []  # reference list managed by GameState

    def max_mines(self) -> int:
        return MINE_MAX_IN_PLAY[self.index()]

    def on_press(self, craft, active_projectiles) -> bool:
        # active_projectiles is actually the mines list in GameState; the
        # state passes its mine list as the second argument for uniformity.
        mines = active_projectiles
        if len(mines) >= self.max_mines():
            return False  # blocked by cap
        # Spawn mine; GameState will append it
        return True  # successful activation, state will spawn

    def draw(self, screen, craft):
        # No weapon visuals beyond the mines themselves
        pass
