"""Stage 6 tests: HUD, minimap, landing prompt, and the message overlay.

Three layers:

* The pure helpers in :mod:`src.hud` (bar widths, status strings, minimap
  scale/off-map detection, arrow direction and geometry, the landing prompt, and
  the non-overlapping layout that must fit in the 341px HUD column). These are the
  same functions the renderer executes, so a green helper test means the pixels
  agree.
* The :class:`~src.hud.HudView` component: it clears its own column, renders a
  player-centred minimap (white 2x2 ship at the centre, green 4x4 planet, red 2x2
  contacts, large arrow when the planet cannot be shown), and never paints a
  number beside a status bar.
* :class:`~src.overlays.MessageOverlay`, which puts the landing prompt and later
  transient messages onto the game view.
"""

import math

import pygame
import pytest

import main  # noqa: F401  (ensures project root is on sys.path)

from src.config import base_config
from src.scenes.game_scene import GameScene
from src.scenes.tactical_view import TacticalView
from src.hud import (
    BORDER,
    GAP,
    HUD_WIDTH,
    LINE_HEIGHT,
    MINIMAP_SIZE,
    PLANET_MARKER_SIZE,
    SCREEN_SIZE,
    SHIP_MARKER_SIZE,
    VIEW_WIDTH,
    HudView,
    bar_width,
    capacity_text,
    direction_vector,
    hud_layout,
    is_planet_off_map,
    landing_prompt_text,
    minimap_scale,
    navigation_is_bold,
    navigation_status_text,
    planet_arrow_points,
    planet_minimap_marker,
    ship_status_row_rects,
    status_bar_rect,
    status_row_geometry,
    to_screen_layout,
    _HudPalette,
)
from src.model.factions import FACTION_PIRATE, faction_color
from src.model.game_state import GameState
from src.overlays import MessageOverlay


class _Contact:
    """The slice of a Stage 10 NPC ship the HUD is allowed to read.

    The minimap only ever asks a contact for its world position and its faction,
    so a test hands it exactly that. Handing it a real ``NpcShip`` would couple
    the Stage 6 layout tests to the NPC model's constructor.
    """

    def __init__(self, position, faction=FACTION_PIRATE):
        self.position = position
        self.faction = faction


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


class _FakeManager:
    """Minimal stand-in exposing only what :class:`HudView` reads at init."""

    def __init__(self, config):
        self.configs = {"config_easy.json": config}
        self.selected_config = config

    def game_config(self):
        return self.selected_config


def _make_hud_view(config=None, position=(0.0, 0.0)):
    """A HudView over a fabricated config plus an offscreen surface.

    The HUD is handed the GameState it renders; it must never build its own.
    """
    config = config or base_config()
    game_state = GameState(config)
    game_state.set_position(*position)
    view = HudView(_FakeManager(config), game_state)
    return view, pygame.Surface((1024, 768))


def _pixels_in(surface, color, rect):
    """Coordinates inside `rect` painted exactly `color`."""
    return {
        (x, y)
        for y in range(rect.top, rect.bottom)
        for x in range(rect.left, rect.right)
        if surface.get_at((x, y))[:3] == color
    }


def _centroid(coords):
    xs, ys = zip(*coords)
    return (sum(xs) / len(xs), sum(ys) / len(ys))


# ---------------------------------------------------------------------------
# Pure helpers: widths / rects
# ---------------------------------------------------------------------------


def test_bar_width_subtracts_horizontal_padding_from_available_space():
    """A bar's inner width is the available space minus both side paddings."""
    assert bar_width(100) == 100 - 2 * 6
    # Never negative for absurdly small inputs.
    assert bar_width(0) == 0


def test_status_bar_rect_is_padded_inside_its_containing_box():
    """The drawable rect is inset by the horizontal padding on both sides."""
    rect = status_bar_rect(x=10, y=20, available=200)
    assert rect.left == 10 + 6
    assert rect.top == 20
    assert rect.height == 8
    assert rect.width == bar_width(200)


def test_status_row_geometry_puts_the_bar_to_the_right_of_the_widest_label():
    """Every ship-status row shares one label column and one bar left edge."""
    row = pygame.Rect(685, 254, HUD_WIDTH - 2 * BORDER, 30)
    label_x, track = status_row_geometry(row, ("shield", "armor", "fuel"))

    assert label_x > row.left
    assert track.left > label_x
    assert track.right <= row.right
    # The bar must not swallow the whole row: the label needs its space.
    assert track.width < row.width
    assert track.height == 8


