"""Stage 13 tests: the four endings, the flow back to the title, and the anti-softlock sweep.

Five layers, mirroring the split of the implementation:

* :mod:`src.model.endgame` — the pure predicates. Every ending the spec names has
  a test that constructs the state and asks the model how it died, including the
  two ordering traps the spec itself warns about: the bankruptcy check must run
  *after* the auto-unload (a fare can pay for the tank of fuel that was otherwise
  unaffordable), and the win condition must not fire from a bounty earned in
  mid-flight.
* The empty-tank rules on :class:`GameState` — a hull with a dry tank has no
  engine. Without that, "Stranded!" is a suggestion: the frame after the tank
  empties, the ship would still be accelerating for free.
* :mod:`src.model.run_stats` — the ledger the end screen reads, and the summary
  it prints.
* :class:`src.end_of_run.EndOfRun` wired into :class:`GameScene` — the stage's
  "triggers fire exactly once" gate, the exact-fuel special case, and the
  spaceport checks that a frozen tactical scene can never make on its own.
* The real :class:`FixedTimestepLoop` — the stage's second gate: a *second* new
  game must carry nothing over from the first, which is only a meaningful test
  when the first game was genuinely dirtied.

The stage gate: win/lose triggers fire exactly once; a second new game has no
leaked state from the first; no reachable state where the player can neither
jump, land, nor lose.
"""

import random
from collections import Counter

import pygame
import pygame_gui
import pytest

import main  # noqa: F401  (ensures project root is on sys.path)

from src.audio import AudioSystem
from src.config import base_config
from src.end_of_run import EndOfRun
from src.harness import RecordingAudio
from src.main_loop import FixedTimestepLoop, SCREEN_SIZE
from src.map_systems.graph import NATO_SYSTEMS
from src.model.economy import CarriedLoad
from src.model.encounter import Encounter
from src.model.endgame import (
    ENDING_BANKRUPT,
    ENDING_NONE,
    ENDING_SHIP_LOST,
    ENDING_STRANDED,
    ENDING_VICTORY,
    can_jump_the_price,
    can_still_burn_to_a_loss,
    ending_at_port,
    ending_copy,
    ending_explanation,
    ending_in_flight,
    escape_options,
    is_broke_at_port,
    is_stranded,
    victory_reached,
)
from src.model.factions import FACTION_PIRATE, FACTION_PLAYER
from src.model.game_state import GameState, PLANET_WORLD_POSITION
from src.model.npc_ship import NpcShip, roll_npc_stats
from src.model.run_stats import RunLedger, RunSummary
from src.model.weapons import Shot
from src.scene_manager import SceneManager
from src.scenes.end_screen import (
    HEADLINE_RECT,
    RETURN_BUTTON_TEXT,
    RETURN_RECT,
    SUMMARY_LINE_HEIGHT,
    SUMMARY_RECT,
    EndPalette,
    EndScreenScene,
)
from src.scenes.exit_confirm import (
    PANEL_RECT,
    SUBTITLE_LINES,
    ExitConfirmation,
)
from src.scenes.game_scene import GameScene
from src.scenes.map_view import MapView
from src.scenes.spaceport_view import SpaceportView
from src.scenes.title_screen import TitleScene

# Seeded, like every other scene-test file: an unseeded run means a different
# world, a different market board, and a different first button every time.
SCENE_SEED = 20251115

# The spec's own four headlines, quoted here rather than re-derived from the
# implementation: the strings are the contract with the player.
SPEC_STRANDED_COPY = "Stranded! Lost in space!"
SPEC_SHIP_LOST_COPY = "Ship lost with all hands!"
SPEC_BANKRUPT_COPY = "Bankrupt!"
SPEC_VICTORY_COPY = "You're a millionaire! You win!"

# A fresh run's fog of war, per the spec: Alpha plus its three guaranteed links.
START_REVEALED = frozenset({"Alpha", "Bravo", "Charlie", "Delta"})


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def scene_config(**section_tweaks) -> dict:
    """A fabricated, seeded config with no lottery in it. Never a shipped file.

    Spawn chances are zeroed so a scene test gets the fleet it asked for rather
    than a roll of the dice, and the tweaks are whole-section updates so a test
    can write ``scene_config(new_game={"starting_credits": 40})``.
    """
    config = base_config()
    config["rng"]["seed"] = SCENE_SEED
    config["npc"].update({"spawn_chance_near": 0.0, "spawn_chance_far": 0.0})
    for section, values in section_tweaks.items():
        if section not in config:
            raise KeyError(f"no such config section to tweak: {section!r}")
        config[section].update(values)
    return config


class _StackManager:
    """Enough of SceneManager for the wiring tests: config, audio, and a real stack.

    ``clear()`` and the ``pop()`` -> ``on_resume()`` handover are implemented the
    way the real manager does them, because the end screen and the exit
    confirmation both depend on that behaviour and a fake that skipped it would
    test the fake instead of the flow.
    """

    def __init__(self, config: "dict | None" = None) -> None:
        self._config = config or scene_config()
        self.audio = RecordingAudio()
        self.stack: "list" = []
        self.quit_called = False

    def game_config(self) -> dict:
        return self._config

    def push(self, scene) -> None:
        self.stack.append(scene)
        scene.on_enter(self)

    def pop(self) -> None:
        if self.stack:
            self.stack.pop().on_exit()
            if self.stack:
                self.stack[-1].on_resume()

    def clear(self) -> None:
        while self.stack:
            self.stack.pop().on_exit()

    def quit(self) -> None:
        self.quit_called = True

    @property
    def top(self):
        return self.stack[-1] if self.stack else None

    def names(self) -> "list[str]":
        return [type(scene).__name__ for scene in self.stack]

    def scenes_of(self, scene_type):
        return [scene for scene in self.stack if isinstance(scene, scene_type)]


def game_scene(config: "dict | None" = None):
    """A (GameScene, fake manager) pair: real 26-system world, market, fleet, ledger."""
    manager = _StackManager(config)
    scene = GameScene(manager)
    manager.push(scene)
    return scene, manager


def advance(scene: GameScene, frames: int) -> None:
    for _ in range(frames):
        scene.update()


def press(scene: GameScene, key: int) -> None:
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, scancode=0, mod=0))


def release(scene: GameScene, key: int) -> None:
    scene.handle_event(pygame.event.Event(pygame.KEYUP, key=key, scancode=0, mod=0))


def tap(scene: GameScene, key: int) -> None:
    """One real keypress: press, drain a frame, then release."""
    press(scene, key)
    scene.update()
    release(scene, key)


def park_ships_in_scene(scene: GameScene, *ships: NpcShip) -> Encounter:
    """Replace a scene's fleet with an exact set of hulls (see Stage 11)."""
    scene.encounter = Encounter(
        system=scene.system_map.current_system,
        ships=list(ships),
        rules=scene.npc_rules,
        system_pixel_size=scene.game_state.system_pixel_size,
        relations=scene.relations,
    )
    return scene.encounter


def hull(config: dict, faction: str, x: float, y: float) -> NpcShip:
    """One hand-placed NPC hull, variance rolled out of it."""
    return NpcShip(
        faction=faction,
        stats=roll_npc_stats(
            GameState(config).starting_stats, 1.0, 0.0, random.Random(7)
        ),
        position=(x, y),
        heading_degrees=0.0,
        velocity=(0.0, 0.0),
    )


