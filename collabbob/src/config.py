"""Game configuration loading and validation.

The game reads its configuration from three JSON files (config_easy.json,
config_medium.json, config_hard.json) in the directory that contains the
main.py entry-point shim. All three files must contain exactly the keys
described by CONFIG_ROOT; missing keys and unrecognized keys are fatal.
JSON parsing and validation happen once, at startup.
"""

import json
import os
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, ValidationError

# Directory holding the main.py shim (the game root), resolved from this
# module's location so the config files are always found relative to the
# project root, regardless of the current working directory.
GAME_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_FILES = (
    "config_easy.json",
    "config_medium.json",
    "config_hard.json",
)


class ConfigLoadError(Exception):
    """Raised when a config file is missing, unreadable, or invalid."""


class _ConfigModel(BaseModel):
    """Base class: reject any key that is not declared below."""

    model_config = ConfigDict(extra="forbid")


class _JumpConfig(_ConfigModel):
    fuel_cost: float
    frames: int
    acceleration: float


class _StarConfig(_ConfigModel):
    count: int
    grey_min: int
    grey_max: int


class _TacticalConfig(_ConfigModel):
    system_pixel_size: int
    fuel_burn_per_frame: float
    landing_range: int
    planet_diameter: int
    launch_immunity_frames: int
    jump: _JumpConfig
    stars: _StarConfig


class _PlayerShipConfig(_ConfigModel):
    fuel_capacity: int
    passenger_space: int
    cargo_room: int
    shields: int
    armor: int
    weapon_power: float
    weapon_fire_rate: float
    turn_rate_deg_per_sec: float
    weapon_range: int
    acceleration_rate: float
    top_speed: float
    length: int
    width: int


class _UpgradeStepConfig(_ConfigModel):
    shields: int
    armor: int
    engine_percent: float
    weapon_damage: int
    fuel: int
    cargo: int
    passenger: int


class _CombatConfig(_ConfigModel):
    projectile_speed_bonus: float
    projectile_radius: int
    pirate_bounty: int
    bobber_bounty: int
    localhoster_bounty: int


class _EconomyConfig(_ConfigModel):
    win_credits: int
    fuel_cost_per_unit: float
    repair_cost_per_point: float
    upgrade_base_cost: float
    upgrade_cost_multiplier: float
    upgrade_max_level: int
    upgrade_offers_min: int
    upgrade_offers_max: int
    missions_min: int
    missions_max: int
    cargo_fare_per_unit: List[float]
    passenger_fare_each: List[float]
    far_destination_bonus: float
    cargo_types: List[str]


class _NewGameConfig(_ConfigModel):
    starting_credits: int


class _RngConfig(_ConfigModel):
    seed: Optional[int] = None


class ConfigRoot(_ConfigModel):
    rng: _RngConfig
    new_game: _NewGameConfig
    player_ship: _PlayerShipConfig
    upgrade_steps: _UpgradeStepConfig
    tactical: _TacticalConfig
    combat: _CombatConfig
    economy: _EconomyConfig


def base_config() -> dict:
    """A complete, valid base configuration (medium difficulty) as a plain dict.

    Used by the config-factory test fixture to materialize full config sets
    in temp directories. The shipped config_*.json files are the canonical
    configuration data; this mirrors them for tests.
    """
    return {
        "rng": {"seed": None},
        "new_game": {"starting_credits": 20000},
        "player_ship": {
            "fuel_capacity": 1000,
            "passenger_space": 5,
            "cargo_room": 20,
            "shields": 50,
            "armor": 100,
            "weapon_power": 10,
            "weapon_fire_rate": 1,
            "turn_rate_deg_per_sec": 180,
            "weapon_range": 1200,
            "acceleration_rate": 0.2,
            "top_speed": 5,
            "length": 40,
            "width": 20,
        },
        "upgrade_steps": {
            "shields": 50,
            "armor": 100,
            "engine_percent": 20,
            "weapon_damage": 15,
            "fuel": 250,
            "cargo": 20,
            "passenger": 5,
        },
        "tactical": {
            "system_pixel_size": 2000,
            "fuel_burn_per_frame": 0.2,
            "landing_range": 100,
            "planet_diameter": 40,
            "launch_immunity_frames": 120,
            "jump": {"fuel_cost": 250, "frames": 180, "acceleration": 1.2},
            "stars": {"count": 150, "grey_min": 128, "grey_max": 255},
        },
        "combat": {
            "projectile_speed_bonus": 8,
            "projectile_radius": 3,
            "pirate_bounty": 10000,
            "bobber_bounty": 5000,
            "localhoster_bounty": 5000,
        },
        "economy": {
            "win_credits": 1000000,
            "fuel_cost_per_unit": 2,
            "repair_cost_per_point": 4,
            "upgrade_base_cost": 1000,
            "upgrade_cost_multiplier": 2,
            "upgrade_max_level": 5,
            "upgrade_offers_min": 2,
            "upgrade_offers_max": 5,
            "missions_min": 4,
            "missions_max": 8,
            "cargo_fare_per_unit": [150, 400],
            "passenger_fare_each": [800, 2000],
            "far_destination_bonus": 1.5,
            "cargo_types": [
                "iron ore",
                "wine",
                "textiles",
                "computer parts",
                "colony supplies",
                "machine parts",
            ],
        },
    }


def load_config(config_dir=GAME_ROOT) -> dict:
    """Load and validate the three game config files from `config_dir`.

    Raises ConfigLoadError if any file is missing, unreadable, not valid
    JSON, or missing/unrecognized keys. The three files are parsed and
    validated once, at startup; returns the validated configs keyed by file
    name.
    """
    loaded = {}
    for name in CONFIG_FILES:
        path = os.path.join(config_dir, name)
        loaded[name] = _load_single(name, path)
    return loaded


def _load_single(name: str, path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            raw = json.load(handle)
    except OSError as exc:
        raise ConfigLoadError(
            f"cannot read config file {name} at {path}: {exc}"
        ) from exc
    except UnicodeDecodeError as exc:
        raise ConfigLoadError(
            f"config file {name} at {path} is not valid text: {exc}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ConfigLoadError(
            f"config file {name} at {path} is not valid JSON: {exc}"
        ) from exc

    try:
        model = ConfigRoot.model_validate(raw)
    except ValidationError as exc:
        raise ConfigLoadError(f"config file {name} at {path} is invalid: {exc}") from exc

    return model.model_dump()
