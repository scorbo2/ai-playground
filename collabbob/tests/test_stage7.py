"""Stage 7 tests: system graph, map layout, fog of war, selection, map modal.

Four layers, mirroring the split of the implementation:

* :mod:`src.map_systems.graph` - property tests over 200+ seeds proving every
  topology invariant (26 NATO systems, degree bounds, Alpha's pinned edges,
  connectivity), determinism per seed, and that nonsense constraints fail loudly
  instead of hanging or crashing with an IndexError.
* :mod:`src.map_systems.layout` - pure geometry: the gate's "node + label must
  not overlap" check, per-angle label offsets, hit testing, and the ring
  ordering that keeps edges from tangling.
* :class:`~src.map_systems.system_map.SystemMapState` - select/unselect/gating
  transitions and fog-of-war reveal rules.
* :class:`~src.scenes.map_view.MapView` plus the ``M`` binding in the real loop -
  pixel-level checks that the modal repaints the whole window, draws *only*
  revealed systems, and keeps labels off the circles they name.

The pixel checks exist because every one of those four mistakes was present in
the first Stage 7 revision, and none of them were visible to a test that only
called helper functions.
"""

import functools
import hashlib
import os
import random
import subprocess
import sys
from pathlib import Path

import pygame
import pytest

import main  # noqa: F401  (ensures project root is on sys.path)

from src.config import base_config, load_config
from src.fonts import game_font
from src.map_systems.graph import (
    NATO_SYSTEMS,
    GraphConstraints,
    GraphGenerationError,
    SystemGraphGenerator,
)
from src.map_systems.layout import (
    HEADER_BAND,
    LABEL_FONT_SIZES,
    MapLayoutError,
    boxes_overlap,
    build_map_layout,
    circle_overlaps_box,
    circles_clear,
    graph_circular_order,
    label_offset_for_angle,
    point_in_box,
)
from src.map_systems.system_map import DESELECTED, IGNORED, SELECTED, SystemMapState
from src.scenes.map_view import MapView, _MapPalette

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# The stage gate asks for "property tests over >= 200 seeds".
SEED_SAMPLE = range(200)
LAYOUT_SEED_SAMPLE = range(60)  # layout checks build real fonts, so keep this tighter

# The shipped-shape constraints every graph test generates against.
DEFAULT_CONSTRAINTS = GraphConstraints(system_count=26, min_degree=1, max_degree=3)


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


