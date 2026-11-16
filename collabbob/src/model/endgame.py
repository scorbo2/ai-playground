"""How a run ends: the four endings, the copy that names them, and the rules (Stage 13).

The spec lists four ways a game finishes, and each is a *predicate*, not a
screen:

* **Ship lost** — armour reaches zero. Checked on every tactical frame.
* **Stranded** — the tanks are empty outside landing range. Also checked every
  tactical frame, and deliberately *not* rescued by Newtonian drift: a ship with
  an empty tank that could coast to the planet still dies, because the spec says
  so and because "empty tank, out of range, drifting away from the only lifeboat
  in the system" is otherwise an unrecoverable state nobody reports.
* **Bankrupt** — not enough fuel to jump, and not enough credits to buy fuel at
  the port the player is standing in. Checked **only at a spaceport**, because
  the auto-unload of cargo and passengers on landing may lift the balance back
  above the price of a tank.
* **Victory** — the balance reaches ``economy.win_credits``. Also checked only at
  a spaceport, so a bounty that crosses the line mid-flight does not win the game
  until the player lands (spec: "they must land at any spaceport for this
  condition to be evaluated").

Everything here is pure: no pygame, no scene stack, no sound. The predicates take
the :class:`~src.model.game_state.GameState` they are judging, so a test can
construct a state and ask it how it died.

The "exactly once" guarantee is *not* here. A predicate that keeps returning the
same ending on the next frame is correct and harmless; the once-only rule belongs
to the thing that pushes a screen (``src.end_of_run.EndOfRun``), because pushing
twice is a presentation bug, not a rules bug.
"""

from __future__ import annotations

from src.model.game_state import PLANET_WORLD_POSITION

# Ending ids. Enum-like ids live in code per the spec's config guidance.
ENDING_NONE = ""
ENDING_SHIP_LOST = "ship_lost"
ENDING_STRANDED = "stranded"
ENDING_BANKRUPT = "bankrupt"
ENDING_VICTORY = "victory"

ENDINGS: tuple[str, ...] = (
    ENDING_SHIP_LOST,
    ENDING_STRANDED,
    ENDING_BANKRUPT,
    ENDING_VICTORY,
)

# The end-screen headline. The four loss strings and the win string are quoted
# from the spec, punctuation included, and the tests assert them verbatim: a
# reworded ending is a silently changed contract with the player.
ENDING_COPY = {
    ENDING_SHIP_LOST: "Ship lost with all hands!",
    ENDING_STRANDED: "Stranded! Lost in space!",
    ENDING_BANKRUPT: "Bankrupt!",
    ENDING_VICTORY: "You're a millionaire! You win!",
}

# One line of explanation under the headline, naming the condition that fired.
# Kept beside the headline so a rule and its explanation cannot drift apart.
ENDING_EXPLANATION = {
    ENDING_SHIP_LOST: "Armour reached zero.",
    ENDING_STRANDED: "The tanks ran dry outside landing range.",
    ENDING_BANKRUPT: "Not enough fuel to jump, and not enough credits to buy more.",
    ENDING_VICTORY: "The balance cleared the target at a spaceport.",
    ENDING_NONE: "",
}

# Fuel and stats are floats that have been subtracted from floats, so "the tank is
# empty" is a rule the hull itself owns — see GameState.is_out_of_fuel and
# EMPTY_TANK_EPSILON. The stranded check asks that one question rather than
# comparing against a second epsilon it invented.


def ending_copy(ending: str) -> str:
    """The headline for ``ending``; raises on an ending the game does not have."""
    if ending not in ENDING_COPY:
        raise ValueError(f"unknown ending {ending!r}; expected one of {ENDINGS}")
    return ENDING_COPY[ending]


def ending_explanation(ending: str) -> str:
    """The one-line explanation under the headline."""
    if ending not in ENDING_EXPLANATION:
        raise ValueError(f"unknown ending {ending!r}; expected one of {ENDINGS}")
    return ENDING_EXPLANATION[ending]


def is_victory(ending: str) -> bool:
    """Whether this ending is the win (the end screen colours it differently)."""
    if ending not in ENDING_COPY:
        raise ValueError(f"unknown ending {ending!r}; expected one of {ENDINGS}")
    return ending == ENDING_VICTORY


# ---------------------------------------------------------------------------
# The in-flight endings: ship lost, stranded
# ---------------------------------------------------------------------------
def is_stranded(game_state) -> bool:
    """Empty tanks and no spaceport within landing range.

    Landed and jumping ships are excluded by rule, not by call site: a ship at a
    spaceport with an empty tank is a customer, not a castaway (the port sells
    fuel, and :func:`is_broke_at_port` decides whether it can afford any), and a
    ship in hyperspace has already paid for a system it is about to arrive in.
    """
    if game_state.is_landed or game_state.is_jumping:
        return False
    if not game_state.is_out_of_fuel():
        return False
    planet_x, planet_y = PLANET_WORLD_POSITION
    return not game_state.in_landing_range((planet_x, planet_y))


def victory_reached(game_state) -> bool:
    """The win condition: the balance has reached ``economy.win_credits``.

    ``>=``, not ``>``: the target is a milestone the player is meant to be able
    to hit exactly, and the spec's own million is a round number the shipped
    configs use.
    """
    return game_state.credits >= game_state.economy.win_credits


