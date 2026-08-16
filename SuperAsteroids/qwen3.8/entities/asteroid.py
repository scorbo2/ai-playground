"""Asteroid: an irregular polygon that tumbles, drifts, and wraps the screen.

One class serves both flavors of asteroid in the game:
  - Game Mode fields (later stages add weapon-driven split/destruction)
  - The Title Screen's cosmetic field, which per the spec uses the exact
    same movement and screen-wrapping behavior.

There is intentionally NO asteroid-vs-asteroid collision: they pass through
each other (spec: "Asteroids" section).
"""

import math
import random
from typing import Optional

import pygame

from game_constants import (
    ASTEROID_LARGEST_RADIUS,
    ASTEROID_MAX_FILL,
    ASTEROID_MAX_SPEED,
    ASTEROID_MIN_FILL,
    ASTEROID_MIN_RADIUS_FOR_SPLIT,
    ASTEROID_MIN_SPEED,
    ASTEROID_OUTLINE_WIDTH,
    ASTEROID_ROTATION_RADIUS_LARGE,
    ASTEROID_ROTATION_RADIUS_SMALL,
    ASTEROID_ROTATION_RATE_LARGE,
    ASTEROID_ROTATION_RATE_SMALL,
    ASTEROID_SPAWN_ATTEMPTS,
    ASTEROID_SPEED_INCREMENT_PER_LEVEL,
    ASTEROID_SPLIT_CHILDREN,
    ASTEROID_SPLIT_RADIUS_DIVISOR,
    ASTEROID_SPLIT_SPEED_MULTIPLIER,
    ASTEROID_VERTEX_COUNT_RANGE,
    ASTEROID_VERTEX_RADIUS_FACTOR_RANGE,
    CRAFT_SPAWN_SAFE_DISTANCE,
    TITLE_ASTEROID_COUNT_RANGE,
    WHITE,
)
from position_utils import wrap_around


def rotation_speed_for_radius(radius: float) -> float:
    """Tumble speed in degrees/frame for an asteroid of ``radius`` px.

    Spec: rotation scales inversely with size, anchored at 1 deg/frame for
    radius >= 40 and 10 deg/frame for radius <= 20, with linear
    interpolation between. Clamped at both ends so out-of-range radii (e.g.
    child asteroids shrinking below 20) keep a sane rate.
    """
    if radius >= ASTEROID_ROTATION_RADIUS_LARGE:
        return ASTEROID_ROTATION_RATE_LARGE
    if radius <= ASTEROID_ROTATION_RADIUS_SMALL:
        return ASTEROID_ROTATION_RATE_SMALL
    t = ((ASTEROID_ROTATION_RADIUS_LARGE - radius)
         / (ASTEROID_ROTATION_RADIUS_LARGE - ASTEROID_ROTATION_RADIUS_SMALL))
    return (ASTEROID_ROTATION_RATE_LARGE
            + t * (ASTEROID_ROTATION_RATE_SMALL - ASTEROID_ROTATION_RATE_LARGE))


class Asteroid:
    """A tumbling, drifting asteroid with screen wrap on all edges."""

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 radius: float, fill, rotation_speed: float,
                 shape: Optional[list] = None):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.radius = float(radius)
        self.fill = fill
        # Signed degrees/frame: the SIGN is the tumble direction, fixed for
        # the asteroid's lifetime (children inherit it, spec: Asteroids).
        self._rotation_speed = rotation_speed
        # Start de-rotated relative to each other so a fresh field does not
        # look like a stamping machine.
        self._rotation = random.uniform(0.0, 360.0)
        self._shape = shape if shape is not None else self._random_shape(radius)

    # ------------------------------------------------------------- simulation

    def update(self, width: int, height: int) -> None:
        self.x += self.vx
        self.y += self.vy
        self._rotation = (self._rotation + self._rotation_speed) % 360.0
        self._wrap(width, height)

    def _wrap(self, width: int, height: int) -> None:
        self.x, self.y = wrap_around(self.x, self.y, self.radius, width, height)

    # ------------------------------------------------------------- game rules

    def split(self) -> list:
        """Result of a weapon impact (stages 4+ call this).

        Returns 2-3 smaller child asteroids, or [] if this asteroid is too
        small to split (it is destroyed instead). Children spawn at the
        parent's position, inherit the parent's rotation direction and
        color, move at 1.2x the parent's speed in random directions, and get
        fresh irregular shapes.
        """
        if self.radius < ASTEROID_MIN_RADIUS_FOR_SPLIT:
            return []
        speed = math.hypot(self.vx, self.vy) * ASTEROID_SPLIT_SPEED_MULTIPLIER
        child_radius = self.radius / ASTEROID_SPLIT_RADIUS_DIVISOR
        children = []
        for _ in range(random.randint(*ASTEROID_SPLIT_CHILDREN)):
            angle = random.uniform(0.0, 2.0 * math.pi)
            children.append(Asteroid(
                x=self.x,
                y=self.y,
                vx=math.cos(angle) * speed,
                vy=math.sin(angle) * speed,
                radius=child_radius,
                fill=self.fill,
                rotation_speed=self._rotation_speed,
            ))
        return children

    # ------------------------------------------------------------------ draw

    def draw(self, screen: pygame.Surface) -> None:
        angle = math.radians(self._rotation)
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        points = [
            (int(round(self.x + px * cos_a - py * sin_a)),
             int(round(self.y + px * sin_a + py * cos_a)))
            for px, py in self._shape
        ]
        pygame.draw.polygon(screen, self.fill, points)
        pygame.draw.polygon(screen, WHITE, points, width=ASTEROID_OUTLINE_WIDTH)

    # --------------------------------------------------------------- factories

    @staticmethod
    def _random_shape(radius: float) -> list:
        """Irregular outline per the spec's suggested generation: 8-14
        vertices on evenly spaced angles, each nudged in or out by
        0.75-1.25x. Stored relative to the center so rotation is cheap."""
        vertex_count = random.randint(*ASTEROID_VERTEX_COUNT_RANGE)
        shape = []
        for i in range(vertex_count):
            angle = 2.0 * math.pi * i / vertex_count
            vertex_radius = radius * random.uniform(*ASTEROID_VERTEX_RADIUS_FACTOR_RANGE)
            shape.append((math.cos(angle) * vertex_radius,
                          math.sin(angle) * vertex_radius))
        return shape


