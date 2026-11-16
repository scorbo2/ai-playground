"""Who is in the system the player just flew into, and what they do (Stage 10).

An :class:`Encounter` is the fleet present during **one visit to one system**.
It owns the ships, rolls their orders every fixed timestep, and hands back the
shots they fired. Its lifetime is exactly the visit: it is dealt when the player
enters a system (a new game, or the arrival half of a jump) and thrown away when
the player jumps out — which is the spec's rule that ships neither respawn nor
persist ("leaving the system via a jump, and then returning ... does not
remember the quantity or types of ships that were there").

Four rules worth naming, because each one is a gate item:

* **Spawn chance scales with alphabetic distance from Alpha**, not with map
  distance: the spec explicitly uses the system's name index, so Zulu is always
  the busiest system and Bravo the quietest, whatever the node layout looks like.
  Alpha is always 0% — the starting system is safe.
* **NPC stats hang off the player's *starting* stats** (see
  :func:`src.model.npc_ship.roll_npc_stats`), so upgrading never quietly
  rescales the galaxy.
* **Random RNG streams are derived, not cursored** (see :func:`encounter_rng`):
  the fleet in a system does not depend on how many frames the player burned
  before arriving, which is the same reasoning that made the Stage 9 job market
  a derived stream.
* **Everyone picks their nearest engageable target from the frame's opening
  snapshot.** Deciding and then moving (rather than deciding one ship at a time)
  means a ship's target choice never depends on whether its neighbour happened
  to be simulated earlier in the list.
"""

from __future__ import annotations

import random as _random_lib
from dataclasses import dataclass
from typing import Optional, Sequence, Tuple

from src.model.ai import AiTuning, Target, plan_order
from src.model.factions import FACTIONS, PlayerRelations, factions_can_engage
from src.model.npc_ship import NpcShip, roll_npc_stats
from src.model.physics import Vec2, distance_between, random_point_in_square
from src.model.stats import ShipStats
from src.model.weapons import Shot

# How many times a spawn point is re-rolled to keep it clear of the player. A
# small system (or an absurd `min_distance_from_player`) can make the criterion
# impossible to satisfy; after this many attempts the point is taken as-is
# rather than looping, and the spawn simply happens to be close.
_SPAWN_REJECTION_LIMIT = 24


