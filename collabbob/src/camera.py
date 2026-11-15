"""Camera / world-to-screen mapping for the tactical view.

The tactical game view is centred on the system's planet, whose centre sits at
the world origin ``(0, 0)`` (see :mod:`src.model.game_state`). ``world_to_screen``
is a pure function that maps a world coordinate to a screen coordinate within the
tactical view by simply adding the view's screen-space centre. Keeping it pure
lets us golden-test the mapping without any pygame surface involved.
"""

from __future__ import annotations

from typing import Tuple

ScreenPoint = Tuple[float, float]


def world_to_screen(world_x: float, world_y: float, view_center: ScreenPoint) -> ScreenPoint:
    """Map a planet-centred world coordinate to screen pixels.

    ``view_center`` is the screen-space ``(x, y)`` of the tactical view's centre
    (the planet's position). Because world coordinates are offsets from that
    centre, the mapping is a plain translation.
    """
    return (view_center[0] + float(world_x), view_center[1] + float(world_y))
