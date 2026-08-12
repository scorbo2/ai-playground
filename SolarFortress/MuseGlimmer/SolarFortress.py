#!/usr/bin/env python3
"""
Solar Fortress - an arcade-inspired shooter game where your spaceship
must shoot holes in a series of force field rings to destroy the enemy
stronghold. Built on pygame-ce.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import random
from enum import IntEnum
from pathlib import Path
from typing import Optional

import pygame
import pygame.locals as pgl

from Fortress import Fortress
from ShieldRing import ShieldRing
from PlayerCraft import PlayerCraft
from HomingMissile import HomingMissile
from EnemyProjectile import EnemyProjectile
from PlayerProjectile import PlayerProjectile
import math
from particles import create_missile_explosion

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Window defaults and constraints
DEFAULT_WINDOW_WIDTH: int = 800
DEFAULT_WINDOW_HEIGHT: int = 600
MIN_WINDOW_WIDTH: int = 640
MIN_WINDOW_HEIGHT: int = 480

# Frame rate
TARGET_FPS: int = 60

# Colors
COLOR_BLACK: tuple[int, int, int] = (0, 0, 0)
COLOR_WHITE: tuple[int, int, int] = (255, 255, 255)
COLOR_GREEN: tuple[int, int, int] = (0, 200, 0)
COLOR_RED: tuple[int, int, int] = (200, 0, 0)
COLOR_CYAN: tuple[int, int, int] = (0, 255, 255)
COLOR_YELLOW: tuple[int, int, int] = (255, 255, 0)

# Font sizes (fixed — do not scale with window)
FONT_SIZE_TITLE: int = 72
FONT_SIZE_SUBTITLE: int = 28
FONT_SIZE_GAME_MODE: int = 64
FONT_SIZE_PAUSE_TITLE: int = 64
FONT_SIZE_PAUSE_LINE: int = 28
FONT_SIZE_GAME_OVER: int = 64

# Pre-created font objects — populated in main() after pygame.init().
# Created once to avoid per-frame SysFont allocation overhead.
FONT_TITLE: pygame.font.Font | None = None
FONT_SUBTITLE: pygame.font.Font | None = None
FONT_GAME_MODE: pygame.font.Font | None = None
FONT_PAUSE_TITLE: pygame.font.Font | None = None
FONT_PAUSE_LINE: pygame.font.Font | None = None
FONT_GAME_OVER: pygame.font.Font | None = None

# Audio config
AUDIO_CONFIG_FILENAME: str = "audio.json"

# Recognised game-event codes (keys into the audio cache)
SUPPORTED_GAME_EVENTS: set[str] = {
    "startup",
    "newGame",
    "pause",
    "unpause",
    "playerShoot",
    "homingSpawn",
    "homingDown",
    "enemyShoot",
    "playerDown",
    "shieldDown",
    "shieldUp",
    "fortressDown",
    "thrusters",
}

# Test-mode auto-exit delay (milliseconds)
TEST_MODE_EXIT_DELAY_MS: int = 250

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger: logging.Logger = logging.getLogger("solar_fortress")

# ---------------------------------------------------------------------------
# Audio subsystem
# ---------------------------------------------------------------------------

class AudioManager:
    """Eagerly loads and caches audio clips keyed by game-event code.

    Missing or unreadable audio files emit a warning but do not crash.
    """

    def __init__(self, source_dir: Path, events: dict[str, str]) -> None:
        """Load every audio file referenced by *events* into memory.

        Parameters
        ----------
        source_dir:
            Directory to resolve relative audio paths against.
        events:
            Mapping of game-event code → audio file path.
        """
        self._cache: dict[str, pygame.mixer.Sound] = {}
        self._loop_channels: dict[str, pygame.mixer.Channel] = {}

        for event_code, audio_path in events.items():
            # Skip anything we don't recognise so callers can extend freely
            if event_code not in SUPPORTED_GAME_EVENTS:
                logger.info("Ignoring unrecognised game event: %s", event_code)
                continue

            resolved = (source_dir / audio_path).resolve()
            try:
                self._cache[event_code] = pygame.mixer.Sound(str(resolved))
            except (pygame.error, FileNotFoundError, PermissionError) as exc:
                logger.warning("Audio file not loadable for event '%s': %s — %s",
                               event_code, resolved, exc)

    def play(self, event_code: str) -> None:
        """Play the sound associated with *event_code*, if cached."""
        sound = self._cache.get(event_code)
        if sound is not None:
            sound.play()

    def play_loop(self, event_code: str) -> None:
        """Play the sound associated with *event_code* in a loop, if cached."""
        sound = self._cache.get(event_code)
        if sound is not None:
            # Stop existing loop to avoid multiple overlapping channels
            self.stop(event_code)
            channel = sound.play(loops=-1)
            if channel is not None:
                self._loop_channels[event_code] = channel

    def stop(self, event_code: str) -> None:
        """Stop a looping sound associated with *event_code*, if playing."""
        channel = self._loop_channels.pop(event_code, None)
        if channel is not None:
            channel.stop()


def _load_audio_config(source_dir: Path) -> Optional[AudioManager]:
    """Parse *audio.json* (if present) and return an ``AudioManager``.

    Returns ``None`` when the config file is absent or unreadable.
    """
    config_path = source_dir / AUDIO_CONFIG_FILENAME
    try:
        with open(config_path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, json.JSONDecodeError, PermissionError) as exc:
        # Silently tolerate a missing or broken config — not an error
        logger.info("No audio config found at %s: %s", config_path, exc)
        return None

    mapping: dict[str, str] = {}
    for entry in data.get("audioMapping", []):
        game_event = entry.get("gameEvent", "")
        audio = entry.get("audio", "")
        if game_event and audio:
            mapping[game_event] = audio

    return AudioManager(source_dir, mapping)


# ---------------------------------------------------------------------------
# Starfield background
# ---------------------------------------------------------------------------

class Starfield:
    """Manages a random starfield background that adapts to window resize."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.stars: list[tuple[int, int, int]] = []
        self._generate_initial(width, height)

    def _generate_initial(self, width: int, height: int) -> None:
        count = random.randint(200, 300)
        for _ in range(count):
            x = random.randint(0, max(1, width - 1))
            y = random.randint(0, max(1, height - 1))
            brightness = random.randint(50, 255)
            self.stars.append((x, y, brightness))

    def ensure_size(self, width: int, height: int) -> None:
        # If window grew, add stars to fill new area
        if width > self.width or height > self.height:
            old_area = self.width * self.height or 1
            new_area = width * height
            # Maintain similar star density
            ratio = new_area / old_area
            target_count = int(len(self.stars) * ratio)
            # Ensure at least a minimum increase
            diff = max(0, target_count - len(self.stars))
            # Add additional stars across the whole new size
            for _ in range(diff):
                x = random.randint(0, max(1, width - 1))
                y = random.randint(0, max(1, height - 1))
                brightness = random.randint(50, 255)
                self.stars.append((x, y, brightness))
            self.width = width
            self.height = height

    def draw(self, surface: pygame.Surface) -> None:
        w, h = surface.get_size()
        # Draw stars; skip those outside current surface
        for x, y, brightness in self.stars:
            if 0 <= x < w and 0 <= y < h:
                surface.set_at((x, y), (brightness, brightness, brightness))


