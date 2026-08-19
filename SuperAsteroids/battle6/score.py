"""Game scoring: shots fired, hits, hit rate, and the nickname.

Spec ("Scoring the game"):
  - shots fired = successful weapon activations (blocked presses excluded);
  - hits = asteroids split/destroyed by PLAYER weapons only;
  - hit rate = hits / shots * 100, one decimal, "0.0%" before any shot;
  - nickname is tiered by hit rate and re-rolled exactly ONCE per tier
    crossing, holding within a tier ("Ace!" stays until the rate drops
    below 80%).
Stats carry across levels and reset to zero at the start of a new game's
level 1 (a fresh GameState builds a fresh tracker).
"""

import random

# Hit-rate nickname (spec: "Scoring the game"). The rate-0 slot is the fixed
# "New recruit" default; the rest are re-rolled membership lists.
NEW_RECRUIT = "New recruit"
NICKNAME_TIERS = (
    # (low, high, choices) - low inclusive, high exclusive, top tier inclusive
    (0.0, 10.0, ("Blind woodsman", "One-eyed Pete", "Unlucky Larry",
                 "No-hit wonder", "Terrible Tom")),
    (10.0, 50.0, ("Amateur", "Wannabe", "Poser", "Good Enough Gary")),
    (50.0, 80.0, ("Great!", "Sharpshooter", "Combat pilot", "Veteran")),
    (80.0, 100.0, ("Ace!", "Combat master", "Top gun", "Hunter")),
)


class ScoreTracker:

    def __init__(self):
        self.shots_fired = 0
        self.hits = 0
        self._nickname = NEW_RECRUIT
        self._tier = self._tier_for(0.0)

    @property
    def hit_rate_percent(self) -> float:
        """Hit rate rounded to ONE decimal (the display precision).

        Rounded here rather than at display time so the nickname tiering
        always agrees with the number the HUD shows (9.96 -> "10.0%" must
        tier like 10%, whatever the raw fraction says).
        """
        if self.shots_fired == 0:
            return 0.0
        return round(self.hits / self.shots_fired * 100.0, 1)

    def hit_rate_text(self) -> str:
        return f"{self.hit_rate_percent:.1f}%"

    @property
    def nickname(self) -> str:
        return self._nickname

    def record_shot(self) -> None:
        self.shots_fired += 1
        self._sync_nickname()

    def record_hit(self) -> None:
        self.hits += 1
        self._sync_nickname()

    def _sync_nickname(self) -> None:
        tier = self._tier_for(self.hit_rate_percent)
        if tier != self._tier:
            self._tier = tier
            self._nickname = (
                NEW_RECRUIT if tier < 0
                else random.choice(NICKNAME_TIERS[tier][2])
            )

    @staticmethod
    def _tier_for(rate: float) -> int:
        """Tier index for a displayed hit rate: -1 = "New recruit" (0%),
        0..3 = the NICKNAME_TIERS entries. Boundaries follow the spec's
        "between X% and Y%" bands with the low end inclusive (10.0% is
        an "Amateur"-band rate, 80.0% is "Ace!"-band, 100.0% tops out)."""
        if rate <= 0.0:
            return -1
        for index, (_low, high, _choices) in enumerate(NICKNAME_TIERS):
            if rate < high or index == len(NICKNAME_TIERS) - 1:
                return index
        return len(NICKNAME_TIERS) - 1  # unreachable; defensive
