"""Placeholder game scene (Stage 2).

Displayed immediately after the player selects a difficulty. Shows the
chosen difficulty and a brief hint. This scene will be replaced by the
full tactical display in Stage 4. ESC returns to the title screen.
"""

import pygame

from src.scene_manager import Scene

_SCREEN_SIZE = (1024, 768)
_GREEN = (100, 220, 100)
_GREY = (150, 150, 150)


class PlaceholderScene(Scene):
    """Temporary stub scene active until Stage 4 replaces it."""

    def on_enter(self, manager) -> None:
        super().on_enter(manager)
        self._font_large = pygame.font.SysFont(None, 48)
        self._font_small = pygame.font.SysFont(None, 30)

    def handle_event(self, event) -> None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            from src.scenes.title_screen import TitleScene  # avoid circular
            self._manager.replace(TitleScene())

    def draw(self, surface: "pygame.Surface") -> None:
        surface.fill((0, 0, 0))
        difficulty = (self._manager.selected_difficulty or "unknown").capitalize()
        line1 = self._font_large.render(
            f"New game \u2014 difficulty: {difficulty}", True, _GREEN
        )
        line2 = self._font_small.render(
            "(placeholder \u2014 tactical view coming in Stage 4)", True, _GREY
        )
        cx, cy = _SCREEN_SIZE[0] // 2, _SCREEN_SIZE[1] // 2
        surface.blit(line1, line1.get_rect(center=(cx, cy - 30)))
        surface.blit(line2, line2.get_rect(center=(cx, cy + 25)))
