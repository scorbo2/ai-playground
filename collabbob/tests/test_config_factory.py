"""Stage 1 tests for the config-factory fixture."""

from src.config import CONFIG_FILES, base_config, load_config


def test_config_factory_writes_valid_config_set(config_factory):
    """The factory writes a complete, valid config set into a temp dir."""
    dir = config_factory()
    configs = load_config(dir)
    assert set(configs) == set(CONFIG_FILES)
    for values in configs.values():
        assert set(values) == set(base_config())


def test_config_factory_overrides_applied(config_factory):
    """Factory overrides are applied to all three config files."""
    dir = config_factory(
        overrides={
            "new_game.starting_credits": 42000,
            "tactical.fuel_burn_per_frame": 0.5,
        }
    )
    configs = load_config(dir)
    for values in configs.values():
        assert values["new_game"]["starting_credits"] == 42000
        assert values["tactical"]["fuel_burn_per_frame"] == 0.5
