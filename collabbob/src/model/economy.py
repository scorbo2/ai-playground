"""Spaceport economy: mission generation, the fare law, and port-offer rules.

A port visit offers a small list of hauling jobs, each bound for some other
system (never the one the player is standing in — that would be a job with
no legs). The fare follows one formula so the economy is legible to the
player:

    fare = size * rolled rate * distance multiplier

where ``size`` is the mission's cargo unit count and passenger count, the
rate is rolled **once per port visit** inside the config's per-unit range, and
the *distance multiplier* grows with the minimum jump count to the destination
— the "far bonus". Because the multiplier is non-decreasing in distance and
the rates are fixed for the whole visit, the fare is monotonic non-decreasing
in every size component *within a visit*: bigger hauls pay more, longer trips
pay more, and two offers on the same screen are comparable. Rolling the rate
per mission instead was the first draft, and it produced screens where a
7-unit haul to Tango paid *less* than a 4-unit haul to the same port.

Offer sizes are capped by the ship's own capacity, so no offer on the board is
permanently unacceptable: on Hard (15 cargo, 4 passengers) a job for 5
passengers would otherwise sit on the screen forever, an unclickable tease
until the player bought passenger space.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence

from src.map_systems.graph import SystemGraph
from src.model.ship_upgrades import UpgradeOffer, generate_upgrade_offers
from src.model.stats import ShipStats

__all__ = [
    "EconomyRules",
    "CarriedLoad",
    "LandingReport",
    "Mission",
    "OFFER_CARGO_CEILING",
    "OFFER_PASSENGER_CEILING",
    "PortTransaction",
    "PortVisit",
    "distance_multiplier",
    "format_credits",
    "generate_port_offers",
    "mission_fare",
    "mission_payload_text",
    "mission_route_text",
]

# Hard ceilings on how big a single offer may be, independent of the ship.
# Together with the per-visit capacity cap below they keep the board readable:
# an offer bigger than the hull is dead weight on screen, and an offer of 900
# cargo units is not a choice, it is a rounding error.
OFFER_CARGO_CEILING = 15
OFFER_PASSENGER_CEILING = 5


@dataclass(frozen=True)
class EconomyRules:
    """Every money tunable, hoisted out of ``economy`` once per game.

    Hoisting keeps raw config dicts out of the model: the port code asks
    ``rules.missions_max`` instead of reaching into a dict three keys deep,
    and the Stage 14 config sweep has exactly one place to poke.
    """

    win_credits: float
    fuel_price_per_unit: float
    repair_price_per_point: float
    upgrade_base_cost: float
    upgrade_cost_multiplier: float
    upgrade_max_level: int
    upgrade_offers_min: int
    upgrade_offers_max: int
    missions_min: int
    missions_max: int
    cargo_fare_min: float
    cargo_fare_max: float
    passenger_fare_min: float
    passenger_fare_max: float
    far_destination_bonus: float
    cargo_types: tuple[str, ...]

    @classmethod
    def from_config(cls, economy: dict) -> "EconomyRules":
        """Build from the ``economy`` config section.

        The loader validates these shapes at startup; the checks here exist
        because ``GameState`` is also built directly by tests and tooling that
        never went through the loader, and a reversed fare range would produce
        a baffling ``ValueError`` from deep inside ``random.uniform``.
        """
        cargo_range = _fare_range(economy["cargo_fare_per_unit"], "cargo_fare_per_unit")
        passenger_range = _fare_range(
            economy["passenger_fare_each"], "passenger_fare_each"
        )
        cargo_types = tuple(economy["cargo_types"])
        # ``new_game.starting_credits`` is deliberately absent here: this class
        # reads the ``economy`` section only, and a default for a key that lives
        # in another section is how a balance change silently stops mattering.
        rules = cls(
            win_credits=float(economy["win_credits"]),
            fuel_price_per_unit=float(economy["fuel_cost_per_unit"]),
            repair_price_per_point=float(economy["repair_cost_per_point"]),
            upgrade_base_cost=float(economy["upgrade_base_cost"]),
            upgrade_cost_multiplier=float(economy["upgrade_cost_multiplier"]),
            upgrade_max_level=int(economy["upgrade_max_level"]),
            upgrade_offers_min=int(economy["upgrade_offers_min"]),
            upgrade_offers_max=int(economy["upgrade_offers_max"]),
            missions_min=int(economy["missions_min"]),
            missions_max=int(economy["missions_max"]),
            cargo_fare_min=cargo_range[0],
            cargo_fare_max=cargo_range[1],
            passenger_fare_min=passenger_range[0],
            passenger_fare_max=passenger_range[1],
            far_destination_bonus=float(economy["far_destination_bonus"]),
            cargo_types=cargo_types,
        )
        rules._check_usable()
        return rules

    def _check_usable(self) -> None:
        """Reject nonsense that would crash generation rather than report it."""
        if self.missions_min < 0 or self.missions_min > self.missions_max:
            raise ValueError(
                "economy.missions_min must be >= 0 and <= economy.missions_max, "
                f"got {self.missions_min}..{self.missions_max}"
            )
        if self.upgrade_offers_min > self.upgrade_offers_max:
            raise ValueError(
                "economy.upgrade_offers_min must be <= economy.upgrade_offers_max, "
                f"got {self.upgrade_offers_min}..{self.upgrade_offers_max}"
            )
        if self.upgrade_max_level < 1:
            raise ValueError("economy.upgrade_max_level must be at least 1")
        if self.upgrade_cost_multiplier < 1.0:
            raise ValueError(
                "economy.upgrade_cost_multiplier must be >= 1.0: further upgrades "
                "may not get cheaper (the spec's cost curve escalates)"
            )
        if not self.cargo_types:
            raise ValueError("economy.cargo_types must name at least one cargo")
        for name, low, high in (
            ("cargo_fare_per_unit", self.cargo_fare_min, self.cargo_fare_max),
            ("passenger_fare_each", self.passenger_fare_min, self.passenger_fare_max),
        ):
            if low < 0 or low > high:
                raise ValueError(
                    f"economy.{name} must be a non-negative [min, max] range, "
                    f"got [{low}, {high}]"
                )
        if self.far_destination_bonus < 0:
            raise ValueError("economy.far_destination_bonus cannot be negative")
        if self.fuel_price_per_unit < 0 or self.repair_price_per_point < 0:
            raise ValueError(
                "economy.fuel_cost_per_unit and economy.repair_cost_per_point "
                "cannot be negative"
            )

    def roll_cargo_rate(self, rng: random.Random) -> float:
        """The port's cargo rate: rolled once per visit, applied to every offer."""
        return rng.uniform(self.cargo_fare_min, self.cargo_fare_max)

    def roll_passenger_rate(self, rng: random.Random) -> float:
        """The port's passenger rate: rolled once per visit, applied to every offer."""
        return rng.uniform(self.passenger_fare_min, self.passenger_fare_max)

    def roll_mission_count(self, rng: random.Random) -> int:
        """How many jobs this port is offering."""
        return rng.randint(self.missions_min, self.missions_max)


