"""Tactical game-view scene (Stage 4+).

Renders the left-hand game area: a black background, a procedurally drawn and
rotated blocky cargo shuttle, the system planet, and a starfield that scrolls
with player movement. The right-hand third of the window belongs to the HUD
component (see :mod:`src.hud`), so this scene deliberately clears only its own
region — and it never draws beneath the HUD.

The camera is locked to the player's ship: the ship is pinned to the centre of
the game view and the world (planet, stars) slides past it.
"""

from __future__ import annotations

import math
import zlib
from typing import TYPE_CHECKING

import pygame

from src.camera import world_to_screen
from src.effects import ImpactEffects, WarpTunnel
from src.hud import VIEW_WIDTH, landing_prompt_text
from src.input import Action, InputLayer
from src.model.combat import CombatRules
from src.model.factions import (
    FACTION_BOBBER,
    FACTION_LOCALHOSTER,
    FACTION_PIRATE,
    combatant_color,
    faction_color,
)
from src.model.game_state import PLANET_WORLD_POSITION, GameState
from src.model.jump import JumpPresentation, PHASE_BURN, PHASE_TRANSITION
from src.model.starfield import Starfield
from src.overlays import MessageOverlay
from src.scene_manager import Scene

if TYPE_CHECKING:
    from src.scene_manager import SceneManager

SCREEN_SIZE = (1024, 768)
# The game view is the left two thirds of a 1024-wide window; HUD takes the rest.
VIEW_WIDTH = 683
_VIEW_CENTER = (VIEW_WIDTH / 2.0, SCREEN_SIZE[1] / 2.0)

# Only the left game-view region is cleared here each frame. The right-hand HUD
# is drawn by a sibling component of GameScene, which owns that region; wiping
# the whole surface would clobber it.
_GAME_VIEW_RECT = pygame.Rect(0, 0, VIEW_WIDTH, SCREEN_SIZE[1])

_BG = (0, 0, 0)
_PLANET_COLORS = [(90, 160, 90), (150, 110, 70), (110, 90, 140), (70, 130, 160), (170, 150, 90)]

# Stars smear into lines during a jump. The cap exists because a jump tops out
# above 200 px/frame: an uncapped smear is a solid white rectangle.
_MAX_STAR_STREAK = 180
# A smear may start off-screen and still cross the view, so the cull box is
# padded by the longest possible streak rather than by the view edge.
_STREAK_CULL_MARGIN = _MAX_STAR_STREAK

# "System boundary reached" is pure copy, so it lives next to the code that
# shows it; its durations come from tactical.boundary_warnings in config.
BOUNDARY_WARNING_TEXT = "System boundary reached"

# NPC hull silhouettes are drawn from the faction's own colour, with a darker
# shade for the interior detail so the shape reads at 40 pixels instead of as a
# coloured smudge.
_HULL_SHADE = 0.55


def _shaded(color: "tuple[int, int, int]", factor: float = _HULL_SHADE) -> "tuple[int, int, int]":
    """A darker version of a colour, for the interior detail of a hull."""
    return tuple(int(round(channel * factor)) for channel in color)  # type: ignore[return-value]


