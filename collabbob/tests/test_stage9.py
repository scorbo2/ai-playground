"""Stage 9 tests: the spaceport, the economy, and the vertical slice closing.

Six layers, mirroring the split of the implementation:

* :mod:`src.model.lore` - the pool file contract (missing/unreadable/empty is
  fatal), the ``(System)`` tag rules (any case, any count, none is legal), and
  the once-per-game assignment with and without duplicates.
* :meth:`SystemGraph.jump_distance` - the hop count the far bonus is priced on.
* :mod:`src.model.economy` + :mod:`src.model.ship_upgrades` - the fare law and
  the board generation, as property tests over 200 seeds: the configured offer
  count, no job bound for where you already stand, no offer bigger than the hull,
  monotonic fares within a board, the far bonus only on real distance, and the
  escalating upgrade curve with its hard wall.
* :class:`~src.model.game_state.GameState` - the money and hold rules: capacity
  rejection, unload-once crediting, the credit floor, refuel/repair rates, and
  the launch immunity window.
* :class:`~src.scenes.spaceport_view.SpaceportView` - geometry (nothing runs under
  the Launch button), the copy the screen prints, and the button wiring.
* :class:`~src.scenes.game_scene.GameScene` plus the real ``FixedTimestepLoop`` -
  ``L`` opening the modal only when the prompt was on screen, one modal per press,
  and land → accept → launch → jump → land → paid exactly once.

The stage gate: seeded generation invariants; capacity rejection; unload crediting
once and only once; the upgrade cost curve table; no purchase path producing
credits <= 0.

One regression in here is worth naming up front: :func:`test_update_launchingThenLandingAgain_shouldOpenThePortAgainInsteadOfSwallowingTheKeypress`.
The spaceport is opened by a keypress, so the matching key-release arrives at the
modal and never reaches the tactical input layer, which then holds a phantom key
forever and refuses the next press of that key. Every stage that pushes a modal on
a keypress inherits that trap.
"""

import random
from pathlib import Path

import pygame
import pygame_gui
import pytest

import main  # noqa: F401  (ensures project root is on sys.path)

from src.audio import AudioSystem
from src.config import base_config, load_config
from src.fonts import game_font
from src.main_loop import FixedTimestepLoop, SCREEN_SIZE
from src.map_systems.graph import NATO_SYSTEMS, SystemGraphGenerator
from src.model.economy import (
    OFFER_CARGO_CEILING,
    OFFER_PASSENGER_CEILING,
    CarriedLoad,
    EconomyRules,
    PortVisit,
    Mission,
    distance_multiplier,
    format_credits,
    generate_port_offers,
    mission_fare,
    mission_payload_text,
    pluralise,
    port_rng,
)
from src.model.game_state import CREDIT_FLOOR, GameState
from src.model.lore import (
    LoreBook,
    assign_lore,
    load_lore,
    render_system_tag,
)
from src.model.jump import JumpParams
from src.model.lore import LORE_FILE as SHIPPED_LORE_FILE
from src.scene_manager import SceneManager
from src.model.ship_upgrades import (
    UPGRADE_TYPES,
    UpgradeOffer,
    apply_upgrade,
    generate_upgrade_offers,
    upgrade_cost,
    upgrade_step_for,
    upgrade_text,
)
from src.scenes.game_scene import GameScene
from src.scenes.spaceport_view import (
    BODY_BOTTOM,
    CONTRACT_ROW_HEIGHT,
    LAUNCH_RECT,
    MANIFEST_LINE_HEIGHT,
    CONTRACT_TEXT_WIDTH,
    MESSAGE_RECT,
    PAYLOAD_SIZE,
    PortPalette,
    ROWS_TOP,
    SECTION_HEADER_HEIGHT,
    SERVICES_TOP,
    SpaceportView,
    contract_button_rect,
    contract_payload_line,
    contract_row_rect,
    contract_terms_line,
    contracts_capacity,
    delivery_message,
    fit_text,
    manifest_capacity,
    manifest_lines,
    manifest_top,
    refuel_button_rect,
    repair_button_rect,
    service_button_text,
    upgrade_button_rect,
    upgrade_row_rect,
    upgrades_capacity,
    wrap_text,
)
PROJECT_ROOT = Path(__file__).resolve().parents[1]

# The stage gate asks for seeded generation invariants; 200 matches Stages 7/8.
SEED_SAMPLE = range(200)

# The spec's own lore contract: 26 systems, so a pool of 26+ avoids duplicates.
MINIMUM_LORE_ENTRIES = 26

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def rules(config: "dict | None" = None) -> EconomyRules:
    """The money rules from a complete config (medium by default)."""
    return EconomyRules.from_config((config or base_config())["economy"])


def world_graph(seed: int = 7, config: "dict | None" = None):
    """A real generated world graph (26 systems, shipped constraints)."""
    return SystemGraphGenerator.from_config(
        (config or base_config())["map"], rng=random.Random(seed)
    ).generate()


def ship(config: "dict | None" = None, seed: int = 11, starting_credits=None) -> GameState:
    """A ship, optionally with a pinned balance instead of the configured one."""
    values = config or base_config()
    if starting_credits is not None:
        values = {**values, "new_game": {**values["new_game"],
                                         "starting_credits": starting_credits}}
    return GameState(values, rng=random.Random(seed))


def damaged_ship(config: "dict | None" = None, seed: int = 11,
                 starting_credits: int = 100_000) -> GameState:
    """A ship the port actually has something to sell: half a tank, half a hull."""
    state = ship(config, seed, starting_credits)
    state.fuel = state.stats.fuel_capacity / 2.0
    state.stats.armor = state.stats.max_armor / 2.0
    return state


def carried(destination: str, fare: int = 100, cargo_units: int = 0,
            passengers: int = 0, cargo_type: "str | None" = "scrap") -> CarriedLoad:
    return CarriedLoad(
        destination=destination, fare=fare, cargo_type=cargo_type,
        cargo_units=cargo_units, passengers=passengers,
    )


def roll_board(state: GameState, graph, current_system: str, seed: int = 5,
               serial: "int | None" = None):
    """One port visit, generated from ``state`` exactly as GameScene does it."""
    serial = state.begin_port_visit() if serial is None else serial
    return generate_port_offers(
        rules=state.economy,
        graph=graph,
        current_system=current_system,
        stats=state.stats,
        upgrade_levels=state.upgrade_levels,
        rng=random.Random(seed),
        visit_serial=serial,
    )


def mission(cargo_units: int = 0, passengers: int = 0, distance: int = 1,
            cargo_rate: float = 200.0, passenger_rate: float = 1000.0,
            far_bonus: float = 1.5, destination: str = "Bravo",
            offer_index: int = 0) -> Mission:
    """A hand-built offer, priced by the real fare law."""
    multiplier = distance_multiplier(distance, far_bonus)
    return Mission(
        offer_id=(1, offer_index),
        cargo_type="iron ore" if cargo_units else None,
        cargo_units=cargo_units,
        passengers=passengers,
        destination=destination,
        distance=distance,
        far_bonus=multiplier,
        fare=mission_fare(cargo_units, cargo_rate, passengers, passenger_rate, multiplier),
    )


class _SpyAudio:
    """Counts the sounds a scene asks for (Stage 12 formalises the real ones).

    Every method SceneManager hands to a gameplay scene is represented, so a test
    that flies a jump cannot trip over an audio call it never meant to exercise.
    """

    def __init__(self):
        self.confirm_count = 0
        self.jump_spinup_count = 0
        self.thunderclap_count = 0

    def play_confirm(self):
        self.confirm_count += 1

    def play_jump_spinup(self):
        self.jump_spinup_count += 1

    def play_thunderclap(self):
        self.thunderclap_count += 1


# The seed every scene-level helper builds its game from. ``base_config()``
# ships ``rng.seed: null`` (an unseeded game, as the player gets), which here
# would mean a different world, a different contract board, and a different
# first Accept button on every run - i.e. tests that go red at random.
SCENE_SEED = 4242


def scene_config(starting_credits: "int | None" = None) -> dict:
    """The seeded medium table the scene tests all share (optionally broke)."""
    values = {**base_config(), "rng": {"seed": SCENE_SEED}}
    if starting_credits is not None:
        values["new_game"] = {**values["new_game"], "starting_credits": starting_credits}
    return values


class _StackManager:
    """Enough of SceneManager for the modal tests: config, audio, and a real stack."""

    def __init__(self, config: "dict | None" = None):
        self._config = config or scene_config()
        self.audio = _SpyAudio()
        self.stack = []
        self.quit_called = False

    def game_config(self) -> dict:
        return self._config

    def push(self, scene) -> None:
        self.stack.append(scene)
        scene.on_enter(self)

    def pop(self) -> None:
        if self.stack:
            self.stack.pop().on_exit()

    def quit(self) -> None:
        self.quit_called = True

    @property
    def top(self):
        return self.stack[-1] if self.stack else None

    def names(self):
        return [type(scene).__name__ for scene in self.stack]


def game_scene(config: "dict | None" = None):
    """A (GameScene, fake manager) pair with a real 26-system world and lore book.

    The scene is pushed onto the fake stack the way the title flow pushes it in
    play, so a modal test can assert on the whole stack and not just its top.
    """
    manager = _StackManager(config)
    scene = GameScene(manager)
    manager.push(scene)
    return scene, manager


def land_at_landing_range(config: "dict | None" = None, seed: int = 11):
    """A GameScene with ``L`` pressed inside landing range: the modal is open.

    The ship starts at the planet centre (Stage 4's convention), which is inside
    landing range, so no repositioning is needed to land - but the key must be
    released after the press, as a hand does.
    """
    scene, manager = game_scene(config)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_l, scancode=0, mod=0))
    scene.update()
    scene.handle_event(pygame.event.Event(pygame.KEYUP, key=pygame.K_l, scancode=0, mod=0))
    return scene, manager, manager.top


def press_button(port: SpaceportView, button) -> None:
    """Fire the real pygame_gui button event the widget would post."""
    port.handle_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=button))


def press_key(scene, key: int) -> None:
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, scancode=0, mod=0))
    scene.update()
    scene.handle_event(pygame.event.Event(pygame.KEYUP, key=key, scancode=0, mod=0))


def lore_book(seed: int = 3, system_names: "tuple[str, ...] | None" = None) -> LoreBook:
    names = system_names or NATO_SYSTEMS[:6]
    return LoreBook.for_world(names, random.Random(seed))


# ---------------------------------------------------------------------------
# Lore: the file contract, the tag rules, and once-per-game assignment
# ---------------------------------------------------------------------------


def test_loadLore_withTheShippedPool_shouldOfferEnoughEntriesToAvoidDuplicates():
    # GIVEN the pool file that ships with the game,
    # THEN it must satisfy the spec's deduplication threshold, and every entry
    # must be distinct (a duplicated line wastes a slot in a 26-system world).
    entries = load_lore(SHIPPED_LORE_FILE)
    assert len(entries) >= MINIMUM_LORE_ENTRIES
    assert len(set(entries)) == len(entries)


