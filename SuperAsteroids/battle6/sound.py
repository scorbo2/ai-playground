"""Sound engine: load every effect from ``sfx/`` into memory at startup and
play one-shots plus the continuous loops (thrusters, UFO hum, mine pulse).

Per the spec (SuperAsteroids2.md -> "Sound"):
  - all effects are loaded into memory when the game starts;
  - load errors and I/O errors are NOT fatal: a warning is logged for each
    file that fails and the game proceeds without that sound (if the audio
    device itself is unavailable, the game proceeds with no audio at all);
  - there is one global on/off switch, toggled with F2 from ANY mode, that
    persists until toggled again ("Sound" line in the HUD reports it);
  - ``--nosound`` does not disable the sound system, it just starts the
    switch off.

Loop discipline: the game state calls ``set_active_loops()`` with the set
of loops that should be audible right now (the thruster loop while the Up
key drives thrust, and the UFO loop while at least one UFO is active). The
mine-pulse sound is NOT a loop - it is a one-shot that fires once every
120 frames while at least one unactivated mine is "scanning" for a target
(the game state plays it as a discrete event). The app clears the set on
every pause / game-over / mode transition, so no loop can survive a frozen
or abandoned game. Toggling sound off stops every loop immediately;
toggling back on re-establishes whatever the game state asked for (the
per-frame sync call keeps that set current).
"""

import sys
from pathlib import Path

import pygame

# -------------------------------------------------------------------- names
# A sound is referenced by the base name of its file in sfx/ (no extension).
# Keeping them as constants (instead of free strings at call sites) means a
# typo cannot silently no-op: it is a NameError, not a missing bang.

SFX_TITLE_SCREEN = "title_screen"
SFX_CANNON_L1 = "cannon_lvl1"
SFX_CANNON_L2 = "cannon_lvl2"
SFX_CANNON_L3 = "cannon_lvl3"
SFX_LASER_L1 = "laser_lvl1"
SFX_LASER_L2 = "laser_lvl2"
SFX_LASER_L3 = "laser_lvl3"
SFX_SHIELD_ACTIVATED = "shield_activated"
SFX_SHIELD_RAM = "shield_ram"
SFX_ASTEROID_SPLIT = "asteroid_split"
SFX_ASTEROID_DESTROYED = "asteroid_destroyed"
SFX_POWERUP_SPAWN = "powerup_spawn"
SFX_POWERUP_DESTROYED = "powerup_destroyed"
SFX_POWERUP_COLLECTED = "powerup_collected"
SFX_SHIP_DESTROYED_ASTEROID = "ship_destroyed_asteroid"
SFX_SHIP_DESTROYED_FRIENDLY_FIRE = "ship_destroyed_friendly_fire"
SFX_MINE_ACTIVATED = "mine_activated"
SFX_MINE_PULSE = "mine_pulse"
SFX_MINE_DETONATE = "mine_detonate"
SFX_UFO = "ufo"
SFX_UFO_DESTROYED = "ufo_destroyed"
SFX_THRUSTERS = "thrusters"

# Cannon/laser fire sounds are indexed by the weapon's 0-based power level.
SFX_CANNON_BY_LEVEL = (SFX_CANNON_L1, SFX_CANNON_L2, SFX_CANNON_L3)
SFX_LASER_BY_LEVEL = (SFX_LASER_L1, SFX_LASER_L2, SFX_LASER_L3)

# Every sound the manager loads at startup. Anything missing from sfx/ is
# skipped with a warning (spec: load failures are not fatal).
ALL_SOUNDS = (
    SFX_TITLE_SCREEN,
    *SFX_CANNON_BY_LEVEL,
    *SFX_LASER_BY_LEVEL,
    SFX_SHIELD_ACTIVATED,
    SFX_SHIELD_RAM,
    SFX_ASTEROID_SPLIT,
    SFX_ASTEROID_DESTROYED,
    SFX_POWERUP_SPAWN,
    SFX_POWERUP_DESTROYED,
    SFX_POWERUP_COLLECTED,
    SFX_SHIP_DESTROYED_ASTEROID,
    SFX_SHIP_DESTROYED_FRIENDLY_FIRE,
    SFX_MINE_ACTIVATED,
    SFX_MINE_PULSE,
    SFX_MINE_DETONATE,
    SFX_UFO,
    SFX_UFO_DESTROYED,
    SFX_THRUSTERS,
)

