"""Game constants for Quakelike."""

# Map dimensions
MAP_WIDTH = 80
MAP_HEIGHT = 40
NUM_MAPS = 40

# Inventory
MAX_INVENTORY_SIZE = 10

# Player starting stats
PLAYER_MAX_HEALTH = 100
PLAYER_START_HEALTH = 100
PLAYER_MAX_ARMOR = 200

# Melee damage (axe damage from Quake)
MELEE_DAMAGE_MIN = 10
MELEE_DAMAGE_MAX = 20

# Tile characters
TILE_WALL = '#'
TILE_FLOOR = '.'
TILE_DOOR = '+'
TILE_SLIPGATE_DOWN = '>'  # Go to next map
TILE_SLIPGATE_UP = '<'    # Go to previous map
TILE_ENTRANCE = 'E'       # Special entrance on map 1
TILE_WATER = '~'
TILE_LAVA = '='

# Entity characters
CHAR_PLAYER = '@'

# Colors (ANSI-like color names for frontend)
COLOR_WALL = '#8B7355'
COLOR_FLOOR = '#4A4A4A'
COLOR_DOOR = '#CD853F'
COLOR_SLIPGATE = '#9400D3'
COLOR_ENTRANCE = '#FFD700'
COLOR_WATER = '#4169E1'
COLOR_LAVA = '#FF4500'
COLOR_PLAYER = '#FFFFFF'

# Direction vectors (y, x)
DIRECTIONS = {
    'k': (-1, 0),   # up
    'j': (1, 0),    # down
    'l': (0, 1),    # right
    'h': (0, -1),   # left
    'u': (-1, 1),   # diag up-right
    'y': (-1, -1),  # diag up-left
    'n': (1, 1),    # diag down-right
    'b': (1, -1),   # diag down-left
}

# Key bindings
KEY_UP = 'k'
KEY_DOWN = 'j'
KEY_RIGHT = 'l'
KEY_LEFT = 'h'
KEY_UP_RIGHT = 'u'
KEY_UP_LEFT = 'y'
KEY_DOWN_RIGHT = 'n'
KEY_DOWN_LEFT = 'b'
KEY_SLIPGATE_DOWN = '>'
KEY_SLIPGATE_UP = '<'
KEY_INVENTORY = 'i'
KEY_TRANSFER = 'Tab'
KEY_EXAMINE = 'x'
KEY_USE = 'Return'
KEY_TARGET = 't'
KEY_TARGET_PREV = 'T'
KEY_TARGET_CLEAR = 'Alt-t'
KEY_FIRE = 'f'
KEY_SWAP_WEAPON = 'w'
KEY_MESSAGE_LOG = 'p'
KEY_HELP = '?'
KEY_SAVE = 'S'
KEY_QUIT = 'Q'
KEY_NAV_UP = 'ArrowUp'
KEY_NAV_DOWN = 'ArrowDown'
KEY_NAV_LEFT = 'ArrowLeft'
KEY_NAV_RIGHT = 'ArrowRight'
KEY_FAST_TRAVEL = '_'
KEY_REST = '.'   # Same char as TILE_FLOOR; safe: key input and tile chars are separate namespaces
KEY_PICKUP = ','

# Map generation parameters
MIN_ROOM_SIZE = 4
MAX_ROOM_SIZE = 12
MIN_ROOMS = 6
MAX_ROOMS = 14
CORRIDOR_WIDTH = 1

# Message log
MAX_VISIBLE_MESSAGES = 3
