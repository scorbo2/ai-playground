"""Sound levels: which events make a noise, and how loud each one is (Stage 12).

This module is deliberately pygame-free. It is the *policy* half of audio — a
plain value object the config loader validates against and the mixer layer
consumes — so the loader can reject an unusable level without dragging pygame
into :mod:`src.config`. The waveform synthesis lives in :mod:`src.audio_buffers`
(also pygame-free), and :mod:`src.audio` is the only place the mixer itself is
touched. The id constants below are imported by the synthesis registry: the
vocabulary is declared once, on the policy side that owns it.

Why levels are mixer state and not part of the waveform
-------------------------------------------------------
Every generated buffer is built at a fixed reference peak and then turned down by
the mixer (:meth:`src.audio.AudioSystem.play`). Baking the level into the samples
instead would mean:

* a config change invalidates every cached buffer (and a difficulty change
  mid-session regenerates ~250 000 samples of pure-Python maths);
* "0.4 means the same loudness in every sound" stops being true, because each
  generator has its own internal headroom.

So the generators own *timbre*, the config owns *level*, and the two meet at
:meth:`level_for`. That is also what makes the gate testable: the buffer for
``ship_impact`` is byte-identical whether the config asks for 0.05 or 0.5, and
the level is a number a test can read straight back off the mixer.

Sound ids double as config keys
-------------------------------
``SOUND_IDS`` is the one vocabulary. The config key, the registry entry in
:mod:`src.audio_buffers`, and the argument to :meth:`level_for` are the same
string, so a typo cannot hide in a translation table between three lists that
"should" agree. (``AudioSystem``'s *method* names are verbs — ``play_impact`` —
because the scenes read as sentences; the id they map to is right there in the
method.)
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields
from typing import Any, Mapping, Tuple

# Sound ids. Also the keys of the ``audio`` config section. Enum-like ids stay in
# code per the spec's config guidance; only the *levels* are tunable.
SOUND_CONFIRM_BEEP = "confirm_beep"
SOUND_WEAPON_FIRE = "weapon_fire"
SOUND_SHIP_IMPACT = "ship_impact"
SOUND_SHIP_DESTRUCTION = "ship_destruction"
SOUND_SCAN_KLAXON = "scan_klaxon"
SOUND_JUMP_SPINUP = "jump_spinup"
SOUND_JUMP_THUNDERCLAP = "jump_thunderclap"

SOUND_IDS: Tuple[str, ...] = (
    SOUND_CONFIRM_BEEP,
    SOUND_WEAPON_FIRE,
    SOUND_SHIP_IMPACT,
    SOUND_SHIP_DESTRUCTION,
    SOUND_SCAN_KLAXON,
    SOUND_JUMP_SPINUP,
    SOUND_JUMP_THUNDERCLAP,
)

# The one knob that is not per-sound, listed separately because it is not a
# member of SOUND_IDS (it is a multiplier *on* every member).
MASTER_VOLUME_KEY = "master_volume"

MAX_VOLUME = 1.0


class AudioLevelError(ValueError):
    """Raised when an ``audio`` section describes levels no mixer can honour.

    A ValueError subclass, because that is what the config loader already turns
    into a fatal, line-numbered configuration error.
    """


def _validated_volume(key: str, value: Any) -> float:
    """Coerce one level to a float in [0, 1], refusing everything else loudly.

    ``bool`` is rejected even though it *is* an int in Python: ``"weapon_fire":
    true`` is either a mistake or somebody's joke, and neither belongs in a
    config that another stage's sweep test is going to read.
    """
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise AudioLevelError(
            f"audio.{key} must be a number between 0 and 1: got {value!r}"
        )
    level = float(value)
    if not math.isfinite(level):
        raise AudioLevelError(f"audio.{key} must be a finite number: got {value!r}")
    if not 0.0 <= level <= MAX_VOLUME:
        raise AudioLevelError(
            f"audio.{key} must be between 0 and 1 (0 silences the effect, "
            f"1 is full scale): got {level}"
        )
    return level


@dataclass(frozen=True)
class AudioLevels:
    """Every level the game plays at, as configured for one run.

    Defaults are the values the shipped config files carry, so a fabricated
    config with no ``audio`` section (or a title screen that beeps before a
    difficulty exists) sounds exactly like the shipped game rather than like a
    test fixture.
    """

    master_volume: float = 0.8
    confirm_beep: float = 0.25
    weapon_fire: float = 0.3
    ship_impact: float = 0.35
    ship_destruction: float = 0.5
    scan_klaxon: float = 0.4
    jump_spinup: float = 0.32
    jump_thunderclap: float = 0.55

    def __post_init__(self) -> None:
        """Validate levels that arrive through the dataclass constructor too.

        :meth:`from_config` is not the only door: tests and tooling construct
        these directly, and a level of 3.0 passed straight in would otherwise
        be silently clamped away at the mixer and never reported.
        """
        for field in fields(self):
            object.__setattr__(
                self,
                field.name,
                _validated_volume(field.name, getattr(self, field.name)),
            )

    # ------------------------------------------------------------------
    @classmethod
    def from_config(cls, audio_config: Mapping[str, Any]) -> "AudioLevels":
        """Build the levels from a config's ``audio`` section.

        Unknown keys are fatal rather than ignored: the loader's ``extra =
        "forbid"`` already rejects them in a file, but this method is also the
        door that tests and tooling walk through, and a typo'd key that quietly
        falls back to the default is how "I turned the explosions down" ends up
        meaning "I turned nothing down".

        Missing keys take the code default, which is the same number the shipped
        files carry.
        """
        known = {MASTER_VOLUME_KEY, *SOUND_IDS}
        unknown = sorted(set(audio_config) - known)
        if unknown:
            raise AudioLevelError(
                f"unknown audio key(s) {unknown}; expected any of {sorted(known)}"
            )
        levels = {
            key: _validated_volume(key, value)
            for key, value in audio_config.items()
            if key in known
        }
        return cls(**levels)

    # ------------------------------------------------------------------
    def level_for(self, sound_id: str) -> float:
        """The volume to hand the mixer for ``sound_id``: master x level.

        Refuses an unknown id instead of returning 0.0. Silence is a perfectly
        normal config value, which is exactly why a typo must not be allowed to
        look like one.
        """
        if sound_id not in SOUND_IDS:
            raise AudioLevelError(
                f"no such sound {sound_id!r}; expected one of {list(SOUND_IDS)}"
            )
        level = getattr(self, sound_id) * self.master_volume
        # Both factors are already in [0, 1], so this can only ever round off.
        return min(MAX_VOLUME, max(0.0, level))

    @property
    def silent(self) -> bool:
        """Whether every sound in the game is configured away.

        ``AudioSystem`` uses this to skip generating buffers it will never play:
        a config that mutes everything should not pay for 250 000 samples of
        maths on the first shot.
        """
        return all(self.level_for(sound_id) == 0.0 for sound_id in SOUND_IDS)

    def as_dict(self) -> dict:
        """Plain-dict form, for logging, debugging overlays, and round-tripping."""
        return {field.name: getattr(self, field.name) for field in fields(self)}

    @classmethod
    def keys(cls) -> Tuple[str, ...]:
        """Every key the ``audio`` section accepts, in config order."""
        return (MASTER_VOLUME_KEY, *SOUND_IDS)
