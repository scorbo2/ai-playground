"""Homing missile: a self-steering rocket that hunts the nearest hazard.

The sixth weapon's world object (game_constants -> "homing missiles" carries
the rationale and every tunable). What the ENTITY owns:

  - its flight law: a rotation toward its lock at the craft's rotation rate,
    a thrust at the craft's acceleration, capped at the craft's max speed.
    Those three numbers are the CRAFT's constants on purpose (the spec hands
    the missile "the same characteristics as the player's ship"), so the
    missile never grows its own private physics;
  - its lock: a plain reference to the asteroid or UFO it is hunting. The
    missile steers at whatever that object's position IS this frame - it does
    not lead, predict, or cheat;
  - its launch grace clock (the window in which it cannot hit its own craft);
  - its silhouette: a 20x6 light gray cylinder, drawn rotated to its heading.

What it deliberately does NOT own: who it locks onto, what its impact
destroys, whether that impact scores, and whether the player survives any of
it. That arbitration touches the shared world lists and the score, so it lives
in the game state - the same split the mine and the gravity well use.

Two design notes worth keeping:

  - the missile holds a REFERENCE to its target rather than coordinates. A
    rock's position moves every frame and the rock itself can leave play;
    holding the object means the game state can detect both ("is my target
    still in play?") without the missile ever polling the world;
  - the missile ALWAYS thrusts while it is in play, lock or no lock. It has
    unlimited fuel and unlimited range, so a rocket with nothing to shoot at
    simply keeps flying straight - the alternative (coast, then the stall
    rule) would park a spent missile in mid-field for the rest of the level,
    where it stays just as lethal and stops making any sense. This is also
    what forces the thruster SFX loop to be shared with the craft: see
    ``GameState._sync_sound_loops``.
"""

import math

import pygame

from game_constants import (
    MISSILE_BODY_COLOR,
    MISSILE_LENGTH,
    MISSILE_OUTLINE_COLOR,
    MISSILE_RADIUS,
    MISSILE_SELF_GRACE,
    MISSILE_WIDTH,
    PLAYER_ACCELERATION,
    PLAYER_MAX_SPEED,
    PLAYER_ROTATION_SPEED,
)
from position_utils import shortest_delta, torus_distance, wrap_around

# Vertices in the missile's LOCAL frame, defined facing RIGHT (angle 0) and
# rotated to the heading each draw - the same trick the craft's triangle and
# the asteroid polygons use. The nose is chamfered by one width: the box is
# still exactly MISSILE_LENGTH x MISSILE_WIDTH, but a perfectly rectangular
# rocket cannot be told from a stray girder at 8 px/frame, and "which way is
# that thing pointing" is load-bearing information when it is your own missile.
_HALF_LENGTH = MISSILE_LENGTH / 2
_HALF_WIDTH = MISSILE_WIDTH / 2
_MISSILE_POINTS = (
    (_HALF_LENGTH, 0.0),
    (_HALF_LENGTH - MISSILE_WIDTH, _HALF_WIDTH),
    (-_HALF_LENGTH, _HALF_WIDTH),
    (-_HALF_LENGTH, -_HALF_WIDTH),
    (_HALF_LENGTH - MISSILE_WIDTH, -_HALF_WIDTH),
)


def rank_targets_by_distance(x: float, y: float, candidates: list,
                             width: int, height: int) -> list:
    """Target candidates sorted NEAREST FIRST, by wrap-aware distance.

    "Nearest" is defined by ``torus_distance`` (spec: Homing Missiles -
    "Targeting should be wrap-aware"), so a craft 5 px off the left edge
    locks onto the rock 5 px off the right edge rather than the one two
    screen-widths away in raw coordinates. Center-to-center, like every other
    proximity rule in the game; stable for equal distances, so a tie keeps the
    caller's list order instead of scattering locks frame to frame.
    """
    return sorted(candidates,
                  key=lambda obj: torus_distance(x, y, obj.x, obj.y,
                                                 width, height))