def fake_measure(text: str, size: int) -> tuple[int, int]:
    """A pygame-free label metric: monospace-ish, width proportional to size.

    Layout code takes metrics as a callable specifically so these tests can run
    without touching fonts; the real-font variants below use ``game_font``.
    """
    return (len(text) * size // 2, size)


def real_measure(text: str, size: int) -> tuple[int, int]:
    """The metrics the renderer actually uses."""
    return game_font(size).size(text)


def graph_for_seed(seed: int, constraints: GraphConstraints = DEFAULT_CONSTRAINTS):
    return SystemGraphGenerator(constraints, rng=random.Random(seed)).generate()


@functools.lru_cache(maxsize=None)
def layout_for_seed(seed: int):
    """Cached: several layout tests want the same 60 worlds, and fonts are slow."""
    graph = graph_for_seed(seed)
    return build_map_layout(graph, (1024, 768), real_measure)


def map_state(seed: int = 0) -> SystemMapState:
    """A full map state over a known graph, layout included."""
    graph = graph_for_seed(seed)
    return SystemMapState(graph=graph, layout=build_map_layout(graph, (1024, 768), real_measure))


class _FakeAudio:
    def __init__(self):
        self.confirm_count = 0

    def play_confirm(self):
        self.confirm_count += 1


class _FakeManager:
    """Enough of SceneManager for MapView: an audio system and stack verbs."""

    def __init__(self):
        self.audio = _FakeAudio()
        self.pop_count = 0
        self.quit_count = 0

    def pop(self):
        self.pop_count += 1

    def quit(self):
        self.quit_count += 1


def _map_view(state: SystemMapState) -> "tuple[MapView, _FakeManager]":
    manager = _FakeManager()
    view = MapView(state)
    view.on_enter(manager)  # what SceneManager.push() does
    return view, manager


def _draw_view_canvas(state: SystemMapState) -> "pygame.Surface":
    """A freshly painted map on a private surface (never the shared display)."""
    canvas = pygame.Surface((1024, 768))
    view, _ = _map_view(state)
    view.draw(canvas)
    return canvas


def _count_colour(canvas: "pygame.Surface", colour: "tuple[int, int, int]") -> int:
    """Exactly how many pixels are ``colour`` (aligned scan, no stride artifacts).

    Sampling on a stride used to make a *fully painted* box measure as 25%
    coverage in this project's suite, so colour checks here are exhaustive.
    """
    raw = pygame.image.tobytes(canvas, "RGB")
    packed = bytes(colour)
    return sum(1 for offset in range(0, len(raw), 3) if raw[offset:offset + 3] == packed)


def _colour_at(canvas: "pygame.Surface", pos: "tuple[int, int]") -> "tuple[int, int, int]":
    return canvas.get_at((int(pos[0]), int(pos[1])))[:3]


def _pixels_of_colour_in_node_area(
    canvas: "pygame.Surface", centre: "tuple[float, float]", colour, radius: int = 8
) -> int:
    """Count ``colour`` pixels inside a small square around a node's slot."""
    hits = 0
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if _colour_at(canvas, (centre[0] + dx, centre[1] + dy)) == colour:
                hits += 1
    return hits


# ---------------------------------------------------------------------------
# Graph generator: the stage gate's property tests over 200+ seeds
# ---------------------------------------------------------------------------


def test_generate_over200Seeds_everyGraphSatisfiesEveryTopologyInvariant():
    """GIVEN 200 distinct seeds, WHEN each graph is generated and validated,
    THEN 26 NATO systems, degree bounds, Alpha's exact edges and connectivity
    all hold for every one of them."""
    constraints = DEFAULT_CONSTRAINTS
    for seed in SEED_SAMPLE:
        graph = graph_for_seed(seed, constraints)

        assert graph.names == NATO_SYSTEMS[:26], f"seed {seed}: wrong system roster"
        assert graph.names[0] == "Alpha", f"seed {seed}: Alpha must be the anchor"
        assert graph.neighbours("Alpha") == frozenset({"Bravo", "Charlie", "Delta"}), (
            f"seed {seed}: Alpha's degree is pinned to Bravo/Charlie/Delta"
        )
        for name in graph.names:
            degree = graph.neighbour_count(name)
            assert 1 <= degree <= 3, f"seed {seed}: {name} has degree {degree}, outside [1,3]"
        assert graph.is_connected(), f"seed {seed}: island systems detected"
        graph.validate(constraints)  # raises on any regression


def test_generate_over200Seeds_edgesAreMutualAndUndirected():
    """GIVEN 200 seeds, WHEN adjacency is inspected, THEN every edge is reciprocal."""
    for seed in SEED_SAMPLE:
        graph = graph_for_seed(seed)
        for first in graph.names:
            for second in graph.neighbours(first):
                assert first in graph.neighbours(second), (
                    f"seed {seed}: one-way edge {first} -> {second}"
                )
        expected = sum(graph.neighbour_count(name) for name in graph.names) // 2
        assert len(graph.edges()) == expected, f"seed {seed}: edges() double-counted"


def test_generate_withTheSameSeedTwice_shouldProduceIdenticalAdjacency():
    """Determinism per seed: one seed, one world."""
    first = graph_for_seed(1234)
    second = graph_for_seed(1234)
    assert first.adjacency == second.adjacency, "the same seed produced two different worlds"


def test_generate_withTheSameSeedAcrossHashSeeds_shouldProduceIdenticalAdjacency():
    """Determinism must survive a new process, not just a fresh generator.

    The first revision drew attachment candidates out of a ``set``. Python
    randomises string hashing per process, so the *same seed* produced a
    different graph on every run - invisible inside a single pytest process,
    fatal for replaying a saved world. This test generates the graph in child
    processes with different PYTHONHASHSEED values and compares digests.
    """
    script = (
        "import hashlib, random, sys;"
        "sys.path.insert(0, sys.argv[1]);"
        "from src.map_systems.graph import SystemGraphGenerator, GraphConstraints;"
        "g=SystemGraphGenerator(GraphConstraints(system_count=26,min_degree=1,max_degree=3),"
        "rng=random.Random(4242)).generate();"
        "print(hashlib.sha256(repr(sorted((k,sorted(v)) for k,v in g.adjacency.items()))"
        ".encode()).hexdigest())"
    )
    digests = set()
    for hash_seed in ("0", "1", "12345"):
        env = dict(os.environ, PYTHONHASHSEED=hash_seed)
        result = subprocess.run(
            [sys.executable, "-c", script, str(PROJECT_ROOT)],
            capture_output=True, text=True, env=env, timeout=60,
        )
        assert result.returncode == 0, f"child process failed: {result.stderr}"
        digests.add(result.stdout.strip())
    assert len(digests) == 1, f"seed 4242 produced {len(digests)} different worlds: {digests}"


def test_generate_over200Seeds_differingSeedsProduceDifferentWorlds():
    """Sanity check on the seeding: a 'fixed' world must not be the only world."""
    digests = set()
    for seed in range(40):
        graph = graph_for_seed(seed)
        digests.add(hashlib.sha256(
            repr(sorted((k, sorted(v)) for k, v in graph.adjacency.items())).encode()
        ).hexdigest())
    assert len(digests) == 40, "the generator is not actually varying with the seed"


def test_generate_withMinDegreeTwo_shouldLiftEveryDegreeAndCreateRouteRedundancy():
    """GIVEN connections_min=2, WHEN generating, THEN no leaf systems remain.

    Phase 3 of the generator is what makes connections_min a real knob: the
    first revision accepted the config key and ignored it, so a world configured
    with min=2 still had degree-1 systems.
    """
    constraints = GraphConstraints(system_count=26, min_degree=2, max_degree=3)
    for seed in range(20):
        graph = graph_for_seed(seed, constraints)
        degrees = {name: graph.neighbour_count(name) for name in graph.names}
        assert min(degrees.values()) >= 2, f"seed {seed}: leaves survived min_degree=2"
        assert max(degrees.values()) <= 3, f"seed {seed}: degree ceiling breached"
        assert graph.is_connected(), f"seed {seed}: disconnected"
        # 26 systems with every degree >= 2 needs > 25 edges: a spanning tree alone
        # can never satisfy min=2, so cycles must have been added.
        assert len(graph.edges()) > len(graph.names) - 1, f"seed {seed}: still a bare tree"


def test_generate_withUnreachableMinDegree_shouldRaiseGraphGenerationError():
    """GIVEN min=max=3 over 5 systems (odd degree sum), THEN a clear error, not a hang.

    A 5-node graph where every node has degree 3 cannot exist; the generator must
    report the unsatisfiable constraint instead of looping or producing a
    half-built world.
    """
    constraints = GraphConstraints(
        system_count=5, min_degree=3, max_degree=3,
        root_neighbours=("Bravo", "Charlie", "Delta"),
    )
    with pytest.raises(GraphGenerationError) as excinfo:
        SystemGraphGenerator(constraints, rng=random.Random(7)).generate()
    assert "connections_min" in str(excinfo.value)


@pytest.mark.parametrize("constraints,expectation", [
    (GraphConstraints(system_count=27, min_degree=1, max_degree=3), "system_count"),
    (GraphConstraints(system_count=1, min_degree=1, max_degree=3), "system_count"),
    (GraphConstraints(system_count=26, min_degree=4, max_degree=3), "connections_min"),
    (GraphConstraints(system_count=26, min_degree=1, max_degree=30), "connections_max"),
    (GraphConstraints(system_count=4, min_degree=1, max_degree=2,
                      root_neighbours=("Bravo", "Charlie", "Delta")), "alpha_connections"),
    (GraphConstraints(system_count=26, min_degree=1, max_degree=3,
                      root_neighbours=("Bravo", "Klingon")), "Klingon"),
    (GraphConstraints(system_count=26, min_degree=1, max_degree=3,
                      root_neighbours=("Bravo", "Bravo")), "duplicates"),
])
def test_constraintsCheck_withNonsense_shouldRaiseGraphGenerationError(constraints, expectation):
    """GIVEN an impossible map config, THEN the failure names the bad knob."""
    with pytest.raises(GraphGenerationError) as excinfo:
        SystemGraphGenerator(constraints, rng=random.Random(1)).generate()
    assert expectation in str(excinfo.value)


def test_fromConfig_withTheShippedMapSections_shouldBuildValidWorlds():
    """Every shipped config's ``map`` section must generate a legal world.

    Ties the three config files to the generator contract: a typo in
    config_hard.json fails here rather than at New game time.
    """
    configs = load_config(str(PROJECT_ROOT))
    for name, config in configs.items():
        graph = SystemGraphGenerator.from_config(
            config["map"], rng=random.Random(99)
        ).generate()
        assert graph.neighbours("Alpha") == frozenset({"Bravo", "Charlie", "Delta"}), name
        assert graph.is_connected(), name


def test_fromConfig_withMissingOrMalformedKeys_shouldRaiseGraphGenerationError():
    """A map section missing a key fails as a named data error, not a KeyError."""
    broken = dict(base_config()["map"])
    broken.pop("connections_max")
    with pytest.raises(GraphGenerationError) as excinfo:
        GraphConstraints.from_config(broken)
    assert "connections_max" in str(excinfo.value)


# ---------------------------------------------------------------------------
# Layout: placement, label boxes, hit testing
# ---------------------------------------------------------------------------


def test_graphCircularOrder_over40Seeds_producesNoCrossingEdges():
    """GIVEN the DFS ring order, WHEN edges are drawn as chords, THEN none cross.

    Degree <= 3 with a depth-first placement means every subtree occupies one
    contiguous arc, so nested edges never cross. Placing the same graph
    alphabetically tangles: measured at ~59 crossing pairs per world.
    """
    def crosses(a, b, c, d):
        def orient(p, q, r):
            return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
        o1, o2 = orient(c, d, a), orient(c, d, b)
        o3, o4 = orient(a, b, c), orient(a, b, d)
        return (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0)

    for seed in range(40):
        graph = graph_for_seed(seed)
        layout = build_map_layout(graph, (1024, 768), real_measure)
        edges = list(graph.edges())
        for index, (first, second) in enumerate(edges):
            for other_first, other_second in edges[index + 1:]:
                if len({first, second, other_first, other_second}) < 4:
                    continue
                assert not crosses(layout.positions[first], layout.positions[second],
                                   layout.positions[other_first], layout.positions[other_second]), (
                    f"seed {seed}: edges ({first},{second}) and ({other_first},{other_second}) cross"
                )


def test_graphCircularOrder_shouldVisitEverySystemOnceStartingAtTheRoot():
    """The ring order is a spanning preorder: all systems, no repeats, root first."""
    graph = graph_for_seed(5)
    order = graph_circular_order(graph, "Alpha")
    assert order[0] == "Alpha"
    assert sorted(order) == sorted(graph.names)
    assert len(order) == len(graph.names)


def test_buildMapLayout_overLayoutSeeds_noNodeOrLabelOverlaps():
    """The gate's overlap check: no label/label, node/node or label/node collisions.

    Runs with the real font metrics the renderer uses, because the first
    revision sized its ring from a "ZZZZZ" proxy (60 px) while the label it was
    protecting ("November") measured 96 px - and shipped a map reading
    "Alha", "Br vo", "Nov ber".
    """
    for seed in LAYOUT_SEED_SAMPLE:
        layout = layout_for_seed(seed)
        offenders = layout.overlapping_pairs()
        assert offenders == [], f"seed {seed}: overlaps {offenders[:5]}"


def test_buildMapLayout_overLayoutSeeds_everyBoxFitsInsideTheWindowBelowTheHeaderBand():
    """Nothing may be clipped by the window edge or hidden under the modal's copy."""
    for seed in LAYOUT_SEED_SAMPLE:
        layout = layout_for_seed(seed)
        assert layout.fits_on_screen((1024, 768)), f"seed {seed}: layout leaves the window"
        tops = [layout.label_boxes[name][1] for name in layout.positions]
        assert min(tops) >= HEADER_BAND, f"seed {seed}: labels intrude on the header band"


def test_buildMapLayout_labelFontIsIdenticalAcrossSeeds():
    """World-to-world the map must look like the same UI, not a lucky font size.

    Sizing the font from the layout that happens to have been built made the
    label size swing between 14 and 20 pt depending on the world seed.
    """
    sizes = {layout_for_seed(seed).label_font_size for seed in LAYOUT_SEED_SAMPLE}
    assert len(sizes) == 1, f"label font size varies per world: {sorted(sizes)}"
    assert sizes.pop() in LABEL_FONT_SIZES


def test_labelOffsetForAngle_atTheHorizontalExtreme_shouldClearHalfTheLabelWidth():
    """A label at 3 o'clock sticks out sideways, so the node needs width clearance.

    The intuitive offset ("half the label height plus a gap") puts the node
    *inside* the label box at the left/right of the ring: a 64x14 label half a
    label-width away from a 24 px circle buries the circle.
    """
    width, height, clearance = 64, 14, 18
    horizontal = label_offset_for_angle(width, height, clearance, 0.0)
    vertical = label_offset_for_angle(width, height, clearance, 1.5707963267948966)

    assert horizontal == pytest.approx(width / 2 + clearance, abs=0.01)
    assert vertical == pytest.approx(height / 2 + clearance, abs=0.01)
    assert horizontal > vertical, "sideways labels need more room than stacked ones"
    assert (width / 2 + clearance) > height / 2, "the naive offset would have failed"


def test_buildMapLayout_labelsAreAnchoredOutsideTheirOwnCircles():
    """The layout must guarantee text never sits on the circle it labels."""
    layout = layout_for_seed(3)
    for name in layout.positions:
        assert circle_overlaps_box(
            layout.positions[name], layout.node_radius, layout.label_boxes[name]
        ) is False, f"{name}: label box intersects its own node circle"


def test_nodeAt_withClickInsideALabelBox_shouldReturnThatSystem():
    """Clicking a system's name selects it, not just clicking the dot."""
    layout = layout_for_seed(3)
    box = layout.label_boxes["Charlie"]
    click = ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)
    assert layout.node_at(click, layout.positions.keys()) == "Charlie"


