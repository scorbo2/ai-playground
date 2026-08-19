"""Global constants for SuperAsteroids.

Per the project plan (see SuperAsteroids2.md), all tunable game parameters
live here so game mechanics can be adjusted in one place instead of
searching across state and entity modules.
"""

# ------------------------------------------------------------------ framerate
FPS = 60                                       # spec: frame rate locked at 60 FPS
TEST_MODE_DURATION_SECONDS = 0.250             # --test exits after 250 ms

# ------------------------------------------------------------------ audio
# Mixer pre_init configuration, applied before pygame.init() so the mixer
# setup is visible in one place. The values match both the shipped WAV
# format (44.1 kHz, 16-bit) and pygame's own defaults, so this is
# documentation of the config rather than a workaround.
SFX_SAMPLE_RATE = 44100
SFX_SAMPLE_SIZE = -16                          # signed 16-bit
SFX_MIXER_CHANNELS = 2    # stereo (1=mono); NOT the number of simultaneous voices
SFX_MIXER_BUFFER = 512

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
BROWN = (139, 69, 19)
LIGHT_BLUE = (173, 216, 230)
CYAN = (0, 255, 255)
LIGHT_RED = (255, 127, 127)
LIGHT_GRAY = (200, 200, 200)
DARK_GRAY = (64, 64, 64)
GRAY = (128, 128, 128)
ASTEROID_MIN_FILL = 72                         # 72,72,72  (random asteroid fills)
ASTEROID_MAX_FILL = 152                        # 152,152,152
FUEL_BAR_FG = (0, 255, 0)                      # bright green (same value as
                                               # GREEN; named per the spec's
                                               # suggested constants)
FUEL_BAR_BG = (0, 64, 0)                       # dark green

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
# Spawn clearance shared by EVERY spawn rule that must keep away from the
# craft (level asteroids, --debug powerups): never closer than this.
CRAFT_SPAWN_SAFE_DISTANCE = 200            # px; never spawn closer than this
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

# ------------------------------------------------------------- weapon system
# Shared by the charged weapons (Laser + Ramming Shield): 100 units of
# charge, activation blocked below 20, power levels capped at 3.
WEAPON_CHARGE_MAX = 100
WEAPON_MIN_ACTIVATE_CHARGE = 20
MAX_WEAPON_POWER = 3

# --------------------------------------------------------------------- cannon
CANNON_PROJECTILE_SIZE = 2             # px: projectiles are 2x2 square blocks
CANNON_PROJECTILE_SPEED = 6            # px/frame added to craft velocity
CANNON_PROJECTILE_DISTANCE = 1000      # px cumulative travel before expiring
                                        # (wraps are transparent to this counter)
CANNON_MAX_PROJECTILES_L1 = 3          # in-flight cap at power level 1
CANNON_PROJECTILE_SIZE_L3 = 4          # px: level 3 projectiles are 4x4 blocks
CANNON_PROJECTILE_SPEED_L3 = 8         # px/frame (levels 1-2 stay at 6)
CANNON_ARC_DEGREES_L2 = 20             # the 3-shot fan, levels 2 and 3
CANNON_MAX_PROJECTILES_L2 = 9          # in-flight cap at power level 2
# One row per power level (index = power_level - 1):
# (shots per press, arc degrees, projectile size, speed, color, in-flight cap).
# cap None = unlimited (level 3). A press is blocked when in_flight +
# shots_per_press would exceed the cap - which reproduces the spec's level 1
# rule ("cap of 3") and level 2 rule ("more than 6 in flight -> nothing").
CANNON_LEVEL_SPECS = (
    (1, 0, CANNON_PROJECTILE_SIZE, CANNON_PROJECTILE_SPEED, YELLOW,
     CANNON_MAX_PROJECTILES_L1),
    (3, CANNON_ARC_DEGREES_L2, CANNON_PROJECTILE_SIZE, CANNON_PROJECTILE_SPEED,
     ORANGE, CANNON_MAX_PROJECTILES_L2),
    (3, CANNON_ARC_DEGREES_L2, CANNON_PROJECTILE_SIZE_L3,
     CANNON_PROJECTILE_SPEED_L3, WHITE, None),
)
CANNON_SELF_GRACE = 30                 # frames a projectile cannot hit its own craft
FRIENDLY_FIRE_MESSAGE = "FRIENDLY FIRE!"

