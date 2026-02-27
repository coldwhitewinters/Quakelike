"""Regression tests for two confirmed LOS bugs.

Bug 1: Closed doors are transparent to LOS (gamemap.py)
  - `is_transparent()` only blocks TILE_WALL; TILE_DOOR passes through.
  - `_has_los()` only checks `== TILE_WALL`, so doors never block reveal_around
    or has_line_of_sight.

Bug 2: Enemies are rendered based on explored status, not current LOS (game.py)
  - The enemy rendering loop checks `(y, x) in gmap.explored` instead of
    testing whether the player currently has line of sight to the enemy.
  - Once a tile is explored, the enemy on it is always rendered even when
    walls now block LOS.

Each test in this file is expected to FAIL against the current (unfixed) code
and will pass once the corresponding bug is fixed.
"""

import pytest
from quakelike.gamemap import GameMap
from quakelike.game import Game, GameState
from quakelike.entity import Position
from quakelike.enemies import Enemy, GRUNT
from quakelike.constants import (
    TILE_WALL, TILE_FLOOR, TILE_DOOR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_corridor_map() -> GameMap:
    """Return a GameMap with a horizontal corridor on row 5, columns 1-9.

    All other tiles remain TILE_WALL (the default).  The caller is responsible
    for placing the door and calling reveal_around / has_line_of_sight.
    """
    gmap = GameMap()
    for x in range(1, 10):
        gmap.set_tile(5, x, TILE_FLOOR)
    return gmap


def _make_game_with_walled_rooms() -> tuple:
    """Set up a Game with two rooms separated by walls and a door between them.

    Layout (rows 2-12, cols 2-22):

      Room A (player): rows 3-7, cols 3-9   (all TILE_FLOOR, fully explored)
      Wall column at x=10 (entire height range)
      Door at (5, 10)
      Room B (enemy): rows 3-7, cols 11-17  (all TILE_FLOOR, fully explored)

    The player is placed at (5, 5) inside Room A.
    The enemy (Grunt) is placed at (5, 15) inside Room B.
    The door at (5, 10) connects the two rooms, but with the door tile present
    the Bresenham LOS from (5,5) to (5,15) passes through (5,10) which is a
    TILE_DOOR — once the bug is fixed this will block LOS.

    Both rooms are added to gmap.explored so the enemy tile is in the explored
    set (reproducing the condition that triggers Bug 2).

    Returns (game, enemy) so tests can inspect the enemy and render state.
    """
    game = Game()
    game.new_game(seed=42)

    gmap = game.current_map
    # Clear procedurally-placed enemies so we control the population exactly
    gmap.enemies.clear()

    # Carve Room A: rows 3-7, cols 3-9
    for y in range(3, 8):
        for x in range(3, 10):
            gmap.set_tile(y, x, TILE_FLOOR)

    # Wall column at x=10 for the full corridor height (rows 2-8)
    for y in range(2, 9):
        gmap.set_tile(y, 10, TILE_WALL)

    # Place door at (5, 10) — the only opening between the two rooms
    gmap.set_tile(5, 10, TILE_DOOR)

    # Carve Room B: rows 3-7, cols 11-17
    for y in range(3, 8):
        for x in range(11, 18):
            gmap.set_tile(y, x, TILE_FLOOR)

    # Mark all carved tiles as explored (simulates the player having visited
    # both rooms previously — this is the condition that triggers Bug 2)
    for y in range(3, 8):
        for x in range(3, 18):
            gmap.explored.add((y, x))
    gmap.explored.add((5, 10))  # door tile itself

    # Place player in Room A (no LOS to Room B through the closed door once fixed)
    game.player.pos = Position(5, 5)

    # Place a Grunt in Room B
    enemy = Enemy.from_def(GRUNT, Position(5, 15))
    gmap.enemies.append(enemy)

    return game, enemy


# ---------------------------------------------------------------------------
# Bug 1a: has_line_of_sight must return False through a closed door
# ---------------------------------------------------------------------------

class TestDoorBlocksHasLineOfSight:
    def test_door_blocks_los_between_two_floor_tiles(self):
        """A closed door in the middle of a corridor must block has_line_of_sight.

        The corridor runs from (5,1) to (5,9).  A door is placed at (5,5).
        With correct LOS logic the door is opaque, so has_line_of_sight from
        (5,1) to (5,9) must return False.

        Currently fails because _has_los only checks for TILE_WALL, treating
        TILE_DOOR as fully transparent.
        """
        gmap = _make_corridor_map()
        # Place a door at the midpoint of the corridor
        gmap.set_tile(5, 5, TILE_DOOR)

        p1 = Position(5, 1)
        p2 = Position(5, 9)

        # A door should block line of sight — this fails with the current bug
        assert not gmap.has_line_of_sight(p1, p2), (
            "has_line_of_sight should return False when a closed door "
            "lies on the Bresenham path between the two positions"
        )

    def test_los_is_clear_on_same_side_of_door(self):
        """Tiles on the same side of a door as the viewer must still have LOS.

        This is a control assertion: the door at (5,5) must not block sight
        to (5,3), which is on the same side (no door between them).
        """
        gmap = _make_corridor_map()
        gmap.set_tile(5, 5, TILE_DOOR)

        p1 = Position(5, 1)
        p_same_side = Position(5, 3)

        assert gmap.has_line_of_sight(p1, p_same_side), (
            "Tiles on the same side of the door as the viewer should still "
            "have clear line of sight"
        )


# ---------------------------------------------------------------------------
# Bug 1b: reveal_around must not reveal tiles behind a closed door
# ---------------------------------------------------------------------------

class TestDoorBlocksRevealAround:
    def test_tiles_past_door_not_revealed(self):
        """reveal_around from (5,1) must not explore tiles past the door at (5,5).

        The corridor runs from (5,1) to (5,9).  A door is placed at (5,5).
        After calling reveal_around(5, 1) the tiles on the far side of the door
        — (5,7), (5,8), (5,9) — must NOT be in gmap.explored.

        Currently fails because _has_los treats TILE_DOOR as transparent.
        """
        gmap = _make_corridor_map()
        gmap.set_tile(5, 5, TILE_DOOR)

        gmap.reveal_around(5, 1)

        for x in (7, 8, 9):
            assert (5, x) not in gmap.explored, (
                f"Tile (5, {x}) is behind the closed door and must NOT be "
                f"revealed by reveal_around, but it is in gmap.explored"
            )

    def test_tiles_before_door_are_revealed(self):
        """reveal_around from (5,1) must still explore tiles on the near side.

        Tiles (5,2), (5,3), (5,4) are between the player and the door and have
        clear LOS — they should be revealed regardless of the door fix.
        """
        gmap = _make_corridor_map()
        gmap.set_tile(5, 5, TILE_DOOR)

        gmap.reveal_around(5, 1)

        for x in (2, 3, 4):
            assert (5, x) in gmap.explored, (
                f"Tile (5, {x}) is on the near side of the door and must be "
                f"revealed by reveal_around"
            )


# ---------------------------------------------------------------------------
# Bug 2: Enemy behind walls must not appear in get_render_state
# ---------------------------------------------------------------------------

class TestEnemyNotRenderedWithoutLOS:
    def test_enemy_char_absent_from_render_map_when_behind_wall(self):
        """An enemy in an explored-but-walled-off room must not appear on the render map.

        Setup: player at (5,5) in Room A; Grunt at (5,15) in Room B.  A wall
        column at x=10 separates the rooms, with a closed door at (5,10).
        Both rooms are marked as explored, so (5,15) is in gmap.explored.

        With the current bug the enemy's char ('g' for Grunt) appears at (5,15)
        in the render map because the code only checks explored status.

        Once Bug 2 is fixed the check will use current LOS instead, and the
        door (Bug 1 also fixed) blocks sight, so the enemy must be hidden.

        NOTE: this test depends on Bug 1 also being fixed (door blocks LOS).
        If only Bug 2 is fixed but Bug 1 is not, the LOS call will still return
        True through the door and the enemy will still be rendered.
        """
        game, enemy = _make_game_with_walled_rooms()

        state = game.get_render_state()
        assert 'map' in state, "get_render_state() must include a 'map' key"

        render_map = state['map']
        enemy_y, enemy_x = enemy.pos.y, enemy.pos.x
        cell = render_map[enemy_y][enemy_x]

        assert cell['char'] != enemy.char, (
            f"Enemy '{enemy.char}' at ({enemy_y},{enemy_x}) appears in the "
            f"render map even though a closed door blocks LOS from the player "
            f"at (5,5).  The enemy should be hidden when LOS is blocked."
        )

    def test_enemy_char_visible_when_player_has_los(self):
        """An enemy in the same open room as the player must appear in the render map.

        Control test: if there are no walls between the player and the enemy the
        enemy must still be rendered.  This must pass both before and after the fix.
        """
        game = Game()
        game.new_game(seed=42)

        gmap = game.current_map
        gmap.enemies.clear()

        # Carve an open room: rows 3-7, cols 3-17 — no walls between player and enemy
        for y in range(3, 8):
            for x in range(3, 18):
                gmap.set_tile(y, x, TILE_FLOOR)
                gmap.explored.add((y, x))

        game.player.pos = Position(5, 5)

        enemy = Enemy.from_def(GRUNT, Position(5, 15))
        gmap.enemies.append(enemy)

        state = game.get_render_state()
        render_map = state['map']
        cell = render_map[5][15]

        assert cell['char'] == enemy.char, (
            f"Enemy '{enemy.char}' at (5,15) should be visible in the render "
            f"map when no walls separate it from the player"
        )
