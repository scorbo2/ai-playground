#!/usr/bin/env python3
"""
PlayerCraft - player spaceship for Solar Fortress.

Stage 3 implementation: basic movement, rotation, thrust, screen wrap,
and rendering as an elongated triangle.
"""

from __future__ import annotations

import math
import random
import pygame
import pygame.locals as pgl


class PlayerCraft:
    """Player-controlled spaceship with thrust, rotation and screen wrap."""

    def __init__(self, x: float, y: float) -> None:
        """Initialize craft at *x*, *y*.

        Parameters
        ----------
        x, y:
            Starting screen coordinates (pixels).
        """
        self.x: float = float(x)
        self.y: float = float(y)
        # Angle in degrees, 0 = right, positive clockwise. Start pointing up.
        self.angle: float = -90.0
        self.velocity_x: float = 0.0
        self.velocity_y: float = 0.0

        # Movement constants per spec
        self.rotation_speed_deg_per_frame: float = 5.0
        self.acceleration_per_frame: float = 0.3
        self.max_speed: float = 8.0
        self.friction: float = 0.98

        # Visual constants
        self.width: float = 20.0
        self.height: float = 30.0
        self.collision_radius: float = 20.0

        # Colors
        self.fill_color: tuple[int, int, int] = (200, 200, 200)
        self.outline_color: tuple[int, int, int] = (255, 255, 255)

        # Thruster particles
        self.thruster_particles: list[dict] = []

    def reset_position(self, width: int, height: int) -> None:
        """Place craft at a random safe spawn within 100px of a screen edge.

        Resets velocity and orientation to defaults.
        """
        margin = 100
        edge = random.choice(['top', 'bottom', 'left', 'right'])
        if edge == 'top':
            self.x = random.uniform(margin, max(margin, width - margin))
            self.y = random.uniform(0, margin)
        elif edge == 'bottom':
            self.x = random.uniform(margin, max(margin, width - margin))
            self.y = random.uniform(max(0, height - margin), height)
        elif edge == 'left':
            self.x = random.uniform(0, margin)
            self.y = random.uniform(margin, max(margin, height - margin))
        else:  # right
            self.x = random.uniform(max(0, width - margin), width)
            self.y = random.uniform(margin, max(margin, height - margin))

        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.angle = -90.0

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def update(self, keys: pygame.key.ScancodeWrapper, screen_width: int, screen_height: int) -> None:
        """Advance simulation one frame.

        Parameters
        ----------
        keys:
            Result of ``pygame.key.get_pressed()``.
        screen_width, screen_height:
            Current window dimensions for screen-wrap handling.
        """
        # Rotation - immediate stop when key released
        if keys[pgl.K_LEFT]:
            self.angle -= self.rotation_speed_deg_per_frame
        if keys[pgl.K_RIGHT]:
            self.angle += self.rotation_speed_deg_per_frame

        # Thrust
        thrusting = keys[pgl.K_UP]
        if thrusting:
            rad = math.radians(self.angle)
            self.velocity_x += math.cos(rad) * self.acceleration_per_frame
            self.velocity_y += math.sin(rad) * self.acceleration_per_frame

            # Clamp to max speed
            speed = math.hypot(self.velocity_x, self.velocity_y)
            if speed > self.max_speed:
                scale = self.max_speed / speed
                self.velocity_x *= scale
                self.velocity_y *= scale

            # Spawn thruster exhaust particle
            self._spawn_thruster_particle()
        else:
            # Linear friction when not thrusting
            self.velocity_x *= self.friction
            self.velocity_y *= self.friction

            # Prevent endless micro-drift
            if abs(self.velocity_x) < 0.01:
                self.velocity_x = 0.0
            if abs(self.velocity_y) < 0.01:
                self.velocity_y = 0.0

        # Integrate position
        self.x += self.velocity_x
        self.y += self.velocity_y

        # Screen wrap
        if self.x < 0:
            self.x = float(screen_width)
        elif self.x > screen_width:
            self.x = 0.0
        if self.y < 0:
            self.y = float(screen_height)
        elif self.y > screen_height:
            self.y = 0.0

        # Update thruster particles
        for particle in self.thruster_particles[:]:
            particle['x'] += particle['vx']
            particle['y'] += particle['vy']
            particle['alpha'] *= 0.95
            if particle['alpha'] <= 1:
                self.thruster_particles.remove(particle)

    def _spawn_thruster_particle(self) -> None:
        """Spawn a thruster exhaust particle at the rear of the ship."""
        # Rear position offset from center
        rad = math.radians(self.angle)
        rear_offset = self.height / 2.0
        rear_x = self.x - math.cos(rad) * rear_offset
        rear_y = self.y - math.sin(rad) * rear_offset

        # Random direction around rear with some spread
        base_angle = self.angle + 180.0
        spread = random.uniform(-30.0, 30.0)
        particle_angle = math.radians(base_angle + spread)
        speed = random.uniform(6.0, 10.0)
        vx = math.cos(particle_angle) * speed
        vy = math.sin(particle_angle) * speed

        radius = random.randint(3, 8)
        self.thruster_particles.append({
            'x': rear_x,
            'y': rear_y,
            'vx': vx,
            'vy': vy,
            'radius': radius,
            'alpha': 255.0,
        })

    def draw(self, surface: pygame.Surface) -> None:
        """Render the elongated triangle with white outline and light-gray fill."""
        # Draw thruster particles first (behind ship)
        for particle in self.thruster_particles:
            alpha = max(0, int(particle['alpha']))
            if alpha <= 0:
                continue
            # Color transition yellow -> orange -> red based on alpha
            t = alpha / 255.0
            if t > 0.66:
                color = (255, 255, 0)
            elif t > 0.33:
                color = (255, 165, 0)
            else:
                color = (255, 0, 0)
            radius = int(particle['radius'])
            # Create temporary surface for alpha blending
            temp = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
            pygame.draw.circle(temp, (*color, alpha), (radius, radius), radius)
            surface.blit(temp, (int(particle['x'] - radius), int(particle['y'] - radius)))

        # Define triangle points relative to center: tip forward, base rear
        tip = (0.0, -self.height / 2.0)
        left = (-self.width / 2.0, self.height / 2.0)
        right = (self.width / 2.0, self.height / 2.0)

        # Offset drawing by 90° so visual orientation matches thrust direction
        draw_angle = self.angle + 90.0
        rad = math.radians(draw_angle)
        cos_a = math.cos(rad)
        sin_a = math.sin(rad)

        def rotate_point(px: float, py: float) -> tuple[float, float]:
            rx = px * cos_a - py * sin_a
            ry = px * sin_a + py * cos_a
            return self.x + rx, self.y + ry

        points = [rotate_point(*p) for p in (tip, left, right)]
        # Pygame expects integer pixel coordinates
        int_points = [(int(x), int(y)) for x, y in points]

        pygame.draw.polygon(surface, self.fill_color, int_points)
        pygame.draw.polygon(surface, self.outline_color, int_points, 1)
