"""Stage 2 tests: scene manager, title screen, difficulty dialog, and audio."""

import pygame
import pygame_gui
import pytest

from src.audio import AudioSystem
from src.config import base_config, load_config
from src.harness import RecordingAudio
from src.scene_manager import Scene, SceneManager
from src.scenes.difficulty_dialog import DifficultyDialog
from src.scenes.game_scene import GameScene
from src.scenes.title_screen import TitleScene


# ---------------------------------------------------------------------------
# Lightweight mock helpers
# ---------------------------------------------------------------------------


class _MockManager:
    """Minimal SceneManager stand-in for unit tests."""

    def __init__(self, configs=None):
        self.configs = configs or {
            "config_easy.json": base_config(),
            "config_medium.json": base_config(),
            "config_hard.json": base_config(),
        }
        self.audio = RecordingAudio()
        self.selected_difficulty = None
        self.selected_config = None
        self._running = True
        self.pushed: list = []
        self.replaced: list = []
        self.popped_count = 0

    @property
    def running(self):
        return self._running

    def quit(self):
        self._running = False

    def push(self, scene):
        self.pushed.append(scene)

    def pop(self):
        self.popped_count += 1

    def replace(self, scene):
        self.replaced.append(scene)

    def game_config(self):
        """Gameplay scenes ask the manager which difficulty the player picked."""
        return self.configs["config_easy.json"]


def _btn_pressed_event(btn):
    """Build a synthetic pygame_gui UI_BUTTON_PRESSED event for a UIButton."""
    return pygame.event.Event(
        pygame_gui.UI_BUTTON_PRESSED,
        {"ui_element": btn, "ui_object_id": "#button"},
    )


# ---------------------------------------------------------------------------
# Audio system
# ---------------------------------------------------------------------------


def test_audio_system_no_crash_with_dummy_driver():
    """AudioSystem initialises and play_confirm() never raises under dummy driver."""
    audio = AudioSystem()
    # Should not raise regardless of whether the dummy driver allows mixing.
    audio.play_confirm()
    audio.play_confirm()


def test_audio_system_available_flag_is_bool():
    audio = AudioSystem()
    assert isinstance(audio.available, bool)


# ---------------------------------------------------------------------------
# Scene base class and SceneManager stack mechanics
# ---------------------------------------------------------------------------


def test_scene_manager_push_calls_on_enter():
    screen = pygame.display.get_surface()
    audio = AudioSystem()
    manager = SceneManager(screen=screen, configs={}, audio=audio)

    entered = []

    class _TrackScene(Scene):
        def on_enter(self, mgr):
            super().on_enter(mgr)
            entered.append(mgr)

    scene = _TrackScene()
    manager.push(scene)
    assert entered == [manager]


def test_scene_manager_pop_calls_on_exit():
    screen = pygame.display.get_surface()
    audio = AudioSystem()
    manager = SceneManager(screen=screen, configs={}, audio=audio)

    exited = []

    class _TrackScene(Scene):
        def on_exit(self):
            exited.append(True)
            super().on_exit()

    scene = _TrackScene()
    manager.push(scene)
    manager.pop()
    assert exited == [True]
    assert manager._stack == []


def test_scene_manager_only_top_scene_updated():
    screen = pygame.display.get_surface()
    audio = AudioSystem()
    manager = SceneManager(screen=screen, configs={}, audio=audio)

    updates: list = []

    class _CountingScene(Scene):
        def __init__(self, name):
            super().__init__()
            self.name = name

        def on_enter(self, mgr):
            super().on_enter(mgr)

        def update(self):
            updates.append(self.name)

    s1, s2 = _CountingScene("bottom"), _CountingScene("top")
    manager.push(s1)
    manager.push(s2)
    manager.update()
    assert updates == ["top"]


def test_scene_manager_quit_stops_running():
    screen = pygame.display.get_surface()
    audio = AudioSystem()
    manager = SceneManager(screen=screen, configs={}, audio=audio)
    assert manager.running
    manager.quit()
    assert not manager.running


# ---------------------------------------------------------------------------
# Title screen
# ---------------------------------------------------------------------------


