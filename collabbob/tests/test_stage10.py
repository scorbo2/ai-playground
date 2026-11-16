"""Stage 10 tests: NPC ships, factions, hostility, and the AI that flies them.

Six layers, mirroring the split of the implementation:

* :mod:`src.model.factions` - the static hostility matrix (Pirates everywhere,
  Localhoster/Bobber mutually hostile, same-faction peaceful except among
  pirates), the friendly-fire filter the AI needs, and the per-session grudge the
  player earns by shooting first.
* :mod:`src.model.encounter` - the spawn roll: Alpha is always empty, the chance
  climbs with *alphabetic* distance from Alpha, the count stays inside the
  configured band, positions land inside the system and clear of the player, and
  the RNG stream is derived per visit so a fleet never shifts under the player.
* :mod:`src.model.npc_ship` - the hull: stats rolled off the player's **starting**
  ship, a gun with a fire-rate gate, shield-first damage ordering, and the same
  physics the player's ship uses (same top speed, same system boundary).
* :mod:`src.model.ai` - the steering law: close on the nearest engageable target,
  brake early enough to arrive at the engagement band standing still, hold
  position when there is nothing to fight, aim with jitter, and never shoot
  something it cannot hurt.
* :mod:`src.model.weapons` - the shot record Stage 11 turns into a projectile.
* :class:`~src.scenes.game_scene.GameScene` - the lifecycle the spec is really
  about: a fleet belongs to a *visit*, so a jump replaces the entire Encounter
  (despawn), landing does not re-roll it, and hyperspace freezes it.

The stage gate: matrix unit tests; Alpha never spawns anything across N seeds;
spawn chance increases with the alphabet; the AI invariants (closes distance,
holds the band, converges on the bearing); despawn on jump.
"""

import dataclasses
import math
import random

import pygame
import pytest

import main  # noqa: F401  (ensures project root is on sys.path)

from src.config import CONFIG_FILES, GAME_ROOT, base_config, load_config
import json
import os

from src.harness import RecordingAudio
from src.hud import HudView
from src.main_loop import SCREEN_SIZE
from src.map_systems.graph import NATO_SYSTEMS
from src.model import physics
from src.model.ai import (
    AiTuning,
    MOTION_BRAKE,
    MOTION_CHASE,
    MOTION_COAST,
    ShipOrder,
    Target,
    choose_motion,
    jittered_aim,
    plan_order,
)
from src.model.encounter import (
    Encounter,
    SpawnRules,
    choose_ship_count,
    encounter_rng,
    roll_encounter,
    spawn_chance_for_system,
    spawn_position,
    system_index,
)
from src.model.factions import (
    FACTION_BOBBER,
    FACTION_LOCALHOSTER,
    FACTION_PIRATE,
    FACTIONS,
    PlayerRelations,
    UnknownFaction,
    faction_color,
    faction_label,
    factions_are_hostile,
    factions_can_engage,
)
from src.model.game_state import GameState
from src.model.npc_ship import NpcShip, NpcStats, roll_npc_stats, roll_stat
from src.model.stats import ShipStats
from src.model.weapons import Shot, weapon_cooldown_frames
from src.scenes.game_scene import GameScene
from src.scenes.tactical_view import TacticalView, npc_ship_surface

# The property gate; matches the seed sweeps in Stages 7-9.
SEED_SAMPLE = range(200)

# A system big enough that "far apart" and "in range" can both be true at once.
ROOMY_SYSTEM_PIXELS = 2000.0

# Where a test parks the player when it wants the NPCs to be busy with each other.
# Only Pirates make this matter - they are hostile from the first frame, so a
# pirate nearest to the player hunts the player instead, and the test ends up
# measuring something else while appearing to measure this. A corner of the
# 2000px system is nearer than the far edge and farther than any NPC pairing a
# test is likely to build.
CORNER_OF_THE_SYSTEM = (900.0, 900.0)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def ai_config(**player_tweaks) -> dict:
    """A fabricated config with narrow guns, so range bands are testable in a small box.

    Never the shipped files: the spec's test rule is "always provide a fabricated
    config". Narrowing ``weapon_range`` (which NPCs inherit) shrinks the
    engagement band without touching the physics, so a chase can finish in a
    couple of seconds of simulated flight.
    """
    config = base_config()
    config["player_ship"].update(
        {"weapon_range": 300, **player_tweaks}
    )
    config["npc"]["engage_range_fraction"] = 0.85
    config["npc"]["aim_jitter_degrees"] = 0.0
    return config


def forced_spawn_config(**npc_tweaks) -> dict:
    """A config where every system except Alpha definitely has traffic."""
    config = ai_config()
    config["npc"].update({"spawn_chance_near": 1.0, "spawn_chance_far": 1.0, **npc_tweaks})
    return config


def spawn_rules(config: dict) -> SpawnRules:
    return SpawnRules.from_config(config["npc"])


def starting_stats(config: dict) -> ShipStats:
    """The starting-stat snapshot a GameScene would hand the spawner."""
    return GameState(config).starting_stats


def make_ship(
    config: dict, faction: str, x: float, y: float, heading: float = 0.0,
    velocity: "tuple[float, float]" = (0.0, 0.0),
) -> NpcShip:
    """One NPC at an exact position, with variance rolled out of the stats.

    ``stat_variance`` is pinned to 0 through :func:`roll_npc_stats` so the hull's
    numbers are the config's numbers: a test that asserts on a range band should
    not be at the mercy of a lucky draw.
    """
    return NpcShip(
        faction=faction,
        stats=roll_npc_stats(starting_stats(config), 4.0, 0.0, random.Random(0)),
        position=(x, y),
        heading_degrees=heading,
        velocity=velocity,
    )


def fleet(
    config: dict,
    *specs: "tuple[str, float, float]",
    system: str = "Bravo",
    relations: "PlayerRelations | None" = None,
    ships: "list[NpcShip] | None" = None,
    seed: int = 17,
) -> Encounter:
    """An Encounter built from exact positions: ``(faction, x, y)`` per ship.

    Exact geometry is the only way to pin an AI invariant. A fleet built by
    ``roll_encounter`` is fine for the spawn tests and useless for "did this ship
    close the distance", because the starting positions are whoever-knows-where.
    """
    built = ships if ships is not None else [
        make_ship(config, faction, x, y) for faction, x, y in specs
    ]
    return Encounter(
        system=system,
        ships=built,
        rules=spawn_rules(config),
        system_pixel_size=float(config["tactical"]["system_pixel_size"]),
        relations=relations,
        rng=random.Random(seed),
    )


def run_frames(encounter: Encounter, player_position, frames: int) -> "list[Shot]":
    """Advance an encounter, collecting every shot fired along the way."""
    shots = []
    for _ in range(frames):
        shots.extend(encounter.advance_frame(player_position))
    return shots


def heading_error(ship: NpcShip, target_position) -> float:
    """How far a ship is from facing a point, in degrees (0 == dead on)."""
    return abs(physics.heading_error_degrees(ship.heading, ship.bearing_to(target_position)))


def _count_colour(canvas: "pygame.Surface", colour: "tuple[int, int, int]") -> int:
    """Exactly how many pixels are ``colour`` across the whole canvas."""
    raw = pygame.image.tobytes(canvas, "RGB")
    packed = bytes(colour)
    return sum(1 for offset in range(0, len(raw), 3) if raw[offset:offset + 3] == packed)


def _count_colour_in(
    canvas: "pygame.Surface", colour: "tuple[int, int, int]", region: "tuple[int, int, int, int]"
) -> int:
    """Pixels painted ``colour`` inside ``(x0, y0, x1, y1)``."""
    x0, y0, x1, y1 = region
    hits = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            if canvas.get_at((x, y))[:3] == colour:
                hits += 1
    return hits


class _StackManager:
    """Enough of SceneManager for GameScene: config, audio, and a real stack."""

    def __init__(self, config: "dict | None" = None):
        self._config = config or base_config()
        self.audio = RecordingAudio()
        self.stack = []

    def game_config(self) -> dict:
        return self._config

    def push(self, scene) -> None:
        self.stack.append(scene)
        scene.on_enter(self)

    def pop(self) -> None:
        if self.stack:
            self.stack.pop().on_exit()

    @property
    def top(self):
        return self.stack[-1] if self.stack else None


def game_scene(config: "dict | None" = None) -> GameScene:
    """A real GameScene (26-system world, lore book, market, fleet) on a fake stack."""
    manager = _StackManager(config)
    scene = GameScene(manager)
    manager.push(scene)
    return scene


def advance(scene: GameScene, frames: int) -> None:
    for _ in range(frames):
        scene.update()


def press(scene: GameScene, key: int) -> None:
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, scancode=0, mod=0))


def release(scene: GameScene, key: int) -> None:
    """Let go of a key.

    The input layer is edge-triggered and a KEYUP discards a rising edge that has
    not been drained yet, which gives tests a sharp edge worth naming: press and
    release inside the same frame is *not* a tap, it is nothing at all (a real
    keypress spans many frames). So a helper that taps must press, let ``update()``
    drain the edge, and only then release.

    Releasing matters anyway: a KEYDOWN that is never released leaves the key in
    the held set, so the second press of a two-hop jump test is not a rising edge
    and the second jump silently never starts.
    """
    scene.handle_event(pygame.event.Event(pygame.KEYUP, key=key, scancode=0, mod=0))


def jump(scene: GameScene, destination: str, limit: int = 400) -> None:
    """Fly a scene to ``destination`` the way the player does: select, tap J, wait.

    Failing loudly beats falling through: a test that silently never arrived is a
    test of whatever system it was already in.
    """
    scene.game_state.set_position(600.0, 0.0)  # outside landing range, inside the boundary
    scene.system_map.select(destination)
    press(scene, pygame.K_j)
    scene.update()  # drains the rising edge; releasing before this would eat the press
    release(scene, pygame.K_j)
    for _ in range(limit):
        scene.update()
        if scene.system_map.current_system == destination and not scene.jumps.is_active:
            return
    raise AssertionError(
        f"never arrived at {destination}: system={scene.system_map.current_system!r} "
        f"jump phase={scene.jumps.phase!r} fuel={scene.game_state.fuel}"
    )


# ===========================================================================
# The hostility matrix
# ===========================================================================


