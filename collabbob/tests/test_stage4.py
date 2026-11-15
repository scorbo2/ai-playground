"""Stage 4 tests: camera mapping, recycling starfield, and tactical view draw.

The camera is locked to the player's ship (spec: "The player's ship is always
centered"), so these tests pin three things the first Stage 4 revision got
wrong: the ship is drawn at the view centre no matter where it is in the world,
the planet slides the opposite way, and the starfield actually scrolls because
the scene drives ``Starfield.update()`` every frame.
"""

import random

import pygame
import pytest

import main  # noqa: F401  (ensures project root is on sys.path)

from src.camera import world_to_screen
from src.config import load_config
from src.model.game_state import GameState
from src.model.starfield import Starfield
from src.scenes import tactical_view as tactical_view_module
from src.scenes.tactical_view import TacticalView, _VIEW_CENTER
from src.scene_manager import SceneManager
from src.audio import AudioSystem


def _view(configs, heading=0.0, position=(0.0, 0.0)):
    """A tactical view over a fabricated config with a known ship state."""
    manager = SceneManager(
        screen=pygame.display.get_surface(), configs=configs, audio=AudioSystem()
    )
    manager.selected_config = configs["config_easy.json"]
    game_state = GameState(configs["config_easy.json"], rng=random.Random(1))
    game_state.heading_degrees = heading
    game_state.set_position(*position)
    return TacticalView(manager, game_state)


def _flat(configs):
    return configs["config_easy.json"]


def _pixel_coords(surface, color):
    """Every screen coordinate on `surface` painted exactly `color`."""
    return {
        (x, y)
        for y in range(surface.get_height())
        for x in range(surface.get_width())
        if surface.get_at((x, y))[:3] == color
    }


def _bounding_box(coords):
    xs = [x for x, _ in coords]
    ys = [y for _, y in coords]
    return (min(xs), min(ys), max(xs), max(ys))


# ---------------------------------------------------------------------------
# world_to_screen golden tests (pure function, no surface needed)
# ---------------------------------------------------------------------------


def test_world_to_screen_puts_the_ship_at_the_view_centre():
    """The camera anchor (the ship) always maps to the centre of the view."""
    center = (341.5, 384.0)
    assert world_to_screen(10.0, 20.0, (10.0, 20.0), center) == (341.5, 384.0)


def test_world_to_screen_translates_other_points_by_their_offset_from_the_ship():
    """A point 100 right / 50 above the ship lands 100 right / 50 up from centre."""
    center = (341.5, 384.0)
    assert world_to_screen(100.0, -50.0, (0.0, 0.0), center) == (441.5, 334.0)


def test_world_to_screen_moves_the_world_opposite_to_the_ship():
    """Flying the ship right shifts everything else left by the same amount."""
    center = (341.5, 384.0)
    before = world_to_screen(0.0, 0.0, (0.0, 0.0), center)
    after = world_to_screen(0.0, 0.0, (120.0, -40.0), center)
    assert (after[0] - before[0], after[1] - before[1]) == (-120.0, 40.0)


def test_world_to_screen_handles_negative_world_coords():
    """Negative ship and world coordinates map without surprises."""
    center = (341.5, 384.0)
    # The point is 20 right and 15 below the ship, so it lands 20 right and 15
    # below the view centre.
    assert world_to_screen(-10.0, 20.0, (-30.0, 5.0), center) == (361.5, 399.0)


# ---------------------------------------------------------------------------
# Starfield recycling + scroll invariants (model level)
# ---------------------------------------------------------------------------


def test_star_count_invariant_over_1000_frames():
    """The on-screen star count never changes, no matter how fast the ship flies."""
    sf = Starfield(count=150, half_extent=341.0, rng=random.Random(99))

    assert len(sf) == 150
    for _ in range(1000):
        sf.update(velocity_x=73.0, velocity_y=-41.0)
        assert len(sf) == 150


