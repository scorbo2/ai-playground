"""Homing Missiles weapon: fire-and-forget rockets that hunt the field.

The sixth weapon, and the only one that keeps working after you pull the
trigger. The other five put a projectile, a beam, a ring, a bomb, or a
singularity between the craft and the world and then stop caring; a missile
chooses its own target and steers.

Per the power-level table (game_constants -> MISSILE_LEVEL_SPECS):
  - each PRESS launches one rocket (two from power 3) from the craft's tip
    along the craft's heading, seeded with the craft's velocity and heading
    (holding the bar does nothing - the owning state only fires on KEYDOWN,
    as every other weapon does);
  - the press gate is a per-power-level RELOAD, not an in-play cap: any
    number of missiles may be in flight at once, but two launches can never
    be closer together than the table's reload. A press inside the window is
    BLOCKED - not a successful activation - so the owning state records no
    shot and plays no launch cue;
  - a launch of two counts as exactly ONE shot for scoring and plays the
    launch cue exactly ONCE, which is the same contract the cannon's fan
    already honors (more than one projectile in a single "shot");
  - the weapon deliberately does NOT pick the targets. It spawns unlocked
    missiles and the game state's targeting pass locks them (nearest first,
    and never the same object twice while another is available, which is what
    makes a salvo land on the nearest and the next-nearest hazard without
    this class ever seeing an asteroid list);
  - power 5 grants immunity to the player's own missiles. The game state
    reads that off the CURRENT weapon, exactly like the mine and gravity-well
    level-5 perks.

Contract note: the base ``on_press`` receives "the in-play list this press
feeds" (see ``GameState._press_target_list``). For this weapon that is the
live-MISSILE list - handed over for the new rockets to join, never measured
against.
"""

import math

from entities.missile import HomingMissile
from game_constants import (
    MISSILE_LEVEL_SPECS,
    MISSILE_LABEL_COLOR,
    MISSILE_SALVO_LATERAL_OFFSET,
    PLAYER_SHAPE_HEIGHT,
)
from weapons.base import Weapon


class HomingMissiles(Weapon):

    NAME = "Homing missiles"
    LABEL_COLOR = MISSILE_LABEL_COLOR

    def __init__(self, power_level: int = 1):
        super().__init__(power_level)
        # Frames until the next launch is permitted. 0 = ready to fire.
        self._frames_until_reloaded = 0

    # --------------------------------------------------------------- ballistics

    @property
    def missiles_per_launch(self) -> int:
        return MISSILE_LEVEL_SPECS[self.index()][0]

    @property
    def reload_frames(self) -> int:
        return MISSILE_LEVEL_SPECS[self.index()][1]

    @property
    def reloading(self) -> bool:
        return self._frames_until_reloaded > 0

    # ----------------------------------------------------------------- firing

    def on_press(self, craft, missiles_in_play) -> bool:
        if self.reloading:
            return False  # inside the reload window: NOT a shot (spec: Weapons)
        # Arming the next launch happens HERE, not in _salvo, so the cadence
        # is spent even by a launch the caller might discard. The counter is
        # then decremented by update(); a launch that sets it to N is
        # followable by another press exactly N frames later.
        self._frames_until_reloaded = self.reload_frames
        missiles_in_play.extend(self._salvo(craft))
        return True

    def update(self, space_held: bool) -> None:
        """Tick the reload. Key state is irrelevant to a rocket that is
        already gone, and this hook only ever runs in the playing phase - so
        the cadence counts frames of ACTIVE play for free (a pause or a level
        intro suspends it exactly like every other timer)."""
        if self.reloading:
            self._frames_until_reloaded -= 1

    def _salvo(self, craft) -> list:
        """The rocket(s) for one press, all seeded with the craft's position,
        velocity, and heading.

        A single missile leaves from the tip on the ship's axis. A salvo of
        two is split across the axis by MISSILE_SALVO_LATERAL_OFFSET so the
        player can SEE the level-3 upgrade land, rather than watching one
        cylinder peel off a second one a third of the way to the target.
        """
        rad = math.radians(craft.angle)
        forward = (math.cos(rad), math.sin(rad))
        # Perpendicular to the heading: the heading rotated +90 degrees, which
        # is a clockwise quarter-turn on screen because +Y points DOWN here.
        # Which side each rocket takes is cosmetic (targets come from the
        # state's ranking pass), so it only has to be consistent.
        lateral = (-forward[1], forward[0])
        tip = PLAYER_SHAPE_HEIGHT / 2
        missiles = []
        for offset in _salvo_offsets(self.missiles_per_launch):
            missiles.append(HomingMissile(
                x=craft.x + forward[0] * tip + lateral[0] * offset,
                y=craft.y + forward[1] * tip + lateral[1] * offset,
                vx=craft.vx,
                vy=craft.vy,
                angle=craft.angle,
            ))
        return missiles


def _salvo_offsets(count: int) -> tuple:
    """Lateral spawn offsets (px) across the launch axis, one per missile:
    evenly spaced about the ship's axis, so one rocket sits dead center, two
    come one per side, and three would be a center rocket plus a pair.

    Deriving the spread from the count (rather than hard-coding the two
    cases the current table happens to use) keeps this correct if a future
    power level buys a third rocket.
    """
    return tuple((index - (count - 1) / 2) * 2 * MISSILE_SALVO_LATERAL_OFFSET
                 for index in range(count))
