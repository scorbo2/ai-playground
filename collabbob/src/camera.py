"""Camera / world-to-screen mapping for the tactical view.

The camera is locked to the player's ship: the ship is *always* drawn at the
centre of the game view and the rest of the world slides past it (spec: "The
player's ship is always centered and zoom is fixed"). World coordinates are
planet-centred, so the system's planet sits at ``(0, 0)`` and drifts off-centre
as the player flies away from it — which is exactly what the Stage 8+ gameplay
loop needs, since the player must fly *to* the planet to land.

An earlier revision translated the world about a fixed centre instead, which kept
the planet centred and let the ship wander to the window edge. ``world_to_screen``
is kept pure so the mapping can be golden-tested without a surface involved.
"""

from __future__ import annotations

from typing import Tuple

ScreenPoint = Tuple[float, float]
WorldPoint = Tuple[float, float]


def world_to_screen(
    world_x: float, world_y: float, ship_position: WorldPoint, view_center: ScreenPoint
) -> ScreenPoint:
    """Map a planet-centred world coordinate to screen pixels.

    ``ship_position`` is the camera anchor (the player's world position) and
    ``view_center`` is where that anchor is drawn. The mapping is a translation
    by the offset between the point and the ship.
    """
    ship_x, ship_y = ship_position
    return (view_center[0] + (float(world_x) - ship_x),
            view_center[1] + (float(world_y) - ship_y))