def test_rightward_movement_shifts_stars_left_by_same_delta():
    """Moving the ship right shifts every star left by exactly that distance."""
    # spawn_margin equals the total movement so no star recycles during the test.
    per_frame = 5.0
    frames = 2
    sf = Starfield(
        count=40, half_extent=341.0, spawn_margin=per_frame * frames, rng=random.Random(7)
    )

    before = [(s.x, s.y) for s in sf.stars]
    assert len(before) == 40

    # Ship moves right (+x) by 5 px/frame for 2 frames => background shifts left (-x) by 10.
    sf.update(per_frame, 0.0)
    sf.update(per_frame, 0.0)
    after = [(s.x, s.y) for s in sf.stars]

    assert len(after) == 40
    for (bx, by), (ax, ay) in zip(before, after):
        assert ax == bx - per_frame * frames
        assert ay == by


def test_starfield_respawns_recycled_star_inside_window():
    sf = Starfield(count=5, half_extent=100.0, rng=random.Random(3))
    # Force a star far outside the window, then update; it must be pulled back in.
    sf.stars[0].x = 999.0
    sf.stars[0].y = -999.0
    sf.update(1.0, 1.0)
    assert all(abs(s.x) <= 100.0 and abs(s.y) <= 100.0 for s in sf.stars)


# ---------------------------------------------------------------------------
# Tactical view rendering (scene level)
# ---------------------------------------------------------------------------


def test_tactical_view_draws_ship_planet_and_stars(config_factory):
    """The tactical view renders its contents without crashing and draws content."""
    configs = load_config(config_factory())
    view = _view(configs, heading=45.0, position=(50.0, -30.0))

    expected_star_count = int(_flat(configs)["tactical"]["stars"]["count"])
    assert len(view.starfield) == expected_star_count

    surface = pygame.Surface((1024, 768))
    view.draw(surface)

    # Something other than pure black must have been drawn (stars + planet + ship).
    non_black = 0
    for py in range(0, 683, 7):
        for px in range(0, 683, 7):
            if surface.get_at((px, py)) != (0, 0, 0):
                non_black += 1
    assert non_black > 0


def test_tactical_view_ship_sprite_matches_configured_size(config_factory):
    """The cached ship sprite matches the configured length/width."""
    configs = load_config(config_factory())
    view = _view(configs)
    flat = _flat(configs)
    assert view._ship_surface.get_size() == (
        int(flat["player_ship"]["length"]),
        int(flat["player_ship"]["width"]),
    )


def test_ship_is_painted_at_the_view_centre_whatever_its_world_position(config_factory):
    """The ship is pinned to the centre of the game view (spec requirement).

    The nose block has a unique colour, so its painted coordinates can be read
    straight off the surface: they must be identical for two different world
    positions when the heading is unchanged.
    """
    configs = load_config(config_factory())
    nose_color = (150, 210, 230)

    surface_a = pygame.Surface((1024, 768))
    _view(configs, heading=0.0, position=(0.0, -120.0)).draw(surface_a)
    surface_b = pygame.Surface((1024, 768))
    _view(configs, heading=0.0, position=(60.0, -180.0)).draw(surface_b)

    nose_a = _pixel_coords(surface_a, nose_color)
    nose_b = _pixel_coords(surface_b, nose_color)
    assert nose_a, "ship nose was not drawn at all"
    assert nose_a == nose_b, "the ship must stay put at the view centre"
    centre = (int(round(_VIEW_CENTER[0])), int(round(_VIEW_CENTER[1])))
    assert centre in nose_a or any(
        abs(x - centre[0]) < 40 and abs(y - centre[1]) < 20 for x, y in nose_a
    ), "the ship must be drawn at the centre of the game view, not off to one side"


def test_planet_slides_opposite_to_the_ships_movement(config_factory):
    """The planet (at the world origin) pans across the view as the ship flies."""
    configs = load_config(config_factory())
    surface_a = pygame.Surface((1024, 768))
    view_a = _view(configs, position=(0.0, -120.0))
    view_a.draw(surface_a)
    surface_b = pygame.Surface((1024, 768))
    _view(configs, position=(60.0, -180.0)).draw(surface_b)

    # Stage 8 made the planet colour a property of the *system*, not of the
    # planet's diameter, so the expected colour comes from the same helper the
    # renderer calls rather than from a re-derivation of its rule.
    planet_color = tactical_view_module.planet_color_for(view_a.system_name)

    box_a = _bounding_box(_pixel_coords(surface_a, planet_color))
    box_b = _bounding_box(_pixel_coords(surface_b, planet_color))
    assert (box_b[0] - box_a[0], box_b[1] - box_a[1]) == (-60, 60), (
        "planet must move by exactly minus the ship's displacement"
    )


