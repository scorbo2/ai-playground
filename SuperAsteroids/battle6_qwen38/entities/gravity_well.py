"""Gravity well: a world-anchored singularity that drags hazards into a core.

The fifth weapon's world object (game_constants -> "gravity wells" carries the
rationale and every tunable). What the ENTITY owns:

  - its geometry: the invisible pull radius and the lethal crush core;
  - its lifetime clock (``expired`` flips when the game state should collapse
    it) and its spin phase (pure cosmetics, but the phase has to live here
    because the draw below is what consumes it);
  - the pull itself, expressed as a per-frame DELTA VELOCITY toward the core
    (``pull_toward``) and the collapse's outward push (``push_away``).

What it deliberately does NOT own: who gets pulled, what happens at the core,
and whether the craft survives any of it. That arbitration touches the shared
world lists and the score, so it lives in the game state - exactly the split
the shrapnel mine already uses.

The well keeps the screen position it was deployed at (no velocity, no
friction). It is only wrapped so a resize cannot strand it outside the new
window; the wrap margin is the CORE radius, like every other entity, so the
core always stays partly on screen. The faint field ring is wider than the
core and is simply clipped at the seam by pygame - cosmetic only, while the
PULL stays fully wrap-aware (torus distance), which is what the player
actually feels.
"""

import math
from typing import Dict

import pygame

from game_constants import (
    BLACK,
    GRAVITY_WELL_COLLAPSE_KICK,
    GRAVITY_WELL_CORE_OUTLINE_WIDTH,
    GRAVITY_WELL_CRAFT_PULL_FACTOR,
    GRAVITY_WELL_FIELD_RING_WIDTH,
    GRAVITY_WELL_INFALL_INTERVAL,
    GRAVITY_WELL_LEVEL_SPECS,
    GRAVITY_WELL_MIN_CRAFT_PULL,
    GRAVITY_WELL_STRENGTH_MIN,
    GRAVITY_WELL_SPIN_ARMS,
    GRAVITY_WELL_SPIN_ARC_DEGREES,
    GRAVITY_WELL_SPIN_DEGREES_PER_FRAME,
    MAX_WEAPON_POWER,
    WHITE,
)
from position_utils import shortest_delta, torus_distance, wrap_around

# The pull-radius ring, cached per (radius, color): one transparent disc
# outline per distinct well spec, reused for every well of that power level
# (wells are uncapped at power 4+, so re-drawing the ring each frame would
# churn the allocator for a shape that never changes).
_field_rings: Dict[tuple, pygame.Surface] = {}


def _field_ring(radius: int, color: tuple) -> pygame.Surface:
    key = (radius, color)
    ring = _field_rings.get(key)
    if ring is None:
        size = radius * 2 + 1
        ring = pygame.Surface((size, size), pygame.SRCALPHA)
        # Translucent so the field reads as a hint, never as a wall: the
        # ring is information ("how far the pull reaches"), not an object.
        # The fill is deliberately fainter than the rim - at level 5 this
        # disc is 300 px across and would otherwise fog half the screen.
        pygame.draw.circle(ring, (*color, 70), (radius, radius), radius,
                           width=GRAVITY_WELL_FIELD_RING_WIDTH)
        pygame.draw.circle(ring, (*color, 20), (radius, radius), radius)
        _field_rings[key] = ring
    return ring


