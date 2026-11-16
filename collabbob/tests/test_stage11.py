"""Stage 11 tests: projectiles, damage, bounties, and the ``T`` scan.

Five layers, mirroring the split of the implementation:

* :mod:`src.model.combat`'s rules — the ``combat`` config section hoisted into a
  validated object (including the 3px-diameter-to-pygame-radius conversion, which
  must have exactly one answer).
* :class:`~src.model.combat.Projectile` — the spec's velocity composition (ship
  velocity plus the configured bonus along the aim) and its travel budget, which
  is the firing gun's range, not a constant.
* :class:`~src.model.combat.Gunfight` — who a round may hit: never the ship that
  fired it, never a hull of its own side, never an immune or already-destroyed
  body, and never a planet. Plus the swept hit test, because a 18px step through a
  20px hull is a miss the player can *watch* happen.
* Damage and its consequences — shield-before-armour order (shared with the
  player's hull), destruction, the faction grudge a player round earns, and the
  bounties a player kill pays (and the ones it does not).
* :class:`~src.model.scan.ShipScanner` — the sticky nearest-ship lock behind ``T``,
  its reversion on destruction, and its reset on a new system.

The stage gate: velocity-composition math; damage order; destruction;
hostility-on-hit; scan stickiness and reversion; projectiles cannot hit their
owner.
"""

import math
import random

import pygame
import pytest

import main  # noqa: F401  (ensures project root is on sys.path)

from src.config import CONFIG_FILES, GAME_ROOT, ConfigLoadError, base_config, load_config
from src.effects import ParticleBurst
from src.hud import (
    BAR_HEIGHT,
    LINE_HEIGHT,
    NEAREST_SHIP_ROWS,
    NO_TARGET_TEXT,
    HudView,
    _HudPalette,
    contact_status_rows,
    nearest_ship_row_rects,
    ship_status_row_rects,
    status_row_geometry,
)
from src.model.combat import (
    CombatRules,
    Combatant,
    Gunfight,
    Projectile,
    bounty_for_kill,
    point_hits_circle,
    segment_entry_parameter,
)
from src.model.encounter import Encounter, SpawnRules, nearest_living_ship
from src.model.factions import (
    FACTION_BOBBER,
    FACTION_LOCALHOSTER,
    FACTION_PIRATE,
    FACTION_PLAYER,
    FACTIONS,
    COMBATANTS,
    PlayerRelations,
    combatant_color,
    faction_color,
    faction_label,
    is_npc_faction,
    require_combatant,
    war_side_of,
)
from src.model.game_state import GameState
from src.model.npc_ship import NpcShip, roll_npc_stats
from src.model.scan import ShipScanner
from src.model.stats import ShipStats, apply_damage_order
from src.model.weapons import Shot, WeaponClock, weapon_cooldown_frames
from src.scenes.game_scene import GameScene
from src.scenes.tactical_view import SCREEN_SIZE, TacticalView, _VIEW_CENTER

# Geometry that shows up in a lot of these: the hull hand-built by :func:`hull`
# has a 40x20 hull (the base config's starting ship), so its hitbox circle is 20px
# in radius. Every distance in this file is centre-to-centre.
HULL_RADIUS = 20.0

# A round fired by :func:`shot` in these tests flies at 10px/frame (the fabricated
# config's bonus, from a stationary shooter), which makes "how many frames until it
# reaches X" pure arithmetic instead of a shrug.
ROUND_SPEED = 10.0


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def combat_config(**tweaks) -> dict:
    """A fabricated config whose fight is small enough to measure.

    Never the shipped files (the spec's rule). ``weapon_range`` is pulled to 300px
    so a round's whole life is a few dozen frames; the speed bonus to 10 so a
    stationary shooter's round steps exactly 10px per frame; jitter to 0 so an
    NPC round goes where the test put it; and the spawn chances to 0 so scene
    tests get the fleet they asked for rather than a lottery.
    """
    config = base_config()
    config["rng"]["seed"] = 20240711
    config["player_ship"].update(
        {"weapon_range": 300, "weapon_fire_rate": 1.0, "weapon_power": 10.0}
    )
    config["combat"].update(
        {
            "projectile_speed_bonus": 10.0,
            "projectile_diameter": 3,
            "pirate_bounty": 10000,
            "bobber_bounty": 5000,
            "localhoster_bounty": 5000,
        }
    )
    config["npc"].update(
        {"spawn_chance_near": 0.0, "spawn_chance_far": 0.0, "aim_jitter_degrees": 0.0}
    )
    for section, values in tweaks.items():
        if section not in config:
            raise KeyError(f"no such config section to tweak: {section!r}")
        config[section].update(values)
    return config


def combat_rules(config: "dict | None" = None) -> CombatRules:
    return CombatRules.from_config((config or combat_config())["combat"])


def starting_stats(config: "dict | None" = None) -> ShipStats:
    return GameState(config or combat_config()).starting_stats


def hull(
    config: "dict",
    faction: str,
    x: float,
    y: float,
    *,
    shields: "float | None" = None,
    armor: "float | None" = None,
    heading: float = 0.0,
    velocity: "tuple[float, float]" = (0.0, 0.0),
) -> NpcShip:
    """One hand-placed NPC hull with variance rolled out of it.

    ``tweaks`` are whole-section overrides, e.g.
    ``combat_config(combat={"pirate_bounty": 0})``.

    ``stat_multiple``/``stat_variance`` are pinned through :func:`roll_npc_stats`
    so the hull's defences are the config's own numbers (the player's starting
    50/100 by default), and the ``shields``/``armor`` overrides let a test start a
    hull one hit away from death without arithmetically reverse-engineering a roll.
    """
    ship = NpcShip(
        faction=faction,
        stats=roll_npc_stats(starting_stats(config), 1.0, 0.0, random.Random(7)),
        position=(x, y),
        heading_degrees=heading,
        velocity=velocity,
    )
    if shields is not None:
        ship.shields = float(shields)
    if armor is not None:
        ship.armor = float(armor)
    return ship


def shot(
    faction: str,
    owner: object,
    origin: "tuple[float, float]",
    direction: "tuple[float, float]",
    *,
    power: float = 10.0,
    weapon_range: float = 300.0,
    ship_velocity: "tuple[float, float]" = (0.0, 0.0),
) -> Shot:
    """A muzzle flash handed to the gunfight, without involving a gun or an AI."""
    return Shot(
        faction=faction,
        owner=owner,
        origin=origin,
        direction=direction,
        ship_velocity=ship_velocity,
        weapon_power=power,
        weapon_range=weapon_range,
    )


def gunfight(config: "dict | None" = None) -> Gunfight:
    return Gunfight(combat_rules(config))


def assert_untouched(ship: NpcShip, config: "dict") -> None:
    """A hull that was never hit still has exactly the defences it was rolled with."""
    starting = starting_stats(config)
    assert ship.shields == starting.shields, f"{ship.faction} hull lost shields it should not have"
    assert ship.armor == starting.armor, f"{ship.faction} hull lost armour it should not have"
    assert ship.destroyed is False


def fly(fight: Gunfight, rounds: int, targets) -> "list":
    """Advance a gunfight, collecting every impact reported along the way."""
    impacts = []
    for _ in range(rounds):
        impacts.extend(fight.advance_frame(targets))
    return impacts


def park_ships_in_scene(scene: "GameScene", *ships: NpcShip, system: str = "Alpha") -> Encounter:
    """Replace a scene's fleet with an exact set of hulls.

    Scene tests need geometry they can reason about, and a rolled fleet is not
    that. The rules object and the relations object are the scene's own, so the
    parked fleet behaves exactly like a rolled one (and any grudge a test earns is
    the session's grudge).
    """
    scene.encounter = Encounter(
        system=system,
        ships=list(ships),
        rules=scene.npc_rules,
        system_pixel_size=scene.game_state.system_pixel_size,
        relations=scene.relations,
    )
    return scene.encounter


class _SpyAudio:
    """Counts the sounds a scene asks for (Stage 12 formalises this pattern)."""

    def __init__(self):
        self.confirm_count = 0
        self.spinup_count = 0
        self.thunderclap_count = 0

    def play_confirm(self):
        self.confirm_count += 1

    def play_jump_spinup(self):
        self.spinup_count += 1

    def play_thunderclap(self):
        self.thunderclap_count += 1


class _StackManager:
    """Enough of SceneManager for GameScene: config, audio, and a real stack."""

    def __init__(self, config: "dict | None" = None):
        self._config = config or combat_config()
        self.audio = _SpyAudio()
        self.stack = []

    def game_config(self) -> dict:
        return self._config

    def push(self, scene) -> None:
        self.stack.append(scene)
        scene.on_enter(self)

    def pop(self) -> None:
        if self.stack:
            self.stack.pop().on_exit()

    @property
    def top(self):
        return self.stack[-1] if self.stack else None


def game_scene(config: "dict | None" = None) -> GameScene:
    """A real GameScene (26-system world, lore book, market, fleet) on a fake stack."""
    manager = _StackManager(config)
    scene = GameScene(manager)
    manager.push(scene)
    return scene


def advance(scene: GameScene, frames: int) -> None:
    for _ in range(frames):
        scene.update()


def press(scene: GameScene, key: int) -> None:
    scene.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key, scancode=0, mod=0))


def release(scene: GameScene, key: int) -> None:
    """Let go of a key (see the Stage 10 note: press+release in one frame is nothing)."""
    scene.handle_event(pygame.event.Event(pygame.KEYUP, key=key, scancode=0, mod=0))


def tap(scene: GameScene, key: int) -> None:
    """One real keypress: press, let a frame drain the rising edge, then release."""
    press(scene, key)
    scene.update()
    release(scene, key)


