"""Weapon timing and the record of a shot being fired (Stage 10).

Three pieces of vocabulary that both the NPC AI (Stage 10) and the projectile
simulation (Stage 11) need, kept in one place so neither side invents its own:

* :func:`weapon_cooldown_frames` — how long a weapon takes to cycle, given a
  fire rate expressed in shots per second at the fixed 60 FPS timestep.
* :class:`Shot` — what a ship decided to do when it pulled the trigger: the
  muzzle position, the aim direction, and everything the projectile needs. Stage
  10 produces shots (the AI owns *when* and *where* a gun fires); Stage 11 turns
  them into travelling projectiles and applies the damage. Keeping the request
  as a value object means the AI never has to know that projectiles exist.
* :class:`WeaponClock` — the fire-rate gate itself, so the player's gun and an
  NPC's gun cannot disagree about what ``weapon_fire_rate`` means, and no hull
  ends up owning two cooldown clocks.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional

from src.model.factions import require_combatant
from src.model.physics import Vec2, normalise

# Frames in the game's fixed timestep. The spec's fire rates are "per second
# (per 60 frames at 60FPS)", so the conversion is pinned here rather than at
# each call site.
FRAMES_PER_SECOND = 60.0


def weapon_cooldown_frames(
    fire_rate_per_second: float, frames_per_second: float = FRAMES_PER_SECOND
) -> float:
    """Frames a weapon must wait between shots.

    A fire rate of 1 gives 60 frames, 2 gives 30, 0.5 gives 120. A non-positive
    rate returns infinity rather than raising: a disabled weapon is a thing the
    AI can check (``weapon_ready`` is simply never true), whereas a raise would
    turn a bad config value into a crash mid-dogfight. The config loader is the
    place that rejects nonsense.
    """
    if fire_rate_per_second <= 0.0:
        return float("inf")
    return frames_per_second / float(fire_rate_per_second)


@dataclass(frozen=True)
class Shot:
    """A weapon discharge produced by a ship on one fixed timestep.

    ``direction`` already carries the AI's aim jitter, and ``ship_velocity`` is
    kept so the muzzle velocity can be composed the way the spec defines it for
    the player's gun ("ship velocity plus 8 px/frame in the facing direction") —
    the same rule for every hull, which is why it lives on the shot rather than
    in the AI.

    ``owner`` is the ship that fired. Stage 11 needs it for two rules that cannot
    be evaluated without an identity: a projectile passes harmlessly through its
    own ship, and only *player* projectiles earn a bounty.

    ``faction`` is really a **combatant** id: one of the three NPC factions, or
    :data:`~src.model.factions.FACTION_PLAYER` when the shot came from the
    player's own trigger. The name is kept because every NPC shot's faction *is*
    its owner's faction (``shot.faction == shot.owner.faction``), and the one
    exception is spelled out here rather than renamed into a second field that
    could disagree with the first.
    """

    faction: str
    owner: object
    origin: Vec2
    direction: Vec2
    ship_velocity: Vec2
    weapon_power: float
    weapon_range: float

    def __post_init__(self) -> None:
        require_combatant(self.faction)
        object.__setattr__(self, "direction", normalise(self.direction))

    def muzzle_velocity(self, projectile_speed_bonus: float) -> Vec2:
        """Projectile launch velocity: ship velocity + bonus along ``direction``.

        The bonus is ``combat.projectile_speed_bonus`` from config, handed in by
        the caller (Stage 11) because a shot does not carry a config dict.
        """
        bonus = max(0.0, float(projectile_speed_bonus))
        return (
            self.ship_velocity[0] + self.direction[0] * bonus,
            self.ship_velocity[1] + self.direction[1] * bonus,
        )

    def is_owner(self, ship: object) -> bool:
        """Whether ``ship`` fired this shot (identity, not equality).

        Ships are mutable and compared by identity everywhere else in the game,
        so an identity test is the only correct version of this question.
        """
        return self.owner is ship


def aim_is_within(actual: Vec2, intended: Vec2, tolerance_degrees: float) -> bool:
    """Whether two aim vectors are within ``tolerance_degrees`` of each other.

    A test/telemetry helper rather than gameplay logic: the jitter is drawn
    uniformly inside the tolerance, and this is how a test checks the draw
    landed inside the cone instead of eyeballing a scatter of vectors.
    """
    import math

    first = normalise(actual)
    second = normalise(intended)
    if first == (0.0, 0.0) or second == (0.0, 0.0):
        return True
    dot = max(-1.0, min(1.0, first[0] * second[0] + first[1] * second[1]))
    return math.degrees(math.acos(dot)) <= tolerance_degrees + 1e-9


@dataclass
class WeaponClock:
    """The countdown one gun keeps between shots (Stage 11).

    Stage 10 put this clock inside :class:`~src.model.npc_ship.NpcShip`. Stage 11
    gives the player a gun, and a second implementation of "is it ready yet?" is
    how one difficulty ends up with two fire rates. One clock, two hulls: the NPC
    gun and the player's, both ticking on the same fixed timestep.

    Deliberately *not* given the weapon's power, range or rate. The player's stats
    are mutated by spaceport upgrades, so a clock holding a copy of any of them
    would be a stale snapshot of a number that is still changing — the cycle length
    is handed over at the moment of firing, from whichever stat block is live.
    """

    frames_until_ready: float = 0.0

    @property
    def ready(self) -> bool:
        """Whether the gun may speak this frame."""
        return self.frames_until_ready <= 0.0

    def advance_frame(self) -> None:
        """Consume one fixed timestep."""
        self.frames_until_ready = max(0.0, self.frames_until_ready - 1.0)

    def pull(self, cooldown_frames: float) -> bool:
        """Whether the trigger may be pulled now; pulling it starts the next cycle.

        A gun that is still cycling answers ``False`` and changes nothing, which
        is the spec's "pressing space while the weapon is reloading does nothing"
        — silence, not a queued shot and not a message. Holding the trigger is
        therefore the correct way to shoot: the rate this clock enforces is what
        turns a held key into exactly ``fire_rate`` shots per second.

        ``cooldown_frames`` of infinity (a non-positive fire rate) means the gun is
        disabled, and a disabled gun has no free first shot hiding in it: it answers
        ``False`` and stays that way, which is what lets the AI check readiness
        rather than crash on a bad config value.
        """
        if not math.isfinite(cooldown_frames):
            self.frames_until_ready = cooldown_frames
            return False
        if not self.ready:
            return False
        self.frames_until_ready = float(cooldown_frames)
        return True