# -------------------------------------------------------------------- laser
# One tuple per power level (index = power_level - 1). Level 3 keeps level 2's
# drain/recharge rates and goes white (the beam color is derived in Laser).
LASER_WIDTHS = (1, 2, 3)               # px
LASER_LENGTHS = (100, 125, 150)        # px, from the craft's tip
LASER_DRAIN = (3, 2, 2)                # charge units/frame while the key is held
LASER_RECHARGE = (1, 2, 2)             # charge units/frame once released
LASER_SAMPLE_STEP = 2                  # px per collision sample (spec suggestion)

# ------------------------------------------------------------------- shield
SHIELD_RADII = (35, 35, 40)            # px around the craft
SHIELD_BORDER_WIDTHS = (1, 2, 4)       # px
SHIELD_DRAIN = (5, 3, 3)               # charge units/frame while the key is held
SHIELD_RECHARGE = (1, 3, 3)            # charge units/frame once released
# Ramming bounce speed = impacting radius / divisor (spec: 40 px rock at
# level 1 -> 40/5 = 8 px/frame, the craft's max speed).
SHIELD_BOUNCE_DIVISORS = (5, 8, 10)

# ----------------------------------------------------------------- shrapnel mines
# A mine is dropped from the craft's rear, coasts to a stop under the craft's
# friction, and - once its launch grace expires - arms when something comes
# within its invisible activation radius. A mine that is touched outright (or
# whose arming countdown runs out) detonates into an 8-way burst of cannon
# projectiles. Per the spec, mines and their projectiles wrap the screen, and
# undetonated mines leave play at the end of each level.
MINE_RADIUS = 12                       # drawn circle = collision radius (spec)
MINE_OUTLINE_WIDTH = 2                 # white border
MINE_FILL = BROWN                      # brown fill
# The "crosshair" inside the circle pulses YELLOW for a few frames on a
# fixed cadence. Its steady color is light gray while the mine is armed but
# not yet activated, and light red once activated (the pulse itself stays).
MINE_CROSSHAIR_IDLE = (170, 170, 170)  # light gray, unactivated
MINE_CROSSHAIR_ACTIVE = LIGHT_RED      # light red, activated
MINE_CROSSHAIR_PULSE_INTERVAL = 120    # frames between pulses
MINE_CROSSHAIR_PULSE_YELLOWS = 5       # frames yellow during each pulse
# Launch: the craft's velocity plus this much BACKWARD drift (spec: 2 px/frame).
MINE_BACK_LAUNCH_SPEED = 2
# Invisible activation radius: ANY object entering it (once out of grace)
# arms the mine and starts the detonation countdown. Wrap-aware (spec).
MINE_ACTIVATION_RADIUS = 150
MINE_GRACE = 90                        # frames with no activation (all objects)
                                       # and no self-collision (craft only)
MINE_DETONATION_DELAY = 180            # frames from activation to explosion
# Detonation: an outward burst of cannon-style projectiles (N,NE,E,SE,S,SW,W,
# NW) plus a 100-particle brown explosion (same count as a UFO, spec).
MINE_BURST_ANGLE_STEP = 45             # 8 compass points, 45 deg apart
MINE_BURST_ANGLES = tuple(a * MINE_BURST_ANGLE_STEP for a in range(8))
MINE_BURST_PROJECTILE_DISTANCE = 500   # shorter than the player's 1000 px
MINE_DETONATION_PARTICLE_COUNT = 100   # same as the UFO explosion
MINE_DETONATION_COLOR = BROWN
# One row per power level (index = power_level - 1):
#   (in-play cap, burst projectile size, burst projectile speed, its color).
# Levels 1 and 2 burst level-1 cannon shots (2x2 yellow at 6 px/frame); level
# 3 bumps the burst to level-3 cannon shots (4x4 white at 8 px/frame). All
# burst shots travel MINE_BURST_PROJECTILE_DISTANCE and carry no grace.
MINE_LEVEL_SPECS = (
    (1, CANNON_PROJECTILE_SIZE, CANNON_PROJECTILE_SPEED, YELLOW),
    (3, CANNON_PROJECTILE_SIZE, CANNON_PROJECTILE_SPEED, YELLOW),
    (5, CANNON_PROJECTILE_SIZE_L3, CANNON_PROJECTILE_SPEED_L3, WHITE),
)
MINE_FRIENDLY_FIRE_MESSAGE = "FRIENDLY FIRE - WATCH THOSE MINES!"

