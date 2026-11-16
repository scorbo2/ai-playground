"""Stage 12 tests: generated buffers, configured levels, and event-to-sound wiring.

Four layers, mirroring the split of the implementation:

* :class:`src.model.audio_levels.AudioLevels` — the *policy*: which sounds exist,
  what each may cost in loudness, and what the config is not allowed to say.
* The config layer — the new ``audio`` section, validated by delegating to the
  same object the runtime builds, so a file that loads is a file the mixer runs.
* The synthesised buffers — the spec's "generated sound effects via ``array`` +
  ``Sound(buffer=...)``". These are the buffer-generation gate tests: shape,
  int16 safety, byte-for-byte determinism, peak normalisation (which is what
  makes a configured level mean the same thing for every effect), and the
  structure each effect is supposed to have (a klaxon alternates, a gunshot
  falls in pitch, a wreck is bigger than a hit in more ways than volume).
* The scene wiring — the spec's "spy-based event X plays sound Y" gate: every
  gameplay event that should make a noise, and the ones that must not.

The stage gate: buffer generation tests; spy-based "event X plays sound Y"
tests; game runs fully with audio disabled.

Note on the mixer under the dummy driver: it *does* initialise (SDL has a dummy
audio backend), so the real :class:`~src.audio.AudioSystem` is exercisable here,
buffers and all. ``Sound.set_volume`` is quantised to 1/128 by SDL, so volume
assertions compare with a tolerance rather than exactly.
"""

import array
import dataclasses
import math
import os
import random
import subprocess
import sys
import wave

import pygame
import pygame_gui
import pytest

import main  # noqa: F401  (ensures project root is on sys.path)

from src import audio as audio_module
from src import audio_buffers as buffers_module
from src.audio import (
    AUDIO_DEBUG_ENV,
    MIXER_VOICE_COUNT,
    AudioSystem,
    _match_mixer,
    _mixer_format,
)
from src.audio_buffers import (
    _BEEP_MS,
    _JUMP_SPINUP_MS,
    _REFERENCE_PEAK,
    _SHIP_DESTRUCTION_MS,
    _SHIP_IMPACT_MS,
    _SCAN_KLAXON_MS,
    _THUNDERCLAP_MS,
    _WEAPON_FIRE_MS,
    BUFFER_GENERATORS,
    _generate_explosion,
    _generate_scan_klaxon,
    _generate_ship_destruction,
    _generate_ship_impact,
    _generate_weapon_fire,
    _normalize,
    write_wav,
)
from src.config import CONFIG_FILES, GAME_ROOT, ConfigLoadError, base_config, load_config
from src.harness import RecordingAudio
from src.hud import VIEW_WIDTH
from src.model.audio_levels import (
    SOUND_IDS,
    SOUND_JUMP_THUNDERCLAP,
    SOUND_SCAN_KLAXON,
    SOUND_SHIP_DESTRUCTION,
    SOUND_SHIP_IMPACT,
    SOUND_WEAPON_FIRE,
    AudioLevelError,
    AudioLevels,
)
from src.model.encounter import Encounter
from src.model.factions import (
    FACTION_BOBBER,
    FACTION_LOCALHOSTER,
    FACTION_PIRATE,
    FACTION_PLAYER,
)
from src.model.game_state import GameState
from src.model.npc_ship import NpcShip, roll_npc_stats
from src.model.weapons import Shot
from src.scenes.game_scene import GameScene
from src.scenes.spaceport_view import SpaceportView

# SDL quantises mixer volume (1/128 in practice); 1/64 is the honest tolerance.
VOLUME_TOLERANCE = 1 / 64

# Which buffer belongs to which sound id, and how long it is supposed to be.
# Parametrised from here so a new sound is picked up by every generation test
# automatically rather than by somebody remembering to add it to four lists.
BUFFER_DURATIONS = {
    "confirm_beep": _BEEP_MS,
    "weapon_fire": _WEAPON_FIRE_MS,
    "ship_impact": _SHIP_IMPACT_MS,
    "ship_destruction": _SHIP_DESTRUCTION_MS,
    "scan_klaxon": _SCAN_KLAXON_MS,
    "jump_spinup": _JUMP_SPINUP_MS,
    "jump_thunderclap": _THUNDERCLAP_MS,
}


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def audio_config(**tweaks) -> dict:
    """A fabricated config for the audio wiring tests. Never the shipped files.

    Same shape as Stage 11's fight config: a short gun range, a slow round, zero
    aim jitter, and spawn chances at zero, so the only ships in a system are the
    ones a test parked there. Every level in the ``audio`` section is left at the
    base config's value unless a test overrides it, because these tests assert
    *which* sound played, not how loud it was.
    """
    config = base_config()
    config["rng"]["seed"] = 20240712
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


def silent_config() -> dict:
    """A config that has muted every sound in the game, master included."""
    muted = {key: 0.0 for key in AudioLevels.keys()}
    return audio_config(audio=muted)


def hull(
    config: dict,
    faction: str,
    x: float,
    y: float,
    *,
    shields: "float | None" = None,
    armor: "float | None" = None,
    heading: float = 0.0,
    velocity: "tuple[float, float]" = (0.0, 0.0),
) -> NpcShip:
    """One hand-placed NPC hull, variance rolled out of it (Stage 11's pattern)."""
    ship = NpcShip(
        faction=faction,
        stats=roll_npc_stats(
            GameState(config or audio_config()).starting_stats, 1.0, 0.0, random.Random(7)
        ),
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
    weapon_range: float = 1000.0,
    ship_velocity: "tuple[float, float]" = (0.0, 0.0),
) -> Shot:
    """A muzzle flash handed straight to the gunfight, no AI and no gun involved."""
    return Shot(
        faction=faction,
        owner=owner,
        origin=origin,
        direction=direction,
        ship_velocity=ship_velocity,
        weapon_power=power,
        weapon_range=weapon_range,
    )


def park_ships_in_scene(scene: GameScene, *ships: NpcShip, system: str = "Alpha") -> Encounter:
    """Replace a scene's fleet with an exact set of hulls."""
    scene.encounter = Encounter(
        system=system,
        ships=list(ships),
        rules=scene.npc_rules,
        system_pixel_size=scene.game_state.system_pixel_size,
        relations=scene.relations,
    )
    return scene.encounter


def with_silent_guns(*ships: NpcShip) -> "tuple[NpcShip, ...]":
    """Give parked hulls guns that never fire, so every impact is the test's own.

    A test that hand-launches a round wants to assert ``impact_count == 1``. A
    parked pirate with a working gun also shoots the player on its own, which
    turns that assertion into a count of how busy the AI was rather than of what
    the scene did with the event it was handed. A fire rate of 0 is the model's
    own way of disabling a weapon (an infinite cooldown), not a fudge.
    """
    for ship in ships:
        ship.stats = dataclasses.replace(ship.stats, weapon_fire_rate=0.0)
    return ships


