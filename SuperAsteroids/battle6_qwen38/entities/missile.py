"""Homing missile: a self-steering light gray capsule that flies to a target.

Per the spec (Homing Missiles):
  - launches from the craft's tail with the craft's velocity; the craft's
    own heading is its initial heading, and it turns toward its locked
    target at the craft's rotation rate (PLAYER_ROTATION_SPEED);
  - thrusts continuously at the craft's acceleration/max speed
    (PLAYER_ACCELERATION / PLAYER_MAX_SPEED) with the same thruster puffs;
  - locks onto whatever asteroid or UFO is nearest the craft AT LAUNCH
    (that selection is the weapon's job, not the entity's); if the target
    is destroyed before the missile impacts it, the entity re-locks onto
    the nearest live asteroid/UFO to the MISSILE (the homing entity),
    wrap-aware via torus_distance;
  - unlimited fuel and unlimited travel distance: it never expires and
    never draws on the player's tank;
  - wraps the screen; grace-protected from the craft for MISSILE_GRACE
    frames (no impact with the craft during that window);
  - the bounding circle (MISSILE_RADIUS, half the length) is used for ALL
    collision checks - the spec gives no other collision shape for a
    capsule.

The entity owns geometry, steering, and drawing. The owning game state
performs re-locking (it holds the live lists) and the collision arbitration,
exactly like the shrapnel mine and gravity well.
"""

import math

import pygame

from game_constants import (
    MISSILE_COLOR,
    MISSILE_GRACE,
    MISSILE_LENGTH,
    MISSILE_NOZZLE_COLOR,
    MISSILE_OUTLINE_WIDTH,
    MISSILE_RADIUS,
    MISSILE_WIDTH,
    PLAYER_ACCELERATION,
    PLAYER_MAX_SPEED,
    PLAYER_ROTATION_SPEED,
    WHITE,
)
from position_utils import shortest_delta, torus_distance, wrap_around


def _capsule_shape() -> list:
    """The 20x6 capsule outline, relative to the center (long axis = +X).

    Eight-segment semicircular ends keep the shape smooth without an
    arc routine; the straight sides are implicit between the endpoint
    pairs (the polygon closes across both ends).
    """
    half_len = MISSILE_LENGTH / 2.0
    half_w = MISSILE_WIDTH / 2.0
    points = []
    for i in range(8):   # right (nose) end, top -> bottom
        angle = math.radians(-90.0 + i * 30.0)
        points.append((half_len + half_w * math.cos(angle),
                       half_w * math.sin(angle)))
    for i in range(8):   # left (tail) end, bottom -> top
        angle = math.radians(90.0 + i * 30.0)
        points.append((-half_len + half_w * math.cos(angle),
                       half_w * math.sin(angle)))
    return points


# The outline never changes - build it once and reuse it every frame.
_SHAPE = _capsule_shape()


class HomingMissile:
    """One self-steering homing missile."""

    def __init__(self, x: float, y: float, angle: float,
                 vx: float, vy: float, target=None):
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        self.angle = float(angle)
        # The locked-on object (an Asteroid or UFO). None while there is
        # nothing to lock onto - the missile then simply flies straight.
        self.target = target
        self.radius = MISSILE_RADIUS
        self.grace_frames = MISSILE_GRACE

    # ------------------------------------------------------------- simulation

    @property
    def in_grace(self) -> bool:
        return self.grace_frames > 0

    @property
    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)

    def relock(self, asteroids, ufos, width: int, height: int) -> None:
        """Lock onto the nearest live asteroid or UFO to THIS missile
        (torus distance), or None when the field is empty. Called by the
        owning state when the current target dies."""
        candidates = list(asteroids) + list(ufos)
        if not candidates:
            self.target = None
            return
        self.target = min(
            candidates,
            key=lambda obj: torus_distance(self.x, self.y, obj.x, obj.y,
                                           width, height),
        )

    def update(self, width: int, height: int) -> None:
        """Advance one frame: steer toward the target, thrust, wrap."""
        self._steer(width, height)
        self._thrust()
        self.x += self.vx
        self.y += self.vy
        self.x, self.y = wrap_around(self.x, self.y, self.radius,
                                     width, height)
        if self.grace_frames > 0:
            self.grace_frames -= 1

    def _steer(self, width: int, height: int) -> None:
        """Rotate toward the target at the craft's rotation rate."""
        if self.target is None:
            return  # nothing to lock onto: fly straight
        dx = shortest_delta(self.target.x - self.x, width)
        dy = shortest_delta(self.target.y - self.y, height)
        if abs(dx) < 1e-9 and abs(dy) < 1e-9:
            return  # coincident: no direction to fall toward
        desired = math.atan2(dy, dx)
        current = math.radians(self.angle)
        diff = (desired - current + math.pi) % (2.0 * math.pi) - math.pi
        max_turn = math.radians(PLAYER_ROTATION_SPEED)
        if abs(diff) <= max_turn:
            self.angle = math.degrees(desired) % 360.0
        else:
            self.angle = (self.angle
                          + math.copysign(PLAYER_ROTATION_SPEED, diff)) % 360.0

    def _thrust(self) -> None:
        """Continuous thrust: the missile always burns (no friction).

        Mirrors PlayerCraft._thrust - same acceleration and max-speed clamp.
        """
        rad = math.radians(self.angle)
        self.vx += math.cos(rad) * PLAYER_ACCELERATION
        self.vy += math.sin(rad) * PLAYER_ACCELERATION
        if self.speed > PLAYER_MAX_SPEED:
            scale = PLAYER_MAX_SPEED / self.speed
            self.vx *= scale
            self.vy *= scale

    # ------------------------------------------------------------- collision

    def touching(self, cx: float, cy: float, radius: float,
                 width: int, height: int) -> bool:
        """Wrap-aware contact test against this missile's bounding circle."""
        return (torus_distance(self.x, self.y, cx, cy, width, height)
                <= self.radius + radius)

    # ------------------------------------------------------------------ draw

    def draw(self, screen: pygame.Surface) -> None:
        rad = math.radians(self.angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        # Nozzle first (it sits behind the capsule).
        nozzle = [
            (-MISSILE_LENGTH / 2 - 4.0, -2.0),
            (-MISSILE_LENGTH / 2 - 4.0, 2.0),
            (-MISSILE_LENGTH / 2, 2.0),
            (-MISSILE_LENGTH / 2, -2.0),
        ]
        pygame.draw.polygon(screen, MISSILE_NOZZLE_COLOR, [
            (int(round(self.x + px * cos_a - py * sin_a)),
             int(round(self.y + px * sin_a + py * cos_a)))
            for px, py in nozzle
        ])
        points = [
            (int(round(self.x + px * cos_a - py * sin_a)),
             int(round(self.y + px * sin_a + py * cos_a)))
            for px, py in _SHAPE
        ]
        pygame.draw.polygon(screen, MISSILE_COLOR, points)
        pygame.draw.polygon(screen, WHITE, points,
                            width=MISSILE_OUTLINE_WIDTH)
