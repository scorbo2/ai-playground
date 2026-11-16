"""Pure geometry for drawing the system map: node placement, label boxes, picking.

Layout is computed **once per game** (see :mod:`src.map_systems.system_map`) and
cached. Recomputing it per frame would make the whole map jitter, and computing
it per modal-open would make "the layout is stable for the whole run" untestable.

Everything here is pygame-free: label metrics arrive through a ``measure``
callable, so the same functions the renderer executes can be unit-tested with a
fake font. The first revision instead measured the string ``"ZZZZZ"`` as a proxy
for the longest label - 60 px at 20 pt, while the label it was sizing for
("November") is 96 px - which is how it confidently shipped a map whose labels
sat on top of each other.

Node placement is one ring, ordered by a depth-first walk from the root, so each
subtree occupies a contiguous arc: on a graph whose degree ceiling is 3 that
turns an alphabetical ring (a tangle of crossing edges) into something a player
can actually trace.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

from src.map_systems.graph import ROOT_SYSTEM, SystemGraph

# A label metric measure: (text, font_size) -> (width, height) in pixels.
LabelMeasure = Callable[[str, int], "tuple[int, int]"]

# Screen geometry lives in code, like the window size and the HUD palette.
SCREEN_MARGIN = 10   # breathing room between the outermost label box and the window edge
HEADER_BAND = 72     # reserved strip at the top of the window for map copy
NODE_RADIUS = 12.0   # "white circles" radius in px
LABEL_GAP = 6.0      # clearance between a label box and anything beside it
HIT_RADIUS_FRACTION = 0.45  # fraction of the node-to-node gap that counts as a click
LABEL_FONT_SIZES = (20, 18, 16, 14, 12, 10)  # tried largest-first
MIN_NODE_RING_RADIUS = 80.0  # below this the "map" is a blob of overlapping nodes

Box = tuple[float, float, float, float]  # left, top, right, bottom
Point = tuple[float, float]


def boxes_overlap(a: Box, b: Box) -> bool:
    """True when two axis-aligned boxes (left, top, right, bottom) overlap.

    Boxes that merely touch at an edge do not count as overlapping: a label
    sitting exactly against a node circle is fine.
    """
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


def point_in_box(point: Point, box: Box) -> bool:
    """True when ``point`` falls inside (or exactly on the edge of) ``box``."""
    return box[0] <= point[0] <= box[2] and box[1] <= point[1] <= box[3]


def circle_overlaps_box(center: Point, radius: float, box: Box) -> bool:
    """True when a circle intersects an axis-aligned box.

    Nodes are drawn as *circles*, so testing them with a bounding square is both
    wrong and unaffordable: a 64x16 label one gap away from a 24px circle at 45
    degrees around the ring overlaps the circle's bounding box while clearing the
    circle itself comfortably. Demanding box-vs-box clearance there would push the
    label ring off the screen.
    """
    nearest_x = min(max(center[0], box[0]), box[2])
    nearest_y = min(max(center[1], box[1]), box[3])
    return (nearest_x - center[0]) ** 2 + (nearest_y - center[1]) ** 2 <= radius ** 2


def circles_clear(first: Point, second: Point, radius: float) -> bool:
    """True when two equal circles of ``radius`` do not overlap."""
    return (first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2 >= (2.0 * radius) ** 2


def box_around(center: Point, width: float, height: float) -> Box:
    """The (left, top, right, bottom) box of ``width`` x ``height`` centred on ``center``."""
    left = center[0] - width / 2.0
    top = center[1] - height / 2.0
    return (left, top, left + width, top + height)


def circular_positions(
    names: Sequence[str],
    center: Point = (0.0, 0.0),
    radius: float = 1.0,
) -> dict[str, Point]:
    """Place ``names`` evenly on a circle of the given ``radius``.

    Name ``i`` sits at angle ``2*pi*i/len(names) - pi/2``: starting at the top
    and proceeding clockwise. The result is centred on ``center``. Nearest
    neighbour separation grows with ``radius``; choose it large enough that each
    label's bounding box clears its neighbours (see :func:`build_map_layout`).
    """
    count = len(names)
    positions: dict[str, Point] = {}
    for index, name in enumerate(names):
        positions[name] = point_at_angle(center, radius, angle_for_index(index, count))
    return positions


def graph_circular_order(graph: SystemGraph, root: str) -> tuple[str, ...]:
    """Depth-first preorder of ``graph`` from ``root``: the ring placement order.

    Placing a system's subtree in one contiguous arc keeps most edges short and
    nested. Measured on a 26-system tree, an alphabetical ring produces ~70
    crossing edge pairs; this ordering cuts that by roughly two thirds while
    leaving the placement math (evenly spaced points on one circle) identical.
    """
    order: list[str] = []
    visited: set[str] = set()
    stack: list[str] = [root]
    while stack:
        name = stack.pop()
        if name in visited:
            continue
        visited.add(name)
        order.append(name)
        # Reverse index order so the stack pops neighbours in NATO order.
        for neighbour in sorted(graph.neighbours(name), key=graph.names.index, reverse=True):
            if neighbour not in visited:
                stack.append(neighbour)
    # Defensive: an unexpected island still gets placed rather than dropped.
    order.extend(name for name in graph.names if name not in visited)
    return tuple(order)


@dataclass(frozen=True)
class MapLayout:
    """Screen geometry for every system on the map, plus exact hit/label boxes.

    Frozen so a view cannot quietly mutate the layout it was handed, and
    self-inspecting (:meth:`overlapping_pairs`, :meth:`fits_on_screen`) so the
    "node + label must not overlap" gate is a property of the layout itself
    rather than of a screenshot.
    """

    center: Point
    radius: float
    node_radius: float
    hit_radius: float
    label_font_size: int
    header_band: int = HEADER_BAND
    root: str = ROOT_SYSTEM
    placement_order: tuple[str, ...] = ()
    positions: dict[str, Point] = field(default_factory=dict)
    label_anchors: dict[str, Point] = field(default_factory=dict)
    label_sizes: dict[str, "tuple[int, int]"] = field(default_factory=dict)
    label_boxes: dict[str, Box] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Derive each label's box from its anchor + measured size so the renderer
        # and the hit test agree on exactly one rectangle per label.
        if not self.label_boxes:
            object.__setattr__(self, "label_boxes", {
                name: box_around(anchor, *self.label_sizes[name])
                for name, anchor in self.label_anchors.items()
            })

    # ------------------------------------------------------------------
    # Boxes
    # ------------------------------------------------------------------
    def node_box(self, name: str) -> Box:
        """The square bounding box of a system's node circle."""
        return box_around(self.positions[name], 2 * self.node_radius, 2 * self.node_radius)

    def node_at(self, pos: Point, candidates: Iterable[str]) -> str | None:
        """The candidate system a click refers to, or ``None`` for empty space.

        A click counts when it lands inside a node's hit circle *or* inside that
        node's label box, so players can click the name as easily as the dot.
        Only ``candidates`` (the visible systems) are considered, which keeps
        fog of war out of the renderer: an unrevealed system cannot be clicked
        even though its slot is known. Nearest match wins when regions overlap.
        """
        best_name: str | None = None
        best_distance = float("inf")
        for name in candidates:
            label_box = self.label_boxes.get(name)
            if label_box is not None and point_in_box(pos, label_box):
                return name  # clicking the name is as good as clicking the dot
            x, y = self.positions[name]
            distance = (x - pos[0]) ** 2 + (y - pos[1]) ** 2
            if distance <= self.hit_radius ** 2 and distance < best_distance:
                best_distance = distance
                best_name = name
        return best_name

    # ------------------------------------------------------------------
    # Self-inspection (used by the Stage 7 gate tests)
    # ------------------------------------------------------------------
    def overlapping_pairs(self) -> list[tuple[str, str, str]]:
        """Every colliding pair as ``(kind, a, b)``; empty means a clean map.

        Three kinds are checked, each with the geometry that matches how the
        thing is actually drawn: label/label (box vs box), node/node (circle vs
        circle) and label/node (box vs circle). A label over **its own** node is
        reported as ``label/own-node`` - white text on a white circle is not a
        cosmetic quibble, it is why the first revision's map read "Alha",
        "Br vo" and "Nov ber".
        """
        names = list(self.positions)
        offenders: list[tuple[str, str, str]] = []
        for name in names:
            label = self.label_boxes.get(name)
            if label is not None and circle_overlaps_box(
                self.positions[name], self.node_radius, label
            ):
                offenders.append(("label/own-node", name, name))
        for index, first in enumerate(names):
            for second in names[index + 1:]:
                label_first = self.label_boxes.get(first)
                label_second = self.label_boxes.get(second)
                if label_first and label_second and boxes_overlap(label_first, label_second):
                    offenders.append(("label/label", first, second))
                if not circles_clear(self.positions[first], self.positions[second], self.node_radius):
                    offenders.append(("node/node", first, second))
                if label_first and circle_overlaps_box(
                    self.positions[second], self.node_radius, label_first
                ):
                    offenders.append(("label/node", first, second))
                if label_second and circle_overlaps_box(
                    self.positions[first], self.node_radius, label_second
                ):
                    offenders.append(("label/node", second, first))
        return offenders

    def fits_on_screen(self, screen_size: "tuple[int, int]") -> bool:
        """True when every node box and label box clears the window *and* header band.

        The header band is part of the contract, not a courtesy: if the ring may
        creep into it, the modal's own copy collides with system labels and no
        per-stage test would notice until a human squinted at a screenshot.
        """
        width, height = screen_size
        for name in self.positions:
            for box in (self.node_box(name), self.label_boxes.get(name)):
                if box is None:
                    continue
                if box[0] < 0 or box[1] < self.header_band or box[2] > width or box[3] > height:
                    return False
        return True