class _StackManager:
    """Enough of SceneManager for GameScene: config, audio, and a real stack."""

    def __init__(self, config: "dict | None" = None):
        self._config = config or audio_config()
        self.audio = RecordingAudio()
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
    """A real GameScene on a fake stack, with a recording audio system."""
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
    scene.handle_event(pygame.event.Event(pygame.KEYUP, key=key, scancode=0, mod=0))


def tap(scene: GameScene, key: int) -> None:
    """One real keypress: press, let a frame drain the rising edge, then release."""
    press(scene, key)
    scene.update()
    release(scene, key)


def buffer_for(sound_id: str, sample_rate: int = 44100) -> array.array:
    """The buffer a sound id generates, through the registry (not by hand)."""
    return BUFFER_GENERATORS[sound_id](sample_rate)


def _counting_generators(monkeypatch) -> "dict[str, int]":
    """Wrap every registered generator so the tests can count synthesis passes."""
    calls: "dict[str, int]" = {}
    for sound_id, factory in BUFFER_GENERATORS.items():
        def wrapper(sample_rate: int, _factory=factory, _id=sound_id) -> array.array:
            calls[_id] = calls.get(_id, 0) + 1
            return _factory(sample_rate)

        monkeypatch.setitem(buffers_module.BUFFER_GENERATORS, sound_id, wrapper)
    return calls


def _rms(samples, start: int = 0, stop: "int | None" = None) -> float:
    stop = len(samples) if stop is None else stop
    window = samples[start:stop]
    if not window:
        return 0.0
    return math.sqrt(sum(float(value) ** 2 for value in window) / len(window))


def _zero_crossings(samples, start: int, stop: int) -> int:
    """A cheap pitch proxy: how many times the wave crosses silence."""
    return sum(
        1
        for index in range(start + 1, stop)
        if (samples[index - 1] < 0) != (samples[index] < 0)
    )


def _lowpass(samples, window: int) -> "list[float]":
    """A box filter, so "this boom is deeper than that one" is measurable.

    Zero-crossing rate on the raw buffer measures the *hiss*, which is what makes
    a wreck a wreck; running the same count over a low-passed copy measures the
    rumble, which is the part whose pitch the generator configured. The default
    window is wide enough (about 3.6ms at 22kHz, a cut near 275Hz) that the
    recovered rate lands on the configured rumble frequency.
    """
    total = 0.0
    queue: "list[float]" = []
    filtered: "list[float]" = []
    for value in samples:
        total += float(value)
        queue.append(float(value))
        if len(queue) > window:
            total -= queue.pop(0)
        filtered.append(total / len(queue))
    return filtered


