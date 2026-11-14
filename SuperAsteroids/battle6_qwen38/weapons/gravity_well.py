"""Gravity Wells weapon: plants singularities that bend the field.

The fifth weapon, and the only one that never touches anything: the other
four put a projectile, a beam, a ring, or a bomb between the craft and the
world, while this one rewrites the local geography and lets the world come
to it.

Per the power-level table (game_constants -> GRAVITY_WELL_LEVEL_SPECS):
  - each PRESS deploys exactly ONE well a fixed distance BEHIND the craft's
    tail (holding the bar does nothing - the owning state only fires on
    KEYDOWN, same as the mine weapon). The aft anchor is deliberate: like a
    shrapnel mine, you lay a well and immediately fly AWAY from it;
  - the in-play cap is per power level (1/2/3/unlimited/unlimited), and a
    press at the cap is BLOCKED - not a successful activation, so the owning
    state records no shot and plays no fire SFX;
  - each well carries the weapon's power level AT DEPLOYMENT, so a well that
    is already turning keeps its own radius/strength/lifetime even after the
    player switches weapons;
  - power 5 grants the player immunity to their own wells' pull and crush
    (the game state reads that off the CURRENT weapon, exactly like the mine
    weapon's level-5 burst-shot immunity).

Contract note: for projectile weapons the base ``on_press`` receives the
projectile list; a well cap is over WELLS, so the owning state hands this one
the live-well list instead (see GameState._press_target_list).
"""

import math

from entities.gravity_well import GravityWell
from game_constants import (
    GRAVITY_WELL_LABEL_COLOR,
    GRAVITY_WELL_LAUNCH_DISTANCE,
    GRAVITY_WELL_LEVEL_SPECS,
    PLAYER_SHAPE_HEIGHT,
)
from weapons.base import Weapon


class GravityWells(Weapon):

    NAME = "Gravity wells"
    LABEL_COLOR = GRAVITY_WELL_LABEL_COLOR

    def on_press(self, craft, wells_in_play) -> bool:
        cap = GRAVITY_WELL_LEVEL_SPECS[self.index()][0]
        if cap is not None and len(wells_in_play) >= cap:
            return False  # at the in-play cap: NOT a shot (spec: Weapons)
        wells_in_play.append(self._deploy(craft))
        return True

    def _deploy(self, craft) -> GravityWell:
        """A fresh well anchored in the world GRAVITY_WELL_LAUNCH_DISTANCE
        AFT of the craft's tail, along the line of the current heading.

        The heading picks the spot; the well does NOT inherit the craft's
        velocity (a drifting singularity would wander out of the fight it was
        thrown into). The anchor mirrors the mine weapon's rear drop: same
        half-height offset, negated, so the well's center stays exactly 215 px
        from the craft's center - the launch stand-off is unchanged, only its
        bearing is. Point-blank self-crush is still impossible, and thrusting
        forward after a deploy pulls the ship OUT of the field it just cast
        instead of straight back into it.
        """
        rad = math.radians(craft.angle)
        astern = PLAYER_SHAPE_HEIGHT / 2 + GRAVITY_WELL_LAUNCH_DISTANCE
        return GravityWell(
            x=craft.x - math.cos(rad) * astern,
            y=craft.y - math.sin(rad) * astern,
            power_level=self.power(),
        )
