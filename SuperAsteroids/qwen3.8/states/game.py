"""Game Mode.

Stage 5: all three weapons are live (Cannon/Laser/Shield, power levels 1-3
via powerup pickups), with the 30-second powerup spawn timer, level-based
powerup drop rolls on asteroid impact events, laser and shield collision
handling, and the --debug spawning hotkeys.

Level intro (start of EVERY level, including level 1): "BEGIN LEVEL N"
holds LEVEL_INTRO_HOLD frames, then fades over LEVEL_INTRO_FADE frames.
During it - and while paused - the field is drawn frozen, the craft is
hidden, no controls work, and no timers (spawn or game time) advance.
Enemy UFOs land in Stage 6.

Frame order in the playing phase (matters for edge cases):
  1. movement: craft, asteroids, projectiles, powerup drift
  2. powerup timer tick, then weapon charge drain/recharge
  3. player weapons vs. the world (projectiles, laser beam, shield ram)
  4. craft death check (shield rams, or fatal asteroid contact)
  5. powerup collection (any time, even during the icon's grace)
  6. drifting powerups vs. asteroids (out of grace only, no score)
  7. level advancement when the field is clear
"""

import math
import random

import pygame

from entities import (PlayerCraft, player_hits_asteroid,
                      spawn_level_asteroids)
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
    LASER_SAMPLE_STEP,
    LEVEL_1_ASTEROID_COUNT,
    LEVEL_ASTEROID_COUNT_INCREMENT,
    LEVEL_INTRO_FADE,
    LEVEL_INTRO_HOLD,
    PLAYER_RADIUS,
    POWERUP_DROP_CHANCES,
    POWERUP_INTERVAL,
    WHITE,
)
from hud import HudData, draw_game_hud
from position_utils import shortest_delta, torus_distance, wrap_around
from score import ScoreTracker
from states.base import GameModeState
from weapons import ChargedWeapon, Laser, RammingShield, make_weapon


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
        self._powerups: list = []
        # The 30-second powerup counter runs ONLY in the playing phase and
        # deliberately survives level advances; a fresh game starts it at
        # full value (spec: Timers / Powerups).
        self._powerup_timer = POWERUP_INTERVAL
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

        Projectiles and powerup icons leave play (UFOs join this sweep in
        Stage 6), the craft returns to center facing up at v=0, an active
        laser/shield deactivates with its charge restored (spec), and the
        new level's field spawns under the intro sequence again. The
        powerup spawn timer and the score are NOT reset (spec: Timers /
        Scoring).
        """
        self.level += 1
        self._asteroid_count += random.randint(*LEVEL_ASTEROID_COUNT_INCREMENT)
        width, height = self.app.screen.get_size()
        self._craft.reset(width // 2, height // 2)
        self._projectiles = []
        self._powerups = []
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
        records a shot (spec: "Weapon activation")."""
        if self._weapon.on_press(self._craft, self._projectiles):
            self._score.record_shot()

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
        # 'u' (spawn a debug UFO) lands in Stage 6 with the UFO entity.

    def _spawn_debug_powerup(self, weapon_name: str) -> None:
        width, height = self.app.screen.get_size()
        x, y = self._debug_spawn_point(width, height)
        self._powerups.append(Powerup(x, y, weapon_name))

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
            return

        self._game_time_frames += 1
        # Live window size keeps every wrap correct right after a resize
        # (the spec's "forced screen wrap" requirement).
        width, height = self.app.screen.get_size()
        thrusting, turning = self._craft_intents()
        self._craft.update(thrusting, turning, width, height)
        for asteroid in self._asteroids:
            asteroid.update(width, height)
        for projectile in self._projectiles:
            projectile.update(width, height)
        for powerup in self._powerups:
            powerup.update(width, height)
        self._tick_powerup_timer(width, height)
        # Charge drain/recharge before collision passes so a beam that
        # depletes this frame is already down when it is (not) resolved.
        self._weapon.update(self._space_held)

        if not self._resolve_weapon_hits(width, height):
            return  # friendly fire already took us to Game Over
        if self._resolve_craft_deaths(width, height):
            return
        self._collect_powerups(width, height)
        self._resolve_powerup_asteroid_hits(width, height)
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
        (out-of-grace destruction), and its own craft (friendly fire,
        grace-gated). Returns False if Game Over was triggered."""
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

    def _resolve_shield_hits(self, width: int, height: int) -> None:
        """The ring rams asteroids (split/destroy + bounce) and shreds
        out-of-grace powerup icons. Unlike the laser, it stays ACTIVE
        after impacts until its charge runs out (spec: Ramming Shield)."""
        weapon = self._weapon
        if not isinstance(weapon, RammingShield) or not weapon.firing:
            return
        # At most one rock rammed per frame: each bounce DISCARDS the
        # craft's current velocity, so a second simultaneous impact would
        # only throw the first bounce away. The rest queue for next frame.
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
                break
        # Icons touching the ring outside their grace period are destroyed
        # (spec). In-grace icons are untouched: the craft may still collect
        # them in _collect_powerups() while the shield is raised.
        self._powerups = [
            p for p in self._powerups
            if not (not p.in_grace and p.overlaps_circle(
                self._craft.x, self._craft.y, weapon.shield_radius,
                width, height))
        ]

    # ------------------------------------------------------- asteroid impacts

    def _apply_asteroid_impact(self, asteroid, score: bool,
                               destroy_outright: bool) -> list:
        """Resolve one asteroid being hit. Returns its replacement children.

        ``score`` records a player "Hit" - player weapons only (spec:
        Scoring; powerup-impact and Stage 6's UFO impacts pass False).
        ``destroy_outright`` (laser/shield power 3) skips the split rules
        entirely. EVERY split and destruction event rolls the level-based
        powerup drop chance (spec: Powerups).
        """
        if score:
            self._score.record_hit()
        if destroy_outright or asteroid.radius < ASTEROID_MIN_RADIUS_FOR_SPLIT:
            children: list = []
        else:
            children = asteroid.split()
        if random.random() < self._powerup_drop_chance():
            self._powerups.append(spawn_drop_powerup(asteroid.x, asteroid.y))
        return children

    def _powerup_drop_chance(self) -> float:
        # 8/6/4/2% on levels 1-4, then 1% forever (spec: Powerups).
        return POWERUP_DROP_CHANCES[
            min(self.level, len(POWERUP_DROP_CHANCES)) - 1]

    # ------------------------------------------------------------- craft fate

    def _resolve_craft_deaths(self, width: int, height: int) -> bool:
        """Returns True if the craft died this frame (state already swapped).

        While the shield is up, its radius (35-40px) fully covers the
        craft's 20px bounding circle, so any asteroid touching the craft
        was ALREADY resolved as a ram-bounce in _resolve_shield_hits() -
        the fatal-contact check is skipped for that frame.
        """
        if isinstance(self._weapon, RammingShield) and self._weapon.firing:
            return False
        if any(player_hits_asteroid(self._craft, a, width, height)
               for a in self._asteroids):
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
        """Remove an icon from play regardless of the cause (Stage 7 will
        add the destroyed-icon SFX here)."""
        try:
            self._powerups.remove(powerup)
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
            for projectile in self._projectiles:
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
