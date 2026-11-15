"""The hyperspace jump: eligibility rules, timing, and arrival (Stage 8).

Everything here is pure logic (no pygame), so the sequence can be driven frame
by frame in a test and checked exactly.

Three phases, in order:

1. ``PHASE_BURN`` — the three seconds of stupidly high acceleration the spec
   asks for. The ship burns along its heading with no top-speed cap and no
   boundary clamp. Input is locked and the jump cannot be cancelled.
2. ``PHASE_TRANSITION`` — the white-out. The screen goes solid white, a
   thunderclap fires, and **the world swap happens under the white**: new
   system, new starfield, new spawn point, shields refilled, velocity zeroed.
   The spec only asks for the acceleration animation; the white-out is the
   part that makes the arrival land, because a discontinuity nobody can see
   is not a bug, it is a cut scene. See the Stage 8 entry in DECISIONS.md.
3. ``PHASE_IDLE`` — input unlocked, no destination selected, HUD nav unbolded.

The *mechanism* of the burn (uncapped thrust, boundary exemption) lives in
:class:`~src.model.game_state.GameState`; this module owns the *policy*: how
long, how far, whether it is legal at all, and what happens on arrival. That
split is why :class:`JumpController` drives the model instead of duplicating
its integration maths.
"""

from __future__ import annotations

import math
import random as _random_lib
from dataclasses import dataclass
from typing import Optional, Tuple

from src.model.game_state import PLANET_WORLD_POSITION

# ---------------------------------------------------------------------------
# Phases
# ---------------------------------------------------------------------------
PHASE_IDLE = "idle"
PHASE_BURN = "burn"
PHASE_TRANSITION = "transition"

# ---------------------------------------------------------------------------
# Blockers: why a jump request was refused. Codes are stable strings so the
# scene, the tests, and Stage 13's game-over hook can all name them.
# ---------------------------------------------------------------------------
BLOCKED_NONE = ""
BLOCKED_ALREADY_JUMPING = "already_jumping"
BLOCKED_NO_DESTINATION = "no_destination"
BLOCKED_INVALID_DESTINATION = "invalid_destination"
BLOCKED_IN_LANDING_RANGE = "in_landing_range"
BLOCKED_INSUFFICIENT_FUEL = "insufficient_fuel"
# Spec special case: J with *exactly* the jump's fuel cost is an immediate game
# over, not a jump. Stage 13 owns the game-over screen; Stage 8 only guarantees
# the jump does not happen and the fuel is not spent. See DECISIONS.md.
BLOCKED_EXACT_FUEL = "exact_fuel"

# Feedback copy. The spec asks for "visible feedback" on the fuel check, so the
# blockers that a player can actually cause carry a message; the ones that
# cannot happen through legal play (or that the spec says must be silent) do
# not. Kept next to the codes rather than in the scene so the rules and their
# explanation can never drift apart.
BLOCKER_MESSAGES = {
    BLOCKED_NONE: "",
    # "If no system is selected, J does nothing" — deliberately silent.
    BLOCKED_ALREADY_JUMPING: "",
    BLOCKED_NO_DESTINATION: "",
    BLOCKED_INVALID_DESTINATION: "",
    BLOCKED_IN_LANDING_RANGE: "Cannot jump this close to the planet",
    BLOCKED_INSUFFICIENT_FUEL: "insufficient fuel",
    # Stage 13 replaces this with the game-over screen, so no banner.
    BLOCKED_EXACT_FUEL: "",
}

# ---------------------------------------------------------------------------
# Events emitted by JumpController.advance() at phase boundaries. Stage 10
# listens for EVENT_ARRIVED to despawn the system's NPCs; Stage 12 hooks the
# audio through EVENT_TRANSITION_STARTED. There is deliberately no
# "jump started" event: the request path already knows it started, and an event
# nobody consumes is a second, drift-prone way to say the same thing.
# ---------------------------------------------------------------------------
EVENT_TRANSITION_STARTED = "transition_started"
EVENT_ARRIVED = "arrived"
EVENT_JUMP_ENDED = "jump_ended"

# Fraction of the transition that it takes the flash to reach full white. The
# world swap happens on the frame the flash saturates, so presentation and
# model share exactly one timing source: :func:`blind_frames_for`.
BLIND_FRACTION = 0.2


def blind_frames_for(transition_frames: int) -> int:
    """Frames of burn-free whiteout before the world swap (flash ramp-up).

    Never zero: a transition of one or two frames still has to swap the world
    under cover of the flash, or the player watches the universe teleport.
    """
    return max(1, int(round(transition_frames * BLIND_FRACTION)))


