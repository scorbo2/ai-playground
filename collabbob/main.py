"""Entry-point shim for the game.

Run from the project root (or from anywhere) with `python main.py`. The
project root is put on sys.path so `src` is importable. pygame is
initialised and the 1024x768 window is created before the game starts
(see src.main_loop).
"""

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from src.config import GAME_ROOT, ConfigLoadError, load_config  # noqa: E402
from src.main_loop import FixedTimestepLoop  # noqa: E402


def main(config_dir=None):
    """Load the game configuration and run the fixed-timestep game loop."""
    try:
        config = load_config(config_dir or GAME_ROOT)
    except ConfigLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    FixedTimestepLoop(on_step=None).run()


if __name__ == "__main__":
    main()
