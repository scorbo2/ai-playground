"""Stack-based scene manager and abstract Scene base class.

The scene stack drives all game screens: title, difficulty dialog, tactical,
map, spaceport, and game-over. Only the top scene receives update and event
calls. All scenes in the stack are drawn bottom-to-top so that modals appear
layered over the screens beneath them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    import pygame
    from src.audio import AudioSystem


class Scene:
    """Abstract base class for all game scenes."""

    def __init__(self) -> None:
        self._manager: Optional["SceneManager"] = None

    def on_enter(self, manager: "SceneManager") -> None:
        self._manager = manager

    def on_exit(self) -> None:
        self._manager = None

    def handle_event(self, event) -> None:  # noqa: ANN001
        pass

    def update(self) -> None:
        pass

    def draw(self, surface) -> None:  # noqa: ANN001
        pass


class SceneManager:
    """Stack-based scene manager; only the top scene is active."""

    def __init__(
        self,
        screen: "pygame.Surface",
        configs: dict,
        audio: "AudioSystem",
    ) -> None:
        self._screen = screen
        self.configs = configs
        self.audio = audio
        self.selected_difficulty: Optional[str] = None
        self.selected_config: Optional[dict] = None
        self._stack: List[Scene] = []
        self._running: bool = True

    @property
    def running(self) -> bool:
        return self._running

    def quit(self) -> None:
        self._running = False

    def push(self, scene: Scene) -> None:
        """Push a new scene onto the top of the stack."""
        scene.on_enter(self)
        self._stack.append(scene)

    def pop(self) -> None:
        """Remove the top scene from the stack."""
        if self._stack:
            top = self._stack.pop()
            top.on_exit()

    def replace(self, scene: Scene) -> None:
        """Replace the top scene with a new one."""
        if self._stack:
            top = self._stack.pop()
            top.on_exit()
        scene.on_enter(self)
        self._stack.append(scene)

    def handle_event(self, event) -> None:  # noqa: ANN001
        """Route the event to the top scene only."""
        if self._stack:
            self._stack[-1].handle_event(event)

    def update(self) -> None:
        """Advance the top scene by one fixed timestep."""
        if self._stack:
            self._stack[-1].update()

    def draw(self) -> None:
        """Draw all scenes from bottom to top onto the managed screen."""
        for scene in self._stack:
            scene.draw(self._screen)
