"""Global constants for SuperAsteroids.

Per the project plan (see SuperAsteroids2.md), all tunable game parameters
live here so game mechanics can be adjusted in one place instead of
searching across state and entity modules. Stage 1 only uses a subset of
these; later stages will make use of the rest.
"""

# ------------------------------------------------------------------ framerate
FPS = 60                                       # spec: frame rate locked at 60 FPS
TEST_MODE_DURATION_SECONDS = 0.250             # --test exits after 250 ms

# -------------------------------------------------------------------- window
INITIAL_WINDOW_SIZE = (800, 600)
MIN_WINDOW_WIDTH = 400                         # resizes below this are rejected
MIN_WINDOW_HEIGHT = 300

# -------------------------------------------------------------------- colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 0, 0)
GREEN = (0, 255, 0)
YELLOW = (255, 255, 0)
ORANGE = (255, 165, 0)
LIGHT_BLUE = (173, 216, 230)
CYAN = (0, 255, 255)
LIGHT_RED = (255, 127, 127)
LIGHT_GRAY = (200, 200, 200)
DARK_GRAY = (64, 64, 64)
GRAY = (128, 128, 128)
ASTEROID_MIN_FILL = 72                         # 72,72,72  (random asteroid fills)
ASTEROID_MAX_FILL = 152                        # 152,152,152

# --------------------------------------------------------------------- fonts
# Pixel sizes for pygame's built-in font.
TITLE_FONT_SIZE = 96                           # "SuperAsteroids" on the title screen
HEADING_FONT_SIZE = 48                         # mode headings (GAME MODE / PAUSE / GAME OVER)
BODY_FONT_SIZE = 22                            # control instructions, on-screen hints

# ------------------------------------------------------------ title screen text
GAME_TITLE = "SuperAsteroids"
TITLE_SCREEN_CONTROL_LINES = (
    "Left/Right: rotate  |  Up: thrust  |  Space: weapon",
    "F11: full screen  |  F2: sound on/off",
    "ESC: exit",
)
TITLE_SCREEN_START_PROMPT = "Press Enter to start"
