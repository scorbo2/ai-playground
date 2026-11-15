"""Stage 1 tests for the headless harness helpers."""

import pygame

from src.harness import advance, pump_events
from src.main_loop import FixedTimestepLoop


def test_pump_events_drains_event_queue_headless():
    """pump_events drains pygame events without a real display."""
    events = pump_events(frames=10)
    assert isinstance(events, list)
    # everything queued by the dummy drivers is consumed by this call
    assert pygame.event.get() == []


def test_advance_steps_loop_by_fixed_number_of_frames():
    """advance drives a fixed-timestep loop by a fixed number of steps."""
    recorded = []

    class RecordingStep:
        def __init__(self):
            self.count = 0

        def __call__(self):
            self.count += 1
            recorded.append(self.count)

    loop = FixedTimestepLoop(on_step=RecordingStep())
    assert advance(frames=60, loop=loop) == 60
    assert recorded == list(range(1, 61))


def test_advance_with_real_loop_headless():
    """advance works on the real FixedTimestepLoop under the dummy driver."""
    loop = FixedTimestepLoop(on_step=None)
    assert advance(frames=30, loop=loop) == 30
