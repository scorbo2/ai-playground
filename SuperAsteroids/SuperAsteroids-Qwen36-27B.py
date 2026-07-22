#!/usr/bin/env python3
"""
SuperAsteroids — Stage 3: Asteroid Spawning + Movement

A derivative of the classic Asteroids arcade game, built with pygame-ce.
Stage 3 adds asteroids with irregular polygon shapes, tumbling rotation,
random movement, screen wrapping, safe-zone spawning, and resize-aware
forced wrapping.
"""

import math
import random
import sys
import pygame

# ─────────────────────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Window dimensions
INITIAL_WINDOW_WIDTH = 800
INITIAL_WINDOW_HEIGHT = 600
MIN_WINDOW_WIDTH = 640
MIN_WINDOW_HEIGHT = 480

# Framerate
TARGET_FPS = 60

# Colors
COLOR_BLACK = (0, 0, 0)
COLOR_WHITE = (255, 255, 255)
COLOR_LIGHT_GRAY = (192, 192, 192)

# Game modes (state machine states)
MODE_TITLE = "TITLE"
MODE_GAME = "GAME"
MODE_PAUSE = "PAUSE"
MODE_GAMEOVER = "GAMEOVER"

# Test mode duration in milliseconds
TEST_MODE_DELAY_MS = 100

# Font sizes (None = default pygame font)
FONT_SIZE_LARGE = 72
FONT_SIZE_MEDIUM = 48
FONT_SIZE_SMALL = 36

# ── Ship constants ──────────────────────────────────────────────────────────

# Ship geometry (elongated triangle)
SHIP_WIDTH = 20          # pixels wide at the base
SHIP_HEIGHT = 30         # pixels tall from tip to base
SHIP_RADIUS = 10         # approximate collision radius (half of width)

# Ship rotation
SHIP_ROTATION_SPEED = 5  # degrees per frame

# Ship thrust
SHIP_THRUST_ACCELERATION = 0.3   # pixels per frame squared
SHIP_MAX_SPEED = 8               # pixels per frame
SHIP_FRICTION = 0.98             # multiplier per frame when not thrusting

# Level text fade
LEVEL_TEXT_DURATION_FRAMES = 120  # 2 seconds at 60 FPS

# ── Asteroid constants ──────────────────────────────────────────────────────

# Asteroid sizes
ASTEROID_LARGE_RADIUS = 40        # maximum asteroid radius (pixels)
ASTEROID_SMALL_RADIUS = 15        # minimum asteroid radius before destruction
ASTEROID_SPLIT_DIVISOR = 1.5      # radius divisor when splitting

# Asteroid movement
ASTEROID_MIN_SPEED = 1.5          # pixels per frame
ASTEROID_MAX_SPEED = 2.5          # pixels per frame
ASTEROID_SPEED_INCREMENT = 0.3    # speed increase per level

# Asteroid tumbling (rotation)
ASTEROID_LARGE_ROTATION_SPEED = 1    # degrees per frame (at LARGE_RADIUS)
ASTEROID_SMALL_ROTATION_SPEED = 10   # degrees per frame (at SMALL_RADIUS)

# Asteroid spawning
ASTEROID_LEVEL1_COUNT = 5                 # starting asteroids on level 1
ASTEROID_SPAWN_EXCLUSION_RADIUS = 200     # minimum distance from ship (pixels)
ASTEROID_MIN_VERTICES = 8                 # minimum polygon vertices
ASTEROID_MAX_VERTICES = 14                # maximum polygon vertices
ASTEROID_RADIUS_VARIATION = 0.15          # ±15% radius variation per vertex

# Asteroid fill colors (brown / beige palette)
ASTEROID_FILL_COLORS = [
    (139, 119, 101),   # brown
    (160, 140, 120),   # warm gray-brown
    (188, 170, 145),   # beige
    (166, 148, 125),   # tan
    (150, 130, 110),   # dark beige
    (175, 155, 135),   # light brown
    (145, 125, 105),   # medium brown
    (190, 175, 155),   # pale beige
]


# ─────────────────────────────────────────────────────────────────────────────
# SHIP CLASS
# ─────────────────────────────────────────────────────────────────────────────

