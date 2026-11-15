"""System map / node-graph model (Stage 7).

The whole game world is a graph of 26 solar systems named after the NATO
phonetic alphabet. This package owns:

* :data:`NATO_SYSTEMS` - the identifier list (kept in code, as the spec says
  enum-like IDs belong there rather than in config).
* :class:`GraphConstraints` - the topology contract a generated graph must
  satisfy, built from the ``map`` config section.
* :class:`SystemGraph` - an immutable snapshot of the graph topology.
* :class:`SystemGraphGenerator` - builds a connected graph with bounded node
  degrees and the root's guaranteed connections, using an injectable RNG so it
  is deterministic per seed and unit-testable without pygame.
* :mod:`src.map_systems.layout` - pure geometry: node placement, label boxes,
  click hit-testing, and the "nothing may overlap" self-check.
* :class:`SystemMapState` - the mutable runtime state (revealed systems, current
  system, selection) plus the selection/reveal rules the map view obeys.

The graph and its layout are generated once per new game and cached; they are
never regenerated or re-layouted while the game runs.
"""

from __future__ import annotations

from src.map_systems.graph import (
    NATO_SYSTEMS,
    GraphConstraints,
    GraphGenerationError,
    SystemGraph,
    SystemGraphGenerator,
)
from src.map_systems.layout import MapLayout, MapLayoutError, build_map_layout
from src.map_systems.system_map import DESELECTED, IGNORED, SELECTED, SystemMapState

__all__ = [
    "DESELECTED",
    "GraphConstraints",
    "GraphGenerationError",
    "IGNORED",
    "MapLayout",
    "MapLayoutError",
    "NATO_SYSTEMS",
    "SELECTED",
    "SystemGraph",
    "SystemGraphGenerator",
    "SystemMapState",
    "build_map_layout",
]
