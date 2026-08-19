"""Heads-up display (spec: "Heads-up display"), rendered in Game Mode only.

Everything - rounded cyan border AND text - is composited on one
transparent surface and blitted at alpha 153 (~60%), so the HUD tints
the scene behind it instead of hard-covering it. The HUD is hidden when
the window is too small to fit it (spec: resize handling).
"""

from dataclasses import dataclass
from typing import Optional

import pygame

from font_manager import get_font
from game_constants import (
    CYAN,
    DARK_GRAY,
    GREEN,
    HUD_ALPHA,
    HUD_BORDER_WIDTH,
    HUD_CHARGE_BAR_HEIGHT,
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
    """One frame's worth of HUD values.

    ``charge_fraction`` (0..1) and ``charge_color`` select the "Charge:"
    progress-bar line for the charged weapons (Laser light blue, Shield
    red); the Cannon passes None and shows no bar (spec)."""
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
    charge_fraction: Optional[float] = None
    charge_color: Optional[tuple] = None


def _format_game_time(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


# Index of the "Power:" line in text_lines; the charge bar goes right after.
_CHARGE_BAR_AFTER_LINE = 6


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

    text_lines = (
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
    has_charge = data.charge_fraction is not None
    y = (HUD_HEIGHT - (len(text_lines) + (1 if has_charge else 0))
         * HUD_LINE_SPACING) // 2
    for index, (text, color) in enumerate(text_lines):
        surface.blit(_fit_render(text, color, available_width),
                     (HUD_TEXT_PADDING, y))
        y += HUD_LINE_SPACING
        # Spec HUD line order: the charge bar gets its OWN line slot,
        # right below "Power:". (The extra slot is already accounted for
        # in the y starting position above.)
        if index == _CHARGE_BAR_AFTER_LINE and has_charge:
            _draw_charge_bar(surface, y, data.charge_fraction,
                             data.charge_color, available_width)
            y += HUD_LINE_SPACING

    surface.set_alpha(HUD_ALPHA)
    screen.blit(surface, rect.topleft)


def _draw_charge_bar(surface: pygame.Surface, y: int, fraction: float,
                     color, available_width: int) -> None:
    """The 'Charge:' line for charged weapons (spec: Laser/Shield): white
    label over a progress bar, bar fill in the weapon's color on dark gray."""
    label = _fit_render("Charge:", WHITE, available_width)
    surface.blit(label, (HUD_TEXT_PADDING, y))
    bar_x = HUD_TEXT_PADDING + label.get_width() + 4
    bar_width = max(10, available_width - label.get_width() - 4)
    bar_y = y + (HUD_LINE_SPACING - HUD_CHARGE_BAR_HEIGHT) // 2
    outer = pygame.Rect(bar_x, bar_y, bar_width, HUD_CHARGE_BAR_HEIGHT)
    pygame.draw.rect(surface, DARK_GRAY, outer)
    fill_width = int(round((outer.width - 2) * max(0.0, min(1.0, fraction))))
    if fill_width > 0:
        pygame.draw.rect(surface, color,
                         (outer.x + 1, outer.y + 1, fill_width,
                          outer.height - 2))
