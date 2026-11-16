"""Stage 8 tests: jumping - eligibility, a frame-exact animation, and arrival.

Five layers, mirroring the split of the implementation:

* :mod:`src.model.jump` - the rules (which jumps are legal, in what order they
  are refused), the phase machine, and the arrival bookkeeping. Pure logic, so
  "180 frames" is asserted as an integer, not eyeballed.
* :class:`~src.model.game_state.GameState` - the jump *mechanism*: thrust that
  exceeds top speed, exemption from the system boundary, and the boundary clamp
  the jump is exempted *from* (which does not exist without a jump to test).
* :mod:`src.config` - the new ``tactical.jump`` and ``tactical.boundary_warnings``
  keys, including the cross-field checks that would otherwise teleport the
  player inside a planet or outside their system.
* :mod:`src.effects` - the white-out and the warp tunnel. The alpha curve is
  pinned against the model's own blind-frame count, because the whole trick is
  that the world swap happens while the screen is solid white.
* The scene layer through the real ``FixedTimestepLoop`` - input locking, the
  map staying shut, audio firing on the right phase, and pixel scans proving the
  flash really does cover the window (HUD column included).

The stage gate: frame-exact animation length; fuel deducted exactly once;
blocked cases verified; shields full after arrival; spawn distance within
config bounds.
"""

import json
import math
import os
import random

import pygame
import pytest

import main  # noqa: F401  (ensures project root is on sys.path)

from src.audio import AudioSystem
from src.audio_buffers import (
    _JUMP_SPINUP_MS,
    _THUNDERCLAP_MS,
    _generate_jump_spinup,
    _generate_thunderclap,
)
from src.config import ConfigLoadError, base_config, load_config
from src.effects import (
    FLASH_HOLD_FRAMES,
    FlashOverlay,
    WarpTunnel,
    flash_alpha,
    warp_speed,
)
from src.harness import RecordingAudio
from src.hud import VIEW_WIDTH
from src.main_loop import SCREEN_SIZE, FixedTimestepLoop
from src.map_systems.graph import GraphConstraints, SystemGraphGenerator
from src.map_systems.layout import build_map_layout
from src.map_systems.system_map import SystemMapState
from src.model.game_state import GameState
from src.model.jump import (
    BLOCKED_ALREADY_JUMPING,
    BLOCKED_EXACT_FUEL,
    BLOCKED_IN_LANDING_RANGE,
    BLOCKED_INSUFFICIENT_FUEL,
    BLOCKED_INVALID_DESTINATION,
    BLOCKED_NO_DESTINATION,
    EVENT_ARRIVED,
    EVENT_JUMP_ENDED,
    EVENT_TRANSITION_STARTED,
    JumpController,
    JumpParams,
    JumpPresentation,
    PHASE_BURN,
    PHASE_IDLE,
    PHASE_TRANSITION,
    blind_frames_for,
    spawn_position,
)
from src.scene_manager import SceneManager
from src.scenes.game_scene import GameScene, JUMP_DENIED_MESSAGE_FRAMES
from src.scenes.map_view import MapView
from src.scenes.tactical_view import TacticalView, planet_color_for

# The gate asks for property coverage of the spawn band; 200 matches Stage 7.
SEED_SAMPLE = range(200)

# A tiny world keeps the controller tests quick: fonts and a 26-node layout are
# only needed by the map tests, and the jump rules do not care how big the graph is.
TINY_SYSTEMS = 8


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def fake_measure(text: str, size: int) -> tuple[int, int]:
    """A pygame-free label metric, so tiny worlds need no font rendering."""
    return (len(text) * size // 2, size)


def tiny_world(seed: int = 7) -> SystemMapState:
    """A revealed Alpha/Bravo/Charlie/Delta map state with a real layout."""
    graph = SystemGraphGenerator(
        GraphConstraints(
            system_count=TINY_SYSTEMS, min_degree=1, max_degree=3
        ),
        rng=random.Random(seed),
    ).generate()
    layout = build_map_layout(graph, (1024, 768), fake_measure)
    return SystemMapState(graph=graph, layout=layout)


def configured_params(config: dict | None = None) -> JumpParams:
    return JumpParams.from_config((config or base_config())["tactical"])


def ship(config: dict | None = None, seed: int = 11) -> GameState:
    """A ship parked outside landing range (the player never starts there)."""
    state = GameState(config or base_config(), rng=random.Random(seed))
    state.set_position(600.0, 0.0)
    return state


def pair(config: dict | None = None, seed: int = 11, world_seed: int = 7):
    """A (GameState, JumpController) pair with a legal destination selected."""
    state = ship(config, seed)
    world = tiny_world(world_seed)
    controller = JumpController(state, world, configured_params(config))
    world.select("Bravo")
    return state, world, controller


def pump_frame(state: GameState, controller: JumpController):
    """One fixed timestep in GameScene's order: simulate, then tick the sequence.

    Order matters and is asserted elsewhere: the tactical view advances the model
    before the scene dispatches actions and ticks the jump, so the frame J was
    pressed on is not a burn frame.
    """
    state.advance_frame()
    return controller.advance()


def run_sequence(state: GameState, controller: JumpController, limit: int = 10_000):
    """Pump until the sequence ends; return ``(events, pumps)``."""
    events = []
    pumps = 0
    while controller.is_active and pumps < limit:
        pumps += 1
        event = pump_frame(state, controller)
        if event is not None:
            events.append((pumps, event.kind))
    return events, pumps


class _FakeManager:
    """Enough of SceneManager for GameScene: config, audio, and stack verbs."""

    def __init__(self, config: dict | None = None):
        self._config = config or base_config()
        self.audio = RecordingAudio()
        self.pushed: list = []

    def game_config(self) -> dict:
        return self._config

    def push(self, scene) -> None:
        self.pushed.append(scene)
        scene.on_enter(self)

    def pop(self) -> None:
        pass


def game_scene(config: dict | None = None) -> GameScene:
    return GameScene(_FakeManager(config))


def jump_to(system_name: str, config: dict | None = None):
    """A GameScene with a legal destination selected and the ship outside landing range."""
    scene = game_scene(config)
    scene.game_state.set_position(600.0, 0.0)
    scene.system_map.select(system_name)
    return scene


def press_j(scene: GameScene) -> None:
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_j, scancode=0, mod=0))


def advance(scene: GameScene, frames: int) -> None:
    for _ in range(frames):
        scene.update()


def _lit_pixels(canvas: "pygame.Surface", region: "tuple[int, int, int, int]") -> int:
    """Pixels inside ``region`` that are not pure black (an aligned scan)."""
    left, top, width, height = region
    hits = 0
    for y in range(top, top + height):
        for x in range(left, left + width):
            if canvas.get_at((x, y)) != (0, 0, 0, 255):
                hits += 1
    return hits


def _count_colour(canvas: "pygame.Surface", colour: "tuple[int, int, int]") -> int:
    """Exactly how many pixels are ``colour`` across the whole canvas."""
    raw = pygame.image.tobytes(canvas, "RGB")
    packed = bytes(colour)
    return sum(1 for offset in range(0, len(raw), 3) if raw[offset:offset + 3] == packed)


def _rms(samples, start: int, end: int) -> float:
    """Root-mean-square of a slice of an int16 buffer: a loudness measure."""
    window = samples[start:end]
    if not window:
        return 0.0
    return math.sqrt(sum(sample * sample for sample in window) / len(window))


