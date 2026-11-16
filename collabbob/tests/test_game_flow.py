"""End-to-end game flow: title screen -> difficulty -> playable simulation.

Every other stage test constructs a scene and calls ``update()``/``draw()`` on it
directly, which silently bypasses the wiring the main loop performs. That is
exactly how the Stage 6 HUD regression shipped: the HUD was pushed onto the scene
stack above the tactical view, only the top scene receives events, and the game
turned into a screenshot — while all 95 tests stayed green.

These tests drive the *real* ``FixedTimestepLoop.step_once()`` with real pygame
events posted into the event queue, so they exercise event routing, the scene
stack, the scene manager, the simulation, and the rendering of both screen
regions in one pass.
"""

import pygame
import pytest

import main  # noqa: F401  (ensures project root is on sys.path)

from src.audio import AudioSystem
from src.config import load_config
from src.hud import VIEW_WIDTH
from src.main_loop import FixedTimestepLoop
from src.scene_manager import SceneManager
from src.scenes.difficulty_dialog import DifficultyDialog
from src.scenes.game_scene import GameScene
from src.scenes.title_screen import TitleScene


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# Difficulty-dependent values written into the fabricated configs so a test can
# tell which config the game actually started with.
HARD_TOP_SPEED = 4.0
HARD_CARGO_ROOM = 15
HARD_SYSTEM_PIXEL_SIZE = 1800


def _configs_with_distinct_hard_difficulty(config_factory):
    """Fabricated config set where the hard file differs in observable ways."""
    configs = load_config(config_factory())
    hard = configs["config_hard.json"]["player_ship"]
    hard["top_speed"] = HARD_TOP_SPEED
    hard["cargo_room"] = HARD_CARGO_ROOM
    configs["config_hard.json"]["tactical"]["system_pixel_size"] = HARD_SYSTEM_PIXEL_SIZE
    return configs


def _build_flow(configs):
    """Title screen plus a real scene manager and fixed-timestep loop."""
    screen = pygame.display.get_surface()
    manager = SceneManager(screen=screen, configs=configs, audio=AudioSystem())
    manager.push(TitleScene())
    loop = FixedTimestepLoop(scene_manager=manager, screen=screen)
    return manager, loop


def _pump(loop, frames):
    """Run the real loop body for `frames` frames, draining the event queue."""
    for _ in range(frames):
        assert loop.step_once(), "the loop stopped unexpectedly"


def _click(loop, button):
    """Hover + click a pygame_gui button through the real pygame event queue."""
    rect = button.relative_rect
    pos = (int(rect.centerx), int(rect.centery))
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEMOTION, pos=pos, rel=(1, 1), buttons=(0, 0, 0)))
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, pos=pos, button=1, buttons=(1, 1, 1)))
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONUP, pos=pos, button=1, buttons=(0, 0, 0)))
    # A few frames for the UIManager to register the hover, fire the button
    # event, and run the resulting scene transition.
    _pump(loop, 5)


def _press(loop, key, frames=1):
    """Press and hold a key for `frames` loop frames."""
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, scancode=0, mod=0))
    _pump(loop, frames)


def _release(loop, key):
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=key, scancode=0, mod=0))
    _pump(loop, 1)


def _new_game(manager, loop, difficulty="hard"):
    """Click through 'New game' and pick a difficulty."""
    title = manager._stack[-1]
    _click(loop, title._new_game_btn)
    assert isinstance(manager._stack[-1], DifficultyDialog), "difficulty dialog did not open"

    dialog = manager._stack[-1]
    button = next(btn for btn, (key, _) in dialog._buttons.items() if key == difficulty)
    _click(loop, button)
    return manager._stack[-1]


# ---------------------------------------------------------------------------
# Flow: title -> difficulty -> game scene
# ---------------------------------------------------------------------------


def test_new_game_leaves_the_game_scene_on_top_of_the_stack(config_factory):
    """A new game leaves exactly one scene on the stack: the game scene.

    The HUD must be a component of that scene, never a stack entry — a passive
    scene on top would receive every event and every update, and the tactical
    view would stop simulating.
    """
    configs = _configs_with_distinct_hard_difficulty(config_factory)
    manager, loop = _build_flow(configs)

    scene = _new_game(manager, loop, difficulty="hard")

    assert len(manager._stack) == 1
    assert isinstance(scene, GameScene)
    assert manager.selected_difficulty == "hard"


def test_selected_difficulty_actually_drives_the_new_game(config_factory):
    """Picking Hard must really load the hard config.

    Both the tactical view and the HUD used to read ``config_easy.json`` by name,
    so every difficulty played the easy game.
    """
    configs = _configs_with_distinct_hard_difficulty(config_factory)
    manager, loop = _build_flow(configs)

    scene = _new_game(manager, loop, difficulty="hard")

    stats = scene.game_state.stats
    assert stats.top_speed == HARD_TOP_SPEED
    assert stats.cargo_room == HARD_CARGO_ROOM
    assert scene.game_state.system_pixel_size == float(HARD_SYSTEM_PIXEL_SIZE)


