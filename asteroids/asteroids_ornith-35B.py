#!/usr/bin/env python3
"""
Asteroids - Classic arcade game implemented with Pygame.
Controls:
  Left/Right Arrow  - Rotate ship
  Up Arrow          - Thrust
  Space             - Fire
  R                 - Restart (after game over)
  B                 - Toggle bonus feature (No Friendly Fire)
"""

import pygame
import random
import math

# ── Window & Constants ────────────────────────────────────────────────
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60

BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
GRAY = (100, 100, 100)
YELLOW = (255, 255, 0)
RED = (255, 50, 50)
CYAN = (0, 255, 255)
ORANGE = (255, 165, 0)

# Ship constants
SHIP_WIDTH = 10
SHIP_HEIGHT = 35
SHIP_ROTATION_SPEED = 5  # degrees per frame
THRUST_ACCEL = 0.3
MAX_SPEED = 8.0
FRICTION = 0.98

# Projectile constants
PROJECTILE_SPEED = 6.0
MAX_PROJECTILES = 3
PROJECTILE_LIFE_PX = 1000
PROJECTILE_SIZE = 4

# Asteroid constants
ASTEROID_LARGE_RADIUS = 40
ASTEROID_MEDIUM_RADIUS = ASTEROID_LARGE_RADIUS / 1.5
ASTEROID_SMALL_RADIUS = ASTEROID_MEDIUM_RADIUS / 1.5
MIN_ASTEROID_RADIUS = 15
ASTEROID_SPLIT_COUNT = 2  # 2-3, we'll randomize
ASTEROID_SPEED_MULT = 1.2
ASTEROID_BASE_SPEED = 2.0  # average of 1.5-2.5
ASTEROID_VERTEX_COUNT = 8

# Level constants
LEVEL_START_ASTEROIDS = 5
LEVEL_ADD_ASTEROIDS = 2
LEVEL_SPEED_INCREMENT = 0.3
LEVEL_TRANSITION_WAIT = 120  # 2 seconds at 60 FPS

# ── Bonus Feature ─────────────────────────────────────────────────────
# Toggle with 'B' key: disables friendly fire (projectiles won't kill the player)
NO_FRIENDLY_FIRE = False


# ── Utility Functions ─────────────────────────────────────────────────

def random_angle():
    return random.uniform(0, 2 * math.pi)


def random_speed(base_speed):
    return random.uniform(base_speed * 0.6, base_speed * 1.4)


def wrap_position(pos):
    """Wrap position to screen bounds."""
    return (pos[0] % SCREEN_WIDTH, pos[1] % SCREEN_HEIGHT)


def distance(p1, p2):
    return math.sqrt((p1[0] - p2[0]) ** 2 + (p1[1] - p2[1]) ** 2)


def random_spawn_away_from(ship_pos, min_dist=150):
    """Generate a random position at least min_dist away from ship_pos."""
    for _ in range(100):
        pos = (random.randint(0, SCREEN_WIDTH - 1), random.randint(0, SCREEN_HEIGHT - 1))
        if distance(pos, ship_pos) >= min_dist:
            return pos
    # Fallback: pick a corner farthest from ship
    corners = [(0, 0), (SCREEN_WIDTH - 1, 0), (0, SCREEN_HEIGHT - 1), (SCREEN_HEIGHT - 1, SCREEN_HEIGHT - 1)]
    return max(corners, key=lambda c: distance(c, ship_pos))


def generate_asteroid_shape(radius, seed=None):
    """Generate an irregular polygon shape for an asteroid."""
    if seed is not None:
        rng = random.Random(seed)
    else:
        rng = random.Random()

    vertices = []
    num_vertices = ASTEROID_VERTEX_COUNT + rng.randint(-2, 2)
    for i in range(num_vertices):
        angle = (2 * math.pi * i) / num_vertices
        # Vary the radius to create irregular shape
        r_variation = rng.uniform(0.7, 1.0)
        vertices.append((radius * r_variation, angle))
    return vertices


def shape_to_points(shape, center, angle):
    """Convert a shape definition to screen points."""
    points = []
    for r, a in shape:
        x = center[0] + r * math.cos(a + angle)
        y = center[1] + r * math.sin(a + angle)
        points.append((x, y))
    return points


# ── Starfield ─────────────────────────────────────────────────────────

class Starfield:
    def __init__(self):
        self.stars = []
        for _ in range(120):
            self.stars.append((
                random.randint(0, SCREEN_WIDTH - 1),
                random.randint(0, SCREEN_HEIGHT - 1),
                random.uniform(0.3, 1.0)  # brightness
            ))

    def draw(self, surface):
        for x, y, brightness in self.stars:
            alpha = int(100 + 155 * brightness)
            color = (alpha, alpha, alpha)
            surface.set_at((x, y), color)


