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
import math
import random
import sys
from enum import IntEnum
from pathlib import Path
from typing import Optional

import pygame
import pygame.locals as pgl

from enemy_projectile import (
    CHARGING_DURATION,
    EnemyProjectile,
    FIRING_DURATION,
    PROJECTILE_RADIUS as ENEMY_PROJECTILE_RADIUS,
    compute_spawn_interval,
)
from fortress import Fortress
from homing_missile import HomingMissile, MISSILE_RADIUS, MISSILE_SPAWN_INTERVAL
from player_craft import PlayerCraft
from player_projectile import (
    BONUS_SPEED,
    INVULNERABILITY_FRAMES,
    MAX_TRAVEL_DISTANCE,
    PlayerProjectile,
    compute_projectile_cap,
)
from shield_ring import NUM_SEGMENTS, ShieldRing

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

# Fortress explosion particle constants
FORTRESS_EXPLOSION_COUNT: int = 120
FORTRESS_EXPLOSION_MIN_DIAMETER: int = 6
FORTRESS_EXPLOSION_MAX_DIAMETER: int = 12
FORTRESS_EXPLOSION_MIN_SPEED: float = 5.0
FORTRESS_EXPLOSION_MAX_SPEED: float = 15.0
FORTRESS_EXPLOSION_ALPHA_MIN_DECAY: float = 0.02  # 2 % per frame
FORTRESS_EXPLOSION_ALPHA_MAX_DECAY: float = 0.06  # 6 % per frame
FORTRESS_ALPHA_DECAY: float = 0.01  # 1 % per frame
COLORS_EXPLOSION: list[tuple[int, int, int]] = [
    (255, 255, 0),   # bright yellow
    (255, 60, 0),    # red-orange
    (255, 140, 0),   # orange
]

# Level transition timing
LEVEL_INTRO_DISPLAY_FRAMES: int = 120
LEVEL_INTRO_FADE_FRAMES: int = 60

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
# Game objects (owned by Game Mode, initialised in _init_game_mode)
# ---------------------------------------------------------------------------

FORTRESS: Fortress | None = None
SHIELDS: list[ShieldRing] = []
PLAYER_CRAFT: PlayerCraft | None = None
HOMING_MISSILES: list[HomingMissile] = []
HOMING_SPAWN_TIMER: int = 0
ENEMY_PROJECTILES: list[EnemyProjectile] = []
PLAYER_PROJECTILES: list[PlayerProjectile] = []
# Set to True when spacebar is pressed; consumed during update
SHOOT_REQUESTED: bool = False
# Fortress firing state machine: "idle" | "charging" | "firing"
FORTRESS_FIRE_STATE: str = "idle"
# Counts toward the next firing event
FORTRESS_FIRE_TIMER: int = 0
LEVEL: int = 1

# -- Fortress destruction state --
# "active" = normal gameplay, "exploding" = fortress hit, particles animating,
# "cleared" = "LEVEL CLEARED" text displayed
FORTRESS_DESTRUCTION_STATE: str = "active"
# Explosion particles for fortress destruction
FORTRESS_EXPLOSION_PARTICLES: list[_FortressExplosionParticle] = []
# Fortress sprite alpha during destruction (255 = fully opaque)
FORTRESS_ALPHA: float = 255.0
# Timer for "LEVEL CLEARED" text display
CLEARED_TEXT_TIMER: int = 0

# -- Level transition state --
# "none" = normal gameplay, "intro" = "BEGIN LEVEL N" text on screen
LEVEL_TRANSITION_STATE: str = "none"
# Timer for level intro text
LEVEL_TRANSITION_TIMER: int = 0

# -- Thruster audio --
# True while the looping thruster SFX is actively playing
THRUSTERS_PLAYING: bool = False

# -- Starfield background --
STARFIELD: Starfield | None = None

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger: logging.Logger = logging.getLogger("solar_fortress")

# ---------------------------------------------------------------------------
# Fortress explosion particle
# ---------------------------------------------------------------------------

