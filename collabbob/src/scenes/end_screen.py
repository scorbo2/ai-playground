"""The end screen: one of four endings, the run's numbers, one way out (Stage 13).

A full-window scene, pushed on top of whatever the run was doing (tactical view,
or the spaceport the player was standing in when the run ended). Because the
:class:`~src.scene_manager.SceneManager` routes ``update()`` and ``handle_event()``
to the top scene only, pushing this one *is* the freeze: the simulation under it
stops without anything having to ask it to.

Spec copy, verbatim: the button is labelled "Return to title screen", and either
clicking it or pressing ``ESC`` goes back to the title.

Split the same way the spaceport splits things:

* rules and copy live in :mod:`src.model.endgame` / :mod:`src.model.run_stats`
  (:func:`~src.model.endgame.ending_copy` and :meth:`RunSummary.lines` are what
  the screen prints, so a test that asserts on them asserts on the pixels);
* geometry lives here as module-level rects a test can also read;
* the only gameplay decision this scene makes is "back to the title now", which
  clears the whole stack rather than popping one scene — a run's scenes must not
  survive a run.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame
import pygame_gui

from src.fonts import render_text
from src.main_loop import SCREEN_SIZE
from src.model.endgame import ending_copy, ending_explanation, is_victory
from src.model.run_stats import RunSummary
from src.scene_manager import Scene

if TYPE_CHECKING:
    from src.scene_manager import SceneManager

WINDOW = pygame.Rect(0, 0, *SCREEN_SIZE)

# -- geometry -----------------------------------------------------------------
MARGIN = 60
HEADLINE_RECT = pygame.Rect(MARGIN, 110, SCREEN_SIZE[0] - 2 * MARGIN, 60)
EXPLANATION_RECT = pygame.Rect(MARGIN, 182, SCREEN_SIZE[0] - 2 * MARGIN, 26)
RULE_RECT = pygame.Rect(MARGIN, 226, SCREEN_SIZE[0] - 2 * MARGIN, 2)
SUMMARY_RECT = pygame.Rect(MARGIN + 40, 258, SCREEN_SIZE[0] - 2 * MARGIN - 80, 260)

SUMMARY_LINE_HEIGHT = 26
# Where the value column starts, measured from the summary block's left edge. The
# widest label the summary can produce is "Systems discovered" (18 monospace
# characters); 210px leaves it room at SUMMARY_SIZE without the columns touching.
VALUE_COLUMN_X = 210
RETURN_WIDTH, RETURN_HEIGHT = 260, 52
RETURN_RECT = pygame.Rect(
    (SCREEN_SIZE[0] - RETURN_WIDTH) // 2, SCREEN_SIZE[1] - 96 - RETURN_HEIGHT // 2,
    RETURN_WIDTH, RETURN_HEIGHT,
)
HINT_RECT = pygame.Rect(MARGIN, SCREEN_SIZE[1] - 40, SCREEN_SIZE[0] - 2 * MARGIN, 20)

# -- type sizes ---------------------------------------------------------------
HEADLINE_SIZE = 44
EXPLANATION_SIZE = 17
SUMMARY_SIZE = 18
HINT_SIZE = 13

RETURN_BUTTON_TEXT = "Return to title screen"


class EndPalette:
    """Presentation colours for the end screen. In code, like every other screen."""

    background = (7, 9, 14)
    lost = (255, 90, 90)
    won = (120, 235, 140)
    explanation = (200, 210, 228)
    label = (150, 160, 180)
    rule = (70, 78, 96)
    hint = (130, 140, 158)


def headline_color(ending: str) -> "tuple[int, int, int]":
    """Green for the win, red for every loss. One lookup, so the headline and the
    explanation of *why* cannot disagree."""
    return EndPalette.won if is_victory(ending) else EndPalette.lost


def summary_rect_for(line: int) -> "pygame.Rect":
    """Where stat line ``line`` (0-based) is drawn; also the overlap test's input."""
    return SUMMARY_RECT.move(0, line * SUMMARY_LINE_HEIGHT)


