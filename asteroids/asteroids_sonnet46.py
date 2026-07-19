import pygame
import math
import random
import sys

# [CHECK CONSTRAINT 1] Window & setup constants - non-resizable 800x600
SCREEN_W = 800
SCREEN_H = 600

# [CHECK CONSTRAINT 2] Ship physics constants
ROTATION_SPEED = 5    # degrees/frame
THRUST_FORCE   = 0.3  # px/frame²
MAX_SPEED      = 8    # px/frame
FRICTION       = 0.98 # multiplier per frame when not thrusting

# [CHECK CONSTRAINT 3] Projectile constants
PROJ_SPEED     = 6    # px/frame added on top of ship velocity
MAX_PROJS      = 3    # max projectiles on screen at once
MAX_TRAVEL     = 1000 # px before projectile disappears

# [CHECK CONSTRAINT 4] Asteroid constants
INIT_COUNT     = 5    # starting asteroid count
LARGE_RADIUS   = 40   # px
SPEED_MIN      = 1.5  # px/frame
SPEED_MAX      = 2.5  # px/frame
MIN_RADIUS     = 15   # px; below this, asteroid is destroyed without splitting

# Colors
BLACK  = (0,   0,   0  )
WHITE  = (255, 255, 255)
RED    = (220, 50,  50 )
YELLOW = (255, 220, 0  )
ORANGE = (255, 140, 0  )
GREEN  = (0,   210, 80 )
CYAN   = (0,   200, 255)
GRAY   = (100, 100, 100)

# Game states
PLAYING       = 'playing'
GAME_OVER     = 'game_over'
FRIENDLY_FIRE = 'friendly_fire'
LEVEL_DONE    = 'level_done'


# ── Utility helpers ──────────────────────────────────────────────────────────

def wrap(x, y):
    """[CHECK CONSTRAINT 2] Wrap coordinates to screen bounds."""
    return x % SCREEN_W, y % SCREEN_H


def wrapped_dist(x1, y1, x2, y2):
    """Distance that accounts for screen wrapping (toroidal space)."""
    dx = min(abs(x1 - x2), SCREEN_W - abs(x1 - x2))
    dy = min(abs(y1 - y2), SCREEN_H - abs(y1 - y2))
    return math.hypot(dx, dy)


def circles_hit(x1, y1, r1, x2, y2, r2):
    return wrapped_dist(x1, y1, x2, y2) < r1 + r2