def test_nodeAt_withClickInsideTheHitCircle_shouldReturnTheNearestSystem():
    layout = layout_for_seed(3)
    x, y = layout.positions["Alpha"]
    assert layout.node_at((x + layout.hit_radius * 0.5, y), layout.positions.keys()) == "Alpha"


def test_nodeAt_withClickInEmptySpace_shouldReturnNone():
    """A click far from every node and label must not select anything by accident.

    The exact centre of the ring is the most adversarial spot in the middle: it
    sits a whole radius away from every node, well past the hit radius.
    """
    layout = layout_for_seed(3)
    assert layout.node_at(layout.center, layout.positions.keys()) is None
    assert layout.hit_radius < layout.radius / 2.0, (
        "the hit radius must stay clear of the ring's centre"
    )


def test_nodeAt_withCandidatesExcludingASystem_shouldNeverReturnIt():
    """Fog of war is enforced at the hit-test level, not only in the renderer."""
    layout = layout_for_seed(3)
    target = "Zulu"
    click = layout.positions[target]
    assert layout.node_at(click, layout.positions.keys()) == target
    assert layout.node_at(click, [n for n in layout.positions if n != target]) != target


def test_buildMapLayout_withATinyWindow_shouldRaiseMapLayoutError():
    """A window too small for 26 labels is a data error, not a silently cramped map."""
    graph = graph_for_seed(0)
    with pytest.raises(MapLayoutError):
        build_map_layout(graph, (120, 120), real_measure)


