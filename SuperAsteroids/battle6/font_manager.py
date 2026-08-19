"""Font helpers for SuperAsteroids.

pygame Font objects are expensive to create, so each font size is created
once and cached here (see the "Code structure" notes in SuperAsteroids2.md).
All text rendering in the game goes through this module.
"""

import pygame

_font_cache: dict = {}

# Line spacing as a multiple of the font size; leaves breathing room for
# ascenders/descenders between stacked lines of text.
_LINE_SPACING_FACTOR = 1.4


def get_font(size: int) -> pygame.font.Font:
    """Return a cached Font for ``size`` pixels, creating it on first use."""
    font = _font_cache.get(size)
    if font is None:
        font = pygame.font.Font(None, size)  # pygame's built-in font
        _font_cache[size] = font
    return font


def render_text(text: str, size: int, color) -> pygame.Surface:
    """Render ``text`` into a new surface using the cached font for ``size``."""
    return get_font(size).render(text, True, color)


def blit_centered(screen: pygame.Surface, surface: pygame.Surface, center) -> None:
    """Blit ``surface`` so it is centered on ``center``."""
    screen.blit(surface, surface.get_rect(center=center))


def draw_centered_lines(screen: pygame.Surface, center_x: int, center_y: int,
                        lines: list) -> None:
    """Render and blit a block of ``(text, size, color)`` lines centered on
    ``(center_x, center_y)``. The whole block is vertically centered, so the
    first line starts above ``center_y`` and the last ends below it."""
    rendered = [(render_text(text, size, color), size) for text, size, color in lines]
    line_heights = [max(surface.get_height(), int(size * _LINE_SPACING_FACTOR))
                    for surface, size in rendered]

    y = center_y - sum(line_heights) // 2
    for (surface, _), line_height in zip(rendered, line_heights):
        screen.blit(surface, (center_x - surface.get_width() // 2, y))
        y += line_height
