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

    def on_resume(self) -> None:
        """This scene has become the top scene again (a modal above it closed).

        A modal swallows the ``KEYUP`` of the very key that opened it: the press
        goes to the scene below, the modal is pushed in the same frame, and the
        release arrives at a scene that has no tactical input layer to feed. The
        scene below is then left holding a phantom key, and the *next* press of
        that key produces no rising edge at all. Every scene that opens a modal
        on a keypress needs this callback; the alternative is each modal reaching
        down through the stack to reset somebody else's input layer.
        """

    def update(self) -> None:
        pass

    def draw(self, surface) -> None:  # noqa: ANN001
        pass


# Fallback used only when no difficulty has been chosen yet (tests, tooling).
# A real game reaches the gameplay scenes through the difficulty dialog, which
# sets ``selected_config`` first.
DEFAULT_DIFFICULTY_CONFIG = "config_medium.json"


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

    def game_config(self) -> dict:
        """The configuration the player chose at "New game".

        Every gameplay scene must read its tunables through this method. Reading
        a fixed filename (as Stages 4-6 did) silently pins the game to one
        difficulty no matter what the player clicked.
        """
        if self.selected_config is not None:
            return self.selected_config
        return self.configs[DEFAULT_DIFFICULTY_CONFIG]

    def push(self, scene: Scene) -> None:
        """Push a new scene onto the top of the stack."""
        scene.on_enter(self)
        self._stack.append(scene)

    def pop(self) -> None:
        """Remove the top scene from the stack and wake up whatever is underneath.

        The new top scene gets :meth:`Scene.on_resume` — one notification from the
        owner of the stack, rather than every modal reaching for the scene below
        it (which a modal can only do by digging into private state).
        """
        if self._stack:
            top = self._stack.pop()
            top.on_exit()
            if self._stack:
                self._stack[-1].on_resume()

    def clear(self) -> None:
        """Pop every scene in the stack, top first.

        The way to end a *run* rather than a screen: a run's scenes hold its
        ``GameState``, its fog of war, its market board, and its grudges, and any
        of them surviving back to the title screen is a leaked save file nobody
        asked for. ``on_resume`` is deliberately *not* fired while unwinding —
        everything below is being discarded too.
        """
        while self._stack:
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
