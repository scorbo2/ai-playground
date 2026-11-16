"""Shared 2D movement maths for every ship in the game (Stage 10).

The player's ship and the NPC fleet obey the same rules: thrust along a
direction, coast when not thrusting (Newtonian drift), get pinned by the system
boundary, and never exceed a top speed. Those rules used to live privately in
:class:`~src.model.game_state.GameState`. Now that NPC ships exist, keeping two
copies would mean two definitions of "top speed" and two definitions of "the
edge of the system" — and the first disagreement between them would be a ship
that flies through a wall, or an NPC that outruns a config change.

Everything here is pure: vectors are ``(x, y)`` float tuples, headings are
degrees in a **y-down** screen space (0° is east, 90° is south, so increasing
heading is a clockwise turn), and nothing imports pygame.

Angles are deliberately *normalised* by the helpers that return them, so a
caller can compare headings without doing its own modulo arithmetic.
"""

from __future__ import annotations

import math
from typing import Optional, Tuple

Vec2 = Tuple[float, float]

# Below this speed a ship counts as standing still. Anything smaller than a
# hundredth of a pixel per frame is float noise from a braking burn, and
# treating it as motion would make a "holding position" ship jitter forever.
_STANDING_STILL_SPEED = 0.01


def unit_from_heading_degrees(heading_degrees: float) -> Vec2:
    """Unit vector pointing along ``heading_degrees`` (0° = east, 90° = south)."""
    radians = math.radians(heading_degrees)
    return (math.cos(radians), math.sin(radians))


def heading_degrees_from_direction(dx: float, dy: float) -> float:
    """Heading (normalised to ``[0, 360)``) that points along ``(dx, dy)``.

    A zero-length direction has no heading; callers get 0° back rather than a
    math domain error, because "no direction" is a normal state (a ship that has
    not moved yet), not a crash.
    """
    if abs(dx) < 1e-12 and abs(dy) < 1e-12:
        return 0.0
    return math.degrees(math.atan2(dy, dx)) % 360.0


def distance_between(first: Vec2, second: Vec2) -> float:
    """Straight-line distance between two world coordinates."""
    return math.hypot(first[0] - second[0], first[1] - second[1])


def speed_of(velocity: Vec2) -> float:
    """Scalar speed in pixels per frame."""
    return math.hypot(velocity[0], velocity[1])


def is_moving(speed: float) -> bool:
    """True when a speed counts as real motion rather than float noise."""
    return speed >= _STANDING_STILL_SPEED


def is_standing_still(velocity: Vec2) -> bool:
    """True when a velocity is small enough to count as "not moving"."""
    return not is_moving(speed_of(velocity))


def signed_angle_degrees(from_degrees: float, to_degrees: float) -> float:
    """Smallest signed rotation from ``from_degrees`` to ``to_degrees``.

    Result lies in ``[-180, 180)``: positive turns clockwise on screen (heading
    increases), negative turns counter-clockwise.
    """
    return (to_degrees - from_degrees + 180.0) % 360.0 - 180.0


def heading_error_degrees(ship_heading: float, target_heading: float) -> float:
    """How far a ship is from facing ``target_heading``, signed and shortest-way."""
    return signed_angle_degrees(ship_heading, target_heading)


def steer_toward(
    heading: float, target_heading: float, max_step_degrees: float
) -> float:
    """Rotate ``heading`` toward ``target_heading`` by at most ``max_step_degrees``.

    Takes the shortest way round, and snaps exactly onto the target when the
    remaining arc is shorter than a full step — otherwise a turning ship would
    wobble around its target by up to one step forever.
    """
    if max_step_degrees <= 0.0:
        return heading % 360.0
    offset = signed_angle_degrees(heading, target_heading)
    if abs(offset) <= max_step_degrees:
        return target_heading % 360.0
    return (heading + math.copysign(max_step_degrees, offset)) % 360.0


def rotate_direction(direction: Vec2, delta_degrees: float) -> Vec2:
    """Rotate a direction vector, for aim jitter and reverse-course burns."""
    angle = math.radians(delta_degrees)
    cosine, sine = math.cos(angle), math.sin(angle)
    x, y = direction
    return (x * cosine - y * sine, x * sine + y * cosine)


