"""Every sound effect in the game, synthesised from stdlib maths — and no pygame.

Stage 12's audio is three layers, split by what each is allowed to depend on:

* **this module** — pure synthesis: :mod:`array`, :mod:`math`, and a seeded
  :mod:`random`. No pygame, no config, no mixer. That is not purity for its own
  sake: it is what lets ``scripts/render_audio_buffers.py`` dump a WAV of every
  effect on a machine (or in a CI container) that has no audio device and no
  display, and it means the buffer-generation tests are arithmetic rather than
  audio-hardware tests. There is a test that pins the "imports without pygame"
  claim, because a boundary nobody can enforce is a boundary that moves.
* :mod:`src.model.audio_levels` — the policy: which effects exist, and how loud
  each one is allowed to be.
* :mod:`src.audio` — the mixer: buffer cache, mixer lifetime, and the levels
  applied with ``Sound.set_volume``.

Loudness policy is deliberately absent here. Every buffer is peak-normalised to
:data:`_REFERENCE_PEAK` (95% of full scale, leaving SDL headroom for the voices it
sums), so a configured level of 0.4 lands at the same perceived loudness for an
explosion as for a beep, and a level change never invalidates a cached buffer.

The noise in the explosions comes from :class:`random.Random` instances with fixed
seeds, one per effect. That makes every buffer byte-identical run to run, which is
what makes them assertable — and it is why the seeds are *different* per effect:
three booms that share a seed are one boom played three times.

One exception to "no config, no policy": the registry keys below are the id
constants from :mod:`src.model.audio_levels`. The config key, the argument to
``AudioLevels.level_for``, and the generator name are the same string, and the
module that owns the vocabulary declares it. That import pulls in four string
constants and no pygame.
"""

import array
import math
import random as _random_lib
import wave
from typing import Callable, Dict, List, Sequence

from src.model.audio_levels import (
    SOUND_CONFIRM_BEEP,
    SOUND_JUMP_SPINUP,
    SOUND_JUMP_THUNDERCLAP,
    SOUND_SCAN_KLAXON,
    SOUND_SHIP_DESTRUCTION,
    SOUND_SHIP_IMPACT,
    SOUND_WEAPON_FIRE,
)

# Buffers are generated at a fixed reference peak and turned down by the mixer.
# 95% of full scale leaves a little headroom for SDL's own mixing of overlapping
# voices (six ships firing at once is six buffers summed by SDL, not by us).
_REFERENCE_PEAK = int(32767 * 0.95)

# The rate every buffer is generated at. ``pygame.mixer.Sound(buffer=...)`` does no
# resampling, so this and the mixer's rate have to agree; ``_mixer_format`` in
# :mod:`src.audio` is the authority at runtime, and asks for this one.
DEFAULT_SAMPLE_RATE = 44100

# Effect lengths. Tuned by ear against the frame rate: the klaxon has to be
# readable while the player is already pressing T again, and the destruction boom
# has to outlast the particle burst it accompanies (Stage 11's biggest burst runs
# ~40 frames, i.e. 0.67 s).
_BEEP_MS = 90
_WEAPON_FIRE_MS = 150
_SHIP_IMPACT_MS = 280
_SHIP_DESTRUCTION_MS = 900
_SCAN_KLAXON_MS = 760
_JUMP_SPINUP_MS = 2600
_THUNDERCLAP_MS = 900

# The spin-up runs slightly *shorter* than the 180-frame (3 s) burn so the sweep
# tops out just before the white-out; the thunderclap lands on the flash.
_JUMP_SPINUP_START_FREQ = 130.0
_JUMP_SPINUP_END_FREQ = 1150.0


def _sample_count(duration_ms: int, sample_rate: int) -> int:
    return max(1, int(sample_rate * duration_ms / 1000))


def _clamp_int16(value: float) -> int:
    """Hard-clip a float sample into the signed 16-bit range."""
    return max(-32768, min(32767, int(value)))


