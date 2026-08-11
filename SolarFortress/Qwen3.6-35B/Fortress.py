#!/usr/bin/env python3
"""
Fortress - the enemy stronghold, rendered as a sprite centred on screen.

Stage 2: renders the neutral sprite only.  Charging/firing/explosion
states are introduced in later stages.
"""

from __future__ import annotations

import pygame
from pathlib import Path


class Fortress:
    """The unmoving enemy fortress at the centre of the screen.

    Attributes
    ----------
    sprite : pygame.Surface
        The currently-displayed fortress image (neutral, charging, or firing).
    rect : pygame.Rect
        Bounding rectangle, centred on the screen.  Updated every frame
        so the fortress stays centred during resize/fullscreen toggles.
    """

    def __init__(self, source_dir: Path) -> None:
        """Load the fortress sprite sheets.

        Parameters
        ----------
        source_dir:
            Directory to resolve sprite paths against (typically ``__file__``'s
            parent directory).
        """
        self._neutral = self._load_sprite(source_dir, "enemy_neutral.png")
        self._charging = self._load_sprite(source_dir, "enemy_charging.png")
        self._firing = self._load_sprite(source_dir, "enemy_firing.png")

        # Current state — defaults to neutral for stage 2.
        self.sprite: pygame.Surface = self._neutral
        self.rect: pygame.Rect = pygame.Rect(0, 0, *self._neutral.get_size())

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(self, surface: pygame.Surface, center_x: int, center_y: int) -> None:
        """Draw the fortress centred on the screen.

        Parameters
        ----------
        surface:
            Target display surface.
        center_x, center_y:
            Screen coordinates of the fortress centre.
        """
        self.rect.center = (center_x, center_y)
        surface.blit(self.sprite, self.rect)

    # ------------------------------------------------------------------
    # State management (for later stages)
    # ------------------------------------------------------------------

    def set_state(self, state: str) -> None:
        """Switch the fortress sprite to the given display state.

        recognised values: ``"neutral"``, ``"charging"``, ``"firing"``.
        Any unknown value falls back to neutral — this is a no-op
        during stage 2 but allows future stages to swap sprites.

        Parameters
        ----------
        state:
            One of the recognised state strings.
        """
        sprites = {
            "neutral": self._neutral,
            "charging": self._charging,
            "firing": self._firing,
        }
        self.sprite = sprites.get(state, self._neutral)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _load_sprite(source_dir: Path, filename: str) -> pygame.Surface:
        """Load a sprite image and convert it for blitting.

        Parameters
        ----------
        source_dir:
            Directory to resolve the path against.
        filename:
            Sprite file name.

        Returns
        -------
        pygame.Surface
            The loaded sprite, optimised for blitting.
        """
        path = source_dir / filename
        try:
            return pygame.image.load(str(path)).convert_alpha()
        except (pygame.error, FileNotFoundError) as exc:
            # Return a tiny transparent surface as a no-op fallback
            # so the game doesn't crash if a sprite is missing.
            return pygame.Surface((1, 1), pygame.SRCALPHA)
