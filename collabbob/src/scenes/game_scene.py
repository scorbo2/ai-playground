"""The single top-level scene for one play session: tactical view + HUD + world map.

Stage 6 originally modelled the HUD as a second scene pushed onto the stack
above the tactical view. ``SceneManager`` only routes ``handle_event()`` and
``update()`` to the *top* scene, so a passive, input-free overlay on top of the
stack silently swallowed every keystroke and froze the simulation — the whole
game became a screenshot. The HUD draws into a region the tactical view
deliberately never touches, so it is a component of this scene rather than a
scene of its own.

GameScene also owns the session's single :class:`GameState` and hands the same
object to both children, so the HUD can never render a phantom ship while the
simulation runs somewhere else. And it owns the world: the system graph and its
screen layout are generated **once** here, from config, and cached for the rest
of the run — the map modal is a window onto that state, never a source of it.

Modals that take over input are pushed onto this scene: the system map and the
spaceport are raised here (``M`` and ``L``), and the game-over screen arrives in
Stage 13. Only the top scene receives events, which is what pauses the
simulation underneath a modal.
"""

from __future__ import annotations

import random as _random_lib
import sys
from typing import TYPE_CHECKING, Tuple

import pygame

from src.effects import FlashOverlay
from src.fonts import game_font
from src.hud import VIEW_WIDTH, HudView
from src.input import Action
from src.map_systems.graph import GraphGenerationError, SystemGraphGenerator
from src.map_systems.layout import build_map_layout
from src.map_systems.system_map import SystemMapState
from src.main_loop import SCREEN_SIZE
from src.model.audio_levels import AudioLevels
from src.model.combat import CombatRules, Combatant, Gunfight, bounty_for_kill
from src.model.economy import PortVisit, generate_port_offers, port_rng
from src.model.encounter import Encounter, SpawnRules, encounter_rng, roll_encounter
from src.model.factions import PlayerRelations, combatant_color, is_npc_faction
from src.model.game_state import PLANET_WORLD_POSITION, GameState
from src.model.jump import (
    BLOCKED_EXACT_FUEL,
    EVENT_ARRIVED,
    EVENT_JUMP_ENDED,
    EVENT_TRANSITION_STARTED,
    JumpController,
    JumpParams,
)
from src.model.lore import LoreBook
from src.model.scan import ShipScanner
from src.model.weapons import Shot
from src.scene_manager import Scene
from src.scenes.map_view import MapView
from src.scenes.spaceport_view import SpaceportView
from src.scenes.tactical_view import TacticalView

if TYPE_CHECKING:
    from src.scene_manager import SceneManager

# "briefly overlay an 'insufficient fuel' message" — two seconds, no more.
JUMP_DENIED_MESSAGE_FRAMES = 120

# How long a bounty (or a kill-reward refusal) stays on the tactical display. The
# spec says "briefly"; three seconds matches the boundary warning and is long
# enough to read while still flying.
BOUNTY_MESSAGE_FRAMES = 180

# The banner shown the frame the hull comes apart. Stage 13 owns the end *screen*;
# this is only the tactical display saying something happened rather than the game
# appearing to shrug and carry on.
PLAYER_LOST_MESSAGE = "Ship lost with all hands!"


def _gameplay_rng(config: dict) -> "_random_lib.Random | None":
    """The session's gameplay RNG: starfields, jump arrival bearings, and soon NPCs.

    Seeded from ``rng.seed`` when one is set, so a seeded run reproduces its skies
    and its arrival points as well as its map. Deliberately a *separate* generator
    from the world-graph one: the topology must come out identical no matter how
    many frames of flight or how many jumps the player burns through first, so the
    two streams can never share a cursor. Same seed, two independent streams — the
    Stage 7 note about threading a single RNG through the whole game is still open.

    Returns None (GameState then makes an unseeded RNG of its own) when no seed is
    configured, which is how the game ships.
    """
    seed = config.get("rng", {}).get("seed")
    return None if seed is None else _random_lib.Random(seed)