# ---------------------------------------------------------------------------
# Geometry primitives
# ---------------------------------------------------------------------------


def test_boxes_overlap_withDisjointBoxes_shouldBeFalseAndWithOverlappingShouldBeTrue():
    """The first revision indexed a[4]/a[5] on a 4-tuple: a guaranteed IndexError."""
    assert boxes_overlap((0, 0, 10, 10), (20, 0, 30, 10)) is False
    assert boxes_overlap((0, 0, 10, 10), (5, 5, 15, 15)) is True
    assert boxes_overlap((0, 0, 10, 10), (10, 0, 20, 10)) is False, "touching edges do not overlap"
    assert boxes_overlap((0, 0, 10, 10), (0, 10, 10, 20)) is False, "vertical touching too"


def test_pointInBox_withInsideOutsideAndEdgeCases_shouldAgreeWithGeometry():
    assert point_in_box((5, 5), (0, 0, 10, 10)) is True
    assert point_in_box((11, 5), (0, 0, 10, 10)) is False
    assert point_in_box((0, 10), (0, 0, 10, 10)) is True, "on the boundary counts"


def test_circleOverlapsBox_withCircleBesideAndOverAndTouchingABox_shouldReportCorrectly():
    box = (0, 0, 10, 10)
    assert circle_overlaps_box((5, 5), 1, box) is True
    assert circle_overlaps_box((20, 5), 1, box) is False
    assert circle_overlaps_box((-2, 5), 3, box) is True
    # Exactly tangent counts as colliding: the overlap check exists to prove a
    # layout has *clearance*, and a tangent layout has none.
    assert circle_overlaps_box((-2, 5), 2, box) is True
    assert circle_overlaps_box((-2, 5), 1.9, box) is False