class _FortressExplosionParticle:
    """A single cosmetic particle from a fortress destruction explosion.

    These particles have no collision detection with any game object.
    They exist purely as a visual effect and self-destruct when their
    alpha reaches zero.
    """

    __slots__ = (
        "x", "y", "vx", "vy", "radius", "color", "alpha", "alpha_decay",
    )

    def __init__(self, x: float, y: float) -> None:
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(
            FORTRESS_EXPLOSION_MIN_SPEED,
            FORTRESS_EXPLOSION_MAX_SPEED,
        )
        self.x: float = x
        self.y: float = y
        self.vx: float = speed * math.cos(angle)
        self.vy: float = speed * math.sin(angle)
        self.radius: float = random.uniform(
            FORTRESS_EXPLOSION_MIN_DIAMETER / 2,
            FORTRESS_EXPLOSION_MAX_DIAMETER / 2,
        )
        self.color: tuple[int, int, int] = random.choice(COLORS_EXPLOSION)
        self.alpha: float = 255.0
        self.alpha_decay: float = random.uniform(
            FORTRESS_EXPLOSION_ALPHA_MIN_DECAY,
            FORTRESS_EXPLOSION_ALPHA_MAX_DECAY,
        )

    def update(self) -> bool:
        """Advance position and fade alpha. Returns True if still alive."""
        self.x += self.vx
        self.y += self.vy
        self.alpha -= self.alpha_decay * 255.0
        if self.alpha <= 0:
            self.alpha = 0.0
            return False
        return True

    def render(self, surface: pygame.Surface) -> None:
        """Draw the particle as a semi-transparent colored circle."""
        size = int(self.radius * 2) + 2
        img = pygame.Surface((size, size), pygame.SRCALPHA)
        center = (size // 2, size // 2)
        r = self.radius + 0.5
        color_with_alpha = (*self.color, int(self.alpha))
        pygame.draw.circle(img, color_with_alpha, center, r)
        rect = img.get_rect(center=(round(self.x), round(self.y)))
        surface.blit(img, rect)


# ---------------------------------------------------------------------------
# Starfield background
# ---------------------------------------------------------------------------

class Starfield:
    """A random starfield of single-pixel stars.

    Generates 200–300 stars with random monochromatic brightness
    (dark gray to white).  Regenerates stars when the display
    dimensions change (resize or fullscreen toggle).
    """

    def __init__(self) -> None:
        self._width: int = 0
        self._height: int = 0
        # List of (x, y, brightness) where brightness is 0–255
        self._stars: list[tuple[int, int, int]] = []

    def update(self, width: int, height: int) -> None:
        """Regenerate stars if display dimensions changed."""
        if width == self._width and height == self._height:
            return
        self._width = width
        self._height = height
        count = random.randint(200, 300)
        self._stars = [
            (
                random.randint(0, width - 1),
                random.randint(0, height - 1),
                random.randint(30, 255),
            )
            for _ in range(count)
        ]

    def render(self, surface: pygame.Surface) -> None:
        """Draw all stars as single-pixel dots on *surface*."""
        for sx, sy, brightness in self._stars:
            surface.set_at((sx, sy), (brightness, brightness, brightness))


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
        # Track the currently playing loop so we can stop it cleanly
        self._loop_sound: pygame.mixer.Sound | None = None
        self._loop_channel: pygame.mixer.Channel | None = None

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
        """Start looping playback for *event_code*, if cached.

        If a loop is already playing, it is stopped first so only one
        loop can be active at a time.
        """
        sound = self._cache.get(event_code)
        if sound is not None:
            self.stop_loop()
            self._loop_sound = sound
            self._loop_channel = sound.play(-1)  # -1 = infinite loop

    def stop_loop(self) -> None:
        """Stop any currently playing loop."""
        if self._loop_channel is not None:
            self._loop_channel.stop()
            self._loop_channel = None
            self._loop_sound = None


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


def _stop_thrusters_audio(audio: Optional[AudioManager]) -> None:
    """Stop the looping thruster sound and reset the playing flag.

    Must be called whenever the player stops thrusting, the craft is
    destroyed, the game is paused, or a level transition begins.
    """
    global THRUSTERS_PLAYING
    if THRUSTERS_PLAYING and audio is not None:
        audio.stop_loop()
        THRUSTERS_PLAYING = False


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
    surface.fill(COLOR_BLACK)
    if STARFIELD is not None:
        STARFIELD.render(surface)

    title_surf = FONT_TITLE.render("Solar Fortress", True, COLOR_GREEN)
    instructions1 = FONT_SUBTITLE.render("Left/Right: rotate  |  Up: thrust  |  Space: shoot", True, COLOR_CYAN)
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


def _init_game_mode(level: int = 1) -> None:
    """Create or reset the fortress and shield rings for a new level.

    Called when the player enters Game Mode from the title screen
    or when a level is cleared.

    Parameters
    ----------
    level :
        The 1-based level number. Defaults to 1 (first playthrough).
    """
    global FORTRESS, SHIELDS, PLAYER_CRAFT
    global HOMING_MISSILES, HOMING_SPAWN_TIMER
    global ENEMY_PROJECTILES, FORTRESS_FIRE_STATE, FORTRESS_FIRE_TIMER
    global PLAYER_PROJECTILES, SHOOT_REQUESTED
    global FORTRESS_DESTRUCTION_STATE, FORTRESS_EXPLOSION_PARTICLES
    global FORTRESS_ALPHA, CLEARED_TEXT_TIMER
    global LEVEL_TRANSITION_STATE, LEVEL_TRANSITION_TIMER
    global THRUSTERS_PLAYING
    global LEVEL

    LEVEL = level
    HOMING_MISSILES = []
    HOMING_SPAWN_TIMER = 0
    ENEMY_PROJECTILES = []
    PLAYER_PROJECTILES = []
    SHOOT_REQUESTED = False
    FORTRESS_FIRE_STATE = "idle"
    FORTRESS_FIRE_TIMER = 0
    FORTRESS_DESTRUCTION_STATE = "active"
    FORTRESS_EXPLOSION_PARTICLES = []
    FORTRESS_ALPHA = 255.0
    CLEARED_TEXT_TIMER = 0
    LEVEL_TRANSITION_STATE = "intro"
    LEVEL_TRANSITION_TIMER = 0
    THRUSTERS_PLAYING = False

    source_dir = Path(__file__).resolve().parent

    FORTRESS = Fortress(source_dir)
    FORTRESS.reset()

    # Three concentric rings: inner (red), middle (yellow), outer (green).
    # Spec: inner=150px CW @1deg/f, middle=200px CCW @0.6deg/f,
    # outer=250px CW @0.3deg/f.
    SHIELDS = [
        ShieldRing(diameter=150, rotation_speed=1.0,   color=COLOR_RED,   line_width=3),
        ShieldRing(diameter=200, rotation_speed=-0.6,  color=COLOR_YELLOW, line_width=2),
        ShieldRing(diameter=250, rotation_speed=0.3,   color=COLOR_GREEN, line_width=1),
    ]

    # Player craft spawns within 100px of a random screen edge.
    # We pick one of four edges, then place the craft along it.
    # Initial position is approximate; the craft wraps on first update.
    edge = random.choice(["top", "bottom", "left", "right"])
    if edge == "top":
        spawn_x = random.uniform(100, DEFAULT_WINDOW_WIDTH - 100)
        spawn_y = random.uniform(0, 100)
    elif edge == "bottom":
        spawn_x = random.uniform(100, DEFAULT_WINDOW_WIDTH - 100)
        spawn_y = random.uniform(DEFAULT_WINDOW_HEIGHT - 100, DEFAULT_WINDOW_HEIGHT)
    elif edge == "left":
        spawn_x = random.uniform(0, 100)
        spawn_y = random.uniform(100, DEFAULT_WINDOW_HEIGHT - 100)
    else:  # right
        spawn_x = random.uniform(DEFAULT_WINDOW_WIDTH - 100, DEFAULT_WINDOW_WIDTH)
        spawn_y = random.uniform(100, DEFAULT_WINDOW_HEIGHT - 100)

    PLAYER_CRAFT = PlayerCraft(spawn_x, spawn_y)


def _render_game_mode(surface: pygame.Surface, width: int, height: int) -> None:
    """Draw the fortress, shield rings, missiles, projectiles, and craft.

    Also handles level transition text, fortress destruction effects,
    and the "LEVEL CLEARED" overlay.
    """
    surface.fill(COLOR_BLACK)

    if STARFIELD is not None:
        STARFIELD.render(surface)

    if FORTRESS is not None:
        # During destruction, render fortress with fading alpha
        if FORTRESS_DESTRUCTION_STATE == "exploding" and FORTRESS_ALPHA > 0:
            _render_fortress_with_alpha(surface, FORTRESS, FORTRESS_ALPHA)
        elif FORTRESS_DESTRUCTION_STATE != "exploding":
            FORTRESS.render(surface)

        # Fortress explosion particles
        if FORTRESS_DESTRUCTION_STATE == "exploding":
            for particle in FORTRESS_EXPLOSION_PARTICLES:
                particle.render(surface)

    for shield in SHIELDS:
        shield.render(surface)

    for miss in HOMING_MISSILES:
        miss.render(surface)

    for proj in ENEMY_PROJECTILES:
        proj.render(surface)

    for proj in PLAYER_PROJECTILES:
        proj.render(surface)

    if PLAYER_CRAFT is not None and not PLAYER_CRAFT.destroyed:
        PLAYER_CRAFT.render(surface)

    # --- Level transition intro ("BEGIN LEVEL N") --------------------------
    if LEVEL_TRANSITION_STATE == "intro":
        _render_level_intro(surface, width, height)

    # --- "LEVEL CLEARED" overlay -------------------------------------------
    if FORTRESS_DESTRUCTION_STATE == "cleared":
        _render_cleared_text(surface, width, height)


def _render_fortress_with_alpha(
    surface: pygame.Surface,
    fortress: Fortress,
    alpha: float,
) -> None:
    """Render the fortress sprite with a given alpha value.

    Creates a temporary surface with per-pixel alpha so the fortress
    can fade during its destruction animation.
    """
    sprite = fortress.sprite
    faded = pygame.Surface(sprite.get_size(), pygame.SRCALPHA)
    faded.blit(sprite, (0, 0))
    # Apply alpha to the entire surface
    faded.set_alpha(int(alpha))
    rect = faded.get_rect(center=fortress.center)
    surface.blit(faded, rect)


def _render_level_intro(
    surface: pygame.Surface, width: int, height: int,
) -> None:
    """Render the 'BEGIN LEVEL N' text with fade-out.

    Text is fully opaque for LEVEL_INTRO_DISPLAY_FRAMES, then fades
    out over LEVEL_INTRO_FADE_FRAMES.
    """
    text = f"BEGIN LEVEL {LEVEL}"
    surf = FONT_GAME_MODE.render(text, True, COLOR_WHITE)
    rect = _center_rect(surf.get_rect(), width, height)

    # Compute alpha: fully opaque during display, then fades
    if LEVEL_TRANSITION_TIMER <= LEVEL_INTRO_DISPLAY_FRAMES:
        alpha = 255
    else:
        fade_progress = (
            LEVEL_TRANSITION_TIMER - LEVEL_INTRO_DISPLAY_FRAMES
        ) / LEVEL_INTRO_FADE_FRAMES
        alpha = max(0, int(255 * (1 - fade_progress)))

    # Create alpha-blended surface for the text
    text_surf = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
    text_surf.blit(surf, (0, 0))
    text_surf.set_alpha(alpha)
    surface.blit(text_surf, rect)


def _render_cleared_text(
    surface: pygame.Surface, width: int, height: int,
) -> None:
    """Render the 'LEVEL CLEARED' text during the post-destruction pause."""
    text = "LEVEL CLEARED"
    surf = FONT_GAME_MODE.render(text, True, COLOR_WHITE)
    rect = _center_rect(surf.get_rect(), width, height)
    surface.blit(surf, rect)


def _render_pause_mode(surface: pygame.Surface, width: int, height: int) -> None:
    """Draw the Pause Mode overlay."""
    surface.fill(COLOR_BLACK)
    if STARFIELD is not None:
        STARFIELD.render(surface)

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
    """Draw the Game Over screen: starfield background with red text."""
    surface.fill(COLOR_BLACK)
    if STARFIELD is not None:
        STARFIELD.render(surface)

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
    # Game-state globals mutated in the main loop
    global HOMING_MISSILES, HOMING_SPAWN_TIMER, LEVEL
    global ENEMY_PROJECTILES, FORTRESS_FIRE_STATE, FORTRESS_FIRE_TIMER
    global PLAYER_PROJECTILES, SHOOT_REQUESTED
    global FORTRESS_DESTRUCTION_STATE, FORTRESS_EXPLOSION_PARTICLES
    global FORTRESS_ALPHA, CLEARED_TEXT_TIMER
    global LEVEL_TRANSITION_STATE, LEVEL_TRANSITION_TIMER
    global THRUSTERS_PLAYING
    global STARFIELD
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

    # Starfield background — initialised once, regenerated on resize
    STARFIELD = Starfield()

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

    clock = pygame.time.Clock()
    state: GameState = GameState.TITLE
    running: bool = True

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
                        _init_game_mode()
                        state = GameState.GAME
                        if audio:
                            audio.play("newGame")
                    elif event.key == pgl.K_ESCAPE:
                        running = False

                elif state == GameState.GAME:
                    if event.key == pgl.K_ESCAPE:
                        _stop_thrusters_audio(audio)
                        state = GameState.PAUSE
                        if audio:
                            audio.play("pause")
                    elif event.key == pgl.K_SPACE:
                        SHOOT_REQUESTED = True

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

        # -- Update --------------------------------------------------------
        width, height = display.get_size()

        # Starfield tracks resize / fullscreen changes
        if STARFIELD is not None:
            STARFIELD.update(width, height)

        if state == GameState.GAME and FORTRESS is not None:
            # --- Level transition intro ("BEGIN LEVEL N") ------------------
            if LEVEL_TRANSITION_STATE == "intro":
                # Thrusters stop during level intro (gameplay is frozen)
                _stop_thrusters_audio(audio)
                LEVEL_TRANSITION_TIMER += 1
                # Still update fortress/shields for centering on resize
                FORTRESS.update(width, height)
                for shield in SHIELDS:
                    shield.update(FORTRESS.center)
                # After display + fade period, transition to active gameplay
                if LEVEL_TRANSITION_TIMER >= (
                    LEVEL_INTRO_DISPLAY_FRAMES + LEVEL_INTRO_FADE_FRAMES
                ):
                    LEVEL_TRANSITION_STATE = "none"
                    LEVEL_TRANSITION_TIMER = 0
                # Skip all gameplay updates during intro
            # --- Fortress destruction sequence -----------------------------
            elif FORTRESS_DESTRUCTION_STATE == "exploding":
                # All other animation stops during explosion.
                # Only update fortress position (for resize tracking),
                # shield rotation (disabled segments keep rotating),
                # and explosion particles.
                # Thrusters stop because gameplay is frozen
                _stop_thrusters_audio(audio)
                FORTRESS.update(width, height)
                for shield in SHIELDS:
                    shield.update(FORTRESS.center)

                # Tick down explosion particles
                FORTRESS_EXPLOSION_PARTICLES = [
                    p for p in FORTRESS_EXPLOSION_PARTICLES if p.update()
                ]

                # Fade fortress sprite alpha
                FORTRESS_ALPHA -= FORTRESS_ALPHA_DECAY * 255.0
                if FORTRESS_ALPHA < 0:
                    FORTRESS_ALPHA = 0.0

                # When fortress is fully invisible, show "LEVEL CLEARED"
                if FORTRESS_ALPHA <= 0:
                    FORTRESS_DESTRUCTION_STATE = "cleared"
                    CLEARED_TEXT_TIMER = 0

            elif FORTRESS_DESTRUCTION_STATE == "cleared":
                # Display "LEVEL CLEARED" text for 120 frames, then advance
                FORTRESS.update(width, height)
                for shield in SHIELDS:
                    shield.update(FORTRESS.center)
                CLEARED_TEXT_TIMER += 1
                if CLEARED_TEXT_TIMER >= 120:
                    # Advance to next level
                    _init_game_mode(LEVEL + 1)
                    if audio:
                        audio.play("newGame")
            # --- Normal gameplay -------------------------------------------
            else:
                FORTRESS.update(width, height)
                for shield in SHIELDS:
                    shield.update(FORTRESS.center)

                # Shield segment reactivation audio
                for shield in SHIELDS:
                    if shield.any_segment_just_reactivated():
                        if audio:
                            audio.play("shieldUp")

                # --- Player projectile spawning ----------------------------
                # Spacebar triggers one projectile per press.
                # Cap: 3 on level 1, +1 per level, unlimited from level 5.
                if SHOOT_REQUESTED and PLAYER_CRAFT is not None:
                    SHOOT_REQUESTED = False
                    cap = compute_projectile_cap(LEVEL)
                    active_count = len([
                        p for p in PLAYER_PROJECTILES if not p.expired
                    ])
                    if cap is None or active_count < cap:
                        angle_rad = math.radians(PLAYER_CRAFT.angle)
                        # Spawn at ship nose: 15px forward from center
                        spawn_x = (
                            PLAYER_CRAFT.x + 15 * math.cos(angle_rad)
                        )
                        spawn_y = (
                            PLAYER_CRAFT.y + 15 * math.sin(angle_rad)
                        )
                        # Velocity = ship velocity + 6 px/frame forward
                        pvx = (
                            PLAYER_CRAFT.vx
                            + BONUS_SPEED * math.cos(angle_rad)
                        )
                        pvy = (
                            PLAYER_CRAFT.vy
                            + BONUS_SPEED * math.sin(angle_rad)
                        )
                        PLAYER_PROJECTILES.append(
                            PlayerProjectile(spawn_x, spawn_y, pvx, pvy)
                        )
                        if audio:
                            audio.play("playerShoot")

                # --- Player projectile update ------------------------------
                for proj in PLAYER_PROJECTILES:
                    proj.update(width, height)

                # Remove expired projectiles (exceeded travel range)
                PLAYER_PROJECTILES = [
                    p for p in PLAYER_PROJECTILES if not p.expired
                ]

                # --- Player projectile vs. homing missiles -----------------
                for proj in PLAYER_PROJECTILES:
                    if proj.expired:
                        continue
                    for miss in HOMING_MISSILES:
                        if miss.destroyed:
                            continue
                        if proj.collides_with_point(
                            miss.x, miss.y, MISSILE_RADIUS,
                        ):
                            miss.destroy()
                            proj._distance_traveled = MAX_TRAVEL_DISTANCE
                            if audio:
                                audio.play("homingDown")
                            break

                # --- Player projectile vs. shield segments -----------------
                for proj in PLAYER_PROJECTILES:
                    if proj.expired:
                        continue
                    for shield in SHIELDS:
                        if shield.segment_hit(proj.x, proj.y):
                            proj._distance_traveled = MAX_TRAVEL_DISTANCE
                            if audio:
                                audio.play("shieldDown")
                            break

                # --- Player projectile vs. enemy projectiles ---------------
                for proj in PLAYER_PROJECTILES:
                    if proj.expired:
                        continue
                    for eproj in ENEMY_PROJECTILES:
                        if proj.collides_with_point(
                            eproj.x, eproj.y, ENEMY_PROJECTILE_RADIUS,
                        ):
                            # Player projectile removed; enemy unaffected
                            proj._distance_traveled = MAX_TRAVEL_DISTANCE
                            break

                # --- Player projectile vs. fortress ------------------------
                for proj in PLAYER_PROJECTILES:
                    if proj.expired:
                        continue
                    if proj.collides_with_point(
                        FORTRESS.center[0], FORTRESS.center[1],
                        FORTRESS.hit_radius,
                    ):
                        # Fortress is destroyed!
                        proj._distance_traveled = MAX_TRAVEL_DISTANCE
                        FORTRESS_DESTRUCTION_STATE = "exploding"
                        FORTRESS_ALPHA = 255.0
                        FORTRESS_EXPLOSION_PARTICLES = [
                            _FortressExplosionParticle(
                                FORTRESS.center[0], FORTRESS.center[1]
                            )
                            for _ in range(FORTRESS_EXPLOSION_COUNT)
                        ]
                        if audio:
                            audio.play("fortressDown")
                        break

                # --- Player projectile vs. own craft -----------------------
                # Only after INVULNERABILITY_FRAMES have elapsed.
                if PLAYER_CRAFT is not None and not PLAYER_CRAFT.destroyed:
                    for proj in PLAYER_PROJECTILES:
                        if proj.expired:
                            continue
                        if proj.age < INVULNERABILITY_FRAMES:
                            continue
                        if proj.collides_with_point(
                            PLAYER_CRAFT.x, PLAYER_CRAFT.y,
                            PLAYER_CRAFT.collision_radius,
                        ):
                            PLAYER_CRAFT.destroy()
                            state = GameState.GAME_OVER
                            if audio:
                                audio.play("playerDown")
                            break

                # --- Homing missile spawning --------------------------------
                HOMING_SPAWN_TIMER += 1
                homing_cap = 2 + LEVEL  # 3 on level 1, 4 on level 2, etc.
                active_missiles = [
                    m for m in HOMING_MISSILES if not m.destroyed
                ]
                if (
                    HOMING_SPAWN_TIMER >= MISSILE_SPAWN_INTERVAL
                    and len(active_missiles) < homing_cap
                ):
                    HOMING_SPAWN_TIMER = 0
                    miss = HomingMissile(
                        FORTRESS.center[0], FORTRESS.center[1]
                    )
                    HOMING_MISSILES.append(miss)
                    if audio:
                        audio.play("homingSpawn")

                # --- Homing missile update ----------------------------------
                for miss in HOMING_MISSILES:
                    if PLAYER_CRAFT is not None and not PLAYER_CRAFT.destroyed:
                        miss.update(PLAYER_CRAFT.x, PLAYER_CRAFT.y)
                    else:
                        miss.update(miss.x, miss.y)

                # Remove missiles whose explosion particles have all faded
                HOMING_MISSILES = [
                    m for m in HOMING_MISSILES
                    if not m.destroyed or not m.explosion_done
                ]

                # --- Fortress firing sequence --------------------------------
                fire_interval = compute_spawn_interval(LEVEL)

                if FORTRESS_FIRE_STATE == "idle":
                    FORTRESS_FIRE_TIMER += 1
                    if FORTRESS_FIRE_TIMER >= fire_interval:
                        FORTRESS_FIRE_STATE = "charging"
                        FORTRESS_FIRE_TIMER = 0
                        FORTRESS.state = "charging"

                elif FORTRESS_FIRE_STATE == "charging":
                    FORTRESS_FIRE_TIMER += 1
                    if FORTRESS_FIRE_TIMER >= CHARGING_DURATION:
                        FORTRESS_FIRE_STATE = "firing"
                        FORTRESS_FIRE_TIMER = 0
                        FORTRESS.state = "firing"

                elif FORTRESS_FIRE_STATE == "firing":
                    FORTRESS_FIRE_TIMER += 1
                    if FORTRESS_FIRE_TIMER == 1:
                        if PLAYER_CRAFT is not None:
                            dx = PLAYER_CRAFT.x - FORTRESS.center[0]
                            dy = PLAYER_CRAFT.y - FORTRESS.center[1]
                            angle = math.atan2(dy, dx)
                            proj = EnemyProjectile(
                                FORTRESS.center[0],
                                FORTRESS.center[1],
                                angle,
                            )
                            ENEMY_PROJECTILES.append(proj)
                            if audio:
                                audio.play("enemyShoot")
                    if FORTRESS_FIRE_TIMER >= FIRING_DURATION:
                        FORTRESS_FIRE_STATE = "idle"
                        FORTRESS_FIRE_TIMER = 0
                        FORTRESS.state = "neutral"

                # --- Enemy projectile update & cleanup -------------------------
                for proj in ENEMY_PROJECTILES:
                    proj.update()

                width, height = display.get_size()
                ENEMY_PROJECTILES = [
                    p for p in ENEMY_PROJECTILES
                    if not p.off_screen(width, height)
                ]

                # --- Player craft update -----------------------------------
                if PLAYER_CRAFT is not None and not PLAYER_CRAFT.destroyed:
                    PLAYER_CRAFT.update(width, height)

                    # Craft vs. homing missiles
                    for miss in HOMING_MISSILES:
                        if miss.collides_with_craft(
                            PLAYER_CRAFT.x, PLAYER_CRAFT.y,
                            PLAYER_CRAFT.collision_radius,
                        ):
                            PLAYER_CRAFT.destroy()
                            state = GameState.GAME_OVER
                            if audio:
                                audio.play("playerDown")
                            break

                    # Craft vs. shield segments
                    if not PLAYER_CRAFT.destroyed:
                        for shield in SHIELDS:
                            dist = shield.min_distance_to_active_segment(
                                PLAYER_CRAFT.x, PLAYER_CRAFT.y,
                            )
                            if dist <= PLAYER_CRAFT.collision_radius:
                                PLAYER_CRAFT.destroy()
                                state = GameState.GAME_OVER
                                if audio:
                                    audio.play("playerDown")
                                break

                    # Craft vs. fortress bounding circle
                    if not PLAYER_CRAFT.destroyed:
                        dx = PLAYER_CRAFT.x - FORTRESS.center[0]
                        dy = PLAYER_CRAFT.y - FORTRESS.center[1]
                        dist_to_fortress = math.hypot(dx, dy)
                        if dist_to_fortress <= (
                            PLAYER_CRAFT.collision_radius + FORTRESS.hit_radius
                        ):
                            PLAYER_CRAFT.destroy()
                            state = GameState.GAME_OVER
                            if audio:
                                audio.play("playerDown")

                    # Craft vs. enemy projectiles
                    if not PLAYER_CRAFT.destroyed:
                        for proj in ENEMY_PROJECTILES:
                            if proj.collides_with_craft(
                                PLAYER_CRAFT.x, PLAYER_CRAFT.y,
                                PLAYER_CRAFT.collision_radius,
                            ):
                                PLAYER_CRAFT.destroy()
                                state = GameState.GAME_OVER
                                if audio:
                                    audio.play("playerDown")
                                break

                # --- Thruster audio (looped) --------------------------------
                # Start looping thruster SFX while the player holds Up arrow.
                # Stop on key release, craft destruction, or level transition.
                if (
                    PLAYER_CRAFT is not None
                    and not PLAYER_CRAFT.destroyed
                    and PLAYER_CRAFT.is_thrusting
                    and not THRUSTERS_PLAYING
                ):
                    if audio:
                        audio.play_loop("thrusters")
                        THRUSTERS_PLAYING = True
                elif (
                    THRUSTERS_PLAYING
                    and (
                        PLAYER_CRAFT is None
                        or PLAYER_CRAFT.destroyed
                        or not PLAYER_CRAFT.is_thrusting
                    )
                ):
                    _stop_thrusters_audio(audio)

        # -- Render --------------------------------------------------------

        if state == GameState.TITLE:
            _render_title_screen(display, width, height)
        elif state == GameState.GAME:
            _render_game_mode(display, width, height)
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