def _late_band_crossing_rate(samples, sample_rate: int, window: int = 80) -> float:
    """Zero crossings per second in the second half of a low-passed buffer.

    The second half, because that is where the crack has decayed and only the
    rumble is left; the first half of an explosion is broadband by definition.
    """
    filtered = _lowpass(samples, window)
    tail = filtered[len(filtered) // 2 :]
    crossings = sum(1 for i in range(1, len(tail)) if (tail[i - 1] < 0) != (tail[i] < 0))
    return crossings / (len(tail) / sample_rate)


def _mean_absolute_step(samples) -> float:
    """Mean sample-to-sample change: a high value is a bright, hissy sound.

    Deliberately crude. It is used to prove "the wreck is crunchier than the hit"
    is a property of the waveform and not of a configured volume, and a crude
    metric with a wide margin is better than a precise one nobody can re-derive.
    """
    steps = [abs(samples[i] - samples[i - 1]) for i in range(1, len(samples))]
    return sum(steps) / len(steps) if steps else 0.0


def _peak(samples) -> int:
    return max(abs(value) for value in samples)


def _head_tail_rms_ratio(samples, portion: float = 0.1) -> float:
    n = len(samples)
    edge = max(1, int(n * portion))
    return _rms(samples, n - edge, n) / max(1.0, _rms(samples, 0, edge))


def _play_every_effect(audio: AudioSystem) -> None:
    for verb in (
        "play_confirm",
        "play_weapon_fire",
        "play_impact",
        "play_destruction",
        "play_klaxon",
        "play_jump_spinup",
        "play_thunderclap",
    ):
        getattr(audio, verb)()


def run_a_noisy_session(scene: GameScene) -> None:
    """Fire, hit, scan, land, buy, launch, jump: every sound the game can make.

    Used by the "game runs fully with audio disabled" gate: the point is that the
    session completes, so the assertions live in the caller.
    """
    press(scene, pygame.K_SPACE)
    scene.update()
    release(scene, pygame.K_SPACE)

    pirate = hull(audio_config(), FACTION_PIRATE, 60.0, 0.0, shields=1.0, armor=1.0)
    with_silent_guns(pirate)
    park_ships_in_scene(scene, pirate)
    scene.gunfight.launch(
        shot(FACTION_PIRATE, pirate, (120.0, 0.0), (-1.0, 0.0), power=4.0)
    )
    advance(scene, 20)
    tap(scene, pygame.K_t)

    scene.game_state.set_position(0.0, 0.0)
    scene.game_state.fuel = 700.0
    tap(scene, pygame.K_l)
    port = scene._manager.stack[-1]
    if isinstance(port, SpaceportView):
        press_button(port, port._refuel_button)
        press_button(port, port._launch_button)

    scene.game_state.set_position(600.0, 0.0)
    scene.system_map.select("Bravo")
    tap(scene, pygame.K_j)
    advance(scene, 300)


def press_button(port: SpaceportView, button) -> None:
    """Fire the real pygame_gui button event the widget would post."""
    port.handle_event(pygame.event.Event(pygame_gui.UI_BUTTON_PRESSED, ui_element=button))


# ---------------------------------------------------------------------------
# AudioLevels: the policy half
# ---------------------------------------------------------------------------


def testlevelFor_withDefaultLevels_shouldBeTheMasterVolumeTimesTheEffectLevel():
    # GIVEN the shipped defaults (master 0.8, ship_impact 0.35),
    levels = AudioLevels()

    # THEN the mixer is asked for the product, not for either factor alone.
    assert levels.level_for(SOUND_SHIP_IMPACT) == pytest.approx(0.28)
    assert levels.level_for(SOUND_WEAPON_FIRE) == pytest.approx(0.24)


def testlevelFor_withMasterVolumeAtZero_shouldSilenceEverySound():
    # GIVEN a config that muted the world without touching a per-effect level,
    levels = AudioLevels.from_config({"master_volume": 0.0})

    # THEN every sound is silent, and the per-effect levels are still intact.
    assert all(levels.level_for(sound_id) == 0.0 for sound_id in SOUND_IDS)
    assert levels.ship_destruction == pytest.approx(AudioLevels().ship_destruction)


def testlevelFor_withAnUnknownSoundId_shouldRefuseRatherThanReportSilence():
    """Silence is a legal config value, which is exactly why a typo must not look like it."""
    levels = AudioLevels()

    with pytest.raises(AudioLevelError, match="no such sound"):
        levels.level_for("explosion")


def testfromConfig_withAnEmptySection_shouldMatchTheCodeDefaultsExactly():
    """A fabricated config with an empty ``audio`` section sounds like the shipped game."""
    # GIVEN,
    from_config = AudioLevels.from_config({})

    # THEN the code defaults are the shipped values, so "no audio section" and
    # "the config we ship" cannot drift into two different loudnesses.
    assert from_config.as_dict() == AudioLevels().as_dict()


def testfromConfig_withEveryKnownKey_shouldAdoptTheConfiguredLevels():
    # GIVEN,
    levels = AudioLevels.from_config(
        {
            "master_volume": 1.0,
            "confirm_beep": 0.0,
            "weapon_fire": 0.125,
            "ship_impact": 0.5,
            "ship_destruction": 0.75,
            "scan_klaxon": 1.0,
            "jump_spinup": 0.0,
            "jump_thunderclap": 0.25,
        }
    )

    # THEN each level is exactly what the config asked for.
    assert levels.level_for(SOUND_WEAPON_FIRE) == pytest.approx(0.125)
    assert levels.level_for(SOUND_SCAN_KLAXON) == pytest.approx(1.0)
    assert levels.level_for("confirm_beep") == 0.0
    assert levels.level_for("jump_spinup") == 0.0


def testfromConfig_withAnUnknownKey_shouldRejectItAndNameTheRealOnes():
    """``explosion`` is not a thing the game can play; saying so must name the choices."""
    # GIVEN,
    with pytest.raises(AudioLevelError, match="ship_impact") as exc_info:

        # THEN the failure lists the keys that do exist, rather than just refusing.
        AudioLevels.from_config({"explosion": 0.5})

    assert "unknown audio key" in str(exc_info.value)


@pytest.mark.parametrize(
    "bad_level",
    [
        -0.01,
        1.5,
        True,
        False,
        "loud",
        None,
        float("nan"),
        float("inf"),
        float("-inf"),
    ],
)
def testfromConfig_withANonNumericOrOutOfRangeLevel_shouldRejectIt(bad_level):
    """A level outside [0, 1] is a data error, not something to clamp and forget."""
    # GIVEN a config that only differs in one bad level,
    config = {sound_id: 0.5 for sound_id in SOUND_IDS}
    config["ship_impact"] = bad_level

    # THEN the whole section is refused.
    with pytest.raises(AudioLevelError):
        AudioLevels.from_config(config)


def testconstructor_withAnOutOfRangeLevel_shouldRejectTheDirectPathToo():
    """from_config is not the only door; a direct constructor must not smuggle 3.0 in."""
    with pytest.raises(AudioLevelError):
        AudioLevels(ship_destruction=3.0)


def testsilent_withEveryLevelZero_shouldBeTrue():
    assert AudioLevels.from_config({key: 0.0 for key in AudioLevels.keys()}).silent is True


def testsilent_withOneAudibleLevel_shouldBeFalse():
    assert AudioLevels.from_config({"ship_impact": 0.4}).silent is False


def testasDict_shouldRoundTripThroughFromConfig():
    # GIVEN a non-default set of levels,
    original = AudioLevels(master_volume=0.5, weapon_fire=0.9, scan_klaxon=0.1)

    # THEN the plain-dict form rebuilds an identical object (config dumps, debug
    # overlays, and a future settings screen all need this to be lossless).
    assert AudioLevels.from_config(original.as_dict()) == original


def testkeys_shouldBeTheSoundIdsPlusTheMasterVolume():
    """One vocabulary: the config keys are the sound ids, plus exactly one multiplier."""
    assert AudioLevels.keys() == ("master_volume", *SOUND_IDS)


# ---------------------------------------------------------------------------
# The config layer: a new section, validated the way every other section is
# ---------------------------------------------------------------------------


def testbaseConfig_shouldShipTheAudioSectionTheLoaderRequires():
    assert set(base_config()["audio"]) == set(AudioLevels.keys())


@pytest.mark.parametrize("name", CONFIG_FILES)
def testshippedConfig_shouldCarryEveryAudioKeyWithUsableLevels(name: str):
    """Every shipped file carries the whole section, and every level is playable."""
    # GIVEN,
    configs = load_config(GAME_ROOT)

    # THEN the keys are exactly the sound ids plus the master, and the levels
    # build the object the runtime builds.
    section = configs[name]["audio"]
    assert set(section) == set(AudioLevels.keys())
    levels = AudioLevels.from_config(section)
    assert 0.0 < levels.level_for(SOUND_SHIP_IMPACT) <= 1.0
    assert 0.0 < levels.level_for(SOUND_SHIP_DESTRUCTION) <= 1.0


def testshippedConfig_audioLevelsShouldNotBeDifficultyTuned():
    """Difficulty changes the galaxy, not the mixer.

    This is a pinned decision rather than an accident: three files whose audio
    sections differ would mean a hard-mode player hears different explosions,
    which is not a difficulty the spec asked for.
    """
    configs = load_config(GAME_ROOT)
    sections = [configs[name]["audio"] for name in CONFIG_FILES]
    assert sections[0] == sections[1] == sections[2]


def testloadConfig_withNoAudioSection_shouldFailAsAMissingSection(config_factory):
    with pytest.raises(ConfigLoadError, match="audio"):
        load_config(config_factory(config_overrides={"audio": None}))


def testloadConfig_withAnUnknownAudioKey_shouldFailAsAnUnknownKey(config_factory):
    with pytest.raises(ConfigLoadError, match="audio"):
        load_config(config_factory(overrides={"audio.explosion": 0.5}))


def testloadConfig_withAnAudioLevelAboveOne_shouldFail(config_factory):
    with pytest.raises(ConfigLoadError, match="audio"):
        load_config(config_factory(overrides={"audio.ship_impact": 1.5}))


def testloadConfig_withABooleanAudioLevel_shouldFailRatherThanBecomingFullScale(
    config_factory,
):
    """pydantic would happily turn ``true`` into 1.0; the loader refuses instead."""
    with pytest.raises(ConfigLoadError, match="audio"):
        load_config(config_factory(overrides={"audio.weapon_fire": True}))


def testloadConfig_withEverythingMuted_shouldLoadBecauseSilenceIsLegal(config_factory):
    loaded = load_config(
        config_factory(overrides={f"audio.{key}": 0.0 for key in AudioLevels.keys()})
    )
    assert AudioLevels.from_config(loaded["config_medium.json"]["audio"]).silent is True


# ---------------------------------------------------------------------------
# Buffer generation: the spec's "generated sound effects" gate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("sound_id", sorted(BUFFER_DURATIONS))
def testgeneratedBuffer_shouldBeInt16SafeNonSilentAndByteIdenticalAcrossRuns(sound_id: str):
    """Every effect: signed 16-bit, audible, and reproducible from a fixed seed.

    Determinism is what makes a sound testable at all: a buffer that changed
    between runs could not be pinned by an assertion, and would mean the game
    sounds slightly different every launch for no reason anybody chose.
    """
    # GIVEN the same generator called twice at the same rate,
    first = buffer_for(sound_id, sample_rate=8000)
    second = buffer_for(sound_id, sample_rate=8000)

    # THEN the buffers are identical samples...
    assert list(first) == list(second)
    # ...inside the signed 16-bit range a mixer consumes...
    assert first.typecode == "h"
    assert all(-32768 <= value <= 32767 for value in first)
    # ...and not an accident of silence.
    assert _peak(first) > 1000, f"{sound_id} generated nothing"


@pytest.mark.parametrize("sound_id", sorted(BUFFER_DURATIONS))
def testgeneratedBuffer_shouldLastTheConfiguredNumberOfMilliseconds(sound_id: str):
    """Sample count = rate x duration, at two rates, so timing is not a coincidence."""
    for sample_rate in (8000, 44100):
        buffer = buffer_for(sound_id, sample_rate=sample_rate)
        expected = sample_rate * BUFFER_DURATIONS[sound_id] / 1000
        assert len(buffer) == pytest.approx(expected, rel=0.01), (
            f"{sound_id} at {sample_rate}Hz is {len(buffer)} samples, "
            f"expected about {expected:.0f}"
        )


@pytest.mark.parametrize("sound_id", sorted(BUFFER_DURATIONS))
def testgeneratedBuffer_shouldPeakAtTheReferenceLevelSoLevelsMeanTheSameThingForEachSound(
    sound_id: str,
):
    """Peak normalisation is the contract that makes ``weapon_fire: 0.4`` mean 0.4.

    Without it, each generator's internal mix would set its own loudness and the
    config would be trimming an unknown baseline — the "volumes from config"
    requirement would be decorative.
    """
    buffer = buffer_for(sound_id, sample_rate=22050)

    assert _peak(buffer) == pytest.approx(_REFERENCE_PEAK, rel=0.02)


@pytest.mark.parametrize("sound_id", sorted(BUFFER_DURATIONS))
def testgeneratedBuffer_shouldStartQuietlySoNoEffectPops(sound_id: str):
    """A full-amplitude first sample is a click, and every buffer starts ramped."""
    buffer = buffer_for(sound_id, sample_rate=44100)

    assert abs(buffer[0]) < _peak(buffer) * 0.01, f"{sound_id} starts with a discontinuity"


def testnormalize_withAMixPeakingAboveFullScale_shouldScaleItDownRatherThanClipIt():
    """The difference between a loud sound and a distorted one, in three samples."""
    # GIVEN a mix that would clip on its own,
    scaled = _normalize([1.4, -2.0, 0.1])

    # THEN the loudest sample is at the reference peak and nothing is flattened:
    # a clipped buffer would land exactly on the int16 ceiling at both extremes.
    assert _peak(scaled) == pytest.approx(_REFERENCE_PEAK, rel=0.001)
    assert len(scaled) == 3


def testnormalize_withSilence_shouldStaySilentRatherThanDivideByZero():
    assert list(_normalize([0.0, 0.0, 0.0])) == [0, 0, 0]


def testweaponFire_shouldFallInPitchAndDecayToSilence():
    """A report, not a siren: the tone sweeps down and the whole thing dies away."""
    buffer = _generate_weapon_fire(44100)
    window = len(buffer) // 5

    assert _zero_crossings(buffer, 0, window) > _zero_crossings(
        buffer, len(buffer) - window, len(buffer)
    ), "a gunshot falls in pitch; a rising tone is an engine"
    assert _rms(buffer, len(buffer) - window, len(buffer)) < _rms(
        buffer, 0, window
    ) * 0.05, "the report must have decayed to near-nothing by the end"


def testscanKlaxon_shouldAlternateTwoTonesInRampedPulses():
    """A klaxon is two pitches and a shape; a single held tone is a test signal."""
    buffer = _generate_scan_klaxon(44100, pulses=4)
    segment = len(buffer) // 4

    def pitch(pulse: int) -> int:
        return _zero_crossings(buffer, pulse * segment + 100, (pulse + 1) * segment - 100)

    low_first, high_first, low_second, high_second = (pitch(n) for n in range(4))

    # Each pair of segments alternates, and the pattern repeats: low-high-low-high.
    assert high_first > low_first * 1.2, f"segment 1 should be higher: {low_first} vs {high_first}"
    assert high_second > low_second * 1.2, f"segment 3 should be higher: {low_second} vs {high_second}"
    assert low_second == pytest.approx(low_first, rel=0.15), "the low tone should repeat"
    assert high_second == pytest.approx(high_first, rel=0.15), "the high tone should repeat"

    edges = [pulse * segment for pulse in range(1, 4)]
    assert all(
        _rms(buffer, edge - 60, edge + 60) < _rms(buffer, 0, segment) * 0.35
        for edge in edges
    ), "each pulse must ramp up and down, or every frequency change is a click"


def testshipDestruction_shouldBeBiggerThanAShipImpactInMoreThanLoudness():
    """A wreck must be told from a hit with the eyes shut, so it cannot only be louder.

    Three independent measures, all on the waveform (both effects are peak
    normalised, so none of them can be "the config turned it up"):
    length, low-frequency tail (the rumble of a hull coming apart), and
    brightness (the debris hiss).
    """
    impact = _generate_ship_impact(22050)
    wreck = _generate_ship_destruction(22050)

    assert len(wreck) > len(impact) * 2, "the wreck should run far longer than a hit"
    assert _head_tail_rms_ratio(wreck) > _head_tail_rms_ratio(impact) * 2, (
        "the wreck keeps a rumble tail; a hit is over and gone"
    )
    assert _mean_absolute_step(wreck) / _peak(wreck) > _mean_absolute_step(impact) / _peak(
        impact
    ) * 1.2, "the wreck's debris hiss should make it the brighter of the two"


def testtheThreeExplosions_shouldShareAGeneratorButNotASound():
    """Impact, wreck, and the hyperspace thunderclap come from one generator on purpose.

    Sharing a generator is the DRY move; sharing a *sound* would be a bug. Each of
    the three is separable on a measured axis, which is the honest way to pin
    "these are three different effects":

    * the wreck rumbles at its configured ~38Hz and hisses (debris) far harder
      than either of the others,
    * the hit rumbles about 2.5x higher and is over in a third of the time,
    * the thunderclap carries the most energy into its tail (an arrival boom keeps
      rolling, a hull does not).
    """
    thunder = buffer_for(SOUND_JUMP_THUNDERCLAP, sample_rate=22050)
    impact = _generate_ship_impact(22050)
    wreck = _generate_ship_destruction(22050)

    brightness = lambda samples: _mean_absolute_step(samples) / _peak(samples)

    assert list(impact) != list(wreck) != list(thunder) != list(impact)
    assert brightness(wreck) > brightness(impact) * 3, (
        "the wreck's debris hiss is what tells it apart from a hit"
    )
    assert _late_band_crossing_rate(impact, 22050) > _late_band_crossing_rate(wreck, 22050) * 1.5, (
        "a hit cracks higher than a hull coming apart"
    )
    assert _head_tail_rms_ratio(thunder) > _head_tail_rms_ratio(impact) * 2, (
        "the arrival boom must outlast a combat hit"
    )


def testexplosion_withASecondCrack_shouldShowADelayedEnergyBump():
    """The wreck's "structure, then fuel" double hit is an observable bump."""
    # GIVEN the same explosion with and without the delayed second crack,
    with_bump = _generate_explosion(
        22050, duration_ms=900, crack_decay=3.4, rumble_freq=38.0, second_crack_at=0.4, seed=5
    )
    without_bump = _generate_explosion(
        22050, duration_ms=900, crack_decay=3.4, rumble_freq=38.0, seed=5
    )

    # THEN energy jumps around the 40% mark for the doubled one only.
    def window(samples, centre_fraction):
        centre = int(len(samples) * centre_fraction)
        return _rms(samples, centre - 300, centre + 300)

    def flank(samples, centre_fraction):
        centre = int(len(samples) * centre_fraction)
        return _rms(samples, centre + 900, centre + 1500)

    assert window(with_bump, 0.4) > flank(with_bump, 0.4), "the second crack never arrived"
    assert window(without_bump, 0.4) < flank(without_bump, 0.4) * 1.5, (
        "the control explosion should only be decaying"
    )


def testexplosion_withDifferentSeeds_shouldNotBeTheSameBuffer():
    """The per-effect seeds are what keep three booms from being one boom."""
    first = _generate_explosion(8000, duration_ms=200, crack_decay=8.0, rumble_freq=80.0, seed=1)
    second = _generate_explosion(8000, duration_ms=200, crack_decay=8.0, rumble_freq=80.0, seed=2)

    assert list(first) != list(second)


# ---------------------------------------------------------------------------
# The mixer layer: fail-soft, lazy, and level-accurate
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "verb,sound_id",
    [
        ("play_confirm", "confirm_beep"),
        ("play_weapon_fire", SOUND_WEAPON_FIRE),
        ("play_impact", SOUND_SHIP_IMPACT),
        ("play_destruction", SOUND_SHIP_DESTRUCTION),
        ("play_klaxon", SOUND_SCAN_KLAXON),
        ("play_jump_spinup", "jump_spinup"),
        ("play_thunderclap", SOUND_JUMP_THUNDERCLAP),
    ],
)
def testaudioSystem_shouldLoadEachSoundAtTheVolumeItsConfigAskedFor(verb: str, sound_id: str):
    """Levels are mixer state: the volume on the Sound *is* the configured level."""
    # GIVEN a mixer (the dummy driver really does initialise) and known levels,
    levels = AudioLevels(master_volume=1.0, **{sound_id: 0.5})
    audio = AudioSystem(levels)

    # THEN playing it applies 0.5, whatever the effect's waveform peaks at.
    getattr(audio, verb)()
    assert audio.loaded_volumes()[sound_id] == pytest.approx(0.5, abs=VOLUME_TOLERANCE)


