"""NPC steering and fire control (Stage 10).

The spec allows the AI to be basic, and this is basic — but "basic" is not the
same as "vague". Every rule below is a pure function that a test can pin, and
the whole controller reduces to one decision per ship per frame: *which way to
point, whether to burn, and whether to shoot*.

The three behaviours the spec asks for:

1. **Thrust toward the nearest hostile.** Chased until the ship is inside its
   engagement band (a fraction of its own weapon range).
2. **When within weapon range, stop thrusting and fire at the configured rate
   with a configurable aim jitter.** The "stop thrusting" half is the band: the
   ship brakes early enough that it arrives *inside* the band instead of
   ploughing through it, so it does not park on the exact range circle where a
   tenth of a pixel decides whether its gun is in range.
3. **No hostiles: hold position.** There is no drag in this universe, so holding
   position is an active retrograde burn down to a standstill, then nothing.

Nothing here mutates a ship, and nothing here knows that projectiles exist: the
output is a :class:`ShipOrder`, and the ship decides whether it can honour the
fire request (see :meth:`src.model.npc_ship.NpcShip.advance_frame`).
"""

from __future__ import annotations

import random as _random_lib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from src.model.physics import (
    Vec2,
    brake,
    is_moving,
    rotate_direction,
    speed_of,
    stopping_distance,
    unit_from_heading_degrees,
)

if TYPE_CHECKING:  # pragma: no cover - typing only, breaks the ship <-> ai cycle
    from src.model.npc_ship import NpcShip

# Motion modes chosen for one ship on one frame. Strings (not enums) match the
# rest of this codebase and keep them printable in test failure messages.
MOTION_CHASE = "chase"
MOTION_BRAKE = "brake"
MOTION_COAST = "coast"


@dataclass(frozen=True)
class AiTuning:
    """The two AI knobs that come from config.

    A value object rather than two loose arguments, because the pair always
    travels together and a swapped argument order would be invisible in a
    failure message.
    """

    engage_range_fraction: float = 0.85
    aim_jitter_degrees: float = 4.0

    def __post_init__(self) -> None:
        if not 0.0 < self.engage_range_fraction <= 1.0:
            raise ValueError(
                "engage_range_fraction must be in (0, 1]: the band a ship holds is "
                f"{self.engage_range_fraction} of its weapon range"
            )
        if self.aim_jitter_degrees < 0.0:
            raise ValueError("aim_jitter_degrees cannot be negative")

    def band_for(self, weapon_range: float) -> float:
        """Radius at which a ship with ``weapon_range`` stops closing on a target.

        A fraction of the gun's own range rather than the range itself: a ship
        that parks exactly on the range circle is one float wobble away from
        deciding its gun is out of range, and the fraction is the config knob
        that sets how aggressively the fleet crowds in on the player.
        """
        return float(weapon_range) * self.engage_range_fraction


@dataclass(frozen=True)
class Target:
    """What a ship is shooting at this frame.

    ``ship`` is the NPC being shot at, or ``None`` when the target is the
    player: the player is not an :class:`NpcShip`, and inventing a fake one to
    keep the type uniform would put a phantom pirate hull in the middle of the
    player's own ship.
    """

    position: Vec2
    ship: Optional["NpcShip"] = None

    @property
    def is_player(self) -> bool:
        return self.ship is None


@dataclass(frozen=True)
class ShipOrder:
    """What one ship should do on one fixed timestep.

    ``turn_to`` is an absolute heading in degrees (``None`` keeps the current
    facing), ``burn`` is a direction to thrust along (``None`` means coast), and
    ``fire``/``aim`` are the trigger and the jittered muzzle direction.

    ``brake`` is a separate instruction rather than ``burn`` set to the retrograde
    vector, because it is a different physical act: a brake is a burn limited to
    the speed that is left, so a ship asked to stop actually stops instead of
    oscillating through zero (see :func:`src.model.physics.brake`).

    NPCs turn to an absolute heading and burn along an arbitrary vector rather
    than mimicking the player's keyboard controls. They are not keyboard-driven;
    pretending otherwise would mean writing a state machine that presses its own
    arrow keys, and the reverse-course machinery would be along for the ride.
    """

    turn_to: Optional[float] = None
    burn: Optional[Vec2] = None
    brake: bool = False
    fire: bool = False
    aim: Optional[Vec2] = None