def shot(
    faction: str,
    owner: object,
    origin: "tuple[float, float]",
    direction: "tuple[float, float]",
    *,
    power: float = 10.0,
    weapon_range: float = 3000.0,
) -> Shot:
    """A muzzle flash handed straight to the gunfight, no gun and no AI involved."""
    return Shot(
        faction=faction,
        owner=owner,
        origin=origin,
        direction=direction,
        ship_velocity=(0.0, 0.0),
        weapon_power=power,
        weapon_range=weapon_range,
    )


def open_port(scene: GameScene, manager: _StackManager) -> SpaceportView:
    """Land where the ship stands (it starts at the planet) and hand back the modal.

    The modal is looked for anywhere on the stack, not just at the top: a port that
    opens onto a bankrupt balance pushes the end screen straight over itself, which
    is the behaviour several of these tests exist to check.
    """
    tap(scene, pygame.K_l)
    ports = manager.scenes_of(SpaceportView)
    assert ports, "L did not open the spaceport"
    return ports[0]


def press_button(view, button) -> None:
    """Fire the real pygame_gui button event the widget would post."""
    view.handle_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=button))


# The real-loop helpers, same shape as tests/test_game_flow.py: a real loop, a
# real scene manager, and events posted into the real pygame queue.
def _build_flow(configs: dict):
    screen = pygame.display.get_surface()
    manager = SceneManager(screen=screen, configs=configs, audio=AudioSystem())
    manager.push(TitleScene())
    loop = FixedTimestepLoop(scene_manager=manager, screen=screen)
    return manager, loop


def _pump(loop, frames: int) -> None:
    for _ in range(frames):
        assert loop.step_once(), "the loop stopped unexpectedly"


def _click(loop, button) -> None:
    rect = button.relative_rect
    pos = (int(rect.centerx), int(rect.centery))
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEMOTION, pos=pos, rel=(1, 1), buttons=(0, 0, 0)))
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONDOWN, pos=pos, button=1, buttons=(1, 1, 1)))
    pygame.event.post(pygame.event.Event(
        pygame.MOUSEBUTTONUP, pos=pos, button=1, buttons=(0, 0, 0)))
    _pump(loop, 5)


def _press_key(loop, key: int, frames: int = 1) -> None:
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, scancode=0, mod=0))
    _pump(loop, frames)


def _release_key(loop, key: int) -> None:
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=key, scancode=0, mod=0))
    _pump(loop, 1)


def _new_game(manager, loop, difficulty: str = "medium"):
    """Click through "New game" and pick a difficulty; return the game scene."""
    title = manager._stack[-1]
    assert isinstance(title, TitleScene), f"expected the title screen, got {title!r}"
    _click(loop, title._new_game_btn)
    dialog = manager._stack[-1]
    button = next(btn for btn, (key, _) in dialog._buttons.items() if key == difficulty)
    _click(loop, button)
    return manager._stack[-1]


def _play_a_dirty_run(manager, loop) -> GameScene:
    """Fly a real run until it strands, so the "second game" test has something to leak.

    Thrust out of the planet's shadow (a jump started inside landing range is
    refused), hold ``J`` past the prompt's hold threshold, sit out the real jump
    sequence to Bravo, take a paid delivery, then run the tank dry. Every one of
    those leaves marks on the first run: fog of war, the ledger, the hold, the
    balance.
    """
    scene = _new_game(manager, loop, difficulty="medium")

    # WHEN the player flies out of the planet's shadow,
    _press_key(loop, pygame.K_UP, frames=240)
    _release_key(loop, pygame.K_UP)
    assert not scene.game_state.in_landing_range(PLANET_WORLD_POSITION), (
        "thrust never took the ship airborne"
    )

    # ...carries a contract bound for the system they are about to visit,
    scene.game_state.accept_load(
        CarriedLoad(
            destination="Bravo", fare=1234, cargo_type="wine",
            cargo_units=3, passengers=2,
        )
    )

    # ...and jumps for real,
    scene.system_map.select("Bravo")
    _press_key(loop, pygame.K_j, frames=10)
    _pump(loop, 320)
    _release_key(loop, pygame.K_j)
    assert scene.system_map.current_system == "Bravo", "the first run never left Alpha"

    # ...unloads it at Bravo's spaceport, and takes off again,
    scene.game_state.land("Bravo")
    scene.game_state.launch()

    # ...and runs the tank dry in mid-air,
    scene.game_state.fuel = 0.0
    _pump(loop, 2)

    # THEN this is the stranded ship the leak test starts from.
    assert isinstance(manager._stack[-1], EndScreenScene), "the run never stranded"
    assert scene.end_of_run.ending == ENDING_STRANDED
    return scene


# ---------------------------------------------------------------------------
# The endings, as pure rules
# ---------------------------------------------------------------------------


def test_ending_in_flight_withAFuelStarvedHullOutsideLandingRange_shouldReportStranded():
    """GIVEN a hull at zero fuel far from the planet, WHEN the rules are asked,
    THEN the answer is the spec's stranded ending."""
    scene, _ = game_scene()
    scene.game_state.set_position(600.0, 0.0)
    scene.game_state.fuel = 0.0

    assert is_stranded(scene.game_state) is True
    assert ending_in_flight(scene.game_state) == ENDING_STRANDED
    assert ending_copy(ENDING_STRANDED) == SPEC_STRANDED_COPY


def test_ending_in_flight_withAFuelStarvedHullInsideLandingRange_shouldReportNoEnding():
    """GIVEN a dry tank one keypress from the ground, WHEN the rules are asked,
    THEN nothing has ended: the player can still press L, and does not die for it.

    The spec's rule is "out of fuel *outside of landing range*". A ship that ran
    dry on the last hop in is a customer, not a castaway.
    """
    scene, _ = game_scene()
    scene.game_state.set_position(0.0, 0.0)
    scene.game_state.fuel = 0.0

    assert is_stranded(scene.game_state) is False
    assert ending_in_flight(scene.game_state) == ENDING_NONE


def test_is_stranded_withAnEmptyTankWhileLanded_shouldNotEndTheRun():
    """A ship at a spaceport with an empty tank is refuelling, not dying.

    The port's own rules (:func:`is_broke_at_port`) decide whether it can pay;
    the stranded rule must not preempt that and call the customer dead.
    """
    scene, _ = game_scene()
    scene.game_state.land("Alpha")
    scene.game_state.fuel = 0.0

    assert is_stranded(scene.game_state) is False


def test_is_stranded_withAnEmptyTankMidJump_shouldNotEndTheRun():
    """Hyperspace cannot strand anyone: the fare was paid up front, and the
    arrival is a different system with a different question to ask."""
    scene, _ = game_scene()
    scene.game_state.set_position(600.0, 0.0)
    scene.game_state.begin_jump(1.0)
    scene.game_state.fuel = 0.0

    assert is_stranded(scene.game_state) is False


def test_ending_in_flight_withZeroArmourAndAnEmptyTank_shouldReportShipLostNotStranded():
    """A hull that runs dry and catches a killing round dies of the round.

    Both predicates are true; the one the player watched happens first. A "lost
    with all hands" wreck reported as "stranded" would misname the cause of death
    on the only screen that names it.
    """
    scene, _ = game_scene()
    scene.game_state.set_position(600.0, 0.0)
    scene.game_state.fuel = 0.0
    scene.game_state.stats.armor = 0.0

    assert ending_in_flight(scene.game_state) == ENDING_SHIP_LOST
    assert ending_copy(ENDING_SHIP_LOST) == SPEC_SHIP_LOST_COPY


def test_ending_copy_withAnUnknownEnding_shouldRaiseRatherThanPrintAnEmptyHeadline():
    with pytest.raises(ValueError):
        ending_copy("mystery")
    with pytest.raises(ValueError):
        ending_explanation("mystery")