def testaudioSystem_withAMixerUp_shouldReserveEnoughVoicesForAVolley():
    """SDL's default of 8 voices drops sounds; four ships plus the player is a volley."""
    audio = AudioSystem()

    if audio.available:
        assert pygame.mixer.get_num_channels() >= MIXER_VOICE_COUNT


def testaudioSystem_whenMixerInitRefuses_shouldReportUnavailableAndStaySilent(monkeypatch):
    """The spec's "never crash if the mixer is unavailable", taken literally."""

    def _refusing_init(*args, **kwargs):
        raise RuntimeError("no audio device, no biscuit")

    # GIVEN,
    monkeypatch.setattr(pygame.mixer, "init", _refusing_init)
    audio = AudioSystem()

    # THEN the game keeps going and makes nothing.
    assert audio.available is False
    _play_every_effect(audio)
    assert audio.loaded_volumes() == {}


def testaudioSystem_whenTheMixerIsNotSixteenBit_shouldRefuseToBeFedTheWrongBuffers(monkeypatch):
    """A format we cannot generate must not be guessed at.

    ``Sound(buffer=...)`` does no conversion: 16-bit samples handed to an 8-bit
    mixer would play as noise, and mono handed to a stereo mixer plays at double
    pitch and half length. The honest answer is "no audio".
    """
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: (22050, -8, 1))
    audio = AudioSystem()

    assert audio.available is False
    _play_every_effect(audio)
    assert audio.loaded_volumes() == {}


