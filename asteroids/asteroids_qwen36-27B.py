#!/usr/bin/env python3
"""
Asteroids — a classic arcade game built with Pygame.
Run with: python game.py

Controls:
  Arrow Up/Left/Right  — Thrust / Rotate
  Space                — Fire
  R                    — Restart (on Game Over)
  B                    — Toggle Bonus Feature (Tri-Fire)
"""

import math
import random
import sys

import pygame

# ──────────────────────────────────────────────────────────────────────
# CONSTANTS
# ──────────────────────────────────────────────────────────────────────
SCREEN_W, SCREEN_H = 800, 600
FPS = 60

SHIP_WIDTH = 20
SHIP_HEIGHT = 30
SHIP_ROT_SPEED = 5          # degrees per frame
SHIP_THRUST = 0.3           # px/frame²
SHIP_MAX_SPEED = 8
SHIP_FRICTION = 0.98

PROJ_SPEED = 6              # added to ship velocity
PROJ_RANGE = 1000           # px before disappearing
PROJ_MAX = 3                # max on screen (normal mode)
PROJ_TRI_MAX = 12           # max on screen (tri-fire bonus mode)

ASTEROID_START = 5
ASTEROID_RADIUS = 40
ASTEROID_MIN_SPEED = 1.5
ASTEROID_MAX_SPEED = 2.5
ASTEROID_SPLIT_FACTOR = 1.5
ASTEROID_SPEED_MULT = 1.2
ASTEROID_MIN_RADIUS = 15

LEVEL_TIMEOUT = 2           # seconds before next level

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 50, 50)
ORANGE = (255, 165, 0)
YELLOW = (255, 255, 0)
CYAN = (0, 255, 255)
MAGENTA = (255, 0, 255)
GREEN = (50, 255, 50)
SHIELD_BLUE = (80, 160, 255)

# ──────────────────────────────────────────────────────────────────────
# UTILITIES
# ──────────────────────────────────────────────────────────────────────
def wrap(val, lo, hi):
    """Wrap *val* into [lo, hi] range."""
    span = hi - lo
    return ((val - lo) % span) + lo


def dist(x1, y1, x2, y2):
    return math.hypot(x2 - x1, y2 - y1)


def random_away_from(x, y, radius, margin):
    """Return a random (x, y) at least *margin* px from (x, y)."""
    for _ in range(200):
        rx = random.randint(0, SCREEN_W - 1)
        ry = random.randint(0, SCREEN_H - 1)
        if dist(rx, ry, x, y) > margin:
            return rx, ry
    return random.randint(0, SCREEN_W - 1), random.randint(0, SCREEN_H - 1)


def make_asteroid_vertices(cx, cy, radius, n=12):
    """Generate an irregular polygon for an asteroid."""
    angles = sorted([random.uniform(0, 2 * math.pi) for _ in range(n)])
    verts = []
    for a in angles:
        r = radius * random.uniform(0.7, 1.0)
        verts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return verts


# ──────────────────────────────────────────────────────────────────────
# STARFIELD
# ──────────────────────────────────────────────────────────────────────
class StarField:
    def __init__(self, count=200):
        self.stars = []
        for _ in range(count):
            self.stars.append({
                "x": random.randint(0, SCREEN_W - 1),
                "y": random.randint(0, SCREEN_H - 1),
                "brightness": random.randint(80, 255),
                "twinkle_speed": random.uniform(0.02, 0.08),
                "phase": random.uniform(0, math.pi * 2),
            })
        self.t = 0

    def update(self):
        self.t += 1

    def draw(self, surf):
        for s in self.stars:
            b = int(s["brightness"] * (0.7 + 0.3 * math.sin(self.t * s["twinkle_speed"] + s["phase"])))
            b = max(30, min(255, b))
            surf.set_at((s["x"], s["y"]), (b, b, b))


# ──────────────────────────────────────────────────────────────────────
# PARTICLE (explosion effects)
# ──────────────────────────────────────────────────────────────────────
class Particle:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(1, 5)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = random.randint(20, 50)
        self.max_life = self.life
        self.color = color
        self.size = random.randint(1, 3)

    def update(self):
        self.x = wrap(self.x + self.vx, 0, SCREEN_W)
        self.y = wrap(self.y + self.vy, 0, SCREEN_H)
        self.vx *= 0.97
        self.vy *= 0.97
        self.life -= 1

    def draw(self, surf):
        alpha = self.life / self.max_life
        c = tuple(int(ch * alpha) for ch in self.color)
        if self.size == 1:
            surf.set_at((int(self.x), int(self.y)), c)
        else:
            pygame.draw.rect(surf, c, (int(self.x), int(self.y), self.size, self.size))

    def alive(self):
        return self.life > 0


