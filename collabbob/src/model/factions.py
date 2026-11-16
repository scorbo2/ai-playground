"""Factions: who exists, who shoots whom, and how long a grudge lasts (Stage 10).

Three factions (see the module-level ids below) and one player. The hostility
rules come straight from the spec:

* **Pirates** are hostile to everyone — the player, Localhosters, Bobbers, and
  (because it is stated flatly) each other.
* **Localhosters and Bobbers** are permanently hostile to each other, and
  permanently hostile to pirates from both sides.
* Neither faction is hostile to the player at the start of a new game. Hitting a
  ship of either faction makes that faction hostile **for the rest of the game**
  (Stage 11 calls :meth:`PlayerRelations.declare_hostile_to_player` on impact).

Hostility is a *relation*, not a property of a ship, so it lives here rather than
on the ship. It is also deliberately cheap to reason about: a static matrix for
faction-vs-faction, and one small mutable object for faction-vs-player.

Faction **colours** live here too, against the faction ids. The spec's palette
guidance allows colours-as-defaults in code, and the three colours the game must
agree on (minimap markers, hulls, projectiles, the HUD alignment label) are
identity, not tunables: a Localhoster is cyan everywhere or the game is lying.

Stage 11 adds a fourth *combatant*: the player. The player is deliberately not a
faction — the matrix has no row for them (their relations are the mutable
:class:`PlayerRelations` above, not a matrix entry), and letting ``"player"``
into the matrix would invite questions like "is a pirate hostile to the player
according to the static table?" which has the wrong answer. What the player *is*
allowed to be is a **combatant**: a side a projectile can be attributed to, and a
colour it can be drawn in (green, per the spec). Hence :func:`require_combatant`
and :func:`combatant_color`, which accept the player, sitting beside
:func:`require_faction`, which does not.
"""

from __future__ import annotations

from typing import Dict, FrozenSet, Tuple

# Faction ids. Enum-like ids may live in code per the spec's config guidance
# ("Bad things to place in the config file: keybindings, enum-like IDs").
FACTION_LOCALHOSTER = "localhoster"
FACTION_BOBBER = "bobber"
FACTION_PIRATE = "pirate"

# Draw order for a fair fight: this tuple is also the roster every random pick
# and every validation check is built from, in this order.
FACTIONS: Tuple[str, ...] = (FACTION_LOCALHOSTER, FACTION_BOBBER, FACTION_PIRATE)

# The player's own side. Not a faction (no matrix row, no spawn pool, no label in
# the scan readout); a provenance tag for a projectile and a colour to draw it in.
FACTION_PLAYER = "player"

# Everything a projectile or a hit may be attributed to.
COMBATANTS: Tuple[str, ...] = FACTIONS + (FACTION_PLAYER,)

# HUD copy (spec: the readout shows "Localhoster" / "Bobber" / "Pirate").
FACTION_LABELS: Dict[str, str] = {
    FACTION_LOCALHOSTER: "Localhoster",
    FACTION_BOBBER: "Bobber",
    FACTION_PIRATE: "Pirate",
}

# Spec-pinned identity colours: Localhoster cyan, Bobber yellow, Pirate red.
FACTION_COLORS: Dict[str, Tuple[int, int, int]] = {
    FACTION_LOCALHOSTER: (0, 200, 200),
    FACTION_BOBBER: (230, 200, 60),
    FACTION_PIRATE: (255, 0, 0),
}

# Spec: "Player projectiles are solid green 3px diameter circles." Green is not
# in the faction trio, which is exactly why the player needs their own entry: a
# player shot drawn in anyone else's colour would misreport who fired.
PLAYER_COLOR: Tuple[int, int, int] = (60, 220, 60)

# The full palette every gun and every readout draws from, keyed by combatant.
COMBATANT_COLORS: Dict[str, Tuple[int, int, int]] = {
    **FACTION_COLORS,
    FACTION_PLAYER: PLAYER_COLOR,
}


class UnknownFaction(ValueError):
    """Raised when code hands a hostility rule a faction that does not exist.

    Loud on purpose: a typo'd faction id would otherwise read as "not hostile"
    and quietly turn a pirate into a tourist.
    """


def require_faction(faction: str) -> str:
    """Validate a faction id, returning it unchanged so it can wrap a lookup."""
    if faction not in FACTIONS:
        raise UnknownFaction(f"unknown faction {faction!r}; expected one of {FACTIONS}")
    return faction


def faction_label(faction: str) -> str:
    """Display name for a faction id, e.g. ``"bobber"`` -> ``"Bobber"``."""
    require_faction(faction)
    return FACTION_LABELS[faction]


def faction_color(faction: str) -> Tuple[int, int, int]:
    """The one true colour of a faction (hulls, markers, projectiles, HUD)."""
    require_faction(faction)
    return FACTION_COLORS[faction]