def testmixerFormat_whenTheMixerWantsStereo_shouldSaySoRatherThanLieAboutMono(monkeypatch):
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: (48000, -16, 2))

    assert _mixer_format() == (48000, 2)


def testmixerFormat_withNoMixerAtAll_shouldReportNothing(monkeypatch):
    monkeypatch.setattr(pygame.mixer, "get_init", lambda: None)

    assert _mixer_format() is None


def testaudioBuffers_shouldImportWithoutTouchingPygame():
    """The synthesis layer's whole point: no pygame, so anything can use it.

    ``scripts/render_audio_buffers.py`` must run in a container with no audio
    device, and the buffer-generation tests must not depend on a mixer coming up.
    A boundary nobody enforces is a boundary that moves, so this imports the
    module in a subprocess and asks whether pygame ended up in ``sys.modules``.
    """
    probe = (
        "import sys, src.audio_buffers as b; "
        "print('pygame' in sys.modules, len(b.BUFFER_GENERATORS))"
    )
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=project_root,
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode == 0, result.stderr
    imported_pygame, generator_count = result.stdout.split()
    assert imported_pygame == "False", "src.audio_buffers pulled pygame into the synthesis layer"
    assert int(generator_count) == len(BUFFER_GENERATORS)


def testmatchMixer_withMono_shouldHandBackTheSameBufferUnchanged():
    buffer = array.array("h", [1, -2, 3])

    assert _match_mixer(buffer, 1) is buffer


def testmatchMixer_withAStereoMixer_shouldDuplicateEverySample():
    """The rare hardware path: a mono buffer read as stereo would be a squeak."""
    stereo = _match_mixer(array.array("h", [1, -2, 3]), 2)

    assert list(stereo) == [1, 1, -2, -2, 3, 3]


def testplay_whenTheSoundConstructorExplodes_shouldSwallowAndCacheNothing(monkeypatch):
    """A half-built sound must not be remembered as a failure forever."""

    def _exploding_sound(*args, **kwargs):
        raise RuntimeError("mixer exploded mid-generation")

    # GIVEN,
    monkeypatch.setattr(pygame.mixer, "Sound", _exploding_sound)
    audio = AudioSystem()

    # THEN nothing is cached, nothing is raised, and a later attempt tries again.
    _play_every_effect(audio)
    _play_every_effect(audio)
    assert audio.loaded_volumes() == {}


def testplay_withAnUnavailableMixer_shouldNeverEvenGenerateABuffer(monkeypatch):
    """Buffer synthesis is pure-Python maths; a dead mixer must not pay for it."""
    calls = _counting_generators(monkeypatch)

    monkeypatch.setattr(pygame.mixer, "init", lambda *a, **k: (_ for _ in ()).throw(RuntimeError()))
    audio = AudioSystem()
    _play_every_effect(audio)

    assert calls == {}


