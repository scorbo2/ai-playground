"""Visual effects: the starfield background and particle systems.

Purely cosmetic by design - nothing in this package takes part in collision
detection, never moves gameplay objects, and (per the spec) is removed
entirely from play on level advancement where applicable.
"""

from effects.particles import (
    Particle,
    spawn_destruction_explosion,
    spawn_mine_detonation,
    spawn_split_explosion,
    spawn_thruster_puffs,
    spawn_ufo_explosion,
)
from effects.starfield import Starfield

__all__ = [
    "Particle",
    "Starfield",
    "spawn_destruction_explosion",
    "spawn_mine_detonation",
    "spawn_split_explosion",
    "spawn_thruster_puffs",
    "spawn_ufo_explosion",
]