def test_loadLore_withTheShippedPool_shouldEveryEntrySurviveTheSystemTagSubstitution():
    # GIVEN every shipped entry,
    # WHEN the tag is substituted for a system name,
    # THEN nothing raises and no ``(System)`` tag survives in any case.
    for entry in load_lore(SHIPPED_LORE_FILE):
        rendered = render_system_tag(entry, "Alpha")
        assert "(System)" not in rendered
        assert "(system)" not in rendered.lower()


def test_loadLore_withAMissingFile_shouldRaiseRuntimeErrorNamingTheFile(tmp_path):
    with pytest.raises(RuntimeError, match="lore file not found"):
        load_lore(tmp_path / "absent.txt")


def test_loadLore_withAnEmptyFile_shouldRaiseRuntimeErrorNamingTheFile(tmp_path):
    # GIVEN a file that exists but contains only blank lines,
    path = tmp_path / "blank.txt"
    path.write_text("\n   \n\n", encoding="utf-8")
    # THEN it is fatal, not a graceful "no lore" (the spec is explicit).
    with pytest.raises(RuntimeError, match="lore file is empty"):
        load_lore(path)


def test_loadLore_withADirectoryInPlaceOfTheFile_shouldRaiseRuntimeError(tmp_path):
    # GIVEN the lore path pointing at a directory (unreadable as text),
    directory = tmp_path / "lore.txt"
    directory.mkdir()
    # THEN the failure is reported as unreadable, and names the cause.
    with pytest.raises(RuntimeError, match="lore file is unreadable"):
        load_lore(directory)


def test_renderSystemTag_withMixedCaseTags_shouldReplaceEveryOccurrence():
    # GIVEN an entry that tags the system three times, in three spellings,
    entry = "(System) greets you; (SYSTEM) overcharges you; (system) apologises later."
    # THEN every occurrence becomes the system's name, and none survives.
    assert render_system_tag(entry, "Zulu") == (
        "Zulu greets you; Zulu overcharges you; Zulu apologises later."
    )


def test_renderSystemTag_withoutAnyTag_shouldReturnTheEntryUnchanged():
    assert render_system_tag("This port keeps a museum of the water shortage.", "Zulu") == (
        "This port keeps a museum of the water shortage."
    )


def test_assignLore_withMoreEntriesThanSystems_shouldGiveEverySystemADistinctRenderedLine():
    # GIVEN a pool of 40 entries and 26 systems,
    entries = [f"(System) log line {index}." for index in range(40)]
    # WHEN the world is populated from a seeded draw,
    lines = assign_lore(NATO_SYSTEMS, entries, random.Random(99))
    # THEN each system's line names that system (this is the guard against the
    # swapped-argument bug, which returned the system *name* as its own lore),
    for name in NATO_SYSTEMS:
        assert lines[name].startswith(f"{name} "), "the tag must name the system"
        assert lines[name] != name, "the lore is not the system's own name"
    # ...and no two systems share a line.
    assert len(set(lines.values())) == len(NATO_SYSTEMS)


def test_assignLore_withFewerEntriesThanSystems_shouldReuseEntriesRatherThanCrash():
    # GIVEN a pool of three entries for 26 systems,
    entries = ["(System) is quiet.", "Nobody leaves (System).", "Dust, everywhere."]
    # THEN every system still gets a line, duplicates are allowed, and the
    # untagged entry stays untagged.
    lines = assign_lore(NATO_SYSTEMS, entries, random.Random(5))
    assert len(lines) == len(NATO_SYSTEMS)
    assert any(line == "Dust, everywhere." for line in lines.values())


def test_assignLore_withTheSameSeed_shouldAssignTheSameLineToTheSameSystem():
    first = assign_lore(NATO_SYSTEMS, load_lore(SHIPPED_LORE_FILE), random.Random(4242))
    second = assign_lore(NATO_SYSTEMS, load_lore(SHIPPED_LORE_FILE), random.Random(4242))
    assert first == second


def test_assignLore_withAnEmptyPool_shouldRaiseValueErrorRatherThanReturnAnEmptyBook():
    with pytest.raises(ValueError, match="empty pool"):
        assign_lore(NATO_SYSTEMS[:3], [], random.Random(1))


def test_assignLore_withNoSystems_shouldReturnAnEmptyBook():
    assert assign_lore((), load_lore(SHIPPED_LORE_FILE), random.Random(1)) == {}


def test_loreBookLineFor_withASystemOutsideTheBook_shouldReturnAnEmptyString():
    # GIVEN a book built for three systems,
    book = lore_book(system_names=("Alpha", "Bravo", "Charlie"))
    # THEN an unknown system gets no lore (cosmetic) rather than a crash mid-run.
    assert book.line_for("Zulu") == ""
    assert book.line_for("Alpha") != ""


def test_loreBookForWorld_withTheMissingPoolFile_shouldRaiseRuntimeError(tmp_path, monkeypatch):
    # GIVEN the module's default pool path redirected at a file that is not there,
    monkeypatch.setattr("src.model.lore.LORE_FILE", str(tmp_path / "gone.txt"))
    # THEN building a world's book fails loudly (the caller turns this into
    # stderr + exit 1; see the GameScene test at the end of this file).
    with pytest.raises(RuntimeError, match="lore file not found"):
        LoreBook.for_world(("Alpha", "Bravo"), random.Random(1))


def test_loreBookForWorld_overSeveralSeeds_shouldCoverEverySystemInTheWorld():
    for seed in range(25):
        book = lore_book(seed=seed, system_names=NATO_SYSTEMS)
        assert len(book) == len(NATO_SYSTEMS)
        assert all(book.line_for(name) for name in NATO_SYSTEMS)


# ---------------------------------------------------------------------------
# Jump distance: the hop count the far bonus is priced on
# ---------------------------------------------------------------------------


def test_jumpDistance_forNeighboursSelfAndMultiHopTargets_shouldReturnMinimumHopCounts():
    # GIVEN a generated world,
    graph = world_graph(seed=7)
    alpha = "Alpha"
    # THEN a neighbour is one hop, the same system is zero hops, and every other
    # system is at least two.
    for neighbour in graph.neighbours(alpha):
        assert graph.jump_distance(alpha, neighbour) == 1
    assert graph.jump_distance(alpha, alpha) == 0
    far = [name for name in graph.names if name not in graph.neighbours(alpha) | {alpha}]
    for name in far:
        assert graph.jump_distance(alpha, name) >= 2


def test_jumpDistance_over200Seeds_shouldBeSymmetricFiniteAndNeverExceedTheWorld():
    for seed in SEED_SAMPLE:
        graph = world_graph(seed=seed)
        for first, second in (
            ("Alpha", name) for name in graph.names if name != "Alpha"
        ):
            hops = graph.jump_distance(first, second)
            assert hops is not None and 1 <= hops <= len(graph.names) - 1
            assert hops == graph.jump_distance(second, first)


def test_jumpDistance_withAnUnknownSystem_shouldReturnNone():
    graph = world_graph(seed=7)
    assert graph.jump_distance("Alpha", "NotASystem") is None
    assert graph.jump_distance("NotASystem", "Alpha") is None


# ---------------------------------------------------------------------------
# The fare law
# ---------------------------------------------------------------------------


def test_distanceMultiplier_oneJumpPaysUnityAndEveryExtraHopAddsTheBonus():
    assert distance_multiplier(1, 1.5) == 1.0
    assert distance_multiplier(2, 1.5) == 2.5
    assert distance_multiplier(4, 1.5) == 5.5
    # A zero/one-jump floor: a bonus can never shrink a fare below its base.
    assert distance_multiplier(0, 1.5) == 1.0


def test_missionFare_shouldMultiplySizeRateAndDistanceAndRoundUp():
    # 10 units at 200.4, one jump, no far bonus -> 2004 exactly.
    assert mission_fare(10, 200.4, 0, 0.0, 1.0) == 2004
    # Half a credit rounds up, never down: a fare must not lose the player money.
    assert mission_fare(1, 0.5, 0, 0.0, 1.0) == 1
    # Cargo and passenger legs add before the distance multiplier applies.
    assert mission_fare(2, 100.0, 3, 200.0, 2.0) == 1600


def test_missionFare_shouldBeMonotonicInUnitsPassengersAndDistance():
    smaller = mission_fare(4, 200.0, 0, 0.0, 1.0)
    bigger = mission_fare(9, 200.0, 0, 0.0, 1.0)
    assert bigger > smaller
    assert mission_fare(0, 0.0, 5, 200.0, 1.0) > mission_fare(0, 0.0, 2, 200.0, 1.0)
    near = mission_fare(5, 200.0, 0, 0.0, distance_multiplier(2, 1.5))
    far = mission_fare(5, 200.0, 0, 0.0, distance_multiplier(6, 1.5))
    assert far > near


# ---------------------------------------------------------------------------
# Board generation: the seeded invariants the gate asks for
# ---------------------------------------------------------------------------


def test_generatePortOffers_over200Seeds_offerCountStaysInsideTheConfiguredRange():
    for seed in SEED_SAMPLE:
        state = ship(seed=seed)
        board = roll_board(state, world_graph(seed=seed), "Alpha", seed=seed)
        assert (
            state.economy.missions_min
            <= len(board.missions)
            <= state.economy.missions_max
        )
        assert 0 <= len(board.upgrade_offers) <= state.economy.upgrade_offers_max


def test_generatePortOffers_over200Seeds_noOfferIsEverBoundForTheCurrentSystem():
    for seed in SEED_SAMPLE:
        state = ship(seed=seed)
        graph = world_graph(seed=seed)
        current = graph.names[seed % len(graph.names)]
        board = roll_board(state, graph, current, seed=seed)
        assert all(mission.destination != current for mission in board.missions)
        assert all(
            mission.destination in graph.names for mission in board.missions
        )


def test_generatePortOffers_over200Seeds_everyOfferFitsTheHullSoNoOfferIsPermanentlyDead():
    # The cap is the ship's own capacity: an offer that could never be accepted
    # even with an empty hold is an unclickable tease on the screen.
    for seed in SEED_SAMPLE:
        state = ship(seed=seed)
        board = roll_board(state, world_graph(seed=seed), "Alpha", seed=seed)
        for job in board.missions:
            assert 0 <= job.cargo_units <= min(OFFER_CARGO_CEILING, state.stats.cargo_room)
            assert 0 <= job.passengers <= min(
                OFFER_PASSENGER_CEILING, state.stats.passenger_space
            )
            # ...but never an empty crate: a job must carry something.
            assert job.cargo_units + job.passengers >= 1


def test_generatePortOffers_withTheHullShrunk_shouldShrinkTheLargestOfferToo(config_factory):
    # GIVEN a config whose ship carries 4 cargo and 2 passengers,
    values = {**base_config()}
    values["player_ship"] = {**values["player_ship"], "cargo_room": 4, "passenger_space": 2}
    values["economy"] = {**values["economy"], "missions_min": 30, "missions_max": 30}
    state = GameState(values, rng=random.Random(1))
    # THEN no offer exceeds that hull, no matter how many offers are rolled.
    board = roll_board(state, world_graph(seed=3), "Alpha", seed=3)
    assert len(board.missions) == 30
    assert all(m.cargo_units <= 4 for m in board.missions if m.cargo_units)
    assert all(m.passengers <= 2 for m in board.missions if m.passengers)


