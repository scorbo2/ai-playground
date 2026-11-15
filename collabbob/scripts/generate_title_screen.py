"""Generate resources/title_screen.png for the game title screen background.

Run from the project root inside the project venv:

    python scripts/generate_title_screen.py

The generated image is a dark gradient that fills the 1024x768 window. The
title screen background is stretched to fill this image when it exists.
"""

import os

import pygame

WINDOW_SIZE = (1024, 768)


def generate_title_screen(path):
    """Create a dark gradient title-screen background image at `path`.

    The surface is deliberately opaque (no ``SRCALPHA``) and every scanline is
    painted: drawing on an SRCALPHA surface with 3-tuple colours, and stepping the
    gradient by more than one pixel, leaves whole bands at alpha 0. A translucent
    title background makes the title screen composite over whatever was drawn
    before it rather than replace it, which is how a cancelled dialog stayed
    visible on the title screen.
    """
    pygame.init()
    surface = pygame.Surface(WINDOW_SIZE)

    top_color = (10, 14, 24)   # very dark navy
    bottom_color = (3, 4, 8)   # near black

    last_row = WINDOW_SIZE[1] - 1
    for y in range(WINDOW_SIZE[1]):
        ratio = y / last_row
        color = tuple(
            round(top_color[i] + (bottom_color[i] - top_color[i]) * ratio)
            for i in range(3)
        )
        pygame.draw.line(surface, color, (0, y), (WINDOW_SIZE[0] - 1, y), 1)

    pygame.image.save(surface, path)


def main():
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    resources_dir = os.path.join(project_root, "resources")
    os.makedirs(resources_dir, exist_ok=True)
    output_path = os.path.join(resources_dir, "title_screen.png")
    generate_title_screen(output_path)
    print(f"generated {output_path}")


if __name__ == "__main__":
    main()
