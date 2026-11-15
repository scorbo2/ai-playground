"""Entry-point shim for the game.

Run from the project root (or from anywhere) with `python main.py`. The
project root is put on sys.path so `src` is importable. pygame is
initialised and the 1024×768 window is created before the game starts.
"""

import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import pygame  # noqa: E402

from src.audio import AudioSystem  # noqa: E402
from src.config import GAME_ROOT, ConfigLoadError, load_config  # noqa: E402
from src.main_loop import SCREEN_SIZE, FixedTimestepLoop  # noqa: E402
from src.scene_manager import SceneManager  # noqa: E402
from src.scenes.title_screen import TitleScene  # noqa: E402


def main(config_dir=None):
    """Load the game configuration, build the scene stack, and run the loop."""
    try:
        configs = load_config(config_dir or GAME_ROOT)
    except ConfigLoadError as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)

    pygame.init()
    pygame.display.set_caption("The velocity of escape")
    screen = pygame.display.set_mode(SCREEN_SIZE, 0, pygame.SWSURFACE, 0, 0)

    audio = AudioSystem()
    manager = SceneManager(screen=screen, configs=configs, audio=audio)
    manager.push(TitleScene())

    FixedTimestepLoop(scene_manager=manager, screen=screen).run()


if __name__ == "__main__":
    main()