def _zero_crossings(samples, start: int, end: int) -> int:
    """Sign changes in a slice: a crude but reliable pitch proxy."""
    crossings = 0
    for index in range(start + 1, end):
        if (samples[index] < 0) != (samples[index - 1] < 0):
            crossings += 1
    return crossings


# ---------------------------------------------------------------------------
# Eligibility: every blocked case, and the order they are refused in
# ---------------------------------------------------------------------------


def test_request_withNothingSelected_shouldNotStartOrCharge_andStaysSilent():
    """GIVEN no destination, WHEN J is pressed, THEN nothing happens at all.

    The spec is explicit that J "does nothing" with no selection, so silence is
    part of the requirement, not an omission: an overlay here would be the game
    nagging the player for pressing a key that has no effect yet.
    """
    state = ship()
    world = tiny_world()
    controller = JumpController(state, world, configured_params())
    fuel_before = state.fuel

    outcome = controller.request()

    assert outcome.started is False
    assert outcome.blocker == BLOCKED_NO_DESTINATION
    assert outcome.message == "", "no selection must be silent, per the spec"
    assert controller.phase == PHASE_IDLE
    assert state.fuel == fuel_before, "a refused jump must never touch the fuel"


def test_request_withFuelBelowTheCost_shouldBlockWithAnInsufficientFuelBanner():
    """GIVEN less fuel than the jump costs, WHEN J is pressed, THEN the player is
    told in the tactical display and the jump does not start."""
    state, world, controller = pair()
    state.fuel = configured_params().fuel_cost - 0.1
    fuel_before = state.fuel

    outcome = controller.request()

    assert outcome.blocker == BLOCKED_INSUFFICIENT_FUEL
    assert outcome.message == "insufficient fuel"
    assert state.fuel == fuel_before


def test_request_withExactlyTheJumpCost_shouldBlockAndLeaveFuelUntouched():
    """GIVEN exactly enough fuel, WHEN J is pressed, THEN no jump and no charge.

    The spec's special case sends the player to the game-over screen on this
    frame. Stage 13 owns that screen; Stage 8 owns the guarantee that the jump
    never animates and the fuel is never spent, which is what this pins.
    """
    state, world, controller = pair()
    state.fuel = configured_params().fuel_cost

    outcome = controller.request()

    assert outcome.blocker == BLOCKED_EXACT_FUEL
    assert controller.phase == PHASE_IDLE
    assert state.fuel == configured_params().fuel_cost, "no jump, no charge"


def test_request_withExactlyTheJumpCost_butInsideLandingRange_shouldReportThePlanetNotTheFuel():
    """GIVEN exactly enough fuel AND a ship inside landing range, WHEN J is
    pressed, THEN the blocker is the planet, never the exact-fuel game over.

    This is the check-order trap the blockers' docstring warns about: the
    exact-fuel rule is a *death sentence*, so it must not fire for a jump that
    was already illegal for an innocent reason. A player nudging the planet with
    250 fuel in the tank must not be killed for it.
    """
    state, world, controller = pair()
    state.fuel = configured_params().fuel_cost
    state.set_position(0.0, 0.0)  # on top of the planet

    outcome = controller.request()

    assert outcome.blocker == BLOCKED_IN_LANDING_RANGE
    assert outcome.message == "Cannot jump this close to the planet"


def test_request_withShipJustOutsideLandingRange_shouldBeAllowed():
    """The landing-range block is a radius, not a vibe: one pixel out is legal."""
    state, world, controller = pair()
    boundary = state.landing_range + 1.0
    state.set_position(boundary, 0.0)

    assert controller.blocker() == ""


def test_request_whileAlreadyJumping_shouldBeRefusedAndMustNotDoubleCharge():
    """GIVEN a jump already running, WHEN J is pressed again, THEN it is refused
    and the fuel is deducted exactly once across both requests."""
    state, world, controller = pair()
    cost = configured_params().fuel_cost
    fuel_before = state.fuel

    first = controller.request()
    second = controller.request()

    assert first.started is True
    assert second.blocker == BLOCKED_ALREADY_JUMPING
    assert state.fuel == fuel_before - cost, "the jump cost is charged once, not twice"


def test_request_withADestinationThatIsNotNeighbouring_shouldBeRefused():
    """GIVEN a destination elsewhere in the graph, WHEN J is pressed, THEN the
    jump is refused.

    The map's own rules make this unreachable by legal clicking; the guard exists
    for whatever else sets a selection later (save games, scripts, Stage 9's
    mission destinations).
    """
    state, world, controller = pair()
    far = next(name for name in world.graph.names if name not in
               (world.current_system, *world.graph.neighbours(world.current_system)))
    world.selected_system = far  # deliberately bypass can_select()

    assert controller.request().blocker == BLOCKED_INVALID_DESTINATION


def test_request_withAFullyLegalSetup_shouldStartTheBurnAndChargeOnceAtTheStart():
    """GIVEN a neighbouring destination, fuel, and open sky, WHEN J is pressed,
    THEN the burn begins and the full fuel cost is paid on that very frame."""
    state, world, controller = pair()
    cost = configured_params().fuel_cost
    fuel_before = state.fuel

    outcome = controller.request()

    assert outcome.started is True
    assert controller.phase == PHASE_BURN
    assert controller.destination == "Bravo"
    assert state.fuel == fuel_before - cost
    assert state.is_jumping is True


# ---------------------------------------------------------------------------
# The sequence: frame-exact lengths
# ---------------------------------------------------------------------------


def test_advance_shouldAccelerateForExactlyTheConfiguredNumberOfFrames():
    """The stage gate's "frame-exact animation length".

    GIVEN a jump started, WHEN the sequence is pumped, THEN the model integrates
    exactly ``tactical.jump.frames`` burn frames and the white-out begins on the
    frame after the last one. Counting burn frames in the controller instead of
    the model is the off-by-one this test exists to keep out: the frame J was
    pressed on has already stepped the simulation.
    """
    config = base_config()
    params = configured_params(config)
    state, world, controller = pair(config)
    controller.request()

    transition_event = None
    for pump in range(1, params.frames + 2):
        event = pump_frame(state, controller)
        assert controller.phase == PHASE_BURN or event is not None
        if event is not None:
            transition_event = (pump, event)
            break

    pump_at_transition, event = transition_event
    assert event.kind == EVENT_TRANSITION_STARTED
    assert state.jump_frames == params.frames, (
        f"the ship burned for {state.jump_frames} frames, expected {params.frames}"
    )
    assert pump_at_transition == params.frames


def test_advance_shouldTakeExactlyBurnPlusTransitionFramesToFinishTheJump():
    """Total sequence length is ``frames + transition_frames - 1`` pump frames.

    The minus one is not sloppiness: the frame the transition begins on *is* its
    first frame, which is also the frame the flash starts drawing. Both counters
    start at 1 on purpose so the white-out and the world swap cannot drift a
    frame apart.
    """
    config = base_config()
    params = configured_params(config)
    state, world, controller = pair(config)
    controller.request()

    events, pumps = run_sequence(state, controller)

    assert pumps == params.frames + params.transition_frames - 1
    assert controller.phase == PHASE_IDLE
    assert [kind for _, kind in events] == [
        EVENT_TRANSITION_STARTED,
        EVENT_ARRIVED,
        EVENT_JUMP_ENDED,
    ]


