"""Homing Missiles weapon: fire-and-forget self-steering missiles.

Per the spec (Homing Missiles):
  - each PRESS launches the level's missile set, provided the reload
    timer has run out (holding the bar does nothing - the owning state
    only fires on KEYDOWN, same as the cannon and the mines);
  - the launch lock is the nearest asteroid/UFO to the CRAFT at launch
    (dual launches: nearest + next-nearest; one target if only one exists);
  - the launch cadence is per power level (90/30/30/15/15 frames);
  - unlimited fuel and unlimited travel distance: missiles never draw on
    the player's tank and never expire;
  - level 5 grants the player immunity to their own missiles - handled in
    the owning state, keyed on the CURRENT weapon (the mine and well perks
    work the same way).

Contract note: unlike the cannon or the mines, the launch needs the world
(target lists + screen size), so the owning state hands this weapon a
``MissileLaunchContext`` instead of a bare list (see
GameState._press_target_list).
"""

import math
from dataclasses import dataclass

from entities.missile import HomingMissile
from game_constants import (
    DODGER_BLUE,
    MISSILE_LEVEL_SPECS,
    MISSILE_RADIUS,
    PLAYER_SHAPE_HEIGHT,
)
from position_utils import torus_distance
from weapons.base import Weapon


@dataclass(frozen=True)
class MissileLaunchContext:
    """Everything the weapon needs to launch the level's missile set."""
    missiles: list      # the live missile list to append to
    asteroids: list     # target candidates (nearest to the craft at launch)
    ufos: list          # target candidates (same set)
    width: int
    height: int


class HomingMissiles(Weapon):

    NAME = "Homing missiles"
    # HUD label color (spec: dodger blue for missiles).
    LABEL_COLOR = DODGER_BLUE

    def __init__(self, power_level: int = 1):
        super().__init__(power_level)
        # Frames left before the next launch may happen. Zero = ready
        # (a fresh weapon, or a fresh level, launches immediately).
        self._reload_frames = 0

    @property
    def reload_frames(self) -> int:
        return self._reload_frames

    def on_press(self, craft, ctx: MissileLaunchContext) -> bool:
        if self._reload_frames > 0:
            return False  # reload not ready: NOT a shot (spec: Weapons)
        count, delay = MISSILE_LEVEL_SPECS[self.index()]
        self._reload_frames = delay
        ctx.missiles.extend(self._launch(craft, ctx, count))
        return True

    def reset_active(self) -> None:
        """Level advancement: missiles leave play, so the cadence re-arms
        (a fresh level launches immediately)."""
        self._reload_frames = 0

    def update(self, space_held: bool) -> None:
        if self._reload_frames > 0:
            self._reload_frames -= 1

    # ------------------------------------------------------------ internals

    def _launch(self, craft, ctx: MissileLaunchContext, count: int) -> list:
        """Build the launch set from the craft's tail.

        The anchor mirrors the mine weapon's rear drop: half the craft's
        height plus the missile's own radius, pushed BEHIND the craft, so
        the capsule does not spawn embedded in the ship's base. Launch
        velocity is the craft's own velocity (like the cannon and the
        mine) - no extra kick: a homing missile flies toward its target,
        not away from it.
        """
        targets = self._nearest_targets(
            craft, ctx.asteroids, ctx.ufos, ctx.width, ctx.height, count)
        rad = math.radians(craft.angle)
        back_x, back_y = -math.cos(rad), -math.sin(rad)
        rear = PLAYER_SHAPE_HEIGHT / 2 + MISSILE_RADIUS
        return [
            HomingMissile(
                x=craft.x + back_x * rear,
                y=craft.y + back_y * rear,
                angle=craft.angle,
                vx=craft.vx,
                vy=craft.vy,
                target=target,
            )
            for target in targets
        ]

    @staticmethod
    def _nearest_targets(craft, asteroids, ufos,
                         width: int, height: int, count: int) -> list:
        """The launch lock set (wrap-aware, torus distance from the CRAFT):
        the nearest, and the next-nearest for dual launches. One target is
        allowed to carry both missiles (spec: 'They may lock onto the same
        object if there is only one asteroid or UFO in play'). An empty
        field yields None targets (the missiles fly straight)."""
        candidates = list(asteroids) + list(ufos)
        if not candidates:
            return [None] * count
        ordered = sorted(
            candidates,
            key=lambda obj: torus_distance(
                craft.x, craft.y, obj.x, obj.y, width, height),
        )
        if count == 1:
            return [ordered[0]]
        second = ordered[1] if len(ordered) >= 2 else ordered[0]
        return [ordered[0], second]
