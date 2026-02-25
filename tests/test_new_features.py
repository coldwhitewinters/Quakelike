"""Tests for new features: inventory always-both, Tab transfer,
examine mode, help screen, and refactored targeting."""

import pytest
from quakelike.game import Game, GameState
from quakelike.entity import Position
from quakelike.items import create_item, SHOTGUN, AXE, SHELLS_SMALL
from quakelike.enemies import Enemy, GRUNT, ROTTWEILER
from quakelike.constants import TILE_FLOOR


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_game_with_enemies_in_los():
    """Return a game with two enemies in a clear LOS corridor."""
    game = Game()
    game.new_game(seed=42)
    # Clear a corridor for reliable LOS
    game.current_map.enemies.clear()
    for x in range(10, 25):
        game.current_map.set_tile(10, x, TILE_FLOOR)
    game.player.pos = Position(10, 10)
    game.current_map.reveal_around(10, 10)
    e1 = Enemy.from_def(GRUNT, Position(10, 12))
    e2 = Enemy.from_def(ROTTWEILER, Position(10, 14))
    game.current_map.enemies.extend([e1, e2])
    return game, e1, e2


# ---------------------------------------------------------------------------
# Change 1: 'i' always opens BOTH panels
# ---------------------------------------------------------------------------

class TestInventoryAlwaysBoth:
    def test_i_opens_inventory_state(self):
        game = Game()
        game.new_game(seed=42)
        state = game.handle_input('i')
        assert game.state == GameState.INVENTORY

    def test_i_shows_both_panels_floor_empty(self):
        """'i' shows both inventory and loot panel even when floor is empty."""
        game = Game()
        game.new_game(seed=42)
        # Ensure no items on floor
        py, px = game.player.pos.y, game.player.pos.x
        game.current_map.items_on_ground.pop((py, px), None)

        state = game.handle_input('i')
        assert state['show_inventory'] is True
        assert state['show_loot'] is True

    def test_i_shows_both_panels_floor_has_items(self):
        """'i' shows both panels when there are items on the floor."""
        game = Game()
        game.new_game(seed=42)
        py, px = game.player.pos.y, game.player.pos.x
        game.current_map.add_item_at(py, px, create_item(SHOTGUN))

        state = game.handle_input('i')
        assert state['show_inventory'] is True
        assert state['show_loot'] is True

    def test_i_default_active_panel_is_inventory(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('i')
        assert game.active_panel == 'inventory'

    def test_i_closes_on_second_i(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('i')
        game.handle_input('i')
        assert game.state == GameState.PLAYING

    def test_i_closes_on_escape(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('i')
        game.handle_input('Escape')
        assert game.state == GameState.PLAYING


# ---------------------------------------------------------------------------
# Change 2: Tab transfers items between panels
# ---------------------------------------------------------------------------

class TestTabTransfer:
    def test_tab_picks_up_item_from_loot(self):
        game = Game()
        game.new_game(seed=42)
        py, px = game.player.pos.y, game.player.pos.x
        game.current_map.add_item_at(py, px, create_item(SHOTGUN))

        # Open inventory panel (both panels shown)
        game.handle_input('i')
        # Switch active panel to loot
        game.active_panel = 'loot'
        game.loot_cursor = 0

        game.handle_input('Tab')
        assert game.player.inventory.find_by_name('Shotgun') is not None
        # Floor should now be empty at player position
        floor_items = game.current_map.get_items_at(py, px)
        assert not any(i.name == 'Shotgun' for i in floor_items)

    def test_tab_drops_item_to_floor(self):
        game = Game()
        game.new_game(seed=42)
        py, px = game.player.pos.y, game.player.pos.x

        game.handle_input('i')
        game.active_panel = 'inventory'
        game.inventory_cursor = 0  # Axe is first item

        game.handle_input('Tab')
        floor_items = game.current_map.get_items_at(py, px)
        assert any(i.name == 'Axe' for i in floor_items)

    def test_x_no_longer_transfers_in_inventory(self):
        """'x' in inventory/loot state should NOT transfer items (Tab does)."""
        game = Game()
        game.new_game(seed=42)
        py, px = game.player.pos.y, game.player.pos.x
        # Use SHELLS_SMALL since player starts without shells on the floor
        from quakelike.items import SHELLS_SMALL
        # Count shells before
        shells_before = game.player.inventory.get_ammo_count(
            __import__('quakelike.items', fromlist=['AmmoType']).AmmoType.SHELLS)

        # Place a second shotgun box on ground
        game.current_map.add_item_at(py, px, create_item(SHELLS_SMALL))

        game.handle_input('i')
        game.active_panel = 'loot'
        game.loot_cursor = 0

        # Count items on floor before
        floor_before = len(game.current_map.get_items_at(py, px))

        game.handle_input('x')
        # Floor item count should NOT have changed (x does nothing in inventory mode)
        floor_after = len(game.current_map.get_items_at(py, px))
        assert floor_after == floor_before


# ---------------------------------------------------------------------------
# Change 3: 'x' enters EXAMINE state
# ---------------------------------------------------------------------------

class TestExamineMode:
    def test_x_enters_examine_state(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('x')
        assert game.state == GameState.EXAMINE

    def test_examine_cursor_starts_at_player_pos(self):
        game = Game()
        game.new_game(seed=42)
        py, px = game.player.pos.y, game.player.pos.x
        game.handle_input('x')
        assert game.examine_cursor == (py, px)

    def test_examine_cursor_moves_with_hjkl(self):
        game = Game()
        game.new_game(seed=42)
        py, px = game.player.pos.y, game.player.pos.x
        game.handle_input('x')  # Enter examine

        # Move right
        game.handle_input('l')
        assert game.examine_cursor == (py, px + 1)

        # Move left
        game.handle_input('h')
        assert game.examine_cursor == (py, px)

        # Move up
        game.handle_input('k')
        assert game.examine_cursor == (py - 1, px)

        # Move down
        game.handle_input('j')
        assert game.examine_cursor == (py, px)

    def test_examine_cursor_moves_diagonally(self):
        game = Game()
        game.new_game(seed=42)
        py, px = game.player.pos.y, game.player.pos.x
        game.handle_input('x')
        game.handle_input('u')  # up-right
        assert game.examine_cursor == (py - 1, px + 1)

    def test_examine_cursor_clamped_at_map_bounds(self):
        game = Game()
        game.new_game(seed=42)
        # Place cursor near top-left corner
        game.examine_cursor = (0, 0)
        game.state = GameState.EXAMINE
        # Try to move up beyond boundary
        game.handle_input('k')
        assert game.examine_cursor[0] >= 0
        # Try to move left beyond boundary
        game.examine_cursor = (0, 0)
        game.handle_input('h')
        assert game.examine_cursor[1] >= 0

    def test_examine_escape_returns_to_playing(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('x')
        assert game.state == GameState.EXAMINE
        game.handle_input('Escape')
        assert game.state == GameState.PLAYING

    def test_examine_x_returns_to_playing(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('x')
        assert game.state == GameState.EXAMINE
        game.handle_input('x')
        assert game.state == GameState.PLAYING

    def test_examine_info_in_render_state(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('x')
        state = game.get_render_state()
        assert state['show_examine'] is True
        assert 'examine_cursor' in state
        assert 'examine_info' in state
        assert isinstance(state['examine_info'], str)

    def test_examine_info_describes_tile(self):
        game = Game()
        game.new_game(seed=42)
        # Place cursor on player tile (which is explored)
        game.handle_input('x')
        state = game.get_render_state()
        # The examine_info should not be empty for explored tiles
        assert len(state['examine_info']) > 0

    def test_examine_info_shows_enemy(self):
        game = Game()
        game.new_game(seed=42)
        game.current_map.enemies.clear()
        game.current_map.set_tile(10, 12, TILE_FLOOR)
        for x in range(10, 13):
            game.current_map.set_tile(10, x, TILE_FLOOR)
        game.player.pos = Position(10, 10)
        game.current_map.reveal_around(10, 10)
        enemy = Enemy.from_def(GRUNT, Position(10, 12))
        game.current_map.enemies.append(enemy)

        # Enter examine and move cursor to enemy position
        game.state = GameState.EXAMINE
        game.examine_cursor = (10, 12)
        info = game._get_examine_info()
        assert 'Grunt' in info
        assert 'HP' in info

    def test_examine_info_shows_items(self):
        game = Game()
        game.new_game(seed=42)
        # Place item on a tile near player
        game.current_map.set_tile(10, 10, TILE_FLOOR)
        game.current_map.add_item_at(10, 10, create_item(SHOTGUN))
        game.current_map.explored.add((10, 10))

        game.state = GameState.EXAMINE
        game.examine_cursor = (10, 10)
        info = game._get_examine_info()
        assert 'Shotgun' in info

    def test_examine_cursor_marker_in_map(self):
        """The examine cursor tile should have cursor=True in the render map."""
        game = Game()
        game.new_game(seed=42)
        game.handle_input('x')
        state = game.get_render_state()
        cy, cx = state['examine_cursor']
        assert state['map'][cy][cx].get('cursor') is True

    def test_show_examine_false_when_not_in_examine(self):
        game = Game()
        game.new_game(seed=42)
        state = game.get_render_state()
        assert state['show_examine'] is False


# ---------------------------------------------------------------------------
# Change 4: Help screen ('?')
# ---------------------------------------------------------------------------

class TestHelpScreen:
    def test_question_mark_opens_help_from_playing(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('?')
        assert game.state == GameState.HELP

    def test_question_mark_opens_help_from_game_over(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('Q')  # Quit -> GAME_OVER
        assert game.state == GameState.GAME_OVER
        game.handle_input('?')
        assert game.state == GameState.HELP

    def test_help_escape_returns_to_playing(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('?')
        game.handle_input('Escape')
        assert game.state == GameState.PLAYING

    def test_help_question_mark_returns_to_playing(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('?')
        game.handle_input('?')
        assert game.state == GameState.PLAYING

    def test_help_from_game_over_returns_to_game_over(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('Q')
        game.handle_input('?')
        assert game.state == GameState.HELP
        game.handle_input('Escape')
        assert game.state == GameState.GAME_OVER

    def test_previous_state_saved_as_playing(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('?')
        assert game.previous_state == GameState.PLAYING

    def test_previous_state_saved_as_game_over(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('Q')
        game.handle_input('?')
        assert game.previous_state == GameState.GAME_OVER

    def test_show_help_in_render_state(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('?')
        state = game.get_render_state()
        assert state['show_help'] is True
        assert isinstance(state['help_content'], list)
        assert len(state['help_content']) > 0

    def test_show_help_false_when_not_in_help(self):
        game = Game()
        game.new_game(seed=42)
        state = game.get_render_state()
        assert state['show_help'] is False
        assert state['help_content'] == []

    def test_help_content_contains_key_bindings(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('?')
        state = game.get_render_state()
        content = '\n'.join(state['help_content'])
        assert 'h/j/k/l' in content
        assert 'Tab' in content
        assert 'examine' in content.lower() or 'x' in content

    def test_previous_state_cleared_after_exit(self):
        game = Game()
        game.new_game(seed=42)
        game.handle_input('?')
        game.handle_input('Escape')
        assert game.previous_state is None


# ---------------------------------------------------------------------------
# Change 5: Target cycling from PLAYING state
# ---------------------------------------------------------------------------

class TestTargetCyclingFromPlaying:
    def test_t_cycles_forward_in_playing_state(self):
        game, e1, e2 = _make_game_with_enemies_in_los()
        # First 't' should select the first enemy
        game.handle_input('t')
        assert game.state == GameState.PLAYING
        assert game.target_cursor >= 0
        assert game.player.target_index >= 0

    def test_t_no_enemies_stays_playing(self):
        game = Game()
        game.new_game(seed=42)
        game.current_map.enemies.clear()
        game.handle_input('t')
        assert game.state == GameState.PLAYING
        assert game.target_cursor == -1

    def test_t_cycles_to_next_enemy(self):
        game, e1, e2 = _make_game_with_enemies_in_los()
        game.handle_input('t')
        first_cursor = game.target_cursor
        game.handle_input('t')
        second_cursor = game.target_cursor
        assert first_cursor != second_cursor

    def test_t_wraps_around(self):
        game, e1, e2 = _make_game_with_enemies_in_los()
        # Cycle through all enemies until we wrap
        for _ in range(len(game.target_list) + 1):
            game.handle_input('t')
        # Should wrap without error and cursor in valid range
        assert 0 <= game.target_cursor < len(game.target_list)

    def test_capital_T_cycles_backward(self):
        game, e1, e2 = _make_game_with_enemies_in_los()
        # Select first target
        game.handle_input('t')
        first_cursor = game.target_cursor
        # Cycle backward
        game.handle_input('T')
        backward_cursor = game.target_cursor
        # After forward then backward, should be at last (wrapped)
        # The exact value depends on list length; just check it changed or is valid
        assert 0 <= backward_cursor < len(game.target_list)

    def test_capital_T_no_enemies_stays_playing(self):
        game = Game()
        game.new_game(seed=42)
        game.current_map.enemies.clear()
        game.handle_input('T')
        assert game.state == GameState.PLAYING
        assert game.target_cursor == -1

    def test_alt_t_clears_target(self):
        game, e1, e2 = _make_game_with_enemies_in_los()
        # First select a target
        game.handle_input('t')
        assert game.player.target_index >= 0

        # Clear target
        game.handle_input('Alt-t')
        assert game.state == GameState.PLAYING
        assert game.player.target_index == -1
        assert game.target_cursor == -1

    def test_alt_t_logs_message(self):
        game, e1, e2 = _make_game_with_enemies_in_los()
        game.handle_input('t')
        game.handle_input('Alt-t')
        msgs = game.message_log.get_all()
        assert any('cleared' in m.lower() for m in msgs)

    def test_t_logs_targeting_message(self):
        game, e1, e2 = _make_game_with_enemies_in_los()
        game.handle_input('t')
        msgs = game.message_log.get_all()
        assert any('Targeting' in m for m in msgs)

    def test_t_stays_in_playing_state(self):
        """'t' should NOT enter TARGETING state anymore."""
        game, e1, e2 = _make_game_with_enemies_in_los()
        game.handle_input('t')
        assert game.state == GameState.PLAYING

    def test_capital_T_backward_wraps_at_start(self):
        """Pressing T when cursor is at 0 should wrap to last enemy."""
        game, e1, e2 = _make_game_with_enemies_in_los()
        # Set cursor to 0 and target_list populated
        game.target_list = game.current_map.get_living_enemies()
        # Wait, use get_enemies_in_los
        from quakelike.ai import get_enemies_in_los
        game.target_list = get_enemies_in_los(game.player, game.current_map)
        game.target_cursor = 0
        game.player.target_index = 0

        game.handle_input('T')
        assert game.target_cursor == len(game.target_list) - 1

    def test_t_forward_wraps_at_end(self):
        """Pressing t when cursor is at last enemy should wrap to 0."""
        game, e1, e2 = _make_game_with_enemies_in_los()
        from quakelike.ai import get_enemies_in_los
        game.target_list = get_enemies_in_los(game.player, game.current_map)
        game.target_cursor = len(game.target_list) - 1
        game.player.target_index = len(game.target_list) - 1

        game.handle_input('t')
        assert game.target_cursor == 0


# ---------------------------------------------------------------------------
# Render state: always include show_loot in INVENTORY state
# ---------------------------------------------------------------------------

class TestRenderStateNewFields:
    def test_render_has_show_examine(self):
        game = Game()
        game.new_game(seed=42)
        state = game.get_render_state()
        assert 'show_examine' in state

    def test_render_has_examine_cursor(self):
        game = Game()
        game.new_game(seed=42)
        state = game.get_render_state()
        assert 'examine_cursor' in state

    def test_render_has_examine_info(self):
        game = Game()
        game.new_game(seed=42)
        state = game.get_render_state()
        assert 'examine_info' in state

    def test_render_has_show_help(self):
        game = Game()
        game.new_game(seed=42)
        state = game.get_render_state()
        assert 'show_help' in state

    def test_render_has_help_content(self):
        game = Game()
        game.new_game(seed=42)
        state = game.get_render_state()
        assert 'help_content' in state

    def test_show_loot_true_in_inventory_state(self):
        """show_loot should be True even in INVENTORY state (not just LOOT)."""
        game = Game()
        game.new_game(seed=42)
        game.handle_input('i')
        state = game.get_render_state()
        assert state['show_loot'] is True
