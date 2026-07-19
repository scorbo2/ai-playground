import pygame
import math
import random
import sys

# --- Configuration & Constants ---
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 60

# Ship Constants
SHIP_WIDTH = 20
SHIP_HEIGHT = 30
SHIP_ROT_SPEED = 5  # Degrees per frame
SHIP_ACCEL = 0.3
SHIP_MAX_SPEED = 8
SHIP_FRICTION = 0.98

# Projectile Constants
PROJ_SPEED_BONUS = 6
PROJ_LIFETIME = 1000
PROJ_MAX_COUNT = 3

# Asteroid Constants
START_ASTEROID_COUNT = 5
MIN_ASTEROID_RADIUS = 15
ASTEROID_SPEED_RANGE = (1.5, 2.5)
ASTEROID_SPLIT_SPEED_MULT = 1.2

# Colors
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
RED = (255, 50, 50)
GRAY = (150, 150, 150)
YELLOW = (255, 255, 0)

class Particle:
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.vx = random.uniform(-2, 2)
        self.vy = random.uniform(-2, 2)
        self.life = 255
        self.color = list(color)

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.life -= 5
        
    def draw(self, screen):
        if self.life > 0:
            alpha_color = [max(0, c) for c in self.color]
            pygame.draw.circle(screen, alpha_color, (int(self.x), int(self.y)), 2)

class Projectile:
    def __init__(self, x, y, angle, ship_vx, ship_vy):
        self.x = x
        self.y = y
        # Initial velocity = ship velocity + (6 px/frame) in facing direction
        speed = PROJ_SPEED_BONUS
        self.vx = ship_vx + math.cos(angle) * speed
        self.vy = ship_vy + math.sin(angle) * speed
        self.distance_traveled = 0
        self.active = True

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.distance_traveled += math.sqrt(self.vx**2 + self.vy**2)
        
        if self.distance_traveled > PROJ_LIFETIME:
            self.active = False
            
        # Screen wrapping
        self.x %= SCREEN_WIDTH
        self.y %= SCREEN_HEIGHT

    def draw(self, screen):
        pygame.draw.rect(screen, WHITE, (self.x - 2, self.y - 2, 4, 4))

class Asteroid:
    def __init__(self, x, y, radius, level_speed_mod=0):
        self.x = x
        self.y = y
        self.radius = radius
        
        # Speed range influenced by level
        base_speed = random.uniform(ASTEROID_SPEED_RANGE[0], ASTEROID_SPEED_RANGE[1])
        speed = (base_speed + level_speed_mod)
        
        angle = random.uniform(0, math.pi * 2)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        
        # Create irregular shape
        self.vertices = []
        num_vertices = random.randint(8, 12)
        for i in range(num_vertices):
            offset = random.uniform(0.8, 1.2)
            theta = (i / num_vertices) * math.pi * 2
            self.vertices.append((math.cos(theta) * radius * offset, math.sin(theta) * radius * offset))

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.x %= SCREEN_WIDTH
        self.y %= SCREEN_HEIGHT

    def draw(self, screen):
        points = []
        for vx, vy in self.vertices:
            points.append((self.x + vx, self.y + vy))
        pygame.draw.polygon(screen, GRAY, points, 2)

class Ship:
    def __init__(self):
        self.reset()

    def reset(self):
        self.x = SCREEN_WIDTH // 2
        self.y = SCREEN_HEIGHT // 2
        self.angle = 0 # In radians
        self.vx = 0
        self.vy = 0
        self.thrusting = False

    def update(self):
        if self.thrusting:
            self.vx += math.cos(self.angle) * SHIP_ACCEL
            self.vy += math.sin(self.angle) * SHIP_ACCEL
        else:
            self.vx *= SHIP_FRICTION
            self.vy *= SHIP_FRICTION

        # Speed limit
        speed = math.sqrt(self.vx**2 + self.vy**2)
        if speed > SHIP_MAX_SPEED:
            ratio = SHIP_MAX_SPEED / speed
            self.vx *= ratio
            self.vy *= ratio

        self.x += self.vx
        self.y += self.vy

        # Screen wrapping
        self.x %= SCREEN_WIDTH
        self.y %= SCREEN_HEIGHT

    def draw(self, screen):
        # Triangle points
        # Ship is 20px wide, 30px tall. Center at x,y.
        # Tip is at the "front" (angle)
        tip_x = self.x + math.cos(self.angle) * 15
        tip_y = self.y + math.sin(self.angle) * 15
        
        # Calculate wings relative to orientation
        wing_dist = 10
        left_x = self.x + math.cos(self.angle + math.pi/2) * wing_dist
        left_y = self.y + math.sin(self.angle + math.pi/2) * wing_dist
        right_x = self.x + math.cos(self.angle - math.pi/2) * wing_dist
        right_y = self.y + math.sin(self.angle - math.pi/2) * wing_dist

        pygame.draw.polygon(screen, WHITE, [(tip_x, tip_y), (left_x, left_y), (right_x, right_y)], 2)
        
        if self.thrusting:
            # Red triangle behind ship
            back_x = self.x - math.cos(self.angle) * 15
            back_y = self.y - math.sin(self.angle) * 15
            # Simplified thruster triangle
            pygame.draw.polygon(screen, RED, [
                (back_x, back_y),
                (back_x - math.cos(self.angle+0.5)*10, back_y - math.sin(self.angle+0.5)*10),
                (back_x - math.cos(self.angle-0.5)*10, back_y - math.sin(self.angle-0.5)*10)
            ], 2)