def test_ending_copy_withEveryEnding_shouldHaveAUniqueHeadline():
    """Four endings, four strings: no two may share a headline.

    "Bankrupt!" and "Ship lost with all hands!" both being, say, "Game over" would
    pass any test that only checked *an* end screen appeared.
    """
    headlines = [ending_copy(ending) for ending in
                 (ENDING_SHIP_LOST, ENDING_STRANDED, ENDING_BANKRUPT, ENDING_VICTORY)]
    assert len(set(headlines)) == 4
    assert Counter(headlines).most_common(1)[0][1] == 1
    for ending in headlines:
        assert ending


def test_victory_reached_withCreditsAtTheTarget_shouldReportVictory():
    """``>=``, not ``>``: the target is a milestone the player can hit exactly."""
    config = scene_config(economy={"win_credits": 100_000})
    scene, _ = game_scene(config)

    assert victory_reached(scene.game_state) is False
    scene.game_state.add_credits(100_000 - scene.game_state.credits)
    assert victory_reached(scene.game_state) is True


def test_ending_at_port_withCreditsAtTheWinTarget_shouldReportVictory():
    """GIVEN a millionaire standing in a spaceport, THEN the run is won.

    The spec evaluates the win only at a spaceport, which is why this predicate
    lives beside the bankruptcy rule and not in the flight poll.
    """
    config = scene_config(economy={"win_credits": 100_000})
    scene, _ = game_scene(config)
    scene.game_state.land("Alpha")
    scene.game_state.add_credits(100_000 - scene.game_state.credits)

    assert ending_at_port(scene.game_state, 250.0) == ENDING_VICTORY
    assert ending_copy(ENDING_VICTORY) == SPEC_VICTORY_COPY


def test_ending_at_port_withNothingToPayForATankAndAJumpItCannotCover_shouldReportBankrupt():
    """GIVEN broke, dry, and stuck, WHEN asked at the port, THEN: Bankrupt!"""
    config = scene_config(new_game={"starting_credits": 40})
    scene, _ = game_scene(config)
    scene.game_state.land("Alpha")
    scene.game_state.fuel = 40.0

    assert is_broke_at_port(scene.game_state, 250.0) is True
    assert ending_at_port(scene.game_state, 250.0) == ENDING_BANKRUPT
    assert ending_copy(ENDING_BANKRUPT) == SPEC_BANKRUPT_COPY


def test_ending_at_port_withAJumpWorthOfFuelAndNoCredits_shouldNotBeBankrupt():
    """More fuel than the fare, no money at all: that is a choice, not a dead end."""
    config = scene_config(new_game={"starting_credits": 0})
    scene, _ = game_scene(config)
    scene.game_state.land("Alpha")
    scene.game_state.fuel = 251.0

    assert can_jump_the_price(scene.game_state, 250.0) is True
    assert is_broke_at_port(scene.game_state, 250.0) is False
    assert ending_at_port(scene.game_state, 250.0) == ENDING_NONE


def test_ending_at_port_withExactlyTheJumpFareAndNoCredits_shouldBeBankrupt():
    """A tank that holds *exactly* the jump price is not an escape route.

    Stage 8 refuses ``J`` at exactly the fare and calls it a game over, so the
    bankruptcy rule has to agree with the jump rules rather than reading them as
    "enough is enough".
    """
    config = scene_config(new_game={"starting_credits": 0})
    scene, _ = game_scene(config)
    scene.game_state.land("Alpha")
    scene.game_state.fuel = 250.0

    assert can_jump_the_price(scene.game_state, 250.0) is False
    assert is_broke_at_port(scene.game_state, 250.0) is True


def test_ending_at_port_afterTheAutoUnloadPaysForATank_shouldNotBeBankrupt():
    """The trap the spec calls out by name: evaluate this *after* the unload.

    GIVEN a player who cannot afford a tank of fuel,
    WHEN they land and a contract bound for this system settles,
    THEN the run continues, because the fare paid for the fuel.

    Checking bankruptcy before the fares land would execute a player who was
    rescued by the landing itself.
    """
    config = scene_config(new_game={"starting_credits": 40})
    scene, _ = game_scene(config)
    scene.game_state.fuel = 40.0
    scene.game_state.accept_load(
        CarriedLoad(destination="Alpha", fare=5000, cargo_type="wine",
                    cargo_units=2, passengers=0)
    )
    tank_price = scene.game_state.fuel_top_up_cost()
    assert scene.game_state.credits < tank_price, "the test needs an unaffordable tank first"

    report = scene.game_state.land("Alpha")

    assert report.credits_gained == 5000
    assert scene.game_state.credits >= tank_price
    assert is_broke_at_port(scene.game_state, 250.0) is False
    assert ending_at_port(scene.game_state, 250.0) == ENDING_NONE


def test_ending_at_port_withATankTooSmallToCoverAJumpAndNothingToBuy_shouldBeBankrupt():
    """A config whose capacity cannot hold a jump fare must end the run, not freeze it.

    ``fuel_top_up_cost()`` is zero for a full tank, and a zero price is trivially
    "affordable", so a naive reading reports a player who can never leave as fine.
    That is the softlock the stage gate forbids, arriving through a config door.
    """
    config = scene_config(
        player_ship={"fuel_capacity": 200},
        tactical={**base_config()["tactical"], "jump": {
            **base_config()["tactical"]["jump"], "fuel_cost": 250,
        }},
    )
    scene, _ = game_scene(config)
    scene.game_state.land("Alpha")

    assert scene.game_state.fuel_room == 0.0
    assert ending_at_port(scene.game_state, 250.0) == ENDING_BANKRUPT


# ---------------------------------------------------------------------------
# The empty tank: no fuel, no engine
# ---------------------------------------------------------------------------


def test_advanceFrame_withAnEmptyTank_shouldNeverAccelerateTheHull():
    """Thrusting on empty does nothing at all — the tank is the engine's fuel.

    Without this gate, a ship at zero fuel keeps accelerating forever: the frame
    after "out of fuel" the player would still be flying, and the stranded rule
    would be describing a ship that is not stranded.
    """
    state = GameState(scene_config())
    state.set_position(600.0, 0.0)
    state.fuel = 0.0

    state.feed_input(thrust=True)
    for _ in range(120):
        state.advance_frame()

    assert state.velocity == (0.0, 0.0), "a dry hull must not accelerate for free"
    assert state.position == (600.0, 0.0)
    assert state.fuel == 0.0
    assert state.is_out_of_fuel() is True


def test_advanceFrame_withAFullTank_shouldStillAccelerateNormally():
    """The guard must not touch ordinary flight (Stage 3's contract)."""
    state = GameState(scene_config())
    state.set_position(600.0, 0.0)

    state.feed_input(thrust=True)
    for _ in range(60):
        state.advance_frame()

    assert state.velocity[0] == pytest.approx(state.stats.top_speed)
    assert state.fuel < state.stats.fuel_capacity
    assert state.is_out_of_fuel() is False


def test_advanceFrame_asTheTankEmpties_shouldBuyExactlyTheThrustItCanAfford():
    """The tank pays for thrust frame by frame, and then stops paying.

    0.4 units at the configured 0.2/frame is two frames of acceleration and no
    third: the frame the tank runs dry is the last frame the engines fire. The
    velocity the hull built up survives (Newton, as specified) — only the free
    acceleration is gone.
    """
    state = GameState(scene_config())
    state.set_position(600.0, 0.0)
    burn = state.fuel_burn_per_frame
    state.fuel = 2 * burn

    state.feed_input(thrust=True)
    state.advance_frame()
    state.advance_frame()
    last_speed = state.velocity[0]
    assert state.fuel == pytest.approx(0.0, abs=1e-12)

    for _ in range(30):
        state.advance_frame()

    assert state.velocity[0] == pytest.approx(last_speed), "no free thrust after dry"
    assert last_speed == pytest.approx(2 * state.stats.acceleration_rate)


