"""Title screen scene.

Displays the game title centred in the upper half of the window and two
pygame_gui buttons ("New game" / "Exit") stacked in the lower half.
Clicking "New game" pushes a DifficultyDialog; "Exit" quits the game.
"""

import os

import pygame
import pygame_gui

from src.config import GAME_ROOT
from src.scene_manager import Scene

_SCREEN_SIZE = (1024, 768)
_TITLE_TEXT = "The velocity of escape"
_BG_PATH = os.path.join(GAME_ROOT, "resources", "title_screen.png")

# Button dimensions and vertical layout within the lower half.
_BTN_W = 220
_BTN_H = 52
_BTN_GAP = 20
_LOWER_HALF_CENTER_Y = _SCREEN_SIZE[1] * 3 // 4  # 576
_NEW_GAME_Y = _LOWER_HALF_CENTER_Y - _BTN_H - _BTN_GAP // 2
_EXIT_Y = _LOWER_HALF_CENTER_Y + _BTN_GAP // 2


class TitleScene(Scene):
    """The main title screen."""

    def on_enter(self, manager) -> None:
        super().on_enter(manager)
        self._ui = pygame_gui.UIManager(_SCREEN_SIZE)

        # Background image (fail-soft: use black if the image is missing/broken).
        self._bg: "pygame.Surface | None" = None
        try:
            img = pygame.image.load(_BG_PATH)
            self._bg = pygame.transform.scale(img, _SCREEN_SIZE)
        except Exception:
            pass

        self._font = pygame.font.SysFont(None, 72)

        cx = _SCREEN_SIZE[0] // 2
        self._new_game_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(cx - _BTN_W // 2, _NEW_GAME_Y, _BTN_W, _BTN_H),
            text="New game",
            manager=self._ui,
        )
        self._exit_btn = pygame_gui.elements.UIButton(
            relative_rect=pygame.Rect(cx - _BTN_W // 2, _EXIT_Y, _BTN_W, _BTN_H),
            text="Exit",
            manager=self._ui,
        )

    def on_exit(self) -> None:
        self._ui.clear_and_reset()
        super().on_exit()

    def handle_event(self, event) -> None:
        self._ui.process_events(event)
        if event.type == pygame_gui.UI_BUTTON_PRESSED:
            if event.ui_element == self._new_game_btn:
                self._manager.audio.play_confirm()
                from src.scenes.difficulty_dialog import DifficultyDialog  # avoid circular
                self._manager.push(DifficultyDialog())
            elif event.ui_element == self._exit_btn:
                self._manager.quit()

    def update(self) -> None:
        self._ui.update(1.0 / 60.0)

    def draw(self, surface: "pygame.Surface") -> None:
        if self._bg is not None:
            surface.blit(self._bg, (0, 0))
        else:
            surface.fill((0, 0, 0))

        title_surf = self._font.render(_TITLE_TEXT, True, (255, 255, 255))
        title_rect = title_surf.get_rect(
            center=(_SCREEN_SIZE[0] // 2, _SCREEN_SIZE[1] // 4)
        )
        surface.blit(title_surf, title_rect)

        self._ui.draw_ui(surface)