def test_advance_shouldSwapTheWorldOnTheFrameTheFlashTurnsFullyOpaque():
    """The one seam between model and presentation, pinned.

    GIVEN the shipped transition lengths, WHEN the arrival frame arrives, THEN
    the flash alpha for that same frame is 255. If these two ever disagree the
    player watches the universe teleport, which is the entire point of the flash.
    """
    for total in (36, 45, 60):
        blind = blind_frames_for(total)
        arrival_pump = blind  # 1-based transition frame the swap happens on
        assert flash_alpha(arrival_pump, total) == 255, (
            f"transition of {total}: the world swaps on frame {arrival_pump} but the "
            f"flash is only {flash_alpha(arrival_pump, total)}/255 opaque"
        )


def test_advance_shouldNotLetTheShipSteerDuringTheJump():
    """All input is ignored during the animation: no cancel, no correction."""
    config = base_config()
    params = configured_params(config)
    state, world, controller = pair(config)
    controller.request()
    heading_at_start = state.heading_degrees

    # Every control held at once, for the whole acceleration.
    for _ in range(params.frames):
        state.feed_input(thrust=True, left=True, right=True, reverse_edge=True)
        pump_frame(state, controller)

    assert state.heading_degrees == heading_at_start, "a jump cannot be steered"
    assert state.reverse_state == "idle", "and a queued reverse-course must not latch"
    assert controller.is_active is True, "holding keys cannot cancel it either"

    _, pumps = run_sequence(state, controller)
    assert controller.is_active is False

    # AND the player gets steering back the moment it ends.
    state.feed_input(left=True)
    state.advance_frame()
    turned = (heading_at_start - state.heading_degrees) % 360.0
    assert turned == pytest.approx(state.stats.turn_rate_deg_per_sec / 60.0), (
        "control must return after arrival (one frame of left-rotation)"
    )


def test_advance_shouldLeaveVelocityFrozenDuringTheWhiteout():
    """The burn is cut at the end of the acceleration, not the world swap.

    The ship coasts through the white-out at its terminal jump speed: a body in
    motion stays in motion, and the player cannot see it either way. What must
    not happen is *more* acceleration while the screen is white.
    """
    config = base_config()
    params = configured_params(config)
    state, world, controller = pair(config)
    controller.request()

    events = []
    while controller.is_active:
        event = pump_frame(state, controller)
        if event is not None:
            events.append(event.kind)
        if event is not None and event.kind == EVENT_TRANSITION_STARTED:
            speed_at_transition = math.hypot(*state.velocity)
            break

    for _ in range(params.transition_frames):
        pump_frame(state, controller)

    arrival_speed = math.hypot(*state.velocity)
    assert arrival_speed == 0.0, "arrival stops the ship dead"
    assert speed_at_transition == pytest.approx(params.acceleration * params.frames)


def test_jumpBurn_shouldExceedTheShipsNormalTopSpeed():
    """The spec says the jump may exceed top speed; the cap must not apply."""
    config = base_config()
    params = configured_params(config)
    state, world, controller = pair(config)
    controller.request()

    for _ in range(params.frames):
        pump_frame(state, controller)

    terminal_speed = math.hypot(*state.velocity)
    assert terminal_speed > state.stats.top_speed * 10, (
        f"jump terminal speed {terminal_speed} should dwarf top_speed "
        f"{state.stats.top_speed}"
    )
    assert terminal_speed == pytest.approx(params.acceleration * params.frames)


def test_jump_shouldCarryTheShipStraightThroughTheSystemBoundary():
    """The player is exempted from the system boundary once a jump starts."""
    config = base_config()
    params = configured_params(config)
    state, world, controller = pair(config)
    state.set_position(900.0, 0.0)  # close to the +x edge (half is 1000)
    controller.request()

    for _ in range(30):
        pump_frame(state, controller)

    half = state.system_pixel_size / 2.0
    assert state.position[0] > half, "a jump must leave the system"


def test_advanceFrame_whenNotJumping_shouldClampTheShipInsideTheSystem():
    """The boundary the jump is exempted from really does exist the rest of the time.

    Stage 8 also lands the clamp the spec asks for in the tactical display: the
    ship cannot leave the system, cannot move further in that direction, and the
    outward velocity is scrubbed so a ship pinned against a wall does not
    slingshot away when it turns around.
    """
    state = ship()
    state.set_position(990.0, 0.0)
    state.heading_degrees = 0.0
    half = state.system_pixel_size / 2.0

    for _ in range(60):
        state.feed_input(thrust=True)
        state.advance_frame()

    assert state.position[0] == half, "the ship must stop dead at the edge"
    assert state.velocity[0] == 0.0, "outward velocity must be scrubbed, not stored"
    assert state.boundary_reached_this_frame() is True


def test_advanceFrame_whenNotJumping_shouldNotReportBoundaryContactAwayFromTheEdge():
    """The banner must not fire for ordinary flight through the middle."""
    state = ship()
    state.heading_degrees = 0.0

    for _ in range(30):
        state.feed_input(thrust=True)
        state.advance_frame()

    assert state.boundary_reached_this_frame() is False


# ---------------------------------------------------------------------------
# Arrival: where the player turns up, and in what condition
# ---------------------------------------------------------------------------


def test_arrival_shouldSpawnEveryTimeOutsideLandingRangeAndInsideTheConfiguredBand():
    """The gate's "spawn distance within config bounds", over 200 seeds."""
    params = configured_params()
    for seed in SEED_SAMPLE:
        state, world, controller = pair(seed=seed, world_seed=seed)
        controller.request()
        while controller.is_active:
            pump_frame(state, controller)

        radius = state.distance_from_point(0.0, 0.0)
        assert params.spawn_min_distance <= radius <= params.spawn_max_distance, (
            f"seed {seed}: spawned {radius} px out, band is "
            f"[{params.spawn_min_distance}, {params.spawn_max_distance}]"
        )
        assert radius > state.landing_range, (
            f"seed {seed}: spawned inside landing range - the player never had "
            "to fly to the planet"
        )
        half = state.system_pixel_size / 2.0
        assert radius <= half, f"seed {seed}: spawned outside the system"