@dataclass(frozen=True)
class JumpParams:
    """Jump tunables, hoisted out of ``tactical.jump`` once per game."""

    fuel_cost: float
    frames: int
    acceleration: float
    transition_frames: int
    spawn_min_distance: float
    spawn_max_distance: float

    @classmethod
    def from_config(cls, tactical: dict) -> "JumpParams":
        """Build from the ``tactical`` config section.

        The loader already rejects a malformed ``spawn_distance`` pair; the
        check here exists because this class is also built directly by tests
        and tooling that never went through the loader.
        """
        jump = tactical["jump"]
        spawn_pair = jump["spawn_distance"]
        if len(spawn_pair) != 2:
            raise ValueError(
                "tactical.jump.spawn_distance must be [min, max]; "
                f"got {spawn_pair!r}"
            )
        return cls(
            fuel_cost=float(jump["fuel_cost"]),
            frames=int(jump["frames"]),
            acceleration=float(jump["acceleration"]),
            transition_frames=int(jump["transition_frames"]),
            spawn_min_distance=float(spawn_pair[0]),
            spawn_max_distance=float(spawn_pair[1]),
        )


@dataclass(frozen=True)
class JumpOutcome:
    """Result of a jump *request*: did it start, and if not, why."""

    started: bool = False
    blocker: str = BLOCKED_NONE
    message: str = ""


@dataclass(frozen=True)
class JumpEvent:
    """A phase boundary crossed by :meth:`JumpController.advance`."""

    kind: str
    system: Optional[str] = None


@dataclass(frozen=True)
class JumpPresentation:
    """What the renderer needs to know about the jump, and nothing else.

    The tactical view and the HUD both read this instead of reaching into the
    controller, so presentation can never start making gameplay decisions.
    """

    phase: str = PHASE_IDLE
    progress: float = 0.0

    @property
    def in_hyperspace(self) -> bool:
        return self.phase != PHASE_IDLE

    @property
    def ship_visible(self) -> bool:
        """Hidden only while the flash is opaque — not for the whole fade.

        Hiding the ship for the entire white-out makes it *pop* into existence on
        the last frame. The fade is the arrival being revealed, and the player is
        part of that arrival, so the ship comes back as soon as the veil starts
        thinning (still behind a fully opaque flash for the hold frames, so this
        can never show a half-drawn ship).
        """
        if self.phase != PHASE_TRANSITION:
            return True
        return self.progress > BLIND_FRACTION


def spawn_position(
    rng: "_random_lib.Random",
    min_distance: float,
    max_distance: float,
    planet_position: Tuple[float, float] = PLANET_WORLD_POSITION,
) -> Tuple[float, float]:
    """A planet-centred world coordinate to arrive at, never near the planet.

    The spec is explicit that entering a system must never drop the player next
    to the planet: they have to fly to it. The distance is uniform in
    ``[min_distance, max_distance]`` and the bearing uniform in all directions,
    which keeps every arrival bearing possible (a fixed set of bearings would
    make the same corner of every system feel like "the entrance").

    A uniform *distance* is not a uniform *area* (outer rings are sparser), and
    that is fine: the constraint the config expresses is a distance band.
    """
    if max_distance < min_distance:
        raise ValueError(
            f"spawn distance band is inverted: {min_distance} > {max_distance}"
        )
    distance = rng.uniform(min_distance, max_distance)
    bearing = rng.uniform(0.0, math.tau)
    return (
        planet_position[0] + distance * math.cos(bearing),
        planet_position[1] + distance * math.sin(bearing),
    )