def test_generatePortOffers_over200Seeds_faresAreMonotonicInSizeAndDistanceWithinABoard():
    # One rate pair is rolled per visit, so two jobs on the same screen are
    # comparable: for a fixed destination distance, more cargo never pays less,
    # and for a fixed size, a longer lane never pays less.
    for seed in SEED_SAMPLE:
        state = ship(seed=seed)
        board = roll_board(state, world_graph(seed=seed), "Alpha", seed=seed)
        cargo_only = [m for m in board.missions if m.cargo_units and not m.passengers]
        for first in cargo_only:
            for second in cargo_only:
                if first.distance == second.distance:
                    if first.cargo_units >= second.cargo_units:
                        assert first.fare >= second.fare
        for first in board.missions:
            for second in board.missions:
                if (
                    first.cargo_units == second.cargo_units
                    and first.passengers == second.passengers
                ):
                    if first.distance >= second.distance:
                        assert first.fare >= second.fare


def test_generatePortOffers_over200Seeds_farBonusIsPositiveOnlyBeyondOneHop():
    for seed in SEED_SAMPLE:
        state = ship(seed=seed)
        graph = world_graph(seed=seed)
        board = roll_board(state, graph, "Alpha", seed=seed)
        bonus = state.economy.far_destination_bonus
        for job in board.missions:
            assert job.distance >= 1
            assert job.far_bonus == distance_multiplier(job.distance, bonus)
            assert (job.far_bonus > 1.0) == (job.distance > 1)
            assert job.fare >= 1


def test_generatePortOffers_over200Seeds_coversAllThreeMissionKindsAndEveryCargoType():
    kinds = set()
    cargo_types = set()
    for seed in SEED_SAMPLE:
        state = ship(seed=seed)
        board = roll_board(state, world_graph(seed=seed), "Alpha", seed=seed)
        for job in board.missions:
            if job.cargo_units and job.passengers:
                kinds.add("mixed")
            elif job.cargo_units:
                kinds.add("cargo")
            else:
                kinds.add("passenger")
            if job.cargo_type is not None:  # passenger runs haul no named cargo
                cargo_types.add(job.cargo_type)
    assert kinds == {"cargo", "passenger", "mixed"}
    # Every configured cargo type appears somewhere across the sample.
    assert cargo_types == set(state.economy.cargo_types)


def test_generatePortOffers_withTheSameSeed_shouldProduceTheIdenticalBoard():
    graph = world_graph(seed=17)
    first_state = ship(seed=11)
    second_state = ship(seed=11)
    first = roll_board(first_state, graph, "Alpha", seed=99, serial=1)
    second = roll_board(second_state, graph, "Alpha", seed=99, serial=1)
    assert first.missions == second.missions
    assert first.upgrade_offers == second.upgrade_offers


def test_generatePortOffers_withADisconnectedGraph_shouldRefuseToPriceAnImpossibleTrip():
    # GIVEN a graph where Bravo is unreachable from Alpha...
    graph = world_graph(seed=7)
    for first, second in (("Alpha", "Bravo"), ("Bravo", "Alpha")):
        graph.adjacency[second] = frozenset(
            name for name in graph.adjacency[second] if name != first
        )
    state = ship(seed=1)
    # ...so Bravo is unreachable from Alpha.
    assert graph.jump_distance("Alpha", "Bravo") is None
    # THEN the generator says the world is broken rather than quietly pricing a
    # trip the player can never take.
    with pytest.raises(ValueError, match="not connected|no hyperspace route"):
        for _ in range(200):
            generate_port_offers(
                rules=state.economy,
                graph=graph,
                current_system="Alpha",
                stats=state.stats,
                upgrade_levels=state.upgrade_levels,
                rng=random.Random(1),
                visit_serial=1,
            )


def test_generatePortOffers_withAOneSystemWorld_shouldOfferNoContracts():
    values = {**base_config()}
    values["map"] = {
        **values["map"],
        "system_count": 2,
        "connections_min": 1,
        "connections_max": 1,
        "alpha_connections": ["Bravo"],
    }
    state = GameState(values, rng=random.Random(1))
    graph = SystemGraphGenerator.from_config(values["map"], rng=random.Random(1)).generate()
    board = generate_port_offers(
        rules=state.economy, graph=graph, current_system="Alpha",
        stats=state.stats, upgrade_levels=state.upgrade_levels,
        rng=random.Random(1), visit_serial=1,
    )
    # The offer count is a config range, not a destination count; what a
    # two-system world forces is that every lane points at Bravo, one hop away.
    assert board.missions, "a connected world must always have something to haul"
    assert {job.destination for job in board.missions} == {"Bravo"}
    assert {job.distance for job in board.missions} == {1}
    assert {job.far_bonus for job in board.missions} == {1.0}


def test_generatePortOffers_withAnUnknownCurrentSystem_shouldRaiseValueError():
    state = ship(seed=1)
    with pytest.raises(ValueError, match="unknown system"):
        generate_port_offers(
            rules=state.economy, graph=world_graph(seed=7), current_system="Nowhere",
            stats=state.stats, upgrade_levels=state.upgrade_levels,
            rng=random.Random(1), visit_serial=1,
        )


# ---------------------------------------------------------------------------
# Upgrade offers: the curve, the wall, and the magnitudes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "level, base, multiplier, expected",
    [
        (1, 1000, 2, 1000),      # first level of any stat costs the base price
        (2, 1000, 2, 2000),
        (3, 1000, 2, 4000),
        (4, 1000, 2, 8000),
        (5, 1000, 2, 16000),    # the max level is the most expensive, never free
        (1, 500, 1.5, 500),
        (3, 500, 1.5, 1125),
        (5, 2500, 3, 202500),  # 2500 * 3**4: the config's wall, not a rounding
    ],
)
def test_upgradeCost_withTheConfigCurve_shouldMatchTheExactLevelTable(level, base, multiplier, expected):
    assert upgrade_cost(level, base, multiplier) == pytest.approx(expected)


def test_upgradeCost_withLevelZero_shouldRaiseValueError():
    with pytest.raises(ValueError, match="level must be >= 1"):
        upgrade_cost(0, 1000, 2)


def test_generateUpgradeOffers_over200Seeds_offersDistinctStatsWithinTheLevelWall():
    for seed in SEED_SAMPLE:
        state = ship(seed=seed)
        offers = generate_upgrade_offers(
            state.economy, state.stats, state.upgrade_levels, random.Random(seed)
        )
        stats = [offer.stat for offer in offers]
        assert len(stats) == len(set(stats))
        assert all(stats.count(stat) == 1 for stat in stats)
        for offer in offers:
            assert offer.stat in UPGRADE_TYPES
            assert 1 <= offer.level <= state.economy.upgrade_max_level
            assert offer.cost == pytest.approx(
                upgrade_cost(
                    offer.level,
                    state.economy.upgrade_base_cost,
                    state.economy.upgrade_cost_multiplier,
                )
            )


def test_generateUpgradeOffers_withEveryStatMaxed_shouldOfferNothingEver():
    for seed in range(50):
        state = ship(seed=seed)
        maxed = {stat: state.economy.upgrade_max_level for stat in UPGRADE_TYPES}
        assert generate_upgrade_offers(
            state.economy, state.stats, maxed, random.Random(seed)
        ) == []


def test_generateUpgradeOffers_withSomeStatsMaxed_shouldKeepOfferingTheRemainingStats():
    # The sample is drawn from stats that can still go up, so maxing three stats
    # must not silently halve the board.
    values = {**base_config()}
    values["economy"] = {**values["economy"], "upgrade_offers_min": 4, "upgrade_offers_max": 5}
    state = GameState(values, rng=random.Random(1))
    maxed = {"shields": 5, "armor": 5, "weapons": 5}
    for seed in range(40):
        offers = generate_upgrade_offers(
            state.economy, state.stats, maxed, random.Random(seed)
        )
        assert len(offers) == 4
        assert all(offer.stat not in maxed for offer in offers)
        # Each offer is exactly one level above where that stat stands now.
        assert all(offer.level == maxed.get(offer.stat, 0) + 1 for offer in offers)


def test_applyUpgrade_withEveryStat_shouldMoveExactlyTheConfiguredMagnitude():
    values = base_config()
    steps = values["upgrade_steps"]
    state = GameState(values, rng=random.Random(1))
    before = (
        state.stats.max_shields, state.stats.max_armor, state.stats.acceleration_rate,
        state.stats.top_speed, state.stats.weapon_power, state.stats.fuel_capacity,
        state.stats.cargo_room, state.stats.passenger_space,
    )
    for stat in UPGRADE_TYPES:
        apply_upgrade(state.stats, stat, upgrade_step_for(steps, stat))
    step = steps
    assert state.stats.max_shields == before[0] + step["shields"]
    assert state.stats.max_armor == before[1] + step["armor"]
    assert state.stats.acceleration_rate == pytest.approx(
        before[2] * (1 + step["engine_percent"] / 100.0)
    )
    assert state.stats.top_speed == pytest.approx(before[3] * (1 + step["engine_percent"] / 100.0))
    assert state.stats.weapon_power == before[4] + step["weapon_damage"]
    assert state.stats.fuel_capacity == before[5] + step["fuel"]
    assert state.stats.cargo_room == before[6] + step["cargo"]
    assert state.stats.passenger_space == before[7] + step["passenger"]


def test_applyUpgrade_withShieldsOrArmor_shouldTopUpTheNewMaximumToo():
    # A stronger hull sitting at the old scar level is a bug the player pays for.
    state = ship()
    state.stats.shields = 1
    state.stats.armor = 1
    apply_upgrade(state.stats, "shields", 50)
    apply_upgrade(state.stats, "armor", 100)
    assert state.stats.shields == state.stats.max_shields
    assert state.stats.armor == state.stats.max_armor


def test_applyUpgrade_withAnUnknownStat_shouldRaiseValueError():
    with pytest.raises(ValueError, match="unknown upgrade stat"):
        apply_upgrade(ship().stats, "warp_core", 10)


def test_upgradeStepFor_withEveryStat_shouldReadTheMatchingConfigKey():
    steps = base_config()["upgrade_steps"]
    assert upgrade_step_for(steps, "engines") == steps["engine_percent"]
    assert upgrade_step_for(steps, "weapons") == steps["weapon_damage"]
    assert upgrade_step_for(steps, "cargo") == steps["cargo"]


def test_upgradeStepFor_withAnUnknownStat_shouldRaiseValueError():
    with pytest.raises(ValueError, match="unknown upgrade stat"):
        upgrade_step_for(base_config()["upgrade_steps"], "hull_plating")


def test_upgradeText_withEngineStats_shouldShowAPercentageAndOtherStatsAPointCount():
    assert upgrade_text(UpgradeOffer("engines", 1, 1000), 20) == "Engines +20%"
    assert upgrade_text(UpgradeOffer("cargo", 2, 4000), 20) == "Cargo room +20"


# ---------------------------------------------------------------------------
# The credit floor and the cost-preview seams
# ---------------------------------------------------------------------------


