"""The world graph: 26 NATO-named solar systems and their connections.

A :class:`SystemGraph` is an immutable snapshot of the topology: which systems
exist and which are directly connected to one another. It is produced once per
new game by :class:`SystemGraphGenerator` and cached for the rest of the run.

Construction rules (all enforced by :meth:`SystemGraph.validate` against an
explicit :class:`GraphConstraints` value object, so the checks mirror the
config rather than hard-coding the spec's numbers):

* There are exactly ``system_count`` systems, taken from the front of
  :data:`NATO_SYSTEMS`. Index 0 is always the root, "Alpha".
* Every system's degree (number of connections) lies in
  ``[connections_min, connections_max]``.
* The root has *exactly* ``alpha_connections`` neighbours - Bravo, Charlie and
  Delta by default - and can therefore never gain further edges.
* The graph is fully connected: no unreachable "island" systems.

Determinism note, because it bit the first revision: every random choice here
is taken from a **list built in :data:`NATO_SYSTEMS` order**, never from set or
dict iteration order. Python randomises string hashing per process, so drawing
candidates out of a ``set`` silently wove ``PYTHONHASHSEED`` into the topology
and the same seed produced a different graph on every run.
"""

from __future__ import annotations

import random as _random
from collections import deque
from dataclasses import dataclass, field

# The NATO phonetic alphabet (26 entries). Spelling follows the NATO table:
# "Juliett" (two t's) is the official NATO form, "Xray" is written as one word,
# and the code point for K is "Kilo" - not the Antipodean "kiwi" that showed up
# in the first draft of this module. Index 0 is Alpha, the system the player
# always starts in and the anchor the graph is built around.
NATO_SYSTEMS: tuple[str, ...] = (
    "Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Golf",
    "Hotel", "India", "Juliett", "Kilo", "Lima", "Mike", "November",
    "Oscar", "Papa", "Quebec", "Romeo", "Sierra", "Tango", "Uniform",
    "Victor", "Whiskey", "Xray", "Yankee", "Zulu",
)

# The root system and the neighbours it is guaranteed to connect to. These are
# also its only connections, pinning its degree at exactly len(...).
ROOT_SYSTEM: str = "Alpha"
ROOT_GUARANTEED_NEIGHBOURS: tuple[str, ...] = ("Bravo", "Charlie", "Delta")


class GraphGenerationError(ValueError):
    """Raised when the requested topology constraints cannot be satisfied.

    Surfaces a bad ``map`` config section as a readable message instead of an
    IndexError or an infinite loop deep inside the generator.
    """


