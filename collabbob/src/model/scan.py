"""The ``T`` binding: which ship the HUD's nearest-ship readout is locked on (Stage 11).

The readout is a *sticky* display, and stickiness is where all of this module's
logic lives. The spec's four rules, restated as code:

* **New system, no target.** Entering a system always resets the readout, so a
  lock acquired in Alpha cannot be showing a hull that is no longer in the
  universe while the player orbits Bravo.
* **``T`` locks onto the nearest ship.** Nothing in the system, nothing displayed.
* **The lock is sticky.** A ship that stops being the nearest is still displayed —
  the player chose to look at *that* one, and having the readout wander off to
  whoever drifted closer is how a scan becomes useless mid-fight.
* **``T`` again re-locks on the current nearest** — a no-op when the displayed
  ship is still the nearest, which is the common case and worth naming because the
  difference between "re-pick" and "keep" is only observable if something else
  (a shield bar, a scan klaxon in Stage 12) reads the result.
* **A destroyed target reverts the readout to "No target"** without another key
  press: the ship is gone, and a readout showing a wreck's shield bar at 0 is
  reporting a fact about an object that no longer exists.

Note what is *not* here: this scanner does not know about factions, hostility,
projectiles, or the HUD. It answers "which ship am I looking at", and the HUD
decides what colour to say it in. (The Stage 12 klaxon wants the same answer plus
one hostility question — both available from here without changing it.)
"""

from __future__ import annotations

from typing import Optional, Sequence

from src.model.encounter import nearest_living_ship
from src.model.physics import Vec2


class ShipScanner:
    """One player's eye: the hull the nearest-ship readout is currently on.

    The displayed ship is held by identity, so the lock survives the fleet being
    reordered or pruned, and dies when that particular hull does.
    """

    def __init__(self, displayed: Optional[object] = None) -> None:
        self.displayed = displayed

    # ------------------------------------------------------------------
    def scan(self, ships: Sequence[object], observer_position: Vec2) -> Optional[object]:
        """Handle a ``T`` press: lock onto the nearest living ship in the system.

        Returns what is displayed afterwards (``None`` when there was nothing to
        lock onto). Locking on when the current lock is *still* nearest is the
        spec's explicit no-op, and assigning the same object back is that no-op
        rather than a branch that could drift from the "nearest" rule.

        A wreck is never a candidate: :func:`~src.model.encounter.nearest_living_ship`
        skips destroyed hulls, so re-scanning in a system the player just cleared
        resets the readout to "No target" instead of re-locking onto the corpse.
        """
        nearest = nearest_living_ship(ships, observer_position)
        if nearest is not None:
            self.displayed = nearest
        return self.displayed

    def refresh(self) -> Optional[object]:
        """Drop the lock if the displayed ship has been destroyed; return the lock.

        Called every frame the fight is resolved, because the spec's "reverts to
        'No target'" is not conditioned on the player pressing ``T`` again.
        """
        if self.displayed is not None and getattr(self.displayed, "destroyed", False):
            self.displayed = None
        return self.displayed

    def clear(self) -> None:
        """Forget the lock: the player has entered a different system (or a new game).

        The spec's "when entering a new system, the nearest ship readout should
        always show 'No target'" — even if the old lock was, say, a pirate that is
        still flying around in the system the player just left.
        """
        self.displayed = None

    # ------------------------------------------------------------------
    @property
    def has_target(self) -> bool:
        """Whether the readout has something to show at all."""
        return self.displayed is not None

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ShipScanner(displayed={self.displayed!r})"
