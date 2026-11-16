"""NPC ships: the hulls the player is not flying (Stage 10).

An NPC is deliberately **not** a :class:`~src.model.game_state.GameState`. The
player's state carries a fuel tank, a cargo hold, passengers, a reverse-course
state machine, hyperspace plumbing, and upgrade levels — none of which an NPC
has. Reusing it would mean phantom fields that read as real ("why does this
pirate have 1000 fuel and 4 passengers?"), and every NPC-only rule would have to
be an ``if not player`` branch somewhere.

What they *do* share is the physics (see :mod:`src.model.physics`) and the
stat vocabulary, so a shield bar and a hitbox mean the same thing on both sides.

Two types:

* :class:`NpcStats` — the immutable spec sheet for one hull, rolled once at
  spawn. Handling and weapons come from the player's **starting** stats (the
  spec's rule for NPC stats is anchored to the ship the player began with, never
  to whatever they have upgraded into, so a maxed-out player is still fighting
  the same pirates they fought on day one).
* :class:`NpcShip` — that spec sheet plus mutable position/velocity/heading and
  current shields/armour, advanced one fixed timestep at a time by an order from
  :mod:`src.model.ai`.

NPC fuel is not modelled at all. "Unlimited fuel" is expressed by the absence of
a fuel field, which cannot drift out of sync with the rule it claims to
implement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.model.ai import ShipOrder
from src.model.factions import require_faction
from src.model.physics import (
    Vec2,
    apply_thrust,
    brake,
    clamp_to_square,
    distance_between,
    heading_degrees_from_direction,
    integrate,
    steer_toward,
)
from src.model.stats import ShipStats
from src.model.weapons import FRAMES_PER_SECOND, Shot, weapon_cooldown_frames

# A rolled stat may never fall to this floor or below. A 0-armour ship is already
# destroyed and a 0-power gun can never damage anything, so a roll that drifted
# that low would create an invulnerable, harmless opponent — and the config
# variance ceiling is what normally prevents it.
_MIN_ROLLED_STAT = 1.0


@dataclass(frozen=True)
class NpcStats:
    """One hull's combat sheet: defences, gun, and handling.

    ``weapon_fire_rate`` and ``weapon_range`` mirror the player's *starting*
    values by the spec's rule, and the handling fields do the same, which is
    what keeps "the player can outrun them with upgrades" true and
    "the player can outrun them by upgrading" the only escape route that works.
    """

    max_shields: float
    max_armor: float
    weapon_power: float
    weapon_fire_rate: float
    weapon_range: float
    turn_rate_deg_per_sec: float
    acceleration_rate: float
    top_speed: float
    length: float
    width: float

    @property
    def hitbox_radius(self) -> float:
        """Radius of the spec's circular hitbox: half the ship's longest axis."""
        return max(self.length, self.width) / 2.0

    @property
    def cooldown_frames(self) -> float:
        """Frames between shots at this gun's fire rate."""
        return weapon_cooldown_frames(self.weapon_fire_rate)

    @property
    def turn_step_degrees(self) -> float:
        """Maximum rotation per fixed timestep at this hull's turn rate."""
        return self.turn_rate_deg_per_sec / FRAMES_PER_SECOND


def roll_stat(
    base: float, multiple: float, variance: float, rng, floor: float = _MIN_ROLLED_STAT
) -> float:
    """Roll one NPC stat: ``base * multiple``, plus or minus ``variance``.

    The spec's example — quadruple the player's starting values, plus or minus up
    to 50% — is ``roll_stat(50, 4.0, 0.5)``: a range of 100..300 for a 50-shield
    starting ship. The floor is defensive: with a legal config
    (``0 <= stat_variance < 1``) the roll can never reach it, but a directly
    constructed absurd variance should produce a barely-alive ship, not one that
    was born already destroyed.
    """
    low = 1.0 - max(0.0, variance)
    high = 1.0 + max(0.0, variance)
    rolled = float(base) * max(0.0, multiple) * rng.uniform(low, high)
    return max(floor, rolled)


def roll_npc_stats(starting_stats: ShipStats, stat_multiple: float, stat_variance: float, rng) -> NpcStats:
    """Roll one NPC's defences and gun against the player's **starting** stats.

    ``starting_stats`` must be the snapshot taken at new-game time, not the live,
    upgrade-mutated one. Passing the live stats is the easy mistake and it
    silently rescales the entire galaxy every time the player buys a shield
    upgrade — the opposite of the spec's "always use the STARTING stats".
    """
    return NpcStats(
        max_shields=roll_stat(starting_stats.max_shields, stat_multiple, stat_variance, rng),
        max_armor=roll_stat(starting_stats.max_armor, stat_multiple, stat_variance, rng),
        weapon_power=roll_stat(starting_stats.weapon_power, stat_multiple, stat_variance, rng),
        # Fire rate and range are *equal to* the player's starting values, not scaled.
        weapon_fire_rate=starting_stats.weapon_fire_rate,
        weapon_range=starting_stats.weapon_range,
        turn_rate_deg_per_sec=starting_stats.turn_rate_deg_per_sec,
        acceleration_rate=starting_stats.acceleration_rate,
        top_speed=starting_stats.top_speed,
        length=starting_stats.length,
        width=starting_stats.width,
    )