# ------------------------------------------------------------------ powerups
POWERUP_RADIUS = 20                    # px
POWERUP_SPEED = 2                      # px/frame drift
POWERUP_INTERVAL = 30 * 60             # 1800 frames of active play
POWERUP_GRACE = 90                     # frames a fresh icon cannot be destroyed
POWERUP_SPAWN_ATTEMPTS = 50            # clearance-check tries for timer spawns
POWERUP_TYPES = (
    ("Cannon", YELLOW, "C"),           # (weapon name, icon color, label letter)
    ("Laser", LIGHT_BLUE, "L"),
    ("Shield", RED, "S"),
    # Shrapnel mine icon (spec: Powerups): brown circle, white "M". The name
    # matches ShrapnelMines.NAME so the HUD and powerup share one string.
    ("Shrapnel mines", BROWN, "M"),
)
POWERUP_COLORS = {name: color for name, color, _letter in POWERUP_TYPES}
POWERUP_LETTERS = {name: letter for name, _color, letter in POWERUP_TYPES}
# Chance of a powerup drop on every asteroid split/destruction event, by
# level; level 5+ clamps to the last entry (1%).
POWERUP_DROP_CHANCES = (0.08, 0.06, 0.04, 0.02, 0.01)

# --------------------------------------------------------------------- fuel
# The craft's tank (spec: "Fuel"): fresh games start full; one unit is
# consumed per frame the craft ACTUALLY thrusts; at 0 the craft cannot
# thrust at all (no acceleration, no exhaust puffs, no thruster sound -
# rotation and weapons keep working). Between levels the tank CARRIES OVER
# and receives a flat bonus; a brand-new game constructs a fresh craft,
# which is what "restores" it to max - level starts must NOT refill it.
FUEL_MAX = 600                             # units, a fresh game's tank
FUEL_CONSUMPTION_PER_FRAME = 1             # per thrusting frame
FUEL_LEVEL_END_BONUS = 120                 # added on every level advance (clamped)
FUEL_POD_PICKUP = 60                       # added per pod collected (clamped)
# Independent per-event roll, applied to EVERY asteroid split or
# destruction event, whatever delivered the hit (spec: Fuel).
FUEL_POD_DROP_CHANCE = 0.02
# The pod itself (spec: Fuel): a rounded 20 px square drawn with a white
# border and a self-oscillating green fill. It drifts, wraps, and collides
# EXACTLY like a powerup icon, so the speed/grace constants are the shared
# powerup ones (POWERUP_SPEED, POWERUP_GRACE).
FUEL_POD_SIZE = 20                         # px, the drawn square
FUEL_POD_CORNER_RADIUS = 6
FUEL_POD_BORDER_WIDTH = 4                  # white border
# Bounding circle for ALL collision checks (spec: "Collision detection" -
# 12 px from the pod's center, regardless of the drawn square).
FUEL_POD_RADIUS = 12
# Fill color ping-pongs 0,128,0 -> 0,255,0 -> 0,128,0 ... at one green
# channel unit per frame (spec: Fuel).
FUEL_POD_GREEN_MIN = 128
FUEL_POD_GREEN_MAX = 255

# --------------------------------------------------------------------- UFO
# Per the spec ("Enemy UFOs"): a hostile that drifts in a straight line,
# deflects periodically, and fires at the craft. Every timer here is counted
# in frames of ACTIVE play, so pause (and level intros) suspend it for free.
UFO_OVAL_WIDTH = 60                    # px, the drawn ellipse is 60 wide...
UFO_OVAL_HEIGHT = 35                   # ...by 35 tall
UFO_OUTLINE_WIDTH = 2                  # px, matches the other outlines
UFO_RADIUS = 60                        # bounding circle (spec: Collision)
UFO_SPEED = 2                          # px/frame, straight-line drift
UFO_SPAWN_ATTEMPTS = 50                # random tries for a safe spawn spot
UFO_INTERVAL = 1 * 60 * 60             # 3600 frames (1 min of active play)
UFO_MAX_ACTIVE = 3                     # cap; an expired timer at cap just resets
UFO_DIRECTION_CHANGE_INTERVAL = 300    # frames between random deflections
UFO_TURN_MAX_DEGREES = 30              # max deflection, random left/right
UFO_FIRE_INTERVAL = 120                # frames between hostile shots
UFO_PROJECTILE_DISTANCE = 500          # half of the player's level 1 range
HOSTILE_FIRE_MESSAGE = "HOSTILE FIRE!"

