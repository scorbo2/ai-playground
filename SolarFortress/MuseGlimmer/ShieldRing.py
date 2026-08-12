#!/usr/bin/env python3
"""
ShieldRing - rotating force field for Solar Fortress.

Implements a 16-sided rotating ring with configurable diameter, color,
line width and rotation speed. Stage 2 renders active segments only.
"""

from __future__ import annotations

import math
import pygame


class ShieldRing:
    """Rotating shield ring composed of 16 line segments."""

    def __init__(
        self,
        diameter: float,
        color: tuple[int, int, int],
        width: int,
        rotation_speed_deg_per_frame: float,
        clockwise: bool = True,
    ) -> None:
        """Create a shield ring.

        Parameters
        ----------
        diameter:
            Diameter in pixels.
        color:
            RGB color for the segments.
        width:
            Line width in pixels.
        rotation_speed_deg_per_frame:
            Absolute speed in degrees per frame.
        clockwise:
            True for clockwise rotation, False for counter-clockwise.
        """
        self.diameter = float(diameter)
        self.radius = self.diameter / 2.0
        self.color = color
        self.width = int(width)
        # Apply sign for direction
        speed = float(rotation_speed_deg_per_frame)
        self.rotation_speed = speed if clockwise else -speed
        self.angle_offset = 0.0
        self.num_segments = 16
        self.segment_angle = 360.0 / self.num_segments
        # Disable timer per segment (0 = active)
        self.segment_timers = [0] * self.num_segments

    def update(self) -> list[int]:
        """Advance rotation by one frame and update segment timers.

        Returns
        -------
        list[int]
            Indices of segments that just reactivated this frame.
        """
        self.angle_offset += self.rotation_speed
        # Keep angle bounded to avoid floating point drift
        self.angle_offset %= 360.0

        reactivated = []
        for i in range(self.num_segments):
            if self.segment_timers[i] > 0:
                self.segment_timers[i] -= 1
                if self.segment_timers[i] == 0:
                    reactivated.append(i)
        return reactivated

    def draw(self, surface: pygame.Surface, center_x: float, center_y: float) -> None:
        """Draw all active segments centered at (center_x, center_y)."""
        # Pre-compute to avoid repeated trig in inner loop? Keep simple for clarity.
        for i in range(self.num_segments):
            if self.segment_timers[i] > 0:
                # Segment disabled - do not render
                continue
            start_angle_deg = self.angle_offset + i * self.segment_angle
            end_angle_deg = self.angle_offset + (i + 1) * self.segment_angle

            start_rad = math.radians(start_angle_deg)
            end_rad = math.radians(end_angle_deg)

            x1 = int(center_x + self.radius * math.cos(start_rad))
            y1 = int(center_y + self.radius * math.sin(start_rad))
            x2 = int(center_x + self.radius * math.cos(end_rad))
            y2 = int(center_y + self.radius * math.sin(end_rad))

            pygame.draw.line(surface, self.color, (x1, y1), (x2, y2), self.width)

    def check_collision(self, point_x: float, point_y: float, center_x: float, center_y: float, threshold: float) -> bool:
        """Return True if *point* is within *threshold* pixels of any active segment.

        This is used for craft vs shield collision detection. Disabled segments
        are ignored.
        """
        for i in range(self.num_segments):
            if self.segment_timers[i] > 0:
                # Segment disabled - cannot collide
                continue
            start_angle_deg = self.angle_offset + i * self.segment_angle
            end_angle_deg = self.angle_offset + (i + 1) * self.segment_angle

            start_rad = math.radians(start_angle_deg)
            end_rad = math.radians(end_angle_deg)

            x1 = center_x + self.radius * math.cos(start_rad)
            y1 = center_y + self.radius * math.sin(start_rad)
            x2 = center_x + self.radius * math.cos(end_rad)
            y2 = center_y + self.radius * math.sin(end_rad)

            if self._point_to_segment_distance(point_x, point_y, x1, y1, x2, y2) < threshold:
                return True
        return False

    def hit_by_projectile(self, point_x: float, point_y: float, center_x: float, center_y: float, threshold: float = 6.0) -> bool:
        """Check if an active segment is hit by a projectile.

        If hit, the nearest active segment is disabled for 300 frames and True is returned.
        Only one segment can be disabled per call.

        Parameters
        ----------
        point_x, point_y:
            Projectile center position.
        center_x, center_y:
            Shield ring center.
        threshold:
            Distance threshold for a hit (default 6px).

        Returns
        -------
        bool
            True if a segment was hit and disabled.
        """
        nearest_dist = float('inf')
        hit_index = -1

        for i in range(self.num_segments):
            if self.segment_timers[i] > 0:
                continue
            start_angle_deg = self.angle_offset + i * self.segment_angle
            end_angle_deg = self.angle_offset + (i + 1) * self.segment_angle

            start_rad = math.radians(start_angle_deg)
            end_rad = math.radians(end_angle_deg)

            x1 = center_x + self.radius * math.cos(start_rad)
            y1 = center_y + self.radius * math.sin(start_rad)
            x2 = center_x + self.radius * math.cos(end_rad)
            y2 = center_y + self.radius * math.sin(end_rad)

            dist = self._point_to_segment_distance(point_x, point_y, x1, y1, x2, y2)
            if dist < threshold and dist < nearest_dist:
                nearest_dist = dist
                hit_index = i

        if hit_index != -1:
            self.segment_timers[hit_index] = 300
            return True
        return False

    @staticmethod
    def _point_to_segment_distance(px: float, py: float, x1: float, y1: float, x2: float, y2: float) -> float:
        """Euclidean distance from point to line segment."""
        # Vector from segment start to end
        dx = x2 - x1
        dy = y2 - y1
        if dx == 0 and dy == 0:
            # Segment is a point
            return math.hypot(px - x1, py - y1)

        # Project point onto line, computing parameter t
        t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
        t = max(0.0, min(1.0, t))

        # Closest point on segment
        closest_x = x1 + t * dx
        closest_y = y1 + t * dy
        return math.hypot(px - closest_x, py - closest_y)
