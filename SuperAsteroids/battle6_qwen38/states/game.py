"""Game Mode.

Stage 6: Cannon/Laser/ShIELD (power levels 1-3 via powerup pickups), the
30-second powerup spawn timer, level-based powerup drop rolls on asteroid
impact events, laser and shield collision handling, the --debug hotkeys,
and the enemy UFOs: the 1-minute spawn clock (max 3 active, survives level
advances), straight drift with periodic deflection, their 120-frame firing
cadence aimed at the craft, powerup stealing, and the full UFO collision
matrix.

Stage 7 (sound): every gameplay event plays its SFX from sfx/ (weapon
activations, rams, asteroid split/destruction, powerup spawn/collect/
destroy, UFO kills), and the continuous loops - the thruster loop while
thrusting, the UFO loop while at least one UFO is active - are reconciled
with the simulation once per frame.

Stage 8 (cosmetics): explosion particles on every asteroid split and
destruction and UFO kill, thruster exhaust puffs while Up is held, and
the app-owned starfield drawn behind everything (it animates in every
mode, so it needs no state wiring in this file beyond drawing it).
Level advancement sweeps the particles exactly like every other
transient object (spec: Game Mode).

Stage 9 (shrapnel mines): the fourth weapon. Space drops one mine from the
craft's rear (capped 1/3/5 by power level, holding does nothing); each mine
coasts to a stop under the craft's friction and, once its 90-frame launch
grace expires, arms when anything comes within 150 px (wrap-aware). A mine
arms for real when touched outright (bypassing the fuse) or when its
180-frame fuse runs out, and detonates into an 8-way burst of cannon shots
plus a 100-particle brown explosion. Mines and their burst shots can kill
the craft ("FRIENDLY FIRE - WATCH THOSE MINES!") unless the ramming shield
is up; the laser and shield also detonate mines on contact; mines can be
armed by any projectile. Undetonated mines and their burst shots leave play
at each level. The mine "scanning" pulse plays as a one-shot every
120 frames per unactivated mine (NOT a continuous loop); mine arm/detonate
one-shots fire on those events.

Stage 10 (fuel): the craft carries a fuel tank - FUEL_MAX on a brand-new
game, one unit per frame it ACTUALLY thrusts, and at 0 it cannot thrust at
all (no acceleration, no exhaust puffs, no thruster sound; rotation and
weapons keep working). Every asteroid split/destruction event rolls an
independent FUEL_POD_DROP_CHANCE to release a fuel pod at the event; the
pod drifts and wraps exactly like a powerup icon (shared speed/grace) and
shares the icon's ENTIRE collision matrix - projectiles, laser, and shield
destroy it out of grace, drifting into an asteroid splits/destroys the rock,
a UFO steals it even during grace - with one difference: picking one up
adds FUEL_POD_PICKUP to the tank (max FUEL_MAX) instead of upgrading a
weapon. Pods leave play at level end with everything else, and the tank
receives a level-end bonus (it CARRIES OVER; level starts never refill it).
Pod SFX reuse the powerup ones: sfx/README defines the spawn/destroy/collect
cues for "a powerup icon or fuel pod".

Stage 11 (the fifth weapon - Gravity Wells): the only weapon that never
strikes anything. One space press ANCHORS a singularity 200 px astern of the
craft's tail (capped 1/2/3/unlimited/unlimited in play by power level, holding
the bar does nothing); the well holds that spot for its whole lifetime
(240-600 frames) while every hazard inside its pull radius (120-300 px,
wrap-aware) gains velocity toward its crush core (14-24 px). Anything that
reaches the core is consumed: asteroids are destroyed outright, UFOs die,
mines detonate (a well is a chain-reaction trigger), and the craft dies
("CRUSHED BY YOUR OWN GRAVITY WELL!") unless the ramming shield is raised -
or unless the player's current weapon is a power-5 well, which no longer
reaches its own ship. Projectiles and drops (icons, pods) are deliberately NOT
pulled: bending a projectile would falsify its cumulative travel budget, and
dragging pickups around makes collection luck-based. When a well expires it
collapses: an inward particle flash, a ring of its own color bursting outward,
and everything still inside the field shoved OUTWARD (linear falloff to
nothing at the rim) - always away from the core, so the collapse can never be
what kills the player. The pull is velocity-only and never brakes anything: a
high-level rock is already faster than the field's speed ceiling, and the
field's job is to bend trajectories, not to impose a limit on the whole world.
Wells leave play at each level with every other transient object. Their two
cues (activation, collapse) are synthesized in-repo because the arcade pack
has nothing for "spacetime".

Stage 12 (the sixth weapon - Homing Missiles): one space press launches a
light gray rocket (two from power 3, and never two launches closer together
than the power level's reload) from the craft's tip. Each one locks onto the
NEAREST asteroid or UFO - ranked by wrap-aware distance from the CRAFT, so a
salvo takes the nearest and the next-nearest - and steers into it at the
CRAFT's rotation rate, acceleration, and top speed. Whatever a missile touches
dies outright: asteroids skip the split rules entirely, UFOs pop, out-of-grace
powerup icons and fuel pods are erased, mines detonate - and the missile goes
with them. Missiles have unlimited fuel and unlimited range, are pulled by
gravity wells (and die on their cores), and can be shot down by any player
weapon (cannon shot, laser beam, shield ram, mine blast) or by an enemy
bullet. A missile shot down that way scores nothing, and a salvo of two is
one "Shot"; only the rocks a missile kills count as "Hits". After a 30-frame
launch grace, a missile that catches its own ship is an immediate "FRIENDLY
FIRE!" - unless the current weapon is a power-5 missile, whose owner they pass
through harmlessly. A missile whose lock dies re-locks onto the next nearest
hazard; one with nothing left to hunt flies straight on (it never coasts, so
it can never park itself uselessly in mid-field). The thruster SFX loop is
shared from here on: it runs while the craft thrusts OR any missile burns.
Missiles leave play at each level with every other transient object, and they
never engage each other.

Level intro (start of EVERY level, including level 1): "BEGIN LEVEL N"
holds LEVEL_INTRO_HOLD frames, then fades over LEVEL_INTRO_FADE frames.
During it - and while paused - the field is drawn frozen, the craft is
hidden, no controls work, and no timers (spawn or game time) advance.

Frame order in the playing phase (matters for edge cases):
  1. movement: craft (emits thruster exhaust while it ACTUALLY thrusts -
     an empty fuel tank makes no exhaust), asteroids, player projectiles,
     UFOs (drift plus their cadence shots), UFO projectiles, powerup drift,
     fuel pod drift, mine drift, mine projectile drift, gravity well
     lifetime tick, homing missile (lock or re-lock, steer, burn, exhaust),
     then the cosmetic particle field advances and its faded members are
     pruned.

     Missiles move LAST among the movers on purpose: a rocket aims at where
     its prey IS this frame, not where it was when the frame began - and the
     thruster loop sync waits for them too, since it has to know whether
     anything with a lock burned this frame
  2. gravity wells bend the field: a velocity nudge toward the core for every
     hazard (the craft, and any missile) inside each pull radius, plus the
     ambient infall particles that make an invisible field legible
  3. spawn timers (powerup, then UFO), then weapon charge drain/recharge
  4. player weapons vs. the world (projectiles, laser beam, shield ram) -
     this is also where UFOs get destroyed by player weapons, where
     powerup icons and fuel pods are destroyed out of grace, and where
     player projectiles/laser/shield detonate mines on contact, and where a
     cannon shot or the beam SHOTS DOWN one of the player's own missiles
  5. homing missiles vs. the world (asteroid destroyed outright and scored,
     UFO destroyed, out-of-grace drop destroyed, own shield absorbs the
     hit, craft -> game over "FRIENDLY FIRE!" once its launch grace spent)
  6. mine interactions: contact detonations (UFO, craft, projectile,
     missile, asteroid), proximity activation (150px, latching), fuse
     expiry
  7. gravity well contacts: crush-core consumption (craft, asteroids, UFOs,
     mines, missiles - the bursts land in the mine projectile list
     arbitrated next), then every expired well collapses (particles +
     outward eviction kick)
  8. mine burst projectiles vs. the world (asteroid score, powerup/fuel
     pod, UFO, other mine detonation, missile shoot-down, craft friendly
     fire)
  9. UFO projectiles vs. the world (asteroids without score, powerup
     icons/fuel pods, mines, missile shoot-down, the craft -> game over
     "HOSTILE FIRE!" unless shielded)
 10. craft death check (fatal asteroid or UFO contact)
 11. drop collection: powerup icons (weapon upgrade) and fuel pods
     (+FUEL_POD_PICKUP, max FUEL_MAX) - any time, even during grace
 12. drifting powerups and fuel pods vs. asteroids (out of grace only,
     no score)
 13. UFOs vs. powerups and fuel pods (steals - work even during grace)
 14. level advancement when the field is clear (UFOs, mines, wells, their
     projectiles, fuel pods, and homing missiles leave play; the UFO spawn
     timer PERSISTS)
"""

import math
import random

import pygame

from entities import (CannonProjectile, PlayerCraft, player_hits_asteroid,
                      player_hits_ufo, rank_targets_by_distance,
                      spawn_fuel_pod, spawn_level_asteroids, spawn_ufo)
from entities.powerup import (Powerup, spawn_drop_powerup,
                              spawn_timer_powerup)
from effects.particles import (spawn_destruction_explosion,
                               spawn_gravity_well_collapse,
                               spawn_gravity_well_infall,
                               spawn_mine_detonation, spawn_split_explosion,
                               spawn_thruster_puffs, spawn_ufo_explosion)
