"""Unit tests for the target highlight background feature.

These tests operate directly on the tile dict structure produced by
get_render_state() for targeted and non-targeted enemies.
"""

import pytest
from quakelike.game import Game
from quakelike.entity import Position
from quakelike.enemies import Enemy, GRUNT, ROTTWEILER
from quakelike.constants import TILE_FLOOR


def _make_game_with_enemy(seed: int = 42) -> tuple[Game, Enemy]:
    """Return a game and a GRUNT enemy visible to the player."""
    game = Game()
    game.new_game(seed=seed)

    game.current_map.enemies.clear()

    # Open a clear corridor from (10,10) to (10,15)
    for x in range(10, 16):
        game.current_map.set_tile(10, x, TILE_FLOOR)

    game.player.pos = Position(10, 10)
    game.current_map.reveal_around(10, 10)

    enemy = Enemy.from_def(GRUNT, Position(10, 15))
    game.current_map.enemies.append(enemy)

    return game, enemy


class TestTargetedTileStructure:
    """Unit tests that verify the exact dict structure of a targeted tile."""

    def test_targeted_tile_has_char(self):
        game, enemy = _make_game_with_enemy()
        game.target_list = [enemy]
        game.target_cursor = 0

        state = game.get_render_state()
        tile = state['map'][enemy.pos.y][enemy.pos.x]

        assert 'char' in tile, f"Expected 'char' in tile, got {tile!r}"

    def test_targeted_tile_has_color(self):
        game, enemy = _make_game_with_enemy()
        game.target_list = [enemy]
        game.target_cursor = 0

        state = game.get_render_state()
        tile = state['map'][enemy.pos.y][enemy.pos.x]

        assert 'color' in tile, f"Expected 'color' in tile, got {tile!r}"

    def test_targeted_tile_has_targeted_true(self):
        """Tile dict for a targeted enemy must contain targeted=True."""
        game, enemy = _make_game_with_enemy()
        game.target_list = [enemy]
        game.target_cursor = 0

        state = game.get_render_state()
        tile = state['map'][enemy.pos.y][enemy.pos.x]

        assert tile.get('targeted') is True, (
            f"Expected tile['targeted'] == True, got tile={tile!r}"
        )

    def test_targeted_tile_color_is_original_enemy_color(self):
        """Tile color must be the enemy's own color, not a red override."""
        game, enemy = _make_game_with_enemy()
        game.target_list = [enemy]
        game.target_cursor = 0

        state = game.get_render_state()
        tile = state['map'][enemy.pos.y][enemy.pos.x]

        assert tile['color'] == enemy.color, (
            f"Expected tile['color'] == {enemy.color!r}, got {tile['color']!r}"
        )


class TestNonTargetedTileStructure:
    """Unit tests that verify a non-targeted enemy's tile has no targeted key."""

    def test_non_targeted_tile_no_flag(self):
        """Tile dict for a non-targeted enemy must not contain a 'targeted' key."""
        game, enemy = _make_game_with_enemy()

        # Add a second enemy; target it so the first is explicitly NOT targeted.
        for x in range(16, 20):
            game.current_map.set_tile(10, x, TILE_FLOOR)
        second_enemy = Enemy.from_def(ROTTWEILER, Position(10, 19))
        game.current_map.enemies.append(second_enemy)
        game.current_map.reveal_around(10, 10)

        game.target_list = [enemy, second_enemy]
        game.target_cursor = 1  # second_enemy is targeted; enemy (GRUNT) is not

        state = game.get_render_state()
        untargeted_tile = state['map'][enemy.pos.y][enemy.pos.x]

        assert not untargeted_tile.get('targeted'), (
            f"Non-targeted tile must not have targeted=True, got {untargeted_tile!r}"
        )

    def test_non_targeted_tile_has_original_color(self):
        """Non-targeted enemy tile color must be the enemy's own color."""
        game, enemy = _make_game_with_enemy()
        # target_cursor == -1 means nothing is targeted
        game.target_list = [enemy]
        game.target_cursor = -1

        state = game.get_render_state()
        tile = state['map'][enemy.pos.y][enemy.pos.x]

        assert tile['color'] == enemy.color, (
            f"Expected tile['color'] == {enemy.color!r}, got {tile['color']!r}"
        )