def testplay_withEveryLevelMuted_shouldNotGenerateABufferAtAll(monkeypatch):
    """A silent config costs nothing: no buffer, no voice, no maths."""
    calls = _counting_generators(monkeypatch)
    audio = AudioSystem(AudioLevels.from_config({key: 0.0 for key in AudioLevels.keys()}))

    _play_every_effect(audio)

    assert audio.available is True, "the mixer is fine; the config asked for silence"
    assert calls == {}
    assert audio.loaded_volumes() == {}


def testapplyLevels_withSoundsAlreadyLoaded_shouldRelevelThemWithoutRegenerating(monkeypatch):
    """The whole point of keeping the level out of the waveform.

    Re-reading a config (a second game, a future settings screen) costs one
    ``set_volume`` per loaded sound, not another synthesis pass.
    """
    calls = _counting_generators(monkeypatch)
    audio = AudioSystem(AudioLevels(master_volume=1.0, ship_impact=0.5))
    audio.play_impact()
    assert calls == {SOUND_SHIP_IMPACT: 1}

    audio.apply_levels(AudioLevels(master_volume=1.0, ship_impact=0.1))
    audio.play_impact()

    assert calls == {SOUND_SHIP_IMPACT: 1}, "the buffer was regenerated for a volume change"
    assert audio.loaded_volumes()[SOUND_SHIP_IMPACT] == pytest.approx(0.1, abs=VOLUME_TOLERANCE)


def testapplyLevels_withAPlainConfigDict_shouldRefuseAndSayHowToDoItRight():
    """``config['audio']`` is the obvious mistake; the error names the fix."""
    audio = AudioSystem()

    with pytest.raises(TypeError, match="from_config"):
        audio.apply_levels({"master_volume": 0.5})


def testplay_withAnUnknownSoundId_shouldStaySilentAndNeverRaise():
    """A typo'd id is a programming error, so it is reported, not turned into silence-by-accident."""
    audio = AudioSystem()

    audio.play("railgun")

    assert audio.loaded_volumes() == {}


def testaudioDebugFlag_shouldPrintTheSwallowedFailureToStderr(monkeypatch, capsys):
    """Fail-soft must not mean undebuggable.

    The default is silent (a broken mixer should not spam a terminal), but with
    the documented environment variable set, every swallowed audio failure is
    visible, which is the only way to tell "the mixer is broken" from "the config
    is mute".
    """
    monkeypatch.setenv(AUDIO_DEBUG_ENV, "1")

    def _exploding_sound(*args, **kwargs):
        raise RuntimeError("mixer exploded")

    monkeypatch.setattr(pygame.mixer, "Sound", _exploding_sound)
    AudioSystem().play_impact()

    captured = capsys.readouterr()
    assert "[audio]" in captured.err
    assert "mixer exploded" in captured.err


def testwriteWav_shouldWritePcmAReaderCanCount(tmp_path):
    """Tooling for human ears (scripts/render_audio_buffers.py), stdlib only."""
    samples = array.array("h", [0, 1000, -1000, 32767, -32768])
    path = os.path.join(str(tmp_path), "effect.wav")

    write_wav(path, samples, sample_rate=8000)

    with wave.open(path, "rb") as handle:
        assert handle.getnchannels() == 1
        assert handle.getsampwidth() == 2
        assert handle.getframerate() == 8000
        assert handle.getnframes() == len(samples)
        assert handle.readframes(len(samples)) == samples.tobytes()


# ---------------------------------------------------------------------------
# Scene wiring: "event X plays sound Y"
# ---------------------------------------------------------------------------


def testscene_firingTheGunsShouldPlayExactlyOneReportPerRound():
    """GIVEN a ready gun, WHEN the player fires once, THEN one report and no more."""
    scene = game_scene(audio_config())

    tap(scene, pygame.K_SPACE)

    assert len(scene.gunfight) == 1
    assert scene._manager.audio.weapon_fire_count == 1


def testscene_aCoolingGunShouldMakeNoNoiseUntilItIsReadyAgain():
    """The cooldown is silent: no shot means no report, on the frame and after it."""
    scene = game_scene(audio_config())
    tap(scene, pygame.K_SPACE)

    press(scene, pygame.K_SPACE)
    advance(scene, 10)

    assert len(scene.gunfight) == 1, "the cooldown should not have produced a second round"
    assert scene._manager.audio.weapon_fire_count == 1


def testscene_aRoundFiredByAnOffscreenShipShouldStillBeHeard():
    """Spec: projectile noises when *any* ship fires, even ships currently offscreen.

    The ship is parked beyond half the tactical view's width, so it is not drawn,
    and it is still inside its own gun band: the player hears a fight they cannot
    see, which is the information the spec is after.
    """
    config = audio_config(
        player_ship={"weapon_range": 900},
        npc={"engage_range_fraction": 0.9},
    )
    scene = game_scene(config)
    scene.game_state.set_position(0.0, 0.0)
    pirate = hull(config, FACTION_PIRATE, 780.0, 0.0)
    park_ships_in_scene(scene, pirate)

    assert abs(pirate.position[0] - scene.game_state.position[0]) > VIEW_WIDTH / 2.0, (
        "the test is not testing offscreen fire if the ship is on screen"
    )

    # Frame by frame, because "offscreen" has to be true at the moment the report
    # is played, not merely at the moment the ship was parked: the AI closes in,
    # and a sound played after it drifted into view proves nothing.
    audio = scene._manager.audio
    distance_at_first_report = None
    for _ in range(400):
        scene.update()
        if audio.weapon_fire_count > 0:
            distance_at_first_report = math.hypot(
                pirate.position[0] - scene.game_state.position[0],
                pirate.position[1] - scene.game_state.position[1],
            )
            break

    assert distance_at_first_report is not None, (
        "an offscreen pirate never fired at all"
    )
    assert distance_at_first_report > VIEW_WIDTH / 2.0, (
        f"the report played at {distance_at_first_report:.0f}px, which is on screen"
    )


def testscene_aRoundLandingOnAHullShouldPlayTheSmallExplosionOnly():
    """GIVEN a hit that does not finish the hull, WHEN it lands, THEN one impact, no boom."""
    scene = game_scene(audio_config())
    pirate, = with_silent_guns(hull(audio_config(), FACTION_PIRATE, 60.0, 0.0))
    park_ships_in_scene(scene, pirate)
    scene.gunfight.launch(
        shot(FACTION_PLAYER, scene.game_state, (-120.0, 0.0), (1.0, 0.0), power=4.0)
    )

    advance(scene, 20)

    assert pirate.shields < 50.0, "the round must actually have landed"
    assert pirate.destroyed is False
    assert scene._manager.audio.impact_count == 1
    assert scene._manager.audio.destruction_count == 0


def testscene_theBlowThatFinishesAHullShouldPlayTheBigBoomExactlyOnce():
    """One event, one sound: the wreck does not also get a small-explosion stacked on it."""
    scene = game_scene(audio_config())
    pirate, = with_silent_guns(
        hull(audio_config(), FACTION_PIRATE, 60.0, 0.0, shields=1.0, armor=1.0)
    )
    park_ships_in_scene(scene, pirate)
    scene.gunfight.launch(
        shot(FACTION_PLAYER, scene.game_state, (-120.0, 0.0), (1.0, 0.0), power=400.0)
    )

    advance(scene, 20)

    assert pirate.destroyed is True
    assert scene._manager.audio.destruction_count == 1
    assert scene._manager.audio.impact_count == 0