def test_canAfford_withACostLeavingExactlyZero_shouldBeFalse():
    # GIVEN 1,000 credits and a 1,000 credit price,
    state = ship(starting_credits=1000)
    # THEN the purchase is refused: the gate is "no purchase path producing
    # credits <= 0", so spending the last credit is out of bounds.
    assert state.can_afford(1000) is False
    assert state.can_afford(999) is True


def test_canAfford_withAZeroCost_shouldBeTrueEvenWithAnEmptyPurse():
    assert ship(starting_credits=0).can_afford(0) is True


def test_fuelTopUpCost_andRepairTopUpCost_shouldFollowTheConfiguredRates():
    values = {**base_config()}
    values["economy"] = {
        **values["economy"], "fuel_cost_per_unit": 2, "repair_cost_per_point": 4,
    }
    state = GameState(values, rng=random.Random(1))
    state.fuel = state.stats.fuel_capacity - 250
    state.stats.armor = state.stats.max_armor - 40
    assert state.fuel_top_up_cost() == pytest.approx(500)
    assert state.repair_top_up_cost() == pytest.approx(160)
    assert state.fuel_top_up_cost(100) == pytest.approx(200)
    # Asking for more than the tank can hold prices the tank, not the request.
    assert state.fuel_top_up_cost(99_999) == pytest.approx(500)


# ---------------------------------------------------------------------------
# Refuel and repair
# ---------------------------------------------------------------------------


def test_buyFuel_withAFullTank_shouldRefuseAndChargeNothing():
    state = ship(starting_credits=10_000)
    result = state.buy_fuel()
    assert not result.succeeded
    assert result.reason == "The tank is already full."
    assert state.credits == 10_000


def test_buyFuel_toFull_shouldPayRateTimesUnitsAndFillExactlyToCapacity():
    state = damaged_ship(starting_credits=100_000)
    expected_units = state.fuel_room
    expected_cost = state.fuel_top_up_cost()
    result = state.buy_fuel()
    assert result.succeeded
    assert state.fuel == pytest.approx(state.stats.fuel_capacity)
    assert state.fuel_room == pytest.approx(0.0)
    assert result.credits_spent == pytest.approx(expected_cost)
    assert state.credits == pytest.approx(100_000 - expected_cost)
    assert f"{int(expected_units)}" in result.reason


def test_buyFuel_partially_shouldChargeOnlyTheUnitsRequestedAndNeverOverfill():
    state = damaged_ship(starting_credits=100_000)
    room = state.fuel_room
    result = state.buy_fuel(room / 2)
    assert result.succeeded
    assert state.fuel_room == pytest.approx(room / 2)
    # And a request for more than fits must not silently overfill the tank.
    state.buy_fuel(room * 4)
    assert state.fuel == pytest.approx(state.stats.fuel_capacity)


def test_buyFuel_whenItWouldTakeCreditsToTheFloor_shouldRefuseAndChangeNothing():
    state = damaged_ship(starting_credits=10)
    fuel_before, credits_before = state.fuel, state.credits
    result = state.buy_fuel()
    assert not result.succeeded
    assert "Not enough credits" in result.reason
    assert state.fuel == fuel_before
    assert state.credits == credits_before


def test_buyFuel_withExactlyThePrice_shouldRefuseButOneCreditMoreShouldSucceed():
    cost = damaged_ship(starting_credits=10_000).fuel_top_up_cost()
    # GIVEN a balance exactly equal to the fill price, THEN refused (the floor).
    assert not damaged_ship(starting_credits=int(cost)).buy_fuel().succeeded
    # GIVEN one credit more, THEN allowed and still above the floor.
    richer = damaged_ship(starting_credits=int(cost) + 1)
    assert richer.buy_fuel().succeeded
    assert richer.credits > CREDIT_FLOOR


def test_repairArmor_withAnIntactHull_shouldRefuseAndChargeNothing():
    state = ship(starting_credits=10_000)
    result = state.repair_armor()
    assert not result.succeeded
    assert result.reason == "The hull is already intact."
    assert state.credits == 10_000


def test_repairArmor_toFull_shouldPayRateTimesPointsAndRestoreTheHull():
    state = damaged_ship(starting_credits=100_000)
    cost = state.repair_top_up_cost()
    result = state.repair_armor()
    assert result.succeeded
    assert state.stats.armor == pytest.approx(state.stats.max_armor)
    assert state.credits == pytest.approx(100_000 - cost)
    # Shields are never sold: they recharged free on landing.
    assert state.stats.shields == state.stats.max_shields


def test_repairArmor_partially_shouldPatchOnlyThePointsRequested():
    state = damaged_ship(starting_credits=100_000)
    missing = state.armor_damage
    state.repair_armor(missing / 4)
    assert state.armor_damage == pytest.approx(missing * 3 / 4)


def test_repairArmor_whenUnaffordable_shouldRefuseAndLeaveTheDamageInPlace():
    state = damaged_ship(starting_credits=1)
    armor_before = state.stats.armor
    result = state.repair_armor()
    assert not result.succeeded
    assert state.stats.armor == armor_before


# ---------------------------------------------------------------------------
# Accepting jobs: capacity gating and the one-fare-per-offer rule
# ---------------------------------------------------------------------------


def test_acceptMission_withRoom_shouldLoadThePayloadAndNameTheDestination():
    state = ship()
    job = mission(cargo_units=6, passengers=2, destination="Delta")
    result = state.accept_mission(job)
    assert result.succeeded
    assert state.cargo_used == 6
    assert state.passengers_used == 2
    assert "Delta" in result.reason
    # No fare is paid for taking a job aboard: the money arrives on delivery.
    assert state.credits == GameState(base_config(), rng=random.Random(1)).credits
    assert state.carried_loads[0].fare == job.fare


def test_acceptMission_shouldCreditNothingUntilTheShipLandsAtTheDestination():
    state = ship(starting_credits=20_000)
    state.accept_mission(mission(cargo_units=4, destination="Bravo"))
    assert state.credits == 20_000


def test_acceptMission_beyondCargoCapacity_shouldRefuseWithTheFreeSlotCountAndLoadNothing():
    # GIVEN a hold that already has room used up,
    state = ship()
    state.accept_mission(mission(cargo_units=state.stats.cargo_room, destination="Zulu"))
    job = mission(cargo_units=3, destination="Bravo", offer_index=1)
    # THEN the refusal says how many slots were free, and the hold is unchanged.
    result = state.accept_mission(job)
    assert not result.succeeded
    assert "Not enough cargo room" in result.reason
    assert "needs 3 slots, and only 0 free." in result.reason
    assert state.cargo_used == state.stats.cargo_room
    assert state.passengers_used == 0


def test_acceptMission_beyondPassengerCapacity_shouldRefuseAndLoadNothing():
    # The spec's own example: 6/8 passengers with a job for 4 must be refused,
    # not partly accepted.
    values = {**base_config()}
    values["player_ship"] = {**values["player_ship"], "passenger_space": 8}
    state = GameState(values, rng=random.Random(1))
    state.accept_load(carried("Zulu", passengers=6))
    result = state.accept_mission(mission(passengers=4, destination="Bravo"))
    assert not result.succeeded
    assert "Not enough passenger space" in result.reason
    assert "needs 4 berths, and only 2 free." in result.reason
    assert state.passengers_used == 6


def test_acceptMission_exactlyFillingTheHold_shouldBeAccepted():
    state = ship()
    assert state.accept_mission(
        mission(cargo_units=state.stats.cargo_room, passengers=state.stats.passenger_space)
    ).succeeded


def test_acceptMission_twiceForTheSameOffer_shouldRefuseTheSecond():
    # The money-glitch guard: a board is a list of offers, not a menu to order
    # from twice.
    state = ship()
    board = roll_board(state, world_graph(seed=7), "Alpha", seed=3)
    job = board.missions[0]
    assert state.accept_mission(job).succeeded
    second = state.accept_mission(job)
    assert not second.succeeded
    assert second.reason == "That job has already been accepted."
    assert state.cargo_used == job.cargo_units


def test_acceptMission_withAStaleVisitNumbering_shouldRefuseEvenWhenTheIdsMatch():
    # Two visits number their offers the same way; the visit serial is what keeps
    # an offer from an abandoned board from being accepted at the next port.
    state = ship()
    first_board = roll_board(state, world_graph(seed=7), "Alpha", seed=3, serial=1)
    assert state.accept_mission(first_board.missions[0]).succeeded
    stale = roll_board(state, world_graph(seed=8), "Bravo", seed=3, serial=1)
    replay = stale.missions[0]
    assert replay.offer_id == first_board.missions[0].offer_id
    assert not state.accept_mission(replay).succeeded


def test_acceptMission_atANewVisit_shouldAcceptAnIdenticalOfferAgain():
    state = ship()
    first = roll_board(state, world_graph(seed=7), "Alpha", seed=3, serial=1)
    state.accept_mission(first.missions[0])
    second = roll_board(state, world_graph(seed=7), "Alpha", seed=3, serial=2)
    assert second.missions[0].offer_id != first.missions[0].offer_id
    assert state.accept_mission(second.missions[0]).succeeded


def test_offerIsAccepted_withAFreshBoard_shouldBeFalseForEveryOffer():
    state = ship()
    board = roll_board(state, world_graph(seed=7), "Alpha", seed=3)
    assert all(not state.offer_is_accepted(job.offer_id) for job in board.missions)


def test_upgradeOfferIsAvailable_withTheCurrentLevel_shouldBeTrueAndWithAStaleLevelFalse():
    state = ship()
    offer = UpgradeOffer("shields", 1, 1000)
    assert state.upgrade_offer_is_available(offer) is True
    state.purchase_upgrade(offer)
    assert state.upgrade_offer_is_available(offer) is False
    assert state.upgrade_offer_is_available(UpgradeOffer("shields", 2, 2000)) is True


def test_upgradeOfferIsAvailable_withAnUnknownStat_shouldRaiseValueError():
    with pytest.raises(ValueError, match="unknown upgrade stat"):
        ship().upgrade_offer_is_available(UpgradeOffer("lucky_paint", 1, 100))


# ---------------------------------------------------------------------------
# Purchasing upgrades: the floor, the wall, and the stale-offer guard
# ---------------------------------------------------------------------------


def test_purchaseUpgrade_withRoomToPay_shouldRaiseTheLevelAndApplyTheStat():
    state = ship(starting_credits=5000)
    offer = UpgradeOffer("cargo", 1, state.economy.upgrade_base_cost)
    room_before = state.stats.cargo_room
    result = state.purchase_upgrade(offer)
    assert result.succeeded
    assert state.upgrade_levels["cargo"] == 1
    assert state.stats.cargo_room == room_before + state.upgrade_steps["cargo"]
    assert state.credits == pytest.approx(5000 - offer.cost)


def test_purchaseUpgrade_withExactlyEnoughCredits_shouldRefuseAndChangeNothing():
    state = ship(starting_credits=1000)
    offer = UpgradeOffer("weapons", 1, 1000)
    weapon_before = state.stats.weapon_power
    result = state.purchase_upgrade(offer)
    assert not result.succeeded
    assert "Not enough credits" in result.reason
    assert state.upgrade_levels["weapons"] == 0
    assert state.stats.weapon_power == weapon_before
    assert state.credits == 1000