def normalise(direction: Vec2) -> Vec2:
    """Unit vector in the same direction; ``(0, 0)`` stays ``(0, 0)``."""
    x, y = direction
    length = math.hypot(x, y)
    if length < 1e-12:
        return (0.0, 0.0)
    return (x / length, y / length)


def brake(velocity: Vec2, acceleration: float) -> Vec2:
    """A retrograde burn that slows a ship down, and never reverses it.

    Deliberately not ``apply_thrust`` along the retrograde vector: a thrust step
    larger than the remaining speed flips the velocity through zero, so a ship
    trying to hold position would jitter back and forth at a fraction of a pixel
    per frame for the rest of the game. Clamping the step to the remaining speed
    is what makes "stopped" reachable with a fixed timestep.

    Also deliberately not ``apply_thrust`` in general: ``apply_thrust`` ignores
    thrust once a ship sits at its speed cap, which is the player's "the throttle
    is already hard down" behaviour but would make braking impossible at top
    speed - exactly when the AI needs it most.
    """
    speed = speed_of(velocity)
    if acceleration <= 0.0 or speed == 0.0:
        return (float(velocity[0]), float(velocity[1]))
    remaining = speed - min(acceleration, speed)
    scale = remaining / speed
    return (velocity[0] * scale, velocity[1] * scale)


def stopping_distance(speed: float, acceleration: float) -> float:
    """Pixels needed to brake to a standstill at ``acceleration``.

    ``v² / 2a``. Returns 0 for a non-positive acceleration (a ship that cannot
    brake cannot stop, and reporting infinity would make the AI's chase/brake
    decision a permanent brake).
    """
    if acceleration <= 0.0:
        return 0.0
    return (speed * speed) / (2.0 * acceleration)


def apply_thrust(
    velocity: Vec2, direction: Vec2, acceleration: float, speed_cap: Optional[float] = None
) -> Vec2:
    """Add ``acceleration`` along ``direction`` to ``velocity``, optionally capped.

    The cap clamps the *magnitude*: the resulting vector is rescaled onto the
    cap so the speed lands exactly on it instead of a hair over. Without the cap
    this is also the hyperspace burn, which the spec lets exceed top speed —
    hence ``speed_cap=None`` there rather than a second, copy-pasted integrator.
    """
    if acceleration <= 0.0:
        return (float(velocity[0]), float(velocity[1]))

    unit = normalise(direction)
    if unit == (0.0, 0.0):
        return (float(velocity[0]), float(velocity[1]))

    if speed_cap is not None and speed_of(velocity) >= speed_cap:
        return (float(velocity[0]), float(velocity[1]))

    vx = velocity[0] + acceleration * unit[0]
    vy = velocity[1] + acceleration * unit[1]
    if speed_cap is not None:
        new_speed = math.hypot(vx, vy)
        if new_speed > speed_cap:
            scale = speed_cap / new_speed
            return (vx * scale, vy * scale)
    return (vx, vy)


def integrate(position: Vec2, velocity: Vec2) -> Vec2:
    """A body in motion stays in motion: position advances by the velocity."""
    return (position[0] + velocity[0], position[1] + velocity[1])


def clamp_to_square(
    position: Vec2, velocity: Vec2, half_extent: float
) -> Tuple[Vec2, Vec2, bool]:
    """Pin a position inside the square ``[-half, +half]``, scrubbing outward velocity.

    Returns ``(position, velocity, clamped)``. Zeroing the velocity component
    that pointed through the wall is what makes the spec's "cannot move any
    further in that direction" behave: a ship left pressed against an edge
    would otherwise accumulate a decade of outward drift and slingshot away the
    moment it turned around.
    """
    x, y = position
    vx, vy = velocity
    clamped_x = min(max(x, -half_extent), half_extent)
    clamped_y = min(max(y, -half_extent), half_extent)
    if clamped_x != x:
        vx = 0.0
    if clamped_y != y:
        vy = 0.0
    return (clamped_x, clamped_y), (vx, vy), (clamped_x, clamped_y) != (x, y)


def random_point_in_square(
    rng, half_extent: float
) -> Vec2:
    """A uniformly random world coordinate inside the system square."""
    return (rng.uniform(-half_extent, half_extent), rng.uniform(-half_extent, half_extent))
