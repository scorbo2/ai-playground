"""The mixer layer: what plays a sound, when, and how loud — fail-soft, always.

Stage 12's audio comes in three modules, and this is the only one of them allowed
to touch ``pygame.mixer``:

* :mod:`src.audio_buffers` — the waveforms. Pure stdlib synthesis, no pygame, no
  config; a test (and a machine with no audio hardware) can exercise it directly.
* :mod:`src.model.audio_levels` — the policy: which effects exist and how loud
  each may be, validated at startup by the config loader.
* **this module** — the mixer: the mixer's lifetime, the per-sound buffer cache,
  the format negotiation with whatever device the machine actually has, and the
  ``play_*`` verbs the scenes call.

Levels are applied with ``Sound.set_volume`` rather than baked into the samples,
so a config change costs one mixer call instead of another synthesis pass, and
"0.4" means the same loudness for an explosion as for a beep (every buffer is
peak-normalised in :mod:`src.audio_buffers` for exactly that reason).

Audio is **never** fatal. Every mixer call is wrapped, so a machine with no audio
device, a mixer that refuses to initialise, a driver reporting a format this
module cannot feed, or a ``Sound()`` that explodes mid-frame all leave the game
running silently. The one concession to debuggability is :data:`AUDIO_DEBUG_ENV`:
set it and the swallowed exceptions go to stderr, which is the only way to tell
"the mixer is broken" apart from "the mixer is configured to be silent".
"""

from __future__ import annotations

import array
import os
import sys
from typing import Dict, Tuple

import pygame

from src.audio_buffers import BUFFER_GENERATORS, DEFAULT_SAMPLE_RATE
from src.model.audio_levels import (
    SOUND_CONFIRM_BEEP,
    SOUND_JUMP_SPINUP,
    SOUND_JUMP_THUNDERCLAP,
    SOUND_SCAN_KLAXON,
    SOUND_SHIP_DESTRUCTION,
    SOUND_SHIP_IMPACT,
    SOUND_WEAPON_FIRE,
    AudioLevels,
)

# Set this environment variable to have the deliberately-swallowed audio errors
# printed to stderr. Off by default: an unsolvable audio problem should degrade
# the game quietly, not spam a terminal, but it must not be *undiagnosable*.
AUDIO_DEBUG_ENV = "COLLABBOB_AUDIO_DEBUG"

# Mixer voice count. SDL's default is 8, and a system with four ships plus the
# player can easily have six explosions and a klaxon wanting a voice at once;
# the extra cost is negligible, and a dropped gunshot is a dropped *event*.
MIXER_VOICE_COUNT = 16

# Requested mixer format. Mono 16-bit is what the generators emit, so no
# conversion is needed on the normal path (see _match_mixer for the fallback).
_MIXER_FREQUENCY = DEFAULT_SAMPLE_RATE
_MIXER_SAMPLE_BITS = -16
_MIXER_CHANNELS = 1


def _debug_enabled() -> bool:
    return bool(os.environ.get(AUDIO_DEBUG_ENV))