# ──────────────────────────────────────────────────────────────────────
# THRUST FLAME PARTICLE
# ──────────────────────────────────────────────────────────────────────
class FlameParticle:
    def __init__(self, x, y, angle):
        spread = random.uniform(-0.4, 0.4)
        a = angle + math.pi + spread
        speed = random.uniform(2, 5)
        self.x = x
        self.y = y
        self.vx = math.cos(a) * speed
        self.vy = math.sin(a) * speed
        self.life = random.randint(6, 14)
        self.max_life = self.life
        self.size = random.randint(2, 4)

    def update(self):
        self.x = wrap(self.x + self.vx, 0, SCREEN_W)
        self.y = wrap(self.y + self.vy, 0, SCREEN_H)
        self.life -= 1

    def draw(self, surf):
        alpha = self.life / self.max_life
        r = 255
        g = int(50 + 150 * alpha)
        b = int(50 * alpha)
        c = (r, g, b)
        pygame.draw.circle(surf, c, (int(self.x), int(self.y)), max(1, self.size))

    def alive(self):
        return self.life > 0


# ──────────────────────────────────────────────────────────────────────
# SHIP
# ──────────────────────────────────────────────────────────────────────
class Ship:
    def __init__(self):
        self.x = SCREEN_W / 2
        self.y = SCREEN_H / 2
        self.angle = -math.pi / 2        # pointing up
        self.vx = 0
        self.vy = 0

    def update(self, keys, bonus):
        # Rotation
        if keys[pygame.K_LEFT]:
            self.angle -= math.radians(SHIP_ROT_SPEED)
        if keys[pygame.K_RIGHT]:
            self.angle += math.radians(SHIP_ROT_SPEED)

        # Thrust
        thrusting = keys[pygame.K_UP]
        if thrusting:
            self.vx += math.cos(self.angle) * SHIP_THRUST
            self.vy += math.sin(self.angle) * SHIP_THRUST

        # Clamp speed
        speed = math.hypot(self.vx, self.vy)
        if speed > SHIP_MAX_SPEED:
            self.vx = self.vx / speed * SHIP_MAX_SPEED
            self.vy = self.vy / speed * SHIP_MAX_SPEED

        # Friction
        if not thrusting:
            self.vx *= SHIP_FRICTION
            self.vy *= SHIP_FRICTION

        # Position
        self.x = wrap(self.x + self.vx, 0, SCREEN_W)
        self.y = wrap(self.y + self.vy, 0, SCREEN_H)

        return thrusting

    def tip(self):
        """World position of the ship's nose."""
        return (
            self.x + math.cos(self.angle) * SHIP_HEIGHT / 2,
            self.y + math.sin(self.angle) * SHIP_HEIGHT / 2,
        )

    def draw(self, surf, thrusting, bonus):
        angle = self.angle
        cos_a, sin_a = math.cos(angle), math.sin(angle)

        # Ship vertices (elongated triangle)
        nose_x = self.x + cos_a * SHIP_HEIGHT / 2
        nose_y = self.y + sin_a * SHIP_HEIGHT / 2
        left_x = self.x - cos_a * SHIP_HEIGHT / 4 - sin_a * SHIP_WIDTH / 2
        left_y = self.y - sin_a * SHIP_HEIGHT / 4 + cos_a * SHIP_WIDTH / 2
        right_x = self.x - cos_a * SHIP_HEIGHT / 4 + sin_a * SHIP_WIDTH / 2
        right_y = self.y - sin_a * SHIP_HEIGHT / 4 - cos_a * SHIP_WIDTH / 2

        pygame.draw.polygon(surf, WHITE, [(nose_x, nose_y), (left_x, left_y), (right_x, right_y)])

        # Thrust flame
        if thrusting:
            # Red triangle behind the ship
            mid_base_x = (left_x + right_x) / 2
            mid_base_y = (left_y + right_y) / 2
            flame_len = SHIP_HEIGHT * 0.4 * (0.8 + 0.2 * random.random())
            flame_tip_x = mid_base_x - cos_a * flame_len
            flame_tip_y = mid_base_y - sin_a * flame_len
            flare_w = SHIP_WIDTH * 0.3
            fl_x = mid_base_x - sin_a * flare_w
            fl_y = mid_base_y + cos_a * flare_w
            fr_x = mid_base_x + sin_a * flare_w
            fr_y = mid_base_y - cos_a * flare_w
            pygame.draw.polygon(surf, RED, [(fl_x, fl_y), (fr_x, fr_y), (flame_tip_x, flame_tip_y)])

        # Bonus shield indicator ring
        if bonus:
            pygame.draw.circle(surf, SHIELD_BLUE, (int(self.x), int(self.y)), 28, 2)