def test_spawnPosition_shouldDrawEveryBearingAndStayInTheBand():
    """Bearings are not a fixed set: every direction must be reachable."""
    params = configured_params()
    rng = random.Random(4242)
    bearings = set()
    for _ in range(200):
        x, y = spawn_position(rng, params.spawn_min_distance, params.spawn_max_distance)
        radius = math.hypot(x, y)
        assert params.spawn_min_distance <= radius <= params.spawn_max_distance
        bearings.add(int(math.degrees(math.atan2(y, x)) % 360) // 45)
    assert bearings == set(range(8)), "spawn bearings collapsed onto a subset of the compass"


def test_spawnPosition_withAnInvertedBand_shouldRaiseRatherThanTeleportThePlayer():
    """A band built backwards (min > max) is a data error, loudly."""
    with pytest.raises(ValueError):
        spawn_position(random.Random(1), 900.0, 100.0)


def test_arrival_shouldRefillShieldsToMaximumEvenAfterHeavyDamage():
    """Shields come back full for free on entering a system."""
    state, world, controller = pair()
    state.stats.shields = 3.0

    controller.request()
    while controller.is_active:
        pump_frame(state, controller)

    assert state.stats.shields == state.stats.max_shields


def test_arrival_shouldResetVelocityAndPutTheShipAwayFromItsOldPosition():
    """Nobody arrives still travelling at 200 px/frame."""
    config = base_config()
    params = configured_params(config)
    state, world, controller = pair(config)
    controller.request()

    while controller.is_active:
        pump_frame(state, controller)

    assert state.velocity == (0.0, 0.0)
    assert state.distance_from_point(0.0, 0.0) >= params.spawn_min_distance
    assert state.is_jumping is False, "the ship is back under normal control"


def test_arrival_shouldMoveThePlayerClearTheSelectionAndRevealTheNewSystem():
    """Current system, fog of war, and the consumed selection."""
    state, world, controller = pair()
    before_revealed = set(world.revealed)

    controller.request()
    while controller.is_active:
        pump_frame(state, controller)

    assert world.current_system == "Bravo"
    assert world.selected_system is None, "a jump consumes its destination"
    assert before_revealed < set(world.revealed), "arriving must reveal Bravo's links"
    assert "Bravo" in world.revealed


def test_arrival_shouldHappenWhileTheScreenIsStillWhite():
    """The system must change *during* the white-out, never after it fades."""
    config = base_config()
    params = configured_params(config)
    state, world, controller = pair(config)
    controller.request()

    arrival_frame = None
    frame = 0
    while controller.phase == PHASE_BURN or (
        controller.phase == PHASE_TRANSITION and controller.transition_frames_elapsed
        < params.transition_frames
    ):
        frame += 1
        event = pump_frame(state, controller)
        if event is not None and event.kind == EVENT_ARRIVED:
            arrival_frame = controller.transition_frames_elapsed
            assert world.current_system == "Bravo", "the swap rides with the event"

    assert arrival_frame == blind_frames_for(params.transition_frames)
    assert arrival_frame < params.transition_frames, "swap must precede the fade-out"


def test_spawnPosition_isIdenticalForAGivenRngSeed():
    """Determinism: the same session seed puts the ship in the same place."""
    first = [
        spawn_position(random.Random(99), 400.0, 850.0) for _ in range(5)
    ]
    second = [
        spawn_position(random.Random(99), 400.0, 850.0) for _ in range(5)
    ]
    assert first == second


# ---------------------------------------------------------------------------
# Config: the new keys, and the geometry they promise
# ---------------------------------------------------------------------------


def test_jumpParams_fromConfig_shouldReadEveryJumpKnob():
    """No hard-coded jump numbers anywhere near the sequence."""
    config = base_config()
    config["tactical"]["jump"].update(
        {"fuel_cost": 7, "frames": 9, "acceleration": 3.5, "transition_frames": 5,
         "spawn_distance": [100, 200]}
    )
    config["tactical"]["landing_range"] = 50
    config["tactical"]["system_pixel_size"] = 600  # half is 300, so [100,200] fits

    params = configured_params(config)

    assert (params.fuel_cost, params.frames, params.acceleration) == (7.0, 9, 3.5)
    assert params.transition_frames == 5
    assert (params.spawn_min_distance, params.spawn_max_distance) == (100.0, 200.0)


def test_jumpParams_fromConfig_withASingleValueSpawnDistance_shouldRaise():
    """This class is built directly by tests and tooling too, so it guards itself."""
    config = base_config()
    config["tactical"]["jump"]["spawn_distance"] = [400]

    with pytest.raises(ValueError):
        configured_params(config)


@pytest.mark.parametrize(
    "dotted_key,value,expectation",
    [
        # A band that reaches into landing range would drop the player on the
        # planet they are supposed to fly to.
        ("tactical.jump.spawn_distance", [50, 850], "below landing_range"),
        # A band outside the system square would drop the player through a wall.
        ("tactical.jump.spawn_distance", [400, 1200], "outside the system"),
        ("tactical.jump.spawn_distance", [900, 400], "inverted band"),
        ("tactical.jump.spawn_distance", [400], "wrong arity"),
        ("tactical.jump.transition_frames", 0, "a zero-frame white-out"),
        ("tactical.jump.frames", 0, "a zero-frame burn"),
        ("tactical.jump.acceleration", 0, "no acceleration"),
        ("tactical.boundary_warnings.cooldown_frames", 0, "no cooldown"),
    ],
)
def test_loadConfig_withAnImpossibleJumpSetting_shouldBeFatalAtStartup(
    config_factory, dotted_key, value, expectation
):
    """GIVEN a config the game could not honour, WHEN it is loaded, THEN the game
    refuses to start rather than mis-teleporting the player later."""
    with pytest.raises(ConfigLoadError):
        load_config(config_factory(overrides={dotted_key: value}))


def test_loadConfig_withTheShippedConfigs_shouldAllPassTheJumpGeometryChecks(config_factory):
    """Sanity for the sanity checks: all three shipped difficulties are legal."""
    configs = load_config(config_factory())
    for name, config in configs.items():
        tactical = config["tactical"]
        low, high = tactical["jump"]["spawn_distance"]
        assert low > tactical["landing_range"]
        assert high <= tactical["system_pixel_size"] / 2.0


def test_configs_everyDifficultyShouldAgreeOnTheNewJumpKeys():
    """The three files must carry identical key sets (unrecognized keys are fatal)."""
    from src.config import CONFIG_FILES, GAME_ROOT

    for name in CONFIG_FILES:
        with open(os.path.join(GAME_ROOT, name), encoding="utf-8") as handle:
            jump_keys = set(json.load(handle)["tactical"]["jump"])
        assert jump_keys == {
            "fuel_cost", "frames", "acceleration", "transition_frames", "spawn_distance"
        }, f"{name} drifted from the jump schema"
        with open(os.path.join(GAME_ROOT, name), encoding="utf-8") as handle:
            warnings = set(json.load(handle)["tactical"]["boundary_warnings"])
        assert warnings == {"message_frames", "cooldown_frames"}, (
            f"{name} drifted from the boundary_warnings schema"
        )


# ---------------------------------------------------------------------------
# Effects: the white-out and the tunnel
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("total", [36, 45, 60, 3])
def test_flashAlpha_shouldRampUpHoldThenDecayToExactlyZero(total):
    """The curve is bookended by "invisible" so the effect cannot leave a residue."""
    blind = blind_frames_for(total)
    assert flash_alpha(1, total) > 0
    assert flash_alpha(total, total) == 0, "the final frame must be clear"

    alphas = [flash_alpha(frame, total) for frame in range(1, total + 1)]
    assert all(0 <= alpha <= 255 for alpha in alphas)
    assert max(alphas) == 255
    peak = alphas.index(255) + 1
    assert peak == blind, f"peak lands on frame {peak}, the blind window ends at {blind}"
    assert alphas[peak:] == sorted(alphas[peak:], reverse=True), "the fade must be monotonic"


def test_flashAlpha_withATransitionShorterThanItsOwnRamp_shouldBeFullyOpaqueThroughout():
    """The documented degenerate case: a 1-frame white-out is just white.

    Not a shipping configuration (the files use 36/45/60), but the model allows
    ``transition_frames: 1`` and the swap still has to happen under cover, so
    that single frame is opaque rather than transparent - which is the opposite
    of the "final frame is clear" rule, and worth stating out loud.
    """
    assert flash_alpha(1, 1) == 255
    assert blind_frames_for(1) == 1


def test_flashAlpha_shouldReachFullOpacityExactlyAtTheModelsBlindFrame():
    """Presentation deferring to the model's clock, in both directions."""
    for total in (36, 45, 60, 100):
        blind = blind_frames_for(total)
        assert flash_alpha(blind - 1, total) < 255 if blind > 1 else True
        assert flash_alpha(blind, total) == 255
        # The hold window spans blind .. blind+FLASH_HOLD_FRAMES inclusive, so the
        # first frame that has started fading is one past its end.
        assert flash_alpha(blind + FLASH_HOLD_FRAMES + 1, total) < 255


def test_flashOverlay_shouldTrackTheSameFrameCountersAsTheJumpSequence():
    """begin() puts frame 1 on the frame it is called, then advance() ticks.

    GameScene advances the flash *before* the controller precisely so these two
    counters stay equal. Ticking them the other way round offsets the white-out
    from the world swap by a frame, and the swap becomes visible.
    """
    overlay = FlashOverlay(pygame.Rect(0, 0, 1024, 768))
    total = 45

    overlay.begin(total)
    assert overlay.frame == 1
    assert overlay.alpha() == flash_alpha(1, total)

    for expected in range(2, total + 1):
        overlay.advance()
        assert overlay.frame == expected
    overlay.advance()
    assert overlay.active is False
    assert overlay.alpha() == 0


def test_flashOverlay_atPeakShouldWhitenEveryPixelOfTheWindow():
    """A screen flash that skips the HUD column is a rendering bug, not drama."""
    from src.effects import _FLASH_TINT

    overlay = FlashOverlay(pygame.Rect(0, 0, 1024, 768))
    overlay.begin(45)
    for _ in range(blind_frames_for(45) - 1):
        overlay.advance()

    canvas = pygame.Surface((1024, 768))
    canvas.fill((10, 20, 30))
    overlay.draw(canvas)

    assert _count_colour(canvas, _FLASH_TINT) == 1024 * 768, (
        "the flash must cover the whole window, HUD included"
    )


def test_flashOverlay_whenIdle_shouldDrawNothing():
    """A no-op draw keeps the arrival view clean once the effect is over."""
    overlay = FlashOverlay(pygame.Rect(0, 0, 1024, 768))
    canvas = pygame.Surface((1024, 768))
    canvas.fill((7, 7, 7))
    overlay.draw(canvas)

    assert _count_colour(canvas, (7, 7, 7)) == 1024 * 768


def test_flashOverlay_shockwave_shouldStayHiddenUntilTheFlashStartsFading():
    """A ring drawn under a fully opaque flash is a ring nobody can see."""
    overlay = FlashOverlay(pygame.Rect(0, 0, 1024, 768), origin=(341, 384))
    overlay.begin(45)
    blind = blind_frames_for(45)

    for _ in range(blind):
        assert overlay.shockwave_radius_fraction() == 0.0
        overlay.advance()

    assert overlay.shockwave_radius_fraction() > 0.0


def test_warpTunnel_shouldKeepItsCountAndGrowStreaksOutwardForever():
    """An effect that thins out over three seconds is a visible bug."""
    tunnel = WarpTunnel(count=60, max_radius=640.0, rng=random.Random(3))

    for frame in range(600):
        tunnel.advance(intensity=min(1.0, frame / 180.0))
        assert len(tunnel.streaks) == 60, f"frame {frame}: streak count drifted"
        for streak in tunnel.streaks:
            assert streak.radius <= tunnel.max_radius, f"frame {frame}: streak escaped"
            assert streak.radius >= tunnel.min_radius
            assert streak.previous_radius <= streak.radius, "streaks must not reverse"


def test_warpSpeed_shouldRiseMonotonicallyWithIntensityAndStayBounded():
    """The tunnel accelerates outward as the burn builds, never backwards."""
    speeds = [warp_speed(intensity) for intensity in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert speeds == sorted(speeds)
    assert speeds[0] > 0.0, "even at zero intensity the tunnel keeps creeping"
    assert warp_speed(-5) == speeds[0] and warp_speed(9) == speeds[-1], "clamped"


def test_warpTunnel_reset_shouldPutEveryStreakBackNearTheVanishingPoint():
    """New system, new tunnel: a jump must not inherit the old one's streaks."""
    tunnel = WarpTunnel(count=40, max_radius=640.0, rng=random.Random(5))
    for _ in range(400):
        tunnel.advance(1.0)
    tunnel.reset()

    assert all(streak.radius < tunnel.min_radius * 3.0 + 1.0 for streak in tunnel.streaks)


# ---------------------------------------------------------------------------
# Audio: generated buffers, and firing on the right frames
# ---------------------------------------------------------------------------


def test_generateJumpSpinup_shouldSweepUpwardInPitchAndRiseInVolume():
    """A rising sweep, not a siren: pitch and loudness both climb."""
    buffer = _generate_jump_spinup(sample_rate=22050)
    window = len(buffer) // 10

    assert len(buffer) == pytest.approx(22050 * _JUMP_SPINUP_MS / 1000, rel=0.01)
    assert _zero_crossings(buffer, 0, window) < _zero_crossings(
        buffer, len(buffer) - window, len(buffer)
    ), "the sweep must end higher in pitch than it starts"
    assert _rms(buffer, window * 7, window * 9) > _rms(buffer, 0, window), (
        "the engine must get louder as it spools up"
    )


def test_generateThunderclap_shouldBeLoudestAtTheCrackAndDecay():
    """A clap: transient first, rumble after."""
    buffer = _generate_thunderclap(sample_rate=22050)

    assert len(buffer) == pytest.approx(22050 * _THUNDERCLAP_MS / 1000, rel=0.01)
    assert _rms(buffer, 0, 500) > _rms(buffer, len(buffer) - 2000, len(buffer)) * 2, (
        "the crack must lead, the tail must decay"
    )


@pytest.mark.parametrize("factory", [_generate_jump_spinup, _generate_thunderclap])
def test_generatedBuffers_shouldBeDeterministicSilentAtTheEdgesAndNeverClip(factory):
    """Byte-identical every run (so a digest can pin them), int16-safe, no clicks."""
    first = factory(sample_rate=8000)
    second = factory(sample_rate=8000)

    assert list(first) == list(second), "a sound that changes per launch cannot be pinned"
    assert all(-32768 <= sample <= 32767 for sample in first)
    assert max(abs(sample) for sample in first) > 1000, "buffer is silent"
    assert abs(first[0]) < max(abs(sample) for sample in first) * 0.5, (
        "the first sample must not pop"
    )


def test_scene_shouldPlayTheSpinupWhenTheJumpStarts():
    """GIVEN a legal jump, WHEN it starts, THEN the spool-up plays - once."""
    scene = jump_to("Bravo")
    press_j(scene)
    scene.update()

    assert scene._manager.audio.spinup_count == 1
    assert scene._manager.audio.thunderclap_count == 0


def test_scene_shouldPlayTheThunderclapOnTheFrameTheScreenGoesWhite():
    """Boom, flash, and phase change share one frame, or the drama deflates."""
    config = base_config()
    params = configured_params(config)
    scene = jump_to("Bravo", config)
    press_j(scene)

    frame = 0
    while True:
        frame += 1
        scene.update()
        if scene.jumps.phase == PHASE_TRANSITION:
            break
        assert scene._manager.audio.thunderclap_count == 0, "too early"
        assert scene.screen_flash.active is False, "the white-out is early too"

    # frames + 1: the update that drained the J press is not itself a burn frame,
    # because the simulation had already stepped before the jump was requested.
    assert frame == params.frames + 1, (
        f"the white-out began after {frame} updates; the burn is {params.frames} frames"
    )
    assert scene._manager.audio.thunderclap_count == 1, "exactly one boom"
    assert scene.screen_flash.active is True
    assert scene.screen_flash.frame == 1, "and the flash starts on that same frame"


def test_scene_shouldPlayNoJumpSoundsForABlockedJump():
    """A refused jump is silent as well as motionless."""
    scene = game_scene()
    scene.game_state.set_position(0.0, 0.0)  # parked on the planet
    scene.system_map.select("Bravo")
    press_j(scene)
    scene.update()

    assert scene._manager.audio.spinup_count == 0
    assert scene._manager.audio.thunderclap_count == 0


def test_audioSystem_shouldExposeTheJumpSoundsAndSurviveWithoutAMixer(monkeypatch):
    """Fail-soft: audio is never fatal, even if the mixer dies mid-game."""
    audio = AudioSystem()
    audio.play_jump_spinup()
    audio.play_thunderclap()

    import src.audio as audio_module

    def _exploding_sound(*args, **kwargs):
        raise RuntimeError("mixer exploded")

    monkeypatch.setattr(audio_module.pygame.mixer, "Sound", _exploding_sound)
    fresh = AudioSystem()
    fresh.play_jump_spinup()  # must swallow it
    fresh.play_thunderclap()
    assert fresh.available is True, "the mixer still reports itself usable"


# ---------------------------------------------------------------------------
# The scene: input lock, banners, and what actually gets drawn
# ---------------------------------------------------------------------------


def test_requestJump_throughTheScene_shouldLockAndUnlockInputForExactlyTheSequence():
    """Input is locked for the whole sequence, then given back."""
    config = base_config()
    params = configured_params(config)
    scene = jump_to("Bravo", config)
    press_j(scene)
    scene.update()

    assert scene.tactical.input.locked is True
    assert scene.game_state.is_jumping is True

    for _ in range(params.frames + params.transition_frames):
        scene.update()

    assert scene.tactical.input.locked is False, "the player must get their ship back"
    assert scene.game_state.is_jumping is False


def test_holdingThrustWhenTheJumpStarts_shouldNotKeepFeedingInput():
    """The latched control frame is cleared on begin_jump.

    Without that, a thrust key held when J landed keeps re-applying ordinary
    (capped) thrust inside the jump, mixing it into the uncapped burn: the ship
    would accelerate at the wrong rate for all 180 frames and no test of the
    terminal speed would mean anything.
    """
    config = base_config()
    params = configured_params(config)
    scene = jump_to("Bravo", config)
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP, scancode=0, mod=0))
    scene.update()  # thrust is now latched and burning normally
    press_j(scene)
    scene.update()  # the jump begins after this frame's simulation step
    speed_at_jump_start = math.hypot(*scene.game_state.velocity)

    scene.update()  # the first real burn frame, with UP still physically held
    speed_after_one_burn = math.hypot(*scene.game_state.velocity)

    assert scene.game_state.is_jumping is True
    assert speed_after_one_burn - speed_at_jump_start == pytest.approx(
        params.acceleration
    ), (
        "a jump frame must apply the jump acceleration alone, not the held thrust "
        f"key's {config['player_ship']['acceleration_rate']}"
    )


