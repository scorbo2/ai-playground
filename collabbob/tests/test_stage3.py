"""Stage 3 tests: pure tactical model core (no pygame).

Covers the fixed-timestep integrator, Newtonian drift, turn rate, the
reverse-course 180-degree edge-triggered state machine, and fuel accounting.
These are deterministic and run headless under the dummy SDL drivers.
"""

import math
import random

import pytest

from src.config import load_config
from src.model.game_state import GameState


def _state(config_factory, overrides=None):
    """Fabricate a valid config set (optionally overriding keys) and build a ship.

    ``load_config`` returns a dict keyed by filename; gameplay needs a single
    flat merged config, so we pull out one difficulty's values here.
    """
    loaded = load_config(config_factory())
    configs = loaded["config_easy.json"]
    if overrides:
        for dotted_key, value in overrides.items():
            node = configs
            for key in dotted_key.split(".")[:-1]:
                node = node[key]
            node[dotted_key.split(".")[-1]] = value
    return GameState(configs, rng=random.Random(0))


def test_thrust_from_rest_reaches_exactly_top_speed_in_60_frames(config_factory):
    """60 frames of thrust from rest with acc 0.2 / top 5 reaches exactly 5 px/frame."""
    state = _state(config_factory)
    assert math.hypot(*state.velocity) == 0.0

    for _ in range(60):
        state.feed_input(thrust=True)
        state.advance_frame()

    speed = math.hypot(*state.velocity)
    assert speed == pytest.approx(5.0, abs=1e-9), f"expected exactly 5.0, got {speed!r}"


def test_velocity_persists_without_input(config_factory):
    """With no input, velocity is unchanged and position drifts by that velocity."""
    state = _state(config_factory)

    # Thrust for a few frames to establish a known velocity.
    for _ in range(10):
        state.feed_input(thrust=True)
        state.advance_frame()
    vx, vy = state.velocity
    assert math.hypot(vx, vy) > 0.0

    # No input for several frames: Newtonian drift, velocity constant.
    start_pos = state.position
    for _ in range(5):
        state.feed_input()
        state.advance_frame()

    assert state.velocity == (vx, vy), "velocity must persist with no thrust"
    expected_dx = vx * 5
    expected_dy = vy * 5
    assert state.position == pytest.approx((start_pos[0] + expected_dx, start_pos[1] + expected_dy))


def test_down_arrow_rotates_exactly_180_in_exactly_60_frames(config_factory):
    """Reverse-course flips the heading by exactly 180 degrees in exactly 60 frames."""
    state = _state(config_factory)
    state.heading_degrees = 42.0

    # Feed the reverse edge, then advance frame-by-frame to find the exact count.
    state.feed_input(reverse_edge=True)
    for n in range(1, 61):
        state.advance_frame()
        if n == 60:
            break

    assert math.isclose(state.heading_degrees, 42.0 + 180.0, abs_tol=1e-9), (
        f"expected {42.0 + 180.0}, got {state.heading_degrees!r}"
    )


def test_down_arrow_mid_rotation_restarts_from_current_heading(config_factory):
    """Pressing Down mid-flip restarts the flip from the current facing direction."""
    state = _state(config_factory)
    start = 10.0
    state.heading_degrees = start

    # Begin a flip and rotate partway (10 frames at 3 deg/frame => +30 degrees).
    state.feed_input(reverse_edge=True)
    for _ in range(10):
        state.advance_frame()
    assert math.isclose(state.heading_degrees, start + 30.0, abs_tol=1e-9)

    # Re-pressing Down restarts from the current heading; it should NOT finish
    # instantly -- a fresh 180-degree rotation begins from +30 degrees.
    state.feed_input(reverse_edge=True)
    assert math.isclose(state.heading_degrees, start + 30.0, abs_tol=1e-9), (
        "re-pressing Down mid-flip must not complete the previous flip"
    )

    # A further 60 frames completes the new 180-degree rotation from +30 degrees.
    for _ in range(60):
        state.advance_frame()
    assert math.isclose(state.heading_degrees, start + 30.0 + 180.0, abs_tol=1e-9), (
        f"expected {start + 210.0}, got {state.heading_degrees!r}"
    )


