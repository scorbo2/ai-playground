#!/usr/bin/env python3
"""
Fortress - enemy stronghold for Solar Fortress.

Handles loading of fortress sprites and rendering at screen center.
Stage 2 implementation: neutral sprite only, centered on resize/fullscreen.
"""

from __future__ import annotations

import math
import random
import pygame
from pathlib import Path


class _ExplosionParticle:
    """Simple particle for fortress explosion."""

    def __init__(self, x: float, y: float) -> None:
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(5, 15)
        self.x = float(x)
        self.y = float(y)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.radius = random.randint(6, 12)
        # Colors: bright yellow, red, orange
        color_choice = random.choice([(255, 255, 0), (255, 0, 0), (255, 165, 0)])
        self.color = color_choice
        self.alpha = 255
        # Alpha decay between 2% and 6% per frame
        self.alpha_decay = random.uniform(0.02, 0.06)

    def update(self) -> None:
        self.x += self.vx
        self.y += self.vy
        self.alpha = max(0, self.alpha * (1 - self.alpha_decay))

    def draw(self, surface: pygame.Surface) -> None:
        if self.alpha <= 0:
            return
        # Create temporary surface for alpha blending
        temp = pygame.Surface((self.radius * 2, self.radius * 2), pygame.SRCALPHA)
        pygame.draw.circle(
            temp,
            (*self.color, int(self.alpha)),
            (self.radius, self.radius),
            self.radius,
        )
        surface.blit(temp, (int(self.x - self.radius), int(self.y - self.radius)))


class Fortress:
    """Enemy fortress that stays centered on screen.

    Stage 5 adds charging/firing animation sequence.
    Stage 6 adds explosion on destruction.
    """

    def __init__(self, neutral_path: Path | str, charging_path: Path | str, firing_path: Path | str) -> None:
        """Load fortress sprites.

        Parameters
        ----------
        neutral_path:
            Path to enemy_neutral.png.
        charging_path:
            Path to enemy_charging.png.
        firing_path:
            Path to enemy_firing.png.
        """
        self.neutral_image = pygame.image.load(str(neutral_path)).convert_alpha()
        self.charging_image = pygame.image.load(str(charging_path)).convert_alpha()
        self.firing_image = pygame.image.load(str(firing_path)).convert_alpha()

        # All sprites share the same rect size (assume same dimensions)
        self.rect = self.neutral_image.get_rect()
        self.center: tuple[int, int] = (0, 0)

        # Animation state
        self.state: str = "neutral"  # neutral, charging, firing, exploding
        self.charge_timer: int = 0
        self.fire_timer: int = 0
        self.current_image: pygame.Surface = self.neutral_image

        # Explosion state
        self.exploding: bool = False
        self.sprite_alpha: int = 255
        self.particles: list[_ExplosionParticle] = []
        self.explosion_finished: bool = False

    def start_firing_sequence(self) -> None:
        """Begin charging/firing animation if currently neutral."""
        if self.state == "neutral":
            self.state = "charging"
            self.charge_timer = 60  # 1 second at 60fps

    def start_explosion(self) -> None:
        """Begin fortress destruction explosion."""
        if self.state == "exploding":
            return
        self.state = "exploding"
        self.exploding = True
        self.sprite_alpha = 255
        self.explosion_finished = False
        cx, cy = self.rect.center
        self.particles = [_ExplosionParticle(cx, cy) for _ in range(120)]

    def update(self, screen_width: int, screen_height: int) -> bool:
        """Re-center fortress and advance firing animation.

        Returns
        -------
        bool
            True if a projectile should be spawned this frame (transition
            from charging to firing).
        """
        self.center = (screen_width // 2, screen_height // 2)
        self.rect.center = self.center

        spawn_projectile = False

        if self.state == "exploding":
            # Update explosion particles
            for p in self.particles:
                p.update()
            # Reduce sprite alpha by 1% per frame
            self.sprite_alpha = max(0, int(self.sprite_alpha * 0.99))
            if self.sprite_alpha == 0 and not self.explosion_finished:
                self.explosion_finished = True
            # Keep current image for drawing with alpha
            self.current_image = self.neutral_image
            return False

        if self.state == "charging":
            self.charge_timer -= 1
            self.current_image = self.charging_image
            if self.charge_timer <= 0:
                self.state = "firing"
                self.fire_timer = 30
                spawn_projectile = True
        elif self.state == "firing":
            self.fire_timer -= 1
            self.current_image = self.firing_image
            if self.fire_timer <= 0:
                self.state = "neutral"
                self.current_image = self.neutral_image
        else:  # neutral
            self.current_image = self.neutral_image

        return spawn_projectile

    def draw(self, surface: pygame.Surface) -> None:
        """Blit current fortress sprite centered on screen, with explosion effects."""
        if self.state == "exploding":
            # Draw explosion particles first
            for p in self.particles:
                p.draw(surface)
            # Draw sprite with reduced alpha
            if self.sprite_alpha > 0:
                temp = self.current_image.copy()
                temp.set_alpha(self.sprite_alpha)
                surface.blit(temp, self.rect)
            return

        surface.blit(self.current_image, self.rect)

    def is_exploding(self) -> bool:
        """Return True while fortress explosion is in progress."""
        return self.state == "exploding"

    def is_explosion_finished(self) -> bool:
        """Return True when sprite is invisible and explosion has completed."""
        return self.explosion_finished