def test_insufficientFuel_shouldBrieflyOverlayAMessageInTheTacticalDisplay():
    """The gate's "fuel check with visible feedback"."""
    scene = jump_to("Bravo")
    scene.game_state.fuel = 10.0
    press_j(scene)
    scene.update()

    assert scene.tactical.overlays.active_messages() == ["insufficient fuel"]

    advance(scene, JUMP_DENIED_MESSAGE_FRAMES)
    assert scene.tactical.overlays.active_messages() == [], "briefly means briefly"


def test_noSelection_shouldProduceNoMessageAndNoMovement():
    """J with nothing selected does nothing, silently."""
    scene = game_scene()
    scene.game_state.set_position(600.0, 0.0)
    fuel_before = scene.game_state.fuel
    press_j(scene)
    scene.update()

    assert scene.tactical.overlays.active_messages() == []
    assert scene.game_state.fuel == fuel_before
    assert scene.jumps.phase == PHASE_IDLE


def test_pendingGameOver_withExactlyTheJumpFuel_shouldFlagTheStage13Seam():
    """Stage 8 refuses the jump and raises the flag; Stage 13 owns the screen."""
    scene = jump_to("Bravo")
    scene.game_state.fuel = configured_params().fuel_cost
    press_j(scene)
    scene.update()

    assert scene.pending_game_over is True
    assert scene.jumps.phase == PHASE_IDLE
    assert scene.game_state.fuel == configured_params().fuel_cost


