import pygame
import random
import math
import time
from dataclasses import dataclass
from typing import List, Tuple, Optional, Set
from enum import Enum, auto

# ============================================================
# CONSTANTS
# ============================================================
ROWS = 8
COLS = 8
CELL_SIZE = 60
TOKEN_SIZE = 50
ANIM_DURATION = 0.4  # seconds

# Colors
COLOR_BG = (179, 217, 255)      # #b3d9ff
COLOR_BLACK = (0, 0, 0)         # #000
COLOR_DARK_GRAY = (68, 68, 68)  # #444
COLOR_GRAY = (204, 204, 204)    # #ccc
COLOR_WHITE = (255, 255, 255)   # #fff
COLOR_SELECTED_BG = (0, 100, 0) # #006400
COLOR_SELECTED_BORDER = (144, 238, 144) # #90ee90
COLOR_OPTION_BG = (51, 51, 51)  # #333
COLOR_OPTION_BORDER = (144, 238, 144) # #90ee90
COLOR_INVALID_BG = (139, 0, 0)  # #8b0000
COLOR_INVALID_BORDER = (255, 102, 102) # #ff6666
COLOR_FLASH_RED = (139, 0, 0)   # #8b0000

TOKEN_COLORS = [
    (255, 0, 0),    # red
    (0, 204, 0),    # green
    (0, 102, 255),  # blue
    (255, 136, 0),  # orange
    (255, 221, 0),  # yellow
    (255, 0, 204),  # pink
]
RED_INDEX = 0

# UI Layout
WINDOW_WIDTH = 720
WINDOW_HEIGHT = 568
TITLE_BAR_HEIGHT = 48
TITLE_SPACER_HEIGHT = 40
BOARD_OFFSET_X = 0
BOARD_OFFSET_Y = TITLE_BAR_HEIGHT + TITLE_SPACER_HEIGHT
SIDEBAR_OFFSET_X = 480 + 40
SIDEBAR_WIDTH = 200

class GameState(Enum):
    IDLE = auto()
    ANIMATING = auto()
    GAME_OVER = auto()

@dataclass
class Position:
    row: int
    col: int

@dataclass
class Particle:
    x: float
    y: float
    vx: float
    vy: float
    life: float
    decay: float
    size: float
    color: Tuple[int, int, int]

@dataclass
class OverlayText:
    text: str
    color: Tuple[int, int, int]
    duration: float
    start_time: float
    fixed: bool = False

