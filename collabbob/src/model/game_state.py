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
from src.model.economy import (
    CarriedLoad,
    EconomyRules,
    LandingReport,
    Mission,
    PortTransaction,
    format_credits,
    pluralise,
)
from src.model.ship_upgrades import (
    UPGRADE_LABELS,
    UPGRADE_TYPES,
    UpgradeOffer,
    apply_upgrade,
    upgrade_cost,
    upgrade_step_for,
)

# Every system's planet sits at the world origin; see the module docstring for
# the coordinate convention. Shared with the tactical view so the view and the
# jump rules cannot disagree about where the ground is.
PLANET_WORLD_POSITION = (0.0, 0.0)

# No purchase may take the balance to this value or below. The spec's Stage 9
# gate is "no purchase path producing credits <= 0", so affordability is checked
# against the *resulting* balance rather than the price: a purchase that would
# leave the player with exactly 0 credits is refused even though they could
# "afford" it. See DECISIONS.md — this also means a player at exactly 0 credits
# can never be talked into a negative balance by any port service.
CREDIT_FLOOR = 0.0

# Tolerance for "the tank (or the hull) is already full" comparisons. Fuel and
# armour are floats that have been subtracted from floats; a residual of 1e-9
# should read as full, not as a purchasable sliver.
_FULL_EPSILON = 1e-9


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
        # Stage 9 economy surface. Every money tunable is hoisted into one
        # frozen rules object so the port code never reaches into a config dict,
        # and the per-stat upgrade magnitudes stay where the loader validated
        # them (the view asks for them through :attr:`upgrade_steps`).
        self.economy = EconomyRules.from_config(configs["economy"])
        # Re-keyed by stat name (not by config key) so the port code and the
        # purchase path both index the same mapping with the same name: "weapons"
        # is a stat, "weapon_damage" is a config key, and mixing the two is how a
        # KeyError reaches a spaceport screen at draw time.
        self._upgrade_steps = {
            stat: upgrade_step_for(configs["upgrade_steps"], stat)
            for stat in UPGRADE_TYPES
        }
        self._credits: float = float(configs["new_game"]["starting_credits"])
        self._carried: list[CarriedLoad] = []
        self._accepted_offers: set[tuple[int, int]] = set()
        self._upgrade_levels: dict[str, int] = {name: 0 for name in UPGRADE_TYPES}
        # Port visits are numbered so that an offer can never be accepted twice,
        # not even across two visits to the same system (see accept_mission).
        self._port_visit_serial: int = 0

        # Post-spaceport state: while landed the ship takes no damage and cannot
        # be steered; on launch a grace period of immunity begins (the spec's
        # "immune for N frames after leaving spaceport"), counted in frames so it
        # ticks with the fixed timestep rather than with wall-clock time.
        self.launch_immunity_frames: int = int(
            configs["tactical"]["launch_immunity_frames"]
        )
        self._landed: bool = False
        self._launch_immunity_frames: int = 0

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

        # Jump plumbing. This model owns the *mechanism* of a jump (uncapped
        # thrust along the heading, exemption from the system boundary); the
        # timing and the eligibility rules live in src.model.jump.
        self._jumping: bool = False
        self._jump_acceleration: float = 0.0
        # Burn frames actually integrated. Counted here because this is the
        # only object that knows whether a fixed timestep really burned fuel-less
        # hyperspace thrust; the jump sequence asks for a count, it does not
        # guess one. See src/model/jump.py.
        self._jump_frames: int = 0

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

    def spend_fuel(self, amount: float) -> None:
        """Pay a one-off fuel cost (a jump, per the spec: charged up front)."""
        self.fuel -= float(amount)

    def reset_velocity(self) -> None:
        """Stop the ship dead. Used on arrival: nobody lands at warp speed."""
        self._velocity = (0.0, 0.0)

    def refill_shields(self) -> None:
        """Shields recharge to maximum for free whenever a system is entered."""
        self.stats.shields = self.stats.max_shields

    def arrive_in_system(self, x: float, y: float) -> None:
        """Land in a freshly entered system: spawn point, stopped, shields up.

        Grouped as one call because arriving always means all three: a jump
        that resets the position but keeps 200 px/frame of hyperspace velocity
        would fling the player straight back out of the system they just paid
        250 fuel to reach.
        """
        self.set_position(x, y)
        self.reset_velocity()
        self.refill_shields()

    # ------------------------------------------------------------------
    # Stage 9: money, cargo, and spaceport state
    # ------------------------------------------------------------------

    @property
    def credits(self) -> float:
        """Credits held by the player.

        Deliberately read-only. The first draft exposed a setter that clamped at
        zero, which turned an unaffordable purchase into a silent one that left
        the player with exactly nothing; every debit now goes through a method
        that checks affordability *before* touching the balance, so a negative
        balance is not clamped away — it is unreachable.
        """
        return self._credits

    @property
    def upgrade_levels(self) -> dict[str, int]:
        """Per-stat upgrade levels (a copy: granting a free upgrade is not an option)."""
        return dict(self._upgrade_levels)

    @property
    def upgrade_steps(self) -> dict[str, float]:
        """The configured magnitude per upgrade **stat name** (``weapons``, not ``weapon_damage``)."""
        return dict(self._upgrade_steps)

    @property
    def carried_loads(self) -> list[CarriedLoad]:
        """The mission payloads currently aboard (a defensive copy)."""
        return list(self._carried)

    @property
    def cargo_used(self) -> int:
        """Total cargo units currently carried (HUD seam)."""
        return sum(load.cargo_units for load in self._carried)

    @property
    def passengers_used(self) -> int:
        """Total passenger slots currently in use (HUD seam)."""
        return sum(load.passengers for load in self._carried)

    def add_credits(self, amount: float) -> None:
        """Credit the player (fares, bounties). Only ever an increase.

        Debits are refused rather than clamped, so a negative ``amount`` here
        would be a back door around :meth:`purchase_upgrade` and friends.
        """
        amount = float(amount)
        if amount < 0:
            raise ValueError(f"credits may only be added, not subtracted: {amount}")
        self._credits += amount

    # -- port visits ----------------------------------------------------

    def begin_port_visit(self) -> int:
        """Number the next port visit and return its serial.

        Offer ids are ``(serial, index)``. Numbering them per visit is what makes
        "accept this job" idempotent: an offer from a stale visit can never be
        replayed for a second fare, even if the player returns to the same system
        and the new visit happens to number its board the same way.
        """
        self._port_visit_serial += 1
        return self._port_visit_serial

    def accept_mission(self, mission: Mission) -> PortTransaction:
        """Take a port's job aboard, if the ship has room and it is still available."""
        if self.offer_is_accepted(mission.offer_id):
            return PortTransaction(False, "That job has already been accepted.")
        result = self.accept_load(
            CarriedLoad(
                destination=mission.destination,
                fare=mission.fare,
                cargo_type=mission.cargo_type,
                cargo_units=mission.cargo_units,
                passengers=mission.passengers,
            )
        )
        if result.succeeded:
            self._accepted_offers.add(mission.offer_id)
        return result

    def accept_load(self, load: CarriedLoad) -> PortTransaction:
        """Take a payload aboard, if there is room.

        Accepting costs capacity, nothing else. The fare is attached to the
        payload and is only collected once the ship lands at the destination.
        A load is never partly accepted: the spec's example (4 passengers with 2
        slots free) is a refusal, not a split, because a half-delivered job pays
        nothing and is indistinguishable from a wasted hold.
        """
        cargo_needed = self.cargo_used + load.cargo_units
        passenger_needed = self.passengers_used + load.passengers
        if cargo_needed > self.stats.cargo_room:
            return PortTransaction(
                succeeded=False,
                reason=(
                    f"Not enough cargo room: this job needs {load.cargo_units} "
                    f"{pluralise(load.cargo_units, 'slot')}, and only "
                    f"{self.stats.cargo_room - self.cargo_used} free."
                ),
            )
        if passenger_needed > self.stats.passenger_space:
            return PortTransaction(
                succeeded=False,
                reason=(
                    f"Not enough passenger space: this job needs {load.passengers} "
                    f"{pluralise(load.passengers, 'berth')}, and only "
                    f"{self.stats.passenger_space - self.passengers_used} free."
                ),
            )
        self._carried.append(load)
        payload = []
        if load.cargo_units:
            payload.append(f"{load.cargo_units} cargo")
        if load.passengers:
            payload.append(f"{load.passengers} passenger(s)")
        return PortTransaction(
            succeeded=True,
            reason=f"Loaded for {load.destination}: {', '.join(payload)}.",
        )

    def offer_is_accepted(self, offer_id: "tuple[int, int]") -> bool:
        """Whether this port's job is already aboard (the spaceport greys it out).

        Queried from the model rather than tracked by the view: a screen that
        keeps its own copy of "what did I accept" will eventually disagree with
        the hold, and the disagreement shows up as an accept button that pays
        nothing.
        """
        return offer_id in self._accepted_offers

    def upgrade_offer_is_available(self, offer: UpgradeOffer) -> bool:
        """Whether an upgrade offer is still buyable at its listed level.

        False once the offer has been bought (the stat has moved on past it) or
        when the stat is maxed. The authority is the same level check
        :meth:`purchase_upgrade` applies, so the greyed-out button and the
        refused purchase can never disagree.
        """
        current = self._upgrade_levels.get(offer.stat)
        if current is None:
            raise ValueError(f"unknown upgrade stat: {offer.stat!r}")
        return current < self.economy.upgrade_max_level and offer.level == current + 1

    # -- landing and launching -------------------------------------------

    @property
    def is_landed(self) -> bool:
        """True while the ship sits at a spaceport (the interface is open).

        The owning scene clears this through :meth:`launch`; the scene that owns
        the port visit watches it go False to drop the visit's offers, which is
        why the flag lives in the model rather than in the view.
        """
        return self._landed

    def land(self, system_name: str) -> LandingReport:
        """Settle at a spaceport.

        Unloads every payload destined for ``system_name`` (in full, as shipped),
        credits their fares, resets velocity, and refills shields. Unloading
        happens *before* the credits are applied and the loads are removed
        outright, so a fare can never be collected twice: landing twice in the
        same system (or landing elsewhere in between) nets the ship nothing from
        those loads.

        Position is deliberately untouched — the spec says the ship stays where
        the player pressed ``L``.
        """
        if self._jumping:
            # Unreachable through legal play (the jump controller refuses a jump
            # started inside landing range, and only the top scene receives
            # input). Loud rather than silently wrong: landing mid-jump would
            # settle fares for a system the player is merely passing through.
            raise ValueError("cannot land while a hyperspace jump is in progress")

        self.reset_velocity()
        self.refill_shields()

        landed = [load for load in self._carried if load.destination == system_name]
        self._carried = [
            load for load in self._carried if load.destination != system_name
        ]
        gained = sum(load.fare for load in landed)
        if gained:
            self.add_credits(gained)
        self._landed = True
        return LandingReport(
            system=system_name,
            credits_gained=int(gained),
            cargo_unloaded=sum(load.cargo_units for load in landed),
            passengers_unloaded=sum(load.passengers for load in landed),
            unloaded=tuple(landed),
        )

    def launch(self) -> None:
        """Leave the spaceport: stopped dead, then immune for the grace period.

        Idempotent by design: the ``Launch!`` button pops a scene and a stray
        second call must not re-arm the immunity clock (that would make the
        grace period a repeatable invulnerability cheat).
        """
        if not self._landed:
            return
        self._landed = False
        self.reset_velocity()
        self._launch_immunity_frames = self.launch_immunity_frames

    @property
    def immune_to_damage(self) -> bool:
        """True while landed, and for the grace period after launching.

        Stage 11's damage path asks this before applying a hit. Landed is
        included because the spec's "no damage while landed" should not depend on
        whether the simulation happens to be paused under the spaceport modal.
        """
        return self._landed or self._launch_immunity_frames > 0

    @property
    def launch_immunity_frames_left(self) -> int:
        """Frames of post-launch immunity remaining (readout/tests seam)."""
        return self._launch_immunity_frames

    # -- port services: refuel, repair, upgrades --------------------------

    @property
    def fuel_room(self) -> float:
        """Unused tank capacity in units."""
        return max(0.0, self.stats.fuel_capacity - self._fuel)

    @property
    def armor_damage(self) -> float:
        """Armour points missing from the hull."""
        return max(0.0, self.stats.max_armor - self.stats.armor)

    def fuel_top_up_cost(self, units: "float | None" = None) -> float:
        """What the port charges to pump ``units`` (all free room by default).

        A preview, so the spaceport can print the price before the player buys,
        and a test can pin the rate without a scene in the way.
        """
        wanted = self.fuel_room if units is None else min(float(units), self.fuel_room)
        return max(0.0, wanted) * self.economy.fuel_price_per_unit

    def repair_top_up_cost(self, points: "float | None" = None) -> float:
        """What the port charges to patch ``points`` of armour (all of it by default)."""
        wanted = self.armor_damage if points is None else min(float(points), self.armor_damage)
        return max(0.0, wanted) * self.economy.repair_price_per_point

    def buy_fuel(self, units: "float | None" = None) -> PortTransaction:
        """Buy fuel at ``economy.fuel_cost_per_unit``, never overfilling the tank.

        All-or-nothing: no partial fill when the player cannot pay, because a
        silent half-fill for the same money is the sort of generosity that
        produces un-debuggable balance bugs. Never drops the balance to the
        credit floor.
        """
        room = self.fuel_room
        if room <= _FULL_EPSILON:
            return PortTransaction(False, "The tank is already full.")
        wanted = room if units is None else min(max(0.0, float(units)), room)
        if wanted <= _FULL_EPSILON:
            return PortTransaction(False, "Nothing to refuel.")

        cost = wanted * self.economy.fuel_price_per_unit
        if not self.can_afford(cost):
            return PortTransaction(
                False,
                f"Not enough credits: {int(wanted)} "
                f"{pluralise(int(wanted), 'unit')} of fuel costs "
                f"{format_credits(cost)} credits.",
            )
        self._credits -= cost
        self._fuel = self._fuel + wanted
        return PortTransaction(
            succeeded=True,
            reason=(
                f"Refuelled {int(wanted)} {pluralise(int(wanted), 'unit')} for "
                f"{format_credits(cost)} credits."
            ),
            credits_spent=cost,
        )

    def repair_armor(self, points: "float | None" = None) -> PortTransaction:
        """Patch armour at ``economy.repair_cost_per_point``.

        Shields are not sold: the spec recharges them free on landing, so a
        "repair shields" option would be a second, contradictory answer to the
        same problem. Only the hull stays broken until paid for.
        """
        missing = self.armor_damage
        if missing <= _FULL_EPSILON:
            return PortTransaction(False, "The hull is already intact.")
        wanted = missing if points is None else min(max(0.0, float(points)), missing)
        if wanted <= _FULL_EPSILON:
            return PortTransaction(False, "Nothing to repair.")

        cost = wanted * self.economy.repair_price_per_point
        if not self.can_afford(cost):
            return PortTransaction(
                False,
                f"Not enough credits: {int(wanted)} "
                f"{pluralise(int(wanted), 'point')} of armour costs "
                f"{format_credits(cost)} credits.",
            )
        self._credits -= cost
        self.stats.armor = self.stats.armor + wanted
        return PortTransaction(
            succeeded=True,
            reason=(
                f"Repaired {int(wanted)} {pluralise(int(wanted), 'point')} of armour "
                f"for {format_credits(cost)} credits."
            ),
            credits_spent=cost,
        )

    def purchase_upgrade(self, offer: UpgradeOffer) -> PortTransaction:
        """Buy one upgrade level: price checked, level bumped, stats applied.

        The price is recomputed from the config curve rather than trusted from
        the offer, and the offer must be for the *next* level of that stat. Those
        two checks together close the two glitches: replaying the same offer
        would otherwise buy a second level at the old (cheaper) price, and a
        stale offer from an earlier visit would otherwise buy a level the ship
        already has.
        """
        if offer.stat not in self._upgrade_levels:
            raise ValueError(f"unknown upgrade stat: {offer.stat!r}")
        label = UPGRADE_LABELS[offer.stat]
        current = self._upgrade_levels[offer.stat]
        if current >= self.economy.upgrade_max_level:
            return PortTransaction(
                False, f"{label} is already at the maximum level."
            )
        if offer.level != current + 1:
            return PortTransaction(
                False,
                f"That {label} offer is out of date: the ship is at level {current}.",
            )

        cost = upgrade_cost(
            offer.level,
            self.economy.upgrade_base_cost,
            self.economy.upgrade_cost_multiplier,
        )
        if not self.can_afford(cost):
            return PortTransaction(
                False,
                f"Not enough credits: {label} level {offer.level} costs "
                f"{format_credits(cost)} credits.",
            )

        self._credits -= cost
        self._upgrade_levels[offer.stat] = offer.level
        apply_upgrade(self.stats, offer.stat, self._upgrade_steps[offer.stat])
        return PortTransaction(
            succeeded=True,
            reason=(
                f"Installed {label} level {offer.level} for "
                f"{format_credits(cost)} credits."
            ),
            credits_spent=cost,
        )

    def can_afford(self, cost: float) -> bool:
        """True when paying ``cost`` leaves the balance strictly above the floor.

        Public because the spaceport greys out buttons with exactly this test: a
        view that re-derives affordability in its own arithmetic is a second
        answer to the question, and the two disagree first at the boundary (a
        purchase that would leave the player with *exactly* 0 credits is refused,
        per the Stage 9 gate).
        """
        cost = float(cost)
        if cost <= 0.0:
            return True  # a free service can never be blocked by the floor
        return self._credits - cost > CREDIT_FLOOR

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
        self._boundary_reached_this_frame = False

        # Post-launch damage immunity ticks down on every frame, jump or
        # no jump. The grace period is meant to span the whole jump and the
        # landing it delivers, not just the landing.
        if self._launch_immunity_frames > 0:
            self._launch_immunity_frames -= 1

        if self._landed:
            # The ship is on the ground: the spaceport modal is on top of the
            # scene stack so nothing should be driving this, but a stray frame
            # from tooling or a future modal must not fly the ship out of the
            # system it parked in. The immunity clock above still ticks: the
            # grace period is measured from launch, not from the last frame.
            return

        if self._jumping:
            # All input is ignored during a jump, and the jump is the only way
            # to leave the system, so the boundary clamp is skipped too.
            self._advance_jump_frame()
            return

        if self._input.reverse_edge:
            self._begin_reverse_course()

        self._advance_reverse_course()

        # Continuous rotation from held arrows is disabled while flipping.
        if self._reverse_state != _ReverseState.REVERSING:
            self._apply_continuous_rotation()

        if self._input.thrust:
            self._apply_thrust(self.stats.acceleration_rate, self.stats.top_speed)
            self._consume_fuel()

        self._integrate_position(clamp_to_system=True)

    def _advance_jump_frame(self) -> None:
        """One frame of hyperspace burn: no speed cap, no boundary, no input.

        The acceleration is supplied by the jump sequence rather than read from
        the ship's stats, because the spec lets a jump exceed the usual top
        speed, and the sequence cuts the burn partway through while the ship is
        still in the animation.
        """
        self._apply_thrust(self._jump_acceleration, speed_cap=None)
        self._integrate_position(clamp_to_system=False)
        self._jump_frames += 1

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

    def _apply_thrust(
        self, acceleration: float, speed_cap: "float | None"
    ) -> None:
        """Apply ``acceleration`` in the facing direction, capped at ``speed_cap``.

        ``speed_cap`` is ``None`` for the hyperspace burn, which the spec lets
        exceed the ship's usual top speed.
        """
        accel = float(acceleration)
        vx, vy = self._velocity
        speed = math.hypot(vx, vy)
        if speed_cap is not None and speed >= speed_cap:
            return  # already capped; adding would only introduce float wobble

        ax = accel * math.cos(math.radians(self.heading))
        ay = accel * math.sin(math.radians(self.heading))
        new_vx = vx + ax
        new_vy = vy + ay
        new_speed = math.hypot(new_vx, new_vy)
        if speed_cap is not None and new_speed > speed_cap:
            # Rescale so the speed lands exactly on top_speed rather than
            # overshooting it by a hair.
            scale = speed_cap / new_speed
            self._velocity = (new_vx * scale, new_vy * scale)
        else:
            self._velocity = (new_vx, new_vy)

    def _consume_fuel(self) -> None:
        """Burn fuel for one frame of thrusting; never below zero."""
        self.fuel -= self.fuel_burn_per_frame
        if self.fuel < 0.0:
            self.fuel = 0.0

    def _integrate_position(self, clamp_to_system: bool) -> None:
        """Newtonian drift: position advances by the current velocity."""
        self._position = (
            self._position[0] + self._velocity[0],
            self._position[1] + self._velocity[1],
        )
        if clamp_to_system:
            self._clamp_to_system()

    def _clamp_to_system(self) -> None:
        """Pin the ship to the system square, scrubbing off the outward speed.

        The spec's rule is positional ("cannot move any further in that
        direction") while still allowing thrust and fuel burn against the wall.
        Zeroing the velocity component through the wall is what makes that
        behave: otherwise a ship pinned for ten seconds accumulates a decade of
        outward drift and slingshots away the instant it turns around. The
        rejected alternative (leave velocity alone) is cheaper but wrong.
        """
        half = self.system_pixel_size / 2.0
        x, y = self._position
        vx, vy = self._velocity
        clamped_x = min(max(x, -half), half)
        clamped_y = min(max(y, -half), half)
        if clamped_x != x:
            vx = 0.0
        if clamped_y != y:
            vy = 0.0
        if (clamped_x, clamped_y) != (x, y):
            self._position = (clamped_x, clamped_y)
            self._velocity = (vx, vy)
            self._boundary_reached_this_frame = True

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

    # ------------------------------------------------------------------
    # Jump plumbing
    # ------------------------------------------------------------------
    @property
    def is_jumping(self) -> bool:
        """True for the whole jump sequence: burn, white-out, and all."""
        return self._jumping

    @property
    def jump_frames(self) -> int:
        """How many fixed timesteps of hyperspace thrust have been integrated."""
        return self._jump_frames

    def begin_jump(self, acceleration: float) -> None:
        """Start a hyperspace burn of ``acceleration`` px/frame squared.

        Clears any latched control frame: the input layer is locked during a
        jump, so a thrust key that was held when the jump began must not keep
        feeding thrust into the model for the rest of the sequence.
        """
        self._input = InputFrame()
        self._reverse_state = _ReverseState.IDLE
        self._jumping = True
        self._jump_acceleration = float(acceleration)
        self._jump_frames = 0

    def set_jump_acceleration(self, acceleration: float) -> None:
        """Change the burn mid-jump (the sequence cuts it to 0 for the white-out)."""
        self._jump_acceleration = float(acceleration)

    def end_jump(self) -> None:
        """Finish a jump sequence and re-enable normal controls.

        Clears the latched control frame again for symmetry: the input layer is
        unlocked on this frame, and a stale frame left over from the sequence
        would be applied as if the player had just pressed it.
        """
        self._jumping = False
        self._jump_acceleration = 0.0
        self._input = InputFrame()