class JumpController:
    """Owns the jump sequence: may we go, how long it takes, what arrives.

    One controller per game session, handed the same :class:`GameState` the
    tactical view simulates and the session's :class:`SystemMapState`.
    """

    def __init__(
        self,
        game_state,
        map_state,
        params: JumpParams,
        rng: "_random_lib.Random | None" = None,
    ) -> None:
        if game_state is None or map_state is None:
            raise ValueError("JumpController needs both the GameState and the SystemMapState")
        self.game_state = game_state
        self.map_state = map_state
        self.params = params
        # Arrival placement is a *gameplay* draw, so it comes from the game's
        # RNG by default — not the separate world-seed RNG that built the
        # graph. One RNG per concern keeps the map reproducible no matter how
        # many jumps the player burns through first.
        self.rng = rng or game_state.rng

        self.phase: str = PHASE_IDLE
        self.destination: Optional[str] = None
        self._frames_total = 0
        self._frames_elapsed = 0

    # ------------------------------------------------------------------
    # State queries
    # ------------------------------------------------------------------
    @property
    def is_active(self) -> bool:
        return self.phase != PHASE_IDLE

    @property
    def transition_frames_elapsed(self) -> int:
        """1-based frame index inside the white-out (0 when not transitioning)."""
        return self._frames_elapsed if self.phase == PHASE_TRANSITION else 0

    def presentation(self) -> JumpPresentation:
        """Phase plus 0..1 progress of the current phase (for effects ramps)."""
        if self.phase == PHASE_IDLE:
            return JumpPresentation()
        elapsed, total = self._phase_progress()
        if total <= 0:
            return JumpPresentation(phase=self.phase)
        return JumpPresentation(phase=self.phase, progress=min(1.0, elapsed / total))

    def _phase_progress(self) -> tuple[int, int]:
        """(elapsed, total) for the current phase, from the right authority.

        The burn's clock is the model's (frames actually accelerated); the
        white-out's clock is the controller's (the ship is not moving under it).
        """
        if self.phase == PHASE_BURN:
            return (self.game_state.jump_frames, self.params.frames)
        return (self._frames_elapsed, self._frames_total)

    # ------------------------------------------------------------------
    # Eligibility
    # ------------------------------------------------------------------
    def blocker(self) -> str:
        """Why a jump is illegal right now, or ``BLOCKED_NONE``.

        **The check order is load-bearing.** The exact-fuel rule is a *game
        over*, so it must never fire for a jump that was already illegal for a
        different reason — a player parked inside landing range with exactly
        250 fuel must be told about the planet, not killed for the fuel. The
        fuel checks therefore come last, after every "you may not attempt this
        at all" rule.
        """
        if self.is_active:
            return BLOCKED_ALREADY_JUMPING

        destination = self.map_state.selected_system
        if destination is None:
            return BLOCKED_NO_DESTINATION
        # Defensive: the map's own rules should make a selection legal, but a
        # destination set programmatically (a future save-game or a scripted
        # test) could point anywhere in the graph.
        if not self.map_state.can_select(destination):
            return BLOCKED_INVALID_DESTINATION
        if self.game_state.in_landing_range(PLANET_WORLD_POSITION):
            return BLOCKED_IN_LANDING_RANGE

        fuel = self.game_state.fuel
        if fuel < self.params.fuel_cost:
            return BLOCKED_INSUFFICIENT_FUEL
        if fuel == self.params.fuel_cost:
            return BLOCKED_EXACT_FUEL
        return BLOCKED_NONE

    def request(self) -> JumpOutcome:
        """Start the jump if it is legal, deducting the fuel exactly once.

        Fuel is taken at the *start*, per the spec — a jump is not refundable,
        and the player is not immune to damage during the burn.
        """
        blocker = self.blocker()
        if blocker != BLOCKED_NONE:
            return JumpOutcome(
                started=False,
                blocker=blocker,
                message=BLOCKER_MESSAGES.get(blocker, ""),
            )

        self.destination = self.map_state.selected_system
        self.game_state.spend_fuel(self.params.fuel_cost)
        self.game_state.begin_jump(self.params.acceleration)
        self._enter_phase(PHASE_BURN, self.params.frames)
        return JumpOutcome(started=True)

    # ------------------------------------------------------------------
    # Sequencing
    # ------------------------------------------------------------------
    def advance(self) -> Optional[JumpEvent]:
        """Advance the sequence by one fixed timestep.

        Returns a :class:`JumpEvent` when a phase boundary was crossed on this
        frame, else ``None``. Callers react to the events (flash, thunderclap,
        NPC despawn) instead of polling phase changes.
        """
        if self.phase == PHASE_IDLE:
            return None

        self._frames_elapsed += 1

        if self.phase == PHASE_BURN:
            # The burn is measured in frames the ship actually accelerated on,
            # not in frames the controller has been alive: the timestep on which
            # J was pressed has already stepped the simulation before the jump
            # begins, so a controller-side counter would deliver 179 frames of
            # a "180 frame" animation. The model keeps that count; this class
            # only decides what the target is.
            if self.game_state.jump_frames < self.params.frames:
                return None
            # The burn ends and the screen starts going white on this frame.
            # Cutting the burn here (rather than zeroing velocity) leaves the
            # ship coasting at its terminal jump speed through the white-out:
            # a body in motion stays in motion, and the player cannot see it
            # either way.
            self.game_state.set_jump_acceleration(0.0)
            self._enter_phase(PHASE_TRANSITION, self.params.transition_frames)
            return JumpEvent(EVENT_TRANSITION_STARTED, system=self.destination)

        # PHASE_TRANSITION: the world swap happens the instant the flash is
        # fully opaque, so the cut is invisible.
        if self._frames_elapsed == blind_frames_for(self._frames_total):
            self._complete_arrival()
            return JumpEvent(EVENT_ARRIVED, system=self.destination)

        if self._frames_elapsed < self._frames_total:
            return None

        arrived_in = self.destination
        self.destination = None
        self.phase = PHASE_IDLE
        self._frames_total = 0
        self._frames_elapsed = 0
        self.game_state.end_jump()
        return JumpEvent(EVENT_JUMP_ENDED, system=arrived_in)

    def _enter_phase(self, phase: str, frames: int) -> None:
        """Start a phase.

        The frame a phase starts on *is* its first frame: the flash begins
        drawing on the same frame the transition phase begins, so both counters
        start at 1 and stay in lockstep without either side compensating.
        """
        self.phase = phase
        self._frames_total = int(frames)
        self._frames_elapsed = 1

    def _complete_arrival(self) -> None:
        """Swap in the destination system under cover of the flash."""
        destination = self.destination
        if destination is None:  # pragma: no cover - advance() guards this
            return
        # Reveal-on-arrival, current-system bookkeeping, and clearing the
        # selection all belong to the map state; a jump consumes its
        # destination, so there is never a selection after one.
        self.map_state.arrive(destination)

        x, y = spawn_position(
            self.rng, self.params.spawn_min_distance, self.params.spawn_max_distance
        )
        self.game_state.arrive_in_system(x, y)
