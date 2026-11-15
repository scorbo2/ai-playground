"""Ship upgrades: per-stat offers, an escalating cost curve, and the in-place
stat mutation.

Upgrades are purchased per port visit: entering a system rolls a small number
of *offers* (distinct stats, each one level above the ship's current level for
that stat). The cost of a level is

    base * cost_multiplier ** (level - 1)

so the first purchase of any stat costs ``base``, the next doubles (or
multiplies by the configured factor) it, and so on. Every stat has a hard
wall at ``upgrade_max_level`` — no offer is ever generated past it.

The magnitudes are fixed by the top-level ``upgrade_steps`` config block
(``shields``, ``armor``, ``engine_percent``, ``weapon_damage``, ``fuel``,
``cargo``, ``passenger``), never hardcoded.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Mapping

from src.model.stats import ShipStats

__all__ = [
    "UPGRADE_LABELS",
    "UPGRADE_TYPES",
    "UpgradeOffer",
    "apply_upgrade",
    "generate_upgrade_offers",
    "upgrade_cost",
    "upgrade_step_for",
    "upgrade_text",
]

# The seven purchasable stats, in display order.
UPGRADE_TYPES = ("shields", "armor", "engines", "weapons", "fuel", "cargo", "passenger")

# upgrade_steps config key per upgrade type.
_STEP_KEYS = {
    "shields": "shields",
    "armor": "armor",
    "engines": "engine_percent",
    "weapons": "weapon_damage",
    "fuel": "fuel",
    "cargo": "cargo",
    "passenger": "passenger",
}

UPGRADE_LABELS = {
    "shields": "Shields",
    "armor": "Armor",
    "engines": "Engines",
    "weapons": "Weapons",
    "fuel": "Fuel",
    "cargo": "Cargo room",
    "passenger": "Passenger space",
}


@dataclass(frozen=True)
class UpgradeOffer:
    """A stat + the level it would buy + its price (level 1 = base cost)."""

    stat: str
    level: int
    cost: float


def upgrade_cost(level: int, base_cost: float, cost_multiplier: float) -> float:
    """Price of the ``level``-th purchase of a stat: ``base * multiplier**(level - 1)``.

    Level 1 pays the base price; every subsequent level multiplies the previous
    price by the configured factor. This is the curve the spec's "escalating
    cost per further upgrade" asks for.
    """
    if level < 1:
        raise ValueError(f"upgrade level must be >= 1, got {level}")
    return base_cost * (cost_multiplier ** (level - 1))


def generate_upgrade_offers(
    rules,
    stats: ShipStats,
    upgrade_levels: Mapping[str, int],
    rng: random.Random,
) -> list[UpgradeOffer]:
    """Roll ``upgrade_offers_min``..``upgrade_offers_max`` distinct-stat offers
    for one port visit.

    The sample is drawn from the stats that can still be upgraded, not from all
    seven and then filtered: filtering afterwards means a ship with several
    maxed stats silently gets fewer offers than the config asked for, and a
    fully maxed ship is told nothing at all (which is correct) rather than
    offered five things it cannot buy (which is noise).
    """
    max_level = rules.upgrade_max_level
    pool = [
        stat for stat in UPGRADE_TYPES if int(upgrade_levels.get(stat, 0)) < max_level
    ]
    if not pool:
        return []

    count = min(
        rng.randint(rules.upgrade_offers_min, rules.upgrade_offers_max), len(pool)
    )
    if count <= 0:
        return []  # a config may legally ask for zero offers

    return [
        UpgradeOffer(
            stat=stat,
            level=int(upgrade_levels.get(stat, 0)) + 1,
            cost=upgrade_cost(
                int(upgrade_levels.get(stat, 0)) + 1,
                rules.upgrade_base_cost,
                rules.upgrade_cost_multiplier,
            ),
        )
        for stat in rng.sample(pool, k=count)
    ]


def apply_upgrade(stats: ShipStats, stat: str, step_magnitude: float) -> None:
    """Apply one level of ``stat`` to the ship, in place.

    Shields and armor are topped up to the new maximum (a stronger hull should
    not sit at the old scar level; landing already refunds shields for free,
    and this is the upgrade's own moment to do the same). Engines scale both
    acceleration and top speed by a percentage, per spec.
    """
    if stat not in UPGRADE_TYPES:
        raise ValueError(f"unknown upgrade stat: {stat!r}")
    if stat == "shields":
        stats.max_shields += step_magnitude
        stats.shields = stats.max_shields
    elif stat == "armor":
        stats.max_armor += step_magnitude
        stats.armor = stats.max_armor
    elif stat == "engines":
        factor = 1.0 + float(step_magnitude) / 100.0
        stats.acceleration_rate *= factor
        stats.top_speed *= factor
    elif stat == "weapons":
        stats.weapon_power += step_magnitude
    elif stat == "fuel":
        stats.fuel_capacity += step_magnitude
    elif stat == "cargo":
        stats.cargo_room += int(step_magnitude)
    elif stat == "passenger":
        stats.passenger_space += int(step_magnitude)


def upgrade_step_for(upgrade_steps: Mapping[str, float], stat: str) -> float:
    """The config magnitude for one stat's upgrade (``upgrade_steps`` section).

    Returns the configured step rather than raising on an unknown stat, because
    the caller has already validated the stat through :data:`UPGRADE_TYPES`;
    a missing key here is a config bug the loader rejects at startup.
    """
    if stat not in _STEP_KEYS:
        raise ValueError(f"unknown upgrade stat: {stat!r}")
    return float(upgrade_steps[_STEP_KEYS[stat]])


def upgrade_text(offer: UpgradeOffer, step_magnitude: float) -> str:
    """Human-readable offer description (no price, so the view can add it)."""
    label = UPGRADE_LABELS[offer.stat]
    if offer.stat == "engines":
        return f"{label} +{int(step_magnitude)}%"
    return f"{label} +{int(step_magnitude)}"