# ---------------------------------------------------------------------------
# The anti-softlock sweep
# ---------------------------------------------------------------------------


def test_escapeOptions_overAFuelAndPositionSweep_shouldNeverOfferNothingWithoutAnEnding():
    """The stage gate: no state where the player can neither jump, land, nor lose.

    Sweeps every combination of tank level, position (inside/outside landing
    range), and landed/aloft, and asserts the invariant that matters: for every
    state, either the player has something they can still do, or an ending is
    available to fire where they stand. A state with neither is a softlock with
    the credits still on the screen.

    The per-category tally at the end is not decoration: a sweep whose samples are
    all trivially fine proves nothing, so it asserts it actually reached the
    stranded, the broke-at-port, and the perfectly-healthy states too.
    """
    jump_fuel_cost = 250.0
    scene, _ = game_scene()
    state = scene.game_state
    landing_range = state.landing_range
    capacity = state.stats.fuel_capacity

    inside = [(0.0, 0.0), (landing_range - 1.0, 0.0)]
    outside = [(600.0, 0.0), (landing_range + 5.0, 0.0), (state.system_pixel_size / 2, 0.0)]
    fuels = [0.0, 1.0, jump_fuel_cost - 1.0, jump_fuel_cost,
             jump_fuel_cost + 1.0, capacity]

    # "Broke" is a state a run can reach, so it gets its own config rather than a
    # poke at a read-only property: credits are the model's to hand out.
    purses = [
        ("broke", scene_config(new_game={"starting_credits": 0})),
        ("funded", scene_config()),
    ]

    resolved = Counter()
    for landed in (False, True):
        for x, y in inside + outside:
            for fuel in fuels:
                for purse, purse_config in purses:
                    # GIVEN one combination, rebuilt from scratch each time so no
                    # leftover of the previous sample can answer the question.
                    probe = GameState(purse_config)
                    probe.set_position(x, y)
                    probe.fuel = fuel
                    if landed:
                        probe.land("Alpha")

                    options = escape_options(probe, jump_fuel_cost)
                    in_flight_ending = ending_in_flight(probe)
                    port_ending = ending_at_port(probe, jump_fuel_cost)

                    # THEN at least one of the player's verbs is available, or an
                    # ending is available to fire in the place where the player is.
                    assert options or in_flight_ending or port_ending, (
                        f"softlock: landed={landed} pos=({x}, {y}) fuel={fuel} "
                        f"purse={purse} options={options} "
                        f"in_flight={in_flight_ending} port={port_ending}"
                    )

                    if options:
                        resolved["options"] += 1
                    if in_flight_ending:
                        resolved["in_flight_ending"] += 1
                    if port_ending:
                        resolved["port_ending"] += 1
                    if not options and not port_ending:
                        resolved["nothingButALoss"] += 1
                    if "thrust" in options:
                        assert can_still_burn_to_a_loss(probe) is True, (
                            "a state that offers thrust must be able to burn to a loss"
                        )

    assert resolved["in_flight_ending"], "the sweep never reached a stranded state"
    assert resolved["port_ending"], "the sweep never reached a broke-at-port state"
    assert resolved["nothingButALoss"], "the sweep never checked a state with no verbs left"
    assert resolved["options"] > 20, "the sweep barely covered the playable states"


def test_burningFuelAwayFromThePlanet_shouldAlwaysResolveIntoALandingOrALoss():
    """The behavioural half of the anti-softlock gate.

    GIVEN a hull aloft with some fuel, WHEN it thrusts until the tank is dry (or
    the planet is close enough to touch), THEN at every single frame it either has
    a verb left or the run has ended, and when the pumping stops it is either
    inside landing range or the run has ended. There is no third outcome, which is
    what makes "fuel left but nowhere to go" unreachable.

    The invariant is checked every frame rather than only at the end: a state the
    player can occupy for one frame is a state they can be stuck in.
    """
    samples = [
        (600.0, 0.0, 40.0),      # too little fuel to get anywhere: it must die
        (-600.0, 0.0, 400.0),    # heading east, straight at the planet
        (0.0, -700.0, 400.0),    # south of the planet, thrusting away from it
        (900.0, 900.0, 20.0),    # a corner of the system, nearly dry
    ]
    for x, y, fuel in samples:
        scene, _ = game_scene()
        state = scene.game_state
        state.set_position(x, y)
        state.fuel = fuel
        press(scene, pygame.K_UP)  # heading 0 faces east and never turns

        # Enough frames to burn the whole tank, plus the slack to drift out of (or
        # into) landing range afterwards.
        frames_available = int(fuel / state.fuel_burn_per_frame) + 120
        for frame in range(frames_available):
            scene.update()
            assert escape_options(state, scene.jumps.params.fuel_cost) or scene.end_of_run.ended, (
                f"stuck mid-burn at frame {frame}: pos={state.position} "
                f"fuel={state.fuel} ending={scene.end_of_run.ending!r}"
            )
            if scene.end_of_run.ended:
                break

        at_home = state.in_landing_range(PLANET_WORLD_POSITION)
        assert at_home or scene.end_of_run.ended, (
            f"stuck: from ({x}, {y}) with {fuel} fuel: "
            f"pos={state.position} fuel={state.fuel} "
            f"ending={scene.end_of_run.ending!r}"
        )
        if scene.end_of_run.ended:
            assert scene.end_of_run.ending == ENDING_STRANDED


def test_escapeOptions_withAFullTankAtThePlanet_shouldOfferEveryVerbAtOnce():
    """The ordinary case: a healthy ship has all its doors open, so no ending applies."""
    scene, _ = game_scene()
    scene.game_state.set_position(0.0, 0.0)

    assert set(escape_options(scene.game_state, 250.0)) == {"jump", "land", "thrust"}
    assert ending_in_flight(scene.game_state) == ENDING_NONE


def test_escapeOptions_withADryTankAwayFromThePlanet_shouldOfferNothingAndEndTheRun():
    """The stranded state has no options at all — which is exactly why it ends."""
    scene, _ = game_scene()
    scene.game_state.set_position(600.0, 0.0)
    scene.game_state.fuel = 0.0

    assert escape_options(scene.game_state, 250.0) == ()
    assert ending_in_flight(scene.game_state) == ENDING_STRANDED


# ---------------------------------------------------------------------------
# The run ledger and the summary it feeds
# ---------------------------------------------------------------------------


def test_runLedger_recordingEveryEvent_shouldAccumulateTheRunsNumbers():
    ledger = RunLedger()
    ledger.record_jump()
    ledger.record_jump()
    ledger.record_delivery(credits=1200, cargo_units=3, passengers=1)
    ledger.record_delivery(credits=300, cargo_units=0, passengers=2)
    ledger.record_bounty(10000)
    ledger.record_kill()
    ledger.record_purchase(1900)
    ledger.record_frames(600)

    assert ledger.jumps == 2
    assert ledger.contracts_delivered == 2
    assert ledger.cargo_delivered == 3
    assert ledger.passengers_delivered == 3
    assert ledger.fare_credits == 1500
    assert ledger.credits_earned == 11500
    assert ledger.credits_spent == 1900
    assert ledger.hulls_destroyed == 1
    assert ledger.clock() == "00:10"


