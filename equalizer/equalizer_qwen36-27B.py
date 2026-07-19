#!/usr/bin/env python3
"""
equalizer.py — Fullscreen media player with real-time graphic equalizer overlay.

Usage:
    python equalizer.py <image_path> <audio_path> [--screen <index>]

Press ESC to quit. Press 'b' to toggle the bonus particle effect.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

import logging
from pathlib import Path
from typing import List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# PyQt6 imports
# ---------------------------------------------------------------------------
from PyQt6.QtCore import (
    Qt,
    QTimer,
    QUrl,
    QEvent,
    QPointF,
    QRectF,
)
from PyQt6.QtGui import (
    QScreen,
    QImage,
    QPainter,
    QColor,
    QPen,
    QBrush,
    QLinearGradient,
    QPolygonF,
)
from PyQt6.QtMultimedia import QMediaPlayer, QAudioOutput
from PyQt6.QtWidgets import QWidget, QApplication

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
log = logging.getLogger("equalizer")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
NUM_BARS: int = 24
FFT_SIZE: int = 2048
UPDATE_INTERVAL_MS: int = 16  # ~60 Hz
DECAY_FACTOR: float = 0.78     # previous-frame energy carry-over
PARTICLE_COUNT: int = 300


# ===================================================================
# Audio decoding helpers
# ===================================================================
def decode_audio_to_pcm(audio_path: str, sample_rate: int = 44100) -> np.ndarray:
    """Decode an audio file to a mono float32 PCM array via ffmpeg.

    The returned array is normalised to approximately [-1, 1].
    """
    cmd = [
        "ffmpeg",
        "-i", audio_path,
        "-f", "f32le",
        "-ac", "1",
        "-ar", str(sample_rate),
        "-",
    ]
    result = subprocess.run(cmd, capture_output=True)
    if result.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed to decode '{audio_path}':\n{result.stderr.decode(errors='replace')}"
        )
    raw = result.stdout
    if len(raw) < 4:
        raise RuntimeError(f"Decoded audio is empty for '{audio_path}'")
    samples = np.frombuffer(raw, dtype=np.float32)
    return samples


def compute_fft_magnitude(samples: np.ndarray, position_ms: int, sr: int = 44100) -> np.ndarray:
    """Extract a short window around *position_ms* and return FFT magnitude bins.

    Uses a Hann window and returns the first half of the real-valued FFT
    magnitudes, normalised to [0, 1].
    """
    frame_len = FFT_SIZE
    sample_idx = int(position_ms * sr / 1000)
    end_idx = sample_idx + frame_len

    if sample_idx < 0 or sample_idx >= len(samples):
        return np.zeros(FFT_SIZE // 2)

    # Truncate if we're near the end of the track
    if end_idx > len(samples):
        frame_len = len(samples) - sample_idx
        if frame_len <= 0:
            return np.zeros(FFT_SIZE // 2)

    window = samples[sample_idx:sample_idx + frame_len]

    # Apply Hann window
    hann = np.hanning(len(window))
    windowed = window * hann

    # Zero-pad to FFT_SIZE if needed
    if len(windowed) < FFT_SIZE:
        padded = np.zeros(FFT_SIZE, dtype=np.float32)
        padded[:len(windowed)] = windowed
        windowed = padded

    fft_result = np.fft.rfft(windowed)
    magnitudes = np.abs(fft_result)

    # Normalise
    peak = magnitudes.max()
    if peak > 0:
        magnitudes /= peak

    return magnitudes


# ===================================================================
# Particle system (bonus visual)
# ===================================================================
class Particle:
    """A single audio-reactive particle."""

    __slots__ = ("x", "y", "vx", "vy", "size", "hue", "life", "max_life")

    def __init__(self, width: int, height: int) -> None:
        self.x: float = np.random.uniform(0, width)
        self.y: float = np.random.uniform(0, height)
        self.vx: float = np.random.uniform(-1.5, 1.5)
        self.vy: float = np.random.uniform(-2.5, -0.3)
        self.size: float = np.random.uniform(3, 8)
        self.hue: float = np.random.uniform(0, 360)
        self.life: float = 1.0
        self.max_life: float = np.random.uniform(150, 450)

    def update(self, energy: float, width: int, height: int) -> None:
        """Advance the particle one frame, influenced by *energy*."""
        self.hue = (self.hue + 0.5 + energy * 2) % 360
        self.vx += (np.random.uniform(-0.2, 0.2) + energy * 0.3)
        self.vy -= energy * 0.15
        self.x += self.vx
        self.y += self.vy
        self.life -= 1.0 / self.max_life

        # Wrap horizontally, respawn from bottom if too high
        if self.x < 0:
            self.x = width
        elif self.x > width:
            self.x = 0
        if self.y < -20:
            self.y = height + 10
            self.vy = np.random.uniform(0.5, 2.0)

    def is_alive(self) -> bool:
        return self.life > 0


class ParticleSystem:
    """Manages a pool of audio-reactive particles."""

    def __init__(self, width: int, height: int, count: int = PARTICLE_COUNT) -> None:
        self.width: int = width
        self.height: int = height
        self.particles: List[Particle] = [Particle(width, height) for _ in range(count)]

    def update(self, energy: float) -> None:
        for p in self.particles:
            p.update(energy, self.width, self.height)
            if not p.is_alive():
                p.__init__(self.width, self.height)

    def draw(self, painter: QPainter) -> None:
        for p in self.particles:
            # Clamp life-derived alpha to [0, 1] — p.life can dip slightly
            # negative before the respawn check in update().
            alpha = float(np.clip(p.life, 0.0, 1.0)) * 0.85
            hue_norm = float(np.clip(p.hue, 0.0, 360.0)) / 360.0
            color = QColor.fromHslF(hue_norm, 0.85, 0.7, alpha)
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(QPointF(p.x, p.y), p.size, p.size)


# ===================================================================
# Main visualizer widget
# ===================================================================
class EqualizerWidget(QWidget):
    """Fullscreen widget that renders the background image, audio-reactive
    equalizer bars, and an optional particle overlay."""

    def __init__(
        self,
        image_path: str,
        audio_path: str,
        screen_index: int,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self.image_path: str = image_path
        self.audio_path: str = audio_path
        self.screen_index: int = screen_index

        # State
        self.particles_enabled: bool = False
        self.particle_system: Optional[ParticleSystem] = None
        self.smoothed_bars: np.ndarray = np.zeros(NUM_BARS)
        self.sample_rate: int = 44100
        self.pcm_data: np.ndarray = np.array([])
        self._running: bool = True
        self._bonus_hue: float = 0.0  # colour-shifting overlay hue

        # Setup UI
        self._setup_screen()
        self._load_image()
        self._setup_audio()
        self._setup_timer()
        self._init_particles()

        # Focus for key events
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setFocus()

    # ------------------------------------------------------------------
    # Screen & image setup
    # ------------------------------------------------------------------
    def _setup_screen(self) -> None:
        """Select the target screen and go fullscreen."""
        screens = QApplication.screens()
        if self.screen_index < len(screens):
            self.screen: QScreen = screens[self.screen_index]
        else:
            log.warning(
                "Screen index %d out of range (%d screens available). Falling back to screen 0.",
                self.screen_index,
                len(screens),
            )
            self.screen = screens[0]

        # QWidget::showFullScreen() uses the screen the widget currently
        # occupies, so we must move it to the target screen first.
        geo = self.screen.availableGeometry()
        self.move(geo.topLeft())
        self.showFullScreen()

    def _load_image(self) -> None:
        """Load the background image into a QImage."""
        self.bg_image = QImage(self.image_path)
        if self.bg_image.isNull():
            sys.exit(1)

    # ------------------------------------------------------------------
    # Audio setup
    # ------------------------------------------------------------------
    def _setup_audio(self) -> None:
        """Decode audio to PCM and set up QMediaPlayer for playback."""
        # Pre-decode
        try:
            self.pcm_data = decode_audio_to_pcm(self.audio_path, self.sample_rate)
        except RuntimeError as exc:
            log.error("Audio decode error: %s", exc)
            sys.exit(1)

        if len(self.pcm_data) == 0:
            log.error("Decoded audio is empty.")
            sys.exit(1)

        log.info("Loaded %d samples (%.1f s) from '%s'",
                 len(self.pcm_data), len(self.pcm_data) / self.sample_rate, self.audio_path)

        # Player
        self.player = QMediaPlayer()
        self.audio_output = QAudioOutput()
        self.player.setAudioOutput(self.audio_output)
        self.player.setSource(QUrl.fromLocalFile(self.audio_path))
        self.player.play()

        # Exit when track finishes
        self.player.mediaStatusChanged.connect(self._on_media_status_changed)

    def _on_media_status_changed(self, status: QMediaPlayer.MediaStatus) -> None:
        """Trigger clean exit when playback ends."""
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            log.info("Track finished. Exiting.")
            self._running = False
            self.player.stop()
            QApplication.quit()

    # ------------------------------------------------------------------
    # Timer for render loop
    # ------------------------------------------------------------------
    def _setup_timer(self) -> None:
        """Start a QTimer that drives the render loop at ~60 FPS."""
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._render_loop)
        self.timer.start(UPDATE_INTERVAL_MS)

    # ------------------------------------------------------------------
    # Particles
    # ------------------------------------------------------------------
    def _init_particles(self) -> None:
        w, h = self.screen.size().width(), self.screen.size().height()
        self.particle_system = ParticleSystem(w, h)

    # ------------------------------------------------------------------
    # Render loop
    # ------------------------------------------------------------------
    def _render_loop(self) -> None:
        """Called every UPDATE_INTERVAL_MS; computes FFT and triggers repaint."""
        if not self._running:
            return

        pos_ms = self.player.position()
        magnitudes = compute_fft_magnitude(self.pcm_data, pos_ms, self.sample_rate)
        self._update_bars(magnitudes)
        self.update()  # schedules paintEvent

    def _update_bars(self, magnitudes: np.ndarray) -> None:
        """Map FFT magnitude bins to NUM_BARS equalizer values with smoothing."""
        n_bins = len(magnitudes)
        bar_values = np.zeros(NUM_BARS)

        # Log-spaced bin mapping so bass gets more bars
        for i in range(NUM_BARS):
            low = int((i / NUM_BARS) ** 1.5 * n_bins)
            high = int(((i + 1) / NUM_BARS) ** 1.5 * n_bins)
            high = min(high, n_bins)
            if high > low:
                bar_values[i] = magnitudes[low:high].mean()
            else:
                bar_values[i] = magnitudes[low]

        # Apply square-root response curve so moderate energy produces
        # visibly tall bars (linear mapping leaves most bars looking small).
        bar_values = np.sqrt(bar_values)

        # Smooth with exponential decay
        self.smoothed_bars = self.smoothed_bars * DECAY_FACTOR + bar_values * (1 - DECAY_FACTOR)

    # ------------------------------------------------------------------
    # Painting
    # ------------------------------------------------------------------
    def _draw_covered_image(self, painter: QPainter) -> None:
        """Draw the background image scaled to cover the widget (CSS object-fit: cover)."""
        gw, gh = self.width(), self.height()
        iw, ih = self.bg_image.width(), self.bg_image.height()

        # Compute scale to cover
        scale = max(gw / iw, gh / ih)
        draw_w = int(iw * scale)
        draw_h = int(ih * scale)

        # Center crop
        dx = (gw - draw_w) // 2
        dy = (gh - draw_h) // 2

        painter.drawImage(QRectF(dx, dy, draw_w, draw_h), self.bg_image)

    def _draw_equalizer(self, painter: QPainter) -> None:
        """Render the equalizer bars occupying the bottom portion of the screen."""
        gw, gh = self.width(), self.height()
        margin_x = float(gw * 0.02)
        bar_area_w = gw - 2 * margin_x
        bar_area_h = float(gh * 0.45) - 20  # ~45% of screen height for bar room
        bar_gap = 4.0
        bar_w = (bar_area_w - bar_gap * (NUM_BARS - 1)) / NUM_BARS
        base_y = float(gh - 20)

        painter.save()

        for i in range(NUM_BARS):
            val = float(np.clip(self.smoothed_bars[i], 0, 1))
            bar_h = max(2.0, val * bar_area_h)
            x = margin_x + i * (bar_w + bar_gap)
            radius = bar_w / 2.0

            # --- Glow layer ---
            glow_color = QColor.fromHslF(i / NUM_BARS, 0.9, 0.55, 0.15)
            painter.setBrush(QBrush(glow_color))
            painter.setPen(Qt.PenStyle.NoPen)
            glow_rect = QRectF(x - 3, base_y - bar_h - 3, bar_w + 6, bar_h + 6)
            painter.drawRoundedRect(glow_rect, 6, 6)

            # --- Main bar gradient ---
            grad = QLinearGradient(x, base_y, x, base_y - bar_h)
            bottom_hue = i / NUM_BARS
            grad.setColorAt(0.0, QColor.fromHslF(bottom_hue, 0.95, 0.45, 0.85))
            grad.setColorAt(0.5, QColor.fromHslF((bottom_hue + 0.05) % 1.0, 0.9, 0.6, 0.9))
            grad.setColorAt(1.0, QColor.fromHslF((bottom_hue + 0.1) % 1.0, 0.85, 0.75, 0.95))

            painter.setBrush(QBrush(grad))
            painter.setPen(QPen(QColor.fromHslF(bottom_hue, 0.8, 0.8, 0.6), 1))
            bar_rect = QRectF(x, base_y - bar_h, bar_w, bar_h)
            painter.drawRoundedRect(bar_rect, radius, radius)

        painter.restore()

    def _draw_particles(self, painter: QPainter) -> None:
        """Draw the bonus particle overlay and a subtle color-shifting tint."""
        if not self.particles_enabled or self.particle_system is None:
            return

        avg_energy = float(np.mean(self.smoothed_bars))
        self.particle_system.update(avg_energy)

        # Subtle color-shifting overlay so the user knows bonus mode is active
        gw, gh = self.width(), self.height()
        hue = (self._bonus_hue + avg_energy * 30) % 360
        self._bonus_hue = hue
        overlay_color = QColor.fromHslF(hue / 360, 0.6, 0.5, 0.06 + avg_energy * 0.04)
        painter.fillRect(QRectF(0, 0, gw, gh), QBrush(overlay_color))

        self.particle_system.draw(painter)

    def paintEvent(self, _event) -> None:  # noqa: ANN001
        """Override: draw background, equalizer, and optional particles.

        NOTE: Do NOT call painter.end() here — QWidget's paint infrastructure
        manages the painter lifecycle. Calling it manually triggers
        QBackingStore warnings and "Painter ended with active states" errors.
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        self._draw_covered_image(painter)
        self._draw_equalizer(painter)
        self._draw_particles(painter)

    def showEvent(self, event) -> None:  # noqa: ANN001
        """Request keyboard focus after the widget is shown (fullscreen).

        setFocus() in __init__ runs before the widget is on-screen, so
        focus is lost when showFullScreen() executes. This ensures we
        actually capture key events in fullscreen mode.
        """
        super().showEvent(event)
        self.setFocus()

    # ------------------------------------------------------------------
    # Input handling
    # ------------------------------------------------------------------
    def event(self, event) -> bool:  # noqa: ANN001
        """Intercept key press events at the widget level, regardless of focus.

        Fullscreen widgets can lose keyboard focus unpredictably. Overriding
        event() guarantees we catch ESC and 'b' even when focus is elsewhere.
        """
        et = event.type()
        if et == QEvent.Type.KeyPress:
            key_event = event  # type: ignore
            key = key_event.key()
            if key == Qt.Key.Key_Escape:
                self._running = False
                self.player.stop()
                QApplication.quit()
                return True
            if key == Qt.Key.Key_B:
                self.particles_enabled = not self.particles_enabled
                log.info("Particles: %s", "ON" if self.particles_enabled else "OFF")
                return True
        return super().event(event)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------
    def closeEvent(self, _event) -> None:  # noqa: ANN001
        """Stop playback on window close."""
        self._running = False
        self.player.stop()