from font_manager import render_text
from game_constants import (
    ASTEROID_MIN_RADIUS_FOR_SPLIT,
    BLACK,
    CRAFT_SPAWN_SAFE_DISTANCE,
    DEBUG_SPAWN_ATTEMPTS,
    FPS,
    FRIENDLY_FIRE_MESSAGE,
    FUEL_LEVEL_END_BONUS,
    FUEL_MAX,
    FUEL_MAX_POWER_REGEN_PER_FRAME,
    FUEL_POD_DROP_CHANCE,
    FUEL_POD_PICKUP,
    GRAVITY_WELL_FRIENDLY_FIRE_MESSAGE,
    GRAVITY_WELL_MAX_PULLED_SPEED,
    GRAVITY_WELL_SELF_IMMUNE_POWER,
    HEADING_FONT_SIZE,
    HOSTILE_FIRE_MESSAGE,
    LASER_SAMPLE_STEP,
    LEVEL_1_ASTEROID_COUNT,
    LEVEL_ASTEROID_COUNT_INCREMENT,
    LEVEL_INTRO_FADE,
    LEVEL_INTRO_HOLD,
    MINE_BURST_ANGLES,
    MINE_BURST_PROJECTILE_DISTANCE,
    MINE_FRIENDLY_FIRE_MESSAGE,
    MINE_LEVEL_SPECS,
    MISSILE_SELF_IMMUNE_POWER,
    PLAYER_MAX_SPEED,
    PLAYER_RADIUS,
    POWERUP_DROP_CHANCES,
    POWERUP_INTERVAL,
    UFO_MAX_ACTIVE,
    UFO_MIN_INTERVAL,
    UFO_MAX_INTERVAL,
    WHITE,
)
from hud import HudData, draw_game_hud
from position_utils import shortest_delta, torus_distance, wrap_around
from score import ScoreTracker
from sound import (
    SFX_ASTEROID_DESTROYED,
    SFX_ASTEROID_SPLIT,
    SFX_CANNON_BY_LEVEL,
    SFX_GRAVITY_WELL_ACTIVATED,
    SFX_GRAVITY_WELL_COLLAPSED,
    SFX_LASER_BY_LEVEL,
    SFX_MINE_ACTIVATED,
    SFX_MINE_DETONATE,
    SFX_MINE_PULSE,
    SFX_MISSILE_LAUNCH,
    SFX_POWERUP_COLLECTED,
    SFX_POWERUP_DESTROYED,
    SFX_POWERUP_SPAWN,
    SFX_SHIELD_ACTIVATED,
    SFX_SHIELD_RAM,
    SFX_THRUSTERS,
    SFX_UFO,
    SFX_UFO_DESTROYED,
)
from states.base import GameModeState
from weapons import (Cannon, ChargedWeapon, GravityWells, HomingMissiles,
                     Laser, RammingShield, ShrapnelMines, make_weapon)


def _add_velocity_and_clamp(obj, dvx: float, dvy: float,
                            max_speed: float) -> None:
    """Add one gravity field's nudge to an object's velocity, then cap the
    result.

    The cap deliberately never BRAKES anything: a high-level asteroid is
    already moving faster than the field's ceiling, and a well's job is to
    bend trajectories, not to impose a speed limit on the whole world. So the
    ceiling is "whatever the object already had, or ``max_speed``, whichever
    is larger" - which keeps the craft inside its own 8 px/frame law (spec:
    Ship physics) while letting a long-lived level-5 well actually reel in a
    rock over hundreds of frames instead of giving it one polite nudge.
    """
    speed_before = math.hypot(obj.vx, obj.vy)
    obj.vx += dvx
    obj.vy += dvy
    ceiling = max(speed_before, max_speed)
    speed_after = math.hypot(obj.vx, obj.vy)
    if speed_after > ceiling:
        scale = ceiling / speed_after
        obj.vx *= scale
        obj.vy *= scale


def _claim_nearest_free(ranked: list, claimed: set):
    """The nearest target in a ranked list that nobody has claimed yet, or
    None if the field is empty.

    When EVERY object in play is already spoken for, this still returns None
    rather than falling back to the nearest claimed one - and the caller then
    has to decide. The game state does fall back (two missiles may share the
    last rock standing, because a missile with no lock is just a firework),
    and it does that in the one place that documents the rule.
    """
    for candidate in ranked:
        if id(candidate) not in claimed:
            return candidate
    return None