def testscene_thePlayerBeingHitShouldSoundLikeAnyoneElse():
    """Spec: "when any ship is hit" includes the player's, and it should be audible."""
    scene = game_scene(audio_config())
    pirate, = with_silent_guns(hull(audio_config(), FACTION_PIRATE, 200.0, 0.0))
    park_ships_in_scene(scene, pirate)
    scene.gunfight.launch(
        shot(FACTION_PIRATE, pirate, (120.0, 0.0), (-1.0, 0.0), power=4.0)
    )

    advance(scene, 20)

    assert scene.game_state.stats.shields < scene.game_state.starting_stats.max_shields
    assert scene._manager.audio.impact_count == 1


def testscene_thePlayersOwnDestructionShouldBeOneBoomNotTwo():
    """The impact that killed the player already played the boom; the death notice must not.

    Two identical buffers on the same frame is not "drama", it is one sound at a
    higher amplitude, and the scene has two places that could have played it.
    """
    scene = game_scene(audio_config())
    pirate, = with_silent_guns(hull(audio_config(), FACTION_PIRATE, 40.0, 0.0))
    park_ships_in_scene(scene, pirate)
    scene.gunfight.launch(
        shot(FACTION_PIRATE, pirate, (0.0, 0.0), (1.0, 0.0), power=10_000.0)
    )

    advance(scene, 3)

    assert scene.game_state.destroyed is True
    assert scene.pending_game_over is True
    assert scene._manager.audio.destruction_count == 1


def testscene_anNpcKillingAnotherNpcShouldSoundLoudlyAndPayNothing():
    """A war-side kill is audible to the player and worth nothing to the player.

    "any ship destruction" is not "any ship the player destroyed": the boom is
    information about the battle, the bounty is not (Stage 11's rule, pinned here
    from the audio side).
    """
    scene = game_scene(audio_config())
    pirate, victim = with_silent_guns(
        hull(audio_config(), FACTION_PIRATE, 120.0, 0.0),
        hull(audio_config(), FACTION_LOCALHOSTER, 260.0, 0.0, shields=1.0, armor=1.0),
    )
    park_ships_in_scene(scene, pirate, victim)
    credits_before = scene.game_state.credits

    scene.gunfight.launch(
        shot(FACTION_PIRATE, pirate, (120.0, 0.0), (1.0, 0.0), power=400.0)
    )
    advance(scene, 30)

    assert victim.destroyed is True
    assert scene._manager.audio.destruction_count == 1
    assert scene._manager.audio.impact_count == 0
    assert scene.game_state.credits == credits_before, "an NPC kill must not pay the player"


def testscene_nothingShouldSoundDuringHyperspace():
    """A jump is silent except for its own two sounds: the fleet is left behind."""
    config = audio_config()
    scene = game_scene(config)
    scene.game_state.set_position(600.0, 0.0)
    pirate = hull(config, FACTION_PIRATE, 700.0, 0.0)
    park_ships_in_scene(scene, pirate)
    audio = scene._manager.audio
    spinup_before, gunfire_before = audio.spinup_count, audio.weapon_fire_count

    scene.system_map.select("Bravo")
    tap(scene, pygame.K_j)

    advance(scene, 60)

    assert scene.jumps.is_active, "the jump should still be burning"
    assert audio.spinup_count == spinup_before + 1, "the spool-up belongs to the burn"
    assert audio.thunderclap_count == 0, "the boom belongs to the arrival"
    assert audio.weapon_fire_count == gunfire_before, "hyperspace has no gunfight"


def testscene_jumpShouldStillPlayItsSpoolUpAndExactlyOneBoom():
    """Stage 8's frame-exact jump audio survives the Stage 12 rewrite."""
    scene = game_scene(audio_config())
    scene.game_state.set_position(600.0, 0.0)
    scene.system_map.select("Bravo")

    tap(scene, pygame.K_j)
    advance(scene, 300)

    assert scene.system_map.current_system == "Bravo"
    assert scene._manager.audio.spinup_count == 1
    assert scene._manager.audio.thunderclap_count == 1
    assert scene._manager.audio.play_order[:2] == ["jump_spinup", "jump_thunderclap"], (
        "the spool-up precedes the boom, or the drama deflates"
    )


def testscene_scanningAHostileContactShouldSoundTheKlaxon():
    """GIVEN a pirate (hostile always), WHEN T locks the readout on it, THEN the alarm."""
    scene = game_scene(audio_config())
    park_ships_in_scene(scene, hull(audio_config(), FACTION_PIRATE, 200.0, 0.0))

    tap(scene, pygame.K_t)

    assert scene.scanner.displayed is not None
    assert scene._manager.audio.klaxon_count == 1


def testscene_scanningANeutralContactShouldStayQuiet():
    """A Localhoster that has not been shot at is not a threat, and says so."""
    scene = game_scene(audio_config())
    park_ships_in_scene(scene, hull(audio_config(), FACTION_LOCALHOSTER, 200.0, 0.0))

    tap(scene, pygame.K_t)

    assert scene.scanner.displayed is not None
    assert scene._manager.audio.klaxon_count == 0


def testscene_scanningAnEmptySystemShouldStayQuiet():
    """No contact, no alarm: the readout says "No target" and the mixer agrees."""
    scene = game_scene(audio_config())
    park_ships_in_scene(scene)

    tap(scene, pygame.K_t)

    assert scene.scanner.displayed is None
    assert scene._manager.audio.klaxon_count == 0


def testscene_theKlaxonShouldFollowAHostilityThePlayerEarned():
    """The alarm answers the grudge question, not the faction-colour question.

    A Bobber is neutral until the player shoots it; after that it is red on the
    readout *and* the klaxon sounds for it, which is what makes the two agree
    instead of being two rules.
    """
    config = audio_config()
    scene = game_scene(config)
    bobber = hull(config, FACTION_BOBBER, 200.0, 0.0)
    park_ships_in_scene(scene, bobber)

    tap(scene, pygame.K_t)
    assert scene._manager.audio.klaxon_count == 0, "neutral is neutral"

    scene.game_state.heading_degrees = 0.0
    tap(scene, pygame.K_SPACE)
    advance(scene, 30)
    assert scene.relations.is_hostile_to_player(FACTION_BOBBER) is True

    tap(scene, pygame.K_t)

    assert scene.scanner.displayed is bobber
    assert scene._manager.audio.klaxon_count == 1, "a hostile earned the hard way still alarms"


