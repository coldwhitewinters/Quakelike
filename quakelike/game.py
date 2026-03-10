"""Main game state and logic for Quakelike."""

from __future__ import annotations
import json
import os
import random
import re
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from quakelike.constants import (
    DIRECTIONS, NUM_MAPS,
    TILE_SLIPGATE_DOWN, TILE_SLIPGATE_UP, TILE_ENTRANCE,
    TILE_LAVA, TILE_WATER, TILE_WALL, TILE_FLOOR, TILE_DOOR,
    KEY_INVENTORY, KEY_TRANSFER, KEY_EXAMINE, KEY_USE,
    KEY_TARGET, KEY_TARGET_PREV, KEY_TARGET_CLEAR, KEY_FIRE,
    KEY_SWAP_WEAPON, KEY_MESSAGE_LOG, KEY_HELP, KEY_SAVE, KEY_QUIT,
    KEY_SLIPGATE_DOWN, KEY_SLIPGATE_UP,
    KEY_NAV_UP, KEY_NAV_DOWN, KEY_NAV_LEFT, KEY_NAV_RIGHT, KEY_FAST_TRAVEL,
    KEY_REST, KEY_PICKUP,
    MAX_VISIBLE_MESSAGES,
    COLOR_WALL, COLOR_FLOOR, COLOR_DOOR, COLOR_SLIPGATE,
    COLOR_ENTRANCE, COLOR_WATER, COLOR_LAVA,
    DOOR_CLOSE_DELAY,
)
from quakelike.entity import Position
from quakelike.player import Player
from quakelike.gamemap import GameMap, generate_map, _find_safe_start
from quakelike.message import MessageLog
from quakelike.items import (
    Item, ItemType, AmmoType, item_from_name, ITEM_BY_NAME, RUNE, create_item,
)
from quakelike.enemies import Enemy, ENEMY_BY_NAME
from quakelike.combat import player_melee_attack, player_fire_weapon
from quakelike.ai import update_enemy, get_enemies_in_los


HELP_CONTENT = [
    '=== QUAKELIKE HELP ===',
    '',
    'MOVEMENT',
    '  h/j/k/l        Move left / down / up / right',
    '  y/u/b/n        Move diagonally',
    '',
    'INVENTORY & ITEMS',
    '  i              Open inventory & floor panel',
    '  ,              Pick up item from floor',
    '  Tab            Transfer item between panels',
    '  Enter          Use / equip selected item',
    '  w              Swap to previous weapon',
    '',
    'COMBAT & TARGETING',
    '  f              Fire equipped weapon at target',
    '  t              Cycle to next target (LOS)',
    '  T              Cycle to previous target (LOS)',
    '  Alt-t          Clear current target',
    '',
    'NAVIGATION',
    '  >              Descend slipgate',
    '  <              Ascend slipgate',
    '',
    'OTHER',
    '  .              Rest / skip turn',
    '  x              Examine tile (move cursor with h/j/k/l)',
    '  _              Fast travel (move cursor, _ to confirm)',
    '  p              View message log',
    '  ?              This help screen',
    '  S              Save game',
    '  Q              Quit game',
    '',
    'HOW TO WIN',
    '  Find the Rune on level 40, then return to level 1.',
    '  Step onto the Entrance (E) tile with the Rune to win.',
    '',
    'Press Escape or ? to close.',
]


SAVES_DIR = 'saves'

# Compiled regex for validating game_id values — must be a canonical UUID
_UUID_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
)


def _validate_game_id(game_id: str) -> bool:
    """Return True if *game_id* is a valid lowercase UUID, False otherwise."""
    return bool(_UUID_RE.match(game_id))


def list_saves(saves_dir: str = SAVES_DIR) -> list:
    """Scan *saves_dir* for save files and return metadata for each.

    Reads every file matching ``game_<uuid>.json`` in *saves_dir*.  Files that
    cannot be parsed, are missing required keys, or whose embedded ``game_id``
    fails UUID validation are silently skipped so that a single corrupt file
    never breaks the save-listing screen.

    Args:
        saves_dir: Path to the directory that holds save files.  Defaults to
            the module-level ``SAVES_DIR`` constant (``"saves"``).  Pass a
            temporary directory in tests to keep isolation clean.

    Returns:
        A list of dicts, one per valid save file, sorted by ``timestamp``
        descending (newest first).  Each dict contains:

        - ``id`` (str): The UUID that uniquely identifies this save.  Pass
          this value to ``Game.load_game(game_id=...)`` to load the save.
        - ``display_name`` (str): Human-readable label shown in the Continue
          Game menu, e.g. ``"Level 3 — Map 7"``.
        - ``timestamp`` (float): Unix timestamp written at save time; used
          for sorting.
        - ``level`` (int): Player experience level at save time.
        - ``map_idx`` (int): Zero-based map index at save time.

        Returns an empty list if *saves_dir* does not exist or contains no
        valid save files.
    """
    results = []
    if not os.path.isdir(saves_dir):
        return results

    for filename in os.listdir(saves_dir):
        if not (filename.startswith('game_') and filename.endswith('.json')):
            continue
        filepath = os.path.join(saves_dir, filename)
        try:
            with open(filepath, 'r') as f:
                data = json.load(f)
            game_id = data['game_id']
            # Skip entries whose game_id is not a valid UUID — this prevents
            # a crafted save file from injecting a traversal path as an ID.
            if not isinstance(game_id, str) or not _validate_game_id(game_id):
                continue
            player_data = data.get('player', {})
            player_level = player_data.get('level', 1)
            map_idx = data.get('current_map_idx', 0)
            timestamp = data.get('timestamp', 0)
            display_name = f"Level {player_level} \u2014 Map {map_idx + 1}"
            results.append({
                'id': game_id,
                'display_name': display_name,
                'timestamp': timestamp,
                'level': player_level,
                'map_idx': map_idx,
            })
        except Exception:
            # Corrupted or incompatible save — skip it
            continue

    results.sort(key=lambda e: e['timestamp'], reverse=True)
    return results


class GameState(Enum):
    PLAYING = auto()
    INVENTORY = auto()
    LOOT = auto()
    MESSAGE_LOG = auto()
    GAME_OVER = auto()
    VICTORY = auto()
    EXAMINE = auto()
    HELP = auto()
    FAST_TRAVEL = auto()