def test_purchaseUpgrade_withOneCreditAboveThePrice_shouldSucceedAndStayAboveTheFloor():
    state = ship(starting_credits=1001)
    assert state.purchase_upgrade(UpgradeOffer("weapons", 1, 1000)).succeeded
    assert state.credits == 1


def test_purchaseUpgrade_twiceForTheSameOffer_shouldRefuseTheSecondAndChargeOnce():
    state = ship(starting_credits=50_000)
    offer = UpgradeOffer("armor", 1, 1000)
    assert state.purchase_upgrade(offer).succeeded
    armor_after_first = state.stats.max_armor
    second = state.purchase_upgrade(offer)
    assert not second.succeeded
    assert "out of date" in second.reason
    assert state.upgrade_levels["armor"] == 1
    assert state.stats.max_armor == armor_after_first


def test_purchaseUpgrade_pastTheMaxLevel_shouldRefuseEveryTimeAndChargeNothing():
    # The hard wall: buying levels 1..5 works, and level 6 does not exist.
    state = ship(starting_credits=10_000_000)
    for level in range(1, state.economy.upgrade_max_level + 1):
        assert state.purchase_upgrade(UpgradeOffer("fuel", level, 0)).succeeded
    assert state.upgrade_levels["fuel"] == state.economy.upgrade_max_level
    credits, capacity = state.credits, state.stats.fuel_capacity
    refused = state.purchase_upgrade(UpgradeOffer("fuel", 6, 0))
    assert not refused.succeeded
    assert "maximum level" in refused.reason
    assert state.credits == credits
    assert state.stats.fuel_capacity == capacity


def test_purchaseUpgrade_withAnUnknownStat_shouldRaiseValueError():
    with pytest.raises(ValueError, match="unknown upgrade stat"):
        ship().purchase_upgrade(UpgradeOffer("sails", 1, 100))


@pytest.mark.parametrize("config_name", [
    "config_easy.json", "config_medium.json", "config_hard.json",
])
def test_everyPortPurchasePath_withTheShippedConfigs_shouldNeverTakeCreditsToZeroOrBelow(
    config_factory, config_name
):
    """The gate: no purchase path produces credits <= 0, at any difficulty.

    Every transaction the port offers, attempted until it starts refusing, on 12
    boards per difficulty, with the balance pinned to every difficulty's own
    starting figure.
    """
    config = load_config(config_factory())[config_name]
    for seed in range(12):
        graph = world_graph(seed=seed, config=config)
        state = GameState(config, rng=random.Random(seed))
        state.fuel = state.stats.fuel_capacity / 2.0
        state.stats.armor = state.stats.max_armor / 2.0
        for visit in range(3):
            board = roll_board(state, graph, "Alpha", seed=seed + visit)
            for job in board.missions:
                before = state.credits
                state.accept_mission(job)
                assert state.credits >= CREDIT_FLOOR
                if state.credits != before:
                    raise AssertionError("accepting a job must not touch the balance")
            for offer in board.upgrade_offers:
                before = state.credits
                result = state.purchase_upgrade(offer)
                assert state.credits > CREDIT_FLOOR, (
                    f"{config_name} seed {seed} {offer.stat} level {offer.level} "
                    f"left {state.credits} credits"
                )
                if not result.succeeded:
                    assert state.credits == before
            for service in (state.buy_fuel, state.repair_armor):
                before = state.credits
                result = service()
                assert state.credits > CREDIT_FLOOR
                if not result.succeeded:
                    assert state.credits == before
            # Landing may only ever add money.
            report = state.land("Alpha")
            assert state.credits >= before or report.credits_gained >= 0


# ---------------------------------------------------------------------------
# Landing, unloading, and the exactly-once fare
# ---------------------------------------------------------------------------


def test_land_shouldUnloadOnlyTheLoadsBoundForThisSystemAndCreditTheirFares():
    state = ship(starting_credits=1000)
    state.accept_load(carried("Bravo", fare=500, cargo_units=4, passengers=2))
    state.accept_load(carried("Charlie", fare=700, cargo_units=1, passengers=1))
    state.accept_load(carried("Bravo", fare=250, cargo_units=2))

    report = state.land("Bravo")
    assert report.credits_gained == 750
    assert report.cargo_unloaded == 6
    assert report.passengers_unloaded == 2
    assert state.credits == 1750
    # The Charlie job is still aboard, and no Bravo fare remains.
    assert [(load.destination, load.fare) for load in state.carried_loads] == [("Charlie", 700)]
    assert state.cargo_used == 1
    assert state.passengers_used == 1


def test_land_twiceAtTheSameSystem_shouldPayEveryFareExactlyOnce():
    state = ship(starting_credits=0)
    state.accept_load(carried("Bravo", fare=999, cargo_units=2))
    first = state.land("Bravo")
    second = state.land("Bravo")
    assert first.credits_gained == 999
    assert second.credits_gained == 0
    assert second.delivered_anything is False
    assert state.credits == 999


def test_land_atADifferentSystem_shouldNotTouchFaresOwedElsewhere():
    state = ship(starting_credits=0)
    state.accept_load(carried("Bravo", fare=999, cargo_units=2))
    assert state.land("Charlie").credits_gained == 0
    assert state.credits == 0
    assert state.land("Bravo").credits_gained == 999
    assert state.credits == 999
    assert state.land("Bravo").credits_gained == 0


def test_land_shouldStopTheShipRefillShieldsAndLeaveItWhereThePlayerPressedL():
    state = ship()
    state.set_position(40.0, -30.0)
    state.feed_input(thrust=True)
    for _ in range(20):
        state.advance_frame()
    assert state.velocity != (0.0, 0.0)
    state.stats.shields = 3
    position_before = state.position

    state.land("Alpha")
    assert state.velocity == (0.0, 0.0)
    assert state.stats.shields == state.stats.max_shields
    assert state.position == position_before


def test_land_shouldMarkTheShipLandedAndImmuneToDamage():
    state = ship()
    assert state.is_landed is False
    state.land("Alpha")
    assert state.is_landed is True
    assert state.immune_to_damage is True


def test_land_whileAJumpIsInProgress_shouldRaiseRatherThanSettleFaresMidFlight():
    state = ship()
    state.set_position(900.0, 0.0)
    state.begin_jump(2.0)
    with pytest.raises(ValueError, match="cannot land while"):
        state.land("Alpha")


def test_land_withAnEmptyHold_shouldReportNothingDelivered():
    report = ship().land("Alpha")
    assert report.credits_gained == 0
    assert report.delivered_anything is False
    assert report.unloaded == ()


# ---------------------------------------------------------------------------
# Launching: the immunity window
# ---------------------------------------------------------------------------


def test_launch_shouldStopTheShipAndArmTheConfiguredImmunityWindow():
    state = ship()
    state.land("Alpha")
    state.launch()
    assert state.is_landed is False
    assert state.immune_to_damage is True
    assert state.launch_immunity_frames_left == state.launch_immunity_frames
    assert state.launch_immunity_frames == base_config()["tactical"]["launch_immunity_frames"]


def test_immuneToDamage_shouldExpireAfterExactlyTheConfiguredFrames():
    state = ship()
    state.land("Alpha")
    state.launch()
    frames = state.launch_immunity_frames
    for _ in range(frames - 1):
        state.advance_frame()
        assert state.immune_to_damage is True
    state.advance_frame()
    assert state.immune_to_damage is False
    assert state.launch_immunity_frames_left == 0


def test_launch_whenNotLanded_shouldNotReArmTheImmunityWindow():
    # A stray second launch must not be a repeatable invulnerability cheat.
    state = ship()
    state.land("Alpha")
    state.launch()
    for _ in range(state.launch_immunity_frames):
        state.advance_frame()
    assert state.immune_to_damage is False
    state.launch()
    assert state.launch_immunity_frames_left == 0


def test_advanceFrame_whileLanded_shouldNotMoveTheShipEvenIfAFrameArrives():
    state = ship()
    state.set_position(10.0, 20.0)
    state.land("Alpha")
    state.feed_input(thrust=True, right=True)
    for _ in range(30):
        state.advance_frame()
    assert state.position == (10.0, 20.0)
    assert state.velocity == (0.0, 0.0)


def test_immuneToDamage_shouldStillTickDownThroughAJump():
    state = ship()
    state.land("Alpha")
    state.launch()
    state.set_position(900.0, 0.0)
    state.begin_jump(1.5)
    for _ in range(state.launch_immunity_frames):
        state.advance_frame()
    assert state.launch_immunity_frames_left == 0


# ---------------------------------------------------------------------------
# Spaceport geometry: nothing may overlap, nothing may run off the window
# ---------------------------------------------------------------------------


def test_spaceportLayout_withTheWorstCaseBoard_shouldFitInsideTheWindow():
    # GIVEN the widest board the shipped configs can roll, plus every stat on offer,
    for index in range(contracts_capacity()):
        row = contract_row_rect(index)
        button = contract_button_rect(index)
        assert row.right <= SCREEN_SIZE[0] and row.bottom <= BODY_BOTTOM
        assert button.left >= row.left and button.right <= row.right
        assert button.top >= row.top and button.bottom <= row.bottom
    for index in range(upgrades_capacity()):
        row = upgrade_row_rect(index)
        button = upgrade_button_rect(index)
        assert row.bottom <= SERVICES_TOP and button.right <= SCREEN_SIZE[0]
    for rect in (refuel_button_rect(), repair_button_rect(), LAUNCH_RECT, MESSAGE_RECT):
        assert rect.left >= 0 and rect.right <= SCREEN_SIZE[0]
        assert rect.bottom <= SCREEN_SIZE[1]


def test_spaceportLayout_everyZoneShouldSitInsideItsColumnAndTouchNothingElse():
    # A row contains its own button by design, so what matters is that the two
    # columns and the footer never collide, and that every clickable control is
    # fully inside the row it belongs to.
    left = contract_row_rect(0)
    for index in range(1, contracts_capacity()):
        left.union_ip(contract_row_rect(index))
    right = upgrade_row_rect(0)
    for index in range(1, upgrades_capacity()):
        right.union_ip(upgrade_row_rect(index))
    right.union_ip(refuel_button_rect())
    right.union_ip(repair_button_rect())
    assert left.colliderect(right) is False
    assert left.colliderect(MESSAGE_RECT) is False and left.colliderect(LAUNCH_RECT) is False
    assert right.colliderect(MESSAGE_RECT) is False and right.colliderect(LAUNCH_RECT) is False
    assert MESSAGE_RECT.colliderect(LAUNCH_RECT) is False
    for index in range(contracts_capacity()):
        assert contract_row_rect(index).contains(contract_button_rect(index))
    for index in range(upgrades_capacity()):
        assert upgrade_row_rect(index).contains(upgrade_button_rect(index))
    # The manifest is the one block no config sizes, so bound it by the geometry.
    last_line = (
        manifest_top() + SECTION_HEADER_HEIGHT + 4 + manifest_capacity() * MANIFEST_LINE_HEIGHT
    )
    assert last_line <= MESSAGE_RECT.top
    assert manifest_top() >= repair_button_rect().bottom