def _normalize(samples: Sequence[float], target_peak: int = _REFERENCE_PEAK) -> array.array:
    """Scale a float mix down to int16 so its loudest sample sits at the target.

    Normalising *before* the clip rather than after is the whole point: a mix that
    peaks at 1.4 would otherwise be flattened into distortion, and every effect
    would arrive at the mixer at a different loudness for reasons nobody configured.
    """
    peak = max((abs(value) for value in samples), default=0.0)
    if peak == 0.0:
        return array.array("h", [0] * len(samples))
    scale = target_peak / peak
    return array.array("h", (_clamp_int16(value * scale) for value in samples))


def _attack_ramp(index: int, attack_samples: int) -> float:
    """A 0→1 ramp over the first ``attack_samples`` samples.

    Every generated sound starts at full amplitude in its first sample or two,
    which is a click: a discontinuity of that size is heard as a pop and seen as
    a spectral splash. Four milliseconds is short enough to stay percussive.
    """
    if attack_samples <= 1:
        return 1.0
    return min(1.0, index / attack_samples)


# ---------------------------------------------------------------------------
# Synthesis
# ---------------------------------------------------------------------------


def _generate_beep(
    sample_rate: int,
    *,
    duration_ms: int = _BEEP_MS,
    freq: float = 880.0,
    attack_ms: float = 2.0,
) -> array.array:
    """The UI confirmation beep: one short tone with a fade-out and a fade-in.

    A plain sine because this is interface feedback, not drama. The linear
    fade-out kills the end click; :func:`_attack_ramp` kills the start one.
    """
    n = _sample_count(duration_ms, sample_rate)
    attack_samples = max(1, int(sample_rate * attack_ms / 1000))
    values: List[float] = []
    for i in range(n):
        t = i / sample_rate
        fade = 1.0 - i / n
        values.append(math.sin(2.0 * math.pi * freq * t) * fade * _attack_ramp(i, attack_samples))
    return _normalize(values)


def _generate_explosion(
    sample_rate: int,
    *,
    duration_ms: int,
    crack_decay: float,
    rumble_freq: float,
    rumble_decay: float = 2.2,
    noise_smooth: float = 0.65,
    debris: float = 0.0,
    hiss_smooth: float = 0.0,
    second_crack_at: float = 0.0,
    second_crack_scale: float = 0.7,
    attack_ms: float = 4.0,
    seed: int,
) -> array.array:
    """One generator for every boom in the game: impact, wreck, and thunderclap.

    A boom is not one sound, so it is not built from one component:

    * **crack** — broadband noise, low-passed by mixing each sample with its
      neighbour so it reads as a concussion rather than a hi-hat, decaying fast;
    * **rumble** — a low sine with a much slower decay: the part you feel;
    * **debris** — the high-passed complement of the same noise (``noise -
      smoothed`` is exactly what the low-pass threw away), which is what makes a
      *breaking hull* audibly different from distant weather; ``hiss_smooth``
      dulls only this component, because raw differentiated white noise is a
      surgical hiss that no hull actually makes,
    * **second crack** — an optional delayed repeat. A wreck lands two blows
      (structure, then the fuel); an arrival does not.

    The noise comes from a fixed-seed RNG, so the buffer is byte-identical every
    run: a sound that changes between launches cannot be pinned by a digest.
    """
    n = _sample_count(duration_ms, sample_rate)
    attack_samples = max(1, int(sample_rate * attack_ms / 1000))
    rng = _random_lib.Random(seed)
    values: List[float] = []
    previous_noise = 0.0
    previous_hiss = 0.0

    for i in range(n):
        progress = i / n
        t = i / sample_rate

        noise = rng.uniform(-1.0, 1.0)
        smoothed = noise_smooth * noise + (1.0 - noise_smooth) * previous_noise
        bright = noise - smoothed
        if hiss_smooth:
            bright = hiss_smooth * bright + (1.0 - hiss_smooth) * previous_hiss
        previous_hiss = bright
        previous_noise = noise

        crack = math.exp(-crack_decay * progress)
        if second_crack_at and progress >= second_crack_at:
            crack += second_crack_scale * math.exp(
                -crack_decay * (progress - second_crack_at)
            )
        rumble = math.sin(2.0 * math.pi * rumble_freq * t) * math.exp(
            -rumble_decay * progress
        )

        value = (0.62 * smoothed + debris * bright) * crack + 0.55 * rumble
        value *= (1.0 - progress**3) * _attack_ramp(i, attack_samples)
        values.append(value)

    return _normalize(values)


