"""Capture the Stage 8 jump sequence to PNG files, for eyeballing the drama.

A 3-second animation is exactly the sort of thing a test suite can measure to
death and still get wrong, and that no human can review in a diff. This script
drives a real :class:`~src.scenes.game_scene.GameScene` headless (SDL dummy
drivers) and dumps fixed frames of one jump, so the sequence can be inspected as
a film strip: approach, smear, white-out, arrival.

Run from the project root:

    python scripts/capture_jump_frames.py [output_dir]   # default: jump_frames/
    python scripts/capture_jump_frames.py --sheet [path] # one contact sheet

``stage8_jump_sequence.png`` in the project root is the committed contact sheet:
one image that shows the whole effect, which is what belongs in a README.

Deterministic: the world graph comes from ``rng.seed`` (the world seed, as ever)
and the starfield plus the arrival spawn come from a fixed game RNG, so the same
command reproduces the same pictures byte for byte.
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from src.audio import AudioSystem  # noqa: E402
from src.config import base_config  # noqa: E402
from src.main_loop import SCREEN_SIZE  # noqa: E402
from src.model.jump import (  # noqa: E402
    PHASE_BURN,
    PHASE_IDLE,
    PHASE_TRANSITION,
    JumpParams,
    blind_frames_for,
)
from src.scenes.game_scene import GameScene  # noqa: E402

WORLD_SEED = 4242
DESTINATION = "Bravo"

# Contact-sheet layout: half-size tiles, four across, a caption under each.
_SHEET_SCALE = 0.5
_SHEET_COLUMNS = 4
_SHEET_CAPTION_HEIGHT = 26
_SHEET_GUTTER = 6
_SHEET_BACKGROUND = (16, 16, 22)
_SHEET_CAPTION_COLOUR = (200, 210, 225)


class _HeadlessManager:
    """The slice of SceneManager that GameScene actually uses, minus the window."""

    def __init__(self, config: dict) -> None:
        self._config = config
        self.audio = AudioSystem()
        self._pushed: list = []

    def game_config(self) -> dict:
        return self._config

    def push(self, scene) -> None:
        self._pushed.append(scene)
        scene.on_enter(self)

    def pop(self) -> None:
        pass


def seeded_config() -> dict:
    """A base config with one fixed world seed and legible hops off Alpha."""
    config = base_config()
    # One configured seed drives two independent streams: the world graph and the
    # gameplay stream (starfields, arrival bearings). Separate generators, so the
    # topology never depends on how much flying happened first.
    config["rng"]["seed"] = WORLD_SEED
    config["map"]["connections_min"] = 2
    return config


def play_one_jump(config: dict) -> list:
    """Fly one Alpha -> Bravo jump and return ``[(label, surface), ...]``.

    The frames picked are the ones a reviewer needs in order to judge the effect:
    the approach, the smear building, the peak of the white-out (which is what
    hides the world swap), the fade, and the arrival.
    """
    scene = GameScene(_HeadlessManager(config))

    params = JumpParams.from_config(config["tactical"])
    # The player never starts next to the planet, and a jump from inside landing
    # range is refused - so fly out first, as a player would.
    scene.game_state.set_position(600.0, 0.0)
    scene.system_map.select(DESTINATION)

    canvas = pygame.Surface(SCREEN_SIZE)
    frames = []
    frame = 0

    def save(label: str) -> None:
        scene.draw(canvas)
        frames.append((label, canvas.copy()))

    save("00_before")

    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_j))
    blind = blind_frames_for(params.transition_frames)
    burn_shots = {1, params.frames // 4, params.frames // 2, params.frames - 1}

    # ``while scene.jumps.is_active`` would exit before the first update: the jump
    # is only requested *during* that update, when the key press is drained.
    limit = params.frames + params.transition_frames + 10
    while frame < limit:
        frame += 1
        scene.update()
        phase = scene.jumps.phase
        if phase == PHASE_BURN and frame in burn_shots:
            save(f"{frame:03d}_burn")
        elif phase == PHASE_TRANSITION:
            elapsed = scene.jumps.transition_frames_elapsed
            if elapsed == blind:
                save("flash_peak")
            elif elapsed == blind + 8:
                save("flash_fading")
        if phase == PHASE_IDLE and frame > 1:
            break

    save("99_arrived")
    print(
        f"arrived in {scene.system_map.current_system}: "
        f"{scene.game_state.distance_from_point(0.0, 0.0):.0f} px from the planet, "
        f"{scene.game_state.stats.shields:.0f} shields, "
        f"{scene.game_state.fuel:.0f} fuel left"
    )
    return frames


def capture(output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    for label, surface in play_one_jump(seeded_config()):
        path = os.path.join(output_dir, f"jump_{label}.png")
        pygame.image.save(surface, path)
        print(f"  {path}")


def contact_sheet(path: str) -> None:
    """Tile every captured frame into one labelled sheet, saved to ``path``."""
    frames = play_one_jump(seeded_config())
    tile_size = (
        int(SCREEN_SIZE[0] * _SHEET_SCALE),
        int(SCREEN_SIZE[1] * _SHEET_SCALE),
    )
    rows = -(-len(frames) // _SHEET_COLUMNS)  # ceiling division
    tile_height = tile_size[1] + _SHEET_CAPTION_HEIGHT
    width = _SHEET_COLUMNS * tile_size[0] + (_SHEET_COLUMNS + 1) * _SHEET_GUTTER
    height = rows * tile_height + (rows + 1) * _SHEET_GUTTER

    sheet = pygame.Surface((width, height))
    sheet.fill(_SHEET_BACKGROUND)
    font = pygame.font.SysFont("dejavusansmono", 17)

    for index, (label, surface) in enumerate(frames):
        column, row = index % _SHEET_COLUMNS, index // _SHEET_COLUMNS
        left = _SHEET_GUTTER + column * (tile_size[0] + _SHEET_GUTTER)
        top = _SHEET_GUTTER + row * (tile_height + _SHEET_GUTTER)
        sheet.blit(pygame.transform.scale(surface, tile_size), (left, top))
        sheet.blit(
            font.render(label.replace("_", " "), True, _SHEET_CAPTION_COLOUR),
            (left + 4, top + tile_size[1] + 5),
        )

    directory = os.path.dirname(path)
    if directory:
        os.makedirs(directory, exist_ok=True)
    pygame.image.save(sheet, path)
    print(f"  {path}")


if __name__ == "__main__":
    pygame.init()
    pygame.display.set_mode(SCREEN_SIZE)
    if sys.argv[1:2] == ["--sheet"]:
        contact_sheet(sys.argv[2] if len(sys.argv) > 2 else "stage8_jump_sequence.png")
    else:
        capture(sys.argv[1] if len(sys.argv) > 1 else "jump_frames")
