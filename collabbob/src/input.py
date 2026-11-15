"""Input layer: translate raw pygame key events into game controls and actions.

The tactical simulation lives in :mod:`src.model.game_state` and must stay free
of any pygame dependency (see the Stage 3 decision). Raw keyboard events, by
contrast, are inherently a pygame concern, so this module is the single place
that bridges the two: it consumes ``KEYDOWN``/``KEYUP`` events and exposes them
as frame-aligned *control signals* plus discrete *actions*.

The tactical scene feeds every pygame event into an :class:`InputLayer`, then
asks the layer to drain one frame's worth of work. This keeps key handling
separated from simulation, so rotation/thrust/reverse semantics can be unit
tested at the input boundary without constructing a full game state.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pygame


# ---------------------------------------------------------------------------
# Key constants
# ---------------------------------------------------------------------------
# Derived from pygame so nothing is hard-coded, and reused across scenes.
KEY_LEFT = pygame.K_LEFT
KEY_RIGHT = pygame.K_RIGHT
KEY_UP = pygame.K_UP
KEY_DOWN = pygame.K_DOWN

# Discrete-binding keys (edge-triggered actions). Space is a hold-to-fire key.
KEY_SPACE = pygame.K_SPACE
KEY_M = pygame.K_m
KEY_J = pygame.K_j
KEY_L = pygame.K_l
KEY_T = pygame.K_t
KEY_ESCAPE = pygame.K_ESCAPE

_CONTROL_KEYS = frozenset({KEY_LEFT, KEY_RIGHT, KEY_UP, KEY_DOWN})
ACTION_KEYS = frozenset({KEY_SPACE, KEY_M, KEY_J, KEY_L, KEY_T, KEY_ESCAPE})


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
class ControlFrame:
    """One frame of level control signals for the tactical ship.

    ``thrust``, ``left`` and ``right`` are *level* (a key currently held).
    ``reverse_edge`` is an *edge* signal describing whether the reverse-course
    key was physically pressed during this frame (not merely held).
    """

    __slots__ = ("thrust", "left", "right", "reverse_edge")

    def __init__(self, thrust=False, left=False, right=False, reverse_edge=False):
        self.thrust = bool(thrust)
        self.left = bool(left)
        self.right = bool(right)
        self.reverse_edge = bool(reverse_edge)


@dataclass(frozen=True)
class Action:
    """A discrete, frame-aligned user action emitted by the input layer.

    ``kind`` is one of: ``fire``, ``open_map``, ``jump``, ``land``, ``scan``,
    ``exit_game``. Payloads are reserved for later stages.
    """

    kind: str = ""


# ---------------------------------------------------------------------------
# Input layer
# ---------------------------------------------------------------------------
@dataclass
class InputLayer:
    """Accumulates raw key events and drains them into per-frame controls."""

    _held: set = field(default_factory=set)
    _rising: set = field(default_factory=set)
    locked: bool = False

    def feed_event(self, event) -> None:
        """Record a single pygame key event for the current real frame.

        Only ``KEYDOWN``/``KEYUP`` are relevant; any other event type is
        ignored so mouse and UI events never disturb the tactical layer.
        """
        if event.type not in (pygame.KEYDOWN, pygame.KEYUP):
            return

        key = event.key
        if event.type == pygame.KEYDOWN:
            # Only keys that drive a control or an action are tracked. This
            # keeps stray keys (future mouse/UI bindings) from leaking empty
            # actions out of drain_frame.
            if key in _CONTROL_KEYS or key in ACTION_KEYS:
                # A rising edge is a press we have not yet seen released this frame.
                if key not in self._held and key not in self._rising:
                    self._rising.add(key)
                self._held.add(key)
        else:  # KEYUP
            self._held.discard(key)
            self._rising.discard(key)

    def drain_frame(self):
        """Return the controls/actions for one drained frame.

        Returns a ``(control_frame, actions)`` tuple. When input is locked
        (a jump is in progress) the control frame is ``None`` and no actions
        are returned; any queued actions are discarded so they cannot leak to
        the following frame.
        """
        if self.locked:
            # Discard this frame's edges: while locked every control and
            # binding is suppressed, so nothing should linger.
            self._rising.clear()
            return None, []

        controls = ControlFrame(
            thrust=KEY_UP in self._held,
            left=KEY_LEFT in self._held,
            right=KEY_RIGHT in self._held,
            reverse_edge=KEY_DOWN in self._rising,
        )

        # Action bindings split into two behaviours:
        #   * space is hold-to-fire: it emits a fire action every frame it is
        #     held (tracked via _held, which persists across drains).
        #   * the other bindings are edge-triggered: they emit once per rising
        #     edge (tracked via _rising, which is cleared each drain).
        actions = []
        if KEY_SPACE in self._held:
            actions.append(Action("fire"))
        for key in (k for k in self._rising if k in ACTION_KEYS and k != KEY_SPACE):
            actions.append(self._pop_action(key))

        # Rising edges belong to a single real frame: clear them so a held key
        # does not keep re-triggering the edge on subsequent drains.
        self._rising.clear()
        return controls, actions

    # ------------------------------------------------------------------
    def _pop_action(self, key: int) -> Action:
        """Build a discrete action from a rising edge on an edge-triggered binding.

        ``drain_frame`` handles hold-to-fire (space) separately; every key that
        reaches here is one of the strictly edge-triggered bindings below.
        """
        mapping = {
            KEY_M: "open_map",
            KEY_J: "jump",
            KEY_L: "land",
            KEY_T: "scan",
            KEY_ESCAPE: "exit_game",
        }
        # Defensive: an unknown binding yields an empty action rather than
        # crashing, so future key additions can't silently break dispatch.
        return Action(mapping.get(key, ""))

    # ------------------------------------------------------------------
    def reset_held_state(self) -> None:
        """Forget every key this layer believes is currently held down.

        A modal that is opened *by* a key press never sees that key's release: the
        press goes to the tactical layer, the modal is pushed during the same
        frame, and the matching ``KEYUP`` arrives on the modal, which has no input
        layer of its own to feed. The layer is then left holding a phantom key, so
        the next press of that key produces no rising edge at all — the symptom is
        "``L`` only works every other time", one frame after leaving the
        spaceport. Any stage that pushes a modal on a keypress (Stage 13's game
        over included) must follow it with this reset.
        """
        self._held.clear()
        self._rising.clear()

    # ------------------------------------------------------------------
    def lock_input(self) -> None:
        """Suppress all controls and actions (used while a jump animates)."""
        self.locked = True

    def unlock_input(self) -> None:
        """Re-enable controls after an input-locked period ends."""
        self.locked = False