# ── Particle System ──────────────────────────────────────────────────

class Particle:
    COLORS = [
        (255, 200, 50),   # yellow
        (255, 100, 30),   # orange
        (255, 50, 50),    # red
        (255, 255, 100),  # bright yellow
        (200, 200, 255),  # white
        (255, 150, 0),    # deep orange
    ]

    def __init__(self, x, y):
        self.x = x
        self.y = y
        angle = random.uniform(0, 2 * math.pi)
        speed = random.uniform(1, 5)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = random.randint(15, 35)
        self.max_life = self.life
        self.color = random.choice(self.COLORS)
        self.size = random.randint(2, 5)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.vx *= 0.97
        self.vy *= 0.97
        self.life -= 1

    def draw(self, surface):
        alpha = max(0, self.life / self.max_life)
        r = int(self.color[0] * alpha)
        g = int(self.color[1] * alpha)
        b = int(self.color[2] * alpha)
        size = max(1, int(self.size * alpha))
        pygame.draw.rect(surface, (r, g, b),
                         (int(self.x) - size // 2, int(self.y) - size // 2, size, size))

    def is_dead(self):
        return self.life <= 0


# ── Projectile ────────────────────────────────────────────────────────

class Projectile:
    def __init__(self, x, y, vx, vy, angle):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.angle = angle
        self.spawn_x = x
        self.spawn_y = y
        self.traveled = 0.0

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.x, self.y = wrap_position((self.x, self.y))
        # Track distance traveled from spawn (accounting for wrap)
        self.traveled += math.sqrt(self.vx ** 2 + self.vy ** 2)
        return self.traveled <= PROJECTILE_LIFE_PX

    def draw(self, surface):
        pygame.draw.rect(surface, CYAN,
                         (int(self.x) - PROJECTILE_SIZE // 2,
                          int(self.y) - PROJECTILE_SIZE // 2,
                          PROJECTILE_SIZE, PROJECTILE_SIZE))


# ── Asteroid ──────────────────────────────────────────────────────────

class Asteroid:
    def __init__(self, x, y, radius, speed, angle=None, seed=None):
        self.x = x
        self.y = y
        self.radius = radius
        self.speed = speed
        if angle is None:
            self.angle = random_angle()
        else:
            self.angle = angle
        self.vx = math.cos(self.angle) * self.speed
        self.vy = math.sin(self.angle) * self.speed
        self.shape = generate_asteroid_shape(radius, seed)
        self.rotation_speed = random.uniform(-0.02, 0.02)
        self.current_rotation = random.uniform(0, 2 * math.pi)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.x, self.y = wrap_position((self.x, self.y))
        self.current_rotation += self.rotation_speed

    def draw(self, surface):
        points = shape_to_points(self.shape, (self.x, self.y), self.current_rotation)
        pygame.draw.polygon(surface, GRAY, points)
        pygame.draw.polygon(surface, (180, 180, 180), points, 1)

    def contains_point(self, px, py):
        """Simple circle-based collision check."""
        return distance((self.x, self.y), (px, py)) < self.radius


# ── Ship ──────────────────────────────────────────────────────────────

class Ship:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.angle = -math.pi / 2  # pointing up
        self.thrusting = False
        self.alive = True

    def reset(self, x, y):
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.angle = -math.pi / 2
        self.thrusting = False
        self.alive = True

    def update(self, keys):
        if not self.alive:
            return

        # Rotation
        if keys[pygame.K_LEFT]:
            self.angle -= math.radians(SHIP_ROTATION_SPEED)
        if keys[pygame.K_RIGHT]:
            self.angle += math.radians(SHIP_ROTATION_SPEED)

        # Thrust
        self.thrusting = keys[pygame.K_UP]
        if self.thrusting:
            self.vx += math.cos(self.angle) * THRUST_ACCEL
            self.vy += math.sin(self.angle) * THRUST_ACCEL

        # Speed cap
        speed = math.sqrt(self.vx ** 2 + self.vy ** 2)
        if speed > MAX_SPEED:
            self.vx = (self.vx / speed) * MAX_SPEED
            self.vy = (self.vy / speed) * MAX_SPEED

        # Friction
        if not self.thrusting:
            self.vx *= FRICTION
            self.vy *= FRICTION

        # Stop micro-drift
        if speed < 0.05:
            self.vx = 0.0
            self.vy = 0.0

        # Move
        self.x += self.vx
        self.y += self.vy
        self.x, self.y = wrap_position((self.x, self.y))

    def get_tip(self):
        """Get the coordinates of the ship's tip (front)."""
        tip_x = self.x + SHIP_HEIGHT / 2 * math.cos(self.angle)
        tip_y = self.y + SHIP_HEIGHT / 2 * math.sin(self.angle)
        return (tip_x, tip_y)

    def draw(self, surface):
        if not self.alive:
            return

        # Draw ship body (elongated triangle)
        nose = self.get_tip()
        left = (
            self.x + SHIP_WIDTH / 2 * math.cos(self.angle + math.pi / 2),
            self.y + SHIP_WIDTH / 2 * math.sin(self.angle + math.pi / 2)
        )
        right = (
            self.x + SHIP_WIDTH / 2 * math.cos(self.angle - math.pi / 2),
            self.y + SHIP_WIDTH / 2 * math.sin(self.angle - math.pi / 2)
        )

        ship_points = [nose, left, right]
        pygame.draw.polygon(surface, WHITE, ship_points)
        pygame.draw.polygon(surface, (200, 200, 200), ship_points, 1)

        # Draw thrust flame
        if self.thrusting:
            flame_length = 15
            flame_width = 6
            # Opposite direction of facing
            fx = self.x - math.cos(self.angle) * flame_length
            fy = self.y - math.sin(self.angle) * flame_length
            # Perpendicular to facing
            px = math.cos(self.angle + math.pi / 2) * flame_width
            py = math.sin(self.angle + math.pi / 2) * flame_width

            flame_points = [
                (self.x, self.y),
                (fx + px, fy + py),
                (fx - px, fy - py),
            ]
            pygame.draw.polygon(surface, RED, flame_points)

    def get_points(self):
        """Get ship vertices for collision (approximation as circle)."""
        return (self.x, self.y), SHIP_WIDTH // 2 + 2  # (center, radius)


# ── Game Class ────────────────────────────────────────────────────────

class Game:
    def __init__(self):
        self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
        pygame.display.set_caption("Asteroids")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont(None, 48)
        self.small_font = pygame.font.SysFont(None, 24)

        self.starfield = Starfield()
        self.space_was_pressed = False
        self.reset_game()

    def reset_game(self):
        """Reset to level 1."""
        self.level = 1
        self.ship = Ship(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2)
        self.projectiles = []
        self.asteroids = []
        self.particles = []
        self.game_over = False
        self.level_transition = False
        self.transition_timer = 0
        self.friendly_fire = False
        self.spawn_asteroids(LEVEL_START_ASTEROIDS)

    def spawn_asteroids(self, count):
        """Spawn asteroids for a new level."""
        base_speed = ASTEROID_BASE_SPEED + (self.level - 1) * LEVEL_SPEED_INCREMENT
        for i in range(count):
            pos = random_spawn_away_from((self.ship.x, self.ship.y))
            speed = random_speed(base_speed)
            seed = random.randint(0, 100000)
            self.asteroids.append(Asteroid(pos[0], pos[1], ASTEROID_LARGE_RADIUS, speed, seed=seed))

    def spawn_explosion(self, x, y):
        """Spawn a colorful particle explosion."""
        for _ in range(25):
            self.particles.append(Particle(x, y))

    def fire_projectile(self):
        """Fire a projectile from the ship."""
        if len(self.projectiles) >= MAX_PROJECTILES:
            return
        tip = self.ship.get_tip()
        # Constraint 3: projectile velocity = ship velocity + 6 px/frame in facing direction
        vx = self.ship.vx + PROJECTILE_SPEED * math.cos(self.ship.angle)
        vy = self.ship.vy + PROJECTILE_SPEED * math.sin(self.ship.angle)
        self.projectiles.append(Projectile(tip[0], tip[1], vx, vy, self.ship.angle))

    def check_collisions(self):
        """Check all collision types."""
        # Projectile vs Asteroid
        for proj in self.projectiles[:]:
            for asteroid in self.asteroids[:]:
                if asteroid.contains_point(proj.x, proj.y):
                    # Remove projectile
                    self.projectiles.remove(proj)
                    # Spawn explosion
                    self.spawn_explosion(asteroid.x, asteroid.y)

                    # Split asteroid
                    if asteroid.radius > MIN_ASTEROID_RADIUS:
                        new_radius = asteroid.radius / ASTEROID_SPLIT_COUNT
                        new_speed = asteroid.speed * ASTEROID_SPEED_MULT
                        num_splits = random.randint(2, 3)
                        for _ in range(num_splits):
                            angle = random_angle()
                            seed = random.randint(0, 100000)
                            self.asteroids.append(
                                Asteroid(asteroid.x, asteroid.y, new_radius, new_speed, angle, seed)
                            )

                    # Remove original asteroid
                    self.asteroids.remove(asteroid)
                    break

        # Ship vs Asteroid
        if self.ship.alive and not self.game_over:
            ship_center, ship_radius = self.ship.get_points()
            for asteroid in self.asteroids:
                if asteroid.contains_point(ship_center[0], ship_center[1]):
                    self.game_over = True
                    self.ship.alive = False
                    self.friendly_fire = False
                    self.spawn_explosion(ship_center[0], ship_center[1])
                    break

        # Projectile vs Ship (Friendly Fire)
        if not NO_FRIENDLY_FIRE and self.ship.alive and not self.game_over:
            ship_center, ship_radius = self.ship.get_points()
            for proj in self.projectiles[:]:
                if distance((proj.x, proj.y), (ship_center[0], ship_center[1])) < ship_radius:
                    self.game_over = True
                    self.ship.alive = False
                    self.friendly_fire = True
                    self.spawn_explosion(ship_center[0], ship_center[1])
                    self.projectiles.remove(proj)
                    break

    def update(self):
        """Update game state."""
        keys = pygame.key.get_pressed()

        # Handle restart
        if self.game_over and keys[pygame.K_r]:
            self.reset_game()
            return

        # Handle level transition
        if self.level_transition:
            self.transition_timer -= 1
            if self.transition_timer <= 0:
                self.level_transition = False
                self.spawn_asteroids(LEVEL_ADD_ASTEROIDS)
            return

        # Update ship
        self.ship.update(keys)

        # Fire projectile (edge detection: only fire on press transition)
        space_pressed = bool(keys[pygame.K_SPACE])
        if space_pressed and not self.space_was_pressed:
            self.fire_projectile()
        self.space_was_pressed = space_pressed

        # Update projectiles
        self.projectiles = [p for p in self.projectiles if p.update()]

        # Update asteroids
        for asteroid in self.asteroids:
            asteroid.update()

        # Update particles
        self.particles = [p for p in self.particles if not p.is_dead()]
        for p in self.particles:
            p.update()

        # Check collisions
        self.check_collisions()

        # Check level complete
        if not self.game_over and len(self.asteroids) == 0:
            self.level_transition = True
            self.transition_timer = LEVEL_TRANSITION_WAIT
            self.level += 1

    def draw(self):
        """Draw everything."""
        self.screen.fill(BLACK)
        self.starfield.draw(self.screen)

        # Draw game objects
        for asteroid in self.asteroids:
            asteroid.draw(self.screen)

        for proj in self.projectiles:
            proj.draw(self.screen)

        self.ship.draw(self.screen)

        for particle in self.particles:
            particle.draw(self.screen)

        # Draw HUD
        level_text = self.small_font.render(f"Level {self.level}", True, WHITE)
        self.screen.blit(level_text, (10, 10))

        # Draw bonus feature indicator
        bonus_text = self.small_font.render(
            "BONUS: No Friendly Fire" if NO_FRIENDLY_FIRE else "Bonus: OFF",
            True, CYAN if NO_FRIENDLY_FIRE else GRAY
        )
        self.screen.blit(bonus_text, (10, SCREEN_HEIGHT - 25))

        # Draw game over text
        if self.game_over:
            if self.friendly_fire:
                go_text = self.font.render("FRIENDLY FIRE! - Press R to Restart", True, RED)
            else:
                go_text = self.font.render("GAME OVER - Press R to Restart", True, RED)
            text_rect = go_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
            self.screen.blit(go_text, text_rect)

        # Draw level transition text
        if self.level_transition:
            trans_text = self.font.render(f"Level {self.level} Starting...", True, WHITE)
            text_rect = trans_text.get_rect(center=(SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2))
            self.screen.blit(trans_text, text_rect)

        pygame.display.flip()

    def run(self):
        """Main game loop."""
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_b:
                        global NO_FRIENDLY_FIRE
                        NO_FRIENDLY_FIRE = not NO_FRIENDLY_FIRE
                    elif event.key == pygame.K_ESCAPE:
                        running = False

            self.update()
            self.draw()
            self.clock.tick(FPS)

        pygame.quit()


# ── Entry Point ───────────────────────────────────────────────────────

if __name__ == "__main__":
    pygame.init()
    game = Game()
    game.run()
