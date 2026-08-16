"""SuperAsteroids - entry point.

Run with:  python3 main.py [--test]

``--nosound`` (Stage 7) and ``--debug`` (Stage 5) will be added here as
their features land in the development plan.
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
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    app = SuperAsteroidsApp(test_mode=args.test)
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
