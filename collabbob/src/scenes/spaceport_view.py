"""The spaceport modal (Stage 9): contracts, upgrades, refuel, repair, lore.

Raised by ``L`` inside landing range, it fills the whole window and pauses the
simulation underneath it (``SceneManager`` routes ``update()``/``handle_event()``
to the top scene only — the same modal semantic the system map relies on).

Split of responsibilities, mirroring the map view:

* **Rules** live in the model. What can be accepted, what a job costs, whether a
  purchase would take the balance to the credit floor, whether a fare has already
  been paid — all of that is :class:`~src.model.game_state.GameState` and
  :mod:`src.model.economy`. This scene never does arithmetic on the player's money.
* **Copy and geometry** live here as pure functions that the renderer actually
  executes (the Stage 6 precedent). A test that asserts on
  :func:`contract_terms_line` is asserting on the pixels.
* **Pixels and buttons** live here: pygame_gui gives the clickable affordances,
  everything else is drawn text, which keeps the element count at ~20 buttons
  instead of 40 labels whose text would then have to be kept in sync by hand.

The board is a snapshot: the offers come from the :class:`PortVisit` rolled when
the player landed, so redrawing the screen cannot re-roll the stock, and leaving
the port discards whatever was not bought.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame
import pygame_gui

from src.fonts import game_font, render_text
from src.model.economy import (
    LandingReport,
    Mission,
    PortVisit,
    format_credits,
    mission_payload_text,
)
from src.model.game_state import GameState
from src.model.lore import LoreBook
from src.model.ship_upgrades import UpgradeOffer, upgrade_text
from src.scene_manager import Scene

if TYPE_CHECKING:
    from src.end_of_run import EndOfRun
    from src.scene_manager import SceneManager

SCREEN_SIZE = (1024, 768)

# -- geometry (fixed, so "everything fits" is a fact about the constants) -----
MARGIN = 24
TITLE_RECT = pygame.Rect(MARGIN, 12, 640, 34)
CREDITS_RECT = pygame.Rect(SCREEN_SIZE[0] - MARGIN - 260, 12, 260, 34)
LORE_RECT = pygame.Rect(MARGIN, 52, SCREEN_SIZE[0] - 2 * MARGIN, 46)

BODY_TOP = 104
BODY_BOTTOM = 646  # nothing in the body may cross this; the message line sits below

LEFT_X = MARGIN
LEFT_WIDTH = 540
RIGHT_X = 596
RIGHT_WIDTH = 404

SECTION_HEADER_HEIGHT = 22
ROWS_TOP = BODY_TOP + SECTION_HEADER_HEIGHT + 6  # 132

CONTRACT_ROW_HEIGHT = 50
CONTRACT_BUTTON_WIDTH = 88
CONTRACT_BUTTON_HEIGHT = 30
CONTRACT_TEXT_WIDTH = LEFT_WIDTH - CONTRACT_BUTTON_WIDTH - 14

UPGRADE_ROW_HEIGHT = 38
UPGRADE_BUTTON_WIDTH = 96
UPGRADE_BUTTON_HEIGHT = 30
UPGRADE_TEXT_WIDTH = RIGHT_WIDTH - UPGRADE_BUTTON_WIDTH - 14
# Seven stats exist, so seven rows is the worst case; the services block is
# placed below that worst case rather than chasing however many rows appeared.
UPGRADE_ROWS_CAPACITY = 7
SERVICES_TOP = ROWS_TOP + UPGRADE_ROWS_CAPACITY * UPGRADE_ROW_HEIGHT + 16
SERVICE_BUTTON_WIDTH = RIGHT_WIDTH
SERVICE_BUTTON_HEIGHT = 36

MESSAGE_RECT = pygame.Rect(MARGIN, 654, SCREEN_SIZE[0] - 2 * MARGIN, 26)
HINT_RECT = pygame.Rect(MARGIN, 744, SCREEN_SIZE[0] - 2 * MARGIN, 20)
LAUNCH_WIDTH, LAUNCH_HEIGHT = 220, 52
LAUNCH_RECT = pygame.Rect(
    (SCREEN_SIZE[0] - LAUNCH_WIDTH) // 2, SCREEN_SIZE[1] - MARGIN - LAUNCH_HEIGHT,
    LAUNCH_WIDTH, LAUNCH_HEIGHT,
)

# -- type sizes ---------------------------------------------------------------
TITLE_SIZE = 26
HEADER_SIZE = 18
PAYLOAD_SIZE = 16
TERMS_SIZE = 14
LORE_SIZE = 15
MESSAGE_SIZE = 17
HINT_SIZE = 13


class PortPalette:
    """Presentation colours for the spaceport. In code, like the HUD and map."""

    background = (8, 10, 16)
    panel = (18, 22, 32)
    border = (96, 104, 122)
    title = (235, 240, 250)
    header = (150, 200, 160)
    text = (210, 220, 235)
    muted = (130, 140, 158)
    aboard = (120, 200, 130)
    credits = (240, 215, 140)
    lore = (150, 170, 200)
    message = (255, 240, 150)


# ---------------------------------------------------------------------------
# Pure layout: the renderer and the tests both call these
# ---------------------------------------------------------------------------
def contract_row_rect(index: int) -> "pygame.Rect":
    """The row box for contract `index` (0-based, top to bottom)."""
    return pygame.Rect(LEFT_X, ROWS_TOP + index * CONTRACT_ROW_HEIGHT,
                       LEFT_WIDTH, CONTRACT_ROW_HEIGHT)


def contract_button_rect(index: int) -> "pygame.Rect":
    """The Accept button for contract `index`, at the right edge of its row."""
    row = contract_row_rect(index)
    return pygame.Rect(
        row.right - CONTRACT_BUTTON_WIDTH,
        row.top + (row.height - CONTRACT_BUTTON_HEIGHT) // 2,
        CONTRACT_BUTTON_WIDTH,
        CONTRACT_BUTTON_HEIGHT,
    )


def upgrade_row_rect(index: int) -> "pygame.Rect":
    """The row box for upgrade offer `index`."""
    return pygame.Rect(RIGHT_X, ROWS_TOP + index * UPGRADE_ROW_HEIGHT,
                       RIGHT_WIDTH, UPGRADE_ROW_HEIGHT)


def upgrade_button_rect(index: int) -> "pygame.Rect":
    """The purchase button for upgrade offer `index`."""
    row = upgrade_row_rect(index)
    return pygame.Rect(
        row.right - UPGRADE_BUTTON_WIDTH,
        row.top + (row.height - UPGRADE_BUTTON_HEIGHT) // 2,
        UPGRADE_BUTTON_WIDTH,
        UPGRADE_BUTTON_HEIGHT,
    )


def refuel_button_rect() -> "pygame.Rect":
    return pygame.Rect(RIGHT_X, SERVICES_TOP + SECTION_HEADER_HEIGHT + 8,
                       SERVICE_BUTTON_WIDTH, SERVICE_BUTTON_HEIGHT)


def repair_button_rect() -> "pygame.Rect":
    return pygame.Rect(RIGHT_X, refuel_button_rect().bottom + 8,
                       SERVICE_BUTTON_WIDTH, SERVICE_BUTTON_HEIGHT)


def contracts_capacity() -> int:
    """How many contract rows fit between the header and the message line.

    The shipped configs top out at 10 offers (easy) and the box fits 10, so the
    overflow path below is unreachable in play — but a config raising
    ``economy.missions_max`` above the box must produce a truncated board and an
    honest "...and N more" note, not rows running under the Launch button.
    """
    return (BODY_BOTTOM - ROWS_TOP) // CONTRACT_ROW_HEIGHT


def upgrades_capacity() -> int:
    """Upgrade rows that fit above the services block (seven stats exist)."""
    return (SERVICES_TOP - ROWS_TOP) // UPGRADE_ROW_HEIGHT


MANIFEST_LINE_HEIGHT = 18


def manifest_top() -> int:
    return repair_button_rect().bottom + 14


def manifest_capacity() -> int:
    """Manifest lines that fit between the services block and the message line.

    The manifest is the one block whose size was never fixed by a config, so it
    is the one block that could grow into the message line. Bounding it by the
    geometry (rather than picking a number) keeps the message readable no matter
    how many contracts the player is carrying.
    """
    return (MESSAGE_RECT.top - 6 - (manifest_top() + SECTION_HEADER_HEIGHT + 4)) // MANIFEST_LINE_HEIGHT


def fit_text(text: str, size: int, max_width: int) -> str:
    """Clip `text` to `max_width` px at `size`, marking the cut with an ellipsis.

    Not decorative: cargo types and system names come from data, and the map
    view's first revision learned the hard way that an over-long label paints
    itself over its own row. Clipping here keeps one line per row, always.
    """
    font = game_font(size)
    if font.size(text)[0] <= max_width:
        return text
    while text and font.size(f"{text}...")[0] > max_width:
        text = text[:-1]
    return f"{text}..." if text else ""


def contract_payload_line(mission: Mission, accepted: bool) -> str:
    """First line of a contract row: where it goes, then what is in the crate.

    The destination leads because it is the part that must survive clipping. A
    mixed job's payload runs to ~50 characters in a ~45-character column, and a
    row that clips to "10 units of colony supplies; 4 p..." while hiding the
    destination is a row the player cannot price: the far bonus and the fare are
    meaningless without knowing where the trip ends.
    """
    prefix = "ABOARD  " if accepted else ""
    return f"{prefix}-> {mission.destination}: {mission_payload_text(mission)}"


def contract_terms_line(mission: Mission) -> str:
    """Second line: the lane, the far bonus, and the fare.

    The spec wants the far bonus shown even for a destination the player has
    never charted, so the hop count is stated plainly: it is a property of the
    lane, not of the player's maps.
    """
    jumps = "1 jump" if mission.distance == 1 else f"{mission.distance} jumps"
    bonus = "" if mission.far_bonus == 1.0 else f", far bonus x{mission.far_bonus:.1f}"
    return f"{jumps}{bonus} - fare {format_credits(mission.fare)} credits"


def upgrade_price_text(offer: UpgradeOffer) -> str:
    """The button caption: a price, not the word "Buy" (the price is the decision)."""
    return f"{format_credits(offer.cost)} cr"


def service_button_text(kind: str, amount: float, cost: float) -> str:
    """Caption for a port service button: what is bought and what it costs."""
    if cost <= 0:
        return "Full" if kind == "fuel" else "Intact"
    quantity = int(amount)
    if kind == "fuel":
        unit = "unit" if quantity == 1 else "units"
        return f"Refuel +{quantity} {unit} - {format_credits(cost)} cr"
    return f"Repair +{quantity} pts - {format_credits(cost)} cr"


def manifest_lines(game_state: GameState) -> tuple[str, ...]:
    """What is aboard, as far as the player can tell from the hold.

    A job already aboard has no Cancel button (the spec forbids cancelling), so
    the manifest exists to explain *why* the capacity line is what it is.
    """
    loads = game_state.carried_loads
    header = (
        f"Cargo {game_state.cargo_used}/{game_state.stats.cargo_room}   "
        f"Passengers {game_state.passengers_used}/{game_state.stats.passenger_space}"
    )
    if not loads:
        return (header, "Hold is empty.")
    lines = [header]
    for load in loads:
        payload = []
        if load.cargo_units:
            payload.append(f"{load.cargo_units} x {load.cargo_type}")
        if load.passengers:
            payload.append(f"{load.passengers} pax")
        lines.append(f"-> {load.destination}: {', '.join(payload)} for {format_credits(load.fare)}")
    return tuple(lines)


def delivery_message(report: LandingReport) -> str:
    """The spec's "a message appears" when cargo/passengers settle on arrival."""
    if not report.delivered_anything:
        return f"Welcome to {report.system}. Nothing here was yours to deliver."
    what = []
    if report.cargo_unloaded:
        unit = "unit" if report.cargo_unloaded == 1 else "units"
        what.append(f"{report.cargo_unloaded} cargo {unit}")
    if report.passengers_unloaded:
        word = "passenger" if report.passengers_unloaded == 1 else "passengers"
        what.append(f"{report.passengers_unloaded} {word}")
    return (
        f"Unloaded {' and '.join(what)} at {report.system}: "
        f"+{format_credits(report.credits_gained)} credits."
    )