def _generate_ship_impact(
    sample_rate: int, *, duration_ms: int = _SHIP_IMPACT_MS, seed: int = 20240612
) -> array.array:
    """A small explosion: a round landing on shields or armour.

    Short, bright, and mid-pitched — deliberately the same generator as the
    wreck, with different parameters, because "bigger" here is a matter of
    decay, pitch, and debris rather than of a different idea.
    """
    return _generate_explosion(
        sample_rate,
        duration_ms=duration_ms,
        crack_decay=11.0,
        rumble_freq=95.0,
        rumble_decay=3.5,
        noise_smooth=0.55,
        debris=0.5,
        hiss_smooth=0.5,
        seed=seed,
    )


def _generate_ship_destruction(
    sample_rate: int, *, duration_ms: int = _SHIP_DESTRUCTION_MS, seed: int = 20240613
) -> array.array:
    """A large explosion: a hull coming apart.

    Three times the impact's length, half its rumble pitch, a second crack a
    quarter of the way in, and a debris hiss on top. Loudness is *not* how this
    is distinguished — the mixer applies a configured level to both — so the
    difference has to be in the waveform or the player cannot tell a hit from a
    kill with their eyes closed.
    """
    return _generate_explosion(
        sample_rate,
        duration_ms=duration_ms,
        crack_decay=3.4,
        rumble_freq=38.0,
        rumble_decay=2.0,
        noise_smooth=0.72,
        debris=0.9,
        hiss_smooth=0.6,
        second_crack_at=0.24,
        second_crack_scale=0.75,
        seed=seed,
    )


def _generate_thunderclap(
    sample_rate: int, *, duration_ms: int = _THUNDERCLAP_MS, seed: int = 20240611
) -> array.array:
    """The hyperspace arrival boom: a big crack over a deep, slow rumble.

    No debris hiss and no second crack: this is the ship arriving, not something
    breaking. Same generator as the two combat booms, deliberately distinct
    parameters (see DECISIONS.md, Stage 12).
    """
    return _generate_explosion(
        sample_rate,
        duration_ms=duration_ms,
        crack_decay=6.0,
        rumble_freq=46.0,
        rumble_decay=2.2,
        noise_smooth=0.65,
        debris=0.0,
        seed=seed,
    )


def _generate_weapon_fire(
    sample_rate: int,
    *,
    duration_ms: int = _WEAPON_FIRE_MS,
    start_freq: float = 760.0,
    end_freq: float = 120.0,
    decay: float = 7.0,
    crack_decay: float = 45.0,
    seed: int = 20240614,
) -> array.array:
    """A gunshot: a crack of muzzle blast over a falling-tone cannon thump.

    The tone sweeps *down* (exponentially, so it sounds like a report and not a
    siren) and decays exponentially, which is what a 3px round leaving a muzzle
    looks like in sound. The noise transient lives for only a few milliseconds:
    without it the effect is a cartoon "pew", with it the effect is a gunshot.
    """
    n = _sample_count(duration_ms, sample_rate)
    attack_samples = max(1, int(sample_rate * 2.0 / 1000))
    rng = _random_lib.Random(seed)
    values: List[float] = []
    phase = 0.0
    ratio = end_freq / start_freq

    for i in range(n):
        progress = i / n
        freq = start_freq * (ratio**progress)
        phase += 2.0 * math.pi * freq / sample_rate
        # A sine plus its own low harmonics: a bare sine sounds like a phone
        # signal, harmonics make it a weapon.
        tone = (
            math.sin(phase)
            + 0.4 * math.sin(2.0 * phase)
            + 0.25 * math.sin(3.0 * phase)
        )
        noise = rng.uniform(-1.0, 1.0)
        value = 0.55 * tone * math.exp(-decay * progress)
        value += 0.55 * noise * math.exp(-crack_decay * progress)
        values.append(value * _attack_ramp(i, attack_samples))

    return _normalize(values)