class NpcShip:
    """One hostile (or merely present) ship inside the current system.

    Position and velocity are world coordinates in the same planet-centred frame
    the player uses. The ship never decides anything itself: it obeys a
    :class:`~src.model.ai.ShipOrder` handed to it by the encounter's controller,
    which keeps "what the AI wants" and "what a hull can do" in separate places.
    """

    def __init__(
        self,
        faction: str,
        stats: NpcStats,
        position: Vec2 = (0.0, 0.0),
        heading_degrees: float = 0.0,
        velocity: Vec2 = (0.0, 0.0),
    ) -> None:
        require_faction(faction)
        self.faction = faction
        self.stats = stats
        self.position: Vec2 = (float(position[0]), float(position[1]))
        self.velocity: Vec2 = (float(velocity[0]), float(velocity[1]))
        self.heading: float = heading_degrees % 360.0
        # Fresh hulls arrive whole: shields at the top of the bar, armour full.
        self.shields: float = stats.max_shields
        self.armor: float = stats.max_armor
        # A gun that has just been "readied" would fire on frame 1 of a spawn;
        # starting ready is the honest reading of a ship that arrived with its
        # weapons hot, and it keeps the first shot's timing a pure function of
        # distance rather than of when the spawn roll happened to land.
        self._weapon_cooldown: float = 0.0

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------
    @property
    def heading_degrees(self) -> float:
        return self.heading % 360.0

    @property
    def hitbox_radius(self) -> float:
        return self.stats.hitbox_radius

    @property
    def destroyed(self) -> bool:
        """True once armour is gone. The wreck itself is Stage 11's business."""
        return self.armor <= 0.0

    @property
    def weapon_ready(self) -> bool:
        """Whether the gun may fire on this frame (the fire-rate gate)."""
        return self._weapon_cooldown <= 0.0

    def distance_to(self, position: Vec2) -> float:
        """Centre-to-point distance, used for range bands and target choice."""
        return distance_between(self.position, position)

    def bearing_to(self, position: Vec2) -> float:
        """Heading that would point this ship at ``position``."""
        return heading_degrees_from_direction(
            position[0] - self.position[0], position[1] - self.position[1]
        )

    def in_weapon_range(self, position: Vec2) -> bool:
        """Whether a point is inside this gun's configured range."""
        return self.distance_to(position) <= self.stats.weapon_range

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------
    def advance_frame(self, order: ShipOrder, system_half_extent: float) -> Optional[Shot]:
        """Obey one order for one fixed timestep; return the shot if the gun fired.

        One frame does four things in a fixed order — cycle the gun, turn,
        burn (or brake), drift — because the order of those steps *is* the
        physics: rotating before burning means this frame's thrust follows the new
        heading, and drifting after the burn keeps every ship on the same
        integration scheme as the player's (which is what makes the Stage 3 gate,
        "60 frames of thrust from rest reaches exactly top speed", true for NPCs
        too).
        """
        self._weapon_cooldown = max(0.0, self._weapon_cooldown - 1.0)

        if order.turn_to is not None:
            self.heading = steer_toward(
                self.heading, order.turn_to, self.stats.turn_step_degrees
            )

        if order.brake:
            # A brake, not a retrograde burn: it may not overshoot through zero
            # (see :func:`src.model.physics.brake`). Checked before ``burn``
            # because a brake and a burn are mutually exclusive instructions; an
            # order carrying both is the AI contradicting itself, and braking wins.
            self.velocity = brake(self.velocity, self.stats.acceleration_rate)
        elif order.burn is not None:
            self.velocity = apply_thrust(
                self.velocity, order.burn, self.stats.acceleration_rate, self.stats.top_speed
            )

        self.position = integrate(self.position, self.velocity)
        self.position, self.velocity, _ = clamp_to_square(
            self.position, self.velocity, system_half_extent
        )

        return self._release_shot(order)

    def _release_shot(self, order: ShipOrder) -> Optional[Shot]:
        """Fire if the order asks and the gun is ready, resetting the cooldown.

        The gate lives here rather than in the AI because the cooldown is this
        object's state: the controller asks for a shot, and the gun decides
        whether it can honour that request this frame. Two owners of the fire
        rate would mean two cooldown clocks, and the ship would shoot at twice
        its configured rate.
        """
        if not order.fire or order.aim is None or not self.weapon_ready:
            return None
        self._weapon_cooldown = self.stats.cooldown_frames
        return Shot(
            faction=self.faction,
            owner=self,
            origin=self.position,
            direction=order.aim,
            ship_velocity=self.velocity,
            weapon_power=self.stats.weapon_power,
            weapon_range=self.stats.weapon_range,
        )

    # ------------------------------------------------------------------
    def apply_damage(self, amount: float) -> None:
        """Shield-first, then armour, exactly as the spec's damage order says.

        Stage 11 calls this; Stage 10 defines it so the ordering rule exists once
        and cannot be reimplemented differently by whoever wires up projectiles.
        Shields absorb first and are *not* regenerated by anything except a
        player jump (NPCs have no shield or armour regeneration at all).
        """
        damage = max(0.0, float(amount))
        absorbed = min(self.shields, damage)
        self.shields -= absorbed
        self.armor -= damage - absorbed

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"NpcShip(faction={self.faction!r}, shields={self.shields:.0f}, "
            f"armor={self.armor:.0f}, at={self.position[0]:.0f},{self.position[1]:.0f})"
        )