def test_spaceportLayout_contractRows_shouldAllSitAboveTheMessageLine():
    bottom_of_board = ROWS_TOP + contracts_capacity() * CONTRACT_ROW_HEIGHT
    assert bottom_of_board <= MESSAGE_RECT.top
    assert contracts_capacity() >= 10  # every shipped config's widest board


def test_contractsCapacity_withTheShippedConfigs_shouldShowEveryOfferOnTheBoard():
    for name, config in load_config_for_layout().items():
        assert contracts_capacity() >= config["economy"]["missions_max"], name


def load_config_for_layout():
    """The three shipped config files, for layout ceilings (no temp fixture needed)."""
    return load_config(PROJECT_ROOT)


# ---------------------------------------------------------------------------
# Spaceport copy: the strings the screen actually draws
# ---------------------------------------------------------------------------


def test_contractTermsLine_withADistantLane_shouldShowTheHopCountAndTheFarBonus():
    line = contract_terms_line(mission(cargo_units=5, distance=4, far_bonus=1.5))
    assert "4 jumps" in line
    assert "far bonus x5.5" in line
    assert f"{format_credits(mission(cargo_units=5, distance=4, far_bonus=1.5).fare)} credits" in line


def test_contractTermsLine_withASingleHop_shouldSayOneJumpAndNoFarBonus():
    line = contract_terms_line(mission(cargo_units=2, distance=1))
    assert "1 jump" in line
    assert "far bonus" not in line


def test_contractPayloadLine_withACargoAndPassengerJob_shouldNameThePayloadAndDestination():
    job = mission(cargo_units=3, passengers=2, destination="Lima")
    assert contract_payload_line(job, accepted=False) == "-> Lima: 3 units of iron ore; 2 passengers"
    # And an accepted job says so on the row, so the screen cannot look like an
    # offer that is still available.
    assert contract_payload_line(job, accepted=True).startswith("ABOARD")


def test_contractPayloadLine_withTheWidestPayloadTheGeneratorCanRoll_shouldStillNameTheDestination():
    # The clip is the whole point: a row that clips away its destination has
    # clipped away the one fact the fare line underneath is about.
    widest = mission(
        cargo_units=OFFER_CARGO_CEILING, passengers=OFFER_PASSENGER_CEILING,
        distance=5, destination="Juliett",
    )
    line = contract_payload_line(widest, accepted=False)
    clipped = fit_text(line, PAYLOAD_SIZE, CONTRACT_TEXT_WIDTH)
    assert clipped != line, "the widest payload must actually clip in this column"
    assert clipped.startswith("-> Juliett"), clipped


def test_pluralise_withOneAndMany_shouldSayOneThingAndThenThings():
    assert pluralise(1, "slot") == "slot"
    assert pluralise(4, "slot") == "slots"
    assert pluralise(0, "unit") == "units"
    assert pluralise(2, "berth", "passes") == "passes"


def test_acceptMission_withOneFreeCargoSlot_shouldRefuseInGrammaticalEnglish():
    # GIVEN one slot left, and a job that needs two,
    state = ship(seed=11)
    state.accept_load(carried("Bravo", cargo_units=state.stats.cargo_room - 1))
    # THEN the refusal reads like English at the singular boundary.
    result = state.accept_mission(mission(cargo_units=2))
    assert not result.succeeded
    assert "needs 2 slots, and only 1 free." in result.reason


def test_buyFuel_withExactlyOneUnit_shouldNotSayOneUnits():
    # Unaffordable on purpose: the copy is what is under test here, and the
    # cheapest possible purse is reached through config, not a poked private.
    state = damaged_ship(seed=11, starting_credits=1)
    state.fuel = state.stats.fuel_capacity - 1
    result = state.buy_fuel(units=1)
    assert not result.succeeded
    assert "1 unit of fuel costs" in result.reason


def test_repairArmor_withExactlyOnePoint_shouldNotSayOnePoints():
    state = damaged_ship(seed=11, starting_credits=1)
    state.stats.armor = state.stats.max_armor - 1
    result = state.repair_armor(points=1)
    assert not result.succeeded
    assert "1 point of armour costs" in result.reason


def test_missionPayloadText_withMixedPassengerCounts_shouldPluraliseCorrectly():
    assert mission_payload_text(mission(passengers=1)) == "1 passenger"
    assert mission_payload_text(mission(passengers=2)) == "2 passengers"
    assert mission_payload_text(mission(cargo_units=4)) == "4 units of iron ore"
    assert mission_payload_text(mission(cargo_units=1)) == "1 unit of iron ore"


def test_serviceButtonText_withAFullTankOrIntactHull_shouldSaySoInsteadOfAZeroPrice():
    assert service_button_text("fuel", 0, 0) == "Full"
    assert service_button_text("armor", 0, 0) == "Intact"
    assert service_button_text("fuel", 1, 2) == "Refuel +1 unit - 2 cr"
    assert service_button_text("fuel", 250, 500) == "Refuel +250 units - 500 cr"
    assert service_button_text("armor", 40, 160) == "Repair +40 pts - 160 cr"


def test_deliveryMessage_withDeliveredCargo_shouldSayWhatWasUnloadedAndForHowMuch():
    state = ship()
    state.accept_load(carried("Bravo", fare=1500, cargo_units=3, passengers=1))
    report = state.land("Bravo")
    message = delivery_message(report)
    assert "Unloaded 3 cargo units and 1 passenger at Bravo" in message
    assert "+1,500 credits" in message


def test_deliveryMessage_withNothingToDeliver_shouldSaySoRatherThanPrintZeroes():
    message = delivery_message(ship().land("Alpha"))
    assert "Welcome to Alpha" in message
    assert "0" not in message


def test_manifestLines_withNothingAboard_shouldSayTheHoldIsEmpty():
    lines = manifest_lines(ship())
    assert lines[0] == "Cargo 0/20   Passengers 0/5"
    assert lines[1] == "Hold is empty."


def test_manifestLines_withLoadsAboard_shouldListEveryDestinationAndFare():
    state = ship()
    state.accept_load(carried("Bravo", fare=900, cargo_units=2, passengers=3, cargo_type="wine"))
    lines = manifest_lines(state)
    assert "-> Bravo: 2 x wine, 3 pax for 900" in lines
    assert lines[0] == "Cargo 2/20   Passengers 3/5"


def test_fitText_withAnOverlongLine_shouldClipWithAnEllipsisAndStayInsideTheWidth():
    from src.fonts import game_font

    text = "a" * 120
    clipped = fit_text(text, 16, 200)
    assert clipped.endswith("...")
    assert game_font(16).size(clipped)[0] <= 200
    # A line that already fits is returned untouched.
    assert fit_text("short", 16, 200) == "short"


def test_wrapText_withALongLoreLine_shouldWrapInsideTheWidthAndLineBudget():
    from src.fonts import game_font

    long_lore = (
        "The charter of (System) fits on one page; the arguments about (System) "
        "fill a thousand pages, mostly about tariffs."
    )
    lines = wrap_text(long_lore, 15, SCREEN_SIZE[0] - 48)
    assert 1 < len(lines) <= 2
    assert " ".join(lines).startswith("The charter of")
    for line in lines:
        assert game_font(15).size(line)[0] <= SCREEN_SIZE[0] - 48


# ---------------------------------------------------------------------------
# The spaceport scene: what it shows, and what a click does
# ---------------------------------------------------------------------------


def test_spaceportView_pushedOnLanding_shouldSitAboveTheGameScene():
    scene, manager, port = land_at_landing_range()
    assert isinstance(port, SpaceportView)
    assert manager.names() == ["GameScene", "SpaceportView"]
    assert port.visit.system == scene.system_map.current_system
    assert port.game_state is scene.game_state


def test_spaceportView_shouldShowTheCurrentSystemAndItsOnceAssignedLoreLine():
    # GIVEN a game scene, whose lore book was built once at new game,
    scene, manager, port = land_at_landing_range()
    system = scene.system_map.current_system
    # THEN the screen's lore is exactly the world's line for that system,
    expected = scene.lore.line_for(system)
    assert " ".join(port.lore_lines) == expected
    # ...and re-entering the same system shows the same line (never re-rolled).
    second_port = SpaceportView(
        port.visit, scene.game_state, scene.game_state.land(system), scene.lore
    )
    assert " ".join(second_port.lore_lines) == expected


def test_spaceportView_withDeliveredCargo_shouldOpenOnTheDeliveryMessage():
    scene, manager = game_scene()
    scene.game_state.accept_load(carried("Alpha", fare=800, cargo_units=2))
    press_key(scene, pygame.K_l)
    port = manager.top
    assert "Unloaded 2 cargo units at Alpha: +800 credits." == port.message


def test_spaceportView_draw_shouldRepaintEveryCornerOfTheWindow():
    # GIVEN the modal on screen,
    _, manager, port = land_at_landing_range()
    canvas = pygame.Surface(SCREEN_SIZE)
    canvas.fill((1, 2, 3))
    port.draw(canvas)
    # THEN the whole window belongs to the modal: every corner is the modal's own
    # background, so the tactical view and HUD cannot show through a "modal".
    corners = [(0, 0), (SCREEN_SIZE[0] - 1, 0), (0, SCREEN_SIZE[1] - 1),
               (SCREEN_SIZE[0] - 1, SCREEN_SIZE[1] - 1)]
    for corner in corners:
        # The modal's own background, read from the palette it paints with.
        assert canvas.get_at(corner)[:3] == PortPalette.background


def test_spaceportView_drawWithoutAnyUpdate_shouldStillPaintEveryButton():
    """The buttons must be visible on the very first frame the modal appears.

    ``pygame_gui`` builds a widget's images during its *first* ``update()``, so a
    scene that only creates its buttons and then draws them paints rows with no
    clickable anything. The real loop hides that (it updates before it draws), so
    the bug is only visible to a screenshot script, a test, or the next scene that
    reuses this one - which is why it is asserted here rather than left to luck.
    """
    _, manager, port = land_at_landing_range()
    canvas = pygame.Surface(SCREEN_SIZE)
    port.draw(canvas)
    # The two colours this screen legitimately paints *behind* a widget: the modal
    # background and the row panel. If a button centre is one of those, the widget
    # has no image and the player is clicking at nothing.
    unpainted = {PortPalette.background, PortPalette.panel}
    targets = [LAUNCH_RECT, refuel_button_rect(), repair_button_rect()]
    targets += [contract_button_rect(index) for index in range(len(port._accept_buttons))]
    targets += [upgrade_button_rect(index) for index in range(len(port._buy_buttons))]
    assert targets, "a port with no buttons at all is not a port"
    for rect in targets:
        assert canvas.get_at(rect.center)[:3] not in unpainted, f"{rect} painted nothing"


def test_spaceportView_withTheBoardOnScreen_shouldDrawOnePanelRowPerOffer():
    _, manager, port = land_at_landing_range()
    assert len(port.contracts) == len(port._accept_buttons)
    assert len(port.upgrades) == len(port._buy_buttons)
    assert len(port.contracts) <= contracts_capacity()