def test_pendingGameOver_withThePlanetTooClose_shouldNeverFlagGameOver():
    """The ordering trap, scene-side: a legal-looking mistake must not be lethal."""
    scene = jump_to("Bravo")
    scene.game_state.fuel = configured_params().fuel_cost
    scene.game_state.set_position(0.0, 0.0)
    press_j(scene)
    scene.update()

    assert scene.pending_game_over is False
    # Parked on the planet, the landing prompt is legitimately up too; the jump
    # refusal sits underneath it rather than replacing it.
    assert scene.tactical.overlays.active_messages() == [
        "Press L to land here",
        "Cannot jump this close to the planet",
    ]


def test_hud_shouldReadHyperspaceBoldlyDuringTheJumpAndClearItAfterwards():
    """The HUD's nav seam is driven by the real sequence.

    ``draw()`` is called between the assertions because the nav line is a
    draw-time seam (it also has to update while a modal has ``update()`` frozen),
    while ``is_jumping`` is synced by ``update()``.
    """
    config = base_config()
    params = configured_params(config)
    scene = jump_to("Bravo", config)
    canvas = pygame.Surface(SCREEN_SIZE)

    scene.draw(canvas)
    assert scene.hud.nav_selected_name == "Bravo"
    assert scene.hud.is_jumping is False

    press_j(scene)
    advance(scene, 30)
    assert scene.hud.is_jumping is True
    scene.draw(canvas)
    assert scene.hud.nav_selected_name == "Bravo", "the destination survives the burn"

    advance(scene, params.frames + params.transition_frames)
    scene.draw(canvas)
    assert scene.hud.is_jumping is False
    assert scene.hud.nav_selected_name is None, "and it is cleared by arrival"


def test_jumpTacticalView_duringTheWhiteout_shouldHideTheShipThenRevealItWithTheFade():
    """Given the presentation reports the transition phase, when the view is asked
    for an opaque frame and then for a fading one, then the ship must be absent
    while the screen is white and present as the fade uncovers the arrival: a
    ship that pops in on the last frame is a seam, not an effect.
    """
    nose_color = (150, 210, 230)
    config = base_config()
    view = TacticalView(_FakeManager(config), ship(config))
    transition_frames = configured_params(config).transition_frames
    blind_frames = blind_frames_for(transition_frames)

    view.jump = JumpPresentation(phase=PHASE_BURN, progress=0.9)
    burning = pygame.Surface(SCREEN_SIZE)
    view.draw(burning)
    assert _count_colour(burning, nose_color) > 0, "the ship is visible during the burn"

    for elapsed in (1, blind_frames):
        view.jump = JumpPresentation(
            phase=PHASE_TRANSITION, progress=elapsed / transition_frames
        )
        blank = pygame.Surface(SCREEN_SIZE)
        view.draw(blank)
        assert _count_colour(blank, nose_color) == 0, (
            f"the ship must be gone {elapsed} frames into the white-out"
        )

    view.jump = JumpPresentation(
        phase=PHASE_TRANSITION, progress=(blind_frames + 2) / transition_frames
    )
    revealed = pygame.Surface(SCREEN_SIZE)
    view.draw(revealed)
    assert _count_colour(revealed, nose_color) > 0, (
        "the ship should be uncovered by the fade, not popped in at the end"
    )


