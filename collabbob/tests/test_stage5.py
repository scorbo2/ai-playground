"""Stage 5 tests: input layer.

The :class:`~src.input.InputLayer` translates raw pygame key events into
frame-aligned control signals and discrete actions, keeping key handling
separated from simulation. These event-pump tests cover hold-vs-tap semantics,
the reverse-course edge trigger, the fire binding, and the input-lock flag that
suppresses every control while a jump animates.
"""

import math

import pytest

import pygame

import main  # noqa: F401  (ensures project root is on sys.path)

from src.config import load_config
from src.input import (
    Action, InputLayer, KEY_DOWN, KEY_ESCAPE, KEY_J, KEY_LEFT, KEY_L,
    KEY_M, KEY_SPACE, KEY_T, KEY_UP,
)
from src.model.game_state import GameState
from src.scenes.tactical_view import TacticalView
from src.scene_manager import SceneManager


def _keydown(key):
    """Build a synthetic pygame KEYDOWN event for `key`."""
    return pygame.event.Event(pygame.KEYDOWN, {"key": key})


def _keyup(key):
    """Build a synthetic pygame KEYUP event for `key`."""
    return pygame.event.Event(pygame.KEYUP, {"key": key})


def _drain(input_layer, *events):
    """Feed events into the layer and drain one frame.

    Returns ``(control_frame_or_None, actions)``.
    """
    for event in events:
        input_layer.feed_event(event)
    return input_layer.drain_frame()


# ---------------------------------------------------------------------------
# Hold vs. tap (level signals)
# ---------------------------------------------------------------------------


def test_hold_thrust_emits_frame_each_drained_frame():
    """Holding UP keeps thrust True across every drained frame."""
    layer = InputLayer()

    # Press and hold thrust; never release it.
    layer.feed_event(_keydown(KEY_UP))

    for _ in range(5):
        controls, actions = _drain(layer)
        assert controls is not None
        assert controls.thrust is True
        assert actions == []


def test_tap_produces_exactly_one_frame_of_level_signal():
    """A tap (press in one frame, release the next) yields exactly one True."""
    layer = InputLayer()

    # Pressed this frame -> held.
    layer.feed_event(_keydown(KEY_UP))
    controls, _ = _drain(layer)
    assert controls.thrust is True

    # Released on the next real frame -> no longer held.
    layer.feed_event(_keyup(KEY_UP))
    controls, _ = _drain(layer)
    assert controls.thrust is False

    controls, _ = _drain(layer)
    assert controls.thrust is False


def test_hold_left_across_frames_sets_level_signal():
    """Holding LEFT keeps the left level signal True across frames."""
    layer = InputLayer()
    layer.feed_event(_keydown(KEY_LEFT))

    for _ in range(3):
        controls, _ = _drain(layer)
        assert controls.left is True


def test_release_left_clears_level_signal():
    """Releasing LEFT clears the left level signal on the next frame."""
    layer = InputLayer()
    layer.feed_event(_keydown(KEY_LEFT))
    controls, _ = _drain(layer)
    assert controls.left is True

    layer.feed_event(_keyup(KEY_LEFT))
    controls, _ = _drain(layer)
    assert controls.left is False


# ---------------------------------------------------------------------------
# Reverse-course edge semantics
# ---------------------------------------------------------------------------


def test_single_down_press_sets_reverse_edge_once():
    """A single DOWN press yields reverse_edge True for exactly one frame."""
    layer = InputLayer()
    layer.feed_event(_keydown(KEY_DOWN))

    controls, _ = _drain(layer)
    assert controls.reverse_edge is True

    # No further events: subsequent frames must not see the edge again.
    controls, _ = _drain(layer)
    assert controls.reverse_edge is False


def test_holding_down_does_not_repeat_reverse_edge():
    """Holding DOWN (press then keep held) only triggers the edge once."""
    layer = InputLayer()
    layer.feed_event(_keydown(KEY_DOWN))  # press and hold

    controls, _ = _drain(layer)
    assert controls.reverse_edge is True  # this frame's rising edge

    # Still held but no new rising edge: the edge must not re-fire.
    for _ in range(3):
        controls, _ = _drain(layer)
        assert controls.reverse_edge is False


def test_re_pressing_down_emits_a_second_edge():
    """Re-pressing DOWN in a later frame sets the edge again (restart rule)."""
    layer = InputLayer()

    # First press.
    layer.feed_event(_keydown(KEY_DOWN))
    controls, _ = _drain(layer)
    assert controls.reverse_edge is True

    # Let it complete without another edge.
    controls, _ = _drain(layer)
    assert controls.reverse_edge is False

    # A second physical press (after release) begins a fresh rising edge.
    layer.feed_event(_keyup(KEY_DOWN))
    controls, _ = _drain(layer)
    assert controls.reverse_edge is False

    layer.feed_event(_keydown(KEY_DOWN))
    controls, _ = _drain(layer)
    assert controls.reverse_edge is True


# ---------------------------------------------------------------------------
# Fire binding (hold-to-fire)
# ---------------------------------------------------------------------------