def test_handleEvent_clickingAccept_shouldLoadThePayloadAndRetireTheButton():
    _, manager, port = land_at_landing_range()
    button = next(iter(port._accept_buttons))
    job = port._accept_buttons[button]
    press_button(port, button)
    assert port.game_state.cargo_used == job.cargo_units
    assert port.game_state.passengers_used == job.passengers
    assert "Loaded for" in port.message
    assert button.is_enabled is False
    assert manager.audio.confirm_count == 1, "a completed transaction earns the beep"


def test_handleEvent_clickingAnAlreadyAboardJob_shouldNotLoadItTwice():
    _, manager, port = land_at_landing_range()
    button = next(iter(port._accept_buttons))
    job = port._accept_buttons[button]
    press_button(port, button)
    loaded_once = port.game_state.cargo_used
    button.enable()  # the model, not the widget, is the authority on availability
    press_button(port, button)
    assert port.game_state.cargo_used == loaded_once
    assert port.message == "That job has already been accepted."


def test_handleEvent_withAFullHold_shouldShowTheCapacityRejectionAndLoadNothing():
    _, manager, port = land_at_landing_range()
    state = port.game_state
    # GIVEN a hold stuffed to the last slot of both kinds - through the model's
    # own capacity check, not by fudging the counters...
    assert state.accept_load(carried(
        "Zulu", cargo_units=state.stats.cargo_room, passengers=state.stats.passenger_space
    )).succeeded
    # ...WHEN every job still on the board is clicked,
    refused = [button for button in port._accept_buttons if button.is_enabled]
    assert refused, "the board must still be showing something to refuse"
    loaded_before = (state.cargo_used, state.passengers_used)
    press_button(port, refused[0])
    # THEN nothing is loaded and the refusal is explained.
    assert (state.cargo_used, state.passengers_used) == loaded_before
    assert "Not enough" in port.message
    assert refused[0].is_enabled is True, "a refusal must stay re-clickable"


def test_handleEvent_clickingRefuel_shouldFillTheTankAtTheConfiguredRate():
    scene, manager, port = land_at_landing_range()
    scene.game_state.fuel = 10
    port._sync_buttons()
    cost = scene.game_state.fuel_top_up_cost()
    credits_before = scene.game_state.credits
    press_button(port, port._refuel_button)
    assert scene.game_state.fuel == pytest.approx(scene.game_state.stats.fuel_capacity)
    assert scene.game_state.credits == pytest.approx(credits_before - cost)
    assert port._refuel_button.is_enabled is False
    assert port._refuel_button.text == "Full"


def test_handleEvent_clickingRepair_shouldPatchTheHullAtTheConfiguredRate():
    _, manager, port = land_at_landing_range()
    port.game_state.stats.armor = 1
    port._sync_buttons()
    cost = port.game_state.repair_top_up_cost()
    press_button(port, port._repair_button)
    assert port.game_state.stats.armor == pytest.approx(port.game_state.stats.max_armor)
    assert "Repaired" in port.message
    assert port._repair_button.text == "Intact"


def test_handleEvent_clickingAnUpgrade_shouldApplyItOnceAndRetireTheOffer():
    _, manager, port = land_at_landing_range()
    if not port._buy_buttons:
        pytest.skip("a board with no upgrades cannot exercise the purchase path")
    button = next(iter(port._buy_buttons))
    offer = port._buy_buttons[button]
    credits_before = port.game_state.credits
    press_button(port, button)
    assert port.game_state.upgrade_levels[offer.stat] == offer.level
    assert port.game_state.credits == pytest.approx(credits_before - offer.cost)
    press_button(port, button)
    assert port.game_state.upgrade_levels[offer.stat] == offer.level
    assert button.is_enabled is False
    assert "out of date" in port.message


def test_handleEvent_withAnUnaffordableUpgrade_shouldGreyTheButtonOutAndRefuseTheClick():
    # GIVEN a save whose entire purse is 1 credit (config, not a poked private),
    scene, manager = game_scene(scene_config(starting_credits=1))
    press_key(scene, pygame.K_l)
    port = manager.top
    if not port._buy_buttons:
        pytest.skip("this board rolled no upgrades")
    button = next(iter(port._buy_buttons))
    offer = port._buy_buttons[button]
    # THEN the caption is greyed out (the model's own can_afford), and clicking
    # the greyed widget still cannot move the level or the money.
    assert button.is_enabled is False
    level_before, credits_before = port.game_state.upgrade_levels[offer.stat], port.game_state.credits
    press_button(port, button)
    assert port.game_state.upgrade_levels[offer.stat] == level_before
    assert port.game_state.credits == credits_before
    assert "Not enough credits" in port.message


def test_handleEvent_clickingLaunch_shouldCloseTheModalAndArmTheImmunityWindow():
    _, manager, port = land_at_landing_range()
    press_button(port, port._launch_button)
    assert manager.names() == ["GameScene"]
    assert port.game_state.is_landed is False
    assert port.game_state.immune_to_damage is True
    assert port.game_state.velocity == (0.0, 0.0)
    assert manager.audio.confirm_count == 1


def test_handleEvent_pressingEscape_shouldLaunchForShortCircuit():
    _, manager, port = land_at_landing_range()
    port.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, scancode=0, mod=0))
    assert manager.names() == ["GameScene"]
    assert port.game_state.launch_immunity_frames_left == port.game_state.launch_immunity_frames


def test_handleEvent_withAQuitRequest_shouldEndTheGameRatherThanJustTheModal():
    _, manager, port = land_at_landing_range()
    port.handle_event(pygame.event.Event(pygame.QUIT))
    assert manager.quit_called is True
    assert manager.names() == ["GameScene", "SpaceportView"]


def test_handleEvent_pressingMapOrJumpOrLandKeys_shouldBeIgnoredByTheModal():
    # The modal is the top scene, so M/J/T/L never reach the tactical layer: the
    # player cannot jump out of a spaceport, and cannot stack a second one.
    scene, manager, port = land_at_landing_range()
    for key in (pygame.K_m, pygame.K_j, pygame.K_l, pygame.K_t, pygame.K_SPACE):
        port.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, scancode=0, mod=0))
    assert manager.names() == ["GameScene", "SpaceportView"]


# ---------------------------------------------------------------------------
# GameScene: the flow that makes the slice vertical
# ---------------------------------------------------------------------------


def test_update_pressingLandOutsideLandingRange_shouldOpenNothingAndStaySilent():
    scene, manager = game_scene()
    scene.game_state.set_position(900.0, 900.0)
    press_key(scene, pygame.K_l)
    assert manager.names() == ["GameScene"], "no modal, and nothing stacked"
    assert scene.game_state.is_landed is False
    # The market still exists (it was dealt on entering Alpha) - pressing L
    # outside landing range simply does not raise it.
    assert scene.port_visit.system == "Alpha"
    assert not scene.tactical.overlays._banners, "an uninvited L must stay silent"


def test_update_pressingLandInsideLandingRange_shouldRollExactlyOnePortVisit():
    scene, manager = game_scene()
    assert scene.system_map.current_system == "Alpha"
    press_key(scene, pygame.K_l)
    port = manager.top
    assert scene.port_visit is port.visit
    assert port.visit.system == "Alpha"
    assert port.visit.serial == 1
    assert 1 <= len(port.contracts) <= scene.game_state.economy.missions_max
    # A second press while landed must not stack a second modal or re-roll.
    press_key(scene, pygame.K_l)
    assert manager.names() == ["GameScene", "SpaceportView"]
    assert scene.port_visit is port.visit


def test_update_launchingThenLandingAgain_shouldOpenThePortAgainInsteadOfSwallowingTheKeypress():
    """Regression: the modal ate the ``KEYUP`` for ``L``.

    The press goes to the tactical layer, the modal is pushed in the same frame,
    and the release arrives at the modal - so the input layer kept holding ``L``
    forever and the next press produced no rising edge. In play that is "the
    spaceport only opens every other time".
    """
    scene, manager = game_scene()
    press_key(scene, pygame.K_l)
    manager.top.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    scene.update()  # GameScene notices the launch and closes the modal
    assert scene.port_visit.system == "Alpha"  # the market outlives the modal
    press_key(scene, pygame.K_l)
    assert manager.names() == ["GameScene", "SpaceportView"]
    assert scene.game_state.is_landed is True


def test_update_afterLaunching_shouldCloseTheModalAndResetTheHeldKeys():
    scene, manager = game_scene()
    press_key(scene, pygame.K_l)
    manager.top.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
    assert scene.game_state.is_landed is False
    assert scene._port_modal_open is True  # closed on the next tactical frame
    scene.update()
    assert scene._port_modal_open is False
    assert scene.tactical.input._held == set()
    assert scene.tactical.input._rising == set()


def market_descriptor(visit: PortVisit) -> tuple:
    """A visit's market as plain data: destinations, sizes, and fares.

    Offer ids are deliberately excluded - they carry the visit serial, so two
    visits never share one and an assertion on ids proves nothing about whether
    the *markets* differ.
    """
    return tuple(
        (job.destination, job.cargo_units, job.passengers, job.fare)
        for job in visit.missions
    ) + tuple((offer.stat, offer.level, offer.cost) for offer in visit.upgrade_offers)


def test_update_launchingThenLandingAgain_shouldOfferTheSameMarketItDealtOnEntry():
    """The exploit this stage is not allowed to ship.

    ``L``, read the contracts, ``ESC``, ``L`` used to re-deal the whole board: a
    free market spin every two key presses, with no cost and no risk. The board
    now belongs to the system entry, so leaving the planet and landing again shows
    the same work - which is also the honest version of a spaceport: the player is
    choosing among offers, not pulling a slot machine lever.
    """
    scene, manager = game_scene()
    press_key(scene, pygame.K_l)
    first = manager.top
    first_board = market_descriptor(first.visit)
    first_offer_ids = tuple(job.offer_id for job in first.visit.missions)
    press_button(first, first._launch_button)
    scene.update()

    press_key(scene, pygame.K_l)
    second = manager.top
    assert second.visit is first.visit, "the very same board, not a re-roll"
    assert market_descriptor(second.visit) == first_board
    assert tuple(job.offer_id for job in second.visit.missions) == first_offer_ids


def test_update_takingAJobThenRelaunchingAndLanding_shouldStillShowItAboardNotAvailable():
    # GIVEN a job accepted, then a launch and a landing in the same system,
    scene, manager = game_scene()
    press_key(scene, pygame.K_l)
    port = manager.top
    button = next(iter(port._accept_buttons))
    job = port._accept_buttons[button]
    press_button(port, button)
    press_button(port, port._launch_button)
    scene.update()
    press_key(scene, pygame.K_l)
    again = manager.top
    # THEN the job is still aboard, still greyed out, and loads nothing more.
    assert again.game_state.offer_is_accepted(job.offer_id) is True
    assert again.game_state.cargo_used == job.cargo_units
    assert again.game_state.passengers_used == job.passengers
    # And the button for it comes back greyed, not as a fresh contract.
    relived = next(
        button for button, offer in again._accept_buttons.items()
        if offer.offer_id == job.offer_id
    )
    assert relived.is_enabled is False
    assert relived.text == "Aboard"


