"""Heads-up display (spec: "Heads-up display"), rendered in Game Mode only.

Everything - rounded cyan border AND text - is composited on one
transparent surface and blitted at alpha 153 (~60%), so the HUD tints
the scene behind it instead of hard-covering it. The HUD is hidden when
the window is too small to fit it (spec: resize handling).
"""

from dataclasses import dataclass

import pygame

from font_manager import get_font
from game_constants import (
    CYAN,
    GREEN,
    HUD_ALPHA,
    HUD_BORDER_WIDTH,
    HUD_CORNER_RADIUS,
    HUD_FONT_SIZE,
    HUD_HEIGHT,
    HUD_LINE_SPACING,
    HUD_MARGIN,
    HUD_MIN_FONT_SIZE,
    HUD_TEXT_PADDING,
    HUD_WIDTH,
    WHITE,
)


@dataclass
class HudData:
    """One frame's worth of HUD values. The weapon's "Charge:" bar line
    lands here in Stage 5 (Laser/Shield); the cannon shows none (spec)."""
    level: int
    shots_fired: int
    hits: int
    hit_rate_text: str
    nickname: str
    weapon_name: str
    weapon_color: tuple
    power_level: int
    sound_on: bool
    game_time_seconds: int


def _format_game_time(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def _fit_render(text: str, color, available_width: int) -> pygame.Surface:
    """Render at HUD_FONT_SIZE, shrinking the size until the line fits
    (spec: font size "scale to fit"). Only the font manager's cache grows,
    and only by fonts actually needed."""
    size = HUD_FONT_SIZE
    font = get_font(size)
    while font.size(text)[0] > available_width and size > HUD_MIN_FONT_SIZE:
        size -= 1
        font = get_font(size)
    return font.render(text, True, color)


def draw_game_hud(screen: pygame.Surface, data: HudData) -> None:
    if (screen.get_width() < HUD_WIDTH + 2 * HUD_MARGIN
            or screen.get_height() < HUD_HEIGHT + 2 * HUD_MARGIN):
        return  # spec: hide the HUD when the window is too small

    rect = pygame.Rect(0, 0, HUD_WIDTH, HUD_HEIGHT)
    rect.right = screen.get_width() - HUD_MARGIN
    rect.top = HUD_MARGIN

    surface = pygame.Surface((HUD_WIDTH, HUD_HEIGHT), pygame.SRCALPHA)
    pygame.draw.rect(surface, CYAN, (0, 0, HUD_WIDTH, HUD_HEIGHT),
                     width=HUD_BORDER_WIDTH, border_radius=HUD_CORNER_RADIUS)

    lines = (
        (f"Level: {data.level}", WHITE),
        (f"Shots fired: {data.shots_fired}", WHITE),
        (f"Hits: {data.hits}", WHITE),
        (f"Hit rate: {data.hit_rate_text}", WHITE),
        (f"Nickname: {data.nickname}", WHITE),
        (f"Weapon: {data.weapon_name}", data.weapon_color),
        (f"Power: {data.power_level}", data.weapon_color),
        (f"Sound: {'On' if data.sound_on else 'Off'}", WHITE),
        (f"Game time: {_format_game_time(data.game_time_seconds)}", GREEN),
    )

    available_width = HUD_WIDTH - 2 * HUD_TEXT_PADDING
    rendered = [_fit_render(text, color, available_width)
                for text, color in lines]
    y = (HUD_HEIGHT - len(rendered) * HUD_LINE_SPACING) // 2
    for text_surface in rendered:
        surface.blit(text_surface, (HUD_TEXT_PADDING, y))
        y += HUD_LINE_SPACING

    surface.set_alpha(HUD_ALPHA)
    screen.blit(surface, rect.topleft)
