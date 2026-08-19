"""Starfield background (spec: "Starfield background").

A subtle field of 150-300 single-pixel grayscale stars, shown in ALL modes.
The stars do not move; each one's brightness oscillates between 0 and 192,
changing by 0.1% of max brightness per frame and reversing direction at each
end of the range. A star's initial brightness and direction are random, so
the sky twinkles out of phase instead of pulsing in lockstep.

The field is regenerated (not patched) whenever the window resizes - the
spec explicitly allows full regeneration to cover newly exposed areas.
"""

import random

import pygame

from game_constants import (
    STAR_BRIGHTNESS_RATE,
    STAR_COUNT_RANGE,
    STAR_MAX_BRIGHTNESS,
)

# Per-frame brightness change: 0.1% of the max, in either direction.
_STAR_STEP = STAR_MAX_BRIGHTNESS * STAR_BRIGHTNESS_RATE


class _Star:
    """One pixel of sky. Small enough to be a tuple, structured enough to
    read as a noun."""

    __slots__ = ("x", "y", "brightness", "rising")

    def __init__(self, width: int, height: int):
        self.x = random.uniform(0.0, width)
        self.y = random.uniform(0.0, height)
        # Random phase within the cycle: a field where every star started
        # at brightness 0 would light up in one flat wave.
        self.brightness = random.uniform(0.0, STAR_MAX_BRIGHTNESS)
        self.rising = random.random() < 0.5


class Starfield:
    """Owns the star list and advances/draws it. Re-created by the app on
    every resize or full-screen toggle; otherwise stateless."""

    def __init__(self, width: int, height: int):
        count = random.randint(*STAR_COUNT_RANGE)
        self._stars = [_Star(width, height) for _ in range(count)]

    def update(self) -> None:
        """Advance every star one frame within its brightness cycle."""
        for star in self._stars:
            brightness = star.brightness + _STAR_STEP if star.rising \
                else star.brightness - _STAR_STEP
            if brightness >= STAR_MAX_BRIGHTNESS:
                brightness = STAR_MAX_BRIGHTNESS
                star.rising = False
            elif brightness <= 0.0:
                brightness = 0.0
                star.rising = True
            star.brightness = brightness

    def draw(self, screen: pygame.Surface) -> None:
        """One pixel per star, always grayscale (all components equal)."""
        for star in self._stars:
            value = int(round(star.brightness))
            color = (value, value, value)
            screen.fill(color, (int(star.x), int(star.y), 1, 1))
