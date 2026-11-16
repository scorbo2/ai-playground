"""Headless test helpers.

These helpers let tests drive the game logic without a real display: the
pytest suite runs under the dummy video/audio SDL drivers (see conftest.py),
so pygame events can be drained and fixed-timestep advancement can be done
without waiting for real time.

This module is test scaffolding that lives in ``src`` rather than in ``tests``
for one reason: the capture scripts under ``scripts/`` import the same helpers,
and ``tests/`` is not an importable package. It must stay free of any real
audio or display setup — a helper that touched the mixer would make the
fail-soft tests fail for the wrong reason.
"""

from collections import Counter

import pygame

from src.model.audio_levels import SOUND_IDS, AudioLevels


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


class RecordingAudio:
    """An :class:`~src.audio.AudioSystem` stand-in that records what was asked for.

    Stages 2, 7, 8, 9, 10 and 11 each hand-rolled their own audio spy, which is
    how the pattern works but also how the pattern rots: every stage that adds a
    sound has to remember to add a method to five classes, or an unrelated test
    fails with an ``AttributeError`` about a sound it never meant to exercise.
    Stage 12 is the audio stage, so it owns the one shared version.

    * Every verb the real AudioSystem exposes is present, including
      ``apply_levels``, so a scene can be driven without tripping over audio.
    * ``plays`` is a :class:`~collections.Counter` keyed by verb name, and
      ``play_order`` keeps the sequence, so "the spin-up precedes the boom" is a
      test rather than an earshot.
    * Count properties are provided per verb because ``audio.impact_count == 2``
      reads better in an assertion than ``audio.plays["impact"] == 2``.
    """

    def __init__(self, levels: "AudioLevels | None" = None) -> None:
        self.available = True
        self.levels = levels if levels is not None else AudioLevels()
        self.levels_applied: "list[AudioLevels]" = []
        self.plays: "Counter[str]" = Counter()
        self.play_order: "list[str]" = []

    # -- the AudioSystem surface ---------------------------------------
    def apply_levels(self, levels: AudioLevels) -> None:
        if not isinstance(levels, AudioLevels):
            raise TypeError(
                "apply_levels expects an AudioLevels; got "
                f"{type(levels).__name__} (call AudioLevels.from_config first)"
            )
        self.levels_applied.append(levels)
        self.levels = levels

    def loaded_volumes(self) -> "dict[str, float]":
        """What each sound *would* play at, given the levels last applied."""
        return {sound_id: self.levels.level_for(sound_id) for sound_id in SOUND_IDS}

    def _record(self, verb: str) -> None:
        self.plays[verb] += 1
        self.play_order.append(verb)

    def play_confirm(self) -> None:
        self._record("confirm")

    def play_weapon_fire(self) -> None:
        self._record("weapon_fire")

    def play_impact(self) -> None:
        self._record("impact")

    def play_destruction(self) -> None:
        self._record("destruction")

    def play_klaxon(self) -> None:
        self._record("klaxon")

    def play_jump_spinup(self) -> None:
        self._record("jump_spinup")

    def play_thunderclap(self) -> None:
        self._record("jump_thunderclap")

    # -- assertion conveniences ----------------------------------------
    @property
    def total_plays(self) -> int:
        return sum(self.plays.values())

    @property
    def confirm_count(self) -> int:
        return self.plays["confirm"]

    @property
    def weapon_fire_count(self) -> int:
        return self.plays["weapon_fire"]

    @property
    def impact_count(self) -> int:
        return self.plays["impact"]

    @property
    def destruction_count(self) -> int:
        return self.plays["destruction"]

    @property
    def klaxon_count(self) -> int:
        return self.plays["klaxon"]

    @property
    def spinup_count(self) -> int:
        return self.plays["jump_spinup"]

    @property
    def thunderclap_count(self) -> int:
        return self.plays["jump_thunderclap"]
