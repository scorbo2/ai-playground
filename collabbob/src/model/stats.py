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
