#!/usr/bin/env python3
"""
SuperAsteroids — Full Game with Weapons, Powerups, and HUD

A derivative of the classic Asteroids arcade game, built with pygame-ce.
Developed in stages:
Stage 1: Window setup, resize handling, F11 fullscreen, state machine.
Stage 2: Ship class, physics (rotation, thrust, friction, wrap).
Stage 3: Asteroid class, irregular polygons, tumbling, safe spawning.
Stage 4: Collision, asteroid splitting/destruction, hit counter, level progression.
Stage 5: Cannon weapon with 3 power levels, projectile physics, friendly fire.
Stage 6: Laser weapon with charge mechanics, screen-wrapping beam, L3 instant destroy.
Stage 7: Shield weapon with charge mechanics, bounce physics, asteroid deflection.
Stage 8: Powerup spawning, collection, weapon switching.
Stage 9: Full HUD panel with rounded border, level/hits/weapon/charge display.
Stage 10: Visual effects (thruster fire, explosion particles, twinkling starfield)
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
COLOR_RED = (255, 0, 0)
COLOR_YELLOW = (255, 255, 0)
COLOR_ORANGE = (255, 165, 0)
COLOR_GREEN = (0, 255, 0)
COLOR_CYAN = (0, 255, 255)

# Game modes (state machine states)
MODE_TITLE = "TITLE"
MODE_GAME = "GAME"
MODE_PAUSE = "PAUSE"
MODE_GAMEOVER = "GAMEOVER"

# Test mode duration in milliseconds
TEST_MODE_DELAY_MS = 100

# Font sizes (None = default pygame font)
FONT_SIZE_TITLE = 96
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
ASTEROID_SMALL_RADIUS = 15        # minimum asteroid size range (for rotation speed)
ASTEROID_DESTRUCTION_RADIUS = 20  # asteroids below this radius are destroyed, not split
ASTEROID_SPLIT_DIVISOR = 1.5      # radius divisor when splitting

# Asteroid movement
ASTEROID_MIN_SPEED = 1.5          # pixels per frame
ASTEROID_MAX_SPEED = 2.5          # pixels per frame
ASTEROID_SPEED_INCREMENT = 0.3    # speed increase per level
ASTEROID_SPLIT_SPEED_MULT = 1.2   # speed multiplier when splitting

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

# ── Cannon constants ────────────────────────────────────────────────────────

# Weapon types
WEAPON_CANNON = "Cannon"

# Cannon projectile speed (added to ship velocity in facing direction)
CANNON_L1_SPEED = 6           # pixels per frame (L1 and L2)
CANNON_L3_SPEED = 8           # pixels per frame (L3)

# Cannon projectile travel distance
CANNON_PROJECTILE_DISTANCE = 1000  # pixels before projectile expires

# Cannon projectile sizes
CANNON_L1_PROJECTILE_SIZE = 2       # pixels (L1 and L2: drawn as points)
CANNON_L3_PROJECTILE_SIZE = 4       # pixels (L3: 4x4 square)

# Cannon max projectiles in flight
CANNON_L1_MAX_FLIGHT = 3            # L1
CANNON_L2_MAX_FLIGHT = 9            # L2
CANNON_L3_MAX_FLIGHT = float('inf') # L3: unlimited

# Cannon L2 spread arc
CANNON_L2_ARC = 20  # degrees total arc for 3-projectile spread

# Cannon projectile colors
CANNON_L1_COLOR = COLOR_YELLOW
CANNON_L2_COLOR = COLOR_ORANGE
CANNON_L3_COLOR = COLOR_WHITE

# Projectile invulnerability (frames after spawn where projectile
# cannot hit the player's own ship)
PROJECTILE_INVULNERABLE_FRAMES = 10

# ─────────────────────────────────────────────────────────────────────────────
# LASER CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Weapon types
WEAPON_LASER = "Laser"

# Laser beam geometry per power level
LASER_L1_WIDTH = 1        # pixels wide
LASER_L1_LENGTH = 100     # pixels long
LASER_L1_COLOR = (100, 200, 255)   # light blue

LASER_L2_WIDTH = 2        # pixels wide
LASER_L2_LENGTH = 125     # pixels long
LASER_L2_COLOR = (100, 200, 255)   # light blue

LASER_L3_WIDTH = 3        # pixels wide
LASER_L3_LENGTH = 125     # pixels long (same as L2)
LASER_L3_COLOR = COLOR_WHITE

# Laser charge mechanics
LASER_MAX_CHARGE = 100
LASER_MIN_CHARGE_TO_ACTIVATE = 20   # minimum charge needed to fire

# Laser L1 charge rates
LASER_L1_DRAIN_RATE = 3     # charge drained per frame while active
LASER_L1_RECHARGE_RATE = 1  # charge recovered per frame when inactive

# Laser L2 charge rates
LASER_L2_DRAIN_RATE = 2
LASER_L2_RECHARGE_RATE = 2

# Laser L3 charge rates (same drain/recharge as L2 per spec)
LASER_L3_DRAIN_RATE = 2
LASER_L3_RECHARGE_RATE = 2

# HUD charge bar dimensions
LASER_HUD_BAR_WIDTH = 150   # pixels
LASER_HUD_BAR_HEIGHT = 12   # pixels
LASER_HUD_BAR_BORDER = 1    # pixels

# ─────────────────────────────────────────────────────────────────────────────
# SHIELD CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Weapon types
WEAPON_SHIELD = "Shield"

# Shield geometry per power level
SHIELD_L1_RADIUS = 35       # pixels
SHIELD_L1_BORDER = 1        # pixels wide border
SHIELD_L1_BOUNCE_DIVISOR = 5   # bounce velocity = radius / 5

SHIELD_L2_RADIUS = 35       # pixels (same as L1)
SHIELD_L2_BORDER = 2        # pixels wide border
SHIELD_L2_BOUNCE_DIVISOR = 8  # bounce velocity = radius / 8

SHIELD_L3_RADIUS = 40       # pixels (larger)
SHIELD_L3_BORDER = 3        # pixels wide border
SHIELD_L3_BOUNCE_DIVISOR = 10  # bounce velocity = radius / 10

# Shield charge mechanics
SHIELD_MAX_CHARGE = 100
SHIELD_MIN_CHARGE_TO_ACTIVATE = 20  # minimum charge needed to activate

# Shield L1 charge rates
SHIELD_L1_DRAIN_RATE = 5    # charge drained per frame while active
SHIELD_L1_RECHARGE_RATE = 1  # charge recovered per frame when inactive

# Shield L2 charge rates
SHIELD_L2_DRAIN_RATE = 3
SHIELD_L2_RECHARGE_RATE = 3

# Shield L3 charge rates (same drain/recharge as L2 per spec)
SHIELD_L3_DRAIN_RATE = 3
SHIELD_L3_RECHARGE_RATE = 3

# Shield color
SHIELD_COLOR = COLOR_RED

# HUD charge bar dimensions (shared with laser)
SHIELD_HUD_BAR_WIDTH = 150   # pixels
SHIELD_HUD_BAR_HEIGHT = 12   # pixels
SHIELD_HUD_BAR_BORDER = 1    # pixels

# ─────────────────────────────────────────────────────────────────────────────
# POWERUP CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Powerup geometry
POWERUP_RADIUS = 20           # pixels
POWERUP_SPEED = 2             # pixels per frame (drift speed)

# Powerup spawn interval
POWERUP_SPAWN_INTERVAL_FRAMES = 1800  # 30 seconds at 60 FPS

# Powerup types and colors
POWERUP_CANNON = "C"
POWERUP_LASER = "L"
POWERUP_SHIELD = "S"

POWERUP_CANNON_COLOR = COLOR_YELLOW
POWERUP_LASER_COLOR = (100, 200, 255)  # light blue
POWERUP_SHIELD_COLOR = COLOR_RED

# HUD text colors (match weapon colors)
HUD_CANNON_COLOR = COLOR_YELLOW
HUD_LASER_COLOR = (100, 200, 255)     # light blue
HUD_SHIELD_COLOR = COLOR_RED

# HUD panel (Stage 9: full HUD with border and background)
HUD_BACKGROUND_ALPHA = 153     # 60% opacity (0-255 scale)
HUD_BORDER_COLOR = (0, 255, 255, HUD_BACKGROUND_ALPHA)  # 60% opaque cyan
HUD_BORDER_WIDTH = 4
HUD_BORDER_RADIUS = 8         # corner rounding in pixels
HUD_MARGIN = 10               # margin from screen edges (upper-right)
HUD_PADDING = 10              # internal padding inside the panel
HUD_FONT_SIZE = 24            # font size for HUD text
HUD_LINE_SPACING = 24         # vertical spacing between HUD lines
HUD_CHARGE_BAR_WIDTH = 150    # width of charge bar within HUD
HUD_CHARGE_BAR_HEIGHT = 12    # height of charge bar
HUD_CHARGE_BAR_GAP = 6        # gap between "Charge:" label and bar

# ─────────────────────────────────────────────────────────────────────────────
# STAGE 10: COSMETIC EFFECTS CONSTANTS
# ─────────────────────────────────────────────────────────────────────────────

# Starfield
STARFIELD_MIN_COUNT = 100     # minimum number of stars
STARFIELD_MAX_COUNT = 200     # maximum number of stars
STAR_TWINKLE_RATE_MIN = 0.015 # minimum twinkle speed (1.5% of 0-255 range)
STAR_TWINKLE_RATE_MAX = 0.04  # maximum twinkle speed (4% of 0-255 range)
STAR_MIN_BRIGHTNESS = 0       # black
STAR_MAX_BRIGHTNESS = 255     # pure white

# Thruster exhaust particles
THRUSTER_PARTICLE_RADIUS_MIN = 3   # pixels
THRUSTER_PARTICLE_RADIUS_MAX = 8   # pixels
THRUSTER_ALPHA_DECAY = 0.05        # 5% per frame
THRUSTER_BASE_SPEED_MIN = 6        # px/frame opposite to ship facing
THRUSTER_BASE_SPEED_MAX = 10       # px/frame opposite to ship facing
THRUSTER_ARC_SPREAD = 10           # ±10 degrees from opposite direction
THRUSTER_EMIT_RATE = 3             # particles per frame when thrusting
THRUSTER_COLORS = [
    COLOR_YELLOW,   # (255, 255, 0)
    COLOR_ORANGE,   # (255, 165, 0)
    COLOR_RED,      # (255, 0, 0)
]

# Explosion particles
EXPLOSION_COUNT_MULTIPLIER = 3       # count = radius * 3
EXPLOSION_VELOCITY_MIN = 5           # px/frame
EXPLOSION_VELOCITY_MAX = 15          # px/frame
EXPLOSION_ALPHA_DECAY_MIN = 0.03     # 3% per frame
EXPLOSION_ALPHA_DECAY_MAX = 0.10     # 10% per frame
EXPLOSION_SPLIT_COLORS = [           # colorful for splits
    COLOR_YELLOW,
    COLOR_RED,
    COLOR_ORANGE,
]
EXPLOSION_DESTRUCTION_COLOR = (128, 128, 128)  # gray for destructions

# Title screen asteroids
TITLE_ASTEROID_MIN = 2
TITLE_ASTEROID_MAX = 5
TITLE_ASTEROID_SPEED = 0.5           # gentle drift speed


# ─────────────────────────────────────────────────────────────────────────────
# STAR CLASS
# ─────────────────────────────────────────────────────────────────────────────

class Star:
    """A single twinkling star for the background starfield.

    Rendered as a single pixel with grayscale color. Brightness oscillates
    between black and white at a slow rate, creating a twinkle effect.
    """

    def __init__(self, x, y):
        """Create a new star at the given position.

        Args:
            x: Horizontal position in screen coordinates.
            y: Vertical position in screen coordinates.
        """
        self.x = x
        self.y = y
        # Random initial brightness (0-255)
        self.brightness = random.randint(
            STAR_MIN_BRIGHTNESS, STAR_MAX_BRIGHTNESS
        )
        # Random twinkle direction: +1 (brightening) or -1 (dimming)
        self.direction = random.choice([-1, 1])
        # Per-star twinkle speed (2-6% of 0-255 range per frame)
        self.twinkle_rate = random.uniform(
            STAR_TWINKLE_RATE_MIN, STAR_TWINKLE_RATE_MAX
        )

    def update(self):
        """Update star brightness with twinkle effect."""
        self.brightness += int(self.twinkle_rate * 255) * self.direction
        if self.brightness >= STAR_MAX_BRIGHTNESS:
            self.brightness = STAR_MAX_BRIGHTNESS
            self.direction = -1
        elif self.brightness <= STAR_MIN_BRIGHTNESS:
            self.brightness = STAR_MIN_BRIGHTNESS
            self.direction = 1

    def draw(self, screen):
        """Render the star as a single grayscale pixel.

        Args:
            screen: The pygame Surface to draw on.
        """
        color = (self.brightness, self.brightness, self.brightness)
        screen.set_at((self.x, self.y), color)


# ─────────────────────────────────────────────────────────────────────────────
# PARTICLE CLASS
# ─────────────────────────────────────────────────────────────────────────────

class Particle:
    """A cosmetic particle for thruster exhaust or explosions.

    Rendered as a colored circle with alpha transparency. Particles move
    at constant velocity and fade out over time.
    """

    def __init__(self, x, y, vx, vy, color, radius, alpha_decay):
        """Create a new particle.

        Args:
            x: Initial horizontal position.
            y: Initial vertical position.
            vx: Horizontal velocity in pixels per frame.
            vy: Vertical velocity in pixels per frame.
            color: RGB color tuple.
            radius: Display radius in pixels.
            alpha_decay: Alpha decay rate per frame (0.0 to 1.0).
        """
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        self.color = color
        self.radius = radius
        self.alpha = 255.0
        self.alpha_decay = alpha_decay
        self.alive = True

    def update(self, screen_width, screen_height):
        """Update particle position and alpha.

        Args:
            screen_width: Current window width in pixels.
            screen_height: Current window height in pixels.

        Returns:
            True if particle is still alive, False if faded out.
        """
        self.x += self.vx
        self.y += self.vy

        # Screen wrapping
        if self.x < 0:
            self.x += screen_width
        elif self.x >= screen_width:
            self.x -= screen_width
        if self.y < 0:
            self.y += screen_height
        elif self.y >= screen_height:
            self.y -= screen_height

        # Alpha decay
        self.alpha -= self.alpha_decay * 255
        if self.alpha <= 0:
            self.alpha = 0
            self.alive = False

        return self.alive

    def draw(self, screen):
        """Render the particle as a semi-transparent colored circle.

        Args:
            screen: The pygame Surface to draw on.
        """
        if not self.alive or self.alpha <= 0:
            return
        # Create a temporary surface for alpha blending
        size = self.radius * 2 + 2
        surf = pygame.Surface((size, size), pygame.SRCALPHA)
        alpha_color = (
            self.color[0], self.color[1], self.color[2],
            int(self.alpha),
        )
        pygame.draw.circle(surf, alpha_color, (size // 2, size // 2),
                           self.radius)
        screen.blit(surf, (int(self.x) - size // 2, int(self.y) - size // 2))


# ─────────────────────────────────────────────────────────────────────────────
# POWERUP CLASS
# ─────────────────────────────────────────────────────────────────────────────

class Powerup:
    """A collectible weapon powerup.

    Rendered as a colored circle with a white letter label (C, L, or S).
    Drifts at constant speed in a random direction. Only one powerup
    can exist on screen at a time.
    """

    def __init__(self, x, y, powerup_type):
        """Create a new powerup.

        Args:
            x: Initial horizontal position.
            y: Initial vertical position.
            powerup_type: One of POWERUP_CANNON, POWERUP_LASER, POWERUP_SHIELD.
        """
        self.x = float(x)
        self.y = float(y)
        self.powerup_type = powerup_type

        # Movement: random direction at POWERUP_SPEED
        angle = random.uniform(0, 360)
        angle_rad = math.radians(angle)
        self.vx = POWERUP_SPEED * math.cos(angle_rad)
        self.vy = POWERUP_SPEED * math.sin(angle_rad)

        # Color based on type
        if self.powerup_type == POWERUP_CANNON:
            self.color = POWERUP_CANNON_COLOR
        elif self.powerup_type == POWERUP_LASER:
            self.color = POWERUP_LASER_COLOR
        else:  # POWERUP_SHIELD
            self.color = POWERUP_SHIELD_COLOR

    # ── Update ───────────────────────────────────────────────────────────

    def update(self, screen_width, screen_height):
        """Update powerup position and screen wrapping.

        Args:
            screen_width: Current window width in pixels.
            screen_height: Current window height in pixels.
        """
        self.x += self.vx
        self.y += self.vy
        self._wrap(screen_width, screen_height)

    def _wrap(self, screen_width, screen_height):
        """Wrap powerup position to stay within screen boundaries."""
        if self.x < -POWERUP_RADIUS:
            self.x += screen_width + POWERUP_RADIUS * 2
        elif self.x > screen_width + POWERUP_RADIUS:
            self.x -= screen_width + POWERUP_RADIUS * 2

        if self.y < -POWERUP_RADIUS:
            self.y += screen_height + POWERUP_RADIUS * 2
        elif self.y > screen_height + POWERUP_RADIUS:
            self.y -= screen_height + POWERUP_RADIUS * 2

    # ── Drawing ──────────────────────────────────────────────────────────

    def draw(self, screen):
        """Render the powerup as a colored circle with a letter label.

        Args:
            screen: The pygame Surface to draw on.
        """
        # Colored circle
        pygame.draw.circle(screen, self.color,
                           (int(self.x), int(self.y)),
                           POWERUP_RADIUS)
        pygame.draw.circle(screen, COLOR_WHITE,
                           (int(self.x), int(self.y)),
                           POWERUP_RADIUS, 1)

        # White letter label
        font = pygame.font.Font(None, 24)
        text = font.render(self.powerup_type, True, COLOR_WHITE)
        rect = text.get_rect(center=(int(self.x), int(self.y)))
        screen.blit(text, rect)


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
# PROJECTILE CLASS
# ─────────────────────────────────────────────────────────────────────────────

class Projectile:
    """A cannon projectile fired from the player's ship.

    Travels in a straight line at constant velocity. Expires after traveling
    CANNON_PROJECTILE_DISTANCE pixels from its spawn point. Has a brief
    invulnerability period after spawn to prevent hitting the player's ship.
    """

    def __init__(self, x, y, vx, vy, color, size):
        """Create a new projectile.

        Args:
            x: Initial horizontal position.
            y: Initial vertical position.
            vx: Horizontal velocity in pixels per frame.
            vy: Vertical velocity in pixels per frame.
            color: RGB color tuple for rendering.
            size: Display size in pixels (2 for L1/L2, 4 for L3).
        """
        self.x = float(x)
        self.y = float(y)
        self.vx = float(vx)
        self.vy = float(vy)
        self.color = color
        self.size = size

        # Tracking
        self.spawn_x = float(x)
        self.spawn_y = float(y)
        self.distance_traveled = 0.0
        self.age = 0  # frames since spawn (for invulnerability)

    # ── Update ───────────────────────────────────────────────────────────

    def update(self, screen_width, screen_height):
        """Update projectile position and travel distance.

        Args:
            screen_width: Current window width in pixels.
            screen_height: Current window height in pixels.

        Returns:
            True if projectile is still alive, False if it should be removed.
        """
        # Accumulate distance traveled this frame (cumulative, not displacement)
        frame_distance = math.hypot(self.vx, self.vy)
        self.distance_traveled += frame_distance

        # Move
        self.x += self.vx
        self.y += self.vy

        # Age
        self.age += 1

        # Screen wrapping
        self._wrap(screen_width, screen_height)

        # Check if projectile has traveled too far
        return self.distance_traveled <= CANNON_PROJECTILE_DISTANCE

    def _wrap(self, screen_width, screen_height):
        """Wrap projectile position to stay within screen boundaries."""
        if self.x < 0:
            self.x += screen_width
        elif self.x >= screen_width:
            self.x -= screen_width

        if self.y < 0:
            self.y += screen_height
        elif self.y >= screen_height:
            self.y -= screen_height

    @property
    def is_invulnerable(self):
        """True if the projectile is still in its invulnerability window.

        During this period, the projectile cannot hit the player's own ship.
        """
        return self.age < PROJECTILE_INVULNERABLE_FRAMES

    # ── Drawing ──────────────────────────────────────────────────────────

    def draw(self, screen):
        """Render the projectile on the given surface.

        Args:
            screen: The pygame Surface to draw on.
        """
        if self.size <= 2:
            # L1/L2: draw as a small filled circle (2px diameter)
            pygame.draw.circle(screen, self.color,
                               (int(self.x), int(self.y)), 1)
        else:
            # L3: draw as a 4x4 square
            rect = pygame.Rect(
                int(self.x) - self.size // 2,
                int(self.y) - self.size // 2,
                self.size, self.size,
            )
            pygame.draw.rect(screen, self.color, rect)


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

        # Projectiles (cannon)
        self.projectiles = []

        # Weapon state
        self.weapon_type = WEAPON_CANNON
        self.weapon_power = 1  # 1, 2, or 3

        # Laser state
        self.laser_charge = LASER_MAX_CHARGE
        self.laser_active = False        # True while beam is currently firing
        self.laser_hit_asteroids = set()  # Indices of asteroids already hit this burst

        # Shield state
        self.shield_charge = SHIELD_MAX_CHARGE
        self.shield_active = False       # True while shield is currently active
        self.shield_hit_asteroids = set()  # Asteroids already bounced this frame

        # Powerup state
        self.powerup = None              # Current active powerup (or None)
        self.powerup_spawn_timer = POWERUP_SPAWN_INTERVAL_FRAMES  # Frames until next powerup spawn

        # Cosmetic effects (Stage 10)
        self.stars = []                  # Starfield stars
        self.particles = []              # Thruster/exhaust/explosion particles
        self.title_asteroids = []        # Tumbling asteroids on title screen

        # Hit counter (only destruction events, not splits)
        self.hit_count = 0

        # Game over reason (for special messages like "Friendly fire!")
        self.gameover_reason = ""

        # Level text fade
        self.level_text_timer = 0        # frames remaining for "Begin level N" text
        self.level_text_level = 1        # which level number to display

        # Input state (for detecting key press vs hold)
        self._space_was_pressed = False

        # Timing
        self.clock = pygame.time.Clock()
        self.running = True

        # Fonts (initialized after pygame.init)
        self._fonts = {}
        self._init_fonts()

        # Cosmetic effects (initialized after window is created)
        self._init_starfield()
        self._init_title_asteroids()

    # ── Font management ──────────────────────────────────────────────────

    def _init_fonts(self):
        """Create cached font objects for reuse across screens."""
        self._fonts["large"] = pygame.font.Font(None, FONT_SIZE_LARGE)
        self._fonts["medium"] = pygame.font.Font(None, FONT_SIZE_MEDIUM)
        self._fonts["small"] = pygame.font.Font(None, FONT_SIZE_SMALL)

    # ── Starfield initialization ─────────────────────────────────────────

    def _init_starfield(self):
        """Initialize the starfield with random stars across the screen."""
        self.stars = []
        count = random.randint(STARFIELD_MIN_COUNT, STARFIELD_MAX_COUNT)
        for _ in range(count):
            x = random.randint(0, self.window_width - 1)
            y = random.randint(0, self.window_height - 1)
            self.stars.append(Star(x, y))

    def _adjust_starfield(self):
        """Adjust starfield to match current window dimensions after resize.

        Removes stars outside the new bounds and adds stars if the window
        grew, maintaining density even if this exceeds the 200-star limit.
        """
        # Remove stars that are now outside the window
        self.stars = [
            s for s in self.stars
            if 0 <= s.x < self.window_width and 0 <= s.y < self.window_height
        ]

        # Calculate how many stars we should have based on current area
        # Target density: ~150 stars per 800x600 area
        target_area = INITIAL_WINDOW_WIDTH * INITIAL_WINDOW_HEIGHT
        current_area = self.window_width * self.window_height
        target_count = int(
            random.randint(STARFIELD_MIN_COUNT, STARFIELD_MAX_COUNT)
            * (current_area / target_area)
        )

        # Add stars if we need more to fill the expanded area
        deficit = target_count - len(self.stars)
        for _ in range(max(0, deficit)):
            x = random.randint(0, self.window_width - 1)
            y = random.randint(0, self.window_height - 1)
            self.stars.append(Star(x, y))

    def _init_title_asteroids(self):
        """Initialize tumbling asteroids for the title screen."""
        self.title_asteroids = []
        count = random.randint(TITLE_ASTEROID_MIN, TITLE_ASTEROID_MAX)
        for _ in range(count):
            x = random.uniform(0, self.window_width)
            y = random.uniform(0, self.window_height)
            radius = random.uniform(20, ASTEROID_LARGE_RADIUS)
            asteroid = Asteroid(x, y, radius, TITLE_ASTEROID_SPEED)
            self.title_asteroids.append(asteroid)

    def _update_title_asteroids(self):
        """Update title screen asteroids' positions and rotation."""
        for asteroid in self.title_asteroids:
            asteroid.update(self.window_width, self.window_height)

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
            elif event.type == pygame.KEYUP:
                self._handle_keyup(event.key)

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

        # Adjust starfield to fill the new window dimensions
        self._adjust_starfield()

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

    def _handle_keyup(self, key):
        """Track key release events for press-vs-hold detection."""
        if key == pygame.K_SPACE:
            self._space_was_pressed = False

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
        elif key == pygame.K_SPACE:
            # Space bar: fire weapon (press only, not hold)
            if not self._space_was_pressed:
                self._space_was_pressed = True
                if self.weapon_type == WEAPON_CANNON:
                    self._fire_cannon()
                elif self.weapon_type == WEAPON_LASER:
                    self._activate_laser()
                elif self.weapon_type == WEAPON_SHIELD:
                    self._activate_shield()

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
            # Restart from level 1, resetting all state
            self._start_new_game()
        elif key == pygame.K_ESCAPE:
            # Return to Title Screen
            self.current_mode = MODE_TITLE

    # ── Cannon weapon ────────────────────────────────────────────────────

    def _fire_cannon(self):
        """Fire cannon projectiles based on current weapon power level.

        Level 1: 1 yellow projectile, max 3 in flight.
        Level 2: 3 orange projectiles in 20° arc, max 9 in flight.
        Level 3: 3 white 4x4 projectiles at 8 px/frame, unlimited in flight.
        """
        if self.weapon_type != WEAPON_CANNON:
            return

        power = self.weapon_power
        max_flight = self._get_cannon_max_flight(power)

        # Check if we can fire
        if len(self.projectiles) >= max_flight:
            return

        tip_x, tip_y = self.ship.tip
        facing_rad = math.radians(self.ship.angle - 90)

        if power == 1:
            # Single projectile
            speed = CANNON_L1_SPEED
            color = CANNON_L1_COLOR
            size = CANNON_L1_PROJECTILE_SIZE
            proj_vx = self.ship.vx + speed * math.cos(facing_rad)
            proj_vy = self.ship.vy + speed * math.sin(facing_rad)
            self.projectiles.append(Projectile(tip_x, tip_y, proj_vx, proj_vy,
                                               color, size))

        elif power == 2:
            # Three projectiles in 20° arc
            speed = CANNON_L1_SPEED
            color = CANNON_L2_COLOR
            size = CANNON_L1_PROJECTILE_SIZE
            half_arc = CANNON_L2_ARC / 2  # 10°
            for offset in [-half_arc, 0, half_arc]:
                angle_rad = facing_rad + math.radians(offset)
                proj_vx = self.ship.vx + speed * math.cos(angle_rad)
                proj_vy = self.ship.vy + speed * math.sin(angle_rad)
                self.projectiles.append(Projectile(tip_x, tip_y, proj_vx, proj_vy,
                                                   color, size))

        elif power == 3:
            # Three white 4x4 projectiles at 8 px/frame
            speed = CANNON_L3_SPEED
            color = CANNON_L3_COLOR
            size = CANNON_L3_PROJECTILE_SIZE
            half_arc = CANNON_L2_ARC / 2  # 10°
            for offset in [-half_arc, 0, half_arc]:
                angle_rad = facing_rad + math.radians(offset)
                proj_vx = self.ship.vx + speed * math.cos(angle_rad)
                proj_vy = self.ship.vy + speed * math.sin(angle_rad)
                self.projectiles.append(Projectile(tip_x, tip_y, proj_vx, proj_vy,
                                                   color, size))

    def _get_cannon_max_flight(self, power):
        """Get max projectiles in flight for the given power level.

        Args:
            power: Weapon power level (1, 2, or 3).

        Returns:
            Maximum number of projectiles allowed in flight.
        """
        if power == 1:
            return CANNON_L1_MAX_FLIGHT
        elif power == 2:
            return CANNON_L2_MAX_FLIGHT
        else:
            return CANNON_L3_MAX_FLIGHT

    # ── Laser weapon ─────────────────────────────────────────────────────

    def _activate_laser(self):
        """Attempt to activate the laser beam.

        Only activates if the laser is not already active and there is
        enough charge (>= LASER_MIN_CHARGE_TO_ACTIVATE).
        """
        if self.weapon_type != WEAPON_LASER:
            return
        if self.laser_active:
            return
        if self.laser_charge < LASER_MIN_CHARGE_TO_ACTIVATE:
            return
        self.laser_active = True
        self.laser_hit_asteroids.clear()

    def _deactivate_laser(self):
        """Deactivate the laser beam."""
        self.laser_active = False
        self.laser_hit_asteroids.clear()

    def _get_laser_params(self):
        """Get laser beam parameters for the current power level.

        Returns:
            Tuple of (width, length, color, drain_rate, recharge_rate).
        """
        power = self.weapon_power
        if power == 1:
            return (
                LASER_L1_WIDTH, LASER_L1_LENGTH, LASER_L1_COLOR,
                LASER_L1_DRAIN_RATE, LASER_L1_RECHARGE_RATE,
            )
        elif power == 2:
            return (
                LASER_L2_WIDTH, LASER_L2_LENGTH, LASER_L2_COLOR,
                LASER_L2_DRAIN_RATE, LASER_L2_RECHARGE_RATE,
            )
        else:  # power == 3
            return (
                LASER_L3_WIDTH, LASER_L3_LENGTH, LASER_L3_COLOR,
                LASER_L3_DRAIN_RATE, LASER_L3_RECHARGE_RATE,
            )

    def _update_laser(self, keys):
        """Update laser charge, activation state, and collision detection.

        Args:
            keys: Result of pygame.key.get_pressed().
        """
        if self.weapon_type != WEAPON_LASER:
            return

        _, _, _, drain_rate, recharge_rate = self._get_laser_params()

        if self.laser_active:
            # Drain charge while beam is active
            self.laser_charge -= drain_rate
            self.laser_charge = max(0, self.laser_charge)

            # Deactivate if charge dropped below minimum
            if self.laser_charge < LASER_MIN_CHARGE_TO_ACTIVATE:
                self._deactivate_laser()
                return

            # Check for asteroid collisions
            self._check_lasteroid_collision()
        else:
            # Recharge when inactive and space bar is not held
            if not keys[pygame.K_SPACE]:
                self.laser_charge += recharge_rate
                self.laser_charge = min(LASER_MAX_CHARGE, self.laser_charge)

    def _check_lasteroid_collision(self):
        """Check if the active laser beam has hit any asteroid.

        Uses sampling along the beam line to detect collisions, with
        screen wrapping awareness. On first hit, the asteroid is split
        or destroyed (L3 destroys instantly regardless of size), and the
        beam deactivates.
        """
        if not self.laser_active:
            return

        beam_width, beam_length, _, _, _ = self._get_laser_params()
        tip_x, tip_y = self.ship.tip
        facing_rad = math.radians(self.ship.angle - 90)
        dx = math.cos(facing_rad)
        dy = math.sin(facing_rad)

        # Sampling interval: small enough to catch all collisions
        SAMPLE_INTERVAL = 5  # pixels between samples

        best_hit = None       # (asteroid_index, distance along beam)
        best_distance = float('inf')
        # Track closest powerup hit separately
        best_powerup_distance = float('inf')

        for t in range(0, int(beam_length) + 1, SAMPLE_INTERVAL):
            # Sample point along beam, with screen wrapping
            sx = (tip_x + dx * t) % self.window_width
            sy = (tip_y + dy * t) % self.window_height

            for ai, asteroid in enumerate(self.asteroids):
                if ai in self.laser_hit_asteroids:
                    continue

                adx = sx - asteroid.x
                ady = sy - asteroid.y
                # Account for screen wrapping in distance check
                if abs(adx) > self.window_width / 2:
                    adx -= math.copysign(self.window_width, adx)
                if abs(ady) > self.window_height / 2:
                    ady -= math.copysign(self.window_height, ady)

                distance = math.hypot(adx, ady)
                hit_threshold = asteroid.radius + beam_width / 2

                if distance < hit_threshold and t < best_distance:
                    best_hit = ai
                    best_distance = t

            # Check if beam hits the active powerup
            if self.powerup is not None:
                pdx = sx - self.powerup.x
                pdy = sy - self.powerup.y
                # Account for screen wrapping in distance check
                if abs(pdx) > self.window_width / 2:
                    pdx -= math.copysign(self.window_width, pdx)
                if abs(pdy) > self.window_height / 2:
                    pdy -= math.copysign(self.window_height, pdy)

                pdistance = math.hypot(pdx, pdy)
                phit_threshold = POWERUP_RADIUS + beam_width / 2

                if pdistance < phit_threshold and t < best_powerup_distance:
                    best_powerup_distance = t

        # Resolve the closest hit (asteroid or powerup)
        if best_hit is not None and best_distance <= best_powerup_distance:
            # Hit an asteroid
            asteroid = self.asteroids[best_hit]
            self.laser_hit_asteroids.add(best_hit)

            if self.weapon_power == 3:
                # L3: instant destroy, bypass split
                self._destroy_asteroid(asteroid, best_hit)
            else:
                # L1/L2: normal split or destroy
                self._hit_asteroid_from_laser(asteroid, best_hit)

            # Beam deactivates after first hit
            self._deactivate_laser()
        elif best_powerup_distance < float('inf'):
            # Hit the powerup — destroy it and deactivate beam
            self.powerup = None
            self._deactivate_laser()

    def _destroy_asteroid(self, asteroid, asteroid_index):
        """Destroy an asteroid completely (used by laser L3).

        Increments the hit counter. Does not produce split asteroids.

        Args:
            asteroid: The asteroid to destroy.
            asteroid_index: Index in the asteroids list.
        """
        self.hit_count += 1
        self.asteroids.pop(asteroid_index)

    def _hit_asteroid_from_laser(self, asteroid, asteroid_index):
        """Handle an asteroid being hit by the laser (L1/L2 behavior).

        If the asteroid is smaller than ASTEROID_DESTRUCTION_RADIUS, it is
        destroyed and the hit counter is incremented. Otherwise, it splits
        into 2-3 smaller asteroids.

        Args:
            asteroid: The asteroid that was hit.
            asteroid_index: Index of the asteroid in the asteroids list.
        """
        if asteroid.radius < ASTEROID_DESTRUCTION_RADIUS:
            # Destroy — count as a hit
            self.hit_count += 1
            self._spawn_explosion(asteroid.x, asteroid.y, asteroid.radius, True)
            self.asteroids.pop(asteroid_index)
        else:
            # Split into 2-3 smaller asteroids
            num_splits = random.randint(2, 3)
            new_radius = asteroid.radius / ASTEROID_SPLIT_DIVISOR
            new_speed = math.hypot(asteroid.vx, asteroid.vy) * ASTEROID_SPLIT_SPEED_MULT

            # Spawn split explosion
            self._spawn_explosion(asteroid.x, asteroid.y, asteroid.radius, False)

            # Remove the parent asteroid
            self.asteroids.pop(asteroid_index)

            # Create replacement asteroids
            for _ in range(num_splits):
                angle = random.uniform(0, 360)
                self.asteroids.append(Asteroid(
                    asteroid.x, asteroid.y, new_radius, new_speed, angle
                ))

    # ── Laser rendering ──────────────────────────────────────────────────

    def _draw_laser_beam(self):
        """Render the active laser beam from the ship's tip.

        Handles screen wrapping by drawing multiple segments when the
        beam crosses a screen edge.
        """
        if not self.laser_active:
            return

        beam_width, beam_length, beam_color, _, _ = self._get_laser_params()
        tip_x, tip_y = self.ship.tip
        facing_rad = math.radians(self.ship.angle - 90)
        dx = math.cos(facing_rad)
        dy = math.sin(facing_rad)

        end_x = tip_x + dx * beam_length
        end_y = tip_y + dy * beam_length

        # Determine which edges the beam crosses (for wrapping)
        wraps_x = (tip_x < 0) != (end_x < 0) or \
                  (tip_x >= self.window_width) != (end_x >= self.window_width)
        wraps_y = (tip_y < 0) != (end_y < 0) or \
                  (tip_y >= self.window_height) != (end_y >= self.window_height)

        # More precise wrapping detection: check if beam starts and ends
        # on different sides of each screen edge
        wraps_x = (
            (0 < tip_x < self.window_width and
             (end_x < 0 or end_x >= self.window_width)) or
            (0 < end_x < self.window_width and
             (tip_x < 0 or tip_x >= self.window_width))
        )
        wraps_y = (
            (0 < tip_y < self.window_height and
             (end_y < 0 or end_y >= self.window_height)) or
            (0 < end_y < self.window_height and
             (tip_y < 0 or tip_y >= self.window_height))
        )

        # Clamp endpoints for the primary segment
        px1, py1 = tip_x, tip_y
        px2, py2 = end_x, end_y

        if not wraps_x and not wraps_y:
            # Simple case: no wrapping
            pygame.draw.line(self.screen, beam_color,
                             (int(px1), int(py1)),
                             (int(px2), int(py2)),
                             max(beam_width, 1))
        else:
            # Beam crosses a screen edge — compute segment boundaries
            if wraps_x:
                # Determine which edge is crossed
                if dx > 0:
                    # Crossing right edge
                    seg1_end_x = float(self.window_width)
                    seg2_start_x = 0.0
                else:
                    # Crossing left edge
                    seg1_end_x = 0.0
                    seg2_start_x = float(self.window_width)

                # Compute Y at the wrap boundary using line parametric equation
                t1 = (seg1_end_x - tip_x) / dx if dx != 0 else 0
                seg1_end_y = tip_y + dy * t1
                t2 = (seg2_start_x - tip_x) / dx if dx != 0 else 0
                seg2_end_y = tip_y + dy * t2

                pygame.draw.line(self.screen, beam_color,
                                 (int(tip_x), int(tip_y)),
                                 (int(seg1_end_x), int(seg1_end_y)),
                                 max(beam_width, 1))
                pygame.draw.line(self.screen, beam_color,
                                 (int(seg2_start_x), int(seg2_end_y % self.window_height)),
                                 (int(end_x % self.window_width),
                                  int(end_y % self.window_height)),
                                 max(beam_width, 1))

            if wraps_y:
                # Determine which edge is crossed
                if dy > 0:
                    seg1_end_y = float(self.window_height)
                    seg2_start_y = 0.0
                else:
                    seg1_end_y = 0.0
                    seg2_start_y = float(self.window_height)

                t1 = (seg1_end_y - tip_y) / dy if dy != 0 else 0
                seg1_end_x = tip_x + dx * t1
                t2 = (seg2_start_y - tip_y) / dy if dy != 0 else 0
                seg2_end_x = tip_x + dx * t2

                pygame.draw.line(self.screen, beam_color,
                                 (int(tip_x), int(tip_y)),
                                 (int(seg1_end_x % self.window_width),
                                  int(seg1_end_y)),
                                 max(beam_width, 1))
                pygame.draw.line(self.screen, beam_color,
                                 (int(seg2_end_x % self.window_width),
                                  int(seg2_start_y)),
                                 (int(end_x % self.window_width),
                                  int(end_y % self.window_height)),
                                 max(beam_width, 1))

    # ── Shield weapon ────────────────────────────────────────────────────

    def _activate_shield(self):
        """Attempt to activate the shield.

        Only activates if the shield is not already active and there is
        enough charge (>= SHIELD_MIN_CHARGE_TO_ACTIVATE).
        """
        if self.weapon_type != WEAPON_SHIELD:
            return
        if self.shield_active:
            return
        if self.shield_charge < SHIELD_MIN_CHARGE_TO_ACTIVATE:
            return
        self.shield_active = True
        self.shield_hit_asteroids.clear()

    def _get_shield_params(self):
        """Get shield parameters for the current power level.

        Returns:
            Tuple of (radius, border_width, bounce_divisor, drain_rate,
                      recharge_rate).
        """
        power = self.weapon_power
        if power == 1:
            return (
                SHIELD_L1_RADIUS, SHIELD_L1_BORDER,
                SHIELD_L1_BOUNCE_DIVISOR,
                SHIELD_L1_DRAIN_RATE, SHIELD_L1_RECHARGE_RATE,
            )
        elif power == 2:
            return (
                SHIELD_L2_RADIUS, SHIELD_L2_BORDER,
                SHIELD_L2_BOUNCE_DIVISOR,
                SHIELD_L2_DRAIN_RATE, SHIELD_L2_RECHARGE_RATE,
            )
        else:  # power == 3
            return (
                SHIELD_L3_RADIUS, SHIELD_L3_BORDER,
                SHIELD_L3_BOUNCE_DIVISOR,
                SHIELD_L3_DRAIN_RATE, SHIELD_L3_RECHARGE_RATE,
            )

    def _update_shield(self, keys):
        """Update shield charge, activation state, and collision detection.

        Args:
            keys: Result of pygame.key.get_pressed().
        """
        if self.weapon_type != WEAPON_SHIELD:
            return

        _, _, _, drain_rate, recharge_rate = self._get_shield_params()

        if self.shield_active:
            # Drain charge while shield is active
            self.shield_charge -= drain_rate
            self.shield_charge = max(0, self.shield_charge)

            # Deactivate if charge dropped below minimum
            if self.shield_charge < SHIELD_MIN_CHARGE_TO_ACTIVATE:
                self.shield_active = False
                self.shield_hit_asteroids.clear()
                return

            # Check for asteroid collisions
            self._check_shield_asteroid_collisions()

            # Check for powerup collisions
            self._check_shield_powerup_collision()
        else:
            # Recharge when inactive and space bar is not held
            if not keys[pygame.K_SPACE]:
                self.shield_charge += recharge_rate
                self.shield_charge = min(SHIELD_MAX_CHARGE, self.shield_charge)

    def _check_shield_asteroid_collisions(self):
        """Check if any asteroid has collided with the active shield.

        On collision, the asteroid is split or destroyed using the normal
        hit rules, and the ship's velocity is replaced by a bounce velocity
        directed away from the asteroid.

        Each asteroid can only trigger one bounce per frame to prevent
        multiple asteroids from compounding the bounce effect.
        """
        if not self.shield_active:
            return

        shield_radius, _, bounce_divisor, _, _ = self._get_shield_params()
        bounce_speed = shield_radius / bounce_divisor

        for ai, asteroid in enumerate(self.asteroids):
            if ai in self.shield_hit_asteroids:
                continue

            dx = self.ship.x - asteroid.x
            dy = self.ship.y - asteroid.y
            distance = math.hypot(dx, dy)
            hit_threshold = shield_radius + asteroid.radius

            if distance < hit_threshold:
                # Collision! Mark asteroid as hit this frame
                self.shield_hit_asteroids.add(ai)

                # Bounce ship away from asteroid
                if distance > 0:
                    # Normalize direction away from asteroid
                    nx = dx / distance
                    ny = dy / distance
                else:
                    # Asteroid is exactly on ship — bounce in ship's facing direction
                    facing_rad = math.radians(self.ship.angle - 90)
                    nx = math.cos(facing_rad)
                    ny = math.sin(facing_rad)

                self.ship.vx = nx * bounce_speed
                self.ship.vy = ny * bounce_speed

                # Apply asteroid hit (split or destroy)
                self._hit_asteroid_from_shield(asteroid, ai)

                # If we're in game over mode (shouldn't happen with shield,
                # but be safe), stop processing
                if self.current_mode != MODE_GAME:
                    return

    def _check_shield_powerup_collision(self):
        """Check if the active shield has collided with the powerup.

        If a collision is detected, the powerup icon is destroyed.
        The shield does not bounce off the powerup; it simply destroys it.
        """
        if not self.shield_active:
            return
        if self.powerup is None:
            return

        shield_radius, _, _, _, _ = self._get_shield_params()

        dx = self.ship.x - self.powerup.x
        dy = self.ship.y - self.powerup.y
        distance = math.hypot(dx, dy)
        hit_threshold = shield_radius + POWERUP_RADIUS

        if distance < hit_threshold:
            # Shield destroys the powerup on contact
            self.powerup = None

    def _hit_asteroid_from_shield(self, asteroid, asteroid_index):
        """Handle an asteroid being hit by the shield.

        If the asteroid is smaller than ASTEROID_DESTRUCTION_RADIUS, it is
        destroyed and the hit counter is incremented. Otherwise, it splits
        into 2-3 smaller asteroids.

        Args:
            asteroid: The asteroid that was hit.
            asteroid_index: Index of the asteroid in the asteroids list.
        """
        if asteroid.radius < ASTEROID_DESTRUCTION_RADIUS:
            # Destroy — count as a hit
            self.hit_count += 1
            self._spawn_explosion(asteroid.x, asteroid.y, asteroid.radius, True)
            self.asteroids.pop(asteroid_index)
        else:
            # Split into 2-3 smaller asteroids
            num_splits = random.randint(2, 3)
            new_radius = asteroid.radius / ASTEROID_SPLIT_DIVISOR
            new_speed = math.hypot(asteroid.vx, asteroid.vy) * ASTEROID_SPLIT_SPEED_MULT

            # Spawn split explosion
            self._spawn_explosion(asteroid.x, asteroid.y, asteroid.radius, False)

            # Remove the parent asteroid
            self.asteroids.pop(asteroid_index)

            # Create replacement asteroids
            for _ in range(num_splits):
                angle = random.uniform(0, 360)
                self.asteroids.append(Asteroid(
                    asteroid.x, asteroid.y, new_radius, new_speed, angle
                ))

    def _draw_shield(self):
        """Render the shield as a red circle around the ship."""
        if not self.shield_active:
            return

        shield_radius, border_width, _, _, _ = self._get_shield_params()
        pygame.draw.circle(
            self.screen, SHIELD_COLOR,
            (int(self.ship.x), int(self.ship.y)),
            shield_radius,
            border_width,
        )

    # ── Powerup management ───────────────────────────────────────────────

    def _try_spawn_powerup(self):
        """Attempt to spawn a new powerup if the timer has expired.

        Spawns a random weapon type powerup at a safe position (not on ship
        or asteroids). Only one powerup can exist at a time.
        """
        if self.powerup is not None:
            return  # Already have one on screen

        self.powerup_spawn_timer -= 1
        if self.powerup_spawn_timer > 0:
            return  # Not time yet

        # Timer expired — try to spawn
        powerup_type = random.choice([
            POWERUP_CANNON, POWERUP_LASER, POWERUP_SHIELD
        ])

        # Try random positions
        for _ in range(50):
            x = random.uniform(POWERUP_RADIUS,
                               self.window_width - POWERUP_RADIUS)
            y = random.uniform(POWERUP_RADIUS,
                               self.window_height - POWERUP_RADIUS)
            if self._is_safe_powerup_position(x, y):
                self.powerup = Powerup(x, y, powerup_type)
                self.powerup_spawn_timer = POWERUP_SPAWN_INTERVAL_FRAMES
                return

        # Fallback: try corners
        corners = [
            (50, 50),
            (self.window_width - 50, 50),
            (50, self.window_height - 50),
            (self.window_width - 50, self.window_height - 50),
        ]
        for cx, cy in corners:
            if self._is_safe_powerup_position(cx, cy):
                self.powerup = Powerup(cx, cy, powerup_type)
                self.powerup_spawn_timer = POWERUP_SPAWN_INTERVAL_FRAMES
                return

    def _is_safe_powerup_position(self, x, y):
        """Check if a position is safe for powerup spawning.

        A position is safe if it's not too close to the ship or any asteroid.

        Args:
            x: Horizontal position to check.
            y: Vertical position to check.

        Returns:
            True if the position is safe, False otherwise.
        """
        # Check distance from ship
        dx = x - self.ship.x
        dy = y - self.ship.y
        if math.hypot(dx, dy) < POWERUP_RADIUS + SHIP_RADIUS + 30:
            return False

        # Check distance from asteroids
        for asteroid in self.asteroids:
            dx = x - asteroid.x
            dy = y - asteroid.y
            if math.hypot(dx, dy) < POWERUP_RADIUS + asteroid.radius + 30:
                return False

        return True

    def _check_ship_powerup_collision(self):
        """Check if the ship has collected the active powerup.

        If collected:
        - Same weapon type → power level +1 (max 3)
        - Different weapon type → switch to that type, power resets to 1
        """
        if self.powerup is None:
            return

        dx = self.ship.x - self.powerup.x
        dy = self.ship.y - self.powerup.y
        distance = math.hypot(dx, dy)

        if distance < SHIP_RADIUS + POWERUP_RADIUS:
            # Determine which weapon type this powerup represents
            if self.powerup.powerup_type == POWERUP_CANNON:
                new_weapon = WEAPON_CANNON
            elif self.powerup.powerup_type == POWERUP_LASER:
                new_weapon = WEAPON_LASER
            else:  # POWERUP_SHIELD
                new_weapon = WEAPON_SHIELD

            if self.weapon_type == new_weapon:
                # Same weapon type → upgrade power level
                self.weapon_power = min(3, self.weapon_power + 1)
            else:
                # Different weapon type → switch and reset power
                self.weapon_type = new_weapon
                self.weapon_power = 1
                # Deactivate other weapons
                self.laser_active = False
                self.shield_active = False

            # Remove powerup
            self.powerup = None

    def _check_asteroid_powerup_collision(self):
        """Check if any asteroid has collided with the active powerup.

        If collision occurs:
        - Powerup is destroyed
        - Asteroid is split or destroyed following normal hit rules
        """
        if self.powerup is None:
            return

        for ai, asteroid in enumerate(self.asteroids):
            dx = self.powerup.x - asteroid.x
            dy = self.powerup.y - asteroid.y
            distance = math.hypot(dx, dy)

            if distance < POWERUP_RADIUS + asteroid.radius:
                # Powerup destroyed
                self.powerup = None

                # Asteroid is hit (split or destroy)
                if asteroid.radius < ASTEROID_DESTRUCTION_RADIUS:
                    self.hit_count += 1
                    self.asteroids.pop(ai)
                else:
                    num_splits = random.randint(2, 3)
                    new_radius = asteroid.radius / ASTEROID_SPLIT_DIVISOR
                    new_speed = math.hypot(
                        asteroid.vx, asteroid.vy
                    ) * ASTEROID_SPLIT_SPEED_MULT

                    self.asteroids.pop(ai)
                    for _ in range(num_splits):
                        angle = random.uniform(0, 360)
                        self.asteroids.append(Asteroid(
                            asteroid.x, asteroid.y,
                            new_radius, new_speed, angle
                        ))
                return  # Only one collision per frame

    def _draw_powerup(self):
        """Render the active powerup if one exists."""
        if self.powerup is not None:
            self.powerup.draw(self.screen)

    # ── Cosmetic effects (Stage 10) ──────────────────────────────────────

    def _spawn_thruster_particles(self):
        """Spawn thruster exhaust particles when ship is thrusting.

        Particles are ejected from the ship's rear in the opposite direction
        of the ship's facing, with a slight random spread.
        """
        if self.current_mode != MODE_GAME:
            return

        keys = pygame.key.get_pressed()
        if not keys[pygame.K_UP]:
            return

        # Ship rear position (opposite of tip)
        half_h = SHIP_HEIGHT / 2
        facing_rad = math.radians(self.ship.angle - 90)
        rear_x = self.ship.x - half_h * math.cos(facing_rad)
        rear_y = self.ship.y - half_h * math.sin(facing_rad)

        for _ in range(THRUSTER_EMIT_RATE):
            # Random angle within ±10 degrees of opposite direction
            angle_offset = random.uniform(
                -math.radians(THRUSTER_ARC_SPREAD),
                math.radians(THRUSTER_ARC_SPREAD),
            )
            particle_angle = facing_rad + math.pi + angle_offset

            # Random speed between 6-10 px/frame
            speed = random.uniform(
                THRUSTER_BASE_SPEED_MIN, THRUSTER_BASE_SPEED_MAX
            )
            vx = self.ship.vx + speed * math.cos(particle_angle)
            vy = self.ship.vy + speed * math.sin(particle_angle)

            # Random radius and color
            radius = random.randint(
                THRUSTER_PARTICLE_RADIUS_MIN,
                THRUSTER_PARTICLE_RADIUS_MAX,
            )
            color = random.choice(THRUSTER_COLORS)

            self.particles.append(Particle(
                rear_x, rear_y, vx, vy, color, radius, THRUSTER_ALPHA_DECAY
            ))

    def _spawn_explosion(self, x, y, radius, is_destruction):
        """Spawn explosion particles at the given position.

        Args:
            x: Horizontal position of explosion center.
            y: Vertical position of explosion center.
            radius: Asteroid radius (used to determine particle count).
            is_destruction: True for destruction (gray), False for split (colorful).
        """
        count = int(radius * EXPLOSION_COUNT_MULTIPLIER)
        if count < 3:
            count = 3

        for _ in range(count):
            # Random direction
            angle = random.uniform(0, 360)
            angle_rad = math.radians(angle)

            # Random speed
            speed = random.uniform(
                EXPLOSION_VELOCITY_MIN, EXPLOSION_VELOCITY_MAX
            )
            vx = speed * math.cos(angle_rad)
            vy = speed * math.sin(angle_rad)

            # Color based on explosion type
            if is_destruction:
                color = EXPLOSION_DESTRUCTION_COLOR
            else:
                color = random.choice(EXPLOSION_SPLIT_COLORS)

            # Random radius and alpha decay
            radius = random.randint(2, 5)
            alpha_decay = random.uniform(
                EXPLOSION_ALPHA_DECAY_MIN, EXPLOSION_ALPHA_DECAY_MAX
            )

            self.particles.append(Particle(
                x, y, vx, vy, color, radius, alpha_decay
            ))

    def _update_particles(self):
        """Update all particles, removing dead ones."""
        self.particles = [
            p for p in self.particles
            if p.update(self.window_width, self.window_height)
        ]

    def _draw_particles(self):
        """Render all active particles."""
        for particle in self.particles:
            particle.draw(self.screen)

    def _draw_starfield(self):
        """Render the starfield background."""
        for star in self.stars:
            star.draw(self.screen)

    def _update_starfield(self):
        """Update star brightness (twinkle effect)."""
        for star in self.stars:
            star.update()

    def _draw_hud(self):
        """Render the complete HUD panel in the upper-right corner.

        Panel features:
        - Rounded cyan border (4 px width)
        - 60% opacity dark background
        - Displays: Level, Hits, Weapon name, Power level
        - Charge bar (for laser or shield only)

        HUD is only visible in Game Mode.
        """
        if self.current_mode != MODE_GAME:
            return

        font = pygame.font.Font(None, HUD_FONT_SIZE)

        # Determine weapon color
        if self.weapon_type == WEAPON_CANNON:
            weapon_color = HUD_CANNON_COLOR
        elif self.weapon_type == WEAPON_LASER:
            weapon_color = HUD_LASER_COLOR
        else:  # WEAPON_SHIELD
            weapon_color = HUD_SHIELD_COLOR

        # Build HUD lines
        lines = [
            ("Level: " + str(self.level), COLOR_WHITE),
            ("Hits: " + str(self.hit_count), COLOR_WHITE),
            ("Weapon: " + self.weapon_type, weapon_color),
            ("Power: " + str(self.weapon_power), weapon_color),
        ]

        # Determine if we need a charge bar line
        has_charge = self.weapon_type in (WEAPON_LASER, WEAPON_SHIELD)

        # Measure all text to compute panel width
        max_width = 0
        for text, _ in lines:
            tw = font.size(text)[0]
            if tw > max_width:
                max_width = tw

        if has_charge:
            charge_label = font.render("Charge:", True, COLOR_WHITE)
            charge_label_w = charge_label.get_width()
            charge_total_w = charge_label_w + HUD_CHARGE_BAR_GAP + HUD_CHARGE_BAR_WIDTH
            if charge_total_w > max_width:
                max_width = charge_total_w

        # Panel dimensions
        panel_width = max_width + HUD_PADDING * 2
        line_height = HUD_LINE_SPACING
        panel_height = (len(lines) * line_height) + HUD_PADDING * 2

        if has_charge:
            panel_height += HUD_CHARGE_BAR_HEIGHT + HUD_CHARGE_BAR_GAP

        # Panel position (upper-right corner)
        panel_x = self.window_width - panel_width - HUD_MARGIN
        panel_y = HUD_MARGIN

        # Create panel surface with alpha
        panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)

        # Draw semi-transparent background
        bg_color = (0, 0, 0, HUD_BACKGROUND_ALPHA)
        panel.fill(bg_color)

        # Draw rounded border (cyan)
        pygame.draw.rect(
            panel, HUD_BORDER_COLOR,
            (0, 0, panel_width, panel_height),
            width=HUD_BORDER_WIDTH,
            border_radius=HUD_BORDER_RADIUS,
        )

        # Blit panel to screen
        self.screen.blit(panel, (panel_x, panel_y))

        # Render text lines onto screen (positioned relative to panel)
        text_x = panel_x + HUD_PADDING
        for i, (text, color) in enumerate(lines):
            surface = font.render(text, True, color)
            text_y = panel_y + HUD_PADDING + (i * line_height)
            self.screen.blit(surface, (text_x, text_y))

        # Render charge bar if applicable
        if has_charge:
            charge_y = panel_y + HUD_PADDING + (len(lines) * line_height) + HUD_CHARGE_BAR_GAP

            # "Charge:" label
            charge_label = font.render("Charge:", True, COLOR_WHITE)
            self.screen.blit(charge_label, (text_x, charge_y))

            # Charge bar background (dark gray)
            bar_x = text_x + charge_label_w + HUD_CHARGE_BAR_GAP
            bar_rect = pygame.Rect(
                bar_x, charge_y,
                HUD_CHARGE_BAR_WIDTH, HUD_CHARGE_BAR_HEIGHT,
            )
            pygame.draw.rect(self.screen, (40, 40, 40), bar_rect,
                             border_radius=3)

            # Charge bar fill
            if self.weapon_type == WEAPON_LASER:
                charge = self.laser_charge
                max_charge = LASER_MAX_CHARGE
                fill_color = weapon_color
            else:  # WEAPON_SHIELD
                charge = self.shield_charge
                max_charge = SHIELD_MAX_CHARGE
                fill_color = weapon_color

            fill_width = int(HUD_CHARGE_BAR_WIDTH * (charge / max_charge))
            if fill_width > 0:
                fill_rect = pygame.Rect(
                    bar_x, charge_y, fill_width, HUD_CHARGE_BAR_HEIGHT
                )
                pygame.draw.rect(self.screen, fill_color, fill_rect,
                                 border_radius=2)

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
        self.projectiles.clear()
        self.gameover_reason = ""
        self.laser_active = False
        self.laser_hit_asteroids.clear()
        self.shield_active = False
        self.shield_hit_asteroids.clear()
        self.powerup = None
        self.powerup_spawn_timer = POWERUP_SPAWN_INTERVAL_FRAMES  # Reset spawn timer for new level
        self.particles.clear()  # Clear particles for new level
        self._spawn_level_asteroids(level_number)
        self.level_text_timer = LEVEL_TEXT_DURATION_FRAMES
        self.level_text_level = level_number

    def _start_new_game(self):
        """Start a completely new game from level 1, resetting all state."""
        self.hit_count = 0
        self.weapon_type = WEAPON_CANNON
        self.weapon_power = 1
        self.laser_charge = LASER_MAX_CHARGE
        self.laser_active = False
        self.laser_hit_asteroids.clear()
        self.shield_charge = SHIELD_MAX_CHARGE
        self.shield_active = False
        self.shield_hit_asteroids.clear()
        self.powerup = None
        self.powerup_spawn_timer = POWERUP_SPAWN_INTERVAL_FRAMES
        self._start_level(1)

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

    # ── Collision detection ──────────────────────────────────────────────

    def _check_ship_asteroid_collision(self):
        """Check if the ship has collided with any asteroid.

        If a collision is detected, immediately transitions to Game Over mode.
        """
        for asteroid in self.asteroids:
            dx = self.ship.x - asteroid.x
            dy = self.ship.y - asteroid.y
            distance = math.hypot(dx, dy)
            # Ship collision radius + asteroid radius
            if distance < SHIP_RADIUS + asteroid.radius:
                # Spawn explosion at collision point
                self._spawn_explosion(
                    self.ship.x, self.ship.y, SHIP_RADIUS, True
                )
                self.current_mode = MODE_GAMEOVER
                self.gameover_reason = ""
                return True
        return False

    def _check_projectile_asteroid_collisions(self):
        """Check all projectiles against all asteroids.

        Handles asteroid splitting/destruction and projectile removal.
        """
        # Collect indices of projectiles to remove
        projectiles_to_remove = set()
        # Collect asteroids to remove and their replacements
        asteroids_to_remove = set()
        new_asteroids = []

        for pi, projectile in enumerate(self.projectiles):
            for ai, asteroid in enumerate(self.asteroids):
                if pi in projectiles_to_remove or ai in asteroids_to_remove:
                    continue

                dx = projectile.x - asteroid.x
                dy = projectile.y - asteroid.y
                distance = math.hypot(dx, dy)

                if distance < asteroid.radius:
                    # Hit! Remove projectile
                    projectiles_to_remove.add(pi)

                    # Split or destroy asteroid
                    self._hit_asteroid(asteroid, ai, new_asteroids)
                    asteroids_to_remove.add(ai)

        # Remove hit projectiles
        self.projectiles = [
            p for i, p in enumerate(self.projectiles)
            if i not in projectiles_to_remove
        ]

        # Remove hit asteroids and add replacements
        self.asteroids = [
            a for i, a in enumerate(self.asteroids)
            if i not in asteroids_to_remove
        ]
        self.asteroids.extend(new_asteroids)

    def _check_projectile_ship_collisions(self):
        """Check if any projectile has hit the player's own ship.

        Only projectiles past their invulnerability window can hit the ship.
        If a collision is detected, transitions to Game Over with
        "Friendly fire!" message.
        """
        for projectile in self.projectiles:
            if projectile.is_invulnerable:
                continue

            dx = projectile.x - self.ship.x
            dy = projectile.y - self.ship.y
            distance = math.hypot(dx, dy)

            if distance < SHIP_RADIUS:
                # Spawn explosion at collision point
                self._spawn_explosion(
                    self.ship.x, self.ship.y, SHIP_RADIUS, True
                )
                self.current_mode = MODE_GAMEOVER
                self.gameover_reason = "Friendly fire!"
                return

    def _check_projectile_powerup_collisions(self):
        """Check if any projectile has hit the active powerup.

        If a collision is detected, the projectile is removed and the
        powerup icon is destroyed.
        """
        if self.powerup is None:
            return

        projectiles_to_remove = set()

        for pi, projectile in enumerate(self.projectiles):
            if pi in projectiles_to_remove:
                continue

            dx = projectile.x - self.powerup.x
            dy = projectile.y - self.powerup.y
            distance = math.hypot(dx, dy)

            if distance < POWERUP_RADIUS:
                # Hit! Remove projectile and destroy powerup
                projectiles_to_remove.add(pi)
                self.powerup = None
                break  # Powerup is gone, no more collisions possible

        # Remove hit projectiles
        if projectiles_to_remove:
            self.projectiles = [
                p for i, p in enumerate(self.projectiles)
                if i not in projectiles_to_remove
            ]

    def _hit_asteroid(self, asteroid, asteroid_index, new_asteroids_list):
        """Handle an asteroid being hit by a projectile.

        If the asteroid is smaller than ASTEROID_DESTRUCTION_RADIUS, it is
        destroyed and the hit counter is incremented. Otherwise, it splits
        into 2-3 smaller asteroids.

        Args:
            asteroid: The asteroid that was hit.
            asteroid_index: Index of the asteroid in the asteroids list.
            new_asteroids_list: List to append new asteroids to.
        """
        if asteroid.radius < ASTEROID_DESTRUCTION_RADIUS:
            # Destroy — count as a hit
            self.hit_count += 1
            self._spawn_explosion(asteroid.x, asteroid.y, asteroid.radius, True)
        else:
            # Split into 2-3 smaller asteroids
            num_splits = random.randint(2, 3)
            new_radius = asteroid.radius / ASTEROID_SPLIT_DIVISOR
            new_speed = math.hypot(asteroid.vx, asteroid.vy) * ASTEROID_SPLIT_SPEED_MULT

            # Spawn split explosion
            self._spawn_explosion(asteroid.x, asteroid.y, asteroid.radius, False)

            for _ in range(num_splits):
                angle = random.uniform(0, 360)
                new_asteroids_list.append(Asteroid(
                    asteroid.x, asteroid.y, new_radius, new_speed, angle
                ))

    def _check_level_complete(self):
        """Check if all asteroids have been destroyed.

        If so, advance to the next level.
        """
        if len(self.asteroids) == 0 and self.current_mode == MODE_GAME:
            self._start_level(self.level + 1)

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
        # Starfield updates in all modes
        self._update_starfield()

        # Title screen asteroids update on title screen
        if self.current_mode == MODE_TITLE:
            self._update_title_asteroids()

        if self.current_mode == MODE_GAME:
            self._update_game()

    def _update_game(self):
        """Update gameplay: ship, asteroids, projectiles, laser, shield, powerups."""
        keys = pygame.key.get_pressed()
        self.ship.update(keys, self.window_width, self.window_height)

        # Update all asteroids — but freeze them while the "Begin level N"
        # text is fading, so they can't drift into the ship before it appears
        if self.level_text_timer <= 0:
            for asteroid in self.asteroids:
                asteroid.update(self.window_width, self.window_height)

        # Update projectiles (only after fade-out)
        if self.level_text_timer <= 0:
            self.projectiles = [
                p for p in self.projectiles
                if p.update(self.window_width, self.window_height)
            ]

            # Update laser (charge drain/recharge, collision detection)
            self._update_laser(keys)

            # Update shield (charge drain/recharge, collision + bounce)
            self._update_shield(keys)

            # Spawn thruster exhaust particles
            self._spawn_thruster_particles()

            # Update all particles (thruster + explosions)
            self._update_particles()

            # Update powerup (drift, spawning, collision)
            if self.powerup is not None:
                self.powerup.update(self.window_width, self.window_height)

            # Try to spawn a new powerup if timer has expired
            self._try_spawn_powerup()

            # Collision detection
            # Note: ship-asteroid collision is skipped when shield is active,
            # since the shield handles those impacts
            if not self.shield_active:
                self._check_ship_asteroid_collision()
            if self.current_mode == MODE_GAME:
                self._check_projectile_asteroid_collisions()
                self._check_projectile_ship_collisions()
                self._check_projectile_powerup_collisions()
                self._check_ship_powerup_collision()
                self._check_asteroid_powerup_collision()
                self._check_level_complete()

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
        """Render the Title Screen with starfield, asteroids, and polished text."""
        # Draw starfield background
        self._draw_starfield()

        # Draw tumbling asteroids
        for asteroid in self.title_asteroids:
            asteroid.draw(self.screen)

        # Draw title text (extra-large font)
        title_font = pygame.font.Font(None, FONT_SIZE_TITLE)
        title = title_font.render("Super Asteroids", True, COLOR_WHITE)
        self._blit_centered(title, vertical_ratio=0.25)

        # Draw instructions
        instructions = [
            "Arrow Keys or WASD: Rotate and Thrust",
            "Space: Shoot",
            "ESC: Pause  |  F11: Fullscreen",
            "",
            "Press Enter to Start",
        ]
        for i, line in enumerate(instructions):
            text = self._fonts["small"].render(line, True, COLOR_WHITE)
            self._blit_centered(text, vertical_ratio=0.42 + i * 0.04)

    def _draw_game_screen(self):
        """Render the Game Mode: asteroids, ship, projectiles, laser, shield, powerups, HUD.

        The ship is hidden while the 'Begin level N' text is fading in,
        so the player doesn't see the ship until the fade-out completes.
        Asteroids are always drawn (they're visible during the fade).
        """
        # Draw starfield background
        self._draw_starfield()

        # Draw all asteroids (always visible)
        for asteroid in self.asteroids:
            asteroid.draw(self.screen)

        # Draw all projectiles
        for projectile in self.projectiles:
            projectile.draw(self.screen)

        # Draw powerup (always visible when present)
        self._draw_powerup()

        # Draw "Begin level N" fade-out text (always drawn on top)
        if self.level_text_timer > 0:
            self._draw_level_text()
        else:
            # Ship only appears after the fade-out text has finished
            self.ship.draw(self.screen)

            # Draw laser beam (only when ship is visible)
            self._draw_laser_beam()

            # Draw shield (only when ship is visible)
            self._draw_shield()

        # Draw particles (thruster + explosions) on top
        self._draw_particles()

        # Draw complete HUD
        self._draw_hud()

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
        """Render the Game Over screen."""
        # "GAME OVER" in red
        title = self._fonts["large"].render("GAME OVER", True, COLOR_RED)

        # Optional reason (e.g., "Friendly fire!")
        if self.gameover_reason:
            reason = self._fonts["medium"].render(
                self.gameover_reason, True, COLOR_GREEN
            )

        restart = self._fonts["small"].render("R to restart", True, COLOR_WHITE)
        exit_text = self._fonts["small"].render("ESC to exit", True, COLOR_WHITE)

        self._blit_centered(title, vertical_ratio=0.25)

        if self.gameover_reason:
            self._blit_centered(reason, vertical_ratio=0.42)
            self._blit_centered(restart, vertical_ratio=0.55)
            self._blit_centered(exit_text, vertical_ratio=0.65)
        else:
            self._blit_centered(restart, vertical_ratio=0.5)
            self._blit_centered(exit_text, vertical_ratio=0.6)

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