def jump(scene: GameScene, destination: str, limit: int = 400) -> None:
    """Fly a scene to ``destination`` the way the player does: select, tap J, wait."""
    scene.game_state.set_position(600.0, 0.0)
    scene.system_map.select(destination)
    press(scene, pygame.K_j)
    scene.update()
    release(scene, pygame.K_j)
    for _ in range(limit):
        scene.update()
        if scene.system_map.current_system == destination and not scene.jumps.is_active:
            return
    raise AssertionError(
        f"never arrived at {destination}: system={scene.system_map.current_system!r} "
        f"jump phase={scene.jumps.phase!r} fuel={scene.game_state.fuel}"
    )


def count_launches(fight: Gunfight) -> "list[Shot]":
    """Every shot the gunfight is handed, in order (a launch counter, not a spy on maths)."""
    launched: "list[Shot]" = []
    original = fight.launch

    def counting_launch(fired: Shot):
        launched.append(fired)
        return original(fired)

    fight.launch = counting_launch  # type: ignore[method-assign]
    return launched


def _count_colour_in(
    canvas: "pygame.Surface", region: "tuple[int, int, int, int]", colour: "tuple[int, int, int]"
) -> int:
    """Pixels painted exactly ``colour`` inside ``(x0, y0, x1, y1)``."""
    x0, y0, x1, y1 = region
    hits = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            if canvas.get_at((x, y))[:3] == colour:
                hits += 1
    return hits


# ===========================================================================
# The combat rules (config, and the one place units get converted)
# ===========================================================================


def testcombatRules_fromConfig_shouldCarryEveryTunableInTheCombatSection():
    """GIVEN the fabricated combat section, THEN every knob is readable."""
    rules = combat_rules()

    assert rules.projectile_speed_bonus == 10.0
    assert rules.projectile_diameter == 3
    assert rules.pirate_bounty == 10000.0
    assert rules.bobber_bounty == 5000.0
    assert rules.localhoster_bounty == 5000.0


def testcombatRules_shippedConfigs_shouldAllDefineADiameterAndNoLongerARadius():
    """The key is named for the measurement the spec fixes, in all three files.

    ``projectile_radius`` used to say "radius" while shipping the value 3, which is
    the spec's *diameter*. Unrecognised config keys are fatal, so a config that
    still carried the old name would not start — which is the correct outcome, and
    the next test pins it.
    """
    for name in CONFIG_FILES:
        combat = load_config(GAME_ROOT)[name]["combat"]
        assert "projectile_diameter" in combat, f"{name} is missing the diameter key"
        assert "projectile_radius" not in combat, f"{name} still carries the old key"
        assert combat["projectile_diameter"] == 3, f"{name} should keep the spec's 3px"


def testloadConfig_withTheRetiredProjectileRadiusKey_shouldFailAsAnUnknownKey(config_factory):
    """GIVEN a config carrying the retired key, THEN startup refuses it (extra=forbid)."""
    directory = config_factory(overrides={"combat.projectile_radius": 3})

    with pytest.raises(ConfigLoadError):
        load_config(directory)


def testcombatRules_projectileRadius_shouldConvertTheSpecs3pxDiameterToADrawRadius():
    """A 3px-diameter circle is pygame ``draw.circle`` radius 1, in exactly one place.

    Pinned because the alternative is every call site doing its own conversion, and
    then "3px" means 3px on the tactical display and 6px anywhere else.
    """
    assert CombatRules(10.0, 3, 0, 0, 0).projectile_radius == 1
    assert CombatRules(10.0, 5, 0, 0, 0).projectile_radius == 2
    # A 1px request still has to be visible, so the drawing radius never collapses
    # to zero (a zero-radius circle is nothing at all).
    assert CombatRules(10.0, 1, 0, 0, 0).projectile_radius == 1


@pytest.mark.parametrize(
    "override",
    [
        {"projectile_speed_bonus": -1.0},
        {"projectile_diameter": 0},
        {"projectile_diameter": -3},
        {"pirate_bounty": -1},
        {"bobber_bounty": -1},
        {"localhoster_bounty": -1},
    ],
)
def testcombatRules_withAnImpossibleValue_shouldBeRejectedAtConstruction(override):
    """An invalid rules object cannot exist, whoever built it (loader, test, save file).

    Same lesson Stage 10 recorded for ``SpawnRules``: validation that lives only in
    ``from_config`` leaves a directly-constructed nonsense object free to reach a
    dogfight and fail there.
    """
    values = {
        "projectile_speed_bonus": 8.0,
        "projectile_diameter": 3,
        "pirate_bounty": 10000,
        "bobber_bounty": 5000,
        "localhoster_bounty": 5000,
    }
    values.update(override)

    with pytest.raises(ValueError):
        CombatRules(**values)


def testcombatRules_fromConfig_withAMissingOrJunkKey_shouldReportAConfigFailure():
    """A hand-built config (tooling, saves) fails with a combat-shaped message."""
    with pytest.raises(ValueError, match="invalid combat config section"):
        CombatRules.from_config({"projectile_speed_bonus": 8.0})


def testcombatRules_bountyFor_shouldBeKeyedByTheVictimNotThePayer():
    """``localhoster_bounty`` is what killing a Localhoster pays.

    Both shipped configs set all three bounties the same, so nothing but this test
    and the docstring says which way the mapping runs — and getting it backwards is
    invisible until someone changes one value and the wrong faction starts paying.
    """
    rules = CombatRules(8.0, 3, 10000, 2000, 500)

    assert rules.bounty_for(FACTION_PIRATE) == 10000
    assert rules.bounty_for(FACTION_LOCALHOSTER) == 500
    assert rules.bounty_for(FACTION_BOBBER) == 2000


# ===========================================================================
# Combatants, the player included
# ===========================================================================


def testcombatVocabulary_thePlayerIsACombatantButNeverAFaction():
    """The player gets provenance and a colour, and no row in the hostility matrix.

    Letting ``"player"`` into the matrix would let code ask "is a pirate hostile to
    the player?" of a table that cannot answer it — the player's relations are a
    separate, mutable thing (`PlayerRelations`), and the matrix is what the AI reads.
    """
    assert FACTION_PLAYER not in FACTIONS
    assert FACTION_PLAYER in COMBATANTS
    assert is_npc_faction(FACTION_PIRATE) is True
    assert is_npc_faction(FACTION_PLAYER) is False
    assert require_combatant(FACTION_PLAYER) == FACTION_PLAYER

    assert combatant_color(FACTION_PLAYER) == (60, 220, 60)
    for faction in FACTIONS:
        assert combatant_color(faction) == faction_color(faction)


def testcombatantColor_withAnUnknownSide_shouldRaiseRatherThanGuessGreen():
    with pytest.raises(ValueError):
        combatant_color("smugglers")


def testwarSideOf_theWarsidesAreEachOthersRivalAndPiratesHaveNone():
    """The bounty payer for a war-side kill is the other war-side; pirates pay up front."""
    assert war_side_of(FACTION_LOCALHOSTER) == FACTION_BOBBER
    assert war_side_of(FACTION_BOBBER) == FACTION_LOCALHOSTER
    with pytest.raises(ValueError):
        war_side_of(FACTION_PIRATE)


def testcombatant_fromPlayer_shouldCarryTheLiveImmunityFlag():
    """Landed or in the launch grace period means unhittable, copied at snapshot time.

    The flag is read when the frame's target list is built, not when the damage is
    about to land, so a round cannot be half-absorbed by a state that changed
    mid-frame.
    """
    state = GameState(combat_config())
    assert Combatant.from_player(state).immune is False
    assert Combatant.from_player(state).faction == FACTION_PLAYER

    state.land("Alpha")
    assert Combatant.from_player(state).immune is True


# ===========================================================================
# Velocity composition and the travel budget
# ===========================================================================


def testprojectile_fromStationaryShot_shouldTravelAlongTheAimAtTheConfiguredBonus():
    """Spec: 8 px/frame along the facing direction, from a ship standing still."""
    rules = CombatRules(projectile_speed_bonus=8.0, projectile_diameter=3,
                        pirate_bounty=0, bobber_bounty=0, localhoster_bounty=0)
    fired = shot(FACTION_PLAYER, object(), (0.0, 0.0), (1.0, 0.0))

    round_in_flight = Projectile.from_shot(fired, rules)

    assert round_in_flight.velocity == pytest.approx((8.0, 0.0))


def testprojectile_fromShot_shouldAddTheFiringShipsOwnVelocityToTheMuzzleSpeed():
    """Spec: "the ship's velocity plus 8 px/frame in the ship's facing direction".

    A round fired from a ship doing 6px/frame east is doing 14 east; fired while
    drifting north it keeps that north component too. This is the gate's
    "velocity-composition math", and it is one function for every hull.
    """
    rules = combat_rules()
    fired = shot(
        FACTION_PIRATE, object(), (0.0, 0.0), (1.0, 0.0), ship_velocity=(6.0, -3.0)
    )

    assert Projectile.from_shot(fired, rules).velocity == pytest.approx((16.0, -3.0))


def testprojectile_fromShot_shouldHonourWhateverBonusTheConfigAsksFor():
    """The bonus is config, not a literal: three configs, three muzzle speeds."""
    for bonus in (4.0, 8.0, 20.0):
        rules = CombatRules(bonus, 3, 0, 0, 0)
        fired = shot(FACTION_PLAYER, object(), (0.0, 0.0), (0.0, 1.0))

        assert Projectile.from_shot(fired, rules).velocity == pytest.approx((0.0, bonus))


def testprojectile_fromShot_shouldTakeItsTravelBudgetFromTheGunThatFiredIt():
    """Spec: "a max cumulative travel distance of ``player_ship.weapon_range``".

    NPC guns are copied from the player's starting stats, so the range travels with
    the shot rather than being looked up from the shooter (which the projectile
    simulation does not have) or read from a config section it may not match.
    """
    rules = combat_rules()
    fired = shot(FACTION_BOBBER, object(), (0.0, 0.0), (1.0, 0.0), weapon_range=250.0)

    round_in_flight = Projectile.from_shot(fired, rules)
    assert round_in_flight.max_travel == 250.0
    assert round_in_flight.range_left == 250.0
    assert round_in_flight.spent is False