def test_runLedger_withANegativeAmount_shouldRefuseRatherThanErasetheRun():
    """A negative "delivery" would be a way to lose credits in the run summary,
    which is the same back door ``add_credits`` refuses."""
    ledger = RunLedger()
    with pytest.raises(ValueError):
        ledger.record_delivery(credits=-1, cargo_units=1, passengers=0)
    with pytest.raises(ValueError):
        ledger.record_purchase(-5)
    with pytest.raises(ValueError):
        ledger.record_kill(-1)
    with pytest.raises(ValueError):
        ledger.record_frames(-1)


def test_runLedger_copy_shouldBeIndependentOfTheRun():
    ledger = RunLedger()
    ledger.record_jump()
    snapshot = ledger.copy()
    ledger.record_jump()

    assert snapshot.jumps == 1
    assert ledger.jumps == 2


def test_land_withAPaidDelivery_shouldRecordTheFareCargoAndPassengersExactlyOnce():
    """The ledger is fed by the model that settles the fare, not by the screen that shows it."""
    scene, _ = game_scene()
    scene.game_state.accept_load(
        CarriedLoad(destination="Alpha", fare=800, cargo_type="iron ore",
                    cargo_units=4, passengers=2)
    )

    scene.game_state.land("Alpha")
    scene.game_state.land("Alpha")  # the same hold again: pays nothing, records nothing

    ledger = scene.game_state.ledger
    assert ledger.contracts_delivered == 1
    assert ledger.cargo_delivered == 4
    assert ledger.passengers_delivered == 2
    assert ledger.fare_credits == 800


def test_purchasePaths_shouldRecordEveryCreditThePortsTook():
    scene, _ = game_scene()
    scene.game_state.spend_fuel(50)       # make room to buy anything back
    # Shield-first damage, so this has to punch through the shields to reach the
    # armour the port is about to charge for.
    scene.game_state.apply_damage(scene.game_state.stats.shields + 10)
    assert scene.game_state.buy_fuel(10).succeeded
    assert scene.game_state.repair_armor(5).succeeded

    assert scene.game_state.ledger.credits_spent == pytest.approx(40.0)


def test_runSummary_fromRun_shouldReadTheLedgerAndTheMapNotReDeriveThem():
    config = scene_config(economy={"win_credits": 5000})
    scene, _ = game_scene(config)
    state = scene.game_state
    state.accept_load(
        CarriedLoad(destination="Alpha", fare=800, cargo_type="wine",
                    cargo_units=2, passengers=3)
    )
    state.land("Alpha")
    state.ledger.record_jump()
    state.ledger.record_bounty(10000)
    state.ledger.record_kill()
    state.ledger.record_purchase(1900)
    state.ledger.record_frames(60 * 75)

    summary = RunSummary.from_run(
        ending=ENDING_VICTORY,
        game_state=state,
        systems_revealed=len(scene.system_map.revealed),
        systems_total=len(scene.system_map.graph.names),
        current_system=scene.system_map.current_system,
    )

    assert summary.ending == ENDING_VICTORY
    assert summary.systems_revealed == len(scene.system_map.revealed)
    assert summary.systems_total == len(NATO_SYSTEMS)
    assert summary.current_system == "Alpha"
    assert summary.jumps == 1
    assert summary.hulls_destroyed == 1
    assert summary.clock == "01:15"
    assert summary.credits_earned == pytest.approx(10800.0)


def test_runSummary_pairs_shouldPrintOneLabelAndValuePerStatWithNoBlanks():
    """The stat block the end screen paints: nine rows, all of them meaningful.

    Asserted on pairs rather than pixels because the pairs *are* what the renderer
    draws — a test here is a test on the screen.
    """
    summary = RunSummary(
        ending=ENDING_STRANDED, credits=1234.0, win_credits=1_000_000.0,
        systems_revealed=4, systems_total=26, current_system="Zulu", jumps=3,
        contracts_delivered=2, cargo_delivered=5, passengers_delivered=7,
        fare_credits=1000.0, bounty_credits=5000.0, credits_earned=6000.0,
        credits_spent=900.0, hulls_destroyed=1, clock="04:20",
    )
    pairs = summary.pairs()

    assert len(pairs) == 9
    labels = [label for label, _ in pairs]
    assert len(set(labels)) == len(labels), "two stats sharing a label"
    for label, value in pairs:
        assert label and value, f"empty cell in the summary: {label!r}"
    values = dict(pairs)
    assert values["Systems discovered"] == "4 of 26"
    assert "1,234" in values["Final balance"]
    assert "1,000,000" in values["Final balance"]
    assert values["Contracts delivered"] == "2 (5 cargo, 7 passenger(s))"
    assert "5,000 bounties" in values["Credits earned"]


def test_runSummary_pairs_withANoWinsRun_shouldStillFillEveryCell():
    """A run that delivered nothing and killed nobody prints zeros, not gaps."""
    summary = RunSummary(
        ending=ENDING_SHIP_LOST, credits=0.0, win_credits=1_000_000.0,
        systems_revealed=1, systems_total=26, current_system="Alpha", jumps=0,
        contracts_delivered=0, cargo_delivered=0, passengers_delivered=0,
        fare_credits=0.0, bounty_credits=0.0, credits_earned=0.0,
        credits_spent=0.0, hulls_destroyed=0, clock="00:00",
    )
    values = dict(summary.pairs())

    assert values["Contracts delivered"] == "0"
    assert values["Credits earned"] == "0 credits"
    assert values["Jumps made"] == "0"


# ---------------------------------------------------------------------------
# EndOfRun: exactly once, and in the right place
# ---------------------------------------------------------------------------


def test_endOfRun_withNeitherManagerNorMap_shouldRefuseToBuild():
    """A coordinator that cannot push a screen is a rule with no consequence."""
    state = GameState(scene_config())
    scene, manager = game_scene()
    with pytest.raises(ValueError):
        EndOfRun(None, state, scene.system_map, 250.0)
    with pytest.raises(ValueError):
        EndOfRun(manager, state, None, 250.0)
    with pytest.raises(ValueError):
        EndOfRun(manager, state, scene.system_map, -1.0)


def test_update_withTheTanksDryOutsideLandingRange_shouldRaiseTheEndScreenOnce():
    """The stage gate, loss side: one stranded ship, one end screen, many frames.

    GIVEN a run flying on empty outside landing range,
    WHEN the scene is advanced for a hundred more frames,
    THEN exactly one :class:`EndScreenScene` is on the stack and the run's own
    scenes have not been replaced under it.
    """
    scene, manager = game_scene()
    scene.game_state.set_position(600.0, 0.0)
    scene.game_state.fuel = 0.0

    advance(scene, 100)

    screens = manager.scenes_of(EndScreenScene)
    assert len(screens) == 1, f"{len(screens)} end screens pushed for one stranded ship"
    assert screens[0].headline == SPEC_STRANDED_COPY
    assert scene.end_of_run.ending == ENDING_STRANDED
    assert manager.names() == ["GameScene", "EndScreenScene"]


def test_update_asTheTankBurnsToEmpty_shouldStrandTheRunOnTheFrameItRunsDry():
    """The trigger is the tank emptying, not a later inspection of it."""
    scene, manager = game_scene()
    scene.game_state.set_position(600.0, 0.0)
    scene.game_state.fuel = 0.4  # two frames at 0.2/frame

    press(scene, pygame.K_UP)
    advance(scene, 1)
    assert scene.end_of_run.ended is False, "the run ended with fuel still in the tank"
    advance(scene, 1)

    assert scene.end_of_run.ending == ENDING_STRANDED
    assert scene.game_state.fuel == pytest.approx(0.0, abs=1e-12)
    assert scene.tactical.input.locked is True


