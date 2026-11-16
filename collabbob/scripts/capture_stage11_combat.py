"""Capture Stage 11's combat and the ``T`` scan to PNG files, for eyeballing.

Ammo, damage order, bounty copy, scan stickiness and particle effects are all
things a test can pin numerically and still get wrong *on screen*: a round can be
mathematically in flight and invisible, a "3px" dot can be a single pixel nobody
sees coming, and a bounty message can be arithmetically perfect and unreadable. So
this script drives a real :class:`~src.scenes.game_scene.GameScene` headless (SDL
dummy drivers) and dumps one fight, frame by frame.

Run from the project root:

    python scripts/capture_stage11_combat.py [output_dir]     # default: combat_frames/
    python scripts/capture_stage11_combat.py --sheet [path]   # one contact sheet

``stage11_combat.png`` in the project root is the committed contact sheet.

Deterministic: the fleet is hand-placed with variance rolled out of it, both RNG
streams are seeded, and NPC aim jitter is zero, so the same command reproduces the
same pictures byte for byte. A rolled encounter would make every future change to
the spawn rules change the pictures too, which is the opposite of what a visual
diff wants.
"""

import dataclasses
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
    FACTION_PLAYER,
    PlayerRelations,
)
from src.model.game_state import GameState  # noqa: E402
from src.model.npc_ship import NpcShip, roll_npc_stats  # noqa: E402
from src.scenes.game_scene import GameScene  # noqa: E402

WORLD_SEED = 1101
GAMEPLAY_SEED = 8675309

# The fleet as it is parked: the Pirate due west of the player and nearest (so it is
# the hull the scan locks onto, the one the player's gun is aimed at, and the one
# that hunts the player), the Localhoster and the Bobber far enough out that their
# duel wanders through the middle of the view. All inside the 683px-wide game view
# at the capture's engagement band.
_FLEET_POSITIONS = ((-300.0, 0.0), (190.0, 250.0), (250.0, -190.0))

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


def capture_config() -> dict:
    """The default config, retuned so one fight fits in nine pictures.

    Every change here is about legibility, not about balance:

    * ``player_ship.weapon_range`` 420px (band 315px) so the whole engagement
      happens inside the game view instead of on the minimap. (See DECISIONS.md,
      Stage 10: on the shipped tuning a band-holding fleet is never on screen.)
    * ``weapon_fire_rate`` 3/s (the shipped hard setting), so a tile can show more
      than one of the player's rounds in flight at once: at 8px/frame a round
      crosses the ~240px to its target in 30 frames, and a 1/s gun never has two
      rounds airborne on that distance. The shipped ``combat.projectile_speed_bonus`` of 8 is left
      alone: at 8px/frame a round visibly outruns a 5px/frame ship, and slowing it
      below the ship is its own kind of lie.
    * ``weapon_power`` 75 so a hull actually comes apart inside the capture window,
      and the destruction burst is a thing a reviewer can see rather than a number a
      test asserts. The fleet's own guns are turned back down to 12 damage and one
      round every three seconds (see :func:`hand_placed_fleet`), because an NPC hull
      is rolled from the player's stat block and a 75-damage pirate with 1000 armour
      is not a picture, it is a funfair.
    * ``npc.aim_jitter_degrees`` 0 so the incoming red rounds fly where the picture
      says they do, and ``npc.stat_multiple`` 1.0 so nothing is quadrupled by the
      roll before the fleet's own tuning replaces it.
    """
    config = base_config()
    config["rng"]["seed"] = WORLD_SEED
    config["player_ship"].update(
        {
            "weapon_range": 420,
            "weapon_fire_rate": 3,
            "weapon_power": 75,
        }
    )
    config["npc"].update(
        {
            "spawn_chance_near": 0.0,
            "spawn_chance_far": 0.0,
            "stat_multiple": 1.0,
            "stat_variance": 0.0,
            "aim_jitter_degrees": 0.0,
        }
    )
    return config


def give_player_a_prop_hull(game_state: GameState) -> None:
    """Thicken the player's hull, on the live stat block only.

    Nine tiles of capture need the player to still be flying at tile nine. This is
    deliberately *not* a config change: every NPC hull is rolled from the player's
    starting stat block, so boosting the config would put 1000 points of armour on
    every pirate in the picture and the fight would never end.
    """
    game_state.stats.max_shields = 200.0
    game_state.stats.shields = 200.0
    game_state.stats.max_armor = 1000.0
    game_state.stats.armor = 1000.0


