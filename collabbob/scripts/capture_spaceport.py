"""Capture the Stage 9 spaceport to PNG files, for eyeballing a screen.

Layout is the one thing on this screen that a test suite can measure precisely
and still get ugly: four blocks, twenty buttons, and text that comes from data
(cargo types, system names, lore lines up to ~104 characters). The geometry tests
assert rectangles; this script shows whether the result reads as a screen a human
would use.

Run from the project root:

    python scripts/capture_spaceport.py [output_dir]   # default: spaceport_frames/
    python scripts/capture_spaceport.py --sheet [path] # one contact sheet

``stage9_spaceport.png`` in the project root is the committed contact sheet (see
``stage8_jump_sequence.png`` for the precedent).

Four states are captured, because each one exercises a different failure mode of
the layout: a fresh board, a board with jobs aboard (the manifest grows), a
capacity refusal (the message line), and a player who can afford nothing (every
upgrade price greyed out). Deterministic: the world, the contract board, and the
upgrade offers all come from one seed.
"""

import os
import sys

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pygame  # noqa: E402
import pygame_gui  # noqa: E402

from src.audio import AudioSystem  # noqa: E402
from src.config import base_config  # noqa: E402
from src.main_loop import SCREEN_SIZE  # noqa: E402
from src.model.economy import CarriedLoad  # noqa: E402
from src.scenes.game_scene import GameScene  # noqa: E402

WORLD_SEED = 4242

# Contact-sheet layout: half-size tiles, two across, a caption under each.
_SHEET_SCALE = 0.5
_SHEET_COLUMNS = 2
_SHEET_CAPTION_HEIGHT = 26
_SHEET_GUTTER = 6
_SHEET_BACKGROUND = (16, 16, 22)
_SHEET_CAPTION_COLOUR = (200, 210, 225)


class _HeadlessManager:
    """The slice of SceneManager the spaceport actually uses: config, audio, stack."""

    def __init__(self, config: dict) -> None:
        self._config = config
        self.audio = AudioSystem()
        self._stack: list = []

    def game_config(self) -> dict:
        return self._config

    def push(self, scene) -> None:
        self._stack.append(scene)
        scene.on_enter(self)

    def pop(self) -> None:
        if self._stack:
            self._stack.pop()

    def quit(self) -> None:
        pass

    @property
    def top(self):
        return self._stack[-1] if self._stack else None


def seeded_config(starting_credits: "int | None" = None) -> dict:
    """The seeded medium table, optionally with an empty purse."""
    config = base_config()
    config["rng"]["seed"] = WORLD_SEED
    if starting_credits is not None:
        config["new_game"]["starting_credits"] = starting_credits
    return config


def _open_port(config: dict):
    """A GameScene with ``L`` pressed inside landing range: the modal is open.

    The ship starts at the planet centre, which is inside landing range, so no
    repositioning is needed. The release must still be delivered, as a hand does:
    the input layer is edge-triggered.
    """
    manager = _HeadlessManager(config)
    scene = GameScene(manager)
    manager.push(scene)
    press = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_l, scancode=0, mod=0)
    release = pygame.event.Event(pygame.KEYUP, key=pygame.K_l, scancode=0, mod=0)
    scene.handle_event(press)
    scene.update()
    scene.handle_event(release)
    return scene, manager.top


def _click(port, button) -> None:
    port.handle_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=button))


def capture_states(config: dict) -> list:
    """``[(label, surface), ...]``: one screen per layout stress case."""
    canvas = pygame.Surface(SCREEN_SIZE)
    frames = []

    def save(port, label: str) -> None:
        # Update, then draw, exactly as FixedTimestepLoop does. pygame_gui
        # re-renders a widget's caption on its next update, so drawing straight
        # after a transaction would photograph the caption from before it.
        port.update()
        port.draw(canvas)
        frames.append((label, canvas.copy()))

    # 1. Arrival: nothing aboard, the delivery greeting on the message line.
    _scene, port = _open_port(config)
    save(port, "01_arrival")

    # 2. Jobs aboard: the manifest block has to explain why the hold is not empty.
    for button in list(port._accept_buttons)[:3]:
        _click(port, button)
    save(port, "02_three_jobs_aboard")

    # 3. A refusal: the hold is full, so the next click writes the capacity
    #    message that has to fit the message line.
    state = port.game_state
    state.accept_load(CarriedLoad(
        destination="Zulu", fare=1, cargo_type="iron ore",
        cargo_units=state.stats.cargo_room, passengers=state.stats.passenger_space,
    ))
    port._sync_buttons()
    still_live = [button for button in port._accept_buttons if button.is_enabled]
    if still_live:
        _click(port, still_live[0])
    save(port, "03_capacity_refusal")

    # 4. No money: every upgrade price is greyed, and the services show their price
    #    or say "Full"/"Intact". One damage point so Repair is still a live choice.
    _scene, broke = _open_port(seeded_config(starting_credits=1))
    broke.game_state.stats.armor -= 1
    broke._sync_buttons()
    save(broke, "04_broke_upgrades_greyed")
    return frames


def capture(output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    for label, surface in capture_states(
        seeded_config(starting_credits=20_000)
    ):
        path = os.path.join(output_dir, f"spaceport_{label}.png")
        pygame.image.save(surface, path)
        print(f"  {path}")


def contact_sheet(path: str) -> None:
    frames = capture_states(seeded_config(starting_credits=20_000))
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
        top = _SHEET_GUTTER + row * tile_height + _SHEET_GUTTER
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
        contact_sheet(sys.argv[2] if len(sys.argv) > 2 else "stage9_spaceport.png")
    else:
        capture(sys.argv[1] if len(sys.argv) > 1 else "spaceport_frames")
