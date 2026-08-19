"""Powerup icon: a drifting colored circle with a weapon label.

Per the spec (Weapons -> Powerups):
  - timer spawns (every POWERUP_INTERVAL of active play) may NOT land on the
    craft or in contact with any asteroid (all checks wrap-aware);
  - split/destruction-event spawns DO sit at the event point (exempt);
  - every icon is grace-protected for POWERUP_GRACE frames: it cannot be
    destroyed by asteroids or weapons, but the CRAFT may still collect it;
  - a craft pickup upgrades the current weapon type (+1 power, max 3) or
    switches to the icon's type at power 1.
"""

import math
import random

import pygame

from font_manager import render_text
from game_constants import (
    PLAYER_RADIUS,
    POWERUP_COLORS,
    POWERUP_GRACE,
    POWERUP_LETTERS,
    POWERUP_RADIUS,
    POWERUP_SPAWN_ATTEMPTS,
    POWERUP_SPEED,
    POWERUP_TYPES,
    WHITE,
)
from position_utils import torus_distance, wrap_around

# One cached label surface per weapon type (icons have no cap, so these are
# reused instead of re-rendered; fonts themselves are font-manager-cached).
_powerup_label_font_size = 22
_LABELS: dict = {}


def _label(weapon_name: str) -> pygame.Surface:
    label = _LABELS.get(weapon_name)
    if label is None:
        label = render_text(POWERUP_LETTERS[weapon_name],
                            _powerup_label_font_size, WHITE)
        _LABELS[weapon_name] = label
    return label


def random_powerup(x: float, y: float,
                   grace_frames: int = POWERUP_GRACE) -> "Powerup":
    """A powerup with a randomly chosen weapon type at (x, y)."""
    weapon_name = random.choice([n for n, _c, _l in POWERUP_TYPES])
    return Powerup(x, y, weapon_name, grace_frames)


def spawn_timer_powerup(width: int, height: int, ship_position: tuple,
                        asteroids) -> "Powerup":
    """The periodic 30-second spawn: hunts a position that is not on the
    craft and not touching any asteroid (spec), then falls back to a plain
    random spot (a screen packed solid with rocks is the only failure)."""
    for _ in range(POWERUP_SPAWN_ATTEMPTS):
        x = random.uniform(0.0, width)
        y = random.uniform(0.0, height)
        if _spot_is_clear(x, y, ship_position, asteroids, width, height):
            return random_powerup(x, y)
    return random_powerup(random.uniform(0.0, width),
                          random.uniform(0.0, height))


def spawn_drop_powerup(x: float, y: float) -> "Powerup":
    """Dropped by an asteroid split/destruction event, AT that event's
    location (exempt from the clearance rule by design - spec)."""
    return random_powerup(x, y)


def _spot_is_clear(x: float, y: float, ship_position: tuple, asteroids,
                   width: int, height: int) -> bool:
    if torus_distance(x, y, ship_position[0], ship_position[1],
                      width, height) < PLAYER_RADIUS + POWERUP_RADIUS:
        return False
    return all(torus_distance(x, y, a.x, a.y, width, height)
               >= a.radius + POWERUP_RADIUS
               for a in asteroids)


class Powerup:

    def __init__(self, x: float, y: float, weapon_name: str,
                 grace_frames: int = POWERUP_GRACE):
        self.x = float(x)
        self.y = float(y)
        self.weapon_name = weapon_name
        self.grace_frames = grace_frames
        self.radius = POWERUP_RADIUS
        self.fill = POWERUP_COLORS[weapon_name]
        heading = random.uniform(0.0, 2.0 * math.pi)
        self.vx = math.cos(heading) * POWERUP_SPEED
        self.vy = math.sin(heading) * POWERUP_SPEED

    @property
    def in_grace(self) -> bool:
        return self.grace_frames > 0

    def update(self, width: int, height: int) -> None:
        self.x += self.vx
        self.y += self.vy
        self.x, self.y = wrap_around(self.x, self.y, self.radius,
                                     width, height)
        if self.grace_frames > 0:
            self.grace_frames -= 1

    def overlaps_circle(self, cx: float, cy: float, radius: float,
                        width: int, height: int) -> bool:
        return (torus_distance(self.x, self.y, cx, cy, width, height)
                <= self.radius + radius)

    def draw(self, screen: pygame.Surface) -> None:
        pygame.draw.circle(screen, self.fill,
                           (int(round(self.x)), int(round(self.y))),
                           self.radius)
        label = _label(self.weapon_name)
        screen.blit(label, label.get_rect(
            center=(int(round(self.x)), int(round(self.y)))))