# ---------------------------------------------------------------------------
# Game-state enum
# ---------------------------------------------------------------------------

class GameState(IntEnum):
    """Integer enum representing the game's screen modes.

    Using ``IntEnum`` gives us exhaustiveness checking in type checkers
    and prevents accidental comparison with bare integers.
    """
    TITLE = 0
    GAME = 1
    PAUSE = 2
    GAME_OVER = 3


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------

def _center_rect(rect: pygame.Rect, width: int, height: int) -> pygame.Rect:
    """Return a copy of *rect* centred within (*width*, *height*)."""
    rect = rect.copy()
    rect.center = (width // 2, height // 2)
    return rect


def _render_title_screen(surface: pygame.Surface, width: int, height: int) -> None:
    """Draws the Title Screen."""
    # Background handled by starfield
    title_surf = FONT_TITLE.render("Solar Fortress", True, COLOR_GREEN)
    instructions1 = FONT_SUBTITLE.render("Left/Right: rotate  |  Up: thrust", True, COLOR_CYAN)
    instructions2 = FONT_SUBTITLE.render("F11: toggle fullscreen mode", True, COLOR_CYAN)
    start_surf = FONT_SUBTITLE.render("Press Enter to start", True, COLOR_WHITE)
    exit_surf = FONT_SUBTITLE.render("Press ESC to exit", True, COLOR_WHITE)

    # Centre title in the upper half
    title_rect = title_surf.get_rect()
    title_rect.center = (width // 2, height // 4)
    surface.blit(title_surf, title_rect)

    # Centre sub-lines just below the midpoint
    inst1_rect = instructions1.get_rect()
    inst1_rect.centerx = width // 2
    inst1_rect.top = (height // 2)
    surface.blit(instructions1, inst1_rect)

    inst2_rect = instructions2.get_rect()
    inst2_rect.centerx = width // 2
    inst2_rect.top = inst1_rect.bottom + 10
    surface.blit(instructions2, inst2_rect)

    start_rect = start_surf.get_rect()
    start_rect.centerx = width // 2
    start_rect.top = inst2_rect.bottom + 40
    surface.blit(start_surf, start_rect)

    exit_rect = exit_surf.get_rect()
    exit_rect.centerx = width // 2
    exit_rect.top = start_rect.bottom + 10
    surface.blit(exit_surf, exit_rect)


def _render_game_mode(surface: pygame.Surface, width: int, height: int) -> None:
    """Draw the Game Mode placeholder.

    TODO: Replace this entire function with your actual game rendering logic.
    """
    # Background handled by starfield
    text_surf = FONT_GAME_MODE.render("GAME MODE", True, COLOR_WHITE)
    rect = _center_rect(text_surf.get_rect(), width, height)
    surface.blit(text_surf, rect)


def _render_pause_mode(surface: pygame.Surface, width: int, height: int) -> None:
    """Draw the Pause Mode overlay."""
    # Background handled by starfield
    lines = [
        ("PAUSE", COLOR_WHITE, FONT_PAUSE_TITLE),
        ("PRESS ESC TO RESUME", COLOR_WHITE, FONT_PAUSE_LINE),
        ("PRESS X TO EXIT", COLOR_WHITE, FONT_PAUSE_LINE),
    ]

    y_offset = (height - (len(lines) * 60)) // 2  # rough vertical centre

    for text, color, font in lines:
        surf = font.render(text, True, color)
        rect = surf.get_rect()
        rect.centerx = width // 2
        rect.centery = y_offset + 30
        surface.blit(surf, rect)
        y_offset += 60


def _render_game_over(surface: pygame.Surface, width: int, height: int) -> None:
    """Draw the Game Over placeholder.

    TODO: Wire up your own game-over trigger to transition into this state.
    """
    # Background handled by starfield
    text_surf = FONT_GAME_OVER.render("GAME OVER", True, COLOR_RED)
    rect = _center_rect(text_surf.get_rect(), width, height)
    surface.blit(text_surf, rect)


# ---------------------------------------------------------------------------
# Fullscreen management
# ---------------------------------------------------------------------------

class WindowState:
    """Tracks the window's pre-fullscreen position and dimensions.

    Both *pos* and the size fields are updated every time the user
    enters fullscreen, so restoring always returns to the most recent
    window placement — not the original launch position.
    """

    def __init__(self, width: int, height: int) -> None:
        self.width: int = width
        self.height: int = height
        self.pos: tuple[int, int] = (0, 0)


def _toggle_fullscreen(
    display: pygame.Surface,
    window: WindowState,
) -> pygame.Surface:
    """Switch the display into fullscreen mode at the desktop's native
    resolution.

    The caller is responsible for saving the current window position and
    dimensions into *window* before this function is called.

    Returns the new fullscreen display surface.
    """
    # Passing (0, 0) with FULLSCREEN lets pygame pick the native
    # resolution internally — one atomic call instead of a separate
    # display.Info() round-trip plus set_mode().
    return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)


def _restore_window(
    display: pygame.Surface,
    window: WindowState,
) -> pygame.Surface:
    """Restore the windowed display from a saved ``WindowState``."""
    new_surface = pygame.display.set_mode(
        (window.width, window.height), pygame.RESIZABLE
    )
    pygame.display.set_window_position(window.pos)
    return new_surface


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse and validate command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Solar Fortress — a vector-graphics arcade-inspired shooter game."
    )
    parser.add_argument(
        "--width",
        type=int,
        default=DEFAULT_WINDOW_WIDTH,
        help=f"Starting window width (minimum {MIN_WINDOW_WIDTH}, default {DEFAULT_WINDOW_WIDTH})",
    )
    parser.add_argument(
        "--height",
        type=int,
        default=DEFAULT_WINDOW_HEIGHT,
        help=f"Starting window height (minimum {MIN_WINDOW_HEIGHT}, default {DEFAULT_WINDOW_HEIGHT})",
    )
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        default=False,
        help="Start in fullscreen mode.",
    )
    parser.add_argument(
        "--test",
        action="store_true",
        default=False,
        help="Run a quick smoke-test and exit.",
    )
    parser.add_argument(
        "--nosound",
        action="store_true",
        default=False,
        help="Disable all audio.",
    )

    args = parser.parse_args(argv)

    # Validate dimensions
    if args.width < MIN_WINDOW_WIDTH:
        parser.error(f"--width must be >= {MIN_WINDOW_WIDTH}")
    if args.height < MIN_WINDOW_HEIGHT:
        parser.error(f"--height must be >= {MIN_WINDOW_HEIGHT}")

    return args


