"""Difficulty-selection dialog scene.

Pushed over the TitleScene when the player clicks "New game". Presents
Easy / Medium / Hard choices plus a Cancel button. Selecting a difficulty
stores it in the SceneManager, pops this dialog, and replaces the title
screen with the PlaceholderScene. Cancelling simply pops this dialog,
returning the player to the title screen.
"""

import pygame
import pygame_gui

from src.scenes.tactical_view import TacticalView
from src.scene_manager import Scene

_SCREEN_SIZE = (1024, 768)

# Config filenames keyed by difficulty label
_DIFFICULTIES = [
    ("easy", "config_easy.json", "Easy"),
    ("medium", "config_medium.json", "Medium"),
    ("hard", "config_hard.json", "Hard"),
]

# Panel geometry
_PANEL_W = 420
_PANEL_H = 240
_PANEL_X = (_SCREEN_SIZE[0] - _PANEL_W) // 2
_PANEL_Y = (_SCREEN_SIZE[1] - _PANEL_H) // 2

# Difficulty button layout (three across)
_DBTN_W = 100
_DBTN_H = 44
_DBTN_GAP = 16
_DBTN_ROW_TOTAL_W = 3 * _DBTN_W + 2 * _DBTN_GAP
_DBTN_START_X = _PANEL_X + (_PANEL_W - _DBTN_ROW_TOTAL_W) // 2
_DBTN_Y = _PANEL_Y + 90

# Cancel button (centred beneath difficulty row)
_CBTN_W = 100
_CBTN_H = 40
_CBTN_X = _PANEL_X + (_PANEL_W - _CBTN_W) // 2
_CBTN_Y = _DBTN_Y + _DBTN_H + _DBTN_GAP


class DifficultyDialog(Scene):
    """Modal difficulty-selection dialog pushed over the title screen."""

    def on_enter(self, manager) -> None:
        super().on_enter(manager)
        self._ui = pygame_gui.UIManager(_SCREEN_SIZE)

        # Semi-transparent dark overlay drawn over lower scenes.
        self._overlay = pygame.Surface(_SCREEN_SIZE, pygame.SRCALPHA)
        self._overlay.fill((0, 0, 0, 160))

        self._font_title = pygame.font.SysFont(None, 36)

        # Difficulty buttons; mapped to (difficulty_key, config_filename).
        self._buttons: dict = {}
        for i, (key, config_name, label) in enumerate(_DIFFICULTIES):
            btn = pygame_gui.elements.UIButton(
                relative_rect=pygame.Rect(
                    _DBTN_START_X + i * (_DBTN_W + _DBTN_GAP),
                    _DBTN_Y,
                    _DBTN_W,
                    _DBTN_H,
                ),
                text=label,
                manager=self._ui,
            )
            self._buttons[btn] = (key, config_name)

        self._cancel_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(_CBTN_X, _CBTN_Y, _CBTN_W, _CBTN_H),
            text="Cancel",
            manager=self._ui,
        )

    def on_exit(self) -> None:
        self._ui.clear_and_reset()
        super().on_exit()

    def handle_event(self, event) -> None:
        self._ui.process_events(event)
        if event.type != pygame_gui.UI_BUTTON_PRESSED:
            return

        if event.ui_element == self._cancel_btn:
            self._manager.pop()
            return

        if event.ui_element in self._buttons:
            key, config_name = self._buttons[event.ui_element]
            self._manager.audio.play_confirm()
            self._manager.selected_difficulty = key
            self._manager.selected_config = self._manager.configs[config_name]

            # Save manager ref before pop() nulls self._manager via on_exit.
            manager = self._manager
            manager.pop()  # pops self; stack now has [TitleScene]
            manager.replace(TacticalView(manager))  # replaces TitleScene with the game view

    def update(self) -> None:
        self._ui.update(1.0 / 60.0)

    def draw(self, surface: "pygame.Surface") -> None:
        # Dim overlay on top of whatever is beneath this scene.
        surface.blit(self._overlay, (0, 0))

        # Panel background
        pygame.draw.rect(surface, (30, 30, 50), (_PANEL_X, _PANEL_Y, _PANEL_W, _PANEL_H))
        pygame.draw.rect(surface, (100, 100, 140), (_PANEL_X, _PANEL_Y, _PANEL_W, _PANEL_H), 2)

        # Prompt text
        prompt = self._font_title.render("Select difficulty", True, (220, 220, 255))
        surface.blit(
            prompt,
            prompt.get_rect(center=(_SCREEN_SIZE[0] // 2, _PANEL_Y + 45)),
        )

        self._ui.draw_ui(surface)