def test_factionsAreHostile_pirateAgainstEveryFaction_shouldBeTrueInBothOrders():
    """GIVEN any faction, WHEN asked whether pirates are hostile, THEN always yes.

    Including pirate-vs-pirate: the spec states flatly that pirates are hostile
    to *everyone*, so the matrix reports that even though the friendly-fire rule
    makes the pair unable to act on it (next test). Splitting those two notions
    is deliberate - "do they hate each other" and "can they shoot each other"
    are different questions, and collapsing them is how pirates end up duelling
    their own squad, or end up friendly to each other.
    """
    for faction in FACTIONS:
        assert factions_are_hostile(FACTION_PIRATE, faction) is True
        assert factions_are_hostile(faction, FACTION_PIRATE) is True


def test_factionsAreHostile_localhosterAndBobber_shouldBeMutuallyHostile():
    """The war the player flew into: L and B hate each other, permanently, both ways."""
    assert factions_are_hostile(FACTION_LOCALHOSTER, FACTION_BOBBER) is True
    assert factions_are_hostile(FACTION_BOBBER, FACTION_LOCALHOSTER) is True


def test_factionsAreHostile_sameNonPirateFaction_shouldBePeaceful():
    """No civil war: two Localhosters (or two Bobbers) never shoot each other."""
    assert factions_are_hostile(FACTION_LOCALHOSTER, FACTION_LOCALHOSTER) is False
    assert factions_are_hostile(FACTION_BOBBER, FACTION_BOBBER) is False


@pytest.mark.parametrize("faction", FACTIONS)
def test_factionsCanEngage_sameFaction_shouldBeFalseBecauseFriendlyFireIsImpossible(faction):
    """Hostility is not enough: a shot at your own kind is a shot wasted.

    Pirate-vs-pirate is the interesting case. The matrix calls it hostile, and
    the AI still refuses to *pursue* it, because the spec says projectiles pass
    harmlessly through same-faction ships - so a pirate that engaged the pirate
    next to it would spend the entire encounter trading sparks with an ally and
    never once chase the freighter it could actually hurt.
    """
    assert factions_can_engage(faction, faction) is False


def test_factionsCanEngage_theUsualSuspects_shouldBeTrue():
    """Everyone else may shoot: pirates at all, and L vs B both ways."""
    assert factions_can_engage(FACTION_PIRATE, FACTION_LOCALHOSTER) is True
    assert factions_can_engage(FACTION_LOCALHOSTER, FACTION_PIRATE) is True
    assert factions_can_engage(FACTION_BOBBER, FACTION_PIRATE) is True
    assert factions_can_engage(FACTION_LOCALHOSTER, FACTION_BOBBER) is True


@pytest.mark.parametrize("first,second", [("pirate", "turkeys"), ("", "bobber"), ("Pirate", "bobber")])
def test_factionsAreHostile_withAnUnknownFactionId_shouldRaiseRatherThanSayingNo(
    first, second
):
    """"Not hostile" is a load-bearing answer, so a typo must not produce it.

    A faction id that is merely unknown would otherwise read as a peaceful
    faction, and the symptom would be a pirate that watches the player fly by.
    ``"Pirate"`` (capitalised) is the realistic version of this bug, because the
    HUD copy is capitalised and someone will eventually pass it back in.
    """
    with pytest.raises(UnknownFaction):
        factions_are_hostile(first, second)


def test_factionLabelsAndColors_shouldMatchTheSpecsReadoutIdentity():
    """The HUD prints "Localhoster"/"Bobber"/"Pirate" in cyan/yellow/red.

    Pinned here because Stage 11's readout and the minimap markers and the
    projectiles all have to agree with each other, and the spec names all three
    in one sentence.
    """
    assert faction_label(FACTION_LOCALHOSTER) == "Localhoster"
    assert faction_label(FACTION_BOBBER) == "Bobber"
    assert faction_label(FACTION_PIRATE) == "Pirate"

    assert faction_color(FACTION_LOCALHOSTER) == (0, 200, 200)
    assert faction_color(FACTION_BOBBER) == (230, 200, 60)
    assert faction_color(FACTION_PIRATE) == (255, 0, 0)


def testplayerRelations_newGame_shouldBeNeutralToBothWarsidesAndOnlyPiratesHostile():
    """Spec: "the player is initially neutral, and neither faction is initially hostile"."""
    relations = PlayerRelations()

    assert relations.is_hostile_to_player(FACTION_LOCALHOSTER) is False
    assert relations.is_hostile_to_player(FACTION_BOBBER) is False
    assert relations.is_hostile_to_player(FACTION_PIRATE) is True
    assert relations.factions_hostile_to_player == frozenset({FACTION_PIRATE})


def testplayerRelations_declareHostile_shouldBePermanentAndScopedToOneFaction():
    """Hitting a Localhoster makes *Localhosters* hostile; Bobbers stay neutral.

    And the grudge never expires: there is no code path here that clears it,
    which is the API-level statement of "for the remainder of the game".
    """
    relations = PlayerRelations()

    assert relations.declare_hostile_to_player(FACTION_LOCALHOSTER) is True
    assert relations.is_hostile_to_player(FACTION_LOCALHOSTER) is True
    assert relations.is_hostile_to_player(FACTION_BOBBER) is False
    assert relations.factions_hostile_to_player == frozenset(
        {FACTION_LOCALHOSTER, FACTION_PIRATE}
    )

    for _ in range(50):
        assert relations.is_hostile_to_player(FACTION_LOCALHOSTER) is True


def testplayerRelations_declaringAnAlreadyHostileFaction_shouldReportNoChange():
    """The return value is "did this change anything", so the caller can print news once.

    Without it the damage path would need its own copy of the grudge list to
    decide whether "Localhosters are now hostile to you" is worth showing, and
    the two copies would drift.
    """
    relations = PlayerRelations()
    relations.declare_hostile_to_player(FACTION_BOBBER)

    assert relations.declare_hostile_to_player(FACTION_BOBBER) is False
    # Pirates were never neutral, so "declaring" them hostile is a no-op too.
    assert relations.declare_hostile_to_player(FACTION_PIRATE) is False


def testplayerRelations_hostilityIsSharedAcrossEncountersInTheSameSession():
    """A grudge is per game session, not per system.

    Same relations object handed to a second Encounter in a different system: the
    Bobbers in Zulu remember what happened in Alpha.
    """
    config = ai_config()
    relations = PlayerRelations()
    relations.declare_hostile_to_player(FACTION_BOBBER)

    in_alpha = fleet(config, (FACTION_BOBBER, 0.0, 0.0), system="Alpha", relations=relations)
    in_zulu = fleet(config, (FACTION_BOBBER, 0.0, 0.0), system="Zulu", relations=relations)

    assert in_alpha.relations is relations
    assert in_zulu.relations is relations
    assert in_zulu.relations.is_hostile_to_player(FACTION_BOBBER) is True


def testplayerRelations_withAnUnknownFaction_shouldRaise():
    with pytest.raises(UnknownFaction):
        PlayerRelations().is_hostile_to_player("miners")


# ===========================================================================
# Spawning: chance, count, placement, determinism
# ===========================================================================


def testrollEncounter_inAlpha_shouldSpawnNothingAcrossManySeeds():
    """The gate's "Alpha never spawns anything across N seeds".

    Spawn chance is pinned to 100% for every other system, so the only thing
    keeping Alpha empty is the rule under test - not the dice.
    """
    config = forced_spawn_config()
    rules = spawn_rules(config)
    stats = starting_stats(config)

    for seed in SEED_SAMPLE:
        encounter = roll_encounter(
            system="Alpha",
            system_names=NATO_SYSTEMS,
            rules=rules,
            starting_stats=stats,
            system_pixel_size=2000.0,
            player_position=(0.0, 0.0),
            rng=random.Random(seed),
        )
        assert encounter.ships == (), f"seed {seed}: Alpha spawned {len(encounter)} ships"
        assert encounter.is_empty is True


def testspawnChanceForSystem_shouldBeZeroAtAlphaAndRiseStrictlyWithAlphabeticIndex():
    """The gate's "spawn chance increases with alphabet".

    Strictly increasing from Bravo to Zulu (given a non-flat config), with Alpha
    pinned at zero: the spec decides danger from the *name*, so a far-flung node
    called Echo can never be more dangerous than a near one called Yankee.
    """
    config = ai_config()
    rules = spawn_rules(config)

    chances = [spawn_chance_for_system(name, NATO_SYSTEMS, rules) for name in NATO_SYSTEMS]

    assert chances[0] == 0.0, "Alpha must be 0% whatever the config says"
    assert chances[1] == pytest.approx(rules.spawn_chance_near)
    assert all(later > earlier for earlier, later in zip(chances[1:], chances[2:])), (
        f"spawn chance is not strictly increasing across {NATO_SYSTEMS[1:]}: {chances}"
    )


def testspawnChanceForSystem_shouldTopOutAtTheConfiguredMaxOnTheLastSystemInPlay():
    """The ramp spans the systems in play, not a hard-coded 26.

    Shrink ``map.system_count`` and the configured maximum chance moves to the
    new last system, instead of being stranded beyond the end of the roster (and
    every system in play then being meaningfully cheaper than the config asked
    for).
    """
    config = ai_config()
    rules = spawn_rules(config)
    roster = NATO_SYSTEMS[:8]

    assert spawn_chance_for_system(roster[-1], roster, rules) == pytest.approx(
        rules.spawn_chance_far
    ), "the last system in play must reach the configured far chance"
    # The name that would have been last on the full roster is simply not in
    # play: the spawner is asked about systems that exist, never about names.
    with pytest.raises(ValueError):
        spawn_chance_for_system("India", roster, rules)


def testspawnChanceForSystem_withASingleSystemRoster_shouldNeverSpawnTraffic():
    """A one-system roster has nowhere to ramp to, and index 0 is always Alpha.

    Division by ``last_index`` would be a ZeroDivisionError here; the guard keeps
    a degenerate map (``map.system_count: 1``) a data question rather than a
    crash.
    """
    rules = spawn_rules(ai_config())
    assert spawn_chance_for_system("Alpha", NATO_SYSTEMS[:1], rules) == 0.0


def testspawnChanceForSystem_withAnUnknownSystemName_shouldRaise():
    with pytest.raises(ValueError):
        spawn_chance_for_system("Tardis", NATO_SYSTEMS, spawn_rules(ai_config()))


def testsystemIndex_shouldFollowTheAlphabeticRoster():
    assert system_index("Alpha", NATO_SYSTEMS) == 0
    assert system_index("Bravo", NATO_SYSTEMS) == 1
    assert system_index("Zulu", NATO_SYSTEMS) == 25


