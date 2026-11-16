"""The "Exit game?" confirmation: ESC in tactical, and one way to abandon a run.

Stage 13's optional pause-to-title, implemented as a *confirmation* rather than a
menu. ``ESC`` is already the "close what is open" key in this game, and binding it
straight to the title screen would end a forty-minute run on a fat finger — with
no save and no resume anywhere in the game, that is not a pause, it is an
execution. So the key raises a question instead.

Deliberately minimal: two buttons, no settings, no save, no "quit to desktop"
(that is what closing the window is for, and the README says so). Like the
difficulty dialog, it is a modal drawn *over* the tactical view, and the stack's
top-scene-only routing is what pauses the simulation underneath it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame
import pygame_gui

from src.fonts import render_text
from src.main_loop import SCREEN_SIZE
from src.scene_manager import Scene

if TYPE_CHECKING:
    from src.scene_manager import SceneManager

# Panel geometry, shared with the tests so a pixel probe and the layout cannot
# drift apart.
PANEL_W, PANEL_H = 440, 220
PANEL_X = (SCREEN_SIZE[0] - PANEL_W) // 2
PANEL_Y = (SCREEN_SIZE[1] - PANEL_H) // 2
PANEL_RECT = pygame.Rect(PANEL_X, PANEL_Y, PANEL_W, PANEL_H)

RESUME_W, RESUME_H = 150, 44
RETURN_W, RETURN_H = 150, 44
_BUTTON_GAP = 20
_BUTTON_ROW_W = RESUME_W + RETURN_W + _BUTTON_GAP
_BUTTON_X = PANEL_X + (PANEL_W - _BUTTON_ROW_W) // 2
_BUTTON_Y = PANEL_Y + 130
RESUME_RECT = pygame.Rect(_BUTTON_X, _BUTTON_Y, RESUME_W, RESUME_H)
RETURN_RECT = pygame.Rect(_BUTTON_X + RESUME_W + _BUTTON_GAP, _BUTTON_Y, RETURN_W, RETURN_H)

TITLE_RECT = pygame.Rect(PANEL_X, PANEL_Y + 28, PANEL_W, 34)
SUBTITLE_RECT = pygame.Rect(PANEL_X + 20, PANEL_Y + 66, PANEL_W - 40, 50)

PROMPT = "Exit game?"
# Pre-wrapped rather than wrapped at draw time: this is authored copy, not loaded
# data, and a Stage 13 test measures both lines against the panel.
SUBTITLE_LINES = (
    "This run ends here. There is no save,",
    "and nothing to come back to.",
)

RESUME_TEXT = "Keep playing"
RETURN_TEXT = "Return to title"

# Named so a test can prove the panel is gone again after the dialog closes — a
# colour that only exists inline cannot be probed for absence.
PANEL_FILL = (26, 22, 34)
PANEL_BORDER = (150, 96, 96)
PROMPT_COLOR = (255, 120, 120)
SUBTITLE_COLOR = (200, 205, 220)
OVERLAY_SHADE = (0, 0, 0, 170)


class ExitConfirmation(Scene):
    """Modal confirmation for abandoning the current run."""

    def on_enter(self, manager: "SceneManager") -> None:
        super().on_enter(manager)
        self._ui = pygame_gui.UIManager(SCREEN_SIZE)
        self._overlay = pygame.Surface(SCREEN_SIZE, pygame.SRCALPHA)
        self._overlay.fill(OVERLAY_SHADE)

        self._resume_button = pygame_gui.elements.UIButton(
            relative_rect=RESUME_RECT, text=RESUME_TEXT, manager=self._ui
        )
        self._return_button = pygame_gui.elements.UIButton(
            relative_rect=RETURN_RECT, text=RETURN_TEXT, manager=self._ui
        )
        # pygame_gui builds a widget's images during its first update, so a draw
        # before that paints a dialog with no buttons (see SpaceportView).
        self._ui.update(1.0 / 60.0)

    def on_exit(self) -> None:
        if getattr(self, "_ui", None) is not None:
            self._ui.clear_and_reset()
        super().on_exit()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def handle_event(self, event) -> None:
        """Buttons, ESC (= keep playing), and QUIT. Nothing else leaves this screen."""
        if getattr(self, "_ui", None) is None or self._manager is None:
            return
        self._ui.process_events(event)

        if event.type == pygame.QUIT:
            self._manager.quit()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._resume()
            return
        if event.type != pygame_gui.UI_BUTTON_PRESSED:
            return
        if event.ui_element is self._resume_button:
            self._resume()
        elif event.ui_element is self._return_button:
            self._return_to_title()

    def _resume(self) -> None:
        """Close the question and hand the keyboard back to the tactical view.

        ``pop()`` notifies the scene underneath through :meth:`Scene.on_resume`,
        which is where GameScene forgets the phantom ``ESC`` this dialog swallowed
        (the press opened this modal, so its release never reached the tactical
        input layer — see ``InputLayer.reset_held_state``).
        """
        if self._manager is None:
            return
        self._manager.audio.play_confirm()
        self._manager.pop()

    def _return_to_title(self) -> None:
        """Abandon the run: the whole stack goes, and a fresh title screen replaces it."""
        manager = self._manager
        if manager is None:
            return
        manager.audio.play_confirm()
        manager.clear()
        from src.scenes.title_screen import TitleScene  # late: the title flow owns us

        manager.push(TitleScene())

    # ------------------------------------------------------------------
    # Update / draw
    # ------------------------------------------------------------------
    def update(self) -> None:
        if getattr(self, "_ui", None) is not None:
            self._ui.update(1.0 / 60.0)

    def draw(self, surface: "pygame.Surface") -> None:
        """Dim what is underneath, draw the question, then the buttons.

        A modal that repaints only its own panel leaves the previous frame's
        pixels around it — and this one sits over a moving tactical view, so the
        ghost would be a slideshow. The dim overlay covers the whole window
        instead, which is also what tells the player the game is waiting.
        """
        surface.blit(self._overlay, (0, 0))
        pygame.draw.rect(surface, PANEL_FILL, PANEL_RECT)
        pygame.draw.rect(surface, PANEL_BORDER, PANEL_RECT, 2)

        prompt = render_text(PROMPT, 30, PROMPT_COLOR, bold=True)
        surface.blit(prompt, prompt.get_rect(center=TITLE_RECT.center))
        for offset, line in enumerate(SUBTITLE_LINES):
            render = render_text(line, 15, SUBTITLE_COLOR)
            surface.blit(
                render,
                render.get_rect(center=(SUBTITLE_RECT.centerx,
                                        SUBTITLE_RECT.top + 12 + offset * 20)),
            )
        self._ui.draw_ui(surface)