def test_reverse_course_does_not_affect_velocity_or_fuel(config_factory):
    """Reverse-course is a pure rotation: it consumes no fuel and no velocity."""
    state = _state(config_factory)
    state.fuel = 500.0

    for _ in range(60):
        state.feed_input(reverse_edge=True)
        state.advance_frame()

    assert state.velocity == (0.0, 0.0)
    assert math.hypot(*state.position) == 0.0
    assert state.fuel == pytest.approx(500.0, abs=1e-9)


def test_thrust_consumes_fuel(config_factory):
    """Each thrusting frame burns fuel; fuel never drops below zero."""
    state = _state(config_factory)
    state.fuel = 100.0

    # Fuel burns per thrusting frame; verify the balance actually drops.
    before = state.fuel
    for _ in range(50):
        state.feed_input(thrust=True)
        state.advance_frame()
    after = state.fuel

    assert after < before, "thrusting should consume fuel"
    assert state.fuel >= 0.0


def test_facing_vector_aligns_with_heading(config_factory):
    """The facing vector points along the configured heading."""
    state = _state(config_factory)
    state.heading_degrees = 90.0
    fx, fy = state.facing_vector()
    assert (fx, fy) == pytest.approx((math.cos(math.radians(90.0)), math.sin(math.radians(90.0))))


def test_reverse_course_frame_count_tracks_turn_rate(config_factory):
    """Reverse-course completion time is derived from the configured turn rate."""
    # A faster turn rate should complete the 180-degree flip in fewer frames.
    state = _state(config_factory, {"player_ship.turn_rate_deg_per_sec": 360})
    state.heading_degrees = 0.0
    state.feed_input(reverse_edge=True)

    completed_at = None
    for n in range(1, 601):
        state.advance_frame()
        if math.isclose(state.heading_degrees, 180.0, abs_tol=1e-6):
            completed_at = n
            break
    assert completed_at is not None
    assert 1 < completed_at <= 60


def test_left_arrow_rotates_the_ship_counter_clockwise_on_screen(config_factory):
    """Holding LEFT must turn the ship counter-clockwise as the player sees it.

    The view is drawn on a y-down screen, so heading 0 faces east and heading 90
    faces south; increasing heading is therefore a *clockwise* turn and "left"
    must decrease the heading. The first revision had these swapped, so every
    turn input steered the ship the wrong way.
    """
    state = _state(config_factory)
    state.heading_degrees = 90.0  # facing straight down (south)

    for _ in range(20):
        state.feed_input(left=True)
        state.advance_frame()

    rate = state.stats.turn_rate_deg_per_sec / 60.0
    assert math.isclose(state.heading_degrees, (90.0 - 20 * rate) % 360.0, abs_tol=1e-6)

    # Turning left from south heads the nose toward east (6 o'clock -> 3 o'clock).
    facing_x, facing_y = state.facing_vector()
    assert facing_x > 0.0, "left from south must swing the nose toward east"
    assert facing_y > 0.0


def test_right_arrow_rotates_the_ship_clockwise_on_screen(config_factory):
    """Holding RIGHT is the mirror image: south swings toward west."""
    state = _state(config_factory)
    state.heading_degrees = 90.0  # facing straight down (south)

    for _ in range(20):
        state.feed_input(right=True)
        state.advance_frame()

    rate = state.stats.turn_rate_deg_per_sec / 60.0
    assert math.isclose(state.heading_degrees, (90.0 + 20 * rate) % 360.0, abs_tol=1e-6)

    facing_x, facing_y = state.facing_vector()
    assert facing_x < 0.0, "right from south must swing the nose toward west"
    assert facing_y > 0.0


def test_left_and_right_are_symmetric_at_the_configured_turn_rate(config_factory):
    """Equal holds in opposite directions cancel out at the configured rate."""
    state = _state(config_factory)
    state.heading_degrees = 37.0

    for _ in range(15):
        state.feed_input(right=True)
        state.advance_frame()
    for _ in range(15):
        state.feed_input(left=True)
        state.advance_frame()

    assert math.isclose(state.heading_degrees, 37.0, abs_tol=1e-6)
