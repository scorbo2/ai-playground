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

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator

from src.map_systems.graph import NATO_SYSTEMS

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
    """Hyperspace tunables.

    ``spawn_distance`` is the [min, max] band, in world pixels from the planet,
    at which the player arrives. ``transition_frames`` is the white-out that
    covers the world swap (see DECISIONS.md, Stage 8).
    """

    fuel_cost: float
    frames: int
    acceleration: float
    transition_frames: int
    spawn_distance: List[float]


class _BoundaryWarningConfig(_ConfigModel):
    """The "System boundary reached" banner: how long it shows, how often it repeats."""

    message_frames: int
    cooldown_frames: int

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
    boundary_warnings: _BoundaryWarningConfig
    stars: _StarConfig

    @model_validator(mode="after")
    def _check_jump_is_sane(self) -> "_TacticalConfig":
        """Reject jump geometry that would spawn the player somewhere impossible.

        These span three config keys (the jump band, the landing range, and the
        system size), so they cannot be validated inside ``_JumpConfig`` alone.
        A band that overlaps the landing range would drop the player on top of
        the planet they are supposed to fly to; a band outside the system would
        drop them straight through the boundary they cannot cross.
        """
        jump = self.jump
        if jump.frames < 1:
            raise ValueError("tactical.jump.frames must be at least 1")
        if jump.transition_frames < 1:
            raise ValueError("tactical.jump.transition_frames must be at least 1")
        if jump.acceleration <= 0:
            raise ValueError("tactical.jump.acceleration must be greater than 0")
        if jump.fuel_cost < 0:
            raise ValueError("tactical.jump.fuel_cost cannot be negative")

        if len(jump.spawn_distance) != 2:
            raise ValueError(
                "tactical.jump.spawn_distance must be [min, max], "
                f"got {jump.spawn_distance!r}"
            )
        low, high = jump.spawn_distance
        if low >= high:
            raise ValueError(
                f"tactical.jump.spawn_distance must ascend, got [{low}, {high}]"
            )
        if low <= self.landing_range:
            raise ValueError(
                f"tactical.jump.spawn_distance[0] ({low}) must exceed "
                f"tactical.landing_range ({self.landing_range}): arriving inside "
                "landing range means the player never has to fly to the planet"
            )
        half = self.system_pixel_size / 2.0
        if high > half:
            raise ValueError(
                f"tactical.jump.spawn_distance[1] ({high}) must stay inside half of "
                f"tactical.system_pixel_size ({self.system_pixel_size}), otherwise "
                "the player arrives outside the system they just jumped to"
            )

        warnings = self.boundary_warnings
        if warnings.message_frames < 1 or warnings.cooldown_frames < 1:
            raise ValueError(
                "tactical.boundary_warnings frame budgets must be at least 1"
            )
        return self


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


class _MapConfig(_ConfigModel):
    """World-graph shape. Cross-field sanity checks live here, not in the game.

    A config the loader accepts but the generator cannot build would otherwise
    fail at "New game" time - after the window is open and the player has
    invested in a difficulty choice. The generator still validates its own
    output, but nonsense ranges are config errors and belong here.
    """

    system_count: int
    connections_min: int
    connections_max: int
    alpha_connections: List[str]

    @model_validator(mode="after")
    def _check_connections_are_possible(self) -> "_MapConfig":
        if self.system_count < 2:
            raise ValueError("map.system_count must be at least 2")
        if self.system_count > len(NATO_SYSTEMS):
            raise ValueError(
                f"map.system_count cannot exceed {len(NATO_SYSTEMS)}: the roster of "
                "NATO system names is fixed in code"
            )
        if not 1 <= self.connections_min <= self.connections_max:
            raise ValueError(
                "map.connections_min must be >= 1 and <= map.connections_max"
            )
        if self.connections_max >= self.system_count:
            raise ValueError(
                "map.connections_max must be below map.system_count: a system "
                "cannot connect to itself"
            )
        if not self.alpha_connections:
            raise ValueError("map.alpha_connections must name at least one system")
        if len(set(self.alpha_connections)) != len(self.alpha_connections):
            raise ValueError("map.alpha_connections contains duplicates")
        if len(self.alpha_connections) > self.connections_max:
            raise ValueError(
                "map.alpha_connections lists more systems than map.connections_max allows"
            )
        return self


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
    map: _MapConfig


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
            "jump": {
                "fuel_cost": 250,
                "frames": 180,
                "acceleration": 1.2,
                "transition_frames": 45,
                "spawn_distance": [400, 850],
            },
            "boundary_warnings": {"message_frames": 120, "cooldown_frames": 300},
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
        "map": {
            "system_count": 26,
            "connections_min": 1,
            "connections_max": 3,
            "alpha_connections": ["Bravo", "Charlie", "Delta"],
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
