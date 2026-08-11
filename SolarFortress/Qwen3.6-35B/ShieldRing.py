#!/usr/bin/env python3
"""
ShieldRing - one of the three concentric rotating force fields.

Each ring is a 16-sided roughly-circular polygon whose segments can be
individually disabled (stage 6+) and reactivated after a timeout.

Stage 2: all segments are always active and the ring simply rotates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

import pygame

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

NUM_SEGMENTS: int = 16
DISABLE_DURATION: int = 300  # frames a segment stays disabled


# ---------------------------------------------------------------------------
# Geometry helper
# ---------------------------------------------------------------------------

def _point_to_segment_distance(
    px: float, py: float,
    x1: float, y1: float,
    x2: float, y2: float,
) -> float:
    """Return the shortest distance from point *(px, py)* to the line
    segment *(x1, y1)-(x2, y2)*.

    Parameters
    ----------
    px, py:
        Coordinates of the test point.
    x1, y1, x2, y2:
        Endpoints of the line segment.

    Returns
    -------
    float
        The perpendicular distance if the projection falls within the
        segment, otherwise the distance to the nearest endpoint.
    """
    dx = x2 - x1
    dy = y2 - y1

    # If the segment is degenerate (both endpoints are the same point)
    if dx == 0 and dy == 0:
        return math.hypot(px - x1, py - y1)

    # t is the normalised position along the segment (0 = start, 1 = end)
    t = ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)
    t = max(0.0, min(1.0, t))

    closest_x = x1 + t * dx
    closest_y = y1 + t * dy

    return math.hypot(px - closest_x, py - closest_y)


# ---------------------------------------------------------------------------
# ShieldRing
# ---------------------------------------------------------------------------

@dataclass
class ShieldRing:
    """One concentric rotating force-field ring.

    Parameters
    ----------
    radius:
        Diameter of the ring in pixels.  The vertices sit on this circle.
    rotation_speed:
        Degrees per frame.  Positive → clockwise, negative → counter-clockwise.
    color:
        RGB colour tuple for the segment lines.
    line_width:
        Thickness of each segment line in pixels.
    num_segments:
        Number of segments (default 16).
    """

    radius: int
    rotation_speed: float
    color: tuple[int, int, int]
    line_width: int
    num_segments: int = NUM_SEGMENTS

    # Internal state — not part of the constructor signature.
    _angle: float = field(default=0.0, repr=False)
    _timers: list[int] = field(default_factory=lambda: [0] * NUM_SEGMENTS)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset all segment timers to 0 (fully active)."""
        self._timers = [0] * self.num_segments
        self._angle = 0.0

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self) -> None:
        """Advance the rotation angle and decrement segment timers by one frame."""
        self._angle += self.rotation_speed
        # Keep angle in [0, 360) to avoid floating-point drift over very long runs.
        self._angle %= 360.0

        for i in range(self.num_segments):
            if self._timers[i] > 0:
                self._timers[i] -= 1

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def render(
        self,
        surface: pygame.Surface,
        center_x: int,
        center_y: int,
    ) -> None:
        """Draw all *active* segments as lines on *surface*.

        Disabled segments are simply skipped — no line is drawn.

        Parameters
        ----------
        surface:
            Target display surface.
        center_x, center_y:
            Screen coordinates of the ring centre (the fortress position).
        """
        for i in range(self.num_segments):
            # Skip disabled segments
            if self._timers[i] > 0:
                continue

            # Compute endpoints for this segment
            a1 = math.radians(self._angle + i * 360.0 / self.num_segments)
            a2 = math.radians(self._angle + (i + 1) * 360.0 / self.num_segments)

            x1 = center_x + self.radius * math.cos(a1)
            y1 = center_y + self.radius * math.sin(a1)
            x2 = center_x + self.radius * math.cos(a2)
            y2 = center_y + self.radius * math.sin(a2)

            pygame.draw.line(surface, self.color, (x1, y1), (x2, y2), self.line_width)

    # ------------------------------------------------------------------
    # Collision queries (for later stages)
    # ------------------------------------------------------------------

    def disable_segment_at(
        self,
        px: float,
        py: float,
        center_x: float,
        center_y: float,
    ) -> None:
        """Disable the active segment *closest* to point *(px, py)*.

        If no active segment is within 6 px of the point, nothing happens.

        Parameters
        ----------
        px, py:
            Screen coordinates of the impact point (e.g. projectile centre).
        center_x, center_y:
            Screen coordinates of the ring centre.
        """
        # Convert impact point to local (ring-centred) coordinates
        lx = px - center_x
        ly = py - center_y

        best_dist = 6.0  # threshold from the spec
        best_idx = -1

        for i in range(self.num_segments):
            if self._timers[i] > 0:
                continue  # already disabled

            # Compute the segment endpoints in local space
            a1 = math.radians(self._angle + i * 360.0 / self.num_segments)
            a2 = math.radians(self._angle + (i + 1) * 360.0 / self.num_segments)

            x1 = self.radius * math.cos(a1)
            y1 = self.radius * math.sin(a1)
            x2 = self.radius * math.cos(a2)
            y2 = self.radius * math.sin(a2)

            dist = _point_to_segment_distance(lx, ly, x1, y1, x2, y2)

            if dist < best_dist:
                best_dist = dist
                best_idx = i

        if best_idx >= 0:
            self._timers[best_idx] = DISABLE_DURATION

    def contains_point(
        self,
        px: float,
        py: float,
        center_x: float,
        center_y: float,
    ) -> bool:
        """Return ``True`` if *(px, py)* is within 6 px of any active segment.

        Used for player-craft collision with shield segments.

        Parameters
        ----------
        px, py:
            Screen coordinates to test.
        center_x, center_y:
            Screen coordinates of the ring centre.

        Returns
        -------
        bool
            ``True`` if the point is close enough to an active segment.
        """
        # Convert test point to local (ring-centred) coordinates
        lx = px - center_x
        ly = py - center_y

        for i in range(self.num_segments):
            if self._timers[i] > 0:
                continue

            a1 = math.radians(self._angle + i * 360.0 / self.num_segments)
            a2 = math.radians(self._angle + (i + 1) * 360.0 / self.num_segments)

            x1 = self.radius * math.cos(a1)
            y1 = self.radius * math.sin(a1)
            x2 = self.radius * math.cos(a2)
            y2 = self.radius * math.sin(a2)

            dist = _point_to_segment_distance(lx, ly, x1, y1, x2, y2)
            if dist <= 6.0:
                return True

        return False

    def get_active_segments(
        self,
        center_x: int,
        center_y: int,
    ) -> list[tuple[float, float, float, float]]:
        """Return a list of active segment line endpoints as
        ``[(x1, y1, x2, y2), ...]`` in **screen coordinates**.

        Parameters
        ----------
        center_x, center_y:
            Screen coordinates of the ring centre.

        Returns
        -------
        list[tuple[float, float, float, float]]
            Each tuple is ``(x1, y1, x2, y2)`` for an active segment.
        """
        segments: list[tuple[float, float, float, float]] = []
        for i in range(self.num_segments):
            if self._timers[i] > 0:
                continue

            a1 = math.radians(self._angle + i * 360.0 / self.num_segments)
            a2 = math.radians(self._angle + (i + 1) * 360.0 / self.num_segments)

            x1 = center_x + self.radius * math.cos(a1)
            y1 = center_y + self.radius * math.sin(a1)
            x2 = center_x + self.radius * math.cos(a2)
            y2 = center_y + self.radius * math.sin(a2)

            segments.append((x1, y1, x2, y2))

        return segments