def _fare_range(pair: Sequence[float], key: str) -> tuple[float, float]:
    """Read a ``[min, max]`` fare pair, reporting a malformed one by key name."""
    if len(pair) != 2:
        raise ValueError(f"economy.{key} must be [min, max], got {pair!r}")
    return float(pair[0]), float(pair[1])


@dataclass(frozen=True)
class Mission:
    """One offer on the table.

    Exactly one of ``cargo_type/cargo_units`` and ``passengers`` is non-zero for
    a single-kind job; mixed jobs set both. The destination is never the current
    system, and is always present in the world graph even when unrevealed (the
    spec allows cargo for a system the player has not found yet).

    ``offer_id`` carries the port visit's serial, so an offer from a stale
    visit can never be accepted twice — not even if the player re-enters the
    same system and a fresh visit happens to number its offers the same way.
    """

    offer_id: tuple[int, int]
    cargo_type: str | None
    cargo_units: int
    passengers: int
    destination: str
    distance: int  # minimum jump count from the offering system
    far_bonus: float  # the distance multiplier already baked into ``fare``
    fare: int


@dataclass(frozen=True)
class PortVisit:
    """Everything on offer at one port, rolled once when the player lands.

    Frozen and inert: it is a snapshot of what the port is selling, so the
    spaceport screen cannot re-roll its own stock by being redrawn. Whether an
    offer is still available is the game state's business (see
    :meth:`~src.model.game_state.GameState.accept_mission`).
    """

    system: str
    serial: int
    missions: tuple[Mission, ...]
    upgrade_offers: tuple[UpgradeOffer, ...]


