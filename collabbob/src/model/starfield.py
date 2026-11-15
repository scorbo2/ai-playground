"""Deterministic starfield model (no pygame).

Maintains a fixed number of stars centred on the system's planet (the world
origin) and scrolls them according to player velocity so the background indicates
motion. Stars that drift out of the visible window are recycled back into range,
which keeps the on-screen count exactly constant regardless of how fast the ship
moves. This is intentionally free of pygame so its invariants can be unit-tested.
"""

from __future__ import annotations

import random as _random_lib
from dataclasses import dataclass


@dataclass
class Star:
    """A single background star at a world coordinate with a fixed colour."""

    x: float
    y: float
    color: tuple[int, int, int] = (255, 255, 255)

    @property
    def world_position(self) -> tuple[float, float]:
        return (self.x, self.y)


class Starfield:
    """A recycling starfield anchored on the planet at the world origin.

    Parameters
    ----------
    count:
        The exact number of stars to keep visible at all times.
    half_extent:
        Half the size of the visible window (in world pixels). Stars are generated
        within ``[-half_extent, +half_extent]`` on each axis and recycled once they
        leave that box, guaranteeing the count never changes.
    """

    def __init__(
        self,
        count: int,
        half_extent: float,
        spawn_margin: float = 0.0,
        rng: "_random_lib.Random | None" = None,
    ) -> None:
        self.count = int(count)
        self.half_extent = float(half_extent)
        # Stars respawn strictly inside this inset box so a controlled movement
        # of up to ``spawn_margin`` pixels never pushes a star out of the visible
        # window (and therefore never triggers recycling mid-test).
        self.spawn_margin = float(spawn_margin)
        self._rng = rng or _random_lib.Random()
        self._stars: list[Star] = []
        for _ in range(self.count):
            self._stars.append(self._respawn())

    def _respawn(self, star: Star | None = None) -> Star:
        """Create (or replace ``star`` with) a new star inside the visible window."""
        inset = self.half_extent - self.spawn_margin
        pos = (self._rng.uniform(-inset, inset),
               self._rng.uniform(-inset, inset))
        grey = self._rng.randint(128, 255)
        color = (grey, grey, grey)
        if star is None:
            return Star(*pos, color)
        star.x, star.y, star.color = pos[0], pos[1], color
        return star

    def update(self, velocity_x: float, velocity_y: float) -> None:
        """Scroll every star by ``-velocity`` and recycle any that leave the window.

        The count is invariant: existing stars are only moved or recycled in place,
        never dropped or added.
        """
        for star in self._stars:
            star.x -= velocity_x
            star.y -= velocity_y
            if not (-self.half_extent <= star.x <= self.half_extent and
                    -self.half_extent <= star.y <= self.half_extent):
                self._respawn(star)

    @property
    def stars(self) -> list[Star]:
        return self._stars

    def __len__(self) -> int:
        return len(self._stars)