def testrollEncounter_shouldAlwaysSpawnWhenTheChanceIsOneAndNeverWhenItIsZero():
    """The chance knob is honoured at both ends, over 200 seeds."""
    always = forced_spawn_config(spawn_chance_near=1.0, spawn_chance_far=1.0)
    never = forced_spawn_config(spawn_chance_near=0.0, spawn_chance_far=0.0)

    for seed in SEED_SAMPLE:
        for config, expected in ((always, True), (never, False)):
            encounter = roll_encounter(
                system="Yankee",
                system_names=NATO_SYSTEMS,
                rules=spawn_rules(config),
                starting_stats=starting_stats(config),
                system_pixel_size=2000.0,
                player_position=(0.0, 0.0),
                rng=random.Random(seed),
            )
            assert (len(encounter.ships) > 0) is expected, (
                f"seed {seed}, chance "
                f"{spawn_rules(config).spawn_chance_far}: got {len(encounter.ships)} ships"
            )


def testrollEncounter_shipCountShouldStayInsideTheConfiguredBand():
    """Spec: "a random number of between 1 and 4 ships", straight from config.

    Counted across 200 seeds, and with a narrowed band to prove the band is real
    rather than decorative.
    """
    for ships_min, ships_max in ((1, 4), (1, 1), (3, 4)):
        config = forced_spawn_config(ships_min=ships_min, ships_max=ships_max)
        rules = spawn_rules(config)
        counts = set()
        for seed in SEED_SAMPLE:
            encounter = roll_encounter(
                system="Zulu",
                system_names=NATO_SYSTEMS,
                rules=rules,
                starting_stats=starting_stats(config),
                system_pixel_size=2000.0,
                player_position=(0.0, 0.0),
                rng=random.Random(seed),
            )
            counts.add(len(encounter.ships))
            assert ships_min <= len(encounter.ships) <= ships_max

        assert counts == set(range(ships_min, ships_max + 1)), (
            f"ship counts drawn for [{ships_min}, {ships_max}] collapsed to {sorted(counts)}"
        )


def testchooseShipCount_shouldComeFromTheRulesNotFromAHardCodedOneToFour():
    """2..4 in config means never 1: the "1-4" in the spec is an example, not a law."""
    config = forced_spawn_config(ships_min=2, ships_max=4)
    rules = spawn_rules(config)

    counts = {choose_ship_count(random.Random(seed), rules) for seed in range(60)}

    assert 1 not in counts
    assert counts <= {2, 3, 4}


def testrollEncounter_spawnPositions_shouldStayInsideTheSystemAndClearOfThePlayer():
    """The spec's "random starting positions within the system", plus the clearance rule.

    The clearance exists because a uniform draw inside the system can land a
    pirate on top of the player's arrival point, and the player's first sight of
    a hostile system should not be an unavoidable point-blank volley.
    """
    config = ai_config()
    config["npc"]["min_distance_from_player"] = 400
    rules = spawn_rules(config)
    player = (250.0, -350.0)

    for seed in SEED_SAMPLE:
        encounter = roll_encounter(
            system="Zulu",
            system_names=NATO_SYSTEMS,
            rules=rules,
            starting_stats=starting_stats(config),
            system_pixel_size=ROOMY_SYSTEM_PIXELS,
            player_position=player,
            rng=random.Random(seed),
        )
        half = ROOMY_SYSTEM_PIXELS / 2.0
        for ship in encounter.ships:
            x, y = ship.position
            assert -half <= x <= half and -half <= y <= half, (
                f"seed {seed}: spawned at {x:.0f},{y:.0f} outside +/-{half}"
            )
            assert ship.distance_to(player) >= rules.min_distance_from_player, (
                f"seed {seed}: spawned {ship.distance_to(player):.0f}px from the player"
            )


def testspawnPosition_shouldDrawEveryCornerOfTheSystem():
    """"Random positions" must mean the whole square, not a ring or a quadrant."""
    corners = set()
    for seed in range(200):
        x, y = spawn_position(random.Random(seed), 2000.0, (0.0, 0.0), 0.0)
        corners.add((x >= 0, y >= 0))
    assert corners == {(True, True), (True, False), (False, True), (False, False)}


def testspawnPosition_whenTheClearanceIsImpossible_shouldGiveUpAndStillStayInside():
    """A 3000px clearance in a 2000px system cannot be satisfied: do not hang.

    The documented degradation is "accept the last candidate", because a spawn
    that lands closer than the preference is a cosmetic failure and a spawn loop
    that never terminates is a frozen game.
    """
    point = spawn_position(random.Random(5), 200.0, (0.0, 0.0), 5000.0, rejection_limit=6)
    assert abs(point[0]) <= 100.0 and abs(point[1]) <= 100.0