class Token:
    def __init__(self, row: int, col: int, color_idx: int):
        self.color_idx = color_idx
        self.row = row
        self.col = col
        self.target_x = col * CELL_SIZE + (CELL_SIZE - TOKEN_SIZE) // 2
        self.target_y = row * CELL_SIZE + (CELL_SIZE - TOKEN_SIZE) // 2
        self.curr_x = self.target_x
        self.curr_y = self.target_y
        self.opacity = 255.0
        self.is_removing = False
        self.remove_start_time = 0.0

    def update(self, dt: float):
        # Simple linear interpolation for movement (approx ease-in)
        # In a real production app, we might use a proper easing function.
        # But for a port, we'll stick to a smooth transition.
        lerp_factor = 0.15
        self.curr_x += (self.target_x - self.curr_x) * lerp_factor
        self.curr_y += (self.target_y - self.curr_y) * lerp_factor
        
        if self.is_removing:
            self.opacity -= 1000 * dt # Fade out over ~0.25s
            if self.opacity < 0:
                self.opacity = 0

    def set_position(self, row: int, col: int):
        self.row = row
        self.col = col
        self.target_x = col * CELL_SIZE + (CELL_SIZE - TOKEN_SIZE) // 2
        self.target_y = row * CELL_SIZE + (CELL_SIZE - TOKEN_SIZE) // 2

    def draw(self, surface: pygame.Surface):
        if self.opacity <= 0:
            return
        
        # Create a surface for the token to handle opacity
        token_surf = pygame.Surface((TOKEN_SIZE, TOKEN_SIZE), pygame.SRCALPHA)
        color = TOKEN_COLORS[self.color_idx]
        
        # Draw circle
        pygame.draw.circle(token_surf, (*color, int(self.opacity)), (TOKEN_SIZE // 2, TOKEN_SIZE // 2), TOKEN_SIZE // 2)
        # Draw white border
        pygame.draw.circle(token_surf, (255, 255, 255, int(self.opacity)), (TOKEN_SIZE // 2, TOKEN_SIZE // 2), TOKEN_SIZE // 2, 2)
        
        surface.blit(token_surf, (self.curr_x, self.curr_y))

class AudioManager:
    def __init__(self):
        self.sounds = {}
        try:
            self.sounds['match'] = pygame.mixer.Sound('sfx/match.wav')
            self.sounds['match_plus'] = pygame.mixer.Sound('sfx/match_plus.wav')
            self.sounds['match_chain'] = pygame.mixer.Sound('sfx/match_chain.wav')
            self.sounds['begin'] = pygame.mixer.Sound('sfx/begin.wav')
            self.sounds['match_red'] = pygame.mixer.Sound('sfx/match_red.wav')
        except pygame.error as e:
            print(f"Warning: Could not load some sound effects: {e}")

    def play(self, name: str):
        if name in self.sounds:
            self.sounds[name].play()

class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        pygame.display.set_caption("MATCH 3")
        self.clock = pygame.time.Clock()
        self.font_main = pygame.font.SysFont('Segoe UI', 28, bold=True)
        self.font_small = pygame.font.SysFont('Segoe UI', 14)
        self.font_large = pygame.font.SysFont('Segoe UI', 36, bold=True)
        
        self.audio = AudioManager()
        
        self.reset_game()

    def reset_game(self):
        self.level = 1
        self.score = 0
        self.target = 100
        self.state = GameState.IDLE
        self.selected: Optional[Position] = None
        self.board: List[List[int]] = [[-1 for _ in range(COLS)] for _ in range(ROWS)]
        self.tokens: List[List[Optional[Token]]] = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.particles: List[Particle] = []
        self.overlays: List[OverlayText] = []
        self.board_flash_red_until = 0.0
        self.invalid_flash_until = 0.0
        self.invalid_cells: Set[Tuple[int, int]] = set()
        
        self.init_board()
        self.audio.play('begin')

    def init_board(self):
        for r in range(ROWS):
            for c in range(COLS):
                color = -1
                while True:
                    color = random.randint(0, len(TOKEN_COLORS) - 1)
                    if not self.would_create_match(r, c, color):
                        break
                self.board[r][c] = color
                self.tokens[r][c] = Token(r, c, color)

    def would_create_match(self, r: int, c: int, color: int) -> bool:
        # Horizontal
        left = 0
        for i in range(c - 1, -1, -1):
            if self.board[r][i] == color: left += 1
            else: break
        right = 0
        for i in range(c + 1, COLS):
            if self.board[r][i] == color: right += 1
            else: break
        if left + right + 1 >= 3: return True
        
        # Vertical
        up = 0
        for i in range(r - 1, -1, -1):
            if self.board[i][c] == color: up += 1
            else: break
        down = 0
        for i in range(r + 1, ROWS):
            if self.board[i][c] == color: down += 1
            else: break
        if up + down + 1 >= 3: return True
        
        return False

    def get_neighbors(self, r: int, c: int) -> List[Position]:
        neighbors = []
        if r > 0: neighbors.append(Position(r - 1, c))
        if r < ROWS - 1: neighbors.append(Position(r + 1, c))
        if c > 0: neighbors.append(Position(r, c - 1))
        if c < COLS - 1: neighbors.append(Position(r, c + 1))
        return neighbors

    def find_all_matches(self) -> Set[Tuple[int, int]]:
        matched = set()
        # Horizontal
        for r in range(ROWS):
            run_len = 1
            for c in range(1, COLS):
                if self.board[r][c] == self.board[r][c - 1] and self.board[r][c] != -1:
                    run_len += 1
                else:
                    if run_len >= 3:
                        for i in range(c - run_len, c):
                            matched.add((r, i))
                    run_len = 1
            if run_len >= 3:
                for i in range(COLS - run_len, COLS):
                    matched.add((r, i))
        # Vertical
        for c in range(COLS):
            run_len = 1
            for r in range(1, ROWS):
                if self.board[r][c] == self.board[r - 1][c] and self.board[r][c] != -1:
                    run_len += 1
                else:
                    if run_len >= 3:
                        for i in range(r - run_len, r):
                            matched.add((i, c))
                    run_len = 1
            if run_len >= 3:
                for i in range(ROWS - run_len, ROWS):
                    matched.add((i, c))
        return matched

    def find_contiguous_groups(self, matches: Set[Tuple[int, int]]) -> List[Tuple[int, int]]:
        visited = set()
        groups = []
        for m in matches:
            if m in visited: continue
            color = self.board[m[0]][m[1]]
            group = []
            queue = [m]
            visited.add(m)
            while queue:
                curr = queue.pop(0)
                group.append(curr)
                for n in self.get_neighbors(curr[0], curr[1]):
                    pos = (n.row, n.col)
                    if pos not in visited and pos in matches and self.board[pos[0]][pos[1]] == color:
                        visited.add(pos)
                        queue.append(pos)
            groups.append((color, len(group)))
        return groups

    async def process_matches(self, chain_level: int):
        matches = self.find_all_matches()
        if not matches:
            self.state = GameState.IDLE
            if self.score >= self.target:
                await self.show_level_complete()
            elif not self.has_valid_moves():
                self.state = GameState.GAME_OVER
                self.show_overlay_text("NO MOVES - GAME OVER", (255, 100, 100), 2.0, fixed=True)
            return

        groups = self.find_contiguous_groups(matches)
        total_points = 0
        has_red = False
        has_bonus = False
        
        for color_idx, count in groups:
            is_red = (color_idx == RED_INDEX)
            if is_red: has_red = True
            
            pts = -count if is_red else count
            if count > 3:
                has_bonus = True
                pts += -(count - 3) if is_red else (count - 3)
            
            total_points += pts * chain_level
        
        self.score += total_points
        
        # Sound and Overlays
        if has_red:
            self.audio.play('match_red')
            self.board_flash_red_until = time.time() + 0.6
            self.show_overlay_text("OH NO!", (255, 100, 100), 2.0)
        elif chain_level > 1:
            self.audio.play('match_chain')
            self.show_overlay_text("NICE!", (255, 255, 255), 2.0)
        elif has_bonus or len(groups) > 1:
            self.audio.play('match_plus')
            if len(groups) > 1:
                self.show_overlay_text("MULTI-MATCH!", (255, 255, 255), 2.0)
            if has_bonus:
                self.show_overlay_text("BONUS!", (100, 255, 100), 2.0)
        else:
            self.audio.play('match')

        self.spawn_particles(matches)

        # Animate removal
        for m in matches:
            t = self.tokens[m[0]][m[1]]
            if t: t.is_removing = True
        
        await self.delay(0.25)
        
        for m in matches:
            self.board[m[0]][m[1]] = -1
            self.tokens[m[0]][m[1]] = None
            
        await self.apply_gravity()
        await self.fill_empty()
        await self.process_matches(chain_level + 1)

    async def apply_gravity(self):
        max_fall = 0
        for c in range(COLS):
            write_row = ROWS - 1
            for r in range(ROWS - 1, -1, -1):
                if self.board[r][c] != -1:
                    if write_row != r:
                        self.board[write_row][c] = self.board[r][c]
                        self.board[r][c] = -1
                        token = self.tokens[r][c]
                        self.tokens[write_row][c] = token
                        self.tokens[r][c] = None
                        if token:
                            token.set_position(write_row, c)
                            max_fall = max(max_fall, write_row - r)
                    write_row -= 1
        if max_fall > 0:
            await self.delay(min(0.5, max(ANIM_DURATION, max_fall * 0.08)))

    async def fill_empty(self):
        max_fall = 0
        for c in range(COLS):
            empty_count = sum(1 for r in range(ROWS) if self.board[r][c] == -1)
            for r in range(empty_count):
                color = random.randint(0, len(TOKEN_COLORS) - 1)
                self.board[r][c] = color
                token = Token(r, c, color)
                # Start above the board
                token.curr_x = c * CELL_SIZE + (CELL_SIZE - TOKEN_SIZE) // 2
                token.curr_y = (r - empty_count) * CELL_SIZE + (CELL_SIZE - TOKEN_SIZE) // 2
                self.tokens[r][c] = token
                max_fall = max(max_fall, empty_count - r)
        if max_fall > 0:
            await self.delay(min(0.5, max(ANIM_DURATION, max_fall * 0.08)))

    def spawn_particles(self, matches: Set[Tuple[int, int]]):
        for m in matches:
            cx = m[1] * CELL_SIZE + CELL_SIZE // 2
            cy = m[0] * CELL_SIZE + CELL_SIZE // 2
            color = TOKEN_COLORS[self.board[m[0]][m[1]]] if self.board[m[0]][m[1]] != -1 else COLOR_WHITE
            for i in range(40):
                angle = (math.pi * 2 * i) / 40 + (random.random() - 0.5) * 0.5
                speed = 2 + random.random() * 4
                self.particles.append(Particle(
                    x=cx, y=cy,
                    vx=math.cos(angle) * speed,
                    vy=math.sin(angle) * speed,
                    life=1.0,
                    decay=0.015 + random.random() * 0.02,
                    size=2 + random.random() * 4,
                    color=color
                ))

    def show_overlay_text(self, text: str, color: Tuple[int, int, int], duration: float = 2.0, fixed: bool = False):
        self.overlays.append(OverlayText(text, color, duration, time.time(), fixed))

    async def show_level_complete(self):
        self.state = GameState.ANIMATING
        self.show_overlay_text("LEVEL COMPLETE!", (173, 216, 230), 2.0, fixed=True)
        await self.delay(2.0)
        
        self.level += 1
        self.score = 0
        self.target = 100 + (self.level - 1) * 50
        
        # Clear board
        self.board = [[-1 for _ in range(COLS)] for _ in range(ROWS)]
        self.tokens = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.init_board()
        
        self.show_overlay_text(f"BEGIN LEVEL {self.level}", (255, 105, 180), 1.2, fixed=True)
        self.audio.play('begin')
        await self.delay(1.2)
        self.state = GameState.IDLE

    def has_valid_moves(self) -> bool:
        # Temp board for simulation
        temp_board = [row[:] for row in self.board]
        def simulate_swap(r1, c1, r2, c2):
            temp_board[r1][c1], temp_board[r2][c2] = temp_board[r2][c2], temp_board[r1][c1]

        def find_sim_matches():
            matched = set()
            # Horizontal
            for r in range(ROWS):
                run = 1
                for c in range(1, COLS):
                    if temp_board[r][c] == temp_board[r][c-1] and temp_board[r][c] != -1: run += 1
                    else:
                        if run >= 3:
                            for i in range(c-run, c): matched.add((r, i))
                        run = 1
                if run >= 3:
                    for i in range(COLS-run, COLS): matched.add((r, i))
            # Vertical
            for c in range(COLS):
                run = 1
                for r in range(1, ROWS):
                    if temp_board[r][c] == temp_board[r-1][c] and temp_board[r][c] != -1: run += 1
                    else:
                        if run >= 3:
                            for i in range(r-run, r): matched.add((i, c))
                        run = 1
                if run >= 3:
                    for i in range(ROWS-run, ROWS): matched.add((i, c))
            return matched

        for r in range(ROWS):
            for c in range(COLS):
                # Right
                if c < COLS - 1:
                    simulate_swap(r, c, r, c + 1)
                    if find_sim_matches(): return True
                    simulate_swap(r, c, r, c + 1)
                # Down
                if r < ROWS - 1:
                    simulate_swap(r, c, r + 1, c)
                    if find_sim_matches(): return True
                    simulate_swap(r, c, r + 1, c)
        return False

    async def delay(self, seconds: float):
        # We use a custom delay that allows the game loop to continue
        # In this implementation, we will handle it by tracking time in the update loop
        # but since the process_matches is an async function, we can just sleep 
        # if we are running it in a separate thread or use a state-based timer.
        # For simplicity in this Pygame port, I'll use a simple sleep for these 
        # sequence-heavy animations, but normally I'd use a timer in the loop.
        # To avoid freezing the screen, I'll just return and let the game loop
        # handle the transition if I can. 
        # Actually, I'll implement a simple timer-based sequence.
        import asyncio
        await asyncio.sleep(seconds)

    def handle_click(self, x: int, y: int):
        if self.state != GameState.IDLE: return
        
        # Convert screen coords to board coords
        bx = x - BOARD_OFFSET_X
        by = y - BOARD_OFFSET_Y
        if not (0 <= bx < 480 and 0 <= by < 480): return
        
        c = bx // CELL_SIZE
        r = by // CELL_SIZE
        
        if self.selected is None:
            self.selected = Position(r, c)
        elif self.selected.row == r and self.selected.col == c:
            self.selected = None
        elif abs(self.selected.row - r) + abs(self.selected.col - c) == 1:
            # Attempt swap
            self.state = GameState.ANIMATING
            import asyncio
            asyncio.create_task(self.attempt_swap(self.selected.row, self.selected.col, r, c))
            self.selected = None
        else:
            self.selected = Position(r, c)

    async def attempt_swap(self, r1, c1, r2, c2):
        # Swap data
        self.board[r1][c1], self.board[r2][c2] = self.board[r2][c2], self.board[r1][c1]
        
        if not self.find_all_matches():
            # Invalid
            self.board[r1][c1], self.board[r2][c2] = self.board[r2][c2], self.board[r1][c1]
            self.invalid_cells = {(r1, c1), (r2, c2)}
            self.invalid_flash_until = time.time() + 0.3
            self.state = GameState.IDLE
            return
        
        # Valid
        t1 = self.tokens[r1][c1]
        t2 = self.tokens[r2][c2]
        if t1: t1.set_position(r2, c2)
        if t2: t2.set_position(r1, c1)
        self.tokens[r1][c1], self.tokens[r2][c2] = t2, t1
        
        await self.delay(ANIM_DURATION)
        await self.process_matches(1)

    def update(self, dt: float):
        # Update tokens
        for r in range(ROWS):
            for c in range(COLS):
                t = self.tokens[r][c]
                if t: t.update(dt)
        
        # Update particles
        for p in self.particles[:]:
            p.x += p.vx
            p.y += p.vy
            p.vy += 0.05
            p.life -= p.decay
            if p.life <= 0:
                self.particles.remove(p)
        
        # Update overlays
        now = time.time()
        for o in self.overlays[:]:
            if now - o.start_time > o.duration:
                self.overlays.remove(o)

    def draw(self):
        self.screen.fill(COLOR_BG)
        
        # Title Bar
        pygame.draw.rect(self.screen, COLOR_BLACK, (0, 0, WINDOW_WIDTH, TITLE_BAR_HEIGHT))
        pygame.draw.rect(self.screen, COLOR_DARK_GRAY, (0, 0, WINDOW_WIDTH, TITLE_BAR_HEIGHT), 4)
        title_text = self.font_main.render("MATCH 3", True, COLOR_WHITE)
        self.screen.blit(title_text, (WINDOW_WIDTH // 2 - title_text.get_width() // 2, 10))
        
        # Board
        pygame.draw.rect(self.screen, COLOR_BLACK, (BOARD_OFFSET_X, BOARD_OFFSET_Y, 480, 480))
        border_color = COLOR_DARK_GRAY
        if time.time() < self.board_flash_red_until:
            border_color = COLOR_FLASH_RED
        pygame.draw.rect(self.screen, border_color, (BOARD_OFFSET_X, BOARD_OFFSET_Y, 480, 480), 4)
        
        for r in range(ROWS):
            for c in range(COLS):
                rect = pygame.Rect(BOARD_OFFSET_X + c * CELL_SIZE, BOARD_OFFSET_Y + r * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                
                # Cell highlight
                cell_bg = COLOR_BLACK
                cell_border = COLOR_GRAY
                
                if self.selected and self.selected.row == r and self.selected.col == c:
                    cell_bg = COLOR_SELECTED_BG
                    cell_border = COLOR_SELECTED_BORDER
                elif self.selected and any(n.row == r and n.col == c for n in self.get_neighbors(self.selected.row, self.selected.col)):
                    cell_bg = COLOR_OPTION_BG
                    cell_border = COLOR_OPTION_BORDER
                elif time.time() < self.invalid_flash_until and (r, c) in self.invalid_cells:
                    cell_bg = COLOR_INVALID_BG
                    cell_border = COLOR_INVALID_BORDER
                
                pygame.draw.rect(self.screen, cell_bg, rect)
                pygame.draw.rect(self.screen, cell_border, rect, 1)
        
        # Tokens
        for r in range(ROWS):
            for c in range(COLS):
                t = self.tokens[r][c]
                if t:
                    # Offset token drawing by the board offsets
                    old_x, old_y = t.curr_x, t.curr_y
                    t.curr_x += BOARD_OFFSET_X
                    t.curr_y += BOARD_OFFSET_Y
                    t.draw(self.screen)
                    t.curr_x, t.curr_y = old_x, old_y
        
        # Particles
        for p in self.particles:
            # Particle coordinates are board-relative
            s = pygame.Surface((p.size*2, p.size*2), pygame.SRCALPHA)
            pygame.draw.circle(s, (*p.color, int(p.life * 255)), (p.size, p.size), p.size)
            self.screen.blit(s, (BOARD_OFFSET_X + p.x - p.size, BOARD_OFFSET_Y + p.y - p.size))
            
        # Sidebar
        pygame.draw.rect(self.screen, COLOR_BLACK, (SIDEBAR_OFFSET_X, BOARD_OFFSET_Y, SIDEBAR_WIDTH, 480))
        pygame.draw.rect(self.screen, COLOR_DARK_GRAY, (SIDEBAR_OFFSET_X, BOARD_OFFSET_Y, SIDEBAR_WIDTH, 480), 4)
        
        # Sidebar content
        y_off = BOARD_OFFSET_Y + 20
        def draw_sidebar_item(label, value, color=COLOR_WHITE):
            lbl = self.font_small.render(label, True, COLOR_WHITE)
            val = self.font_main.render(str(value), True, color)
            self.screen.blit(lbl, (SIDEBAR_OFFSET_X + (SIDEBAR_WIDTH - lbl.get_width()) // 2, y_off))
            self.screen.blit(val, (SIDEBAR_OFFSET_X + (SIDEBAR_WIDTH - val.get_width()) // 2, y_off + 20))
            
        draw_sidebar_item("Level", self.level)
        pygame.draw.line(self.screen, (85, 85, 85), (SIDEBAR_OFFSET_X + 20, y_off + 60), (SIDEBAR_OFFSET_X + 180, y_off + 60), 1)
        y_off += 80
        
        score_color = (255, 102, 102) if self.score < 0 else COLOR_WHITE
        draw_sidebar_item("Score", self.score, score_color)
        pygame.draw.line(self.screen, (85, 85, 85), (SIDEBAR_OFFSET_X + 20, y_off + 60), (SIDEBAR_OFFSET_X + 180, y_off + 60), 1)
        y_off += 80
        
        draw_sidebar_item("Target", self.target)
        
        # Restart Button
        btn_rect = pygame.Rect(SIDEBAR_OFFSET_X + 40, y_off + 80, 120, 40)
        pygame.draw.rect(self.screen, (51, 51, 51), btn_rect, border_radius=4)
        pygame.draw.rect(self.screen, (102, 102, 102), btn_rect, 2, border_radius=4)
        btn_text = self.font_small.render("RESTART", True, COLOR_WHITE)
        self.screen.blit(btn_text, (btn_rect.centerx - btn_text.get_width() // 2, btn_rect.centery - btn_text.get_height() // 2))
        
        # Overlays
        now = time.time()
        for o in self.overlays:
            progress = (now - o.start_time) / o.duration
            if progress > 1: continue
            
            text_surf = self.font_large.render(o.text, True, o.color)
            opacity = int((1 - progress) * 255)
            
            # Apply opacity
            temp_surf = pygame.Surface((text_surf.get_width(), text_surf.get_height()), pygame.SRCALPHA)
            temp_surf.blit(text_surf, (0, 0))
            temp_surf.fill((255, 255, 255, 255 - opacity), special_flags=pygame.BLEND_RGBA_SUB)
            
            if o.fixed:
                self.screen.blit(temp_surf, (WINDOW_WIDTH // 2 - temp_surf.get_width() // 2, WINDOW_HEIGHT // 2 - temp_surf.get_height() // 2))
            else:
                y_pos = WINDOW_HEIGHT // 2 - temp_surf.get_height() // 2 - (40 * progress)
                self.screen.blit(temp_surf, (WINDOW_WIDTH // 2 - temp_surf.get_width() // 2, y_pos))
        
        pygame.display.flip()

    def run(self):
        import asyncio
        
        # We need an event loop to handle the async process_matches
        loop = asyncio.get_event_loop()
        
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    # Check restart button
                    if SIDEBAR_OFFSET_X + 40 <= mx <= SIDEBAR_OFFSET_X + 160 and \
                       BOARD_OFFSET_Y + 240 <= my <= BOARD_OFFSET_Y + 280:
                        self.reset_game()
                    else:
                        self.handle_click(mx, my)
            
            self.update(dt)
            self.draw()
            
            # Handle async tasks
            loop.stop() # This is tricky in a game loop. 
            # I'll refactor the async parts to use a timer instead of asyncio.
            
        pygame.quit()

# Since the game logic is sequential and involves waiting, I will rewrite the 
# async parts as a state-machine with timers to avoid complexity with asyncio in pygame.

class GameSequential(Game):
    def __init__(self):
        super().__init__()
        self.timer = 0.0
        self.pending_action = None

    def update(self, dt: float):
        super().update(dt)
        if self.pending_action:
            self.timer -= dt
            if self.timer <= 0:
                action = self.pending_action
                self.pending_action = None
                action()

    def schedule_action(self, delay, action):
        self.timer = delay
        self.pending_action = action

    def handle_click(self, x: int, y: int):
        if self.state != GameState.IDLE: return
        bx = x - BOARD_OFFSET_X
        by = y - BOARD_OFFSET_Y
        if not (0 <= bx < 480 and 0 <= by < 480): return
        c = bx // CELL_SIZE
        r = by // CELL_SIZE
        if self.selected is None:
            self.selected = Position(r, c)
        elif self.selected.row == r and self.selected.col == c:
            self.selected = None
        elif abs(self.selected.row - r) + abs(self.selected.col - c) == 1:
            self.state = GameState.ANIMATING
            self.attempt_swap_seq(self.selected.row, self.selected.col, r, c)
            self.selected = None
        else:
            self.selected = Position(r, c)

    def attempt_swap_seq(self, r1, c1, r2, c2):
        self.board[r1][c1], self.board[r2][c2] = self.board[r2][c2], self.board[r1][c1]
        if not self.find_all_matches():
            self.board[r1][c1], self.board[r2][c2] = self.board[r2][c2], self.board[r1][c1]
            self.invalid_cells = {(r1, c1), (r2, c2)}
            self.invalid_flash_until = time.time() + 0.3
            self.state = GameState.IDLE
            return
        
        t1 = self.tokens[r1][c1]
        t2 = self.tokens[r2][c2]
        if t1: t1.set_position(r2, c2)
        if t2: t2.set_position(r1, c1)
        self.tokens[r1][c1], self.tokens[r2][c2] = t2, t1
        
        self.schedule_action(ANIM_DURATION, lambda: self.process_matches_seq(1))

    def process_matches_seq(self, chain_level):
        matches = self.find_all_matches()
        if not matches:
            self.state = GameState.IDLE
            if self.score >= self.target:
                self.show_level_complete_seq()
            elif not self.has_valid_moves():
                self.state = GameState.GAME_OVER
                self.show_overlay_text("NO MOVES - GAME OVER", (255, 100, 100), 2.0, fixed=True)
            return

        groups = self.find_contiguous_groups(matches)
        total_points = 0
        has_red = False
        has_bonus = False
        for color_idx, count in groups:
            is_red = (color_idx == RED_INDEX)
            if is_red: has_red = True
            pts = -count if is_red else count
            if count > 3:
                has_bonus = True
                pts += -(count - 3) if is_red else (count - 3)
            total_points += pts * chain_level
        
        self.score += total_points
        if has_red:
            self.audio.play('match_red')
            self.board_flash_red_until = time.time() + 0.6
            self.show_overlay_text("OH NO!", (255, 100, 100), 2.0)
        elif chain_level > 1:
            self.audio.play('match_chain')
            self.show_overlay_text("NICE!", (255, 255, 255), 2.0)
        elif has_bonus or len(groups) > 1:
            self.audio.play('match_plus')
            if len(groups) > 1: self.show_overlay_text("MULTI-MATCH!", (255, 255, 255), 2.0)
            if has_bonus: self.show_overlay_text("BONUS!", (100, 255, 100), 2.0)
        else:
            self.audio.play('match')

        self.spawn_particles(matches)
        for m in matches:
            t = self.tokens[m[0]][m[1]]
            if t: t.is_removing = True
        
        self.schedule_action(0.25, lambda: self.finalize_matches_seq(matches, chain_level))

    def finalize_matches_seq(self, matches, chain_level):
        for m in matches:
            self.board[m[0]][m[1]] = -1
            self.tokens[m[0]][m[1]] = None
        
        self.apply_gravity_seq(chain_level)

    def apply_gravity_seq(self, chain_level):
        max_fall = 0
        for c in range(COLS):
            write_row = ROWS - 1
            for r in range(ROWS - 1, -1, -1):
                if self.board[r][c] != -1:
                    if write_row != r:
                        self.board[write_row][c] = self.board[r][c]
                        self.board[r][c] = -1
                        token = self.tokens[r][c]
                        self.tokens[write_row][c] = token
                        self.tokens[r][c] = None
                        if token:
                            token.set_position(write_row, c)
                            max_fall = max(max_fall, write_row - r)
                    write_row -= 1
        
        delay = 0
        if max_fall > 0:
            delay = min(0.5, max(ANIM_DURATION, max_fall * 0.08))
        
        self.schedule_action(delay, lambda: self.fill_empty_seq(chain_level))

    def fill_empty_seq(self, chain_level):
        max_fall = 0
        for c in range(COLS):
            empty_count = sum(1 for r in range(ROWS) if self.board[r][c] == -1)
            for r in range(empty_count):
                color = random.randint(0, len(TOKEN_COLORS) - 1)
                self.board[r][c] = color
                token = Token(r, c, color)
                token.curr_x = c * CELL_SIZE + (CELL_SIZE - TOKEN_SIZE) // 2
                token.curr_y = (r - empty_count) * CELL_SIZE + (CELL_SIZE - TOKEN_SIZE) // 2
                self.tokens[r][c] = token
                max_fall = max(max_fall, empty_count - r)
        
        delay = 0
        if max_fall > 0:
            delay = min(0.5, max(ANIM_DURATION, max_fall * 0.08))
        
        self.schedule_action(delay, lambda: self.process_matches_seq(chain_level + 1))

    def show_level_complete_seq(self):
        self.state = GameState.ANIMATING
        self.show_overlay_text("LEVEL COMPLETE!", (173, 216, 230), 2.0, fixed=True)
        self.schedule_action(2.0, self.advance_level_seq)

    def advance_level_seq(self):
        self.level += 1
        self.score = 0
        self.target = 100 + (self.level - 1) * 50
        self.board = [[-1 for _ in range(COLS)] for _ in range(ROWS)]
        self.tokens = [[None for _ in range(COLS)] for _ in range(ROWS)]
        self.init_board()
        self.show_overlay_text(f"BEGIN LEVEL {self.level}", (255, 105, 180), 1.2, fixed=True)
        self.audio.play('begin')
        self.schedule_action(1.2, lambda: setattr(self, 'state', GameState.IDLE))

    def run(self):
        running = True
        while running:
            dt = self.clock.tick(60) / 1000.0
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    if SIDEBAR_OFFSET_X + 40 <= mx <= SIDEBAR_OFFSET_X + 160 and \
                       BOARD_OFFSET_Y + 240 <= my <= BOARD_OFFSET_Y + 280:
                        self.reset_game()
                    else:
                        self.handle_click(mx, my)
            self.update(dt)
            self.draw()
        pygame.quit()

if __name__ == "__main__":
    game = GameSequential()
    game.run()