def test_title_new_game_button_pushes_difficulty_dialog():
    """Clicking 'New game' pushes a DifficultyDialog onto the mock manager."""
    mock = _MockManager()
    scene = TitleScene()
    scene.on_enter(mock)
    try:
        event = _btn_pressed_event(scene._new_game_btn)
        scene.handle_event(event)
        assert len(mock.pushed) == 1
        assert isinstance(mock.pushed[0], DifficultyDialog)
    finally:
        scene.on_exit()


def test_title_new_game_plays_confirm_beep():
    mock = _MockManager()
    scene = TitleScene()
    scene.on_enter(mock)
    try:
        scene.handle_event(_btn_pressed_event(scene._new_game_btn))
        assert mock.audio.confirm_count == 1
    finally:
        scene.on_exit()


def test_title_exit_button_quits():
    """Clicking 'Exit' calls quit() on the manager."""
    mock = _MockManager()
    scene = TitleScene()
    scene.on_enter(mock)
    try:
        event = _btn_pressed_event(scene._exit_btn)
        scene.handle_event(event)
        assert not mock.running
    finally:
        scene.on_exit()


def test_title_draws_without_crash():
    """draw() must not raise with or without the background image."""
    mock = _MockManager()
    scene = TitleScene()
    scene.on_enter(mock)
    try:
        surface = pygame.Surface((1024, 768))
        scene.draw(surface)
    finally:
        scene.on_exit()


def test_title_draw_repaints_the_whole_window_so_no_stale_pixels_survive():
    """A full-window scene must clear pixels it never draws.

    GIVEN a window pre-filled with the difficulty dialog's panel colour - exactly
    what a cancelled dialog leaves behind
    WHEN the title scene draws one frame
    THEN no sampled pixel anywhere on the window still shows that colour.

    The first revision only blitted ``resources/title_screen.png``, and that image
    is partially transparent (see scripts/generate_title_screen.py), so the blit
    composited the title *over* the dialog instead of replacing it: the cancelled
    dialog stayed visible, and the title glyphs re-composited over their own
    previous frames and saturated to solid white.
    """
    from src.scenes.difficulty_dialog import _PANEL_FILL

    scene = TitleScene()
    scene.on_enter(_MockManager())
    try:
        surface = pygame.Surface((1024, 768))
        surface.fill(_PANEL_FILL)
        scene.draw(surface)

        stale = [
            (x, y)
            for y in range(0, 768, 6)
            for x in range(0, 1024, 6)
            if surface.get_at((x, y))[:3] == _PANEL_FILL
        ]
        assert not stale, f"{len(stale)} stale pixels survived the title redraw: {stale[:5]}"
    finally:
        scene.on_exit()