def test_jumpPresentation_shipVisible_shouldHideTheShipOnlyWhileTheFlashIsOpaque():
    """Given a transition in progress, when progress is sampled across the whole
    white-out, then the ship is hidden only up to the blind fraction: the fade
    uncovers the arrival instead of popping a ship into it at the last frame.
    """
    transition_frames = 45
    blind_frames = blind_frames_for(transition_frames)

    assert JumpPresentation(phase=PHASE_IDLE).ship_visible is True
    assert JumpPresentation(phase=PHASE_BURN, progress=1.0).ship_visible is True

    for elapsed in range(1, blind_frames + 1):
        assert JumpPresentation(
            phase=PHASE_TRANSITION, progress=elapsed / transition_frames
        ).ship_visible is False, f"ship visible {elapsed} frames into the white-out"

    for elapsed in range(blind_frames + 1, transition_frames + 1):
        assert JumpPresentation(
            phase=PHASE_TRANSITION, progress=elapsed / transition_frames
        ).ship_visible is True, f"ship hidden {elapsed} frames into the white-out"


def test_jumpTacticalView_shouldSmearStarsIntoStreaksDuringTheBurn():
    """Motion the player can read: 150 stars become 150 lines."""
    config = base_config()
    state = ship(config)
    view = TacticalView(_FakeManager(config), state)
    state.begin_jump(1.2)
    for _ in range(150):
        state.advance_frame()
    view.jump = JumpPresentation(phase=PHASE_BURN, progress=0.8)

    idle = pygame.Surface(SCREEN_SIZE)
    view.jump = JumpPresentation()
    view.draw(idle)
    streaked = pygame.Surface(SCREEN_SIZE)
    view.jump = JumpPresentation(phase=PHASE_BURN, progress=0.8)
    view.draw(streaked)

    region = (0, 0, VIEW_WIDTH, SCREEN_SIZE[1])
    idle_lit = _lit_pixels(idle, region)
    streak_lit = _lit_pixels(streaked, region)
    assert streak_lit > idle_lit * 4, (
        f"streaks lit {streak_lit}px vs idle {idle_lit}px: the jump must look fast"
    )


def test_notifySystemChanged_shouldRegenerateTheSkyAndClearTheOldSystemsPrompts():
    """Arrival is a new system: new starfield, new planet colour, same star count."""
    config = base_config()
    state = ship(config)
    view = TacticalView(_FakeManager(config), state)
    before = [(star.x, star.y) for star in view.starfield.stars]
    view.overlays.set_sticky("Press L to land here")
    for _ in range(400):
        view.warp.advance(1.0)

    view.notify_system_changed("Bravo")

    after = [(star.x, star.y) for star in view.starfield.stars]
    assert len(after) == len(before), "the 150-star invariant holds across a jump"
    assert after != before, "the sky must be a new one, not the old one re-used"
    assert view.system_name == "Bravo"
    assert view.overlays.active_messages() == [], (
        "the old system's landing prompt must not follow the player through the gate"
    )
    assert all(
        star.x <= view.starfield.half_extent and star.y <= view.starfield.half_extent
        for star in view.starfield.stars
    ), "a fresh sky must be entirely inside the view box"
    assert all(
        streak.radius <= view.warp.min_radius * 3.0 for streak in view.warp.streaks
    ), "the warp tunnel must start over, not inherit the old system's streaks"


def test_planetColorFor_shouldBeStableAcrossProcessesAndDifferBetweenSystems():
    """``hash()`` is randomised per process; crc32 is not (see DECISIONS.md)."""
    colours = {planet_color_for(name) for name in ("Alpha", "Bravo", "Charlie", "Delta")}
    assert len(colours) > 1, "every planet would otherwise look identical"
    assert planet_color_for("Bravo") == planet_color_for("Bravo")


def test_landingPrompt_shouldBeSuppressedThroughoutTheJump():
    """Even a ship parked in landing range gets no prompt mid-jump."""
    config = base_config()
    state = ship(config)
    state.set_position(10.0, 0.0)
    view = TacticalView(_FakeManager(config), state)
    view.jump = JumpPresentation(phase=PHASE_BURN, progress=0.5)

    view.update()

    assert "Press L to land here" not in view.overlays.active_messages()


def test_boundaryWarning_shouldAppearAtMostOncePerConfiguredCooldown():
    """Spec: "at most once every five seconds", and five seconds comes from config."""
    config = base_config()
    cooldown = int(config["tactical"]["boundary_warnings"]["cooldown_frames"])
    state = ship(config)
    state.set_position(state.system_pixel_size / 2.0 - 10.0, 0.0)
    state.heading_degrees = 0.0
    view = TacticalView(_FakeManager(config), state)
    # Thrust is driven through the input layer, because TacticalView.update()
    # re-feeds the model every frame - poking feed_input directly would just be
    # overwritten (which is exactly the seam Stage 5 established).
    view.input.feed_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_UP))

    text = "System boundary reached"
    appearances = 0
    previous = text in view.overlays.active_messages()
    for _ in range(3 * cooldown):
        view.update()
        current = text in view.overlays.active_messages()
        if current and not previous:
            appearances += 1
        previous = current

    assert appearances == 3, (
        f"the boundary banner fired {appearances} times in {3 * cooldown} frames of "
        f"pressing against the wall; expected one per {cooldown}-frame cooldown"
    )


def test_twoScenesWithTheSameSeed_shouldReproduceTheSkyAndTheArrivalPoint():
    """``rng.seed`` now pins the arrival, not just the map.

    Stage 7 left ``GameState.rng`` unseeded, so a seeded run reproduced its world
    topology but not its skies or its jump bearings. Both scenes below run the
    identical script, so everything observable must match - while the graph stays
    a separate stream (next test), because topology must not depend on how much
    flying happened first.
    """
    config = base_config()
    config["rng"]["seed"] = 1234

    first = _play_one_jump(config)
    second = _play_one_jump(config)

    assert first["spawn"] == second["spawn"], "arrival bearings must be replayable"
    assert first["stars"] == second["stars"], "the arrival sky must be replayable"
    assert first["revealed"] == second["revealed"]


def test_twoScenesWithDifferentSeeds_shouldArriveAtDifferentPlaces():
    """A seed that changed nothing is a seed that is not being used."""
    spawns = set()
    for seed in (11, 12):
        config = base_config()
        config["rng"]["seed"] = seed
        spawns.add(_play_one_jump(config)["spawn"])
    assert len(spawns) == 2, "every seed produced the same arrival point"


def test_theWorldGraph_shouldNotDependOnTheGameplayStream():
    """Two streams, one seed: the map must survive any amount of prior flying.

    If the graph generator and the gameplay RNG ever shared a cursor, the world a
    player mapped would depend on how many frames they had thrusted for before
    opening the map - the nastiest class of bug this project has already found
    once (see the Stage 7 PYTHONHASHSEED note).
    """
    config = base_config()
    config["rng"]["seed"] = 777

    plain = game_scene(config)
    flown = _play_one_jump(config)

    assert plain.system_map.graph.adjacency == flown["adjacency"], (
        "a jump consumed graph-generator randomness: the two RNG streams are shared"
    )


def _play_one_jump(config: dict) -> dict:
    """Build a scene, fly it out, jump Alpha -> Bravo, and report what varied."""
    scene = game_scene(config)
    scene.game_state.set_position(600.0, 0.0)
    scene.system_map.select("Bravo")
    params = configured_params(config)

    press_j(scene)
    for _ in range(params.frames + params.transition_frames + 2):
        scene.update()

    return {
        "spawn": tuple(round(value, 6) for value in scene.game_state.position),
        "stars": tuple(
            (round(star.x, 6), round(star.y, 6), star.color)
            for star in scene.tactical.starfield.stars
        ),
        "revealed": frozenset(scene.system_map.revealed),
        "adjacency": scene.system_map.graph.adjacency,
    }


