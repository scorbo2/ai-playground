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
    """Create a dark gradient title-screen background image at `path`."""
    pygame.init()
    surface = pygame.Surface(WINDOW_SIZE, pygame.SRCALPHA)

    top_color = (10, 14, 24)   # very dark navy
    bottom_color = (3, 4, 8)   # near black

    for y in range(0, WINDOW_SIZE[1], 4):
        ratio = y / WINDOW_SIZE[1]
        color = (
            top_color[0] + (bottom_color[0] - top_color[0]) * ratio,
            top_color[1] + (bottom_color[1] - top_color[1]) * ratio,
            top_color[2] + (bottom_color[2] - top_color[2]) * ratio,
        )
        pygame.draw.line(surface, color, (0, y), (WINDOW_SIZE[0], y), 1)

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
