"""Runtime state for the system map: layout, visibility, current/selected system.

:class:`SystemMapState` is the single owner of everything the map screen shows.
The immutable topology comes from :class:`~src.map_systems.graph.SystemGraph`,
the once-per-game screen geometry from :class:`~src.map_systems.layout.MapLayout`,
and the mutable part (fog of war, current system, selection) lives here.

That split is deliberate. The first Stage 7 revision asked the *view* for the
node ring, then re-derived visibility inside a nested loop over all 26 systems
while drawing - and promptly drew all 26 node circles whether revealed or not,
handing the player the whole map on turn one. The view now asks this object what
is visible and draws exactly what it is told.

Rules enforced here (all pure logic, no pygame):

* A system may be selected only if it is revealed **and** directly connected to
  the current system. The current system is never selectable - the player is
  already there. Clicking an already-selected system toggles it back off.
* Arriving in a system reveals it and all of its connections permanently. At
  game start only the root plus its guaranteed neighbours are revealed.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from src.map_systems.graph import SystemGraph
from src.map_systems.layout import MapLayout, graph_circular_order

# Outcomes of a map click, so the view can react (sound, repaint) without
# re-implementing any of the selection rules.
SELECTED = "selected"
DESELECTED = "deselected"
IGNORED = "ignored"


@dataclass
class SystemMapState:
    """Mutable runtime state layered over an immutable world graph + layout."""

    graph: SystemGraph
    layout: MapLayout
    current_system: str = "Alpha"
    selected_system: str | None = None
    revealed: set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.current_system not in self.graph.names:
            raise ValueError(f"unknown current system {self.current_system!r}")
        if tuple(self.layout.placement_order) != graph_circular_order(self.graph, self.layout.root):
            # A layout carried over from a different world would put real system
            # names at the wrong coordinates: every click would select the wrong
            # star system, and nothing would look wrong on screen.
            raise ValueError(
                "MapLayout does not belong to this graph: the systems match but the "
                "placement order does not"
            )
        # No revealed set supplied: derive it from the starting position, i.e.
        # the current system plus the systems one jump away.
        if not self.revealed:
            self.reveal_on_arrival(self.current_system)

    # ------------------------------------------------------------------
    # What the map may draw
    # ------------------------------------------------------------------
    def visible_nodes(self) -> tuple[str, ...]:
        """Revealed systems, in the layout's ring order (stable draw order)."""
        return tuple(name for name in self.layout.positions if name in self.revealed)

    def visible_edges(self) -> tuple[tuple[str, str], ...]:
        """Edges whose *both* endpoints are revealed - never a stub into the dark.

        An edge to an unrevealed system would leak topology the player has not
        earned, which is exactly what fog of war is for.
        """
        return tuple(
            (first, second)
            for first, second in self.graph.edges()
            if first in self.revealed and second in self.revealed
        )

    def is_revealed(self, name: str) -> bool:
        return name in self.revealed

    # ------------------------------------------------------------------
    # Selection rules
    # ------------------------------------------------------------------
    def can_select(self, name: str | None) -> bool:
        """Whether ``name`` is a legal selection target.

        Not the current system, revealed, and directly connected to the current
        system. Systems revealed earlier (a sibling of the current one, for
        instance) stay visible but become unselectable once they are no longer
        adjacent to the player.
        """
        if name is None or name == self.current_system:
            return False
        if name not in self.revealed:
            return False
        return name in self.graph.neighbours(self.current_system)

    def select(self, name: str) -> None:
        """Select ``name``; raise if it is not a legal selection target."""
        if not self.can_select(name):
            raise ValueError(
                f"cannot select system {name!r}: not revealed or not connected to "
                f"current system {self.current_system!r}"
            )
        self.selected_system = name

    def deselect(self) -> None:
        """Clear the selection, leaving no system selected."""
        self.selected_system = None

    @property
    def has_selection(self) -> bool:
        return self.selected_system is not None

    def handle_map_click(self, name: str | None) -> str:
        """Apply the click rules to ``name`` and report what happened.

        Toggle-off is tested **before** selectability: an already-selected system
        is still a perfectly legal selection target (it is a neighbour), so
        checking selectability first re-selects it on the second click and the
        spec's toggle-off becomes unreachable - which is exactly how the first
        version of this method behaved, and no helper test noticed because each
        rule passed in isolation.

        Ignores everything else: empty space, unrevealed systems, and systems
        that are revealed but no longer adjacent to the current one.
        """
        if name is None:
            return IGNORED
        if self.selected_system == name:
            self.deselect()
            return DESELECTED
        if self.can_select(name):
            self.select(name)
            return SELECTED
        return IGNORED

    # ------------------------------------------------------------------
    # Visibility / travel rules
    # ------------------------------------------------------------------
    def reveal_on_arrival(self, name: str) -> None:
        """Permanently reveal ``name`` and all of its connections."""
        self.revealed.add(name)
        self.revealed |= self.graph.neighbours(name)

    def arrive(self, name: str) -> None:
        """Move the player to ``name``, revealing it and its connections.

        Stage 8 (jumping) is the caller. The selection is cleared because a
        jump consumes it: you cannot still be bound for the system you just
        landed in.
        """
        if name not in self.graph.names:
            raise ValueError(f"unknown system {name!r}")
        self.current_system = name
        self.selected_system = None
        self.reveal_on_arrival(name)
