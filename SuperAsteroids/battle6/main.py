"""SuperAsteroids - entry point.

Run with:  python3 main.py [--test] [--debug] [--nosound]
"""

import argparse
import sys

from app import SuperAsteroidsApp


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="SuperAsteroids",
        description="A derivative of the classic Asteroids arcade game.",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="start the title screen, then exit after 250 ms with exit code 0 "
              "(confirms the game starts up correctly)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="enable debug hotkeys in Game Mode: C/L/S spawn a Cannon/Laser/"
               "Shield powerup, U spawns an enemy UFO",
    )
    parser.add_argument(
        "--nosound",
        action="store_true",
        help="start with sound off; F2 still toggles sound on/off at any time",
    )
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    app = SuperAsteroidsApp(
        test_mode=args.test,
        debug_mode=args.debug,
        # Spec (Sound): sound defaults ON; --nosound starts it off.
        sound_on=not args.nosound,
    )
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