def _session_seed(config: dict) -> int:
    """The base for every derived per-system stream: markets and fleets alike.

    With ``rng.seed`` set, every market board and every spawn roll in the run is
    reproducible from that seed plus the order of entries. With it unset - how the
    game ships - a random per-run nonce is drawn, which still gives the property
    that matters here: the world does not change under the player between the
    moment they enter a system and the moment they look at it.

    One seed, many streams: each consumer namespaces the key it derives
    (``port_rng`` for the job market, ``encounter_rng`` for the fleet), so
    sharing the seed cannot make the pirates in Bravo depend on the cargo rates
    in Bravo.
    """
    seed = config.get("rng", {}).get("seed")
    if seed is None:
        return _random_lib.randrange(1, 2**63)
    return int(seed)


class GameScene(Scene):
    """Owns the tactical view, the HUD and the world graph for one game."""

    def __init__(self, manager: "SceneManager") -> None:
        super().__init__()
        # The stack also hands us the manager in ``on_enter()``; holding onto the
        # constructor's reference keeps a directly-constructed GameScene (as many
        # unit tests do) able to open modals without a full stack round-trip.
        self._manager = manager
        config = manager.game_config()
        # A run's config carries the sound levels, so a run is exactly when the
        # mixer is told about them (see _apply_audio_levels).
        self._apply_audio_levels(config)
        # One ship state, shared by the view that simulates it and the HUD that
        # reports it. Created from the difficulty the player actually picked.
        self.game_state = GameState(config, rng=_gameplay_rng(config))
        self.tactical = TacticalView(manager, self.game_state)
        self.hud = HudView(manager, self.game_state)
        self.system_map = self._build_system_map(config)
        # Lore is world state too: one line per system, drawn once here so the
        # spaceport never re-rolls a system's history between visits.
        self.lore = self._build_lore_book(config, self.system_map.graph)
        # The job market of the system the player currently occupies. Owned here
        # (not in the modal) because entering a system is a world event: the board
        # is dealt on entry and survives launches, so "launch, then land again"
        # cannot re-roll the work on offer. It is replaced only when the player
        # enters a system again (see :meth:`_enter_system`).
        #
        # The same entry also deals the fleet. Both are per-entry, both derive
        # their RNG stream from this one session seed, and neither shares a
        # stream with the other (the suffixes in the two rng helpers keep them
        # apart).
        self.session_seed = _session_seed(config)
        self.npc_rules = self._build_spawn_rules(config)
        # Grudges outlive systems and visits: one relations object per game, so
        # a faction shot at in Alpha is still shooting in Zulu, and a new game
        # starts neutral because it builds a new GameScene.
        self.relations = PlayerRelations()
        # Stage 11's three pieces of fight state, all per-game and all cheap:
        # the combat tunables, the rounds currently in the *current* visit, and
        # whichever hull the HUD's nearest-ship readout is locked on.
        self.combat_rules = self._build_combat_rules(config)
        self.gunfight = Gunfight(self.combat_rules)
        self.scanner = ShipScanner()
        # Declared here so a reader of __init__ sees the two per-visit world
        # objects a GameScene always has; both are filled by _enter_system.
        self.port_visit: PortVisit
        self.encounter: Encounter
        self._enter_system(self.system_map.current_system)
        # Whether the spaceport modal is currently on the stack. Deliberately
        # separate from ``port_visit``, which now outlives the modal.
        self._port_modal_open = False
        # Whatever the system's fleet fired on the most recent frame. Replaced,
        # never appended to, so a scene that never drains it (every scene until
        # Stage 11) cannot grow it. Stage 11 turns these into projectiles.
        self.pending_shots: "list[Shot]" = []
        # The jump sequence is owned here because it is the only thing that
        # needs the ship *and* the world at the same time.
        self.jumps = JumpController(
            game_state=self.game_state,
            map_state=self.system_map,
            params=JumpParams.from_config(config["tactical"]),
        )
        # The flash covers the whole window, HUD included, so it is drawn by the
        # scene that draws last — a flash that politely skipped the right-hand
        # third would read as a rendering bug, not as drama. The shockwave does
        # start at the ship, though: the centre of the game view.
        self.screen_flash = FlashOverlay(
            pygame.Rect(0, 0, *SCREEN_SIZE),
            origin=(VIEW_WIDTH / 2.0, SCREEN_SIZE[1] / 2.0),
        )
        # Stage 13 seam: see _request_jump. Public so the flow tests can assert
        # on it without reaching into private state.
        self.pending_game_over = False

    def _apply_audio_levels(self, config: dict) -> None:
        """Tell the mixer how loud this run's effects are.

        The levels are per-run config data (all three shipped files carry them),
        but the mixer exists before a difficulty is chosen — the title screen and
        the difficulty dialog both beep — so the handover happens here, at the one
        moment a run's config is known and a run actually begins. Starting a
        second game builds a second GameScene, which re-levels the same mixer.

        Fail-soft by contract, not by try/except in the scene: AudioSystem swallows
        every mixer failure, so gameplay code can treat a sound as an event that
        always succeeds. A scene that wrapped each ``play_*`` in its own try block
        would be hiding its own bug the first time an id is misspelled.
        """
        self._manager.audio.apply_levels(
            AudioLevels.from_config(config.get("audio", {}))
        )

    def _build_spawn_rules(self, config: dict) -> SpawnRules:
        """Hoist the ``npc`` section into the rules the spawner and AI run on.

        The loader already rejects nonsense ranges, so this only exists to turn a
        hand-built config (tooling, or a future save file) into the same
        "report it like a config failure" message instead of a raw KeyError in the
        middle of the first hostile system the player ever enters.
        """
        try:
            return SpawnRules.from_config(config["npc"])
        except (KeyError, TypeError, ValueError) as exc:
            print(f"error: cannot build NPC spawn rules from config: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

    def _build_combat_rules(self, config: dict) -> CombatRules:
        """Hoist the ``combat`` section into the rules the projectile code runs on.

        Same deal as :meth:`_build_spawn_rules`: a hand-built config (tooling, a
        future save file) should fail the way a config failure fails everywhere
        else in this game — stderr and exit — rather than as a KeyError the first
        time the player taps the space bar.
        """
        try:
            return CombatRules.from_config(config["combat"])
        except (KeyError, TypeError, ValueError) as exc:
            print(f"error: cannot build combat rules from config: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

    # ------------------------------------------------------------------
    # The world: generated once per game, then cached
    # ------------------------------------------------------------------
    def _build_system_map(self, config: dict) -> SystemMapState:
        """Generate the world graph and its screen layout exactly once.

        The layout is built here rather than in the modal so "layout computed
        once per game and cached" is a fact about the world, not about how often
        the player presses M.

        The graph gets its **own** seeded :class:`random.Random`, separate from
        ``game_state.rng``: the world topology is a *world seed* (same seed must
        give the same 26 systems and the same connections), and sharing one RNG
        with the starfield/AI draws would make the map depend on how many frames
        of thrust the player happened to log before opening it.
        """
        try:
            generator = SystemGraphGenerator.from_config(
                config["map"], rng=_random_lib.Random(config.get("rng", {}).get("seed"))
            )
            graph = generator.generate()
            layout = build_map_layout(
                graph, SCREEN_SIZE, measure=lambda text, size: game_font(size).size(text)
            )
        except (GraphGenerationError, KeyError, TypeError) as exc:
            # A bad `map` config section is a data error, not a crash to debug at
            # runtime: report it the way a config failure is reported everywhere
            # else (stderr + exit) rather than opening a half-built world.
            print(f"error: cannot build the system map from config: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc
        return SystemMapState(graph=graph, layout=layout)

    def _build_lore_book(self, config: dict, graph) -> LoreBook:
        """Assign one lore line per system, once, from ``resources/lore.txt``.

        A third independent RNG stream (world graph, gameplay, lore): the map must
        not shift because a different system was visited first, and the lore must
        not shift because the player burned fuel for ten thousand frames. A
        missing, unreadable, or empty pool file is fatal per the spec, reported the
        way a bad config is reported rather than as a traceback or, worse, a spaceport
        with nothing to say.
        """
        try:
            return LoreBook.for_world(
                graph.names, _random_lib.Random(config.get("rng", {}).get("seed"))
            )
        except (RuntimeError, OSError) as exc:
            print(f"error: cannot load world lore: {exc}", file=sys.stderr)
            raise SystemExit(1) from exc

    # ------------------------------------------------------------------
    # Events / update
    # ------------------------------------------------------------------
    def handle_event(self, event) -> None:
        """All gameplay input belongs to the tactical view; the HUD is read-only."""
        self.tactical.handle_event(event)

    def update(self) -> Tuple[Action, ...]:
        """Advance the simulation, drive the jump, fly the shots, return the actions.

        ``open_map`` (pressing M) raises the system-map modal, unless a jump is
        animating — the spec blocks the map during a jump. ``jump`` (pressing J)
        runs the eligibility rules. ``fire`` (holding space) asks the ship's gun
        for a shot, and ``scan`` (pressing T) moves the HUD's nearest-ship lock.
        Returning the actions keeps this scene's reaction to discrete input
        testable without driving the whole stack.

        The order of the halves below is the frame's causality, not a style
        choice: input is drained and the ship moves, then the jump advances (which
        may end this visit and its fight), then the fleet acts, then every shot
        anyone produced this frame crosses the system and is resolved. Firing is
        resolved *after* the jump check so a shot pulled on the same frame a jump
        starts is simply gone with the rest of the visit — the alternative is a
        round that outlives the universe it was fired in.
        """
        actions = self.tactical.update()
        shots: "list[Shot]" = []
        for action in actions:
            if action.kind == "open_map":
                self._open_system_map()
            elif action.kind == "jump":
                self._request_jump()
            elif action.kind == "land":
                self._open_spaceport()
            elif action.kind == "scan":
                self._handle_scan()
            elif action.kind == "fire":
                shot = self.game_state.try_fire()
                if shot is not None:
                    shots.append(shot)
        self._close_port_modal()
        self._advance_jump()
        self._advance_encounter()
        self._advance_gunfight(shots)
        self._sync_jump_presentation()
        return tuple(actions)

    def _enter_system(self, system: str) -> None:
        """Deal what one visit to a system consists of: its job market and its traffic.

        Both are dealt on *entry*, not on landing, and both for the same reason.
        Rolling the market on landing made the port a free slot machine: ``L``,
        glance at the contracts, ``ESC``, ``L`` - two key presses and everything is
        re-dealt, so the best board was always one abort away. Rolling the fleet on
        landing would be the same trick in the other direction: park in orbit,
        ``L`` to make everyone disappear, launch, and repeat until the system
        happens to be empty. The visit is the unit of both, so a jump out and back
        is the only thing that re-deals them.

        The market is also priced against the hull the player had *on entry*, which
        closes the other free lunch: "buy the cargo upgrade here, land again, farm
        bigger jobs at the same port".

        Dropping the old :class:`Encounter` here *is* the despawn rule: ships do not
        respawn, and a jump out and back does not remember who was orbiting last
        time. Stage 11 must clear its projectiles at the same boundary — the ships
        that fired them no longer exist.

        Both rolls key off the same system-entry serial but namespace it
        differently (see :func:`port_rng` and :func:`encounter_rng`), so entering
        Bravo deals a Bravo market and a Bravo fleet reproducibly without either
        one consuming the other's random draws.

        Stage 11's fight state is dealt at the same boundary for the same reason
        it is *dropped* there: rounds in flight belong to the visit that fired
        them, and the nearest-ship lock belongs to a system the player is no
        longer in (spec: the readout always starts a new system at "No target").
        """
        serial = self.game_state.begin_port_visit()
        self.port_visit = generate_port_offers(
            rules=self.game_state.economy,
            graph=self.system_map.graph,
            current_system=system,
            stats=self.game_state.stats,
            upgrade_levels=self.game_state.upgrade_levels,
            rng=port_rng(self.session_seed, system, serial),
            visit_serial=serial,
        )
        self.encounter = roll_encounter(
            system=system,
            system_names=self.system_map.graph.names,
            rules=self.npc_rules,
            # Never ``game_state.stats``: the spec pins NPC hulls to the ship the
            # player *started* with, so upgrading never rescales the galaxy.
            starting_stats=self.game_state.starting_stats,
            system_pixel_size=self.game_state.system_pixel_size,
            player_position=self.game_state.position,
            rng=encounter_rng(self.session_seed, system, serial),
            relations=self.relations,
        )
        self.gunfight.clear()
        self.scanner.clear()

    def _advance_encounter(self) -> None:
        """Run the current system's fleet for one frame; keep the shots it fired.

        Skipped while a jump is animating: the player is in hyperspace, and the
        ships in the system being left are thrown away at the far end of the
        sequence anyway, so a frame of NPC physics spent on them is behaviour
        nobody can observe. The new system's fleet is dealt by ``_enter_system``
        on the arrival frame and starts moving on the next one.

        ``pending_shots`` is Stage 11's seam: the AI owns when and where a gun
        fires, the projectile simulation owns what a projectile does. They are not
        the same job, and this is the handoff.
        """
        if self.jumps.is_active:
            self.pending_shots = []
            return
        self.pending_shots = self.encounter.advance_frame(self.game_state.position)

    # ------------------------------------------------------------------
    # Combat (Stage 11)
    # ------------------------------------------------------------------
    def _advance_gunfight(self, player_shots: "list[Shot]") -> None:
        """Fly every round in the system, then deal with whatever it landed on.

        Two halves, in this order:

        1. The rounds already in flight move and are resolved against the bodies
           standing where the frame *opened* — the same snapshot discipline the
           fleet's AI uses, so a hit cannot depend on whether some other ship's
           physics happened to run earlier in the frame.
        2. This frame's shots are launched *after* that, which is what stops a
           round from registering a point-blank hit on the frame it is born — a
           muzzle flare inside someone's cockpit is not yet a hit.

        Skipped during hyperspace, and cleared outright: the visit ends at the
        gate, and a projectile that followed the player through it would be a
        killer from a universe nobody is standing in.
        """
        if self.jumps.is_active:
            self.gunfight.clear()
            return

        impacts = self.gunfight.advance_frame(self._battlefield())
        self._resolve_impacts(impacts)
        launched = list(self.pending_shots) + player_shots
        self.gunfight.launch_all(launched)
        # After the launch, so a round that failed to become a projectile is not
        # heard anyway.
        self._sound_gunfire(len(launched))

    def _handle_scan(self) -> None:
        """Handle ``T``: move the readout's lock, and sound the alarm if it found a hostile.

        The klaxon is a *press* event, not a display event. The spec ties it to
        pressing ``T``, so an auto-revert to "No target" is silent, and so is a
        hostile quietly becoming the nearest ship while the player is not looking.
        The one question it asks — "is the hull I am looking at hostile to me?" —
        is the same question the readout answers in red, which is why both read
        the same :class:`PlayerRelations` rather than each keeping a rule.
        """
        self.scanner.scan(self.encounter.ships, self.game_state.position)
        if self._displayed_contact_is_hostile():
            self._manager.audio.play_klaxon()

    def _displayed_contact_is_hostile(self) -> bool:
        """Whether the scanned contact belongs to a faction currently at war with us.

        ``getattr`` rather than an attribute access because the scanner's lock is
        whatever the last scan found (``None`` between scans, an NPC hull after
        one): there is no type to lean on here, and a ship from a modded faction
        list must not be able to raise from a HUD nicety.
        """
        faction = getattr(self.scanner.displayed, "faction", None)
        return (
            faction is not None
            and is_npc_faction(faction)
            and self.relations.is_hostile_to_player(faction)
        )

    def _sound_gunfire(self, rounds: int) -> None:
        """One report per round that actually left a gun, whoever fired it.

        Counting *rounds* rather than firing ships matters: two hulls can fire on
        the same frame, and a shot that was never launched makes no noise. Ships
        outside the 683px view are included by spec — a ship you can hear but not
        see is information — and the mixer has no notion of the tactical view's
        camera, so an off-screen report is simply the same sound at the same level
        (see DECISIONS.md, Stage 12).
        """
        for _ in range(max(0, rounds)):
            self._manager.audio.play_weapon_fire()

    def _battlefield(self) -> "list[Combatant]":
        """Every body a round could hit this frame: the player plus the fleet.

        A destroyed player is left off entirely — resolving hits against a wreck
        produces impacts, bounties, and particle effects for a run that Stage 13
        is about to end. Wrecked NPC hulls are already gone from the fleet (see
        :meth:`~src.model.encounter.Encounter.prune_destroyed`).
        """
        bodies: "list[Combatant]" = []
        if not self.game_state.destroyed:
            bodies.append(Combatant.from_player(self.game_state))
        bodies.extend(Combatant.from_ship(ship) for ship in self.encounter.ships)
        return bodies

    def _resolve_impacts(self, impacts: "list") -> None:
        """Turn the model's :class:`~src.model.combat.Impact` events into game state.

        Three consequences per hit, all of them the spec's and none of them the
        projectile code's business:

        * **Sparks.** Small spray for a hit, big one for a hull coming apart.
          Tinted with the *firer's* colour, so a player round reads green even in
          a screenful of red pirate fire.
        * **Grudges.** A player round that lands on a Localhoster or a Bobber
          makes that faction hostile for the rest of the game — on the *impact*,
          not on the kill: a shield that soaked the hit changes the galaxy just as
          much as a hull that didn't survive it.
        * **Bounties**, and only for a hull the player's own gun finished.

        Grudges are recorded before bounties on purpose. The bounty a war-side
        pays depends on that *payer's* relations, and a hit can only make the
        *victim's* faction hostile, so the two never actually interfere — but the
        order that cannot interfere is the one worth writing down.
        """
        for impact in impacts:
            tint = combatant_color(impact.faction)
            if impact.destroyed:
                self.tactical.show_destruction(impact.position, tint)
                self._manager.audio.play_destruction()
            else:
                self.tactical.show_impact(impact.position, tint)
                self._manager.audio.play_impact()

            if impact.fired_by_player and is_npc_faction(impact.target_faction):
                self.relations.declare_hostile_to_player(impact.target_faction)
            if impact.destroyed:
                self._award_bounty(impact)

        # Deaths are pruned here rather than in the projectile code: the fleet, the
        # minimap, the scan lock, and the bounty above all ask the same question
        # ("is that hull still flying?") and get one answer if the fleet is edited
        # once, in one place, at the end of the frame that killed it.
        self.encounter.prune_destroyed()
        self.scanner.refresh()
        self._note_player_destruction()

    def _award_bounty(self, impact) -> None:
        """Pay and announce the bounty for one hull the player finished.

        The rule lives in :func:`src.model.combat.bounty_for_kill`; this is the
        half that touches the wallet and the screen, which is a scene's job. No
        bounty is silent, and no bounty is payable for a kill somebody else's gun
        finished, or for one the war-side that would pay already hates the player
        for (see the Stage 11 notes in DECISIONS.md).
        """
        if not impact.fired_by_player or not is_npc_faction(impact.target_faction):
            return
        bounty = bounty_for_kill(impact.target_faction, self.combat_rules, self.relations)
        if bounty is None:
            return
        self.game_state.add_credits(bounty.credits)
        self.tactical.show_message(bounty.message, BOUNTY_MESSAGE_FRAMES)

    def _note_player_destruction(self) -> None:
        """Flag the run as over the frame the hull comes apart, and stop flying.

        Stage 13 owns the end screen (and the other ways to lose), so this stage
        raises the flag rather than the screen. What it *does* do is lock the
        controls: a wreck that can still steer and shoot is a bug the player can
        keep playing in, and the difference between "dead" and "dead but still
        flying" is the sort of thing a Stage 13 gate has to be able to assert.

        No explosion sound is played here on purpose. Only an impact can destroy
        the hull, and :meth:`_resolve_impacts` already played the big boom for the
        round that did it; a second one would be the same waveform stacked on top
        of itself, which the mixer renders as a louder hit rather than as a death.
        """
        if not self.game_state.destroyed:
            return
        if not self.pending_game_over:
            self.tactical.input.lock_input()
            self.tactical.show_message(PLAYER_LOST_MESSAGE, BOUNTY_MESSAGE_FRAMES)
        self.pending_game_over = True

    def _close_port_modal(self) -> None:
        """Notice that the player launched: the modal is gone, the market is not.

        The model's ``is_landed`` flag is the signal rather than a callback from the
        modal: the spaceport can be left by a button, by ``ESC``, or by a window
        quit, and every one of those paths already clears the flag. The market board
        deliberately survives the launch - it is replaced by :meth:`_enter_system`,
        not by leaving a planet.
        """
        if not self._port_modal_open or self.game_state.is_landed:
            return
        self._port_modal_open = False
        # The press that opened the port left its release at the door: the modal
        # swallowed the KEYUP, so the tactical layer would otherwise still believe
        # ``L`` is being held and refuse the next press.
        self.tactical.input.reset_held_state()

    def _sync_jump_presentation(self) -> None:
        """Hand the current jump phase to the view and the HUD.

        This lives with ``update()`` rather than with ``draw()`` (unlike the HUD's
        nav line) because the jump sequence only advances in ``update()`` — and
        the tactical view *consumes* the presentation during its own update, to
        drive the warp tunnel's intensity. Syncing at draw time would leave every
        consumer one frame stale; syncing the nav line at draw time is correct for
        the opposite reason, since it changes while ``update()`` is not running
        (the map modal is on top of the stack). Each seam syncs where its state
        actually changes.
        """
        self.hud.is_jumping = self.jumps.is_active
        self.tactical.jump = self.jumps.presentation()

    # ------------------------------------------------------------------
    # Jumping (Stage 8)
    # ------------------------------------------------------------------
    def _request_jump(self) -> None:
        """Handle J: start the sequence, or show why it cannot start.

        Silence is a valid answer: the spec says J "does nothing" when no
        system is selected, so only the blockers that carry copy say anything.
        """
        outcome = self.jumps.request()
        if outcome.started:
            # Two locks, on purpose: the input layer stops the player steering,
            # and ``GameState.is_jumping`` blocks the map and lets the ship
            # ignore the system boundary.
            self.tactical.input.lock_input()
            self._manager.audio.play_jump_spinup()
            return

        if outcome.blocker == BLOCKED_EXACT_FUEL:
            # Spec special case: J with *exactly* the jump's fuel cost is an
            # immediate game over, with no animation. Stage 8 owns the half it
            # can see (no jump, no fuel spent); Stage 13 turns this flag into
            # the game-over screen. Flagged rather than silently implemented so
            # the seam is not mistaken for the whole rule.
            self.pending_game_over = True
        if outcome.message:
            self.tactical.show_message(outcome.message, JUMP_DENIED_MESSAGE_FRAMES)

    def _advance_jump(self) -> None:
        """Tick the jump sequence and the flash, reacting to phase boundaries.

        The flash is advanced *before* the controller so the frame a phase
        begins on is frame 1 for both counters. Ticking them in the other order
        offsets the white-out from the world swap by a frame, and the player
        watches the universe teleport instead of arriving.
        """
        self.screen_flash.advance()
        event = self.jumps.advance()
        if event is None:
            return

        if event.kind == EVENT_TRANSITION_STARTED:
            self.screen_flash.begin(self.jumps.params.transition_frames)
            self._manager.audio.play_thunderclap()
        elif event.kind == EVENT_ARRIVED:
            self.tactical.notify_system_changed(event.system)
            # Entering a system deals everything the visit consists of: its job
            # market and its fleet. The roll happens even if the player never
            # lands, and the old encounter object is dropped here — which is the
            # despawn rule, not a cleanup nicety. Ships do not follow the player
            # through the gate, and the new system's traffic is a fresh roll.
            self._enter_system(event.system)
        elif event.kind == EVENT_JUMP_ENDED:
            self.tactical.input.unlock_input()

    def draw(self, surface: "pygame.Surface") -> None:
        """Draw the tactical view, the HUD, then the screen flash over both.

        The HUD's nav sync lives here rather than in ``update()`` because
        ``update()`` is not called while a modal is on top of the stack, yet
        ``draw()`` always is — so a destination chosen on the map would
        otherwise only appear on the HUD after the modal closed. The jump
        presentation syncs in ``update()`` instead: see
        :meth:`_sync_jump_presentation`.
        """
        self.hud.nav_selected_name = self.system_map.selected_system
        # The economy readouts sync at draw time for the same reason the nav line
        # does: every credit the player spends or earns in a port happens while
        # update() is frozen under the modal, so a draw-time sync is the only one
        # that is guaranteed to have seen it.
        self.hud.credits = self.game_state.credits
        self.hud.cargo_used = self.game_state.cargo_used
        self.hud.passengers_used = self.game_state.passengers_used
        # The fleet is published to both renderers at draw time, for the same
        # reason the nav line is: it is *shared* state rather than an owned view,
        # and a draw-time sync guarantees both the hulls in the game view and the
        # contacts on the minimap are looking at the same ships in the same
        # places. Two sync points for one list is how a minimap ends up a frame
        # behind a hull.
        self.tactical.encounter = self.encounter
        self.hud.contacts = self.encounter.ships
        # The same draw-time argument applies to Stage 11's two additions: the
        # rounds in flight are published so the view paints exactly the shots the
        # simulation is holding (not a stale tuple), and the nearest-ship readout
        # reads the scanner's lock rather than picking a ship itself — a HUD that
        # re-derives "which ship am I looking at" is a second scanner, and it will
        # eventually disagree with the first (spec: the display is *sticky*).
        self.tactical.projectiles = self.gunfight.projectiles
        self.hud.nearest_ship = self.scanner.displayed
        self.tactical.draw(surface)
        self.hud.draw(surface)
        self.screen_flash.draw(surface)

    def _open_system_map(self) -> None:
        """Push the system-map modal, except while a jump is in progress.

        Mid-jump the player has already paid for the trip and cannot steer, so a
        map would offer them a destination they cannot act on.

        No "is the map already open" guard is needed: only the top scene of the
        stack is updated, so this method cannot run while the modal is up.
        """
        if self.game_state.is_jumping:
            return
        self._manager.push(MapView(self.system_map))

    # ------------------------------------------------------------------
    # Landing (Stage 9)
    # ------------------------------------------------------------------
    def _open_spaceport(self) -> None:
        """Handle ``L``: settle at the planet, roll the port, raise the modal.

        Deliberately silent outside landing range, matching the Stage 8 rule for
        ``J`` with nothing selected: the "Press L to land here" prompt is the
        invitation, and a banner for pressing it unprompted is noise the spec
        never asks for. The one message the spec does ask for — what just got
        unloaded, and for how much — is the spaceport's opening line, because the
        player is reading that screen when it happens.

        The offers were dealt on entering the system (see :meth:`_enter_system`).
        Landing only raises the screen that shows them, which is what stops a
        player re-rolling a market by leaving the planet and landing again.
        """
        if self.game_state.is_jumping:
            return
        # A port already on screen means the modal owns the keyboard in play, but
        # "the modal owns the keyboard" is a property of the scene stack, not of
        # this method. Guarding here keeps a re-routed L from stacking a second
        # modal on top of the first (and re-rolling a board the player is reading).
        if self._port_modal_open:
            return
        if not self.game_state.in_landing_range(PLANET_WORLD_POSITION):
            return

        current = self.system_map.current_system
        report = self.game_state.land(current)
        if self.port_visit.system != current:
            # Defensive: every entry deals a board, so this is unreachable in play.
            # A scene built (or a system reached) without an arrival event still
            # gets a market, and a board for the *wrong* system would be worse than
            # none at all.
            self._enter_system(current)
        self._port_modal_open = True
        self._manager.push(
            SpaceportView(self.port_visit, self.game_state, report, self.lore)
        )
