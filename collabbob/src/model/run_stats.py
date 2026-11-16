"""What a run did, counted as it happened, and printed when the run ends (Stage 13).

The end screen has to summarise a run, and almost none of it is derivable at the
end: the hold has been emptied by the delivery that killed the run, the fares are
spent, the wrecks are gone. So the counters are recorded *at the moment the thing
happens*, in the object that already knows about it:

* deliveries and purchases in :class:`~src.model.game_state.GameState` (it is the
  only place money and cargo change hands),
* jumps and kills in :class:`~src.scenes.game_scene.GameScene` (it is where the
  arrival event and the impact events land),
* frames flown in :meth:`GameState.advance_frame` (the single simulation tick).

There is deliberately no ``spend``/``award`` on this object: it records, it does
not transact. That is what keeps a bug in the run summary from ever being able to
change the player's balance.
"""

from __future__ import annotations

from dataclasses import dataclass, fields

from src.model.economy import format_credits

# Seconds per simulation frame. The timestep is fixed at 1/60 by the main loop
# and the spec forbids reading real dt, so a run's elapsed time is a frame count
# converted with this constant — never a wall clock.
SECONDS_PER_FRAME = 1.0 / 60.0


def _require_non_negative(amount: float, what: str) -> float:
    value = float(amount)
    if value < 0.0:
        raise ValueError(f"{what} cannot be negative: {amount}")
    return value


@dataclass
class RunLedger:
    """Per-run counters. One per game, owned by the game state, never shared."""

    jumps: int = 0
    contracts_delivered: int = 0
    cargo_delivered: int = 0
    passengers_delivered: int = 0
    fare_credits: float = 0.0
    bounty_credits: float = 0.0
    credits_spent: float = 0.0
    hulls_destroyed: int = 0
    frames_flown: int = 0

    # -- recorders -------------------------------------------------------
    def record_jump(self, count: int = 1) -> None:
        """One completed hyperspace jump (counted on arrival, not on request)."""
        self.jumps += _require_count(count, "jumps")

    def record_delivery(self, credits: float, cargo_units: int, passengers: int) -> None:
        """A payload was unloaded and paid for at a spaceport."""
        self.contracts_delivered += 1
        self.cargo_delivered += _require_count(cargo_units, "cargo units")
        self.passengers_delivered += _require_count(passengers, "passengers")
        self.fare_credits += _require_non_negative(credits, "fare credits")

    def record_bounty(self, credits: float) -> None:
        """A bounty was actually paid (a refusal is not a bounty)."""
        self.bounty_credits += _require_non_negative(credits, "bounty credits")

    def record_kill(self, count: int = 1) -> None:
        """A hull the player's own gun finished."""
        self.hulls_destroyed += _require_count(count, "hulls destroyed")

    def record_purchase(self, credits: float) -> None:
        """Credits paid to a port: fuel, armour, or an upgrade."""
        self.credits_spent += _require_non_negative(credits, "credits spent")

    def record_frames(self, frames: int = 1) -> None:
        """Frames of simulation this run has run. Time in the saddle."""
        self.frames_flown += _require_count(frames, "frames")

    # -- derived ---------------------------------------------------------
    @property
    def credits_earned(self) -> float:
        """Everything that came in, fares and bounties together."""
        return self.fare_credits + self.bounty_credits

    @property
    def seconds_elapsed(self) -> float:
        return self.frames_flown * SECONDS_PER_FRAME

    def clock(self) -> str:
        """Elapsed run time as ``mm:ss`` (``h:mm:ss`` past an hour)."""
        total = int(self.seconds_elapsed)
        hours, remainder = divmod(total, 3600)
        minutes, seconds = divmod(remainder, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes:02d}:{seconds:02d}"

    def copy(self) -> "RunLedger":
        """A snapshot copy, so a reader can never advance the run's books."""
        return RunLedger(**{field.name: getattr(self, field.name) for field in fields(self)})


def _require_count(count: int, what: str) -> int:
    value = int(count)
    if value < 0:
        raise ValueError(f"{what} cannot be negative: {count}")
    return value


@dataclass(frozen=True)
class RunSummary:
    """The end screen's payload: the ending plus the run's numbers.

    Built once, when the run ends, from the ledger and the live game state. It is
    frozen and holds no references to the run's objects on purpose: the end screen
    is drawn for as long as the player lingers on it, and a summary that read the
    live balance could not survive the scene stack underneath it changing.
    """

    ending: str
    credits: float
    win_credits: float
    systems_revealed: int
    systems_total: int
    current_system: str
    jumps: int
    contracts_delivered: int
    cargo_delivered: int
    passengers_delivered: int
    fare_credits: float
    bounty_credits: float
    credits_earned: float
    credits_spent: float
    hulls_destroyed: int
    clock: str

    @classmethod
    def from_run(
        cls,
        ending: str,
        game_state,
        systems_revealed: int,
        systems_total: int,
        current_system: str,
    ) -> "RunSummary":
        """Snapshot a finished run.

        ``systems_revealed``/``systems_total``/``current_system`` come from the
        scene's :class:`~src.map_systems.system_map.SystemMapState`: fog of war is
        map state, not ship state, and the ledger has no business owning it.
        """
        ledger = game_state.ledger
        return cls(
            ending=ending,
            credits=game_state.credits,
            win_credits=game_state.economy.win_credits,
            systems_revealed=int(systems_revealed),
            systems_total=int(systems_total),
            current_system=current_system,
            jumps=ledger.jumps,
            contracts_delivered=ledger.contracts_delivered,
            cargo_delivered=ledger.cargo_delivered,
            passengers_delivered=ledger.passengers_delivered,
            fare_credits=ledger.fare_credits,
            bounty_credits=ledger.bounty_credits,
            credits_earned=ledger.credits_earned,
            credits_spent=ledger.credits_spent,
            hulls_destroyed=ledger.hulls_destroyed,
            clock=ledger.clock(),
        )

    def pairs(self) -> "tuple[tuple[str, str], ...]":
        """The stat block, top to bottom, as ``(label, value)`` pairs.

        Pairs rather than one padded string: the label column and the value column
        are positioned by the screen, and padding baked into the text would be a
        second, drift-prone answer about where the columns sit. Still a pure
        function rather than draw code, per the Stage 6/9 precedent — a test that
        asserts on these pairs asserts on the pixels.
        """
        payload = []
        if self.cargo_delivered:
            payload.append(f"{self.cargo_delivered} cargo")
        if self.passengers_delivered:
            payload.append(f"{self.passengers_delivered} passenger(s)")
        delivery = f" ({', '.join(payload)})" if payload else ""

        earned = f"{format_credits(self.credits_earned)} credits"
        if self.bounty_credits:
            earned += (
                f" = {format_credits(self.fare_credits)} fares"
                f" + {format_credits(self.bounty_credits)} bounties"
            )

        return (
            ("Final balance", f"{format_credits(self.credits)} of "
             f"{format_credits(self.win_credits)} credits"),
            ("Ended in", self.current_system),
            ("Systems discovered", f"{self.systems_revealed} of {self.systems_total}"),
            ("Jumps made", str(self.jumps)),
            ("Contracts delivered", f"{self.contracts_delivered}{delivery}"),
            ("Credits earned", earned),
            ("Credits spent", format_credits(self.credits_spent)),
            ("Hulls destroyed", str(self.hulls_destroyed)),
            ("Time in the saddle", self.clock),
        )