@dataclass(frozen=True)
class CarriedLoad:
    """A mission payload currently aboard the ship.

    A load is never split: it is accepted in full and unloaded in full when the
    ship lands at its destination. It carries its own fare, which is credited
    exactly once, on landing there.
    """

    destination: str
    fare: int
    cargo_type: str | None
    cargo_units: int
    passengers: int


@dataclass(frozen=True)
class PortTransaction:
    """Outcome of one thing the player can do at a port.

    Accepting a job, filling the tank, patching the hull, and buying an upgrade
    are all the same shape of question — "may I, and why not?" — so they return
    one type. Two near-identical result types (`LoadResult.accepted` vs
    `PurchaseResult.completed`) is how a caller ends up testing an attribute that
    happens to exist on one of them, which is exactly the crash this replaced.

    ``reason`` is copy for the spaceport message line in both directions: the
    player is told what happened, not merely that it happened.
    """

    succeeded: bool
    reason: str = ""
    credits_spent: float = 0.0

    def __bool__(self) -> bool:
        return self.succeeded


@dataclass(frozen=True)
class LandingReport:
    """What a spaceport settled: the loads just unloaded and the credits paid."""

    system: str
    credits_gained: int
    cargo_unloaded: int
    passengers_unloaded: int
    unloaded: tuple[CarriedLoad, ...] = ()

    @property
    def delivered_anything(self) -> bool:
        """False for the common case: an empty hold, or nothing bound for here."""
        return bool(self.unloaded)




def port_rng(run_seed: object, system: str, visit_serial: int) -> "random.Random":
    """A fresh RNG for one system's market board, derived rather than cursored.

    Three streams feed a run: the world graph, the gameplay simulation, and (now)
    each system's job market. Deriving the market stream from
    ``(run_seed, system, visit_serial)`` instead of drawing from the gameplay
    generator buys the two properties the port needs: a board cannot shift because
    the player burned fuel for ten thousand frames first, and two entries into the
    same system get different boards because their serials differ. Same seed, same
    visit order, same markets - which is what Stage 14's determinism sweep wants.

    ``run_seed`` is whatever identifies the run (``rng.seed`` when configured, a
    random per-run nonce otherwise); it only has to be stable within the run.
    """
    return random.Random(f"{run_seed}:{system}:{visit_serial}")


def distance_multiplier(distance: int, far_destination_bonus: float) -> float:
    """The 'far bonus' as a fare multiplier.

    A one-jump trip pays 1.0x (nothing extra for the shortest hop); each
    additional jump beyond the first adds ``far_destination_bonus``. So a
    three-jump trip at bonus 1.5 multiplies the base fare by 4.0.
    """
    extra_hops = max(0, int(distance) - 1)
    return 1.0 + extra_hops * far_destination_bonus


def mission_fare(
    cargo_units: int,
    cargo_rate: float,
    passengers: int,
    passenger_rate: float,
    multiplier: float,
) -> int:
    """The fare law: ``size * rolled rate * distance multiplier``, per spec.

    Rounded **up**, so a fare never comes in under its raw expectation and the
    function stays monotonic non-decreasing in every size component even at
    small values.
    """
    base = cargo_units * float(cargo_rate) + passengers * float(passenger_rate)
    return int(math.ceil(base * float(multiplier)))


def generate_port_offers(
    rules: EconomyRules,
    graph: SystemGraph,
    current_system: str,
    stats: ShipStats,
    upgrade_levels: "dict[str, int]",
    rng: random.Random,
    visit_serial: int,
) -> PortVisit:
    """Roll one port visit: its transport contracts and its ship upgrades.

    * Kind: cargo-only, passenger-only, or mixed, equally likely.
    * Destination: a uniformly random system that is *not* the current one —
      possibly one the player has not discovered yet, per the spec. Several
      jobs may share a destination; two freighters bound for the same port is
      not a bug, it is a busy port.
    * Size: capped by the ship's own capacity (see the module docstring).
    * Fare: the single fare law, with one rate pair rolled for the whole visit.
    * Upgrades: distinct stats, each one level above the ship's current level,
      none past ``economy.upgrade_max_level``.

    ``visit_serial`` must come from the same session counter that
    :meth:`~src.model.game_state.GameState.begin_port_visit` uses; the two
    together are what make ``offer_id`` unrepeatable.
    """
    if current_system not in graph.names:
        raise ValueError(f"unknown system {current_system!r} in port generation")

    destinations = [name for name in graph.names if name != current_system]
    missions = tuple(
        _roll_missions(rules, graph, current_system, destinations, stats, rng, visit_serial)
    )
    return PortVisit(
        system=current_system,
        serial=visit_serial,
        missions=missions,
        upgrade_offers=tuple(generate_upgrade_offers(rules, stats, upgrade_levels, rng)),
    )


