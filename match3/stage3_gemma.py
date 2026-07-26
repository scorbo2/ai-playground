"""
Match 3 - A pygame-ce port of the classic match-3 browser game.

Reverse-engineered from Match3.html. All game rules, scoring, colors,
dimensions, and animations are preserved from the original.
"""

import os
import sys
import math
import random
import pygame

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BOARD_SIZE = 8
CELL_SIZE = 60
TOKEN_SIZE = 50
TOKEN_OFFSET = (CELL_SIZE - TOKEN_SIZE) // 2  # 5px centering offset

# Board geometry
BOARD_PIXELS = BOARD_SIZE * CELL_SIZE  # 480

# Layout (matching the original HTML/CSS pixel values)
TITLE_WIDTH = 720          # (8*60) + 40 + 200
TITLE_HEIGHT = 40          # 24px font + 10px padding top + 10px padding bottom - ~4px line-height adjustment
TITLE_MARGIN_BOTTOM = 40
SIDEBAR_WIDTH = 200
SIDEBAR_HEIGHT = BOARD_PIXELS  # 480
SIDEBAR_PADDING = 20
SIDEBAR_GAP = 20            # gap between sidebar labels
PADDING = 20                # window edge padding

WINDOW_WIDTH = PADDING * 2 + TITLE_WIDTH
WINDOW_HEIGHT = PADDING * 2 + TITLE_HEIGHT + TITLE_MARGIN_BOTTOM + SIDEBAR_HEIGHT

# Color palette (hex from original CSS)
COLORS = {
    'red':    pygame.Color('#ff0000'),
    'green':  pygame.Color('#00ff00'),
    'blue':   pygame.Color('#0000ff'),
    'orange': pygame.Color('#ffa500'),
    'yellow': pygame.Color('#ffff00'),
    'pink':   pygame.Color('#ffc0cb'),
}
COLOR_KEYS = list(COLORS.keys())

# UI colors
BG_COLOR = pygame.Color('#e0f0ff')
BORDER_THICK = pygame.Color('#444444')
BORDER_THIN = pygame.Color('#cccccc')
BORDER_THICK_WIDTH = 5
BORDER_THIN_WIDTH = 1
TEXT_WHITE = pygame.Color('#ffffff')
SELECTED_BORDER = pygame.Color('#90ee90')
SELECTED_BG = pygame.Color('#006400')
OPTION_BORDER = pygame.Color('#90ee90')
OPTION_BG = pygame.Color('#444444')
INVALID_BORDER = pygame.Color('#ffcccb')
INVALID_BG = pygame.Color('#8b0000')
RED_BORDER_COLOR = pygame.Color('#8b0000')
NEGATIVE_SCORE_COLOR = pygame.Color('#ffcccb')
BUTTON_BG = pygame.Color('#444444')
BUTTON_HOVER_BG = pygame.Color('#666666')

# Animation timing (ms)
SWAP_DURATION = 400
REMOVAL_DURATION = 200
GRAVITY_DURATION = 200
INVALID_FLASH_DURATION = 300
PARTICLE_DURATION = 600
FLOAT_TEXT_DURATION = 2000
LEVEL_COMPLETE_DURATION = 2000
LEVEL_BEGIN_DURATION = 1500

# Particle config
PARTICLES_PER_CELL = 40
PARTICLE_SIZE = 4
PARTICLE_MIN_DIST = 20
PARTICLE_MAX_DIST = 80  # 60+20 from original

# Scoring thresholds
INITIAL_THRESHOLD = 100
THRESHOLD_INCREMENT = 50

# Sound event names (mapped to sfx files)
SFX_MATCH = 'match.wav'
SFX_MATCH_PLUS = 'match_plus.wav'
SFX_MATCH_CHAIN = 'match_chain.wav'
SFX_BEGIN = 'begin.wav'
SFX_MATCH_RED = 'match_red.wav'

# Game states
STATE_IDLE = 'idle'
STATE_SWAP_ANIM = 'swap_anim'
STATE_MATCH = 'match'
STATE_REMOVE_ANIM = 'remove_anim'
STATE_GRAVITY_ANIM = 'gravity_anim'
STATE_CHAIN_WAIT = 'chain_wait'
STATE_LEVEL_COMPLETE = 'level_complete'
STATE_LEVEL_BEGIN = 'level_begin'
STATE_GAME_OVER = 'game_over'


# ---------------------------------------------------------------------------
# Particle - explosion effect for matched tokens
# ---------------------------------------------------------------------------

