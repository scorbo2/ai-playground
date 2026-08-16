"""Particle effects: explosion debris and thruster exhaust.

Per the spec (Asteroids / Enemy UFOs / Thrusters), particles are PURELY
cosmetic: no collision detection, no screen wrap (at 5-15 px/frame they
fade to invisible within a couple of seconds, so wrapping is unnecessary
cost). Every particle starts fully opaque and loses a random 3-10% of its
REMAINING alpha each frame (thruster puffs: 3-6%) until invisible, at which
point it is removed from play.

The alpha decay is multiplicative on purpose: "gradually ... until they are
invisible" reads as a tapering fade, and it guarantees no particle ever
lingers at a faint but visible glow.
"""

import math
import random
from typing import Dict

import pygame

from game_constants import (
    LIGHT_RED,
    PARTICLE_ALPHA_DECAY_RANGE,
    PARTICLE_COUNT_PER_RADIUS,
    PARTICLE_SIZE,
    PARTICLE_SPEED_RANGE,
    PLAYER_SHAPE_HEIGHT,
    SPLIT_PARTICLE_COLORS,
    THRUSTER_BACK_SPEED_RANGE,
    THRUSTER_COLORS,
    THRUSTER_ALPHA_DECAY_RANGE,
    THRUSTER_PUFFS_PER_FRAME_RANGE,
    THRUSTER_PUFF_RADIUS_RANGE,
    UFO_PARTICLE_COUNT,
    WRECKAGE_BRIGHTNESS_RANGE,
)

# Opaque glyph surfaces, cached per (kind, size, color): allocating a small
# surface per particle per frame would churn the allocator for nothing.
_glyphs: Dict[tuple, pygame.Surface] = {}


def _square_glyph(color: tuple) -> pygame.Surface:
    key = ("square", PARTICLE_SIZE, color)
    glyph = _glyphs.get(key)
    if glyph is None:
        glyph = pygame.Surface((PARTICLE_SIZE, PARTICLE_SIZE), pygame.SRCALPHA)
        glyph.fill(color)
        _glyphs[key] = glyph
    return glyph


def _circle_glyph(radius: int, color: tuple) -> pygame.Surface:
    key = ("circle", radius, color)
    glyph = _glyphs.get(key)
    if glyph is None:
        size = radius * 2 + 1  # odd so the circle sits on an exact center
        glyph = pygame.Surface((size, size), pygame.SRCALPHA)
        pygame.draw.circle(glyph, color, (radius, radius), radius)
        _glyphs[key] = glyph
    return glyph


class Particle:
    """One fading dot of light. ``update()`` returns False on the frame the
    particle has faded out, so a list of particles advances with a single
    filter: ``[p for p in particles if p.update()]``."""

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 color: tuple, decay_fraction: float):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.color = color
        self.alpha = 255.0
        self.decay_fraction = decay_fraction

    def update(self) -> bool:
        """Advance one frame; True while the particle is still visible."""
        self.x += self.vx
        self.y += self.vy
        self.alpha *= 1.0 - self.decay_fraction
        return self.alpha >= 1.0

    def draw(self, screen: pygame.Surface) -> None:
        glyph = self.glyph()
        glyph.set_alpha(int(self.alpha))
        screen.blit(glyph, glyph.get_rect(
            center=(int(round(self.x)), int(round(self.y)))))

    def glyph(self) -> pygame.Surface:
        """The cached opaque shape this particle fades with. Subclasses
        choose the shape (debris squares, exhaust circles)."""
        raise NotImplementedError


class ExplosionParticle(Particle):
    """A PARTICLE_SIZE square of debris from an asteroid or UFO going boom."""

    def glyph(self) -> pygame.Surface:
        return _square_glyph(self.color)


class ThrusterPuff(Particle):
    """A solid exhaust circle, radius 3-8 px, ejected from the craft's base."""

    def __init__(self, x: float, y: float, vx: float, vy: float,
                 color: tuple, decay_fraction: float, radius: int):
        super().__init__(x, y, vx, vy, color, decay_fraction)
        self.radius = radius

    def glyph(self) -> pygame.Surface:
        return _circle_glyph(self.radius, self.color)


# ------------------------------------------------------------------ factories

def _random_explosion_velocity() -> tuple:
    angle = random.uniform(0.0, 2.0 * math.pi)
    speed = random.uniform(*PARTICLE_SPEED_RANGE)
    return (math.cos(angle) * speed, math.sin(angle) * speed)


def _explosion_particle(x: float, y: float, color: tuple) -> ExplosionParticle:
    vx, vy = _random_explosion_velocity()
    return ExplosionParticle(
        x=x,
        y=y,
        vx=vx,
        vy=vy,
        color=color,
        decay_fraction=random.uniform(*PARTICLE_ALPHA_DECAY_RANGE),
    )


def spawn_split_explosion(x: float, y: float, radius: float) -> list:
    """An asteroid SPLIT: colorful debris, one random color (bright yellow,
    red, or orange) per particle, count = radius * 3 (spec: 40 -> 120)."""
    return [_explosion_particle(x, y, random.choice(SPLIT_PARTICLE_COLORS))
            for _ in range(int(radius * PARTICLE_COUNT_PER_RADIUS))]


def spawn_destruction_explosion(x: float, y: float, radius: float) -> list:
    """An asteroid DESTROYED with no further split (too small to break, or
    a level-3 laser/shield): monochrome debris, each particle's grayscale
    level drawn independently from 128 (mid-gray) to 255 (white)."""
    particles = []
    for _ in range(int(radius * PARTICLE_COUNT_PER_RADIUS)):
        brightness = random.randint(*WRECKAGE_BRIGHTNESS_RANGE)
        particles.append(_explosion_particle(x, y,
                                             (brightness, brightness, brightness)))
    return particles


def spawn_ufo_explosion(x: float, y: float) -> list:
    """A UFO destroyed: a flat 100 light red particles (spec: Enemy UFOs)."""
    return [_explosion_particle(x, y, LIGHT_RED)
            for _ in range(UFO_PARTICLE_COUNT)]


def spawn_thruster_puffs(craft) -> list:
    """One thrusting frame of exhaust (spec: Thrusters): a random 2-3
    circles at the craft's BASE (half its height aft of center), each with
    the craft's velocity plus a random 6-10 px/frame kick BACKWARDS along
    the craft's facing direction (no lateral spread - the spec gives none)."""
    angle = math.radians(craft.angle)
    back_x, back_y = -math.cos(angle), -math.sin(angle)   # "backwards"
    base_offset = PLAYER_SHAPE_HEIGHT / 2
    puffs = []
    for _ in range(random.randint(*THRUSTER_PUFFS_PER_FRAME_RANGE)):
        back_speed = random.uniform(*THRUSTER_BACK_SPEED_RANGE)
        puffs.append(ThrusterPuff(
            x=craft.x + back_x * base_offset,
            y=craft.y + back_y * base_offset,
            vx=craft.vx + back_x * back_speed,
            vy=craft.vy + back_y * back_speed,
            color=random.choice(THRUSTER_COLORS),
            decay_fraction=random.uniform(*THRUSTER_ALPHA_DECAY_RANGE),
            radius=random.randint(*THRUSTER_PUFF_RADIUS_RANGE),
        ))
    return puffs