# ---------------------------------------------------------------------------
# Main game loop
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> None:
    """Entry point: parse args, initialise pygame, run the game loop."""
    args = _parse_args(argv)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format="%(name)s [%(levelname)s] %(message)s",
    )
    logger.info("Starting Solar Fortress (test=%s, nosound=%s)",
                args.test, args.nosound)

    # Initialise pygame subsystems
    pygame.init()

    # Pre-create font objects once — avoids per-frame SysFont allocation
    global FONT_TITLE, FONT_SUBTITLE, FONT_GAME_MODE
    global FONT_PAUSE_TITLE, FONT_PAUSE_LINE, FONT_GAME_OVER
    FONT_TITLE = pygame.font.SysFont("arial", FONT_SIZE_TITLE)
    FONT_SUBTITLE = pygame.font.SysFont("arial", FONT_SIZE_SUBTITLE)
    FONT_GAME_MODE = pygame.font.SysFont("arial", FONT_SIZE_GAME_MODE)
    FONT_PAUSE_TITLE = pygame.font.SysFont("arial", FONT_SIZE_PAUSE_TITLE)
    FONT_PAUSE_LINE = pygame.font.SysFont("arial", FONT_SIZE_PAUSE_LINE)
    FONT_GAME_OVER = pygame.font.SysFont("arial", FONT_SIZE_GAME_OVER)

    # Audio — skip entirely in test mode or when --nosound is set
    audio: Optional[AudioManager] = None
    if not args.test and not args.nosound:
        pygame.mixer.init()
        source_dir = Path(__file__).resolve().parent
        audio = _load_audio_config(source_dir)

    if audio:
        audio.play("startup")

    # Display
    display = pygame.display.set_mode(
        (args.width, args.height),
        pygame.RESIZABLE,
    )
    pygame.display.set_caption("Solar Fortress")

    # Tell the window manager to enforce our minimum size natively.
    # This avoids the need to fight the WM in the VIDEORESIZE handler,
    # which would cause flicker during fullscreen toggles.
    try:
        pygame.display.set_window_minimum_size(
            MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT
        )
    except AttributeError:
        # Vanilla pygame (non-ce) may lack this API. In that case,
        # the VIDEORESIZE handler still clamps tracked dimensions
        # for game-logic purposes.
        # Weirdly, in my testing with pygame-ce 2.5.7, even pygame-ce
        # doesn't seem to have this. I'm not sure why Qwen is so
        # sure that this function exists.
        logger.info(
            "set_window_minimum_size unavailable — window may be "
            "resized below %sx%s", MIN_WINDOW_WIDTH, MIN_WINDOW_HEIGHT
        )

    window = WindowState(args.width, args.height)
    is_fullscreen: bool = False

    # Starfield background
    current_width, current_height = display.get_size()
    starfield = Starfield(current_width, current_height)

    # If --fullscreen was requested, toggle immediately
    if args.fullscreen:
        # Capture the OS-assigned window position and size before going
        # fullscreen so we can restore to exactly where the user left it.
        window.pos = pygame.display.get_window_position()
        w, h = pygame.display.get_window_size()
        window.width = w
        window.height = h
        display = _toggle_fullscreen(display, window)
        is_fullscreen = True

    # Game objects for Stage 2
    source_dir = Path(__file__).resolve().parent
    fortress = Fortress(
        source_dir / "enemy_neutral.png",
        source_dir / "enemy_charging.png",
        source_dir / "enemy_firing.png",
    )

    # Shield colors - bright as per spec
    SHIELD_RED = (255, 0, 0)
    SHIELD_YELLOW = (255, 255, 0)
    SHIELD_GREEN = (0, 255, 0)

    shield_rings = [
        ShieldRing(diameter=150, color=SHIELD_RED, width=3, rotation_speed_deg_per_frame=1.0, clockwise=True),
        ShieldRing(diameter=200, color=SHIELD_YELLOW, width=2, rotation_speed_deg_per_frame=0.6, clockwise=False),
        ShieldRing(diameter=250, color=SHIELD_GREEN, width=1, rotation_speed_deg_per_frame=0.3, clockwise=True),
    ]

    # Player craft - start near bottom center, safe from initial shields
    player = PlayerCraft(args.width // 2, args.height - 100)

    # Stage 4: homing missiles
    level = 1
    missile_cap = 3 + (level - 1)
    homing_missiles = []
    missile_spawn_timer = 0

    # Stage 5: enemy projectiles
    enemy_projectiles = []
    enemy_shoot_timer = 0
    # Interval decreases each level, minimum 300 frames
    enemy_shoot_interval = max(300, 600 - (level - 1) * 50)

    # Stage 6: player projectiles
    player_projectiles = []
    # Level phase management
    level_phase = "title"  # title, begin, playing, exploding, cleared
    begin_timer = 0
    cleared_timer = 0
    missile_particle_effects = []  # list of particle lists for missile explosions

    clock = pygame.time.Clock()
    state: GameState = GameState.TITLE
    running: bool = True
    thrust_audio_playing: bool = False

    # Test-mode timer
    test_start: int = 0
    if args.test:
        test_start = pygame.time.get_ticks()

    while running:
        # -- Test mode: exit after TEST_MODE_EXIT_DELAY_MS ----------------
        if args.test:
            elapsed = pygame.time.get_ticks() - test_start
            if elapsed >= TEST_MODE_EXIT_DELAY_MS:
                logger.info("Test mode elapsed %d ms — exiting.", elapsed)
                pygame.quit()
                sys.exit(0)

        # -- Event handling ------------------------------------------------
        for event in pygame.event.get():
            if event.type == pgl.QUIT:
                running = False
                continue

            if event.type == pgl.KEYDOWN:
                # F11 — fullscreen toggle (all modes)
                if event.key == pgl.K_F11:
                    if is_fullscreen:
                        display = _restore_window(display, window)
                        is_fullscreen = False
                    else:
                        # Save the current window position and size so we can
                        # restore to exactly where the user left it.
                        window.pos = pygame.display.get_window_position()
                        w, h = pygame.display.get_window_size()
                        window.width = w
                        window.height = h
                        display = _toggle_fullscreen(display, window)
                        is_fullscreen = True
                    continue

                if state == GameState.TITLE:
                    if event.key == pgl.K_RETURN:
                        # Start new game with level begin phase
                        level = 1
                        missile_cap = 3 + (level - 1)
                        enemy_shoot_interval = max(300, 600 - (level - 1) * 50)
                        homing_missiles.clear()
                        enemy_projectiles.clear()
                        player_projectiles.clear()
                        missile_spawn_timer = 0
                        enemy_shoot_timer = 0
                        missile_particle_effects.clear()
                        # Reset fortress
                        fortress.state = "neutral"
                        fortress.charge_timer = 0
                        fortress.fire_timer = 0
                        fortress.current_image = fortress.neutral_image
                        fortress.exploding = False
                        fortress.sprite_alpha = 255
                        fortress.particles = []
                        fortress.explosion_finished = False
                        # Reset shields
                        for ring in shield_rings:
                            ring.segment_timers = [0] * ring.num_segments
                        level_phase = "begin"
                        begin_timer = 120
                        state = GameState.GAME
                        if audio:
                            audio.play("newGame")
                    elif event.key == pgl.K_ESCAPE:
                        running = False

                elif state == GameState.GAME:
                    if event.key == pgl.K_ESCAPE:
                        state = GameState.PAUSE
                        if audio:
                            audio.play("pause")
                    elif event.key == pgl.K_SPACE and level_phase == "playing":
                        # Spawn player projectile if under cap
                        projectile_cap = 0 if level >= 5 else 3 + (level - 1)
                        if projectile_cap == 0 or len(player_projectiles) < projectile_cap:
                            angle_rad = math.radians(player.angle)
                            spawn_x = player.x + math.cos(angle_rad) * 15
                            spawn_y = player.y + math.sin(angle_rad) * 15
                            vx = player.velocity_x + math.cos(angle_rad) * 6
                            vy = player.velocity_y + math.sin(angle_rad) * 6
                            player_projectiles.append(PlayerProjectile(spawn_x, spawn_y, vx, vy))
                            if audio:
                                audio.play("playerShoot")

                elif state == GameState.PAUSE:
                    if event.key == pgl.K_ESCAPE:
                        state = GameState.GAME
                        if audio:
                            audio.play("unpause")
                    elif event.key == pgl.K_x:
                        state = GameState.TITLE

                elif state == GameState.GAME_OVER:
                    if event.key == pgl.K_ESCAPE:
                        state = GameState.TITLE

            if event.type == pgl.VIDEORESIZE:
                # Clamp dimensions to minimum so the window can't be shrunk
                # below a usable size.  Pygame has no native minimum-size API,
                # so we enforce it here by clamping the *tracked* dimensions
                # for game-logic purposes only.
                #
                # CRITICAL: we do NOT call pygame.display.set_mode() here.
                # Doing so fights the window manager, causes the window to
                # snap back, and — during fullscreen toggles — creates a
                # feedback loop of surface recreation that manifests as
                # visible screen flicker.  Instead, we just read the actual
                # surface dimensions after the WM finishes resizing.
                if not is_fullscreen:
                    w, h = display.get_size()
                    clamped_w = max(w, MIN_WINDOW_WIDTH)
                    clamped_h = max(h, MIN_WINDOW_HEIGHT)
                    window.width = clamped_w
                    window.height = clamped_h

        # Stop thrusters audio if not in playing phase
        if not (state == GameState.GAME and level_phase == "playing"):
            if thrust_audio_playing:
                if audio:
                    audio.stop("thrusters")
                thrust_audio_playing = False

        # -- Render --------------------------------------------------------
        width, height = display.get_size()
        # Update starfield for resize
        starfield.ensure_size(width, height)
        # Clear screen and draw starfield background
        display.fill(COLOR_BLACK)
        starfield.draw(display)

        if state == GameState.TITLE:
            _render_title_screen(display, width, height)
        elif state == GameState.GAME:
            width, height = display.get_size()
            center_x = width // 2
            center_y = height // 2

            if level_phase == "begin":
                # Background handled by starfield
                # Render BEGIN LEVEL text
                text = f"BEGIN LEVEL {level}"
                surf = FONT_GAME_MODE.render(text, True, COLOR_WHITE)
                rect = surf.get_rect(center=(width // 2, height // 2))
                display.blit(surf, rect)
                if begin_timer > 0:
                    begin_timer -= 1
                else:
                    # Start playing phase
                    level_phase = "playing"
                    player.reset_position(width, height)
                    homing_missiles.clear()
                    enemy_projectiles.clear()
                    player_projectiles.clear()
                    missile_spawn_timer = 0
                    enemy_shoot_timer = 0
                    fortress.state = "neutral"
                    fortress.charge_timer = 0
                    fortress.fire_timer = 0
                    fortress.current_image = fortress.neutral_image
                    fortress.exploding = False
                    fortress.sprite_alpha = 255
                    fortress.particles = []
                    fortress.explosion_finished = False
                    for ring in shield_rings:
                        ring.segment_timers = [0] * ring.num_segments

            elif level_phase == "playing":
                # Background handled by starfield

                # Update fortress
                spawn_enemy_projectile = fortress.update(width, height)
                fortress.draw(display)

                # Update and draw shield rings
                for ring in shield_rings:
                    reactivated = ring.update()
                    if audio and reactivated:
                        # Play shield up for each reactivated segment (or once per ring)
                        audio.play("shieldUp")
                    ring.draw(display, center_x, center_y)

                # Player update
                keys = pygame.key.get_pressed()
                # Thrusters audio loop control
                thrusting = keys[pgl.K_UP]
                if thrusting:
                    if not thrust_audio_playing:
                        if audio:
                            audio.play_loop("thrusters")
                        thrust_audio_playing = True
                else:
                    if thrust_audio_playing:
                        if audio:
                            audio.stop("thrusters")
                        thrust_audio_playing = False

                player.update(keys, width, height)
                player.draw(display)

                # Update and draw missile explosion particles
                for effect in missile_particle_effects[:]:
                    alive_any = False
                    for p in effect:
                        p.update()
                        if p.alive:
                            alive_any = True
                    if not alive_any:
                        missile_particle_effects.remove(effect)
                    else:
                        for p in effect:
                            p.draw(display)

                # Homing missiles
                missile_spawn_timer += 1
                if missile_spawn_timer >= 180 and len(homing_missiles) < missile_cap:
                    missile_spawn_timer = 0
                    mx = fortress.rect.centerx
                    my = fortress.rect.centery
                    homing_missiles.append(HomingMissile(mx, my))
                    if audio:
                        audio.play("homingSpawn")

                for missile in homing_missiles[:]:
                    missile.update(player.x, player.y)
                    missile.draw(display)
                    if missile.collides_with_player(player.x, player.y, player.collision_radius):
                        if audio:
                            audio.play("playerDown")
                        state = GameState.GAME_OVER
                        break

                # Enemy firing
                enemy_shoot_timer += 1
                if enemy_shoot_timer >= enemy_shoot_interval and fortress.state == "neutral":
                    fortress.start_firing_sequence()
                    enemy_shoot_timer = 0
                    if audio:
                        pass

                if spawn_enemy_projectile:
                    px = fortress.rect.centerx
                    py = fortress.rect.centery
                    enemy_projectiles.append(EnemyProjectile(px, py, player.x, player.y))
                    if audio:
                        audio.play("enemyShoot")

                # Update enemy projectiles
                for proj in enemy_projectiles[:]:
                    proj.update()
                    proj.draw(display)
                    if proj.is_off_screen(width, height):
                        enemy_projectiles.remove(proj)
                        continue
                    if proj.collides_with_player(player.x, player.y, player.collision_radius):
                        if audio:
                            audio.play("playerDown")
                        state = GameState.GAME_OVER
                        break

                # Player projectiles
                for pproj in player_projectiles[:]:
                    pproj.update(width, height)
                    if not pproj.alive:
                        player_projectiles.remove(pproj)
                        continue
                    pproj.draw(display)

                    # Collision with shields
                    hit_shield = False
                    for ring in shield_rings:
                        if ring.hit_by_projectile(pproj.x, pproj.y, center_x, center_y, threshold=6.0):
                            pproj.kill()
                            hit_shield = True
                            if audio:
                                audio.play("shieldDown")
                            break
                    if hit_shield:
                        player_projectiles.remove(pproj)
                        continue

                    # Collision with homing missiles
                    hit_missile = False
                    for missile in homing_missiles[:]:
                        dist = math.hypot(pproj.x - missile.x, pproj.y - missile.y)
                        if dist < pproj.radius + missile.radius:
                            homing_missiles.remove(missile)
                            pproj.kill()
                            player_projectiles.remove(pproj)
                            if audio:
                                audio.play("homingDown")
                            # Create explosion particles for missile
                            missile_particle_effects.append(create_missile_explosion(missile.x, missile.y))
                            hit_missile = True
                            break
                    if hit_missile:
                        continue

                    # Collision with fortress
                    fortress_radius = fortress.rect.width / 2
                    dist_f = math.hypot(pproj.x - fortress.rect.centerx, pproj.y - fortress.rect.centery)
                    if dist_f < fortress_radius + pproj.radius:
                        fortress.start_explosion()
                        pproj.kill()
                        player_projectiles.remove(pproj)
                        if audio:
                            audio.play("fortressDown")
                        level_phase = "exploding"
                        continue

                    # Self collision with player (after immunity)
                    if pproj.can_collide_with_player():
                        if math.hypot(pproj.x - player.x, pproj.y - player.y) < player.collision_radius + pproj.radius:
                            if audio:
                                audio.play("playerDown")
                            state = GameState.GAME_OVER
                            break

                # Player vs shield collision
                for ring in shield_rings:
                    if ring.check_collision(player.x, player.y, center_x, center_y, 20.0):
                        if audio:
                            audio.play("playerDown")
                        state = GameState.GAME_OVER
                        break
                if state == GameState.GAME_OVER:
                    pass
                else:
                    # Player vs fortress collision
                    fortress_radius = fortress.rect.width / 2
                    if math.hypot(player.x - fortress.rect.centerx, player.y - fortress.rect.centery) < player.collision_radius + fortress_radius:
                        if audio:
                            audio.play("playerDown")
                        state = GameState.GAME_OVER

            elif level_phase == "exploding":
                # Background handled by starfield
                fortress.update(width, height)
                fortress.draw(display)
                # Draw static background elements
                for ring in shield_rings:
                    ring.draw(display, center_x, center_y)
                player.draw(display)
                for missile in homing_missiles:
                    missile.draw(display)
                for proj in enemy_projectiles:
                    proj.draw(display)
                for pproj in player_projectiles:
                    pproj.draw(display)
                if fortress.is_explosion_finished():
                    level_phase = "cleared"
                    cleared_timer = 120

            elif level_phase == "cleared":
                # Background handled by starfield
                surf = FONT_GAME_MODE.render("LEVEL CLEARED", True, COLOR_WHITE)
                rect = surf.get_rect(center=(width // 2, height // 2))
                display.blit(surf, rect)
                if cleared_timer > 0:
                    cleared_timer -= 1
                else:
                    # Advance to next level
                    level += 1
                    missile_cap = 3 + (level - 1)
                    enemy_shoot_interval = max(300, 600 - (level - 1) * 50)
                    level_phase = "begin"
                    begin_timer = 120
                    homing_missiles.clear()
                    enemy_projectiles.clear()
                    player_projectiles.clear()
                    missile_spawn_timer = 0
                    enemy_shoot_timer = 0
                    fortress.state = "neutral"
                    fortress.charge_timer = 0
                    fortress.fire_timer = 0
                    fortress.current_image = fortress.neutral_image
                    fortress.exploding = False
                    fortress.sprite_alpha = 255
                    fortress.particles = []
                    fortress.explosion_finished = False
                    for ring in shield_rings:
                        ring.segment_timers = [0] * ring.num_segments
        elif state == GameState.PAUSE:
            _render_pause_mode(display, width, height)
        elif state == GameState.GAME_OVER:
            _render_game_over(display, width, height)

        pygame.display.flip()
        clock.tick(TARGET_FPS)

    pygame.quit()
    sys.exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