class Ship:
    """Player-controlled spacecraft.

    Rendered as an elongated triangle (20 px wide, 30 px tall) with a white
    outline and light gray fill. Supports rotation, thrust, friction, and
    screen wrapping.
    """

    def __init__(self):
        """Initialize ship with default position and zero velocity."""
        self.x = 0.0
        self.y = 0.0
        self.angle = 0.0       # degrees, 0 = pointing up, clockwise positive
        self.vx = 0.0          # velocity x component
        self.vy = 0.0          # velocity y component

    # ── Reset ────────────────────────────────────────────────────────────

    def reset(self, x, y):
        """Reset ship to a given position with zero velocity, pointing up.

        Args:
            x: Horizontal position in screen coordinates.
            y: Vertical position in screen coordinates.
        """
        self.x = float(x)
        self.y = float(y)
        self.angle = 0.0
        self.vx = 0.0
        self.vy = 0.0

    # ── Update ───────────────────────────────────────────────────────────

    def update(self, keys, screen_width, screen_height):
        """Update ship physics based on held keys and screen boundaries.

        Args:
            keys: Result of pygame.key.get_pressed().
            screen_width: Current window width in pixels.
            screen_height: Current window height in pixels.
        """
        # Rotation
        if keys[pygame.K_LEFT]:
            self.angle -= SHIP_ROTATION_SPEED
        if keys[pygame.K_RIGHT]:
            self.angle += SHIP_ROTATION_SPEED

        # Normalize angle to [0, 360)
        self.angle = self.angle % 360

        # Thrust
        if keys[pygame.K_UP]:
            # Convert angle to radians; 0° = up = negative Y direction
            angle_rad = math.radians(self.angle - 90)
            self.vx += SHIP_THRUST_ACCELERATION * math.cos(angle_rad)
            self.vy += SHIP_THRUST_ACCELERATION * math.sin(angle_rad)

            # Clamp to max speed
            speed = math.hypot(self.vx, self.vy)
            if speed > SHIP_MAX_SPEED:
                scale = SHIP_MAX_SPEED / speed
                self.vx *= scale
                self.vy *= scale
        else:
            # Apply friction when not thrusting
            self.vx *= SHIP_FRICTION
            self.vy *= SHIP_FRICTION

            # Snap very small velocities to zero to avoid drift
            if math.hypot(self.vx, self.vy) < 0.01:
                self.vx = 0.0
                self.vy = 0.0

        # Move
        self.x += self.vx
        self.y += self.vy

        # Screen wrapping
        self._wrap(screen_width, screen_height)

    def _wrap(self, screen_width, screen_height):
        """Wrap ship position to stay within screen boundaries."""
        # Account for ship radius when wrapping
        if self.x < -SHIP_RADIUS:
            self.x += screen_width + SHIP_RADIUS * 2
        elif self.x > screen_width + SHIP_RADIUS:
            self.x -= screen_width + SHIP_RADIUS * 2

        if self.y < -SHIP_RADIUS:
            self.y += screen_height + SHIP_RADIUS * 2
        elif self.y > screen_height + SHIP_RADIUS:
            self.y -= screen_height + SHIP_RADIUS * 2

    # ── Drawing ──────────────────────────────────────────────────────────

    def draw(self, screen):
        """Render the ship as a rotated triangle on the given surface.

        Args:
            screen: The pygame Surface to draw on.
        """
        # Define triangle vertices with the ship pointing up (angle = 0)
        # Tip is at (0, -SHIP_HEIGHT/2), base corners at (±SHIP_WIDTH/2, SHIP_HEIGHT/2)
        half_w = SHIP_WIDTH / 2
        half_h = SHIP_HEIGHT / 2
        base_vertices = [
            (0.0, -half_h),           # tip
            (-half_w, half_h),        # bottom-left
            (half_w, half_h),         # bottom-right
        ]

        # Rotate each vertex around the origin by self.angle degrees
        rotated = self._rotate_vertices(base_vertices)

        # Translate to ship position
        points = [(self.x + vx, self.y + vy) for vx, vy in rotated]

        # Draw filled triangle with outline
        pygame.draw.polygon(screen, COLOR_LIGHT_GRAY, points)
        pygame.draw.polygon(screen, COLOR_WHITE, points, width=1)

    def _rotate_vertices(self, vertices):
        """Rotate a list of (x, y) vertices around the origin.

        Args:
            vertices: List of (x, y) tuples in local coordinates.

        Returns:
            List of rotated (x, y) tuples.
        """
        angle_rad = math.radians(self.angle)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        rotated = []
        for vx, vy in vertices:
            rx = vx * cos_a - vy * sin_a
            ry = vx * sin_a + vy * cos_a
            rotated.append((rx, ry))
        return rotated

    # ── Properties ───────────────────────────────────────────────────────

    @property
    def tip(self):
        """Return the (x, y) position of the ship's tip (nose).

        Useful for weapon spawning and laser rendering.
        """
        half_h = SHIP_HEIGHT / 2
        angle_rad = math.radians(self.angle - 90)
        return (
            self.x + half_h * math.cos(angle_rad),
            self.y + half_h * math.sin(angle_rad),
        )