# ---------------------------------------------------------------------------
# Flow: playing the game after the transition
# ---------------------------------------------------------------------------


def test_holding_thrust_through_the_real_loop_moves_the_ship_and_burns_fuel(config_factory):
    """The Stage 6 regression test: the player's input must reach the simulation.

    With the HUD on top of the scene stack, 60 frames of held thrust left the
    ship at (0, 0) with 1000 fuel and an empty input layer.
    """
    configs = _configs_with_distinct_hard_difficulty(config_factory)
    manager, loop = _build_flow(configs)
    scene = _new_game(manager, loop, difficulty="hard")

    assert scene.game_state.fuel == pytest.approx(1000.0)

    _press(loop, pygame.K_UP, frames=60)

    ship = scene.game_state
    assert ship.velocity[0] > 0.0, "thrust must accelerate the ship"
    assert ship.position[0] > 0.0, "the ship must actually move"
    assert ship.fuel < 1000.0, "thrust must burn fuel"


def test_rotation_and_reverse_course_work_through_the_real_loop(config_factory):
    """Keyboard rotation and the reverse-course flip survive the full pipeline."""
    configs = _configs_with_distinct_hard_difficulty(config_factory)
    manager, loop = _build_flow(configs)
    scene = _new_game(manager, loop, difficulty="hard")

    start_heading = scene.game_state.heading_degrees
    _press(loop, pygame.K_LEFT, frames=20)
    _release(loop, pygame.K_LEFT)

    turned = scene.game_state.heading_degrees
    rate = scene.game_state.stats.turn_rate_deg_per_sec / 60.0
    assert turned == pytest.approx((start_heading - 20 * rate) % 360.0), (
        "left must rotate the ship counter-clockwise on screen"
    )

    _press(loop, pygame.K_DOWN, frames=1)
    _pump(loop, 60)
    assert scene.game_state.heading_degrees == pytest.approx((turned + 180.0) % 360.0), (
        "reverse course must flip the heading exactly 180 degrees"
    )