class Particle:
    """A single particle in an explosion effect."""

    def __init__(self, x, y, color):
        self.start_x = x
        self.start_y = y
        self.color = color
        angle = random.uniform(0, math.pi * 2)
        dist = random.uniform(PARTICLE_MIN_DIST, PARTICLE_MAX_DIST)
        self.dx = math.cos(angle) * dist
        self.dy = math.sin(angle) * dist
        self.elapsed = 0.0

    def update(self, dt_ms):
        self.elapsed += dt_ms

    @property
    def alive(self):
        return self.elapsed < PARTICLE_DURATION

    @property
    def progress(self):
        return min(self.elapsed / PARTICLE_DURATION, 1.0)

    def draw(self, surface, board_offset_x, board_offset_y):
        t = self.progress
        alpha = int(255 * (1 - t))
        x = self.start_x + self.dx * t
        y = self.start_y + self.dy * t
        px = board_offset_x + x
        py = board_offset_y + y
        # Draw with alpha blending
        img = pygame.Surface((PARTICLE_SIZE, PARTICLE_SIZE), pygame.SRCALPHA)
        color_rgba = (self.color.r, self.color.g, self.color.b, alpha)
        pygame.draw.circle(img, color_rgba,
                           (PARTICLE_SIZE // 2, PARTICLE_SIZE // 2),
                           PARTICLE_SIZE // 2)
        surface.blit(img, (px - PARTICLE_SIZE // 2, py - PARTICLE_SIZE // 2))


# ---------------------------------------------------------------------------
# FloatingText - animated score feedback text
# ---------------------------------------------------------------------------

class FloatingText:
    """Text that floats upward and fades out."""

    def __init__(self, text, color, x, y):
        self.text = text
        self.color = pygame.Color(color) if not isinstance(color, pygame.Color) else color
        self.x = x
        self.y = y
        self.elapsed = 0.0
        self.font = pygame.font.SysFont('Arial', 48, bold=True)

    def update(self, dt_ms):
        self.elapsed += dt_ms

    @property
    def alive(self):
        return self.elapsed < FLOAT_TEXT_DURATION

    @property
    def progress(self):
        return min(self.elapsed / FLOAT_TEXT_DURATION, 1.0)

    def draw(self, surface, board_offset_x, board_offset_y):
        t = self.progress
        alpha = int(255 * (1 - t))
        # Float upward: from center to -200px offset
        dy = -200 * t
        sx = board_offset_x + self.x
        sy = board_offset_y + self.y + dy

        # Use SRCALPHA surface for alpha-blended text
        rendered = self.font.render(self.text, True, self.color)
        rendered.set_alpha(alpha)
        rect = rendered.get_rect(center=(sx, sy))
        surface.blit(rendered, rect)


# ---------------------------------------------------------------------------
# Token - a single game piece on the board
# ---------------------------------------------------------------------------

class Token:
    """
    Represents a colored token on the board.

    Tracks both grid position (row, col) and render position (x, y) so that
    tokens can be animated independently of the logical board state.
    """

    def __init__(self, row, col, color, magical_type=None):
        self.row = row
        self.col = col
        self.color = color
        self.magical_type = magical_type  # 'horizontal', 'vertical', or None
        self.x = col * CELL_SIZE + TOKEN_OFFSET
        self.y = row * CELL_SIZE + TOKEN_OFFSET
        self.opacity = 255
        self.fading = False

    @property
    def target_x(self):
        return self.col * CELL_SIZE + TOKEN_OFFSET

    @property
    def target_y(self):
        return self.row * CELL_SIZE + TOKEN_OFFSET

    @property
    def visible(self):
        return self.opacity > 0

    def set_fade(self):
        self.fading = True

    def update_remove(self, dt_ms):
        """Fade out during removal animation."""
        if self.fading:
            self.opacity = max(0, self.opacity - 255 * dt_ms / REMOVAL_DURATION)

    def update_gravity(self, dt_ms):
        """
        Move toward target position during gravity animation.

        Uses a fixed speed derived from the animation duration so tokens
        fall at a visually consistent rate regardless of distance.
        """
        speed = CELL_SIZE * BOARD_SIZE * dt_ms / GRAVITY_DURATION
        dx = self.target_x - self.x
        dy = self.target_y - self.y

        if abs(dx) > 0.5:
            self.x += math.copysign(min(abs(dx), speed), dx)
        if abs(dy) > 0.5:
            self.y += math.copysign(min(abs(dy), speed), dy)

        # Snap when close enough
        if abs(dx) <= 0.5 and abs(dy) <= 0.5:
            self.x = self.target_x
            self.y = self.target_y

    def update_swap(self, dt_ms, start_x, start_y, start_time):
        """Linear interpolation for swap animation."""
        t = min((pygame.time.get_ticks() - start_time) / SWAP_DURATION, 1.0)
        self.x = start_x + (self.target_x - start_x) * t
        self.y = start_y + (self.target_y - start_y) * t

    def draw(self, surface, offset_x, offset_y):
        if not self.visible:
            return

        # Look up the actual pygame.Color from the string key
        pg_color = COLORS.get(self.color, TEXT_WHITE)

        # Draw token with opacity
        img = pygame.Surface((TOKEN_SIZE, TOKEN_SIZE), pygame.SRCALPHA)
        color_with_alpha = (pg_color.r, pg_color.g, pg_color.b, self.opacity)
        pygame.draw.circle(img, color_with_alpha,
                               (TOKEN_SIZE // 2, TOKEN_SIZE // 2),
                               TOKEN_SIZE // 2)

        # Draw magical stripe if applicable
        if self.magical_type:
            stripe_color = (TEXT_WHITE.r, TEXT_WHITE.g, TEXT_WHITE.b, self.opacity)
            if self.magical_type == 'horizontal':
                pygame.draw.rect(img, stripe_color, 
                                 (0, TOKEN_SIZE // 2 - 4, TOKEN_SIZE, 8))
            elif self.magical_type == 'vertical':
                pygame.draw.rect(img, stripe_color, 
                                 (TOKEN_SIZE // 2 - 4, 0, 8, TOKEN_SIZE))

        # White border
        if self.opacity > 0:
            border_color = (TEXT_WHITE.r, TEXT_WHITE.g, TEXT_WHITE.b, self.opacity)
            pygame.draw.circle(img, border_color,
                               (TOKEN_SIZE // 2, TOKEN_SIZE // 2),
                               TOKEN_SIZE // 2, 1)
        surface.blit(img, (offset_x + self.x, offset_y + self.y))


# ---------------------------------------------------------------------------
# Match3Game - Main game class
# ---------------------------------------------------------------------------

class Match3Game:
    """
    The main game controller.

    Manages the game state machine, board logic, input handling,
    and rendering. The state machine drives the animation pipeline:
    IDLE -> SWAP_ANIM -> MATCH -> REMOVE_ANIM -> GRAVITY_ANIM ->
    (CHAIN_WAIT -> MATCH -> ...) or back to IDLE.
    """

    def __init__(self, sfx_dir='sfx'):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption('Match 3')
        self.clock = pygame.time.Clock()

        # Fonts
        self.font_title = pygame.font.SysFont('Arial', 24, bold=True)
        self.font_sidebar = pygame.font.SysFont('Arial', 18)
        self.font_button = pygame.font.SysFont('Arial', 16)
        self.font_overlay = pygame.font.SysFont('Arial', 48, bold=True)

        # Load sound effects
        self.sfx_dir = sfx_dir
        self.sounds = {}
        self._load_sounds()

        # Board state
        self.board = []          # 2D array of Token or None
        self.score = 0
        self.level = 1
        self.threshold = INITIAL_THRESHOLD
        self.selected = None     # (row, col) or None
        self.chain_multiplier = 1
        self.magical_spawn_chance = 0.005

        # Animation state
        self.state = STATE_IDLE
        self.swap_start_time = 0
        self.swap_start_positions = {}  # (r,c) -> (x, y) at swap start
        self.invalid_timer = 0
        self.invalid_cells = set()
        self.red_border_timer = 0

        # Particles and floating text
        self.particles = []
        self.floating_texts = []

        # Overlay text for persistent messages (level complete, game over)
        self.overlay_text = ''
        self.overlay_color = TEXT_WHITE
        self.overlay_timer = 0

        # Button state
        self.button_rect = None
        self.button_hover = False

        self.reset_game()

    def _load_sounds(self):
        """Load all sound effects from the sfx directory."""
        sfx_map = {
            'match': SFX_MATCH,
            'match_plus': SFX_MATCH_PLUS,
            'match_chain': SFX_MATCH_CHAIN,
            'begin': SFX_BEGIN,
            'match_red': SFX_MATCH_RED,
        }
        for name, filename in sfx_map.items():
            path = os.path.join(self.sfx_dir, filename)
            if os.path.exists(path):
                self.sounds[name] = pygame.mixer.Sound(path)
            else:
                # Create a silent fallback so play() never crashes
                silent = pygame.sndarray.make_sound(
                    pygame.sndarray.zeros((44100,), dtype=int16))
                self.sounds[name] = silent

    def _play(self, name):
        """Play a sound effect by name, ignoring errors."""
        sound = self.sounds.get(name)
        if sound:
            try:
                sound.play()
            except pygame.error:
                pass

    # -----------------------------------------------------------------------
    # Board management
    # -----------------------------------------------------------------------

    def reset_game(self):
        """Reset all game state and fill the board."""
        self.score = 0
        self.level = 1
        self.threshold = INITIAL_THRESHOLD
        self.selected = None
        self.chain_multiplier = 1
        self.state = STATE_IDLE
        self.particles = []
        self.floating_texts = []
        self.overlay_text = ''
        self.overlay_timer = 0
        self.red_border_timer = 0
        self.invalid_timer = 0
        self.invalid_cells = set()
        self.magical_spawn_chance = 0.005
        self.fill_board()

    def _determine_token_type(self):
        """
        Determine if a new token should be magical based on current spawn chance.
        Resets chance to 0.5% if a magical token is spawned.
        """
        if random.random() < self.magical_spawn_chance:
            self.magical_spawn_chance = 0.005
            return random.choice(['horizontal', 'vertical'])
        return None

    def fill_board(self):
        """
        Fill the board with random tokens, avoiding initial matches.

        Each cell is assigned a random color that doesn't create a
        horizontal or vertical run of 3 with already-placed neighbors.
        """
        # Pre-initialize empty rows so _would_create_match can read them.
        self.board = [[] for _ in range(BOARD_SIZE)]
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                color = self._pick_safe_color(r, c)
                magical_type = self._determine_token_type()
                token = Token(r, c, color, magical_type=magical_type)
                self.board[r].append(token)

    def _pick_safe_color(self, r, c):
        """Pick a random color that won't create a match at (r, c)."""
        while True:
            color = random.choice(COLOR_KEYS)
            if not self._would_create_match(r, c, color):
                return color

    def _would_create_match(self, r, c, color):
        """Check if placing 'color' at (r, c) creates a 3+ run."""
        # Check left neighbors
        if c >= 2:
            t1 = self.board[r][c - 1]
            t2 = self.board[r][c - 2]
            if t1 and t2 and t1.color == color and t2.color == color:
                return True
        # Check above neighbors
        if r >= 2:
            t1 = self.board[r - 1][c]
            t2 = self.board[r - 2][c]
            if t1 and t2 and t1.color == color and t2.color == color:
                return True
        return False

    # -----------------------------------------------------------------------
    # Match detection
    # -----------------------------------------------------------------------

    def find_matches(self):
        """
        Find all groups of 3+ adjacent same-colored tokens.

        Returns a list of dicts with keys: 'r', 'c', 'length', 'color',
        'orientation', 'startC' (for horizontal), 'startR' (for vertical).
        """
        matches = []

        # Horizontal scan
        for r in range(BOARD_SIZE):
            c = 0
            while c < BOARD_SIZE - 2:
                token = self.board[r][c]
                if token is None:
                    c += 1
                    continue
                color = token.color
                if (self.board[r][c + 1] and self.board[r][c + 1].color == color and
                        self.board[r][c + 2] and self.board[r][c + 2].color == color):
                    length = 3
                    while (c + length < BOARD_SIZE and
                           self.board[r][c + length] and
                           self.board[r][c + length].color == color):
                        length += 1
                    matches.append({
                        'r': r, 'c': 0, 'length': length,
                        'color': color, 'orientation': 'h', 'startC': c,
                    })
                    c += length
                else:
                    c += 1

        # Vertical scan
        for c in range(BOARD_SIZE):
            r = 0
            while r < BOARD_SIZE - 2:
                token = self.board[r][c]
                if token is None:
                    r += 1
                    continue
                color = token.color
                if (self.board[r + 1][c] and self.board[r + 1][c].color == color and
                        self.board[r + 2][c] and self.board[r + 2][c].color == color):
                    length = 3
                    while (r + length < BOARD_SIZE and
                           self.board[r + length][c] and
                           self.board[r + length][c].color == color):
                        length += 1
                    matches.append({
                        'r': 0, 'c': c, 'length': length,
                        'color': color, 'orientation': 'v', 'startR': r,
                    })
                    r += length
                else:
                    r += 1

        return matches

    def _get_matched_cells(self, matches):
        """Extract unique (r, c) positions from a list of matches."""
        cells = set()
        for m in matches:
            if m['orientation'] == 'h':
                for i in range(m['length']):
                    cells.add((m['r'], m['startC'] + i))
            else:
                for i in range(m['length']):
                    cells.add((m['startR'] + i, m['c']))
        return cells

    # -----------------------------------------------------------------------
    # Swap logic
    # -----------------------------------------------------------------------

    @staticmethod
    def _is_neighbor(r1, c1, r2, c2):
        return abs(r1 - r2) + abs(c1 - c2) == 1

    def _test_swap(self, r1, c1, r2, c2):
        """
        Check if swapping two cells would create a match.

        Temporarily swaps colors, checks for matches, then swaps back.
        """
        t1, t2 = self.board[r1][c1], self.board[r2][c2]
        if not t1 or not t2:
            return False
        c1_color, c2_color = t1.color, t2.color
        t1.color, t2.color = c2_color, c1_color
        has_match = len(self.find_matches()) > 0
        t1.color, t2.color = c1_color, c2_color
        return has_match

    def _do_swap(self, r1, c1, r2, c2):
        """Swap two tokens in the board array."""
        self.board[r1][c1], self.board[r2][c2] = self.board[r2][c2], self.board[r1][c1]
        # Update grid positions
        self.board[r1][c1].row, self.board[r1][c1].col = r1, c1
        self.board[r2][c2].row, self.board[r2][c2].col = r2, c2

    # -----------------------------------------------------------------------
    # Input handling
    # -----------------------------------------------------------------------

    def handle_click(self, pos):
        """Process a mouse click."""
        if self.state == STATE_GAME_OVER:
            # Check if restart button was clicked
            if self.button_rect and self.button_rect.collidepoint(pos):
                self.reset_game()
            return

        if self.state != STATE_IDLE:
            return

        # Check if restart button was clicked
        if self.button_rect and self.button_rect.collidepoint(pos):
            self.reset_game()
            return

        # Convert click to board coordinates
        board_x = PADDING
        board_y = PADDING + TITLE_HEIGHT + TITLE_MARGIN_BOTTOM
        cx, cy = pos[0] - board_x, pos[1] - board_y

        if not (0 <= cx < BOARD_PIXELS and 0 <= cy < BOARD_PIXELS):
            return

        col = cx // CELL_SIZE
        row = cy // CELL_SIZE

        if self.selected:
            sr, sc = self.selected
            if self._is_neighbor(row, col, sr, sc):
                # Attempt swap
                if self._test_swap(sr, sc, row, col):
                    self._do_swap(sr, sc, row, col)
                    self.selected = None
                    self.swap_start_time = pygame.time.get_ticks()
                    # Record start positions for animation
                    self.swap_start_positions = {
                        (sr, sc): (self.board[sr][sc].x, self.board[sr][sc].y),
                        (row, col): (self.board[row][col].x, self.board[row][col].y),
                    }
                    self.state = STATE_SWAP_ANIM
                else:
                    # Invalid swap - flash red
                    self.invalid_cells = {(sr, sc), (row, col)}
                    self.invalid_timer = INVALID_FLASH_DURATION
                    self.selected = None
            else:
                # Select different cell
                self.selected = (row, col)
        else:
            self.selected = (row, col)

    def handle_key(self, key, mod):
        """Process a key press."""
        if self.state == STATE_GAME_OVER and key == pygame.K_r:
            self.reset_game()
        elif self.state == STATE_IDLE and key == pygame.K_ESCAPE:
            self.selected = None

    # -----------------------------------------------------------------------
    # State machine update
    # -----------------------------------------------------------------------

    def update(self, dt_ms):
        """Advance the game state by one frame."""
        # Update particles and floating text regardless of state
        for p in self.particles:
            p.update(dt_ms)
        self.particles = [p for p in self.particles if p.alive]

        for ft in self.floating_texts:
            ft.update(dt_ms)
        self.floating_texts = [ft for ft in self.floating_texts if ft.alive]

        # Timers
        if self.invalid_timer > 0:
            self.invalid_timer -= dt_ms
            if self.invalid_timer <= 0:
                self.invalid_cells = set()

        if self.red_border_timer > 0:
            self.red_border_timer -= dt_ms

        if self.overlay_timer > 0:
            self.overlay_timer -= dt_ms

        # State-specific updates
        if self.state == STATE_SWAP_ANIM:
            self._update_swap_anim(dt_ms)
        elif self.state == STATE_MATCH:
            self._update_match(dt_ms)
        elif self.state == STATE_REMOVE_ANIM:
            self._update_remove_anim(dt_ms)
        elif self.state == STATE_GRAVITY_ANIM:
            self._update_gravity_anim(dt_ms)
        elif self.state == STATE_CHAIN_WAIT:
            self._update_chain_wait(dt_ms)
        elif self.state == STATE_LEVEL_COMPLETE:
            self._update_level_complete(dt_ms)
        elif self.state == STATE_LEVEL_BEGIN:
            self._update_level_begin(dt_ms)

    def _update_swap_anim(self, dt_ms):
        """Animate the swap transition."""
        elapsed = pygame.time.get_ticks() - self.swap_start_time
        if elapsed >= SWAP_DURATION:
            # Swap complete - check for matches
            matches = self.find_matches()
            if matches:
                self.state = STATE_MATCH
            else:
                # Shouldn't happen (we pre-checked), but safety net
                self.state = STATE_IDLE

    def _process_magical_clears(self, matched_cells):
        """
        Process magical token effects: clear rows/cols and handle chaining.
        Returns the expanded set of cells to clear and any additional score.
        """
        extra_score = 0
        cells_to_clear = set(matched_cells)
        magical_queue = []
        
        # Initial magical tokens that were part of the match
        for r, c in matched_cells:
            token = self.board[r][c]
            if token and token.magical_type:
                magical_queue.append((r, c))
                
        processed_magical = set()
        
        while magical_queue:
            r, c = magical_queue.pop(0)
            if (r, c) in processed_magical:
                continue
            processed_magical.add((r, c))
            
            token = self.board[r][c]
            if not token:
                continue
            
            if token.magical_type == 'horizontal':
                # Clear entire row
                for col in range(BOARD_SIZE):
                    cells_to_clear.add((r, col))
                    t = self.board[r][col]
                    if t and t.magical_type:
                        magical_queue.append((r, col))
                    if t:
                        extra_score += 1 if t.color != 'red' else -1
            elif token.magical_type == 'vertical':
                # Clear entire column
                for row in range(BOARD_SIZE):
                    cells_to_clear.add((row, c))
                    t = self.board[row][c]
                    if t and t.magical_type:
                        magical_queue.append((row, c))
                    if t:
                        extra_score += 1 if t.color != 'red' else -1
                        
        return cells_to_clear, extra_score

    def _update_match(self, dt_ms):
        """
        Process matches: calculate score, spawn effects, play sounds.
        Handles magical token effects and their scoring.
        """
        matches = self.find_matches()
        if not matches:
            self.chain_multiplier = 1
            self.state = STATE_IDLE
            return

        # 1. Base Scoring
        match_points = 0
        for m in matches:
            length = m['length']
            base = length + (length - 3)  # = 2*length - 3
            if m['color'] == 'red':
                match_points -= base
            else:
                match_points += base
        match_points *= self.chain_multiplier
        self.score += match_points

        # 2. Magical Effects
        matched_cells = self._get_matched_cells(matches)
        expanded_cells, extra_score = self._process_magical_clears(matched_cells)
        self.score += extra_score
        
        magical_triggered = len(expanded_cells) > len(matched_cells)
        matched_cells = expanded_cells

        # 3. Spawn Chance update
        # Increase chance by 0.5% per successful match (regardless of color)
        self.magical_spawn_chance += 0.005

        # 4. Feedback and Sounds
        has_red = any(m['color'] == 'red' for m in matches)
        is_multi = len(matches) > 1
        has_bonus = any(m['length'] > 3 for m in matches)
        is_chain = self.chain_multiplier > 1

        if has_red:
            self._play('match_red')
        elif is_chain:
            self._play('match_chain')
        elif is_multi or has_bonus:
            self._play('match_plus')
        else:
            self._play('match')

        board_center_x = BOARD_PIXELS / 2
        board_center_y = BOARD_PIXELS / 2
        if has_red:
            self.floating_texts.append(
                FloatingText("OH NO!", (240, 128, 128),
                             board_center_x, board_center_y))
            self.red_border_timer = 500
        else:
            if is_multi:
                self.floating_texts.append(
                    FloatingText("MULTI-MATCH!", (255, 255, 255),
                                 board_center_x, board_center_y))
            elif is_chain:
                self.floating_texts.append(
                    FloatingText("NICE!", (255, 255, 255),
                                 board_center_x, board_center_y))
            if has_bonus and not has_red:
                self.floating_texts.append(
                    FloatingText("BONUS!", (0, 255, 0),
                                 board_center_x, board_center_y))

        if magical_triggered:
            self.floating_texts.append(
                FloatingText("MAGICAL POWER!", (139, 0, 0),
                             board_center_x, board_center_y))

        # 5. Removal setup
        for r, c in matched_cells:
            token = self.board[r][c]
            if token:
                self._spawn_explosion(r, c, COLORS[token.color])
                token.set_fade()

        self.state = STATE_REMOVE_ANIM
        self.remove_start_time = pygame.time.get_ticks()

    def _update_remove_anim(self, dt_ms):
        """Animate token fade-out, then apply gravity."""
        elapsed = pygame.time.get_ticks() - self.remove_start_time

        # Fade tokens
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                token = self.board[r][c]
                if token and token.fading:
                    token.update_remove(dt_ms)

        if elapsed >= REMOVAL_DURATION:
            # Clear removed tokens from board
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    token = self.board[r][c]
                    if token and token.opacity <= 0:
                        self.board[r][c] = None

            self._apply_gravity()
            self.state = STATE_GRAVITY_ANIM
            self.gravity_start_time = pygame.time.get_ticks()

    def _apply_gravity(self):
        """
        Shift surviving tokens down and spawn new tokens at the top.

        For each column, surviving tokens are compacted to the bottom.
        New random tokens are created above the board to fill gaps.
        New tokens start with y positioned above the visible board so
        they animate falling in.
        """
        for c in range(BOARD_SIZE):
            # Collect surviving tokens (top to bottom)
            survivors = []
            for r in range(BOARD_SIZE):
                if self.board[r][c] is not None:
                    survivors.append(self.board[r][c])

            num_survivors = len(survivors)
            num_new = BOARD_SIZE - num_survivors

            # Place survivors at bottom
            for i, token in enumerate(survivors):
                r = num_new + i
                self.board[r][c] = token
                token.row = r
                token.col = c
                token.fading = False
                token.opacity = 255

            # Create new tokens at top
            for i in range(num_new):
                r = i
                color = random.choice(COLOR_KEYS)
                magical_type = self._determine_token_type()
                token = Token(r, c, color, magical_type=magical_type)
                # Start above the board
                token.y = -TOKEN_SIZE - i * CELL_SIZE
                token.x = c * CELL_SIZE + TOKEN_OFFSET
                self.board[r][c] = token

    def _update_gravity_anim(self, dt_ms):
        """Animate tokens falling into place."""
        all_settled = True
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                token = self.board[r][c]
                if token:
                    token.update_gravity(dt_ms)
                    if token.y != token.target_y or token.x != token.target_x:
                        all_settled = False

        elapsed = pygame.time.get_ticks() - self.gravity_start_time
        if all_settled or elapsed >= GRAVITY_DURATION:
            # Snap all tokens to target
            for r in range(BOARD_SIZE):
                for c in range(BOARD_SIZE):
                    token = self.board[r][c]
                    if token:
                        token.x = token.target_x
                        token.y = token.target_y

            # Check for cascade matches
            matches = self.find_matches()
            if matches:
                self.chain_multiplier *= 2
                self.state = STATE_CHAIN_WAIT
                self.chain_wait_start = pygame.time.get_ticks()
            else:
                self.chain_multiplier = 1
                self.state = STATE_IDLE
                # Check for game over (no valid moves)
                self._check_game_over()

    def _update_chain_wait(self, dt_ms):
        """Brief pause before processing cascade matches."""
        elapsed = pygame.time.get_ticks() - self.chain_wait_start
        if elapsed >= 150:  # Short pause for visual clarity
            self.state = STATE_MATCH

    def _update_level_complete(self, dt_ms):
        """Wait for level complete overlay, then transition."""
        elapsed = pygame.time.get_ticks() - self.overlay_timer
        # overlay_timer counts down; when it reaches 0, transition
        if self.overlay_timer <= 0:
            self.level += 1
            self.threshold += THRESHOLD_INCREMENT
            self.score = 0
            self.chain_multiplier = 1
            self.magical_spawn_chance = 0.005
            self.fill_board()
            self.state = STATE_LEVEL_BEGIN
            self.overlay_text = f"BEGIN LEVEL {self.level}"
            self.overlay_color = COLORS['pink']
            self.overlay_timer = LEVEL_BEGIN_DURATION
            self._play('begin')

    def _update_level_begin(self, dt_ms):
        """Wait for level begin overlay, then return to idle."""
        if self.overlay_timer <= 0:
            self.overlay_text = ''
            self.state = STATE_IDLE

    def _check_level_advance(self):
        """Check if the player has reached the score threshold."""
        if self.score >= self.threshold:
            self.state = STATE_LEVEL_COMPLETE
            self.overlay_text = "LEVEL COMPLETE!"
            self.overlay_color = pygame.Color('lightblue')
            self.overlay_timer = LEVEL_COMPLETE_DURATION

    def _check_game_over(self):
        """
        Check if any valid swap exists on the board.

        If no valid moves remain, transition to game over state.
        """
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                if c < BOARD_SIZE - 1:
                    if self._test_swap(r, c, r, c + 1):
                        return
                if r < BOARD_SIZE - 1:
                    if self._test_swap(r, c, r + 1, c):
                        return
        self.state = STATE_GAME_OVER
        self.overlay_text = "NO MOVES\nGAME OVER"
        self.overlay_color = pygame.Color('lightcoral')

    def _spawn_explosion(self, r, c, color):
        """Create PARTICLES_PER_CELL particles at a cell's center."""
        cx = c * CELL_SIZE + CELL_SIZE / 2
        cy = r * CELL_SIZE + CELL_SIZE / 2
        for _ in range(PARTICLES_PER_CELL):
            self.particles.append(Particle(cx, cy, color))

    # -----------------------------------------------------------------------
    # Rendering
    # -----------------------------------------------------------------------

    def render(self):
        """Draw the complete game frame."""
        self.screen.fill(BG_COLOR)

        board_x = PADDING
        board_y = PADDING + TITLE_HEIGHT + TITLE_MARGIN_BOTTOM

        self._draw_title_bar()
        self._draw_board(board_x, board_y)
        self._draw_tokens(board_x, board_y)
        self._draw_particles(board_x, board_y)
        self._draw_floating_texts(board_x, board_y)
        self._draw_sidebar()
        self._draw_overlay()

        pygame.display.flip()

    def _draw_title_bar(self):
        """Draw the top title bar."""
        x = PADDING
        y = PADDING
        rect = pygame.Rect(x, y, TITLE_WIDTH, TITLE_HEIGHT)
        pygame.draw.rect(self.screen, pygame.Color('#000000'), rect)
        pygame.draw.rect(self.screen, BORDER_THICK, rect, BORDER_THICK_WIDTH)

        title = self.font_title.render("MATCH 3", True, TEXT_WHITE)
        title_rect = title.get_rect(center=(x + TITLE_WIDTH // 2, y + TITLE_HEIGHT // 2))
        self.screen.blit(title, title_rect)

    def _draw_board(self, ox, oy):
        """Draw the game board grid with cell borders and highlights."""
        # Board background and thick border
        board_rect = pygame.Rect(ox, oy, BOARD_PIXELS, BOARD_PIXELS)
        pygame.draw.rect(self.screen, pygame.Color('#000000'), board_rect)

        # Determine border color (red flash for red matches)
        border_color = RED_BORDER_COLOR if self.red_border_timer > 0 else BORDER_THICK
        pygame.draw.rect(self.screen, border_color, board_rect, BORDER_THICK_WIDTH)

        # Draw cells
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                cx = ox + c * CELL_SIZE
                cy = oy + r * CELL_SIZE
                cell_rect = pygame.Rect(cx, cy, CELL_SIZE, CELL_SIZE)

                # Cell background and border
                bg = pygame.Color('#000000')
                border = BORDER_THIN
                bw = BORDER_THIN_WIDTH

                if (r, c) in self.invalid_cells:
                    bg = INVALID_BG
                    border = INVALID_BORDER
                    bw = BORDER_THIN_WIDTH
                elif self.selected and self.selected == (r, c):
                    bg = SELECTED_BG
                    border = SELECTED_BORDER
                    bw = BORDER_THIN_WIDTH
                elif self.selected and self._is_neighbor(r, c, *self.selected):
                    bg = OPTION_BG
                    border = OPTION_BORDER
                    bw = BORDER_THIN_WIDTH

                pygame.draw.rect(self.screen, bg, cell_rect)
                pygame.draw.rect(self.screen, border, cell_rect, bw)

    def _draw_tokens(self, ox, oy):
        """Draw all tokens on the board."""
        for r in range(BOARD_SIZE):
            for c in range(BOARD_SIZE):
                token = self.board[r][c]
                if token:
                    token.draw(self.screen, ox, oy)

    def _draw_particles(self, ox, oy):
        """Draw all active explosion particles."""
        for p in self.particles:
            p.draw(self.screen, ox, oy)

    def _draw_floating_texts(self, ox, oy):
        """Draw all active floating score feedback texts."""
        for ft in self.floating_texts:
            ft.draw(self.screen, ox, oy)

    def _draw_sidebar(self):
        """Draw the sidebar with score, level, target, and restart button."""
        x = PADDING + BOARD_PIXELS + SIDEBAR_GAP  # gap between board and sidebar
        y = PADDING + TITLE_HEIGHT + TITLE_MARGIN_BOTTOM

        # Sidebar background
        sidebar_rect = pygame.Rect(x, y, SIDEBAR_WIDTH, SIDEBAR_HEIGHT)
        pygame.draw.rect(self.screen, pygame.Color('#000000'), sidebar_rect)
        pygame.draw.rect(self.screen, BORDER_THICK, sidebar_rect, BORDER_THICK_WIDTH)

        inner_x = x + SIDEBAR_PADDING
        inner_y = y + SIDEBAR_PADDING

        # Level
        level_text = self.font_sidebar.render(
            f"Level: {self.level}", True, TEXT_WHITE)
        self.screen.blit(level_text, (inner_x, inner_y))

        # Score (red if negative)
        score_color = NEGATIVE_SCORE_COLOR if self.score < 0 else TEXT_WHITE
        score_text = self.font_sidebar.render(
            f"Score: {self.score}", True, score_color)
        self.screen.blit(score_text, (inner_x, inner_y + 40))

        # Target
        target_text = self.font_sidebar.render(
            f"Target: {self.threshold}", True, TEXT_WHITE)
        self.screen.blit(target_text, (inner_x, inner_y + 80))

        # Restart button
        btn_w = SIDEBAR_WIDTH - SIDEBAR_PADDING * 2
        btn_h = 40
        btn_x = inner_x
        btn_y = y + SIDEBAR_HEIGHT - SIDEBAR_PADDING - btn_h
        self.button_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)

        # Check hover
        mouse_pos = pygame.mouse.get_pos()
        self.button_hover = self.button_rect.collidepoint(mouse_pos) if self.button_rect else False
        btn_color = BUTTON_HOVER_BG if self.button_hover else BUTTON_BG

        pygame.draw.rect(self.screen, btn_color, self.button_rect)
        pygame.draw.rect(self.screen, TEXT_WHITE, self.button_rect, 1)

        btn_text = self.font_button.render("Restart", True, TEXT_WHITE)
        btn_text_rect = btn_text.get_rect(center=self.button_rect.center)
        self.screen.blit(btn_text, btn_text_rect)

    def _draw_overlay(self):
        """Draw persistent overlay text (level complete, game over)."""
        if not self.overlay_text:
            return

        lines = self.overlay_text.split('\n')
        center_x = PADDING + BOARD_PIXELS // 2
        center_y = PADDING + TITLE_HEIGHT + TITLE_MARGIN_BOTTOM + BOARD_PIXELS // 2

        for i, line in enumerate(lines):
            offset = (i - (len(lines) - 1) / 2) * 56
            text = self.font_overlay.render(line, True, self.overlay_color)
            rect = text.get_rect(center=(center_x, center_y + offset))
            self.screen.blit(text, rect)

    # -----------------------------------------------------------------------
    # Main loop
    # -----------------------------------------------------------------------

    def run(self):
        """Run the main game loop."""
        running = True
        while running:
            dt_ms = self.clock.tick(60)

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.handle_click(event.pos)
                elif event.type == pygame.KEYDOWN:
                    self.handle_key(event.key, event.mod)

            self.update(dt_ms)
            self.render()

        pygame.quit()
        sys.exit()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Initialize and run the game."""
    # Determine sfx directory relative to this script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    sfx_dir = os.path.join(script_dir, 'sfx')
    game = Match3Game(sfx_dir=sfx_dir)
    game.run()


if __name__ == '__main__':
    main()
