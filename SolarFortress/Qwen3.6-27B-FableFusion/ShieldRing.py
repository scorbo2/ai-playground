#!/usr/bin/env python3
"""
ShieldRing — a single rotating force-field ring around the fortress.

Each ring is a 16-sided polygon that rotates at a constant speed.
Stage 2 renders all segments continuously; segment disable/reattivation
logic is deferred to Stage 6 when player projectiles are introduced.
"""

from __future__ import annotations

import math
import logging

import pygame

logger = logging.getLogger("solar_fortress.shieldring")


class ShieldRing:
    """A rotating 16-sided force-field ring.

    Parameters
    ----------
    diameter :
        Outer diameter of the ring in pixels.
    rotation_speed_deg_per_frame :
        Rotation rate in degrees per frame. Positive = clockwise,
        negative = counter-clockwise.
    line_width :
        Width of the ring's line segments in pixels.
    color :
        RGB color tuple for the ring segments.
    """

    def __init__(
        self,
        diameter: int,
        rotation_speed_deg_per_frame: float,
        line_width: int,
        color: tuple[int, int, int],
    ) -> None:
        self._radius = diameter / 2.0
        self._rotation_speed = rotation_speed_deg_per_frame
        self._line_width = line_width
        self._color = color
        self._angle_deg = 0.0  # cumulative rotation angle
        self._center = (0, 0)
        self._rect = pygame.Rect(0, 0, diameter, diameter)

    @property
    def center(self) -> tuple[int, int]:
        """Current ring center position."""
        return self._center

    @center.setter
    def center(self, value: tuple[int, int]) -> None:
        """Update ring center (called every frame from the game loop)."""
        self._center = value
        self._rect.center = value

    def update(self) -> None:
        """Advance the ring's rotation by one frame."""
        self._angle_deg = (self._angle_deg + self._rotation_speed) % 360.0

    def _compute_vertices(self) -> list[tuple[float, float]]:
        """Compute the 16 vertex positions for the current rotation angle.

        Extracted as a shared helper so both rendering and collision
        detection use identical geometry (no subtle drift between what
        you see and what you collide with).
        """
        cx, cy = self._center
        angle_rad = math.radians(self._angle_deg)
        segment_angle = 2.0 * math.pi / 16  # 22.5 degrees per segment

        vertices: list[tuple[float, float]] = []
        for i in range(16):
            theta = angle_rad + i * segment_angle
            x = cx + self._radius * math.cos(theta)
            y = cy + self._radius * math.sin(theta)
            vertices.append((x, y))
        return vertices

    def render(self, surface: pygame.Surface) -> None:
        """Draw the 16-sided polygon onto *surface*."""
        vertices = self._compute_vertices()

        # Draw closed polygon: lines connecting consecutive vertices,
        # wrapping from last back to first.
        pygame.draw.lines(surface, self._color, True, vertices, self._line_width)

    def get_segments(self) -> list[tuple[tuple[float, float], tuple[float, float]]]:
        """Return the current positions of all 16 shield segments.

        Each segment is a pair of (start, end) points in world coordinates.
        Segments wrap from last vertex back to first, forming a closed ring.

        This is used by collision detection code to check distances from
        game objects to shield segments.
        """
        vertices = self._compute_vertices()
        segments: list[tuple[tuple[float, float], tuple[float, float]]] = []
        for i in range(16):
            start = vertices[i]
            end = vertices[(i + 1) % 16]
            segments.append((start, end))
        return segments
