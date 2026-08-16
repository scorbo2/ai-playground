"""Enemy UFO: a drifting hostile that fires at the player's craft.

Per the spec (Enemy UFOs):
  - horizontal oval (40x15 px) with a white outline and light red fill;
  - straight-line drift at 2 px/frame in a random heading; every
    UFO_DIRECTION_CHANGE_INTERVAL frames the heading deflects by up to
    30 degrees, random left or right; screen wrap on all edges;
  - passes THROUGH asteroids (no collision with them);
  - "steals" powerups on contact - the icon is removed from play, the UFO
    is unaffected, and this works even during the icon's grace period;
  - every UFO_FIRE_INTERVAL frames fires a level 1 cannon projectile
    (2x2 yellow, half the player's level 1 range) at the craft;
  - destroyed by any player weapon, or by the ramming shield (which also
    bounces the craft per the usual rules); a craft touching one dies -
    unless the shield is raised.

  Stage note: the 100-particle light red destruction explosion lands in
  Stage 8 with the particle effects; until then, killing a UFO simply
  removes it from play.
"""

import math
import random

import pygame

from entities.player import PlayerCraft
from entities.projectile import CannonProjectile
from game_constants import (
    CANNON_PROJECTILE_SIZE,
    CANNON_PROJECTILE_SPEED,
    CRAFT_SPAWN_SAFE_DISTANCE,
    LIGHT_RED,
    PLAYER_RADIUS,
    UFO_DIRECTION_CHANGE_INTERVAL,
    UFO_FIRE_INTERVAL,
    UFO_OVAL_HEIGHT,
    UFO_OVAL_WIDTH,
    UFO_OUTLINE_WIDTH,
    UFO_PROJECTILE_DISTANCE,
    UFO_RADIUS,
    UFO_SPAWN_ATTEMPTS,
    UFO_SPEED,
    UFO_TURN_MAX_DEGREES,
    WHITE,
    YELLOW,
)
from position_utils import shortest_delta, torus_distance, wrap_around


class UFO:
    """Enemy UFO: drifts straight, deflects periodically, fires at the craft."""

    def __init__(self, x: float, y: float, heading: float):
        self.x = float(x)
        self.y = float(y)
        # Degrees, same convention as the craft and asteroids
        # (0 = +X axis, positive toward +Y in screen coordinates).
        self.heading = heading
        # The spec's collision rule: a 30px bounding circle, oval ignored.
        self.radius = UFO_RADIUS
        # First deflection and first shot on a full interval after spawn.
        self._turn_timer = UFO_DIRECTION_CHANGE_INTERVAL
        self._fire_timer = UFO_FIRE_INTERVAL

    @property
    def fire_ready(self) -> bool:
        """True once the 120-frame firing cadence is up (spec)."""
        return self._fire_timer <= 0

    def velocity(self) -> tuple:
        rad = math.radians(self.heading)
        return (math.cos(rad) * UFO_SPEED, math.sin(rad) * UFO_SPEED)

    def update(self, width: int, height: int) -> None:
        vx, vy = self.velocity()
        self.x += vx
        self.y += vy
        self.x, self.y = wrap_around(self.x, self.y, self.radius,
                                     width, height)
        self._turn_timer -= 1
        if self._turn_timer <= 0:
            self._turn_timer = UFO_DIRECTION_CHANGE_INTERVAL
            # "Up to 30 degrees randomly left/right": magnitude AND sign
            # are random, so the deflection range is -30..+30 (spec).
            self.heading = (self.heading
                            + random.uniform(-UFO_TURN_MAX_DEGREES,
                                             UFO_TURN_MAX_DEGREES)) % 360.0
        self._fire_timer -= 1

    def fire_toward(self, target_x: float, target_y: float,
                    width: int, height: int) -> CannonProjectile:
        """One hostile shot aimed at the craft's position via the SHORTEST
        on-screen path (the wrap-aware delta, like every collision in the
        game - a craft 5 px past the left edge is fired at from the left).

        "Level 1 cannon projectile" means the player's level 1 shot spec:
        the shooter's own velocity plus 6 px/frame along the shot, a 2x2
        yellow block - but with only HALF the travel budget (500 px).
        Enemy shots carry no self-immunity grace: they pass through enemy
        UFOs, so there is nothing to protect the shooter from.
        """
        dx = shortest_delta(target_x - self.x, width)
        dy = shortest_delta(target_y - self.y, height)
        rad = math.atan2(dy, dx)
        vx, vy = self.velocity()
        self._fire_timer = UFO_FIRE_INTERVAL  # cadence restarts per shot
        return CannonProjectile(
            x=self.x,
            y=self.y,
            vx=vx + CANNON_PROJECTILE_SPEED * math.cos(rad),
            vy=vy + CANNON_PROJECTILE_SPEED * math.sin(rad),
            size=CANNON_PROJECTILE_SIZE,
            color=YELLOW,
            distance_limit=UFO_PROJECTILE_DISTANCE,
            grace_frames=0,
        )

    def draw(self, screen: pygame.Surface) -> None:
        rect = pygame.Rect(0, 0, UFO_OVAL_WIDTH, UFO_OVAL_HEIGHT)
        rect.center = (int(round(self.x)), int(round(self.y)))
        pygame.draw.ellipse(screen, LIGHT_RED, rect)
        pygame.draw.ellipse(screen, WHITE, rect, width=UFO_OUTLINE_WIDTH)


def player_hits_ufo(craft: PlayerCraft, ufo: UFO,
                    width: int, height: int) -> bool:
    """Wrap-aware circle-circle test: the craft's 20 px bounding circle vs.
    the UFO's 30 px bounding circle (spec: Collision detection)."""
    return (torus_distance(craft.x, craft.y, ufo.x, ufo.y, width, height)
            <= PLAYER_RADIUS + ufo.radius)


def spawn_ufo(width: int, height: int, ship_position: tuple) -> UFO:
    """A random-heading UFO at a random screen position at least
    CRAFT_SPAWN_SAFE_DISTANCE from the craft (spec: Enemy UFOs).

    Uses the wrap-aware (torus) distance so a craft near an edge is handled
    correctly. If a packed screen leaves no open spot, falls back to any
    screen corner - the same last-resort behavior as the level asteroid
    spawner (spec: Asteroids)."""
    ship_x, ship_y = ship_position
    for _ in range(UFO_SPAWN_ATTEMPTS):
        x = random.uniform(0.0, width)
        y = random.uniform(0.0, height)
        if (torus_distance(x, y, ship_x, ship_y, width, height)
                >= CRAFT_SPAWN_SAFE_DISTANCE):
            return UFO(x, y, random.uniform(0.0, 360.0))
    corner = random.choice(((0, 0), (width, 0), (0, height), (width, height)))
    return UFO(corner[0], corner[1], random.uniform(0.0, 360.0))
