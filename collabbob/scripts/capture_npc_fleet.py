"""Capture Stage 10's traffic to PNG files, for eyeballing what the AI actually does.

Three new ship silhouettes and a steering law are exactly the kind of thing the
test suite can pin to death and still get wrong on screen: the numbers can all be
right while the fleet looks like it is drifting, orbiting, or vibrating against
the system boundary. This script drives a real
:class:`~src.scenes.game_scene.GameScene` headless (SDL dummy drivers) and dumps a
few frames of one encounter, so a reviewer can judge the effect as pictures.

Run from the project root:

    python scripts/capture_npc_fleet.py [output_dir]      # default: npc_frames/
    python scripts/capture_npc_fleet.py --sheet [path]    # one contact sheet

``stage10_npc_fleet.png`` in the project root is the committed contact sheet.

Deterministic: the fleet is hand-placed rather than rolled, and the game RNG is
seeded, so the same command reproduces the same pictures byte for byte. Rolling a
real encounter here would make every future change to the spawn rules change the
pictures too, which is the opposite of what a visual diff wants.
"""

import os
import random
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
from src.model.encounter import Encounter, SpawnRules  # noqa: E402
from src.model.factions import (  # noqa: E402
    FACTION_BOBBER,
    FACTION_LOCALHOSTER,
    FACTION_PIRATE,
    PlayerRelations,
)
from src.model.game_state import GameState  # noqa: E402
from src.model.npc_ship import NpcShip, roll_npc_stats  # noqa: E402
from src.scenes.game_scene import GameScene  # noqa: E402

WORLD_SEED = 4242
GAMEPLAY_SEED = 90210

# Where the fleet starts: about twice the capture config's engagement band, so
# the chase has somewhere to go, and close enough that the whole encounter happens
# inside the 683px game view instead of in the far corners of a 2000px system.
_FAR_POSITIONS = ((-600.0, 0.0), (300.0, -520.0), (300.0, 520.0))
_CLOSE_UP_POSITIONS = ((-130.0, 0.0), (65.0, -113.0), (65.0, 113.0))

# Contact-sheet layout: half-size tiles, three across, a caption under each.
_SHEET_SCALE = 0.5
_SHEET_COLUMNS = 3
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
    """The default config with both RNG streams pinned and the guns pulled in.

    ``player_ship.weapon_range`` is narrowed to 400px (band 300px) on purpose. The
    shipped medium tuning parks a ship 900px from its target, which is outside the
    683px-wide game view: on the real tuning a band-holding fleet is *only* ever
    visible on the minimap, which is a fact worth knowing but makes a useless
    picture. See DECISIONS.md, Stage 10 — the visibility question belongs to
    Stage 11.
    """
    config = base_config()
    config["rng"]["seed"] = WORLD_SEED
    config["player_ship"]["weapon_range"] = 400
    return config


def hand_placed_fleet(
    config: dict, game_state: GameState, system: str, positions: "tuple[tuple[float, float], ...]"
) -> Encounter:
    """One ship per faction, at fixed positions, at rest.

    The whole point is that the geometry is known: a reviewer comparing the
    "closing" tile with the "on the band" tile is watching the same three hulls
    move, not a different fleet that happened to spawn. The Pirate is nearest the
    player and so hunts the player; the Bobber and the Localhoster hunt each
    other, which is the faction logic visible without a legend.
    """
    stats = game_state.starting_stats
    rules = SpawnRules.from_config(config["npc"])
    hulls = (
        (FACTION_PIRATE, positions[0]),
        (FACTION_BOBBER, positions[1]),
        (FACTION_LOCALHOSTER, positions[2]),
    )
    ships = [
        NpcShip(
            faction=faction,
            stats=roll_npc_stats(stats, 2.0, 0.0, random.Random(1)),
            position=position,
            heading_degrees=0.0,
        )
        for faction, position in hulls
    ]
    return Encounter(
        system=system,
        ships=ships,
        rules=rules,
        system_pixel_size=float(config["tactical"]["system_pixel_size"]),
        relations=PlayerRelations(),
        rng=random.Random(GAMEPLAY_SEED),
    )


# Roughly the half-width of the game view: a ship outside this radius from the
# player is off screen entirely, which is worth showing once and then getting
# past. The capture waits on it rather than on a frame count, so the tile labelled
# "closing in" really does show ships on screen.
_VISIBLE_RADIUS = 340.0


def capture_frames(config: dict) -> list:
    """Play one encounter long enough to show chase, band-holding, and the hide.

    The player sits on the planet at the world origin, unarmed and un-moving, for
    the whole run: this script is about what the fleet does, not about whether the
    player survives it (and Stage 11 is where anything gets shot).
    """
    scene = GameScene(_HeadlessManager(config))
    canvas = pygame.Surface(SCREEN_SIZE)
    frames = []

    def save(label: str) -> None:
        scene.draw(canvas)
        frames.append((label, canvas.copy()))

    # Alpha is empty by rule, whatever the config says about traffic.
    save("00_alpha_is_empty")

    system = scene.system_map.current_system
    scene.encounter = hand_placed_fleet(config, scene.game_state, system, _FAR_POSITIONS)
    save("02_far_apart")

    # The pirate is the ship that hunts the player (it is hostile to the player
    # from the first frame; the other two are neutral and are busy with each
    # other), so its distance is the clock this script keeps.
    pirate = scene.encounter.ships[0]
    player_position = scene.game_state.position
    frame = 0
    while frame < 1500 and pirate.distance_to(player_position) > _VISIBLE_RADIUS:
        scene.update()
        frame += 1
    print(f"  lead ship on screen after {frame} frames")
    save("06_closing_in")

    for _ in range(300):
        scene.update()
    save("10_holding_the_band")
    print(
        "  distances after settling: "
        + ", ".join(
            f"{ship.faction} {ship.distance_to(player_position):.0f}px "
            f"(band {scene.npc_rules.ai_tuning.band_for(ship.stats.weapon_range):.0f})"
            for ship in scene.encounter.ships
        )
    )

    scene.encounter = hand_placed_fleet(
        config, scene.game_state, system, _CLOSE_UP_POSITIONS
    )
    scene.update()
    save("12_three_hulls")

    # Mid white-out: nobody is in this universe, so no hulls either - the same
    # rule that hides the player's ship.
    scene.game_state.set_position(600.0, 0.0)
    scene.system_map.select("Bravo")
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_j))
    hidden = False
    for _ in range(250):
        scene.update()
        if not scene.tactical.jump.ship_visible:
            hidden = True
            break
    save("14_hidden_in_hyperspace" if hidden else "14_never_went_white")
    return frames


def capture(output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    for label, surface in capture_frames(seeded_config()):
        path = os.path.join(output_dir, f"npc_{label}.png")
        pygame.image.save(surface, path)
        print(f"  {path}")


def contact_sheet(path: str) -> None:
    """Tile every captured frame into one labelled sheet, saved to ``path``."""
    frames = capture_frames(seeded_config())
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
        contact_sheet(sys.argv[2] if len(sys.argv) > 2 else "stage10_npc_fleet.png")
    else:
        capture(sys.argv[1] if len(sys.argv) > 1 else "npc_frames")