def _warn(context: str, exc: BaseException) -> None:
    """Report a swallowed audio failure, but only to whoever asked to hear it."""
    if _debug_enabled():
        print(f"[audio] {context}: {type(exc).__name__}: {exc}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Mixer format handling
# ---------------------------------------------------------------------------


def _mixer_format() -> "Tuple[int, int] | None":
    """The format the mixer actually came up with, as ``(sample_rate, channels)``.

    ``Sound(buffer=...)`` does not resample: it assumes the buffer is already in
    the mixer's format. Requesting 44.1 kHz mono usually gets you exactly that,
    but a device that overrides the request would otherwise turn a 0.9 s boom
    into a 0.45 s squeak (a mono buffer read as stereo halves its length).
    Returning None means "this mixer cannot be fed the buffers we generate", and
    the caller treats that as *no audio*, never as a crash.
    """
    try:
        initialisation = pygame.mixer.get_init()
    except Exception as exc:  # pragma: no cover - driver-dependent
        _warn("mixer get_init", exc)
        return None
    if not initialisation:
        return None
    frequency, sample_bits, channels = initialisation
    if abs(int(sample_bits)) != 16:
        _warn(
            "mixer sample size",
            ValueError(
                f"mixer came up at {sample_bits} bits; only 16-bit buffers are generated"
            ),
        )
        return None
    return int(frequency), int(channels)


def _match_mixer(buffer: array.array, channels: int) -> array.array:
    """Duplicate mono samples if the mixer insisted on more than one channel.

    The rare path: we ask for mono, and mono is what SDL gives us unless the
    device refuses. The loop is O(n) Python, which is acceptable precisely
    because it almost never runs.
    """
    if channels <= 1:
        return buffer
    interleaved = array.array("h", [0]) * (len(buffer) * channels)
    for index, sample in enumerate(buffer):
        for voice in range(channels):
            interleaved[index * channels + voice] = sample
    return interleaved


# ---------------------------------------------------------------------------
# Playback
# ---------------------------------------------------------------------------


class AudioSystem:
    """Every sound the game makes, fail-soft, at the levels the config asked for.

    Sounds are generated lazily on first use and cached: the jump sweep alone is
    ~115 000 samples of pure-Python maths, and making the title screen wait for a
    sound the player may never trigger is a bad trade.

    ``apply_levels`` exists because the levels belong to a *run*, and a run does
    not exist until the player has picked a difficulty: anything the title screen
    and the difficulty dialog play runs at the defaults.
    """

    def __init__(self, levels: "AudioLevels | None" = None) -> None:
        self.levels = levels if levels is not None else AudioLevels()
        self._available = False
        self._sample_rate = _MIXER_FREQUENCY
        self._channels = _MIXER_CHANNELS
        self._sounds: Dict[str, pygame.mixer.Sound] = {}
        try:
            pygame.mixer.init(
                frequency=_MIXER_FREQUENCY,
                size=_MIXER_SAMPLE_BITS,
                channels=_MIXER_CHANNELS,
                buffer=512,
            )
            format_ = _mixer_format()
            if format_ is None:
                return
            self._sample_rate, self._channels = format_
            pygame.mixer.set_num_channels(MIXER_VOICE_COUNT)
            self._available = True
        except Exception as exc:
            # Audio is never fatal: a game that cannot make a sound still plays.
            _warn("mixer init", exc)
            self._available = False

    # ------------------------------------------------------------------
    @property
    def available(self) -> bool:
        """Whether a usable mixer is up (not whether anything is audible)."""
        return self._available

    def apply_levels(self, levels: AudioLevels) -> None:
        """Adopt a new set of levels, re-levelling anything already generated.

        Called by :class:`~src.scenes.game_scene.GameScene` when a run starts, and
        by nothing else during a session. Cached buffers are kept: the level is
        mixer state, so re-reading a config costs one ``set_volume`` per loaded
        sound rather than a fresh synthesis pass.
        """
        if not isinstance(levels, AudioLevels):
            raise TypeError(
                "apply_levels expects an AudioLevels; got "
                f"{type(levels).__name__} (call AudioLevels.from_config first)"
            )
        self.levels = levels
        for name, sound in self._sounds.items():
            self._set_volume(name, sound)

    def loaded_volumes(self) -> Dict[str, float]:
        """Levels currently applied to the sounds that have been generated.

        Introspection for tests and for a future debug overlay. Read from the
        mixer rather than echoed from the config, so a driver that quantises
        volume is reported honestly.
        """
        volumes: Dict[str, float] = {}
        for name, sound in self._sounds.items():
            try:
                volumes[name] = float(sound.get_volume())
            except Exception as exc:  # pragma: no cover - defensive
                _warn(f"get_volume {name}", exc)
        return volumes

    # ------------------------------------------------------------------
    def play(self, sound_id: str) -> None:
        """Play one of the registered effects. Never raises, never blocks."""
        try:
            level = self.levels.level_for(sound_id)
        except Exception as exc:  # an unknown id is a programming error: say so
            _warn(f"unknown sound id {sound_id!r}", exc)
            return
        if not self._available or level == 0.0:
            # A muted effect costs nothing at all: no buffer, no voice, no maths.
            return
        try:
            sound = self._sounds.get(sound_id)
            if sound is None:
                sound = self._build(sound_id)
                if sound is None:
                    return
            sound.play()
        except Exception as exc:
            _warn(f"play {sound_id}", exc)

    def _build(self, sound_id: str) -> "pygame.mixer.Sound | None":
        """Generate (once) and cache the buffer for one sound id."""
        factory = BUFFER_GENERATORS.get(sound_id)
        if factory is None:
            _warn(f"no generator registered for {sound_id!r}", ValueError("missing"))
            return None
        try:
            buffer = _match_mixer(factory(self._sample_rate), self._channels)
            sound = pygame.mixer.Sound(buffer=buffer)
        except Exception as exc:
            # Leave nothing cached: a half-built sound must not be remembered as
            # a permanent silence.
            self._sounds.pop(sound_id, None)
            _warn(f"generate {sound_id}", exc)
            return None
        self._set_volume(sound_id, sound)
        self._sounds[sound_id] = sound
        return sound

    def _set_volume(self, sound_id: str, sound: "pygame.mixer.Sound") -> None:
        try:
            sound.set_volume(self.levels.level_for(sound_id))
        except Exception as exc:  # pragma: no cover - defensive
            _warn(f"set_volume {sound_id}", exc)

    # ------------------------------------------------------------------
    # The verbs the scenes call. Each is one sound id, named as the event rather
    # than as the waveform, so a scene reads as sentences: "play_impact".
    # ------------------------------------------------------------------
    def play_confirm(self) -> None:
        """UI confirmation beep: a selection happened in a modal."""
        self.play(SOUND_CONFIRM_BEEP)

    def play_weapon_fire(self) -> None:
        """Any ship's gun firing — including ships off-screen (spec)."""
        self.play(SOUND_WEAPON_FIRE)

    def play_impact(self) -> None:
        """A round landed on a hull: the small explosion."""
        self.play(SOUND_SHIP_IMPACT)

    def play_destruction(self) -> None:
        """A hull came apart: the large explosion."""
        self.play(SOUND_SHIP_DESTRUCTION)

    def play_klaxon(self) -> None:
        """The ``T`` alarm, for a hostile contact only."""
        self.play(SOUND_SCAN_KLAXON)

    def play_jump_spinup(self) -> None:
        """The hyperspace spool-up, started with the burn."""
        self.play(SOUND_JUMP_SPINUP)

    def play_thunderclap(self) -> None:
        """The arrival boom, on the frame the screen goes white."""
        self.play(SOUND_JUMP_THUNDERCLAP)