def wrap_text(text: str, size: int, max_width: int, max_lines: int = 2) -> tuple[str, ...]:
    """Lore arrives as one line and the window is only so wide.

    Word-wrapped (never character-clipped): the pool runs to ~104 characters,
    which at 15px monospace is wider than the window.
    """
    font = game_font(size)
    lines: list[str] = []
    current = ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if not current or font.size(candidate)[0] <= max_width:
            current = candidate
            continue
        lines.append(current)
        current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = fit_text(lines[-1], size, max_width)
    return tuple(lines)


# ---------------------------------------------------------------------------
# The scene
# ---------------------------------------------------------------------------
class SpaceportView(Scene):
    """Full-screen spaceport modal: read the world, spend money, launch."""

    def __init__(
        self,
        visit: PortVisit,
        game_state: GameState,
        landing_report: LandingReport,
        lore_book: LoreBook,
        end_of_run: "EndOfRun",
    ) -> None:
        """Take the visit that was rolled when the player landed.

        No scene manager here: :meth:`on_enter` receives it, exactly as the map
        modal does. The lore comes from the world's book rather than a string so
        the scene cannot invent (or re-roll) a system's history.

        ``end_of_run`` is not decoration: this screen spends the player's money,
        and a purchase here can be the one that makes the next tank of fuel
        unaffordable. The credit endings must be re-checked after every
        transaction, and this scene is the only thing that sees a transaction —
        the tactical scene underneath is frozen while the modal is up, so a check
        left to the next frame of play would never run at all.
        """
        super().__init__()
        if visit is None or game_state is None:
            raise ValueError("SpaceportView needs the port visit and the game state")
        if end_of_run is None:
            raise ValueError(
                "SpaceportView needs the run's EndOfRun: buying an upgrade can be "
                "what bankrupts a run, and a port that cannot report it is a softlock"
            )
        self.visit = visit
        self.game_state = game_state
        self.landing_report = landing_report
        self.end_of_run = end_of_run
        self.lore_lines = wrap_text(
            lore_book.line_for(visit.system), LORE_SIZE, SCREEN_SIZE[0] - 2 * MARGIN
        )
        self.message = delivery_message(landing_report)

        # The board is sliced once, here, by the same capacities the layout uses.
        # Slicing separately in the row renderer and in the button builder is how
        # an Accept button ends up wired to a contract that is not on screen.
        self.contracts = visit.missions[: contracts_capacity()]
        self.upgrades = visit.upgrade_offers[: upgrades_capacity()]

        # Widgets are built in on_enter (a UIManager needs the display), and the
        # id -> widget maps are the only way a button event can be traced back to
        # the offer it belongs to.
        self._accept_buttons: "dict[pygame_gui.elements.UIButton, Mission]" = {}
        self._buy_buttons: "dict[pygame_gui.elements.UIButton, UpgradeOffer]" = {}
        self._launch_button = None
        self._refuel_button = None
        self._repair_button = None
        self._ui = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------
    def on_enter(self, manager: "SceneManager") -> None:
        super().on_enter(manager)
        # No theme argument: these buttons are the same pygame_gui defaults the
        # title screen and the difficulty dialog use, and a bespoke-styled
        # spaceport next to unstyled title buttons is an inconsistency, not a
        # design.
        self._ui = pygame_gui.UIManager(SCREEN_SIZE)
        self._build_buttons()
        # pygame_gui builds a widget's images during its *first update*, so a
        # draw before that first update paints a screen with no buttons at all
        # (the real loop happens to update before it draws; a screenshot script,
        # a test, or any future scene that draws first would not). One update at
        # build time makes "buttons exist" and "buttons are visible" the same
        # fact instead of two.
        self._ui.update(1.0 / 60.0)

    def on_exit(self) -> None:
        if self._ui is not None:
            self._ui.clear_and_reset()
        self._accept_buttons.clear()
        self._buy_buttons.clear()
        super().on_exit()

    def _build_buttons(self) -> None:
        """Create one button per offer, plus services and Launch.

        Buttons are created once for the visit and then enabled/disabled as the
        player spends: recreating them on every transaction would move them
        around under the cursor mid-click.
        """
        for index, mission in enumerate(self.contracts):
            self._accept_buttons[
                pygame_gui.elements.UIButton(
                    relative_rect=contract_button_rect(index),
                    text="Accept",
                    manager=self._ui,
                )
            ] = mission

        for index, offer in enumerate(self.upgrades):
            self._buy_buttons[
                pygame_gui.elements.UIButton(
                    relative_rect=upgrade_button_rect(index),
                    text=upgrade_price_text(offer),
                    manager=self._ui,
                )
            ] = offer

        self._refuel_button = pygame_gui.elements.UIButton(
            relative_rect=refuel_button_rect(), text="Refuel", manager=self._ui
        )
        self._repair_button = pygame_gui.elements.UIButton(
            relative_rect=repair_button_rect(), text="Repair", manager=self._ui
        )
        self._launch_button = pygame_gui.elements.UIButton(
            relative_rect=LAUNCH_RECT, text="Launch!", manager=self._ui
        )
        self._sync_buttons()

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------
    def handle_event(self, event) -> None:
        """Buttons, QUIT, and ESC. Nothing else leaves this screen.

        ``ESC`` launches. The spec names only the "Launch!" button, but the
        README already promises that ESC closes whatever modal is open, and a
        modal with nothing to cancel should not look like it has swallowed the
        keyboard. See DECISIONS.md.
        """
        if self._manager is None or self._ui is None:
            return
        self._ui.process_events(event)

        if event.type == pygame.QUIT:
            self._manager.quit()
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._launch()
            return
        if event.type != pygame_gui.UI_BUTTON_PRESSED:
            return

        element = event.ui_element
        if element is self._launch_button:
            self._launch()
        elif element in self._accept_buttons:
            self._accept(self._accept_buttons[element])
        elif element in self._buy_buttons:
            self._buy_upgrade(self._buy_buttons[element])
        elif element is self._refuel_button:
            self._report(self.game_state.buy_fuel())
        elif element is self._repair_button:
            self._report(self.game_state.repair_armor())

    def _accept(self, mission: Mission) -> None:
        result = self.game_state.accept_mission(mission)
        self._report(result)

    def _buy_upgrade(self, offer: UpgradeOffer) -> None:
        # The price shown is the offer's, but the model recomputes it from the
        # config curve and refuses a stale level, so this call cannot be talked
        # into a second level one at the old price.
        self._report(self.game_state.purchase_upgrade(offer))

    def _report(self, result) -> None:
        """Show the outcome, and beep only when something actually happened.

        Then ask whether the balance the transaction just changed has ended the
        run. A player who spends their last credits on a cargo upgrade with a dry
        tank is bankrupt on this frame, not on the next one they cannot reach: the
        run's scenes are frozen behind this modal.
        """
        self.message = result.reason
        if result.succeeded:
            self._manager.audio.play_confirm()
        self._sync_buttons()
        self.end_of_run.poll_at_port()

    def _launch(self) -> None:
        """Leave the port: the model arms the immunity window, then we pop.

        The order matters. ``game_state.launch()`` is what flips ``is_landed``
        false, and :class:`~src.scenes.game_scene.GameScene` watches that flag to
        discard this visit's offers; popping first would let a frame of tactical
        simulation run with the old board still in hand.
        """
        if self._manager is None:
            return
        self._manager.audio.play_confirm()
        self.game_state.launch()
        self._manager.pop()

    # ------------------------------------------------------------------
    # Update / draw
    # ------------------------------------------------------------------
    def update(self) -> None:
        """Drive the UI manager; the tactical simulation stays paused below."""
        if self._ui is not None:
            self._ui.update(1.0 / 60.0)

    def draw(self, surface: "pygame.Surface") -> None:
        """Repaint the whole window. A modal that clears half the screen is a window."""
        surface.fill(PortPalette.background)
        self._draw_header(surface)
        self._draw_contracts(surface)
        self._draw_upgrades(surface)
        self._draw_services(surface)
        self._draw_manifest(surface)
        self._draw_footer(surface)
        self._ui.draw_ui(surface)

    def _draw_header(self, surface: "pygame.Surface") -> None:
        self._blit(surface, self.visit.system.upper(), TITLE_SIZE, TITLE_RECT,
                   PortPalette.title, bold=True)
        self._blit(surface, "SPACEPORT", TITLE_SIZE,
                   TITLE_RECT.move(TITLE_RECT.width + 18, 0), PortPalette.header)
        credits_line = f"Credits {format_credits(self.game_state.credits)}"
        render = render_text(credits_line, HEADER_SIZE, PortPalette.credits)
        surface.blit(render, render.get_rect(topright=CREDITS_RECT.topright))
        for offset, line in enumerate(self.lore_lines):
            self._blit(surface, line, LORE_SIZE, LORE_RECT.move(0, offset * 20),
                       PortPalette.lore)

    def _draw_contracts(self, surface: "pygame.Surface") -> None:
        self._section_header(surface, "TRANSPORT CONTRACTS", LEFT_X, BODY_TOP)
        for index, mission in enumerate(self.contracts):
            row = contract_row_rect(index)
            accepted = self.game_state.offer_is_accepted(mission.offer_id)
            self._panel_for(surface, row)
            self._blit(surface, contract_payload_line(mission, accepted), PAYLOAD_SIZE,
                       pygame.Rect(row.left + 8, row.top + 6, CONTRACT_TEXT_WIDTH, 20),
                       PortPalette.aboard if accepted else PortPalette.text)
            self._blit(surface, contract_terms_line(mission), TERMS_SIZE,
                       pygame.Rect(row.left + 8, row.top + 28, CONTRACT_TEXT_WIDTH, 18),
                       PortPalette.muted)
        hidden = len(self.visit.missions) - len(self.contracts)
        if hidden > 0:
            # Stays inside the body: an overflow note that runs under Launch is a
            # layout bug wearing a helpful caption.
            self._blit(surface, f"...and {hidden} more contract(s) this port cannot show.",
                       TERMS_SIZE,
                       pygame.Rect(LEFT_X, ROWS_TOP + len(self.contracts) * CONTRACT_ROW_HEIGHT,
                                   LEFT_WIDTH, 14),
                       PortPalette.muted)

    def _draw_upgrades(self, surface: "pygame.Surface") -> None:
        self._section_header(surface, "SHIP UPGRADES", RIGHT_X, BODY_TOP)
        steps = self.game_state.upgrade_steps
        for index, offer in enumerate(self.upgrades):
            row = upgrade_row_rect(index)
            self._panel_for(surface, row)
            self._blit(surface, upgrade_text(offer, float(steps[offer.stat])), PAYLOAD_SIZE,
                       pygame.Rect(row.left + 8, row.top + (row.height - 20) // 2,
                                   UPGRADE_TEXT_WIDTH, 20), PortPalette.text)
        hidden = len(self.visit.upgrade_offers) - len(self.upgrades)
        if hidden > 0:
            self._blit(surface, f"...and {hidden} more upgrade(s) this port cannot show.",
                       TERMS_SIZE,
                       pygame.Rect(RIGHT_X, ROWS_TOP + len(self.upgrades) * UPGRADE_ROW_HEIGHT,
                                   RIGHT_WIDTH, 18),
                       PortPalette.muted)
        elif not self.upgrades:
            self._blit(surface, "Nothing on offer here.", TERMS_SIZE,
                       pygame.Rect(RIGHT_X, ROWS_TOP, RIGHT_WIDTH, 18), PortPalette.muted)

    def _draw_services(self, surface: "pygame.Surface") -> None:
        self._section_header(surface, "PORT SERVICES", RIGHT_X, SERVICES_TOP)

    def _draw_manifest(self, surface: "pygame.Surface") -> None:
        top = manifest_top()
        self._section_header(surface, "MANIFEST", RIGHT_X, top)
        lines = manifest_lines(self.game_state)
        visible = lines[: manifest_capacity()]
        for offset, line in enumerate(visible):
            self._blit(surface, line, TERMS_SIZE,
                       pygame.Rect(RIGHT_X,
                                   top + SECTION_HEADER_HEIGHT + 4 + offset * MANIFEST_LINE_HEIGHT,
                                   RIGHT_WIDTH, MANIFEST_LINE_HEIGHT), PortPalette.muted)
        if len(lines) > len(visible):
            self._blit(surface, f"...and {len(lines) - len(visible)} more aboard.", TERMS_SIZE,
                       pygame.Rect(RIGHT_X,
                                   top + SECTION_HEADER_HEIGHT + 4 + len(visible) * MANIFEST_LINE_HEIGHT,
                                   RIGHT_WIDTH, MANIFEST_LINE_HEIGHT), PortPalette.muted)

    def _draw_footer(self, surface: "pygame.Surface") -> None:
        self._blit(surface, self.message, MESSAGE_SIZE, MESSAGE_RECT, PortPalette.message)
        self._blit(surface, "ESC or Launch! leaves the port. Accepted jobs cannot be cancelled.",
                   HINT_SIZE, HINT_RECT, PortPalette.muted)

    # -- bits and pieces --------------------------------------------------
    def _section_header(self, surface: "pygame.Surface", text: str, x: int, y: int) -> None:
        self._blit(surface, text, HEADER_SIZE, pygame.Rect(x, y, 400, SECTION_HEADER_HEIGHT),
                   PortPalette.header, bold=True)

    def _panel_for(self, surface: "pygame.Surface", rect: "pygame.Rect") -> None:
        """A flat panel behind one offer row, so rows read as separate choices."""
        pygame.draw.rect(surface, PortPalette.panel, rect)
        pygame.draw.rect(surface, PortPalette.border, rect, 1)

    def _blit(
        self, surface: "pygame.Surface", text: str, size: int, rect: "pygame.Rect",
        color: "tuple[int, int, int]", bold: bool = False,
    ) -> None:
        """Draw one clipped line of text inside `rect`."""
        surface.blit(
            render_text(fit_text(text, size, rect.width), size, color, bold=bold),
            (rect.left, rect.top),
        )

    @staticmethod
    def _set_enabled(button: "pygame_gui.elements.UIButton", enabled: bool) -> None:
        """Enable or disable a button (pygame_gui offers two methods, not a flag)."""
        if button is None:
            return
        button.enable() if enabled else button.disable()

    def _sync_buttons(self) -> None:
        """Refresh captions and enabled states after every transaction.

        Read entirely from the model: whatever the hold, tank, hull and balance
        say is what the buttons say, so a caption cannot promise a price the
        model will not honour.
        """
        for button, mission in self._accept_buttons.items():
            if self.game_state.offer_is_accepted(mission.offer_id):
                button.set_text("Aboard")
                button.disable()

        for button, offer in self._buy_buttons.items():
            if not self.game_state.upgrade_offer_is_available(offer):
                button.set_text("Done")
                button.disable()
            else:
                # Grey out what the player cannot pay for. The model is asked,
                # not the price tag: a caption that decides on its own maths is a
                # caption that can disagree with the refusal text.
                self._set_enabled(button, self.game_state.can_afford(offer.cost))

        state = self.game_state
        self._set_enabled(self._refuel_button, self._service_is_live(
            state.fuel_room, state.fuel_top_up_cost()
        ))
        self._refuel_button.set_text(
            service_button_text("fuel", state.fuel_room, state.fuel_top_up_cost())
        )
        self._set_enabled(self._repair_button, self._service_is_live(
            state.armor_damage, state.repair_top_up_cost()
        ))
        self._repair_button.set_text(
            service_button_text("armor", state.armor_damage, state.repair_top_up_cost())
        )

    def _service_is_live(self, quantity: float, cost: float) -> bool:
        """Whether a service button should be clickable right now.

        The affordability half of this test is the model's own
        :meth:`~src.model.game_state.GameState.can_afford`, so a caption and a
        refusal cannot disagree about what the player can pay for.
        """
        return quantity > 0 and self.game_state.can_afford(cost)
