"""SuperAsteroids entities (world objects that move and are drawn)."""

from entities.asteroid import (
    Asteroid,
    spawn_level_asteroids,
    spawn_title_screen_asteroids,
)

__all__ = [
    "Asteroid",
    "spawn_level_asteroids",
    "spawn_title_screen_asteroids",
]