class HomingMissile:
    """One in-flight missile: heading, thrust, lock, and launch grace."""

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 angle: float, grace_frames: int = MISSILE_SELF_GRACE):
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        # Screen-angle degrees (0 = +X, positive toward +Y), the convention
        # the craft, the asteroids, and the UFOs all share.
        self.angle = float(angle) % 360.0
        # Bounding circle for EVERY collision check (see game_constants).
        self.radius = MISSILE_RADIUS
        # The asteroid or UFO this missile is hunting; None until the game
        # state's targeting pass assigns one (and again whenever it dies).
        self.target = None
        # Frames left in which this missile may not hit its own craft. Every
        # OTHER impact is live from launch, grace included (spec).
        self.grace_frames = grace_frames
        self._thrusting = False

    # ------------------------------------------------------------- simulation

    @property
    def in_grace(self) -> bool:
        """True while this missile may not touch its own craft."""
        return self.grace_frames > 0

    @property
    def thrusting(self) -> bool:
        """True once this missile has burned this frame. The owning state
        feeds it to the shared thruster SFX loop and the exhaust puffs; it is
        False only on the launch frame, before the first ``update()``."""
        return self._thrusting

    @property
    def rear_offset(self) -> float:
        """Distance from the missile's center to its tail, i.e. where the
        exhaust comes out (half the cylinder's length)."""
        return _HALF_LENGTH

    def lock_onto(self, target) -> None:
        """Assign (or re-assign) the hunt target. Passing None leaves the
        missile flying straight on its current heading until the next
        targeting pass - which is what a field with nothing left in it looks
        like, and it resolves itself the moment something appears."""
        self.target = target

    def update(self, width: int, height: int) -> None:
        """Advance one frame: steer toward the lock, burn, move, wrap."""
        if self.target is not None:
            self._steer_toward(self.target.x, self.target.y, width, height)
        self._thrust()
        self.x += self.vx
        self.y += self.vy
        self.x, self.y = wrap_around(self.x, self.y, self.radius,
                                     width, height)
        if self.grace_frames > 0:
            self.grace_frames -= 1
        self._thrusting = True

    def _steer_toward(self, target_x: float, target_y: float,
                      width: int, height: int) -> None:
        """Turn at most one frame's rotation toward the lock, the SHORT way
        round, along the wrap-aware bearing (a target across the seam is
        approached through the seam, not the long way around the screen)."""
        dx = shortest_delta(target_x - self.x, width)
        dy = shortest_delta(target_y - self.y, height)
        if math.hypot(dx, dy) <= 1e-9:
            return  # coincident: no bearing to steer by (and it is already
                    # touching whatever it is on top of, so contact resolves)
        desired = math.degrees(math.atan2(dy, dx))
        # Signed shortest turn from the current heading, folded to [-180,180).
        error = (desired - self.angle + 180.0) % 360.0 - 180.0
        turn = max(-PLAYER_ROTATION_SPEED, min(PLAYER_ROTATION_SPEED, error))
        self.angle = (self.angle + turn) % 360.0

    def _thrust(self) -> None:
        """Accelerate along the heading, capped at the craft's max speed -
        the identical law to ``PlayerCraft._thrust``, and unconditionally:
        a rocket with unlimited fuel never coasts (see this module's header).
        No friction either: friction is what the craft applies when its
        thruster is OFF, and this one never is."""
        rad = math.radians(self.angle)
        self.vx += math.cos(rad) * PLAYER_ACCELERATION
        self.vy += math.sin(rad) * PLAYER_ACCELERATION
        speed = math.hypot(self.vx, self.vy)
        if speed > PLAYER_MAX_SPEED:
            scale = PLAYER_MAX_SPEED / speed
            self.vx *= scale
            self.vy *= scale

    # ------------------------------------------------------------- collision

    def touching(self, cx: float, cy: float, radius: float,
                 width: int, height: int) -> bool:
        """Wrap-aware contact with this missile's bounding circle."""
        return (torus_distance(self.x, self.y, cx, cy, width, height)
                <= self.radius + radius)

    # ------------------------------------------------------------------ draw

    def draw(self, screen: pygame.Surface) -> None:
        rad = math.radians(self.angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        points = [
            (int(round(self.x + px * cos_a - py * sin_a)),
             int(round(self.y + px * sin_a + py * cos_a)))
            for px, py in _MISSILE_POINTS
        ]
        pygame.draw.polygon(screen, MISSILE_BODY_COLOR, points)
        pygame.draw.polygon(screen, MISSILE_OUTLINE_COLOR, points, width=1)
