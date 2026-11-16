"""Render every generated sound effect to a WAV file, and draw its shape.

Stage 12's answer to the per-stage contact sheet: a screenshot cannot prove an
explosion sounds bigger than a hit. This script writes one 16-bit PCM WAV per
effect (play them in any media player, or hand them to somebody with ears) and
prints an amplitude profile per effect, so a code review can at least *see* that
the wreck is longer, deeper, and crunchier than a hit.

Nothing here needs an audio device, or pygame at all: the buffers are pure-Python
synthesis from :mod:`src.audio_buffers`, and ``write_wav`` is stdlib :mod:`wave`.
That is deliberate — the script must run on a machine (or CI container) that
cannot make a sound.

Usage
-----
    python scripts/render_audio_buffers.py                 # -> audio_wav/*.wav
    python scripts/render_audio_buffers.py --out /tmp/noise --raw
    python scripts/render_audio_buffers.py --rate 8000 --profile-width 60
    python scripts/render_audio_buffers.py --config config_hard.json

``--raw`` writes the buffers at the synthesis reference peak (what the generator
returns before the mixer turns it down); the default applies the configured
levels, which is what the player actually hears.

The WAV files are generated output and are deliberately not committed: they are
reproducible byte-for-byte from the seeds in :mod:`src.audio_buffers`.
"""

from __future__ import annotations

import argparse
import array
import json
import math
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.audio_buffers import (  # noqa: E402
    BUFFER_GENERATORS,
    DEFAULT_SAMPLE_RATE,
    _REFERENCE_PEAK,
    write_wav,
)
from src.config import CONFIG_FILES, load_config  # noqa: E402
from src.model.audio_levels import AudioLevels  # noqa: E402


def parse_args(argv: "list[str] | None" = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        default=os.path.join(_ROOT, "audio_wav"),
        help="directory to write the WAV files into (default: ./audio_wav)",
    )
    parser.add_argument(
        "--rate",
        type=int,
        default=DEFAULT_SAMPLE_RATE,
        help="sample rate for the dump (default 44100, matching the mixer)",
    )
    parser.add_argument(
        "--config",
        default="config_medium.json",
        help=f"which shipped config's levels to apply (one of {list(CONFIG_FILES)})",
    )
    parser.add_argument(
        "--raw",
        action="store_true",
        help="skip the configured levels: write the buffers at reference peak",
    )
    parser.add_argument(
        "--profile-width",
        type=int,
        default=48,
        help="columns in the printed amplitude profile (0 disables it)",
    )
    return parser.parse_args(argv)


def _levels_for(config_name: str) -> AudioLevels:
    """The levels from one shipped config, or the code defaults if it is absent.

    Reading through ``load_config`` would be stricter, but it validates all three
    files and needs the whole config set to be present; this script's job is audio,
    and a broken map section should not stop a sound dump.
    """
    path = os.path.join(_ROOT, config_name)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            section = json.load(handle).get("audio", {})
    except (OSError, json.JSONDecodeError) as exc:
        print(f"warning: could not read levels from {config_name}: {exc}", file=sys.stderr)
        section = {}
    return AudioLevels.from_config(section)


def _scaled(samples: array.array, factor: float) -> array.array:
    """Apply a mixer volume to a buffer by hand (the WAV has no mixer)."""
    if factor == 1.0:
        return samples
    return array.array(
        "h", [max(-32768, min(32767, int(value * factor))) for value in samples]
    )


def _rms(window) -> float:
    if not window:
        return 0.0
    return math.sqrt(sum(float(value) ** 2 for value in window) / len(window))


def _profile(samples, columns: int) -> str:
    """A crude spectrogram for a terminal: RMS per slice, as a bar per row.

    Time runs downwards (each row is one time slice) because the interesting
    shape of an effect is its envelope: the crack of an explosion is the first
    row, and a hull coming apart keeps a bar visible many rows later.
    """
    if columns <= 0 or not samples:
        return ""
    slice_length = max(1, len(samples) // columns)
    lines = []
    for index in range(columns):
        window = samples[index * slice_length : (index + 1) * slice_length]
        if not window:
            break
        magnitude = _rms(window) / max(1, _REFERENCE_PEAK)
        length = round(magnitude * columns)
        lines.append(f"|{'#' * length}{'.' * (columns - length)}| {magnitude * 100:5.1f}%")
    return "\n".join(lines)


def main(argv: "list[str] | None" = None) -> int:
    args = parse_args(argv)
    levels = _levels_for(args.config)
    os.makedirs(args.out, exist_ok=True)

    print(f"sample rate {args.rate}Hz, levels from {'(reference peak)' if args.raw else args.config}")
    print(f"writing to {args.out}\n")

    header = f"{'effect':<18} {'ms':>5} {'samples':>8} {'peak':>6} {'rms':>7} {'level':>6} file"
    print(header)
    print("-" * len(header))

    for sound_id in sorted(BUFFER_GENERATORS):
        buffer = BUFFER_GENERATORS[sound_id](args.rate)
        level = 1.0 if args.raw else levels.level_for(sound_id)
        rendered = _scaled(buffer, level)
        path = os.path.join(args.out, f"{sound_id}.wav")
        write_wav(path, rendered, sample_rate=args.rate)

        peak = max(abs(value) for value in buffer)
        print(
            f"{sound_id:<18} {len(buffer) * 1000 // args.rate:>5} {len(buffer):>8} "
            f"{peak:>6} {_rms(buffer):>7.0f} {level:>6.3f} {path}"
        )
        if args.profile_width > 0:
            print(_profile(buffer, args.profile_width))
            print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