def ending_in_flight(game_state) -> str:
    """Which ending the current tactical state implies, or ``ENDING_NONE``.

    Ship lost outranks stranded on purpose. A hull can run its tank dry and catch
    a killing round in the same frame; "all hands lost" is the story the player
    just watched, and the dry tank is an epitaph detail.
    """
    if game_state.destroyed:
        return ENDING_SHIP_LOST
    if is_stranded(game_state):
        return ENDING_STRANDED
    return ENDING_NONE


# ---------------------------------------------------------------------------
# The spaceport endings: victory, bankrupt
# ---------------------------------------------------------------------------
def can_jump_the_price(game_state, jump_fuel_cost: float) -> bool:
    """Whether the ship could pay for a jump and survive it.

    *Strictly* greater than the jump cost, which is the jump rules' own answer:
    Stage 8 refuses ``J`` at exactly the price and calls it a game over, so a
    tank that holds exactly the fare is not an escape route.
    """
    return game_state.fuel > float(jump_fuel_cost)


def is_broke_at_port(game_state, jump_fuel_cost: float) -> bool:
    """True when the port the player is standing in cannot get them out of the system.

    The port sells exactly one fuel product: a full tank, at
    ``economy.fuel_cost_per_unit``. So the question has two halves, and both must
    be true:

    1. the tank cannot pay for a jump (see :func:`can_jump_the_price`), and
    2. a full tank is not affordable — or there is nothing left to buy, which is
       the same dead end wearing a different hat (a config whose
       ``fuel_capacity`` does not exceed ``tactical.jump.fuel_cost`` leaves the
       player permanently unable to leave, and must end the run rather than
       strand them politely).

    A *prorated* top-up ("buy exactly enough to jump") is not what the port
    sells, and pricing one would mean inventing a margin above the jump cost —
    Stage 8's exact-fuel rule makes "exactly enough" a fatal purchase. See the
    Stage 13 entry in DECISIONS.md.
    """
    if can_jump_the_price(game_state, jump_fuel_cost):
        return False
    tank_price = game_state.fuel_top_up_cost()
    if tank_price <= 0.0:
        return True  # nothing for sale, and not enough in the tank to leave
    return not game_state.can_afford(tank_price)


def ending_at_port(game_state, jump_fuel_cost: float) -> str:
    """Which ending the spaceport state implies, or ``ENDING_NONE``.

    Victory first: a player who has just settled a fat fare and can no longer
    afford a tank has *won*, and reporting it as "Bankrupt!" would be a lie about
    what just happened. (Both predicates can be true at once only for a config
    where the win target is cheaper than a tank of fuel.)
    """
    if victory_reached(game_state):
        return ENDING_VICTORY
    if is_broke_at_port(game_state, jump_fuel_cost):
        return ENDING_BANKRUPT
    return ENDING_NONE


# ---------------------------------------------------------------------------
# The anti-softlock question
# ---------------------------------------------------------------------------
def can_still_burn_to_a_loss(game_state) -> bool:
    """True when the player is aloft with fuel left, so the run can still end.

    This is the half of the anti-softlock argument that is not about buttons: a
    hull flying on *some* fuel can always spend it, and the moment the tank
    empties the stranded rule judges it — either the ship is inside landing range
    (so it can land) or it is not (so it dies). There is no third branch, which is
    exactly why the "no thrust on an empty tank" gate in
    :meth:`GameState.advance_frame` matters: without it, fuel 0 would still buy
    acceleration and the loop would never close.
    """
    if game_state.is_landed or game_state.is_jumping:
        return False
    return not game_state.is_out_of_fuel()


def escape_options(game_state, jump_fuel_cost: float) -> "tuple[str, ...]":
    """What the player can still *do* from this state.

    Empty means the run is over (the caller then asks :func:`ending_in_flight` /
    :func:`ending_at_port`). The stage gate is "no reachable state where the
    player can neither jump, land, nor lose", and this function is what makes
    that question answerable instead of rhetorical: a state with no options must
    have an ending to go with it.

    The verbs are the player's, not the game's: ``jump``, ``land``, ``refuel``,
    ``launch``, ``thrust``. ``thrust`` is listed for any hull aloft with fuel,
    because spending fuel is always possible and :func:`can_still_burn_to_a_loss`
    shows where that leads. A ship in hyperspace is *between* decisions — the jump
    is paid for and the arrival frame will ask these questions again — so it has
    no options here, and the gate sweep deliberately does not sample that state.
    """
    if game_state.is_jumping:
        return ()
    if game_state.is_landed:
        # On the ground the player can always leave the ground, and the fuel they
        # carry is judged by the tank, not by the button they happen to afford.
        options = ["launch"]
        if game_state.fuel_room > 0.0:
            options.append("refuel")
        return tuple(options)

    options = []
    if can_jump_the_price(game_state, jump_fuel_cost):
        options.append("jump")
    planet_x, planet_y = PLANET_WORLD_POSITION
    if game_state.in_landing_range((planet_x, planet_y)):
        options.append("land")
    if can_still_burn_to_a_loss(game_state):
        options.append("thrust")
    return tuple(options)