def test_shipped_title_background_image_is_fully_opaque():
    """The title background asset must be opaque, whatever generated it.

    A translucent background turns the title screen into a compositor over the
    previous frame's contents. The generator script used to draw its gradient on an
    SRCALPHA surface with 3-tuple colours on a 4px stride, which left most rows at
    alpha 0 - so this asserts the shipped asset, not just the generator.
    """
    import os

    from src.scenes.title_screen import _BG_PATH

    if not os.path.exists(_BG_PATH):
        pytest.skip("title background asset is optional (fail-soft in TitleScene)")

    image = pygame.image.load(_BG_PATH)
    assert image.get_size() == (1024, 768), "title background must cover the window"

    # Sample every row (the historical defect was row-banded: the gradient drew one
    # line every 4 pixels and left the rows between them at alpha 0) at several
    # columns, so a stride that happens to match the band period cannot hide it.
    columns = [0, image.get_width() // 5, image.get_width() // 2,
               3 * image.get_width() // 4, image.get_width() - 1]
    transparent = [
        (x, y)
        for y in range(image.get_height())
        for x in columns
        if image.get_at((x, y)).a != 255
    ]
    assert not transparent, (
        f"title background is translucent at {len(transparent)} sampled pixels "
        f"(first few: {transparent[:5]})"
    )


# ---------------------------------------------------------------------------
# Difficulty dialog
# ---------------------------------------------------------------------------


def test_difficulty_cancel_pops_dialog():
    """Clicking Cancel pops the dialog without selecting a difficulty."""
    mock = _MockManager()
    dialog = DifficultyDialog()
    dialog.on_enter(mock)
    try:
        event = _btn_pressed_event(dialog._cancel_btn)
        dialog.handle_event(event)
        assert mock.popped_count == 1
        assert mock.selected_difficulty is None
        assert mock.replaced == []
    finally:
        # on_exit already called by pop() in real manager; call manually here.
        dialog.on_exit()


def test_difficulty_easy_selection_stores_difficulty_and_replaces_scene():
    """Selecting Easy stores the difficulty and transitions to the game scene."""
    mock = _MockManager()
    dialog = DifficultyDialog()
    dialog.on_enter(mock)

    easy_btn = next(btn for btn, (key, _) in dialog._buttons.items() if key == "easy")
    dialog.handle_event(_btn_pressed_event(easy_btn))

    assert mock.selected_difficulty == "easy"
    assert mock.selected_config == base_config()
    assert mock.popped_count == 1
    assert len(mock.replaced) == 1
    assert isinstance(mock.replaced[0], GameScene)
    assert mock.audio.confirm_count == 1


@pytest.mark.parametrize("key,cfg_name", [
    ("easy", "config_easy.json"),
    ("medium", "config_medium.json"),
    ("hard", "config_hard.json"),
])
def test_difficulty_all_options_work(key, cfg_name):
    mock = _MockManager()
    dialog = DifficultyDialog()
    dialog.on_enter(mock)

    btn = next(b for b, (k, _) in dialog._buttons.items() if k == key)
    dialog.handle_event(_btn_pressed_event(btn))

    assert mock.selected_difficulty == key
    assert mock.selected_config == mock.configs[cfg_name]


def test_difficulty_dialog_draws_without_crash():
    mock = _MockManager()
    dialog = DifficultyDialog()
    dialog.on_enter(mock)
    try:
        surface = pygame.Surface((1024, 768))
        # Draw the dark overlay and panel onto a blank surface.
        dialog.draw(surface)
    finally:
        dialog.on_exit()


# ---------------------------------------------------------------------------
# Integration: full SceneManager flow with real scenes
# ---------------------------------------------------------------------------


def test_integration_new_game_full_flow(config_factory):
    """Synthetic 'New game → Easy' flow using the real SceneManager."""
    configs = load_config(config_factory())
    screen = pygame.display.get_surface()
    audio = AudioSystem()
    manager = SceneManager(screen=screen, configs=configs, audio=audio)
    manager.push(TitleScene())

    # Click "New game"
    title = manager._stack[-1]
    assert isinstance(title, TitleScene)
    manager.handle_event(_btn_pressed_event(title._new_game_btn))

    # DifficultyDialog should now be on top
    assert isinstance(manager._stack[-1], DifficultyDialog)
    assert len(manager._stack) == 2

    # Select "Easy"
    dialog = manager._stack[-1]
    easy_btn = next(b for b, (k, _) in dialog._buttons.items() if k == "easy")
    manager.handle_event(_btn_pressed_event(easy_btn))

    # GameScene (tactical view + HUD) replaces the whole stack. The HUD must not
    # be a stack entry: only the top scene gets events, so a passive HUD on top
    # would freeze the game (the Stage 6 review bug).
    assert len(manager._stack) == 1
    assert isinstance(manager._stack[-1], GameScene)
    assert manager.selected_difficulty == "easy"
    assert manager.running

    # Cleanup
    manager.pop()


def test_integration_cancel_returns_to_title(config_factory):
    """Cancelling the difficulty dialog returns to the title screen."""
    configs = load_config(config_factory())
    screen = pygame.display.get_surface()
    audio = AudioSystem()
    manager = SceneManager(screen=screen, configs=configs, audio=audio)
    manager.push(TitleScene())

    title = manager._stack[-1]
    manager.handle_event(_btn_pressed_event(title._new_game_btn))

    dialog = manager._stack[-1]
    assert isinstance(dialog, DifficultyDialog)

    manager.handle_event(_btn_pressed_event(dialog._cancel_btn))

    # Back to title
    assert len(manager._stack) == 1
    assert isinstance(manager._stack[-1], TitleScene)

    manager.pop()


def test_integration_exit_button_stops_manager(config_factory):
    """Clicking Exit sets manager.running to False."""
    configs = load_config(config_factory())
    screen = pygame.display.get_surface()
    audio = AudioSystem()
    manager = SceneManager(screen=screen, configs=configs, audio=audio)
    manager.push(TitleScene())

    title = manager._stack[-1]
    manager.handle_event(_btn_pressed_event(title._exit_btn))

    assert not manager.running
    manager.pop()