def hand_placed_fleet(config: dict, game_state: GameState, system: str) -> Encounter:
    """One hull per faction, at fixed positions, at rest, on hand-tuned stat sheets.

    The Pirate is nearest, so the ``T`` scan locks onto it and the readout shows the
    red "Pirate" word; it is also hostile to the player from the first frame, so the
    red rounds coming back are its own and not a mislabelled Bobber.

    The stat sheets are replaced rather than rolled because an NPC hull copies the
    player's gun and defences, and the capture's player gun (see
    :func:`capture_config`) would otherwise be fitted to every hull in the system:
    50/100 defences so the Pirate dies in two hits and the pictures have an ending,
    12 damage and one round every three seconds so the return fire is visible but
    never ends the run.
    """
    rules = SpawnRules.from_config(config["npc"])
    hulls = (
        (FACTION_PIRATE, _FLEET_POSITIONS[0]),
        (FACTION_BOBBER, _FLEET_POSITIONS[1]),
        (FACTION_LOCALHOSTER, _FLEET_POSITIONS[2]),
    )
    ships = []
    for faction, position in hulls:
        rolled = roll_npc_stats(game_state.starting_stats, 1.0, 0.0, random.Random(1))
        stats = dataclasses.replace(
            rolled,
            max_shields=50.0,
            max_armor=100.0,
            weapon_power=12.0,
            weapon_fire_rate=1.0,  # one round a second: incoming fire, not a wall
        )
        ships.append(
            NpcShip(
                faction=faction,
                stats=stats,
                position=position,
                heading_degrees=0.0,
            )
        )
    return Encounter(
        system=system,
        ships=ships,
        rules=rules,
        system_pixel_size=float(config["tactical"]["system_pixel_size"]),
        relations=PlayerRelations(),
        rng=random.Random(GAMEPLAY_SEED),
    )


def empty_fleet(config: dict, system: str) -> Encounter:
    """A system with nobody in it but the player and the planet.

    Used for the planet tile: a round crossing the disc must not have a hull to hit
    on the way, or the picture proves nothing about the planet.
    """
    return Encounter(
        system=system,
        ships=[],
        rules=SpawnRules.from_config(config["npc"]),
        system_pixel_size=float(config["tactical"]["system_pixel_size"]),
        relations=PlayerRelations(),
        rng=random.Random(GAMEPLAY_SEED),
    )


def press(scene: GameScene, key: int) -> None:
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, scancode=0, mod=0))


def release(scene: GameScene, key: int) -> None:
    scene.handle_event(pygame.event.Event(pygame.KEYUP, key=key, scancode=0, mod=0))


def advance_until(scene: GameScene, predicate, limit: int) -> int:
    """Frame-step until ``predicate`` holds, and report how long that took."""
    for frame in range(1, limit + 1):
        scene.update()
        if predicate():
            return frame
    return limit


def let_sparks_spread(scene: GameScene, frames: int) -> None:
    """Advance a burst off its birth frame before photographing it.

    Every spark starts stacked on the impact point, so a picture taken on the frame
    the hit landed shows one dot of the wrong colour rather than a spray. The bursts
    live 22 (impact) and 48 (destruction) frames, so the waits below are well inside
    their lifetime.
    """
    for _ in range(frames):
        scene.update()


def _spy_presentations(scene: GameScene) -> "tuple[list, list]":
    """Record the destruction bursts and the banners the scene asks for.

    A capture script may cheat about *when* to take a picture; it must not cheat
    about what is drawn. Wrapping the presentation calls is the difference, and it
    beats guessing at "did a bounty happen?" from the wallet, which starts non-empty.
    """
    destructions: "list[tuple[float, float]]" = []
    banners: "list[str]" = []
    original_destruction = scene.tactical.show_destruction
    original_message = scene.tactical.show_message

    def spy_destruction(position, tint):
        destructions.append(position)
        original_destruction(position, tint)

    def spy_message(text, frames=60):
        banners.append(text)
        original_message(text, frames)

    scene.tactical.show_destruction = spy_destruction  # type: ignore[method-assign]
    scene.tactical.show_message = spy_message  # type: ignore[method-assign]
    return destructions, banners


def _player_rounds(scene: GameScene) -> int:
    """How many of the rounds in flight are the player's own."""
    return sum(1 for round_ in scene.gunfight.projectiles if round_.faction == FACTION_PLAYER)


def _npc_rounds(scene: GameScene) -> int:
    """How many of the rounds in flight belong to somebody else."""
    return len(scene.gunfight.projectiles) - _player_rounds(scene)


def _rounds_clear_of_the_hull(scene: GameScene) -> int:
    """The player's rounds that are visible as rounds, not as a pixel on their own hull.

    Rounds are painted *under* the ship sprite, so a round in its first few frames of
    flight is inside the player's own hull and invisible. Counting only rounds more
    than a hull-length away is what makes the "volley in flight" tile show a volley.
    """
    ship = scene.game_state.position
    return sum(
        1
        for round_ in scene.gunfight.projectiles
        if round_.faction == FACTION_PLAYER
        and (round_.position[0] - ship[0]) ** 2 + (round_.position[1] - ship[1]) ** 2 > 40.0**2
    )


