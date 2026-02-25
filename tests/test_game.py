"""Tests for the main game module."""

import json
import os
import random
import pytest
from quakelike.game import Game, GameState
from quakelike.entity import Position
from quakelike.items import (
    create_item, ItemDef, ItemType, RUNE,
    AXE, SHOTGUN, SHELLS_SMALL, GREEN_ARMOR, SMALL_HEALTH,
    QUAD_DAMAGE, BIOSUIT,
)
from quakelike.enemies import Enemy, GRUNT, ROTTWEILER
from quakelike.constants import (
    TILE_FLOOR, TILE_LAVA, TILE_SLIPGATE_DOWN, TILE_SLIPGATE_UP,
    TILE_ENTRANCE, NUM_MAPS,
)


class TestNewGame:
    def test_new_game_creates_player(self):
        game = Game()
        game.new_game(seed=42)
        assert game.player is not None
        assert game.player.is_alive

    def test_new_game_creates_first_map(self):
        game = Game()
        game.new_game(seed=42)
        assert 0 in game.maps
        assert game.current_map_idx == 0

    def test_new_game_has_entrance(self):
        game = Game()
        game.new_game(seed=42)
        assert game.current_map.entrance_pos is not None

    def test_new_game_player_starts_with_axe(self):
        game = Game()
        game.new_game(seed=42)
        assert game.player.equipped_weapon.name == 'Axe'

    def test_new_game_welcome_message(self):
        game = Game()
        game.new_game(seed=42)
        msgs = game.message_log.get_all()
        assert len(msgs) > 0
        assert any('Welcome' in m for m in msgs)

    def test_seed_reproducibility(self):
        game1 = Game()
        game1.new_game(seed=42)
        game2 = Game()
        game2.new_game(seed=42)
        # Same seed should produce same map layout
        rooms1 = [(r.y, r.x) for r in game1.current_map.rooms]
        rooms2 = [(r.y, r.x) for r in game2.current_map.rooms]
        assert rooms1 == rooms2


class TestMovement:
    def test_move_player(self):
        game = Game()
        game.new_game(seed=42)
        # Place player in open space
        gmap = game.current_map
        # Find a floor tile
        for y in range(gmap.height):
            for x in range(gmap.width):
                if (gmap.get_tile(y, x) == TILE_FLOOR and
                        gmap.get_tile(y - 1, x) == TILE_FLOOR and
                        gmap.get_enemy_at(y, x) is None and
                        gmap.get_enemy_at(y - 1, x) is None):
                    game.player.pos = Position(y, x)
                    old_y = y
                    game.handle_input('k')  # Move up
                    assert game.player.pos.y == old_y - 1
                    return
        pytest.skip('Could not find suitable test position')

    def test_cannot_move_into_wall(self):
        game = Game()
        game.new_game(seed=42)
        # Place player next to wall
        game.player.pos = Position(1, 1)
        game.current_map.set_tile(1, 1, TILE_FLOOR)
        # Try to move up into wall (row 0 is always wall)
        old_pos = game.player.pos.copy()
        game.handle_input('k')
        assert game.player.pos.y == old_pos.y  # Didn't move

    def test_melee_attack_on_move(self):
        game = Game()
        game.new_game(seed=42)
        # Place player and enemy adjacent
        game.player.pos = Position(10, 10)
        game.current_map.set_tile(10, 10, TILE_FLOOR)
        game.current_map.set_tile(10, 11, TILE_FLOOR)
        enemy = Enemy.from_def(ROTTWEILER, Position(10, 11))
        game.current_map.enemies.append(enemy)

        initial_hp = enemy.health
        game.handle_input('l')  # Move right into enemy
        assert enemy.health < initial_hp