class GameState(GameModeState):

    LEVEL_1 = 1
    PHASE_INTRO = "intro"        # "BEGIN LEVEL N": frozen field, no controls
    PHASE_PLAYING = "playing"    # full simulation

    def __init__(self, app):
        super().__init__(app)
        self.level = self.LEVEL_1
        # Asteroids to spawn for the CURRENT level. Level 1 is fixed at 5;
        # each advancement rolls +1 or +2 (the spec's random growth).
        self._asteroid_count = LEVEL_1_ASTEROID_COUNT
        self._score = ScoreTracker()
        # A brand-new game always starts with the default weapon at power 1
        # (spec: Powerups). Weapon and power DO carry over level advances.
        self._weapon = make_weapon("Cannon", power_level=1)
        self._projectiles: list = []
        # Enemy shots live in a SEPARATE list: their collision rules
        # (no score, no enemy friendly-fire, shield-blocked) differ from
        # the player's, and two passes keep both rule sets flat.
        self._ufo_projectiles: list = []
        self._mines: list = []
        self._mine_projectiles: list = []
        # Homing missiles (the sixth weapon) ride their own list too: they
        # are neither projectiles (no travel budget, no grace-based firing
        # rules) nor mines (no fuse), and every pass that can shoot one down
        # needs to see them all.
        self._missiles: list = []
        # Gravity wells (the fifth weapon) ride their own list, exactly like
        # mines: the press-time cap is over live WELLS, and the objects they
        # shove are everybody else's.
        self._wells: list = []
        self._powerups: list = []
        # Fuel pods (spec: Fuel): they share the powerup icons' drift,
        # grace, and collision matrix, so they ride in a parallel list and
        # the collision passes below iterate both (see ``_drops``).
        self._fuel_pods: list = []
        self._ufos: list = []
        # Cosmetic-only particles (explosion debris, thruster puffs). They
        # have no collision role, so they are a simple last-in list and get
        # swept at the same point as every other transient object
        # (spec: Game Mode - level advancement).
        self._particles: list = []
        # The 30-second powerup counter runs ONLY in the playing phase and
        # deliberately survives level advances; a fresh game starts it at
        # full value (spec: Timers / Powerups). The 3-minute UFO counter
        # has the exact same persistence rule (spec: Enemy UFOs).
        self._powerup_timer = POWERUP_INTERVAL
        self._ufo_timer = random.randint(UFO_MIN_INTERVAL, UFO_MAX_INTERVAL)
        self._game_time_frames = 0  # active game time only (spec: Timers)
        # Keys physically held right now. Space is press-based for
        # activations but the HOLD state feeds the laser/shield drain.
        # Everything here is dropped in on_pause() so a stale physical key
        # cannot resume as if it had just been pressed (safer than trusting
        # pygame's key state across focus changes; see Stage 3 notes).
        self._held_keys: set = set()
        self._space_held = False
        width, height = app.screen.get_size()
        self._phase = self.PHASE_INTRO
        self._intro_frame = 0
        self._craft = PlayerCraft(width // 2, height // 2)
        self._asteroids = self._spawn_level_field(width, height)

    # ------------------------------------------------------------ level flow

    def _spawn_level_field(self, width: int, height: int) -> list:
        # Speeds derive from self.level inside the factory (+0.3/level,
        # uncapped); the craft's spawn keeps the field 200px clear of it.
        return spawn_level_asteroids(
            self.level, self._asteroid_count, width, height,
            ship_position=(self._craft.x, self._craft.y),
        )

    def _advance_level(self) -> None:
        """All asteroids cleared -> next level (spec: Asteroids).

        Projectiles, powerup icons, UFOs, UFO projectiles, and every homing
        missile in flight all leave play (spec: Homing Missiles - "When a
        level ends, all homing missiles in play are removed from play"; and
        Enemy UFOs - "those UFOs are simply removed"), the
        craft returns to center facing up at v=0, an active laser/shield
        deactivates with its charge restored (spec), and the new level's
        field spawns under the intro sequence again. The powerup and UFO
        spawn timers and the score are NOT reset (spec: Timers / Scoring).
        """
        self.level += 1
        self._asteroid_count += random.randint(*LEVEL_ASTEROID_COUNT_INCREMENT)
        width, height = self.app.screen.get_size()
        self._craft.reset(width // 2, height // 2)
        # Level-end refuel (spec: Fuel): +FUEL_LEVEL_END_BONUS on top of
        # whatever the tank already has, clamped at FUEL_MAX. (reset() does
        # NOT refill the tank - the fuel has to carry over between levels.)
        self._craft.add_fuel(FUEL_LEVEL_END_BONUS)
        self._projectiles = []
        self._ufo_projectiles = []
        self._mines = []
        self._mine_projectiles = []
        self._missiles = []
        self._wells = []
        self._powerups = []
        self._fuel_pods = []
        self._ufos = []
        # Cosmetic debris of the level just left behind dies with it
        # (spec: "all explosion particles, powerup icons, thruster exhaust
        # circles, projectiles, and enemy UFOs are removed").
        self._particles = []
        # Re-arming a still-held space bar would require a fresh press on
        # re-activation anyway, so the hold state is cleared as well.
        self._space_held = False
        self._weapon.reset_active()
        self._asteroids = self._spawn_level_field(width, height)
        self._phase = self.PHASE_INTRO
        self._intro_frame = 0

    # --------------------------------------------------------------- events

    def handle_events(self, events: list) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.app.to_pause()
                elif event.key == pygame.K_SPACE:
                    # Controls are dead during the intro (spec: Game Mode).
                    if self._phase == self.PHASE_PLAYING:
                        self._space_held = True
                        self._on_weapon_press()
                elif event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP):
                    self._held_keys.add(event.key)
                elif (self.app.debug_mode
                      and self._phase == self.PHASE_PLAYING):
                    self._handle_debug_key(event.key)
            elif event.type == pygame.KEYUP:
                self._held_keys.discard(event.key)
                if event.key == pygame.K_SPACE:
                    self._space_held = False
            elif event.type == pygame.WINDOWFOCUSLOST:
                # Keys released without focus never produced KEYUP events.
                self._held_keys.clear()
                self._space_held = False

    def on_pause(self) -> None:
        # The craft must not wake up "thrusting" or "firing" because a key
        # happened to be held when the pause key went down.
        self._held_keys.clear()
        self._space_held = False

    def _on_weapon_press(self) -> None:
        """One space press: the cannon spawns projectiles, the charged
        weapons arm their beam/shield, the mine weapon drops a mine, the
        gravity-well weapon anchors a singularity, the missile weapon lights
        a rocket (or two).
        ONLY a successful activation records a shot (spec: "Weapon
        activation") - or plays its SFX: the firing sounds key off the
        same success, so a blocked press (projectile cap, charge below 20,
        mine cap reached, well cap reached) is silent and not counted."""
        if self._weapon.on_press(self._craft, self._press_target_list()):
            self._score.record_shot()
            self._play_weapon_activation_sound()

    def _press_target_list(self) -> list:
        """The in-play list this press's cap is measured against.

        ``Weapon.on_press`` documents that each weapon knows which list it
        was handed: the mine cap counts live MINES, the well cap counts live
        WELLS, the cannon's in-flight cap counts PROJECTILES. This is the one
        place that decides who gets what, so the weapons themselves never
        have to reach into the game state."""
        if isinstance(self._weapon, ShrapnelMines):
            return self._mines
        if isinstance(self._weapon, GravityWells):
            return self._wells
        if isinstance(self._weapon, HomingMissiles):
            # The missile weapon has no in-play cap - its press gate is its
            # own reload timer - so it is handed the live-missile list purely
            # as the place to put what it launches.
            return self._missiles
        return self._projectiles

    def _play_weapon_activation_sound(self) -> None:
        """The SFX for one successful activation (sfx/README.md): the
        cannon and laser each have a per-power-level shot; the shield, the
        gravity wells, and the homing missiles play one cue at any level."""
        if isinstance(self._weapon, Cannon):
            name = SFX_CANNON_BY_LEVEL[self._weapon.index()]
        elif isinstance(self._weapon, Laser):
            name = SFX_LASER_BY_LEVEL[self._weapon.index()]
        elif isinstance(self._weapon, RammingShield):
            name = SFX_SHIELD_ACTIVATED
        elif isinstance(self._weapon, GravityWells):
            name = SFX_GRAVITY_WELL_ACTIVATED
        elif isinstance(self._weapon, HomingMissiles):
            # One cue per LAUNCH, not per rocket: this hook runs once per
            # successful press, so a power-3+ salvo of two missiles is
            # automatically one sound and one shot (spec: Audio).
            name = SFX_MISSILE_LAUNCH
        else:
            # The mine weapon has no activation cue of its own: its sounds
            # are the pulse/arm/detonate events the mines themselves make.
            return
        self.app.sound.play(name)

    def _handle_debug_key(self, key: int) -> None:
        # --debug cheat keys (spec: "Debug option"). Only meaningful in
        # Game Mode - there is no craft (and no safe-distance anchor)
        # anywhere else.
        if key == pygame.K_c:
            self._spawn_debug_powerup("Cannon")
        elif key == pygame.K_l:
            self._spawn_debug_powerup("Laser")
        elif key == pygame.K_s:
            self._spawn_debug_powerup("Shield")
        elif key == pygame.K_m:
            self._spawn_debug_powerup("Shrapnel mines")
        elif key == pygame.K_g:
            self._spawn_debug_powerup("Gravity wells")
        elif key == pygame.K_h:
            self._spawn_debug_powerup("Homing missiles")
        elif key == pygame.K_f:
            self._spawn_debug_fuel_pod()
        elif key == pygame.K_u:
            self._spawn_debug_ufo()

    def _spawn_debug_ufo(self) -> None:
        # Spec: 'U' spawns an enemy UFO "if not already at UFO cap" -
        # the normal 200px spawn clearance applies to cheat spawns too.
        if len(self._ufos) < UFO_MAX_ACTIVE:
            width, height = self.app.screen.get_size()
            self._ufos.append(spawn_ufo(
                width, height, (self._craft.x, self._craft.y)))

    def _spawn_debug_powerup(self, weapon_name: str) -> None:
        width, height = self.app.screen.get_size()
        x, y = self._debug_spawn_point(width, height)
        self._powerups.append(Powerup(x, y, weapon_name))
        # A powerup icon has appeared - cheat or not, the same cue applies.
        self.app.sound.play(SFX_POWERUP_SPAWN)

    def _spawn_debug_fuel_pod(self) -> None:
        # Like the powerup cheats: no cap, safe-distance placement, and the
        # same spawn cue (sfx/README defines it for "a powerup icon or
        # fuel pod").
        width, height = self.app.screen.get_size()
        x, y = self._debug_spawn_point(width, height)
        self._fuel_pods.append(spawn_fuel_pod(x, y))
        self.app.sound.play(SFX_POWERUP_SPAWN)

    def _debug_spawn_point(self, width: int, height: int) -> tuple:
        """A random screen point at least CRAFT_SPAWN_SAFE_DISTANCE from the
        craft (spec: --debug), falling back to any random point if a packed
        screen leaves no open spot (debug aid only - never a gameplay path)."""
        for _ in range(DEBUG_SPAWN_ATTEMPTS):
            x, y = random.uniform(0.0, width), random.uniform(0.0, height)
            if (torus_distance(x, y, self._craft.x, self._craft.y,
                               width, height) >= CRAFT_SPAWN_SAFE_DISTANCE):
                return (x, y)
        return (random.uniform(0.0, width), random.uniform(0.0, height))

    # --------------------------------------------------------------- update

    def update(self) -> None:
        if self._phase == self.PHASE_INTRO:
            # Only the intro clock runs (spec: Timers - spawn/game timers
            # are suspended during the sequence). The ">" (not ">=") gives
            # the text exactly HOLD fully-opaque frames plus FADE fade
            # frames: the 120th draw is the fully-faded (alpha 0) frame,
            # and the phase flips on the 121st update.
            self._intro_frame += 1
            if self._intro_frame > LEVEL_INTRO_HOLD + LEVEL_INTRO_FADE:
                self._phase = self.PHASE_PLAYING
                # Controls (including any held keys/space) start fresh
                # after the intro: the craft was invisible, so nothing the
                # player may be holding can count as having been pressed.
                self._held_keys.clear()
                self._space_held = False
            # Nothing may be heard during the intro (no thrust, no UFOs,
            # no missiles - they all leave play on level advance): sync to
            # the empty set rather than letting a loop from the previous
            # level run on under the "BEGIN LEVEL N" text.
            self._sync_sound_loops(craft_thrusting=False)
            return

        self._game_time_frames += 1
        # Live window size keeps every wrap correct right after a resize
        # (the spec's "forced screen wrap" requirement).
        width, height = self.app.screen.get_size()
        thrusting, turning = self._craft_intents()
        # The craft reports whether it ACTUALLY thrust (a held key with an
        # empty tank does not count, spec: Fuel); that gates both the
        # exhaust puffs and the thruster sound loop.
        thrust_applied = self._craft.update(thrusting, turning, width, height)
        if thrust_applied:
            # Thruster exhaust (spec: Thrusters): every thrusting frame
            # ejects a random 2-3 puffs. After the craft's motion for this
            # frame, so puffs are emitted from where the ship IS - the
            # resulting one-frame offset is deliberate and unperceptible.
            # Purely cosmetic: no collision, no wrap.
            self._particles.extend(spawn_thruster_puffs(self._craft))
        elif self._weapon.power() >= 5:
            # Max-power perk: passive fuel regen when not thrusting.
            self._craft.add_fuel(FUEL_MAX_POWER_REGEN_PER_FRAME)
        for asteroid in self._asteroids:
            asteroid.update(width, height)
        for projectile in self._projectiles:
            projectile.update(width, height)
        for projectile in self._ufo_projectiles:
            projectile.update(width, height)
        for ufo in self._ufos:
            ufo.update(width, height)
            # Hostile shots land in the enemy projectile list, where the
            # UFO-projectile pass of the frame order arbitrates their hits.
            if ufo.fire_ready:
                self._ufo_projectiles.append(ufo.fire_toward(
                    self._craft.x, self._craft.y, width, height))
        for powerup in self._powerups:
            powerup.update(width, height)
        for pod in self._fuel_pods:
            pod.update(width, height)
        for mine in self._mines:
            mine.update(width, height)
        # The "scanning" pulse is a one-shot every 120 frames per mine
        # (NOT a continuous loop - spec: sfx/README). Fire on the first
        # frame of each pulse cycle for non-activated mines only.
        for mine in self._mines:
            if not mine.activated and mine.pulse_onset:
                self.app.sound.play(SFX_MINE_PULSE)
                break  # one pulse sound per frame is plenty
        for projectile in self._mine_projectiles:
            projectile.update(width, height)
        for well in self._wells:
            # Lifetime tick + vortex spin. The collapse itself waits for the
            # contact pass below, so a well that dies this frame still gets
            # to eat whatever reached its core first.
            well.update(width, height)
        # Homing missiles move LAST among the movers (stage 12): a rocket
        # aims at where its prey IS this frame rather than where it was when
        # the frame started, and the shared thruster loop below cannot be
        # decided until every missile has reported whether it burned.
        self._sync_missile_locks(width, height)
        for missile in self._missiles:
            missile.update(width, height)
            if missile.thrusting:
                # "A thruster on the back with the same visual effects ... as
                # the player's ship": the same exhaust factory, firing off
                # the missile's own tail instead of the craft's base.
                self._particles.extend(
                    spawn_thruster_puffs(missile, missile.rear_offset))
        self._sync_sound_loops(thrust_applied)
        # Cosmetic particles keep advancing until their alpha fades to 0;
        # Particle.update() reports its own fade-out, so a filter is the
        # whole cleanup. (No width/height: particles do not wrap.)
        self._particles = [p for p in self._particles if p.update()]
        # Step 2 of the frame order: the wells bend the field (velocity only
        # - the motion itself shows up on the next movement step).
        self._apply_gravity_well_pull(width, height)
        self._tick_powerup_timer(width, height)
        self._tick_ufo_timer(width, height)
        # Charge drain/recharge before collision passes so a beam that
        # depletes this frame is already down when it is (not) resolved.
        self._weapon.update(self._space_held)

        if not self._resolve_weapon_hits(width, height):
            return  # friendly fire already took us to Game Over
        if not self._resolve_missile_hits(width, height):
            return  # a missile caught its own ship; Game Over already ran
        if not self._resolve_mine_interactions(width, height):
            return  # mine friendly fire already took us to Game Over
        if not self._resolve_gravity_well_contacts(width, height):
            return  # a well crushed the craft; Game Over already triggered
        if not self._resolve_mine_projectile_hits(width, height):
            return  # mine burst friendly fire already took us to Game Over
        if not self._resolve_ufo_projectile_hits(width, height):
            return  # hostile fire already took us to Game Over
        if self._resolve_craft_deaths(width, height):
            return
        self._collect_drops(width, height)
        self._resolve_drop_asteroid_hits(width, height)
        self._resolve_ufo_drop_steals(width, height)
        if not self._asteroids:
            self._advance_level()

    def _tick_powerup_timer(self, width: int, height: int) -> None:
        """The 30-second spawn clock (frames, paused with the game)."""
        self._powerup_timer -= 1
        if self._powerup_timer <= 0:
            self._powerup_timer = POWERUP_INTERVAL
            self._powerups.append(spawn_timer_powerup(
                width, height, (self._craft.x, self._craft.y),
                self._asteroids))
            self.app.sound.play(SFX_POWERUP_SPAWN)

    def _tick_ufo_timer(self, width: int, height: int) -> None:
        """The 3-minute spawn clock (frames, paused with the game).

        Persists across level advances; only a brand-new game starts it
        fresh (spec: Enemy UFOs). An expiration at the 3-UFO cap does NOT
        carry over - the timer just restarts, as the spec requires. The
        UFO hum loop that follows a spawn is not started here: the
        per-frame loop sync in update() picks up the new UFO next frame.
        """
        self._ufo_timer -= 1
        if self._ufo_timer > 0:
            return
        self._ufo_timer = random.randint(UFO_MIN_INTERVAL, UFO_MAX_INTERVAL)
        if len(self._ufos) >= UFO_MAX_ACTIVE:
            return  # at cap: reset only, no spawn (spec)
        self._ufos.append(spawn_ufo(
            width, height, (self._craft.x, self._craft.y)))

    def _sync_sound_loops(self, craft_thrusting: bool) -> None:
        """Reconcile the continuous SFX with the simulation (spec: Sound):
        the thruster loop sounds while the craft thrusts OR while any homing
        missile is burning (one shared sample, so a salvo and a ship burning
        together still make exactly one loop), the UFO hum only while at
        least one UFO is active (it keeps going while several UFOs remain and
        stops when the last one is destroyed).

        The app clears the loop set on every pause / game-over / mode
        transition, so this per-frame call is also what re-establishes it
        after a resume. The manager only starts/stops on set CHANGES, so
        calling it every frame is cheap and cannot re-stutter a running
        loop.
        """
        wanted: set = set()
        if self._ufos:
            wanted.add(SFX_UFO)
        if craft_thrusting or self._missiles:
            wanted.add(SFX_THRUSTERS)
        self.app.sound.set_active_loops(frozenset(wanted))

    # ------------------------------------------------------------- weapon hits

    def _resolve_weapon_hits(self, width: int, height: int) -> bool:
        """Player weapons vs. the world, in the frame-order above.
        Returns False iff friendly fire took us to Game Over."""
        if not self._resolve_projectile_hits(width, height):
            return False
        self._resolve_laser_hits(width, height)
        self._resolve_shield_hits(width, height)
        return True

    def _resolve_projectile_hits(self, width: int, height: int) -> bool:
        """Projectiles vs. asteroids (impact events), powerup icons
        (out-of-grace destruction), enemy UFOs (any player weapon kills
        one), the player's OWN homing missiles (shot down, at any power
        level), and its own craft (friendly fire, grace-gated). Returns
        False if Game Over was triggered."""
        live = list(self._asteroids)
        replacements: list = []
        survivors: list = []
        for projectile in self._projectiles:
            asteroid = next(
                (a for a in live
                 if projectile.hits_circle(a.x, a.y, a.radius,
                                           width, height)),
                None,
            )
            if asteroid is not None:
                # Asteroid impact event: the projectile is consumed, the
                # rock is replaced by its split children (or none, if too
                # small to split - then it is simply destroyed). Impacts
                # by player weapons are what "Hits" count. Debris bursts
                # from the projectile's position: the actual contact point.
                live.remove(asteroid)
                replacements.extend(self._apply_asteroid_impact(
                    asteroid, score=True, destroy_outright=False,
                    impact_point=(projectile.x, projectile.y)))
                continue
            drop = next(
                (p for p in self._drops
                 if not p.in_grace
                 and projectile.hits_circle(p.x, p.y, p.radius,
                                            width, height)),
                None,
            )
            if drop is not None:
                # The projectile consumes the icon or fuel pod (spec:
                # Cannon / Fuel - pods share the icon's rules). No shot or
                # hit is recorded - an impact, not an activation.
                self._destroy_drop(drop)
                continue
            ufo = next(
                (u for u in self._ufos
                 if projectile.hits_circle(u.x, u.y, u.radius,
                                           width, height)),
                None,
            )
            if ufo is not None:
                # Any player weapon destroys a UFO (spec: Enemy UFOs). No
                # "Hit" is recorded - the stat counts asteroids only - and
                # the destruction explosion is a Stage 8 effect.
                self._destroy_ufo(ufo)
                continue
            mine = next(
                (m for m in self._mines
                 if projectile.hits_circle(m.x, m.y, m.radius,
                                           width, height)),
                None,
            )
            if mine is not None:
                # A player projectile touching a mine detonates it
                # (spec: Shrapnel Mines - contact set). The projectile is
                # consumed; the burst shots land in the mine projectile
                # list for the next resolution pass.
                self._mine_projectiles.extend(self._detonate_mine(mine))
                continue
            missile = next(
                (m for m in self._missiles
                 if projectile.hits_circle(m.x, m.y, m.radius,
                                           width, height)),
                None,
            )
            if missile is not None:
                # Homing missiles can be shot down (spec: Homing Missiles):
                # a cannon shot at ANY power level kills one and is spent on
                # it. This is the whole reason a player who wants their
                # missiles put back in the box switches weapons first.
                self._destroy_missile(missile)
                continue
            if (projectile.can_hit_player
                    and projectile.hits_circle(self._craft.x, self._craft.y,
                                               PLAYER_RADIUS, width, height)):
                self.app.to_game_over(FRIENDLY_FIRE_MESSAGE)
                return False
            if not projectile.expired:
                survivors.append(projectile)
        self._projectiles = survivors
        self._asteroids = live + replacements
        return True

    def _resolve_laser_hits(self, width: int, height: int) -> None:
        """The beam samples along its length (2px steps per spec suggestion),
        wraps each sample point, and acts on the FIRST object it touches -
        it does not pass through asteroids. Any successful impact deactivates
        the beam for this activation (spec: Laser)."""
        weapon = self._weapon
        if not isinstance(weapon, Laser) or not weapon.firing:
            return
        x, y, dir_x, dir_y = weapon.beam_geometry(self._craft)
        travelled = 0.0
        while travelled < weapon.beam_length:
            travelled += LASER_SAMPLE_STEP
            x += LASER_SAMPLE_STEP * dir_x
            y += LASER_SAMPLE_STEP * dir_y
            sx, sy = wrap_around(x, y, 0.0, width, height)
            # Asteroids before powerups at the same sample: a rock is the
            # harder target and gets the impact event.
            asteroid = next(
                (a for a in self._asteroids
                 if torus_distance(sx, sy, a.x, a.y, width, height)
                 <= a.radius),
                None,
            )
            if asteroid is not None:
                # (sx, sy) is the sample that touched the rock - the beam's
                # true contact point.
                self._asteroids.remove(asteroid)
                self._asteroids.extend(self._apply_asteroid_impact(
                    asteroid, score=True,
                    destroy_outright=weapon.destroys_on_hit(),
                    impact_point=(sx, sy)))
                weapon.deactivate_after_hit()
                return
            drop = next(
                (p for p in self._drops
                 if not p.in_grace
                 and torus_distance(sx, sy, p.x, p.y, width, height)
                 <= p.radius),
                None,
            )
            if drop is not None:
                # A fuel pod is a game object to the beam, just like an
                # icon: destroyed, and the beam is spent by the hit
                # (spec: Laser / Fuel).
                self._destroy_drop(drop)
                weapon.deactivate_after_hit()
                return
            mine = next(
                (m for m in self._mines
                 if torus_distance(sx, sy, m.x, m.y, width, height)
                 <= m.radius),
                None,
            )
            if mine is not None:
                # The laser detonates mines on contact (spec: Shrapnel
                # Mines). The beam is spent by the hit, like every other
                # target.
                self._mine_projectiles.extend(self._detonate_mine(mine))
                weapon.deactivate_after_hit()
                return
            ufo = next(
                (u for u in self._ufos
                 if torus_distance(sx, sy, u.x, u.y, width, height)
                 <= u.radius),
                None,
            )
            if ufo is not None:
                # Instantly destroyed at ANY power level (spec: Laser).
                # Like the other targets: the beam is spent by the hit,
                # and no "Hit" is recorded (asteroids only).
                self._destroy_ufo(ufo)
                weapon.deactivate_after_hit()
                return
            missile = next(
                (m for m in self._missiles
                 if torus_distance(sx, sy, m.x, m.y, width, height)
                 <= m.radius),
                None,
            )
            if missile is not None:
                # The beam shoots a missile down at ANY power level and is
                # deactivated by the hit (spec: Homing Missiles). Last in the
                # sampling order on purpose: a friendly rocket should never
                # steal an impact from a rock, a hostile, or a live mine.
                self._destroy_missile(missile)
                weapon.deactivate_after_hit()
                return

    def _resolve_shield_hits(self, width: int, height: int) -> None:
        """The ring rams asteroids and UFOs (destroy + bounce) and shreds
        out-of-grace powerup icons and fuel pods. Unlike the laser, it
        stays ACTIVE after impacts until its charge runs out (spec:
        Ramming Shield / Fuel)."""
        weapon = self._weapon
        if not isinstance(weapon, RammingShield) or not weapon.firing:
            return
        # At most one ram per frame: each bounce DISCARDS the craft's
        # current velocity, so a second simultaneous impact would only
        # throw the first bounce away. Asteroids keep first dibs, then
        # mines, then UFOs; the rest queue for next frame.
        if not self._shield_rams_asteroid(weapon, width, height):
            if not self._shield_rams_mine(weapon, width, height):
                self._shield_rams_ufo(weapon, width, height)
        # Icons/pods touching the ring outside their grace period are
        # destroyed - through _destroy_drop so they get the same
        # destruction cue as every other destroy path (spec: "by any
        # means"). In-grace drops are untouched: the craft may still
        # collect them in _collect_drops() while the shield is raised.
        self._powerups = self._survive_shield_ring(
            weapon, self._powerups, width, height)
        self._fuel_pods = self._survive_shield_ring(
            weapon, self._fuel_pods, width, height)

    def _survive_shield_ring(self, weapon: RammingShield, drops: list,
                             width: int, height: int) -> list:
        """The drops (powerup icons and/or fuel pods) the raised ring did
        NOT shred this frame. An explicit loop rather than a comprehension
        filter: _destroy_drop mutates the list backing each drop, which
        the loop must not race."""
        survivors = []
        for drop in drops:
            if (not drop.in_grace
                    and drop.overlaps_circle(
                        self._craft.x, self._craft.y, weapon.shield_radius,
                        width, height)):
                self._destroy_drop(drop)
            else:
                survivors.append(drop)
        return survivors

    def _shield_rams_asteroid(self, weapon: RammingShield,
                              width: int, height: int) -> bool:
        """First asteroid touching the ring: impact event + bounce.
        Returns True if a ram happened (so no Ufo can ram the same frame)."""
        for asteroid in self._asteroids:
            # Wrap-aware vector from the rock's center to the craft's:
            # exactly "directly away from the point of impact".
            dx = shortest_delta(self._craft.x - asteroid.x, width)
            dy = shortest_delta(self._craft.y - asteroid.y, height)
            length = math.hypot(dx, dy)
            if length <= weapon.shield_radius + asteroid.radius:
                # Where the ring actually touches the rock: the debris
                # bursts from the contact, not from the rock's center.
                if length > 1e-9:
                    impact = (self._craft.x - dx / length * weapon.shield_radius,
                              self._craft.y - dy / length * weapon.shield_radius)
                else:
                    impact = (self._craft.x, self._craft.y)  # coincident centers
                self._asteroids.remove(asteroid)
                self._asteroids.extend(self._apply_asteroid_impact(
                    asteroid, score=True,
                    destroy_outright=weapon.destroys_on_hit(),
                    impact_point=impact))
                self._craft.bounce(
                    dx, dy, asteroid.radius / weapon.bounce_divisor)
                # sfx/README.md: shield_ram is the asteroid-ram cue (a UFO
                # ram has its own ufo_destroyed cue and no ram cue).
                self.app.sound.play(SFX_SHIELD_RAM)
                return True
        return False

    def _shield_rams_ufo(self, weapon: RammingShield,
                          width: int, height: int) -> None:
        """First UFO touching the ring: destroyed instantly at ANY power
        level (spec: Ramming Shield / Enemy UFOs). The bounce formula is
        the same as for asteroids, with the UFO's 30 px bounding radius in
        place of the rock's."""
        for ufo in self._ufos:
            dx = shortest_delta(self._craft.x - ufo.x, width)
            dy = shortest_delta(self._craft.y - ufo.y, height)
            if math.hypot(dx, dy) <= weapon.shield_radius + ufo.radius:
                self._destroy_ufo(ufo)
                self._craft.bounce(
                    dx, dy, ufo.radius / weapon.bounce_divisor)
                return

    def _shield_rams_mine(self, weapon: RammingShield,
                          width: int, height: int) -> bool:
        """First mine touching the ring: detonated + bounce. Returns True
        if a ram happened (so no UFO can ram the same frame). The mine's
        own 12 px radius feeds the bounce formula. The detonation cue
        (SFX_MINE_DETONATE) plays from _detonate_mine; no separate ram cue
        is used (same pattern as the UFO ram)."""
        for mine in list(self._mines):
            dx = shortest_delta(self._craft.x - mine.x, width)
            dy = shortest_delta(self._craft.y - mine.y, height)
            if math.hypot(dx, dy) <= weapon.shield_radius + mine.radius:
                self._mine_projectiles.extend(self._detonate_mine(mine))
                self._craft.bounce(
                    dx, dy, mine.radius / weapon.bounce_divisor)
                return True
        return False

    # ---------------------------------------------------------- homing missiles

    def _sync_missile_locks(self, width: int, height: int) -> None:
        """Give every lock-less missile something to hunt.

        A missile keeps its lock until the object it is chasing leaves play;
        then - and only then - it re-locks. Locks are ranked by wrap-aware
        distance from the CRAFT: the spec defines the launch lock as "the
        nearest asteroid or UFO to the player craft", and a re-lock uses the
        same anchor so the two rules can never disagree about which rock is
        "next nearest".

        Missiles that come loose in the SAME frame claim DIFFERENT targets
        while different targets exist. That one rule is what makes a power-3
        salvo take "the nearest and the next-nearest" without the weapon ever
        seeing an asteroid list - and what lets two missiles share a target
        only when the field has nothing else to hand them (spec).
        """
        unlocked = [m for m in self._missiles
                    if not self._target_still_in_play(m.target)]
        if not unlocked:
            return
        ranked = rank_targets_by_distance(
            self._craft.x, self._craft.y,
            list(self._asteroids) + list(self._ufos), width, height)
        claimed: set = set()
        for missile in unlocked:
            target = _claim_nearest_free(ranked, claimed)
            if target is None and ranked:
                # Every object left is already somebody's target: share the
                # nearest rather than send a missile off with no lock at all
                # (spec: two rockets "may lock onto the same object if there
                # is only one asteroid or UFO in play").
                target = ranked[0]
            missile.lock_onto(target)
            if target is not None:
                claimed.add(id(target))

    def _target_still_in_play(self, target) -> bool:
        """Is a missile's lock still a live asteroid or UFO?

        Identity, not equality: a rock that was destroyed and replaced by a
        split child of the same size and color is a DIFFERENT object, and a
        missile should re-acquire rather than chase a ghost.
        """
        if target is None:
            return False
        return (any(target is asteroid for asteroid in self._asteroids)
                or any(target is ufo for ufo in self._ufos))

    def _resolve_missile_hits(self, width: int, height: int) -> bool:
        """Homing missiles vs. the world (spec: Homing Missiles). Returns
        False iff a missile caught its own craft (GameOver already triggered).

        A missile takes whatever it hits with it, and rocks skip the split
        rules entirely: a warhead does not mulch an asteroid, it deletes it
        (which also means a missile can clear a field no cannon can be
        bothered with). Arbitration order: asteroid (destroy outright, the
        one impact kind that scores a "Hit"), UFO (destroy, NO "Hit" - the
        stat counts asteroids only), out-of-grace drop (destroy, no "Hit"),
        the player's own raised shield (the missile dies, the ring does not),
        then the craft - gated by the 30-frame launch grace and, at power 5,
        by the owner's immunity.

        Mines and gravity-well cores also shoot missiles down; they are
        arbitrated in their own passes below, which is also where a missile
        that hits a mine hands over the resulting burst.
        """
        shield_up = (isinstance(self._weapon, RammingShield)
                     and self._weapon.firing)
        owner_immune = self._craft_is_immune_to_own_missiles()
        for missile in list(self._missiles):
            asteroid = next(
                (a for a in self._asteroids
                 if missile.touching(a.x, a.y, a.radius, width, height)),
                None,
            )
            if asteroid is not None:
                # Debris bursts from the missile's own position: the contact.
                self._asteroids.remove(asteroid)
                self._asteroids.extend(self._apply_asteroid_impact(
                    asteroid, score=True, destroy_outright=True,
                    impact_point=(missile.x, missile.y)))
                self._destroy_missile(missile)
                continue
            ufo = next(
                (u for u in self._ufos
                 if missile.touching(u.x, u.y, u.radius, width, height)),
                None,
            )
            if ufo is not None:
                # Same usual destruction cue as any other UFO kill; no Hit.
                self._destroy_ufo(ufo)
                self._destroy_missile(missile)
                continue
            drop = next(
                (p for p in self._drops
                 if not p.in_grace
                 and missile.touching(p.x, p.y, p.radius, width, height)),
                None,
            )
            if drop is not None:
                # Out of grace only: a fresh icon is still immortal, and the
                # missile flies on through it looking for a real target.
                self._destroy_drop(drop)
                self._destroy_missile(missile)
                continue
            if (shield_up
                    and missile.touching(self._craft.x, self._craft.y,
                                         self._weapon.shield_radius,
                                         width, height)):
                # The player's own ring shoots it down at any power level.
                # Nothing bounces: a rocket arrives, it does not ram, and the
                # shield is the one thing in this pass that is never consumed.
                self._destroy_missile(missile)
                continue
            if (not missile.in_grace
                    and not owner_immune
                    and missile.touching(self._craft.x, self._craft.y,
                                         PLAYER_RADIUS, width, height)):
                self.app.to_game_over(FRIENDLY_FIRE_MESSAGE)
                return False
        return True

    def _destroy_missile(self, missile) -> None:
        """Remove a missile from play regardless of the cause (its own
        impact, the player's cannon/laser/shield/mine blast, an enemy bullet,
        or a gravity well's core).

        Deliberately silent: sfx/README.md has no "shot-down missile" cue, and
        inventing one would put a sample in the pack that its own README
        cannot explain. It does scatter light-gray wreckage (the same
        grayscale burst a small asteroid uses, scaled to the missile's 10 px
        bounding circle) so an interception is at least visible. The
        ValueError guard matters for the usual reason: several passes can
        reach the same missile in one frame, and the debris must appear once.
        """
        try:
            self._missiles.remove(missile)
        except ValueError:
            return  # already blown up this frame
        self._particles.extend(spawn_destruction_explosion(
            missile.x, missile.y, missile.radius))

    def _craft_is_immune_to_own_missiles(self) -> bool:
        """The power-5 perk of the sixth weapon: the player's own missiles
        pass through the ship harmlessly. Keyed on the CURRENT weapon, exactly
        like the mine and gravity-well level-5 perks - switching weapons hands
        the old missiles their teeth back."""
        return (isinstance(self._weapon, HomingMissiles)
                and self._weapon.power() >= MISSILE_SELF_IMMUNE_POWER)

    # ---------------------------------------------------------------- mines

    def _detonate_mine(self, mine) -> list:
        """Detonate a mine: remove it from play, play the SFX, add the
        100-particle brown explosion. Returns the 8-way burst projectiles
        (the caller appends them to ``self._mine_projectiles``).

        The ValueError guard matters: several detonation paths (player
        projectile, laser, shield, contact, fuse) can all target the same
        mine in one frame - the SFX and explosion each fire exactly once.
        """
        try:
            self._mines.remove(mine)
        except ValueError:
            return []  # already detonated this frame
        self.app.sound.play(SFX_MINE_DETONATE)
        self._particles.extend(spawn_mine_detonation(mine.x, mine.y))
        return self._mine_burst_projectiles(mine)

    def _mine_burst_projectiles(self, mine) -> list:
        """The 8-way burst: ``CannonProjectile`` instances seeded at the
        mine's position with velocity = mine velocity plus the burst speed
        along each of the 8 compass angles. The spec is the mine's OWN
        power level (fixed at launch), not the current weapon."""
        _cap, size, speed, color = MINE_LEVEL_SPECS[mine.power_level - 1]
        projectiles = []
        for angle_deg in MINE_BURST_ANGLES:
            rad = math.radians(angle_deg)
            projectiles.append(CannonProjectile(
                x=mine.x, y=mine.y,
                vx=mine.vx + speed * math.cos(rad),
                vy=mine.vy + speed * math.sin(rad),
                size=size, color=color,
                distance_limit=MINE_BURST_PROJECTILE_DISTANCE,
                grace_frames=0,  # no grace (spec: burst shots travel instantly)
            ))
        return projectiles

    def _resolve_mine_interactions(self, width: int, height: int) -> bool:
        """Contact detonations, proximity activations, and fuse expiries
        (spec: Shrapnel Mines). Returns False iff the craft died to a
        mine's detonation (GameOver already triggered).

        Contact is checked FIRST for each mine (it bypasses the grace for
        everything except the craft). The 150 px proximity activation is
        checked LAST (it only arms the fuse, does not detonate).

        Side effects on the contacted object:
          - Asteroid: no effect (the rock continues)
          - UFO: destroyed (same cue as any other destruction)
          - Craft: game over (or bounce if the shield is raised)
          - Projectile (any type): consumed
          - Homing missile: consumed along with the mine (spec: Homing
            Missiles puts mines on the list of things that shoot one down)
        """
        shield_up = (isinstance(self._weapon, RammingShield)
                     and self._weapon.firing)
        for mine in list(self._mines):
            if mine not in self._mines:
                continue  # already detonated by an earlier pass this frame

            # -- Contact: instantaneous detonation (bypasses fuse) --
            # UFOs
            ufo = next((u for u in self._ufos
                        if mine.touching(u.x, u.y, u.radius,
                                         width, height)), None)
            if ufo is not None:
                self._destroy_ufo(ufo)
                self._mine_projectiles.extend(self._detonate_mine(mine))
                continue
            # Craft (the ONLY object immune to contact during grace)
            if not mine.in_grace and mine.touching(
                    self._craft.x, self._craft.y, PLAYER_RADIUS,
                    width, height):
                self._mine_projectiles.extend(self._detonate_mine(mine))
                if shield_up:
                    dx = shortest_delta(self._craft.x - mine.x, width)
                    dy = shortest_delta(self._craft.y - mine.y, height)
                    self._craft.bounce(
                        dx, dy, mine.radius / self._weapon.bounce_divisor)
                else:
                    self.app.to_game_over(MINE_FRIENDLY_FIRE_MESSAGE)
                    return False
                continue
            # Player projectiles
            proj = next(
                (p for p in self._projectiles
                 if p.hits_circle(mine.x, mine.y, mine.radius,
                                  width, height)),
                None,
            )
            if proj is not None:
                self._projectiles.remove(proj)
                self._mine_projectiles.extend(self._detonate_mine(mine))
                continue
            # UFO projectiles
            ufo_proj = next(
                (p for p in self._ufo_projectiles
                 if p.hits_circle(mine.x, mine.y, mine.radius,
                                  width, height)),
                None,
            )
            if ufo_proj is not None:
                self._ufo_projectiles.remove(ufo_proj)
                self._mine_projectiles.extend(self._detonate_mine(mine))
                continue
            # Mine projectiles (burst shots from other mines)
            mine_proj = next(
                (p for p in self._mine_projectiles
                 if p.hits_circle(mine.x, mine.y, mine.radius,
                                  width, height)),
                None,
            )
            if mine_proj is not None:
                self._mine_projectiles.remove(mine_proj)
                self._mine_projectiles.extend(self._detonate_mine(mine))
                continue
            # Homing missiles (contact detonates the mine AND the missile)
            missile = next(
                (m for m in self._missiles
                 if mine.touching(m.x, m.y, m.radius, width, height)),
                None,
            )
            if missile is not None:
                self._mine_projectiles.extend(self._detonate_mine(mine))
                self._destroy_missile(missile)
                continue
            # Asteroids (contact detonates the mine; the rock continues)
            asteroid = next(
                (a for a in self._asteroids
                 if mine.touching(a.x, a.y, a.radius,
                                  width, height)),
                None,
            )
            if asteroid is not None:
                self._mine_projectiles.extend(self._detonate_mine(mine))
                continue

            # -- Fuse expiry: activated mine whose countdown hit 0 --
            if mine.activated and mine.detonation_timer <= 0:
                self._mine_projectiles.extend(self._detonate_mine(mine))
                continue

            # -- Proximity activation: 150px, latching, once per mine --
            # During grace NO object can activate the mine (spec).
            if not mine.in_grace and not mine.activated:
                if self._mine_in_activation_range(mine, width, height):
                    mine.activate()
                    self.app.sound.play(SFX_MINE_ACTIVATED)
        return True

    def _mine_in_activation_range(self, mine, width: int,
                                  height: int) -> bool:
        """True if any object in the activation set is within the mine's
        invisible 150 px radius (wrap-aware). Mines and powerups are NOT in
        the activation set (spec: Shrapnel Mines); homing missiles are, since
        a missile is just a projectile with opinions."""
        if mine.within_activation_radius(self._craft.x, self._craft.y,
                                         PLAYER_RADIUS, width, height):
            return True
        for ufo in self._ufos:
            if mine.within_activation_radius(
                    ufo.x, ufo.y, ufo.radius, width, height):
                return True
        for asteroid in self._asteroids:
            if mine.within_activation_radius(
                    asteroid.x, asteroid.y, asteroid.radius, width, height):
                return True
        for proj in self._projectiles:
            if mine.within_activation_radius(
                    proj.x, proj.y, proj.half_size, width, height):
                return True
        for proj in self._ufo_projectiles:
            if mine.within_activation_radius(
                    proj.x, proj.y, proj.half_size, width, height):
                return True
        for proj in self._mine_projectiles:
            if mine.within_activation_radius(
                    proj.x, proj.y, proj.half_size, width, height):
                return True
        for missile in self._missiles:
            # A rocket hunting the field counts as "anything nearby" for the
            # proximity fuse, exactly like the projectiles it outruns.
            if mine.within_activation_radius(missile.x, missile.y,
                                             missile.radius, width, height):
                return True
        return False

    def _resolve_mine_projectile_hits(self, width: int,
                                      height: int) -> bool:
        """Mine burst projectiles vs. the world (spec: Shrapnel Mines).
        Returns False iff the craft died to a friendly-fire burst shot.

        Arbitration order: asteroid (score), powerup (destroy), UFO
        (destroy), other mine (detonate), homing missile (shot down, and the
        shrapnel is spent on it), shield (absorb), craft
        (game over). A detonated mine's new burst projectiles accumulate
        in ``new_bursts`` and are appended after the pass (they have not
        yet moved, and extending ``self._mine_projectiles`` mid-iteration
        would corrupt the ``survivors`` assignment).
        """
        shield_up = (isinstance(self._weapon, RammingShield)
                     and self._weapon.firing)
        mine_immune = (isinstance(self._weapon, ShrapnelMines)
                       and self._weapon.power() >= 5)
        live = list(self._asteroids)
        replacements: list = []
        survivors: list = []
        new_bursts: list = []
        for projectile in self._mine_projectiles:
            asteroid = next(
                (a for a in live
                 if projectile.hits_circle(a.x, a.y, a.radius,
                                           width, height)),
                None,
            )
            if asteroid is not None:
                live.remove(asteroid)
                replacements.extend(self._apply_asteroid_impact(
                    asteroid, score=True, destroy_outright=False,
                    impact_point=(projectile.x, projectile.y)))
                continue
            drop = next(
                (p for p in self._drops
                 if not p.in_grace
                 and projectile.hits_circle(p.x, p.y, p.radius,
                                            width, height)),
                None,
            )
            if drop is not None:
                # Burst shots shred icons and fuel pods exactly as player
                # projectiles do (spec: Fuel - same rules as icons).
                self._destroy_drop(drop)
                continue
            ufo = next(
                (u for u in self._ufos
                 if projectile.hits_circle(u.x, u.y, u.radius,
                                           width, height)),
                None,
            )
            if ufo is not None:
                self._destroy_ufo(ufo)
                continue
            mine = next(
                (m for m in self._mines
                 if projectile.hits_circle(m.x, m.y, m.radius,
                                           width, height)),
                None,
            )
            if mine is not None:
                new_bursts.extend(self._detonate_mine(mine))
                continue
            missile = next(
                (m for m in self._missiles
                 if projectile.hits_circle(m.x, m.y, m.radius,
                                           width, height)),
                None,
            )
            if missile is not None:
                # A mine's shrapnel shoots a missile down and the shrapnel is
                # spent on it (spec: Homing Missiles).
                self._destroy_missile(missile)
                continue
            if shield_up and projectile.hits_circle(
                    self._craft.x, self._craft.y,
                    self._weapon.shield_radius, width, height):
                continue  # absorbed by the raised shield
            if mine_immune and projectile.hits_circle(
                    self._craft.x, self._craft.y,
                    PLAYER_RADIUS, width, height):
                continue  # level-5 mines: player is immune to own burst shots
            if projectile.hits_circle(self._craft.x, self._craft.y,
                                      PLAYER_RADIUS, width, height):
                self.app.to_game_over(MINE_FRIENDLY_FIRE_MESSAGE)
                return False
            if not projectile.expired:
                survivors.append(projectile)
        self._mine_projectiles = survivors + new_bursts
        self._asteroids = live + replacements
        return True

    # ----------------------------------------------------------- gravity wells

    def _apply_gravity_well_pull(self, width: int, height: int) -> None:
        """Every live well bends the field - the fifth weapon's whole trick.

        Asteroids, mines, UFOs and the craft gain velocity toward the core
        while they are inside the field. The change is velocity-only, so the
        visible motion (and therefore the crush-core contact) lands on the
        NEXT frame: the pull reads as a curve, not a teleport.

        Exempt on purpose: projectiles (bending one would falsify the
        cumulative travel distance the spec counts) and drops (a powerup icon
        or fuel pod that gets flung around turns collection into luck).
        Homing missiles are NOT exempt - the spec singles them out ("not
        immune to gravity well pull"), and a weapon that steers by velocity
        is exactly the kind of thing a singularity should be able to ruin.

        The craft feels it too - scaled down and floored by the entity's
        ``craft_pull_toward`` so a well is a threat you fight against rather
        than a vacuum you cannot argue with - but from only ONE well at a
        time (see ``_pull_craft_toward_wells``).
        """
        for well in self._wells:
            for asteroid in self._asteroids:
                self._well_pulls(well, asteroid, asteroid.radius,
                                 GRAVITY_WELL_MAX_PULLED_SPEED, width, height)
            for mine in self._mines:
                self._well_pulls(well, mine, mine.radius,
                                 GRAVITY_WELL_MAX_PULLED_SPEED, width, height)
            for ufo in self._ufos:
                # A UFO has no velocity of its own (it drifts at the spec's
                # constant 2 px/frame), so the field pushes it instead.
                if well.within_pull_radius(ufo.x, ufo.y, ufo.radius,
                                           width, height):
                    ufo.apply_push(*well.pull_toward(ufo.x, ufo.y,
                                                     width, height))
            for missile in self._missiles:
                # "Homing missiles are not immune to gravity well pull!" -
                # and they clamp at the CRAFT's top speed rather than the
                # pulled-hazard ceiling, because a rocket's own flight law is
                # the ship's (game_constants: homing missiles).
                self._well_pulls(well, missile, missile.radius,
                                 PLAYER_MAX_SPEED, width, height)
            if well.infall_due:
                # Specks falling into the core: the field itself is invisible
                # by design, so without these the pull looks like random
                # drift and the weapon looks broken rather than strange.
                self._particles.extend(spawn_gravity_well_infall(well))
        self._pull_craft_toward_wells(width, height)

    def _pull_craft_toward_wells(self, width: int, height: int) -> None:
        """The craft only ever feels the NEAREST well's field.

        Fields genuinely stack for everything else in the world - six wells
        really do bend a rock six times harder, and that stacking is a large
        part of why the high power levels are the overpowered ones. It must
        NOT stack on the player: overlapping pulls compound past what the
        craft's 0.3 px/frame^2 of thrust can answer, which would turn the
        weapon from a tool into a punishment for pressing the button twice.
        The crush cores still all count - standing between two wells is still
        lethal, it just does not vacuum you in.
        """
        if self._craft_is_immune_to_own_wells():
            return  # the power-5 perk: a caster's own wells let them alone
        nearest = None
        nearest_distance = None
        for well in self._wells:
            if not well.within_pull_radius(self._craft.x, self._craft.y,
                                           PLAYER_RADIUS, width, height):
                continue
            distance = torus_distance(self._craft.x, self._craft.y,
                                      well.x, well.y, width, height)
            if nearest_distance is None or distance < nearest_distance:
                nearest, nearest_distance = well, distance
        if nearest is None:
            return
        dvx, dvy = nearest.craft_pull_toward(self._craft.x, self._craft.y,
                                             width, height)
        _add_velocity_and_clamp(self._craft, dvx, dvy, PLAYER_MAX_SPEED)

    def _well_pulls(self, well, target, target_radius: float,
                    max_speed: float, width: int, height: int) -> None:
        """One inward nudge on anything that carries its own velocity."""
        if not well.within_pull_radius(target.x, target.y, target_radius,
                                       width, height):
            return
        dvx, dvy = well.pull_toward(target.x, target.y, width, height)
        _add_velocity_and_clamp(target, dvx, dvy, max_speed)

    def _craft_is_immune_to_own_wells(self) -> bool:
        """The power-5 perk of the fifth weapon: a level-5 well no longer
        reaches the ship that cast it.

        Keyed on the CURRENT weapon, exactly like the mine weapon's level-5
        immunity to its own burst shots - switching weapons hands the old
        singularity its teeth back."""
        return (isinstance(self._weapon, GravityWells)
                and self._weapon.power() >= GRAVITY_WELL_SELF_IMMUNE_POWER)

    def _resolve_gravity_well_contacts(self, width: int,
                                       height: int) -> bool:
        """Crush-core arbitration, then the collapse of every expired well.
        Returns False iff the craft was crushed (GameOver already triggered).

        The craft is checked FIRST and the frame aborts on the crush, as the
        mine and mine-burst passes do: once the player is dead, eating the
        rest of the field is pointless.

        What the core consumes:
          - asteroid: destroyed OUTRIGHT (no split). A well grinds, it does
            not mulch - and splitting inside the field would just feed the
            core a dozen more rocks a frame later;
          - UFO: destroyed (same cue as any other destruction);
          - mine: detonated, so a well is a chain-reaction trigger. The burst
            shots join the list the very next pass arbitrates;
          - homing missile: shot down - the event horizon swallows it and the
            well is unaffected (spec: Homing Missiles).
        """
        shield_up = (isinstance(self._weapon, RammingShield)
                     and self._weapon.firing)
        self_immune = self._craft_is_immune_to_own_wells()
        for well in list(self._wells):
            if (not self_immune
                    and well.touching(self._craft.x, self._craft.y,
                                      PLAYER_RADIUS, width, height)):
                if shield_up:
                    # The ring holds (spec: nothing penetrates it) and the
                    # craft is thrown off the core with the usual bounce
                    # rules, the well's core radius standing in for the
                    # impacting rock's.
                    dx = shortest_delta(self._craft.x - well.x, width)
                    dy = shortest_delta(self._craft.y - well.y, height)
                    self._craft.bounce(
                        dx, dy,
                        well.core_radius / self._weapon.bounce_divisor)
                else:
                    self.app.to_game_over(GRAVITY_WELL_FRIENDLY_FIRE_MESSAGE)
                    return False
            for asteroid in list(self._asteroids):
                if well.touching(asteroid.x, asteroid.y, asteroid.radius,
                                 width, height):
                    self._asteroids.remove(asteroid)
                    self._asteroids.extend(self._apply_asteroid_impact(
                        asteroid, score=True, destroy_outright=True,
                        impact_point=(well.x, well.y)))
            for ufo in list(self._ufos):
                if well.touching(ufo.x, ufo.y, ufo.radius, width, height):
                    self._destroy_ufo(ufo)
            for mine in list(self._mines):
                if well.touching(mine.x, mine.y, mine.radius, width, height):
                    self._mine_projectiles.extend(self._detonate_mine(mine))
            for missile in list(self._missiles):
                if well.touching(missile.x, missile.y, missile.radius,
                                 width, height):
                    # The event horizon eats the rocket and is itself
                    # unaffected (spec: Homing Missiles) - the one shoot-down
                    # in the game the player cannot argue with, since they
                    # cannot shoot the well back.
                    self._destroy_missile(missile)
            if well.expired:
                self._collapse_gravity_well(well, width, height)
        return True

    def _collapse_gravity_well(self, well, width: int, height: int) -> None:
        """A well's lifetime runs out: it flashes, bursts its own color
        outward, and evicts everything still inside the field.

        The ValueError guard matters for the same reason it does for mines:
        several passes can reach the same object in one frame, and a well
        must never collapse (and never make noise) twice.
        """
        try:
            self._wells.remove(well)
        except ValueError:
            return  # already collapsed this frame
        self.app.sound.play(SFX_GRAVITY_WELL_COLLAPSED)
        self._particles.extend(spawn_gravity_well_collapse(well))
        self._evict_gravity_well(well, width, height)

    def _evict_gravity_well(self, well, width: int, height: int) -> None:
        """The collapse kick: everything still inside the field is shoved
        straight OUTWARD, linearly fading to nothing at the rim.

        Always away from the core, so the collapse can never be the thing
        that kills the player - it is the signal that the field let go, and a
        free shove clear of a well that has just finished chewing through the
        board. The craft gets it too (the shield is irrelevant here)."""
        for asteroid in self._asteroids:
            self._well_kicks(well, asteroid, asteroid.radius,
                             GRAVITY_WELL_MAX_PULLED_SPEED, width, height)
        for mine in self._mines:
            self._well_kicks(well, mine, mine.radius,
                             GRAVITY_WELL_MAX_PULLED_SPEED, width, height)
        for ufo in self._ufos:
            if well.within_pull_radius(ufo.x, ufo.y, ufo.radius,
                                       width, height):
                ufo.apply_push(*well.push_away(ufo.x, ufo.y, width, height))
        self._well_kicks(well, self._craft, PLAYER_RADIUS, PLAYER_MAX_SPEED,
                         width, height)

    def _well_kicks(self, well, target, target_radius: float,
                    max_speed: float, width: int, height: int) -> None:
        """One outward nudge on anything that carries its own velocity."""
        if not well.within_pull_radius(target.x, target.y, target_radius,
                                       width, height):
            return
        dvx, dvy = well.push_away(target.x, target.y, width, height)
        _add_velocity_and_clamp(target, dvx, dvy, max_speed)

    # ---------------------------------------------------------------- enemy fire

    def _resolve_ufo_projectile_hits(self, width: int, height: int) -> bool:
        """Hostile shots vs. the world (spec: Enemy UFOs). Returns False iff
        the craft died to a hostile shot (GameOver already triggered).

        Rules, in arbitration order: asteroids split/destroy WITHOUT
        scoring the player; powerup icons are destroyed (out of grace
        only); a homing missile in the way is shot down (spec: Homing
        Missiles - enemy fire destroys one on contact, and the bullet with
        it); the craft dies with "HOSTILE FIRE!" - unless the ramming
        shield is raised, which BLOCKS a shot (spec exception: shots
        "cannot penetrate" it; the projectile is absorbed, with no
        bounce - the bounce rules cover the shield ramming things, not
        things landing on the shield). Enemy projectiles pass through
        enemy UFOs: no friendly fire among hostiles (spec).
        """
        shield_up = (isinstance(self._weapon, RammingShield)
                     and self._weapon.firing)
        live = list(self._asteroids)
        replacements: list = []
        survivors: list = []
        for projectile in self._ufo_projectiles:
            asteroid = next(
                (a for a in live
                 if projectile.hits_circle(a.x, a.y, a.radius,
                                            width, height)),
                None,
            )
            if asteroid is not None:
                # Same impact event as player weapons, but no "Hit": the
                # stat counts asteroids destroyed by PLAYER weapons only.
                live.remove(asteroid)
                replacements.extend(self._apply_asteroid_impact(
                    asteroid, score=False, destroy_outright=False,
                    impact_point=(projectile.x, projectile.y)))
                continue
            drop = next(
                (p for p in self._drops
                 if not p.in_grace
                 and projectile.hits_circle(p.x, p.y, p.radius,
                                             width, height)),
                None,
            )
            if drop is not None:
                self._destroy_drop(drop)
                continue
            mine = next(
                (m for m in self._mines
                 if projectile.hits_circle(m.x, m.y, m.radius,
                                           width, height)),
                None,
            )
            if mine is not None:
                # A UFO projectile touching a mine detonates it
                # (spec: Shrapnel Mines - contact set).
                self._mine_projectiles.extend(self._detonate_mine(mine))
                continue
            missile = next(
                (m for m in self._missiles
                 if projectile.hits_circle(m.x, m.y, m.radius,
                                           width, height)),
                None,
            )
            if missile is not None:
                # Hostile fire shoots missiles down on contact (spec: Homing
                # Missiles) - the saucer's bullet is consumed with it, the
                # same mutual kill every other shoot-down in this file pays.
                self._destroy_missile(missile)
                continue
            if shield_up and projectile.hits_circle(
                    self._craft.x, self._craft.y, self._weapon.shield_radius,
                    width, height):
                continue  # absorbed by the raised shield (spec)
            if projectile.hits_circle(self._craft.x, self._craft.y,
                                       PLAYER_RADIUS, width, height):
                self.app.to_game_over(HOSTILE_FIRE_MESSAGE)
                return False
            if not projectile.expired:
                survivors.append(projectile)
        self._ufo_projectiles = survivors
        self._asteroids = live + replacements
        return True

    def _destroy_ufo(self, ufo) -> None:
        """Remove a UFO from play regardless of the cause. The ValueError
        guard matters: several player weapons (or the shield) can target
        the same UFO in one frame - the destruction SFX and the 100-particle
        light red explosion each fire exactly once, on the removal that
        actually happens."""
        try:
            self._ufos.remove(ufo)
            self.app.sound.play(SFX_UFO_DESTROYED)
            self._particles.extend(spawn_ufo_explosion(ufo.x, ufo.y))
        except ValueError:
            pass  # already shredded by another hit this frame

    def _resolve_ufo_drop_steals(self, width: int, height: int) -> None:
        """A UFO "steals" a powerup icon or fuel pod on contact: the drop
        is removed from play, the UFO is UNaffected (no split, no damage,
        no bounce), and - unlike every other destroyer in the game - this
        works even during the drop's grace period (spec: Enemy UFOs /
        Fuel - pods share the icons' rules)."""
        for ufo in self._ufos:
            # _drops is a fresh concatenation, so _destroy_drop mutating
            # either backing list is safe mid-iteration.
            for drop in self._drops:
                if (torus_distance(ufo.x, ufo.y, drop.x, drop.y,
                                   width, height)
                        <= ufo.radius + drop.radius):
                    self._destroy_drop(drop)

    # ------------------------------------------------------- asteroid impacts

    def _apply_asteroid_impact(self, asteroid, score: bool,
                               destroy_outright: bool,
                               impact_point: tuple) -> list:
        """Resolve one asteroid being hit. Returns its replacement children.

        ``score`` records a player "Hit" - player weapons only (spec:
        Scoring; powerup impacts and UFO-projectile impacts pass False).
        ``destroy_outright`` (laser/shield power 3) skips the split rules
        entirely. ``impact_point`` is the contact point the debris bursts
        from - the spec wants particles to "spread out from the point where
        the collision occurred", not from the rock's center. (The powerup
        drop, if the roll succeeds, still spawns at the rock's own
        position: the rock "has" it, whatever touched it.) EVERY split and
        destruction event rolls the level-based powerup drop chance
        (spec: Powerups) AND the flat fuel pod drop chance (spec: Fuel) -
        and plays the spawn cue, whoever (or whatever) delivered the hit,
        since the sfx README defines those sounds by the EVENT (a spawn /
        a split / a destruction), not the cause.
        """
        if score:
            self._score.record_hit()
        if destroy_outright or asteroid.radius < ASTEROID_MIN_RADIUS_FOR_SPLIT:
            children: list = []
            self.app.sound.play(SFX_ASTEROID_DESTROYED)
            # Monochrome wreckage: radius * 3 gray particles, 128-255.
            self._particles.extend(spawn_destruction_explosion(
                impact_point[0], impact_point[1], asteroid.radius))
        else:
            children = asteroid.split()
            self.app.sound.play(SFX_ASTEROID_SPLIT)
            # Colorful debris: one random yellow/red/orange per particle.
            self._particles.extend(spawn_split_explosion(
                impact_point[0], impact_point[1], asteroid.radius))
        if random.random() < self._powerup_drop_chance():
            self._powerups.append(spawn_drop_powerup(asteroid.x, asteroid.y))
            self.app.sound.play(SFX_POWERUP_SPAWN)
        if random.random() < FUEL_POD_DROP_CHANCE:
            # Independent of the powerup roll: a single event CAN release
            # both (spec: Fuel - its own 2% on every event). The spawn cue
            # covers pods too (sfx/README: "powerup icon or fuel pod").
            self._fuel_pods.append(spawn_fuel_pod(asteroid.x, asteroid.y))
            self.app.sound.play(SFX_POWERUP_SPAWN)
        return children

    def _powerup_drop_chance(self) -> float:
        # 8/6/4/2% on levels 1-4, then 1% forever (spec: Powerups).
        return POWERUP_DROP_CHANCES[
            min(self.level, len(POWERUP_DROP_CHANCES)) - 1]

    # ------------------------------------------------------------- craft fate

    def _resolve_craft_deaths(self, width: int, height: int) -> bool:
        """Returns True if the craft died this frame (state already swapped).

        While the shield is up, its radius (35-40px) fully covers the
        craft's 20px bounding circle, so any asteroid OR UFO touching the
        craft was ALREADY resolved as a ram-bounce earlier this frame -
        the fatal-contact checks are skipped for that frame (and hostile
        bullets were stopped at the shield in step 4).
        """
        if isinstance(self._weapon, RammingShield) and self._weapon.firing:
            return False
        if any(player_hits_asteroid(self._craft, a, width, height)
               for a in self._asteroids):
            self.app.to_game_over()
            return True
        # Spec: "Player craft collides with enemy UFO: instant game over."
        # No special message is defined for this one (only the FRIENDLY /
        # HOSTILE FIRE strings exist).
        if any(player_hits_ufo(self._craft, u, width, height)
               for u in self._ufos):
            self.app.to_game_over()
            return True
        return False

    # -------------------------------------------------------------- powerups

    def _collect_drops(self, width: int, height: int) -> None:
        """The craft may collect powerup icons AND fuel pods ANY time -
        even during their grace period (spec: Powerups / Fuel). Icons
        upgrade the weapon (same type: power +1, max 3; different type:
        switch at power 1). Pods add FUEL_POD_PICKUP to the tank (capped
        at FUEL_MAX). Neither kind has a cap, so several can be collected
        in one frame (the last one's effect wins, like any rapid pickup;
        the cue plays per pickup - pygame simply re-fires the channel)."""
        powerup_survivors = []
        for powerup in self._powerups:
            if powerup.overlaps_circle(self._craft.x, self._craft.y,
                                       PLAYER_RADIUS, width, height):
                if powerup.weapon_name == self._weapon.NAME:
                    # Same type: keep the SAME instance so its charge
                    # state survives the power-up.
                    self._weapon.boost()
                else:
                    self._weapon = make_weapon(powerup.weapon_name,
                                                power_level=1)
                self.app.sound.play(SFX_POWERUP_COLLECTED)
            else:
                powerup_survivors.append(powerup)
        self._powerups = powerup_survivors
        pod_survivors = []
        for pod in self._fuel_pods:
            if pod.overlaps_circle(self._craft.x, self._craft.y,
                                   PLAYER_RADIUS, width, height):
                # sfx/README: the pickup cue covers fuel pods too.
                self._craft.add_fuel(FUEL_POD_PICKUP)
                self.app.sound.play(SFX_POWERUP_COLLECTED)
            else:
                pod_survivors.append(pod)
        self._fuel_pods = pod_survivors

    def _resolve_drop_asteroid_hits(self, width: int, height: int) -> None:
        """A drifting out-of-grace icon or fuel pod touching an asteroid is
        destroyed, and the asteroid splits/destroys per the normal impact
        rules - without scoring the player (spec: Powerups / Fuel /
        Scoring). Each drop and rock is consumed at most once per frame."""
        consumed_drops: set = set()
        # Rock id -> the drop position that hit it (the debris origin).
        impacted_rocks: dict = {}
        for drop in self._drops:
            if drop.in_grace:
                continue
            for asteroid in self._asteroids:
                if id(asteroid) in impacted_rocks:
                    continue
                if drop.overlaps_circle(asteroid.x, asteroid.y,
                                        asteroid.radius, width, height):
                    consumed_drops.add(id(drop))
                    impacted_rocks[id(asteroid)] = (drop.x, drop.y)
                    break  # one rock per drop per frame
        # A second FRESH snapshot: _destroy_drop mutates the backing
        # lists, and the first concatenation is stale by now.
        for drop in self._drops:
            if id(drop) in consumed_drops:
                self._destroy_drop(drop)
        # Iterate a SNAPSHOT: the loop body rebuilds self._asteroids, and
        # removing elements from a list mid-iteration would skip the rock
        # sitting right after each removed one.
        for asteroid in list(self._asteroids):
            if id(asteroid) in impacted_rocks:
                self._asteroids.remove(asteroid)
                self._asteroids.extend(self._apply_asteroid_impact(
                    asteroid, score=False, destroy_outright=False,
                    impact_point=impacted_rocks[id(asteroid)]))

    def _destroy_drop(self, drop) -> None:
        """Remove a powerup icon or fuel pod from play regardless of the
        cause (projectile, beam, shield, drifting rock, stolen by a UFO).
        The destruction cue (sfx/README: covers both kinds) plays once, on
        the removal that actually happens."""
        try:
            self._powerups.remove(drop)
            self.app.sound.play(SFX_POWERUP_DESTROYED)
        except ValueError:
            pass  # not an icon - check the pod list below
        try:
            self._fuel_pods.remove(drop)
            self.app.sound.play(SFX_POWERUP_DESTROYED)
        except ValueError:
            pass  # already consumed by another collision this frame

    @property
    def _drops(self) -> list:
        """Every drifting drop (powerup icons + fuel pods) as ONE fresh
        concatenation. The two kinds share drift, grace, and the whole
        collision matrix (spec: Fuel), so the collision passes iterate this
        view. It documents, rather than owns, the data: mutations always
        go through the backing lists (_destroy_drop/_collect_drops/
        _advance_level), never through this list."""
        return self._powerups + self._fuel_pods

    # ----------------------------------------------------------------- view

    def _craft_intents(self) -> tuple:
        """Decode held keys into (thrusting, turning). Both rotation keys
        held = straight (they cancel); the craft only ever sees booleans
        and an integer, never key codes."""
        turning = 0
        if pygame.K_LEFT in self._held_keys:
            turning -= 1
        if pygame.K_RIGHT in self._held_keys:
            turning += 1
        return (pygame.K_UP in self._held_keys, turning)

    def draw(self, screen: pygame.Surface) -> None:
        screen.fill(BLACK)
        # Starfield first: it underlies every mode's content (spec).
        self.app.starfield.draw(screen)
        for asteroid in self._asteroids:
            asteroid.draw(screen)
        if self._phase == self.PHASE_PLAYING:
            for powerup in self._powerups:
                powerup.draw(screen)
            for pod in self._fuel_pods:
                pod.draw(screen)
            for ufo in self._ufos:
                ufo.draw(screen)
            for projectile in self._projectiles:
                projectile.draw(screen)
            for projectile in self._ufo_projectiles:
                projectile.draw(screen)
            for mine in self._mines:
                mine.draw(screen)
            for projectile in self._mine_projectiles:
                projectile.draw(screen)
            for missile in self._missiles:
                missile.draw(screen)
            for well in self._wells:
                well.draw(screen)
            # Debris and exhaust over the field, under the craft and beam:
            # an explosion reads as happening IN the world the craft flies
            # through, not on top of the player's own ship. (The list is
            # always empty during the intro - level advance sweeps it and
            # nothing emits while the field is frozen - so the
            # PHASE_PLAYING guard exists to document that invariant.)
            for particle in self._particles:
                particle.draw(screen)
            self._weapon.draw(screen, self._craft)
            self._craft.draw(screen)
        draw_game_hud(screen, self._hud_data())
        if self._phase == self.PHASE_INTRO:
            self._draw_level_intro(screen)

    def _weapon_charge_display(self) -> tuple:
        """(fraction 0..1, bar color) for the HUD charge line, or
        (None, None) for weapons without a recharge indicator (cannon)."""
        if isinstance(self._weapon, ChargedWeapon):
            return (self._weapon.charge / ChargedWeapon.CHARGE_MAX,
                    self._weapon.LABEL_COLOR)
        return None, None

    def _hud_data(self) -> HudData:
        charge_fraction, charge_color = self._weapon_charge_display()
        return HudData(
            level=self.level,
            shots_fired=self._score.shots_fired,
            hits=self._score.hits,
            hit_rate_text=self._score.hit_rate_text(),
            nickname=self._score.nickname,
            weapon_name=self._weapon.NAME,
            weapon_color=self._weapon.LABEL_COLOR,
            power_level=self._weapon.power(),
            sound_on=self.app.sound_on,
            game_time_seconds=self._game_time_frames // FPS,
            charge_fraction=charge_fraction,
            charge_color=charge_color,
            # The HUD owns the /FUEL_MAX scaling (spec: Fuel); the tank
            # itself only ever deals in integer units.
            fuel_fraction=self._craft.fuel / FUEL_MAX,
        )

    def _draw_level_intro(self, screen: pygame.Surface) -> None:
        # Full opacity during the hold, then a linear per-frame fade
        # (spec: "hold for 90 frames, then fade out over 30 frames").
        fade_progress = self._intro_frame - LEVEL_INTRO_HOLD
        if fade_progress < 0:
            alpha = 255
        else:
            alpha = int(255 * max(0.0, 1.0 - fade_progress / LEVEL_INTRO_FADE))
        surface = render_text(f"BEGIN LEVEL {self.level}",
                              HEADING_FONT_SIZE, WHITE)
        if alpha < 255:
            surface.set_alpha(alpha)
        width, height = screen.get_size()
        screen.blit(surface,
                    surface.get_rect(center=(width // 2, height // 2)))
