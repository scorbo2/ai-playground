"""Unit tests for the homing missile weapon (spec: homing_missiles.md).

Run from the project root with:

    python3 -m unittest discover -s tests -v

The tests use lightweight fakes for the world objects the missile rules touch
(to every collision check in this game an asteroid is "a thing with x, y,
radius"), plus a stub app, so no mixer or window is needed for the rules. The
two tests that do want a real surface ask pygame for one under the dummy video
driver, which the module selects before pygame loads.
"""

import math
import os
import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame  # noqa: E402  (sys.path + SDL env must be set up first)

import states.game as game_module  # noqa: E402
from entities.gravity_well import GravityWell  # noqa: E402
from entities.mine import ShrapnelMine  # noqa: E402
from entities.missile import HomingMissile, rank_targets_by_distance  # noqa: E402
from entities.powerup import Powerup  # noqa: E402
from entities.projectile import CannonProjectile  # noqa: E402
from game_constants import (  # noqa: E402
    DODGER_BLUE,
    FRIENDLY_FIRE_MESSAGE,
    LIGHT_GRAY,
    MISSILE_BODY_COLOR,
    MISSILE_LABEL_COLOR,
    MISSILE_LENGTH,
    MISSILE_RADIUS,
    MISSILE_SALVO_LATERAL_OFFSET,
    MISSILE_LEVEL_SPECS,
    MISSILE_SELF_GRACE,
    MISSILE_WIDTH,
    POWERUP_LETTERS,
    PLAYER_MAX_SPEED,
    PLAYER_ROTATION_SPEED,
    PLAYER_SHAPE_HEIGHT,
)
from sound import SFX_MISSILE_LAUNCH, SFX_THRUSTERS  # noqa: E402
from states.game import GameState  # noqa: E402
from weapons import HomingMissiles, make_weapon  # noqa: E402

SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
MISSILE_WEAPON_NAME = "Homing missiles"


# --------------------------------------------------------------------- fakes

class FakeScreen:
    def __init__(self, width=SCREEN_WIDTH, height=SCREEN_HEIGHT):
        self._size = (width, height)

    def get_size(self):
        return self._size


class FakeStarfield:
    """The app owns the starfield; the state only ever draws it."""

    def draw(self, screen):
        pass


class FakeSound:
    def __init__(self):
        self.played = []
        self.active_loops = set()

    def play(self, name):
        self.played.append(name)

    def set_active_loops(self, names):
        self.active_loops = set(names)

    def stop_loops(self):
        self.set_active_loops(frozenset())


class FakeApp:
    """Everything GameState asks of the app shell, minus pygame itself."""

    def __init__(self):
        self.screen = FakeScreen()
        self.sound = FakeSound()
        self.starfield = FakeStarfield()
        self.debug_mode = True
        self.sound_on = True
        self.game_over_message = "NOT CALLED"

    def to_game_over(self, special_message=None):
        self.game_over_message = special_message


class FakeAsteroid:
    """x/y/radius - plus a split() that reports how often it was called."""

    def __init__(self, x, y, radius=40.0):
        self.x = float(x)
        self.y = float(y)
        self.radius = float(radius)
        self.vx = 0.0
        self.vy = 0.0
        self.split_calls = 0

    def split(self):
        self.split_calls += 1
        return [FakeAsteroid(self.x, self.y, self.radius / 1.5)]

    def update(self, width, height):
        """Stationary rock: the frame-order tests only need it to survive a
        tick without drifting out from under the thing aimed at it."""


class FakeUfo:
    def __init__(self, x, y, radius=60.0):
        self.x = float(x)
        self.y = float(y)
        self.radius = float(radius)


class FakePowerup:
    def __init__(self, x, y, in_grace=False, radius=20.0):
        self.x = float(x)
        self.y = float(y)
        self.radius = float(radius)
        self.in_grace = in_grace


class FakeCraft:
    """Just enough craft for the weapon's launch geometry."""

    def __init__(self, x=400.0, y=300.0, angle=0.0, vx=0.0, vy=0.0):
        self.x = x
        self.y = y
        self.angle = angle
        self.vx = vx
        self.vy = vy


# --------------------------------------------------------------- weapon tests