class GravityWell:
    """One deployed singularity: pull field, crush core, lifetime."""

    def __init__(self, x: float, y: float, power_level: int):
        self.power_level = max(1, min(MAX_WEAPON_POWER, power_level))
        # Power level is captured at deployment (like a mine's), so an
        # already-open well keeps its own strength even if the player
        # switches weapons or powers up afterwards.
        (_cap, self.pull_radius, strength, self.core_radius,
         lifetime, self.color) = GRAVITY_WELL_LEVEL_SPECS[
            self.power_level - 1]
        # The floor is a trap-avoidance, not a buff: the player craft and the
        # mines both apply friction before moving, and both snap sub-stall
        # speeds to zero, so a strength under that threshold would silently do
        # NOTHING to them. Clamping here keeps a table-tweaking mistake from
        # turning into an invisible weapon.
        self.pull_strength = max(GRAVITY_WELL_STRENGTH_MIN, strength)
        self.x = float(x)
        self.y = float(y)
        self.frames_remaining = lifetime
        self._spin = 0.0
        self._age_frames = 0

    # ------------------------------------------------------------- simulation

    @property
    def expired(self) -> bool:
        """True once the game state should collapse it (the state owns the
        collapse: particles, SFX, and the outward eviction kick)."""
        return self.frames_remaining <= 0

    @property
    def infall_due(self) -> bool:
        """True on the first frame of each infall-puff cycle. The edge mirrors
        ``ShrapnelMine.pulse_onset``: the entity reports WHEN, the state
        decides whether anything (a particle, a sound) happens."""
        return self._age_frames % GRAVITY_WELL_INFALL_INTERVAL == 0

    def update(self, width: int, height: int) -> None:
        """Advance one frame: tick the lifetime, turn the vortex."""
        self.frames_remaining -= 1
        self._age_frames += 1
        self._spin = (self._spin + GRAVITY_WELL_SPIN_DEGREES_PER_FRAME) % 360.0
        self.x, self.y = wrap_around(self.x, self.y, self.core_radius,
                                     width, height)

    # ------------------------------------------------------------- collision

    def touching(self, cx: float, cy: float, radius: float,
                 width: int, height: int) -> bool:
        """Wrap-aware contact with the crush core (the lethal part)."""
        return (torus_distance(self.x, self.y, cx, cy, width, height)
                <= self.core_radius + radius)

    def within_pull_radius(self, cx: float, cy: float, radius: float,
                           width: int, height: int) -> bool:
        """Wrap-aware test against the invisible field edge."""
        return (torus_distance(self.x, self.y, cx, cy, width, height)
                <= self.pull_radius + radius)

    def pull_toward(self, cx: float, cy: float, width: int, height: int,
                    strength_scale: float = 1.0) -> tuple:
        """(dvx, dvy) to add to an object's velocity this frame: the well's
        pull strength aimed from (cx, cy) at the core along the SHORTEST
        wrap-aware path. A coincident object gets nothing (no direction to
        fall in - and it is at the core already, so the core resolves it)."""
        dx = shortest_delta(self.x - cx, width)
        dy = shortest_delta(self.y - cy, height)
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            return (0.0, 0.0)
        strength = self.pull_strength * strength_scale
        return (dx / length * strength, dy / length * strength)

    def craft_pull_toward(self, cx: float, cy: float, width: int,
                          height: int) -> tuple:
        """(dvx, dvy) as applied to the PLAYER's craft: the well's strength
        scaled down by GRAVITY_WELL_CRAFT_PULL_FACTOR, but never below
        GRAVITY_WELL_MIN_CRAFT_PULL (see game_constants: under the craft's
        stall threshold a pull is not weak, it is nonexistent).
        """
        scale = GRAVITY_WELL_CRAFT_PULL_FACTOR
        if self.pull_strength * scale < GRAVITY_WELL_MIN_CRAFT_PULL:
            scale = GRAVITY_WELL_MIN_CRAFT_PULL / self.pull_strength
        return self.pull_toward(cx, cy, width, height, scale)

    def push_away(self, cx: float, cy: float, width: int, height: int,
                  kick: float = GRAVITY_WELL_COLLAPSE_KICK) -> tuple:
        """(dvx, dvy) for the collapse kick: straight OUTWARD from the core,
        strongest at the core and fading linearly to nothing at the field
        edge, so escaping the field is always free."""
        dx = shortest_delta(cx - self.x, width)
        dy = shortest_delta(cy - self.y, height)
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            return (0.0, 0.0)
        falloff = max(0.0, 1.0 - length / self.pull_radius)
        return (dx / length * kick * falloff, dy / length * kick * falloff)

    # ------------------------------------------------------------------ draw

    def draw(self, screen: pygame.Surface) -> None:
        cx, cy = int(round(self.x)), int(round(self.y))
        screen.blit(_field_ring(self.pull_radius, self.color),
                    _field_ring(self.pull_radius, self.color).get_rect(
                        center=(cx, cy)))
        # Spinning arms: they show the field is ACTIVE and which way it is
        # turning, and their speed reads as strength at a glance.
        arm_radius = int(self.core_radius * 1.9)
        rect = pygame.Rect(0, 0, arm_radius * 2, arm_radius * 2)
        rect.center = (cx, cy)
        for arm in range(GRAVITY_WELL_SPIN_ARMS):
            start = math.radians(self._spin
                                 + arm * (360.0 / GRAVITY_WELL_SPIN_ARMS))
            stop = start + math.radians(GRAVITY_WELL_SPIN_ARC_DEGREES)
            pygame.draw.arc(screen, self.color, rect, start, stop,
                            GRAVITY_WELL_CORE_OUTLINE_WIDTH)
        # The hole itself: black disc, colored rim, white outline.
        pygame.draw.circle(screen, BLACK, (cx, cy), self.core_radius)
        pygame.draw.circle(screen, self.color, (cx, cy), self.core_radius,
                           width=GRAVITY_WELL_CORE_OUTLINE_WIDTH)
        pygame.draw.circle(screen, WHITE, (cx, cy), self.core_radius + 1,
                           width=1)
