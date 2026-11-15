"""HUD, minimap, and landing-prompt helpers for the tactical display (Stage 6).

The right-hand third of the window holds a read-only HUD plus a square minimap;
the left two thirds remain the game view from Stage 4. Geometry and copy are
exposed as *pure functions* first, and — unlike the first Stage 6 revision —
those functions are the code the renderer actually executes, so a passing unit
test means the pixels on screen agree with them.

Styling (background, text/bars, borders) lives in code as a small
:class:`_HudPalette`; see the Stage 6 decision in DECISIONS.md for why this is
not config.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Optional, Sequence

import pygame

from src.fonts import game_font, render_text
from src.model.game_state import GameState

if TYPE_CHECKING:
    from src.scene_manager import SceneManager

SCREEN_SIZE = (1024, 768)
VIEW_WIDTH = 683
# The HUD occupies the right-hand third of a 1024-wide window.
HUD_WIDTH = SCREEN_SIZE[0] - VIEW_WIDTH
HUD_ORIGIN_X = VIEW_WIDTH

# ---------------------------------------------------------------------------
# Layout constants (component coordinates are screen-absolute; the HUD column
# starts at HUD_ORIGIN_X so it can never bleed into the game view).
# ---------------------------------------------------------------------------
BORDER = 2          # border width in px around every HUD component
MINIMAP_SIZE = 240  # minimap is square and fits inside this many px per side
BAR_HEIGHT = 8      # height of a status bar in px
BAR_PADDING_X = 6   # horizontal padding inside a status bar
GAP = 12            # vertical gap between stacked components
LINE_HEIGHT = 30    # height of a single text line (navigation, cargo rows)
NEAREST_RESERVE = 90  # reserved height for the nearest-ship readout block

TEXT_SIZE = 18
BANNER_TEXT_SIZE = 18

# Marker sizes are fixed by the spec: "white 2x2 ship", "green 4x4 planet",
# "red 2x2 enemies", and a "large arrow" when the planet cannot be shown.
SHIP_MARKER_SIZE = 2
PLANET_MARKER_SIZE = 4
ENEMY_MARKER_SIZE = 2
ARROW_SIZE = 22       # "large arrow": obvious next to a 2px ship marker
ARROW_EDGE_INSET = 4  # keep the arrow head off the minimap's own border line


class _HudPalette:
    """Presentation colours for the HUD. Kept in code on purpose."""

    background = (0, 0, 0)
    text = (140, 255, 140)
    text_muted = (120, 160, 120)
    bar_fill = (80, 200, 80)
    bar_track = (60, 90, 60)
    border = (128, 128, 128)
    ship = (255, 255, 255)
    planet = (60, 180, 90)
    enemy = (255, 0, 0)


# ---------------------------------------------------------------------------
# Pure helpers: these ARE the production code paths for status text and geometry.
# ---------------------------------------------------------------------------
def bar_width(available: int) -> int:
    """Inner width available to a status bar within `available` px."""
    return max(0, available - 2 * BAR_PADDING_X)


def status_bar_rect(x: int, y: int, available: int) -> "pygame.Rect":
    """Drawable track rect for a status bar in the box starting at (`x`, `y`)."""
    return pygame.Rect(x + BAR_PADDING_X, y, bar_width(available), BAR_HEIGHT)


def status_row_geometry(row: "pygame.Rect", labels: Sequence[str]) -> tuple[int, "pygame.Rect"]:
    """Return ``(label_x, bar_track)`` shared by every ship-status row.

    Labels share a left edge and bars start after the widest label, so all three
    bars line up. Deriving the geometry once for the whole group (rather than per
    row) is what keeps the bars aligned; the renderer and the tests both call this.
    """
    label_x = row.left + BORDER + BAR_PADDING_X
    font = game_font(TEXT_SIZE)
    widest_label = max((font.size(label)[0] for label in labels), default=0)
    bar_area_x = label_x + widest_label + GAP
    bar_area_width = max(0, row.right - bar_area_x)
    track = status_bar_rect(bar_area_x, row.top + (row.height - BAR_HEIGHT) // 2, bar_area_width)
    return label_x, track


def ship_status_row_rects(status_rect: "pygame.Rect", row_count: int = 3) -> list:
    """Split the ship-status block into its individual bordered rows.

    Exported (and used by the tests) so the renderer and its tests can never
    drift apart on where a bar actually lands.
    """
    return [
        pygame.Rect(status_rect.left, status_rect.top + i * (LINE_HEIGHT + GAP),
                    status_rect.width, LINE_HEIGHT)
        for i in range(row_count)
    ]


def navigation_status_text(is_selected: bool, selected_name: Optional[str]) -> str:
    """One-line navigation status string.

    Reads "No destination" when nothing is selected, otherwise
    "Hyperspace / <system>".
    """
    if not is_selected or not selected_name:
        return "No destination"
    return f"Hyperspace / {selected_name}"


def navigation_is_bold(jumping: bool) -> bool:
    """The nav status text goes bold while a jump is in progress."""
    return jumping


def capacity_text(used: int, capacity: int) -> str:
    """Format a used/capacity pair as ``used/capacity`` (e.g. ``16/50``)."""
    return f"{int(used)}/{int(capacity)}"


def direction_vector(dx: float, dy: float) -> tuple[float, float]:
    """Unit vector pointing from the ship toward a target offset (dx, dy).

    Screen space uses +x right and +y down, so this is also the on-screen
    direction the player should fly. Returns ``(0, 0)`` when the target
    coincides with the ship.
    """
    length = math.hypot(dx, dy)
    if length < 1e-9:
        return (0.0, 0.0)
    return (dx / length, dy / length)


def minimap_scale(minimap_half: float, world_half_extent: float) -> float:
    """Scale factor fitting the whole system into the minimap's half-width."""
    if world_half_extent < 1e-9:
        return 1.0
    return minimap_half / world_half_extent