def testscene_aHostileBecomingNearestWithoutAKeyPressShouldNotSound():
    """The klaxon is tied to pressing T, not to the readout's contents changing."""
    config = audio_config()
    scene = game_scene(config)
    neutral = hull(config, FACTION_LOCALHOSTER, 100.0, 0.0)
    hostile = hull(config, FACTION_PIRATE, 400.0, 0.0)
    park_ships_in_scene(scene, neutral, hostile)
    scene.scanner.scan(scene.encounter.ships, scene.game_state.position)

    # The lock is sticky: the pirate being nearer (once it drifts, or once the
    # neutral is destroyed) changes what is displayed without a keypress.
    scene.scanner.scan(scene.encounter.ships, (10_000.0, 0.0))
    advance(scene, 5)

    assert scene.scanner.displayed is not None
    assert scene._manager.audio.klaxon_count == 0


def testscene_theKlaxonShouldSoundOnEveryPressThatFindsAHostile():
    """Two presses, two alarms: the player asked twice, and the answer is still bad."""
    scene = game_scene(audio_config())
    park_ships_in_scene(scene, hull(audio_config(), FACTION_PIRATE, 200.0, 0.0))

    tap(scene, pygame.K_t)
    tap(scene, pygame.K_t)

    assert scene._manager.audio.klaxon_count == 2


def testscene_aDestroyedContactRevertingTheReadoutShouldBeSilent():
    """Stage 11's auto-revert to "No target" is a display event, not an alarm event."""
    scene = game_scene(audio_config())
    pirate = hull(audio_config(), FACTION_PIRATE, 200.0, 0.0, shields=1.0, armor=1.0)
    park_ships_in_scene(scene, pirate)
    tap(scene, pygame.K_t)
    assert scene._manager.audio.klaxon_count == 1

    scene.game_state.heading_degrees = 0.0
    tap(scene, pygame.K_SPACE)
    advance(scene, 40)

    assert pirate.destroyed is True
    assert scene.scanner.displayed is None
    assert scene._manager.audio.klaxon_count == 1, "the revert played no extra alarm"


def testgameScene_shouldAdoptTheAudioLevelsFromItsOwnConfig():
    """The run's config is the authority on levels, handed over when the run starts."""
    config = audio_config(audio={"master_volume": 0.5, "ship_impact": 0.9})
    scene = game_scene(config)

    applied = scene._manager.audio.levels_applied
    assert len(applied) == 1, "a level handover per game, not per frame"
    assert applied[0].level_for(SOUND_SHIP_IMPACT) == pytest.approx(0.45)


def testgameScene_withAConfigMissingTheAudioSectionShouldAdoptTheDefaults():
    """A fabricated config that predates Stage 12 still gets the shipped levels."""
    config = audio_config()
    del config["audio"]
    scene = game_scene(config)

    assert scene._manager.audio.levels_applied[0].as_dict() == AudioLevels().as_dict()


def testgameScene_aSecondGameShouldRelevelTheMixer():
    """A new game is a new config: the mixer follows it rather than the first run."""
    first = _StackManager(audio_config(audio={"master_volume": 0.1}))
    GameScene(first)
    second = _StackManager(audio_config(audio={"master_volume": 1.0}))
    GameScene(second)

    assert first.audio.levels_applied[0].master_volume == pytest.approx(0.1)
    assert second.audio.levels_applied[0].master_volume == pytest.approx(1.0)


def testmapView_selectingASystemShouldConfirmWithTheBeep():
    """The spec's UI beep in the map view, pinned from the audio stage.

    Map selection is a world question the model answers (selected/toggled), and
    the beep follows the model's answer — which is why an ignored click (a
    distant system) is silent rather than polite.
    """
    scene = game_scene(audio_config())
    tap(scene, pygame.K_m)
    modal = scene._manager.top

    x, y = scene.system_map.layout.positions["Bravo"]
    modal.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(int(x), int(y)), button=1)
    )

    assert scene.system_map.selected_system == "Bravo"
    assert scene._manager.audio.confirm_count == 1


def testspaceportView_aCompletedTransactionShouldConfirmWithTheBeep():
    """The spec's UI beep in the spaceport view: success beeps, refusal does not."""
    scene = game_scene(audio_config())
    scene.game_state.set_position(0.0, 0.0)
    scene.game_state.fuel = 700.0
    tap(scene, pygame.K_l)
    port = scene._manager.top
    assert isinstance(port, SpaceportView)
    fuel_before = scene.game_state.fuel

    press_button(port, port._refuel_button)

    assert scene.game_state.fuel > fuel_before, "the refuel must actually have happened"
    assert scene._manager.audio.confirm_count == 1


def testspaceportView_aRefusalShouldNotBeep():
    """A beep that means "no" is a bug wearing a friendly face."""
    scene = game_scene(audio_config(new_game={"starting_credits": 0}))
    scene.game_state.set_position(0.0, 0.0)
    tap(scene, pygame.K_l)
    port = scene._manager.top
    credits_before = scene.game_state.credits

    press_button(port, port._refuel_button)

    assert scene.game_state.credits == credits_before
    assert scene._manager.audio.confirm_count == 0


# ---------------------------------------------------------------------------
# The gate: the game runs fully with audio disabled
# ---------------------------------------------------------------------------


def testfullSession_withTheMixerUnavailableShouldCompleteAndGenerateNothing(monkeypatch):
    """Every sound-triggering screen, with a mixer that refuses to start.

    This is the spec's "game runs fully with audio disabled" gate in one test:
    firing, getting hit, scanning, landing, buying fuel, and jumping all still
    happen, and the audio system never generated a single buffer on the way.
    """
    monkeypatch.setattr(pygame.mixer, "init", lambda *a, **k: None)
    monkeypatch.setattr(audio_module, "_mixer_format", lambda: None)

    scene = game_scene(audio_config())
    scene._manager.audio = AudioSystem()
    scene._apply_audio_levels(scene._manager.game_config())

    assert scene._manager.audio.available is False
    run_a_noisy_session(scene)

    assert scene._manager.audio.loaded_volumes() == {}
    assert scene.system_map.current_system == "Bravo", "the run itself went nowhere"
    assert scene.game_state.credits is not None


def testfullSession_withEverySoundMutedShouldStillRunAndSynthesizeNothing():
    """A mute-everything config is a legal config, and it should also be free."""
    scene = game_scene(silent_config())
    scene._manager.audio = AudioSystem(AudioLevels.from_config(silent_config()["audio"]))

    run_a_noisy_session(scene)

    assert scene.system_map.current_system == "Bravo"
    assert scene._manager.audio.loaded_volumes() == {}
    assert scene._manager.audio.available is True, "the mixer works; the config is mute"


def testfullSession_withTheRealAudioSystemAndEveryEffectPlayedShouldNotRaise():
    """The dummy driver really does take these buffers, so play them for real."""
    scene = game_scene(audio_config())
    scene._manager.audio = AudioSystem()
    scene._apply_audio_levels(scene._manager.game_config())

    run_a_noisy_session(scene)

    if scene._manager.audio.available:
        # Every effect the session asked for is loaded and at a sane level.
        volumes = scene._manager.audio.loaded_volumes()
        assert SOUND_SHIP_IMPACT in volumes
        assert all(0.0 < value <= 1.0 for value in volumes.values())