def testprojectile_step_shouldCountWorldSpaceTravelIncludingTheShipsOwnMotion():
    """A round fired from a moving ship runs out of range sooner in world terms.

    The budget is the distance the round actually crossed, which is what "travel
    distance" means when the muzzle was already moving: the same gun, the same
    round, more ground covered per frame.
    """
    rules = combat_rules()
    fired = shot(
        FACTION_PLAYER, object(), (0.0, 0.0), (1.0, 0.0),
        ship_velocity=(5.0, 0.0), weapon_range=60.0,
    )
    round_in_flight = Projectile.from_shot(fired, rules)

    start, end = round_in_flight.step()

    assert end == pytest.approx((15.0, 0.0))
    assert round_in_flight.travelled == pytest.approx(15.0)
    assert round_in_flight.range_left == pytest.approx(45.0)


# ===========================================================================
# Firing the player's gun: the fire-rate gate
# ===========================================================================


def testweaponClock_shouldAllowExactlyOneShotPerConfiguredCycle():
    """One clock, one rate: a gun that takes 60 frames to cycle may be pulled once.

    Pinned on the clock itself because two owners of the fire rate (a gun and an AI,
    or a gun and a scene) is the classic way to end up firing at double the
    configured rate.
    """
    clock = WeaponClock()

    assert clock.ready is True
    assert clock.pull(60.0) is True
    assert clock.pull(60.0) is False
    assert clock.frames_until_ready == 60.0

    for _ in range(59):
        clock.advance_frame()
    assert clock.ready is False
    clock.advance_frame()
    assert clock.pull(60.0) is True


def testweaponClock_withAnInfiniteCycle_shouldBeImpossibleToFireFromTheFirstFrame():
    """A disabled weapon is a state, not a crash, and it has no free first shot.

    A clock born ready would let a hull with a zero fire rate get exactly one shot
    off before the infinity landed — which is the kind of bug that only shows up in
    a config someone edited by hand.
    """
    for rate in (0.0, -1.0):
        cooldown = weapon_cooldown_frames(rate)
        clock = WeaponClock()
        for _ in range(240):
            assert clock.pull(cooldown) is False
            clock.advance_frame()


def testweaponClock_withAFasterCycleMidFight_shouldApplyToTheVeryNextShot():
    """The cycle length is handed in at the pull, so an upgrade is never stale.

    A clock that memorised the fire rate would keep the boot-time rate for the rest
    of the run, and a player who bought a faster gun would see no difference until
    they died and restarted — the same trap the shot's power and range avoid.
    """
    clock = WeaponClock()

    assert clock.pull(60.0) is True
    for _ in range(60):
        clock.advance_frame()

    assert clock.pull(20.0) is True
    assert clock.frames_until_ready == 20.0
    for _ in range(20):
        clock.advance_frame()
    assert clock.pull(20.0) is True


def testgameState_gunCooldownFrames_shouldComeFromTheLiveStatBlock():
    """The hull reports its own cycle length, upgrades included."""
    state = GameState(combat_config())

    assert state.gun_cooldown_frames == pytest.approx(60.0)

    state.stats.weapon_fire_rate = 3.0
    assert state.gun_cooldown_frames == pytest.approx(20.0)


def testgameState_tryFire_shouldProduceAShotFromTheShipsFacingAndVelocity():
    """The player's gun produces the same :class:`Shot` record an NPC's gun does.

    One muzzle vocabulary for both sides means the projectile simulation has one
    ballistics rule, and the "only player rounds earn a bounty" rule is an identity
    check on ``owner`` rather than a faction lookup.
    """
    state = GameState(combat_config())
    state.set_position(100.0, -50.0)
    state.heading = 90.0  # south, in this y-down convention

    fired = state.try_fire()

    assert fired is not None
    assert fired.faction == FACTION_PLAYER
    assert fired.owner is state
    assert fired.origin == (100.0, -50.0)
    assert fired.direction == pytest.approx((0.0, 1.0))
    assert fired.weapon_power == state.stats.weapon_power
    assert fired.weapon_range == state.stats.weapon_range


def testgameState_tryFire_holdingTheTrigger_shouldGiveTheConfiguredShotsPerSecond():
    """Spec: "holding space will release the configured number of projectiles per second".

    Three seconds at 2/s is six shots, no more: the input layer hands over a fire
    action on *every* frame space is held, so the clock is the only thing between a
    held key and sixty shots a second.
    """
    state = GameState(combat_config(player_ship={"weapon_fire_rate": 2.0}))

    fired = 0
    for _ in range(180):
        state.advance_frame()
        if state.try_fire() is not None:
            fired += 1

    assert fired == 6, f"expected 6 shots in 3 seconds at 2/s, got {fired}"


def testgameState_tryFire_whileReloading_shouldSayNothingAndQueueNothing():
    """A reload is a silent no, not a queued shot that arrives late.

    Tapping space faster than the gun cycles must not build a backlog, or the fire
    rate stops being a config value and becomes "as fast as the player can tap". And
    a rejected pull must not touch the countdown: a rejected tap that restarted the
    clock would make the gun slower the more often the player taps it.
    """
    state = GameState(combat_config(player_ship={"weapon_fire_rate": 1.0}))

    first = state.try_fire()
    taps = [state.try_fire() for _ in range(30)]

    assert first is not None
    assert all(fired is None for fired in taps), "a reloading gun queued or fired early"
    assert state.gun_frames_until_ready == 60.0, "a rejected pull moved the clock"

    for _ in range(59):
        state.advance_frame()
    assert state.try_fire() is None, "the clock came up one frame early"
    state.advance_frame()
    assert state.try_fire() is not None


@pytest.mark.parametrize(
    "condition",
    ["landed", "jumping", "destroyed"],
)
def testgameState_tryFire_whenTheShipCannotFight_shouldFireNothing(condition):
    """On the ground, in hyperspace, or in pieces, the trigger does nothing.

    A wreck getting one last shot off, or a ship shooting through its own
    hyperspace burn, are both states the player would call a bug.
    """
    state = GameState(combat_config())
    if condition == "landed":
        state.land("Alpha")
    elif condition == "jumping":
        state.begin_jump(1.0)
    else:
        state.apply_damage(10_000.0)
        assert state.destroyed is True

    assert state.try_fire() is None


def testgameState_gunClock_shouldKeepCyclingWhileJumpedOrParked():
    """A weapon that stops counting during a jump is an unconfigured rate bonus.

    Two jumps of 180 frames on a 1/s gun: the trigger is ready again long before
    the player arrives, which is the honest reading of "cycling" — the gun was
    cycling the whole time, it just had nothing to shoot.
    """
    state = GameState(combat_config(player_ship={"weapon_fire_rate": 1.0}))
    state.try_fire()
    state.begin_jump(1.0)

    for _ in range(180):
        state.advance_frame()
    state.end_jump()

    assert state.gun_frames_until_ready == 0.0
    assert state.try_fire() is not None


# ===========================================================================
# The gunfight: travel, expiry, and who may be hit
# ===========================================================================


def testgunfight_launch_thenAdvance_shouldMoveTheRoundAndKeepItInFlight():
    """A launched round is in the fight, and steps once per frame."""
    fight = gunfight()
    target_ship = hull(combat_config(), FACTION_PIRATE, 5000.0, 5000.0)
    fight.launch(shot(FACTION_PIRATE, target_ship, (0.0, 0.0), (1.0, 0.0)))

    fight.advance_frame([])

    assert len(fight) == 1
    assert fight.projectiles[0].position == pytest.approx((ROUND_SPEED, 0.0))


def testgunfight_shouldRemoveARoundExactlyWhenItSpendsItsTravelBudget():
    """300px of range at 10px/frame is 30 frames, then the round dies harmlessly.

    Frame-exact: a round that lingers is a weapon with a longer range than the
    config paid for, and a round that dies early is the same lie in the other
    direction.
    """
    fight = gunfight()
    fight.launch(
        shot(FACTION_PLAYER, object(), (0.0, 0.0), (1.0, 0.0), weapon_range=300.0)
    )

    for frame in range(1, 30):
        assert fight.advance_frame([]) == []
        assert len(fight) == 1, f"round vanished on frame {frame}"

    assert fight.advance_frame([]) == []
    assert len(fight) == 0, "the round outlived its configured range"


def testgunfight_aRoundShouldPassHarmlesslyThroughTheShipThatFiredIt():
    """Gate item: projectiles cannot hit their owner.

    The shooter is sitting *inside* its own hitbox at the moment of firing, so
    without this rule every muzzle flash would be a suicide. The round must also
    still be in flight afterwards — "harmlessly" is not "removed".
    """
    config = combat_config()
    pirate = hull(config, FACTION_PIRATE, 0.0, 0.0)
    fight = gunfight(config)
    fight.launch(shot(FACTION_PIRATE, pirate, (0.0, 0.0), (1.0, 0.0)))

    impacts = fight.advance_frame([Combatant.from_ship(pirate)])

    assert impacts == []
    assert len(fight) == 1
    assert_untouched(pirate, config)

    # And the exemption is by identity, not by appearance: another hull parked on
    # the same spot, of a faction the round may hit, takes it. The owner is still
    # listed as a target, so the pass-through is not a filtering accident.
    neighbour = hull(config, FACTION_LOCALHOSTER, 0.0, 0.0)
    other_fight = gunfight(config)
    other_fight.launch(shot(FACTION_PIRATE, pirate, (0.0, 0.0), (1.0, 0.0), power=5.0))
    impacts = other_fight.advance_frame(
        [Combatant.from_ship(pirate), Combatant.from_ship(neighbour)]
    )

    assert len(impacts) == 1
    assert impacts[0].target is neighbour
    assert_untouched(pirate, config)


