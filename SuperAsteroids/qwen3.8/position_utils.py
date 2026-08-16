"""Position helpers shared by every wrapping entity.

Asteroids (Stage 2) and the player craft (Stage 3) wrap the screen today;
projectiles, thruster exhaust, UFOs, and powerups (later stages) will join
them, so the modulo math lives in exactly one place.
"""


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