def test_update_withTheTanksDryInsideLandingRange_shouldNotEndTheRun():
    """A dry tank in the landing bubble is a landing, not a death sentence."""
    scene, manager = game_scene()
    scene.game_state.fuel = 0.0

    advance(scene, 30)

    assert scene.end_of_run.ended is False
    assert manager.names() == ["GameScene"]


def test_update_withTheHullDestroyed_shouldRaiseTheShipLostScreenAndKeepTheLatch():
    """Stage 11's flag and Stage 13's screen are one fact, not two.

    ``pending_game_over`` used to be a boolean attribute this scene wrote; it is
    now read from the coordinator's latch, which is what lets the once-only gate
    be true without two records of the same death disagreeing.
    """
    config = scene_config()
    scene, manager = game_scene(config)
    scene.game_state.set_position(0.0, 0.0)
    pirate = hull(config, FACTION_PIRATE, 40.0, 0.0)
    park_ships_in_scene(scene, pirate)
    scene.gunfight.launch(
        shot(FACTION_PIRATE, pirate, (0.0, 0.0), (1.0, 0.0), power=10_000.0)
    )

    advance(scene, 3)

    assert scene.pending_game_over is True
    assert scene.end_of_run.ending == ENDING_SHIP_LOST
    screens = manager.scenes_of(EndScreenScene)
    assert len(screens) == 1
    assert screens[0].headline == SPEC_SHIP_LOST_COPY


def test_update_afterTheRunEnds_shouldNotLetTheHullKeepTakingTurns():
    """The end screen sits on top of the stack, so the tactical view stops updating.

    Driven through the real loop: pushing a scene during ``update()`` must not
    leave the run simulating underneath its own funeral.
    """
    configs = {"config_medium.json": scene_config()}
    manager, loop = _build_flow(configs)
    scene = _new_game(manager, loop)
    scene.game_state.set_position(600.0, 0.0)
    scene.game_state.fuel = 0.0
    _pump(loop, 3)

    frozen = (scene.game_state.position, scene.game_state.velocity)
    _pump(loop, 60)

    assert isinstance(manager._stack[-1], EndScreenScene)
    assert scene.game_state.position == frozen[0]
    assert scene.game_state.velocity == frozen[1]
    assert manager.update is not None  # the stack still has exactly one top scene
    assert len(manager._stack) == 2


def test_requestJump_withExactlyTheJumpFuelCost_shouldEndTheRunAsStranded():
    """Stage 8's special case, finished: the jump is refused, the fuel is not
    spent, and the run ends with the stranded headline rather than a banner."""
    scene, manager = game_scene()
    scene.game_state.set_position(600.0, 0.0)
    scene.system_map.select("Bravo")
    scene.game_state.fuel = scene.jumps.params.fuel_cost
    fuel_before = scene.game_state.fuel

    press(scene, pygame.K_j)
    scene.update()
    release(scene, pygame.K_j)

    assert scene.jumps.is_active is False
    assert scene.game_state.fuel == fuel_before, "a refused jump must never spend fuel"
    assert scene.end_of_run.ending == ENDING_STRANDED
    assert manager.scenes_of(EndScreenScene)[0].headline == SPEC_STRANDED_COPY
    assert scene.pending_game_over is True


def test_requestJump_withExactlyTheJumpFuelCostInsideLandingRange_shouldNotEndTheRun():
    """The ordering trap, Stage 13 side: a jump that was already illegal for a
    different reason must not kill the player for the fuel as well."""
    scene, manager = game_scene()
    scene.game_state.set_position(0.0, 0.0)
    scene.system_map.select("Bravo")
    scene.game_state.fuel = scene.jumps.params.fuel_cost

    press(scene, pygame.K_j)
    scene.update()
    release(scene, pygame.K_j)
    advance(scene, 5)

    assert scene.pending_game_over is False
    assert manager.names() == ["GameScene"]


def test_endOfRun_latch_shouldKeepTheFirstDeathRatherThanTheLoudest():
    """Two deaths in one frame is one ending: the one the player is owed first."""
    state = GameState(scene_config())
    scene, manager = game_scene()
    coordinator = EndOfRun(manager, state, scene.system_map, 250.0)

    coordinator.latch(ENDING_SHIP_LOST)
    coordinator.latch(ENDING_STRANDED)

    assert coordinator.pending_ending == ENDING_SHIP_LOST
    assert coordinator.poll_flight() == ENDING_SHIP_LOST
    assert coordinator.pending_ending == ENDING_NONE, "the latch must be cleared on show"
    assert coordinator.poll_flight() == ENDING_NONE


def test_openSpaceport_withADryTankAndNoCredits_shouldEndTheRunInsideThePort():
    """Bankruptcy is evaluated by the landing, not by the next frame of play.

    The tactical scene is frozen while the spaceport modal owns the stack, so a
    check left to ``GameScene.update()`` would never run and the player would sit
    in a spaceport with nothing to buy forever.
    """
    config = scene_config(new_game={"starting_credits": 40})
    scene, manager = game_scene(config)
    scene.game_state.fuel = 40.0

    open_port(scene, manager)

    assert manager.names() == ["GameScene", "SpaceportView", "EndScreenScene"]
    assert manager.scenes_of(EndScreenScene)[0].headline == SPEC_BANKRUPT_COPY
    assert scene.end_of_run.ending == ENDING_BANKRUPT


def test_openSpaceport_withADeliveryThatPaysForATank_shouldKeepTheRunAlive():
    """The same state, one contract richer: the unload paid, so the run goes on."""
    config = scene_config(new_game={"starting_credits": 40})
    scene, manager = game_scene(config)
    scene.game_state.fuel = 40.0
    scene.game_state.accept_load(
        CarriedLoad(destination="Alpha", fare=9000, cargo_type="wine",
                    cargo_units=1, passengers=0)
    )

    port = open_port(scene, manager)

    assert scene.end_of_run.ended is False
    assert manager.names() == ["GameScene", "SpaceportView"]
    assert port.message == "Unloaded 1 cargo unit at Alpha: +9,000 credits."


def test_portTransaction_thatMakesTheNextTankUnaffordable_shouldEndTheRunOnThatClick():
    """Buying an upgrade can be the purchase that strands a run: the port must say so.

    GIVEN a player who can just afford a tank of fuel,
    WHEN they spend enough of the balance on an upgrade that they can no longer,
    THEN the end screen appears over the spaceport, on the frame of the click.
    """
    config = scene_config(new_game={"starting_credits": 2100})
    scene, manager = game_scene(config)
    scene.game_state.fuel = 50.0
    port = open_port(scene, manager)
    assert scene.end_of_run.ended is False
    tank_price = scene.game_state.fuel_top_up_cost()
    assert scene.game_state.can_afford(tank_price), "the tank must start affordable"

    button, offer = next(iter(port._buy_buttons.items()))
    assert offer.level == 1
    press_button(port, button)

    assert not scene.game_state.can_afford(tank_price), "the purchase must have hurt"
    assert manager.scenes_of(EndScreenScene)[0].headline == SPEC_BANKRUPT_COPY
    assert scene.end_of_run.ending == ENDING_BANKRUPT
    assert manager.names() == ["GameScene", "SpaceportView", "EndScreenScene"]


