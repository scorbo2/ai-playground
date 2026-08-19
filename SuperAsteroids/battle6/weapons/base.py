"""Weapon base classes.

``Weapon`` is the common shape (name/HUD color, power level, press hook,
per-frame hook, draw hook). ``ChargedWeapon`` adds the 100-unit charge
state machine shared by the Laser and Ramming Shield:

  - a fresh PRESS (``on_press``) activates iff the weapon is not already
    firing, wasn't just spent, and charge >= 20; each activation is one
    "shot fired" (the owning state records it);
  - while firing, charge drains every frame; at 0 the effect ends;
  - the LASER additionally ends by HIT: the beam is consumed by the first
    impacted object. Both lasers and shields that end by hit or depletion
    while the key is still held keep DRAINING until release (spec) - the
    "spent" flag marks that; the shield, unlike the laser, does not end
    on asteroid hits, so it rams freely for the charge it has left;
  - releasing a still-firing effect ends it normally (recharge resumes).
"""

import pygame

from game_constants import (
    MAX_WEAPON_POWER,
    WEAPON_CHARGE_MAX,
    WEAPON_MIN_ACTIVATE_CHARGE,
)


class Weapon:
    NAME = "Weapon"
    LABEL_COLOR = None  # set by subclasses (spec: Cannon yellow, Laser blue, Shield red)

    def __init__(self, power_level: int = 1):
        self.power_level = power_level

    def power(self) -> int:
        """Clamped 1-based power level (defensive against stray values)."""
        return max(1, min(MAX_WEAPON_POWER, self.power_level))

    def index(self) -> int:
        """0-based index into the per-power-level parameter tables."""
        return self.power() - 1

    def boost(self) -> None:
        """A same-type powerup pickup: power +1, capped at 3 (spec)."""
        self.power_level = max(1, min(MAX_WEAPON_POWER, self.power_level + 1))

    def reset_active(self) -> None:
        """Level-advancement sweep (spec): any active effect is deactivated
        and its charge restored to 100%. Weapons without charge state are
        unaffected."""
        pass

    def on_press(self, craft, active) -> bool:
        """Space pressed. Returns True iff this was a SUCCESSFUL weapon
        activation (the state records exactly one shot for it).

        ``active`` is the list of in-play objects that gate this press.
        Projectile weapons are handed the projectile list (an in-flight cap
        may apply); the shrapnel-mine weapon is handed the live-mine list,
        because its cap is over MINES. Each weapon knows which it received
        - the owning state selects it (see GameState._on_weapon_press)."""
        return False

    def update(self, space_held: bool) -> None:
        """Per-frame state work (charge drain/recharge, etc.)."""
        pass

    def draw(self, screen: pygame.Surface, craft) -> None:
        """Render the weapon's own visuals (beam, shield ring, ...)."""
        pass


class ChargedWeapon(Weapon):
    CHARGE_MAX = float(WEAPON_CHARGE_MAX)
    ACTIVATE_MIN = WEAPON_MIN_ACTIVATE_CHARGE

    def __init__(self, power_level: int = 1):
        super().__init__(power_level)
        self.charge = self.CHARGE_MAX
        self.firing = False
        # True after a hit/depletion end while the key stayed held: drain
        # continues, recharge and re-activation are blocked until release.
        self._spent = False

    @property
    def drain_rate(self) -> float:
        raise NotImplementedError

    @property
    def recharge_rate(self) -> float:
        raise NotImplementedError

    def on_press(self, craft, active_projectiles) -> bool:
        if self.firing or self._spent or self.charge < self.ACTIVATE_MIN:
            return False  # blocked activation: NOT a shot (spec: Weapons)
        self.firing = True
        return True

    def deactivate_after_hit(self) -> None:
        """The effect was consumed by an impact (laser behavior): stop
        rendering, keep draining while the key is held, and require a fresh
        press after release (spec: Laser). The shield never calls this -
        it keeps ramming while its charge lasts."""
        self.firing = False
        self._spent = True

    def reset_active(self) -> None:
        """Level-advancement sweep: deactivate and restore full charge."""
        self.firing = False
        self._spent = False
        self.charge = self.CHARGE_MAX

    def update(self, space_held: bool) -> None:
        if not space_held:
            # Key released: the effect ends (if active) and recharge resumes.
            # The release frame itself counts as "not held" (spec: recharge
            # applies whenever the bar is not held).
            self.firing = False
            self._spent = False
            self.charge = min(self.CHARGE_MAX, self.charge + self.recharge_rate)
            return
        if self.firing:
            self.charge = max(0.0, self.charge - self.drain_rate)
            if self.charge <= 0.0:
                self.firing = False
                self._spent = True  # depleted under a held key
        elif self._spent:
            # Ended by a hit or by depletion, but the user is still holding:
            # drain continues (spec: Laser).
            self.charge = max(0.0, self.charge - self.drain_rate)
        # Held, not firing, not spent: a blocked press keeps the charge
        # untouched - no drain, no recharge (spec: cannot activate < 20).