# ---------------------------------------------------------------- spawn rules

def _make_asteroid(radius: float, speed_range: tuple, position: tuple) -> Asteroid:
    """One randomly configured asteroid: speed, heading, grayscale fill, and
    tumble direction all chosen per the spec's randomness rules."""
    speed = random.uniform(*speed_range)
    heading = random.uniform(0.0, 2.0 * math.pi)
    fill_value = random.randint(ASTEROID_MIN_FILL, ASTEROID_MAX_FILL)
    direction = random.choice((-1.0, 1.0))
    return Asteroid(
        x=position[0],
        y=position[1],
        vx=math.cos(heading) * speed,
        vy=math.sin(heading) * speed,
        radius=radius,
        fill=(fill_value, fill_value, fill_value),
        rotation_speed=direction * rotation_speed_for_radius(radius),
    )


def _position_away_from_ship(width: int, height: int, ship_position: tuple) -> tuple:
    """A random position at least CRAFT_SPAWN_SAFE_DISTANCE from the
    player's ship, falling back to a random screen corner after a fixed
    number of failed attempts (spec: "fall back to any screen corner")."""
    ship_x, ship_y = ship_position
    for _ in range(ASTEROID_SPAWN_ATTEMPTS):
        x, y = random.uniform(0.0, width), random.uniform(0.0, height)
        if math.hypot(x - ship_x, y - ship_y) >= CRAFT_SPAWN_SAFE_DISTANCE:
            return (x, y)
    return random.choice(((0, 0), (width, 0), (0, height), (width, height)))


def asteroid_speed_range_for_level(level: int) -> tuple:
    """[min, max] starting speed for level ``level`` (1-based), +0.3 px/frame
    on both bounds per level advance, uncapped (spec: Asteroids)."""
    offset = (level - 1) * ASTEROID_SPEED_INCREMENT_PER_LEVEL
    return (ASTEROID_MIN_SPEED + offset, ASTEROID_MAX_SPEED + offset)


def spawn_level_asteroids(level: int, asteroid_count: int, width: int,
                          height: int, ship_position: tuple) -> list:
    """A fresh field of large asteroids for a level.

    ``asteroid_count`` is passed in rather than derived because per-level
    count growth is random (1-2 per advancement) and only the game state
    knows the history of those rolls for the current run.
    """
    speed_range = asteroid_speed_range_for_level(level)
    return [
        _make_asteroid(
            radius=ASTEROID_LARGEST_RADIUS,
            speed_range=speed_range,
            position=_position_away_from_ship(width, height, ship_position),
        )
        for _ in range(asteroid_count)
    ]


def spawn_title_screen_asteroids(width: int, height: int) -> list:
    """The title screen's cosmetic field: 3-6 large asteroids drifting and
    tumbling on level-1 speeds. No ship-distance constraint (there is no
    ship on the title screen) and no collisions or splits, ever."""
    count = random.randint(*TITLE_ASTEROID_COUNT_RANGE)
    level_one_speeds = asteroid_speed_range_for_level(1)
    return [
        _make_asteroid(
            radius=ASTEROID_LARGEST_RADIUS,
            speed_range=level_one_speeds,
            position=(random.uniform(0.0, width), random.uniform(0.0, height)),
        )
        for _ in range(count)
    ]