class TestSlipgates:
    def test_go_down_slipgate(self):
        game = Game()
        game.new_game(seed=42)
        gmap = game.current_map
        # Move player to slipgate down
        assert gmap.slipgate_down_pos is not None
        game.player.pos = gmap.slipgate_down_pos.copy()
        game.handle_input('>')
        assert game.current_map_idx == 1
        assert 1 in game.maps

    def test_go_up_slipgate(self):
        game = Game()
        game.new_game(seed=42)
        # Go to map 1 first
        gmap = game.current_map
        game.player.pos = gmap.slipgate_down_pos.copy()
        game.handle_input('>')
        assert game.current_map_idx == 1

        # Now go back
        new_map = game.current_map
        assert new_map.slipgate_up_pos is not None
        game.player.pos = new_map.slipgate_up_pos.copy()
        game.handle_input('<')
        assert game.current_map_idx == 0

    def test_slipgate_not_on_gate(self):
        game = Game()
        game.new_game(seed=42)
        game.player.pos = Position(10, 10)
        game.current_map.set_tile(10, 10, TILE_FLOOR)
        old_map = game.current_map_idx
        game.handle_input('>')
        assert game.current_map_idx == old_map  # Didn't change


class TestInventoryUI:
    def test_open_inventory(self):
        game = Game()
        game.new_game(seed=42)
        state = game.handle_input('i')
        assert game.state == GameState.INVENTORY
        assert state['show_inventory']

    def test_close_inventory(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('i')
        game.handle_input('i')
        assert game.state == GameState.PLAYING

    def test_close_inventory_escape(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('i')
        game.handle_input('Escape')
        assert game.state == GameState.PLAYING

    def test_navigate_inventory(self):
        game = Game()
        game.new_game(seed=42)
        # Add items
        game.player.inventory.add_item(create_item(SHOTGUN))
        game.handle_input('i')
        game.handle_input('ArrowDown')
        assert game.inventory_cursor == 1

    def test_pick_up_item(self):
        game = Game()
        game.new_game(seed=42)
        # Place item on ground
        shotgun = create_item(SHOTGUN)
        py, px = game.player.pos.y, game.player.pos.x
        game.current_map.add_item_at(py, px, shotgun)

        # Quick pick/drop should open loot panel
        game.handle_input('x')
        assert game.state == GameState.LOOT
        assert game.active_panel == 'loot'

        # Pick it up
        game.handle_input('x')
        assert game.player.inventory.find_by_name('Shotgun') is not None

    def test_drop_item(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('i')
        game.active_panel = 'inventory'
        game.inventory_cursor = 0
        # Drop the axe
        game.handle_input('x')
        items = game.current_map.get_items_at(
            game.player.pos.y, game.player.pos.x)
        assert any(i.name == 'Axe' for i in items)

    def test_activate_weapon_in_inventory(self):
        game = Game()
        game.new_game(seed=42)
        shotgun = create_item(SHOTGUN)
        game.player.inventory.add_item(shotgun)

        game.handle_input('i')
        game.active_panel = 'inventory'
        game.inventory_cursor = 1  # Shotgun is second
        game.handle_input('Return')
        assert game.player.equipped_weapon.name == 'Shotgun'


class TestTargeting:
    def test_start_targeting(self):
        game = Game()
        game.new_game(seed=42)
        # Place enemy in LOS
        game.current_map.set_tile(10, 10, TILE_FLOOR)
        game.current_map.set_tile(10, 15, TILE_FLOOR)
        for x in range(10, 16):
            game.current_map.set_tile(10, x, TILE_FLOOR)
        game.player.pos = Position(10, 10)
        game.current_map.reveal_around(10, 10)
        enemy = Enemy.from_def(GRUNT, Position(10, 15))
        game.current_map.enemies.append(enemy)

        game.handle_input('t')
        assert game.state == GameState.TARGETING
        assert len(game.target_list) > 0

    def test_no_targets(self):
        game = Game()
        game.new_game(seed=42)
        # Remove all enemies
        game.current_map.enemies.clear()
        game.handle_input('t')
        assert game.state == GameState.PLAYING

    def test_cycle_targets(self):
        game = Game()
        game.new_game(seed=42)
        for x in range(10, 25):
            game.current_map.set_tile(10, x, TILE_FLOOR)
        game.player.pos = Position(10, 10)
        game.current_map.reveal_around(10, 10)
        e1 = Enemy.from_def(GRUNT, Position(10, 12))
        e2 = Enemy.from_def(ROTTWEILER, Position(10, 14))
        game.current_map.enemies.extend([e1, e2])

        game.handle_input('t')
        first_target = game.target_cursor
        game.handle_input('t')
        second_target = game.target_cursor
        assert first_target != second_target


class TestSwapWeapon:
    def test_swap_weapon(self):
        game = Game()
        game.new_game(seed=42)
        shotgun = create_item(SHOTGUN)
        game.player.inventory.add_item(shotgun)
        game.player.equip_weapon(shotgun)

        assert game.player.equipped_weapon.name == 'Shotgun'
        game.handle_input('w')
        assert game.player.equipped_weapon.name == 'Axe'

    def test_swap_no_previous(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('w')
        msgs = game.message_log.get_recent(1)
        assert any('no previous' in m.lower() for m in msgs)


class TestMessageLog:
    def test_open_message_log(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('p')
        assert game.state == GameState.MESSAGE_LOG

    def test_close_message_log(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('p')
        game.handle_input('p')
        assert game.state == GameState.PLAYING


class TestDeath:
    def test_player_death_ends_game(self):
        game = Game()
        game.new_game(seed=42)
        game.player.take_damage(999)
        game.player.is_alive = False
        # Trigger end turn check
        game._end_turn()
        assert game.state == GameState.GAME_OVER

    def test_quit_game(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('Q')
        assert game.state == GameState.GAME_OVER


class TestVictory:
    def test_victory_with_rune_at_entrance(self):
        game = Game()
        game.new_game(seed=42)
        # Give player the rune
        rune_def = ItemDef(name='Rune', item_type=ItemType.POWERUP,
                           char='&', color='#FFD700')
        rune = create_item(rune_def)
        game.player.inventory.add_item(rune)
        assert game.player.has_rune()

        # Move to entrance on map 0
        entrance = game.current_map.entrance_pos
        # Place player adjacent to entrance
        game.player.pos = Position(entrance.y + 1, entrance.x)
        game.current_map.set_tile(entrance.y + 1, entrance.x, TILE_FLOOR)
        game.current_map.set_tile(entrance.y, entrance.x, TILE_ENTRANCE)

        # Move onto entrance
        game.handle_input('k')  # Move up
        assert game.state == GameState.VICTORY

    def test_no_victory_without_rune(self):
        game = Game()
        game.new_game(seed=42)
        entrance = game.current_map.entrance_pos
        game.player.pos = entrance.copy()
        game.handle_input('<')
        assert game.state != GameState.VICTORY


class TestSaveLoad:
    def test_save_game(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('S')
        assert os.path.exists('saves/savegame.json')

    def test_load_game(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('S')

        game2 = Game()
        assert game2.load_game()
        assert game2.player is not None
        assert game2.player.health == game.player.health
        assert game2.current_map_idx == game.current_map_idx
        assert game2.seed == game.seed

    def test_load_preserves_inventory(self):
        game = Game()
        game.new_game(seed=42)
        # Add item to inventory
        shotgun = create_item(SHOTGUN)
        game.player.inventory.add_item(shotgun)
        game.handle_input('S')

        game2 = Game()
        game2.load_game()
        assert game2.player.inventory.find_by_name('Shotgun') is not None

    def test_load_nonexistent(self):
        if os.path.exists('saves/savegame.json'):
            os.remove('saves/savegame.json')
        game = Game()
        assert not game.load_game()

    def test_save_load_preserves_map_state(self):
        game = Game()
        game.new_game(seed=42)
        # Explore
        game.current_map.reveal_around(game.player.pos.y, game.player.pos.x)
        explored_count = len(game.current_map.explored)
        game.handle_input('S')

        game2 = Game()
        game2.load_game()
        assert len(game2.current_map.explored) == explored_count


class TestRenderState:
    def test_render_state_has_all_fields(self):
        game = Game()
        game.new_game(seed=42)
        state = game.get_render_state()

        assert 'state' in state
        assert 'map' in state
        assert 'map_width' in state
        assert 'map_height' in state
        assert 'status' in state
        assert 'messages' in state
        assert 'inventory' in state
        assert 'loot' in state

    def test_status_has_all_fields(self):
        game = Game()
        game.new_game(seed=42)
        state = game.get_render_state()
        status = state['status']

        assert 'health' in status
        assert 'max_health' in status
        assert 'armor' in status
        assert 'weapon' in status
        assert 'ammo' in status
        assert 'level' in status
        assert 'xp' in status
        assert 'map_level' in status
        assert 'powerups' in status

    def test_map_dimensions_correct(self):
        game = Game()
        game.new_game(seed=42)
        state = game.get_render_state()
        assert len(state['map']) == state['map_height']
        assert len(state['map'][0]) == state['map_width']


class TestEnvironmentalDamage:
    def test_lava_deals_damage(self):
        game = Game()
        game.new_game(seed=42)
        # Setup a lava tile
        game.current_map.set_tile(10, 10, TILE_FLOOR)
        game.current_map.set_tile(10, 11, TILE_LAVA)
        game.player.pos = Position(10, 10)
        # Clear enemies from the destination
        game.current_map.enemies = [
            e for e in game.current_map.enemies
            if e.pos != Position(10, 11)
        ]

        initial_hp = game.player.health
        game.handle_input('l')  # Move right into lava
        assert game.player.health < initial_hp

    def test_biosuit_protects_from_lava(self):
        game = Game()
        game.new_game(seed=42)
        game.current_map.set_tile(10, 10, TILE_FLOOR)
        game.current_map.set_tile(10, 11, TILE_LAVA)
        game.player.pos = Position(10, 10)
        game.player.biosuit_turns = 10
        game.current_map.enemies = [
            e for e in game.current_map.enemies
            if e.pos != Position(10, 11)
        ]

        initial_hp = game.player.health
        game.handle_input('l')
        assert game.player.health == initial_hp


class TestMeleeXP:
    def test_melee_kill_awards_xp(self):
        game = Game()
        game.new_game(seed=42)
        game.player.pos = Position(10, 10)
        game.current_map.set_tile(10, 10, TILE_FLOOR)
        game.current_map.set_tile(10, 11, TILE_FLOOR)
        enemy = Enemy.from_def(ROTTWEILER, Position(10, 11))
        enemy.health = 1  # One hit kill
        game.current_map.enemies.append(enemy)

        initial_xp = game.player.xp
        game.handle_input('l')  # Move right into enemy
        assert not enemy.is_alive
        assert game.player.xp > initial_xp
        msgs = game.message_log.get_all()
        assert any('XP' in m for m in msgs)


class TestQuitVsDeath:
    def test_quit_sets_quit_flag(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('Q')
        assert game.state == GameState.GAME_OVER
        assert game.quit is True

    def test_death_does_not_set_quit_flag(self):
        game = Game()
        game.new_game(seed=42)
        game.player.health = 1
        game.player.is_alive = True
        game.player.take_damage(999)
        game._end_turn()
        assert game.state == GameState.GAME_OVER
        assert game.quit is False

    def test_render_state_includes_quit_flag(self):
        game = Game()
        game.new_game(seed=42)
        state = game.get_render_state()
        assert 'quit' in state
        assert state['quit'] is False
        game.handle_input('Q')
        state = game.get_render_state()
        assert state['quit'] is True


class TestPermadeath:
    def test_save_deleted_on_death(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('S')  # Save
        assert os.path.exists('saves/savegame.json')

        # Kill the player
        game.player.health = 1
        game.player.take_damage(999)
        game._end_turn()
        assert game.state == GameState.GAME_OVER
        assert not os.path.exists('saves/savegame.json')


class TestSaveLoadRune:
    def test_save_load_preserves_rune(self):
        game = Game()
        game.new_game(seed=42)
        rune = create_item(RUNE)
        game.player.inventory.add_item(rune)
        assert game.player.has_rune()

        game.handle_input('S')

        game2 = Game()
        game2.load_game()
        assert game2.player.has_rune()

    def test_save_load_rune_on_ground(self):
        game = Game()
        game.new_game(seed=42)
        rune = create_item(RUNE)
        py, px = game.player.pos.y, game.player.pos.x
        game.current_map.add_item_at(py, px, rune)

        game.handle_input('S')

        game2 = Game()
        game2.load_game()
        items = game2.current_map.get_items_at(py, px)
        assert any(i.name == 'Rune' for i in items)
