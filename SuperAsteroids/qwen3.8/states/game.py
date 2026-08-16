"""Game Mode.

Stage 6: all three weapons (Cannon/Laser/Shield, power levels 1-3 via
powerup pickups), the 30-second powerup spawn timer, level-based powerup
drop rolls on asteroid impact events, laser and shield collision handling,
the --debug hotkeys, and - new this stage - the enemy UFOs: the 3-minute
spawn clock (max 3 active, survives level advances), straight drift with
periodic deflection, their 120-frame firing cadence aimed at the craft,
powerup stealing, and the full UFO collision matrix from the spec.

Stage 7 (sound): every gameplay event plays its SFX from sfx/ (weapon
activations, rams, asteroid split/destruction, powerup spawn/collect/
destroy, UFO kills), and the two continuous loops - the thruster loop
while thrusting and the UFO loop while at least one UFO is active - are
reconciled with the simulation once per frame.

Level intro (start of EVERY level, including level 1): "BEGIN LEVEL N"
holds LEVEL_INTRO_HOLD frames, then fades over LEVEL_INTRO_FADE frames.
During it - and while paused - the field is drawn frozen, the craft is
hidden, no controls work, and no timers (spawn or game time) advance.

Frame order in the playing phase (matters for edge cases):
  1. movement: craft, asteroids, player projectiles, UFOs (drift plus
     their cadence shots), UFO projectiles, powerup drift
  2. spawn timers (powerup, then UFO), then weapon charge drain/recharge
  3. player weapons vs. the world (projectiles, laser beam, shield ram) -
     this is also where UFOs get destroyed by player weapons
  4. UFO projectiles vs. the world (asteroids without score, powerup
     icons, the craft -> game over "HOSTILE FIRE!" unless shielded)
  5. craft death check (fatal asteroid or UFO contact)
  6. powerup collection (any time, even during the icon's grace)
  7. drifting powerups vs. asteroids (out of grace only, no score)
  8. UFOs vs. powerups (steals - work even during the icon's grace)
  9. level advancement when the field is clear (UFOs and their
     projectiles leave play; the UFO spawn timer PERSISTS)
"""

import math
import random

import pygame

from entities import (PlayerCraft, player_hits_asteroid,
                      player_hits_ufo, spawn_level_asteroids, spawn_ufo)
from entities.powerup import (Powerup, spawn_drop_powerup,
                              spawn_timer_powerup)