# ===================================================================
# CLI entry point
# ===================================================================
def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Fullscreen media player with real-time graphic equalizer.",
    )
    parser.add_argument("image_path", help="Path to background image (PNG/JPEG)")
    parser.add_argument("audio_path", help="Path to audio file (MP3/WAV)")
    parser.add_argument(
        "--screen",
        type=int,
        default=0,
        help="Screen index (0-based). Defaults to primary screen (0).",
    )
    return parser.parse_args(argv)


def validate_inputs(image_path: str, audio_path: str) -> None:
    """Validate that input files exist and have supported extensions."""
    img = Path(image_path)
    aud = Path(audio_path)

    if not img.exists():
        log.error("Image file not found: '%s'", image_path)
        sys.exit(1)
    if not aud.exists():
        log.error("Audio file not found: '%s'", audio_path)
        sys.exit(1)

    valid_img_ext = {".png", ".jpg", ".jpeg", ".bmp", ".gif", ".tiff", ".webp"}
    valid_aud_ext = {".mp3", ".wav", ".ogg", ".flac", ".aac", ".m4a", ".wma"}

    if img.suffix.lower() not in valid_img_ext:
        log.error(
            "Unsupported image format '%s'. Supported: %s",
            img.suffix,
            ", ".join(sorted(valid_img_ext)),
        )
        sys.exit(1)
    if aud.suffix.lower() not in valid_aud_ext:
        log.error(
            "Unsupported audio format '%s'. Supported: %s",
            aud.suffix,
            ", ".join(sorted(valid_aud_ext)),
        )
        sys.exit(1)


def main(argv: Optional[List[str]] = None) -> None:
    """Application entry point."""
    args = parse_args(argv)

    # Validate
    validate_inputs(args.image_path, args.audio_path)

    # Ensure we have a display
    app = QApplication(sys.argv if argv is None else [sys.argv[0]] + argv)
    app.setApplicationName("Equalizer")

    if not QApplication.screens():
        log.error("No screens detected. Cannot start fullscreen visualizer.")
        sys.exit(1)

    widget = EqualizerWidget(args.image_path, args.audio_path, args.screen)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