# ─────────────────────────────────────────────────────────────────────────────
# ASTEROID CLASS
# ─────────────────────────────────────────────────────────────────────────────

class Asteroid:
    """A tumbling, irregular polygon asteroid.

    Each asteroid has a randomly generated irregular shape, a random brown/beige
    fill color, and a white outline. It moves at a constant velocity and rotates
    (tumbles) at a rate inversely proportional to its size.
    """

    def __init__(self, x, y, radius, speed, angle=None):
        """Create a new asteroid.

        Args:
            x: Initial horizontal position.
            y: Initial vertical position.
            radius: Asteroid radius in pixels (affects shape and rotation speed).
            speed: Movement speed in pixels per frame.
            angle: Movement direction in degrees (0 = right, clockwise).
                   If None, a random direction is chosen.
        """
        self.x = float(x)
        self.y = float(y)
        self.radius = float(radius)

        # Movement
        if angle is None:
            angle = random.uniform(0, 360)
        angle_rad = math.radians(angle)
        self.vx = speed * math.cos(angle_rad)
        self.vy = speed * math.sin(angle_rad)

        # Tumbling rotation
        self.angle = random.uniform(0, 360)
        self.rotation_speed = self._compute_rotation_speed(radius)

        # Shape: irregular polygon
        self.fill_color = random.choice(ASTEROID_FILL_COLORS)
        self.base_vertices = self._generate_shape(radius)

    # ── Shape generation ─────────────────────────────────────────────────

    def _generate_shape(self, radius):
        """Generate an irregular polygon shape for this asteroid.

        The shape is a perturbed circle: each vertex is placed at a random
        angle with a radius that varies by ±ASTEROID_RADIUS_VARIATION.

        Args:
            radius: Base radius of the asteroid.

        Returns:
            List of (x, y) tuples representing the polygon vertices in local
            coordinates (centered at origin).
        """
        num_vertices = random.randint(
            ASTEROID_MIN_VERTICES, ASTEROID_MAX_VERTICES
        )
        vertices = []
        for i in range(num_vertices):
            theta = (2 * math.pi * i) / num_vertices + random.uniform(
                -math.pi / num_vertices, math.pi / num_vertices
            )
            r = radius * (1 + random.uniform(
                -ASTEROID_RADIUS_VARIATION, ASTEROID_RADIUS_VARIATION
            ))
            vertices.append((r * math.cos(theta), r * math.sin(theta)))
        return vertices

    # ── Rotation speed ───────────────────────────────────────────────────

    @staticmethod
    def _compute_rotation_speed(radius):
        """Compute tumbling rotation speed based on asteroid radius.

        Larger asteroids rotate slowly (1°/frame at radius 40), smaller ones
        rotate faster (10°/frame at radius 15). Linear interpolation between
        these two extremes.

        Args:
            radius: Asteroid radius in pixels.

        Returns:
            Rotation speed in degrees per frame.
        """
        if radius <= ASTEROID_SMALL_RADIUS:
            return ASTEROID_SMALL_ROTATION_SPEED
        if radius >= ASTEROID_LARGE_RADIUS:
            return ASTEROID_LARGE_ROTATION_SPEED

        # Linear interpolation
        t = (ASTEROID_LARGE_RADIUS - radius) / (
            ASTEROID_LARGE_RADIUS - ASTEROID_SMALL_RADIUS
        )
        return ASTEROID_LARGE_ROTATION_SPEED + t * (
            ASTEROID_SMALL_ROTATION_SPEED - ASTEROID_LARGE_ROTATION_SPEED
        )

    # ── Update ───────────────────────────────────────────────────────────

    def update(self, screen_width, screen_height):
        """Update asteroid position and rotation.

        Args:
            screen_width: Current window width in pixels.
            screen_height: Current window height in pixels.
        """
        # Move
        self.x += self.vx
        self.y += self.vy

        # Tumble
        self.angle += self.rotation_speed
        self.angle = self.angle % 360

        # Screen wrapping
        self._wrap(screen_width, screen_height)

    def _wrap(self, screen_width, screen_height):
        """Wrap asteroid position to stay within screen boundaries.

        Args:
            screen_width: Current window width in pixels.
            screen_height: Current window height in pixels.
        """
        # Account for asteroid radius when wrapping
        if self.x < -self.radius:
            self.x += screen_width + self.radius * 2
        elif self.x > screen_width + self.radius:
            self.x -= screen_width + self.radius * 2

        if self.y < -self.radius:
            self.y += screen_height + self.radius * 2
        elif self.y > screen_height + self.radius:
            self.y -= screen_height + self.radius * 2

    def force_wrap(self, screen_width, screen_height):
        """Force-wrap asteroid position if it's off-screen.

        Used after window resizes to ensure asteroids reappear on-screen.
        Unlike normal wrapping (which handles gradual movement past edges),
        this uses modular arithmetic to snap the asteroid back into bounds.

        Args:
            screen_width: Current window width in pixels.
            screen_height: Current window height in pixels.
        """
        self.x = self.x % screen_width
        self.y = self.y % screen_height

    # ── Drawing ──────────────────────────────────────────────────────────

    def draw(self, screen):
        """Render the asteroid as a rotated irregular polygon.

        Args:
            screen: The pygame Surface to draw on.
        """
        rotated = self._rotate_vertices(self.base_vertices)
        points = [(self.x + vx, self.y + vy) for vx, vy in rotated]

        pygame.draw.polygon(screen, self.fill_color, points)
        pygame.draw.polygon(screen, COLOR_WHITE, points, width=1)

    def _rotate_vertices(self, vertices):
        """Rotate a list of (x, y) vertices around the origin.

        Args:
            vertices: List of (x, y) tuples in local coordinates.

        Returns:
            List of rotated (x, y) tuples.
        """
        angle_rad = math.radians(self.angle)
        cos_a = math.cos(angle_rad)
        sin_a = math.sin(angle_rad)
        rotated = []
        for vx, vy in vertices:
            rx = vx * cos_a - vy * sin_a
            ry = vx * sin_a + vy * cos_a
            rotated.append((rx, ry))
        return rotated


