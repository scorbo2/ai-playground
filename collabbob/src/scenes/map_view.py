"""The system-map modal (Stage 7): fog-of-war graph, node picking, selection.

A full-screen modal raised by pressing ``M`` during tactical play and dismissed
by ``ESC`` (``M`` closes it too, as a convenience). It renders the *revealed*
part of the world graph: white circles for systems, thin grey edges for direct
connections, a green circle for the system the player is standing in, text
labels, and light-grey ``[`` / ``]`` brackets around the currently-selected
destination.

This view owns pixels and mouse plumbing only. Geometry lives in
:class:`~src.map_systems.layout.MapLayout`, the rules (what is revealed, what may
be selected, toggle-off) live in
:class:`~src.map_systems.system_map.SystemMapState`, and the topology lives in
:class:`~src.map_systems.graph.SystemGraph`. That separation is the fix for the
first revision, which drew every one of the 26 systems regardless of fog of war,
blitted white labels centred on white circles (giving "Alha", "Br vo" and
"Nov ber"), never cleared the screen (so the HUD and minimap showed through the
"modal"), and recomputed its layout on every keypress.

Nothing here is pushed onto the stack by this module: :class:`GameScene` decides
when the map may open (never mid-jump) and pushes it.
"""

from __future__ import annotations

import pygame

from src.fonts import render_text
from src.map_systems.system_map import DESELECTED, SELECTED, SystemMapState
from src.scene_manager import Scene


class _MapPalette:
    """Presentation colours for the map. In code, like the HUD palette and window size."""

    background = (0, 0, 0)
    edge = (120, 120, 130)      # "thin grey edges"
    node = (245, 245, 250)      # "white circles"
    current = (120, 190, 120)   # "you are here"
    label = (210, 235, 210)
    label_current = (140, 255, 140)
    bracket = (235, 235, 235)
    banner = (140, 255, 140)
    hint = (150, 150, 150)


_EDGE_WIDTH = 1  # "thin grey edges": one pixel, not the HUD's 2px borders
_BANNER_TEXT_SIZE = 18
_HINT_TEXT_SIZE = 14
_HEADER_FIRST_BASELINE = 8
_HEADER_LINE_HEIGHT = 22  # banner (18px) and hint lines (14px) stacked inside HEADER_BAND