def test_bountyCreditsPastTheWinTargetInFlight_shouldNotWinUntilThePlayerLands():
    """The spec's other half: a bounty that crosses the line does not end the game.

    GIVEN a run whose balance passes ``economy.win_credits`` mid-flight,
    WHEN the tactical scene keeps updating,
    THEN nothing has ended; and when the player finally lands, they win.
    """
    config = scene_config(economy={"win_credits": 1000})
    scene, manager = game_scene(config)
    scene.game_state.set_position(600.0, 0.0)
    scene.game_state.add_credits(2000)

    # WHEN the tactical scene keeps updating in mid-air,
    advance(scene, 10)

    # THEN the target has been passed, but nothing has ended:
    assert victory_reached(scene.game_state) is True
    assert scene.end_of_run.ended is False, "the win fired in mid-air"
    assert manager.names() == ["GameScene"]

    # ...and WHEN the player finally reaches a spaceport,
    # THEN that is where the win fires.
    scene.game_state.set_position(0.0, 0.0)
    open_port(scene, manager)
    assert scene.end_of_run.ending == ENDING_VICTORY
    assert manager.scenes_of(EndScreenScene)[0].headline == SPEC_VICTORY_COPY


def test_endOfRun_summary_shouldCountTheJumpsAndKillsTheSceneActuallyDid():
    """The ledger is fed at the events, so the end screen reports the run it ended."""
    config = scene_config()
    scene, manager = game_scene(config)
    scene.game_state.set_position(600.0, 0.0)
    scene.system_map.select("Bravo")
    press(scene, pygame.K_j)
    advance(scene, 1)
    release(scene, pygame.K_j)
    advance(scene, 300)

    assert scene.system_map.current_system == "Bravo"

    scene.game_state.set_position(0.0, 0.0)
    bobber = hull(config, "bobber", 60.0, 0.0)
    park_ships_in_scene(scene, bobber)
    scene.gunfight.launch(
        shot(FACTION_PLAYER, scene.game_state, (0.0, 0.0), (1.0, 0.0),
             power=10_000.0)
    )
    advance(scene, 5)

    ledger = scene.game_state.ledger
    assert ledger.jumps == 1
    assert ledger.hulls_destroyed == 1
    assert ledger.bounty_credits == 5000, "the bobber bounty should have been paid"
    assert ledger.cargo_delivered == 0


# ---------------------------------------------------------------------------
# The end screen itself
# ---------------------------------------------------------------------------


def test_endScreenScene_shouldOfferTheButtonsTheSpecNames():
    """The label is the spec's, and ESC is the spec's other way out."""
    scene, manager = game_scene()
    scene.game_state.set_position(600.0, 0.0)
    scene.game_state.fuel = 0.0
    advance(scene, 2)
    screen = manager.scenes_of(EndScreenScene)[0]

    assert RETURN_BUTTON_TEXT == "Return to title screen"
    assert screen._return_button.text == RETURN_BUTTON_TEXT


def test_endScreenScene_clickingReturnToTitle_shouldLeaveExactlyTheTitleScreen():
    """One click, one scene: every scene of the finished run is gone.

    Popping would leave the tactical view (and, behind it, a spaceport) on the
    stack, and a run's scenes surviving a run is a save file nobody designed.
    """
    scene, manager = game_scene(scene_config(new_game={"starting_credits": 40}))
    open_port(scene, manager)  # a modal under the end screen, to be cleared too
    scene.game_state.fuel = 40.0
    scene.end_of_run.poll_at_port()
    assert manager.names() == ["GameScene", "SpaceportView", "EndScreenScene"]

    screen = manager.scenes_of(EndScreenScene)[0]
    press_button(screen, screen._return_button)

    assert manager.names() == ["TitleScene"]


def test_endScreenScene_pressingEscape_shouldReturnToTheTitleScreen():
    scene, manager = game_scene()
    scene.game_state.set_position(600.0, 0.0)
    scene.game_state.fuel = 0.0
    advance(scene, 2)
    screen = manager.scenes_of(EndScreenScene)[0]

    screen.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE,
                                           scancode=0, mod=0))

    assert manager.names() == ["TitleScene"]


def test_endScreenScene_withAnUnknownEnding_shouldFailWhenBuiltNotWhenDrawn():
    with pytest.raises(ValueError):
        EndScreenScene("catastrophe", RunSummary(
            ending="catastrophe", credits=0.0, win_credits=1.0, systems_revealed=1,
            systems_total=26, current_system="Alpha", jumps=0,
            contracts_delivered=0, cargo_delivered=0, passengers_delivered=0,
            fare_credits=0.0, bounty_credits=0.0, credits_earned=0.0,
            credits_spent=0.0, hulls_destroyed=0, clock="00:00",
        ))


def test_endScreenScene_draw_shouldPaintTheHeadlineAndEveryStatInsideTheWindow():
    """Geometry: nothing runs off the window or under the button."""
    screen, manager = game_scene()
    screen.game_state.set_position(600.0, 0.0)
    screen.game_state.fuel = 0.0
    advance(screen, 2)
    end = manager.scenes_of(EndScreenScene)[0]

    canvas = pygame.Surface(SCREEN_SIZE)
    canvas.fill((1, 2, 3))
    end.draw(canvas)

    window = pygame.Rect(0, 0, *SCREEN_SIZE)
    assert window.contains(HEADLINE_RECT)
    assert window.contains(RETURN_RECT)
    last_row_top = SUMMARY_RECT.top + SUMMARY_LINE_HEIGHT * (len(end.summary.pairs()) - 1)
    assert last_row_top + SUMMARY_LINE_HEIGHT <= RETURN_RECT.top, (
        "the stat block runs into the button"
    )

    # Something was painted: headline, explanation, nine stat rows, and a button.
    painted = sum(
        1
        for y in range(0, SCREEN_SIZE[1], 4)
        for x in range(0, SCREEN_SIZE[0], 4)
        if canvas.get_at((x, y))[:3] != (1, 2, 3)
    )
    assert painted > 200, "the end screen drew almost nothing"


# ---------------------------------------------------------------------------
# The "Exit game?" confirmation (optional pause-to-title)
# ---------------------------------------------------------------------------


def test_exitConfirmation_ESCWhileFlying_shouldOpenTheConfirmationNotEndTheRun():
    scene, manager = game_scene()
    scene.game_state.set_position(600.0, 0.0)

    tap(scene, pygame.K_ESCAPE)

    assert manager.names() == ["GameScene", "ExitConfirmation"]
    assert scene.end_of_run.ended is False


def test_exitConfirmation_ESCWhileJumping_shouldBeIgnored():
    """Mid-jump the player cannot steer and cannot cancel; offering an exit from a
    system they are already paying to reach is a third way to be lied to."""
    scene, manager = game_scene()
    scene.game_state.set_position(600.0, 0.0)
    scene.system_map.select("Bravo")
    press(scene, pygame.K_j)
    scene.update()
    release(scene, pygame.K_j)
    advance(scene, 3)

    tap(scene, pygame.K_ESCAPE)

    assert scene.jumps.is_active is True
    assert manager.names() == ["GameScene"]


def test_exitConfirmation_keepPlaying_shouldResumeTheRunAndLeaveTheKeyboardWorking():
    """The phantom-key trap, Stage 13 edition.

    The press that opened this dialog never had its release seen by the tactical
    input layer, so without ``SceneManager.pop()`` waking the scene below, ESC (or
    ``M``) would work every other time.
    """
    scene, manager = game_scene()
    tap(scene, pygame.K_ESCAPE)
    dialog = manager.top

    dialog.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE,
                                           scancode=0, mod=0))

    assert manager.names() == ["GameScene"]
    assert scene.tactical.input._held == set(), "the dialog left a phantom key behind"

    # And the next ESC opens the dialog again, rather than vanishing into a held key.
    tap(scene, pygame.K_ESCAPE)
    assert isinstance(manager.top, ExitConfirmation)