def localhoster_polygon(length: int, width: int) -> "tuple[tuple[int, int], ...]":
    """Long and angular, like an arrow: the nose leads, the body tapers behind.

    Vertices are in surface coordinates (x grows toward the nose, y is down), so
    the polygon must be built for the unrotated surface and rotated with it.
    """
    mid_y = width // 2
    return (
        (length - 1, mid_y),           # nose, dead ahead
        (length // 4, 0),              # upper shoulder
        (0, 0),                        # upper tail
        (length // 2, mid_y),          # swept-in belly
        (0, width - 1),                # lower tail
        (length // 4, width - 1),      # lower shoulder
    )


def bobber_ellipses(length: int, width: int) -> "tuple[tuple[int, int, int, int], ...]":
    """A rounded flying saucer: a wide hull ellipse plus a smaller dome.

    Rect-based so the shape stays a saucer at any size the config asks for, and
    the dome sits forward of centre so the facing is still readable.
    """
    dome_w = max(4, length // 3)
    dome_h = max(3, width // 3)
    dome_x = length // 2 - dome_w // 2
    return (
        (0, width // 6, length, width * 2 // 3),           # hull
        (dome_x, 0, dome_w, dome_h * 2),                    # dome, on top of it
    )


def pirate_polygon(length: int, width: int) -> "tuple[tuple[int, int], ...]":
    """Sharp nose with forward-swept wings: the tips sit *ahead* of the roots.

    Forward-swept means the wing tips are further forward (larger x) than where
    the wings join the fuselage, which is what makes this silhouette read as
    "aggressive" against the Localhoster's straight arrow.
    """
    mid_y = width // 2
    return (
        (length - 1, mid_y),               # sharp nose
        (int(length * 0.60), 0),           # upper wing tip, forward
        (int(length * 0.30), int(width * 0.40)),  # upper wing root
        (0, mid_y),                        # tail
        (int(length * 0.30), int(width * 0.60)),  # lower wing root
        (int(length * 0.60), width - 1),   # lower wing tip, forward
    )


def npc_ship_surface(faction: str, length: int, width: int) -> "pygame.Surface":
    """Procedurally draw one NPC hull, unrotated, nose along +x.

    Same approach as the player's shuttle (Stage 4): no image assets, so the
    silhouettes scale with whatever ``player_ship.length``/``width`` the config
    asks for and a missing resource file is not a crash. The three shapes come
    from the spec's "other ship designs" section.
    """
    length = max(4, int(length))
    width = max(4, int(width))
    color = faction_color(faction)
    surface = pygame.Surface((length, width), pygame.SRCALPHA)

    if faction == FACTION_BOBBER:
        for rect in bobber_ellipses(length, width):
            pygame.draw.ellipse(surface, color, rect)
        pygame.draw.ellipse(
            surface, _shaded(color), (length // 3, width // 4, length // 3, width // 2), 1
        )
        return surface

    polygon = (
        localhoster_polygon(length, width)
        if faction == FACTION_LOCALHOSTER
        else pirate_polygon(length, width)
    )
    pygame.draw.polygon(surface, color, polygon)
    pygame.draw.polygon(surface, _shaded(color), polygon, 1)
    return surface


def planet_color_for(system_name: str) -> "tuple[int, int, int]":
    """A stable planet colour per system name.

    ``zlib.crc32`` rather than ``hash()``: Python randomises string hashing per
    process, so ``hash()`` would repaint every planet every launch and make the
    colour impossible to assert on (see the Stage 7 hash-seed note in
    DECISIONS.md - same trap, different module).
    """
    return _PLANET_COLORS[zlib.crc32(system_name.encode("utf-8")) % len(_PLANET_COLORS)]


class TacticalView:
    """Game view + planet + starfield + message overlay for one solar system.

    This is a component of :class:`~src.scenes.game_scene.GameScene`, not a
    scene-stack entry: GameScene owns the single :class:`GameState` and forwards
    input here, so a passive component (the HUD) can never sit on top of the
    stack and swallow the player's keystrokes.
    """

    def __init__(self, manager: "SceneManager", game_state: GameState) -> None:
        """Build the tactical view with its ship state and cached ship sprite."""
        if game_state is None:
            raise ValueError("TacticalView requires the GameState it will simulate")
        self._manager = manager
        # The input layer sits between raw pygame events and the simulation.
        self.input = InputLayer()
        # Difficulty comes from the player's selection, never a fixed filename.
        self.configs = manager.game_config()
        self.game_state = game_state
        self.overlays = MessageOverlay(_GAME_VIEW_RECT)
        # Stars live in view space and are scrolled by the ship's velocity, so
        # the box must cover the taller axis of the view or the top and bottom
        # of the game view would be star-free.
        self.starfield = self._build_starfield()
        # Hyperspace presentation. ``jump`` is published by GameScene each
        # frame from the jump controller; the view never asks the controller
        # anything, so it cannot start making gameplay decisions.
        self.jump = JumpPresentation()
        self.warp = WarpTunnel(
            count=int(self.configs["tactical"]["stars"]["count"]),
            max_radius=math.hypot(VIEW_WIDTH, SCREEN_SIZE[1]) / 2.0,
            rng=self.game_state.rng,
        )
        # Presentation-only use of the combat rules: the view needs the dot size,
        # and reading it through the same :class:`CombatRules` the simulation uses
        # (same function, same validated config section) is what keeps "a 3px
        # circle" from meaning 3px on one screen and 6px on another.
        self.combat_rules = CombatRules.from_config(self.configs["combat"])
        # Which system is being rendered: drives the planet colour, and is set
        # by notify_system_changed() on arrival.
        self.system_name = "Alpha"
        # The fleet to draw, published by GameScene at draw time. ``None`` only
        # for a view built standalone (tests, tooling): the scene that owns a
        # world always publishes an Encounter, and drawing is not allowed to
        # invent one.
        self.encounter = None
        # The shots currently in flight, likewise published by GameScene. Empty
        # for a standalone view: an unarmed reviewer gets an honest picture.
        self.projectiles: "tuple" = ()
        # Sparks from impacts and wrecks, advanced and drawn by this view.
        self.impacts = ImpactEffects(rng=self.game_state.rng)
        self._npc_surfaces = self._build_npc_surfaces()
        self._boundary_warning_cooldown = 0
        # Cached, unrotated blocky shuttle drawn at the ship's length/width.
        self._ship_surface = self._build_ship_surface()

    def _build_starfield(self) -> Starfield:
        """A fresh sky: 150 stars covering the taller axis of the game view."""
        return Starfield(
            count=int(self.configs["tactical"]["stars"]["count"]),
            half_extent=max(VIEW_WIDTH, SCREEN_SIZE[1]) / 2.0,
            rng=self.game_state.rng,
        )

    def notify_system_changed(self, system_name: str) -> None:
        """The player just arrived somewhere else: new sky, new planet, new tunnel.

        A jump that kept the old starfield would show the player flying back
        into the system they just fled at 200 px/frame, then stopping dead.
        Regenerating the sky (same 150-star invariant) is the visual half of
        the world swap the jump model performs under the flash.
        """
        self.system_name = system_name
        self.starfield = self._build_starfield()
        self.warp.reset()
        self.impacts.clear()
        self.overlays.set_sticky(None)

    # ------------------------------------------------------------------
    # Event + update plumbing (Stage 5 input layer)
    # ------------------------------------------------------------------
    def handle_event(self, event) -> None:
        """Route every pygame event into the input layer for later draining."""
        self.input.feed_event(event)

    def update(self) -> "list[Action]":
        """Drain one frame: feed ship controls and advance the simulation.

        Returns the discrete actions produced this frame (empty when none fired)
        so the owning scene can react to them - an ``open_map`` action raises the
        system map. Callers that ignore actions may discard the result.
        """
        control_frame, actions = self.input.drain_frame()
        if control_frame is not None:
            self.game_state.feed_input(
                thrust=control_frame.thrust,
                left=control_frame.left,
                right=control_frame.right,
                reverse_edge=control_frame.reverse_edge,
            )
        # Advance the pure model by exactly one fixed timestep.
        self.game_state.advance_frame()

        # The camera is pinned to the ship, so the background must be scrolled
        # by the ship's velocity each frame (spec: rightward flight moves the
        # stars left at the same rate).
        vx, vy = self.game_state.velocity
        self.starfield.update(vx, vy)

        if self.jump.in_hyperspace:
            self.warp.advance(self._warp_intensity())

        self.impacts.advance()
        self._update_landing_prompt()
        self._update_boundary_warning()
        self.overlays.update()

        for action in actions:
            self.on_action(action)

        return actions

    def show_message(self, text: str, duration_frames: int = 180) -> None:
        """Overlay a transient message on the game view (Stages 8/11 use this)."""
        self.overlays.show(text, duration_frames)

    def show_impact(self, position: "tuple[float, float]", tint: "tuple[int, int, int]") -> None:
        """A projectile landed at this world point: paint the small spray.

        Called by :class:`~src.scenes.game_scene.GameScene` when the model reports
        an :class:`~src.model.combat.Impact`. The position is a world coordinate,
        so the sparks stay where the hit happened even as the camera slides on.
        """
        self.impacts.spawn_impact(position, tint=tint)

    def show_destruction(
        self, position: "tuple[float, float]", tint: "tuple[int, int, int]"
    ) -> None:
        """A hull came apart at this world point: paint the big spray."""
        self.impacts.spawn_destruction(position, tint=tint)

    def _update_landing_prompt(self) -> None:
        """Keep the landing prompt visible while the ship is in landing range.

        Suppressed in hyperspace: the jump model refuses a jump that starts
        inside landing range and spawns the player well outside it, so the
        prompt *should* be impossible to see mid-jump. "Should" is what the
        pixel test that pins this behaviour exists for.
        """
        if self.jump.in_hyperspace:
            self.overlays.set_sticky(None)
            return
        planet_x, planet_y = PLANET_WORLD_POSITION
        distance = self.game_state.distance_from_point(planet_x, planet_y)
        prompt = landing_prompt_text(distance, self.game_state.landing_range)
        self.overlays.set_sticky(prompt)

    def _update_boundary_warning(self) -> None:
        """Banner the boundary message at most once per configured cooldown.

        The model reports boundary contact on every frame the ship is pressed
        against an edge, which would otherwise re-arm the banner every frame;
        the spec's "at most once every five seconds" is this cooldown, and its
        length comes from config, not a literal.
        """
        self._boundary_warning_cooldown = max(0, self._boundary_warning_cooldown - 1)
        if self._boundary_warning_cooldown > 0:
            return
        if not self.game_state.boundary_reached_this_frame():
            return
        warnings = self.configs["tactical"]["boundary_warnings"]
        self.overlays.show(BOUNDARY_WARNING_TEXT, int(warnings["message_frames"]))
        self._boundary_warning_cooldown = int(warnings["cooldown_frames"])

    def on_action(self, action: Action) -> None:
        """Dispatch a discrete action from the input layer.

        Stage 5 registered the bindings here; Stage 11 moved the one that matters
        for the simulation elsewhere. ``fire`` is handled by
        :class:`~src.scenes.game_scene.GameScene`, because pulling the player's
        trigger is a session concern (it produces a :class:`Shot` that the visit's
        :class:`~src.model.combat.Gunfight` consumes), not a rendering concern —
        the view that both drains the input and paints the result is the worst
        place to decide whether the gun was actually ready.
        """
        # open_map / jump / land / scan / fire / exit_game are consumed by their
        # owning stages; the view has no gameplay input of its own left.
        return

    # ------------------------------------------------------------------
    # Drawing
    # ------------------------------------------------------------------
    def draw(self, surface: "pygame.Surface") -> None:
        # Only clear the left game-view region so the sibling HudView component's
        # right-third HUD is not wiped each frame.
        surface.fill(_BG, _GAME_VIEW_RECT)
        self._draw_game_view(surface)

    def _draw_game_view(self, surface: "pygame.Surface") -> None:
        self._draw_stars(surface)
        self._draw_planet(surface)
        self._draw_contacts(surface)
        self._draw_projectiles(surface)
        self._draw_ship(surface)
        self._draw_impacts(surface)
        self._draw_warp_tunnel(surface)
        self.overlays.draw(surface)

    def _draw_stars(self, surface: "pygame.Surface") -> None:
        """Stars are single pixels in view space, culled to the game-view rect.

        During a jump each star becomes a smear trailing along the direction of
        travel, its length the ship's speed capped at ``_MAX_STAR_STREAK``: the
        smear is what tells the player this is not ordinary thrusting, and the
        cap is what keeps the game view from becoming one solid white block.
        """
        streak = self._star_streak_vector()
        if streak is None:
            for star in self.starfield.stars:
                sx = int(round(_VIEW_CENTER[0] + star.x))
                sy = int(round(_VIEW_CENTER[1] + star.y))
                if 0 <= sx < VIEW_WIDTH and 0 <= sy < SCREEN_SIZE[1]:
                    surface.set_at((sx, sy), star.color)
            return

        offset_x, offset_y = streak
        for star in self.starfield.stars:
            sx = _VIEW_CENTER[0] + star.x
            sy = _VIEW_CENTER[1] + star.y
            if not (-_STREAK_CULL_MARGIN <= sx <= VIEW_WIDTH + _STREAK_CULL_MARGIN
                    and -_STREAK_CULL_MARGIN <= sy <= SCREEN_SIZE[1] + _STREAK_CULL_MARGIN):
                continue
            pygame.draw.line(surface, star.color, (sx, sy), (sx + offset_x, sy + offset_y), 1)

    def _star_streak_vector(self) -> "tuple[float, float] | None":
        """The smear offset for a star, or None to draw plain single pixels.

        Returns None outside hyperspace and in the single frame after arrival
        where velocity has already been zeroed but the jump phase has not ended.
        """
        if not self.jump.in_hyperspace:
            return None
        vx, vy = self.game_state.velocity
        speed = math.hypot(vx, vy)
        if speed < 1e-9:
            return None
        length = min(speed, _MAX_STAR_STREAK) / speed
        return (-vx * length, -vy * length)

    def _draw_warp_tunnel(self, surface: "pygame.Surface") -> None:
        """Hyperspace streaks, poured over everything else in the view."""
        if not self.jump.in_hyperspace:
            return
        self.warp.draw(surface, _VIEW_CENTER)

    def _warp_intensity(self) -> float:
        """Tunnel intensity: builds through the burn, collapses through the flash.

        The white-out phase ramps *down* so the tunnel dies at the same rate the
        flash fades, rather than still blazing on arrival.
        """
        if self.jump.phase == PHASE_BURN:
            return self.jump.progress
        if self.jump.phase == PHASE_TRANSITION:
            return 1.0 - self.jump.progress
        return 0.0

    def _draw_planet(self, surface: "pygame.Surface") -> None:
        """Planet sits at the world origin, so the camera slides it around."""
        diameter = float(self.configs["tactical"]["planet_diameter"])
        color = planet_color_for(self.system_name)
        screen_pos = world_to_screen(
            PLANET_WORLD_POSITION[0], PLANET_WORLD_POSITION[1],
            self.game_state.position, _VIEW_CENTER,
        )
        pygame.draw.circle(surface, color, (int(round(screen_pos[0])), int(round(screen_pos[1]))),
                           int(diameter / 2.0))

    def _draw_contacts(self, surface: "pygame.Surface") -> None:
        """The fleet orbiting this system, each hull in its own faction colour.

        Drawn *before* the player's ship on purpose: ships pass through each other
        in this model, so the only question a collision of pixels can raise is who
        wins it, and the answer must always be the hull the player is steering.

        Ships are hidden during the white-out for the same reason the player is
        (see :meth:`_draw_ship`): during hyperspace nobody is in this universe. The
        projectiles and sparks the same visit produced inherit that rule rather
        than reinventing it.

        Culling is not a performance nicety. A system is ``tactical.system_pixel_size``
        across and the game view is 683px, so in most frames most of a fleet is off
        screen; an unculled blit at an arbitrary offset is how a pirate 900px away
        ends up painted over the HUD column.
        """
        if self.encounter is None or not self.jump.ship_visible:
            return
        # A hull half off the left edge must not have its other half painted over
        # the HUD column: `blit` is not clipped to a region by itself, so the
        # destination surface is clipped to the game view for the duration.
        surface.set_clip(_GAME_VIEW_RECT)
        try:
            for ship in self.encounter.ships:
                self._draw_one_contact(surface, ship)
        finally:
            surface.set_clip(None)

    def _draw_projectiles(self, surface: "pygame.Surface") -> None:
        """Every round in flight, as the spec's solid 3px circle.

        Coloured by whoever fired it (the player green, each faction its own),
        which is the only cue the player has that a stray Localhoster round is not
        an act of war — see the pass-through note in :mod:`src.model.combat`.

        Hidden during the white-out for the same reason the hulls are: a visit ends
        at the gate and the rounds with it, so anything in flight here would be a
        projectile from a universe the player is no longer in.
        """
        if not self.projectiles or not self.jump.ship_visible:
            return
        radius = self.combat_rules.projectile_radius
        surface.set_clip(_GAME_VIEW_RECT)
        try:
            for shot in self.projectiles:
                screen_x, screen_y = world_to_screen(
                    shot.position[0], shot.position[1],
                    self.game_state.position, _VIEW_CENTER,
                )
                # A round outside the view costs nothing to skip, and clipping the
                # surface would not be enough on its own: a 3px dot two pixels off
                # the HUD edge is still a dot painted on the HUD.
                if not (0.0 <= screen_x < VIEW_WIDTH and 0.0 <= screen_y < SCREEN_SIZE[1]):
                    continue
                pygame.draw.circle(
                    surface,
                    combatant_color(shot.faction),
                    (int(round(screen_x)), int(round(screen_y))),
                    radius,
                )
        finally:
            surface.set_clip(None)

    def _draw_impacts(self, surface: "pygame.Surface") -> None:
        """Sparks from hits and wrecks, drawn over the hulls they happened to."""
        if self.impacts.is_empty or not self.jump.ship_visible:
            return
        surface.set_clip(_GAME_VIEW_RECT)
        try:
            self.impacts.draw(surface, self.game_state.position, _VIEW_CENTER)
        finally:
            surface.set_clip(None)

    def _draw_one_contact(self, surface: "pygame.Surface", ship: "NpcShip") -> None:
        hull = self._npc_surfaces.get(ship.faction)
        if hull is None:
            # An unrecognised faction is a bug in the spawner, not a reason to
            # blank the screen: skip the hull and let the sim say so.
            return
        rotated = pygame.transform.rotate(hull, -ship.heading)
        screen_x, screen_y = world_to_screen(
            ship.position[0], ship.position[1], self.game_state.position, _VIEW_CENTER
        )
        rect = rotated.get_rect(center=(int(round(screen_x)), int(round(screen_y))))
        if rect.colliderect(_GAME_VIEW_RECT):
            surface.blit(rotated, rect)

    def _draw_ship(self, surface: "pygame.Surface") -> None:
        """The player's ship is always drawn at the centre of the game view.

        Except during the white-out, when the ship is not in this universe any
        more. Leaving it on screen would be the giveaway that the arrival is a
        teleport rather than a journey.
        """
        if not self.jump.ship_visible:
            return
        rotated = pygame.transform.rotate(self._ship_surface, -self.game_state.heading_degrees)
        rect = rotated.get_rect(center=_VIEW_CENTER)
        surface.blit(rotated, rect)

    # ------------------------------------------------------------------
    # Ship sprite construction
    # ------------------------------------------------------------------
    def _build_npc_surfaces(self) -> "dict[str, pygame.Surface]":
        """One cached hull per faction, sized from the player's **starting** hull.

        Every NPC rolls its length and width straight from those starting values
        (the spec wants all ships "roughly the same size as the player's ship"),
        so one surface per faction covers a whole system's fleet. Built once per
        view rather than per frame: rotating a cached surface is cheap, redrawing
        polygons 60 times a second for every hull in the system is not.

        This cache deliberately survives ``notify_system_changed``: hull sizes are
        per-game constants, so a jump has nothing to rebuild.
        """
        starting = self.game_state.starting_stats
        return {
            faction: npc_ship_surface(faction, starting.length, starting.width)
            for faction in (FACTION_LOCALHOSTER, FACTION_BOBBER, FACTION_PIRATE)
        }

    def _build_ship_surface(self) -> "pygame.Surface":
        """Procedurally draw a blocky cargo shuttle centred on its body.

        The nose must stay visible: it is the only cue the player has that the
        ship is facing a given way. An earlier revision drew the rear wings at
        ``3 * length / 4``, which is exactly where the nose block started, so the
        wings painted the nose out completely and every heading looked identical.
        """
        length = int(self.configs["player_ship"]["length"])
        width = int(self.configs["player_ship"]["width"])
        surface = pygame.Surface((length, width), pygame.SRCALPHA)

        # Main fuselage (blocky, rectangular-ish).
        pygame.draw.rect(surface, (180, 180, 190), (0, width // 4, length, width // 2))
        # Rear wings, aft quarter: one block above and one below the fuselage.
        wing_w = max(4, length // 8)
        wing_h = max(4, width // 2)
        wing_x = length // 4
        pygame.draw.rect(surface, (120, 120, 130), (wing_x, 0, wing_w, wing_h))
        pygame.draw.rect(surface, (120, 120, 130), (wing_x, width - wing_h, wing_w, wing_h))
        # Nose cone / cockpit block, drawn last so it is never occluded
        # (the nose points along +x == heading 0).
        nose = max(6, length // 4)
        pygame.draw.rect(surface, (150, 210, 230), (length - nose, 0, nose, width))
        return surface
