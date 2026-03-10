"""Acceptance tests for the target highlight background feature.

These tests define the expected NEW behavior where a targeted enemy's tile:
  - gains a `targeted: True` key in the render state dict
  - keeps its original enemy `color` (NOT overridden to '#FF0000')

All tests are written in the RED phase — they will FAIL against the current
implementation and must pass only after the feature is implemented.
"""

import pytest
from unittest import mock

from quakelike.game import Game, GameState
from quakelike.entity import Position
from quakelike.enemies import Enemy, GRUNT, ROTTWEILER
from quakelike.constants import TILE_FLOOR


def _setup_game_with_visible_enemy(seed: int = 42) -> tuple[Game, Enemy]:
    """Return a game and an enemy that is in LOS of the player.

    The player is placed at (10, 10) with a clear corridor to (10, 15) where
    the enemy stands.  All tiles in between are revealed so LOS computation
    works correctly.
    """
    game = Game()
    game.new_game(seed=seed)

    # Clear existing enemies to have full control over the target list.
    game.current_map.enemies.clear()

    # Build an open corridor so LOS is unobstructed.
    for x in range(10, 16):
        game.current_map.set_tile(10, x, TILE_FLOOR)

    game.player.pos = Position(10, 10)
    # Reveal the full map so visibility checks succeed.
    game.current_map.reveal_around(10, 10)

    enemy = Enemy.from_def(GRUNT, Position(10, 15))
    game.current_map.enemies.append(enemy)

    return game, enemy


class TestTargetHighlightAcceptance:
    """Acceptance tests for the targeted enemy tile rendering change.

    Current behavior (red phase):
        - targeted enemy tile has `color == '#FF0000'`
        - no `targeted` key is present

    Required new behavior (these tests define):
        - targeted enemy tile has `targeted == True`
        - `color` is the enemy's original `.color` attribute, NOT '#FF0000'
    """

    # ------------------------------------------------------------------
    # 1. Targeted enemy tile has `targeted: True`
    # ------------------------------------------------------------------
    def test_targeted_enemy_has_targeted_flag(self):
        """Tile for the enemy at target_cursor must contain targeted=True."""
        game, enemy = _setup_game_with_visible_enemy()

        # Directly put the game into targeting state with this enemy selected.
        game.target_list = [enemy]
        game.target_cursor = 0

        state = game.get_render_state()
        tile = state['map'][enemy.pos.y][enemy.pos.x]

        assert tile.get('targeted') is True, (
            f"Expected tile['targeted'] == True, got tile={tile!r}"
        )

    # ------------------------------------------------------------------
    # 2. Targeted enemy color is NOT the red override
    # ------------------------------------------------------------------
    def test_targeted_enemy_color_is_not_red_override(self):
        """Targeted enemy tile must NOT have color overridden to '#FF0000'."""
        game, enemy = _setup_game_with_visible_enemy()

        game.target_list = [enemy]
        game.target_cursor = 0

        state = game.get_render_state()
        tile = state['map'][enemy.pos.y][enemy.pos.x]

        assert tile['color'] != '#FF0000', (
            f"Expected color to NOT be '#FF0000', but got color={tile['color']!r}"
        )

    # ------------------------------------------------------------------
    # 3. Targeted enemy preserves original enemy color
    # ------------------------------------------------------------------
    def test_targeted_enemy_preserves_original_color(self):
        """Targeted enemy tile color must equal the enemy's own .color attribute."""
        game, enemy = _setup_game_with_visible_enemy()

        game.target_list = [enemy]
        game.target_cursor = 0

        state = game.get_render_state()
        tile = state['map'][enemy.pos.y][enemy.pos.x]

        assert tile['color'] == enemy.color, (
            f"Expected tile['color'] == {enemy.color!r} (enemy's own color), "
            f"got {tile['color']!r}"
        )

    # ------------------------------------------------------------------
    # 4. Non-targeted visible enemy has no targeted flag
    # ------------------------------------------------------------------
    def test_non_targeted_enemy_has_no_targeted_flag(self):
        """A visible but non-targeted enemy's tile must NOT have targeted=True.

        The test first confirms the targeted enemy DOES have targeted=True (the
        new behavior), then confirms a non-targeted visible enemy does NOT.
        Because the current code never sets targeted=True on any tile, the
        first assertion fails — keeping this test in the red phase.
        """
        game, enemy = _setup_game_with_visible_enemy()

        # Add a second enemy and target only it, leaving the first untargeted.
        for x in range(16, 20):
            game.current_map.set_tile(10, x, TILE_FLOOR)
        second_enemy = Enemy.from_def(ROTTWEILER, Position(10, 19))
        game.current_map.enemies.append(second_enemy)
        game.current_map.reveal_around(10, 10)

        # Target the second enemy; the first (GRUNT) should be unaffected.
        game.target_list = [enemy, second_enemy]
        game.target_cursor = 1  # second_enemy is targeted

        state = game.get_render_state()

        # Pre-condition: the targeted tile must have targeted=True (new behavior).
        # This assertion fails against the current code (no targeted key exists),
        # anchoring this test firmly in the red phase.
        targeted_tile = state['map'][second_enemy.pos.y][second_enemy.pos.x]
        assert targeted_tile.get('targeted') is True, (
            f"Pre-condition failed: targeted enemy tile should have targeted=True "
            f"but got tile={targeted_tile!r}"
        )

        # The non-targeted enemy tile must not have targeted=True.
        untargeted_tile = state['map'][enemy.pos.y][enemy.pos.x]
        assert not untargeted_tile.get('targeted'), (
            f"Non-targeted enemy tile should not have targeted=True, "
            f"got tile={untargeted_tile!r}"
        )

    # ------------------------------------------------------------------
    # 5. No active target → no tile has targeted=True
    # ------------------------------------------------------------------
    def test_no_target_no_targeted_flag(self):
        """When target_cursor is -1, no tile in the map should have targeted=True.

        The test first confirms that when a target IS selected the targeted flag
        appears (new behavior), then confirms clearing the target removes it.
        Because the current code never sets targeted=True, the first assertion
        fails — keeping this test in the red phase.
        """
        game, enemy = _setup_game_with_visible_enemy()

        # Step 1: with a target selected, the targeted tile must have the flag.
        game.target_list = [enemy]
        game.target_cursor = 0
        state_with_target = game.get_render_state()
        tile_targeted = state_with_target['map'][enemy.pos.y][enemy.pos.x]
        assert tile_targeted.get('targeted') is True, (
            f"Pre-condition failed: targeted enemy tile should have targeted=True "
            f"but got tile={tile_targeted!r}"
        )

        # Step 2: after clearing the target, no tile should have targeted=True.
        game.target_list = []
        game.target_cursor = -1
        state_no_target = game.get_render_state()
        map_tiles = state_no_target['map']

        targeted_tiles = [
            (y, x)
            for y, row in enumerate(map_tiles)
            for x, tile in enumerate(row)
            if isinstance(tile, dict) and tile.get('targeted')
        ]

        assert targeted_tiles == [], (
            f"Expected no targeted tiles when target_cursor==-1, "
            f"but found targeted tiles at: {targeted_tiles}"
        )