def is_planet_off_map(
    planet_screen_dx: float, planet_screen_dy: float, minimap_half: float
) -> bool:
    """True when the scaled planet position falls outside the minimap box."""
    return abs(planet_screen_dx) > minimap_half or abs(planet_screen_dy) > minimap_half


def planet_minimap_marker(
    ship_x: float, ship_y: float, scale: float, minimap_half: float,
    planet_position: tuple[float, float] = (0.0, 0.0),
) -> tuple[str, float, float]:
    """Decide how the minimap shows the planet: a marker offset, or an arrow.

    The minimap is player-centred, so an entity's offset from the minimap centre
    is its world offset from the ship, scaled. When the planet is too far away to
    fit alongside the ship, the spec wants a large arrow instead of a marker; the
    returned ``(ux, uy)`` is the unit direction the player must fly.

    Returns ``("marker", offset_x, offset_y)`` or ``("arrow", unit_x, unit_y)``.
    """
    dx, dy = planet_position[0] - ship_x, planet_position[1] - ship_y
    offset_x, offset_y = dx * scale, dy * scale
    if is_planet_off_map(offset_x, offset_y, minimap_half):
        ux, uy = direction_vector(dx, dy)
        return ("arrow", ux, uy)
    return ("marker", offset_x, offset_y)


def planet_arrow_points(
    center: tuple[float, float], radius: float, ux: float, uy: float,
    size: int = ARROW_SIZE,
) -> tuple[tuple[float, float], ...]:
    """Triangle vertices for the "large arrow" pointing along ``(ux, uy)``.

    The head sits just inside the minimap edge, the tail points back toward the
    centre, so the arrow reads as "fly that way" rather than "the planet is
    exactly here" (which would be a lie once it is off-map).
    """
    cx, cy = center
    depth = radius - ARROW_EDGE_INSET
    tip = (cx + ux * depth, cy + uy * depth)
    back = depth - size
    base_x, base_y = cx + ux * back, cy + uy * back
    perp_x, perp_y = -uy, ux
    half_base = size * 0.42
    return (
        tip,
        (base_x + perp_x * half_base, base_y + perp_y * half_base),
        (base_x - perp_x * half_base, base_y - perp_y * half_base),
    )


def landing_prompt_text(distance: float, landing_range: float) -> Optional[str]:
    """Return the landing prompt if `distance` to the planet is within range."""
    if distance <= landing_range:
        return "Press L to land here"
    return None


def hud_layout(available_width: int) -> dict[str, "pygame.Rect"]:
    """Local-coordinate rects for every HUD component.

    Pure and layout-testable: the gate asserts these fit inside `available_width`
    (341 px) with no overlaps. The ship-status block is a single rect that the
    scene subdivides into three bars when drawing.
    """
    bars_y = BORDER + MINIMAP_SIZE + GAP
    # Each status row is LINE_HEIGHT tall and separated by GAP; the block spans
    # exactly the three rows it draws (no trailing gap, which would otherwise
    # report phantom space to the overlap check).
    status_height = 3 * LINE_HEIGHT + 2 * GAP
    nav_y = bars_y + status_height + GAP
    nearest_y = nav_y + LINE_HEIGHT + GAP
    cargo_y = nearest_y + NEAREST_RESERVE + GAP
    return {
        "minimap": pygame.Rect(BORDER, BORDER, MINIMAP_SIZE, MINIMAP_SIZE),
        "ship_status": pygame.Rect(BORDER, bars_y, available_width, status_height),
        "navigation": pygame.Rect(BORDER, nav_y, available_width, LINE_HEIGHT),
        "nearest_ship": pygame.Rect(BORDER, nearest_y, available_width, NEAREST_RESERVE),
        "cargo_and_credits": pygame.Rect(BORDER, cargo_y, available_width, 3 * LINE_HEIGHT),
    }