class HomingMissilesWeaponTest(unittest.TestCase):

    def setUp(self):
        # A craft facing +X at the screen center, drifting at (1, 2).
        self.craft = FakeCraft(x=400.0, y=300.0, angle=0.0, vx=1.0, vy=2.0)

    def test_on_press_withReadyWeapon_shouldLaunchOneRocketFromTheTip(self):
        # GIVEN a power-1 missile weapon
        weapon = HomingMissiles(power_level=1)
        missiles = []

        # WHEN fire is pressed, THEN one unlocked rocket appears at the
        # craft's TIP on its heading, carrying the craft's velocity:
        self.assertTrue(weapon.on_press(self.craft, missiles))
        self.assertEqual(1, len(missiles))
        missile = missiles[0]
        self.assertIsNone(missile.target)
        self.assertAlmostEqual(400.0 + PLAYER_SHAPE_HEIGHT / 2, missile.x,
                               places=6)
        self.assertAlmostEqual(300.0, missile.y, places=6)
        self.assertAlmostEqual(0.0, missile.angle, places=6)
        self.assertAlmostEqual(1.0, missile.vx)
        self.assertAlmostEqual(2.0, missile.vy)

    def test_on_press_withinReloadWindow_shouldSpawnNothingAndReportBlocked(
            self):
        # GIVEN a power-1 weapon (90-frame reload) that has just fired
        weapon = HomingMissiles(power_level=1)
        missiles = []
        weapon.on_press(self.craft, missiles)

        # WHEN 89 frames pass with the bar hammered every frame, THEN every
        # press is blocked and no further rocket appears (a blocked press is
        # not an activation, so it must neither spawn nor score):
        for _ in range(89):
            weapon.update(space_held=True)
            self.assertFalse(weapon.on_press(self.craft, missiles))
        self.assertEqual(1, len(missiles))

        # WHEN the 90th frame arrives, THEN the next press fires again:
        weapon.update(space_held=True)
        self.assertTrue(weapon.on_press(self.craft, missiles))
        self.assertEqual(2, len(missiles))

    def test_on_press_atPower2_shouldReloadEvery30Frames(self):
        # GIVEN a power-2 weapon that has just fired
        weapon = HomingMissiles(power_level=2)
        missiles = []
        weapon.on_press(self.craft, missiles)
        self.assertEqual(1, weapon.missiles_per_launch)

        # WHEN 29 frames pass, THEN it is still reloading; the 30th frees it:
        for _ in range(29):
            weapon.update(space_held=False)
        self.assertTrue(weapon.reloading)
        weapon.update(space_held=False)
        self.assertFalse(weapon.reloading)
        self.assertTrue(weapon.on_press(self.craft, missiles))
        self.assertEqual(2, len(missiles))

    def test_on_press_atPower3_shouldLaunchTwoRocketsSideBySideOnAS30FrameCadence(
            self):
        # GIVEN a power-3 weapon and a craft facing +X
        weapon = HomingMissiles(power_level=3)
        missiles = []

        # WHEN one press lands, THEN TWO rockets appear, spaced one per side
        # of the ship's axis rather than stacked on the same pixel:
        self.assertTrue(weapon.on_press(self.craft, missiles))
        self.assertEqual(2, len(missiles))
        self.assertAlmostEqual(2 * MISSILE_SALVO_LATERAL_OFFSET,
                               abs(missiles[0].y - missiles[1].y), places=6)
        self.assertAlmostEqual(415.0, missiles[0].x, places=6)  # shared tip
        self.assertAlmostEqual(415.0, missiles[1].x, places=6)
        self.assertEqual(30, weapon.reload_frames)

    def test_on_press_atPower4_shouldHalveTheReloadTo15Frames(self):
        # GIVEN a power-4 weapon
        weapon = HomingMissiles(power_level=4)

        # THEN the table says 15 frames between launches, two rockets each:
        self.assertEqual(15, weapon.reload_frames)
        self.assertEqual(2, weapon.missiles_per_launch)
        self.assertEqual((2, 15), MISSILE_LEVEL_SPECS[3])
        self.assertEqual((2, 15), MISSILE_LEVEL_SPECS[4])  # L5 keeps the pace

    def test_on_press_repeatedlyWithoutWaiting_shouldSpawnOnlyOneRocket(self):
        # GIVEN a power-1 weapon and a player mashing the bar for 60 frames
        weapon = HomingMissiles(power_level=1)
        missiles = []
        successes = 0
        for _ in range(60):
            if weapon.on_press(self.craft, missiles):
                successes += 1
            weapon.update(space_held=True)

        # THEN only the first press ever counted:
        self.assertEqual(1, successes)
        self.assertEqual(1, len(missiles))

    def test_resetActive_withLevelAdvance_shouldStayUsable(self):
        # GIVEN a mid-reload weapon (its missiles are swept, the weapon lives
        # on through the level change)
        weapon = HomingMissiles(power_level=2)
        weapon.on_press(self.craft, [])

        # THEN the level sweep is a harmless no-op and the reload state is
        # still the weapon's own to report:
        weapon.reset_active()
        self.assertTrue(weapon.reloading)
        self.assertEqual(2, weapon.power())

    def test_hudIdentity_shouldBeDodgerBlue(self):
        # GIVEN the weapon class
        # THEN its HUD/powerup identity is the spec's dodger blue, and the
        # missile BODY is light gray (they must never be confused):
        self.assertEqual(DODGER_BLUE, HomingMissiles.LABEL_COLOR)
        self.assertEqual(MISSILE_LABEL_COLOR, HomingMissiles.LABEL_COLOR)
        self.assertEqual(LIGHT_GRAY, MISSILE_BODY_COLOR)
        self.assertEqual(MISSILE_WEAPON_NAME, HomingMissiles.NAME)


