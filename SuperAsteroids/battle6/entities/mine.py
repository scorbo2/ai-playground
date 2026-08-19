"""Shrapnel mine entity.

Per spec (Weapons -> Shrapnel Mines):
- 12px radius circle with white 2px border, brown fill, crosshair overlay.
- Starts with craft velocity + 2px/frame backwards, subject to friction.
- Grace period 90 frames, then activation radius 150px.
- Activates on proximity, detonates 180 frames after activation.
- Contact with any object triggers immediate explosion (except other mines).
- Explosion spawns 8 cannon-style projectiles (level 1 or level 3 depending
  on mine power) with 500px travel, no grace.
- Mine cannot be deactivated once activated.
- Pulse visual every 120 frames for 5 frames.
"""

import math
import random

import pygame

from game_constants import (
    BROWN,
    LIGHT_GRAY,
    LIGHT_RED,
    MINE_ACTIVATION_RADIUS,
    MINE_BACKWARD_SPEED,
    MINE_BORDER_WIDTH,
    MINE_DETONATION_DELAY,
    MINE_FILL_COLOR,
    MINE_GRACE_FRAMES,
    MINE_PULSE_DURATION,
    MINE_PULSE_INTERVAL,
    MINE_RADIUS,
    PLAYER_FRICTION,
    PLAYER_STALL_SPEED,
    WHITE,
    YELLOW,
)
from position_utils import wrap_around


class ShrapnelMine:
    """A mine released by the Shrapnel Mines weapon."""

    def __init__(self, x: float, y: float, vx: float, vy: float, power_level: int = 1):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.power_level = power_level
        self.radius = MINE_RADIUS
        self.grace_frames = MINE_GRACE_FRAMES
        self.activated = False
        self.activation_frame = None
        # Pulse timer: counts frames since last pulse start
        self._pulse_timer = random.randint(0, MINE_PULSE_INTERVAL)

    @property
    def is_active(self) -> bool:
        return self.activated

    @property
    def is_detonated(self) -> bool:
        return self.activated and self.activation_frame is not None and \
               (self._frames_since_activation() >= MINE_DETONATION_DELAY)

    def _frames_since_activation(self) -> int:
        if not self.activated or self.activation_frame is None:
            return 0
        # The activation_frame is stored as the frame count at activation;
        # we approximate by using an internal counter updated each update.
        # Simpler: keep a counter.
        return getattr(self, "_activation_counter", 0)

    # We'll maintain a counter internally
    def update(self, width: int, height: int) -> bool:
        """Return False if the mine should be removed (detonated)."""
        # Apply friction like the craft
        speed = math.hypot(self.vx, self.vy)
        if speed > 0:
            self.vx *= PLAYER_FRICTION
            self.vy *= PLAYER_FRICTION
            speed = math.hypot(self.vx, self.vy)
            if speed < PLAYER_STALL_SPEED:
                self.vx = 0.0
                self.vy = 0.0

        self.x += self.vx
        self.y += self.vy
        self.x, self.y = wrap_around(self.x, self.y, self.radius, width, height)

        # Grace countdown
        if self.grace_frames > 0:
            self.grace_frames -= 1

        # Update pulse timer
        self._pulse_timer += 1

        # If activated, count down to detonation
        if self.activated:
            self._activation_counter = getattr(self, "_activation_counter", 0) + 1
            if self._activation_counter >= MINE_DETONATION_DELAY:
                return False  # signal detonation
        return True

    def activate(self) -> None:
        if not self.activated and self.grace_frames <= 0:
            self.activated = True
            self._activation_counter = 0

    def pulse_active(self) -> bool:
        """True during the 5-frame yellow flash."""
        # Pulse every 120 frames for 5 frames
        cycle = self._pulse_timer % MINE_PULSE_INTERVAL
        return cycle < MINE_PULSE_DURATION

    def crosshair_color(self) -> tuple:
        base = LIGHT_RED if self.activated else LIGHT_GRAY
        if self.pulse_active():
            return YELLOW
        return base

    def draw(self, screen: pygame.Surface) -> None:
        # Brown fill with white border
        pygame.draw.circle(screen, MINE_FILL_COLOR,
                           (int(round(self.x)), int(round(self.y))),
                           self.radius)
        pygame.draw.circle(screen, WHITE,
                           (int(round(self.x)), int(round(self.y))),
                           self.radius, width=MINE_BORDER_WIDTH)
        # Crosshair
        color = self.crosshair_color()
        # Vertical line
        pygame.draw.line(screen, color,
                         (int(round(self.x)), int(round(self.y - self.radius))),
                         (int(round(self.x)), int(round(self.y + self.radius))),
                         2)
        # Horizontal line
        pygame.draw.line(screen, color,
                         (int(round(self.x - self.radius)), int(round(self.y))),
                         (int(round(self.x + self.radius)), int(round(self.y))),
                         2)

    @staticmethod
    def spawn_from_craft(craft, power_level: int = 1):
        """Create a mine at the rear of the craft."""
        # Rear position: opposite heading
        rad = math.radians(craft.angle)
        dir_x, dir_y = math.cos(rad), math.sin(rad)
        # Rear offset
        rear_offset = 15  # approximate
        x = craft.x - dir_x * rear_offset
        y = craft.y - dir_y * rear_offset
        # Velocity: craft velocity + backwards 2 px/frame
        vx = craft.vx - dir_x * MINE_BACKWARD_SPEED
        vy = craft.vy - dir_y * MINE_BACKWARD_SPEED
        return ShrapnelMine(x, y, vx, vy, power_level)