def testrollEncounter_shipsShouldStartStoppedFacingARandomWay():
    """Spec: a starting velocity of 0 and a random initial facing direction.

    The heading is seeded per ship, so it is never the degenerate zero vector,
    and the bearings across a fleet are not all the same.
    """
    config = forced_spawn_config()
    bearings = set()
    for seed in SEED_SAMPLE:
        encounter = roll_encounter(
            system="Zulu",
            system_names=NATO_SYSTEMS,
            rules=spawn_rules(config),
            starting_stats=starting_stats(config),
            system_pixel_size=ROOMY_SYSTEM_PIXELS,
            player_position=(0.0, 0.0),
            rng=random.Random(seed),
        )
        for ship in encounter.ships:
            assert ship.velocity == (0.0, 0.0)
            assert 0.0 <= ship.heading < 360.0
            assert ship.shields == ship.stats.max_shields, "fresh hulls arrive with shields up"
            assert ship.armor == ship.stats.max_armor
            bearings.add(int(ship.heading) // 90)

    assert bearings == {0, 1, 2, 3}, "spawn bearings collapsed onto part of the compass"


def testrollEncounter_factionMixShouldBeRandomButAlwaysKnown():
    """All three factions must be reachable, and no made-up faction ever appears."""
    config = forced_spawn_config(ships_max=4)
    seen = set()
    for seed in SEED_SAMPLE:
        encounter = roll_encounter(
            system="Zulu",
            system_names=NATO_SYSTEMS,
            rules=spawn_rules(config),
            starting_stats=starting_stats(config),
            system_pixel_size=ROOMY_SYSTEM_PIXELS,
            player_position=(0.0, 0.0),
            rng=random.Random(seed),
        )
        seen.update(ship.faction for ship in encounter.ships)

    assert seen == set(FACTIONS), f"the faction draw never produced {set(FACTIONS) - seen}"


def testencounterRng_theSameVisitAlwaysDealsTheSameFleet():
    """The fleet belongs to the visit, not to how the player arrived in it.

    Two rolls off the same derived stream are identical: same factions, same
    positions, same headings. The stream is keyed on the run seed, the system and
    the visit serial - the frame count is not an input, which is why burning fuel
    for ten thousand frames before jumping cannot change who is waiting.
    """
    config = forced_spawn_config()

    def dealt() -> "list[tuple[str, tuple[float, float], float]]":
        encounter = roll_encounter(
            system="Zulu",
            system_names=NATO_SYSTEMS,
            rules=spawn_rules(config),
            starting_stats=starting_stats(config),
            system_pixel_size=ROOMY_SYSTEM_PIXELS,
            player_position=(0.0, 0.0),
            rng=encounter_rng("a-fixed-run-seed", "Zulu", 4),
        )
        return [(ship.faction, ship.position, ship.heading) for ship in encounter.ships]

    assert dealt() == dealt(), "the fleet shifted under the player between two identical rolls"
    assert len(dealt()) >= 1, "spawn chance is 100%: nothing was dealt"


def testencounterRng_aSecondVisitToTheSameSystemIsADifferentDeal():
    """The visit serial is in the key, so a return visit is a fresh roll.

    Without it, Alpha -> Bravo -> Alpha -> Bravo would reproduce the first Bravo
    fleet exactly, and the spec's "does not remember the quantity or types of
    ships" would be false in the model even with the despawn implemented.
    """
    first = [encounter_rng("seed", "Zulu", 1).random() for _ in range(3)]
    second = [encounter_rng("seed", "Zulu", 2).random() for _ in range(3)]

    assert first != second


def testencounterRng_theFleetStreamIsNotTheJobMarketStream():
    """Entering a system rolls a market and a fleet; neither may eat the other's draws.

    Same seed, same system, same visit serial, two namespaces. If the suffix were
    dropped the two streams would be the same object in all but name, so buying a
    different job would change who shoots at the player - a coupling nobody asked
    for and nobody would think to look for.
    """
    from src.model.economy import port_rng

    fleet_draws = [encounter_rng("seed", "Bravo", 7).random() for _ in range(3)]
    market_draws = [port_rng("seed", "Bravo", 7).random() for _ in range(3)]

    assert fleet_draws != market_draws


# ===========================================================================
# NPC hull stats: the "quadruple the starting stats" rule
# ===========================================================================


def testrollNpcStats_shouldSitInsideTheStartingStatEnvelopeAcrossSeeds():
    """The gate's stat formula: 4x the player's starting values, plus or minus 50%.

    Checked against the spec's own worked example: a 50-shield starting ship
    produces NPCs between 100 and 300 shields.
    """
    config = base_config()
    stats = starting_stats(config)
    assert (stats.max_shields, stats.max_armor, stats.weapon_power) == (50.0, 100.0, 10.0)

    for seed in SEED_SAMPLE:
        rolled = roll_npc_stats(stats, 4.0, 0.5, random.Random(seed))
        assert 100.0 <= rolled.max_shields <= 300.0
        assert 200.0 <= rolled.max_armor <= 600.0
        assert 20.0 <= rolled.weapon_power <= 60.0


def testrollNpcStats_shouldCoverTheWholeEnvelopeAndNotJustTheMiddle():
    """A variance knob that never reaches its extremes is a knob nobody can hear."""
    config = base_config()
    stats = starting_stats(config)
    shields = [
        roll_npc_stats(stats, 4.0, 0.5, random.Random(seed)).max_shields
        for seed in range(400)
    ]
    assert min(shields) < 110.0 and max(shields) > 290.0, (
        f"rolled shields span {min(shields):.0f}..{max(shields):.0f}, not the 100..300 the config allows"
    )


def testrollNpcStats_withZeroVariance_shouldRollTheMultipleExactly():
    """The variance knob at 0 is the pure multiplier - and this is what the AI tests use."""
    config = base_config()
    rolled = roll_npc_stats(starting_stats(config), 4.0, 0.0, random.Random(1))

    assert rolled.max_shields == pytest.approx(200.0)
    assert rolled.max_armor == pytest.approx(400.0)
    assert rolled.weapon_power == pytest.approx(40.0)


@pytest.mark.parametrize("multiple,variance,expected_floor,expected_ceiling", [
    (3.0, 0.4, 70 * 3 * 0.6, 70 * 3 * 1.4),
    (5.0, 0.5, 70 * 5 * 0.5, 70 * 5 * 1.5),
])
def testrollStat_shouldHonourWhateverDifficultyTheConfigAsksFor(
    multiple, variance, expected_floor, expected_ceiling
):
    """Easy (3.0x / 0.4) and Hard (5.0x / 0.5) get their own envelope.

    A test that only exercised the spec's 4x/50% would not notice the difficulty
    files being identical, which is exactly the Stage 14 sweep's complaint.
    """
    for seed in range(60):
        rolled = roll_stat(70.0, multiple, variance, random.Random(seed))
        assert expected_floor <= rolled <= expected_ceiling


def testrollNpcStats_gunAndHandlingComeFromTheStartingShipVerbatim():
    """Spec: "Other ships have a firing rate and projectile range equal to the player's starting stats."

    Handling (turn rate, acceleration, top speed, hull size) is not named by the
    spec, so it follows the same anchor: the galaxy is scaled to the ship the
    player *began* with, which is what makes upgrading into an engine Mk.IV mean
    something against the same pirates.
    """
    config = ai_config(weapon_range=440, top_speed=4.25, acceleration_rate=0.17,
                       turn_rate_deg_per_sec=140, length=38, width=18)
    stats = starting_stats(config)
    rolled = roll_npc_stats(stats, 4.0, 0.5, random.Random(3))

    assert rolled.weapon_fire_rate == stats.weapon_fire_rate
    assert rolled.weapon_range == stats.weapon_range == 440.0
    assert rolled.turn_rate_deg_per_sec == stats.turn_rate_deg_per_sec == 140.0
    assert rolled.acceleration_rate == stats.acceleration_rate == 0.17
    assert rolled.top_speed == stats.top_speed == 4.25
    assert (rolled.length, rolled.width) == (38.0, 18.0)


def testrollEncounter_shouldUseTheStartingStatsEvenAfterHeavyUpgrades():
    """The spec's loudest NPC rule, and the easiest one to break by accident.

    ``game_state.stats`` mutates every time the player buys a level. Passing *it*
    to the spawner would quietly rescale every pirate in the galaxy, and the
    player's own upgrades would turn into the galaxy's upgrades.
    """
    config = base_config()
    state = GameState(config, rng=random.Random(5))
    before = roll_encounter(
        system="Zulu", system_names=NATO_SYSTEMS, rules=spawn_rules(config),
        starting_stats=state.starting_stats, system_pixel_size=2000.0,
        player_position=state.position, rng=random.Random(11),
    )
    # Six levels of shields/armor/weapons later, the live stats have tripled.
    state.stats.max_shields = state.stats.shields = 500.0
    state.stats.max_armor = state.stats.armor = 900.0
    state.stats.weapon_power = 120.0

    after = roll_encounter(
        system="Zulu", system_names=NATO_SYSTEMS, rules=spawn_rules(config),
        starting_stats=state.starting_stats, system_pixel_size=2000.0,
        player_position=state.position, rng=random.Random(11),
    )

    assert [(s.faction, s.stats.max_shields, s.stats.max_armor, s.stats.weapon_power)
            for s in after.ships] == [
        (s.faction, s.stats.max_shields, s.stats.max_armor, s.stats.weapon_power)
        for s in before.ships
    ]
    assert state.stats.max_shields == 500.0, "the player's own upgrades are still there"


def testnpcShip_shouldHaveNoFuelAndNoJumpingAtAll():
    """Spec: "Other ships have unlimited fuel but cannot initiate jumps."

    Expressed by absence rather than by a field set to a big number: an
    ``NpcShip.fuel`` attribute would be state that can drift out of sync with the
    rule it claims to represent, and "cannot jump" needs a guard nobody can
    reach. Asserting the absence is the only way to keep it that way.
    """
    ship = make_ship(ai_config(), FACTION_PIRATE, 0.0, 0.0)

    assert not hasattr(ship, "fuel")
    assert not hasattr(ship, "fuel_capacity")
    for forbidden in ("begin_jump", "jump", "start_jump"):
        assert not hasattr(ship, forbidden)

    stat_fields = {field.name for field in dataclasses.fields(NpcStats)}
    assert not any("fuel" in name or "jump" in name for name in stat_fields), stat_fields


# ===========================================================================
# Physics: the NPC's ship moves like the player's
# ===========================================================================


def testnpcShipThrust_shouldReachTopSpeedOnTheSameFrameThePlayerDoes():
    """One physics law, two ships.

    The Stage 3 gate ("60 frames of thrust from rest with acc 0.2 / top 5 reaches
    exactly 5 px/frame") has to be true for NPC hulls too, or the chase maths in
    :func:`choose_motion` is a lie for one side of the fight.
    """
    config = ai_config(acceleration_rate=0.2, top_speed=5.0)
    player = GameState(config, rng=random.Random(1))
    player.heading_degrees = 0.0
    npc = make_ship(config, FACTION_PIRATE, 0.0, 0.0, heading=0.0)

    for _ in range(60):
        player.feed_input(thrust=True)
        player.advance_frame()
        npc.advance_frame(ShipOrder(burn=(1.0, 0.0)), ROOMY_SYSTEM_PIXELS / 2.0)

    player_speed = math.hypot(*player.velocity)
    npc_speed = math.hypot(*npc.velocity)
    assert player_speed == pytest.approx(5.0, abs=1e-9)
    assert npc_speed == pytest.approx(player_speed, abs=1e-9)
    assert npc.position[0] == pytest.approx(player.position[0], abs=1e-9)
    assert npc.position[1] == pytest.approx(player.position[1], abs=1e-9)


def testnpcShip_shouldBePinnedInsideTheSystemJustLikeThePlayer():
    """A pirate that could fly through the system boundary is a pirate that leaves."""
    config = ai_config()
    ship = make_ship(config, FACTION_PIRATE, 900.0, 0.0, heading=0.0)
    order = ShipOrder(burn=(1.0, 0.0))

    for _ in range(200):
        ship.advance_frame(order, ROOMY_SYSTEM_PIXELS / 2.0)

    half = ROOMY_SYSTEM_PIXELS / 2.0
    assert ship.position[0] == pytest.approx(half)
    assert ship.velocity[0] == 0.0, "outward velocity is scrubbed, not stored"


def testnpcShipHitbox_shouldBeTheLongestAxisOfTheHull():
    """Spec: hitbox is a circle with a diameter equal to the ship's longest measurement."""
    ship = make_ship(ai_config(length=40, width=20), FACTION_PIRATE, 0.0, 0.0)
    assert ship.hitbox_radius == 20.0

    player = GameState(ai_config(length=40, width=20))
    assert player.hitbox_radius == ship.hitbox_radius, (
        "the player and the NPCs must be hit by the same rule"
    )


def testnpcShipApplyDamage_shouldDrainShieldsBeforeArmour():
    """The spec's damage order, defined once on the ship rather than in the projectile code.

    Overkill damage carries through to the hull, and a ship at 0 armour is
    destroyed - both of which Stage 11 depends on and would otherwise be tempted
    to reimplement.
    """
    ship = make_ship(ai_config(), FACTION_PIRATE, 0.0, 0.0)
    assert (ship.shields, ship.armor) == (200.0, 400.0)

    ship.apply_damage(120.0)
    assert (ship.shields, ship.armor) == (80.0, 400.0)
    assert ship.destroyed is False

    ship.apply_damage(180.0)
    # 80 of it is absorbed by what was left of the shields; the other 100 bites.
    assert (ship.shields, ship.armor) == (0.0, 300.0)

    ship.apply_damage(400.0)
    assert ship.armor <= 0.0 and ship.destroyed is True


# ===========================================================================
# The AI: chase, hold, aim, fire
# ===========================================================================


def testadvanceFrame_hostileOutOfGunRange_shouldCloseTheDistanceEveryFrame():
    """The gate's "closes distance" invariant.

    A Pirate with a hostile outside its engagement band must shorten the distance
    every single frame: one frame of approach could be inertia, eighty frames of
    monotone approach is a chase. The player is the target here - a Pirate is
    hostile from the first frame - and is deliberately stationary, because with a
    moving target "the distance shrank" stops being evidence of anything.

    The numbers are measured, not assumed: from 600px the ship is still outside
    the 255px band at frame 80 (it arrives, standing still, at frame 93), so the
    whole run below is chase, not a ship parked on its band.
    """
    config = ai_config()  # weapon_range 300 -> band 255
    band = spawn_rules(config).ai_tuning.band_for(float(config["player_ship"]["weapon_range"]))
    encounter = fleet(config, (FACTION_PIRATE, -600.0, 0.0))
    pirate = encounter.ships[0]

    distances = []
    for _ in range(80):
        distances.append(pirate.distance_to((0.0, 0.0)))
        encounter.advance_frame((0.0, 0.0))

    assert all(later < earlier for earlier, later in zip(distances, distances[1:])), (
        f"the pirate stopped closing: {distances[-5:]}"
    )
    assert distances[0] - distances[-1] > 300.0, (
        f"a chase that covers {distances[0] - distances[-1]:.0f}px in 80 frames is not a chase"
    )
    assert distances[-1] > band, "the run stopped being a chase partway through"


def testadvanceFrame_shouldConvergeOnTheBearingToItsTarget():
    """The gate's "converges on bearing": the heading error must shrink to zero.

    A Pirate and a Bobber after each other, with the player neutral and out of
    the picture. Each is the other's nearest engageable ship, so they close along
    the line joining them - and a ship that is converging on its target must end
    up pointing exactly along that line, not orbiting it.

    Turn rate is finite (180 deg/s = 3 deg/frame), so convergence takes frames;
    the point is that it *converges*, monotonically, rather than overshooting and
    swinging back.
    """
    config = ai_config(turn_rate_deg_per_sec=180)
    encounter = fleet(config, (FACTION_PIRATE, -200.0, -200.0), (FACTION_BOBBER, 200.0, 200.0))
    pirate = encounter.ships[0]

    assert pirate.heading == 0.0, "spawned facing east, target sits at 45 degrees"
    errors = [heading_error(pirate, encounter.ships[1].position)]
    for _ in range(180):
        encounter.advance_frame(CORNER_OF_THE_SYSTEM)
        errors.append(heading_error(pirate, encounter.ships[1].position))

    assert errors[-1] == pytest.approx(0.0, abs=1e-9), (
        f"after 3 seconds the pirate is still {errors[-1]:.1f} deg off its target"
    )
    assert all(earlier >= later for earlier, later in zip(errors, errors[1:])), (
        f"the turn overshot its target somewhere: {errors[:25]}"
    )
    # One frame in, the 3-degree-per-frame turn has eaten exactly one step.
    assert errors[1] == pytest.approx(errors[0] - 3.0)


def testadvanceFrame_shouldArriveAtTheEngagementBandAndStayThere():
    """The gate's "holds band" invariant.

    The ship must end up *on* the band (so its gun works) and must then stay
    there: not mill about outside it, not plough through the target, not fly
    away. A fixed timestep cannot stop a 5px/frame ship on a dime, so the
    tolerance on the near side is one frame of travel - measured, not a fudge:
    the chase reaches the band at frame 93 and the ship is standing dead still on
    it by frame 94.
    """
    config = ai_config()
    gun_range = float(config["player_ship"]["weapon_range"])
    band = spawn_rules(config).ai_tuning.band_for(gun_range)  # 255px
    encounter = fleet(config, (FACTION_PIRATE, 600.0, 0.0))
    pirate = encounter.ships[0]

    run_frames(encounter, (0.0, 0.0), 200)

    distance = pirate.distance_to((0.0, 0.0))
    assert band - pirate.stats.top_speed <= distance <= band, (
        f"pirate settled at {distance:.1f}px; the configured band is {band:.0f}px "
        "and one frame of travel is the only excuse for missing it"
    )
    assert physics.speed_of(pirate.velocity) == 0.0, (
        "a ship still moving on its band has not arrived on it"
    )

    for frame in range(300):
        encounter.advance_frame((0.0, 0.0))
        distance = pirate.distance_to((0.0, 0.0))
        assert band - pirate.stats.top_speed <= distance <= band, (
            f"frame {frame}: the pirate left its own engagement band ({distance:.1f}px)"
        )


def testadvanceFrame_twoShipsChasingEachOther_shouldComeToRestInsideGunRange():
    """The same law with two moving bodies, which is what the player actually sees.

    Neither ship is stationary, so each brakes on its own distance and the pair
    converge between them. The failure mode this pins is the interesting one: an
    AI without the braking lead arrives at the target at full speed, turns around,
    and repeats - on screen, a swarm buzzing through the player forever.
    """
    config = ai_config()
    gun_range = float(config["player_ship"]["weapon_range"])
    encounter = fleet(
        config, (FACTION_PIRATE, -200.0, -200.0), (FACTION_BOBBER, 200.0, 200.0)
    )
    pirate, bobber = encounter.ships

    run_frames(encounter, CORNER_OF_THE_SYSTEM, 300)

    distance = pirate.distance_to(bobber.position)
    assert 0.0 < distance <= gun_range, (
        f"the pair came to rest {distance:.1f}px apart; their guns reach {gun_range:.0f}px"
    )
    assert physics.speed_of(pirate.velocity) == 0.0, "the pirate never stopped"
    assert physics.speed_of(bobber.velocity) == 0.0, "the Bobber never stopped"


def testchooseMotion_farAway_shouldChaseInsideBand_shouldBrakeThenCoast():
    """The bang-bang law itself, at the three distances that matter.

    The middle case is the one that exists: 600px out at top speed, the ship has
    to start braking *before* the band, because ``v²/2a`` says it cannot stop in
    time otherwise. Without that lead the fleet arrives at the player's position
    at 5px/frame, overshoots, turns around, and repeats - which reads on screen
    as a swarm buzzing past the player forever.
    """
    band = 255.0
    assert choose_motion(600.0, 5.0, 0.2, band) == MOTION_CHASE
    # Stopping distance at 5 px/frame and 0.2 px/frame^2 is 62.5px.
    assert choose_motion(band + 30.0, 5.0, 0.2, band) == MOTION_BRAKE
    assert choose_motion(band - 10.0, 5.0, 0.2, band) == MOTION_BRAKE
    assert choose_motion(band - 10.0, 0.0, 0.2, band) == MOTION_COAST
    # Stopped and outside the band: chase, not coast.
    assert choose_motion(band + 10.0, 0.0, 0.2, band) == MOTION_CHASE


def testphysicsBrake_shouldNeverReverseAShipSlowerThanOneBurnStep():
    """The difference between "stopped" and "vibrating at a fraction of a pixel".

    A fixed timestep means a brake step is a fixed size. If the remaining speed
    is smaller than that step, a plain retrograde thrust would flip the velocity
    through zero and the ship would oscillate around a standstill forever, never
    quite reaching the "hold position" the spec asks for. ``brake`` clamps the
    step to the speed that is left.
    """
    # A normal braking frame: 3 px/frame becomes 2.8 px/frame along the same line.
    assert physics.brake((0.0, 3.0), 0.2) == pytest.approx((0.0, 2.8))
    # Slower than one step: lands dead on zero rather than at -0.15.
    assert physics.brake((0.1, 0.0), 0.2) == (0.0, 0.0)
    assert physics.brake((0.0, 0.0), 0.2) == (0.0, 0.0)
    # A ship that cannot brake keeps coasting, which is the truth and not a bug.
    assert physics.brake((1.0, 0.0), 0.0) == (1.0, 0.0)
    # Direction is preserved exactly: braking is a scalar reduction, not a rotation.
    slowed = physics.brake((3.0, -4.0), 1.0)
    assert math.hypot(*slowed) == pytest.approx(4.0)
    assert slowed[0] * slowed[1] < 0.0 and slowed[0] > 0.0 > slowed[1]


def testadvanceFrame_withNoEngageableTarget_shouldHoldItsPosition():
    """Spec: "if there are no hostile ships in the current system, hold position".

    A neutral Localhoster, a neutral player, and nobody else in the system.
    "Hold position" is not "stop thrusting" in a universe with no drag: the ship
    starts with drift, so holding position is an active retrograde burn down to a
    standstill, and then nothing at all.

    The bound on the drift is the ship's own braking distance, v^2/2a = 50px for
    the (4, 2) drift at 0.2 px/frame^2. A ship that merely stopped thrusting
    would have travelled 4.47px/frame x 240 frames = over a kilometre, which is
    the difference between "holds position" and "coasts out of the system".
    """
    config = ai_config()
    drift = make_ship(config, FACTION_LOCALHOSTER, 0.0, 0.0, velocity=(4.0, 2.0))
    encounter = fleet(config, system="Bravo", ships=[drift])

    braking_distance = physics.stopping_distance(
        physics.speed_of(drift.velocity), drift.stats.acceleration_rate
    )
    run_frames(encounter, CORNER_OF_THE_SYSTEM, 240)

    assert drift.velocity == pytest.approx((0.0, 0.0), abs=1e-12), (
        f"still drifting at {drift.velocity} after 4 seconds"
    )
    travelled = drift.distance_to((0.0, 0.0))
    assert 0.0 < travelled <= braking_distance + 1.0, (
        f"travelled {travelled:.1f}px; the braking distance is {braking_distance:.1f}px"
    )


def testpick_target_neutralFaction_shouldIgnoreThePlayerUntilRelationsFlip():
    """Neutral means neutral: a Localhoster does not chase a player who has done nothing.

    Same geometry, same code, one grudge declared - and the target flips. This is
    the whole "political relations" feature in one test.
    """
    config = ai_config()
    localhost = make_ship(config, FACTION_LOCALHOSTER, 0.0, 0.0)
    player_position = (300.0, 0.0)

    peaceful = fleet(config, ships=[localhost], relations=PlayerRelations())
    assert peaceful.pick_target(localhost, player_position) is None

    aggrieved = fleet(config, ships=[localhost], relations=PlayerRelations())
    aggrieved.relations.declare_hostile_to_player(FACTION_LOCALHOSTER)
    target = aggrieved.pick_target(localhost, player_position)

    assert target is not None
    assert target.is_player is True
    assert target.position == player_position


def testpick_target_pirateShouldNeverTargetAnotherPirate():
    """The friendly-fire filter, at the target-selection end.

    Two pirates parked 20px apart, and a player 300px away: both must turn their
    guns on the player. A pirate that engaged its own neighbour would trade
    harmless shots with it for the entire encounter.
    """
    config = ai_config()
    near = make_ship(config, FACTION_PIRATE, 0.0, 0.0)
    far = make_ship(config, FACTION_PIRATE, 20.0, 0.0)
    encounter = fleet(config, ships=[near, far], relations=PlayerRelations())

    target = encounter.pick_target(near, (300.0, 0.0))

    assert target is not None and target.is_player is True


def testpick_target_shouldChooseTheNearestEngageableShipNotTheNearestShip():
    """A same-faction neighbour sitting between two enemies must not block the shot.

    Order matters here too: the Bobber is physically closer to the pirate than
    the Localhoster is, and is still not the target, because the pirate cannot
    hurt it.
    """
    config = ai_config()
    pirate = make_ship(config, FACTION_PIRATE, 0.0, 0.0)
    ally = make_ship(config, FACTION_PIRATE, 50.0, 0.0)
    foe = make_ship(config, FACTION_BOBBER, 120.0, 0.0)
    neutral = make_ship(config, FACTION_LOCALHOSTER, 400.0, 0.0)
    encounter = fleet(config, ships=[pirate, ally, foe, neutral], seed=3)

    target = encounter.pick_target(pirate, (5000.0, 5000.0))

    assert target is not None and target.ship is foe


def testpick_target_bothWarsides_shouldTargetEachOther():
    """The Localhoster/Bobber war runs with or without the player's involvement."""
    config = ai_config()
    localhost = make_ship(config, FACTION_LOCALHOSTER, -100.0, 0.0)
    bobber = make_ship(config, FACTION_BOBBER, 100.0, 0.0)
    encounter = fleet(config, ships=[localhost, bobber], relations=PlayerRelations())

    assert encounter.pick_target(localhost, (0.0, 2000.0)).ship is bobber
    assert encounter.pick_target(bobber, (0.0, 2000.0)).ship is localhost


def testadvanceFrame_targetsAreChosenFromTheFramesOpeningSnapshot():
    """Every ship decides before anyone moves.

    The geometry is built so that a single-pass implementation (decide, move,
    decide, move) would change the Bobber's answer: when the frame opens the
    Localhoster at 300px is nearer than the Pirate at 302px, but the Localhoster
    is drifting away at 10px/frame, so by the time a decide-after-moving
    implementation looks, the Pirate is the nearer ship.

    The heading is the tell. The Bobber starts at 45 degrees - exactly halfway
    between the two candidates - so one 3-degree turn step says which ship it was
    looking at when the frame opened: 42 degrees is the Localhoster on +x, 48 is
    the Pirate on +y. If that ever happens, fleet behaviour depends on spawn
    order, a bug that survives every test with one ship in it.
    """
    config = ai_config()
    localhost = make_ship(config, FACTION_LOCALHOSTER, 300.0, 0.0, velocity=(10.0, 0.0))
    bobber = make_ship(config, FACTION_BOBBER, 0.0, 0.0, heading=45.0)
    pirate = make_ship(config, FACTION_PIRATE, 0.0, 302.0)
    encounter = fleet(config, ships=[localhost, bobber, pirate], seed=4)

    encounter.advance_frame((0.0, 0.0))

    assert bobber.heading == pytest.approx(42.0), (
        "the Bobber turned toward the Pirate rather than the ship that was nearest "
        f"when the frame opened: heading {bobber.heading:.1f}"
    )


def testadvanceFrame_withinGunRange_shouldFireAtTheConfiguredRate():
    """Spec: "fire at max firing rate". The rate is config, not a constant.

    Two ships parked inside each other's band, holding the trigger for three
    seconds. The expected count is arithmetic rather than a magic number: a gun
    that cycles every ``60 / fire_rate`` frames is ready when it spawns and once
    per cooldown after that, so ``1 + (frames - 1) // cooldown`` shots each, times
    the two ships in the system. A cooldown implemented twice (once in the AI, once
    in the gun) would fire on a different cadence entirely, and the gaps between
    consecutive shots would not be exactly ``cooldown`` frames.
    """
    frames = 180
    for fire_rate in (0.5, 1.0, 3.0):
        config = ai_config(weapon_fire_rate=fire_rate)
        cooldown = int(weapon_cooldown_frames(fire_rate))
        encounter = fleet(config, (FACTION_PIRATE, 0.0, 0.0), (FACTION_BOBBER, 100.0, 0.0))

        shots = run_frames(encounter, CORNER_OF_THE_SYSTEM, frames)

        per_ship = 1 + (frames - 1) // cooldown
        assert len(shots) == 2 * per_ship, (
            f"fire_rate {fire_rate} (cooldown {cooldown} frames): {len(shots)} shots in "
            f"{frames} frames, expected {2 * per_ship} ({per_ship} per ship)"
        )
        by_owner: "dict[int, list[int]]" = {}
        for index, shot in enumerate(shots):
            by_owner.setdefault(id(shot.owner), []).append(index)
        for owner_shots in by_owner.values():
            assert len({
                later - earlier for earlier, later in zip(owner_shots, owner_shots[1:])
            }) == 1 or len(owner_shots) == 1, f"uneven trigger discipline: {owner_shots}"


def testadvanceFrame_triplingTheConfiguredFireRate_shouldTripleTheShots():
    """The knob, not the constant: same encounter, different config, different rate.

    Same seeded geometry, three configs. If the fire rate were hard-coded, the
    shot counts would be identical and this test would say so.
    """
    counts = {}
    for fire_rate in (1.0, 3.0):
        config = ai_config(weapon_fire_rate=fire_rate)
        encounter = fleet(
            config, (FACTION_PIRATE, 0.0, 0.0), (FACTION_BOBBER, 100.0, 0.0), seed=11
        )
        counts[fire_rate] = len(run_frames(encounter, CORNER_OF_THE_SYSTEM, 180))

    assert counts[3.0] == 3 * counts[1.0], f"1/s gave {counts[1.0]} shots, 3/s gave {counts[3.0]}"


def testadvanceFrame_shouldNotFireWhenTheTargetIsOutOfGunRange():
    """The range ceiling is the config's, and out of range means out of range."""
    config = ai_config(weapon_range=300)
    encounter = fleet(config, (FACTION_PIRATE, -1000.0, 0.0), (FACTION_BOBBER, 1000.0, 0.0))

    shots = run_frames(encounter, (0.0, 0.0), 60)

    assert shots == [], f"fired {len(shots)} shots at a target 2000px away"


def testadvanceFrame_aGunThatNeedsTimeToCycleShouldNotFireOnTheFrameItSpawns():
    """Two shots on consecutive frames is the classic double-cooldown bug.

    With a 1 shot/second gun, the gap between consecutive shots is 60 frames, and
    that gap must be exact rather than "roughly a second".
    """
    config = ai_config(weapon_fire_rate=1.0)
    encounter = fleet(config, (FACTION_PIRATE, 0.0, 0.0), (FACTION_BOBBER, 100.0, 0.0))

    shot_frames = []
    for frame in range(1, 241):
        if encounter.advance_frame((5000.0, 5000.0)):
            shot_frames.append(frame)

    assert len(shot_frames) >= 3
    gaps = {later - earlier for earlier, later in zip(shot_frames, shot_frames[1:])}
    assert gaps == {60}, f"shot spacing was {sorted(gaps)} frames, expected exactly [60]"


def testweaponCooldownFrames_shouldConvertPerSecondRatesToFrames():
    assert weapon_cooldown_frames(1.0) == 60.0
    assert weapon_cooldown_frames(2.0) == 30.0
    assert weapon_cooldown_frames(0.5) == 120.0
    assert math.isinf(weapon_cooldown_frames(0.0)), "a rate of zero never readies"


def testjitteredAim_shouldStayInsideTheJitterConeAndActuallyVary():
    """Spec: fire "with a configurable aim jitter".

    Two properties, both easy to get wrong: every shot must land inside the
    configured cone (a 4-degree jitter that sometimes throws 40 degrees is a
    different config key), and the draws must *vary* (a jitter that always
    returns the true bearing is a jitter that was never implemented).
    """
    from src.model.weapons import aim_is_within

    bearing = 37.0
    intended = physics.unit_from_heading_degrees(bearing)
    rng = random.Random(2024)
    bearings = set()
    for _ in range(400):
        aim = jittered_aim(bearing, 4.0, rng)
        assert aim_is_within(aim, intended, 4.0 + 1e-6), (
            f"aim {physics.heading_degrees_from_direction(*aim)} left the 4-degree cone"
        )
        bearings.add(round(physics.heading_degrees_from_direction(*aim), 3))

    assert len(bearings) > 200, "jitter never moved the shot"


def testjitteredAim_withZeroJitter_shouldAimDeadOn():
    """A config asking for perfect aim gets perfect aim, no noise floor."""
    bearing = 210.0
    assert jittered_aim(bearing, 0.0, random.Random(1)) == pytest.approx(
        physics.unit_from_heading_degrees(bearing), abs=1e-12
    )


def testplan_order_withATargetInsideTheBand_shouldFaceItHoldStillAndShoot():
    """The gun-range half of the spec: in reach, stop closing and fire.

    A hand-built :class:`Target` rather than a fleet, because what is under test
    is one ship's one frame: the facing it asked for, the burn (none) and the
    trigger state. A Target with no ``ship`` is the player, which is also the
    only way the AI is ever asked to aim at something that is not an NpcShip.
    """
    config = ai_config()  # weapon_range 300 -> band 255
    ship = make_ship(config, FACTION_PIRATE, 0.0, 0.0, heading=200.0)
    tuning = AiTuning(engage_range_fraction=0.85, aim_jitter_degrees=0.0)

    engagement = plan_order(ship, Target(position=(100.0, 0.0)), tuning, random.Random(1))

    assert engagement.target is not None and engagement.target.is_player is True
    assert engagement.distance == pytest.approx(100.0)
    assert engagement.motion == MOTION_COAST, "already inside the band and standing still"
    assert engagement.order.turn_to == pytest.approx(0.0), "the target sits on +x"
    assert engagement.order.burn is None and engagement.order.brake is False
    assert engagement.order.fire is True
    assert engagement.order.aim == pytest.approx((1.0, 0.0), abs=1e-12)


def testplan_order_withATargetOutsideGunRange_shouldBurnTowardItAndNotFire():
    """Out of gun range: the trigger stays off, and the burn is toward the target.

    A ship that fires at a target 600px away with a 300px gun is a ship whose
    projectile will die short - and Stage 11 would have to reimplement the range
    check that the AI already made.
    """
    config = ai_config()
    ship = make_ship(config, FACTION_PIRATE, 0.0, 0.0, heading=0.0)
    tuning = AiTuning(engage_range_fraction=0.85, aim_jitter_degrees=0.0)

    engagement = plan_order(ship, Target(position=(0.0, 600.0)), tuning, random.Random(1))

    assert engagement.motion == MOTION_CHASE
    assert engagement.order.fire is False
    assert engagement.order.aim is None
    assert engagement.order.burn == pytest.approx((0.0, 1.0), abs=1e-12)
    assert engagement.order.turn_to == pytest.approx(90.0)


def testplan_order_withNoTarget_shouldNotTurnNotFireAndOnlyBrake():
    """The "hold position" order: no facing change, no trigger, a bounded brake.

    A brake rather than a retrograde burn: a burn of ``acceleration`` against a
    ship moving slower than that would reverse it, and a ship holding position
    would then oscillate through zero forever.
    """
    ship = make_ship(ai_config(), FACTION_LOCALHOSTER, 0.0, 0.0, heading=90.0,
                     velocity=(0.0, 3.0))

    engagement = plan_order(ship, None, AiTuning(), random.Random(1))

    assert engagement.target is None
    assert engagement.motion == MOTION_BRAKE
    assert engagement.order.turn_to is None
    assert engagement.order.fire is False
    assert engagement.order.burn is None
    assert engagement.order.brake is True

    # And the brake itself lands on a dead stop rather than a reversed velocity.
    slowed = physics.brake(ship.velocity, ship.stats.acceleration_rate)
    assert physics.speed_of(slowed) == pytest.approx(2.8)
    stopped = physics.brake((0.0, 0.1), ship.stats.acceleration_rate)
    assert stopped == (0.0, 0.0), "a brake that overshoots zero never holds position"


def testaiTuning_withAnOutOfRangeBandFraction_shouldRefuseToBeBuilt():
    """A band of 1.2x weapon range means ships stop thrusting before they are in range.

    That is the "nobody ever fires" bug in config form, so it is rejected at
    construction rather than discovered in play.
    """
    for fraction in (0.0, -0.5, 1.5):
        with pytest.raises(ValueError):
            AiTuning(engage_range_fraction=fraction)


def testaiTuning_withANegativeJitter_shouldBeRejected():
    with pytest.raises(ValueError):
        AiTuning(aim_jitter_degrees=-1.0)


# ===========================================================================
# The shot record (Stage 11's seam)
# ===========================================================================


def testshot_muzzleVelocity_shouldComposeShipVelocityWithTheSpeedBonus():
    """Spec: projectile velocity is the ship's velocity plus the bonus along the aim.

    Pinned now because Stage 11 will otherwise be the first test of a rule the
    AI already half-implemented: the shot carries the aim *and* the ship's
    motion, and the bonus is config, not a literal.
    """
    shot = Shot(
        faction=FACTION_PIRATE,
        owner=object(),
        origin=(0.0, 0.0),
        direction=(1.0, 0.0),
        ship_velocity=(3.0, -4.0),
        weapon_power=40.0,
        weapon_range=1200.0,
    )

    assert shot.muzzle_velocity(8.0) == pytest.approx((11.0, -4.0))


def testshot_aimDirectionIsNormalisedAndCarriesItsOwnerIdentity():
    """The owner travels with the shot: Stage 11 needs it for two rules at once

    ("a projectile passes harmlessly through its own ship", and "only player
    projectiles earn a bounty"), and identity - not equality - is the only right
    test for two mutable ships.
    """
    shooter = make_ship(ai_config(), FACTION_BOBBER, 10.0, 20.0)
    shot = Shot(
        faction=FACTION_BOBBER,
        owner=shooter,
        origin=(10.0, 20.0),
        direction=(3.0, 4.0),
        ship_velocity=(0.0, 0.0),
        weapon_power=40.0,
        weapon_range=1200.0,
    )

    assert math.hypot(*shot.direction) == pytest.approx(1.0)
    assert shot.is_owner(shooter) is True
    assert shot.is_owner(make_ship(ai_config(), FACTION_BOBBER, 10.0, 20.0)) is False


def testshot_withAnUnknownFaction_shouldBeRejected():
    with pytest.raises(UnknownFaction):
        Shot(
            faction="smugglers", owner=object(), origin=(0.0, 0.0), direction=(1.0, 0.0),
            ship_velocity=(0.0, 0.0), weapon_power=1.0, weapon_range=1.0,
        )


def testadvanceFrame_shotsShouldBeAttributedToTheShipThatFiredThem():
    """The encounter hands Stage 11 the shooter, not just a muzzle flare."""
    config = ai_config(weapon_fire_rate=2.0)
    encounter = fleet(config, (FACTION_PIRATE, 0.0, 0.0), (FACTION_BOBBER, 80.0, 0.0))
    pirate, bobber = encounter.ships

    shots = run_frames(encounter, (5000.0, 5000.0), 60)

    assert {shot.owner for shot in shots} == {pirate, bobber}
    assert all(shot.faction == shot.owner.faction for shot in shots)


# ===========================================================================
# Encounter lifecycle through the real scene: despawn on jump
# ===========================================================================


def testnewGame_alphaShouldBeEmptyEvenWithSpawnChancePinnedToOne():
    """The player's home system is safe, and no config value can change that."""
    scene = game_scene(forced_spawn_config())

    assert scene.encounter.system == "Alpha"
    assert scene.encounter.is_empty is True


def testjumpArrival_shouldDespawnTheOldFleetAndSpawnTheNewSystems():
    """The gate's "despawn on jump".

    A jump Alpha -> Bravo with the spawn chance pinned to 100%: on arrival the
    scene must be holding a *Bravo* fleet of its own, and not one hull of
    anything that was in the previous system. Identity is what is asserted, not
    counts: a reused NpcShip keeps its shields, its wounds, and its heading, so
    "the same ship, renamed" would pass a count-only test.
    """
    config = forced_spawn_config()
    scene = game_scene(config)
    scene.game_state.set_position(600.0, 0.0)
    scene.system_map.select("Bravo")

    # Alpha is empty by rule, so seed the scene with a stand-in fleet to be sure
    # the despawn has something to remove.
    placeholder = fleet(config, (FACTION_PIRATE, 10.0, 10.0))
    scene.encounter = placeholder

    press(scene, pygame.K_j)
    for _ in range(400):
        scene.update()
        if scene.jumps.phase == "idle" and scene.system_map.current_system == "Bravo":
            break

    assert scene.system_map.current_system == "Bravo"
    assert scene.encounter is not placeholder
    assert scene.encounter.system == "Bravo"
    assert len(scene.encounter.ships) >= 1, "spawn chance is 100%: Bravo should have traffic"
    assert set(scene.encounter.ships).isdisjoint(placeholder.ships), (
        "a ship from the previous system survived the jump"
    )


def testjumpingOutOfASystem_shouldStopSimulatingItsShips():
    """Nobody is simulated in hyperspace, and nobody is left running afterwards.

    The frames of a jump are spent between two systems, so an NPC frame burnt
    during the burn is behaviour the player can never observe - and on arrival
    the old fleet is thrown away anyway.
    """
    config = forced_spawn_config()
    scene = game_scene(config)
    scene.game_state.set_position(600.0, 0.0)
    scene.system_map.select("Bravo")
    scene.encounter = fleet(config, (FACTION_PIRATE, 700.0, 60.0))
    before = [(ship.position, ship.velocity) for ship in scene.encounter.ships]

    press(scene, pygame.K_j)
    scene.update()  # the jump begins
    assert scene.jumps.is_active is True

    for _ in range(60):
        scene.update()
        assert scene.pending_shots == [], "a gun fired inside hyperspace"

    after = [(ship.position, ship.velocity) for ship in scene.encounter.ships]
    assert before == after or scene.encounter.system != "Alpha", (
        "the abandoned fleet kept flying during the burn"
    )


def testlandingAndLaunching_shouldNotReRollTheFleet():
    """A fleet belongs to the *visit*, not to the planet.

    Landing pauses the simulation; it must not be a free re-roll of the system's
    traffic (and, in Stage 11, an easy way to make a hostile pirate vanish by
    parking on a planet for a frame).
    """
    scene = game_scene(forced_spawn_config())
    scene.game_state.set_position(0.0, 0.0)  # inside landing range
    encounter_before = scene.encounter

    press(scene, pygame.K_l)
    scene.update()
    assert scene.game_state.is_landed is True

    scene.game_state.launch()
    scene.update()

    assert scene.encounter is encounter_before


def testjumpingOutAndBack_shouldDealADifferentFleet():
    """Spec: returning "does not remember the quantity or types of ships" from before.

    Bravo, Alpha, Bravo again. Alpha is the control: it is always empty, so the
    middle hop is a guaranteed gap in which nothing could carry over. The last
    assertion is on positions rather than counts because the spawn chance and the
    ship band are both pinned here - a fleet that came back identical in count
    *and* place would be the old fleet wearing a hat.
    """
    config = forced_spawn_config(ships_min=4, ships_max=4)
    scene = game_scene(config)

    jump(scene, "Bravo")
    bravo_fleet = scene.encounter
    bravo_positions = [ship.position for ship in bravo_fleet.ships]
    assert len(bravo_positions) == 4

    jump(scene, "Alpha")
    assert scene.encounter.is_empty, "Alpha is always empty"

    jump(scene, "Bravo")

    assert scene.encounter is not bravo_fleet
    assert [ship.position for ship in scene.encounter.ships] != bravo_positions, (
        "the second visit to Bravo reproduced the first visit's fleet exactly"
    )


def testdraw_shouldPublishTheSameFleetToTheViewAndTheHud():
    """One list, two renderers, one sync point.

    If the minimap and the game view ever get different Encounter objects, a
    player will read "one pirate" on the minimap while dodging two.
    """
    scene = game_scene(forced_spawn_config())
    scene.encounter = fleet(config_for_scene(), (FACTION_PIRATE, 100.0, 0.0))
    canvas = pygame.Surface(SCREEN_SIZE)

    scene.draw(canvas)

    assert scene.tactical.encounter is scene.encounter
    assert scene.hud.contacts == scene.encounter.ships


def config_for_scene() -> dict:
    """Kept as a function so the test above stays a one-liner with no hidden config."""
    return forced_spawn_config()


# ===========================================================================
# Presentation: hulls in the game view, contacts on the minimap
# ===========================================================================


def tactical_view(config: "dict | None" = None) -> "tuple[TacticalView, GameState]":
    config = config or ai_config()
    state = GameState(config, rng=random.Random(7))
    view = TacticalView(_StackManager(config), state)
    return view, state


def testnpcShipSurfaces_shouldBeDistinctSilhouettesPerFaction():
    """Spec's "other ship designs": arrow, saucer, and a pronged raider.

    Compared as pixel counts and shapes rather than by eye: three faction hulls
    that paint the same number of pixels in the same pattern are three copies of
    one sprite with different colours bolted on.
    """
    surfaces = {
        faction: npc_ship_surface(faction, 40, 20)
        for faction in (FACTION_LOCALHOSTER, FACTION_BOBBER, FACTION_PIRATE)
    }

    assert len({surface.get_size() for surface in surfaces.values()}) == 1, (
        "all ships should be roughly the same size as the player's ship"
    )

    painted = {
        faction: sum(
            1 for x in range(40) for y in range(20) if surfaces[faction].get_at((x, y))[3] > 0
        )
        for faction in surfaces
    }
    assert len(set(painted.values())) == 3, f"hull silhouettes are not distinct: {painted}"

    # An arrow tapers: few pixels on the nose row, many mid-hull. A saucer is the
    # opposite (wide and rounded), and the pirate has prongs (gaps at mid-height
    # at the aft edge that neither of the others has).
    pirate = surfaces[FACTION_PIRATE]
    assert pirate.get_at((0, 10))[3] > 0, "the pirate's tail should be on the centre line"
    assert pirate.get_at((2, 1))[3] == 0 and pirate.get_at((2, 18))[3] == 0, (
        "the pirate's aft edge should be pronged, not a solid wall"
    )


def testtacticalView_shouldDrawNpcHullsInTheirFactionColoursOnTheCorrectSide():
    """A Bobber to the player's east must appear on the east of the game view.

    Colour plus position: the hulls are drawn from the same world coordinates the
    simulation moved, in the faction's colour, and are not decorative.
    """
    config = ai_config()
    view, state = tactical_view(config)
    east = make_ship(config, FACTION_BOBBER, 150.0, 0.0, heading=180.0)
    west = make_ship(config, FACTION_LOCALHOSTER, -150.0, 0.0, heading=0.0)
    view.encounter = fleet(config, ships=[east, west])

    canvas = pygame.Surface(SCREEN_SIZE)
    view.draw(canvas)

    view_width = 683
    yellow = _count_colour_in(canvas, faction_color(FACTION_BOBBER), (0, 0, view_width, 768))
    cyan = _count_colour_in(canvas, faction_color(FACTION_LOCALHOSTER), (0, 0, view_width, 768))
    assert yellow > 20 and cyan > 20, "no NPC hulls were drawn at all"

    yellow_pixels = [
        (x, y)
        for y in range(768)
        for x in range(view_width)
        if canvas.get_at((x, y))[:3] == faction_color(FACTION_BOBBER)
    ]
    assert sum(x for x, _ in yellow_pixels) / len(yellow_pixels) > view_width / 2, (
        "the Bobber east of the player was drawn west of it"
    )


def testtacticalView_shouldNotDrawHullsThatAreOffScreen():
    """A system is 2000px across and the view is 683; culling is not optional.

    Not a performance nicety only: an unculled blit at an arbitrary coordinate is
    how a pirate 900px away ends up painted on top of the HUD column.
    """
    config = ai_config()
    view, state = tactical_view(config)
    far = make_ship(config, FACTION_PIRATE, 1400.0, 0.0)
    view.encounter = fleet(config, ships=[far])

    canvas = pygame.Surface(SCREEN_SIZE)
    view.draw(canvas)

    assert _count_colour(canvas, faction_color(FACTION_PIRATE)) == 0, (
        "an off-screen pirate was painted somewhere on the window"
    )


def testtacticalView_playerShipShouldBeDrawnOverAnNpcHullOnTopOfIt():
    """Ships pass through each other, but the player must never be hidden by one."""
    config = ai_config()
    view, state = tactical_view(config)
    bodyguard = make_ship(config, FACTION_PIRATE, 0.0, 0.0)
    view.encounter = fleet(config, ships=[bodyguard])

    canvas = pygame.Surface(SCREEN_SIZE)
    view.draw(canvas)

    centre = (341, 384)
    # The shuttle's nose block has its own colour (Stage 4); if it survived, the
    # player was drawn last.
    nose_colour = (150, 210, 230)
    assert _count_colour(canvas, nose_colour) > 0, (
        "a pirate sitting on the player painted the player out"
    )
    assert canvas.get_at(centre)[:3] != faction_color(FACTION_PIRATE) or (
        _count_colour(canvas, nose_colour) > 0
    )


def testhudMinimap_shouldColourContactsByFaction():
    """The minimap answers "who is out there", not merely "how many".

    Red pirate, cyan Localhoster, yellow Bobber, all as 2x2 markers.
    """
    config = ai_config()
    state = GameState(config, rng=random.Random(2))
    hud = HudView(_StackManager(config), state)
    hud.contacts = [
        make_ship(config, FACTION_PIRATE, 100.0, 0.0),
        make_ship(config, FACTION_LOCALHOSTER, -100.0, 0.0),
        make_ship(config, FACTION_BOBBER, 0.0, 100.0),
    ]

    canvas = pygame.Surface(SCREEN_SIZE)
    hud.draw(canvas)

    for faction in FACTIONS:
        assert _count_colour(canvas, faction_color(faction)) == 4, (
            f"{faction}: expected one 2x2 marker, got "
            f"{_count_colour(canvas, faction_color(faction))}px"
        )


# ===========================================================================
# Config: the new keys, and the difficulty they are supposed to encode
# ===========================================================================


NPC_KEYS = {
    "spawn_chance_near",
    "spawn_chance_far",
    "ships_min",
    "ships_max",
    "stat_multiple",
    "stat_variance",
    "aim_jitter_degrees",
    "engage_range_fraction",
    "min_distance_from_player",
}


def testshippedConfigs_shouldAllCarryTheIdenticalNpcKeySet():
    """Unrecognised keys are fatal, so all three files must move together."""
    for name in CONFIG_FILES:
        with open(os.path.join(GAME_ROOT, name), encoding="utf-8") as handle:
            npc_section = json.load(handle)["npc"]
        assert set(npc_section) == NPC_KEYS, f"{name} drifted from the npc schema"


def testshippedConfigs_shouldGetMoreDangerousFromEasyToHard():
    """The difficulty files must actually differ where this stage touches.

    The one-line version of Stage 14's config sweep: if Easy and Hard agree on
    spawn chance and hull strength, the difficulty choice is a decoration.
    """
    chances, multiples = {}, {}
    for name in CONFIG_FILES:
        with open(os.path.join(GAME_ROOT, name), encoding="utf-8") as handle:
            npc = json.load(handle)["npc"]
        difficulty = name.split("_")[1].split(".")[0]
        chances[difficulty] = (npc["spawn_chance_near"], npc["spawn_chance_far"])
        multiples[difficulty] = npc["stat_multiple"]

    assert chances["easy"] < chances["medium"] < chances["hard"], (
        f"spawn chances are not ordered by difficulty: {chances}"
    )
    assert multiples["easy"] < multiples["medium"] < multiples["hard"], (
        f"NPC hull strength is not ordered by difficulty: {multiples}"
    )


def testshippedConfigs_engagementBandsShouldFitInsideTheirOwnSystems():
    """A tuning rule the loader deliberately does not enforce, so this test does.

    ``engage_range_fraction`` x ``player_ship.weapon_range`` is the radius a ship
    parks at around its target. Make it larger than half the system and there is
    simply not enough universe: every ship presses itself against the system
    boundary instead of holding its band. Nothing crashes and nobody dies, the
    fleet just never behaves the way the numbers say it should - which is exactly
    the kind of thing a config retune in Stage 14 would introduce unnoticed.
    """
    for name in CONFIG_FILES:
        with open(os.path.join(GAME_ROOT, name), encoding="utf-8") as handle:
            values = json.load(handle)
        band = values["npc"]["engage_range_fraction"] * values["player_ship"]["weapon_range"]
        half_system = values["tactical"]["system_pixel_size"] / 2.0

        assert band <= half_system, (
            f"{name}: an engagement band of {band:.0f}px does not fit in a system whose "
            f"half-width is {half_system:.0f}px"
        )


def testloadConfig_withAnUnknownNpcKey_shouldBeFatal(config_factory):
    """Unrecognised keys are fatal (spec, Validation)."""
    config_dir = config_factory()
    path = os.path.join(config_dir, CONFIG_FILES[0])
    with open(path, encoding="utf-8") as handle:
        values = json.load(handle)
    values["npc"]["spawn_chance_med"] = 0.5
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(values, handle)

    with pytest.raises(Exception):
        load_config(config_dir)


def testloadConfig_withAMissingNpcKey_shouldBeFatal(config_factory):
    """Missing keys are fatal (spec, Validation) - actually missing, not merely null.

    Editing the JSON rather than overriding through the fixture, because the
    fixture's dotted-path override *sets* a value: a null would be an invalid
    value, and the two failure modes need different messages in the log.
    """
    config_dir = config_factory()
    path = os.path.join(config_dir, CONFIG_FILES[0])
    with open(path, encoding="utf-8") as handle:
        values = json.load(handle)
    del values["npc"]["ships_min"]
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(values, handle)

    with pytest.raises(Exception):
        load_config(config_dir)


@pytest.mark.parametrize(
    "dotted_key,value,expectation",
    [
        ("npc.spawn_chance_near", 1.5, "a probability above 1"),
        ("npc.spawn_chance_far", -0.1, "a negative probability"),
        ("npc.spawn_chance_near", 0.9, "near above far (the ramp would descend)"),
        ("npc.ships_min", 0, "a zero-ship spawn band"),
        ("npc.ships_min", 5, "ships_min above ships_max"),
        ("npc.stat_variance", 1.0, "a variance that can roll a stat to zero"),
        ("npc.stat_variance", -0.2, "a negative variance"),
        ("npc.stat_multiple", 0.0, "NPCs made of nothing"),
        ("npc.engage_range_fraction", 0.0, "a zero-width engagement band"),
        ("npc.engage_range_fraction", 1.5, "ships that stop thrusting out of gun range"),
        ("npc.aim_jitter_degrees", -1.0, "a negative jitter cone"),
        # 3000px of clearance in a 2000px system: no candidate point can satisfy it.
        ("npc.min_distance_from_player", 3000, "clearance wider than the system"),
    ],
)
def testloadConfig_withAnImpossibleNpcSetting_shouldBeFatalAtStartup(
    config_factory, dotted_key, value, expectation
):
    """GIVEN an ``npc`` value the spawner could not honour, THEN the game refuses to start.

    Every one of these would otherwise be discovered as a crash (``randint`` with
    a reversed band) or a silent gameplay collapse (nobody ever fires, because the
    band they stop at is beyond their gun's range) - both worse than a startup
    error naming the key.
    """
    if dotted_key.endswith("ships_min") and value == 5:
        # ships_min above ships_max needs both ends moved; one override alone is legal.
        with pytest.raises(Exception):
            load_config(config_factory(overrides={
                dotted_key: value, "npc.ships_max": 2,
            }))
        return
    with pytest.raises(Exception):
        load_config(config_factory(overrides={dotted_key: value}))


def testloadConfig_withTheShippedNpcSections_shouldAllProduceUsableRules():
    """Sanity for the sanity checks: all three difficulties build working rules."""
    for name, config in load_config(GAME_ROOT).items():
        rules = spawn_rules(config)
        assert 0.0 <= rules.spawn_chance_near <= rules.spawn_chance_far <= 1.0
        assert 1 <= rules.ships_min <= rules.ships_max
        assert 0.0 < rules.engage_range_fraction <= 1.0
        assert rules.min_distance_from_player < config["tactical"]["system_pixel_size"]


def testspawnRules_fromAHandBuiltSection_shouldRejectNonsenseDirectly():
    """Rules built outside the loader (tests, tooling, a future save file) still guard themselves."""
    with pytest.raises(ValueError):
        SpawnRules.from_config({})

    with pytest.raises(ValueError):
        SpawnRules(
            spawn_chance_near=0.9, spawn_chance_far=0.2, ships_min=1, ships_max=4,
            stat_multiple=4.0, stat_variance=0.5, aim_jitter_degrees=4.0,
            engage_range_fraction=0.85, min_distance_from_player=350.0,
        )


def testnpcRules_areDrivenByConfigNotByConstants():
    """The Stage 14 sweep, pre-empted: change the knob, change the behaviour.

    Weapon range (which NPCs inherit) sets the band; ``engage_range_fraction``
    scales it; ``stat_multiple`` rescales the hull. If any of those were a
    constant in the AI, one of these three assertions fails.
    """
    narrow = ai_config(weapon_range=200)
    wide = ai_config(weapon_range=800)
    assert spawn_rules(narrow).ai_tuning.band_for(
        starting_stats(narrow).weapon_range
    ) == pytest.approx(170.0)
    assert spawn_rules(wide).ai_tuning.band_for(
        starting_stats(wide).weapon_range
    ) == pytest.approx(680.0)

    beefy = forced_spawn_config()
    beefy["npc"]["stat_multiple"] = 7.0
    rolled = roll_npc_stats(starting_stats(beefy), 7.0, 0.0, random.Random(1))
    assert rolled.max_shields == pytest.approx(350.0)