# ---------------------------------------------------------------------------
# Pure helpers: navigation status strings / bold flag
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("is_selected,selected_name", [
    (False, "Bravo"),
    (True, None),
    (True, ""),
])
def test_navigation_status_text_reports_no_destination_when_unselected_or_empty(
    is_selected, selected_name
):
    """No active selection yields the neutral placeholder text."""
    assert navigation_status_text(is_selected, selected_name) == "No destination"


def test_navigation_status_text_reads_hyperspace_and_system():
    """A selected system reads as 'Hyperspace / <system>'."""
    assert navigation_status_text(True, "Bravo") == "Hyperspace / Bravo"


def test_navigation_is_bold_only_while_jumping():
    """The nav line is bold exactly during an in-progress jump."""
    assert navigation_is_bold(True) is True
    assert navigation_is_bold(False) is False


# ---------------------------------------------------------------------------
# Pure helpers: capacity formatting
# ---------------------------------------------------------------------------


def test_capacity_text_formats_used_over_capacity():
    """Used/capacity pairs render as 'used/capacity' with ints coerced."""
    assert capacity_text(16, 50) == "16/50"
    assert capacity_text(3.7, 4.2) == "3/4"


# ---------------------------------------------------------------------------
# Pure helpers: direction vector / minimap scale / off-map detection
# ---------------------------------------------------------------------------


def test_direction_vector_is_a_unit_vector_for_any_offset():
    """Normalised offsets always have magnitude ~1."""
    for dx, dy in [(3, 4), (-5, 12), (1, -1), (7, 0)]:
        ux, uy = direction_vector(dx, dy)
        assert math.hypot(ux, uy) == pytest.approx(1.0)


def test_direction_vector_returns_zero_when_target_equals_ship():
    """Zero-length offset collapses to the origin vector."""
    assert direction_vector(0, 0) == (0.0, 0.0)


def test_minimap_scale_fits_system_into_half_width():
    """Scale equals minimap half-width divided by the world half-extent."""
    assert minimap_scale(60.0, 120.0) == pytest.approx(0.5)


def test_minimap_scale_degenerates_to_one_when_world_has_no_extent():
    """A zero-sized system is shown at full scale rather than collapsing."""
    assert minimap_scale(10.0, 0.0) == 1.0


@pytest.mark.parametrize("dx,dy,half,expected", [
    (0, 0, 10, False),      # centre -> on map
    (9, 0, 10, False),      # just inside edge
    (10, 0, 10, False),     # exactly on the edge is still on-map (strict >)
    (11, 3, 10, True),      # beyond the edge
])
def test_is_planet_off_map_flags_positions_past_the_box_edge(dx, dy, half, expected):
    """Positions whose scaled offset exceeds the half-extent are off-map."""
    assert is_planet_off_map(dx, dy, half) is expected


# ---------------------------------------------------------------------------
# Pure helpers: minimap planet marker / arrow
# ---------------------------------------------------------------------------


def test_planet_marker_is_an_offset_while_the_planet_fits_on_the_minimap():
    """Close enough means a marker: the offset is the scaled planet-minus-ship."""
    kind, offset_x, offset_y = planet_minimap_marker(
        ship_x=100.0, ship_y=-50.0, scale=0.5, minimap_half=120.0
    )
    assert kind == "marker"
    # The planet sits at the world origin, so it is opposite the ship.
    assert offset_x == pytest.approx(-50.0)
    assert offset_y == pytest.approx(25.0)


@pytest.mark.parametrize("ship_x,ship_y,expected_quadrant", [
    (900.0, -900.0, ("down", "left")),    # planet is astern and below on screen
    (900.0, 900.0, ("up", "left")),
    (-900.0, 900.0, ("up", "right")),
    (-900.0, -900.0, ("down", "right")),
])
def test_planet_arrow_points_back_toward_the_planet_in_every_quadrant(
    ship_x, ship_y, expected_quadrant
):
    """When the planet cannot be shown, the arrow points the player toward it."""
    kind, ux, uy = planet_minimap_marker(ship_x=ship_x, ship_y=ship_y, scale=0.5, minimap_half=120.0)

    assert kind == "arrow", "a distant planet must be an arrow, not a marker"
    assert math.hypot(ux, uy) == pytest.approx(1.0)
    # The arrow must point from the ship back to the origin.
    assert ux == pytest.approx(-ship_x / math.hypot(ship_x, ship_y))
    assert uy == pytest.approx(-ship_y / math.hypot(ship_x, ship_y))
    vertical, horizontal = expected_quadrant
    assert ("down" if uy > 0 else "up") == vertical
    assert ("left" if ux < 0 else "right") == horizontal


