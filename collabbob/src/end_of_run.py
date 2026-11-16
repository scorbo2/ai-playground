"""Who decides that a run is over — once — and who says so on screen (Stage 13).

Four endings, two places they can be noticed, and one screen. If each of those
places kept its own copy of "and now we end the game", the once-only guarantee
the stage gate asks for would have to be re-established at every call site, and
the *order* the endings are checked in would be folklore. This object is the
single owner of both.

* :meth:`poll_flight` runs on every tactical frame (ship lost, stranded).
* :meth:`poll_at_port` runs when the spaceport opens and after every transaction
  there (victory, bankrupt) — never anywhere else, because the spec evaluates the
  credit conditions only after arrival at a spaceport, and an auto-unload may have
  paid enough to buy the tank of fuel the player could otherwise not afford.
* :meth:`latch` is for the endings a *scene* is told about before the model can
  see them: Stage 8's "``J`` with exactly the jump's fuel cost" special case,
  which is a refusal (no jump, no fuel spent) that is also a death sentence.

The rules themselves are pure and live in :mod:`src.model.endgame`; this is the
part that decides when to ask, remembers the answer, and pushes exactly one
screen. A predicate that stays true on the next frame is not a bug — a second end
screen stacked on the first is, which is why "exactly once" is a property of this
class and not of the predicates.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.model.endgame import (
    ENDING_NONE,
    ending_copy,
    ending_at_port,
    ending_in_flight,
    is_victory,
)
from src.model.run_stats import RunSummary

if TYPE_CHECKING:
    from src.map_systems.system_map import SystemMapState
    from src.model.game_state import GameState
    from src.scene_manager import SceneManager


class EndOfRun:
    """The run's death-and-victory switchboard."""

    def __init__(
        self,
        manager: "SceneManager",
        game_state: "GameState",
        system_map: "SystemMapState",
        jump_fuel_cost: float,
    ) -> None:
        if manager is None or game_state is None or system_map is None:
            raise ValueError(
                "EndOfRun needs the scene manager, the GameState, and the SystemMapState"
            )
        if float(jump_fuel_cost) < 0.0:
            raise ValueError(f"jump fuel cost cannot be negative: {jump_fuel_cost}")
        self._manager = manager
        self.game_state = game_state
        self.system_map = system_map
        self.jump_fuel_cost = float(jump_fuel_cost)

        # The ending currently on screen (ENDING_NONE while the run is live).
        self._ending: str = ENDING_NONE
        # An ending a scene knows about but has not yet put on screen. A latch,
        # not an event: it survives until it is shown, and it is cleared when it
        # is, so the same death cannot be announced twice (the Stage 8 note about
        # "the player dies again next frame").
        self._latched: str = ENDING_NONE
        self.summary: "RunSummary | None" = None

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    @property
    def ending(self) -> str:
        """The ending that has fired, or ``ENDING_NONE`` while the run is live."""
        return self._ending

    @property
    def ended(self) -> bool:
        return self._ending != ENDING_NONE

    @property
    def pending_ending(self) -> str:
        """A latched-but-unshown ending (``ENDING_NONE`` when there is none)."""
        return self._latched

    def latch(self, ending: str) -> None:
        """Record an ending the model's per-frame predicates cannot see.

        Firing is still the poll's job, so the ordering rules stay in one place:
        a latched ending loses to an already-shown one, and a second latched loss
        never overwrites the first one owed to the player.
        """
        if ending == ENDING_NONE:
            return
        if self.ended:
            return
        if self._latched != ENDING_NONE and not is_victory(ending):
            # Something is already owed to the player; keep the first one rather
            # than let a later, quieter condition overwrite the louder one.
            return
        self._latched = ending

    # ------------------------------------------------------------------
    # Polls
    # ------------------------------------------------------------------
    def poll_flight(self) -> str:
        """Check the in-flight endings; fire one if the run is over. Returns the ending.

        Skipped mid-jump on purpose: hyperspace cannot strand anyone (the fare is
        paid up front and the jump rules refuse a jump that would empty the tank),
        and nothing in a system the player has left can shoot them. A jump that
        *lands* them out of fuel is caught by the first frame after arrival.
        """
        if self.ended or self.game_state.is_jumping:
            return ENDING_NONE

        ending = self._latched
        if ending == ENDING_NONE:
            ending = ending_in_flight(self.game_state)
        if ending == ENDING_NONE:
            return ENDING_NONE
        self._fire(ending)
        return ending

    def poll_at_port(self) -> str:
        """Check the credit endings, which only ever apply at a spaceport.

        Call it when the port opens (after the auto-unload has settled) and after
        every transaction inside it: buying an upgrade can be the purchase that
        makes the next tank of fuel unaffordable, and that is exactly the state
        the "Bankrupt!" ending exists to name.
        """
        if self.ended:
            return ENDING_NONE
        ending = ending_at_port(self.game_state, self.jump_fuel_cost)
        if ending == ENDING_NONE:
            return ENDING_NONE
        self._fire(ending)
        return ending

    # ------------------------------------------------------------------
    # The one place a screen is pushed
    # ------------------------------------------------------------------
    def _fire(self, ending: str) -> None:
        """Freeze the run and show the result screen, exactly once.

        The end screen goes on *top* of whatever is underneath: the scene stack
        gives events and updates to the top scene only, so this is also the
        freeze. The run's scenes stay on the stack until the player chooses to
        return to the title, which is why the tactical view underneath this one
        keeps drawing a finished ship instead of being torn down mid-frame.
        """
        from src.scenes.end_screen import EndScreenScene  # late: the screen owns pygame_gui

        self._ending = ending
        self._latched = ENDING_NONE
        self.summary = RunSummary.from_run(
            ending=ending,
            game_state=self.game_state,
            systems_revealed=len(self.system_map.revealed),
            systems_total=len(self.system_map.graph.names),
            current_system=self.system_map.current_system,
        )
        self._manager.push(EndScreenScene(ending, self.summary))

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        headline = ending_copy(self._ending) if self.ended else ""
        return (
            f"EndOfRun(ending={self._ending!r}, latched={self._latched!r}, "
            f"headline={headline!r})"
        )