# sfx/ sits next to this module (the project root).
DEFAULT_SFX_DIR = Path(__file__).resolve().parent / "sfx"


class SoundManager:
    """Owns all playback. Created once by the app, shared by every state.

    Safe to use on a machine with no audio: every method degrades to a
    no-op (one warning logged) rather than raising.
    """

    def __init__(self, sfx_dir: Path = DEFAULT_SFX_DIR,
                 sound_on: bool = True):
        self._sounds: dict = {}
        self._sound_on = sound_on
        # What the game state asked for (persists while sound is turned off)
        # vs. what is actually playing right now.
        self._desired_loops: set = set()
        self._active_loops: set = set()
        self._audio_available = self._ensure_mixer()
        if self._audio_available:
            self._load_sounds(sfx_dir)

    # ------------------------------------------------------------- state API

    @property
    def sound_on(self) -> bool:
        return self._sound_on

    @property
    def has_sound(self, name: str) -> bool:
        """True if the named effect loaded successfully (a failed file is
        remembered as absent and its warnings were already logged)."""
        return name in self._sounds

    def toggle(self) -> bool:
        """F2 handler: flip the global switch and make the loops obey it
        immediately. Returns the NEW state."""
        self._sound_on = not self._sound_on
        self._sync_loops()
        return self._sound_on

    def play(self, name: str) -> None:
        """Fire a one-shot effect. No-ops when sound is off, the device is
        unavailable, or the file failed to load at startup."""
        if not (self._sound_on and self._audio_available):
            return
        sound = self._sounds.get(name)
        if sound is None:
            return
        sound.play()

    def set_active_loops(self, names: frozenset) -> None:
        """The set of loops that should be audible right now (spec: Sound).

        Idempotent per frame: only loops entering or leaving the set are
        touched, so an unchanged set never restarts (and re-stutters) an
        already-running loop.
        """
        self._desired_loops = set(names)
        self._sync_loops()

    def stop_loops(self) -> None:
        """The app calls this on every pause / game-over / mode transition,
        so no loop can outlive the mode that started it."""
        self.set_active_loops(frozenset())

    # ------------------------------------------------------------ internal

    @staticmethod
    def _ensure_mixer() -> bool:
        """True if the mixer is (or can be) initialized. Failure is a single
        non-fatal warning - the spec makes audio load errors non-fatal, and
        a headless machine with no audio device is the same family of event.
        """
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init()
            return True
        except pygame.error as err:
            print(f"Warning: audio device unavailable, continuing without "
                  f"sound: {err}", file=sys.stderr)
            return False

    def _load_sounds(self, sfx_dir: Path) -> None:
        if not sfx_dir.is_dir():
            print(f"Warning: sfx directory not found: {sfx_dir}, "
                  f"continuing without sound", file=sys.stderr)
            return
        for name in ALL_SOUNDS:
            path = sfx_dir / f"{name}.wav"
            try:
                self._sounds[name] = pygame.mixer.Sound(str(path))
            except (pygame.error, OSError) as err:
                # Spec: warn and proceed without THIS sound; the rest load.
                print(f"Warning: could not load sound {path}: {err}",
                      file=sys.stderr)

    def _sync_loops(self) -> None:
        """Reconcile playing loops with the desired set (iff sound is on)."""
        if self._sound_on and self._audio_available:
            wanted = self._desired_loops & self._sounds.keys()
        else:
            wanted = set()
        for name in self._active_loops - wanted:
            self._sounds[name].stop()
        for name in wanted - self._active_loops:
            self._sounds[name].play(-1)
        self._active_loops = wanted