class EndScreenScene(Scene):
    """The result screen for a finished run."""

    def __init__(self, ending: str, summary: RunSummary) -> None:
        super().__init__()
        if not isinstance(summary, RunSummary):
            raise ValueError(
                "EndScreenScene needs a RunSummary built from the finished run "
                f"(got {type(summary).__name__})"
            )
        # ``ending_copy`` is called here rather than at draw time so an ending the
        # game does not have fails when the run ends, with the ending in the
        # traceback, instead of as a KeyError from inside a render loop.
        self.ending = ending
        self.headline = ending_copy(ending)
        self.explanation = ending_explanation(ending)
        self.summary = summary
        self._ui: "pygame_gui.UIManager | None" = None
        self._return_button: "pygame_gui.elements.UIButton | None" = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def on_enter(self, manager: "SceneManager") -> None:
        super().on_enter(manager)
        self._ui = pygame_gui.UIManager(SCREEN_SIZE)
        self._return_button = pygame_gui.elements.UIButton(
            relative_rect=RETURN_RECT, text=RETURN_BUTTON_TEXT, manager=self._ui
        )
        # pygame_gui builds a widget's images in its first update, so a draw
        # before that paints a screen with no button (see SpaceportView).
        self._ui.update(1.0 / 60.0)

    def on_exit(self) -> None:
        if self._ui is not None:
            self._ui.clear_and_reset()
        self._return_button = None
        super().on_exit()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def handle_event(self, event) -> None:
        """The button, ESC, and QUIT. Nothing else is input on this screen."""
        if self._ui is None:
            return
        self._ui.process_events(event)

        if event.type == pygame.QUIT:
            if self._manager is not None:
                self._manager.quit()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._return_to_title()
            return
        if event.type == pygame_gui.UI_BUTTON_PRESSED and event.ui_element is self._return_button:
            self._return_to_title()

    def _return_to_title(self) -> None:
        """Clear the stack, then put a fresh title screen on an empty one.

        Clearing rather than popping: this scene sits above a tactical view and
        possibly a spaceport, and a run whose scenes survive it is a run whose
        ``GameState``, fog of war, and grudges can be walked back into. The title
        screen is rebuilt (not reused) for the same reason — its buttons and
        ``UIManager`` were destroyed on its last ``on_exit``.
        """
        manager = self._manager
        if manager is None:
            return
        manager.audio.play_confirm()
        manager.clear()
        from src.scenes.title_screen import TitleScene  # late: title flow owns us

        manager.push(TitleScene())

    # ------------------------------------------------------------------
    # Update / draw
    # ------------------------------------------------------------------
    def update(self) -> None:
        if self._ui is not None:
            self._ui.update(1.0 / 60.0)

    def draw(self, surface: "pygame.Surface") -> None:
        """Repaint the whole window: whatever is under this scene is a finished run."""
        surface.fill(EndPalette.background)
        accent = headline_color(self.ending)

        label = render_text(self.headline, HEADLINE_SIZE, accent, bold=True)
        surface.blit(label, label.get_rect(center=HEADLINE_RECT.center))

        why = render_text(self.explanation, EXPLANATION_SIZE, EndPalette.explanation)
        surface.blit(why, why.get_rect(center=EXPLANATION_RECT.center))

        pygame.draw.rect(surface, EndPalette.rule, RULE_RECT)
        for row, (label_text, value) in enumerate(self.summary.pairs()):
            self._draw_stat(surface, row, label_text, value)

        hint = render_text("Press ESC to return to the title screen", HINT_SIZE, EndPalette.hint)
        surface.blit(hint, hint.get_rect(center=HINT_RECT.center))
        self._ui.draw_ui(surface)

    def _draw_stat(
        self,
        surface: "pygame.Surface",
        row: int,
        label_text: str,
        value: str,
    ) -> None:
        """One stat row: label column in muted grey, value column in readable white.

        The columns are positioned here, from :data:`SUMMARY_RECT` and
        :data:`VALUE_COLUMN_X`, because the summary hands over ``(label, value)``
        pairs rather than pre-padded strings: one owner for the geometry.
        """
        top = SUMMARY_RECT.top + row * SUMMARY_LINE_HEIGHT
        render = render_text(label_text, SUMMARY_SIZE, EndPalette.label)
        surface.blit(render, render.get_rect(topleft=(SUMMARY_RECT.left, top)))
        if value:
            value_render = render_text(value, SUMMARY_SIZE, EndPalette.explanation)
            surface.blit(
                value_render,
                value_render.get_rect(topleft=(SUMMARY_RECT.left + VALUE_COLUMN_X, top)),
            )
