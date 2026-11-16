"""Projectiles, hits, and what a hit does to the rest of the galaxy (Stage 11).

Stage 10 ended with ships that *want* to shoot: the AI produced a :class:`Shot`
and the scene kept it in a list labelled "pending". This module is what was
pending. It owns three things and nothing else:

* **A projectile in flight** (:class:`Projectile`) — launched from a :class:`Shot`
  with the spec's velocity composition (the firing ship's velocity plus
  ``combat.projectile_speed_bonus`` along the aim), carrying the weapon's power and
  the gun's range, which is also the projectile's own travel budget.
* **Who it hits** (:class:`Combatant`, :class:`Impact`) — the player plus the
  system's fleet, resolved under the spec's pass-through rules: a projectile never
  hits the ship that fired it, never hits a ship of its own side, and passes
  straight through a planet, a wreck, and an immune hull.
* **What a kill pays** (:func:`bounty_for_kill`) — credits and the copy that goes
  with them, keyed by the *victim's* faction.

Not modelled here, on purpose: particles, sound, and every other presentation of
an impact (the scene turns :class:`Impact` events into those), and any of the AI's
opinions about what to shoot at. The damage order itself lives in
:func:`src.model.stats.apply_damage_order`, shared with the player's hull so there
is exactly one answer to "do shields soak first?".

One :class:`Gunfight` belongs to one system visit, exactly like the
:class:`~src.model.encounter.Encounter` it shoots at. That is not tidiness: the
ships a projectile came from stop existing when the player jumps, and a missile
that outlives its universe is a ghost that can still kill you in a system it was
never fired in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

from src.model.factions import (
    FACTION_BOBBER,
    FACTION_LOCALHOSTER,
    FACTION_PIRATE,
    FACTION_PLAYER,
    PlayerRelations,
    faction_label,
    is_npc_faction,
    require_combatant,
    war_side_of,
)
from src.model.physics import Vec2, speed_of
from src.model.weapons import Shot


@dataclass(frozen=True)
class CombatRules:
    """Every combat tunable, hoisted out of the ``combat`` config section once.

    Same reasoning as :class:`~src.model.encounter.SpawnRules` and
    :class:`~src.model.economy.EconomyRules`: the model asks for
    ``rules.projectile_speed_bonus`` instead of reaching into a config dict, and
    Stage 14's config sweep has one object to poke to prove the numbers are not
    hard-coded.
    """

    projectile_speed_bonus: float
    projectile_diameter: int
    pirate_bounty: float
    bobber_bounty: float
    localhoster_bounty: float

    def __post_init__(self) -> None:
        """An invalid CombatRules object may not exist at all.

        Validation lives here rather than only in :meth:`from_config` (the same
        lesson Stage 10 learned with ``SpawnRules``): a test, a tool, or a future
        save-file loader must not be able to build a ruleset the projectile code
        then chokes on mid-dogfight.
        """
        if self.projectile_speed_bonus < 0.0:
            raise ValueError(
                "combat.projectile_speed_bonus cannot be negative: a projectile's "
                f"launch speed is the ship's velocity plus this bonus (got {self.projectile_speed_bonus})"
            )
        if self.projectile_diameter < 1:
            raise ValueError(
                "combat.projectile_diameter must be at least 1 pixel: a projectile "
                "the player cannot see is a hazard, not a weapon"
            )
        for name, credits in (
            ("pirate_bounty", self.pirate_bounty),
            ("bobber_bounty", self.bobber_bounty),
            ("localhoster_bounty", self.localhoster_bounty),
        ):
            if credits < 0.0:
                raise ValueError(f"combat.{name} cannot be negative")

    @classmethod
    def from_config(cls, combat_config: dict) -> "CombatRules":
        """Build from the validated ``combat`` config section."""
        try:
            return cls(
                projectile_speed_bonus=float(combat_config["projectile_speed_bonus"]),
                projectile_diameter=int(combat_config["projectile_diameter"]),
                pirate_bounty=float(combat_config["pirate_bounty"]),
                bobber_bounty=float(combat_config["bobber_bounty"]),
                localhoster_bounty=float(combat_config["localhoster_bounty"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid combat config section: {exc}") from exc

    @property
    def projectile_radius(self) -> int:
        """The ``draw.circle`` radius for a projectile, in pixels.

        ``draw.circle`` paints a filled disc ``2r + 1`` pixels across, so the
        spec's "solid 3px diameter circles" is radius 1. The config says diameter
        because that is the number the spec fixes; converting here (and only
        here) keeps that conversion from being re-derived at every call site, which
        is how a 3px dot ends up 6px wide on one screen and 3px on another.
        """
        return max(1, int(self.projectile_diameter) // 2)

    def bounty_for(self, victim_faction: str) -> float:
        """The configured bounty for destroying a hull **of** ``victim_faction``.

        Keyed by the victim, not by the payer: ``combat.localhoster_bounty`` is
        what the player is paid for killing a Localhoster (the Bobbers foot the
        bill — see :func:`bounty_for_kill`). Two of the three shipped configs set
        all three values the same, which is precisely why the direction of that
        mapping has to be written down somewhere.
        """
        return {
            FACTION_PIRATE: self.pirate_bounty,
            FACTION_LOCALHOSTER: self.localhoster_bounty,
            FACTION_BOBBER: self.bobber_bounty,
        }[victim_faction]


# ---------------------------------------------------------------------------
# The projectile
# ---------------------------------------------------------------------------
@dataclass
class Projectile:
    """One shot in flight, in world coordinates.

    A projectile is inert by design: it holds no reference to a target (a
    homing missile would be a different game), and it is removed either when it
    spends its travel budget (``weapon_range``) or when it hits something.

    ``travelled`` is the *world-space* path length, which is what the spec's
    "max cumulative travel distance" measures — not the distance from the muzzle,
    which for a shot fired from a moving ship is not the same number.
    """

    faction: str
    owner: object
    position: Vec2
    velocity: Vec2
    weapon_power: float
    max_travel: float
    travelled: float = 0.0

    def __post_init__(self) -> None:
        require_combatant(self.faction)
        self.position = (float(self.position[0]), float(self.position[1]))
        self.velocity = (float(self.velocity[0]), float(self.velocity[1]))
        self.weapon_power = max(0.0, float(self.weapon_power))
        self.max_travel = max(0.0, float(self.max_travel))
        self.travelled = max(0.0, float(self.travelled))

    @classmethod
    def from_shot(cls, shot: Shot, rules: CombatRules) -> "Projectile":
        """Launch a shot: the spec's velocity composition happens here, once.

        ``Shot.muzzle_velocity`` is ship velocity + bonus along the aim direction,
        which is why a projectile fired while the shooter is moving is faster on
        one side of a dogfight than the other. Both the player's gun and an NPC's
        go through this function, so no hull gets its own private ballistics.
        """
        return cls(
            faction=shot.faction,
            owner=shot.owner,
            position=shot.origin,
            velocity=shot.muzzle_velocity(rules.projectile_speed_bonus),
            weapon_power=shot.weapon_power,
            max_travel=shot.weapon_range,
        )

    @property
    def speed(self) -> float:
        return speed_of(self.velocity)

    @property
    def range_left(self) -> float:
        """Pixels this projectile may still cross before it dies harmlessly."""
        return max(0.0, self.max_travel - self.travelled)

    @property
    def spent(self) -> bool:
        """Whether the travel budget is gone (removed without an impact)."""
        return self.travelled >= self.max_travel - 1e-9

    def step(self) -> "Tuple[Vec2, Vec2]":
        """Move one fixed timestep; return ``(from, to)`` for the swept hit test."""
        start = self.position
        end = (start[0] + self.velocity[0], start[1] + self.velocity[1])
        self.position = end
        self.travelled += math.hypot(self.velocity[0], self.velocity[1])
        return start, end

    def fired_by(self, body: object) -> bool:
        """Whether ``body`` fired this projectile (identity, not equality)."""
        return self.owner is body

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"Projectile(faction={self.faction!r}, at={self.position[0]:.0f},"
            f"{self.position[1]:.0f}, range_left={self.range_left:.0f})"
        )


@dataclass(frozen=True)
class Combatant:
    """One body a projectile could hit this frame.

    The player and an NPC hull are different types with different concerns, but
    the collision question is identical for both: where are you, how big is your
    hitbox, which side are you on, and are you currently unhittable. Freezing that
    into a value object each frame is what stops the damage code from growing an
    ``if player:`` branch (and from accidentally mutating a ship while "just
    asking" about it).
    """

    body: object
    faction: str
    position: Vec2
    hitbox_radius: float
    immune: bool = False

    def __post_init__(self) -> None:
        require_combatant(self.faction)

    @classmethod
    def from_ship(cls, ship) -> "Combatant":
        """An NPC hull: its faction is its side, and nothing makes an NPC immune."""
        return cls(
            body=ship,
            faction=ship.faction,
            position=ship.position,
            hitbox_radius=ship.hitbox_radius,
        )

    @classmethod
    def from_player(cls, game_state) -> "Combatant":
        """The player's hull, immune while landed and for the launch grace period.

        The immunity flag is copied from the live game state rather than queried
        later: the frame's opening snapshot is what the whole frame resolves
        against, and a flag that could flip between the hit test and the damage
        would let one projectile be half-absorbed.
        """
        return cls(
            body=game_state,
            faction=FACTION_PLAYER,
            position=game_state.position,
            hitbox_radius=game_state.hitbox_radius,
            immune=game_state.immune_to_damage,
        )


@dataclass(frozen=True)
class Impact:
    """One projectile landing on one body.

    Emitted to the scene, which is where the particles, the sound cue, and the
    bounty copy belong. ``position`` is the point on the travel segment where the
    projectile first entered the hitbox — the muzzle-relative truth of the hit,
    which is also where a burst should start.
    """

    position: Vec2
    faction: str
    target: object
    target_faction: str
    damage: float
    destroyed: bool

    @property
    def fired_by_player(self) -> bool:
        return self.faction == FACTION_PLAYER

    @property
    def hit_player(self) -> bool:
        return self.target_faction == FACTION_PLAYER


@dataclass(frozen=True)
class Bounty:
    """What one kill pays, and the line the tactical display shows with it."""

    credits: float
    message: str


def _thousands(credits: float) -> str:
    """Render credits the way the spec's bounty copy does: 10000 -> ``10K``.

    Under a thousand there is no "K" to say: "0.5K bounty paid" is bank-speak, and a
    bounty poster writes 500. Fractional thousands keep one decimal because the
    shipped configs price a kill at 1500, and "1K" or "2K" would both be a lie.
    """
    amount = float(credits)
    if amount < 1000.0:
        return f"{int(amount)}"
    thousands = amount / 1000.0
    if thousands.is_integer():
        return f"{int(thousands)}K"
    return f"{thousands:.1f}K"


def bounty_for_kill(
    victim_faction: str, rules: CombatRules, relations: PlayerRelations
) -> Optional[Bounty]:
    """What the player is paid for destroying one NPC hull.

    Call this only for a hull the player's own gun finished: the spec is explicit
    that a pirate killed by another ship's projectile pays nothing, and the
    "who fired" question is identity-based, so it is settled upstream (see
    :attr:`Impact.fired_by_player`) rather than guessed at here.

    Rules, in order:

    * **Pirate**: a flat ``combat.pirate_bounty`` from the game itself. Pirates
      have no rival to thank the player, so no relations check applies.
    * **Localhoster or Bobber**: paid by the victim's *enemy* war-side, and only
      while that payer is not hostile to the player. Shoot both war-sides and the
      cross-faction bounties vanish — the spec's "if the player has made enemies
      of both factions, then no reward is offered for destroying ships from either
      side". Note this is not the same as the victim being hostile: shooting a
      Bobber makes the Bobbers hostile, and the Localhosters still pay.
    * Anything else (including the player's own hull) pays nothing.

    A configured bounty of zero pays nothing at all, message included: printing
    "0K bounty paid!" for a config that decided kills are worthless is the kind of
    flourish nobody asked for.
    """
    if not is_npc_faction(victim_faction):
        return None

    credits = rules.bounty_for(victim_faction)
    if credits <= 0.0:
        return None

    if victim_faction == FACTION_PIRATE:
        return Bounty(
            credits=credits,
            message=f"{_thousands(credits)} bounty paid! Pirates destroyed.",
        )

    payer = war_side_of(victim_faction)
    if relations.is_hostile_to_player(payer):
        return None
    return Bounty(
        credits=credits,
        message=(
            f"{faction_label(payer)}s send their thanks! "
            f"{_thousands(credits)} bounty paid."
        ),
    )


# ---------------------------------------------------------------------------
# Collision geometry
# ---------------------------------------------------------------------------
def segment_entry_parameter(
    start: Vec2, end: Vec2, center: Vec2, radius: float
) -> Optional[float]:
    """Where a projectile's one-frame sweep first enters a circle, as ``t`` in [0, 1].

    A swept test rather than a point test, because the fixed timestep is generous
    to tunnelling: a projectile can cross 18px in a frame (the shipped
    ``projectile_speed_bonus`` plus the shooter's speed), which is comparable to a
    hull's hitbox radius. Sampling only the endpoint would let a fast shot pass
    clean through a hull between two frames — a miss that the player can *see*
    happen.

    Returns ``0.0`` when the segment starts inside the circle (a point-blank hit),
    and ``None`` when the segment misses entirely.
    """
    radius = float(radius)
    if radius < 0.0:
        return None

    dx, dy = end[0] - start[0], end[1] - start[1]
    fx, fy = start[0] - center[0], start[1] - center[1]
    if fx * fx + fy * fy <= radius * radius:
        return 0.0

    quadratic_a = dx * dx + dy * dy
    if quadratic_a < 1e-12:
        # A stationary projectile: the point test above already answered this.
        return None

    quadratic_b = 2.0 * (fx * dx + fy * dy)
    quadratic_c = fx * fx + fy * fy - radius * radius
    discriminant = quadratic_b * quadratic_b - 4.0 * quadratic_a * quadratic_c
    if discriminant < 0.0:
        return None

    entry = (-quadratic_b - math.sqrt(discriminant)) / (2.0 * quadratic_a)
    if 0.0 <= entry <= 1.0:
        return entry
    return None


def point_hits_circle(position: Vec2, center: Vec2, radius: float) -> bool:
    """Whether a point lies inside a circle (the t=0 case of the swept test).

    Exposed because it is the spec's literal wording of a hit — "any projectile
    that enters that circle counts as a hit" — and because a test that pins the
    boundary should not have to reason about quadratics to do it.
    """
    return segment_entry_parameter(position, position, center, radius) == 0.0


def _may_be_hit_by(projectile: Projectile, target: Combatant) -> bool:
    """The spec's pass-through rules, as one predicate.

    Three kinds of "no":
    * the ship that fired it (no friendly fire against yourself),
    * any body on the same side (an NPC shot passes through its own faction —
      which is also why two pirates never duelling each other is consistent with
      the AI refusing to target them),
    * an immune body (landed, launch grace, or a wreck already off the list).

    The player is not a faction, so an NPC projectile is never "same side" with
    them: a Localhoster's stray shot at a Bobber can clip the player without that
    counting as an act of war (see DECISIONS.md, Stage 11).
    """
    if target.immune:
        return False
    if projectile.fired_by(target.body):
        return False
    return projectile.faction != target.faction


# ---------------------------------------------------------------------------
# The fight
# ---------------------------------------------------------------------------
class Gunfight:
    """Every projectile in flight during one system visit.

    The scene hands it the shots its ships produced (:meth:`launch`) and the
    bodies that are standing around (:meth:`advance_frame`), and gets back the
    impacts to report. It does not know what an NPC is, what the AI wants, or
    what a particle looks like.
    """

    def __init__(self, rules: CombatRules) -> None:
        self.rules = rules
        self._projectiles: List[Projectile] = []

    # ------------------------------------------------------------------
    # Inventory
    # ------------------------------------------------------------------
    @property
    def projectiles(self) -> "Tuple[Projectile, ...]":
        """The shots currently in flight, in launch order (a copy)."""
        return tuple(self._projectiles)

    @property
    def in_flight(self) -> bool:
        return bool(self._projectiles)

    def __len__(self) -> int:
        return len(self._projectiles)

    def launch(self, shot: Shot) -> Projectile:
        """Turn one ship's decision to fire into a travelling projectile."""
        projectile = Projectile.from_shot(shot, self.rules)
        self._projectiles.append(projectile)
        return projectile

    def launch_all(self, shots: Sequence[Shot]) -> None:
        """Launch a frame's worth of shots (the fleet's, then the player's)."""
        for shot in shots:
            self.launch(shot)

    def clear(self) -> None:
        """Forget every projectile in flight: this visit to this system is over.

        Not housekeeping — a rule. Leaving the system destroys the ships that
        fired these shots, and a projectile that survives the gate would arrive in
        a system it was never fired in, still carrying its shooter's identity (so
        it could still "be the player's shot" for bounty purposes). The scene calls
        this on the same boundary that drops the fleet.
        """
        self._projectiles.clear()

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------
    def advance_frame(self, targets: Sequence[Combatant]) -> "List[Impact]":
        """Move every projectile one fixed timestep; return what it hit.

        One pass per projectile, and each projectile can hit at most one body:
        the shot is spent on the first hull it enters, so a single round cannot
        perforate a formation. When two hulls are close enough that one sweep
        crosses both, the one entered *first along the path* takes the hit, which
        makes the outcome a property of the geometry rather than of the order the
        target list happened to be built in.

        A projectile that both expires and lands on this frame counts as a hit:
        the round reached the hull at (or before) the moment its range ran out,
        and resolving the hit first is what makes a weapon's stated range the
        honest number rather than one pixel short of it.
        """
        impacts: List[Impact] = []
        survivors: List[Projectile] = []

        for projectile in self._projectiles:
            start, end = projectile.step()
            hit = self._first_hit(projectile, start, end, targets)
            if hit is not None:
                impacts.append(hit)
                continue
            if projectile.spent:
                continue
            survivors.append(projectile)

        self._projectiles = survivors
        return impacts

    def _first_hit(
        self,
        projectile: Projectile,
        start: Vec2,
        end: Vec2,
        targets: Sequence[Combatant],
    ) -> Optional[Impact]:
        """Resolve this frame's sweep against every body it could hit."""
        best_target: Optional[Combatant] = None
        best_entry: Optional[float] = None

        for target in targets:
            if not _may_be_hit_by(projectile, target):
                continue
            entry = segment_entry_parameter(
                start, end, target.position, target.hitbox_radius
            )
            if entry is None:
                continue
            if best_entry is None or entry < best_entry:
                best_target, best_entry = target, entry

        if best_target is None or best_entry is None:
            return None

        hit_point = (
            start[0] + (end[0] - start[0]) * best_entry,
            start[1] + (end[1] - start[1]) * best_entry,
        )
        damage = projectile.weapon_power
        best_target.body.apply_damage(damage)

        return Impact(
            position=hit_point,
            faction=projectile.faction,
            target=best_target.body,
            target_faction=best_target.faction,
            damage=damage,
            # ``destroyed`` is part of the shared hull vocabulary: both the
            # player's GameState and an NpcShip answer it, and both mean armour
            # at or below zero. Duck-typing it (rather than an isinstance check)
            # is what lets a future hull type join a fight without editing combat.
            destroyed=bool(getattr(best_target.body, "destroyed", False)),
        )

    # ------------------------------------------------------------------
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Gunfight(projectiles={len(self._projectiles)})"
