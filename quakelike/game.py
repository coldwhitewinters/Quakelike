"""Main game state and logic for Quakelike."""

from __future__ import annotations
import json
import os
import random
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from quakelike.constants import (
    DIRECTIONS, NUM_MAPS,
    TILE_SLIPGATE_DOWN, TILE_SLIPGATE_UP, TILE_ENTRANCE,
    TILE_LAVA, TILE_WATER,
    KEY_INVENTORY, KEY_PICK_DROP, KEY_USE, KEY_TARGET, KEY_FIRE,
    KEY_SWAP_WEAPON, KEY_MESSAGE_LOG, KEY_SAVE, KEY_QUIT,
    KEY_SLIPGATE_DOWN, KEY_SLIPGATE_UP,
    KEY_NAV_UP, KEY_NAV_DOWN, KEY_NAV_LEFT, KEY_NAV_RIGHT,
    MAX_VISIBLE_MESSAGES,
    COLOR_WALL, COLOR_FLOOR, COLOR_DOOR, COLOR_SLIPGATE,
    COLOR_ENTRANCE, COLOR_WATER, COLOR_LAVA,
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


class GameState(Enum):
    PLAYING = auto()
    INVENTORY = auto()
    LOOT = auto()
    MESSAGE_LOG = auto()
    GAME_OVER = auto()
    VICTORY = auto()
    TARGETING = auto()


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

    quit: bool = False

    # UI state
    inventory_cursor: int = 0
    loot_cursor: int = 0
    active_panel: str = 'loot'  # 'loot' or 'inventory'
    message_log_scroll: int = 0
    target_list: list[Enemy] = field(default_factory=list)
    target_cursor: int = -1

    @property
    def current_map(self) -> GameMap:
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
            return self._get_render_state()
        if self.state == GameState.VICTORY:
            return self._get_render_state()

        if self.state == GameState.INVENTORY or self.state == GameState.LOOT:
            return self._handle_inventory_input(key)
        elif self.state == GameState.MESSAGE_LOG:
            return self._handle_message_log_input(key)
        elif self.state == GameState.TARGETING:
            return self._handle_targeting_input(key)
        else:
            return self._handle_playing_input(key)

    def _handle_playing_input(self, key: str) -> dict:
        """Handle input during normal play."""
        if key in DIRECTIONS:
            self._move_player(key)
        elif key == KEY_SLIPGATE_DOWN:
            self._use_slipgate_down()
        elif key == KEY_SLIPGATE_UP:
            self._use_slipgate_up()
        elif key == KEY_INVENTORY:
            self._open_inventory()
        elif key == KEY_PICK_DROP:
            self._quick_pick_drop()
        elif key == KEY_TARGET:
            self._start_targeting()
        elif key == KEY_FIRE:
            self._fire_weapon()
        elif key == KEY_SWAP_WEAPON:
            self._swap_weapon()
        elif key == KEY_MESSAGE_LOG:
            self.state = GameState.MESSAGE_LOG
            self.message_log_scroll = 0
        elif key == KEY_SAVE:
            self._save_game()
        elif key == KEY_QUIT:
            self.state = GameState.GAME_OVER
            self.quit = True
            self.message_log.add('You quit the game.')

        return self._get_render_state()

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
        """Open inventory panel."""
        self.state = GameState.INVENTORY
        self.inventory_cursor = 0
        self.active_panel = 'inventory'

    def _quick_pick_drop(self) -> None:
        """Quick pick/drop - open loot+inventory if items on ground."""
        items = self.current_map.get_items_at(
            self.player.pos.y, self.player.pos.x)
        if items:
            self.state = GameState.LOOT
            self.loot_cursor = 0
            self.inventory_cursor = 0
            self.active_panel = 'loot'
        else:
            # Open inventory for dropping
            self.state = GameState.INVENTORY
            self.inventory_cursor = 0
            self.active_panel = 'inventory'

    def _handle_inventory_input(self, key: str) -> dict:
        """Handle input while in inventory/loot mode."""
        gmap = self.current_map
        ground_items = gmap.get_items_at(self.player.pos.y, self.player.pos.x)
        has_loot = len(ground_items) > 0

        if key == KEY_INVENTORY or key == 'Escape':
            self.state = GameState.PLAYING
        elif key == KEY_NAV_UP:
            if self.active_panel == 'loot':
                self.loot_cursor = max(0, self.loot_cursor - 1)
            else:
                self.inventory_cursor = max(0, self.inventory_cursor - 1)
        elif key == KEY_NAV_DOWN:
            if self.active_panel == 'loot':
                self.loot_cursor = min(len(ground_items) - 1,
                                       self.loot_cursor + 1)
            else:
                self.inventory_cursor = min(
                    self.player.inventory.count - 1,
                    self.inventory_cursor + 1)
        elif key == KEY_NAV_LEFT:
            if has_loot:
                self.active_panel = 'loot'
        elif key == KEY_NAV_RIGHT:
            self.active_panel = 'inventory'
        elif key == KEY_PICK_DROP:
            self._pick_drop_item(ground_items)
        elif key == KEY_USE or key == 'Enter':
            self._use_selected_item()

        return self._get_render_state()

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

        return self._get_render_state()

    def _start_targeting(self) -> None:
        """Start targeting mode."""
        self.target_list = get_enemies_in_los(self.player, self.current_map)
        if not self.target_list:
            self.message_log.add('No enemies in sight.')
            return
        self.state = GameState.TARGETING
        self.target_cursor = 0
        enemy = self.target_list[0]
        self.message_log.add(
            f'Targeting: {enemy.name} (HP: {enemy.health}/{enemy.max_health})')

    def _handle_targeting_input(self, key: str) -> dict:
        """Handle input during targeting."""
        if key == 'Escape':
            self.state = GameState.PLAYING
            self.player.target_index = -1
        elif key == KEY_TARGET:
            # Cycle through targets
            if self.target_list:
                self.target_cursor = (self.target_cursor + 1) % len(self.target_list)
                enemy = self.target_list[self.target_cursor]
                self.message_log.add(
                    f'Targeting: {enemy.name} '
                    f'(HP: {enemy.health}/{enemy.max_health})')
                self.player.target_index = self.target_cursor
        elif key == KEY_FIRE:
            self._fire_at_target()
            self.state = GameState.PLAYING

        return self._get_render_state()

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
            msgs = update_enemy(enemy, self.player, gmap, self.rng)
            for m in msgs:
                self.message_log.add(m)

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

    def _save_game(self) -> None:
        """Save game state to file."""
        save_data = self._serialize()
        os.makedirs('saves', exist_ok=True)
        with open('saves/savegame.json', 'w') as f:
            json.dump(save_data, f)
        self.message_log.add('Game saved.')

    def _delete_save(self) -> None:
        """Delete save file for permadeath."""
        try:
            os.remove('saves/savegame.json')
        except FileNotFoundError:
            pass

    def load_game(self) -> bool:
        """Load game from file. Returns True on success."""
        try:
            with open('saves/savegame.json', 'r') as f:
                data = json.load(f)
            self._deserialize(data)
            self.message_log.add('Game loaded.')
            return True
        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            return False

    def _serialize(self) -> dict:
        """Serialize game state to dict."""
        maps_data = {}
        for idx, gmap in self.maps.items():
            maps_data[str(idx)] = self._serialize_map(gmap)

        return {
            'seed': self.seed,
            'turn': self.turn,
            'current_map_idx': self.current_map_idx,
            'player': self._serialize_player(),
            'maps': maps_data,
            'messages': self.message_log.to_dict(),
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
        self.seed = data['seed']
        self.rng = random.Random(self.seed)
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

    def _get_render_state(self) -> dict:
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
                    color = _tile_color(tile)
                    row.append({'char': tile, 'color': color})
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
            if (enemy.pos.y, enemy.pos.x) in gmap.explored:
                color = enemy.color
                if enemy is targeted_enemy:
                    color = '#FF0000'  # Highlighted target
                visible_tiles[enemy.pos.y][enemy.pos.x] = {
                    'char': enemy.char,
                    'color': color,
                }

        # Place player
        visible_tiles[p.pos.y][p.pos.x] = {
            'char': p.char,
            'color': p.color,
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

        return {
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
            'show_inventory': self.state in (GameState.INVENTORY,
                                              GameState.LOOT),
            'show_loot': self.state == GameState.LOOT,
            'show_message_log': self.state == GameState.MESSAGE_LOG,
            'message_log_scroll': self.message_log_scroll,
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
