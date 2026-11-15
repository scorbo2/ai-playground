"""Fail-soft audio system using stdlib array + pygame.mixer.Sound.

Audio mixer init failure is never fatal. All public methods silently
succeed when audio is unavailable (e.g. under the dummy audio driver in
the test suite).
"""

import array
import math
import random as _random_lib

import pygame


def _generate_beep(
    freq: float = 880.0,
    duration_ms: int = 80,
    volume: float = 0.25,
    sample_rate: int = 44100,
) -> "array.array[int]":
    """Generate a sine-wave beep as a signed 16-bit mono array.

    A short linear fade-out removes the click artefact at the end.
    """
    n_samples = int(sample_rate * duration_ms / 1000)
    buf: array.array = array.array("h", [0] * n_samples)
    for i in range(n_samples):
        t = i / sample_rate
        fade = 1.0 - i / n_samples
        val = int(32767 * volume * fade * math.sin(2.0 * math.pi * freq * t))
        buf[i] = max(-32768, min(32767, val))
    return buf


# Gains live in code for now, matching the Stage 2 confirm beep. Stage 12 is the
# dedicated audio pass and owns moving every gain into config; until then there
# is exactly one place to look for each number.
_JUMP_SPINUP_GAIN = 0.32
_THUNDERCLAP_GAIN = 0.55

# The spin-up runs slightly *shorter* than the 180-frame (3 s) burn so the sweep
# tops out just before the white-out; the thunderclap then lands on the flash.
_JUMP_SPINUP_MS = 2600
_THUNDERCLAP_MS = 900


def _clamp_int16(value: float) -> int:
    """Hard-clip a float sample into the signed 16-bit range."""
    return max(-32768, min(32767, int(value)))


def _generate_jump_spinup(
    duration_ms: int = _JUMP_SPINUP_MS,
    volume: float = _JUMP_SPINUP_GAIN,
    start_freq: float = 130.0,
    end_freq: float = 1150.0,
    sample_rate: int = 44100,
) -> "array.array[int]":
    """A rising engine sweep: the ship spooling up to hyperspace.

    The frequency ramps *exponentially* (start_freq * ratio^t) rather than
    linearly: a linear ramp sounds like a siren, an exponential one sounds like
    an engine, because equal time spans cover equal musical intervals.
    Amplitude climbs with the pitch and the last few percent fade out so the
    cut into the thunderclap does not click.
    """
    n_samples = int(sample_rate * duration_ms / 1000)
    buf: array.array = array.array("h", [0] * n_samples)
    ratio = end_freq / start_freq
    phase = 0.0
    for i in range(n_samples):
        progress = i / n_samples
        freq = start_freq * (ratio ** progress)
        phase += 2.0 * math.pi * freq / sample_rate
        # A second, detuned partial a fifth up turns a bare sine into something
        # mechanical rather than something like a phone signal.
        envelope = progress ** 0.6
        if progress > 0.94:
            envelope *= (1.0 - progress) / 0.06
        wave = math.sin(phase) + 0.35 * math.sin(phase * 1.5)
        buf[i] = _clamp_int16(32767 * volume * envelope * wave * 0.6)
    return buf


def _generate_thunderclap(
    duration_ms: int = _THUNDERCLAP_MS,
    volume: float = _THUNDERCLAP_GAIN,
    rumble_freq: float = 46.0,
    sample_rate: int = 44100,
) -> "array.array[int]":
    """A thunderclap: a crack of noise over a decaying sub-bass rumble.

    Two components, because a clap is not one sound:
      * broadband noise that decays fast (the "crack"), low-passed by mixing
        each sample with its neighbour so it is a boom and not a hi-hat;
      * a very low sine that decays slowly (the rumble you feel in the chest).

    The noise comes from a fixed-seed RNG so the buffer is byte-identical every
    run: a sound that changes between launches cannot be tested by digest.
    """
    n_samples = int(sample_rate * duration_ms / 1000)
    rng = _random_lib.Random(20240611)
    buf: array.array = array.array("h", [0] * n_samples)
    previous_noise = 0.0
    for i in range(n_samples):
        t = i / sample_rate
        progress = i / n_samples
        # Fast attack, long exponential tail: exp(-6) is inaudible by the end.
        crack = math.exp(-6.0 * progress)
        noise = rng.uniform(-1.0, 1.0)
        # Cheap one-pole low-pass: unfiltered white noise is painful at 55% gain.
        smoothed = 0.65 * noise + 0.35 * previous_noise
        previous_noise = noise
        rumble = math.sin(2.0 * math.pi * rumble_freq * t) * math.exp(-2.2 * progress)
        # The initial transient is the loudest thing in the mix, which is what
        # makes it read as a *clap* rather than as distant weather.
        sample = (0.62 * smoothed * crack + 0.55 * rumble) * (1.0 - progress ** 3)
        buf[i] = _clamp_int16(32767 * volume * sample)
    return buf


class AudioSystem:
    """Wrapper around pygame.mixer that fails softly if unavailable."""

    def __init__(self) -> None:
        self._available = False
        self._confirm_sound: "pygame.mixer.Sound | None" = None
        # Buffers are generated on first use, not at construction: the jump and
        # thunderclap sweeps are ~150k samples each of pure Python maths, and
        # making the title screen wait half a second for a sound the player may
        # never hear is a bad trade.
        self._sounds: dict = {}
        try:
            pygame.mixer.init(frequency=44100, size=-16, channels=1, buffer=512)
            self._available = True
            beep_buf = _generate_beep()
            self._confirm_sound = pygame.mixer.Sound(buffer=beep_buf)
        except Exception:
            pass

    @property
    def available(self) -> bool:
        return self._available

    def play_confirm(self) -> None:
        """Play the UI confirmation beep (no-op if audio is unavailable)."""
        if self._available and self._confirm_sound is not None:
            try:
                self._confirm_sound.play()
            except Exception:
                pass

    def play_jump_spinup(self) -> None:
        """The hyperspace spool-up, started with the burn (fail-soft)."""
        self._play_lazy("jump_spinup", _generate_jump_spinup)

    def play_thunderclap(self) -> None:
        """The arrival boom, fired on the frame the screen goes white (fail-soft)."""
        self._play_lazy("thunderclap", _generate_thunderclap)

    def _play_lazy(self, name: str, buffer_factory) -> None:
        """Build (once) then play a generated buffer, swallowing any mixer failure."""
        if not self._available:
            return
        try:
            sound = self._sounds.get(name)
            if sound is None:
                sound = pygame.mixer.Sound(buffer=buffer_factory())
                self._sounds[name] = sound
            sound.play()
        except Exception:
            # Audio is never fatal: a game that cannot make a sound still plays.
            pass
