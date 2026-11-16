"""Cached font handles.

``pygame.font.SysFont`` performs a filesystem font search on every call. The HUD
used to call it roughly eight times per frame (once per rendered label), burning
around 6% of the 16.6ms frame budget on lookups that never change. Fonts are
cached here by size so scenes ask for what they want without paying for it.
"""

from __future__ import annotations

import pygame

_FAMILY = "monospace"
_CACHE: dict[tuple[int, bool], "pygame.font.Font"] = {}


def game_font(size: int, bold: bool = False) -> "pygame.font.Font":
    """Return a cached monospace font of the requested pixel size/weight."""
    key = (size, bold)
    font = _CACHE.get(key)
    if font is None:
        font = pygame.font.SysFont(_FAMILY, size, bold=bold)
        _CACHE[key] = font
    return font


def render_text(
    text: str, size: int, color: tuple[int, int, int], bold: bool = False
) -> "pygame.Surface":
    """Render antialiased text as an alpha surface in display-native format.

    ``Font.render(antialias=True)`` returns an ``SRCALPHA`` surface in which *every*
    pixel - including the fully transparent ones - already carries the text colour;
    coverage lives only in the alpha byte. ``convert()`` therefore does not just
    speed the blit up, it *deletes* the coverage and leaves a solid filled rectangle
    of the text colour where the glyphs should be. ``convert_alpha()`` keeps the
    coverage while still converting to the display format, which is what blits
    correctly onto the (alpha-less) display surface.
    """
    return game_font(size, bold).render(text, True, color).convert_alpha()