class MapLayoutError(ValueError):
    """No font size in :data:`LABEL_FONT_SIZES` places every label cleanly."""


def angle_for_index(index: int, count: int) -> float:
    """The ring angle of placement slot ``index``: top of the circle, clockwise."""
    return (2.0 * math.pi * index / count) - math.pi / 2.0


def point_at_angle(center: Point, radius: float, angle: float) -> Point:
    """The point at ``angle`` on a circle of ``radius`` centred on ``center``."""
    return (center[0] + radius * math.cos(angle), center[1] + radius * math.sin(angle))


def label_offset_for_angle(width: float, height: float, clearance: float, angle: float) -> float:
    """How far a ``width`` x ``height`` label box must sit from its node, radially.

    "One label half-height plus a gap" is the intuitive answer and it is wrong
    except at the very top and bottom of the ring: a 64x14 label at the 3 o'clock
    position extends 32 px *towards* its own node, so a node 18 px away is buried
    inside the label's bounding box. This solves for the true radial offset by
    bisecting on the distance from the node centre to the box, so every label
    clears its own circle by ``clearance`` whatever its angle.
    """
    half_w, half_h = width / 2.0, height / 2.0
    cos_component, sin_component = abs(math.cos(angle)), abs(math.sin(angle))

    def gap_at(distance: float) -> float:
        """Distance from a node ``distance`` away along ``angle`` to the label box."""
        outside_x = max(0.0, distance * cos_component - half_w)
        outside_y = max(0.0, distance * sin_component - half_h)
        return math.hypot(outside_x, outside_y)

    # `high` puts the node outside the box on both axes, so it always clears.
    low, high = 0.0, half_w + half_h + clearance + 1.0
    for _ in range(48):
        middle = (low + high) / 2.0
        if gap_at(middle) >= clearance:
            high = middle
        else:
            low = middle
    return high