# ─────────────────────────────────────────────────────────────────────────────
# GAME CLASS
# ─────────────────────────────────────────────────────────────────────────────

class Game:
    """Main game controller. Manages the window, state machine, and rendering."""

    def __init__(self):
        """Initialize pygame and set up the window."""
        pygame.init()

        # Window state tracking
        self.window_width = INITIAL_WINDOW_WIDTH
        self.window_height = INITIAL_WINDOW_HEIGHT
        self.is_fullscreen = False
        self.saved_window_rect = None  # Saved before entering fullscreen

        # Create the initial resizable window
        self.screen = pygame.display.set_mode(
            (self.window_width, self.window_height),
            pygame.RESIZABLE,
        )
        pygame.display.set_caption("SuperAsteroids")

        # State machine
        self.current_mode = MODE_TITLE
        self.level = 1

        # Ship
        self.ship = Ship()

        # Asteroids
        self.asteroids = []

        # Level text fade
        self.level_text_timer = 0        # frames remaining for "Begin level N" text
        self.level_text_level = 1        # which level number to display

        # Timing
        self.clock = pygame.time.Clock()
        self.running = True

        # Fonts (initialized after pygame.init)
        self._fonts = {}
        self._init_fonts()

    # ── Font management ──────────────────────────────────────────────────

    def _init_fonts(self):
        """Create cached font objects for reuse across screens."""
        self._fonts["large"] = pygame.font.Font(None, FONT_SIZE_LARGE)
        self._fonts["medium"] = pygame.font.Font(None, FONT_SIZE_MEDIUM)
        self._fonts["small"] = pygame.font.Font(None, FONT_SIZE_SMALL)

    # ── Main loop ────────────────────────────────────────────────────────

    def run(self):
        """Execute the main game loop until the player quits."""
        while self.running:
            self.running = self._handle_events()
            self._update()
            self._draw()
            pygame.display.flip()
            self.clock.tick(TARGET_FPS)

        pygame.quit()
        sys.exit(0)

    # ── Event handling ───────────────────────────────────────────────────

    def _handle_events(self):
        """Process all pending pygame events. Returns True if game should continue."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                return False

            if event.type == pygame.VIDEORESIZE:
                self._handle_resize(event)
                continue

            if event.type == pygame.KEYDOWN:
                self._handle_keydown(event.key)

        return True

    def _handle_resize(self, event):
        """Handle window resize events, enforcing minimum dimensions.

        We do NOT call pygame.display.set_mode() here — that would fight
        with the window manager and cause the window to snap back.
        Instead, we just read the actual surface dimensions after the WM
        finishes resizing. Pygame updates the surface automatically when
        RESIZABLE is set.
        """
        # Read the actual surface dimensions — pygame updates the surface
        # automatically for RESIZABLE windows.
        self.window_width, self.window_height = self.screen.get_size()

        # Clamp our tracked dimensions to the minimum. This ensures game
        # logic (wrapping, spawning, etc.) never uses values below minimum,
        # even if the WM allowed a smaller window.
        self.window_width = max(self.window_width, MIN_WINDOW_WIDTH)
        self.window_height = max(self.window_height, MIN_WINDOW_HEIGHT)

        # Force-wrap any asteroids that may have ended up off-screen
        # due to the resize
        for asteroid in self.asteroids:
            asteroid.force_wrap(self.window_width, self.window_height)

    def _handle_keydown(self, key):
        """Route key presses to the appropriate handler based on current mode."""
        # F11 is global — toggles fullscreen from any mode
        if key == pygame.K_F11:
            self._toggle_fullscreen()
            return

        if self.current_mode == MODE_TITLE:
            self._handle_title_input(key)
        elif self.current_mode == MODE_GAME:
            self._handle_game_input(key)
        elif self.current_mode == MODE_PAUSE:
            self._handle_pause_input(key)
        elif self.current_mode == MODE_GAMEOVER:
            self._handle_gameover_input(key)

    # ── Mode-specific input handlers ─────────────────────────────────────

    def _handle_title_input(self, key):
        """Handle input while on the Title Screen."""
        if key == pygame.K_RETURN:
            # Enter Game Mode at level 1
            self._start_level(1)
        elif key == pygame.K_ESCAPE:
            # Exit the game immediately
            pygame.quit()
            sys.exit(0)

    def _handle_game_input(self, key):
        """Handle input while in Game Mode."""
        if key == pygame.K_ESCAPE:
            # Pause the game
            self.current_mode = MODE_PAUSE

    def _handle_pause_input(self, key):
        """Handle input while in Pause Mode."""
        if key == pygame.K_ESCAPE:
            # Resume the game
            self.current_mode = MODE_GAME
        elif key == pygame.K_x:
            # Abandon game, return to Title Screen
            self.current_mode = MODE_TITLE

    def _handle_gameover_input(self, key):
        """Handle input while in Game Over Mode."""
        if key == pygame.K_r:
            # Restart from level 1
            self._start_level(1)
        elif key == pygame.K_ESCAPE:
            # Return to Title Screen
            self.current_mode = MODE_TITLE

    # ── Level management ─────────────────────────────────────────────────

    def _start_level(self, level_number):
        """Initialize a new level: reset ship, spawn asteroids, start text fade.

        Args:
            level_number: The 1-based level number to start.
        """
        self.level = level_number
        self.current_mode = MODE_GAME
        self.ship.reset(
            self.window_width / 2,
            self.window_height / 2,
        )
        self._spawn_level_asteroids(level_number)
        self.level_text_timer = LEVEL_TEXT_DURATION_FRAMES
        self.level_text_level = level_number

    def _spawn_level_asteroids(self, level_number):
        """Spawn asteroids for the given level.

        Level 1 starts with ASTEROID_LEVEL1_COUNT large asteroids.
        Each subsequent level adds 1-2 more asteroids and increases
        their base speed by ASTEROID_SPEED_INCREMENT.

        Args:
            level_number: The 1-based level number.
        """
        self.asteroids.clear()

        # Calculate asteroid count: level 1 = 5, each level adds 1-2
        count = ASTEROID_LEVEL1_COUNT
        for lvl in range(1, level_number):
            count += random.randint(1, 2)

        # Calculate base speed: level 1 = 1.5-2.5, each level adds 0.3
        base_speed = (ASTEROID_MIN_SPEED + ASTEROID_MAX_SPEED) / 2
        base_speed += (level_number - 1) * ASTEROID_SPEED_INCREMENT

        for _ in range(count):
            asteroid = self._spawn_single_asteroid(base_speed)
            if asteroid is not None:
                self.asteroids.append(asteroid)

    def _spawn_single_asteroid(self, base_speed):
        """Spawn a single large asteroid at a safe distance from the ship.

        Tries up to 50 random positions. Falls back to a screen corner if
        no safe position is found.

        Args:
            base_speed: Base speed for the asteroid.

        Returns:
            An Asteroid instance, or None if spawning failed entirely.
        """
        speed = base_speed + random.uniform(
            -(ASTEROID_MAX_SPEED - ASTEROID_MIN_SPEED) / 2,
            (ASTEROID_MAX_SPEED - ASTEROID_MIN_SPEED) / 2,
        )
        speed = max(ASTEROID_MIN_SPEED, speed)

        # Try random positions first
        for _ in range(50):
            x = random.uniform(0, self.window_width)
            y = random.uniform(0, self.window_height)
            if self._is_safe_spawn_position(x, y):
                return Asteroid(x, y, ASTEROID_LARGE_RADIUS, speed)

        # Fallback: try screen corners
        corners = [
            (50, 50),
            (self.window_width - 50, 50),
            (50, self.window_height - 50),
            (self.window_width - 50, self.window_height - 50),
        ]
        for cx, cy in corners:
            if self._is_safe_spawn_position(cx, cy):
                return Asteroid(cx, cy, ASTEROID_LARGE_RADIUS, speed)

        # Last resort: pick any corner (even if not ideal)
        cx, cy = random.choice(corners)
        return Asteroid(cx, cy, ASTEROID_LARGE_RADIUS, speed)

    def _is_safe_spawn_position(self, x, y):
        """Check if a position is safe for asteroid spawning.

        A position is safe if it's at least ASTEROID_SPAWN_EXCLUSION_RADIUS
        pixels away from the player's ship.

        Args:
            x: Horizontal position to check.
            y: Vertical position to check.

        Returns:
            True if the position is safe, False otherwise.
        """
        dx = x - self.ship.x
        dy = y - self.ship.y
        distance = math.hypot(dx, dy)
        return distance >= ASTEROID_SPAWN_EXCLUSION_RADIUS

    # ── Fullscreen toggle ────────────────────────────────────────────────

    def _toggle_fullscreen(self):
        """Toggle between windowed and fullscreen mode, preserving window state."""
        if self.is_fullscreen:
            # Restore previous windowed state
            if self.saved_window_rect is not None:
                self.screen = pygame.display.set_mode(
                    (self.saved_window_rect.width, self.saved_window_rect.height),
                    pygame.RESIZABLE,
                )
                pygame.display.set_window_position(
                    self.saved_window_rect.x,
                    self.saved_window_rect.y,
                )
                self.window_width = self.saved_window_rect.width
                self.window_height = self.saved_window_rect.height
            else:
                # Fallback to defaults if we couldn't save the rect
                self.screen = pygame.display.set_mode(
                    (INITIAL_WINDOW_WIDTH, INITIAL_WINDOW_HEIGHT),
                    pygame.RESIZABLE,
                )
                self.window_width = INITIAL_WINDOW_WIDTH
                self.window_height = INITIAL_WINDOW_HEIGHT

            self.is_fullscreen = False
        else:
            # Save current window position and size, then go fullscreen
            try:
                self.saved_window_rect = pygame.display.get_window_rect()
            except Exception:
                self.saved_window_rect = None

            # (0, 0) with FULLSCREEN flag uses the display's native resolution
            self.screen = pygame.display.set_mode(
                (0, 0),
                pygame.FULLSCREEN,
            )
            self.window_width = self.screen.get_width()
            self.window_height = self.screen.get_height()
            self.is_fullscreen = True

        # After fullscreen toggle, force-wrap asteroids to new dimensions
        for asteroid in self.asteroids:
            asteroid.force_wrap(self.window_width, self.window_height)

    # ── Update ───────────────────────────────────────────────────────────

    def _update(self):
        """Update game state each frame."""
        if self.current_mode == MODE_GAME:
            self._update_game()

    def _update_game(self):
        """Update gameplay: ship physics, asteroids, and level text fade timer."""
        keys = pygame.key.get_pressed()
        self.ship.update(keys, self.window_width, self.window_height)

        # Update all asteroids — but freeze them while the "Begin level N"
        # text is fading, so they can't drift into the ship before it appears
        if self.level_text_timer <= 0:
            for asteroid in self.asteroids:
                asteroid.update(self.window_width, self.window_height)

        # Decrement level text fade timer
        if self.level_text_timer > 0:
            self.level_text_timer -= 1

    # ── Rendering ────────────────────────────────────────────────────────

    def _draw(self):
        """Render the current screen based on the active game mode."""
        self.screen.fill(COLOR_BLACK)

        if self.current_mode == MODE_TITLE:
            self._draw_title_screen()
        elif self.current_mode == MODE_GAME:
            self._draw_game_screen()
        elif self.current_mode == MODE_PAUSE:
            self._draw_pause_screen()
        elif self.current_mode == MODE_GAMEOVER:
            self._draw_gameover_screen()

    def _draw_title_screen(self):
        """Render the Title Screen placeholder."""
        title = self._fonts["large"].render("Title Screen", True, COLOR_WHITE)
        subtitle = self._fonts["small"].render("Press Enter / ESC", True, COLOR_WHITE)

        self._blit_centered(title, vertical_ratio=0.35)
        self._blit_centered(subtitle, vertical_ratio=0.6)

    def _draw_game_screen(self):
        """Render the Game Mode: asteroids, ship, level text overlay.

        The ship is hidden while the 'Begin level N' text is fading in,
        so the player doesn't see the ship until the fade-out completes.
        Asteroids are always drawn (they're visible during the fade).
        """
        # Draw all asteroids (always visible)
        for asteroid in self.asteroids:
            asteroid.draw(self.screen)

        # Draw "Begin level N" fade-out text (always drawn on top)
        if self.level_text_timer > 0:
            self._draw_level_text()
        else:
            # Ship only appears after the fade-out text has finished
            self.ship.draw(self.screen)

    def _draw_level_text(self):
        """Render the fading 'Begin level N' text overlay."""
        # Compute alpha: full opacity at start, fades to 0 at end
        alpha = int(255 * (self.level_text_timer / LEVEL_TEXT_DURATION_FRAMES))
        alpha = max(0, min(255, alpha))

        text = self._fonts["medium"].render(
            f"Begin level {self.level_text_level}", True, COLOR_WHITE
        )

        # Create a per-surface alpha overlay
        faded = text.copy()
        faded.set_alpha(alpha)

        self._blit_centered(faded, vertical_ratio=0.5)

    def _draw_pause_screen(self):
        """Render the Pause Mode placeholder."""
        title = self._fonts["large"].render("PAUSED", True, COLOR_WHITE)
        resume = self._fonts["small"].render("ESC to resume", True, COLOR_WHITE)
        exit_text = self._fonts["small"].render("X to exit", True, COLOR_WHITE)

        self._blit_centered(title, vertical_ratio=0.3)
        self._blit_centered(resume, vertical_ratio=0.55)
        self._blit_centered(exit_text, vertical_ratio=0.65)

    def _draw_gameover_screen(self):
        """Render the Game Over placeholder."""
        title = self._fonts["large"].render("GAME OVER", True, COLOR_WHITE)
        restart = self._fonts["small"].render("R to restart", True, COLOR_WHITE)
        exit_text = self._fonts["small"].render("ESC to exit", True, COLOR_WHITE)

        self._blit_centered(title, vertical_ratio=0.3)
        self._blit_centered(restart, vertical_ratio=0.55)
        self._blit_centered(exit_text, vertical_ratio=0.65)

    # ── Rendering helpers ────────────────────────────────────────────────

    def _blit_centered(self, surface, vertical_ratio):
        """Blit a surface centered horizontally at a given vertical ratio of the screen.

        Args:
            surface: The pygame Surface to render.
            vertical_ratio: A float between 0.0 (top) and 1.0 (bottom)
                            specifying the vertical center position.
        """
        center_x = self.window_width // 2
        center_y = int(self.window_height * vertical_ratio)
        rect = surface.get_rect(center=(center_x, center_y))
        self.screen.blit(surface, rect)


# ─────────────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def main():
    """Application entry point. Handles --test mode flag."""
    test_mode = "--test" in sys.argv

    game = Game()

    if test_mode:
        # Test mode: render the title screen briefly, then exit cleanly
        game._draw()
        pygame.display.flip()
        pygame.time.wait(TEST_MODE_DELAY_MS)
        pygame.quit()
        sys.exit(0)
    else:
        # Normal mode: run the full game loop
        game.run()


if __name__ == "__main__":
    main()