@dataclass(frozen=True)
class Engagement:
    """Everything the encounter worked out about one ship this frame.

    Carries the chosen target so the encounter can emit shots with the right
    provenance (and so Stage 11's "who shot whom" logging has an answer) without
    recomputing the target choice — a second, slightly different answer is how
    the AI and the damage report end up disagreeing about who was shooting.
    """

    ship: "NpcShip"
    target: Optional[Target]
    distance: float
    motion: str
    order: ShipOrder


def engagement_band(weapon_range: float, range_fraction: float) -> float:
    """Convenience wrapper over :meth:`AiTuning.band_for` (validation lives there)."""
    return AiTuning(engage_range_fraction=range_fraction).band_for(weapon_range)


def choose_motion(
    distance: float, speed: float, acceleration: float, band: float
) -> str:
    """Chase, brake, or coast — the entire speed control for one ship.

    The lead-in check (``distance - stopping_distance``) is what keeps the ship
    from ploughing through the band: at the fixed timestep's accelerations a
    ship at top speed needs ``v²/2a`` pixels to stop, and starting the retrograde
    burn that far out means it arrives at the band standing still rather than
    overshooting, turning around, and repeating. Parking still *outside* the band
    is not a stable state either: the chase resumes the frame after it stops.
    """
    if distance > band:
        if is_moving(speed) and distance - stopping_distance(speed, acceleration) <= band:
            return MOTION_BRAKE
        return MOTION_CHASE
    if is_moving(speed):
        # Inside the band and moving: kill the drift, or inertia walks the ship
        # out of range of its own gun.
        return MOTION_BRAKE
    return MOTION_COAST


def jittered_aim(
    bearing_degrees: float, jitter_degrees: float, rng: "_random_lib.Random"
) -> Vec2:
    """Aim unit vector: the true bearing, deflected by up to ``jitter_degrees``.

    Jitter lands on the *shot*, never on the hull's facing: a ship that turns
    4° off-target every frame would wobble across the screen for no reason the
    player can read, whereas a ship that aims true and hits wide is exactly the
    "they are not very good at this" flavour the spec asks for.
    """
    if jitter_degrees <= 0.0:
        return unit_from_heading_degrees(bearing_degrees)
    deflection = rng.uniform(-jitter_degrees, jitter_degrees)
    return rotate_direction(unit_from_heading_degrees(bearing_degrees), deflection)


def plan_order(
    ship: "NpcShip",
    target: Optional[Target],
    tuning: AiTuning,
    rng: "_random_lib.Random",
) -> Engagement:
    """Decide one ship's frame: face the target, close or hold, and pull the trigger.

    With no target the ship only brakes to a standstill and keeps its facing —
    the spec's "hold position", implemented as a retrograde burn because
    Newtonian drift does not stop on its own.
    """
    if target is None:
        # "No hostiles: hold position." With no drag, that is an active brake down
        # to a standstill; once stopped there is nothing left to do, and a ship
        # that reported MOTION_BRAKE forever would suggest an engine running.
        moving = is_moving(speed_of(ship.velocity))
        return Engagement(
            ship=ship,
            target=None,
            distance=float("inf"),
            motion=MOTION_BRAKE if moving else MOTION_COAST,
            order=ShipOrder(turn_to=None, brake=moving),
        )

    distance = ship.distance_to(target.position)
    bearing = ship.bearing_to(target.position)
    band = tuning.band_for(ship.stats.weapon_range)
    motion = choose_motion(distance, speed_of(ship.velocity), ship.stats.acceleration_rate, band)

    burn: Optional[Vec2] = None
    braking = False
    if motion == MOTION_CHASE:
        burn = unit_from_heading_degrees(bearing)
    elif motion == MOTION_BRAKE:
        braking = True

    in_range = distance <= ship.stats.weapon_range
    aim = jittered_aim(bearing, tuning.aim_jitter_degrees, rng) if in_range else None

    return Engagement(
        ship=ship,
        target=target,
        distance=distance,
        motion=motion,
        order=ShipOrder(
            turn_to=bearing,
            burn=burn,
            brake=braking,
            # "When within weapon range, ... fire at max firing rate": the ship
            # holds the trigger down, and its own cooldown sets the actual rate.
            fire=in_range,
            aim=aim,
        ),
    )