# ──────────────────────────────────────────────────────────────────────
# PROJECTILE
# ──────────────────────────────────────────────────────────────────────
class Projectile:
    def __init__(self, x, y, vx, vy):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.spawn_x = x
        self.spawn_y = y
        self.traveled = 0
        self.radius = 3

    def update(self):
        dx = self.vx
        dy = self.vy
        self.x = wrap(self.x + dx, 0, SCREEN_W)
        self.y = wrap(self.y + dy, 0, SCREEN_H)
        self.traveled += math.hypot(dx, dy)

    def dead(self):
        return self.traveled >= PROJ_RANGE

    def draw(self, surf):
        # Draw as a small bright square
        pygame.draw.rect(surf, YELLOW,
                         (int(self.x) - self.radius, int(self.y) - self.radius,
                          self.radius * 2, self.radius * 2))


# ──────────────────────────────────────────────────────────────────────
# ASTEROID
# ──────────────────────────────────────────────────────────────────────
class Asteroid:
    def __init__(self, x, y, radius, speed=None):
        self.x = x
        self.y = y
        self.radius = radius
        if speed is None:
            speed = random.uniform(ASTEROID_MIN_SPEED, ASTEROID_MAX_SPEED)
        angle = random.uniform(0, math.pi * 2)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.vertices = make_asteroid_vertices(0, 0, radius)
        self.rot_angle = 0
        self.rot_speed = random.uniform(-0.03, 0.03)
        # Color tint based on size
        t = int(140 + (radius / ASTEROID_RADIUS) * 80)
        self.color = (t, t, t - 20) if t > 20 else (t, t, t)

    def update(self):
        self.x = wrap(self.x + self.vx, 0, SCREEN_W)
        self.y = wrap(self.y + self.vy, 0, SCREEN_H)
        self.rot_angle += self.rot_speed

    def draw(self, surf):
        cos_r, sin_r = math.cos(self.rot_angle), math.sin(self.rot_angle)
        pts = []
        for px, py in self.vertices:
            rx = px * cos_r - py * sin_r
            ry = px * sin_r + py * cos_r
            pts.append((self.x + rx, self.y + ry))
        pygame.draw.polygon(surf, self.color, pts)
        pygame.draw.polygon(surf, WHITE, pts, 1)