class MapView(Scene):
    """Full-screen system-graph modal: draw the revealed graph, honour the rules."""

    def __init__(self, state: SystemMapState) -> None:
        """Take the map state whose layout was already computed once per game.

        The scene manager is *not* a constructor argument: ``Scene.on_enter()``
        receives it when the modal is pushed. The first revision took the
        ``GameScene`` here under a parameter named ``manager`` and then had
        ``on_enter`` overwrite it, leaving a lie in the signature and calls to
        ``self._manager.pop()`` against an object with no ``pop()``.
        """
        super().__init__()
        if state is None:
            raise ValueError("MapView requires the session's SystemMapState")
        self.state = state

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def handle_event(self, event) -> None:
        """QUIT exits the game, ESC/M close the modal, a left click picks a node.

        No pygame_gui elements exist on this screen, so raw mouse events are
        never consumed by a UI manager before they reach node picking.
        """
        if self._manager is None:
            return  # events cannot arrive before push()/on_enter(), but do not crash
        if event.type == pygame.QUIT:
            self._manager.quit()
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_ESCAPE, pygame.K_m):
            self._manager.pop()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._on_node_click(event.pos)

    def _on_node_click(self, pos: "tuple[int, int]") -> None:
        """Translate a click into a selection through the model's rules."""
        name = self.state.layout.node_at(pos, self.state.visible_nodes())
        outcome = self.state.handle_map_click(name)
        if outcome in (SELECTED, DESELECTED):
            self._manager.audio.play_confirm()
        # IGNORED covers empty space, unrevealed systems and systems that are
        # revealed but not adjacent to the current one: all silently unclickable.

    # ------------------------------------------------------------------
    # Update + draw
    # ------------------------------------------------------------------
    def update(self) -> None:
        """The map is a static modal: the simulation is paused underneath it.

        ``SceneManager`` routes ``update()`` to the top scene only, so the
        tactical view is not advanced while the map is open. That is the modal
        semantic the stack exists for (see DECISIONS.md, Stage 6 review fix 1).
        """

    def draw(self, surface: "pygame.Surface") -> None:
        """Repaint the whole window: a full-screen scene composites over nothing.

        Filling only part of the surface would leave the tactical view, HUD and
        minimap showing through, which is not a modal.
        """
        surface.fill(_MapPalette.background)
        self._draw_edges(surface)
        self._draw_nodes(surface)
        self._draw_header(surface)

    # ------------------------------------------------------------------
    # Drawing helpers
    # ------------------------------------------------------------------
    def _draw_edges(self, surface: "pygame.Surface") -> None:
        """Thin grey lines under the nodes, revealed endpoints only."""
        positions = self.state.layout.positions
        for first, second in self.state.visible_edges():
            pygame.draw.line(
                surface,
                _MapPalette.edge,
                self._pixel(positions[first]),
                self._pixel(positions[second]),
                _EDGE_WIDTH,
            )

    def _draw_nodes(self, surface: "pygame.Surface") -> None:
        """Circles, labels, and selection brackets for revealed systems."""
        layout = self.state.layout
        for name in self.state.visible_nodes():
            centre = self._pixel(layout.positions[name])
            is_current = name == self.state.current_system
            color = _MapPalette.current if is_current else _MapPalette.node
            pygame.draw.circle(
                surface, color, centre, int(round(layout.node_radius))
            )
            self._draw_label(surface, name, is_current)
            if self.state.selected_system == name:
                self._draw_brackets(surface, name)

    def _draw_label(self, surface: "pygame.Surface", name: str, is_current: bool) -> None:
        """Blit a system's label at the exact box the layout computed and hit-tests.

        The label is anchored radially outside its circle, so it can never sit on
        top of it (white glyph on white circle = invisible text).
        """
        layout = self.state.layout
        box = layout.label_boxes[name]
        color = _MapPalette.label_current if is_current else _MapPalette.label
        rendered = render_text(name, layout.label_font_size, color)
        # Paint the label's own slot opaque first. With the shipped configs the
        # graph is a tree and the DFS ring keeps every edge out of every label
        # box (measured: 0 intersections across 25 worlds), but a config raising
        # connections_min adds cycle edges that can cut a strikethrough through
        # a name. One rect is cheaper than auditing every future edge for it.
        pygame.draw.rect(
            surface,
            _MapPalette.background,
            pygame.Rect(int(box[0]), int(box[1]),
                        int(round(box[2] - box[0])) + 1, int(round(box[3] - box[1])) + 1),
        )
        surface.blit(rendered, (int(round(box[0])), int(round(box[1]))))

    def _draw_brackets(self, surface: "pygame.Surface", name: str) -> None:
        """Light-grey ``[`` and ``]`` hugging the selected system's label."""
        layout = self.state.layout
        box = layout.label_boxes[name]
        size = layout.label_font_size
        vertical_centre = int(round((box[1] + box[3]) / 2.0))
        left = render_text("[", size, _MapPalette.bracket)
        right = render_text("]", size, _MapPalette.bracket)
        surface.blit(left, left.get_rect(midright=(int(round(box[0])) - 2, vertical_centre)))
        surface.blit(right, right.get_rect(midleft=(int(round(box[2])) + 2, vertical_centre)))

    def _draw_header(self, surface: "pygame.Surface") -> None:
        """Banner plus current/destination/hint lines, centred in the header band.

        The layout guarantees the node ring and every label box start below
        ``layout.header_band``, so centred copy in that strip can never collide
        with a system label - unlike the first draft, which parked copy at the
        top-left of a ring that ran straight through it.
        """
        layout = self.state.layout
        for index, (text, size, color) in enumerate(self._header_lines()):
            rendered = render_text(text, size, color)
            surface.blit(
                rendered,
                rendered.get_rect(
                    midtop=(int(round(layout.center[0])),
                             _HEADER_FIRST_BASELINE + index * _HEADER_LINE_HEIGHT)
                ),
            )

    def _header_lines(self) -> tuple[tuple[str, int, "tuple[int, int, int]"], ...]:
        """Header copy is built per draw: the destination changes while the map is open."""
        state = self.state
        destination = state.selected_system or "none"
        return (
            ("SYSTEM MAP", _BANNER_TEXT_SIZE, _MapPalette.banner),
            (f"Current: {state.current_system}   Destination: {destination}",
             _HINT_TEXT_SIZE, _MapPalette.hint),
            ("Click a linked system to set a destination; ESC or M closes the map.",
             _HINT_TEXT_SIZE, _MapPalette.hint),
        )

    @staticmethod
    def _pixel(point: "tuple[float, float]") -> "tuple[int, int]":
        """Round a layout point to an integer pixel for pygame's draw calls."""
        return (int(round(point[0])), int(round(point[1])))