def test_circlesClear_withOverlappingAndSeparatedCentres_shouldReportCorrectly():
    assert circles_clear((0, 0), (10, 0), 6) is False
    assert circles_clear((0, 0), (12, 0), 6) is True


# ---------------------------------------------------------------------------
# SystemMapState: fog of war, selection rules, transitions
# ---------------------------------------------------------------------------


def test_initialState_shouldRevealOnlyTheCurrentSystemAndItsNeighbours():
    """Fog of war at game start: Alpha plus Bravo, Charlie, Delta. Nothing else."""
    state = map_state(0)
    assert state.current_system == "Alpha"
    assert state.revealed == {"Alpha", "Bravo", "Charlie", "Delta"}
    assert state.selected_system is None
    assert state.visible_nodes() == ("Alpha", "Bravo", "Charlie", "Delta")


def test_visibleEdges_shouldOmitEveryEdgeTouchingAnUnrevealedSystem():
    """An edge into the dark hands the player topology they have not discovered.

    The first revision drew every node circle on screen regardless of reveal
    state, so the whole 26-system map was visible from the first frame.
    """
    state = map_state(0)
    edges = state.visible_edges()
    assert set(edges) == {("Alpha", "Bravo"), ("Alpha", "Charlie"), ("Alpha", "Delta")}
    for first, second in edges:
        assert first in state.revealed and second in state.revealed
    assert len(edges) < len(state.graph.edges()), "the whole graph must not be visible yet"


def test_visibleNodes_withMoreSystemsRevealed_shouldGrowAndStayInLayoutOrder():
    state = map_state(0)
    before = set(state.visible_nodes())
    state.arrive("Bravo")
    after = set(state.visible_nodes())
    assert before < after, "arriving must reveal more of the map"
    assert set(after) <= set(state.layout.positions), "visible nodes must be placeable"
    assert list(state.visible_nodes()) == [
        name for name in state.layout.positions if name in state.revealed
    ], "draw order must follow the cached layout order"


def test_canSelect_withAdjacentRevealedSystem_shouldBeTrue():
    state = map_state(0)
    assert state.can_select("Bravo") is True


def test_canSelect_withTheCurrentSystem_shouldBeFalse():
    """You cannot set a destination for the system you are already standing in."""
    state = map_state(0)
    assert state.can_select("Alpha") is False


def test_canSelect_withAnUnrevealedSystem_shouldBeFalse():
    state = map_state(0)
    assert state.can_select("Zulu") is False
    assert state.can_select("Whiskey") is False


def test_canSelect_withRevealedButNonAdjacentSystem_shouldBeFalse():
    """Revealed is not the same as reachable: sibling systems stay unclickable."""
    state = map_state(0)
    state.arrive("Bravo")  # Charlie and Delta stay revealed, but are Bravo's siblings
    assert state.is_revealed("Charlie") is True
    assert "Charlie" not in state.graph.neighbours("Bravo")
    assert state.can_select("Charlie") is False


def test_handleMapClick_withLegalNeighbour_shouldSelectItAndReportSelected():
    state = map_state(0)
    assert state.handle_map_click("Delta") == SELECTED
    assert state.selected_system == "Delta"
    assert state.has_selection is True


def test_handleMapClick_withTheAlreadySelectedSystem_shouldDeselectAndReportDeselected():
    """Toggle-off, per spec.

    Order matters here: a selected neighbour is still selectable, so a
    can_select-first implementation re-selects it forever and the toggle is dead
    code. This test is what caught that ordering bug.
    """
    state = map_state(0)
    state.handle_map_click("Bravo")
    assert state.can_select("Bravo") is True, "still a legal target, which is the trap"
    assert state.handle_map_click("Bravo") == DESELECTED
    assert state.selected_system is None
    assert state.handle_map_click("Bravo") == SELECTED, "and a third click selects again"