def build_map_layout(
    graph: SystemGraph,
    screen_size: "tuple[int, int]",
    measure: LabelMeasure,
    root: str | None = None,
    node_radius: float = NODE_RADIUS,
) -> MapLayout:
    """Compute the whole map's screen geometry once, proving it fits as we go.

    ``measure`` supplies font metrics (the view passes ``game_font(size).size``),
    which keeps this module free of pygame and the result unit-testable.

    Every size in :data:`LABEL_FONT_SIZES` is tried largest-first, and a size is
    accepted only when the resulting layout *verifiably* has no overlapping
    pairs and stays inside the window below :data:`HEADER_BAND`. That is a
    deliberate change from the first revision, which scaled the node ring down
    until a "should fit" estimate looked plausible and thereby destroyed the
    clearance the estimate existed to guarantee - the labels then measured 96 px
    wide against an 82 px slot, and the map read "Alha", "Br vo", "Nov ber".

    Labels are anchored radially *outside* their node, each at its own offset:
    the offset a 3 o'clock label needs is more than double the offset a 12
    o'clock label needs, so a single shared offset cannot be correct for both.
    """
    names = graph_circular_order(graph, root or graph.names[0])
    if len(names) < 2:
        raise ValueError("a system map needs at least two systems to place")

    for size in LABEL_FONT_SIZES:
        layout = _layout_for_size(names, screen_size, size, measure, node_radius)
        if layout is None:
            continue
        if layout.overlapping_pairs() or not layout.fits_on_screen(screen_size):
            continue
        return layout

    raise MapLayoutError(
        f"cannot place {len(names)} system labels inside {screen_size} without "
        f"overlap (tried font sizes {LABEL_FONT_SIZES})"
    )