def testgunfight_aRoundShouldPassThroughItsOwnFactionButNotAnotherS():
    """Spec: "projectiles fired from any faction ship pass harmlessly through other ships of the same faction".

    One Bobber round, one Bobber hull, one Pirate hull: the Bobber is untouched,
    the Pirate is not, and no friendly fire is possible in either direction.
    """
    config = combat_config()
    shooter = hull(config, FACTION_BOBBER, 0.0, 0.0)
    friend = hull(config, FACTION_BOBBER, 40.0, 0.0)
    foe = hull(config, FACTION_PIRATE, 80.0, 0.0)
    fight = gunfight(config)
    fight.launch(shot(FACTION_BOBBER, shooter, (0.0, 0.0), (1.0, 0.0), power=7.0))

    impacts = fly(
        fight,
        8,
        [Combatant.from_ship(friend), Combatant.from_ship(foe)],
    )

    assert len(impacts) == 1, "friendly fire, or the round missed the pirate"
    assert impacts[0].target is foe
    assert_untouched(friend, config)  # a same-faction hull must not absorb the round


def testgunfight_aPlayerRound_shouldBeAbleToHitEveryNpcFaction():
    """The player has no faction, so no NPC is "same side" with them.

    A player round passing through a Localhoster because both were treated as one
    side would hide the hostility rule entirely: nothing would ever make the
    war-sides angry.
    """
    for faction in FACTIONS:
        config = combat_config()
        state = GameState(config)
        victim = hull(config, faction, 20.0, 0.0)
        fight = gunfight(config)
        fight.launch(shot(FACTION_PLAYER, state, (0.0, 0.0), (1.0, 0.0), power=4.0))

        impacts = fight.advance_frame([Combatant.from_player(state), Combatant.from_ship(victim)])

        assert len(impacts) == 1, f"a player round passed through a {faction}"
        assert impacts[0].target_faction == faction


def testgunfight_anImmuneHull_shouldBePassedThroughAndNotConsumeTheRound():
    """Landed or in the launch grace period: the round keeps flying.

    Immunity has to mean "not there for this round", not "absorbed it": consuming
    the round on an immune hull would make a grace period a free magazine emptying
    line, and would report an impact the player cannot see.
    """
    config = combat_config()
    state = GameState(config)
    state.land("Alpha")
    fight = gunfight(config)
    fight.launch(shot(FACTION_PIRATE, object(), (0.0, 0.0), (1.0, 0.0), power=40.0))

    impacts = fly(fight, 5, [Combatant.from_player(state)])

    assert impacts == []
    assert len(fight) == 1
    assert state.stats.armor == state.starting_stats.max_armor


def testgunfight_aDestroyedHullIsNotInTheWayAnythingAnymore():
    """Wrecks are pruned from the fleet, so nothing shoots a corpse for a second bounty.

    Asserted here on the prune rather than through the gunfight, because the
    gunfight is handed the fleet: if the fleet is right, the gunfight cannot be
    wrong about what is standing in it.
    """
    config = combat_config()
    wreck = hull(config, FACTION_PIRATE, 0.0, 0.0, armor=0.0)
    alive = hull(config, FACTION_BOBBER, 100.0, 0.0)
    encounter = Encounter(
        system="Bravo",
        ships=[wreck, alive],
        rules=SpawnRules.from_config(config["npc"]),
        system_pixel_size=2000.0,
        relations=PlayerRelations(),
    )

    removed = encounter.prune_destroyed()

    assert removed == [wreck]
    assert encounter.ships == (alive,)
    assert encounter.prune_destroyed() == []
    assert encounter.nearest_ship_to((0.0, 0.0)) is alive


# ===========================================================================
# The hit test: swept, not sampled
# ===========================================================================


def testsegmentEntryParameter_shouldCatchAFastRoundThatSpansTheWholeHullInOneStep():
    """A 100px step straight through a 20px-radius hull is still a hit.

    A point test at the endpoint would call this a miss, and the player would watch
    a round travel down the middle of a ship that never took damage. The shipped
    numbers make this real: ``projectile_speed_bonus`` 10 plus a shooter doing 6
    is a 16px step against a 20px hitbox radius.
    """
    entry = segment_entry_parameter((0.0, 0.0), (100.0, 0.0), (50.0, 0.0), HULL_RADIUS)

    assert entry is not None
    assert 0.0 < entry < 1.0
    assert entry == pytest.approx(0.3)  # enters the circle at x = 30


def testsegmentEntryParameter_shouldReturnZeroWhenTheRoundStartsInsideTheHull():
    """Point-blank: a round born inside a hitbox has already entered it."""
    assert segment_entry_parameter((50.0, 0.0), (60.0, 0.0), (50.0, 0.0), HULL_RADIUS) == 0.0


def testsegmentEntryParameter_shouldMissCleanlyOnEitherSide():
    """Parallel and short of the hull: no entry, no imaginary hit."""
    assert segment_entry_parameter((0.0, 0.0), (100.0, 0.0), (50.0, 60.0), HULL_RADIUS) is None
    assert segment_entry_parameter((0.0, 0.0), (10.0, 0.0), (100.0, 0.0), HULL_RADIUS) is None


def testpointHitsCircle_shouldUseTheSameBoundaryAsTheSweptTest():
    """The spec's wording ("enters that circle") and the swept maths agree.

    Inside is a hit, exactly on the edge is a hit, one pixel outside is not. The
    hitbox radius is the ship's longest axis over two, so a 40x20 hull is a 20px
    circle: 20.0 in, 20.001 out.
    """
    assert point_hits_circle((50.0, 0.0), (50.0, 0.0), HULL_RADIUS) is True
    assert point_hits_circle((70.0, 0.0), (50.0, 0.0), HULL_RADIUS) is True
    assert point_hits_circle((70.5, 0.0), (50.0, 0.0), HULL_RADIUS) is False


def testgunfight_aFullFrameStepAcrossAHullShouldStillReportOneImpact():
    """The swept test wired into the fight, not just into the geometry helper.

    A round stepping 90px in one frame from a hull doing that much: the endpoint
    sample is on the far side of the victim, so a point test reports a miss.
    """
    config = combat_config()
    victim = hull(config, FACTION_PIRATE, 50.0, 0.0)
    shooter = hull(config, FACTION_LOCALHOSTER, 0.0, 0.0)
    fight = gunfight(config)
    fight.launch(
        shot(
            FACTION_LOCALHOSTER, shooter, (0.0, 0.0), (1.0, 0.0),
            power=5.0, ship_velocity=(90.0, 0.0), weapon_range=400.0,
        )
    )

    impacts = fight.advance_frame([Combatant.from_ship(victim)])

    assert len(impacts) == 1
    assert victim.shields == pytest.approx(45.0)


def testgunfight_twoHullsOnOnePath_shouldHitTheOneEnteredFirstNotTheFirstInTheList():
    """Order-independence: the geometry decides, not the list order.

    Same frame, two target lists in opposite orders. A hit resolution that walked
    the list and stopped at the first hitbox would attribute the damage to
    whichever hull happened to be spawned earlier, which is the same class of
    spawn-order bug Stage 10 pinned for the AI's target choice.
    """
    config = combat_config()
    near = hull(config, FACTION_PIRATE, 40.0, 0.0)
    far = hull(config, FACTION_PIRATE, 90.0, 0.0)

    orders = ([near, far], [far, near])
    targets_hit = []
    for order in orders:
        fight = gunfight(config)
        # A 70px step, chosen so the sweep enters *both* hitboxes inside the same
        # frame: that is the only arrangement where the resolution order could
        # matter at all.
        fight.launch(
            shot(
                FACTION_BOBBER, object(), (0.0, 0.0), (1.0, 0.0),
                power=5.0, ship_velocity=(60.0, 0.0), weapon_range=400.0,
            )
        )
        impacts = fight.advance_frame([Combatant.from_ship(ship) for ship in order])
        assert len(impacts) == 1, "one sweep should spend the round once"
        targets_hit.append(impacts[0].target)
        assert len(fight) == 0, "a round that hit something kept flying"

    assert targets_hit[0] is targets_hit[1] is near


def testgunfight_oneRoundShouldDamageAtMostOneHull():
    """A round is spent on the first hull it enters: no perforating a formation."""
    config = combat_config()
    first = hull(config, FACTION_BOBBER, 30.0, 0.0)
    second = hull(config, FACTION_LOCALHOSTER, 60.0, 0.0)
    fight = gunfight(config)
    fight.launch(shot(FACTION_PIRATE, object(), (0.0, 0.0), (1.0, 0.0), power=5.0))

    impacts = fly(fight, 20, [Combatant.from_ship(first), Combatant.from_ship(second)])

    assert len(impacts) == 1
    assert_untouched(second, config)


def testgunfight_impactPosition_shouldBeThePointTheRoundEnteredTheHitbox():
    """Where the sparks go: the entry point, not the muzzle or the hull's centre.

    A burst at a hull's centre for a round that grazed the rim would read as a
    hit that never quite happened, and vice versa.
    """
    config = combat_config()
    victim = hull(config, FACTION_PIRATE, 105.0, 0.0)
    fight = gunfight(config)
    fight.launch(shot(FACTION_PLAYER, object(), (10.0, 0.0), (1.0, 0.0)))

    impacts = fly(fight, 8, [Combatant.from_ship(victim)])

    assert len(impacts) == 1
    assert impacts[0].position[0] == pytest.approx(105.0 - HULL_RADIUS)
    assert impacts[0].position[1] == pytest.approx(0.0)


def testgunfight_aRoundBornInsideAHullShouldHitItAtTheMuzzlePoint():
    """Documented edge case: hulls overlap, so a round can be born inside a victim.

    There is no hull-on-hull collision in this game, so two ships can occupy the
    same water. The swept test reports an entry parameter of 0.0 for a round already
    inside, and the impact is recorded at the muzzle point rather than ignored — "you
    were inside me, therefore my gun does nothing" is the worse rule of the two.
    """
    config = combat_config()
    victim = hull(config, FACTION_PIRATE, 105.0, 0.0)
    fight = gunfight(config)
    fight.launch(shot(FACTION_PLAYER, object(), (100.0, 0.0), (1.0, 0.0)))

    impacts = fight.advance_frame([Combatant.from_ship(victim)])

    assert len(impacts) == 1
    assert impacts[0].position == pytest.approx((100.0, 0.0))
    assert victim.shields == pytest.approx(starting_stats(config).shields - 10.0)