def test_exitConfirmation_returnToTitle_shouldClearTheWholeRunAway():
    scene, manager = game_scene()
    open_port(scene, manager)
    tap(scene, pygame.K_ESCAPE)
    assert manager.names() == ["GameScene", "SpaceportView", "ExitConfirmation"]

    dialog = manager.top
    press_button(dialog, dialog._return_button)

    assert manager.names() == ["TitleScene"]


def test_exitConfirmation_subtitle_shouldFitInsideThePanelItIsDrawnOn():
    """Authored copy is only allowed to be pre-wrapped if somebody measures it."""
    from src.fonts import game_font

    for line in SUBTITLE_LINES:
        width, _ = game_font(15).size(line)
        assert width <= PANEL_RECT.width - 40, f"subtitle line runs out of the panel: {line!r}"


def test_realLoop_pressingEscapeInTactical_thenReturnToTitle_shouldEndTheRun():
    """The same flow through the real loop, where the stack and the events are real."""
    manager, loop = _build_flow({"config_medium.json": scene_config()})
    scene = _new_game(manager, loop)
    scene.game_state.set_position(600.0, 0.0)

    _press_key(loop, pygame.K_ESCAPE)
    _release_key(loop, pygame.K_ESCAPE)
    assert isinstance(manager._stack[-1], ExitConfirmation)

    dialog = manager._stack[-1]
    _click(loop, dialog._return_button)

    assert len(manager._stack) == 1
    assert isinstance(manager._stack[-1], TitleScene)
    _pump(loop, 5)  # the title screen repaints without the game scene under it


# ---------------------------------------------------------------------------
# Gate: a second new game carries nothing over from the first
# ---------------------------------------------------------------------------


def test_secondNewGame_afterAFullRun_shouldStartCleanInEveryObservableWay():
    """The stage gate, spelled out because "no leaked state" is not one assertion.

    GIVEN a run that flew, jumped, delivered, and finally stranded,
    WHEN the player returns to the title screen from the end screen and starts a
    new game,
    THEN the new run has none of the old run's numbers, charts, hold, grudges, or
    corpse.
    """
    manager, loop = _build_flow({"config_medium.json": scene_config()})
    first = _play_a_dirty_run(manager, loop)

    # GIVEN the first run really was dirty (otherwise this test proves nothing).
    assert first.system_map.current_system == "Bravo"
    assert first.system_map.revealed > START_REVEALED
    assert first.game_state.ledger.jumps == 1
    assert first.game_state.ledger.cargo_delivered == 3
    assert first.pending_game_over is True

    screen = [s for s in manager._stack if isinstance(s, EndScreenScene)][-1]
    _click(loop, screen._return_button)
    assert len(manager._stack) == 1 and isinstance(manager._stack[-1], TitleScene)

    second = _new_game(manager, loop, difficulty="medium")
    assert second is not first
    _pump(loop, 2)

    # THEN: money, hold, hull, and upgrades are all exactly as a new game configures.
    state = second.game_state
    assert state.credits == pytest.approx(20000.0)
    assert state.cargo_used == 0
    assert state.passengers_used == 0
    assert state.carried_loads == []
    assert state.fuel == pytest.approx(state.stats.fuel_capacity)
    assert state.stats.shields == state.starting_stats.shields
    assert state.stats.armor == state.starting_stats.armor
    assert state.destroyed is False
    assert state.is_landed is False
    assert state.is_jumping is False
    assert all(level == 0 for level in state.upgrade_levels.values())

    # THEN: the ledger is empty, so the end screen has nothing to remember.
    assert state.ledger.jumps == 0
    assert state.ledger.credits_spent == 0.0
    assert state.ledger.contracts_delivered == 0
    assert state.ledger.credits_earned == 0.0
    assert state.ledger.frames_flown > 0, "the new run is not being simulated at all"

    # THEN: fog of war is back to the four systems a new game reveals.
    assert second.system_map.current_system == "Alpha"
    assert second.system_map.selected_system is None
    assert frozenset(second.system_map.revealed) == START_REVEALED

    # THEN: nobody hates the player, nothing is scanning, nothing is flying.
    assert second.relations.factions_hostile_to_player == {FACTION_PIRATE}
    assert second.scanner.displayed is None
    assert list(second.encounter.ships) == []
    assert len(second.gunfight) == 0
    assert second.jumps.phase == "idle"
    assert second.end_of_run.ended is False
    assert second.pending_game_over is False

    # THEN: the market board and the lore are the new game's own, not the old one's.
    assert second.port_visit.system == "Alpha"
    assert second.lore.line_for("Alpha")

    # AND the first run's coordinator did not follow it into the new game.
    assert first.end_of_run.ended is True
    assert first.system_map.current_system == "Bravo"


def _end_screen_residue(canvas) -> "list[tuple[int, int]]":
    """Sampled pixels that still carry one of the end screen's own colours.

    A 3px grid: the headline glyphs are 44px tall, so a step of 3 lands well
    inside a glyph, and the colours watched for are the end screen's accent red,
    its win green, and its rule grey — none of which the title screen paints.
    """
    watched = (EndPalette.lost, EndPalette.won, EndPalette.rule)
    return [
        (x, y)
        for y in range(HEADLINE_RECT.top, RETURN_RECT.bottom, 3)
        for x in range(0, SCREEN_SIZE[0], 3)
        if canvas.get_at((x, y))[:3] in watched
    ]


def test_returnToTitle_fromTheEndScreen_leavesNoGameOverPixelsOnTheTitleScreen():
    """The end screen is a full-window repaint, so the title must erase it.

    The Stage 2 review found a cancelled dialog that stayed on screen forever
    because the title scene "cleared" by compositing a translucent image over it.
    An end screen with a red headline is the same bug with more contrast.

    The positive control is not decoration: without a check that the probe *can*
    see the end screen while it is up, this is a scan for colours that were never
    on screen, i.e. a test that cannot fail.
    """
    manager, loop = _build_flow({"config_medium.json": scene_config()})
    scene = _play_a_dirty_run(manager, loop)
    screen = [s for s in manager._stack if isinstance(s, EndScreenScene)][-1]
    canvas = pygame.display.get_surface()

    # GIVEN the end screen is actually on the surface being probed,
    painted = _end_screen_residue(canvas)
    assert len(painted) > 20, (
        "the probe found no end-screen pixels while the end screen was up: "
        f"{painted[:5]}"
    )

    # WHEN the player takes the way out,
    _click(loop, screen._return_button)
    _pump(loop, 8)

    # THEN the title screen has erased every trace of the finished run.
    residue = _end_screen_residue(canvas)
    assert not residue, f"end-screen colours survived the return to title: {residue[:5]}"
    assert isinstance(manager._stack[-1], TitleScene)


def test_realLoop_mapModal_shouldReopenAfterBeingClosedWithEscape():
    """``M`` -> ESC -> ``M`` must open the map again, not swallow the keypress.

    Every modal in this game that opens on a keypress inherits the phantom-key
    trap; the map is the one that has always had it, and Stage 13's
    ``Scene.on_resume`` is what fixes it. Left in this file because the fix is
    Stage 13's and the gate is "the flow works".
    """
    manager, loop = _build_flow({"config_medium.json": scene_config()})
    _new_game(manager, loop)

    _press_key(loop, pygame.K_m)
    _release_key(loop, pygame.K_m)
    assert isinstance(manager._stack[-1], MapView)

    _press_key(loop, pygame.K_ESCAPE)
    _release_key(loop, pygame.K_ESCAPE)
    assert len(manager._stack) == 1

    _press_key(loop, pygame.K_m)
    _release_key(loop, pygame.K_m)
    assert isinstance(manager._stack[-1], MapView), "the second M press was swallowed"