def _roll_missions(
    rules: EconomyRules,
    graph: SystemGraph,
    current_system: str,
    destinations: Sequence[str],
    stats: ShipStats,
    rng: random.Random,
    visit_serial: int,
) -> list[Mission]:
    """The contracts on this port's board."""
    if not destinations:
        # A one-system world (reachable only via a custom `map.system_count`):
        # there is nowhere to haul, so the board is empty rather than nonsense.
        return []

    cargo_rate = rules.roll_cargo_rate(rng)
    passenger_rate = rules.roll_passenger_rate(rng)
    cargo_ceiling = max(1, min(OFFER_CARGO_CEILING, stats.cargo_room))
    passenger_ceiling = max(1, min(OFFER_PASSENGER_CEILING, stats.passenger_space))

    missions: list[Mission] = []
    for index in range(rules.roll_mission_count(rng)):
        kind = rng.choice(("cargo", "passenger", "mixed"))
        destination = rng.choice(destinations)
        distance = graph.jump_distance(current_system, destination)
        if not distance:
            # Generated worlds are validated connected, and the destination is
            # never the current system, so a zero/None hop count means the graph
            # handed us a disconnected world. Say so, rather than quietly
            # pricing a trip that cannot be taken.
            raise ValueError(
                f"no hyperspace route from {current_system} to {destination}: "
                "the world graph is not connected"
            )
        multiplier = distance_multiplier(distance, rules.far_destination_bonus)

        cargo_type: str | None = None
        cargo_units = 0
        passengers = 0
        if kind in ("cargo", "mixed"):
            cargo_type = rng.choice(rules.cargo_types)
            cargo_units = rng.randint(1, cargo_ceiling)
        if kind in ("passenger", "mixed"):
            passengers = rng.randint(1, passenger_ceiling)

        missions.append(
            Mission(
                offer_id=(visit_serial, index),
                cargo_type=cargo_type,
                cargo_units=cargo_units,
                passengers=passengers,
                destination=destination,
                distance=distance,
                far_bonus=multiplier,
                fare=mission_fare(
                    cargo_units, cargo_rate, passengers, passenger_rate, multiplier
                ),
            )
        )
    return missions


def pluralise(count: int, singular: str, plural: "str | None" = None) -> str:
    """``pluralise(1, "slot") == "slot"``; ``pluralise(4, "slot") == "slots"``.

    Every refusal and receipt on this screen states a quantity, and "this job
    needs 2 berths and only 1 are free" is the kind of copy a test suite will
    happily never notice. The rule lives here so the model and the view cannot
    each invent their own.
    """
    return singular if count == 1 else (plural if plural is not None else f"{singular}s")


def mission_payload_text(mission: Mission) -> str:
    """What the job carries, without the destination (the view adds routing)."""
    parts: list[str] = []
    if mission.cargo_units:
        units = pluralise(mission.cargo_units, "unit")
        parts.append(f"{mission.cargo_units} {units} of {mission.cargo_type}")
    if mission.passengers:
        word = "passengers" if mission.passengers != 1 else "passenger"
        parts.append(f"{mission.passengers} {word}")
    return "; ".join(parts)


def mission_route_text(mission: Mission) -> str:
    """Where it goes and what the far bonus did to the price.

    The spec wants the far bonus visible even for an undiscovered destination,
    so the hop count is stated as a fact of the lane, not of the player's charts.
    """
    jumps = "1 jump" if mission.distance == 1 else f"{mission.distance} jumps"
    bonus = "" if mission.far_bonus == 1.0 else f", far bonus x{mission.far_bonus:.1f}"
    return f"{mission.destination} ({jumps}{bonus})"


def format_credits(amount: float) -> str:
    """Credits as whole, thousands-separated digits (``20,000``).

    Credits are floats internally (fuel is priced per unit, and a unit price may
    be 2.5), but every readout in the game is whole: fractional credits are an
    artefact of the pricing, not something the player can act on.
    """
    return f"{int(amount):,}"
