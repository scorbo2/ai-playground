"""Player weapons.

Stage 5: all three weapons (Cannon, Laser, Ramming Shield) are live, with
power levels 1-3 driven by powerup pickups. ``make_weapon`` materializes a
weapon from its spec name (what powerup icons carry).
"""

from weapons.base import ChargedWeapon, Weapon
from weapons.cannon import Cannon
from weapons.laser import Laser
from weapons.mines import ShrapnelMines
from weapons.shield import RammingShield

__all__ = [
    "Cannon",
    "ChargedWeapon",
    "Laser",
    "RammingShield",
    "ShrapnelMines",
    "Weapon",
    "make_weapon",
]

# Powerup icons carry a weapon TYPE by name; this table turns that name
# back into a weapon instance. The NAMES are the single source of truth
# (POWERUP_TYPES in game_constants uses the same strings).
_WEAPONS = {
    Cannon.NAME: Cannon,
    Laser.NAME: Laser,
    RammingShield.NAME: RammingShield,
    ShrapnelMines.NAME: ShrapnelMines,
}


def make_weapon(weapon_name: str, power_level: int = 1) -> Weapon:
    """A fresh weapon of ``weapon_name`` type at ``power_level``."""
    weapon_class = _WEAPONS.get(weapon_name)
    if weapon_class is None:
        # Unreachable if POWERUP_TYPES and _WEAPONS stay in sync; fall back
        # to the default weapon rather than crashing mid-game over a name.
        return Cannon(power_level)
    return weapon_class(power_level)
