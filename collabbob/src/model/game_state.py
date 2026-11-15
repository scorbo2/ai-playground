"""Pure tactical model core (no pygame).

This module owns everything that simulates the player's ship in tactical mode:
position, velocity, heading, fuel and the input-driven control logic
(thrusting, rotating, and the reverse-course 180-degree flip). It is deliberately
free of any pygame dependency so it can be unit-tested deterministically under
the dummy SDL drivers.

Coordinate convention (finalised here, used by Stage 4): world coordinates are
centred on the system's planet, whose centre sits at ``(0, 0)``. Positions and
velocities are therefore offsets from the planet. The system boundary is a square
spanning ``[-system_pixel_size / 2, +system_pixel_size / 2]`` on each axis.

Heading convention: the tactical view is drawn on a screen whose y axis points
*down*, so heading 0 faces east and heading 90 faces south; increasing heading
therefore rotates the ship clockwise on screen. "Left" must *decrease* the
heading (counter-clockwise), and the ship sprite is rotated by ``-heading``
because ``pygame.transform.rotate`` takes positive-contrary-to-our-convention.
"""

from __future__ import annotations

import math
import random as _random_lib
from dataclasses import dataclass

from src.model.stats import ShipStats, ship_stats_from_config


@dataclass(frozen=True)
class InputFrame:
    """A single frame of discrete user input for the tactical controls.

    ``thrust``, ``left`` and ``right`` are *level* signals: they describe whether
    a key is currently held down. ``reverse_edge`` is an *edge* signal describing
    whether the reverse-course key was pressed (not merely held) during this frame.
    """

    thrust: bool = False
    left: bool = False
    right: bool = False
    reverse_edge: bool = False


class _ReverseState:
    IDLE = "idle"
    REVERSING = "reversing"


