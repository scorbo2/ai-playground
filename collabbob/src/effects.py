"""Hyperspace presentation, and the sparks a gunfight throws (Stages 8 and 11).

The spec asks for an acceleration animation and stops there. This module is the
"and then it gets *dramatic*" part: three effects that turn a straight-line
speed-up into something that feels like leaving reality, and one of them (the
white-out) exists because it hides the world swap.

The second half of the module is Stage 11's half: particle bursts for projectile
impacts and ship destructions, plus the manager that keeps every live burst in
one place. Those are **world-anchored** (a spark cloud stays where the hit
happened as the camera slides past it), where the warp tunnel is view-anchored
(the vanishing point is the ship, by definition). That difference is the whole
reason the two draw calls take different arguments.

Everything time-related here is derived from a frame index and a total, not from
wall-clock time, so the animation is frame-exact and testable under the fixed
timestep. :func:`flash_alpha` deliberately takes its ramp length from
:func:`src.model.jump.blind_frames_for`, so the model swaps the world on exactly
the frame this module goes fully opaque. One timing source, two consumers.
"""

from __future__ import annotations

import math
import random as _random_lib
from dataclasses import dataclass
from typing import List, Sequence, Tuple

import pygame

from src.camera import world_to_screen
from src.model.jump import blind_frames_for
from src.model.physics import Vec2, unit_from_heading_degrees

# Frames the flash sits at full opacity before it starts decaying. Two is long
# enough to cover the world swap, short enough that it does not read as a
# loading screen.
FLASH_HOLD_FRAMES = 2

# The flash is not pure white: a faint blue-violet reads as energy rather than
# as "the window broke".
_FLASH_TINT = (226, 240, 255)
_TINT_CORE = (255, 255, 255)

# Hyperspace streaks drift from white to the same blue-violet as the flash, so
# the tunnel and the white-out look like one event and not two overlays.
_WARP_TINT = (150, 170, 255)


# ---------------------------------------------------------------------------
# The white-out
# ---------------------------------------------------------------------------
def flash_alpha(frame: int, total_frames: int) -> int:
    """Opacity (0-255) of the screen flash on 1-based ``frame`` of ``total_frames``.

    Ramps up over the model's "blind" window, holds, then decays to exactly 0 on
    the final frame so the effect cannot leave a residue on the arrival view.
    The ramp length comes from the jump model, which is what guarantees the
    system swap happens while the player is staring at pure white.
    """
    if total_frames <= 0:
        return 0
    frame = max(1, min(int(frame), int(total_frames)))
    blind = blind_frames_for(total_frames)
    if frame < blind:
        return int(round(255.0 * frame / blind))
    if frame == blind:
        return 255

    hold = min(FLASH_HOLD_FRAMES, max(0, total_frames - blind - 1))
    if frame <= blind + hold:
        return 255
    decay_span = total_frames - blind - hold
    if decay_span <= 0:
        return 0
    remaining = total_frames - frame
    return int(round(255.0 * remaining / decay_span))


