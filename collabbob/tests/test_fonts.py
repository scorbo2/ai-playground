"""Text rendering tests (src/fonts.py).

These exist because of a nasty visual bug: pygame's ``Font.render(antialias=True)``
returns an SRCALPHA surface in which *every* pixel already carries the text colour
and coverage lives only in the alpha byte. Calling ``convert()`` on that surface
drops the alpha byte, so the glyph bounding box blits as a solid filled rectangle
of the text colour - "text" that is an unreadable block. The suite stayed green
because nothing checked that the space *between* glyphs stayed the background
colour.
"""

import pygame
import pytest

from src.fonts import game_font, render_text

_TEXT_COLOR = (140, 255, 140)
_BACKGROUND = (12, 34, 56)


def _blit_on_background(text, size=18, bold=False):
    """Blit rendered text onto a solid background; return (surface, rect)."""
    surface = pygame.Surface((400, 120))
    surface.fill(_BACKGROUND)
    label = render_text(text, size, _TEXT_COLOR, bold=bold)
    rect = label.get_rect(center=surface.get_rect().center)
    surface.blit(label, rect)
    return surface, rect


def test_render_text_keeps_the_bounding_box_transparent_between_glyphs():
    """Text must not blit as a solid rectangle of the text colour.

    GIVEN a surface filled with a known background colour
    WHEN antialiased text is blitted onto it
    THEN most of the text's bounding box is still the background colour, and the
    box corners in particular are untouched.
    """
    surface, rect = _blit_on_background("Cargo: 3/20")

    corners = [
        rect.topleft,
        (rect.right - 1, rect.top),
        (rect.left, rect.bottom - 1),
        (rect.right - 1, rect.bottom - 1),
    ]
    for point in corners:
        assert surface.get_at(point)[:3] == _BACKGROUND, (
            f"corner {point} was overwritten: text blitted as a solid block"
        )

    untouched = sum(
        1
        for y in range(rect.top, rect.bottom)
        for x in range(rect.left, rect.right)
        if surface.get_at((x, y))[:3] == _BACKGROUND
    )
    ratio = untouched / (rect.width * rect.height)
    assert ratio > 0.4, (
        f"only {ratio:.0%} of the text box survived as background; expected the "
        "glyph strokes to cover a minority of the box"
    )


def test_render_text_glyph_strokes_reach_the_requested_colour():
    """At least some pixels land at the exact requested colour (not washed out)."""
    surface, rect = _blit_on_background("Fuel", size=24)

    exact = sum(
        1
        for y in range(rect.top, rect.bottom)
        for x in range(rect.left, rect.right)
        if surface.get_at((x, y))[:3] == _TEXT_COLOR
    )
    assert exact > 0, "no pixel reached the requested text colour"


def test_render_text_does_not_leave_the_dialog_background_showing_through():
    """Antialiased edges must blend, not stamp a coloured slab.

    The block bug made 100% of the box the exact text colour. Here the count of
    exactly-text-coloured pixels must stay a small minority of the box.
    """
    surface, rect = _blit_on_background("Press L to land here", size=20)

    exact = sum(
        1
        for y in range(rect.top, rect.bottom)
        for x in range(rect.left, rect.right)
        if surface.get_at((x, y))[:3] == _TEXT_COLOR
    )
    ratio = exact / (rect.width * rect.height)
    assert ratio < 0.5, f"{ratio:.0%} of the text box is solid text colour"


def test_game_font_returns_the_same_cached_font_for_identical_requests():
    """Font handles are cached: a construction per label per frame is far too slow."""
    assert game_font(18) is game_font(18)


@pytest.mark.parametrize("size,bold", [(18, False), (18, True), (20, False)])
def test_game_font_caches_separately_per_size_and_weight(size, bold):
    """Size and weight are part of the cache key, never silently reused."""
    assert isinstance(game_font(size, bold), pygame.font.Font)
    assert game_font(size, bold) is game_font(size, bold)
    if bold:
        assert game_font(size, bold) is not game_font(size, False)
