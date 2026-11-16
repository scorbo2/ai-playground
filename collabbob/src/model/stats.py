"""Player ship statistics.

A :class:`ShipStats` block captures the *current* tunable numbers that drive
the player's craft: how much fuel it holds, its cargo/passenger capacity, its
defences and weapons, and its handling characteristics. Upgrades mutate this
block in place; combat and economy code read from it.

The starting values come straight from ``player_ship`` in the game config.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ShipStats:
    """Mutable snapshot of the player ship's tunable statistics."""

    fuel_capacity: float
    passenger_space: int
    cargo_room: int
    # Maximum values for the defence bars. ``shields`` auto-refill to this and
    # ``armor`` never regenerates, so both are stable capacities the HUD can
    # divide the current values against when drawing status bars.
    max_shields: float
    max_armor: float
    shields: float
    armor: float
    weapon_power: float
    weapon_fire_rate: float
    turn_rate_deg_per_sec: float
    weapon_range: float
    acceleration_rate: float
    top_speed: float
    length: float
    width: float


def ship_stats_from_config(player_ship: dict) -> ShipStats:
    """Build a :class:`ShipStats` from the ``player_ship`` config section."""
    return ShipStats(
        fuel_capacity=float(player_ship["fuel_capacity"]),
        passenger_space=int(player_ship["passenger_space"]),
        cargo_room=int(player_ship["cargo_room"]),
        max_shields=float(player_ship["shields"]),
        max_armor=float(player_ship["armor"]),
        shields=float(player_ship["shields"]),
        armor=float(player_ship["armor"]),
        weapon_power=float(player_ship["weapon_power"]),
        weapon_fire_rate=float(player_ship["weapon_fire_rate"]),
        turn_rate_deg_per_sec=float(player_ship["turn_rate_deg_per_sec"]),
        weapon_range=float(player_ship["weapon_range"]),
        acceleration_rate=float(player_ship["acceleration_rate"]),
        top_speed=float(player_ship["top_speed"]),
        length=float(player_ship["length"]),
        width=float(player_ship["width"]),
    )


def apply_damage_order(
    shields: float, armor: float, amount: float
) -> "tuple[float, float]":
    """Spend damage on shields first, then on the hull; return ``(shields, armor)``.

    The spec's damage order, written exactly once. The player's hull and every
    NPC hull call this, because "shield absorbs before armour" is the sort of
    rule that silently drifts the moment it exists twice — one copy starting to
    round, another to floor, a third to let a shot punch through shields early.

    Nothing here clamps armour at zero: a hull below zero is a destroyed hull
    (see the ``destroyed`` properties that read this), and clamping here would
    make "overkill" unobservable to the code that reports kills and bounties.
    Shields are never driven below zero, since that would be armour damage
    charged twice.
    """
    incoming = max(0.0, float(amount))
    current_shields = float(shields)
    absorbed = min(current_shields, incoming)
    return current_shields - absorbed, float(armor) - (incoming - absorbed)