def require_combatant(combatant: str) -> str:
    """Validate a *combatant* id: the three factions plus the player.

    The wider vocabulary exists for Stage 11's provenance rules (whose gun fired,
    whose hull gets clipped). It is deliberately not accepted by the hostility
    matrix, whose :func:`require_faction` still refuses ``"player"``.
    """
    if combatant not in COMBATANTS:
        raise UnknownFaction(
            f"unknown combatant {combatant!r}; expected one of {COMBATANTS}"
        )
    return combatant


def combatant_color(combatant: str) -> Tuple[int, int, int]:
    """The colour of anything attributable to ``combatant``, the player included."""
    require_combatant(combatant)
    return COMBATANT_COLORS[combatant]


def is_npc_faction(combatant: str) -> bool:
    """Whether ``combatant`` is one of the three spawned factions.

    Combat code asks this a lot: only NPC hulls can be scanned, only NPC hulls
    carry bounties, and the player is not a faction that can hold a grudge.
    """
    return combatant in FACTIONS


def war_side_of(faction: str) -> str:
    """The other war-side (Localhoster <-> Bobber); pirates have no ally or rival.

    Stage 11's cross-faction bounties are paid by the victim's *enemy*, so the
    game needs this one lookup, and it needs to refuse to answer for pirates
    rather than inventing a "pirate rival" that the lore does not have.
    """
    require_faction(faction)
    if faction == FACTION_PIRATE:
        raise UnknownFaction(
            "pirates are hostile to every faction, so no faction pays a bounty for "
            "killing one: the bounty comes from the game, not from a rival"
        )
    return FACTION_BOBBER if faction == FACTION_LOCALHOSTER else FACTION_LOCALHOSTER


def factions_are_hostile(first: str, second: str) -> bool:
    """Static, symmetric, permanent hostility between two factions.

    Same-faction pairs are hostile only for pirates: the spec says pirates are
    hostile to *everyone*, and this function reports what the spec says. Whether
    a hostile pair can actually trade lead is a separate question — see
    :func:`factions_can_engage`, which applies the no-friendly-fire rule.
    """
    require_faction(first)
    require_faction(second)

    if first == second:
        return first == FACTION_PIRATE
    if FACTION_PIRATE in (first, second):
        return True
    # The only remaining pair is Localhoster/Bobber: mutually hostile.
    return {first, second} == {FACTION_LOCALHOSTER, FACTION_BOBBER}


def factions_can_engage(attacker: str, victim: str) -> bool:
    """Whether ``attacker`` may shoot at ``victim`` at all.

    Hostile **and not the same faction**: the spec forbids friendly fire
    ("projectiles fired from any faction ship pass harmlessly through other
    ships of the same faction"). Reporting pirate-vs-pirate as *engageable*
    would give every pirate a permanent, completely harmless duel with their
    nearest neighbour, and they would never once chase the ship they can
    actually hurt. So the matrix keeps the spec's wording, and this filter keeps
    the AI sane.
    """
    return factions_are_hostile(attacker, victim) and attacker != victim


class PlayerRelations:
    """Which factions have decided to shoot the player, permanently.

    One instance per game session, owned by the scene that owns the run, and
    shared by every encounter in every system: a Localhoster who has been shot
    at in Alpha holds a grudge in Zulu. Nothing here can forgive a faction —
    there is no ``declare_peace`` on purpose, because the spec's grudge lasts
    "for the remainder of the game" and an unforgiving API cannot drift into a
    forgiving game.
    """

    def __init__(self, initially_hostile: Tuple[str, ...] = ()) -> None:
        for faction in initially_hostile:
            require_faction(faction)
        self._hostile: set[str] = set(initially_hostile)

    def is_hostile_to_player(self, faction: str) -> bool:
        """Whether ships of ``faction`` will attack the player right now."""
        require_faction(faction)
        # Pirates need no grudge: they were never neutral.
        return faction == FACTION_PIRATE or faction in self._hostile

    def declare_hostile_to_player(self, faction: str) -> bool:
        """Make ``faction`` hostile to the player for the rest of the game.

        Returns True when this changed the relations, False when they were
        already hostile — which lets the damage path decide whether to print
        "(Faction) sends their thanks" style news without keeping its own copy
        of the grudge list.
        """
        require_faction(faction)
        if self.is_hostile_to_player(faction):
            return False
        self._hostile.add(faction)
        return True

    @property
    def factions_hostile_to_player(self) -> FrozenSet[str]:
        """Every faction currently shooting at the player (a copy)."""
        return frozenset(self._hostile | {FACTION_PIRATE})

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"PlayerRelations(hostile={sorted(self.factions_hostile_to_player)})"