class GameState:
    """Deterministic tactical state for the player's ship.

    Construct one per new game and hand it to the input layer / simulation loop.
    Feed discrete input with :meth:`feed_input`, then call :meth:`advance_frame`
    once per fixed timestep. An injectable ``random.Random`` instance may be passed
    in for any randomness; by default a fresh RNG is created.
    """

    def __init__(self, configs: dict, rng: "random.Random | None" = None) -> None:
        self.rng = rng or _random_lib.Random()
        # Starting stats are fixed for the whole game; combat uses these.
        self.stats = ship_stats_from_config(configs["player_ship"])
        # Fuel burn is a tactical-mode concern, not a ship stat.
        self.fuel_burn_per_frame: float = float(
            configs["tactical"]["fuel_burn_per_frame"]
        )
        self.system_pixel_size: float = float(
            configs["tactical"]["system_pixel_size"]
        )
        self.landing_range: float = float(configs["tactical"]["landing_range"])

        # World state (planet-centred coordinates).
        self._position: tuple[float, float] = (0.0, 0.0)
        self._velocity: tuple[float, float] = (0.0, 0.0)
        self.heading: float = 0.0  # facing direction in degrees

        self._fuel: float = float(configs["player_ship"]["fuel_capacity"])
        self._input: InputFrame = InputFrame()

        # Reverse-course state machine bookkeeping.
        self._reverse_state: str = _ReverseState.IDLE
        self._reverse_start: float = 0.0
        self._boundary_reached_this_frame: bool = False

    # ------------------------------------------------------------------
    # Read-only accessors
    # ------------------------------------------------------------------
    @property
    def position(self) -> tuple[float, float]:
        return self._position

    @property
    def velocity(self) -> tuple[float, float]:
        return self._velocity

    @property
    def heading_degrees(self) -> float:
        """Heading normalised into ``[0, 360)`` degrees."""
        return self.heading % 360.0

    @heading_degrees.setter
    def heading_degrees(self, value: float) -> None:
        self.heading = value % 360.0

    @property
    def fuel(self) -> float:
        return self._fuel

    @fuel.setter
    def fuel(self, value: float) -> None:
        self._fuel = max(0.0, float(value))

    def set_position(self, x: float, y: float) -> None:
        """Place the ship at world coordinates (used when entering a system)."""
        self._position = (float(x), float(y))

    @property
    def reverse_state(self) -> str:
        return self._reverse_state

    # ------------------------------------------------------------------
    # Input + simulation
    # ------------------------------------------------------------------
    def feed_input(
        self,
        thrust: bool = False,
        left: bool = False,
        right: bool = False,
        reverse_edge: bool = False,
    ) -> None:
        """Record the input for the current frame."""
        self._input = InputFrame(
            thrust=thrust, left=left, right=right, reverse_edge=reverse_edge
        )

    def advance_frame(self) -> None:
        """Advance the simulation by exactly one fixed timestep (1/60 s)."""
        if self._input.reverse_edge:
            self._begin_reverse_course()

        self._advance_reverse_course()

        # Continuous rotation from held arrows is disabled while flipping.
        if self._reverse_state != _ReverseState.REVERSING:
            self._apply_continuous_rotation()

        if self._input.thrust:
            self._apply_thrust()
            self._consume_fuel()

        self._integrate_position()

    # ------------------------------------------------------------------
    # Control logic
    # ------------------------------------------------------------------
    def _begin_reverse_course(self) -> None:
        """Edge-triggered start (or restart) of a 180-degree flip.

        Pressing reverse while idle begins a fresh flip from the current heading.
        Pressing it again mid-flip restarts the flip from wherever the ship is now
        heading, beginning a new 180-degree rotation from that facing direction.
        """
        self._reverse_start = self.heading
        self._reverse_state = _ReverseState.REVERSING

    def _apply_continuous_rotation(self) -> None:
        """Rotate steadily while the left/right arrows are held.

        Left is counter-clockwise on screen, which in this y-down convention
        means *decreasing* heading; right is the mirror image.
        """
        rate = self.stats.turn_rate_deg_per_sec / 60.0  # deg per frame @ fixed 60FPS
        if self._input.left:
            self.heading -= rate
        elif self._input.right:
            self.heading += rate

    def _advance_reverse_course(self) -> None:
        """Rotate one step toward the 180-degree flip target, if reversing."""
        if self._reverse_state != _ReverseState.REVERSING:
            return
        rate = self.stats.turn_rate_deg_per_sec / 60.0
        target = (self._reverse_start + 180.0) % 360.0
        remaining = (target - self.heading) % 360.0
        if remaining <= rate + 1e-9:
            # Reached (or would overshoot); land exactly on the target heading.
            self.heading = target
            self._reverse_state = _ReverseState.IDLE
        else:
            self.heading += rate

    def _apply_thrust(self) -> None:
        """Apply acceleration toward ``top_speed`` in the facing direction."""
        accel = self.stats.acceleration_rate
        vx, vy = self._velocity
        speed = math.hypot(vx, vy)
        if speed >= self.stats.top_speed:
            return  # already capped; adding would only introduce float wobble

        ax = accel * math.cos(math.radians(self.heading))
        ay = accel * math.sin(math.radians(self.heading))
        new_vx = vx + ax
        new_vy = vy + ay
        new_speed = math.hypot(new_vx, new_vy)
        if new_speed > self.stats.top_speed:
            # Rescale so the speed lands exactly on top_speed rather than
            # overshooting it by a hair.
            scale = self.stats.top_speed / new_speed
            self._velocity = (new_vx * scale, new_vy * scale)
        else:
            self._velocity = (new_vx, new_vy)

    def _consume_fuel(self) -> None:
        """Burn fuel for one frame of thrusting; never below zero."""
        self.fuel -= self.fuel_burn_per_frame
        if self.fuel < 0.0:
            self.fuel = 0.0

    def _integrate_position(self) -> None:
        """Newtonian drift: position advances by the current velocity."""
        self._position = (
            self._position[0] + self._velocity[0],
            self._position[1] + self._velocity[1],
        )

    # ------------------------------------------------------------------
    # Convenience geometry helpers (used later by tactical/HUD code)
    # ------------------------------------------------------------------
    def facing_vector(self) -> tuple[float, float]:
        """Unit vector pointing in the ship's current facing direction."""
        return (math.cos(math.radians(self.heading)), math.sin(math.radians(self.heading)))

    def distance_from_point(self, x: float, y: float) -> float:
        """Euclidean distance from the ship to a world coordinate."""
        dx = self._position[0] - x
        dy = self._position[1] - y
        return math.hypot(dx, dy)

    def in_landing_range(self, planet_position: tuple[float, float]) -> bool:
        """True when the ship is within ``landing_range`` of the planet centre."""
        half = self.distance_from_point(planet_position[0], planet_position[1])
        return half <= self.landing_range

    def on_boundary(self) -> bool:
        """True when the ship has touched any edge of the system square."""
        half = self.system_pixel_size / 2.0
        return (
            self._position[0] <= -half
            or self._position[0] >= half
            or self._position[1] <= -half
            or self._position[1] >= half
        )

    def boundary_reached_this_frame(self) -> bool:
        return self._boundary_reached_this_frame