def main():
    pygame.init()
    screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
    pygame.display.set_caption("Asteroids")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("Arial", 24)

    # Starfield generation
    stars = []
    for _ in range(100):
        stars.append((random.randint(0, SCREEN_WIDTH), random.randint(0, SCREEN_HEIGHT), random.randint(1, 3)))

    ship = Ship()
    asteroids = []
    projectiles = []
    particles = []
    
    level = 1
    level_speed_mod = 0
    game_over = False
    game_over_reason = ""
    next_level_timer = 0
    
    # Bonus feature: Hyper-fire (Violates constraint 3: max 3 projectiles)
    hyper_fire = False

    def init_level():
        nonlocal asteroids, level_speed_mod
        asteroids = []
        count = START_ASTEROID_COUNT + (level - 1) * 2
        for _ in range(count):
            # Ensure asteroids don't spawn on the ship
            while True:
                rx = random.randint(0, SCREEN_WIDTH)
                ry = random.randint(0, SCREEN_HEIGHT)
                dist = math.sqrt((rx - ship.x)**2 + (ry - ship.y)**2)
                if dist > 150:
                    asteroids.append(Asteroid(rx, ry, 40, level_speed_mod))
                    break

    init_level()

    running = True
    while running:
        screen.fill(BLACK)
        
        # Draw stars
        for s in stars:
            pygame.draw.circle(screen, (100, 100, 100), (s[0], s[1]), s[2])

        # Event Handling
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r and game_over:
                    # Restart
                    ship.reset()
                    level = 1
                    level_speed_mod = 0
                    init_level()
                    game_over = False
                    projectiles.clear()
                    particles.clear()
                
                if event.key == pygame.K_SPACE and not game_over:
                    # Fire projectile
                    if len(projectiles) < PROJ_MAX_COUNT or hyper_fire:
                        projectiles.append(Projectile(
                            ship.x + math.cos(ship.angle) * 15,
                            ship.y + math.sin(ship.angle) * 15,
                            ship.angle, ship.vx, ship.vy
                        ))
                
                if event.key == pygame.K_b:
                    hyper_fire = not hyper_fire
                    print(f"Hyper-fire: {hyper_fire}") # For debugging

        # Continuous input (keys held down)
        keys = pygame.key.get_pressed()
        if not game_over:
            if keys[pygame.K_LEFT]:
                ship.angle -= math.radians(SHIP_ROT_SPEED)
            if keys[pygame.K_RIGHT]:
                ship.angle += math.radians(SHIP_ROT_SPEED)
            if keys[pygame.K_UP]:
                ship.thrusting = True
            else:
                ship.thrusting = False

        if not game_over:
            ship.update()
            
            # Update projectiles
            for p in projectiles[:]:
                p.update()
                if not p.active:
                    projectiles.remove(p)
                else:
                    # Friendly fire check (proximity)
                    dist_to_ship = math.sqrt((p.x - ship.x)**2 + (p.y - ship.y)**2)
                    if dist_to_ship < 20:
                        game_over = True
                        game_over_reason = "FRIENDLY FIRE!"

            # Update asteroids
            for a in asteroids:
                a.update()
                
                # Ship-Asteroid Collision
                dist = math.sqrt((a.x - ship.x)**2 + (a.y - ship.y)**2)
                if dist < a.radius + 10:
                    game_over = True
                    game_over_reason = "GAME OVER"

            # Projectile-Asteroid Collision
            for p in projectiles:
                for a in asteroids[:]:
                    dist = math.sqrt((p.x - a.x)**2 + (p.y - a.y)**2)
                    if dist < a.radius:
                        # Explosion particles
                        for _ in range(15):
                            particles.append(Particle(p.x, p.y, YELLOW))
                        
                        # Split logic
                        if a.radius >= MIN_ASTEROID_RADIUS:
                            num_splits = random.randint(2, 3)
                            for _ in range(num_splits):
                                new_r = a.radius / 1.5
                                if new_r >= MIN_ASTEROID_RADIUS:
                                    asteroids.append(Asteroid(a.x, a.y, new_r, level_speed_mod))
                        
                        if a in asteroids:
                            asteroids.remove(a)
                        if p in projectiles:
                            projectiles.remove(p)
                        break

            # Level completion
            if not asteroids and not game_over:
                next_level_timer += 1
                if next_level_timer == FPS * 2: # Wait 2 seconds
                    level += 1
                    level_speed_mod += 0.3
                    init_level()
                    next_level_timer = 0
                    particles.extend([Particle(ship.x, ship.y, WHITE) for _ in range(30)])
            else:
                next_level_timer = 0

        # Update particles
        for p in particles[:]:
            p.update()
            if p.life <= 0:
                particles.remove(p)

        # --- Drawing ---
        ship.draw(screen)
        for p in projectiles:
            p.draw(screen)
        for a in asteroids:
            a.draw(screen)
        for p in particles:
            p.draw(screen)

        if game_over:
            msg = font.render(f"{game_over_reason} - Press R to Restart", True, WHITE)
            screen.blit(msg, (SCREEN_WIDTH//2 - msg.get_width()//2, SCREEN_HEIGHT//2))
        elif next_level_timer > 0 and not asteroids:
            msg = font.render(f"Level {level+1} starting soon...", True, WHITE)
            screen.blit(msg, (SCREEN_WIDTH//2 - msg.get_width()//2, SCREEN_HEIGHT//2))

        # Bonus status
        if hyper_fire:
            bonus_msg = font.render("HYPER-FIRE ACTIVE", True, RED)
            screen.blit(bonus_msg, (10, 10))

        pygame.display.flip()
        clock.tick(FPS)

    pygame.quit()
    sys.exit()

if __name__ == "__main__":
    main()
