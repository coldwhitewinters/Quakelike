"""Regression tests for 4 known bugs (red phase — all should FAIL until fixes are applied)."""

import pytest
from quakelike.game import Game, GameState
from quakelike.entity import Position
from quakelike.items import create_item, SHOTGUN
from quakelike.constants import TILE_FLOOR


class TestRestKey:
    def test_pressing_dot_skips_turn_and_logs_rest_message(self):
        """Issue 1: '.' key should end the player's turn and add 'You rest.' message.

        Currently '.' has no handler in _handle_playing_input, so nothing happens
        and no message is logged.
        """
        game = Game()
        game.new_game(seed=42)

        initial_turn = game.turn
        game.handle_input('.')

        # The turn counter must have advanced (proves _end_turn was called)
        assert game.turn == initial_turn + 1, (
            "Pressing '.' should call _end_turn(), advancing the turn counter"
        )

        # A rest message must appear in the log
        all_messages = game.message_log.get_all()
        assert any('rest' in m.lower() for m in all_messages), (
            "Pressing '.' should log a 'You rest.' message"
        )


class TestInventoryDefaultPanel:
    def test_open_inventory_defaults_to_loot_panel_when_floor_items_present(self):
        """Issue 2: opening inventory when there are floor items should default to 'loot' panel.

        Currently _open_inventory() always sets active_panel = 'inventory' regardless
        of whether there are items on the floor.
        """
        game = Game()
        game.new_game(seed=42)

        # Place an item on the floor at the player's position
        py, px = game.player.pos.y, game.player.pos.x
        shotgun = create_item(SHOTGUN)
        game.current_map.add_item_at(py, px, shotgun)

        # Open inventory
        game.handle_input('i')
        assert game.state == GameState.INVENTORY

        assert game.active_panel == 'loot', (
            "When floor items are present, opening inventory should default to the 'loot' panel"
        )


class TestCommaPickup:
    def test_comma_picks_up_first_floor_item_without_opening_inventory(self):
        """Issue 3: ',' key should pick up the first floor item directly.

        Currently ',' has no handler in _handle_playing_input, so nothing happens.
        """
        game = Game()
        game.new_game(seed=42)

        # Place an item on the floor at the player's position
        py, px = game.player.pos.y, game.player.pos.x
        shotgun = create_item(SHOTGUN)
        game.current_map.add_item_at(py, px, shotgun)

        initial_inv_count = game.player.inventory.count
        game.handle_input(',')

        # Game must stay in PLAYING state — inventory should NOT have opened
        assert game.state == GameState.PLAYING, (
            "Pressing ',' should not open the inventory panel"
        )

        # Item must have been added to inventory
        assert game.player.inventory.count == initial_inv_count + 1, (
            "Pressing ',' should pick up the first floor item into inventory"
        )

        # The floor must now be empty at that position
        remaining = game.current_map.get_items_at(py, px)
        assert len(remaining) == 0, (
            "Pressing ',' should remove the picked-up item from the floor"
        )

        # A 'Picked up' message must appear in the log
        all_messages = game.message_log.get_all()
        assert any('picked up' in m.lower() for m in all_messages), (
            "Pressing ',' should log a 'Picked up <item>.' message"
        )

    def test_comma_with_full_inventory_logs_inventory_is_full(self):
        """Issue 3 (full-inventory branch): ',' with a full inventory logs appropriate message and does not advance the turn."""
        game = Game()
        game.new_game(seed=42)

        # Fill inventory to the max (10 slots)
        for _ in range(10):
            game.player.inventory.add_item(create_item(SHOTGUN))

        py, px = game.player.pos.y, game.player.pos.x
        game.current_map.add_item_at(py, px, create_item(SHOTGUN))

        initial_turn = game.turn
        game.handle_input(',')

        assert game.turn == initial_turn, "Failed pickup should not advance the turn"
        all_messages = game.message_log.get_all()
        assert any('inventory is full' in m.lower() for m in all_messages), (
            "Pressing ',' with a full inventory should log 'Inventory is full.'"
        )

    def test_comma_with_no_floor_items_logs_nothing_to_pick_up(self):
        """Issue 3 (no-item branch): ',' with nothing on the floor logs appropriate message."""
        game = Game()
        game.new_game(seed=42)

        # Ensure no items at player position
        py, px = game.player.pos.y, game.player.pos.x
        assert game.current_map.get_items_at(py, px) == [], (
            "Test pre-condition: no items on floor"
        )

        game.handle_input(',')

        all_messages = game.message_log.get_all()
        assert any('nothing to pick up' in m.lower() for m in all_messages), (
            "Pressing ',' with no floor items should log 'Nothing to pick up.'"
        )


class TestInventoryVimNavigation:
    def test_j_moves_inventory_cursor_down(self):
        """Issue 4: 'j' should move the cursor down inside the inventory panel.

        Currently _handle_inventory_input only checks KEY_NAV_DOWN ('ArrowDown'),
        not the vim key 'j'.
        """
        game = Game()
        game.new_game(seed=42)

        # Add a second item so there is somewhere to move the cursor
        game.player.inventory.add_item(create_item(SHOTGUN))
        game.handle_input('i')
        game.active_panel = 'inventory'
        game.inventory_cursor = 0

        game.handle_input('j')

        assert game.inventory_cursor == 1, (
            "'j' in inventory should move cursor down (same as ArrowDown)"
        )

    def test_k_moves_inventory_cursor_up(self):
        """Issue 4: 'k' should move the cursor up inside the inventory panel."""
        game = Game()
        game.new_game(seed=42)

        game.player.inventory.add_item(create_item(SHOTGUN))
        game.handle_input('i')
        game.active_panel = 'inventory'
        game.inventory_cursor = 1  # Start at second item

        game.handle_input('k')

        assert game.inventory_cursor == 0, (
            "'k' in inventory should move cursor up (same as ArrowUp)"
        )

    def test_h_switches_to_loot_panel(self):
        """Issue 4: 'h' should switch focus to the loot panel (same as ArrowLeft)."""
        game = Game()
        game.new_game(seed=42)

        game.handle_input('i')
        game.active_panel = 'inventory'

        game.handle_input('h')

        assert game.active_panel == 'loot', (
            "'h' in inventory should switch active panel to 'loot' (same as ArrowLeft)"
        )

    def test_l_switches_to_inventory_panel(self):
        """Issue 4: 'l' should switch focus to the inventory panel (same as ArrowRight)."""
        game = Game()
        game.new_game(seed=42)

        game.handle_input('i')
        game.active_panel = 'loot'

        game.handle_input('l')

        assert game.active_panel == 'inventory', (
            "'l' in inventory should switch active panel to 'inventory' (same as ArrowRight)"
        )
