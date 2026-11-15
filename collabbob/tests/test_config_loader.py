"""Stage 1 tests: config loading, validation, and startup failure handling."""

import json
import os

import pytest

import main

from src.config import (
    CONFIG_FILES,
    ConfigLoadError,
    base_config,
    load_config,
)


def test_shipped_configs_load_and_validate():
    """The config files shipped with the project load and validate."""
    configs = load_config()
    assert set(configs) == set(CONFIG_FILES)
    for values in configs.values():
        assert set(values) == set(base_config())


def test_shipped_configs_have_identical_key_sets():
    """All three config files must share exactly the same key set."""
    configs = load_config()
    key_sets = {frozenset(values) for values in configs.values()}
    assert len(key_sets) == 1


def test_config_missing_file_raises_config_error(tmp_path):
    """A missing config file is a fatal config error."""
    with pytest.raises(ConfigLoadError) as excinfo:
        load_config(tmp_path)
    assert "config_easy.json" in str(excinfo.value)


def test_config_missing_file_exits_game_with_error(tmp_path, capsys):
    """A missing config file makes the game exit immediately with a stderr error."""
    with pytest.raises(SystemExit) as excinfo:
        main.main(config_dir=tmp_path)
    assert excinfo.value.code == 1
    captured = capsys.readouterr()
    assert "config_easy.json" in captured.err
    assert captured.err.strip()


def test_config_unreadable_file_raises_config_error(tmp_path):
    """An unreadable config file (a directory in place of a file) is fatal."""
    os.makedirs(os.path.join(tmp_path, "config_easy.json"))
    with pytest.raises(ConfigLoadError) as excinfo:
        load_config(tmp_path)
    assert "config_easy.json" in str(excinfo.value)


def test_config_invalid_json_raises_config_error(tmp_path):
    """A config file with invalid JSON is fatal."""
    path = os.path.join(tmp_path, "config_easy.json")
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{not valid json")
    with pytest.raises(ConfigLoadError) as excinfo:
        load_config(tmp_path)
    assert "config_easy.json" in str(excinfo.value)


def test_config_missing_expected_key_raises_config_error(config_factory):
    """A config file missing an expected key is fatal."""
    dir = config_factory()
    easy_path = os.path.join(dir, "config_easy.json")
    with open(easy_path, encoding="utf-8") as handle:
        values = json.load(handle)
    del values["player_ship"]["fuel_capacity"]
    with open(easy_path, "w", encoding="utf-8") as handle:
        json.dump(values, handle)

    with pytest.raises(ConfigLoadError) as excinfo:
        load_config(dir)
    assert "fuel_capacity" in str(excinfo.value)


def test_config_unrecognized_key_raises_config_error(config_factory):
    """A config file with an unrecognized key is fatal."""
    dir = config_factory()
    easy_path = os.path.join(dir, "config_easy.json")
    with open(easy_path, encoding="utf-8") as handle:
        values = json.load(handle)
    values["unexpected_key"] = 1
    with open(easy_path, "w", encoding="utf-8") as handle:
        json.dump(values, handle)

    with pytest.raises(ConfigLoadError) as excinfo:
        load_config(dir)
    assert "unexpected_key" in str(excinfo.value)