def testnearestLivingShip_shouldSkipWrecksAndBreakTiesBySpawnOrder():
    """The query both the HUD readout and the scan use, once.

    Ties are settled by spawn order so two hulls parked symmetrically around the
    player produce the same answer every frame, instead of the readout flickering
    between them.
    """
    config = combat_config()
    alive = hull(config, FACTION_PIRATE, 400.0, 0.0)
    wreck = hull(config, FACTION_BOBBER, 10.0, 0.0, armor=-5.0)

    assert nearest_living_ship([wreck, alive], (0.0, 0.0)) is alive
    assert nearest_living_ship([], (0.0, 0.0)) is None

    left = hull(config, FACTION_PIRATE, 100.0, 0.0)
    right = hull(config, FACTION_PIRATE, -100.0, 0.0)
    assert nearest_living_ship([left, right], (0.0, 0.0)) is left
    assert nearest_living_ship([right, left], (0.0, 0.0)) is right


# ===========================================================================
# Damage order and destruction
# ===========================================================================


def testapplyDamageOrder_shouldSpendShieldsBeforeTouchingTheHull():
    """Gate item, and one implementation for both sides of the fight.

    30 damage into 50 shields: shields 20, hull 100. 70 damage into 50 shields:
    shields 0, hull 80. The split is exact at the boundary — a shield that soaks
    exactly the right amount leaves the hull untouched.
    """
    assert apply_damage_order(50.0, 100.0, 30.0) == (20.0, 100.0)
    assert apply_damage_order(50.0, 100.0, 50.0) == (0.0, 100.0)
    assert apply_damage_order(50.0, 100.0, 70.0) == (0.0, 80.0)
    assert apply_damage_order(0.0, 100.0, 10.0) == (0.0, 90.0)
    assert apply_damage_order(50.0, 100.0, -5.0) == (50.0, 100.0)


def testapplyDamageOrder_shouldNotClampNegativeArmour():
    """"Dead" and "very dead" must be different numbers, or overkill is invisible.

    Nothing in the game reads the difference today; the point is that no future
    consumer (a run-stat screen, a "how badly you were hit" cue) has to undo a
    clamp to find out.
    """
    assert apply_damage_order(0.0, 10.0, 999.0) == (0.0, -989.0)


def testnpcShipDamageThroughAGunfight_shouldFollowThatOrderAndReportDestruction():
    """A pirate hit twice for 40 into 50/100: shields gone, hull at 70, not destroyed;
    a third hit for 40 takes the hull to 30; lethal damage reports ``destroyed``."""
    config = combat_config()
    pirate = hull(config, FACTION_PIRATE, 30.0, 0.0, shields=50.0, armor=100.0)
    shooter = object()
    fight = gunfight(config)

    def hit(power: float):
        fight.launch(shot(FACTION_PLAYER, shooter, (0.0, 0.0), (1.0, 0.0), power=power))
        return fight.advance_frame([Combatant.from_ship(pirate)])

    first = hit(40.0)
    assert pirate.shields == pytest.approx(10.0) and pirate.armor == 100.0
    assert first[0].destroyed is False

    hit(40.0)
    assert pirate.shields == 0.0 and pirate.armor == pytest.approx(70.0)

    second_round = hit(80.0)
    assert pirate.armor == pytest.approx(-10.0)
    assert pirate.destroyed is True
    assert second_round[0].destroyed is True
    assert second_round[0].damage == 80.0


def testgameState_applyDamage_shouldUseTheSameOrderAsAnNpcHull():
    """The player's defences obey the rule the NPCs obey — one function, two callers."""
    state = GameState(combat_config())

    state.apply_damage(20.0)
    assert state.stats.shields == pytest.approx(30.0)
    assert state.stats.armor == 100.0

    state.apply_damage(80.0)
    assert state.stats.shields == 0.0
    # 30 of those 80 was spent by the shields; the hull eats the other 50.
    assert state.stats.armor == pytest.approx(50.0)
    assert state.destroyed is False

    state.apply_damage(50.0)
    assert state.stats.armor == 0.0
    assert state.destroyed is True


def testgunfight_anNpcRoundShouldDamageThePlayerEvenFromANeutralFaction():
    """A stray round from a faction that is not at war with the player still hurts.

    Hostility decides who *aims* at you; geometry decides who clips you. There is
    no "dodge damage from people who like you" rule in the spec, and an invisible
    damage exemption would be indistinguishable from the round missing.
    """
    config = combat_config()
    state = GameState(config)
    shooter = hull(config, FACTION_LOCALHOSTER, 0.0, 0.0)
    fight = gunfight(config)
    fight.launch(shot(FACTION_LOCALHOSTER, shooter, (0.0, 0.0), (1.0, 0.0), power=25.0))

    impacts = fight.advance_frame([Combatant.from_player(state), Combatant.from_ship(shooter)])

    assert len(impacts) == 1
    assert impacts[0].hit_player is True
    assert state.stats.shields == pytest.approx(25.0)


# ===========================================================================
# The scan (T): sticky, re-scan, reversion, reset
# ===========================================================================


def testshipScanner_pressingT_shouldLockOntoTheNearestLivingHull():
    """The scan picks the nearest hull in the system, whatever its faction."""
    config = combat_config()
    far = hull(config, FACTION_PIRATE, 500.0, 0.0)
    near = hull(config, FACTION_BOBBER, 120.0, 0.0)
    scanner = ShipScanner()

    assert scanner.displayed is None
    assert scanner.scan([far, near], (0.0, 0.0)) is near
    assert scanner.has_target is True


def testshipScanner_pressingTInAnEmptySystem_shouldDisplayNothing():
    """Nothing to scan, nothing displayed: "No target" rather than a stale lock."""
    scanner = ShipScanner()

    assert scanner.scan([], (0.0, 0.0)) is None
    assert scanner.has_target is False


def testshipScanner_theLockIsSticky_whenAnotherHullBecomesNearest():
    """Spec: "the currently-displayed ship remains displayed even if it is no longer the nearest".

    The player chose to look at that hull. A readout that follows whoever drifts
    closest is unusable in a dogfight, which is the only time it is being read. The
    frames between presses are covered by :meth:`ShipScanner.refresh`, which is what
    the scene calls each frame — no key, no re-lock.
    """
    config = combat_config()
    chosen = hull(config, FACTION_PIRATE, 100.0, 0.0)
    interloper = hull(config, FACTION_BOBBER, 200.0, 0.0)
    scanner = ShipScanner()

    scanner.scan([chosen, interloper], (0.0, 0.0))
    assert scanner.displayed is chosen

    interloper.position = (10.0, 0.0)
    scanner.refresh()

    assert scanner.displayed is chosen
    assert nearest_living_ship([chosen, interloper], (0.0, 0.0)) is interloper


def testshipScanner_pressingTAgain_shouldReLockOnTheCurrentNearest():
    """A press is a re-scan; stickiness governs the frames in between, not the key.

    A second press that did nothing would leave the player staring at a pirate who
    fled to the far side of the system, with no way to look at the hull that is now
    pointed at them. The spec's named no-op is re-scanning when the lock is *already*
    the nearest hull.
    """
    config = combat_config()
    chosen = hull(config, FACTION_PIRATE, 100.0, 0.0)
    interloper = hull(config, FACTION_BOBBER, 200.0, 0.0)
    scanner = ShipScanner()

    scanner.scan([chosen, interloper], (0.0, 0.0))
    assert scanner.displayed is chosen

    interloper.position = (10.0, 0.0)
    assert scanner.scan([chosen, interloper], (0.0, 0.0)) is interloper

    again = scanner.scan([chosen, interloper], (0.0, 0.0))
    assert again is interloper, "re-scanning when the lock is already nearest changed it"


def testshipScanner_aDestroyedTargetRevertsToNoTargetWithoutAnotherKeyPress():
    """Spec: "if the currently-displayed ship is destroyed, this component reverts to No target"."""
    victim = hull(combat_config(), FACTION_PIRATE, 100.0, 0.0, shields=1.0, armor=1.0)
    scanner = ShipScanner()
    scanner.scan([victim], (0.0, 0.0))
    assert scanner.displayed is victim

    victim.apply_damage(50.0)
    scanner.refresh()

    assert scanner.displayed is None
    assert scanner.refresh() is None


def testshipScanner_refreshingAnEmptySystemOrANewGame_dropsNothingButTheLock():
    """``refresh`` on no lock is a no-op, and ``clear`` is the new-system reset."""
    chosen = hull(combat_config(), FACTION_PIRATE, 100.0, 0.0)
    scanner = ShipScanner(displayed=chosen)

    scanner.clear()

    assert scanner.displayed is None
    assert scanner.refresh() is None


def testshipScanner_rescanningAClearedSystem_shouldNotReLockOnAWreck():
    """Pruned hulls are not candidates: a system the player just cleared reads "No target"."""
    wreck = hull(combat_config(), FACTION_PIRATE, 10.0, 0.0, armor=-1.0)
    scanner = ShipScanner()

    assert scanner.scan([wreck], (0.0, 0.0)) is None


# ===========================================================================
# Bounties
# ===========================================================================


def testbountyForKill_aPirateFinishedByThePlayer_shouldPayTheConfiguredBounty():
    """10,000 credits and the exact copy the spec asks for."""
    rules = combat_rules()

    bounty = bounty_for_kill(FACTION_PIRATE, rules, PlayerRelations())

    assert bounty is not None
    assert bounty.credits == 10000.0
    assert bounty.message == "10K bounty paid! Pirates destroyed."


