"""Game Mode.

Stage 4: the Cannon (power level 1) fires; projectiles split or destroy
asteroids; clearing the whole field advances the level (fresh asteroid
specs, random +1-2 count roll) and replays the "BEGIN LEVEL N" intro.
Scoring (shots/hits/hit rate/nickname) and the HUD are live.

Level intro (start of EVERY level, including level 1): "BEGIN LEVEL N"
holds LEVEL_INTRO_HOLD frames, then fades over LEVEL_INTRO_FADE frames.
During it - and while paused - the field is drawn frozen, the craft is
hidden, no controls work, and no timers (spawn or game time) advance.
Powerups and enemy UFOs (Stages 5-6) and weapon levels 2-3 (Stage 5)
extend this state further.
"""

import random

import pygame

from entities import (PlayerCraft, player_hits_asteroid,
                      spawn_level_asteroids)
from font_manager import render_text
from game_constants import (
    BLACK,
    FPS,
    HEADING_FONT_SIZE,
    LEVEL_1_ASTEROID_COUNT,
    LEVEL_ASTEROID_COUNT_INCREMENT,
    LEVEL_INTRO_FADE,
    LEVEL_INTRO_HOLD,
    PLAYER_RADIUS,
    WHITE,
)
from hud import HudData, draw_game_hud
from score import ScoreTracker
from states.base import GameModeState
from weapons import Cannon


class GameState(GameModeState):

    LEVEL_1 = 1
    PHASE_INTRO = "intro"        # "BEGIN LEVEL N": frozen field, no controls
    PHASE_PLAYING = "playing"    # full simulation

    FRIENDLY_FIRE_MESSAGE = "FRIENDLY FIRE!"

    def __init__(self, app):
        super().__init__(app)
        self.level = self.LEVEL_1
        # Asteroids to spawn for the CURRENT level. Level 1 is fixed at 5;
        # each advancement rolls +1 or +2 (the spec's random growth).
        self._asteroid_count = LEVEL_1_ASTEROID_COUNT
        self._score = ScoreTracker()
        self._weapon = Cannon()
        self._projectiles: list = []
        self._game_time_frames = 0  # active game time only (spec: Timers)
        # Keys physically held right now (arrows only - Space is press-based).
        # Dropped in on_pause()/on focus loss so stale presses can't leak in
        # (pygame has no key-repeat unless set_repeat() is called, so a key
        # still physically held after resume stays "released" until pressed
        # again - safer than the alternative of a stuck thrust).
        self._held_keys: set = set()
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

        Projectiles are dropped (Stage 5+ adds particles/powerups/UFOs to
        this sweep), the craft returns to center facing up at v=0, and the
        new level's field spawns under the intro sequence again.
        """
        self.level += 1
        self._asteroid_count += random.randint(*LEVEL_ASTEROID_COUNT_INCREMENT)
        width, height = self.app.screen.get_size()
        self._craft.reset(width // 2, height // 2)
        self._projectiles = []
        self._asteroids = self._spawn_level_field(width, height)
        self._phase = self.PHASE_INTRO
        self._intro_frame = 0

    # --------------------------------------------------------------- events

    def handle_events(self, events: list) -> None:
        for event in events:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.app.to_pause()
                elif (event.key == pygame.K_SPACE
                      and self._phase == self.PHASE_PLAYING):
                    self._fire_weapon()
                elif event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP):
                    self._held_keys.add(event.key)
            elif event.type == pygame.KEYUP:
                self._held_keys.discard(event.key)
            elif event.type == pygame.WINDOWFOCUSLOST:
                # Keys released without focus never produced KEYUP events.
                self._held_keys.clear()

    def on_pause(self) -> None:
        # The craft must not wake up still "thrusting" because a key
        # happened to be held when the pause key went down.
        self._held_keys.clear()

    def _fire_weapon(self) -> None:
        spawned = self._weapon.fire(self._craft, self._projectiles)
        if not spawned:
            return  # in-flight cap: a BLOCKED press scores no shot (spec)
        self._projectiles.extend(spawned)
        self._score.record_shot()

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

        if not self._resolve_projectile_hits(width, height):
            return  # friendly fire already took us to Game Over
        if any(player_hits_asteroid(self._craft, a, width, height)
               for a in self._asteroids):
            self.app.to_game_over()
            return
        if not self._asteroids:
            self._advance_level()

    def _resolve_projectile_hits(self, width: int, height: int) -> bool:
        """Projectiles vs. asteroids (impact events) and vs. its own craft
        (friendly fire, grace-gated). Returns False if Game Over was
        triggered (friendly fire), True if the game continues.
        """
        live = list(self._asteroids)
        replacements: list = []
        survivors: list = []
        for projectile in self._projectiles:
            target = next(
                (a for a in live
                 if projectile.hits_circle(a.x, a.y, a.radius, width, height)),
                None,
            )
            if target is not None:
                # Asteroid impact event: the projectile is consumed, the
                # hit asteroid is removed, and its split children (or none,
                # if too small to split - then it is simply destroyed) take
                # its place. Splits by player weapons are what "Hits" count.
                live.remove(target)
                replacements.extend(target.split())
                self._score.record_hit()
            elif (projectile.can_hit_player
                  and projectile.hits_circle(self._craft.x, self._craft.y,
                                             PLAYER_RADIUS, width, height)):
                self.app.to_game_over(self.FRIENDLY_FIRE_MESSAGE)
                return False
            elif not projectile.expired:
                survivors.append(projectile)
        self._projectiles = survivors
        self._asteroids = live + replacements
        return True

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
            for projectile in self._projectiles:
                projectile.draw(screen)
            self._craft.draw(screen)
        draw_game_hud(screen, self._hud_data())
        if self._phase == self.PHASE_INTRO:
            self._draw_level_intro(screen)

    def _hud_data(self) -> HudData:
        return HudData(
            level=self.level,
            shots_fired=self._score.shots_fired,
            hits=self._score.hits,
            hit_rate_text=self._score.hit_rate_text(),
            nickname=self._score.nickname,
            weapon_name=self._weapon.NAME,
            weapon_color=self._weapon.LABEL_COLOR,
            power_level=self._weapon.power_level,
            sound_on=self.app.sound_on,
            game_time_seconds=self._game_time_frames // FPS,
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
