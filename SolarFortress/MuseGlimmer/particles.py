#!/usr/bin/env python3
"""
particles.py - generic particle effects for Solar Fortress.

Provides simple fading circular particles used for explosions.
"""

from __future__ import annotations

import math
import random
import pygame


class Particle:
    """A simple fading circular particle."""

    def __init__(
        self,
        x: float,
        y: float,
        radius_range: tuple[int, int],
        speed_range: tuple[float, float],
        alpha_decay_range: tuple[float, float],
        color: tuple[int, int, int] | None = None,
        color_choices: list[tuple[int, int, int]] | None = None,
    ) -> None:
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(speed_range[0], speed_range[1])
        self.x = float(x)
        self.y = float(y)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.radius = random.randint(radius_range[0], radius_range[1])
        if color_choices:
            self.color = random.choice(color_choices)
        else:
            self.color = color if color else (255, 255, 255)
        self.alpha = 255
        self.alpha_decay = random.uniform(alpha_decay_range[0], alpha_decay_range[1])
        self.alive = True

    def update(self) -> None:
        self.x += self.vx
        self.y += self.vy
        self.alpha = max(0, self.alpha * (1 - self.alpha_decay))
        if self.alpha <= 0:
            self.alive = False

    def draw(self, surface: pygame.Surface) -> None:
        if not self.alive or self.alpha <= 0:
            return
        temp = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(
            temp,
            (*self.color, int(self.alpha)),
            (self.radius, self.radius),
            self.radius,
        )
        surface.blit(temp, (int(self.x - self.radius), int(self.y - self.radius)))


def create_missile_explosion(x: float, y: float) -> list[Particle]:
    """Create 100 white particles for homing missile destruction."""
    particles = []
    for _ in range(100):
        p = Particle(
            x,
            y,
            radius_range=(4, 8),
            speed_range=(5, 15),
            alpha_decay_range=(0.04, 0.08),
            color=(255, 255, 255),
        )
        particles.append(p)
    return particles


def create_fortress_explosion(x: float, y: float) -> list[Particle]:
    """Create 120 particles for fortress destruction (colors yellow/red/orange)."""
    # Colors chosen from spec
    color_choices = [(255, 255, 0), (255, 0, 0), (255, 165, 0)]
    particles = []
    for _ in range(120):
        p = Particle(
            x,
            y,
            radius_range=(6, 12),
            speed_range=(5, 15),
            alpha_decay_range=(0.02, 0.06),
            color_choices=color_choices,
        )
        particles.append(p)
    return particles