def test_tactical_view_update_scrolls_the_starfield(config_factory):
    """The scene drives Starfield.update(): thrust really does move the background.

    This is the wiring the first Stage 4 revision never performed — the model
    class scrolled its stars beautifully while the game view stayed frozen.

    Stars that drifted out of the view box are recycled in place, so only the
    stars that could not possibly have left the box are compared exactly.
    """
    configs = load_config(config_factory())
    view = _view(configs)

    before = [(s.x, s.y) for s in view.starfield.stars]
    start_position = view.game_state.position

    for _ in range(20):
        view.input.feed_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP))
        view.update()

    moved = view.game_state.position
    travelled = (moved[0] - start_position[0], moved[1] - start_position[1])
    assert travelled[0] > 0.0, "thrust must move the ship"

    after = [(s.x, s.y) for s in view.starfield.stars]
    assert len(after) == len(before)

    # A star this far from the box edge cannot have been recycled.
    furthest = max(abs(travelled[0]), abs(travelled[1]))
    safe_extent = view.starfield.half_extent - furthest
    compared = 0
    for index, (bx, by) in enumerate(before):
        if max(abs(bx), abs(by)) <= safe_extent:
            ax, ay = after[index]
            assert ax == pytest.approx(bx - travelled[0], abs=1e-9), "star must shift left"
            assert ay == pytest.approx(by - travelled[1], abs=1e-9), "star must shift up/down"
            compared += 1

    assert compared > len(before) // 2, (
        f"only {compared}/{len(before)} stars were in range to compare — the "
        "test is not actually proving the background scrolls"
    )


def test_ship_sprite_is_rotated_by_negative_heading_in_degrees(config_factory, monkeypatch):
    """``pygame.transform.rotate`` takes DEGREES (positive = counter-clockwise).

    Passing ``math.radians(heading)`` rotates the sprite by 1/57th of the real
    heading, so the ship looks welded to one facing no matter what the player
    does. The sign is negative because our heading convention is clockwise on a
    y-down screen while pygame's positive rotation is counter-clockwise.
    """
    configs = load_config(config_factory())
    heading = 90.0
    view = _view(configs, heading=heading)

    captured = []
    real_rotate = pygame.transform.rotate

    def spy_rotate(surface, angle):
        captured.append(angle)
        return real_rotate(surface, angle)

    monkeypatch.setattr(pygame.transform, "rotate", spy_rotate)
    view.draw(pygame.Surface((1024, 768)))

    assert captured, "the ship sprite was never rotated"
    assert captured[0] == -heading, (
        f"expected -{heading} degrees, got {captured[0]!r} "
        "(radians were passed where degrees were required)"
    )


def test_ship_facing_south_is_drawn_facing_south(config_factory):
    """A ship whose velocity points south must LOOK like it points south.

    Heading 90 means the facing vector is (0, +1) = screen-down. The sprite's nose
    starts at +x, so only a clockwise rotation puts the nose at the bottom; get
    the sign wrong and the ship flies one way while drawing itself mirrored.
    """
    configs = load_config(config_factory())
    view = _view(configs, heading=90.0)

    facing_x, facing_y = view.game_state.facing_vector()
    assert (round(facing_x), round(facing_y)) == (0, 1), "heading 90 must face screen-down"

    surface = pygame.Surface((1024, 768))
    view.draw(surface)
    nose = _pixel_coords(surface, (150, 210, 230))
    assert nose, "ship nose was not drawn"
    nose_centre_y = sum(y for _, y in nose) / len(nose)
    assert nose_centre_y > _VIEW_CENTER[1], (
        f"ship faces south but its nose was drawn above the hull centre "
        f"(nose y={nose_centre_y:.1f}, centre y={_VIEW_CENTER[1]})"
    )