def test_handleMapClick_withUnreachableOrEmptyTarget_shouldIgnoreAndLeaveStateAlone():
    state = map_state(0)
    state.handle_map_click("Charlie")
    for ignored in (None, "Zulu", "Alpha"):
        assert state.handle_map_click(ignored) == IGNORED
    assert state.selected_system == "Charlie", "an ignored click must not disturb the selection"


def test_select_withIllegalTarget_shouldRaiseValueError():
    """The raising path stays for callers that want the failure spelled out."""
    state = map_state(0)
    with pytest.raises(ValueError):
        state.select("Zulu")
    with pytest.raises(ValueError):
        state.select("Alpha")


def test_arrive_withANewSystem_shouldRevealItAndItsNeighboursPermanently():
    """Reveal-on-arrival is monotonic: revealed never shrinks."""
    state = map_state(0)
    graph = state.graph
    before = set(state.revealed)
    state.arrive("Bravo")
    expected = before | {"Bravo"} | set(graph.neighbours("Bravo"))
    assert state.revealed == expected
    assert state.current_system == "Bravo"
    state.arrive("Charlie")
    assert before <= state.revealed, "fog of war never closes back in"


def test_arrive_shouldClearTheSelection():
    """A jump consumes its destination: you cannot still be bound for where you are."""
    state = map_state(0)
    state.handle_map_click("Bravo")
    state.arrive("Bravo")
    assert state.selected_system is None


def test_arrive_withAnUnknownSystem_shouldRaiseValueError():
    state = map_state(0)
    with pytest.raises(ValueError):
        state.arrive("Klingon")


def test_systemMapState_withALayoutFromAnotherWorld_shouldRaiseValueError():
    """Same 26 names, different world: the layout must belong to this graph.

    Both worlds contain Alpha..Zulu, so a name-set comparison passes while the
    coordinates are those of a different topology - every click would then
    select the wrong star system, with nothing visibly wrong on screen.
    """
    graph = graph_for_seed(0)
    other_graph = graph_for_seed(1)
    layout = build_map_layout(other_graph, (1024, 768), real_measure)
    assert set(layout.positions) == set(graph.names), "the trap: the name sets do match"
    with pytest.raises(ValueError):
        SystemMapState(graph=graph, layout=layout)


def test_systemMapState_withUnknownCurrentSystem_shouldRaiseValueError():
    graph = graph_for_seed(0)
    layout = build_map_layout(graph, (1024, 768), real_measure)
    with pytest.raises(ValueError):
        SystemMapState(graph=graph, layout=layout, current_system="Klingon")


# ---------------------------------------------------------------------------
# MapView: what actually gets painted
# ---------------------------------------------------------------------------


def test_draw_shouldLeaveNoTraceOfTheSceneBeneathIt():
    """A full-screen modal repaints; it does not composite.

    The first revision never cleared, so the tactical view, HUD and minimap
    showed straight through the "modal". Filling the canvas with a colour the
    map never uses makes any leftover pixel unmissable.
    """
    state = map_state(0)
    canvas = pygame.Surface((1024, 768))
    canvas.fill((255, 0, 255))
    view, _ = _map_view(state)
    view.draw(canvas)
    assert _count_colour(canvas, (255, 0, 255)) == 0, "the modal left pixels behind"


def test_draw_withUnrevealedSystems_shouldNotPaintTheirCircles():
    """Fog of war at the pixel level: 4 revealed, 26 slots known."""
    state = map_state(0)
    canvas = _draw_view_canvas(state)
    hidden = [name for name in state.graph.names if not state.is_revealed(name)]
    assert len(hidden) == 22, "sanity: most of the world must still be hidden"
    for name in hidden:
        hits = _pixels_of_colour_in_node_area(canvas, state.layout.positions[name], _MapPalette.node)
        assert hits == 0, f"{name} was drawn although it is not revealed"


def test_draw_withRevealedSystems_shouldPaintTheirCircles():
    state = map_state(0)
    canvas = _draw_view_canvas(state)
    for name in ("Bravo", "Charlie", "Delta"):
        hits = _pixels_of_colour_in_node_area(canvas, state.layout.positions[name], _MapPalette.node)
        assert hits > 0, f"{name} is revealed but was not drawn"


def test_draw_currentSystem_shouldUseTheYouAreHereColour():
    state = map_state(0)
    canvas = _draw_view_canvas(state)
    centre = state.layout.positions["Alpha"]
    assert _colour_at(canvas, centre) == _MapPalette.current


def test_draw_shouldNeverRenderLabelGlyphsOnTopOfTheirOwnCircle():
    """The centre of a node must stay the circle's own colour.

    Labels used to be blitted centred on the node: white text on a white
    circle, which measured as "Alha", "Br vo" and "Nov ber" on screen.
    """
    state = map_state(0)
    canvas = _draw_view_canvas(state)
    for name in ("Bravo", "Charlie", "Delta"):
        centre = state.layout.positions[name]
        assert _colour_at(canvas, centre) == _MapPalette.node, f"{name}: text over its own circle"


