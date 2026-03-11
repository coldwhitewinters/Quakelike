"""Map data structures and procedural generation for Quakelike."""

from __future__ import annotations
import random
from dataclasses import dataclass, field
from typing import Optional

from quakelike.constants import (
    MAP_WIDTH, MAP_HEIGHT, TILE_WALL, TILE_FLOOR, TILE_DOOR,
    TILE_SLIPGATE_DOWN, TILE_SLIPGATE_UP, TILE_ENTRANCE,
    TILE_WATER, TILE_LAVA, TILE_CORPSE, COLOR_CORPSE,
    MIN_ROOM_SIZE, MAX_ROOM_SIZE, MIN_ROOMS, MAX_ROOMS,
    NUM_MAPS, DOOR_CLOSE_DELAY,
)
from quakelike.entity import Position
from quakelike.items import (
    Item, ItemDef, create_item, RUNE,
    ALL_WEAPONS, ALL_AMMO, ALL_ARMOR, ALL_HEALTH, ALL_POWERUPS,
    AXE, SHOTGUN, SHELLS_SMALL, SMALL_HEALTH, MEDIUM_HEALTH, MEGAHEALTH,
)
from quakelike.enemies import (
    Enemy, EnemyDef, ALL_ENEMIES,
)


@dataclass
class Room:
    """A rectangular room on the map."""
    y: int
    x: int
    height: int
    width: int

    @property
    def center(self) -> Position:
        """Get the center position of the room."""
        return Position(self.y + self.height // 2, self.x + self.width // 2)

    @property
    def y2(self) -> int:
        """Get the bottom edge y-coordinate (y + height)."""
        return self.y + self.height

    @property
    def x2(self) -> int:
        """Get the right edge x-coordinate (x + width)."""
        return self.x + self.width

    def intersects(self, other: Room, margin: int = 1) -> bool:
        """Check if this room overlaps with another (with margin)."""
        return (self.x - margin < other.x2 + margin and
                self.x2 + margin > other.x - margin and
                self.y - margin < other.y2 + margin and
                self.y2 + margin > other.y - margin)


@dataclass
class GameMap:
    """A single game map/level."""
    width: int = MAP_WIDTH
    height: int = MAP_HEIGHT
    level: int = 0
    tiles: list[list[str]] = field(default_factory=list)
    rooms: list[Room] = field(default_factory=list)
    items_on_ground: dict[tuple[int, int], list[Item]] = field(default_factory=dict)
    enemies: list[Enemy] = field(default_factory=list)
    corpses: dict[tuple[int, int], dict[str, str]] = field(default_factory=dict)
    slipgate_down_pos: Optional[Position] = None
    slipgate_up_pos: Optional[Position] = None
    entrance_pos: Optional[Position] = None
    player_start: Optional[Position] = None
    explored: set[tuple[int, int]] = field(default_factory=set)
    open_doors: dict = field(default_factory=dict)  # pos (y, x) → close_turn

    def __post_init__(self):
        """Initialize the tile grid if not provided."""
        if not self.tiles:
            self.tiles = [[TILE_WALL] * self.width for _ in range(self.height)]

    def get_tile(self, y: int, x: int) -> str:
        """Get tile at position."""
        if 0 <= y < self.height and 0 <= x < self.width:
            return self.tiles[y][x]
        return TILE_WALL

    def set_tile(self, y: int, x: int, tile: str) -> None:
        """Set tile at position."""
        if 0 <= y < self.height and 0 <= x < self.width:
            self.tiles[y][x] = tile

    def is_open_door(self, y: int, x: int) -> bool:
        """Check if the door at (y, x) is currently open."""
        return (y, x) in self.open_doors

    def open_door(self, y: int, x: int, close_turn: int) -> None:
        """Open the door at (y, x); it will auto-close at close_turn."""
        self.open_doors[(y, x)] = close_turn

    def close_door(self, y: int, x: int) -> None:
        """Close the door at (y, x)."""
        self.open_doors.pop((y, x), None)

    def is_walkable(self, y: int, x: int) -> bool:
        """Check if a tile can be walked on."""
        tile = self.get_tile(y, x)
        if tile == TILE_DOOR:
            return (y, x) in self.open_doors
        return tile in (TILE_FLOOR, TILE_SLIPGATE_DOWN,
                        TILE_SLIPGATE_UP, TILE_ENTRANCE, TILE_WATER,
                        TILE_LAVA)

    def is_blocking(self, y: int, x: int) -> bool:
        """Check if a tile blocks movement."""
        return not self.is_walkable(y, x)

    def is_transparent(self, y: int, x: int) -> bool:
        """Check if a tile allows line of sight."""
        tile = self.get_tile(y, x)
        if tile == TILE_DOOR:
            return (y, x) in self.open_doors
        return tile != TILE_WALL

    def get_items_at(self, y: int, x: int) -> list[Item]:
        """Get items on the ground at position."""
        return self.items_on_ground.get((y, x), [])

    def add_item_at(self, y: int, x: int, item: Item) -> None:
        """Add item to the ground at position."""
        key = (y, x)
        if key not in self.items_on_ground:
            self.items_on_ground[key] = []
        self.items_on_ground[key].append(item)

    def remove_item_at(self, y: int, x: int, index: int) -> Optional[Item]:
        """Remove item from the ground at position."""
        key = (y, x)
        items = self.items_on_ground.get(key, [])
        if 0 <= index < len(items):
            item = items.pop(index)
            if not items:
                del self.items_on_ground[key]
            return item
        return None

    def get_enemy_at(self, y: int, x: int) -> Optional[Enemy]:
        """Get enemy at position."""
        for enemy in self.enemies:
            if enemy.is_alive and enemy.pos.y == y and enemy.pos.x == x:
                return enemy
        return None

    def get_living_enemies(self) -> list[Enemy]:
        """Get all living enemies on the map."""
        return [e for e in self.enemies if e.is_alive]

    def add_corpse(self, y: int, x: int, name: str) -> None:
        """Place a corpse marker at (y, x). Purely visual; does not block movement."""
        self.corpses[(y, x)] = {'char': TILE_CORPSE, 'color': COLOR_CORPSE, 'name': name}

    def get_random_floor_pos(self, rng: random.Random) -> Optional[Position]:
        """Get a random floor tile position."""
        floor_tiles = []
        for y in range(self.height):
            for x in range(self.width):
                if self.tiles[y][x] == TILE_FLOOR:
                    floor_tiles.append(Position(y, x))
        if floor_tiles:
            return rng.choice(floor_tiles)
        return None

    def reveal_around(self, y: int, x: int, radius: int = 200) -> None:
        """Reveal tiles around a position (simple FOV).

        The default radius of 200 exceeds MAP_WIDTH + MAP_HEIGHT so every
        tile on the map is a candidate; wall blocking is handled entirely
        by the Bresenham LOS check.
        """
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                ny, nx = y + dy, x + dx
                if 0 <= ny < self.height and 0 <= nx < self.width:
                    if self._has_los(y, x, ny, nx):
                        self.explored.add((ny, nx))

    def _has_los(self, y1: int, x1: int, y2: int, x2: int) -> bool:
        """Simple line of sight check using Bresenham's line."""
        points = bresenham_line(y1, x1, y2, x2)
        for py, px in points[1:-1]:  # Skip start and end
            if not self.is_transparent(py, px):
                return False
        return True

    def has_line_of_sight(self, pos1: Position, pos2: Position) -> bool:
        """Check line of sight between two positions."""
        return self._has_los(pos1.y, pos1.x, pos2.y, pos2.x)

    def get_line(self, pos1: Position, pos2: Position) -> list[Position]:
        """Get all positions along a line between two points."""
        points = bresenham_line(pos1.y, pos1.x, pos2.y, pos2.x)
        return [Position(y, x) for y, x in points]


def bresenham_line(y1: int, x1: int, y2: int, x2: int) -> list[tuple[int, int]]:
    """Bresenham's line algorithm."""
    points = []
    dx = abs(x2 - x1)
    dy = abs(y2 - y1)
    sx = 1 if x1 < x2 else -1
    sy = 1 if y1 < y2 else -1
    err = dx - dy
    cy, cx = y1, x1

    while True:
        points.append((cy, cx))
        if cy == y2 and cx == x2:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            cx += sx
        if e2 < dx:
            err += dx
            cy += sy
    return points


def _find_safe_start(gmap: GameMap, anchor: Position) -> Position:
    """Find a walkable tile near the anchor position for player placement."""
    # Try the tile directly below first
    for dy, dx in [(1, 0), (-1, 0), (0, 1), (0, -1),
                   (1, 1), (1, -1), (-1, 1), (-1, -1)]:
        ny, nx = anchor.y + dy, anchor.x + dx
        if gmap.is_walkable(ny, nx):
            return Position(ny, nx)
    # Fallback: return anchor itself
    return anchor.copy()


def generate_map(level: int, rng: random.Random) -> GameMap:
    """Generate a procedural map for a given level.

    Creates Quake-style indoor environments with rooms and corridors.
    """
    gmap = GameMap(level=level)

    # Generate rooms
    rooms = _generate_rooms(gmap, rng)
    gmap.rooms = rooms

    # Carve rooms into the map
    for room in rooms:
        _carve_room(gmap, room)

    # Connect rooms with corridors (sequential + loop connections)
    for i in range(len(rooms) - 1):
        _connect_rooms(gmap, rooms[i], rooms[i + 1], rng)

    # Add extra connections for loops (Quake-like non-linear layout)
    if len(rooms) > 3:
        num_extra = rng.randint(1, max(1, len(rooms) // 3))
        for _ in range(num_extra):
            r1 = rng.choice(rooms)
            r2 = rng.choice(rooms)
            if r1 is not r2:
                _connect_rooms(gmap, r1, r2, rng)

    # Add doors at corridor-room junctions
    _add_doors(gmap, rng)

    # Place slipgates (BEFORE environment features to protect them)
    if level == 0:
        # First map has entrance
        gmap.entrance_pos = rooms[0].center
        gmap.set_tile(rooms[0].center.y, rooms[0].center.x, TILE_ENTRANCE)
        gmap.player_start = _find_safe_start(gmap, rooms[0].center)
    else:
        # Slipgate up (back to previous map)
        gmap.slipgate_up_pos = rooms[0].center
        gmap.set_tile(rooms[0].center.y, rooms[0].center.x, TILE_SLIPGATE_UP)
        gmap.player_start = _find_safe_start(gmap, rooms[0].center)

    if level < NUM_MAPS - 1:
        # Slipgate down (to next map)
        last_room = rooms[-1]
        gmap.slipgate_down_pos = last_room.center
        gmap.set_tile(last_room.center.y, last_room.center.x, TILE_SLIPGATE_DOWN)

    # Add some water/lava features
    _add_environment_features(gmap, rooms, rng)

    # Place items
    _place_items(gmap, level, rooms, rng)

    # Place enemies
    _place_enemies(gmap, level, rooms, rng)

    # Place rune on last map
    if level == NUM_MAPS - 1:
        last_room = rooms[-1]
        gmap.add_item_at(last_room.center.y, last_room.center.x, create_item(RUNE))

    return gmap


def _generate_rooms(gmap: GameMap, rng: random.Random) -> list[Room]:
    """Generate non-overlapping rooms."""
    rooms = []
    attempts = 0
    target = rng.randint(MIN_ROOMS, MAX_ROOMS)

    while len(rooms) < target and attempts < 200:
        w = rng.randint(MIN_ROOM_SIZE, MAX_ROOM_SIZE)
        h = rng.randint(MIN_ROOM_SIZE, MAX_ROOM_SIZE)
        x = rng.randint(1, gmap.width - w - 1)
        y = rng.randint(1, gmap.height - h - 1)
        room = Room(y, x, h, w)

        if not any(room.intersects(r) for r in rooms):
            rooms.append(room)
        attempts += 1

    return rooms


def _carve_room(gmap: GameMap, room: Room) -> None:
    """Carve out a room in the map."""
    for y in range(room.y, room.y2):
        for x in range(room.x, room.x2):
            if 0 < y < gmap.height - 1 and 0 < x < gmap.width - 1:
                gmap.tiles[y][x] = TILE_FLOOR


def _connect_rooms(gmap: GameMap, room1: Room, room2: Room,
                   rng: random.Random) -> None:
    """Connect two rooms with an L-shaped corridor."""
    c1 = room1.center
    c2 = room2.center

    if rng.random() < 0.5:
        _carve_h_corridor(gmap, c1.x, c2.x, c1.y)
        _carve_v_corridor(gmap, c1.y, c2.y, c2.x)
    else:
        _carve_v_corridor(gmap, c1.y, c2.y, c1.x)
        _carve_h_corridor(gmap, c1.x, c2.x, c2.y)


def _carve_h_corridor(gmap: GameMap, x1: int, x2: int, y: int) -> None:
    """Carve a horizontal corridor."""
    for x in range(min(x1, x2), max(x1, x2) + 1):
        if 0 < y < gmap.height - 1 and 0 < x < gmap.width - 1:
            gmap.tiles[y][x] = TILE_FLOOR


def _carve_v_corridor(gmap: GameMap, y1: int, y2: int, x: int) -> None:
    """Carve a vertical corridor."""
    for y in range(min(y1, y2), max(y1, y2) + 1):
        if 0 < y < gmap.height - 1 and 0 < x < gmap.width - 1:
            gmap.tiles[y][x] = TILE_FLOOR


def _add_doors(gmap: GameMap, rng: random.Random) -> None:
    """Add doors at corridor-room transitions."""
    for y in range(1, gmap.height - 1):
        for x in range(1, gmap.width - 1):
            if gmap.tiles[y][x] != TILE_FLOOR:
                continue
            # Check for door-worthy positions (corridor meets room)
            h_walls = (gmap.tiles[y - 1][x] == TILE_WALL and
                       gmap.tiles[y + 1][x] == TILE_WALL)
            v_walls = (gmap.tiles[y][x - 1] == TILE_WALL and
                       gmap.tiles[y][x + 1] == TILE_WALL)
            if not (h_walls or v_walls):
                continue
            # Only place at junctions: at least one perpendicular neighbour
            # must open into non-corridor space (i.e., a room floor that does
            # not itself have walls on the same two opposite sides).
            is_junction = False
            if h_walls:
                for nx in (x - 1, x + 1):
                    if (gmap.tiles[y][nx] == TILE_FLOOR and
                            not (gmap.tiles[y - 1][nx] == TILE_WALL and
                                 gmap.tiles[y + 1][nx] == TILE_WALL)):
                        is_junction = True
                        break
            if v_walls and not is_junction:
                for ny in (y - 1, y + 1):
                    if (gmap.tiles[ny][x] == TILE_FLOOR and
                            not (gmap.tiles[ny][x - 1] == TILE_WALL and
                                 gmap.tiles[ny][x + 1] == TILE_WALL)):
                        is_junction = True
                        break
            if is_junction and rng.random() < 0.3:
                gmap.tiles[y][x] = TILE_DOOR


def _add_environment_features(gmap: GameMap, rooms: list[Room],
                              rng: random.Random) -> None:
    """Add water and lava patches to some rooms."""
    if len(rooms) < 3:
        return

    # Possibly add water to one room (avoid first and last rooms)
    if rng.random() < 0.3:
        room = rng.choice(rooms[1:-1]) if len(rooms) > 2 else rooms[0]
        _add_pool(gmap, room, TILE_WATER, rng)

    # Possibly add lava to another room (higher levels)
    if gmap.level > 5 and rng.random() < 0.2:
        room = rng.choice(rooms[1:-1]) if len(rooms) > 2 else rooms[0]
        _add_pool(gmap, room, TILE_LAVA, rng)


def _add_pool(gmap: GameMap, room: Room, tile: str,
              rng: random.Random) -> None:
    """Add a small pool of water/lava in a room."""
    center = room.center
    radius = min(room.width, room.height) // 4
    if radius < 1:
        radius = 1

    # Collect positions that must not be overwritten
    protected = set()
    for pos in (gmap.slipgate_down_pos, gmap.slipgate_up_pos,
                gmap.entrance_pos):
        if pos is not None:
            protected.add((pos.y, pos.x))

    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if abs(dy) + abs(dx) <= radius:
                ny, nx = center.y + dy, center.x + dx
                if (ny, nx) in protected:
                    continue
                # Only replace floor tiles, and not the exact center
                if (gmap.get_tile(ny, nx) == TILE_FLOOR and
                        (ny != center.y or nx != center.x)):
                    gmap.set_tile(ny, nx, tile)


def _place_items(gmap: GameMap, level: int, rooms: list[Room],
                 rng: random.Random) -> None:
    """Place items throughout the map based on level."""
    num_items = rng.randint(2, 5) + level // 5

    weapon_pool = [w for w in ALL_WEAPONS if w != AXE]
    ammo_pool = ALL_AMMO
    armor_pool = ALL_ARMOR
    powerup_pool = ALL_POWERUPS
    # Weighted health pool: SMALL/MEDIUM at 44% each, MEGAHEALTH at 12%
    health_weights = [44, 44, 12]

    for _ in range(num_items):
        room = rng.choice(rooms[1:] if len(rooms) > 1 else rooms)
        pos = _random_floor_in_room(gmap, room, rng)
        if pos is None:
            continue

        roll = rng.random()
        if roll < 0.15 and level > 2:
            item_def = rng.choice(weapon_pool)
        elif roll < 0.40:
            item_def = rng.choice(ammo_pool)
        elif roll < 0.60:
            item_def = rng.choices(
                [SMALL_HEALTH, MEDIUM_HEALTH, MEGAHEALTH],
                weights=health_weights,
                k=1,
            )[0]
        elif roll < 0.82 and level > 3:
            item_def = rng.choice(armor_pool)
        elif roll < 0.87 and level > 15:
            item_def = rng.choice(powerup_pool)
        else:
            # Fallback: only non-mega health or ammo
            item_def = rng.choice(ammo_pool + [SMALL_HEALTH, MEDIUM_HEALTH])

        gmap.add_item_at(pos.y, pos.x, create_item(item_def))


def _place_enemies(gmap: GameMap, level: int, rooms: list[Room],
                   rng: random.Random) -> None:
    """Place enemies on the map based on level."""
    available = [e for e in ALL_ENEMIES if e.min_map_level <= level + 1]
    if not available:
        return

    num_enemies = rng.randint(2, 4) + level // 3

    for _ in range(num_enemies):
        room = rng.choice(rooms[1:] if len(rooms) > 1 else rooms)
        pos = _random_floor_in_room(gmap, room, rng)
        if pos is None:
            continue

        if gmap.get_enemy_at(pos.y, pos.x) is not None:
            continue

        weights = []
        for e in available:
            w = max(1, 10 - (e.min_map_level - level) if e.min_map_level <= level + 1 else 1)
            weights.append(w)

        enemy_def = rng.choices(available, weights=weights, k=1)[0]
        enemy = Enemy.from_def(enemy_def, pos)
        gmap.enemies.append(enemy)


def _random_floor_in_room(gmap: GameMap, room: Room,
                          rng: random.Random) -> Optional[Position]:
    """Get a random walkable floor position in a room."""
    candidates = []
    for y in range(room.y + 1, room.y2 - 1):
        for x in range(room.x + 1, room.x2 - 1):
            if gmap.tiles[y][x] == TILE_FLOOR:
                candidates.append(Position(y, x))
    if candidates:
        return rng.choice(candidates)
    return None
