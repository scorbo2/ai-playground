"""Fail-soft audio system using stdlib array + pygame.mixer.Sound.

Audio mixer init failure is never fatal. All public methods silently
succeed when audio is unavailable (e.g. under the dummy audio driver in
the test suite).
"""

import array
import math

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


class AudioSystem:
    """Wrapper around pygame.mixer that fails softly if unavailable."""

    def __init__(self) -> None:
        self._available = False
        self._confirm_sound: "pygame.mixer.Sound | None" = None
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