def testbountyForKill_aLocalhosterFinishedIsPaidByTheBobbersAndViceVersa():
    """The victim's enemy pays, and the victim's own faction never does.

    Killing a Bobber earns the Localhosters' thanks; killing a Localhoster earns
    the Bobbers'. Each bounty value is the one keyed to the *victim* (see
    :meth:`CombatRules.bounty_for`), so a config can price the two sides
    separately without the payer mapping moving underneath it.
    """
    rules = CombatRules(8.0, 3, 10000, 2000, 500)

    bobber_killed = bounty_for_kill(FACTION_BOBBER, rules, PlayerRelations())
    localhoster_killed = bounty_for_kill(FACTION_LOCALHOSTER, rules, PlayerRelations())

    assert bobber_killed is not None and bobber_killed.credits == 2000.0
    assert bobber_killed.message == "Localhosters send their thanks! 2K bounty paid."
    assert localhoster_killed is not None and localhoster_killed.credits == 500.0
    assert localhoster_killed.message == "Bobbers send their thanks! 500 bounty paid."


def testbountyForKill_whenThePayingFactionAlreadyHatesThePlayer_shouldPayNothing():
    """Spec: "This ONLY applies if the paying faction is not hostile to the player."

    Shooting a Bobber makes *Bobbers* hostile, and the Localhosters still pay for a
    Bobber kill. Once both war-sides are hostile, neither pays for anything: the
    player has made enemies of both, and there is nobody left to thank them.
    """
    rules = combat_rules()

    relations = PlayerRelations()
    relations.declare_hostile_to_player(FACTION_BOBBER)
    assert bounty_for_kill(FACTION_LOCALHOSTER, rules, relations) is None, (
        "Bobbers paid for a Localhoster kill they already hate the player for"
    )
    assert bounty_for_kill(FACTION_BOBBER, rules, relations) is not None, (
        "the victim's own grudge was mistaken for the payer's"
    )

    relations.declare_hostile_to_player(FACTION_LOCALHOSTER)
    assert bounty_for_kill(FACTION_LOCALHOSTER, rules, relations) is None
    assert bounty_for_kill(FACTION_BOBBER, rules, relations) is None


def testbountyForKill_aPirateBountyDoesNotCareAboutRelations():
    """Pirate bounties come from the game, not from a rival faction.

    Pirates are hostile to everyone, so a relations check here would make the
    pirate bounty permanently unreachable.
    """
    relations = PlayerRelations(initially_hostile=FACTIONS)

    bounty = bounty_for_kill(FACTION_PIRATE, combat_rules(), relations)

    assert bounty is not None and bounty.credits == 10000.0


def testbountyForKill_zeroBounties_shouldNotAnnounceAnything():
    """A config that prices kills at nothing gets no message, not "0K bounty paid!"."""
    rules = CombatRules(8.0, 3, 0, 0, 0)

    assert bounty_for_kill(FACTION_PIRATE, rules, PlayerRelations()) is None
    assert bounty_for_kill(FACTION_BOBBER, rules, PlayerRelations()) is None


@pytest.mark.parametrize(
    "credits,expected",
    [
        (10000, "10K"),
        (5000, "5K"),
        (15000, "15K"),
        (1500, "1.5K"),
        (1000, "1K"),
        (500, "500"),
        (999, "999"),
    ],
)
def testbountyForKill_copyShouldFollowTheConfiguredAmount(credits, expected):
    """The banner quotes the number, so a config sweep moves the copy and the purse.

    The sub-1000 cases are here because a difficulty tweak that prices a kill at 500
    should read "500 bounty paid", not "0.5K bounty paid".
    """
    rules = CombatRules(8.0, 3, credits, credits, credits)

    bounty = bounty_for_kill(FACTION_PIRATE, rules, PlayerRelations())

    assert bounty is not None
    assert expected in bounty.message, bounty.message


def testbountyForKill_thePlayersOwnHullAndUnknownFactionsPayNothing():
    """Nobody is paid for anything by dying, and an unknown faction cannot be farmed."""
    rules = combat_rules()

    assert bounty_for_kill(FACTION_PLAYER, rules, PlayerRelations()) is None
    assert bounty_for_kill("smugglers", rules, PlayerRelations()) is None


# ===========================================================================
# Scene integration: the fight inside a real game
# ===========================================================================


def testscene_holdingSpace_shouldPutRoundsInFlightAtTheConfiguredRate():
    """The whole pipeline: input layer, gun clock, gunfight, one round per cycle.

    Three seconds of held space at 2/s is six rounds — the input layer asks for one
    every frame, and everything downstream has to say no sixty times a second.
    """
    scene = game_scene(combat_config(player_ship={"weapon_fire_rate": 2.0}))
    launched = count_launches(scene.gunfight)
    scene.game_state.set_position(900.0, 900.0)

    press(scene, pygame.K_SPACE)
    advance(scene, 180)
    release(scene, pygame.K_SPACE)

    assert len(launched) == 6, f"got {len(launched)} shots in 3 seconds at 2/s"
    assert all(fired.faction == FACTION_PLAYER for fired in launched)


def testscene_pressingT_shouldPublishTheScannedHullToTheHud():
    """``T`` is registered, reaches the scene, and drives the readout."""
    scene = game_scene(combat_config())
    scene.game_state.set_position(0.0, 0.0)
    nearby = hull(combat_config(), FACTION_PIRATE, 200.0, 0.0)
    park_ships_in_scene(scene, nearby)

    tap(scene, pygame.K_t)
    scene.draw(pygame.Surface((1024, 768)))

    assert scene.scanner.displayed is nearby
    assert scene.hud.nearest_ship is nearby


def testscene_aPlayerRoundThatHitsANpcMakesThatFactionPermanentlyHostile():
    """Gate item: hostility-on-hit, through the scene that owns the session's grudge.

    The Bobbers are hit; the Localhosters are not, and stay neutral. The grudge is
    the session's, so it outlives the system the shot was fired in (the same
    :class:`PlayerRelations` is handed to every encounter).
    """
    scene = game_scene(combat_config())
    scene.game_state.set_position(0.0, 0.0)
    victim = hull(combat_config(), FACTION_BOBBER, 40.0, 0.0, shields=500.0, armor=500.0)
    bystander = hull(combat_config(), FACTION_LOCALHOSTER, 900.0, 900.0)
    park_ships_in_scene(scene, victim, bystander)
    scene.gunfight.launch(
        shot(FACTION_PLAYER, scene.game_state, (0.0, 0.0), (1.0, 0.0), power=10.0)
    )

    advance(scene, 3)

    assert victim.shields < 500.0, "the player's round missed"
    assert scene.relations.is_hostile_to_player(FACTION_BOBBER) is True
    assert scene.relations.is_hostile_to_player(FACTION_LOCALHOSTER) is False
    assert scene.relations.factions_hostile_to_player == {FACTION_PIRATE, FACTION_BOBBER}


def testscene_aRoundThatOnlyCostShieldsStillStartsTheGrudge():
    """The grudge is earned on the *impact*, not on the kill.

    A shield that soaked the hit is the faction being shot at, and the spec's
    trigger is the projectile impacting, not the hull being destroyed.
    """
    scene = game_scene(combat_config())
    scene.game_state.set_position(0.0, 0.0)
    victim = hull(combat_config(), FACTION_LOCALHOSTER, 40.0, 0.0, shields=900.0, armor=900.0)
    park_ships_in_scene(scene, victim)
    scene.gunfight.launch(
        shot(FACTION_PLAYER, scene.game_state, (0.0, 0.0), (1.0, 0.0), power=10.0)
    )

    advance(scene, 3)

    assert victim.shields < 900.0
    assert victim.destroyed is False
    assert scene.relations.is_hostile_to_player(FACTION_LOCALHOSTER) is True


def testscene_killingAPiratePaysTheBountyOnceAndSaysSo():
    """Credits, copy, and a wreck that stops being in the fleet."""
    config = combat_config(combat={"pirate_bounty": 12345})
    scene = game_scene(config)
    scene.game_state.set_position(0.0, 0.0)
    pirate = hull(config, FACTION_PIRATE, 40.0, 0.0, shields=20.0, armor=20.0)
    park_ships_in_scene(scene, pirate)
    credits_before = scene.game_state.credits
    scene.gunfight.launch(
        shot(FACTION_PLAYER, scene.game_state, (0.0, 0.0), (1.0, 0.0), power=100.0)
    )

    advance(scene, 3)

    assert pirate.destroyed is True
    assert scene.game_state.credits == pytest.approx(credits_before + 12345.0)
    assert "12.3K bounty paid! Pirates destroyed." in scene.tactical.overlays.active_messages()
    assert scene.encounter.ships == (), "a wreck is still being treated as a ship"

    # A second frame with nothing in flight pays nothing: the bounty is per hull,
    # and the hull is gone rather than merely flagged.
    advance(scene, 60)
    assert scene.game_state.credits == pytest.approx(credits_before + 12345.0)


def testscene_anNpcKilledByAnotherNpcPaysThePlayerNothing():
    """Gate item: NPC-vs-NPC combat with zero player reward.

    A pirate round through a Bobber hull is a kill the player only watched. It
    still burns, and it still changes the galaxy (the factions were already at war),
    but the player's balance does not move — and no bounty copy appears, because
    the player never fired.
    """
    config = combat_config()
    scene = game_scene(config)
    scene.game_state.set_position(950.0, 950.0)  # far from the meat grinder
    pirate = hull(config, FACTION_PIRATE, 0.0, 0.0)
    bobber = hull(config, FACTION_BOBBER, 40.0, 0.0, shields=5.0, armor=5.0)
    park_ships_in_scene(scene, pirate, bobber)
    credits_before = scene.game_state.credits
    scene.gunfight.launch(
        shot(FACTION_PIRATE, pirate, (0.0, 0.0), (1.0, 0.0), power=50.0)
    )

    advance(scene, 3)

    assert bobber.destroyed is True
    assert scene.game_state.credits == credits_before
    assert scene.tactical.overlays.active_messages() == [
        message for message in scene.tactical.overlays.active_messages()
        if "bounty" not in message
    ]