def test_fire_action_emitted_each_frame_while_space_held():
    """Holding space emits a fire action on every drained frame."""
    layer = InputLayer()
    layer.feed_event(_keydown(KEY_SPACE))

    for _ in range(4):
        controls, actions = _drain(layer)
        assert actions == [Action("fire")]


def test_fire_action_stops_when_space_released():
    """Releasing space stops the fire action."""
    layer = InputLayer()
    layer.feed_event(_keydown(KEY_SPACE))
    _, actions = _drain(layer)
    assert actions and actions[0].kind == "fire"

    layer.feed_event(_keyup(KEY_SPACE))
    controls, actions = _drain(layer)
    assert controls.thrust is False
    assert actions == []


# ---------------------------------------------------------------------------
# Discrete bindings (edge-triggered)
# ---------------------------------------------------------------------------


def test_open_map_binding_emits_once_per_press():
    """Pressing M emits a single open_map action."""
    layer = InputLayer()
    layer.feed_event(_keydown(KEY_M))
    controls, actions = _drain(layer)
    assert controls is not None
    assert actions == [Action("open_map")]


def test_binding_hold_does_not_repeat_action():
    """Holding a binding key does not repeat its action."""
    layer = InputLayer()
    layer.feed_event(_keydown(KEY_M))  # press and hold

    first, actions1 = _drain(layer)
    assert actions1 == [Action("open_map")]

    second, actions2 = _drain(layer)
    assert actions2 == []  # no rising edge -> no action


def test_all_bindings_map_to_expected_actions():
    """Each binding key maps to its documented action kind."""
    layer = InputLayer()
    bindings = {
        KEY_J: "jump",
        KEY_L: "land",
        KEY_T: "scan",
        KEY_ESCAPE: "exit_game",
    }
    for key, expected in bindings.items():
        layer.feed_event(_keydown(key))
        _, actions = _drain(layer)
        assert actions == [Action(expected)], f"key {key} -> {actions}"


# ---------------------------------------------------------------------------
# Input-lock flag
# ---------------------------------------------------------------------------


def test_locked_suppresses_all_controls_and_actions():
    """When locked, drain_frame returns no control frame and no actions."""
    layer = InputLayer()
    layer.feed_event(_keydown(KEY_UP))
    layer.feed_event(_keydown(KEY_SPACE))

    layer.lock_input()
    controls, actions = _drain(layer)
    assert controls is None
    assert actions == []


def test_locked_discards_queued_actions():
    """Any action queued while locked must not leak to the next frame."""
    layer = InputLayer()
    layer.feed_event(_keydown(KEY_M))  # queue open_map
    layer.lock_input()

    controls, actions = _drain(layer)
    assert controls is None
    assert actions == []

    # The queued action is gone; a real press afterwards still works.
    layer.unlock_input()
    layer.feed_event(_keydown(KEY_J))
    _, actions = _drain(layer)
    assert actions == [Action("jump")]


def test_lock_then_unlock_restores_controls():
    """Unlocking restores normal control/action behaviour."""
    layer = InputLayer()
    layer.lock_input()
    controls, actions = _drain(layer)
    assert (controls, actions) == (None, [])

    layer.unlock_input()
    layer.feed_event(_keydown(KEY_UP))
    controls, actions = _drain(layer)
    assert controls is not None and controls.thrust is True


# ---------------------------------------------------------------------------
# Integration: tactical scene feeds controls into the simulation
# ---------------------------------------------------------------------------


def test_tactical_view_update_feeds_thrust_into_game_state(config_factory):
    """Holding thrust through TacticalView.update() accelerates the ship."""
    loaded = load_config(config_factory())
    configs = loaded["config_easy.json"]
    screen = pygame.display.get_surface()
    manager = SceneManager(
        screen=screen, configs=loaded, audio=_SilentAudio()
    )
    manager.selected_config = configs
    view = TacticalView(manager, GameState(configs))

    assert math.hypot(*view.game_state.velocity) == 0.0

    # Hold thrust for exactly 60 frames at acc 0.2 / top 5 => 5 px/frame.
    layer = view.input
    for _ in range(60):
        layer.feed_event(_keydown(KEY_UP))
        view.update()

    assert math.hypot(*view.game_state.velocity) == pytest.approx(5.0, abs=1e-9)


def test_tactical_view_update_reverse_flip_after_60_frames(config_factory):
    """A DOWN edge pressed through the scene flips heading 180° in 60 frames."""
    loaded = load_config(config_factory())
    configs = loaded["config_easy.json"]
    screen = pygame.display.get_surface()
    manager = SceneManager(
        screen=screen, configs=loaded, audio=_SilentAudio()
    )
    manager.selected_config = configs
    view = TacticalView(manager, GameState(configs))
    view.game_state.heading_degrees = 10.0

    layer = view.input
    layer.feed_event(_keydown(KEY_DOWN))
    for _ in range(60):
        view.update()

    assert math.isclose(view.game_state.heading_degrees, 190.0, abs_tol=1e-9)


class _SilentAudio:
    """Minimal audio stand-in so TacticalView can be constructed headless."""

    available = False

    def play_confirm(self):
        pass
