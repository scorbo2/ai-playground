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

# ------------------------------------------------------------------ asteroids
# Per-level spawn rules. Speed range is a pure function of the level number,
# but the COUNT is not: it grows by a random 1-2 on each level advancement,
# so the owning game state tracks the current count and passes it in
# (Stage 4 wires up the advancement trigger itself).
LEVEL_1_ASTEROID_COUNT = 5
LEVEL_ASTEROID_COUNT_INCREMENT = (1, 2)        # random, per level advancement
ASTEROID_LARGEST_RADIUS = 40                   # level-start asteroids
ASTEROID_MIN_SPEED = 1.5                       # px/frame, level 1 lower bound
ASTEROID_MAX_SPEED = 2.5                       # px/frame, level 1 upper bound
ASTEROID_SPEED_INCREMENT_PER_LEVEL = 0.3       # added to both bounds, no cap
ASTEROID_PLAYER_SAFE_DISTANCE = 200            # px; never spawn closer than this
ASTEROID_SPAWN_ATTEMPTS = 50                   # random tries before a corner
# Tumbling. Rotates inversely with size: radius >= LARGE is 1 deg/frame,
# radius <= SMALL is 10 deg/frame, linearly interpolated between the anchors.
ASTEROID_ROTATION_RADIUS_LARGE = 40
ASTEROID_ROTATION_RATE_LARGE = 1.0             # degrees/frame
ASTEROID_ROTATION_RADIUS_SMALL = 20
ASTEROID_ROTATION_RATE_SMALL = 10.0            # degrees/frame
# Weapon impact -> split rules (stages 4-6 trigger these). Radius below the
# split threshold is destroyed outright instead of splitting further.
ASTEROID_MIN_RADIUS_FOR_SPLIT = 20
ASTEROID_SPLIT_CHILDREN = (2, 3)               # random per impact
ASTEROID_SPLIT_RADIUS_DIVISOR = 1.5
ASTEROID_SPLIT_SPEED_MULTIPLIER = 1.2
# Irregular outline, per the spec's suggested generation.
ASTEROID_VERTEX_COUNT_RANGE = (8, 14)
ASTEROID_VERTEX_RADIUS_FACTOR_RANGE = (0.75, 1.25)
ASTEROID_OUTLINE_WIDTH = 2

# ------------------------------------------------------------- title screen
# Cosmetic asteroids: same movement, tumbling, and wrapping as game asteroids.
TITLE_ASTEROID_COUNT_RANGE = (3, 6)

# ---------------------------------------------------------------- player craft
# The craft is an elongated triangle, 20 px wide (base) by 30 px tall
# (apex to base), drawn with a white outline and light gray fill.
PLAYER_SHAPE_WIDTH = 20
PLAYER_SHAPE_HEIGHT = 30
PLAYER_OUTLINE_WIDTH = 2
# Bounding circle for ALL collision checks, and the wrap margin (spec:
# "Collision detection" -> "Player craft: a simple 20px radius circle").
PLAYER_RADIUS = 20
# Screen-angle convention (degrees): 0 = +X axis, positive toward +Y
# (screen coordinates). "Up" is therefore -90, the craft's start heading.
PLAYER_START_ANGLE = -90.0
PLAYER_ROTATION_SPEED = 5.0            # degrees/frame while left/right held
PLAYER_ACCELERATION = 0.3              # px/frame^2 in facing dir while Up held
PLAYER_MAX_SPEED = 8.0                 # px/frame, clamped after thrust
PLAYER_FRICTION = 0.98                 # velocity multiplier/frame when not thrusting
PLAYER_STALL_SPEED = 0.05              # px/frame; below this, speed snaps to 0
