"""Position helpers shared by every wrapping entity.

Asteroids (Stage 2) and the player craft (Stage 3) wrap the screen today;
projectiles, thruster exhaust, UFOs, and powerups (later stages) will join
them, so the modulo math lives in exactly one place.
"""

import math


def wrap_around(x: float, y: float, radius: float,
                width: int, height: int) -> tuple:
    """Wrap a point so its bounding circle re-enters from the opposite edge
    as soon as it is fully off-screen.

    Modulo math (rather than a pair of if/else checks) stays correct even
    when a window resize - or returning from full screen - leaves the point
    far outside the new bounds. Every entity calls this once per frame, so
    the spec's "forced re-wrap right after a resize" happens on the very
    next frame with no dedicated resize handler.
    """
    return (
        (x + radius) % (width + 2 * radius) - radius,
        (y + radius) % (height + 2 * radius) - radius,
    )


def shortest_delta(delta: float, extent: float) -> float:
    """Signed SHORTEST offset from one point to another ``delta`` units apart
    along a wrapping axis of size ``extent`` (result in [-extent/2, extent/2)).

    Collision detection must respect screen wrap (spec), so every cross-object
    distance is measured through this fold first.
    """
    delta = delta % extent
    if delta > extent / 2:
        delta -= extent
    return delta


def torus_distance(x1: float, y1: float, x2: float, y2: float,
                   width: int, height: int) -> float:
    """Center-to-center distance between two points on the wrapped screen.

    Each axis folds across the wrap first, so a craft 5 px from the left
    edge is correctly seen as close to an object 5 px from the right edge.
    """
    dx = abs(shortest_delta(x1 - x2, width))
    dy = abs(shortest_delta(y1 - y2, height))
    return math.hypot(dx, dy)


def wrapped_circle_hits_box(cx: float, cy: float, radius: float,
                            box_x: float, box_y: float,
                            half_w: float, half_h: float,
                            width: int, height: int) -> bool:
    """Wrap-aware circle vs. axis-aligned box test.

    Projectiles keep their EXACT shape for collision (spec: "Cannon
    projectiles: use the exact shape and size"), so a 2x2 block is a
    half-size-1 box, tested the classic way - distance from the circle
    center to the nearest box point (the clamped delta vector), with each
    axis folded across the wrap first.
    """
    dx = shortest_delta(box_x - cx, width)
    dy = shortest_delta(box_y - cy, height)
    nearest_x = max(-half_w, min(half_w, dx))
    nearest_y = max(-half_h, min(half_h, dy))
    return (dx - nearest_x) ** 2 + (dy - nearest_y) ** 2 <= radius ** 2