def draw_centered(surface, text, font, color, cy):
    surf = font.render(text, True, color)
    surface.blit(surf, ((SCREEN_W - surf.get_width()) // 2, cy))


def rotate_point(lx, ly, angle_deg):
    """Rotate local-space point clockwise by angle_deg; returns world offset."""
    rad = math.radians(angle_deg)
    c, s = math.cos(rad), math.sin(rad)
    # [CHECK CONSTRAINT 2] Standard 2D rotation: angle 0 = pointing up in screen space
    return lx * c - ly * s, lx * s + ly * c


# ── Ship ─────────────────────────────────────────────────────────────────────

class Ship:
    # [CHECK CONSTRAINT 2] Elongated triangle: 20px wide (±10 x), 30px tall (−15 tip, +15 base)
    _LOCAL = [(0, -15), (-10, 15), (10, 15)]  # tip, back-left, back-right
    RADIUS = 12  # approximate collision radius

    def __init__(self):
        self.x = SCREEN_W / 2
        self.y = SCREEN_H / 2
        self.angle = 0.0   # degrees; 0 = pointing up; increases clockwise
        self.vx = 0.0
        self.vy = 0.0
        self.thrusting = False

    def fwd(self):
        """Unit vector in the ship's facing direction."""
        rad = math.radians(self.angle)
        return math.sin(rad), -math.cos(rad)

    def tip(self):
        """World position of the ship's tip (used as projectile spawn point)."""
        fdx, fdy = self.fwd()
        return self.x + fdx * 15, self.y + fdy * 15

    def world_pts(self):
        return [(self.x + ox, self.y + oy)
                for ox, oy in (rotate_point(lx, ly, self.angle)
                               for lx, ly in self._LOCAL)]

    def update(self, keys):
        # [CHECK CONSTRAINT 2] Rotation: 5 degrees/frame
        if keys[pygame.K_LEFT]:
            self.angle -= ROTATION_SPEED
        if keys[pygame.K_RIGHT]:
            self.angle += ROTATION_SPEED

        # [CHECK CONSTRAINT 2] Thrust: 0.3 px/frame² in facing direction
        self.thrusting = bool(keys[pygame.K_UP])
        if self.thrusting:
            fdx, fdy = self.fwd()
            self.vx += fdx * THRUST_FORCE
            self.vy += fdy * THRUST_FORCE
            # [CHECK CONSTRAINT 2] Clamp to max speed 8 px/frame
            spd = math.hypot(self.vx, self.vy)
            if spd > MAX_SPEED:
                self.vx, self.vy = self.vx / spd * MAX_SPEED, self.vy / spd * MAX_SPEED
        else:
            # [CHECK CONSTRAINT 2] Linear friction 0.98/frame when not thrusting
            self.vx *= FRICTION
            self.vy *= FRICTION

        self.x += self.vx
        self.y += self.vy
        # [CHECK CONSTRAINT 2] Screen wrapping
        self.x, self.y = wrap(self.x, self.y)

    def draw(self, surf):
        pygame.draw.polygon(surf, WHITE, self.world_pts(), 2)
        if self.thrusting:
            # Thrust flame at the back of the ship
            fdx, fdy = self.fwd()
            bx, by = self.x - fdx * 12, self.y - fdy * 12
            pygame.draw.line(surf, YELLOW,
                             (bx, by),
                             (self.x - fdx * (20 + random.randint(0, 6)),
                              self.y - fdy * (20 + random.randint(0, 6))), 2)


# ── Projectile ───────────────────────────────────────────────────────────────

class Projectile:
    RADIUS = 3

    def __init__(self, x, y, vx, vy):
        self.x, self.y = x, y
        self.vx, self.vy = vx, vy
        self.dist  = 0.0  # cumulative distance traveled
        self.alive = True

    def update(self):
        self.x += self.vx
        self.y += self.vy
        # [CHECK CONSTRAINT 3] Track exact distance traveled
        self.dist += math.hypot(self.vx, self.vy)
        # [CHECK CONSTRAINT 3] Disappear after exactly 1000 px
        if self.dist >= MAX_TRAVEL:
            self.alive = False
        # Projectiles wrap around edges (enables friendly-fire via wrap)
        self.x, self.y = wrap(self.x, self.y)

    def draw(self, surf):
        pygame.draw.circle(surf, WHITE, (int(self.x), int(self.y)), self.RADIUS)


# ── Asteroid ─────────────────────────────────────────────────────────────────

class Asteroid:
    def __init__(self, x, y, radius, vx, vy):
        self.x, self.y   = x, y
        self.radius       = radius
        self.vx, self.vy  = vx, vy
        self.alive        = True
        self.rot          = random.uniform(0, 360)
        self.rot_spd      = random.uniform(-2, 2)
        # Irregular polygon: random vertex distances
        n = random.randint(8, 12)
        self._shape = [(i / n * 2 * math.pi, radius * random.uniform(0.68, 1.0))
                       for i in range(n)]

    def world_pts(self):
        rr = math.radians(self.rot)
        return [(self.x + math.cos(a + rr) * r, self.y + math.sin(a + rr) * r)
                for a, r in self._shape]

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.rot += self.rot_spd
        # [CHECK CONSTRAINT 4] Screen wrapping
        self.x, self.y = wrap(self.x, self.y)

    def draw(self, surf):
        pts = self.world_pts()
        if len(pts) >= 3:
            pygame.draw.polygon(surf, WHITE, pts, 2)
        # Draw wrapped copies for seamless edge crossing
        for dx, dy in _edge_offsets(self.x, self.y, self.radius):
            if dx or dy:
                tmp_pts = [(px + dx, py + dy) for px, py in pts]
                pygame.draw.polygon(surf, WHITE, tmp_pts, 2)

    def split(self):
        """[CHECK CONSTRAINT 4] Split into 2–3 smaller asteroids at 1.2× speed."""
        new_r = self.radius / 1.5
        # [CHECK CONSTRAINT 4] Asteroids smaller than 15 px are destroyed, no split
        if new_r < MIN_RADIUS:
            return []
        count  = random.randint(2, 3)
        spd    = math.hypot(self.vx, self.vy) * 1.2
        result = []
        for _ in range(count):
            a = random.uniform(0, 2 * math.pi)
            result.append(Asteroid(self.x, self.y, new_r,
                                   math.cos(a) * spd, math.sin(a) * spd))
        return result


def _edge_offsets(x, y, r):
    """Return (dx,dy) pairs for drawing wrapped ghost copies near screen edges."""
    dxs = [0] + ([SCREEN_W]  if x < r else []) + ([-SCREEN_W] if x > SCREEN_W - r else [])
    dys = [0] + ([SCREEN_H]  if y < r else []) + ([-SCREEN_H] if y > SCREEN_H - r else [])
    return [(dx, dy) for dx in dxs for dy in dys]


# ── Particle ─────────────────────────────────────────────────────────────────

class Particle:
    """[CHECK CONSTRAINT 7] Bonus feature component: explosion particle."""
    def __init__(self, x, y, speed_mult=1.0):
        a = random.uniform(0, 2 * math.pi)
        spd = random.uniform(0.5, 5) * speed_mult
        self.x, self.y   = x, y
        self.vx, self.vy  = math.cos(a) * spd, math.sin(a) * spd
        self.life         = random.randint(18, 55)
        self.max_life     = self.life
        # Warm orange/yellow/white palette
        choices = [(255,220,0),(255,140,0),(255,80,40),(255,255,200),(200,200,255)]
        self.color = random.choice(choices)

    def update(self):
        self.x  += self.vx
        self.y  += self.vy
        self.vx *= 0.92
        self.vy *= 0.92
        self.life -= 1

    def draw(self, surf):
        t    = self.life / self.max_life
        r, g, b = (int(c * t) for c in self.color)
        size = max(1, int(4 * t))
        pygame.draw.circle(surf, (r, g, b), (int(self.x), int(self.y)), size)

    @property
    def alive(self):
        return self.life > 0


# ── Spawning helpers ─────────────────────────────────────────────────────────

def spawn_asteroids(count, spd_min, spd_max, avoid_x, avoid_y):
    """[CHECK CONSTRAINT 4] Spawn large asteroids at random positions, away from ship."""
    result = []
    for _ in range(count):
        for _ in range(200):
            x = random.uniform(0, SCREEN_W)
            y = random.uniform(0, SCREEN_H)
            if math.hypot(x - avoid_x, y - avoid_y) > 150:
                break
        a   = random.uniform(0, 2 * math.pi)
        spd = random.uniform(spd_min, spd_max)
        # [CHECK CONSTRAINT 4] Start speed 1.5–2.5 px/frame, random direction
        result.append(Asteroid(x, y, LARGE_RADIUS,
                                math.cos(a) * spd, math.sin(a) * spd))
    return result


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    pygame.init()
    # [CHECK CONSTRAINT 1] Non-resizable 800×600 window
    screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
    # [CHECK CONSTRAINT 1] Title
    pygame.display.set_caption("Asteroids")
    clock = pygame.time.Clock()

    font_big = pygame.font.SysFont(None, 68)
    font_med = pygame.font.SysFont(None, 36)
    font_sml = pygame.font.SysFont(None, 24)

    # ── Game state ────────────────────────────────────────────────────────────
    level       = 1
    spd_bonus   = 0.0   # cumulative speed increase per level
    state       = PLAYING
    lvl_end_ms  = 0     # timestamp when level was completed

    # [CHECK CONSTRAINT 7] Bonus feature: TRIPLE SHOT (3-way spread, no bullet cap)
    # Toggle with B key. When ON: space fires 3 bullets spread ±15°, removes 3-bullet limit.
    bonus_on = False

    ship       = Ship()
    projectiles: list[Projectile] = []
    asteroids  = spawn_asteroids(INIT_COUNT, SPEED_MIN, SPEED_MAX, ship.x, ship.y)
    particles: list[Particle] = []

    def restart():
        nonlocal level, spd_bonus, state, lvl_end_ms
        nonlocal ship, projectiles, asteroids, particles
        # [CHECK CONSTRAINT 5] Restart resets to Level 1 with original settings
        level      = 1
        spd_bonus  = 0.0
        state      = PLAYING
        lvl_end_ms = 0
        ship       = Ship()
        projectiles = []
        asteroids   = spawn_asteroids(INIT_COUNT, SPEED_MIN, SPEED_MAX, ship.x, ship.y)
        particles   = []

    def fire_projectiles():
        """Fire one (normal) or three spread (bonus) projectiles."""
        tx, ty   = ship.tip()
        fdx, fdy = ship.fwd()
        if bonus_on:
            # [CHECK CONSTRAINT 7] Triple shot: three bullets in ±15° spread, no cap
            for spread in (-15, 0, 15):
                sx, sy = rotate_point(fdx, fdy, spread)
                # rotate the forward vector
                # Actually redo: compute a new forward direction rotated by spread
                rad = math.radians(ship.angle + spread)
                sfx, sfy = math.sin(rad), -math.cos(rad)
                pvx = ship.vx + sfx * PROJ_SPEED
                pvy = ship.vy + sfy * PROJ_SPEED
                projectiles.append(Projectile(tx, ty, pvx, pvy))
        else:
            # [CHECK CONSTRAINT 3] Max 3 projectiles; ignore if limit reached
            if len(projectiles) < MAX_PROJS:
                pvx = ship.vx + fdx * PROJ_SPEED
                pvy = ship.vy + fdy * PROJ_SPEED
                projectiles.append(Projectile(tx, ty, pvx, pvy))

    # ── Main loop ─────────────────────────────────────────────────────────────
    running = True
    while running:
        clock.tick(60)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                # [CHECK CONSTRAINT 7] Toggle bonus feature with B key
                if event.key == pygame.K_b:
                    bonus_on = not bonus_on

                # [CHECK CONSTRAINT 5] Press R to restart after game over
                if event.key == pygame.K_r and state in (GAME_OVER, FRIENDLY_FIRE):
                    restart()

                # [CHECK CONSTRAINT 3] Space bar fires projectile(s)
                if event.key == pygame.K_SPACE and state == PLAYING:
                    fire_projectiles()

        # ── Update ────────────────────────────────────────────────────────────
        if state == PLAYING:
            keys = pygame.key.get_pressed()
            ship.update(keys)

            for p in projectiles:
                p.update()
            projectiles = [p for p in projectiles if p.alive]

            for a in asteroids:
                a.update()
                # [CHECK CONSTRAINT 4] No collision detection between asteroids

            for p in particles:
                p.update()
            particles = [p for p in particles if p.alive]

            # [CHECK CONSTRAINT 5] Ship–asteroid collision → Game Over
            for a in asteroids:
                if circles_hit(ship.x, ship.y, Ship.RADIUS, a.x, a.y, a.radius):
                    state = GAME_OVER
                    break

            # [CHECK CONSTRAINT 3] Projectile hits own ship → Friendly Fire
            # Only check once the projectile has traveled far enough to have wrapped around
            if state == PLAYING:
                for p in projectiles:
                    if p.dist > 80 and circles_hit(p.x, p.y, Projectile.RADIUS,
                                                    ship.x, ship.y, Ship.RADIUS):
                        state = FRIENDLY_FIRE
                        break

            # Projectile–asteroid collisions
            if state == PLAYING:
                dead_proj_idx = set()
                dead_ast      = set()
                new_asts      = []

                for pi, proj in enumerate(projectiles):
                    if pi in dead_proj_idx:
                        continue
                    for ai, ast in enumerate(asteroids):
                        if ai in dead_ast:
                            continue
                        if circles_hit(proj.x, proj.y, Projectile.RADIUS,
                                       ast.x,  ast.y,  ast.radius):
                            dead_proj_idx.add(pi)
                            dead_ast.add(ai)
                            # Spawn particle burst (always, for a small flash)
                            burst = int(ast.radius * 0.8) if not bonus_on else int(ast.radius * 2.5)
                            for _ in range(burst):
                                particles.append(Particle(ast.x, ast.y,
                                                          speed_mult=(2.0 if bonus_on else 1.0)))
                            # [CHECK CONSTRAINT 4] Split or destroy asteroid
                            new_asts.extend(ast.split())
                            break

                projectiles = [p for i, p in enumerate(projectiles) if i not in dead_proj_idx]
                asteroids   = [a for i, a in enumerate(asteroids)   if i not in dead_ast] + new_asts

                # [CHECK CONSTRAINT 5] All asteroids gone → level complete
                if not asteroids:
                    state      = LEVEL_DONE
                    lvl_end_ms = pygame.time.get_ticks()

        elif state == LEVEL_DONE:
            # Keep particles animating during the 2-second pause
            for p in particles:
                p.update()
            particles = [p for p in particles if p.alive]

            # [CHECK CONSTRAINT 5] Wait 2 seconds then advance to next level
            if pygame.time.get_ticks() - lvl_end_ms >= 2000:
                level     += 1
                spd_bonus += 0.3  # [CHECK CONSTRAINT 5] Base speed +0.3 px/frame per level
                ship       = Ship()
                projectiles = []
                # [CHECK CONSTRAINT 5] +2 starting asteroids per level
                count  = INIT_COUNT + (level - 1) * 2
                s_min  = SPEED_MIN + spd_bonus
                s_max  = SPEED_MAX + spd_bonus
                asteroids = spawn_asteroids(count, s_min, s_max, ship.x, ship.y)
                state  = PLAYING

        # ── Draw ──────────────────────────────────────────────────────────────
        screen.fill(BLACK)

        for a in asteroids:
            a.draw(screen)

        for p in projectiles:
            p.draw(screen)

        for p in particles:
            p.draw(screen)

        # Draw ship during play and the level-transition pause
        if state in (PLAYING, LEVEL_DONE):
            ship.draw(screen)

        # ── HUD ───────────────────────────────────────────────────────────────
        screen.blit(font_sml.render(f"Level: {level}", True, WHITE), (10, 10))
        screen.blit(font_sml.render(f"Asteroids: {len(asteroids)}", True, WHITE), (10, 30))

        # [CHECK CONSTRAINT 7] Bonus feature indicator (top-right)
        b_color = YELLOW if bonus_on else GRAY
        b_label = f"[B] Triple Shot: {'ON' if bonus_on else 'OFF'}"
        b_surf  = font_sml.render(b_label, True, b_color)
        screen.blit(b_surf, (SCREEN_W - b_surf.get_width() - 10, 10))

        # ── State overlays ────────────────────────────────────────────────────
        if state == GAME_OVER:
            # [CHECK CONSTRAINT 5] Ship–asteroid collision message
            draw_centered(screen, "GAME OVER", font_big, RED, SCREEN_H // 2 - 55)
            draw_centered(screen, "Press R to Restart", font_med, WHITE, SCREEN_H // 2 + 18)

        elif state == FRIENDLY_FIRE:
            # [CHECK CONSTRAINT 3] Friendly fire message
            draw_centered(screen, "FRIENDLY FIRE!", font_big, YELLOW, SCREEN_H // 2 - 55)
            draw_centered(screen, "Press R to Restart", font_med, WHITE, SCREEN_H // 2 + 18)

        elif state == LEVEL_DONE:
            draw_centered(screen, f"Level {level} Clear!", font_big, GREEN, SCREEN_H // 2 - 55)
            draw_centered(screen, "Prepare for the next wave...", font_med, WHITE, SCREEN_H // 2 + 18)

        pygame.display.flip()

    pygame.quit()
    sys.exit()


if __name__ == '__main__':
    main()