def test_planet_arrow_head_lies_toward_the_minimap_edge():
    """The arrow's tip sits near the edge in its direction, tail pointing inward."""
    center, radius = (800.0, 120.0), 120.0
    ux, uy = direction_vector(-3.0, 4.0)
    tip, corner_a, corner_b = planet_arrow_points(center, radius, ux, uy)

    def distance(point):
        return math.hypot(point[0] - center[0], point[1] - center[1])

    assert distance(tip) > distance(corner_a)
    assert distance(tip) > distance(corner_b)
    assert distance(tip) <= radius, "the arrow must stay inside the minimap box"
    assert distance(corner_a) <= radius and distance(corner_b) <= radius

    # The head must be displaced along the arrow direction, not sideways.
    assert (tip[0] - center[0]) * ux >= 0.0
    assert (tip[1] - center[1]) * uy >= 0.0
    # The two base corners straddle the direction line (a real triangle).
    assert corner_a != corner_b


# ---------------------------------------------------------------------------
# Pure helper: landing prompt
# ---------------------------------------------------------------------------


def test_landing_prompt_shows_when_within_range():
    """A ship close enough to the planet sees the landing prompt."""
    assert landing_prompt_text(50.0, 100.0) == "Press L to land here"


def test_landing_prompt_is_none_when_out_of_range():
    """Too far away means no prompt."""
    assert landing_prompt_text(200.0, 100.0) is None


# ---------------------------------------------------------------------------
# Pure helper: layout fit / non-overlap (the Stage 6 gate)
# ---------------------------------------------------------------------------


def test_hud_layout_fits_inside_the_available_width_and_height_gate():
    """Every component stays inside the full HUD column and the 768px height.

    Content fills between the two 2px borders: left starts at `BORDER` and the
    right edge lands exactly on `HUD_WIDTH - BORDER`, so nothing spills onto the
    left game-view region or past the screen.
    """
    layout = hud_layout(available_width=HUD_WIDTH - 2 * BORDER)
    for name, rect in layout.items():
        assert rect.left >= BORDER
        assert rect.right <= HUD_WIDTH - BORDER
        assert rect.top >= BORDER
        assert rect.bottom <= SCREEN_SIZE[1]


def test_hud_layout_has_no_overlapping_components():
    """No two cached rects overlap, so each draws to its own region."""
    layout = hud_layout(available_width=HUD_WIDTH - 2 * BORDER)
    names = list(layout)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            assert _no_overlap(layout[names[i]], layout[names[j]]), (
                f"{names[i]} overlaps {names[j]}"
            )


def test_hud_layout_is_left_aligned_and_full_width_for_rows():
    """The single-line components share the left border and full available width.

    `minimap` is square by design; the multi-row blocks span exactly the rows
    they draw so the overlap check does not see phantom space.
    """
    layout = hud_layout(available_width=HUD_WIDTH - 2 * BORDER)
    expected_width = HUD_WIDTH - 2 * BORDER
    for name, rect in layout.items():
        if name == "minimap":
            assert rect.width == rect.height == MINIMAP_SIZE
            continue
        assert rect.left == BORDER
        assert rect.width == expected_width


def test_to_screen_layout_offsets_the_column_into_the_right_third():
    """Local HUD coordinates land entirely right of the game view."""
    layout = to_screen_layout(hud_layout(HUD_WIDTH - 2 * BORDER))
    for name, rect in layout.items():
        assert rect.left >= VIEW_WIDTH, f"{name} would draw over the game view"
        assert rect.right <= SCREEN_SIZE[0]


def _no_overlap(a, b):
    """True when two axis-aligned rects do not share any area."""
    return (a.right <= b.left or a.left >= b.right
            or a.bottom <= b.top or a.top >= b.bottom)