def test_draw_selectedSystem_shouldBracketItsLabel(monkeypatch):
    """The [ ] markers come from the spec and must appear on selection."""
    rendered = _spy_on_render_text(monkeypatch)
    state = map_state(0)
    state.handle_map_click("Bravo")
    view, _ = _map_view(state)
    view.draw(pygame.Surface((1024, 768)))
    texts = [text for text, _ in rendered]
    assert "Bravo" in texts
    assert "[" in texts and "]" in texts, "selection must be marked with [ ] brackets"


def test_draw_withoutSelection_shouldNotBracketAnything(monkeypatch):
    rendered = _spy_on_render_text(monkeypatch)
    view, _ = _map_view(map_state(0))
    view.draw(pygame.Surface((1024, 768)))
    texts = [text for text, _ in rendered]
    assert "[" not in texts and "]" not in texts


def test_draw_header_shouldNameTheCurrentSystemAndTheDestination(monkeypatch):
    rendered = _spy_on_render_text(monkeypatch)
    state = map_state(0)
    state.handle_map_click("Delta")
    view, _ = _map_view(state)
    view.draw(pygame.Surface((1024, 768)))
    texts = [text for text, _ in rendered]
    assert "SYSTEM MAP" in texts
    assert any("Current: Alpha" in text and "Destination: Delta" in text for text in texts)


def _spy_on_render_text(monkeypatch):
    """Record every string the map renders (same pattern as the Stage 6 HUD tests)."""
    import src.scenes.map_view as map_view_module

    rendered = []
    original = map_view_module.render_text

    def spy(text, size, color, bold=False):
        rendered.append((text, size))
        return original(text, size, color, bold)

    monkeypatch.setattr(map_view_module, "render_text", spy)
    return rendered


# ---------------------------------------------------------------------------
# MapView: events and picking
# ---------------------------------------------------------------------------


def test_handleEvent_escape_shouldPopTheModal():
    view, manager = _map_view(map_state(0))
    view.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))
    assert manager.pop_count == 1


def test_handleEvent_m_shouldAlsoCloseTheModal():
    """M is the documented toggle; closing with the same key is free UX."""
    view, manager = _map_view(map_state(0))
    view.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_m, mod=0))
    assert manager.pop_count == 1


def test_handleEvent_quit_shouldQuitTheGameNotJustTheModal():
    view, manager = _map_view(map_state(0))
    view.handle_event(pygame.event.Event(pygame.QUIT))
    assert manager.quit_count == 1
    assert manager.pop_count == 0


def test_handleEvent_leftClickOnANodePosition_shouldSelectThatSystem():
    state = map_state(0)
    view, manager = _map_view(state)
    x, y = state.layout.positions["Bravo"]
    view.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(int(x), int(y)), button=1))
    assert state.selected_system == "Bravo"
    assert manager.audio.confirm_count == 1, "a selection needs audible confirmation"


def test_handleEvent_leftClickTwiceOnTheSameNode_shouldToggleTheSelectionOff():
    state = map_state(0)
    view, _ = _map_view(state)
    x, y = state.layout.positions["Bravo"]
    for _ in range(2):
        view.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(int(x), int(y)), button=1))
    assert state.selected_system is None


def test_handleEvent_leftClickOnAnUnclickableSystem_shouldIgnoreItWithoutSound():
    """Revealed-but-not-adjacent and hidden systems are both inert."""
    state = map_state(0)
    state.arrive("Bravo")
    view, manager = _map_view(state)

    hidden = next(name for name in state.graph.names if not state.is_revealed(name))
    x, y = state.layout.positions[hidden]
    view.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(int(x), int(y)), button=1))

    sibling = next(name for name in state.revealed
                   if name not in state.graph.neighbours("Bravo") and name != "Bravo")
    x, y = state.layout.positions[sibling]
    view.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(int(x), int(y)), button=1))

    assert state.selected_system is None
    assert manager.audio.confirm_count == 0


def test_handleEvent_leftClickOnEmptySpace_shouldChangeNothing():
    state = map_state(0)
    state.handle_map_click("Charlie")
    view, _ = _map_view(state)
    view.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(4, 4), button=1))
    assert state.selected_system == "Charlie"


def test_handleEvent_rightClick_shouldDoNothing():
    state = map_state(0)
    view, _ = _map_view(state)
    x, y = state.layout.positions["Bravo"]
    view.handle_event(pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(int(x), int(y)), button=3))
    assert state.selected_system is None


def test_update_shouldDoNothingBecauseTheMapIsAStaticModal():
    view, _ = _map_view(map_state(0))
    assert view.update() is None


# ---------------------------------------------------------------------------
# Wiring through the real scene stack: M opens the map, exactly once per game
# ---------------------------------------------------------------------------


def _build_game(config_factory):
    """A real SceneManager + GameScene, ready for keyboard input (no dialog clicking).

    Cheaper than clicking through the title screen for every map test, and the
    difficulty dialog's own wiring is covered by the Stage 2 flow tests.
    """
    from src.audio import AudioSystem
    from src.main_loop import FixedTimestepLoop
    from src.scene_manager import SceneManager
    from src.scenes.game_scene import GameScene

    configs = load_config(config_factory())
    screen = pygame.display.get_surface()
    manager = SceneManager(screen=screen, configs=configs, audio=AudioSystem())
    manager.selected_config = configs["config_medium.json"]
    game = GameScene(manager)
    manager.push(game)
    loop = FixedTimestepLoop(scene_manager=manager, screen=screen)
    return manager, game, loop