def _layout_for_size(
    names: Sequence[str],
    screen_size: "tuple[int, int]",
    font_size: int,
    measure: LabelMeasure,
    node_radius: float,
) -> MapLayout | None:
    """Lay the ring out at one font size, or ``None`` if it cannot fit the window.

    The radius is chosen as large as the window allows *after* the label offsets
    are known, because each label hangs outside the ring and the deepest one
    decides how much room is left.
    """
    count = len(names)
    playfield_height = screen_size[1] - HEADER_BAND
    if count < 2 or playfield_height <= 0:
        return None

    center: Point = (screen_size[0] / 2.0, HEADER_BAND + playfield_height / 2.0)
    angles = {name: angle_for_index(index, count) for index, name in enumerate(names)}
    label_sizes = {name: measure(name, font_size) for name in names}
    offsets = {
        name: label_offset_for_angle(
            label_sizes[name][0], label_sizes[name][1], node_radius + LABEL_GAP, angles[name]
        )
        for name in names
    }

    deepest_down = max(offsets[name] + label_sizes[name][1] / 2.0 for name in names)
    widest_across = max(offsets[name] + label_sizes[name][0] / 2.0 for name in names)
    radius = min(playfield_height / 2.0 - deepest_down, screen_size[0] / 2.0 - widest_across)
    radius -= SCREEN_MARGIN
    if radius < MIN_NODE_RING_RADIUS:
        return None
    if not _labels_clear_adjacent_slots(label_sizes, radius, offsets, count):
        return None

    return MapLayout(
        center=center,
        radius=radius,
        node_radius=node_radius,
        hit_radius=_hit_radius(count, radius),
        label_font_size=font_size,
        header_band=HEADER_BAND,
        root=names[0],
        placement_order=tuple(names),
        positions={name: point_at_angle(center, radius, angles[name]) for name in names},
        label_anchors={
            name: point_at_angle(center, radius + offsets[name], angles[name]) for name in names
        },
        label_sizes=label_sizes,
    )


def _hit_radius(count: int, radius: float) -> float:
    """A click radius that cannot reach past the midpoint to a neighbouring node."""
    gap = 2.0 * radius * math.sin(math.pi / max(2, count))
    return max(NODE_RADIUS + 2.0, gap * HIT_RADIUS_FRACTION)


def _labels_clear_adjacent_slots(
    label_sizes: dict[str, "tuple[int, int]"],
    radius: float,
    offsets: dict[str, float],
    count: int,
) -> bool:
    """Would the two widest labels clear each other in *adjacent* ring slots?

    Checking only the placement we happen to have built is not a guarantee: the
    DFS ordering changes with the world seed, so a "verify the layout we built"
    rule happily accepted 20 pt labels for some seeds and 14 pt for others - the
    map's typography would then vary from game to game. This bounds the worst
    case instead: at the top and bottom of the ring, neighbouring slots are
    separated *horizontally*, which is the axis labels are wide along, so the two
    widest names must fit side by side there whatever the world generator did.
    """
    widest = sorted((width for width, _ in label_sizes.values()), reverse=True)[:2]
    if len(widest) < 2:
        return True
    needed = widest[0] / 2.0 + widest[1] / 2.0 + LABEL_GAP
    # The tightest label-to-label gap is on the smallest label ring, i.e. where
    # the radial offset is smallest (top and bottom of the node ring).
    tightest_label_ring = radius + min(offsets.values())
    available = 2.0 * tightest_label_ring * math.sin(math.pi / max(2, count))
    return needed <= available