def testscene_aPlayerKillOfAWarSidePaysOnlyWhenTheOtherSideIsStillFriendly():
    """The cross-faction bounty through the scene, including the "both sides hostile" wall.

    First run: shoot a Localhoster, kill a Bobber, and the Localhosters pay.
    Second run: shoot both sides and a third kill pays nothing at all.
    """
    config = combat_config()
    scene = game_scene(config)
    scene.game_state.set_position(0.0, 0.0)

    scene.relations.declare_hostile_to_player(FACTION_BOBBER)
    bobber = hull(config, FACTION_BOBBER, 40.0, 0.0, shields=5.0, armor=5.0)
    park_ships_in_scene(scene, bobber)
    before = scene.game_state.credits
    scene.gunfight.launch(
        shot(FACTION_PLAYER, scene.game_state, (0.0, 0.0), (1.0, 0.0), power=50.0)
    )
    advance(scene, 3)
    assert scene.game_state.credits == pytest.approx(before + config["combat"]["localhoster_bounty"])

    scene.relations.declare_hostile_to_player(FACTION_LOCALHOSTER)
    localhosteer = hull(config, FACTION_LOCALHOSTER, 40.0, 0.0, shields=5.0, armor=5.0)
    park_ships_in_scene(scene, localhosteer)
    after_first_kill = scene.game_state.credits
    scene.gunfight.launch(
        shot(FACTION_PLAYER, scene.game_state, (0.0, 0.0), (1.0, 0.0), power=50.0)
    )
    advance(scene, 3)

    assert localhosteer.destroyed is True
    assert scene.game_state.credits == after_first_kill, (
        "a war-side that already hates the player paid a bounty anyway"
    )


def testscene_landingMakesThePlayerUntouchableAndRoundsKeepGoing():
    """Spec: no damage while landed — and the round does not stop at the hull.

    Asserted at scene level because the immunity flag lives on the game state and
    the pass-through lives in the gunfight: if either half regresses, the player
    gets shot on the runway or the round vanishes on the way down.
    """
    scene = game_scene(combat_config())
    scene.game_state.set_position(0.0, 0.0)
    pirate = hull(combat_config(), FACTION_PIRATE, 900.0, 0.0)
    park_ships_in_scene(scene, pirate)
    scene.gunfight.launch(
        shot(FACTION_PIRATE, pirate, (20.0, 0.0), (-1.0, 0.0), power=40.0, weapon_range=1000.0)
    )

    scene.game_state.land("Alpha")
    advance(scene, 3)

    assert scene.game_state.immune_to_damage is True
    assert scene.game_state.stats.shields == scene.game_state.starting_stats.max_shields
    assert len(scene.gunfight) == 1, "a round was eaten by an immune hull"


def testscene_takingLethalDamageEndsTheRunAndStopsTheShipFlying():
    """Armour to zero: the game-over flag is raised exactly once and the controls die.

    Stage 13 owns the end screen, so this asserts the flag rather than the screen —
    and asserts that a wreck cannot keep steering, which is the difference between
    "lost with all hands" and "lost but still flying".
    """
    scene = game_scene(combat_config())
    scene.game_state.set_position(0.0, 0.0)
    pirate = hull(combat_config(), FACTION_PIRATE, 40.0, 0.0)
    park_ships_in_scene(scene, pirate)
    scene.gunfight.launch(
        shot(FACTION_PIRATE, pirate, (0.0, 0.0), (1.0, 0.0), power=10_000.0)
    )

    advance(scene, 3)

    assert scene.game_state.destroyed is True
    assert scene.pending_game_over is True
    assert scene.tactical.input.locked is True
    assert "Ship lost with all hands!" in scene.tactical.overlays.active_messages()

    # Still locked and still flagged many frames later: the flag is not re-raised
    # (Stage 13 must be able to fire its "exactly once" gate on this).
    advance(scene, 60)
    assert scene.pending_game_over is True
    assert scene.tactical.input.locked is True
    assert scene.game_state.try_fire() is None


def testscene_jumpShouldLeaveEveryRoundInTheSystemItWasFiredIn():
    """Projectiles are cleared on the same boundary the fleet is.

    The shot is fired with the player's own identity attached, so a round that
    followed through the gate would still count as a *player* round — a bounty
    waiting in a system where nobody fired a gun. It also must not hit the player
    on arrival: the round that was one pixel away is simply gone.
    """
    scene = game_scene(combat_config())
    scene.game_state.set_position(600.0, 0.0)
    pirate = hull(combat_config(), FACTION_PIRATE, 610.0, 0.0)
    park_ships_in_scene(scene, pirate)
    scene.gunfight.launch(
        shot(FACTION_PIRATE, pirate, (605.0, 0.0), (-1.0, 0.0), power=40.0, weapon_range=2000.0)
    )
    scene.system_map.select("Bravo")

    press(scene, pygame.K_j)
    scene.update()  # the jump starts
    release(scene, pygame.K_j)
    for _ in range(400):
        scene.update()
        if scene.system_map.current_system == "Bravo" and not scene.jumps.is_active:
            break

    assert scene.system_map.current_system == "Bravo"
    assert len(scene.gunfight) == 0, "a round crossed the hyperspace gate"
    assert scene.game_state.stats.shields == scene.game_state.starting_stats.max_shields


def testscene_noRoundIsFlownOrFiredWhileInHyperspace():
    """Nobody is in this universe during the burn, including the ammunition."""
    scene = game_scene(combat_config(player_ship={"weapon_fire_rate": 3.0}))
    scene.game_state.set_position(600.0, 0.0)
    park_ships_in_scene(scene, hull(combat_config(), FACTION_PIRATE, 700.0, 0.0))
    scene.system_map.select("Bravo")

    press(scene, pygame.K_j)
    scene.update()
    release(scene, pygame.K_j)
    press(scene, pygame.K_SPACE)

    for _ in range(120):
        scene.update()
        assert len(scene.gunfight) == 0, "a gun fired, or a round flew, inside hyperspace"
        assert scene.pending_shots == []

    release(scene, pygame.K_SPACE)


def testscene_aRoundCrossingThePlanetShouldPassStraightThrough():
    """Spec: "the system's planet is immune to projectiles - they pass through".

    The planet is never a target on the battlefield at all, which is the only way
    that rule stays true: a "planet" entry in the target list would need an immunity
    flag, and forgetting that flag is how planets start absorbing rounds. The round is
    fired from 200px out and flown 25 frames, so it spends several frames inside the
    planet's own 40px disc and keeps going.
    """
    config = combat_config()
    scene = game_scene(config)
    scene.game_state.set_position(200.0, 0.0)
    scene.game_state.heading = 180.0  # due west, straight through the planet
    park_ships_in_scene(scene, hull(config, FACTION_PIRATE, 900.0, 900.0))

    press(scene, pygame.K_SPACE)
    advance(scene, 25)
    release(scene, pygame.K_SPACE)

    assert len(scene.gunfight) == 1, f"the planet ate a round ({len(scene.gunfight)} left)"
    assert scene.gunfight.projectiles[0].position[0] < 0.0, "the round stopped short of the planet"
    assert scene.game_state.stats.shields == starting_stats(config).shields


def testscene_drawShouldPublishTheRoundsInFlightToTheTacticalView():
    """The view paints exactly the simulation's rounds, not a stale copy of them."""
    scene = game_scene(combat_config())
    scene.game_state.set_position(900.0, 900.0)
    park_ships_in_scene(scene)
    scene.gunfight.launch(
        shot(FACTION_PLAYER, scene.game_state, (0.0, 0.0), (1.0, 0.0), weapon_range=1000.0)
    )

    scene.draw(pygame.Surface((1024, 768)))

    assert scene.tactical.projectiles == scene.gunfight.projectiles
    assert len(scene.tactical.projectiles) == 1


def testprojectiles_shouldBePaintedInTheirShootersColourAndSurviveAFrame():
    """The player can see incoming fire, which the spec requires and the hull cannot tell them.

    The view's `projectiles` seam is what the scene fills each frame. Round
    positions are chosen so they land well away from the player's own hull (painted
    at the view centre *after* the rounds, on top of them) and away from the planet.
    Colours are counted exactly because every star is a grey and no combatant colour
    is one.
    """
    state = GameState(combat_config())
    view = TacticalView(_StackManager(), state)
    view.projectiles = [
        Projectile(FACTION_PIRATE, None, (100.0, -100.0), (0.0, 10.0), 10.0, 300.0),
        Projectile(FACTION_BOBBER, None, (170.0, -100.0), (0.0, 10.0), 10.0, 300.0),
    ]

    canvas = pygame.Surface(SCREEN_SIZE)
    view.draw(canvas)

    pirate_round = _screen_box(100.0, -100.0)
    bobber_round = _screen_box(170.0, -100.0)
    assert _count_colour_in(canvas, pirate_round, faction_color(FACTION_PIRATE)) >= 1
    assert _count_colour_in(canvas, bobber_round, faction_color(FACTION_BOBBER)) >= 1

    view.update()
    view.draw(canvas)
    assert _count_colour_in(canvas, pirate_round, faction_color(FACTION_PIRATE)) >= 1, (
        "a frame update lost the rounds in flight"
    )


def _screen_box(wx: float, wy: float, half: int = 8) -> "tuple[int, int, int, int]":
    """A counting box around where world point (wx, wy) lands with the camera at the origin."""
    x = int(round(_VIEW_CENTER[0] + wx))
    y = int(round(_VIEW_CENTER[1] + wy))
    return (x - half, y - half, x + half, y + half)


