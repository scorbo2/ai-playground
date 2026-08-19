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
    FUEL_BAR_BG,
    FUEL_BAR_FG,
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
    red); the Cannon passes None and shows no bar (spec).

    ``fuel_fraction`` (0..1) is the "Fuel:" progress-bar line - bright
    green on dark green, and ALWAYS the last line of the HUD (spec: Fuel)."""
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
    fuel_fraction: float = 1.0


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
    # Two progress-bar lines exist: the optional "Charge:" bar (its own slot
    # right below "Power:") and the "Fuel:" bar, which is ALWAYS the last
    # line of the HUD (spec: Fuel). Both slots are pre-counted into the y
    # start below so the text stays vertically centered either way.
    bar_lines = (1 if has_charge else 0) + 1
    y = (HUD_HEIGHT - (len(text_lines) + bar_lines) * HUD_LINE_SPACING) // 2
    for index, (text, color) in enumerate(text_lines):
        surface.blit(_fit_render(text, color, available_width),
                     (HUD_TEXT_PADDING, y))
        y += HUD_LINE_SPACING
        # Spec HUD line order: the charge bar gets its OWN line slot,
        # right below "Power:".
        if index == _CHARGE_BAR_AFTER_LINE and has_charge:
            _draw_progress_line(surface, y, "Charge:", data.charge_fraction,
                                data.charge_color, DARK_GRAY, available_width)
            y += HUD_LINE_SPACING
    # The fuel line is ALWAYS last (spec: Fuel), after the game time line.
    _draw_progress_line(surface, y, "Fuel:", data.fuel_fraction,
                        FUEL_BAR_FG, FUEL_BAR_BG, available_width)

    surface.set_alpha(HUD_ALPHA)
    screen.blit(surface, rect.topleft)


def _draw_progress_line(surface: pygame.Surface, y: int, label: str,
                        fraction: float, fill_color, background_color,
                        available_width: int) -> None:
    """One progress-bar line (the HUD's "Charge:" and "Fuel:" lines): white
    label on the left, a bar filled with ``fill_color`` on ``background_color``
    to its right (spec: Laser/Shield/Fuel)."""
    label_surface = _fit_render(label, WHITE, available_width)
    surface.blit(label_surface, (HUD_TEXT_PADDING, y))
    bar_x = HUD_TEXT_PADDING + label_surface.get_width() + 4
    bar_width = max(10, available_width - label_surface.get_width() - 4)
    bar_y = y + (HUD_LINE_SPACING - HUD_CHARGE_BAR_HEIGHT) // 2
    outer = pygame.Rect(bar_x, bar_y, bar_width, HUD_CHARGE_BAR_HEIGHT)
    pygame.draw.rect(surface, background_color, outer)
    fill_width = int(round((outer.width - 2) * max(0.0, min(1.0, fraction))))
    if fill_width > 0:
        pygame.draw.rect(surface, fill_color,
                         (outer.x + 1, outer.y + 1, fill_width,
                          outer.height - 2))