@dataclass
class Game:
    """Main game object holding all state."""
    maps: dict[int, GameMap] = field(default_factory=dict)
    player: Optional[Player] = None
    current_map_idx: int = 0
    message_log: MessageLog = field(default_factory=MessageLog)
    state: GameState = GameState.PLAYING
    rng: random.Random = field(default_factory=lambda: random.Random())
    seed: int = 0
    turn: int = 0
    game_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    quit: bool = False

    # Autopath travel state
    travel_path: list = field(default_factory=list)
    _travel_frames: list = field(default_factory=list)

    # UI state
    inventory_cursor: int = 0
    loot_cursor: int = 0
    active_panel: str = 'loot'  # 'loot' or 'inventory'
    message_log_scroll: int = 0
    target_list: list[Enemy] = field(default_factory=list)
    target_cursor: int = -1
    examine_cursor: tuple[int, int] = field(default_factory=lambda: (0, 0))
    fast_travel_cursor: tuple[int, int] = field(default_factory=lambda: (0, 0))
    previous_state: Optional[GameState] = None

    @property
    def current_map(self) -> GameMap:
        """Get the currently active game map."""
        return self.maps[self.current_map_idx]

    def new_game(self, seed: Optional[int] = None) -> None:
        """Start a new game."""
        if seed is None:
            seed = random.randint(0, 2**31)
        self.seed = seed
        self.rng = random.Random(seed)
        self.maps = {}
        self.turn = 0
        self.state = GameState.PLAYING
        self.quit = False
        self.travel_path = []
        self._travel_frames = []

        # Generate first map
        first_map = generate_map(0, self.rng)
        self.maps[0] = first_map
        self.current_map_idx = 0

        # Create player
        self.player = Player.create(first_map.player_start.copy())

        self.message_log = MessageLog()
        self.message_log.add('Welcome to Quakelike! Find the Rune and return to the entrance.')
        self.message_log.add('You grip your axe tightly...')

        # Reveal area around player
        first_map.reveal_around(self.player.pos.y, self.player.pos.x)

    def handle_input(self, key: str) -> dict:
        """Handle a key input. Returns game state for rendering."""
        if self.state == GameState.GAME_OVER:
            if key == KEY_HELP:
                self.previous_state = GameState.GAME_OVER
                self.state = GameState.HELP
            return self.get_render_state()
        if self.state == GameState.VICTORY:
            return self.get_render_state()

        if self.state == GameState.INVENTORY or self.state == GameState.LOOT:
            return self._handle_inventory_input(key)
        elif self.state == GameState.MESSAGE_LOG:
            return self._handle_message_log_input(key)
        elif self.state == GameState.EXAMINE:
            return self._handle_examine_input(key)
        elif self.state == GameState.FAST_TRAVEL:
            return self._handle_fast_travel_input(key)
        elif self.state == GameState.HELP:
            return self._handle_help_input(key)
        else:
            return self._handle_playing_input(key)

    def _handle_playing_input(self, key: str) -> dict:
        """Handle input during normal play."""
        self._travel_frames = []  # clear stale animation data from previous travel
        if key in DIRECTIONS:
            self._move_player(key)
        elif key == KEY_SLIPGATE_DOWN:
            self._use_slipgate_down()
        elif key == KEY_SLIPGATE_UP:
            self._use_slipgate_up()
        elif key == KEY_INVENTORY:
            self._open_inventory()
        elif key == KEY_EXAMINE:
            self._enter_examine()
        elif key == KEY_FAST_TRAVEL:
            self._enter_fast_travel()
        elif key == KEY_TARGET:
            self._cycle_target_forward()
        elif key == KEY_TARGET_PREV:
            self._cycle_target_backward()
        elif key == KEY_TARGET_CLEAR:
            self._clear_target()
        elif key == KEY_FIRE:
            self._fire_weapon()
        elif key == KEY_SWAP_WEAPON:
            self._swap_weapon()
        elif key == KEY_MESSAGE_LOG:
            self.state = GameState.MESSAGE_LOG
            self.message_log_scroll = 0
        elif key == KEY_HELP:
            self.previous_state = GameState.PLAYING
            self.state = GameState.HELP
        elif key == KEY_SAVE:
            self._save_game()
            state = self.get_render_state()
            state['goto_menu'] = True
            return state
        elif key == KEY_QUIT:
            # Legacy: Q sets GAME_OVER for backward compatibility.
            # The new frontend uses quit_without_save() with a confirmation dialog.
            self.state = GameState.GAME_OVER
            self.quit = True
            self.message_log.add('You quit the game.')
        elif key == KEY_REST:
            self.message_log.add('You rest.')
            self._end_turn()
        elif key == KEY_PICKUP:
            self._pickup_floor_item()

        return self.get_render_state()

    def _move_player(self, key: str) -> None:
        """Move player in a direction."""
        dy, dx = DIRECTIONS[key]
        new_y = self.player.pos.y + dy
        new_x = self.player.pos.x + dx
        gmap = self.current_map

        # Check for enemy at destination (melee attack)
        enemy = gmap.get_enemy_at(new_y, new_x)
        if enemy is not None:
            damage, msg = player_melee_attack(self.player, enemy, self.rng)
            self.message_log.add(msg)
            if not enemy.is_alive:
                xp, leveled = self.player.gain_xp(enemy.xp_value)
                self.message_log.add(f'You gained {enemy.xp_value} XP.')
                if leveled:
                    self.message_log.add(
                        f'Level up! You are now level {self.player.level}.')
            self._end_turn()
            return

        # Auto-open closed door
        tile = gmap.get_tile(new_y, new_x)
        if tile == TILE_DOOR and not gmap.is_open_door(new_y, new_x):
            gmap.open_door(new_y, new_x, self.turn + 1 + DOOR_CLOSE_DELAY)
            self.message_log.add('The door opens.')
            # Fall through: door is now open, is_walkable will return True

        # Check walkability
        if not gmap.is_walkable(new_y, new_x):
            return

        # Move player
        self.player.pos.y = new_y
        self.player.pos.x = new_x

        # Check environmental damage
        tile = gmap.get_tile(new_y, new_x)
        if tile == TILE_LAVA and self.player.biosuit_turns <= 0:
            dmg = self.player.take_damage(10)
            self.message_log.add(f'The lava burns you for {dmg} damage!')
        elif tile == TILE_WATER and self.player.biosuit_turns <= 0:
            # Water doesn't damage but shows message
            pass

        # Check for items
        items = gmap.get_items_at(new_y, new_x)
        if items:
            names = ', '.join(i.name for i in items)
            self.message_log.add(f'You see: {names}')

        # Reveal FOV
        gmap.reveal_around(new_y, new_x)

        # Check victory condition
        if (tile == TILE_ENTRANCE and self.player.has_rune() and
                self.current_map_idx == 0):
            self.state = GameState.VICTORY
            self.message_log.add('You return with the Rune! VICTORY!')
            return

        self._end_turn()

    def _use_slipgate_down(self) -> None:
        """Use slipgate to go to the next map."""
        tile = self.current_map.get_tile(self.player.pos.y, self.player.pos.x)
        if tile != TILE_SLIPGATE_DOWN:
            self.message_log.add('No slipgate here.')
            return

        next_idx = self.current_map_idx + 1
        if next_idx >= NUM_MAPS:
            self.message_log.add('This slipgate leads nowhere.')
            return

        # Generate map if needed
        if next_idx not in self.maps:
            self.maps[next_idx] = generate_map(next_idx, self.rng)

        self.current_map_idx = next_idx
        self.player.current_map = next_idx
        new_map = self.current_map

        # Place player at a safe position near the slipgate up
        if new_map.slipgate_up_pos:
            self.player.pos = _find_safe_start(new_map, new_map.slipgate_up_pos)
        elif new_map.player_start:
            self.player.pos = new_map.player_start.copy()

        new_map.reveal_around(self.player.pos.y, self.player.pos.x)
        self.message_log.add(f'You enter level {next_idx + 1}.')
        self._end_turn()

    def _use_slipgate_up(self) -> None:
        """Use slipgate to go to the previous map."""
        tile = self.current_map.get_tile(self.player.pos.y, self.player.pos.x)
        if tile not in (TILE_SLIPGATE_UP, TILE_ENTRANCE):
            self.message_log.add('No slipgate here.')
            return

        if self.current_map_idx == 0:
            if self.player.has_rune():
                self.state = GameState.VICTORY
                self.message_log.add('You return with the Rune! VICTORY!')
            else:
                self.message_log.add('You need the Rune before you can leave.')
            return

        prev_idx = self.current_map_idx - 1
        self.current_map_idx = prev_idx
        self.player.current_map = prev_idx
        prev_map = self.maps[prev_idx]

        # Place player at a safe position near the slipgate down
        if prev_map.slipgate_down_pos:
            self.player.pos = _find_safe_start(prev_map, prev_map.slipgate_down_pos)
        elif prev_map.player_start:
            self.player.pos = prev_map.player_start.copy()

        prev_map.reveal_around(self.player.pos.y, self.player.pos.x)
        self.message_log.add(f'You return to level {prev_idx + 1}.')
        self._end_turn()

    def _open_inventory(self) -> None:
        """Open inventory and loot panels simultaneously."""
        self.state = GameState.INVENTORY
        self.inventory_cursor = 0
        self.loot_cursor = 0
        ground_items = self.current_map.get_items_at(self.player.pos.y, self.player.pos.x)
        self.active_panel = 'loot' if ground_items else 'inventory'

    def _pickup_floor_item(self) -> None:
        """Pick up the first item on the floor at the player's position."""
        py, px = self.player.pos.y, self.player.pos.x
        floor_items = self.current_map.get_items_at(py, px)
        if not floor_items:
            self.message_log.add('Nothing to pick up.')
            return
        item = floor_items[0]
        if self.player.inventory.can_add(item):
            self.current_map.remove_item_at(py, px, 0)
            self.player.inventory.add_item(item)
            self.message_log.add(f'Picked up {item.name}.')
            self._end_turn()
        else:
            self.message_log.add('Inventory is full.')

    def _handle_inventory_input(self, key: str) -> dict:
        """Handle input while in inventory/loot mode."""
        gmap = self.current_map
        ground_items = gmap.get_items_at(self.player.pos.y, self.player.pos.x)

        if key == KEY_INVENTORY or key == 'Escape':
            self.state = GameState.PLAYING
        elif key == KEY_NAV_UP or key == 'k':
            if self.active_panel == 'loot':
                self.loot_cursor = max(0, self.loot_cursor - 1)
            else:
                self.inventory_cursor = max(0, self.inventory_cursor - 1)
        elif key == KEY_NAV_DOWN or key == 'j':
            if self.active_panel == 'loot':
                if ground_items:
                    self.loot_cursor = min(len(ground_items) - 1,
                                           self.loot_cursor + 1)
            else:
                self.inventory_cursor = min(
                    self.player.inventory.count - 1,
                    self.inventory_cursor + 1)
        elif key == KEY_NAV_LEFT or key == 'h':
            self.active_panel = 'loot'
        elif key == KEY_NAV_RIGHT or key == 'l':
            self.active_panel = 'inventory'
        elif key == KEY_TRANSFER:
            self._pick_drop_item(ground_items)
        elif key == KEY_USE or key == 'Enter':
            self._use_selected_item()

        return self.get_render_state()

    def _pick_drop_item(self, ground_items: list[Item]) -> None:
        """Move item between inventory and ground."""
        if self.active_panel == 'loot' and ground_items:
            # Pick up from ground
            if 0 <= self.loot_cursor < len(ground_items):
                item = ground_items[self.loot_cursor]
                if self.player.inventory.can_add(item):
                    removed = self.current_map.remove_item_at(
                        self.player.pos.y, self.player.pos.x,
                        self.loot_cursor)
                    if removed:
                        self.player.inventory.add_item(removed)
                        self.message_log.add(f'Picked up {removed.name}.')
                        # Adjust cursor
                        new_items = self.current_map.get_items_at(
                            self.player.pos.y, self.player.pos.x)
                        if self.loot_cursor >= len(new_items):
                            self.loot_cursor = max(0, len(new_items) - 1)
                else:
                    self.message_log.add('Inventory is full.')
        elif self.active_panel == 'inventory':
            # Drop from inventory
            if 0 <= self.inventory_cursor < self.player.inventory.count:
                item = self.player.inventory.remove_item(self.inventory_cursor)
                if item:
                    # Unequip if dropping equipped weapon
                    if item is self.player.equipped_weapon:
                        self.player.equipped_weapon = None
                    if item is self.player.previous_weapon:
                        self.player.previous_weapon = None
                    self.current_map.add_item_at(
                        self.player.pos.y, self.player.pos.x, item)
                    self.message_log.add(f'Dropped {item.name}.')
                    if self.inventory_cursor >= self.player.inventory.count:
                        self.inventory_cursor = max(
                            0, self.player.inventory.count - 1)

    def _use_selected_item(self) -> None:
        """Use/activate the selected item in inventory."""
        if self.active_panel != 'inventory':
            return
        item = self.player.inventory.get_item(self.inventory_cursor)
        if item is None:
            return
        success, msg = self.player.activate_item(item)
        self.message_log.add(msg)
        if success:
            # Adjust cursor after consumption
            if self.inventory_cursor >= self.player.inventory.count:
                self.inventory_cursor = max(
                    0, self.player.inventory.count - 1)

    def _handle_message_log_input(self, key: str) -> dict:
        """Handle input while viewing message log."""
        if key in (KEY_MESSAGE_LOG, 'Escape', KEY_INVENTORY):
            self.state = GameState.PLAYING
        elif key == KEY_NAV_UP:
            self.message_log_scroll = max(0, self.message_log_scroll - 1)
        elif key == KEY_NAV_DOWN:
            self.message_log_scroll += 1

        return self.get_render_state()

    def _cycle_target_forward(self) -> None:
        """Cycle to the next enemy in LOS (forward)."""
        self.target_list = get_enemies_in_los(self.player, self.current_map)
        if not self.target_list:
            self.message_log.add('No enemies in sight.')
            self.player.target_index = -1
            self.target_cursor = -1
            return
        if self.target_cursor < 0 or self.target_cursor >= len(self.target_list):
            self.target_cursor = 0
        else:
            self.target_cursor = (self.target_cursor + 1) % len(self.target_list)
        self.player.target_index = self.target_cursor
        enemy = self.target_list[self.target_cursor]
        self.message_log.add(
            f'Targeting: {enemy.name} (HP: {enemy.health}/{enemy.max_health})')

    def _cycle_target_backward(self) -> None:
        """Cycle to the previous enemy in LOS (backward)."""
        self.target_list = get_enemies_in_los(self.player, self.current_map)
        if not self.target_list:
            self.message_log.add('No enemies in sight.')
            self.player.target_index = -1
            self.target_cursor = -1
            return
        if self.target_cursor < 0 or self.target_cursor >= len(self.target_list):
            self.target_cursor = len(self.target_list) - 1
        else:
            self.target_cursor = (self.target_cursor - 1) % len(self.target_list)
        self.player.target_index = self.target_cursor
        enemy = self.target_list[self.target_cursor]
        self.message_log.add(
            f'Targeting: {enemy.name} (HP: {enemy.health}/{enemy.max_health})')

    def _clear_target(self) -> None:
        """Clear the current target."""
        self.player.target_index = -1
        self.target_cursor = -1
        self.message_log.add('Target cleared.')

    def _enter_examine(self) -> None:
        """Enter examine mode with cursor at player position."""
        self.examine_cursor = (self.player.pos.y, self.player.pos.x)
        self.state = GameState.EXAMINE

    def _handle_examine_input(self, key: str) -> dict:
        """Handle input while in examine mode."""
        if key == 'Escape' or key == KEY_EXAMINE:
            self.state = GameState.PLAYING
        elif key in DIRECTIONS:
            dy, dx = DIRECTIONS[key]
            cy, cx = self.examine_cursor
            ny = max(0, min(self.current_map.height - 1, cy + dy))
            nx = max(0, min(self.current_map.width - 1, cx + dx))
            self.examine_cursor = (ny, nx)

        return self.get_render_state()

    def _enter_fast_travel(self) -> None:
        """Enter fast travel cursor mode."""
        self.fast_travel_cursor = (self.player.pos.y, self.player.pos.x)
        self.state = GameState.FAST_TRAVEL

    def _handle_fast_travel_input(self, key: str) -> dict:
        """Handle input while in fast travel cursor mode."""
        if key == 'Escape':
            self.state = GameState.PLAYING
        elif key == KEY_FAST_TRAVEL:
            self._confirm_fast_travel()
        elif key in DIRECTIONS:
            dy, dx = DIRECTIONS[key]
            cy, cx = self.fast_travel_cursor
            ny = max(0, min(self.current_map.height - 1, cy + dy))
            nx = max(0, min(self.current_map.width - 1, cx + dx))
            self.fast_travel_cursor = (ny, nx)
        elif key == KEY_USE:
            self._confirm_fast_travel()
        return self.get_render_state()

    def _bfs_path(self, start: tuple, end: tuple) -> list:
        """Compute a BFS path from start to end through explored, passable tiles.

        Closed door tiles (TILE_DOOR) are treated as passable for path-planning
        purposes; _confirm_fast_travel opens them when the player steps through.

        Returns a list of (y, x) positions from start (exclusive) to end
        (inclusive).  Returns an empty list if no path found or start == end.
        Only 4-connected neighbors are considered (up, down, left, right).
        """
        if start == end:
            return []

        gmap = self.current_map
        queue = deque()
        queue.append(start)
        came_from = {start: None}

        neighbors = [(-1, 0), (1, 0), (0, -1), (0, 1)]

        while queue:
            current = queue.popleft()
            if current == end:
                break
            cy, cx = current
            for dy, dx in neighbors:
                ny, nx = cy + dy, cx + dx
                neighbor = (ny, nx)
                if neighbor in came_from:
                    continue
                # Treat closed doors as passable for path planning;
                # _confirm_fast_travel will open them during execution.
                if not gmap.is_walkable(ny, nx) and gmap.get_tile(ny, nx) != TILE_DOOR:
                    continue
                if neighbor not in gmap.explored:
                    continue
                came_from[neighbor] = current
                queue.append(neighbor)

        if end not in came_from:
            return []

        # Reconstruct path from end back to start (excluding start)
        path = []
        node = end
        while node != start:
            path.append(node)
            node = came_from[node]
        path.reverse()
        return path

    def _confirm_fast_travel(self) -> None:
        """Execute all travel steps to the fast travel cursor position in one call.

        Closed door tiles are valid destinations and are auto-opened when the
        path passes through them; "The door opens." is logged for each one.
        Travel halts early if a living enemy blocks a step or enters the player's
        target list mid-path.
        """
        cy, cx = self.fast_travel_cursor
        gmap = self.current_map

        if (cy, cx) not in gmap.explored:
            self.message_log.add('You cannot travel to unexplored areas.')
            return
        if not gmap.is_walkable(cy, cx) and gmap.get_tile(cy, cx) != TILE_DOOR:
            self.message_log.add('You cannot travel there.')
            return
        enemy = gmap.get_enemy_at(cy, cx)
        if enemy is not None and enemy.is_alive:
            self.message_log.add('An enemy blocks the way.')
            return

        start = (self.player.pos.y, self.player.pos.x)
        end = (cy, cx)

        if start == end:
            # Zero steps: just end turn
            self.state = GameState.PLAYING
            self.travel_path = []
            self._travel_frames = []
            self._end_turn()
            return

        path = self._bfs_path(start, end)
        if not path:
            self.message_log.add('No path to destination.')
            return  # stay in FAST_TRAVEL

        # Execute ALL steps, collecting intermediate positions
        self.state = GameState.PLAYING
        frames = []
        for step in path:
            ey, ex = step
            enemy = gmap.get_enemy_at(ey, ex)
            if enemy is not None and enemy.is_alive:
                self.message_log.add('An enemy blocks the path.')
                break
            # Auto-open closed doors encountered on the path
            tile = gmap.get_tile(ey, ex)
            if tile == TILE_DOOR and not gmap.is_open_door(ey, ex):
                gmap.open_door(ey, ex, self.turn + DOOR_CLOSE_DELAY)
                self.message_log.add('The door opens.')
            # Move player
            self.player.pos.y = ey
            self.player.pos.x = ex
            frames.append([ey, ex])
            # Environmental effects
            if tile == TILE_LAVA and self.player.biosuit_turns <= 0:
                dmg = self.player.take_damage(10)
                self.message_log.add(f'The lava burns you for {dmg} damage!')
            # Reveal FOV
            gmap.reveal_around(ey, ex)
            # Victory check
            if (tile == TILE_ENTRANCE and self.player.has_rune() and
                    self.current_map_idx == 0):
                self.state = GameState.VICTORY
                self.message_log.add('You return with the Rune! VICTORY!')
                self._travel_frames = frames
                return
            # End turn for this step
            self._end_turn()
            if self.state == GameState.GAME_OVER:
                self._travel_frames = frames
                return
            if self.target_list:
                self.message_log.add('An enemy is nearby!')
                break
        self._travel_frames = frames

    def _get_examine_info(self) -> str:
        """Get a description of the tile at the examine cursor."""
        cy, cx = self.examine_cursor
        gmap = self.current_map

        if (cy, cx) not in gmap.explored:
            return 'Unexplored area.'

        tile = gmap.get_tile(cy, cx)
        tile_names = {
            TILE_WALL: 'Wall',
            TILE_FLOOR: 'Floor',
            TILE_DOOR: 'Door',
            TILE_WATER: 'Water',
            TILE_LAVA: 'Lava',
            TILE_SLIPGATE_DOWN: 'Slipgate (down)',
            TILE_SLIPGATE_UP: 'Slipgate (up)',
            TILE_ENTRANCE: 'Entrance',
        }
        tile_desc = tile_names.get(tile, 'Unknown')

        parts = [tile_desc]

        # Check for enemy
        enemy = gmap.get_enemy_at(cy, cx)
        if enemy is not None and enemy.is_alive:
            parts.append(
                f'{enemy.name} (HP: {enemy.health}/{enemy.max_health})')

        # Check for items
        items = gmap.get_items_at(cy, cx)
        if items:
            item_names = ', '.join(i.name for i in items)
            parts.append(f'Items: {item_names}')

        return ' | '.join(parts)

    def _handle_help_input(self, key: str) -> dict:
        """Handle input while viewing help."""
        if key == 'Escape' or key == KEY_HELP:
            if self.previous_state is not None:
                self.state = self.previous_state
            else:
                self.state = GameState.PLAYING
            self.previous_state = None

        return self.get_render_state()

    def _fire_weapon(self) -> None:
        """Fire equipped weapon at target or straight ahead."""
        target = None
        if (self.player.target_index >= 0 and
                self.player.target_index < len(self.target_list)):
            target = self.target_list[self.player.target_index]
            if not target.is_alive:
                target = None

        success, msg, extra = player_fire_weapon(
            self.player, target, self.current_map, self.rng)
        self.message_log.add(msg)
        for m in extra:
            self.message_log.add(m)

        if success:
            self._end_turn()

    def _fire_at_target(self) -> None:
        """Fire at the currently targeted enemy."""
        if not self.target_list or self.target_cursor < 0:
            return

        target = self.target_list[self.target_cursor]
        if not target.is_alive:
            self.message_log.add('Target is already dead.')
            return

        success, msg, extra = player_fire_weapon(
            self.player, target, self.current_map, self.rng)
        self.message_log.add(msg)
        for m in extra:
            self.message_log.add(m)

        if success:
            self._end_turn()

    def _swap_weapon(self) -> None:
        """Swap to previously equipped weapon."""
        if self.player.swap_weapon():
            self.message_log.add(
                f'Swapped to {self.player.equipped_weapon.name}.')
        else:
            self.message_log.add('No previous weapon to swap to.')

    def _end_turn(self) -> None:
        """Process end of turn: enemy AI, powerup timers, etc."""
        self.turn += 1
        gmap = self.current_map

        # Enemy turns
        for enemy in gmap.get_living_enemies():
            msgs = update_enemy(enemy, self.player, gmap, self.rng,
                                current_turn=self.turn)
            for m in msgs:
                self.message_log.add(m)

        # Auto-close expired doors
        expired = [pos for pos, close_turn in gmap.open_doors.items()
                   if self.turn >= close_turn]
        for pos in expired:
            y, x = pos
            # Defer close if player is on the tile
            if y == self.player.pos.y and x == self.player.pos.x:
                gmap.open_doors[pos] = self.turn + 1
                continue
            # Defer close if an enemy is on the tile
            if gmap.get_enemy_at(y, x) is not None:
                gmap.open_doors[pos] = self.turn + 1
                continue
            gmap.close_door(y, x)

        # Check player death
        if not self.player.is_alive:
            self.state = GameState.GAME_OVER
            self.message_log.add('You have died. Game over.')
            # Permadeath: delete save file
            self._delete_save()
            return

        # Tick powerups
        powerup_msgs = self.player.tick_powerups()
        for m in powerup_msgs:
            self.message_log.add(m)

        # Update targeting list
        self.target_list = get_enemies_in_los(self.player, self.current_map)
        if (self.player.target_index >= len(self.target_list) or
                self.player.target_index < 0):
            self.player.target_index = -1
            self.target_cursor = -1

    def _save_game(self) -> None:
        """Save game state to per-ID file under SAVES_DIR.

        When SAVES_DIR is the default 'saves' directory, also writes a legacy
        ``saves/savegame.json`` so that old tooling continues to work.
        When SAVES_DIR is patched to a temp dir (e.g. in tests), the legacy
        file is NOT written there, keeping test isolation clean.
        """
        save_data = self._serialize()
        os.makedirs(SAVES_DIR, exist_ok=True)
        save_path = os.path.join(SAVES_DIR, f'game_{self.game_id}.json')
        with open(save_path, 'w') as f:
            json.dump(save_data, f)
        # Legacy path: only write savegame.json when using the default saves dir.
        # When SAVES_DIR has been patched to a temp directory, skip it so that
        # acceptance tests (which assert savegame.json does NOT exist in the
        # temp dir) continue to pass.
        default_saves_abs = os.path.abspath('saves')
        current_saves_abs = os.path.abspath(SAVES_DIR)
        if current_saves_abs == default_saves_abs:
            with open(os.path.join(SAVES_DIR, 'savegame.json'), 'w') as f:
                json.dump(save_data, f)
        self.message_log.add('Game saved.')

    def _delete_save(self) -> None:
        """Delete per-ID save file for permadeath.

        When SAVES_DIR is the default 'saves' directory, also removes the
        legacy ``saves/savegame.json`` file (best-effort; never raises).

        Does nothing if ``self.game_id`` does not pass UUID validation.
        """
        if not _validate_game_id(self.game_id):
            return
        save_path = os.path.join(SAVES_DIR, f'game_{self.game_id}.json')
        try:
            os.remove(save_path)
        except FileNotFoundError:
            pass
        # Legacy: clean up savegame.json only when using the real saves dir
        default_saves_abs = os.path.abspath('saves')
        current_saves_abs = os.path.abspath(SAVES_DIR)
        if current_saves_abs == default_saves_abs:
            try:
                os.remove(os.path.join(SAVES_DIR, 'savegame.json'))
            except FileNotFoundError:
                pass

    def quit_without_save(self) -> dict:
        """Quit the current game without saving, permanently deleting its save file.

        This implements the ``Q`` (Shift+Q) quit-without-saving flow.  The
        frontend is expected to show a confirmation dialog before calling this
        method; once called there is no undo — the save file for this
        ``game_id`` is deleted immediately.

        Internally delegates to ``_delete_save()``, which removes
        ``SAVES_DIR/game_<game_id>.json`` (and the legacy
        ``saves/savegame.json`` when running against the default saves
        directory).  If no save file exists yet, the deletion is a no-op.

        Returns:
            The current render-state dict (as returned by
            ``get_render_state()``) with an additional ``goto_menu`` key set
            to ``True``.  The server inspects this flag and emits a
            ``goto_menu`` socket event so the browser returns to the main menu.
        """
        self._delete_save()
        state = self.get_render_state()
        state['goto_menu'] = True
        return state

    def load_game(self, game_id: Optional[str] = None) -> bool:
        """Load game from file by game_id. Returns True on success.

        If *game_id* is provided, loads from ``SAVES_DIR/game_{game_id}.json``.
        If omitted, falls back to the legacy ``saves/savegame.json`` path for
        backward compatibility with old save files and tests.

        Returns False immediately if *game_id* is provided but fails UUID
        validation, preventing path-traversal attacks.
        """
        if game_id is not None:
            if not _validate_game_id(game_id):
                return False
            save_path = os.path.join(SAVES_DIR, f'game_{game_id}.json')
        else:
            save_path = os.path.join('saves', 'savegame.json')
        try:
            with open(save_path, 'r') as f:
                data = json.load(f)
            self._validate_save_data(data)
            self._deserialize(data)
            if game_id is not None:
                self.game_id = game_id
            self.message_log.add('Game loaded.')
            return True
        except (FileNotFoundError, json.JSONDecodeError, KeyError,
                TypeError, ValueError, IndexError):
            return False

    @staticmethod
    def _validate_save_data(data: dict) -> None:
        """Validate that required fields exist in save data.

        Raises KeyError if required fields are missing.
        Raises TypeError if data is not a dict.
        """
        if not isinstance(data, dict):
            raise TypeError('Save data must be a dict')
        required = ('seed', 'turn', 'current_map_idx', 'player', 'maps')
        for key in required:
            if key not in data:
                raise KeyError(f'Missing required save field: {key}')
        player = data['player']
        if not isinstance(player, dict):
            raise TypeError('Player data must be a dict')
        player_required = ('pos_y', 'pos_x', 'health', 'max_health',
                           'inventory')
        for key in player_required:
            if key not in player:
                raise KeyError(f'Missing required player field: {key}')

    def _serialize(self) -> dict:
        """Serialize game state to dict."""
        maps_data = {}
        for idx, gmap in self.maps.items():
            maps_data[str(idx)] = self._serialize_map(gmap)

        return {
            'game_id': self.game_id,
            'seed': self.seed,
            'rng_state': self.rng.getstate(),
            'turn': self.turn,
            'current_map_idx': self.current_map_idx,
            'player': self._serialize_player(),
            'maps': maps_data,
            'messages': self.message_log.to_dict(),
            'timestamp': time.time(),
        }

    def _serialize_player(self) -> dict:
        p = self.player
        return {
            'pos_y': p.pos.y,
            'pos_x': p.pos.x,
            'health': p.health,
            'max_health': p.max_health,
            'armor': p.armor,
            'armor_absorption': p.armor_absorption,
            'xp': p.xp,
            'level': p.level,
            'current_map': p.current_map,
            'inventory': p.inventory.to_dict(),
            'equipped_weapon': (p.equipped_weapon.name
                                if p.equipped_weapon else None),
            'previous_weapon': (p.previous_weapon.name
                                if p.previous_weapon else None),
            'quad_damage_turns': p.quad_damage_turns,
            'invulnerability_turns': p.invulnerability_turns,
            'invisibility_turns': p.invisibility_turns,
            'biosuit_turns': p.biosuit_turns,
            'megahealth_decay': p.megahealth_decay,
        }

    def _serialize_map(self, gmap: GameMap) -> dict:
        return {
            'level': gmap.level,
            'tiles': [''.join(row) for row in gmap.tiles],
            'explored': list(gmap.explored),
            'enemies': [self._serialize_enemy(e) for e in gmap.enemies],
            'items': {
                f'{k[0]},{k[1]}': [i.to_dict() for i in v]
                for k, v in gmap.items_on_ground.items()
            },
            'slipgate_down': ([gmap.slipgate_down_pos.y, gmap.slipgate_down_pos.x]
                              if gmap.slipgate_down_pos else None),
            'slipgate_up': ([gmap.slipgate_up_pos.y, gmap.slipgate_up_pos.x]
                            if gmap.slipgate_up_pos else None),
            'entrance': ([gmap.entrance_pos.y, gmap.entrance_pos.x]
                         if gmap.entrance_pos else None),
            'open_doors': {f'{k[0]},{k[1]}': v for k, v in gmap.open_doors.items()},
        }

    def _serialize_enemy(self, e: Enemy) -> dict:
        return {
            'name': e.name,
            'pos_y': e.pos.y,
            'pos_x': e.pos.x,
            'health': e.health,
            'is_alive': e.is_alive,
            'alerted': e.alerted,
            'attack_cooldown': e.attack_cooldown,
        }

    def _deserialize(self, data: dict) -> None:
        """Restore game state from dict."""
        # Restore game_id with fallback to current value if missing (old saves)
        self.game_id = data.get('game_id', self.game_id)
        self.seed = data['seed']
        self.rng = random.Random(self.seed)
        if 'rng_state' in data:
            self.rng.setstate(tuple(
                tuple(x) if isinstance(x, list) else x
                for x in data['rng_state']
            ))
        self.turn = data['turn']
        self.current_map_idx = data['current_map_idx']

        # Restore maps
        self.maps = {}
        for idx_str, map_data in data['maps'].items():
            idx = int(idx_str)
            gmap = GameMap(level=map_data['level'])
            gmap.tiles = [list(row) for row in map_data['tiles']]
            gmap.explored = set(tuple(p) for p in map_data['explored'])

            # Restore enemies
            for edata in map_data['enemies']:
                if edata['name'] in ENEMY_BY_NAME:
                    edef = ENEMY_BY_NAME[edata['name']]
                    enemy = Enemy.from_def(edef, Position(edata['pos_y'],
                                                          edata['pos_x']))
                    enemy.health = edata['health']
                    enemy.is_alive = edata['is_alive']
                    enemy.alerted = edata['alerted']
                    enemy.attack_cooldown = edata['attack_cooldown']
                    gmap.enemies.append(enemy)

            # Restore items on ground
            for key_str, items_data in map_data['items'].items():
                y, x = map(int, key_str.split(','))
                for idata in items_data:
                    name = idata['item_name']
                    if name in ITEM_BY_NAME:
                        item = item_from_name(name, idata['quantity'])
                        gmap.add_item_at(y, x, item)
                    elif name == 'Rune':
                        gmap.add_item_at(y, x, create_item(RUNE))

            if map_data['slipgate_down']:
                gmap.slipgate_down_pos = Position(*map_data['slipgate_down'])
            if map_data['slipgate_up']:
                gmap.slipgate_up_pos = Position(*map_data['slipgate_up'])
            if map_data['entrance']:
                gmap.entrance_pos = Position(*map_data['entrance'])

            # Restore open doors
            for key_str, close_turn in map_data.get('open_doors', {}).items():
                y, x = map(int, key_str.split(','))
                gmap.open_doors[(y, x)] = close_turn

            self.maps[idx] = gmap

        # Restore player
        pdata = data['player']
        self.player = Player.create(Position(pdata['pos_y'], pdata['pos_x']))
        self.player.health = pdata['health']
        self.player.max_health = pdata['max_health']
        self.player.armor = pdata['armor']
        self.player.armor_absorption = pdata['armor_absorption']
        self.player.xp = pdata['xp']
        self.player.level = pdata['level']
        self.player.current_map = pdata['current_map']
        self.player.quad_damage_turns = pdata['quad_damage_turns']
        self.player.invulnerability_turns = pdata['invulnerability_turns']
        self.player.invisibility_turns = pdata['invisibility_turns']
        self.player.biosuit_turns = pdata['biosuit_turns']
        self.player.megahealth_decay = pdata.get('megahealth_decay', False)

        # Restore inventory
        self.player.inventory.items.clear()
        for idata in pdata['inventory']:
            name = idata['item_name']
            if name in ITEM_BY_NAME:
                item = item_from_name(name, idata['quantity'])
                self.player.inventory.items.append(item)
            elif name == 'Rune':
                self.player.inventory.items.append(create_item(RUNE))

        # Restore equipped weapon references
        if pdata['equipped_weapon']:
            idx = self.player.inventory.find_by_name(pdata['equipped_weapon'])
            if idx is not None:
                self.player.equipped_weapon = self.player.inventory.items[idx]
        if pdata['previous_weapon']:
            idx = self.player.inventory.find_by_name(pdata['previous_weapon'])
            if idx is not None:
                self.player.previous_weapon = self.player.inventory.items[idx]

        # Restore messages
        self.message_log = MessageLog()
        self.message_log.messages = data.get('messages', [])
        self.state = GameState.PLAYING

    def get_render_state(self) -> dict:
        """Get the current game state for rendering."""
        gmap = self.current_map
        p = self.player

        # Build visible map
        visible_tiles = []
        for y in range(gmap.height):
            row = []
            for x in range(gmap.width):
                if (y, x) in gmap.explored:
                    tile = gmap.tiles[y][x]
                    if tile == TILE_DOOR and gmap.is_open_door(y, x):
                        char = TILE_FLOOR   # show passable opening
                        color = COLOR_DOOR  # keep door-frame color
                    else:
                        char = tile
                        color = _tile_color(tile)
                    row.append({'char': char, 'color': color})
                else:
                    row.append({'char': ' ', 'color': '#000000'})
            visible_tiles.append(row)

        # Place items on map
        for (iy, ix), items in gmap.items_on_ground.items():
            if (iy, ix) in gmap.explored and items:
                visible_tiles[iy][ix] = {
                    'char': items[0].char,
                    'color': items[0].color,
                }

        # Place enemies on map
        targeted_enemy = None
        if (self.target_cursor >= 0 and
                self.target_cursor < len(self.target_list)):
            targeted_enemy = self.target_list[self.target_cursor]

        for enemy in gmap.get_living_enemies():
            if gmap.has_line_of_sight(p.pos, enemy.pos):
                tile = {'char': enemy.char, 'color': enemy.color}
                if enemy is targeted_enemy:
                    tile['targeted'] = True
                visible_tiles[enemy.pos.y][enemy.pos.x] = tile

        # Place player
        visible_tiles[p.pos.y][p.pos.x] = {
            'char': p.char,
            'color': p.color,
        }

        # Place examine cursor (overrides whatever is at that tile)
        if self.state == GameState.EXAMINE:
            cy, cx = self.examine_cursor
            existing = visible_tiles[cy][cx]
            visible_tiles[cy][cx] = {
                'char': existing['char'],
                'color': existing['color'],
                'cursor': True,
            }

        # Place fast travel cursor
        if self.state == GameState.FAST_TRAVEL:
            cy, cx = self.fast_travel_cursor
            existing = visible_tiles[cy][cx]
            visible_tiles[cy][cx] = {
                'char': existing['char'],
                'color': existing['color'],
                'cursor': True,
            }

        # Build status bar data
        weapon_name = p.equipped_weapon.name if p.equipped_weapon else 'None'
        ammo_info = {}
        for at in AmmoType:
            ammo_info[at.name.lower()] = p.inventory.get_ammo_count(at)

        status = {
            'health': p.health,
            'max_health': p.max_health,
            'armor': p.armor,
            'weapon': weapon_name,
            'ammo': ammo_info,
            'level': p.level,
            'xp': p.xp,
            'map_level': self.current_map_idx + 1,
            'turn': self.turn,
        }

        # Powerup indicators
        powerups_active = []
        if p.quad_damage_turns > 0:
            powerups_active.append(f'Quad({p.quad_damage_turns})')
        if p.invulnerability_turns > 0:
            powerups_active.append(f'Pent({p.invulnerability_turns})')
        if p.invisibility_turns > 0:
            powerups_active.append(f'Ring({p.invisibility_turns})')
        if p.biosuit_turns > 0:
            powerups_active.append(f'Bio({p.biosuit_turns})')
        status['powerups'] = powerups_active

        # Messages
        recent_messages = self.message_log.get_recent(MAX_VISIBLE_MESSAGES)

        # Inventory data
        inventory_items = []
        for i, item in enumerate(p.inventory.items):
            entry = {
                'name': item.name,
                'char': item.char,
                'color': item.color,
                'quantity': item.quantity,
                'selected': i == self.inventory_cursor,
                'equipped': item is p.equipped_weapon,
            }
            inventory_items.append(entry)

        # Loot data
        ground_items_data = []
        ground_items = gmap.get_items_at(p.pos.y, p.pos.x)
        for i, item in enumerate(ground_items):
            entry = {
                'name': item.name,
                'char': item.char,
                'color': item.color,
                'quantity': item.quantity,
                'selected': i == self.loot_cursor,
            }
            ground_items_data.append(entry)

        # Full message log (for log view)
        all_messages = self.message_log.get_all()

        # Examine state
        in_inventory_or_loot = self.state in (GameState.INVENTORY,
                                               GameState.LOOT)
        show_examine = self.state == GameState.EXAMINE
        examine_info = self._get_examine_info() if show_examine else ''

        # Help state
        show_help = self.state == GameState.HELP
        help_content = HELP_CONTENT if show_help else []

        return {
            'game_id': self.game_id,
            'state': self.state.name,
            'map': visible_tiles,
            'map_width': gmap.width,
            'map_height': gmap.height,
            'status': status,
            'messages': recent_messages,
            'all_messages': all_messages,
            'inventory': inventory_items,
            'loot': ground_items_data,
            'active_panel': self.active_panel,
            'show_inventory': in_inventory_or_loot,
            'show_loot': in_inventory_or_loot,
            'show_message_log': self.state == GameState.MESSAGE_LOG,
            'message_log_scroll': self.message_log_scroll,
            'show_examine': show_examine,
            'examine_cursor': list(self.examine_cursor),
            'examine_info': examine_info,
            'show_fast_travel': self.state == GameState.FAST_TRAVEL,
            'fast_travel_cursor': list(self.fast_travel_cursor),
            'traveling': False,
            'player_pos': [self.player.pos.y, self.player.pos.x],
            'travel_frames': list(self._travel_frames),
            'show_help': show_help,
            'help_content': help_content,
            'quit': self.quit,
        }


def _tile_color(tile: str) -> str:
    """Get color for a tile character."""
    colors = {
        '#': COLOR_WALL,
        '.': COLOR_FLOOR,
        '+': COLOR_DOOR,
        '>': COLOR_SLIPGATE,
        '<': COLOR_SLIPGATE,
        'E': COLOR_ENTRANCE,
        '~': COLOR_WATER,
        '=': COLOR_LAVA,
    }
    return colors.get(tile, '#FFFFFF')