def _generate_scan_klaxon(
    sample_rate: int,
    *,
    duration_ms: int = _SCAN_KLAXON_MS,
    low_freq: float = 470.0,
    high_freq: float = 690.0,
    pulses: int = 4,
    ramp_ms: float = 6.0,
) -> array.array:
    """A two-tone alarm: the "you are looking at something that wants you dead" cue.

    Two frequencies alternate in equal segments, each segment ramped up and down
    at its edges. The ramps are not decoration — a hard gate on a tone is a click,
    and the frequency is *held* constant within a segment (only its rate changes at
    a boundary, never its phase) so the alternation stays clean. The odd harmonics
    are what make an alarm an alarm rather than a test tone.
    """
    n = _sample_count(duration_ms, sample_rate)
    segment = n / max(1, pulses)
    ramp = max(1.0, sample_rate * ramp_ms / 1000) / segment
    values: List[float] = []
    phase = 0.0

    for i in range(n):
        pulse = int(i // segment)
        local = (i - pulse * segment) / segment
        freq = low_freq if pulse % 2 == 0 else high_freq
        phase += 2.0 * math.pi * freq / sample_rate
        tone = (
            math.sin(phase)
            + 0.33 * math.sin(3.0 * phase)
            + 0.2 * math.sin(5.0 * phase)
        )
        edge = min(1.0, local / ramp, (1.0 - local) / ramp)
        values.append(tone * max(0.0, edge))

    return _normalize(values)


def _generate_jump_spinup(
    sample_rate: int,
    *,
    duration_ms: int = _JUMP_SPINUP_MS,
    start_freq: float = _JUMP_SPINUP_START_FREQ,
    end_freq: float = _JUMP_SPINUP_END_FREQ,
) -> array.array:
    """A rising engine sweep: the ship spooling up to hyperspace.

    The frequency ramps *exponentially* (start_freq * ratio^t) rather than
    linearly: a linear ramp sounds like a siren, an exponential one sounds like
    an engine, because equal time spans cover equal musical intervals. Amplitude
    climbs with the pitch and the last few percent fade out so the cut into the
    thunderclap does not click.
    """
    n = _sample_count(duration_ms, sample_rate)
    ratio = end_freq / start_freq
    values: List[float] = []
    phase = 0.0

    for i in range(n):
        progress = i / n
        freq = start_freq * (ratio**progress)
        phase += 2.0 * math.pi * freq / sample_rate
        # A second, detuned partial a fifth up turns a bare sine into something
        # mechanical rather than something like a phone signal.
        envelope = progress**0.6
        if progress > 0.94:
            envelope *= (1.0 - progress) / 0.06
        wave = math.sin(phase) + 0.35 * math.sin(phase * 1.5)
        values.append(envelope * wave)

    return _normalize(values)


# Sound id -> buffer factory. Adding an effect means adding one generator and
# one entry here, plus a key in the config's ``audio`` section and a ``play_*``
# verb on AudioSystem; there is no fourth place on purpose.
BUFFER_GENERATORS: Dict[str, Callable[[int], array.array]] = {
    SOUND_CONFIRM_BEEP: _generate_beep,
    SOUND_WEAPON_FIRE: _generate_weapon_fire,
    SOUND_SHIP_IMPACT: _generate_ship_impact,
    SOUND_SHIP_DESTRUCTION: _generate_ship_destruction,
    SOUND_SCAN_KLAXON: _generate_scan_klaxon,
    SOUND_JUMP_SPINUP: _generate_jump_spinup,
    SOUND_JUMP_THUNDERCLAP: _generate_thunderclap,
}


def write_wav(
    path: str,
    samples: Sequence[int],
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    channels: int = 1,
) -> None:
    """Write signed 16-bit PCM samples to a WAV file (tooling, not gameplay).

    Used by ``scripts/render_audio_buffers.py`` so a human can actually *listen*
    to a generated effect without playing the game. No pygame involved.
    """
    buffer = array.array("h", samples)
    with wave.open(path, "wb") as handle:
        handle.setnchannels(channels)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(buffer.tobytes())