@dataclass(frozen=True)
class SpawnRules:
    """Every NPC tunable, hoisted out of the ``npc`` config section once per game.

    Same reasoning as :class:`~src.model.economy.EconomyRules`: the model asks for
    ``rules.ships_max`` instead of reaching into a config dict, and Stage 14's
    config sweep has exactly one place to poke to prove nothing is hard-coded.
    """

    spawn_chance_near: float
    spawn_chance_far: float
    ships_min: int
    ships_max: int
    stat_multiple: float
    stat_variance: float
    aim_jitter_degrees: float
    engage_range_fraction: float
    min_distance_from_player: float

    def __post_init__(self) -> None:
        """A SpawnRules object that exists is a SpawnRules object that works.

        Validation lives here rather than only in :meth:`from_config` so a test,
        a tool, or a future save-file loader cannot build a rules object with a
        reversed ship band and discover the crash mid-dogfight.
        """
        self.check()

    @classmethod
    def from_config(cls, npc_config: dict) -> "SpawnRules":
        """Build from the validated ``npc`` config section."""
        try:
            rules = cls(
                spawn_chance_near=float(npc_config["spawn_chance_near"]),
                spawn_chance_far=float(npc_config["spawn_chance_far"]),
                ships_min=int(npc_config["ships_min"]),
                ships_max=int(npc_config["ships_max"]),
                stat_multiple=float(npc_config["stat_multiple"]),
                stat_variance=float(npc_config["stat_variance"]),
                aim_jitter_degrees=float(npc_config["aim_jitter_degrees"]),
                engage_range_fraction=float(npc_config["engage_range_fraction"]),
                min_distance_from_player=float(npc_config["min_distance_from_player"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"invalid npc config section: {exc}") from exc
        return rules

    def check(self) -> None:
        """Reject ranges no spawner could honour, before the window opens.

        The loader validates the same shape for the shipped files; this exists
        because tests and tooling build rules directly, and a reversed chance or
        ship band would otherwise surface as a ``random.uniform``/``randint``
        crash in the middle of a dogfight.
        """
        for name, chance in (
            ("spawn_chance_near", self.spawn_chance_near),
            ("spawn_chance_far", self.spawn_chance_far),
        ):
            if not 0.0 <= chance <= 1.0:
                raise ValueError(f"npc.{name} must be a probability in [0, 1], got {chance}")
        if self.spawn_chance_near > self.spawn_chance_far:
            raise ValueError(
                "npc.spawn_chance_near must not exceed npc.spawn_chance_far: the "
                f"chance rises with distance from Alpha, got {self.spawn_chance_near} "
                f"-> {self.spawn_chance_far}"
            )
        if not 1 <= self.ships_min <= self.ships_max:
            raise ValueError(
                "npc.ships_min must be >= 1 and <= npc.ships_max, got "
                f"{self.ships_min}..{self.ships_max}"
            )
        if self.stat_multiple <= 0.0:
            raise ValueError("npc.stat_multiple must be greater than 0")
        if not 0.0 <= self.stat_variance < 1.0:
            raise ValueError(
                "npc.stat_variance must be in [0, 1): a variance of 1 or more can "
                f"roll an NPC stat down to zero, got {self.stat_variance}"
            )
        if self.aim_jitter_degrees < 0.0:
            raise ValueError("npc.aim_jitter_degrees cannot be negative")
        if not 0.0 < self.engage_range_fraction <= 1.0:
            raise ValueError("npc.engage_range_fraction must be in (0, 1]")
        if self.min_distance_from_player < 0.0:
            raise ValueError("npc.min_distance_from_player cannot be negative")

    @property
    def ai_tuning(self) -> AiTuning:
        """The AI half of these rules, as the controller wants it."""
        return AiTuning(
            engage_range_fraction=self.engage_range_fraction,
            aim_jitter_degrees=self.aim_jitter_degrees,
        )


def encounter_rng(run_seed: object, system: str, visit_serial: int) -> "_random_lib.Random":
    """A fresh RNG stream for one system visit's fleet.

    Mirrors :func:`src.model.economy.port_rng` and for the same reasons: the
    pirates in Bravo must not depend on how many frames of thrust the player
    logged first, and two visits to the same system must not spawn the same
    fleet. The ``:npc`` suffix is not decoration — without it the encounter would
    be built from the *same* seed string as that system's job market and the two
    would consume identical draws, which is a coupling nobody asked for and
    someone would inevitably "fix".
    """
    return _random_lib.Random(f"{run_seed}:{system}:{visit_serial}:npc")


def system_index(system: str, system_names: Sequence[str]) -> int:
    """Position of ``system`` in the roster, which *is* its distance from Alpha.

    The spec decides NPC spawn chance from the alphabetic index (Alpha 0%, Bravo
    lowest non-zero, Zulu highest), precisely so the layout of the node map
    cannot make a far-flung-but-early-named system dangerous.
    """
    try:
        return list(system_names).index(system)
    except ValueError as exc:
        raise ValueError(f"unknown system {system!r}") from exc


def spawn_chance_for_system(system: str, system_names: Sequence[str], rules: SpawnRules) -> float:
    """Probability that a visit to ``system`` spawns any ships at all.

    ``0.0`` for the first system in the roster (Alpha, where the player always
    starts and which the spec keeps safe), then a straight ramp that starts at
    ``spawn_chance_near`` on the first system after Alpha and reaches
    ``spawn_chance_far`` on the last one. The ramp spans the systems *in play*,
    so shrinking ``map.system_count`` moves the top of the ramp to the new last
    system rather than stranding the configured maximum beyond the end of the
    roster (where no system could ever draw it).

    Edge case worth naming: with only Alpha and one other system there is no
    room to climb, so that system gets ``spawn_chance_near``. A designer who
    wants Alpha to be a dead end and everything else lethal should set
    ``spawn_chance_near == spawn_chance_far``.
    """
    index = system_index(system, system_names)
    if index == 0:
        return 0.0
    last_index = len(system_names) - 1
    if last_index <= 0:
        return 0.0
    step = (index - 1) / max(last_index - 1, 1)
    return rules.spawn_chance_near + (rules.spawn_chance_far - rules.spawn_chance_near) * step


def choose_ship_count(rng: "_random_lib.Random", rules: SpawnRules) -> int:
    """How many ships a successful spawn roll produces (``ships_min..ships_max``)."""
    return rng.randint(rules.ships_min, rules.ships_max)


def nearest_living_ship(ships: Sequence["NpcShip"], position: Vec2) -> Optional["NpcShip"]:
    """The closest not-yet-destroyed ship to a point, or ``None``.

    One implementation because two consumers ask the same question with the same
    answer: the HUD's nearest-ship readout and Stage 11's scan. Ties break to the
    earlier ship in ``ships`` (spawn order), which keeps the answer deterministic
    for a ship that spawned exactly between two others rather than leaving it to
    dictionary or set ordering.
    """
    best: Optional[NpcShip] = None
    best_distance = float("inf")
    for ship in ships:
        if ship.destroyed:
            continue
        distance = distance_between(position, ship.position)
        if distance < best_distance:
            best = ship
            best_distance = distance
    return best


def spawn_position(
    rng: "_random_lib.Random",
    system_pixel_size: float,
    player_position: Vec2,
    min_distance: float,
    rejection_limit: int = _SPAWN_REJECTION_LIMIT,
) -> Vec2:
    """A random point inside the system square, kept clear of the player.

    The spec asks only for "random starting positions within the system", but a
    uniform draw can land a pirate on top of the player's arrival point, and the
    player's first sight of a new system would be an unavoidable point-blank
    volley. So points that fall closer than ``min_distance_from_player`` are
    re-rolled — which leaves the distribution non-uniform only inside that small
    circle around the player, and stops re-rolling entirely after
    ``rejection_limit`` tries so a tiny system cannot stall the game.
    """
    half = system_pixel_size / 2.0
    for attempt in range(rejection_limit):
        point = random_point_in_square(rng, half)
        if min_distance <= 0.0 or distance_between(point, player_position) >= min_distance:
            return point
    return random_point_in_square(rng, half)  # impossible constraint: accept, don't loop


def roll_encounter(
    *,
    system: str,
    system_names: Sequence[str],
    rules: SpawnRules,
    starting_stats: ShipStats,
    system_pixel_size: float,
    player_position: Vec2,
    rng: "_random_lib.Random",
    relations: Optional[PlayerRelations] = None,
) -> "Encounter":
    """Roll one system visit: the spawn chance, the count, then each hull.

    The roll is one coin flip, not ``count`` independent flips: a system either
    has traffic or it does not. Rolling per ship would make the *average* fleet
    size obey the configured chance but make "70% spawn" mean a mixture of empty
    systems and crowded ones, which is not what the spec's single "small chance
    to spawn a random number of between 1 and 4 ships" describes.
    """
    chance = spawn_chance_for_system(system, system_names, rules)
    if chance <= 0.0 or rng.random() >= chance:
        return Encounter.empty(
            system=system,
            rules=rules,
            system_pixel_size=system_pixel_size,
            relations=relations,
            rng=rng,
        )

    half = system_pixel_size / 2.0
    ships = []
    for _ in range(choose_ship_count(rng, rules)):
        faction = rng.choice(list(FACTIONS))
        ships.append(
            NpcShip(
                faction=faction,
                stats=roll_npc_stats(
                    starting_stats, rules.stat_multiple, rules.stat_variance, rng
                ),
                position=spawn_position(
                    rng, system_pixel_size, player_position, rules.min_distance_from_player
                ),
                heading_degrees=rng.uniform(0.0, 360.0),
                # Spec: a starting velocity of 0 and a random initial facing.
                velocity=(0.0, 0.0),
            )
        )
    return Encounter(
        system=system,
        ships=ships,
        rules=rules,
        system_pixel_size=system_pixel_size,
        relations=relations,
        rng=rng,
    )


class Encounter:
    """The ships inhabiting one system visit, simulated one frame at a time."""

    def __init__(
        self,
        system: str,
        ships: Sequence[NpcShip],
        rules: SpawnRules,
        system_pixel_size: float,
        relations: Optional[PlayerRelations] = None,
        rng: Optional["_random_lib.Random"] = None,
    ) -> None:
        self.system = system
        self._ships: Tuple[NpcShip, ...] = tuple(ships)
        self.rules = rules
        self.system_pixel_size = float(system_pixel_size)
        # Grudges outlive encounters: the session's PlayerRelations is shared
        # with every system the player ever visits, so a Localhoster shot at in
        # Alpha shoots back in Zulu. Constructing one here (only reached by
        # standalone tests and tooling) would make the grudge forget itself at
        # every jump.
        self.relations = relations if relations is not None else PlayerRelations()
        self.rng = rng or _random_lib.Random()
        self._tuning = rules.ai_tuning

    # ------------------------------------------------------------------
    @classmethod
    def empty(
        cls,
        system: str,
        rules: SpawnRules,
        system_pixel_size: float,
        relations: Optional[PlayerRelations] = None,
        rng: Optional["_random_lib.Random"] = None,
    ) -> "Encounter":
        """A system with no traffic at all (Alpha always, every failed roll otherwise)."""
        return cls(
            system=system,
            ships=(),
            rules=rules,
            system_pixel_size=system_pixel_size,
            relations=relations,
            rng=rng,
        )

    @property
    def ships(self) -> Tuple[NpcShip, ...]:
        """The fleet, in spawn order (a copy: nobody gets to add their own ship)."""
        return self._ships

    @property
    def is_empty(self) -> bool:
        return not self._ships

    @property
    def system_half_extent(self) -> float:
        """Half the system's side length: the boundary every ship is pinned inside."""
        return self.system_pixel_size / 2.0

    def __len__(self) -> int:
        return len(self._ships)

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------
    def advance_frame(self, player_position: Vec2) -> "list[Shot]":
        """Run one fixed timestep for the whole fleet; return the shots fired.

        Two passes on purpose: every target choice is made against the positions
        the frame *started* on, and only then is anyone moved. Interleaving the
        two would let a ship's decision depend on the simulation order of the
        list, so the fleet would behave differently purely because of spawn
        order — the sort of bug that survives every test that only has one ship
        in it.
        """
        plans = [
            plan_order(ship, self.pick_target(ship, player_position), self._tuning, self.rng)
            for ship in self._ships
        ]
        shots: list[Shot] = []
        for plan in plans:
            shot = plan.ship.advance_frame(plan.order, self.system_half_extent)
            if shot is not None:
                shots.append(shot)
        return shots

    def pick_target(self, ship: NpcShip, player_position: Vec2) -> Optional[Target]:
        """The nearest ship ``ship`` can actually engage, or ``None``.

        "Nearest hostile" is narrowed to "nearest *engageable*": same-faction
        ships are excluded, because friendly fire is impossible and a pirate who
        spent the fight trading harmless shots with the pirate next to him would
        never once chase the freighter he could hurt (see
        :func:`src.model.factions.factions_can_engage`).

        The player is a candidate only when the session's relations say this
        faction is hostile to them — neutral until someone fires first, always
        for pirates.
        """
        best: Optional[Target] = None
        best_distance = float("inf")

        if self.relations.is_hostile_to_player(ship.faction):
            best = Target(position=player_position, ship=None)
            best_distance = ship.distance_to(player_position)

        for other in self._ships:
            if other is ship or other.destroyed:
                continue
            if not factions_can_engage(ship.faction, other.faction):
                continue
            distance = ship.distance_to(other.position)
            if distance < best_distance:
                best = Target(position=other.position, ship=other)
                best_distance = distance

        return best

    # ------------------------------------------------------------------
    # Read-only queries the HUD and (later) the scan need
    # ------------------------------------------------------------------
    def nearest_ship_to(self, position: Vec2) -> Optional[NpcShip]:
        """Closest living ship to a point, for the HUD's "nearest ship" readout.

        Deliberately *not* filtered by hostility: the spec's readout names the
        nearest ship in the system, and the alignment it prints (cyan/yellow/red)
        is the player's way of finding out whether that is a good thing.
        """
        return nearest_living_ship(self._ships, position)

    def prune_destroyed(self) -> "list[NpcShip]":
        """Throw the wrecks overboard; return the hulls removed this frame.

        A destroyed hull is not an object the game keeps arguing with: it is out of
        the system for the rest of the visit (ships "do not respawn" and there is no
        salvage). Removing it rather than flagging it is what makes every other
        question about the fleet answer itself — the AI stops targeting it, the
        minimap stops painting it, the scan stops reporting it, and a stray projectile
        cannot hit a corpse for a second bounty.

        The scan keeps its lock across a prune: :class:`~src.model.scan.ShipScanner`
        holds the object itself, which is exactly how "reverts to No target when the
        displayed ship is destroyed" can be detected at all.
        """
        if not any(ship.destroyed for ship in self._ships):
            return []
        gone = [ship for ship in self._ships if ship.destroyed]
        self._ships = tuple(ship for ship in self._ships if not ship.destroyed)
        return gone

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Encounter(system={self.system!r}, ships={len(self._ships)})"