class FlashOverlay:
    """A full-window white-out with an expanding shockwave on the way out.

    Deliberately drawn by the *scene* that owns the whole window (``GameScene``),
    after the HUD, so the flash covers the HUD too — a flash that politely skips
    the right-hand third looks like a rendering bug.
    """

    def __init__(self, region: "pygame.Rect", origin: "tuple[int, int] | None" = None) -> None:
        """`region` is what gets whited out; `origin` is where the boom starts.

        They differ: the flash covers the whole window, but the shockwave has to
        come from where the ship actually was — the centre of the game view, not
        the centre of the window. Ringing the window's empty middle is how you
        tell a player the effect was pasted on rather than caused by something.
        """
        self._region = region
        self._origin = origin
        self._total = 0
        self._frame = 0
        self._active = False

    def begin(self, total_frames: int) -> None:
        """Start a flash. Frame 1 is drawn on the frame this is called."""
        self._total = max(1, int(total_frames))
        self._frame = 1
        self._active = True

    def advance(self) -> None:
        """Consume one fixed timestep; a no-op when no flash is running."""
        if not self._active:
            return
        self._frame += 1
        if self._frame > self._total:
            self._active = False

    @property
    def active(self) -> bool:
        return self._active

    @property
    def frame(self) -> int:
        return self._frame

    def alpha(self) -> int:
        return flash_alpha(self._frame, self._total) if self._active else 0

    def shockwave_radius_fraction(self) -> float:
        """0..1 progress of the shockwave ring (0 until the flash starts fading).

        The ring only appears once the flash is fading, because a ring drawn on
        top of a fully opaque white flash is a ring nobody can see.
        """
        if not self._active:
            return 0.0
        blind = blind_frames_for(self._total)
        if self._frame <= blind:
            return 0.0
        return (self._frame - blind) / max(1, self._total - blind)

    def draw(self, surface: "pygame.Surface") -> None:
        """Blit the flash (and its shockwave) over the whole window."""
        if not self._active:
            return

        # The shockwave rides *under* the fading flash: it is the last thing the
        # player sees of the jump, expanding out of the ship's position.
        radius_fraction = self.shockwave_radius_fraction()
        if radius_fraction > 0.0:
            self._draw_shockwave(surface, radius_fraction)

        alpha = self.alpha()
        if alpha <= 0:
            return
        veil = pygame.Surface(self._region.size, pygame.SRCALPHA)
        veil.fill((*_FLASH_TINT, alpha))
        surface.blit(veil, self._region.topleft)

    def _shockwave_center(self) -> "tuple[tuple[int, int], float]":
        """The point the boom expands from, and its reach across the window."""
        center = self._origin or self._region.center
        left, top = self._region.topleft
        right, bottom = self._region.bottomleft[0], self._region.bottomleft[1]
        # Farthest corner, so the ring sweeps off the screen edge instead of
        # petering out in the middle of the view.
        reach = max(
            math.hypot(center[0] - x, center[1] - y)
            for x, y in ((left, top), (right, top), (left, bottom), (right, bottom))
        )
        return center, reach

    def _draw_shockwave(self, surface: "pygame.Surface", fraction: float) -> None:
        """Two expanding rings, fading as they grow."""
        center, max_radius = self._shockwave_center()
        # Fade in fast, then out with the flash, so the ring is a "boom" and
        # not a slow ripple.
        alpha = int(round(255.0 * min(1.0, fraction * 4.0) * (1.0 - fraction)))
        if alpha <= 0:
            return

        for scale, width in ((1.0, 4), (0.72, 2)):
            radius = int(round(max_radius * fraction * scale))
            if radius < 2:
                continue
            size = radius * 2 + width * 2
            ring = pygame.Surface((size, size), pygame.SRCALPHA)
            pygame.draw.circle(
                ring, (*_TINT_CORE, alpha), (size // 2, size // 2), radius, width
            )
            surface.blit(ring, (center[0] - size // 2, center[1] - size // 2))


# ---------------------------------------------------------------------------
# The tunnel
# ---------------------------------------------------------------------------
@dataclass
class _Streak:
    """One hyperspace streak: a point receding from the vanishing point."""

    angle: float
    radius: float
    previous_radius: float


def warp_speed(intensity: float, base: float = 0.06, span: float = 0.34) -> float:
    """Per-frame multiplicative growth of a streak's radius.

    Multiplicative (not additive) growth is what makes the streaks *accelerate*
    outward, which is the perspective cue that the camera is moving forwards
    into the tunnel rather than the tunnel sliding sideways past the camera.
    """
    clamped = max(0.0, min(1.0, intensity))
    return base + span * clamped


class WarpTunnel:
    """Radial streaks pouring out of the vanishing point at the ship.

    Positions are *view-space* offsets from the view centre (the ship is pinned
    to the centre of the game view), so the tunnel stays anchored on the player
    no matter where the camera has carried the old system off to.
    """

    def __init__(
        self,
        count: int,
        max_radius: float,
        rng: "_random_lib.Random | None" = None,
        min_radius: float = 3.0,
    ) -> None:
        self.count = int(count)
        self.max_radius = float(max_radius)
        self.min_radius = float(min_radius)
        self.rng = rng or _random_lib.Random()
        self._streaks: List[_Streak] = []
        self.reset()

    def reset(self) -> None:
        """Re-seed every streak near the vanishing point (new system, new tunnel)."""
        self._streaks = [self._new_streak() for _ in range(self.count)]

    def _new_streak(self) -> _Streak:
        angle = self.rng.uniform(0.0, math.tau)
        radius = self.rng.uniform(self.min_radius, self.min_radius * 3.0)
        return _Streak(angle=angle, radius=radius, previous_radius=radius)

    def advance(self, intensity: float) -> None:
        """Move every streak outward one frame; recycle the ones out of range.

        The count is invariant, exactly like the starfield's: an effect that
        thins out over a 3-second animation is a bug the player would see.
        """
        growth = 1.0 + warp_speed(intensity)
        for streak in self._streaks:
            streak.previous_radius = streak.radius
            streak.radius *= growth
            if streak.radius > self.max_radius:
                replacement = self._new_streak()
                streak.angle = replacement.angle
                streak.radius = replacement.radius
                streak.previous_radius = replacement.radius

    @property
    def streaks(self) -> List[_Streak]:
        return self._streaks

    def draw(self, surface: "pygame.Surface", center: "tuple[float, float]") -> None:
        """Draw every streak as a line from its previous position to its current one."""
        import pygame

        cx, cy = center
        for streak in self._streaks:
            # Near the vanishing point the streaks are short and dim; out at the
            # rim they are long, bright, and thick. That gradient is what sells
            # the sense of passing *through* space rather than across it.
            reach = min(1.0, streak.radius / self.max_radius)
            fade = min(1.0, reach * 2.0)
            color = (
                int(_WARP_TINT[0] + (255 - _WARP_TINT[0]) * fade),
                int(_WARP_TINT[1] + (255 - _WARP_TINT[1]) * fade),
                int(_WARP_TINT[2] + (255 - _WARP_TINT[2]) * fade),
            )
            cos, sin = math.cos(streak.angle), math.sin(streak.angle)
            start = (cx + cos * streak.previous_radius, cy + sin * streak.previous_radius)
            end = (cx + cos * streak.radius, cy + sin * streak.radius)
            pygame.draw.line(surface, color, start, end, 1 + int(reach * 2))


# ---------------------------------------------------------------------------
# Gunfire: the sparks (Stage 11)
# ---------------------------------------------------------------------------

# The spec asks for "colorful particle effects" on every projectile impact and
# "larger particle effects" on a destruction. Larger turns all four dials at
# once — more sparks, faster, longer-lived, a pixel thicker — because raising
# only the count of the same tiny dots still reads as the same event.
_IMPACT_PARTICLES = 12
_IMPACT_SPEED = 2.6          # px/frame of initial spread
_IMPACT_LIFETIME_FRAMES = 22
# A radius-1 spark is a 3px smudge that vanishes against the starfield at a
# distance; a hit has to be *seen* to warn the player that something is shooting at
# them. "Bigger" is carried by particle count and spread, not by dot size.
_IMPACT_RADIUS = 2

_DESTRUCTION_PARTICLES = 40
_DESTRUCTION_SPEED = 6.0
_DESTRUCTION_LIFETIME_FRAMES = 48
_DESTRUCTION_RADIUS = 2

# Deliberately not the faction palette. Sparks are hot metal and plasma; reusing
# faction colours would make a pirate's death indistinguishable from a pirate's
# shot, and the *tint* argument is what carries "who hit whom".
_SPARK_PALETTE: Tuple[Tuple[int, int, int], ...] = (
    (255, 236, 170),
    (255, 176, 84),
    (255, 96, 64),
    (168, 236, 255),
    (196, 255, 190),
    (226, 178, 255),
)

_WHITE_HOT: Tuple[int, int, int] = (255, 255, 255)


def _blend(
    first: Tuple[int, int, int], second: Tuple[int, int, int], fraction: float
) -> Tuple[int, int, int]:
    """Linear blend between two colours (``fraction`` 0 -> first, 1 -> second)."""
    fraction = max(0.0, min(1.0, float(fraction)))
    return tuple(
        int(round(a + (b - a) * fraction)) for a, b in zip(first, second)
    )  # type: ignore[return-value]


@dataclass
class _Particle:
    """One spark: a world position, a velocity, a colour, and a frame budget."""

    position: Vec2
    velocity: Vec2
    color: Tuple[int, int, int]
    frames_left: int
    total_frames: int

    def advance(self) -> bool:
        """Move one fixed timestep; False when this spark is done."""
        x, y = self.position
        self.position = (x + self.velocity[0], y + self.velocity[1])
        self.frames_left -= 1
        return self.frames_left > 0

    @property
    def life_fraction(self) -> float:
        """1 on the frame it is born, 0 the frame it dies."""
        if self.total_frames <= 0:
            return 0.0
        return max(0.0, self.frames_left / float(self.total_frames))


class ParticleBurst:
    """One spray of world-anchored sparks from one event, at one world point.

    A burst is inert once thrown: it does not track the ship that was hit, and it
    does not care whether that ship still exists. Sparks keep their velocity for
    their whole life — this is a universe with no drag, and a spark cloud that
    politely decelerated would be the one place the physics visibly lies.
    """

    def __init__(
        self,
        position: Vec2,
        *,
        count: int,
        speed: float,
        lifetime_frames: int,
        radius: int,
        rng: "_random_lib.Random",
        tint: Tuple[int, int, int] = _WHITE_HOT,
    ) -> None:
        self.origin: Vec2 = (float(position[0]), float(position[1]))
        self.radius = max(1, int(radius))
        self.tint = tint
        self._particles = [
            self._new_particle(speed, lifetime_frames, rng) for _ in range(max(1, int(count)))
        ]

    def _new_particle(
        self, speed: float, lifetime_frames: int, rng: "_random_lib.Random"
    ) -> _Particle:
        heading = rng.uniform(0.0, 360.0)
        # A spread of speeds rather than one: every spark at the same speed draws
        # a perfect expanding ring, which looks manufactured rather than exploded.
        pace = speed * rng.uniform(0.35, 1.0)
        unit_x, unit_y = unit_from_heading_degrees(heading)
        # A spread of lifetimes too, so the burst frays instead of vanishing on
        # one frame.
        life = max(1, int(lifetime_frames * rng.uniform(0.55, 1.0)))
        return _Particle(
            position=self.origin,
            velocity=(unit_x * pace, unit_y * pace),
            color=rng.choice(_SPARK_PALETTE),
            frames_left=life,
            total_frames=life,
        )

    @property
    def particles(self) -> "tuple[_Particle, ...]":
        return tuple(self._particles)

    @property
    def alive(self) -> bool:
        """Whether any spark is still burning."""
        return bool(self._particles)

    def advance(self) -> bool:
        """One frame for every spark; True while the burst is still visible."""
        self._particles = [particle for particle in self._particles if particle.advance()]
        return self.alive

    def color_for(self, particle: _Particle) -> Tuple[int, int, int]:
        """A spark's colour on this frame: born white-hot, dies in its own hue.

        The tint is mixed in at the very end of a spark's life so the burst
        carries a fingerprint of *who* landed the hit (the caller passes the
        firer's colour) without every particle being a flat faction swatch.
        """
        life = particle.life_fraction
        if life > 0.75:
            return _blend(particle.color, _WHITE_HOT, (life - 0.75) * 4.0)
        if life < 0.3:
            return _blend(particle.color, self.tint, 1.0 - (life / 0.3))
        return particle.color

    def draw(self, surface: "pygame.Surface", camera: Vec2, view_center: Vec2) -> None:
        """Draw every spark at its world position, through the shipping camera."""
        for particle in self._particles:
            screen_x, screen_y = world_to_screen(
                particle.position[0], particle.position[1], camera, view_center
            )
            radius = self.radius if particle.life_fraction > 0.5 else max(1, self.radius - 1)
            pygame.draw.circle(
                surface,
                self.color_for(particle),
                (int(round(screen_x)), int(round(screen_y))),
                radius,
            )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ParticleBurst(sparks={len(self._particles)})"


class ImpactEffects:
    """Every live burst in the current system visit.

    Owned by the tactical view (it is presentation state, like the starfield and
    the warp tunnel) but *fed* by the scene, because "something got hit at these
    world coordinates" is a model event and "make it pretty here" is not the
    model's business. Bursts are cleared when the visit ends: wreckage does not
    follow the player through a hyperspace gate, and a burst drawn in the wrong
    system is a coordinate bug the player would see as a ghost.
    """

    def __init__(self, rng: "_random_lib.Random | None" = None) -> None:
        self.rng = rng or _random_lib.Random()
        self._bursts: List[ParticleBurst] = []

    def spawn_impact(
        self, position: Vec2, tint: Tuple[int, int, int] = _WHITE_HOT
    ) -> ParticleBurst:
        """A projectile landed somewhere: the small, sharp spray."""
        return self._spawn(
            position,
            count=_IMPACT_PARTICLES,
            speed=_IMPACT_SPEED,
            lifetime_frames=_IMPACT_LIFETIME_FRAMES,
            radius=_IMPACT_RADIUS,
            tint=tint,
        )

    def spawn_destruction(
        self, position: Vec2, tint: Tuple[int, int, int] = _WHITE_HOT
    ) -> ParticleBurst:
        """A hull came apart: the big one."""
        return self._spawn(
            position,
            count=_DESTRUCTION_PARTICLES,
            speed=_DESTRUCTION_SPEED,
            lifetime_frames=_DESTRUCTION_LIFETIME_FRAMES,
            radius=_DESTRUCTION_RADIUS,
            tint=tint,
        )

    def _spawn(self, position, **kwargs) -> ParticleBurst:
        burst = ParticleBurst(position, rng=self.rng, **kwargs)
        self._bursts.append(burst)
        return burst

    def advance(self) -> None:
        """One frame for every live burst; dead bursts are dropped here."""
        self._bursts = [burst for burst in self._bursts if burst.advance()]

    def clear(self) -> None:
        """Forget every burst (new system, new game, hyperspace if you like)."""
        self._bursts.clear()

    @property
    def bursts(self) -> "tuple[ParticleBurst, ...]":
        return tuple(self._bursts)

    @property
    def is_empty(self) -> bool:
        return not self._bursts

    def draw(self, surface: "pygame.Surface", camera: Vec2, view_center: Vec2) -> None:
        """Draw every live burst, oldest first (newest sparks land on top)."""
        for burst in self._bursts:
            burst.draw(surface, camera, view_center)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"ImpactEffects(bursts={len(self._bursts)})"