def _painted_span(surface):
    """(width, height, colors) of everything a draw call put on ``surface`` -
    the honest way to check a rotated polygon actually landed where the spec
    says it should (inclusive pixel counts, so a 20 px body measures 20-21)."""
    xs, ys, colors = [], [], set()
    for y in range(surface.get_height()):
        for x in range(surface.get_width()):
            rgb = surface.get_at((x, y))[:3]
            if rgb != (0, 0, 0):
                xs.append(x)
                ys.append(y)
                colors.add(rgb)
    return (max(xs) - min(xs) + 1, max(ys) - min(ys) + 1, colors)


# --------------------------------------------------------------- entity tests

class HomingMissileEntityTest(unittest.TestCase):

    def test_update_withTargetDeadAhead_shouldReachAndNeverExceedCraftMaxSpeed(
            self):
        # GIVEN a parked missile with a target straight along its heading
        missile = HomingMissile(x=100.0, y=100.0, vx=0.0, vy=0.0, angle=0.0)
        missile.lock_onto(FakeAsteroid(x=500.0, y=100.0))

        # WHEN it burns for 30 frames, THEN it hit the craft's 8 px/frame
        # ceiling (0.3 px/frame^2 reaches 9 in 30 frames, so the cap bit):
        for _ in range(30):
            missile.update(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertAlmostEqual(PLAYER_MAX_SPEED,
                               math.hypot(missile.vx, missile.vy), places=6)

        # WHEN it burns for another 300 - including the frames it spends
        # wheeling around after overshooting - THEN it never breaks the cap:
        for _ in range(300):
            missile.update(SCREEN_WIDTH, SCREEN_HEIGHT)
            self.assertLessEqual(math.hypot(missile.vx, missile.vy),
                                 PLAYER_MAX_SPEED + 1e-9)

    def test_update_withTargetBehind_shouldTurnAtMostTheCraftRotationRate(
            self):
        # GIVEN a missile facing +X with its target directly astern
        missile = HomingMissile(x=400.0, y=300.0, vx=0.0, vy=0.0, angle=0.0)
        missile.lock_onto(FakeAsteroid(x=100.0, y=300.0))
        previous_angle = missile.angle

        # WHEN 120 frames pass, THEN no single frame turned it faster than
        # the craft's 5 degrees per frame...
        for _ in range(120):
            missile.update(SCREEN_WIDTH, SCREEN_HEIGHT)
            turned = (missile.angle - previous_angle + 180.0) % 360.0 - 180.0
            self.assertLessEqual(abs(turned), PLAYER_ROTATION_SPEED + 1e-9)
            previous_angle = missile.angle

        # ...and given enough of them it completes the 180-degree turn and is
        # hunting the target. The tolerance is one frame's turn: it overshoots
        # the (uncolliding) target and starts wheeling after it, which is the
        # missile behaving correctly, not a test failure.
        bearing = math.degrees(math.atan2(300.0 - missile.y, 100.0 - missile.x))
        self.assertLess(
            abs((missile.angle - bearing + 180.0) % 360.0 - 180.0),
            PLAYER_ROTATION_SPEED + 1e-9)

    def test_update_withTargetAcrossTheWrap_shouldSteerTheShortWayRound(self):
        # GIVEN a missile 5 px off the left edge and a target 5 px off the
        # right, both facing +X (the LONG way to that rock)
        missile = HomingMissile(x=5.0, y=300.0, vx=0.0, vy=0.0, angle=0.0)
        missile.lock_onto(FakeAsteroid(x=795.0, y=300.0))

        # WHEN one frame passes, THEN it turned toward 180 degrees - through
        # the seam at 10 px, not 790 px across the open field:
        missile.update(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertAlmostEqual(355.0, missile.angle, places=6)

    def test_update_withNoTarget_shouldKeepBurningStraightAndWrap(self):
        # GIVEN a missile already at top speed, heading +X, nothing to hunt
        missile = HomingMissile(x=790.0, y=300.0, vx=PLAYER_MAX_SPEED,
                                vy=0.0, angle=0.0)

        # WHEN several frames pass, THEN it never coasts to a stop and it
        # re-enters from the left edge rather than leaving the field:
        missile.update(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertAlmostEqual(PLAYER_MAX_SPEED, missile.vx, places=6)
        for _ in range(3):
            missile.update(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertGreater(missile.x, 0.0)
        self.assertLess(missile.x, 790.0)

    def test_in_grace_shouldExpireAfterExactlyThirtyFrames(self):
        # GIVEN a just-launched missile
        missile = HomingMissile(x=100.0, y=100.0, vx=0.0, vy=0.0, angle=0.0)
        self.assertTrue(missile.in_grace)

        # WHEN 29 frames pass, THEN it is still graced; the 30th ends it:
        for _ in range(MISSILE_SELF_GRACE - 1):
            missile.update(SCREEN_WIDTH, SCREEN_HEIGHT)
            self.assertTrue(missile.in_grace)
        missile.update(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertFalse(missile.in_grace)

    def test_touching_shouldUseTheTenPixelBoundingCircleWrapAware(self):
        # GIVEN a missile at the middle of the field and one 5 px off the
        # left edge
        mid_field = HomingMissile(x=400.0, y=300.0, vx=0.0, vy=0.0, angle=0.0)
        at_the_seam = HomingMissile(x=5.0, y=300.0, vx=0.0, vy=0.0, angle=0.0)

        # THEN contact is bounding-circle to bounding-circle (MISSILE_RADIUS
        # = half the 20 px length), measured across the wrap too:
        self.assertEqual(MISSILE_LENGTH / 2, MISSILE_RADIUS)
        self.assertTrue(mid_field.touching(400.0 + MISSILE_RADIUS, 300.0, 0.0,
                                           SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertFalse(mid_field.touching(400.0 + MISSILE_RADIUS + 0.5,
                                            300.0, 0.0,
                                            SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertTrue(at_the_seam.touching(795.0, 300.0, 0.0,
                                             SCREEN_WIDTH, SCREEN_HEIGHT))

    def test_thrusting_shouldReportTheFrameItBurned(self):
        # GIVEN a missile that has not been advanced yet
        missile = HomingMissile(x=10.0, y=10.0, vx=0.0, vy=0.0, angle=0.0)

        # WHEN it advances, THEN it reports burning - with unlimited fuel it
        # always does, which is what the shared thruster loop listens for:
        self.assertFalse(missile.thrusting)
        missile.update(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertTrue(missile.thrusting)

    def test_draw_shouldPaintATwentyBySixLightGrayCylinderThatRotates(self):
        # GIVEN a blank surface and a missile facing +X, then one facing +Y
        pygame.display.init()
        sideways = pygame.Surface((80, 80))
        sideways.fill((0, 0, 0))
        HomingMissile(x=40.0, y=40.0, vx=0.0, vy=0.0,
                      angle=0.0).draw(sideways)
        upright = pygame.Surface((80, 80))
        upright.fill((0, 0, 0))
        HomingMissile(x=40.0, y=40.0, vx=0.0, vy=0.0,
                      angle=90.0).draw(upright)

        # THEN the painted silhouette is the spec's 20 x 6 (allowing a pixel
        # of rasterization on each axis), in light gray...
        x_span, y_span, colors = _painted_span(sideways)
        self.assertIn(x_span, (MISSILE_LENGTH, MISSILE_LENGTH + 1))
        self.assertIn(y_span, (MISSILE_WIDTH, MISSILE_WIDTH + 1))
        self.assertIn(LIGHT_GRAY, colors)

        # ...and it rotates with the heading rather than staying a horizontal
        # bar (the player has to be able to read which way it is going):
        rotated_x, rotated_y, _colors = _painted_span(upright)
        self.assertIn(rotated_y, (MISSILE_LENGTH, MISSILE_LENGTH + 1))
        self.assertIn(rotated_x, (MISSILE_WIDTH, MISSILE_WIDTH + 1))

    def test_construction_shouldMatchTheSpecGeometry(self):
        # GIVEN a fresh missile
        missile = HomingMissile(x=0.0, y=0.0, vx=0.0, vy=0.0, angle=0.0)

        # THEN the spec's numbers hold: 20 px long, 6 px wide, exhaust out of
        # its OWN tail (half a length aft), not the craft's base:
        self.assertAlmostEqual(MISSILE_LENGTH / 2, missile.rear_offset)
        self.assertEqual(6, MISSILE_WIDTH)
        self.assertIsNone(missile.target)


class TargetRankingTest(unittest.TestCase):

    def test_rank_targets_by_distance_shouldUseTorusNotRawDistance(self):
        # GIVEN a craft 5 px off the left edge, a rock 5 px off the right
        # (10 px away around the wrap), and one dead center
        craft = FakeCraft(x=5.0, y=300.0)
        across_the_seam = FakeAsteroid(x=795.0, y=300.0)
        mid_field = FakeAsteroid(x=400.0, y=300.0)

        # WHEN they are ranked, THEN the seam rock wins despite losing on raw
        # coordinates:
        ranked = rank_targets_by_distance(
            craft.x, craft.y, [mid_field, across_the_seam],
            SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertEqual([across_the_seam, mid_field], ranked)


# ------------------------------------------------------------ game state tests

class GameStateMissileTest(unittest.TestCase):
    """Locks, impacts, shoot-downs, friendly fire, scoring, and the shared
    thruster loop.

    ``random.random()`` is pinned high so an asteroid impact's powerup/fuel-pod
    rolls can never add drops a test is not about.
    """

    def setUp(self):
        patch = mock.patch.object(game_module.random, "random",
                                  return_value=1.0)
        patch.start()
        self.addCleanup(patch.stop)
        self.app = FakeApp()
        self.state = GameState(self.app)
        self.state._phase = GameState.PHASE_PLAYING
        self.craft_x = self.state._craft.x
        self.craft_y = self.state._craft.y
        self._clear_field()

    # ------------------------------------------------------------- helpers

    def _clear_field(self):
        for name in ("_asteroids", "_ufos", "_missiles", "_projectiles",
                     "_ufo_projectiles", "_mine_projectiles", "_mines",
                     "_wells", "_powerups", "_fuel_pods", "_particles"):
            setattr(self.state, name, [])

    def _give_weapon(self, name, power=1):
        self.state._weapon = make_weapon(name, power)
        return self.state._weapon

    def _missile_at(self, x, y, angle=0.0, vx=0.0, vy=0.0, target=None,
                    grace_frames=MISSILE_SELF_GRACE):
        missile = HomingMissile(x=x, y=y, vx=vx, vy=vy, angle=angle,
                                grace_frames=grace_frames)
        missile.lock_onto(target)
        self.state._missiles.append(missile)
        return missile

    # ------------------------------------------------------------ targeting

    def test_sync_missile_locks_withTwoRocketsAndTwoRocks_shouldLockNearestAndNextNearest(
            self):
        # GIVEN a near rock, a far rock, and two unlocked rockets (a power-3
        # salvo) with the craft between them
        self.state._craft.x, self.state._craft.y = 400.0, 300.0
        near = FakeAsteroid(x=500.0, y=300.0)
        far = FakeAsteroid(x=700.0, y=300.0)
        self.state._asteroids = [far, near]
        first = self._missile_at(400.0, 300.0)
        second = self._missile_at(406.0, 300.0)

        # WHEN locks are handed out, THEN the first rocket gets the nearest
        # rock and the second takes the NEXT nearest rather than sharing:
        self.state._sync_missile_locks(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertIs(near, first.target)
        self.assertIs(far, second.target)

    def test_sync_missile_locks_withOnlyOneRockInPlay_shouldLetBothRocketsShareIt(
            self):
        # GIVEN a single asteroid and two unlocked rockets
        only = FakeAsteroid(x=600.0, y=300.0)
        self.state._asteroids = [only]
        first = self._missile_at(400.0, 300.0)
        second = self._missile_at(406.0, 300.0)

        # WHEN locks are handed out, THEN BOTH are locked on it (spec: two
        # rockets may share the target when there is one object in play):
        self.state._sync_missile_locks(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertIs(only, first.target)
        self.assertIs(only, second.target)

    def test_sync_missile_locks_withUfoCloserThanAnyRock_shouldHuntTheUfo(
            self):
        # GIVEN a saucer nearer the craft than any asteroid
        self.state._asteroids = [FakeAsteroid(x=700.0, y=300.0)]
        ufo = FakeUfo(x=450.0, y=300.0)
        self.state._ufos = [ufo]
        missile = self._missile_at(400.0, 300.0)

        # WHEN locks are handed out, THEN the saucer is the target:
        self.state._sync_missile_locks(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertIs(ufo, missile.target)

    def test_sync_missile_locks_whenItsLockDies_shouldReLockOntoNextNearest(
            self):
        # GIVEN a rocket locked on a rock, with a second rock in play
        doomed = FakeAsteroid(x=500.0, y=300.0)
        survivor = FakeAsteroid(x=600.0, y=300.0)
        self.state._asteroids = [doomed, survivor]
        missile = self._missile_at(400.0, 300.0, target=doomed)

        # WHEN its target leaves play, THEN the next pass re-locks it onto
        # the next nearest hazard instead of leaving it flying blind:
        self.state._asteroids = [survivor]
        self.state._sync_missile_locks(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertIs(survivor, missile.target)

    def test_sync_missile_locks_withNothingToHunt_shouldKeepFlyingStraight(
            self):
        # GIVEN an unlocked rocket and an empty field
        missile = self._missile_at(400.0, 300.0, angle=0.0)

        # WHEN locks are handed out, THEN it stays unlocked rather than
        # erroring, and keeps burning along its current heading:
        self.state._sync_missile_locks(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertIsNone(missile.target)
        before_x = missile.x
        missile.update(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertGreater(missile.x, before_x)

    # -------------------------------------------------------------- impacts

    def test_resolve_missile_hits_withAsteroidImpact_shouldDestroyOutrightAndScoreOneHit(
            self):
        # GIVEN a big (normally splittable) rock and a missile on top of it
        rock = FakeAsteroid(x=400.0, y=300.0, radius=40.0)
        self.state._asteroids = [rock]
        self._missile_at(400.0, 300.0)

        # WHEN impacts resolve, THEN the rock is gone with NO split children
        # and no split() call at all, the missile is gone, and exactly one
        # "Hit" was recorded:
        self.assertTrue(self.state._resolve_missile_hits(
            SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertEqual([], self.state._asteroids)
        self.assertEqual([], self.state._missiles)
        self.assertEqual(0, rock.split_calls)
        self.assertEqual(1, self.state._score.hits)
        self.assertIn("asteroid_destroyed", self.app.sound.played)

    def test_resolve_missile_hits_withUfoImpact_shouldDestroyBothAndScoreNoHit(
            self):
        # GIVEN a saucer and a missile on top of it
        self.state._ufos = [FakeUfo(x=400.0, y=300.0)]
        self._missile_at(400.0, 300.0)

        # WHEN impacts resolve, THEN both are gone, no hit was counted (the
        # stat counts asteroids only), and the usual UFO cue played:
        self.assertTrue(self.state._resolve_missile_hits(
            SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertEqual([], self.state._ufos)
        self.assertEqual([], self.state._missiles)
        self.assertEqual(0, self.state._score.hits)
        self.assertIn("ufo_destroyed", self.app.sound.played)

    def test_resolve_missile_hits_withOutOfGracePowerup_shouldDestroyBothWithoutScore(
            self):
        # GIVEN a grace-expired powerup icon in a missile's path
        self.state._powerups = [FakePowerup(400.0, 300.0, in_grace=False)]
        self._missile_at(400.0, 300.0)

        # WHEN impacts resolve, THEN the icon and the missile are both gone
        # and nothing scored:
        self.assertTrue(self.state._resolve_missile_hits(
            SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertEqual([], self.state._powerups)
        self.assertEqual([], self.state._missiles)
        self.assertEqual(0, self.state._score.hits)

    def test_resolve_missile_hits_withInGracePowerup_shouldLeaveThemBothAlone(
            self):
        # GIVEN a freshly spawned (grace-protected) icon in the path
        self.state._powerups = [FakePowerup(400.0, 300.0, in_grace=True)]
        missile = self._missile_at(400.0, 300.0)

        # WHEN impacts resolve, THEN the icon survives and so does the
        # missile: grace is immunity, not an invitation to score:
        self.assertTrue(self.state._resolve_missile_hits(
            SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertEqual(1, len(self.state._powerups))
        self.assertEqual([missile], self.state._missiles)

    def test_resolve_missile_hits_withTwoRocketsOnTopOfEachOther_shouldKeepThemBoth(
            self):
        # GIVEN two coincident missiles and nothing else to hit
        first = self._missile_at(400.0, 300.0)
        second = self._missile_at(400.0, 300.0, angle=180.0)

        # WHEN impacts resolve, THEN neither engages the other (spec: they
        # pass through each other):
        self.assertTrue(self.state._resolve_missile_hits(
            SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertEqual([first, second], self.state._missiles)

    # -------------------------------------------------------- friendly fire

    def test_resolve_missile_hits_afterGraceOnCraftContact_shouldEndGameWithFriendlyFire(
            self):
        # GIVEN a missile past its launch grace, sitting on the craft
        self._missile_at(self.craft_x, self.craft_y, grace_frames=0)

        # WHEN impacts resolve, THEN the frame aborts on the plain "FRIENDLY
        # FIRE!" message:
        self.assertFalse(self.state._resolve_missile_hits(
            SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertEqual(FRIENDLY_FIRE_MESSAGE, self.app.game_over_message)

    def test_resolve_missile_hits_withinLaunchGrace_shouldNotTouchTheCraft(
            self):
        # GIVEN a missile inside its 30-frame grace, on top of the ship
        self._missile_at(self.craft_x, self.craft_y)

        # WHEN impacts resolve, THEN the game continues:
        self.assertTrue(self.state._resolve_missile_hits(
            SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertEqual("NOT CALLED", self.app.game_over_message)

    def test_resolve_missile_hits_atPower5_shouldPassThroughTheCraftHarmlessly(
            self):
        # GIVEN a power-5 missile weapon and its own grace-expired missile on
        # top of the ship
        self._give_weapon(MISSILE_WEAPON_NAME, power=5)
        self._missile_at(self.craft_x, self.craft_y, grace_frames=0)

        # WHEN impacts resolve, THEN the owner is immune: no game over, and
        # the rocket lives to hunt:
        self.assertTrue(self.state._resolve_missile_hits(
            SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertEqual("NOT CALLED", self.app.game_over_message)
        self.assertEqual(1, len(self.state._missiles))

    def test_resolve_missile_hits_atPower4_shouldStillKillItsOwnShip(self):
        # GIVEN the same setup one power level lower (the perk is level 5's)
        self._give_weapon(MISSILE_WEAPON_NAME, power=4)
        self._missile_at(self.craft_x, self.craft_y, grace_frames=0)

        # WHEN impacts resolve, THEN it is still friendly fire:
        self.assertFalse(self.state._resolve_missile_hits(
            SCREEN_WIDTH, SCREEN_HEIGHT))

    def test_resolve_missile_hits_withShieldRaised_shouldShootRocketDownWithNoBounce(
            self):
        # GIVEN the ramming shield raised and a grace-expired missile inside
        # the ring (but not on the ship itself)
        shield = self._give_weapon("Shield", power=1)
        shield.firing = True
        self._missile_at(self.craft_x + 30.0, self.craft_y, grace_frames=0)

        # WHEN impacts resolve, THEN the missile is destroyed, the ship took
        # no bounce, and nothing died:
        self.assertTrue(self.state._resolve_missile_hits(
            SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertEqual([], self.state._missiles)
        self.assertEqual((0.0, 0.0),
                         (self.state._craft.vx, self.state._craft.vy))
        self.assertEqual("NOT CALLED", self.app.game_over_message)

    # ---------------------------------------------------------- shoot-downs

    def test_resolve_projectile_hits_withCannonShotOnMissile_shouldDestroyBothAndScoreNothing(
            self):
        # GIVEN a cannon projectile on top of one of the player's own missiles
        self._give_weapon("Cannon", power=1)
        self.state._projectiles = [CannonProjectile(x=400.0, y=300.0,
                                                    vx=0.0, vy=0.0)]
        self._missile_at(400.0, 300.0)

        # WHEN projectile hits resolve, THEN both are gone and nothing scored
        # (the player destroying their own missile is not a "Hit"):
        self.assertTrue(self.state._resolve_projectile_hits(
            SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertEqual([], self.state._projectiles)
        self.assertEqual([], self.state._missiles)
        self.assertEqual(0, self.state._score.hits)

    def test_resolve_laser_hits_withBeamOnMissile_shouldDestroyRocketAndSpendBeam(
            self):
        # GIVEN a firing level-1 laser aimed straight down a missile
        laser = self._give_weapon("Laser", power=1)
        laser.firing = True
        self.state._craft.x, self.state._craft.y = 400.0, 300.0
        self.state._craft.angle = 0.0
        self._missile_at(430.0, 300.0)

        # WHEN the beam is resolved, THEN the rocket is gone and the beam was
        # deactivated by the hit:
        self.state._resolve_laser_hits(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertEqual([], self.state._missiles)
        self.assertFalse(laser.firing)

    def test_resolve_ufo_projectile_hits_withHostileShotOnMissile_shouldDestroyBoth(
            self):
        # GIVEN a UFO bullet on top of a missile
        self.state._ufo_projectiles = [CannonProjectile(x=400.0, y=300.0,
                                                        vx=0.0, vy=0.0)]
        self._missile_at(400.0, 300.0)

        # WHEN hostile shots resolve, THEN the missile is shot down and the
        # bullet is consumed with it:
        self.assertTrue(self.state._resolve_ufo_projectile_hits(
            SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertEqual([], self.state._missiles)
        self.assertEqual([], self.state._ufo_projectiles)

    def test_resolve_mine_interactions_withMissileContact_shouldDetonateMineAndDestroyRocket(
            self):
        # GIVEN an armed mine and a missile on top of it
        self.state._mines = [ShrapnelMine(x=400.0, y=300.0, vx=0.0, vy=0.0,
                                         power_level=1)]
        self._missile_at(400.0, 300.0)

        # WHEN mine interactions resolve, THEN the mine is gone, its 8-way
        # burst is live, and the missile went with it:
        self.assertTrue(self.state._resolve_mine_interactions(
            SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertEqual([], self.state._mines)
        self.assertEqual([], self.state._missiles)
        self.assertEqual(8, len(self.state._mine_projectiles))

    def test_resolve_mine_projectile_hits_withShrapnelOnMissile_shouldDestroyBoth(
            self):
        # GIVEN a mine burst shot on top of a missile
        self.state._mine_projectiles = [CannonProjectile(x=400.0, y=300.0,
                                                         vx=0.0, vy=0.0)]
        self._missile_at(400.0, 300.0)

        # WHEN shrapnel resolves, THEN both are gone:
        self.assertTrue(self.state._resolve_mine_projectile_hits(
            SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertEqual([], self.state._missiles)
        self.assertEqual([], self.state._mine_projectiles)

    def test_resolve_gravity_well_contacts_withRocketOnCore_shouldShootItDownAndLeaveTheWell(
            self):
        # GIVEN a live well, far from the craft, with a missile sitting on its
        # crush core
        well = GravityWell(x=700.0, y=100.0, power_level=1)
        self.state._wells = [well]
        self._missile_at(700.0, 100.0)

        # WHEN well contacts resolve, THEN the missile is gone and the well is
        # entirely unaffected (still live, still its own length):
        self.assertTrue(self.state._resolve_gravity_well_contacts(
            SCREEN_WIDTH, SCREEN_HEIGHT))
        self.assertEqual([], self.state._missiles)
        self.assertEqual([well], self.state._wells)

    def test_apply_gravity_well_pull_shouldDragMissilesTowardTheCore(self):
        # GIVEN a well 100 px off a parked missile's nose (inside its field)
        self.state._wells = [GravityWell(x=500.0, y=300.0, power_level=1)]
        missile = self._missile_at(400.0, 300.0)

        # WHEN the field acts, THEN the missile gains velocity toward the
        # core: it is explicitly NOT pull-immune:
        self.state._apply_gravity_well_pull(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertGreater(missile.vx, 0.0)

    # -------------------------------------- launching through the game state

    def test_on_weapon_press_withPower3Salvo_shouldRecordOneShotAndOneSound(
            self):
        # GIVEN a power-3 missile weapon, ready to fire
        self._give_weapon(MISSILE_WEAPON_NAME, power=3)

        # WHEN fire is pressed once, THEN two rockets are in play but exactly
        # ONE shot was recorded and ONE launch cue played:
        self.state._on_weapon_press()
        self.assertEqual(2, len(self.state._missiles))
        self.assertEqual(1, self.state._score.shots_fired)
        self.assertEqual([SFX_MISSILE_LAUNCH], self.app.sound.played)

    def test_on_weapon_press_duringReload_shouldRecordNoShotAndNoSound(self):
        # GIVEN a power-1 missile weapon that has already fired
        self._give_weapon(MISSILE_WEAPON_NAME, power=1)
        self.state._on_weapon_press()

        # WHEN the bar is hammered on the very next frame, THEN no second
        # shot and no second cue appear:
        self.state._on_weapon_press()
        self.assertEqual(1, self.state._score.shots_fired)
        self.assertEqual([SFX_MISSILE_LAUNCH], self.app.sound.played)

    def test_update_withAFieldToHunt_shouldLockAndMoveItsMissiles(self):
        # GIVEN one rock and one fresh, unlocked missile
        rock = FakeAsteroid(x=600.0, y=300.0)
        self.state._asteroids = [rock]
        missile = self._missile_at(self.craft_x, self.craft_y)
        before = (missile.x, missile.y)

        # WHEN a frame runs, THEN the missile has been given its lock and has
        # moved under its own power:
        self.state.update()
        self.assertIs(rock, missile.target)
        self.assertNotEqual(before, (missile.x, missile.y))

    # ------------------------------------------------------------------ audio

    def test_update_withOnlyMissilesBurning_shouldKeepTheThrusterLoopRunning(
            self):
        # GIVEN a field, a craft that is NOT thrusting, and one burning
        # missile
        self.state._asteroids = [FakeAsteroid(600.0, 300.0)]
        missile = self._missile_at(400.0, 100.0)
        missile.update(SCREEN_WIDTH, SCREEN_HEIGHT)

        # WHEN a frame runs with no keys held, THEN the shared thruster loop
        # is still wanted (the spec's EITHER/OR rule):
        self.state.update()
        self.assertIn(SFX_THRUSTERS, self.app.sound.active_loops)

    def test_update_withNothingBurning_shouldStopTheThrusterLoop(self):
        # GIVEN a field and no missiles, no thrust, no UFOs
        self.state._asteroids = [FakeAsteroid(600.0, 300.0)]

        # WHEN a frame runs, THEN nothing wants the thruster loop:
        self.state.update()
        self.assertNotIn(SFX_THRUSTERS, self.app.sound.active_loops)

    # -------------------------------------------------------------- lifecycle

    def test_advance_level_shouldRemoveEveryHomingMissileFromPlay(self):
        # GIVEN missiles in play and a rock left to clear the frame
        self._missile_at(400.0, 300.0)
        self.state._asteroids = [FakeAsteroid(100.0, 100.0)]

        # WHEN the level advances, THEN every missile left with the level:
        self.state._advance_level()
        self.assertEqual([], self.state._missiles)

    def test_debug_hotkey_h_shouldSpawnADodgerBlueHomingMissileIcon(self):
        # GIVEN a debug-mode game in the playing phase
        # WHEN the H hotkey lands, THEN a missile icon spawns in the spec's
        # dodger blue with the spec's "H" letter:
        self.state._handle_debug_key(pygame.K_h)
        self.assertEqual(1, len(self.state._powerups))
        self.assertEqual(MISSILE_WEAPON_NAME, self.state._powerups[0].weapon_name)
        self.assertEqual(DODGER_BLUE, self.state._powerups[0].fill)
        self.assertEqual("H", POWERUP_LETTERS[MISSILE_WEAPON_NAME])

    def test_collect_drops_withMissileIcon_shouldSwitchToMissilesAtPower1(
            self):
        # GIVEN a power-3 cannon-armed craft and a missile icon on top of it
        self._give_weapon("Cannon", power=3)
        self.state._powerups = [Powerup(self.craft_x, self.craft_y,
                                       MISSILE_WEAPON_NAME)]

        # WHEN drops are collected, THEN the ship carries a POWER-1 missile
        # weapon (a different type switches at power 1) drawn in dodger blue:
        self.state._collect_drops(SCREEN_WIDTH, SCREEN_HEIGHT)
        self.assertIsInstance(self.state._weapon, HomingMissiles)
        self.assertEqual(1, self.state._weapon.power())
        self.assertEqual(DODGER_BLUE, self.state._weapon.LABEL_COLOR)

    def test_hud_data_withMissileWeapon_shouldReportItInDodgerBlue(self):
        # GIVEN a power-2 missile weapon in play
        self._give_weapon(MISSILE_WEAPON_NAME, power=2)

        # WHEN the HUD reads the frame, THEN the weapon line carries the new
        # name and color (no charge bar - a missile weapon has none):
        data = self.state._hud_data()
        self.assertEqual(MISSILE_WEAPON_NAME, data.weapon_name)
        self.assertEqual(DODGER_BLUE, data.weapon_color)
        self.assertEqual(2, data.power_level)
        self.assertIsNone(data.charge_fraction)


if __name__ == "__main__":
    unittest.main()
