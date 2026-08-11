#!/usr/bin/env python3
"""ShieldRing class for Solar Fortress.

Represents one of the three concentric 16-segment force-field rings
that protect the enemy fortress.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from typing import Tuple

# Per-segment disable duration (frames)
SEGMENT_DISABLE_FRAMES: int = 300
# Number of segments per ring
NUM_SEGMENTS: int = 16


class ShieldRing:
    """A rotating, multi-segment force-field ring.

    Each ring is a 16-sided polygon. Individual segments can be
    disabled for a fixed number of frames, creating temporary gaps
    that player projectiles can pass through.
    """

    def __init__(
        self,
        diameter: float,
        rotation_speed: float,
        color: Tuple[int, int, int],
        line_width: int,
    ) -> None:
        """Create a shield ring.

        Parameters
        ----------
        diameter:
            Outer diameter of the ring in pixels.
        rotation_speed:
            Degrees per frame. Positive = clockwise,
            negative = counter-clockwise.
        color:
            RGB colour for the ring's line segments.
        line_width:
            Pixel width of the drawn segments.
        """
        self.diameter: float = diameter
        self.radius: float = diameter / 2
        self.rotation_speed: float = rotation_speed
        self.color: Tuple[int, int, int] = color
        self.line_width: int = line_width
        self._rotation: float = 0.0  # degrees, accumulates every frame
        self._center: tuple[int, int] = (0, 0)
        # Per-segment disable timers. 0 = active, >0 = frames remaining.
        self._disabled_frames: list[int] = [0] * NUM_SEGMENTS
        # Track whether any segment was hit this frame so a single
        # projectile can disable at most one segment.
        self._hit_this_frame: bool = False
        # Track segments that just reactivated this frame (for audio)
        self._just_reactivated: bool = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def update(self, center: tuple[int, int]) -> None:
        """Advance rotation one frame and tick down disable timers.

        Must be called every frame regardless of game state so that
        disabled segments continue rotating with the ring.
        """
        self._center = center
        self._rotation = (self._rotation + self.rotation_speed) % 360
        self._hit_this_frame = False
        self._just_reactivated = False

        for i in range(NUM_SEGMENTS):
            if self._disabled_frames[i] > 0:
                self._disabled_frames[i] -= 1
                if self._disabled_frames[i] == 0:
                    self._just_reactivated = True

    def render(self, surface: pygame.Surface) -> None:
        """Draw active segments as lines forming the ring polygon."""
        vertices = self._compute_vertices()

        for i in range(NUM_SEGMENTS):
            if self._disabled_frames[i] > 0:
                continue  # Gaps are invisible

            start = vertices[i]
            end = vertices[(i + 1) % NUM_SEGMENTS]
            pygame.draw.line(surface, self.color, start, end, self.line_width)

    def segment_hit(self, px: float, py: float) -> bool:
        """Check if point (*px*, *py*) is within 6 px of any active segment.

        If an active segment is hit, it is disabled for
        ``SEGMENT_DISABLE_FRAMES`` frames and this method returns ``True``.
        A single call can disable at most one segment (enforced via
        ``_hit_this_frame``).

        Parameters
        ----------
        px, py:
            Point to test, in display-space pixels.

        Returns
        -------
        ``True`` if a segment was disabled, ``False`` otherwise.
        """
        if self._hit_this_frame:
            return False

        vertices = self._compute_vertices()

        for i in range(NUM_SEGMENTS):
            if self._disabled_frames[i] > 0:
                continue

            start = vertices[i]
            end = vertices[(i + 1) % NUM_SEGMENTS]
            dist = self._point_to_segment_distance(px, py, *start, *end)

            if dist <= 6:
                self._disabled_frames[i] = SEGMENT_DISABLE_FRAMES
                self._hit_this_frame = True
                return True

        return False

    def any_segment_disabled(self) -> bool:
        """Return True if any segment is currently disabled."""
        return any(f > 0 for f in self._disabled_frames)

    def any_segment_just_reactivated(self) -> bool:
        """Return True if any segment reactivated this frame.

        This flag is set during ``update()`` and cleared on the next
        call to ``update()``.  Used to trigger the ``shieldUp`` audio.
        """
        return self._just_reactivated

    def min_distance_to_active_segment(
        self, px: float, py: float,
    ) -> float:
        """Return the shortest distance from (*px*, *py*) to any active segment.

        Unlike ``segment_hit``, this is a pure query — it does not
        disable segments or track per-frame hit state.  Returns
        ``float('inf')`` when no segments are currently active.

        Parameters
        ----------
        px, py:
            Point to test, in display-space pixels.

        Returns
        -------
        Minimum distance in pixels, or infinity if all segments are disabled.
        """
        vertices = self._compute_vertices()
        min_dist: float = float("inf")

        for i in range(NUM_SEGMENTS):
            if self._disabled_frames[i] > 0:
                continue

            start = vertices[i]
            end = vertices[(i + 1) % NUM_SEGMENTS]
            dist = self._point_to_segment_distance(px, py, *start, *end)
            if dist < min_dist:
                min_dist = dist

        return min_dist

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _compute_vertices(self) -> list[Tuple[float, float]]:
        """Return the 16 vertex positions for the current rotation angle."""
        cx, cy = self._center
        r = self.radius
        angle_rad = math.radians(self._rotation)
        vertices: list[Tuple[float, float]] = []

        for i in range(NUM_SEGMENTS):
            seg_angle = angle_rad + (2 * math.pi * i / NUM_SEGMENTS)
            x = cx + r * math.cos(seg_angle)
            y = cy + r * math.sin(seg_angle)
            vertices.append((x, y))

        return vertices

    @staticmethod
    def _point_to_segment_distance(
        px: float, py: float,
        sx: float, sy: float,
        ex: float, ey: float,
    ) -> float:
        """Shortest distance from point P(px, py) to segment S->E.

        Uses standard vector projection clamped to the segment.
        """
        dx = ex - sx
        dy = ey - sy
        length_sq = dx * dx + dy * dy

        if length_sq == 0:
            # Degenerate segment — treat as a point
            return math.hypot(px - sx, py - sy)

        # Project P onto the segment, clamped to [0, 1]
        t = max(0, min(1, ((px - sx) * dx + (py - sy) * dy) / length_sq))
        proj_x = sx + t * dx
        proj_y = sy + t * dy
        return math.hypot(px - proj_x, py - proj_y)
