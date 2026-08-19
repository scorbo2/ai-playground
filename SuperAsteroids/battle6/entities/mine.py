"""Shrapnel mine: a drifting proximity-detonated burst bomb.

Per the spec (Weapons -> Shrapnel Mines, and Collision detection):
  - launched from the craft's rear with velocity = craft velocity plus a
    2 px/frame BACKWARD kick, then coasts to a stop under the SAME friction
    and stall rules as the craft; it wraps the screen;
  - after a MINE_GRACE launch window it is "armed" (activated) the moment
    any tracked object comes within its invisible MINE_ACTIVATION_RADIUS
    (wrap-aware). Activation is LATCHING - a mine cannot be deactivated -
    and starts an MINE_DETONATION_DELAY countdown;
  - direct contact with any game object (other mines excepted) detonates it
    INSTANTLY, bypassing the countdown. The two halves of the grace window
    differ (spec): during grace NO object may activate the mine, but only
    the CRAFT is immune to a contact detonation - a rock or a stray bullet
    can still kill it before its grace is up;
  - the mine itself only carries position, velocity, and the fuse state.
    The owning game state performs collision arbitration and the detonation
    (burst projectiles + brown explosion + SFX), because those touch the
    shared world lists and the score.

Mines pass through each other (no activation, no collision, spec). The
burst's appearance depends on the weapon power level in play at launch, so
each mine carries its own ``power_level``.
"""

import math

import pygame

from game_constants import (
    MINE_ACTIVATION_RADIUS,
    MINE_CROSSHAIR_ACTIVE,
    MINE_CROSSHAIR_IDLE,
    MINE_CROSSHAIR_PULSE_INTERVAL,
    MINE_CROSSHAIR_PULSE_YELLOWS,
    MINE_DETONATION_DELAY,
    MINE_FILL,
    MINE_GRACE,
    MINE_OUTLINE_WIDTH,
    MINE_RADIUS,
    PLAYER_FRICTION,
    PLAYER_STALL_SPEED,
    WHITE,
    YELLOW,
)
from position_utils import torus_distance, wrap_around


class ShrapnelMine:
    """One drifting shrapnel mine with a proximity fuse."""

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 power_level: int):
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        # The weapon power level that launched this mine, kept on the mine so
        # its detonation still bursts the right projectiles even if the player
        # has switched weapons in the meantime (spec: power level is fixed at
        # launch, not read from the current weapon).
        self.power_level = max(1, min(3, power_level))
        self.radius = MINE_RADIUS
        self.activation_radius = MINE_ACTIVATION_RADIUS
        # Two independent clocks: the launch grace (no activation by anyone,
        # no self-collision by the craft) and the post-activation countdown.
        self.grace_frames = MINE_GRACE
        self._activated = False
        self.detonation_timer = MINE_DETONATION_DELAY
        # Monotonic frame counter for the crosshair pulse (never reset after
        # launch - the pulse keeps running for the mine's whole life, spec).
        self._pulse_frame = 0

    # ------------------------------------------------------------- simulation

    @property
    def in_grace(self) -> bool:
        return self.grace_frames > 0

    @property
    def activated(self) -> bool:
        return self._activated

    @property
    def pulse_onset(self) -> bool:
        """True on the first frame of each 120-frame crosshair pulse cycle
        (the frame the crosshair turns yellow). The game state uses this
        edge to fire the 'pulsing/scanning' one-shot SFX."""
        return self._pulse_frame % MINE_CROSSHAIR_PULSE_INTERVAL == 0

    def activate(self) -> None:
        """Arm the mine. Latching: repeated calls are no-ops (once armed it
        stays armed for the rest of its life - spec)."""
        if self._activated:
            return
        self._activated = True
        self.detonation_timer = MINE_DETONATION_DELAY

    def update(self, width: int, height: int) -> None:
        """Advance one frame: coast to a stop, count the grant/fuse down."""
        self._apply_friction()
        self.x += self.vx
        self.y += self.vy
        self.x, self.y = wrap_around(self.x, self.y, self.radius, width, height)
        if self.grace_frames > 0:
            self.grace_frames -= 1
        if self._activated:
            self.detonation_timer -= 1
        self._pulse_frame += 1

    def _apply_friction(self) -> None:
        # Same friction/stall as the craft (spec): the mine bleeds speed each
        # frame and snaps to a dead stop under the stall threshold.
        self.vx *= PLAYER_FRICTION
        self.vy *= PLAYER_FRICTION
        if math.hypot(self.vx, self.vy) < PLAYER_STALL_SPEED:
            self.vx = 0.0
            self.vy = 0.0

    # ------------------------------------------------------------- collision

    def touching(self, cx: float, cy: float, radius: float,
                 width: int, height: int) -> bool:
        """Wrap-aware contact test against this mine's drawn (collision)
        radius: True when another object's bounding circle overlaps it."""
        return (torus_distance(self.x, self.y, cx, cy, width, height)
                <= self.radius + radius)

    def within_activation_radius(self, cx: float, cy: float, radius: float,
                                 width: int, height: int) -> bool:
        """Wrap-aware proximity test against the invisible 150 px activation
        radius: True when the other object's edge has come within that band
        (measured from the mine's center to the object's near edge)."""
        return (torus_distance(self.x, self.y, cx, cy, width, height)
                <= self.activation_radius + radius)

    # ------------------------------------------------------------------ draw

    def crosshair_color(self) -> tuple:
        """The crosshair's color this frame: YELLOW during the 5-frame pulse,
        otherwise light red (activated) or light gray (armed but quiet)."""
        phase = self._pulse_frame % MINE_CROSSHAIR_PULSE_INTERVAL
        if phase < MINE_CROSSHAIR_PULSE_YELLOWS:
            return YELLOW
        return MINE_CROSSHAIR_ACTIVE if self._activated else MINE_CROSSHAIR_IDLE

    def draw(self, screen: pygame.Surface) -> None:
        cx, cy = int(round(self.x)), int(round(self.y))
        pygame.draw.circle(screen, MINE_FILL, (cx, cy), self.radius)
        pygame.draw.circle(screen, WHITE, (cx, cy), self.radius,
                           width=MINE_OUTLINE_WIDTH)
        # The "crosshair": one vertical and one horizontal line through the
        # center (spec), in a color that reflects the pulse / fuse state.
        color = self.crosshair_color()
        span = self.radius - 3
        pygame.draw.line(screen, color, (cx, cy - span), (cx, cy + span), 2)
        pygame.draw.line(screen, color, (cx - span, cy), (cx + span, cy), 2)