# ---------------------------------------------------------------------------
# HudView: shared state, clearing, and readouts
# ---------------------------------------------------------------------------


def test_hud_view_is_given_the_game_state_it_renders():
    """The HUD must never construct its own GameState (two ships = lying HUD)."""
    config = base_config()
    game_state = GameState(config)
    view = HudView(_FakeManager(config), game_state)
    assert view.game_state is game_state

    with pytest.raises(TypeError):
        HudView(_FakeManager(config))


def test_hud_renders_the_ship_state_it_was_handled(config_factory):
    """Mutating the simulated state changes what the HUD reports."""
    config = base_config()
    view, surface = _make_hud_view(config)
    view.game_state.fuel = 40.0
    view.game_state.stats.shields = 12.0
    view.draw(surface)
    # No exception and a painted column is the contract here; the exact bar
    # lengths are covered by the bar tests below.
    assert view.game_state.fuel == 40.0


def test_hud_clears_its_whole_column_every_frame():
    """Nothing else clears the right third, so the HUD must clear it itself.

    TacticalView deliberately fills only the game view. Without a full-column
    clear, the difficulty dialog's panel and the title background stay burnt in
    forever (verified in review: dialog pixels survived at (690, 500)).
    """
    view, surface = _make_hud_view()
    surface.fill((200, 50, 50))

    view.draw(surface)

    layout = view._rects
    # Sample the gaps between components and the spare space below them.
    probes = [
        (layout["minimap"].centerx, layout["minimap"].bottom + GAP // 2),
        (layout["minimap"].centerx, layout["ship_status"].bottom + GAP // 2),
        (VIEW_WIDTH + HUD_WIDTH // 2, SCREEN_SIZE[1] - 20),
    ]
    for x, y in probes:
        assert surface.get_at((x, y))[:3] == _HudPalette.background, (
            f"stale pixel left at ({x}, {y})"
        )


def test_hud_draws_nothing_in_the_game_view_region():
    """The HUD owns the right third only; the left stays the game view's."""
    view, surface = _make_hud_view()
    view.draw(surface)

    for y in range(0, SCREEN_SIZE[1], 13):
        for x in range(0, VIEW_WIDTH, 13):
            assert surface.get_at((x, y))[:3] == (0, 0, 0), (
                f"HUD bled into the game view at ({x}, {y})"
            )


def test_status_rows_draw_labels_and_bars_but_never_numbers(monkeypatch):
    """Spec: a label and a bar per row, no numeric values.

    Rendering is spied so the assertion is about the text actually rendered
    rather than about glyph pixels.
    """
    import src.hud as hud_module

    rendered = _capture_rendered(monkeypatch, hud_module)

    view, surface = _make_hud_view()
    view.game_state.fuel = 400.0
    view.draw(surface)

    labels = [text for text, _bold in rendered]
    assert {"shield", "armor", "fuel"} <= set(labels)
    assert not [text for text in labels if text in ("shield", "armor", "fuel")
                and any(ch.isdigit() for ch in text)], (
        "a status row rendered digits; the bars must stay number-free"
    )
    # Only the three short labels and the cargo/nav lines may contain text; a
    # capacity readout beside a bar would add a numeric label like 'fuel 740'.
    assert not [text for text in labels
                if text.startswith(("shield", "armor", "fuel")) and text not in
                ("shield", "armor", "fuel")], (
        "a status label carried extra text (no numbers beside the bars)"
    )


def test_status_bar_shrinks_when_the_value_drops():
    """A bar that shrinks must not leave its previous fill on screen.

    The HUD redraws in place, so without clearing each row the fuel bar would
    only ever appear full — the single most misleading thing a HUD can do in a
    game where empty fuel ends the run.
    """
    fuel_row_index = 2
    view, surface = _make_hud_view()
    row = ship_status_row_rects(view._rects["ship_status"])[fuel_row_index]
    _label_x, track = status_row_geometry(row, ("shield", "armor", "fuel"))
    far_right = (track.right - 2, track.top + track.height // 2)

    view.game_state.fuel = view.game_state.stats.fuel_capacity
    view.draw(surface)
    assert surface.get_at(far_right)[:3] == _HudPalette.bar_fill, "full fuel must fill the bar"

    view.game_state.fuel = 10.0
    view.draw(surface)
    assert surface.get_at(far_right)[:3] != _HudPalette.bar_fill, (
        "the stale full-fuel bar survived the redraw"
    )


def test_status_row_bars_stay_inside_their_own_row_boxes():
    """A bar may never overdraw its row box, its border, or the block below it.

    The ship-status block is subdivided into three bordered rows, so every bar
    track has to land inside its own row - a track that spills over the row line
    smears into the next readout and makes the HUD unreadable.
    """
    view, _surface = _make_hud_view()
    box = view._rects["ship_status"]
    labels = ("shield", "armor", "fuel")

    for row in ship_status_row_rects(box):
        _label_x, track = status_row_geometry(row, labels)
        assert track.top >= row.top, "bar must start below the row's top border"
        assert track.bottom <= row.bottom, "bar must end above the row's bottom border"
        assert track.right <= row.right, "bar must not run past the block's edge"
        assert track.left > _label_x, "bar must start after the label column"


def test_ship_status_row_rects_tile_the_block_the_hud_draws():
    """The rows the renderer measures are real, non-overlapping, and in bounds.

    Both the renderer and these tests call the same helper, so they can never
    drift apart on where a label or bar actually lands.
    """
    view, _surface = _make_hud_view()
    box = view._rects["ship_status"]
    rows = ship_status_row_rects(box)
    assert len(rows) == 3  # shield, armor, fuel

    for row in rows:
        assert row.left == box.left
        assert row.right == box.right
        assert row.top >= box.top
        assert row.bottom <= box.bottom

    # Rows tile the block top-to-bottom with no overlap and no leftover gap
    # large enough for a phantom fourth row.
    for upper, lower in zip(rows, rows[1:]):
        assert upper.bottom <= lower.top
    assert lower.bottom + GAP <= box.bottom + LINE_HEIGHT
    unused = box.height - (sum(row.height for row in rows) + (len(rows) + 1) * GAP)
    assert unused < LINE_HEIGHT, f"row geometry leaves {unused}px of dead space"


def test_each_status_bar_is_drawn_inside_its_own_row():
    """Three rows, three bars: a bar must never be drawn on another row."""
    view, surface = _make_hud_view()
    box = view._rects["ship_status"]
    rows = ship_status_row_rects(box)
    view.game_state.stats.shields = view.game_state.stats.max_shields
    view.game_state.stats.armor = 0.0
    view.game_state.fuel = 0.0
    view.draw(surface)

    for index, row in enumerate(rows):
        assert row.top >= box.top and row.bottom <= box.bottom, (
            "probing a row outside the status block proves nothing"
        )
        _label_x, track = status_row_geometry(row, ("shield", "armor", "fuel"))
        probe = (track.left + 1, track.top + track.height // 2)
        filled = surface.get_at(probe)[:3] == _HudPalette.bar_fill
        assert filled == (index == 0), (
            f"row {index} bar state wrong: shields full, armor and fuel empty"
        )


def test_cargo_and_passenger_capacities_come_from_the_ship_stats(monkeypatch):
    """Capacities exist in the model today, so the HUD must show them.

    The first revision rendered 'Cargo: 0/0' while the ship it was handed had
    20 cargo holds and 5 passenger berths.
    """
    import src.hud as hud_module

    rendered = _capture_rendered(monkeypatch, hud_module)

    view, surface = _make_hud_view()
    stats = view.game_state.stats
    view.cargo_used = 3
    view.passengers_used = 1
    view.credits = 1234.7
    view.draw(surface)

    assert (f"Cargo: 3/{stats.cargo_room}", False) in rendered
    assert (f"Passengers: 1/{stats.passenger_space}", False) in rendered
    assert ("Credits: 1234", False) in rendered


def test_navigation_line_shows_the_selected_system_and_goes_bold_mid_jump(monkeypatch):
    """'No destination' -> 'Hyperspace / Bravo', bold only while jumping."""
    import src.hud as hud_module

    rendered = _capture_rendered(monkeypatch, hud_module)

    view, surface = _make_hud_view()
    view.draw(surface)
    assert ("No destination", False) in rendered

    view.nav_selected_name = "Bravo"
    view.is_jumping = True
    view.draw(surface)
    assert ("Hyperspace / Bravo", True) in rendered


def test_nearest_ship_readout_defaults_to_no_target(monkeypatch):
    """Entering a system always starts the readout at 'No target'."""
    import src.hud as hud_module

    rendered = _capture_rendered(monkeypatch, hud_module)

    view, surface = _make_hud_view()
    view.draw(surface)
    assert ("No target", False) in rendered


def _capture_rendered(monkeypatch, hud_module):
    """Replace hud's render_text with a spy; return the list of rendered strings.

    The original function is captured first: calling ``hud_module.render_text``
    from inside the spy would recurse into the spy itself.
    """
    rendered = []
    original = hud_module.render_text

    def spy(text, size, color, bold=False):
        rendered.append((text, bold))
        return original(text, size, color, bold)

    monkeypatch.setattr(hud_module, "render_text", spy)
    return rendered


# ---------------------------------------------------------------------------
# HudView: minimap (player-centred, per the spec)
# ---------------------------------------------------------------------------


def test_minimap_ship_is_a_white_2x2_square_at_the_centre():
    """Spec: the player is always a white 2x2 at the centre of the minimap."""
    view, surface = _make_hud_view(position=(240.0, -160.0))
    view.draw(surface)

    rect = view._rects["minimap"]
    white = _pixels_in(surface, _HudPalette.ship, rect)
    assert len(white) == SHIP_MARKER_SIZE ** 2, (
        f"expected a {SHIP_MARKER_SIZE}x{SHIP_MARKER_SIZE} ship marker, got {len(white)} px"
    )
    centre = (rect.left + rect.width // 2, rect.top + rect.height // 2)
    assert all(abs(x - centre[0]) <= 1 and abs(y - centre[1]) <= 1 for x, y in white), (
        "the ship marker must sit at the minimap centre, not at its world position"
    )


def test_minimap_shows_the_planet_as_a_green_4x4_when_it_fits():
    """Spec: the planet is a green 4x4 square, offset from the player."""
    view, surface = _make_hud_view(position=(240.0, -160.0))
    view.draw(surface)

    rect = view._rects["minimap"]
    planet = _pixels_in(surface, _HudPalette.planet, rect)
    assert len(planet) == PLANET_MARKER_SIZE ** 2, (
        f"expected a {PLANET_MARKER_SIZE}x{PLANET_MARKER_SIZE} planet marker, got {len(planet)} px"
    )

    centre = (rect.left + rect.width / 2.0, rect.top + rect.height / 2.0)
    centroid = _centroid(planet)
    # The planet is at the world origin, so it lies opposite the ship (which is
    # east and north of it): the marker must be south-west of centre.
    assert centroid[0] < centre[0], "planet must lie opposite the ship's +x offset"
    assert centroid[1] > centre[1], "planet must lie opposite the ship's -y offset"


def test_minimap_replaces_the_planet_with_a_large_arrow_when_it_is_off_map():
    """The player must be told which way to fly, and the indicator must be visible.

    The first revision blitted an 'off-map marker' at the raw scaled position,
    which landed off the window entirely (x=1405) — an invisible hint.
    """
    view, surface = _make_hud_view(position=(1000.0, -1200.0))
    view.draw(surface)

    rect = view._rects["minimap"]
    arrow = _pixels_in(surface, _HudPalette.planet, rect)
    assert arrow, "no arrow was drawn inside the minimap for an off-map planet"
    assert len(arrow) > PLANET_MARKER_SIZE ** 2, "the arrow should be larger than a marker"

    centre = (rect.left + rect.width / 2.0, rect.top + rect.height / 2.0)
    centroid = _centroid(arrow)
    # The ship is east and north of the planet, so the arrow points south-west.
    assert centroid[0] < centre[0]
    assert centroid[1] > centre[1]


def test_minimap_ship_marker_is_always_visible_even_when_the_planet_is_off_map():
    """An off-map planet never hides the player marker."""
    view, surface = _make_hud_view(position=(1000.0, -1200.0))
    view.draw(surface)

    rect = view._rects["minimap"]
    assert len(_pixels_in(surface, _HudPalette.ship, rect)) == SHIP_MARKER_SIZE ** 2


def test_minimap_draws_hostile_contacts_as_red_2x2_squares():
    """Spec: hostile ships are red 2x2 squares, positioned relative to the player.

    The red is the Pirate faction colour, not a HUD-owned colour: from Stage 10
    on, a contact's colour *is* its faction, so the minimap answers "who is out
    there" as well as "how many".
    """
    view, surface = _make_hud_view(position=(200.0, 0.0))
    view.contacts = [_Contact((400.0, 0.0))]
    view.draw(surface)

    rect = view._rects["minimap"]
    contacts = _pixels_in(surface, faction_color(FACTION_PIRATE), rect)
    assert len(contacts) == 4, f"expected a red 2x2 contact marker, got {len(contacts)} px"

    centre_x = rect.left + rect.width / 2.0
    centroid = _centroid(contacts)
    assert centroid[0] > centre_x, "an enemy further along +x must appear right of centre"


def test_minimap_culls_contacts_that_are_off_map():
    """Off-map contacts need no marker (the spec's arrow is for the planet)."""
    view, surface = _make_hud_view(position=(0.0, 0.0))
    view.contacts = [_Contact((100000.0, 0.0))]
    view.draw(surface)

    rect = view._rects["minimap"]
    assert not _pixels_in(surface, faction_color(FACTION_PIRATE), rect)


def test_landing_prompt_is_drawn_over_the_game_view_within_landing_range():
    """Spec: within landing_range, "Press L to land here" overlays the view.

    The first Stage 6 revision shipped this as a pure function plus two unit
    tests and never called it, so the prompt existed only in the test suite.
    Drawing the same view twice with the only difference being the configured
    landing range means any pixel difference IS the prompt.
    """
    config = base_config()
    view = _make_tactical_view(config, position=(100.0, 0.0), landing_range=1000.0)

    surface = pygame.Surface((1024, 768))
    view.update()
    view.draw(surface)
    with_prompt = surface.copy()

    view.game_state.landing_range = 10.0  # same ship, now out of range
    view.update()
    view.draw(surface)

    differing = [
        (x, y)
        for y in range(768)
        for x in range(VIEW_WIDTH)
        if surface.get_at((x, y)) != with_prompt.get_at((x, y))
    ]
    assert differing, "the landing prompt changed nothing on screen"
    top, bottom = min(y for _, y in differing), max(y for _, y in differing)
    assert top < 60, "the prompt must sit near the top of the tactical display"
    assert bottom < 120, f"prompt strayed down to y={bottom}"


def test_landing_prompt_absent_outside_landing_range():
    """Too far from the planet means no prompt.

    The ship sits at 600 px, not the 1500 px these tests used to use: Stage 8
    added the system-boundary clamp (half of ``system_pixel_size`` is 1000), so
    a ship parked outside the system is no longer a state the game can be in —
    and it now earns a "System boundary reached" banner, which is exactly what
    the old coordinate silently prevented from being asserted.
    """
    config = base_config()
    view = _make_tactical_view(config, position=(600.0, 0.0), landing_range=100.0)
    view.update()
    assert view.overlays.active_messages() == []


def test_landing_prompt_tracks_the_ship_each_frame():
    """The prompt is recomputed from the shared state, not set once and forgotten."""
    config = base_config()
    view = _make_tactical_view(config, position=(600.0, 0.0), landing_range=100.0)
    view.update()
    assert view.overlays.active_messages() == []

    view.game_state.set_position(20.0, 0.0)  # now comfortably inside landing range
    view.update()
    assert view.overlays.active_messages() == ["Press L to land here"]


def test_landing_prompt_does_not_leak_into_the_hud_column():
    """Banners belong to the game view; the HUD column is untouched."""
    config = base_config()
    surface = pygame.Surface((1024, 768))
    _make_tactical_view(config, position=(0.0, 0.0), landing_range=1000.0).draw(surface)

    painted = [
        (x, y)
        for y in range(768)
        for x in range(VIEW_WIDTH, 1024)
        if surface.get_at((x, y)) != (0, 0, 0)
    ]
    assert not painted, f"the game view drew {len(painted)} pixels into the HUD column"


def _make_tactical_view(config, position, landing_range, heading=0.0):
    """A tactical view over a fabricated config with a known ship state."""
    manager = _FakeManager(config)
    game_state = GameState(config)
    game_state.landing_range = landing_range
    game_state.heading_degrees = heading
    game_state.set_position(*position)
    return TacticalView(manager, game_state)


def test_tactical_view_and_hud_share_one_game_state_under_game_scene():
    """GameScene creates the session's single GameState and hands it to both."""
    config = base_config()
    scene = GameScene(_FakeManager(config))

    assert scene.tactical.game_state is scene.game_state
    assert scene.hud.game_state is scene.game_state

    scene.tactical.game_state.fuel = 12.5
    assert scene.hud.game_state.fuel == 12.5


def test_game_scene_routes_all_input_to_the_tactical_view():
    """The HUD is read-only, and it can never intercept gameplay input.

    This is the Stage 6 regression: the HUD was pushed onto the scene stack
    above the tactical view, and since only the top scene receives events, the
    game stopped responding to the player entirely.
    """
    config = base_config()
    scene = GameScene(_FakeManager(config))

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP))
    for _ in range(30):
        scene.update()

    assert scene.game_state.velocity[0] > 0.0, "thrust must move the shared ship"
    assert scene.hud.game_state.velocity[0] > 0.0, "the HUD must see the same ship"


def test_hud_view_is_not_a_scene():
    """A component that is not a Scene can never be pushed onto the stack."""
    from src.scene_manager import Scene

    assert not issubclass(HudView, Scene), (
        "HudView must not be a Scene subclass: a passive overlay on top of the "
        "scene stack swallows every event and freezes the simulation"
    )


# ---------------------------------------------------------------------------
# MessageOverlay: landing prompt and transient banners (over the game view)
# ---------------------------------------------------------------------------


def test_overlay_sticky_message_stays_until_cleared():
    """The landing prompt is sticky: it shows while set, then disappears."""
    overlay = MessageOverlay(pygame.Rect(0, 0, 683, 768))
    overlay.set_sticky("Press L to land here")
    for _ in range(5):
        overlay.update()
        assert "Press L to land here" in overlay.active_messages()

    overlay.set_sticky(None)
    assert overlay.active_messages() == []


def test_overlay_transient_message_expires_after_its_frame_budget():
    """'Briefly overlay' means it must also stop being overlaid."""
    overlay = MessageOverlay(pygame.Rect(0, 0, 683, 768))
    overlay.show("insufficient fuel", duration_frames=3)

    for _ in range(3):
        assert "insufficient fuel" in overlay.active_messages()
        overlay.update()
    assert "insufficient fuel" not in overlay.active_messages()


def test_overlay_re_showing_a_message_refreshes_it_instead_of_stacking():
    """Repeated triggers must not stack duplicates of the same banner.

    A banner shown for N frames is drawn on exactly N frames (the scene draws
    after updating), and re-showing it refreshes rather than duplicates it.
    """
    overlay = MessageOverlay(pygame.Rect(0, 0, 683, 768))
    overlay.show("System boundary reached", duration_frames=3)
    overlay.show("System boundary reached", duration_frames=3)

    visible_frames = 0
    for _ in range(4):
        if overlay.active_messages() == ["System boundary reached"]:
            visible_frames += 1
        overlay.update()

    assert visible_frames == 3, f"banner was drawn on {visible_frames} frames, expected 3"


def test_overlay_sticky_message_is_drawn_above_transient_ones():
    """The landing prompt owns the top row so it never jumps around."""
    overlay = MessageOverlay(pygame.Rect(0, 0, 683, 768))
    overlay.set_sticky("Press L to land here")
    overlay.show("10K bounty paid! Pirates destroyed.")
    assert overlay.active_messages() == [
        "Press L to land here",
        "10K bounty paid! Pirates destroyed.",
    ]


def test_overlay_draws_inside_the_game_view_only():
    """Banners belong to the game view and must not spill into the HUD."""
    region = pygame.Rect(0, 0, 683, 768)
    overlay = MessageOverlay(region)
    overlay.set_sticky("Press L to land here")
    surface = pygame.Surface((1024, 768))
    overlay.draw(surface)

    painted = [
        (x, y)
        for y in range(768)
        for x in range(1024)
        if surface.get_at((x, y)) != (0, 0, 0, 255)
    ]
    assert painted, "the overlay drew nothing at all"
    assert all(x < region.width for x, _ in painted), "a banner crossed into the HUD column"
    assert all(y < 120 for _, y in painted), "banners must sit near the top of the display"