def testparticleSparks_shouldSpreadOutwardFromTheirWorldOriginThenDie():
    """A burst is a cloud of sparks, not a growing blob, and it must not leak.

    Every spark starts at the impact point, flies outward, and expires. The burst
    reports itself dead once the last one is gone, which is what lets the effects
    manager drop it instead of painting it forever. Distances here are world
    distances; the camera mapping is a separate test.
    """
    burst = ParticleBurst(
        (300.0, 300.0), count=12, speed=2.6, lifetime_frames=22, radius=1, rng=random.Random(7)
    )

    assert burst.alive
    assert all(spark.position == pytest.approx((300.0, 300.0)) for spark in burst.particles)

    for _ in range(10):
        burst.advance()

    spread = [math.dist(spark.position, (300.0, 300.0)) for spark in burst.particles]
    assert burst.alive
    assert max(spread) > 5.0, "sparks never left the impact point"
    assert all(distance > 0.0 for distance in spread), "a spark imploded through the origin"

    for _ in range(24):
        burst.advance()

    assert burst.alive is False


def testimpactEffects_anImpactShouldPaintSparksAndADestructionShouldPaintMore():
    """Spec: colourful particle effects on impacts, larger ones on destructions.

    Every canvas comes from the same view at the same camera, so the only pixels that
    differ from the plain canvas are the sparks - the honest way to count "effect
    pixels" when a star field, a planet, a ship and a jump overlay are all painted
    too. The bursts are advanced before drawing because every spark starts stacked on
    the impact point, where an impact and a destruction would be one indistinguishable
    dot.
    """
    view = TacticalView(_StackManager(), GameState(combat_config()))
    centre = (
        int(_VIEW_CENTER[0]) - 80, int(_VIEW_CENTER[1]) - 80,
        int(_VIEW_CENTER[0]) + 80, int(_VIEW_CENTER[1]) + 80,
    )

    plain = _painted_canvas(view)

    view.show_impact((0.0, 0.0), (255, 255, 255))
    _advance_sparks(view, 10)
    impacted = _painted_canvas(view)
    view.impacts.clear()

    view.show_destruction((0.0, 0.0), (255, 255, 255))
    _advance_sparks(view, 10)
    wrecked = _painted_canvas(view)

    impact_pixels = _changed_pixels(plain, impacted, centre)
    destruction_pixels = _changed_pixels(plain, wrecked, centre)

    assert impact_pixels > 0, "an impact painted nothing at all"
    assert destruction_pixels > impact_pixels, (
        f"a destruction ({destruction_pixels} px) was not larger than an impact "
        f"({impact_pixels} px)"
    )


def testimpactEffects_sparksAreAnchoredToTheWorldNotTheScreen():
    """A burst stays where the hit happened.

    If sparks were screen coordinates, moving the camera would drag them along and
    the "sparks off-screen" canvas would still show them. Both comparisons are made
    against a canvas of the same view at the same camera with the bursts cleared, so
    neither the star field nor the planet can flatter the count.
    """
    state = GameState(combat_config())
    view = TacticalView(_StackManager(), state)
    burst_at = (300.0, 300.0)
    region = _screen_box(300.0, 300.0, half=80)

    _spawn_and_advance(view, burst_at, 8)
    with_sparks = _painted_canvas(view)
    view.impacts.clear()
    assert _changed_pixels(_painted_canvas(view), with_sparks, region) > 0, (
        "sparks never appeared at their world point"
    )

    state.set_position(4000.0, 4000.0)
    _spawn_and_advance(view, burst_at, 8)
    off_view = _painted_canvas(view)
    view.impacts.clear()

    assert _changed_pixels(_painted_canvas(view), off_view, region) == 0, (
        "sparks are welded to the screen, not to the world"
    )


def _spawn_and_advance(view: "TacticalView", at: "tuple[float, float]", frames: int) -> None:
    view.show_impact(at, (255, 255, 255))
    _advance_sparks(view, frames)


def _advance_sparks(view: "TacticalView", frames: int) -> None:
    for _ in range(frames):
        view.impacts.advance()


def _painted_canvas(view: "TacticalView") -> pygame.Surface:
    canvas = pygame.Surface(SCREEN_SIZE)
    view.draw(canvas)
    return canvas


def _changed_pixels(
    before: pygame.Surface, after: pygame.Surface, region: "tuple[int, int, int, int]"
) -> int:
    """How many pixels inside ``region`` (x0, y0, x1, y1) the second canvas changed.

    Counting *changed* pixels rather than lit ones is the only honest measurement on
    a real canvas, where a star field, a planet, a ship and a jump overlay are all
    painted too. `tobytes` does the stride arithmetic a per-pixel `get_at` loop would
    pay for itself, and `subsurface` wants a width/height rather than a far corner.
    """
    x0, y0, x1, y1 = region
    window = (x0, y0, x1 - x0, y1 - y0)
    a = pygame.image.tobytes(before.subsurface(window), "RGB")
    b = pygame.image.tobytes(after.subsurface(window), "RGB")
    return sum(1 for i in range(0, len(a), 3) if a[i : i + 3] != b[i : i + 3])


# ===========================================================================
# The HUD's nearest-ship readout
# ===========================================================================


def _hud_view(config: "dict | None" = None) -> "tuple[HudView, pygame.Surface]":
    class _Manager:
        def game_config(self):
            return config or combat_config()

    view = HudView(_Manager(), GameState(config or combat_config()))
    return view, pygame.Surface((1024, 768))


def testnearestShipReadout_withNoLock_shouldPaintNoTargetAndNoBars(monkeypatch):
    """The empty state is exactly the spec's copy, and no phantom bars.

    A "shield 0/0" row for a target that does not exist would be a readout lying
    about a ship rather than admitting it has nothing to look at. The word counts are
    scoped to "exactly one of each", because the player's own Ship Status block draws
    a shield and an armour row too — the claim is that the readout does not add a
    second pair.
    """
    import src.hud as hud_module

    rendered = []
    original = hud_module.render_text

    def spy(text, size, color, bold=False):
        rendered.append((text, bold))
        return original(text, size, color, bold)

    monkeypatch.setattr(hud_module, "render_text", spy)
    view, canvas = _hud_view()
    readout = view._rects["nearest_ship"]

    view.draw(canvas)

    words = [text for text, _ in rendered]
    assert words.count(NO_TARGET_TEXT) == 1
    assert words.count("shield") == 1, "the readout painted a shield row for no target"
    assert words.count("armor") == 1, "the readout painted an armour row for no target"
    assert _count_colour_in(
        canvas, (readout.left, readout.top, readout.right, readout.bottom), _HudPalette.bar_fill
    ) == 0, "a bar was painted in an empty readout"


def testnearestShipReadout_withALockedHull_shouldPaintAlignmentAndTwoBars(monkeypatch):
    """Alignment word, then a shield row and an armor row, and no fuel row.

    Counted against the player's own block: the readout must add a second shield and
    a second armour row (that is the point) and must *not* add a third fuel row, since
    an NPC hull has no fuel and a full bar for a stat that does not exist is a lie.
    """
    import src.hud as hud_module

    rendered = []
    original = hud_module.render_text

    def spy(text, size, color, bold=False):
        rendered.append((text, bold))
        return original(text, size, color, bold)

    monkeypatch.setattr(hud_module, "render_text", spy)
    config = combat_config()
    view, canvas = _hud_view(config)
    view.nearest_ship = hull(config, FACTION_PIRATE, 100.0, 0.0, shields=25.0, armor=50.0)

    view.draw(canvas)

    words = [text for text, _ in rendered]
    assert faction_label(FACTION_PIRATE) in words
    assert words.count("shield") == 2, "the locked contact got no shield row"
    assert words.count("armor") == 2, "the locked contact got no armour row"
    assert words.count("fuel") == 1, "an NPC has no fuel, so a fuel bar would be a lie"


def testnearestShipReadout_theAlignmentWordIsPaintedInTheFactionColour():
    """Gate item: cyan / yellow / red alignment, from the same table as the hulls.

    Counted as pixels inside the readout's own rect, because "the text is red" is a
    claim about a pixel, not about an argument passed to a renderer.
    """
    config = combat_config()
    for faction in FACTIONS:
        view, canvas = _hud_view(config)
        view.nearest_ship = hull(config, faction, 100.0, 0.0)

        view.draw(canvas)

        rect = view._rects["nearest_ship"]
        painted = _count_colour_in(
            canvas, (rect.left, rect.top, rect.right, rect.bottom), faction_color(faction)
        )
        assert painted > 0, f"the {faction} alignment word was not painted in its colour"


def testnearestShipReadout_barsShouldBeDrawnWithThePlayerStatusBarGeometry():
    """Spec: the contact's bars are "displayed similarly to the bar in the player's
    own Ship Status component" — which is only a claim until one test pins that both
    blocks come from the same geometry helper and the same fill style.

    The half-full shield bar is measured in pixels rather than trusted from the call
    site: a bar that fills the wrong fraction is exactly the kind of readout that
    tells a player a pirate is one shot from dying when it is not.
    """
    config = combat_config()
    view, canvas = _hud_view(config)
    pirate = hull(config, FACTION_PIRATE, 100.0, 0.0, shields=25.0, armor=100.0)
    view.nearest_ship = pirate

    rows = nearest_ship_row_rects(view._rects["nearest_ship"])
    view.draw(canvas)

    assert rows == ship_status_row_rects(view._rects["nearest_ship"], len(NEAREST_SHIP_ROWS))
    assert all(row.height == LINE_HEIGHT for row in rows)

    _, shield_track = status_row_geometry(rows[1], ["shield", "armor"])
    _, armor_track = status_row_geometry(rows[2], ["shield", "armor"])
    filled_shields = _count_colour_in(
        canvas,
        (shield_track.left, shield_track.top, shield_track.right, shield_track.bottom),
        _HudPalette.bar_fill,
    )
    full_armor = _count_colour_in(
        canvas, (armor_track.left, armor_track.top, armor_track.right, armor_track.bottom),
        _HudPalette.bar_fill,
    )

    assert filled_shields == int(shield_track.width * 0.5) * BAR_HEIGHT
    assert full_armor == armor_track.width * BAR_HEIGHT
    assert contact_status_rows(pirate) == (("shield", 25.0, 50.0), ("armor", 100.0, 100.0))