@dataclass(frozen=True)
class GraphConstraints:
    """The topology a generated graph must satisfy.

    A value object rather than loose constructor arguments so the generator and
    :meth:`SystemGraph.validate` are held to exactly the same contract, and so
    property tests can assert the *same* constraints they generated against.
    """

    system_count: int
    min_degree: int
    max_degree: int
    root: str = ROOT_SYSTEM
    root_neighbours: tuple[str, ...] = ROOT_GUARANTEED_NEIGHBOURS

    @classmethod
    def from_config(cls, map_config: dict) -> "GraphConstraints":
        """Build constraints from the validated ``map`` config section.

        Config keys live here (one place) rather than being spread across the
        scene that happens to need a graph.
        """
        try:
            constraints = cls(
                system_count=int(map_config["system_count"]),
                min_degree=int(map_config["connections_min"]),
                max_degree=int(map_config["connections_max"]),
                root_neighbours=tuple(map_config["alpha_connections"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GraphGenerationError(f"invalid map config section: {exc}") from exc
        constraints.check()
        return constraints

    def check(self) -> None:
        """Reject constraints no graph could possibly satisfy, before generating."""
        names = NATO_SYSTEMS[: self.system_count]
        if self.system_count < 2 or self.system_count > len(NATO_SYSTEMS):
            raise GraphGenerationError(
                f"map.system_count must be in [2, {len(NATO_SYSTEMS)}], "
                f"got {self.system_count}"
            )
        if not 1 <= self.min_degree <= self.max_degree:
            raise GraphGenerationError(
                f"need 1 <= connections_min <= connections_max, got "
                f"{self.min_degree}/{self.max_degree}"
            )
        if self.max_degree >= self.system_count:
            raise GraphGenerationError(
                f"connections_max ({self.max_degree}) must be below system_count "
                f"({self.system_count}): a system cannot connect to itself"
            )
        if len(set(self.root_neighbours)) != len(self.root_neighbours):
            raise GraphGenerationError(
                f"map.alpha_connections contains duplicates: {self.root_neighbours}"
            )
        if self.root not in names:
            raise GraphGenerationError(
                f"root system {self.root!r} is not among the first "
                f"{self.system_count} NATO names"
            )
        if len(self.root_neighbours) > self.max_degree:
            raise GraphGenerationError(
                f"alpha_connections lists {len(self.root_neighbours)} systems, "
                f"more than connections_max ({self.max_degree}) allows"
            )
        for neighbour in self.root_neighbours:
            if neighbour not in names:
                raise GraphGenerationError(
                    f"alpha_connections entry {neighbour!r} is not one of the "
                    f"{self.system_count} systems in play"
                )


@dataclass(frozen=True)
class SystemGraph:
    """An immutable world-graph topology."""

    names: tuple[str, ...]
    adjacency: dict[str, frozenset[str]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalise stored adjacency into frozensets for cheap membership tests.
        object.__setattr__(self, "adjacency", {
            name: frozenset(neighbours) for name, neighbours in self.adjacency.items()
        })

    def names_tuple(self) -> tuple[str, ...]:
        """Copy of the system-name list, index 0 == the root system."""
        return self.names

    def neighbour_count(self, name: str) -> int:
        """Number of systems directly connected to ``name`` (its degree)."""
        return len(self.adjacency.get(name, frozenset()))

    def neighbours(self, name: str) -> frozenset[str]:
        """The set of systems directly connected to ``name``."""
        return self.adjacency.get(name, frozenset())

    def edges(self) -> tuple[tuple[str, str], ...]:
        """Every undirected edge exactly once, ordered by name pair."""
        return tuple(
            (a, b)
            for a in self.names
            for b in sorted(self.adjacency.get(a, frozenset()))
            if a < b
        )

    def is_connected(self) -> bool:
        """True when every system can be reached from the first system."""
        if not self.names:
            return True
        start = self.names[0]
        seen: set[str] = {start}
        queue: deque[str] = deque([start])
        while queue:
            current = queue.popleft()
            for neighbour in sorted(self.adjacency.get(current, frozenset())):
                if neighbour not in seen:
                    seen.add(neighbour)
                    queue.append(neighbour)
        return len(seen) == len(self.names)

    def validate(self, constraints: GraphConstraints) -> None:
        """Assert every structural invariant holds; raise on violation.

        Bounds come from ``constraints`` rather than spec constants, so changing
        ``map.connections_max`` in config changes the contract too instead of
        making the generator and the checker disagree. Both the generator and
        the property tests funnel through this one place.
        """
        expected_names = NATO_SYSTEMS[: constraints.system_count]
        if self.names != expected_names:
            raise GraphGenerationError(
                f"expected systems {expected_names[:3]}...({constraints.system_count}), "
                f"got {self.names}"
            )
        if self.names[0] != constraints.root:
            raise GraphGenerationError(f"first system must be {constraints.root}")

        expected_root_edges = frozenset(constraints.root_neighbours)
        root_edges = self.neighbours(constraints.root)
        if root_edges != expected_root_edges:
            raise GraphGenerationError(
                f"{constraints.root}'s only connections must be {sorted(expected_root_edges)}, "
                f"got {sorted(root_edges)}"
            )

        for name in self.names:
            degree = self.neighbour_count(name)
            if degree < constraints.min_degree or degree > constraints.max_degree:
                raise GraphGenerationError(
                    f"system {name!r} has degree {degree}, outside "
                    f"[{constraints.min_degree}, {constraints.max_degree}]"
                )

        if not self.is_connected():
            raise GraphGenerationError("the graph must be fully connected (no island nodes)")


class SystemGraphGenerator:
    """Builds a valid :class:`SystemGraph` from :class:`GraphConstraints` + an RNG.

    The construction is correct by design rather than by luck:

    * The root's guaranteed edges are placed first, filling its capacity so it
      can never receive another edge.
    * Every remaining system is attached to the growing component by an edge to
      an already-attached node that still has spare capacity. Each newly
      attached node arrives with ``max_degree - 1`` spare slots, so the
      component's total spare capacity grows by one per step and can never run
      dry - the loop always finds a valid attachment point and never exceeds
      the degree ceiling.
    * Attaching every unattached system yields one connected component.
    * Finally, any node still below ``min_degree`` gains an extra edge to a
      node it is not already connected to. Only reachable while capacity
      remains; when it is not, the constraints are unsatisfiable and
      :class:`GraphGenerationError` is raised rather than the loop stalling.

    With the shipped configs (``connections_min == 1``) the third phase is a
    no-op, so a 26-system world has exactly 25 edges: a spanning tree with no
    route redundancy. See DECISIONS.md (Stage 7).
    """

    def __init__(self, constraints: GraphConstraints, rng: "_random.Random | None" = None) -> None:
        constraints.check()
        self.constraints = constraints
        self.rng = rng if rng is not None else _random.Random()

    @classmethod
    def from_config(cls, map_config: dict, rng: "_random.Random | None" = None) -> "SystemGraphGenerator":
        """Convenience constructor: config section -> constraints -> generator."""
        return cls(GraphConstraints.from_config(map_config), rng=rng)

    def generate(self) -> SystemGraph:
        """Generate one valid graph, validating the result before returning."""
        constraints = self.constraints
        graph = SystemGraph(
            names=NATO_SYSTEMS[: constraints.system_count],
            adjacency=self._build(NATO_SYSTEMS[: constraints.system_count]),
        )
        graph.validate(constraints)  # defensive: catches a regressed construction
        return graph

    # ------------------------------------------------------------------
    def _build(self, names: tuple[str, ...]) -> dict[str, set[str]]:
        max_degree = self.constraints.max_degree
        adjacency: dict[str, set[str]] = {name: set() for name in names}
        # Remaining capacity per node; the root's drops to zero once its
        # guaranteed edges are placed, so it can never receive more.
        capacity: dict[str, int] = {name: max_degree for name in names}

        def add_edge(u: str, v: str) -> bool:
            if u == v or v in adjacency[u]:
                return False
            if capacity[u] <= 0 or capacity[v] <= 0:
                return False
            adjacency[u].add(v)
            adjacency[v].add(u)
            capacity[u] -= 1
            capacity[v] -= 1
            return True

        root = self.constraints.root
        attached: set[str] = {root} | set(self.constraints.root_neighbours)

        # Phase 1: the root's guaranteed connections pin its degree exactly.
        for neighbour in self.constraints.root_neighbours:
            add_edge(root, neighbour)

        # Phase 2: grow a spanning tree over the remaining systems. Candidate
        # lists are built in `names` order (never set order) so an RNG draw here
        # depends only on the seed - see the module docstring.
        for target in [name for name in names if name not in attached]:
            sources = [source for source in names if source in attached and capacity[source] > 0]
            if not sources:
                raise GraphGenerationError(
                    f"cannot attach system {target!r}: every connected system is at "
                    f"its degree ceiling ({max_degree})"
                )
            source = self.rng.choice(sources)
            add_edge(source, target)
            attached.add(target)

        # Phase 3: lift under-connected nodes to connections_min. This is what
        # makes connections_min a real knob instead of a decorative key, and it
        # is the only phase that can introduce cycles.
        self._raise_degrees_to_minimum(names, adjacency, capacity, add_edge)

        return adjacency

    def _raise_degrees_to_minimum(
        self,
        names: tuple[str, ...],
        adjacency: dict[str, set[str]],
        capacity: dict[str, int],
        add_edge,
    ) -> None:
        minimum = self.constraints.min_degree
        while True:
            deficient = [name for name in names if len(adjacency[name]) < minimum]
            if not deficient:
                return
            # Most deficient first, and partners that are themselves deficient
            # first, so the pass converges instead of exhausting capacity early.
            deficient.sort(key=lambda name: (len(adjacency[name]), name))
            progress = False
            for node in deficient:
                if len(adjacency[node]) >= minimum:
                    continue
                partners = [
                    other
                    for other in names
                    if other != node and capacity[other] > 0 and other not in adjacency[node]
                ]
                if not partners:
                    continue
                partners.sort(key=lambda other: (len(adjacency[other]), other))
                # Draw from the sorted candidate list: deterministic per seed.
                if add_edge(node, self.rng.choice(partners)):
                    progress = True
            if not progress:
                raise GraphGenerationError(
                    f"connections_min={minimum} cannot be satisfied with "
                    f"connections_max={self.constraints.max_degree} across "
                    f"{self.constraints.system_count} systems"
                )
