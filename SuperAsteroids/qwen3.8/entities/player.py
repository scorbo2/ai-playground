"""Player craft: an elongated triangle with the classic Asteroids flight model.

Screen angles are used throughout (degrees, 0 = +X axis, positive toward
+Y in screen coordinates), the same convention that orients asteroid
polygons - so "up" is PLAYER_START_ANGLE (-90) and the rotation math below
is identical in spirit to the asteroid tumble.

No weapons yet: Space does nothing until Stage 4.
"""

import math

import pygame

from game_constants import (
    LIGHT_GRAY,
    PLAYER_ACCELERATION,
    PLAYER_FRICTION,
    PLAYER_MAX_SPEED,
    PLAYER_OUTLINE_WIDTH,
    PLAYER_RADIUS,
    PLAYER_ROTATION_SPEED,
    PLAYER_SHAPE_HEIGHT,
    PLAYER_SHAPE_WIDTH,
    PLAYER_START_ANGLE,
    PLAYER_STALL_SPEED,
    WHITE,
)
from position_utils import wrap_around

# Vertices relative to the craft's center, defined in the "facing RIGHT"
# (angle 0) pose: apex forward, base 20 px wide aft. The per-frame rotation
# below orients them to the current heading ("up" at start).
_CRAFT_POINTS = (
    (PLAYER_SHAPE_HEIGHT / 2, 0.0),
    (-PLAYER_SHAPE_HEIGHT / 2, PLAYER_SHAPE_WIDTH / 2),
    (-PLAYER_SHAPE_HEIGHT / 2, -PLAYER_SHAPE_WIDTH / 2),
)


class PlayerCraft:
    """The player's craft: rotation, thrust, friction, max speed, screen wrap."""

    def __init__(self, x: float, y: float):
        # All state is assigned by reset(); the constructor just places it.
        self.reset(x, y)

    def reset(self, x: float, y: float) -> None:
        """Default starting state: at (x, y), facing up, velocity 0 (spec:
        Game Mode / level advancement). Used at new game and level starts."""
        self.x = float(x)
        self.y = float(y)
        self.vx = 0.0
        self.vy = 0.0
        self.angle = PLAYER_START_ANGLE

    @property
    def speed(self) -> float:
        return math.hypot(self.vx, self.vy)

    def update(self, thrusting: bool, turning: int, width: int, height: int) -> None:
        """Advance one frame.

        ``turning`` is -1 (left) / 0 (straight) / +1 (right) - the owning
        state decodes held keys into these intents, so the craft never sees
        raw pygame key codes.
        """
        self._rotate(turning)
        if thrusting:
            self._thrust()
        else:
            self._apply_friction()
        self.x += self.vx
        self.y += self.vy
        self.x, self.y = wrap_around(self.x, self.y, PLAYER_RADIUS, width, height)

    def draw(self, screen: pygame.Surface) -> None:
        rad = math.radians(self.angle)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        points = [
            (int(round(self.x + px * cos_a - py * sin_a)),
             int(round(self.y + px * sin_a + py * cos_a)))
            for px, py in _CRAFT_POINTS
        ]
        pygame.draw.polygon(screen, LIGHT_GRAY, points)
        pygame.draw.polygon(screen, WHITE, points, width=PLAYER_OUTLINE_WIDTH)

    # ------------------------------------------------------------- internals

    def _rotate(self, turning: int) -> None:
        if turning == 0:
            return  # release stops rotation immediately (spec)
        self.angle = (self.angle + turning * PLAYER_ROTATION_SPEED) % 360.0

    def _thrust(self) -> None:
        rad = math.radians(self.angle)
        self.vx += math.cos(rad) * PLAYER_ACCELERATION
        self.vy += math.sin(rad) * PLAYER_ACCELERATION
        if self.speed > PLAYER_MAX_SPEED:
            # Cap at max speed, preserving the heading.
            scale = PLAYER_MAX_SPEED / self.speed
            self.vx *= scale
            self.vy *= scale

    def _apply_friction(self) -> None:
        self.vx *= PLAYER_FRICTION
        self.vy *= PLAYER_FRICTION
        # Spec: under the stall threshold, stop cleanly instead of coasting
        # at a creep speed forever.
        if self.speed < PLAYER_STALL_SPEED:
            self.vx = 0.0
            self.vy = 0.0

    def bounce(self, direction_x: float, direction_y: float, speed: float) -> None:
        """Ramming-shield response (spec: Weapons -> Ramming Shield): the
        craft's current direction/velocity is DISCARDED and replaced with
        ``speed`` px/frame directly away from the impact point, clamped to
        the max craft speed."""
        length = math.hypot(direction_x, direction_y)
        if length <= 1e-9:
            # Degenerate (centers coincident): no defined "away" direction.
            return
        self.vx = direction_x / length * speed
        self.vy = direction_y / length * speed
        if self.speed > PLAYER_MAX_SPEED:
            scale = PLAYER_MAX_SPEED / self.speed
            self.vx *= scale
            self.vy *= scale


def player_hits_asteroid(craft: PlayerCraft, asteroid,
                         width: int, height: int) -> bool:
    """Wrap-aware (torus) circle-circle collision between the craft's
    bounding circle and an asteroid's.

    Collision must respect screen wrap (spec: "Collision detection"), so
    each axis uses the SHORTER distance, straight across or around the wrap:
    e.g. the craft 5 px from the left edge and a 40 px asteroid 5 px from
    the right edge, same Y, are 10 px center-to-center -> a hit.
    """
    dx = abs(craft.x - asteroid.x)
    if dx > width / 2:
        dx = width - dx
    dy = abs(craft.y - asteroid.y)
    if dy > height / 2:
        dy = height - dy
    return math.hypot(dx, dy) < PLAYER_RADIUS + asteroid.radius