# -------------------------------------------------------------------- debug
# --debug hotkeys: C/L/S spawn a powerup of that type (no cap), U spawns a
# UFO if under the active cap. Spawned powerup positions avoid the craft's
# safe distance.
DEBUG_SPAWN_ATTEMPTS = 50

# -------------------------------------------------------------- level intro
# "BEGIN LEVEL N" sequence at the start of every level (spec: Game Mode):
# full opacity for the hold, then a linear fade out.
LEVEL_INTRO_HOLD = 90                  # frames at full opacity
LEVEL_INTRO_FADE = 30                  # frames to fade to invisible

# -------------------------------------------------------------- starfield
# Subtle background in ALL modes (spec: "Starfield background"): static
# single-pixel grayscale stars whose brightness oscillates between
# STAR_MAX_BRIGHTNESS and 0. Each star keeps its own phase (random starting
# brightness and direction), which is what makes the field look "subtle"
# instead of the whole sky pulsing in lockstep.
STAR_COUNT_RANGE = (150, 300)         # random star count, per field
STAR_MAX_BRIGHTNESS = 192             # the top of the RGB oscillation
STAR_BRIGHTNESS_RATE = 0.001          # 0.1% of max brightness, per frame

# -------------------------------------------------------------- particles
# Cosmetic explosion debris (spec: Asteroids / Enemy UFOs). Particles have
# NO collision detection and do NOT screen-wrap: at 5-15 px/frame they fade
# to invisible well within a second or two, so wrapping would only cost
# money for no visible benefit.
PARTICLE_SIZE = 4                     # px, the square debris blocks (spec
                                      # gives no size; 2 looked single-pixel,
                                      # 4 reads as a deliberate explosion)
PARTICLE_SPEED_RANGE = (5, 15)        # px/frame, random direction per particle
PARTICLE_ALPHA_DECAY_RANGE = (0.03, 0.10)  # fraction of CURRENT alpha/frame
PARTICLE_COUNT_PER_RADIUS = 3         # an event spawns radius * 3 (40 -> 120)
SPLIT_PARTICLE_COLORS = (YELLOW, RED, ORANGE)   # one, random per particle
WRECKAGE_BRIGHTNESS_RANGE = (128, 255)  # mid-gray .. white, per particle
UFO_PARTICLE_COUNT = 100              # flat, per the spec

# --------------------------------------------------------------- thruster
# Rear-of-ship exhaust while Up is held (spec: "Thrusters"). Purely
# cosmetic: no collision detection, no screen wrap.
THRUSTER_PUFFS_PER_FRAME_RANGE = (2, 3)      # random count, per frame
THRUSTER_PUFF_RADIUS_RANGE = (3, 8)          # px, random per puff
THRUSTER_BACK_SPEED_RANGE = (6, 10)          # px/frame, added opposite the heading
THRUSTER_ALPHA_DECAY_RANGE = (0.03, 0.06)    # fraction of current alpha/frame
THRUSTER_COLORS = (YELLOW, ORANGE, RED)      # one, random per puff

# ------------------------------------------------------------------------ HUD
# Upper-right HUD (spec: "Heads-up display"). Everything is drawn at a single
# ~60% opacity (alpha 153) on a transparent surface.
HUD_WIDTH = 200
HUD_HEIGHT = 220                        # spec value; the Stage 10 fuel line
                                        # (always the LAST line) needs it
HUD_MARGIN = 10
HUD_CORNER_RADIUS = 12
HUD_BORDER_WIDTH = 4
HUD_ALPHA = 153                        # ~60% for border AND contents
HUD_FONT_SIZE = 18                     # "scale to fit": lines shrink to fit
HUD_LINE_SPACING = 18
HUD_TEXT_PADDING = 8
HUD_MIN_FONT_SIZE = 10                 # floor for the fit-to-width shrink
HUD_CHARGE_BAR_HEIGHT = 10             # px tall, inside its 18px line slot
