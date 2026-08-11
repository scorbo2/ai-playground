#!/usr/bin/env python3
"""
Fortress — the unmoving enemy stronghold at the center of the screen.

For Stage 2 we only render the neutral sprite. The charging/firing
states and explosion logic are deferred to later stages when projectiles
and destruction are introduced.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pygame
import pygame.locals as pgl

logger = logging.getLogger("solar_fortress.fortress")


class Fortress:
    """The stationary enemy fortress rendered at the screen center.

    The fortress never moves; its sprite is re-centred every frame based
    on the current display dimensions. This naturally handles both window
    resize events and fullscreen toggles without special-case code.
    """

    def __init__(self, source_dir: Path) -> None:
        """Load the fortress sprite(s).

        Parameters
        ----------
        source_dir :
            Directory containing the fortress PNG assets.
        """
        sprite_path = source_dir / "enemy_neutral.png"
        try:
            self._sprite: pygame.Surface = pygame.image.load(str(sprite_path)).convert_alpha()
        except pygame.error as exc:
            logger.error("Failed to load fortress sprite %s: %s", sprite_path, exc)
            # Fallback so the game doesn't crash: draw a red rectangle
            self._sprite = pygame.Surface((64, 64))
            self._sprite.fill((200, 0, 0))

        # The sprite is rendered at its native size, never scaled.
        self._rect: pygame.Rect = self._sprite.get_rect()

    @property
    def center(self) -> tuple[int, int]:
        """Current fortress center position."""
        return self._rect.center

    @center.setter
    def center(self, value: tuple[int, int]) -> None:
        """Update fortress center (called every frame from the game loop)."""
        self._rect.center = value

    def render(self, surface: pygame.Surface) -> None:
        """Blit the fortress sprite onto *surface*."""
        surface.blit(self._sprite, self._rect)
