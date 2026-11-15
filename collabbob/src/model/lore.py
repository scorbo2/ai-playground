"""World lore: a file-backed pool of one-line system descriptions.

The spec keeps lore out of the config files (they would otherwise carry 26
strings per difficulty) and puts it in ``resources/lore.txt``, one entry per
line. An entry may contain the replaceable tag ``(System)`` — case
insensitive, zero or more times — which gets replaced with the system's name
when the line is assigned to that system. A tagless line is a valid, if
generic, entry.

Lore is assigned to systems **once at new-game start** (the spec is explicit
that re-rolling per visit is confusing), so a seeded run gets the same
system-to-lore mapping every time. With 26+ entries in the file the draw is
*without* replacement, so the world's systems get unique lines; with fewer
entries, duplicates are drawn with replacement — the spec calls both out
as acceptable.
"""

from __future__ import annotations

import os
import random
import re
from pathlib import Path
from typing import Mapping, Sequence

from src.config import GAME_ROOT

__all__ = ["LORE_FILE", "LoreBook", "assign_lore", "load_lore", "render_system_tag"]

# ``GAME_ROOT`` is the project's single path authority (src/config.py); deriving
# the root a second time here is how a moved package ends up reading a lore file
# that no longer exists while the title screen background still loads fine.
LORE_FILE = os.path.join(GAME_ROOT, "resources", "lore.txt")

# Case-insensitive everywhere: "(System)", "(SYSTEM)", "(sYsTeM)" all substitute.
_SYSTEM_TAG_RE = re.compile(r"\(system\)", re.IGNORECASE)


def load_lore(path: Path | str) -> list[str]:
    """Read the lore pool from a file; fatal if it is missing, unreadable, empty.

    The spec is explicit about the failure contract: a missing, unreadable,
    or empty lore file is a fatal startup error, not a graceful fallback to
    "no lore". Callers convert the raised ``RuntimeError`` into the project's
    stderr-and-exit treatment, the same way a bad config is reported.
    """
    path = Path(path)
    if not path.exists():
        raise RuntimeError(f"lore file not found: {path.name}")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"lore file is unreadable: {path.name} ({exc})") from exc
    entries = [line.strip() for line in text.splitlines() if line.strip()]
    if not entries:
        raise RuntimeError(f"lore file is empty: {path.name}")
    return entries


def render_system_tag(entry: str, system_name: str) -> str:
    """Substitute every ``(System)`` occurrence (any case) with `system_name`.

    Argument order is ``(entry, system_name)``, which is worth stating because
    the swapped call is silent: substituting in a *system name* matches nothing
    and returns the name itself, so every system ends up "describing" itself.
    """
    return _SYSTEM_TAG_RE.sub(system_name, entry)


def assign_lore(
    system_names: Sequence[str],
    entries: Sequence[str],
    rng: "random.Random",
) -> dict[str, str]:
    """Render one final lore line per system, drawn once from the pool.

    * Fewer entries than systems → draw *with* replacement (the spec accepts
      duplicate lore in this case).
    * Enough entries (26+ for the shipped worlds) → draw *without*
      replacement so no two systems share a line.

    Iterates the systems in the order given (the graph's canonical order),
    so the same seed always assigns the same line to the same system.
    """
    if not entries:
        raise ValueError("cannot assign lore from an empty pool")
    if not system_names:
        return {}

    draw_with_replacement = len(system_names) > len(entries)
    pool: list[str] = [] if draw_with_replacement else list(entries)

    lines: list[str] = []
    for name in system_names:
        if draw_with_replacement:
            entry = entries[rng.randrange(len(entries))]
        else:
            entry = pool.pop(rng.randrange(len(pool)))
        lines.append(render_system_tag(entry, name))
    return dict(zip(system_names, lines))


class LoreBook:
    """The world's one lore line per system, decided once per new game."""

    def __init__(self, lines: Mapping[str, str]) -> None:
        self._lines = dict(lines)

    @classmethod
    def for_world(
        cls, system_names: Sequence[str], rng: "random.Random", path: "str | None" = None
    ) -> "LoreBook":
        """Build the book for one world: load the pool, draw once per system.

        ``path`` defaults to :data:`LORE_FILE` **resolved at call time**, not bound
        at definition time: a default that is captured once is a constant in
        disguise, and a test that redirects the module constant would find the real
        shipped pool staring back at it.

        Raises ``RuntimeError`` (not a silent empty book) when the pool file is
        missing, unreadable, or empty — see :func:`load_lore` for the contract
        and DECISIONS.md for why that is fatal rather than cosmetic.
        """
        return cls(assign_lore(system_names, load_lore(LORE_FILE if path is None else path), rng))

    def line_for(self, system_name: str) -> str:
        """The world's lore line for `system_name`.

        A system outside the book (a hand-built test world, a future
        save-game from another world) gets an empty string rather than a
        crash: the spaceport renders its own name prominently, so missing
        flavour text is cosmetic and should never end a run.
        """
        return self._lines.get(system_name, "")

    def __len__(self) -> int:
        return len(self._lines)
