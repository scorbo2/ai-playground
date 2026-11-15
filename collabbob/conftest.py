"""Pytest configuration for the game test suite.

Runs the suite headless: the dummy SDL video/audio drivers are enabled
before pygame is imported by any test module, and the project root is put
on sys.path so tests can import src.*.
"""

import json
import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import pytest

from src.config import CONFIG_FILES, base_config


@pytest.fixture
def config_factory(tmp_path):
    """Factory that writes complete, valid config sets into a temp dir.

    Returns a callable(config_overrides=None, overrides=None) that writes
    the three config files with identical key values (starting from the base
    config) and returns the temp dir where they were written. `config_overrides`
    are merged into the root, `overrides` use dotted paths into the config
    (e.g. new_game.starting_credits).
    """

    def factory(config_overrides=None, overrides=None):
        values = dict(base_config())
        if config_overrides:
            values.update(config_overrides)
        for dotted_key, value in (overrides or {}).items():
            _set_nested(values, dotted_key, value)
        for name in CONFIG_FILES:
            path = os.path.join(tmp_path, name)
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(values, handle, indent=2)
        return tmp_path

    return factory


def _set_nested(values, dotted_key, value):
    """Set `value` at the nested path described by `dotted_key` (dot separated)."""
    keys = dotted_key.split(".")
    node = values
    for key in keys[:-1]:
        node = node.setdefault(key, {})
    node[keys[-1]] = value