from font_manager import render_text
from game_constants import (
    ASTEROID_MIN_RADIUS_FOR_SPLIT,
    BLACK,
    CRAFT_SPAWN_SAFE_DISTANCE,
    DEBUG_SPAWN_ATTEMPTS,
    FPS,
    FRIENDLY_FIRE_MESSAGE,
    HEADING_FONT_SIZE,
    HOSTILE_FIRE_MESSAGE,
    LASER_SAMPLE_STEP,
    LEVEL_1_ASTEROID_COUNT,
    LEVEL_ASTEROID_COUNT_INCREMENT,
    LEVEL_INTRO_FADE,
    LEVEL_INTRO_HOLD,
    PLAYER_RADIUS,
    POWERUP_DROP_CHANCES,
    POWERUP_INTERVAL,
    UFO_INTERVAL,
    UFO_MAX_ACTIVE,
    WHITE,
)
from hud import HudData, draw_game_hud
from position_utils import shortest_delta, torus_distance, wrap_around
from score import ScoreTracker
from sound import (
    SFX_ASTEROID_DESTROYED,
    SFX_ASTEROID_SPLIT,
    SFX_CANNON_BY_LEVEL,
    SFX_LASER_BY_LEVEL,
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
from weapons import Cannon, ChargedWeapon, Laser, RammingShield, make_weapon


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
        self._powerups: list = []
        self._ufos: list = []
        # The 30-second powerup counter runs ONLY in the playing phase and
        # deliberately survives level advances; a fresh game starts it at
        # full value (spec: Timers / Powerups). The 3-minute UFO counter
        # has the exact same persistence rule (spec: Enemy UFOs).
        self._powerup_timer = POWERUP_INTERVAL
        self._ufo_timer = UFO_INTERVAL
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

        Projectiles, powerup icons, UFOs, and UFO projectiles all leave
        play (spec: Enemy UFOs - "those UFOs are simply removed"), the
        craft returns to center facing up at v=0, an active laser/shield
        deactivates with its charge restored (spec), and the new level's
        field spawns under the intro sequence again. The powerup and UFO
        spawn timers and the score are NOT reset (spec: Timers / Scoring).
        """
        self.level += 1
        self._asteroid_count += random.randint(*LEVEL_ASTEROID_COUNT_INCREMENT)
        width, height = self.app.screen.get_size()
        self._craft.reset(width // 2, height // 2)
        self._projectiles = []
        self._ufo_projectiles = []
        self._powerups = []
        self._ufos = []
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
        weapons arm their beam/shield. ONLY a successful activation
        records a shot (spec: "Weapon activation") - or plays its SFX:
        the firing sounds key off the same success, so a blocked press
        (projectile cap, charge below 20) is silent and not counted."""
        if self._weapon.on_press(self._craft, self._projectiles):
            self._score.record_shot()
            self._play_weapon_activation_sound()

    def _play_weapon_activation_sound(self) -> None:
        """The SFX for one successful activation (sfx/README.md): the
        cannon and laser each have a per-power-level shot, the shield one
        sound for any level."""
        if isinstance(self._weapon, Cannon):
            name = SFX_CANNON_BY_LEVEL[self._weapon.index()]
        elif isinstance(self._weapon, Laser):
            name = SFX_LASER_BY_LEVEL[self._weapon.index()]
        elif isinstance(self._weapon, RammingShield):
            name = SFX_SHIELD_ACTIVATED
        else:
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
            # Nothing may be heard during the intro (no thrust, no UFOs -
            # they always leave play on level advance): sync to the empty
            # set rather than letting a loop from the previous level run
            # on under the "BEGIN LEVEL N" text.
            self._sync_sound_loops(thrusting=False)
            return

        self._game_time_frames += 1
        # Live window size keeps every wrap correct right after a resize
        # (the spec's "forced screen wrap" requirement).
        width, height = self.app.screen.get_size()
        thrusting, turning = self._craft_intents()
        self._craft.update(thrusting, turning, width, height)
        self._sync_sound_loops(thrusting)
        for asteroid in self._asteroids:
            asteroid.update(width, height)
        for projectile in self._projectiles:
            projectile.update(width, height)
        for projectile in self._ufo_projectiles:
            projectile.update(width, height)
        for ufo in self._ufos:
            ufo.update(width, height)
            # Hostile shots land in the enemy projectile list, where step 4
            # of the frame order arbitrates their hits.
            if ufo.fire_ready:
                self._ufo_projectiles.append(ufo.fire_toward(
                    self._craft.x, self._craft.y, width, height))
        for powerup in self._powerups:
            powerup.update(width, height)
        self._tick_powerup_timer(width, height)
        self._tick_ufo_timer(width, height)
        # Charge drain/recharge before collision passes so a beam that
        # depletes this frame is already down when it is (not) resolved.
        self._weapon.update(self._space_held)

        if not self._resolve_weapon_hits(width, height):
            return  # friendly fire already took us to Game Over
        if not self._resolve_ufo_projectile_hits(width, height):
            return  # hostile fire already took us to Game Over
        if self._resolve_craft_deaths(width, height):
            return
        self._collect_powerups(width, height)
        self._resolve_powerup_asteroid_hits(width, height)
        self._resolve_ufo_powerup_steals(width, height)
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
        self._ufo_timer = UFO_INTERVAL
        if len(self._ufos) >= UFO_MAX_ACTIVE:
            return  # at cap: reset only, no spawn (spec)
        self._ufos.append(spawn_ufo(
            width, height, (self._craft.x, self._craft.y)))

    def _sync_sound_loops(self, thrusting: bool) -> None:
        """Reconcile the continuous SFX with the simulation (spec: Sound):
        the thruster loop sounds only while Up is applied, the UFO hum only
        while at least one UFO is active (it keeps going while several UFOs
        remain and stops when the last one is destroyed).

        The app clears the loop set on every pause / game-over / mode
        transition, so this per-frame call is also what re-establishes it
        after a resume. The manager only starts/stops on set CHANGES, so
        calling it every frame is cheap and cannot re-stutter a running
        loop.
        """
        wanted: set = set()
        if self._ufos:
            wanted.add(SFX_UFO)
        if thrusting:
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
        one), and its own craft (friendly fire, grace-gated). Returns
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
                # by player weapons are what "Hits" count.
                live.remove(asteroid)
                replacements.extend(self._apply_asteroid_impact(
                    asteroid, score=True, destroy_outright=False))
                continue
            powerup = next(
                (p for p in self._powerups
                 if not p.in_grace
                 and projectile.hits_circle(p.x, p.y, p.radius,
                                            width, height)),
                None,
            )
            if powerup is not None:
                # The projectile consumes the icon (spec: Cannon). No shot
                # or hit is recorded - an impact, not an activation.
                self._destroy_powerup(powerup)
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
                self._asteroids.remove(asteroid)
                self._asteroids.extend(self._apply_asteroid_impact(
                    asteroid, score=True,
                    destroy_outright=weapon.destroys_on_hit()))
                weapon.deactivate_after_hit()
                return
            powerup = next(
                (p for p in self._powerups
                 if not p.in_grace
                 and torus_distance(sx, sy, p.x, p.y, width, height)
                 <= p.radius),
                None,
            )
            if powerup is not None:
                self._destroy_powerup(powerup)
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

    def _resolve_shield_hits(self, width: int, height: int) -> None:
        """The ring rams asteroids and UFOs (destroy + bounce) and shreds
        out-of-grace powerup icons. Unlike the laser, it stays ACTIVE
        after impacts until its charge runs out (spec: Ramming Shield)."""
        weapon = self._weapon
        if not isinstance(weapon, RammingShield) or not weapon.firing:
            return
        # At most one ram per frame: each bounce DISCARDS the craft's
        # current velocity, so a second simultaneous impact would only
        # throw the first bounce away. Asteroids keep first dibs, then
        # UFOs; the rest queue for next frame.
        if not self._shield_rams_asteroid(weapon, width, height):
            self._shield_rams_ufo(weapon, width, height)
        # Icons touching the ring outside their grace period are destroyed
        # - through _destroy_powerup so they get the same destruction cue
        # as every other destroy path (spec: "by any means"). In-grace
        # icons are untouched: the craft may still collect them in
        # _collect_powerups() while the shield is raised. An explicit loop
        # rather than a comprehension filter: _destroy_powerup mutates
        # self._powerups (via .remove), which the loop must not race.
        survivors = []
        for powerup in self._powerups:
            if (not powerup.in_grace
                    and powerup.overlaps_circle(
                        self._craft.x, self._craft.y, weapon.shield_radius,
                        width, height)):
                self._destroy_powerup(powerup)
            else:
                survivors.append(powerup)
        self._powerups = survivors

    def _shield_rams_asteroid(self, weapon: RammingShield,
                              width: int, height: int) -> bool:
        """First asteroid touching the ring: impact event + bounce.
        Returns True if a ram happened (so no Ufo can ram the same frame)."""
        for asteroid in self._asteroids:
            # Wrap-aware vector from the rock's center to the craft's:
            # exactly "directly away from the point of impact".
            dx = shortest_delta(self._craft.x - asteroid.x, width)
            dy = shortest_delta(self._craft.y - asteroid.y, height)
            if math.hypot(dx, dy) <= weapon.shield_radius + asteroid.radius:
                self._asteroids.remove(asteroid)
                self._asteroids.extend(self._apply_asteroid_impact(
                    asteroid, score=True,
                    destroy_outright=weapon.destroys_on_hit()))
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

    # ---------------------------------------------------------------- enemy fire

    def _resolve_ufo_projectile_hits(self, width: int, height: int) -> bool:
        """Hostile shots vs. the world (spec: Enemy UFOs). Returns False iff
        the craft died to a hostile shot (GameOver already triggered).

        Rules, in arbitration order: asteroids split/destroy WITHOUT
        scoring the player; powerup icons are destroyed (out of grace
        only); the craft dies with "HOSTILE FIRE!" - unless the ramming
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
                    asteroid, score=False, destroy_outright=False))
                continue
            powerup = next(
                (p for p in self._powerups
                 if not p.in_grace
                 and projectile.hits_circle(p.x, p.y, p.radius,
                                             width, height)),
                None,
            )
            if powerup is not None:
                self._destroy_powerup(powerup)
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
        the same UFO in one frame - the destruction SFX plays exactly once,
        on the removal that actually happens. (The 100-particle light red
        explosion still lands in Stage 8.)"""
        try:
            self._ufos.remove(ufo)
            self.app.sound.play(SFX_UFO_DESTROYED)
        except ValueError:
            pass  # already shredded by another hit this frame

    def _resolve_ufo_powerup_steals(self, width: int, height: int) -> None:
        """A UFO "steals" a powerup on contact: the icon is removed from
        play, the UFO is UNaffected (no split, no damage, no bounce), and
        - unlike every other destroyer in the game - this works even
        during the icon's grace period (spec: Enemy UFOs)."""
        for ufo in self._ufos:
            # Snapshot: _destroy_powerup mutates self._powerups.
            for powerup in list(self._powerups):
                if (torus_distance(ufo.x, ufo.y, powerup.x, powerup.y,
                                   width, height)
                        <= ufo.radius + powerup.radius):
                    self._destroy_powerup(powerup)

    # ------------------------------------------------------- asteroid impacts

    def _apply_asteroid_impact(self, asteroid, score: bool,
                               destroy_outright: bool) -> list:
        """Resolve one asteroid being hit. Returns its replacement children.

        ``score`` records a player "Hit" - player weapons only (spec:
        Scoring; powerup impacts and UFO-projectile impacts pass False).
        ``destroy_outright`` (laser/shield power 3) skips the split rules
        entirely. EVERY split and destruction event rolls the level-based
        powerup drop chance (spec: Powerups) - and plays its cue, whoever
        (or whatever) delivered the hit, since the sfx README defines both
        sounds by the EVENT (a split / a destruction), not the cause.
        """
        if score:
            self._score.record_hit()
        if destroy_outright or asteroid.radius < ASTEROID_MIN_RADIUS_FOR_SPLIT:
            children: list = []
            self.app.sound.play(SFX_ASTEROID_DESTROYED)
        else:
            children = asteroid.split()
            self.app.sound.play(SFX_ASTEROID_SPLIT)
        if random.random() < self._powerup_drop_chance():
            self._powerups.append(spawn_drop_powerup(asteroid.x, asteroid.y))
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

    def _collect_powerups(self, width: int, height: int) -> None:
        """The craft may collect icons ANY time - even during their grace
        period (spec). Same type: power +1 (max 3). Different type: switch
        at power 1. Icons have no cap, so several can be collected in one
        frame (the last one's effect wins, like any rapid pickup)."""
        survivors = []
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
                # One cue per icon: several pickups in one frame each play
                # (pygame simply re-fires the channel - acceptable).
                self.app.sound.play(SFX_POWERUP_COLLECTED)
            else:
                survivors.append(powerup)
        self._powerups = survivors

    def _resolve_powerup_asteroid_hits(self, width: int, height: int) -> None:
        """A drifting out-of-grace icon touching an asteroid is destroyed,
        and the asteroid splits/destroys per the normal impact rules -
        without scoring the player (spec: Powerups / Scoring). Each icon
        and rock is consumed at most once per frame."""
        consumed_icons: set = set()
        impacted_rocks: set = set()
        for powerup in self._powerups:
            if powerup.in_grace:
                continue
            for asteroid in self._asteroids:
                if id(asteroid) in impacted_rocks:
                    continue
                if powerup.overlaps_circle(asteroid.x, asteroid.y,
                                           asteroid.radius, width, height):
                    consumed_icons.add(id(powerup))
                    impacted_rocks.add(id(asteroid))
                    break  # one rock per icon per frame
        for powerup in self._powerups:
            if id(powerup) in consumed_icons:
                self._destroy_powerup(powerup)
        # Iterate a SNAPSHOT: the loop body rebuilds self._asteroids, and
        # removing elements from a list mid-iteration would skip the rock
        # sitting right after each removed one.
        for asteroid in list(self._asteroids):
            if id(asteroid) in impacted_rocks:
                self._asteroids.remove(asteroid)
                self._asteroids.extend(self._apply_asteroid_impact(
                    asteroid, score=False, destroy_outright=False))

    def _destroy_powerup(self, powerup) -> None:
        """Remove an icon from play regardless of the cause (projectile,
        beam, shield, drifting rock, stolen by a UFO). The destruction cue
        plays once, on the removal that actually happens."""
        try:
            self._powerups.remove(powerup)
            self.app.sound.play(SFX_POWERUP_DESTROYED)
        except ValueError:
            pass  # already consumed by another collision this frame

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
        for asteroid in self._asteroids:
            asteroid.draw(screen)
        if self._phase == self.PHASE_PLAYING:
            for powerup in self._powerups:
                powerup.draw(screen)
            for ufo in self._ufos:
                ufo.draw(screen)
            for projectile in self._projectiles:
                projectile.draw(screen)
            for projectile in self._ufo_projectiles:
                projectile.draw(screen)
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