def _press_key(loop, key):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, scancode=0, mod=0))
    assert loop.step_once(), "the loop stopped unexpectedly"
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=key, scancode=0, mod=0))
    assert loop.step_once(), "the loop stopped unexpectedly"


def test_pressingM_throughTheRealLoop_shouldRaiseTheMapModal(config_factory):
    """The whole chain: binding -> action -> scene -> modal on the stack."""
    manager, game, loop = _build_game(config_factory)
    _press_key(loop, pygame.K_m)
    assert isinstance(manager._stack[-1], MapView), "M must open the system map"
    assert manager._stack[-1].state is game.system_map, "the modal shows the session's map state"


def test_pressingEscapeOnTheMap_shouldReturnToTacticalPlay(config_factory):
    manager, _game, loop = _build_game(config_factory)
    _press_key(loop, pygame.K_m)
    _press_key(loop, pygame.K_ESCAPE)
    assert len(manager._stack) == 1, "the modal must be popped, not merely hidden"


def test_pressingMWhileAJumpIsAnimating_shouldNotOpenTheMap(config_factory):
    """Spec: the map is blocked during a jump.

    ``begin_jump`` now takes the burn acceleration: the jump mechanism (uncapped
    thrust, boundary exemption) is model state, while the *sequence* lives in
    ``src.model.jump`` and is driven by GameScene. Stage 8's own tests drive the
    real sequence; this one only needs the gate, so it sets the flag directly.
    """
    manager, game, loop = _build_game(config_factory)
    game.game_state.begin_jump(1.2)
    _press_key(loop, pygame.K_m)
    assert len(manager._stack) == 1, "the map may not open mid-jump"
    game.game_state.end_jump()
    _press_key(loop, pygame.K_m)
    assert isinstance(manager._stack[-1], MapView), "and it must open again once the jump ends"


def test_openingAndClosingTheMap_shouldNeverRegenerateTheWorld(config_factory, monkeypatch):
    """Graph + layout are computed once per game, not once per modal open.

    Re-layouting on every press would move systems around between visits, which
    makes the map unusable as a chart and the world unrepeatable.
    """
    import src.scenes.game_scene as game_scene_module

    calls = []
    original = game_scene_module.build_map_layout

    def counting_build(*args, **kwargs):
        calls.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(game_scene_module, "build_map_layout", counting_build)

    manager, game, loop = _build_game(config_factory)
    layout_at_start = game.system_map.layout
    positions_at_start = dict(layout_at_start.positions)

    for _ in range(3):
        _press_key(loop, pygame.K_m)
        _press_key(loop, pygame.K_ESCAPE)

    assert len(calls) == 1, "the layout must be built exactly once per game"
    assert game.system_map.layout.positions == positions_at_start


def test_simulationStaysFrozenWhileTheMapIsOpen(config_factory):
    """Only the top scene updates: the tactical sim must not run underneath."""
    manager, game, loop = _build_game(config_factory)
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP, scancode=0, mod=0))
    loop.step_once()
    _press_key(loop, pygame.K_m)
    assert isinstance(manager._stack[-1], MapView)

    position_at_open = game.game_state.position
    fuel_at_open = game.game_state.fuel
    for _ in range(30):
        assert loop.step_once(), "the loop stopped unexpectedly"

    assert game.game_state.position == position_at_open, "the ship moved while the map was open"
    assert game.game_state.fuel == fuel_at_open, "fuel burned while the map was open"
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=pygame.K_UP, scancode=0, mod=0))
    loop.step_once()


def test_selectingADestinationOnTheMap_shouldReachTheHudNavLine(config_factory, monkeypatch):
    """Closes the Stage 6 seam: HudView.nav_selected_name is fed by the map."""
    import src.hud as hud_module

    rendered = []
    original = hud_module.render_text

    def spy(text, size, color, bold=False):
        rendered.append(text)
        return original(text, size, color, bold)

    monkeypatch.setattr(hud_module, "render_text", spy)

    manager, game, loop = _build_game(config_factory)
    game.draw(pygame.display.get_surface())
    assert "No destination" in rendered, "the nav line starts empty"

    _press_key(loop, pygame.K_m)
    x, y = game.system_map.layout.positions["Bravo"]
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, pos=(int(x), int(y)), button=1, buttons=(1, 1, 1)))
    loop.step_once()
    assert game.system_map.selected_system == "Bravo"

    _press_key(loop, pygame.K_ESCAPE)
    rendered.clear()
    game.draw(pygame.display.get_surface())
    assert "Hyperspace / Bravo" in rendered, "the chosen destination never reached the HUD"


def test_mapViewConstructor_withoutAState_shouldRaiseValueError():
    """The first revision's signature took a *scene* where it documented a manager."""
    with pytest.raises(ValueError):
        MapView(None)