def test_hud_reports_the_ship_the_simulation_is_moving(config_factory):
    """The HUD and the tactical view must render one ship, not two.

    The first Stage 6 revision built a second GameState inside the HUD, so the
    status bars and minimap described a phantom ship that never changed.
    """
    configs = _configs_with_distinct_hard_difficulty(config_factory)
    manager, loop = _build_flow(configs)
    scene = _new_game(manager, loop, difficulty="hard")

    assert scene.hud.game_state is scene.game_state
    assert scene.tactical.game_state is scene.game_state

    _press(loop, pygame.K_UP, frames=60)

    # The minimap must have noticed the ship leaving the planet.
    view = scene.hud._rects["minimap"]
    surface = pygame.Surface((1024, 768))
    scene.hud.draw(surface)
    centre = (view.left + view.width // 2, view.top + view.height // 2)
    # The player marker stays pinned to the minimap centre...
    assert surface.get_at(centre)[:3] == (255, 255, 255)
    # ...and the ship's world position the HUD sees is the simulated one.
    assert scene.hud.game_state.position[0] > 0.0


def test_hud_column_is_clean_once_the_dialog_is_gone(config_factory):
    """Neither screen region leaks into the other after a real transition.

    The difficulty dialog's panel overlapped the HUD column (x 683..722) and
    nothing cleared the right third, so dialog pixels used to survive there
    permanently — review found the panel colour still painted at (690, 500).
    """
    configs = _configs_with_distinct_hard_difficulty(config_factory)
    manager, loop = _build_flow(configs)
    _new_game(manager, loop, difficulty="hard")
    _pump(loop, 2)

    screen = pygame.display.get_surface()
    dialog_panel = (30, 30, 50)
    dialog_border = (100, 100, 140)
    residue = [
        (x, y)
        for y in range(0, 768, 3)
        for x in range(VIEW_WIDTH, 1024, 3)
        if screen.get_at((x, y))[:3] in (dialog_panel, dialog_border)
    ]
    assert not residue, f"dialog pixels survived in the HUD column: {residue[:5]}"

    # The game view must be drawing something (ship / planet / starfield).
    drawn = sum(
        1
        for y in range(0, 768, 11)
        for x in range(0, VIEW_WIDTH, 11)
        if screen.get_at((x, y))[:3] != (0, 0, 0)
    )
    assert drawn > 0, "the game view is blank"


def test_landing_prompt_is_live_in_the_real_flow(config_factory):
    """The prompt the spec asks for appears in a real running game.

    A fresh game starts the ship at the planet (Stage 8 moves the spawn point),
    so the prompt must be showing immediately.
    """
    configs = _configs_with_distinct_hard_difficulty(config_factory)
    manager, loop = _build_flow(configs)
    scene = _new_game(manager, loop, difficulty="hard")

    _pump(loop, 2)
    assert scene.tactical.overlays.active_messages() == ["Press L to land here"]


# ---------------------------------------------------------------------------
# Loop mechanics
# ---------------------------------------------------------------------------


def test_step_once_advances_exactly_one_simulation_frame(config_factory):
    """``step_once`` is deterministic: one call, one simulation frame."""
    configs = load_config(config_factory())
    manager, loop = _build_flow(configs)

    counted = []

    class _CountingScene(GameScene):
        def update(self):
            counted.append(1)
            super().update()

    manager.replace(_CountingScene(manager))

    _pump(loop, 40)
    assert len(counted) == 40


def test_quit_event_stops_the_loop(config_factory):
    """A window-close event ends the loop instead of spinning forever."""
    configs = load_config(config_factory())
    manager, loop = _build_flow(configs)

    pygame.event.post(pygame.event.Event(pygame.QUIT))
    assert loop.step_once() is False
    assert not manager.running
    assert loop.step_once() is False


def test_cancel_from_the_dialog_leaves_the_title_screen_running(config_factory):
    """Cancelling the difficulty choice returns to a working title screen."""
    configs = load_config(config_factory())
    manager, loop = _build_flow(configs)

    title = manager._stack[-1]
    _click(loop, title._new_game_btn)
    dialog = manager._stack[-1]
    _click(loop, dialog._cancel_btn)

    assert len(manager._stack) == 1
    assert manager.selected_difficulty is None
    _pump(loop, 5)


def test_cancelling_the_dialog_leaves_no_trace_on_the_title_screen(config_factory):
    """A cancelled dialog must vanish from the window, not linger under the title.

    GIVEN a real loop showing the title screen
    WHEN the player opens the difficulty dialog and cancels it
    THEN no pixel inside the dialog's panel rect still shows dialog colours.

    The title scene used to "clear" by blitting ``resources/title_screen.png``, a
    gradient generated on a transparent surface (three of every four rows had
    alpha 0). That blit composited the title *over* the leftovers of the cancelled
    dialog - panel fill, 2px border, dim overlay - and they stayed on screen
    forever even though the dialog was gone from the stack.
    """
    from src.scenes.difficulty_dialog import (
        _PANEL_BORDER,
        _PANEL_FILL,
        _PANEL_H,
        _PANEL_W,
        _PANEL_X,
        _PANEL_Y,
    )

    configs = load_config(config_factory())
    manager, loop = _build_flow(configs)

    title = manager._stack[-1]
    _click(loop, title._new_game_btn)
    dialog = manager._stack[-1]
    panel = pygame.Rect(_PANEL_X, _PANEL_Y, _PANEL_W, _PANEL_H)

    _click(loop, dialog._cancel_btn)
    _pump(loop, 8)

    screen = pygame.display.get_surface()
    residue = [
        (x, y)
        for y in range(panel.top, panel.bottom, 2)
        for x in range(panel.left, panel.right, 2)
        if screen.get_at((x, y))[:3] in (_PANEL_FILL, _PANEL_BORDER)
    ]
    assert not residue, (
        f"{len(residue)} dialog pixels survived the cancel, e.g. {residue[:5]}"
    )


def test_tactical_text_is_readable_glyphs_not_solid_blocks(config_factory):
    """Overlay/HUD text in a running game must be glyphs, not filled rectangles.

    ``Font.render(antialias=True)`` puts the text colour in the RGB channels of
    every pixel of the glyph box, coverage only in alpha; ``convert()`` throws that
    alpha away and the whole box blits as a solid slab of the text colour. The
    review-era font helper did exactly that, so every string in tactical mode was
    an unreadable block while all tests stayed green (nothing sampled the space
    *between* glyphs).
    """
    configs = load_config(config_factory())
    manager, loop = _build_flow(configs)
    scene = _new_game(manager, loop, difficulty="medium")

    _pump(loop, 2)
    assert scene.tactical.overlays.active_messages() == ["Press L to land here"]

    screen = pygame.display.get_surface()
    banner = (255, 240, 150)  # MessageOverlay banner colour
    region = pygame.Rect(0, 0, VIEW_WIDTH, 90)  # banners are drawn at the top

    # Coarse pass: locate where the banner was drawn at all.
    coarse = [
        (x, y)
        for y in range(region.top, region.bottom, 2)
        for x in range(region.left, region.right, 2)
        if screen.get_at((x, y))[:3] == banner
    ]
    assert coarse, "the landing prompt banner is not being drawn at all"
    bbox = pygame.Rect(min(p[0] for p in coarse), min(p[1] for p in coarse), 0, 0)
    bbox.width = max(p[0] for p in coarse) - bbox.left + 1
    bbox.height = max(p[1] for p in coarse) - bbox.top + 1

    # Fine pass over just that box: what fraction of the banner's own bounding box
    # is solid text colour? Legible antialiased glyphs cover a few percent; the
    # convert() bug covered 100%. Sampling on a stride here would under-count a
    # filled box by exactly that stride, so the box is scanned pixel by pixel.
    filled = sum(
        1
        for y in range(bbox.top, bbox.bottom)
        for x in range(bbox.left, bbox.right)
        if screen.get_at((x, y))[:3] == banner
    )
    coverage = filled / (bbox.width * bbox.height)
    assert coverage < 0.5, (
        f"{coverage:.0%} of the banner's bounding box ({bbox}) is solid text colour - "
        "the string is blitting as a filled rectangle, not glyphs"
    )