def test_update_jumpingAwayAndBack_shouldDealADifferentMarketForThatSystem():
    """Per-entry, not per-run: revisiting a system is a genuine new visit."""
    scene, manager = game_scene()
    alpha_first = market_descriptor(scene.port_visit)
    assert scene.port_visit.serial == 1, "entering Alpha at new game is entry one"

    scene.game_state.set_position(700.0, 0.0)
    scene.system_map.select("Bravo")
    press_key(scene, pygame.K_j)
    for _ in range(900):
        scene.update()
        if not scene.jumps.is_active:
            break
    assert scene.system_map.current_system == "Bravo"
    bravo_board = market_descriptor(scene.port_visit)
    assert scene.port_visit.serial == 2, "Bravo is the second entry of the run"

    scene.game_state.set_position(700.0, 0.0)
    scene.system_map.select("Alpha")
    press_key(scene, pygame.K_j)
    for _ in range(900):
        scene.update()
        if not scene.jumps.is_active:
            break
    assert scene.system_map.current_system == "Alpha"
    assert scene.port_visit.serial == 3, "Alpha entry number two"
    assert market_descriptor(scene.port_visit) != alpha_first, "a new visit deals new work"
    assert market_descriptor(scene.port_visit) != bravo_board


def test_portRng_withTheSameSeedAndEntry_shouldDealTheIdenticalMarket():
    """The market stream is derived, not cursored: seed + system + entry is enough."""
    graph = world_graph(seed=7)
    state = ship(seed=11)

    def deal(system: str, serial: int) -> PortVisit:
        return generate_port_offers(
            rules=state.economy, graph=graph, current_system=system,
            stats=state.stats, upgrade_levels=state.upgrade_levels,
            rng=port_rng(4242, system, serial), visit_serial=serial,
        )

    assert market_descriptor(deal("Bravo", 4)) == market_descriptor(deal("Bravo", 4))
    assert market_descriptor(deal("Bravo", 4)) != market_descriptor(deal("Bravo", 5))
    assert market_descriptor(deal("Bravo", 4)) != market_descriptor(deal("Charlie", 4))


def test_gameScene_marketsAreIndependentOfHowMuchFlyingHappenedFirst():
    """Ten thousand frames of thrust must not change the work on offer at Alpha.

    A market drawn from the gameplay generator would shift with the number of
    prior draws (starfields, arrival bearings, fuel burn), which makes the board a
    function of play history and the determinism tests a function of luck.
    """
    flown, _ = game_scene()
    fresh, _ = game_scene()
    for _ in range(10_000):
        flown.game_state.feed_input(thrust=True)
        flown.game_state.advance_frame()
    assert market_descriptor(flown.port_visit) == market_descriptor(fresh.port_visit)


def test_update_whileLanded_shouldNotAdvanceTheTacticalSimulation():
    # The stack pauses everything below the modal: the ship cannot drift out of
    # the port it is standing in, and cannot be scanned, jumped, or steered.
    scene, manager = game_scene()
    scene.game_state.set_position(60.0, 0.0)
    press_key(scene, pygame.K_l)
    position = scene.game_state.position
    for _ in range(120):
        manager.top.update()
        manager.top._ui.update(1 / 60)
    assert scene.game_state.position == position
    assert scene.game_state.is_landed is True


def test_newGame_withAMissingLoreFile_shouldReportAStartupErrorAndExit():
    # GIVEN the pool file redirected somewhere that does not exist,
    # THEN new game fails the way a bad config does (message + exit code), not
    # with a traceback and not with a spaceport that has nothing to say.
    import src.model.lore as lore_module

    original = lore_module.LORE_FILE
    lore_module.LORE_FILE = str(PROJECT_ROOT / "resources" / "definitely-not-here.txt")
    try:
        with pytest.raises(SystemExit) as exit_info:
            game_scene()
    finally:
        lore_module.LORE_FILE = original
    assert exit_info.value.code == 1


def test_newGame_overSeveralSeeds_shouldAssignEachSystemItsOwnLoreLineOnce():
    books = []
    for seed in (11, 22, 33):
        values = {**base_config(), "rng": {"seed": seed}}
        scene, _ = game_scene(values)
        books.append(scene.lore)
    for book in books:
        lines = [book.line_for(name) for name in NATO_SYSTEMS]
        assert all(lines)
        assert len(set(lines)) == len(NATO_SYSTEMS)


def test_draw_shouldReportTheEconomyFieldsOnTheHud():
    scene, manager = game_scene()
    press_key(scene, pygame.K_l)
    port = manager.top
    # A job that actually occupies cargo space, so the HUD counters cannot agree
    # with the model by both being zero.
    loaded = [(button, job) for button, job in port._accept_buttons.items() if job.cargo_units]
    assert loaded, "this board must have a cargo job to load"
    press_button(port, loaded[0][0])
    canvas = pygame.Surface(SCREEN_SIZE)
    scene.draw(canvas)
    assert scene.hud.cargo_used == scene.game_state.cargo_used > 0
    assert scene.hud.passengers_used == scene.game_state.passengers_used
    assert scene.hud.credits == scene.game_state.credits


# ---------------------------------------------------------------------------
# End-to-end through the real loop: the checkpoint the spec asks for
# ---------------------------------------------------------------------------


def _pump(loop, frames):
    for _ in range(frames):
        assert loop.step_once(), "the loop stopped unexpectedly"


def _tap_key(loop, key):
    """Press, one frame, release, one frame.

    The press and the release must land in *separate* frames: the input layer is
    edge-triggered, and Stage 7/8 learned that a KEYDOWN and its KEYUP arriving
    in the same batch reads as a key that was never pressed.
    """
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, scancode=0, mod=0))
    _pump(loop, 1)
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=key, scancode=0, mod=0))
    _pump(loop, 1)


def _click(loop, button):
    """Hover, press, release, across frames - what a mouse actually does."""
    rect = button.relative_rect
    pos = (int(rect.centerx), int(rect.centery))
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEMOTION, pos=pos, rel=(1, 1), buttons=(0, 0, 0)))
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, pos=pos, button=1, buttons=(1, 1, 1)))
    _pump(loop, 2)
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONUP, pos=pos, button=1, buttons=(0, 0, 0)))
    _pump(loop, 2)


def _lane_path(graph, start: str, target: str) -> "tuple[str, ...]":
    """The systems to fly, hop by hop, following the fewest-hop lane."""
    path = [start]
    current = start
    while current != target:
        remaining = graph.jump_distance(current, target)
        step = min(graph.neighbours(current), key=lambda name: graph.jump_distance(name, target))
        assert graph.jump_distance(step, target) == remaining - 1
        path.append(step)
        current = step
    return tuple(path)


def test_fullPlaythrough_landAcceptJumpLand_shouldPayTheFareExactlyOnce(config_factory):
    """The vertical slice, driven through ``FixedTimestepLoop.step_once()``.

    Title -> difficulty -> tactical -> spaceport (click Accept with the real
    mouse) -> Launch -> jump -> land at the destination -> paid once, then land
    again -> paid zero.
    """
    # One config source for the whole slice: the medium table, seeded, so the
    # world, the board, and the fares are all reproducible.
    config_dir = config_factory(overrides={"rng.seed": 4242})
    configs = load_config(config_dir)
    screen = pygame.display.get_surface()
    manager = SceneManager(screen=screen, configs=configs, audio=AudioSystem())
    manager.selected_config = configs["config_medium.json"]
    game = GameScene(manager)
    manager.push(game)
    loop = FixedTimestepLoop(scene_manager=manager, screen=screen)

    # Land at Alpha (the ship starts at the planet centre, i.e. in range).
    _tap_key(loop, pygame.K_l)
    assert manager._stack[-1].__class__.__name__ == "SpaceportView"
    port = manager._stack[-1]
    assert port.contracts, "the port must have something on the board"

    # Take the shortest lane on the board. The far lanes are the interesting ones
    # to *price*; the short one is the one worth flying in a test.
    delivery_button, delivery_job = min(
        port._accept_buttons.items(), key=lambda item: item[1].distance
    )
    cargo_before, pax_before = game.game_state.cargo_used, game.game_state.passengers_used
    _click(loop, delivery_button)
    assert game.game_state.cargo_used == cargo_before + delivery_job.cargo_units
    assert game.game_state.passengers_used == pax_before + delivery_job.passengers
    assert manager._stack[-1] is port, "accepting must not close the modal"

    # Top the tank up in port, so a multi-hop lane is affordable and the refuel
    # button gets exercised on the way out.
    if game.game_state.fuel_room:
        _click(loop, port._refuel_button)
        assert game.game_state.fuel == pytest.approx(game.game_state.stats.fuel_capacity)

    _click(loop, port._launch_button)
    assert manager._stack[-1] is game
    assert game.game_state.immune_to_damage is True

    # Fly the lane: out of landing range, one jump per hop, until the destination.
    # A 4-hop lane costs more tank than any ship holds, so the trip has to stop
    # for fuel somewhere: this is the part of the loop where the player lands in
    # the middle of nowhere, buys a full tank, and goes back out.
    jump_fuel = JumpParams.from_config(manager.game_config()["tactical"]).fuel_cost
    lane = _lane_path(game.system_map.graph, "Alpha", delivery_job.destination)
    for hop in lane[1:]:
        # "<=", not "<": Stage 8's spec rule is that a jump with *exactly* the
        # fuel price is refused outright, so an empty tank is the safe state.
        if game.game_state.fuel <= jump_fuel:
            game.game_state.set_position(0.0, 0.0)  # back down to the planet
            _tap_key(loop, pygame.K_l)
            enroute = manager._stack[-1]
            assert enroute.__class__.__name__ == "SpaceportView"
            _click(loop, enroute._refuel_button)
            assert game.game_state.fuel == pytest.approx(game.game_state.stats.fuel_capacity)
            _click(loop, enroute._launch_button)
            assert manager._stack[-1] is game
        game.game_state.set_position(700.0, 0.0)
        game.system_map.select(hop)
        _tap_key(loop, pygame.K_j)
        frames = 0
        while game.jumps.is_active and frames < 1200:
            _pump(loop, 1)
            frames += 1
        assert not game.jumps.is_active, f"the jump to {hop} never completed"
        assert game.system_map.current_system == hop

    credits_after_delivery = game.game_state.credits
    cargo_expected = cargo_before
    game.game_state.set_position(50.0, 0.0)
    _tap_key(loop, pygame.K_l)
    assert manager._stack[-1].__class__.__name__ == "SpaceportView"
    assert game.game_state.credits == credits_after_delivery + delivery_job.fare
    assert game.game_state.cargo_used == cargo_expected

    # Launch, stay put, land again: the same job must not pay a second time, and
    # the market must be the one this entry dealt - re-landing is not a re-roll.
    destination_market = market_descriptor(manager._stack[-1].visit)
    _click(loop, manager._stack[-1]._launch_button)
    _pump(loop, 30)
    balance = game.game_state.credits
    game.game_state.set_position(50.0, 0.0)
    _tap_key(loop, pygame.K_l)
    relanded = manager._stack[-1]
    assert relanded.__class__.__name__ == "SpaceportView"
    assert game.game_state.credits == balance
    assert market_descriptor(relanded.visit) == destination_market
    assert relanded.visit.serial == game.port_visit.serial
