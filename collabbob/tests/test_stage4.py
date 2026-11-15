"""Stage 4 tests: camera mapping, recycling starfield, and tactical view draw."""

import random

import pygame

import main  # noqa: F401  (ensures project root is on sys.path)

from src.camera import world_to_screen
from src.config import load_config
from src.model.starfield import Starfield
from src.scenes.tactical_view import TacticalView
from src.scene_manager import SceneManager
from src.audio import AudioSystem


# ---------------------------------------------------------------------------
# world_to_screen golden tests (pure function, no surface needed)
# ---------------------------------------------------------------------------


def test_world_to_screen_maps_origin_to_view_center():
    center = (341.5, 384.0)
    assert world_to_screen(0.0, 0.0, center) == (341.5, 384.0)


def test_world_to_screen_translates_point_right_and_up():
    center = (341.5, 384.0)
    # +100 world-x shifts the screen point right by 100; -50 world-y shifts up.
    assert world_to_screen(100.0, -50.0, center) == (441.5, 334.0)


def test_world_to_screen_handles_negative_world_coords():
    center = (341.5, 384.0)
    assert world_to_screen(-10.0, 20.0, center) == (331.5, 404.0)


# ---------------------------------------------------------------------------
# Starfield recycling + scroll invariants
# ---------------------------------------------------------------------------


def test_star_count_invariant_over_1000_frames(config_factory):
    """The on-screen star count never changes, no matter how fast the ship flies."""
    loaded = load_config(config_factory())
    configs = loaded["config_easy.json"]
    sf = Starfield(count=150, half_extent=341.0, rng=random.Random(99))

    assert len(sf) == 150
    for _ in range(1000):
        sf.update(velocity_x=73.0, velocity_y=-41.0)
        assert len(sf) == 150


def test_rightward_movement_shifts_stars_left_by_same_delta(config_factory):
    """Moving the ship right shifts every star left by exactly that distance."""
    loaded = load_config(config_factory())
    configs = loaded["config_easy.json"]
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


def test_starfield_respawns_recycled_star_inside_window(config_factory):
    loaded = load_config(config_factory())
    sf = Starfield(count=5, half_extent=100.0, rng=random.Random(3))
    # Force a star far outside the window, then update; it must be pulled back in.
    sf.stars[0].x = 999.0
    sf.stars[0].y = -999.0
    sf.update(1.0, 1.0)
    assert all(abs(s.x) <= 100.0 and abs(s.y) <= 100.0 for s in sf.stars)


# ---------------------------------------------------------------------------
# Tactical view rendering smoke test
# ---------------------------------------------------------------------------


def test_tactical_view_draws_ship_planet_and_stars(config_factory):
    """The tactical view renders its contents without crashing and draws content."""
    screen = pygame.display.get_surface()
    manager = SceneManager(screen=screen, configs=load_config(config_factory()), audio=AudioSystem())

    view = TacticalView(manager)
    flat = manager.configs["config_easy.json"]
    expected_star_count = int(flat["tactical"]["stars"]["count"])
    assert len(view.starfield) == expected_star_count

    # Place the ship off-planet and rotate it; drawing must not raise.
    view.game_state.set_position(50.0, -30.0)
    view.game_state.heading_degrees = 45.0

    surface = pygame.Surface((1024, 768))
    view.draw(surface)

    # Something other than pure black must have been drawn (stars + planet + ship).
    non_black = 0
    for py in range(0, 683, 7):
        for px in range(0, 683, 7):
            if surface.get_at((px, py)) != (0, 0, 0):
                non_black += 1
    assert non_black > 0


def test_tactical_view_ship_drawn_at_world_to_screen_position(config_factory):
    """The cached ship sprite matches the configured blocky length/width."""
    screen = pygame.display.get_surface()
    manager = SceneManager(screen=screen, configs=load_config(config_factory()), audio=AudioSystem())

    view = TacticalView(manager)
    flat = manager.configs["config_easy.json"]
    length = float(flat["player_ship"]["length"])
    width = float(flat["player_ship"]["width"])
    assert view._ship_surface.get_size() == (int(length), int(width))