# ──────────────────────────────────────────────────────────────────────
# GAME
# ──────────────────────────────────────────────────────────────────────
class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Asteroids")
        self.clock = pygame.time.Clock()
        self.starfield = StarField()
        self.font = pygame.font.SysFont("monospace", 28, bold=True)
        self.font_small = pygame.font.SysFont("monospace", 18)
        self.font_big = pygame.font.SysFont("monospace", 42, bold=True)
        self.bonus_active = False
        self.reset()

    # ── reset / restart ────────────────────────────────────────────
    def reset(self):
        self.level = 1
        self.ship = Ship()
        self.projectiles = []
        self.asteroids = []
        self.particles = []
        self.flame_particles = []
        self.state = "playing"       # playing | gameover | levelclear
        self.over_msg = ""
        self.clear_timer = 0
        self.base_speed = 1.0
        self.spawn_asteroids(ASTEROID_START, self.base_speed)

    def spawn_asteroids(self, count, speed_mult):
        for _ in range(count):
            ax, ay = random_away_from(self.ship.x, self.ship.y, ASTEROID_RADIUS, 120)
            spd = random.uniform(ASTEROID_MIN_SPEED, ASTEROID_MAX_SPEED) * speed_mult
            self.asteroids.append(Asteroid(ax, ay, ASTEROID_RADIUS, spd))

    # ── input ──────────────────────────────────────────────────────
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            return False

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_r:
                if self.state in ("gameover",):
                    self.reset()
            if event.key == pygame.K_b:
                self.bonus_active = not self.bonus_active
            if event.key == pygame.K_SPACE and self.state == "playing":
                self.fire()

        return True

    # ── firing ─────────────────────────────────────────────────────
    def fire(self):
        max_proj = PROJ_TRI_MAX if self.bonus_active else PROJ_MAX
        if len(self.projectiles) >= max_proj:
            return

        tip_x, tip_y = self.ship.tip()
        base_vx = math.cos(self.ship.angle) * PROJ_SPEED
        base_vy = math.sin(self.ship.angle) * PROJ_SPEED

        if self.bonus_active:
            # Tri-fire: 3 projectiles in a 20° arc
            for offset in [-math.radians(10), 0, math.radians(10)]:
                a = self.ship.angle + offset
                pvx = math.cos(a) * PROJ_SPEED
                pvy = math.sin(a) * PROJ_SPEED
                self.projectiles.append(Projectile(tip_x, tip_y,
                                                    self.ship.vx + pvx,
                                                    self.ship.vy + pvy))
        else:
            self.projectiles.append(Projectile(tip_x, tip_y,
                                                self.ship.vx + base_vx,
                                                self.ship.vy + base_vy))

    # ── particles ──────────────────────────────────────────────────
    def spawn_explosion(self, x, y, radius):
        colors = [RED, ORANGE, YELLOW, WHITE, CYAN, MAGENTA, GREEN]
        count = max(15, int(radius * 2))
        for _ in range(count):
            c = random.choice(colors)
            self.particles.append(Particle(x, y, c))

    def spawn_thrust_flames(self, thrusting):
        if not thrusting:
            return
        # Ship rear center
        cos_a = math.cos(self.ship.angle)
        sin_a = math.sin(self.ship.angle)
        rear_x = self.ship.x - cos_a * SHIP_HEIGHT / 4
        rear_y = self.ship.y - sin_a * SHIP_HEIGHT / 4
        for _ in range(3):
            self.flame_particles.append(FlameParticle(rear_x, rear_y, self.ship.angle))

    # ── splitting asteroids ────────────────────────────────────────
    def split_asteroid(self, ast):
        self.spawn_explosion(ast.x, ast.y, ast.radius)
        new_radius = ast.radius / ASTEROID_SPLIT_FACTOR
        if new_radius < ASTEROID_MIN_RADIUS:
            # Destroy (already spawned explosion)
            return
        speed_mult = ASTEROID_SPEED_MULT
        n = random.randint(2, 3)
        for _ in range(n):
            child = Asteroid(ast.x, ast.y, new_radius)
            # Override velocity
            angle = random.uniform(0, math.pi * 2)
            spd = math.hypot(ast.vx, ast.vy) * speed_mult
            child.vx = math.cos(angle) * spd
            child.vy = math.sin(angle) * spd
            self.asteroids.append(child)

    # ── collision detection ────────────────────────────────────────
    def check_collisions(self):
        # Projectile vs asteroid
        for proj in self.projectiles[:]:
            for ast in self.asteroids[:]:
                if dist(proj.x, proj.y, ast.x, ast.y) < ast.radius + proj.radius:
                    self.projectiles.remove(proj)
                    self.asteroids.remove(ast)
                    self.split_asteroid(ast)
                    break

        # Ship vs asteroid
        for ast in self.asteroids:
            if dist(self.ship.x, self.ship.y, ast.x, ast.y) < ast.radius + SHIP_WIDTH / 2:
                self.state = "gameover"
                self.over_msg = "GAME OVER — Press R to Restart"
                self.spawn_explosion(self.ship.x, self.ship.y, 30)
                return

        # Projectile vs ship (friendly fire)
        for proj in self.projectiles[:]:
            if dist(proj.x, proj.y, self.ship.x, self.ship.y) < SHIP_WIDTH / 2 + proj.radius:
                self.state = "gameover"
                self.over_msg = "FRIENDLY FIRE! — Press R to Restart"
                self.spawn_explosion(self.ship.x, self.ship.y, 30)
                return

    # ── level clear ────────────────────────────────────────────────
    def check_level_clear(self):
        if self.asteroids and self.state == "playing":
            return
        if not self.asteroids and self.state == "playing":
            self.state = "levelclear"
            self.clear_timer = pygame.time.get_ticks()

        if self.state == "levelclear":
            if pygame.time.get_ticks() - self.clear_timer >= LEVEL_TIMEOUT * 1000:
                self.level += 1
                self.base_speed += 0.3
                self.ship = Ship()
                self.projectiles = []
                self.particles = []
                self.flame_particles = []
                self.spawn_asteroids(ASTEROID_START + (self.level - 1) * 2, self.base_speed)
                self.state = "playing"

    # ── main update ────────────────────────────────────────────────
    def update(self):
        keys = pygame.key.get_pressed()
        self.starfield.update()

        # Always check level clear (even from "levelclear" state)
        self.check_level_clear()

        if self.state != "playing":
            # Still update particles
            for p in self.particles:
                p.update()
            self.particles = [p for p in self.particles if p.alive()]
            return

        # Ship
        thrusting = self.ship.update(keys, self.bonus_active)
        self.spawn_thrust_flames(thrusting)

        # Projectiles
        for proj in self.projectiles:
            proj.update()
        self.projectiles = [p for p in self.projectiles if not p.dead()]

        # Asteroids
        for ast in self.asteroids:
            ast.update()

        # Particles
        for p in self.particles:
            p.update()
        self.particles = [p for p in self.particles if p.alive()]

        for fp in self.flame_particles:
            fp.update()
        self.flame_particles = [fp for fp in self.flame_particles if fp.alive()]

        # Collisions
        self.check_collisions()

    # ── render ─────────────────────────────────────────────────────
    def draw(self):
        self.screen.fill(BLACK)
        self.starfield.draw(self.screen)

        # Asteroids
        for ast in self.asteroids:
            ast.draw(self.screen)

        # Projectiles
        for proj in self.projectiles:
            proj.draw(self.screen)

        # Ship (hidden on game over)
        if self.state != "gameover":
            keys = pygame.key.get_pressed()
            thrusting = keys[pygame.K_UP]
            self.ship.draw(self.screen, thrusting, self.bonus_active)

        # Flame particles
        for fp in self.flame_particles:
            fp.draw(self.screen)

        # Explosion particles
        for p in self.particles:
            p.draw(self.screen)

        # HUD
        self.draw_hud()

        # Overlays
        if self.state == "gameover":
            self.draw_overlay(self.over_msg, self.font_big)
        elif self.state == "levelclear":
            msg = f"LEVEL {self.level} CLEAR"
            self.draw_overlay(msg, self.font_big)

        pygame.display.flip()

    def draw_hud(self):
        level_txt = f"Level {self.level}"
        proj_txt = f"Bullets: {len(self.projectiles)}"
        bonus_txt = "TRI-FIRE ON" if self.bonus_active else "TRI-FIRE OFF"
        bonus_color = CYAN if self.bonus_active else (128, 128, 128)

        surf = self.font_small.render(level_txt, True, WHITE)
        self.screen.blit(surf, (10, 10))

        surf = self.font_small.render(proj_txt, True, WHITE)
        self.screen.blit(surf, (10, 34))

        surf = self.font_small.render(bonus_txt, True, bonus_color)
        self.screen.blit(surf, (SCREEN_W - surf.get_width() - 10, 10))

        # Small help text
        help_txt = "[B] Toggle Tri-Fire"
        surf = self.font_small.render(help_txt, True, (100, 100, 100))
        self.screen.blit(surf, (SCREEN_W - surf.get_width() - 10, 34))

    def draw_overlay(self, text, font):
        # Semi-transparent overlay
        overlay = pygame.Surface((SCREEN_W, SCREEN_H))
        overlay.set_alpha(128)
        overlay.fill(BLACK)
        self.screen.blit(overlay, (0, 0))

        surf = font.render(text, True, WHITE)
        rect = surf.get_rect(center=(SCREEN_W / 2, SCREEN_H / 2))
        self.screen.blit(surf, rect)

    # ── main loop ──────────────────────────────────────────────────
    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if not self.handle_event(event):
                    running = False
            self.update()
            self.draw()
            self.clock.tick(FPS)

        pygame.quit()
        sys.exit()


# ──────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    Game().run()