def to_screen_layout(layout: dict[str, "pygame.Rect"]) -> dict[str, "pygame.Rect"]:
    """Offset local HUD coordinates onto the screen (right-hand third)."""
    return {
        name: pygame.Rect(rect.left + HUD_ORIGIN_X, rect.top, rect.width, rect.height)
        for name, rect in layout.items()
    }


# ---------------------------------------------------------------------------
# HudView scene (a component of GameScene, never a scene-stack entry)
# ---------------------------------------------------------------------------
class HudView:
    """Read-only HUD + minimap occupying the right-hand third of the screen.

    The HUD is drawn *by* :class:`~src.scenes.game_scene.GameScene` rather than
    pushed onto the scene stack: it owns no input, and a passive scene on top of
    the stack would swallow every event and freeze the simulation (the Stage 6
    review bug).

    It renders straight from the *same* :class:`GameState` the tactical view
    simulates. Constructing a second GameState here — as the first Stage 6
    revision did — gives the HUD a phantom ship whose fuel and position never
    change.

    Fields that no stage has implemented yet are explicit seams, each documented
    with the stage that fills it: ``enemies`` (Stage 10), ``nearest_ship``
    (Stage 11), ``nav_selected_name``/``is_jumping`` (Stages 7/8), and
    ``credits``/``cargo_used``/``passengers_used`` (Stage 9). Capacities are read
    from the ship stats, which do exist.
    """

    def __init__(self, manager: "SceneManager", game_state: GameState) -> None:
        if game_state is None:
            raise ValueError("HudView requires the GameState the tactical view simulates")
        self._manager = manager
        self.game_state = game_state
        self._rects = to_screen_layout(hud_layout(HUD_WIDTH - 2 * BORDER))
        self._hud_rect = pygame.Rect(HUD_ORIGIN_X, 0, HUD_WIDTH, SCREEN_SIZE[1])

        # Hostile contacts in world coordinates (Stage 10 populates these).
        self.enemies: list[tuple[float, float]] = []
        self.nearest_ship: Optional[object] = None
        self.nav_selected_name: Optional[str] = None
        self.is_jumping: bool = False
        self.credits: float = 0.0
        self.cargo_used: int = 0
        self.passengers_used: int = 0

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self, surface: "pygame.Surface") -> None:
        """Render every HUD component onto `surface`.

        The column is filled with the background colour first: nothing else in
        the game clears the right-hand third (TacticalView deliberately clears
        only the game view), so without this the difficulty dialog's panel and
        the title background stay burnt into the HUD forever, and every changed
        value ghosts over its previous pixels.
        """
        surface.fill(_HudPalette.background, self._hud_rect)
        self._draw_minimap(surface)
        self._draw_ship_status(surface)
        self._draw_navigation(surface)
        self._draw_nearest_ship(surface)
        self._draw_cargo_and_credits(surface)

    # -- minimap -------------------------------------------------------
    def _draw_minimap(self, surface: "pygame.Surface") -> None:
        """Draw the square, player-centred minimap.

        The player is always a white 2x2 at the centre; the planet is a green 4x4
        offset from that centre, or a large arrow when it is too far away to fit.
        """
        rect = self._rects["minimap"]
        self._panel(surface, rect)
        center = (rect.left + rect.width / 2.0, rect.top + rect.height / 2.0)
        half = rect.width / 2.0
        scale = minimap_scale(half, self.game_state.system_pixel_size / 2.0)
        ship_x, ship_y = self.game_state.position

        kind, a, b = planet_minimap_marker(ship_x, ship_y, scale, half)
        if kind == "marker":
            self._marker(surface, center, (a, b), PLANET_MARKER_SIZE, _HudPalette.planet)
        else:
            pygame.draw.polygon(
                surface, _HudPalette.planet, planet_arrow_points(center, half, a, b)
            )

        for enemy_x, enemy_y in self.enemies:
            offset = ((enemy_x - ship_x) * scale, (enemy_y - ship_y) * scale)
            if not is_planet_off_map(offset[0], offset[1], half):
                self._marker(surface, center, offset, ENEMY_MARKER_SIZE, _HudPalette.enemy)

        # The player sits on top of everything else on the minimap.
        self._marker(surface, center, (0.0, 0.0), SHIP_MARKER_SIZE, _HudPalette.ship)

    def _marker(
        self, surface: "pygame.Surface", center, offset, size: int, color: tuple[int, int, int]
    ) -> None:
        """Blit a small square marker offset from the minimap centre."""
        x = int(round(center[0] + offset[0])) - size // 2
        y = int(round(center[1] + offset[1])) - size // 2
        pygame.draw.rect(surface, color, pygame.Rect(x, y, size, size))

    # -- ship status bars ---------------------------------------------
    def _draw_ship_status(self, surface: "pygame.Surface") -> None:
        """Shield/armor/fuel bars: a label and a bar per row, never a number."""
        rect = self._rects["ship_status"]
        rows = (
            ("shield", self.game_state.stats.shields, self.game_state.stats.max_shields),
            ("armor", self.game_state.stats.armor, self.game_state.stats.max_armor),
            ("fuel", self.game_state.fuel, self.game_state.stats.fuel_capacity),
        )
        labels = [label for label, _, _ in rows]

        # One border box per row, cleared before drawing so a shrinking bar
        # cannot leave its previous fill behind.
        row_rects = ship_status_row_rects(rect, len(rows))
        for row in row_rects:
            self._panel(surface, row)

        for i, (label, value, capacity) in enumerate(rows):
            row = row_rects[i]
            # Geometry is derived per row: the horizontal layout is identical for
            # every row, but each bar must sit inside its own bordered box.
            label_x, track = status_row_geometry(row, labels)
            surface.blit(
                render_text(label, TEXT_SIZE, _HudPalette.text),
                (label_x, row.top + (row.height - TEXT_SIZE) // 2),
            )
            pygame.draw.rect(surface, _HudPalette.bar_track, track, 1)
            ratio = value / capacity if capacity else 0.0
            fill_width = int(track.width * max(0.0, min(1.0, ratio)))
            if fill_width > 0:
                pygame.draw.rect(
                    surface, _HudPalette.bar_fill,
                    pygame.Rect(track.left, track.top, fill_width, track.height),
                )

    # -- navigation status --------------------------------------------
    def _draw_navigation(self, surface: "pygame.Surface") -> None:
        rect = self._rects["navigation"]
        self._panel(surface, rect)
        selected = bool(self.nav_selected_name)
        text = navigation_status_text(selected, self.nav_selected_name)
        bold = navigation_is_bold(self.is_jumping)
        colour = _HudPalette.text if bold else _HudPalette.text_muted
        label = render_text(text, TEXT_SIZE, colour, bold=bold)
        surface.blit(
            label,
            (rect.left + BORDER + BAR_PADDING_X, rect.top + (rect.height - label.get_height()) // 2),
        )

    # -- nearest ship readout -----------------------------------------
    def _draw_nearest_ship(self, surface: "pygame.Surface") -> None:
        rect = self._rects["nearest_ship"]
        self._panel(surface, rect)
        # Stage 11 replaces this with the scanned ship's alignment + bars.
        text = "No target" if self.nearest_ship is None else str(self.nearest_ship)
        label = render_text(text, TEXT_SIZE, _HudPalette.text)
        surface.blit(label, (rect.left + BORDER + BAR_PADDING_X, rect.top + GAP))

    # -- cargo / passengers / credits ---------------------------------
    def _draw_cargo_and_credits(self, surface: "pygame.Surface") -> None:
        rect = self._rects["cargo_and_credits"]
        stats = self.game_state.stats
        lines = [
            f"Cargo: {capacity_text(self.cargo_used, stats.cargo_room)}",
            f"Passengers: {capacity_text(self.passengers_used, stats.passenger_space)}",
            f"Credits: {int(self.credits)}",
        ]
        for i, line in enumerate(lines):
            row = pygame.Rect(rect.left, rect.top + i * LINE_HEIGHT, rect.width, LINE_HEIGHT)
            self._panel(surface, row)
            surface.blit(
                render_text(line, TEXT_SIZE, _HudPalette.text),
                (row.left + BORDER + BAR_PADDING_X, row.top + (row.height - TEXT_SIZE) // 2),
            )

    # -- shared -------------------------------------------------------
    def _panel(self, surface: "pygame.Surface", rect: "pygame.Rect") -> None:
        """Clear a component's box and draw its 2px gray border.

        Clearing is not optional: the HUD redraws in place every frame, so any
        pixel an earlier frame painted and the current frame does not would stay
        on screen forever.
        """
        surface.fill(_HudPalette.background, rect)
        # Rect.right/bottom are exclusive; pygame.draw.line would otherwise draw
        # the border one pixel outside the box we just cleared.
        outer = (rect.right - 1, rect.bottom - 1)
        corners = (rect.topleft, (outer[0], rect.top), outer, (rect.left, outer[1]))
        for start, end in zip(corners, corners[1:] + corners[:1]):
            pygame.draw.line(surface, _HudPalette.border, start, end, BORDER)