def capture_frames(config: dict) -> "list[tuple[str, pygame.Surface]]":
    """One system visit: scan, shoot, watch a hull come apart, jump away."""
    scene = GameScene(_HeadlessManager(config))
    canvas = pygame.Surface(SCREEN_SIZE)
    frames: "list[tuple[str, pygame.Surface]]" = []

    def save(label: str) -> None:
        scene.draw(canvas)
        frames.append((label, canvas.copy()))

    system = scene.system_map.current_system
    give_player_a_prop_hull(scene.game_state)
    scene.encounter = hand_placed_fleet(config, scene.game_state, system)
    # Face the Pirate, so the hull the scan locks onto is the hull the player's gun
    # is pointed at. A player aiming east at the two war-sides would spend the
    # Pirate's death on the last tile instead of the middle of the story.
    scene.game_state.heading = 180.0
    scene.update()

    # 1. A fresh system has no scan lock, whatever the fleet looks like.
    save("00_no_target_yet")

    # 2. T: the nearest hull is now the readout's problem, in its faction colour.
    press(scene, pygame.K_t)
    scene.update()
    release(scene, pygame.K_t)
    save("02_scanned_the_pirate")

    # 3. Green going out, red coming in. Rounds are the only cue that a stray shot
    #    from a faction at peace with the player is not an act of war.
    press(scene, pygame.K_SPACE)
    frames_to_air = advance_until(
        scene,
        lambda: _rounds_clear_of_the_hull(scene) >= 2 and _npc_rounds(scene) >= 1,
        240,
    )
    print(
        f"  {len(scene.gunfight)} rounds airborne "
        f"({_player_rounds(scene)} of them the player's) after {frames_to_air} frames"
    )
    save("04_rounds_in_flight")

    # 4. Sparks where a round entered a hull, tinted with the firer's colour.
    destroyed, banners = _spy_presentations(scene)
    frames_to_hit = advance_until(
        scene,
        lambda: any(burst.particles for burst in scene.tactical.impacts.bursts),
        240,
    )
    print(f"  first impact after {frames_to_hit} frames")
    let_sparks_spread(scene, 8)
    save("06_impact_sparks")

    # 5. A hull coming apart, and the bigger burst that says so.
    frames_to_wreck = advance_until(scene, lambda: len(destroyed) > 0, 600)
    print(f"  first wreck after {frames_to_wreck} more frames")
    let_sparks_spread(scene, 12)
    save("08_hull_coming_apart" if destroyed else "08_nothing_died")

    # 6. The bounty banner, which is the only place the payout is ever stated.
    scene.update()
    scene.update()
    paid = [text for text in banners if "bounty paid" in text]
    print(f"  banners so far: {banners}")
    save("10_bounty_paid" if paid else "10_no_bounty_banner")

    # 7. The scan lock died with its target: back to "No target", no key pressed.
    release(scene, pygame.K_SPACE)
    scene.update()
    save(
        "12_readout_reverted" if scene.scanner.displayed is None else "12_still_locked_on"
    )

    # 8. The planet is not a body. A round flies straight through the disc — with
    #    the system emptied first, so "it didn't hit anything" means the planet.
    scene.encounter = empty_fleet(config, scene.system_map.current_system)
    scene.gunfight.clear()
    scene.scanner.clear()
    scene.game_state.set_position(140.0, 0.0)
    scene.game_state.heading = 180.0
    press(scene, pygame.K_SPACE)
    frames_over_planet = advance_until(
        scene,
        lambda: any(
            round_.faction == FACTION_PLAYER and round_.position[0] < -30.0
            for round_ in scene.gunfight.projectiles
        ),
        150,
    )
    release(scene, pygame.K_SPACE)
    print(f"  player round past the planet after {frames_over_planet} frames")
    save("14_planet_eats_nothing")

    # 9. Hyperspace: nobody shoots, and nothing that was shooting follows.
    scene.gunfight.clear()
    scene.game_state.set_position(600.0, 0.0)
    scene.game_state.heading = 0.0
    scene.system_map.select("Bravo")
    press(scene, pygame.K_SPACE)
    press(scene, pygame.K_j)
    scene.update()
    release(scene, pygame.K_j)
    release(scene, pygame.K_SPACE)
    hidden = advance_until(scene, lambda: not scene.tactical.jump.ship_visible, 400)
    print(f"  white-out after {hidden} frames; {len(scene.gunfight)} rounds left")
    save("16_nobody_shoots_in_hyperspace")
    return frames


def capture(output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)
    for label, surface in capture_frames(capture_config()):
        path = os.path.join(output_dir, f"combat_{label}.png")
        pygame.image.save(surface, path)
        print(f"  {path}")


def contact_sheet(path: str) -> None:
    """Tile every captured frame into one labelled sheet, saved to ``path``."""
    frames = capture_frames(capture_config())
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
        contact_sheet(sys.argv[2] if len(sys.argv) > 2 else "stage11_combat.png")
    else:
        capture(sys.argv[1] if len(sys.argv) > 1 else "combat_frames")
