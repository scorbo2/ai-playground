#!/usr/bin/env python3
"""Fortress class for Solar Fortress.

Manages the enemy fortress sprite at screen center, including
sprite state (neutral / charging / firing) and collision radius.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pygame

# Sprite state identifiers
SpriteState = Literal["neutral", "charging", "firing"]


class Fortress:
    """The unmoving enemy fortress at the center of the screen.

    Renders one of three sprite states and re-centers itself
    whenever the display dimensions change.
    """

    def __init__(self, sprite_dir: Path) -> None:
        """Load the three fortress sprites from *sprite_dir*.

        All sprites are loaded at their native size (no scaling).
        """
        self._sprite_dir: Path = sprite_dir
        self._sprites: dict[str, pygame.Surface] = {}
        for state in ("neutral", "charging", "firing"):
            path = sprite_dir / f"enemy_{state}.png"
            surface = pygame.image.load(str(path))
            # Enable per-surface alpha blending so the fortress can
            # fade during its destruction animation (Stage 6+).
            surface = surface.convert_alpha()
            self._sprites[state] = surface

        self.sprite: pygame.Surface = self._sprites["neutral"]
        self._state: SpriteState = "neutral"
        self._width: int = 0
        self._height: int = 0
        self._hit: bool = False
        # Bounding-circle radius for collision detection.
        # Diameter = sprite width per the spec.
        self.radius: float = self.sprite.get_width() / 2

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def center(self) -> tuple[int, int]:
        """Current centre position in display-space pixels."""
        return (self._width // 2, self._height // 2)

    @property
    def state(self) -> SpriteState:
        return self._state

    @state.setter
    def state(self, value: SpriteState) -> None:
        self._state = value
        self.sprite = self._sprites[value]

    @property
    def hit(self) -> bool:
        """True once the fortress has been struck by a player projectile."""
        return self._hit

    @property
    def hit_radius(self) -> float:
        """Bounding-circle radius for collision detection."""
        return self.radius

    def update(self, width: int, height: int) -> None:
        """Re-centre the fortress for the current display size.

        Must be called every frame so the fortress tracks resize
        and fullscreen-toggle events.
        """
        self._width = width
        self._height = height

    def render(self, surface: pygame.Surface) -> None:
        """Draw the current fortress sprite centred on the display."""
        rect = self.sprite.get_rect(center=self.center)
        surface.blit(self.sprite, rect)

    def reset(self) -> None:
        """Restore to neutral state for a new level."""
        self._state = "neutral"
        self.sprite = self._sprites["neutral"]
        self._hit = False
