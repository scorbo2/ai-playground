"""Headless test helpers (stage 1 skeleton).

These helpers let tests drive the game logic without a real display: the
pytest suite runs under the dummy video/audio SDL drivers (see conftest.py),
so pygame events can be drained and fixed-timestep advancement can be done
without waiting for real time.
"""

import pygame


def pump_events(frames=1):
    """Drain the pygame event queue for `frames` fixed timesteps.

    Returns the pygame event objects consumed (an empty list when the queue
    has no events for a frame). Callers that need specific events should
    inject them into the pygame event queue before calling this.
    """
    # Initialise the video system (the dummy driver under the test suite) so
    # the event queue is usable without a real display.
    pygame.init()
    events = []
    for _ in range(frames):
        events.extend(pygame.event.get())
    return events


def advance(frames, loop):
    """Advance a fixed-timestep loop by `frames` simulation steps.

    Calls loop.step() once per fixed step, bypassing the accumulator and
    real-time handling of run(), so tests can simulate a fixed number of
    game frames deterministically. Returns the number of steps taken.
    """
    for _ in range(frames):
        loop.step()
    return frames