# ---------------------------------------------------------------------------
# The whole thing, through the real loop
# ---------------------------------------------------------------------------

# One world for every real-loop test. The tests below name systems outright, so
# the graph must be fixed; see test_thePinnedWorldSeed_shouldOfferEveryHop...
WORLD_SEED = 4242


def _build_game(config_factory, seed: int = WORLD_SEED):
    """A real SceneManager + GameScene + FixedTimestepLoop (see Stage 7 tests).

    The world seed is pinned through the fixture call *here*, not in the tests:
    ``config_factory`` rewrites the three temp config files every time it is
    called, so a pre-call in a test is silently overwritten and the graph comes
    back unseeded. These tests name systems outright ("jump to Bravo"), and that
    is only a legal hop on a specific graph - see the pinned-seed guard test.
    """
    configs = load_config(config_factory(overrides={"rng.seed": seed}))
    screen = pygame.display.get_surface()
    manager = SceneManager(screen=screen, configs=configs, audio=AudioSystem())
    manager.selected_config = configs["config_medium.json"]
    game = GameScene(manager)
    manager.push(game)
    loop = FixedTimestepLoop(scene_manager=manager, screen=screen)
    return manager, game, loop


def _pump(loop, frames):
    for _ in range(frames):
        assert loop.step_once(), "the loop stopped unexpectedly"


def _press(loop, key):
    pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=key, scancode=0, mod=0))
    _pump(loop, 1)
    pygame.event.post(pygame.event.Event(pygame.KEYUP, key=key, scancode=0, mod=0))
    _pump(loop, 1)


def test_thePinnedWorldSeed_shouldOfferEveryHopTheIntegrationTestsTake(config_factory):
    """Given the one seed the real-loop tests build their world from, when its
    graph is inspected, then the hops those tests name by hand must exist.

    Those tests say "select Bravo" rather than "select some neighbour of Alpha",
    because a fixed expectation is a readable expectation. That convenience is
    rented entirely from this seed, so this is where a graph-generator change
    says so out loud instead of turning four unrelated tests flaky.
    """
    _manager, game, _loop = _build_game(config_factory)

    assert game.system_map.current_system == "Alpha"
    assert {"Bravo", "Charlie"} <= set(game.system_map.graph.neighbours("Alpha"))
    assert set(game.system_map.graph.neighbours("Bravo")) - {"Alpha"}, (
        "the two-hop tour needs somewhere onward from Bravo that is not home"
    )


def test_pressingJThroughTheRealLoop_shouldTravelToTheSelectedSystem(config_factory):
    """The whole chain: binding -> action -> rules -> 180-frame burn -> arrival."""
    manager, game, loop = _build_game(config_factory)
    params = configured_params(manager.game_config())

    game.game_state.set_position(600.0, 0.0)  # flown out from the planet
    game.system_map.select("Bravo")
    fuel_before = game.game_state.fuel

    _press(loop, pygame.K_j)
    assert game.jumps.phase == PHASE_BURN, "J must start the burn"

    burn_pumps = 0
    while game.jumps.phase == PHASE_BURN:
        _pump(loop, 1)
        burn_pumps += 1
        assert burn_pumps <= params.frames + 5, "the burn ran away from its budget"

    assert game.game_state.jump_frames == params.frames, (
        f"the ship accelerated on {game.game_state.jump_frames} frames, "
        f"expected exactly {params.frames}"
    )
    assert game.jumps.phase == PHASE_TRANSITION, "then the white-out begins"

    transition_pumps = 0
    while game.jumps.phase == PHASE_TRANSITION:
        _pump(loop, 1)
        transition_pumps += 1
        assert transition_pumps <= params.transition_frames + 5, "the flash ran long"
    # -1 because the frame the white-out began on was already counted by the burn
    # loop: a phase's first frame is the frame it starts on, which is also the
    # frame the flash starts drawing, so the swap can never drift out from under it.
    assert transition_pumps == params.transition_frames - 1

    assert game.system_map.current_system == "Bravo"
    assert game.system_map.selected_system is None
    assert game.game_state.fuel == fuel_before - params.fuel_cost
    assert len(manager._stack) == 1, "a jump pushes no modal"


def test_pressingMWhileAJumpIsRunning_shouldBeRefusedAndThenWorkAgain(config_factory):
    """The map stays shut for the whole sequence, then reopens normally."""
    manager, game, loop = _build_game(config_factory)
    params = configured_params(manager.game_config())

    game.game_state.set_position(600.0, 0.0)
    game.system_map.select("Bravo")
    _press(loop, pygame.K_j)
    _pump(loop, 30)

    _press(loop, pygame.K_m)
    assert len(manager._stack) == 1, "the map may not open mid-jump"

    _pump(loop, params.frames + params.transition_frames)
    _press(loop, pygame.K_m)
    assert isinstance(manager._stack[-1], MapView), "and it works again after arrival"


def test_aFullJump_shouldPaintTheWholeWindowWhiteAtItsPeak(config_factory):
    """Pixel proof, on the real display surface, that the flash covers everything.

    Asserted on the shipped medium config: 45 transition frames, so the peak is
    nine frames into the white-out.
    """
    from src.effects import _FLASH_TINT

    manager, game, loop = _build_game(config_factory)
    params = configured_params(manager.game_config())
    canvas = pygame.Surface(SCREEN_SIZE)

    game.game_state.set_position(600.0, 0.0)
    game.system_map.select("Charlie")
    _press(loop, pygame.K_j)
    _pump(loop, params.frames)
    assert game.jumps.phase == PHASE_TRANSITION

    _pump(loop, blind_frames_for(params.transition_frames) - 1)
    assert game.screen_flash.alpha() == 255

    game.draw(canvas)
    assert _count_colour(canvas, _FLASH_TINT) == 1024 * 768, (
        "at its peak the flash must leave no pixel of the tactical view or the HUD "
        "untouched - that is what hides the world swap"
    )
    assert params.transition_frames == 45


def test_aJumpAcrossTwoSystems_shouldRevealProgressivelyAndClearSelectionEachTime(config_factory):
    """Two jumps in a row: the fog of war peels back one ring at a time."""
    manager, game, loop = _build_game(config_factory)
    params = configured_params(manager.game_config())

    game.game_state.set_position(600.0, 0.0)
    first_revealed = set(game.system_map.revealed)
    assert first_revealed == {"Alpha", "Bravo", "Charlie", "Delta"}

    game.system_map.select("Bravo")
    _press(loop, pygame.K_j)
    _pump(loop, params.frames + params.transition_frames)
    assert game.system_map.current_system == "Bravo"

    second_revealed = set(game.system_map.revealed)
    assert second_revealed >= first_revealed, "the fog of war must not close back in"
    assert second_revealed == (
        first_revealed | set(game.system_map.graph.neighbours("Bravo")) | {"Bravo"}
    ), "arrival must reveal exactly the new system and its links, permanently"

    # And the player can jump on immediately from wherever they landed. Which hops
    # exist is a property of the seeded graph, not of jumping, so the way home is
    # a perfectly good fallback.
    next_hop = next(
        (name for name in game.system_map.graph.neighbours("Bravo") if name != "Alpha"),
        "Alpha",
    )
    game.system_map.select(next_hop)
    _press(loop, pygame.K_j)
    _pump(loop, params.frames + params.transition_frames)

    assert game.system_map.current_system == next_hop
    assert game.system_map.selected_system is None
