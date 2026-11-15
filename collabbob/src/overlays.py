"""Transient banner messages drawn over the tactical game view.

The spec repeatedly asks for messages to be "briefly overlaid" on the tactical
display: "System boundary reached", "insufficient fuel", bounty payouts, and the
persistent "Press L to land here" prompt. Stage 6 shipped the landing prompt as
a unit-tested pure function that no scene ever called, so this is the seam that
actually puts text on screen.

Callers own their own repeat policy (e.g. the boundary message's "at most once
every five seconds" cooldown is a Stage 8 concern); this module only decides how
long a banner stays up and where it sits.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

import pygame

from src.fonts import render_text

BANNER_SIZE = 20
_BANNER_COLOR = (255, 240, 150)
_SHADE = (0, 0, 0)
_SHADE_ALPHA = 170
_PAD_X = 8
_PAD_Y = 4
_LINE_GAP = 6


@dataclass
class _Banner:
    """A transient message with a frame budget."""

    text: str
    frames_left: int

    def tick(self) -> bool:
        """Consume one frame; True while the banner is still alive."""
        self.frames_left -= 1
        return self.frames_left > 0


class MessageOverlay:
    """Stack of text banners anchored near the top of a screen region.

    Sticky text (the landing prompt) always occupies the first row while it is
    set; transient banners queue beneath it and expire on their frame budget.
    Re-showing a text that is already on screen refreshes its timer instead of
    stacking duplicates.
    """

    def __init__(self, region: "pygame.Rect") -> None:
        self._region = region
        self._sticky: Optional[str] = None
        self._banners: List[_Banner] = []

    def set_sticky(self, text: Optional[str]) -> None:
        """Show `text` on every frame until cleared (None)."""
        self._sticky = text

    def show(self, text: str, duration_frames: int = 180) -> None:
        """Overlay `text` for `duration_frames` simulation frames (3s at 60FPS)."""
        if not text:
            return
        for banner in self._banners:
            if banner.text == text:
                banner.frames_left = duration_frames
                return
        self._banners.append(_Banner(text, max(1, int(duration_frames))))

    def update(self) -> None:
        """Advance banner timers by one frame."""
        self._banners = [b for b in self._banners if b.tick()]

    def active_messages(self) -> List[str]:
        """The messages currently on screen, top to bottom (testable view)."""
        messages = []
        if self._sticky:
            messages.append(self._sticky)
        messages.extend(banner.text for banner in self._banners)
        return messages

    def draw(self, surface: "pygame.Surface") -> None:
        """Draw every active banner, centred horizontally in the region."""
        y = self._region.top + _PAD_Y
        for text in self.active_messages():
            y = self._draw_banner(surface, text, y)

    def _draw_banner(self, surface: "pygame.Surface", text: str, y: int) -> int:
        """Blit one banner at `y`; return the y coordinate for the next row."""
        label = render_text(text, BANNER_SIZE, _BANNER_COLOR)
        center_x = self._region.left + self._region.width // 2
        rect = label.get_rect(center=(center_x, y + label.get_height() // 2))

        shade = pygame.Surface((label.get_width() + 2 * _PAD_X, label.get_height() + 2 * _PAD_Y),
                               pygame.SRCALPHA)
        shade.fill((*_SHADE, _SHADE_ALPHA))
        surface.blit(shade, (rect.left - _PAD_X, rect.top - _PAD_Y))
        surface.blit(label, rect)
        return rect.bottom + _LINE_GAP
