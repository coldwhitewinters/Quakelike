"""Tests for the fast travel feature.

These tests are written TDD-style and are expected to FAIL until the feature
is implemented. The feature adds a FAST_TRAVEL GameState entered by pressing
'_' in PLAYING mode, allowing the player to move a cursor and teleport to any
explored, walkable, enemy-free tile.

Planned changes (not yet implemented):
  - quakelike/constants.py: KEY_FAST_TRAVEL = '_'
  - quakelike/game.py:
      - GameState.FAST_TRAVEL in the enum
      - fast_travel_cursor: tuple[int, int] field on Game
      - _enter_fast_travel() / _handle_fast_travel_input(key)
      - _handle_playing_input routes '_' to _enter_fast_travel()
      - get_render_state includes show_fast_travel and fast_travel_cursor
"""

import pytest
from quakelike.game import Game, GameState
from quakelike.entity import Position
from quakelike.items import create_item, RUNE
from quakelike.enemies import Enemy, GRUNT, ROTTWEILER
from quakelike.constants import TILE_FLOOR, TILE_LAVA, TILE_WALL, TILE_ENTRANCE


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game(seed: int = 42) -> Game:
    """Create a new game with enemies cleared and a known player position.

    The player is placed at (10, 10) with a 7x7 open floor area around them,
    all revealed.  The border of the map is always TILE_WALL so boundary tests
    work correctly.
    """
    game = Game()
    game.new_game(seed=seed)
    game.current_map.enemies.clear()
    # Carve a small open area around (10, 10) so cursor movement is possible
    for dy in range(-3, 4):
        for dx in range(-3, 4):
            ny, nx = 10 + dy, 10 + dx
            if 0 < ny < game.current_map.height - 1 and 0 < nx < game.current_map.width - 1:
                game.current_map.set_tile(ny, nx, TILE_FLOOR)
    # Place player on the known floor tile
    game.player.pos = Position(10, 10)
    # Reveal everything around the player so tiles are explored
    game.current_map.reveal_around(10, 10)
    return game


# ---------------------------------------------------------------------------
# 1. Entering fast travel state
# ---------------------------------------------------------------------------

class TestEnterFastTravel:
    def test_underscore_enters_fast_travel_state(self):
        """Pressing '_' in PLAYING state switches game to FAST_TRAVEL."""
        game = _make_game()
        assert game.state == GameState.PLAYING
        game.handle_input('_')
        assert game.state == GameState.FAST_TRAVEL

    def test_fast_travel_cursor_starts_at_player_position(self):
        """On entering FAST_TRAVEL the cursor is initialised at the player's tile."""
        game = _make_game()
        game.handle_input('_')
        py, px = game.player.pos.y, game.player.pos.x
        # fast_travel_cursor must exist and equal the player's position
        assert hasattr(game, 'fast_travel_cursor')
        assert game.fast_travel_cursor == (py, px)


# ---------------------------------------------------------------------------
# 2. Cursor movement
# ---------------------------------------------------------------------------

class TestFastTravelCursorMovement:
    def test_movement_moves_fast_travel_cursor(self):
        """Pressing 'k' (up) in FAST_TRAVEL state moves cursor y by -1."""
        game = _make_game()
        game.handle_input('_')  # enter fast travel
        # This assertion must pass before we check cursor movement
        assert game.state == GameState.FAST_TRAVEL, (
            "Game must be in FAST_TRAVEL state after pressing '_'"
        )
        cy, cx = game.fast_travel_cursor
        game.handle_input('k')  # move cursor up
        new_cy, new_cx = game.fast_travel_cursor
        assert new_cy == cy - 1
        assert new_cx == cx
        # State must remain FAST_TRAVEL
        assert game.state == GameState.FAST_TRAVEL

    def test_cursor_clamped_at_map_bounds(self):
        """Cursor cannot be moved outside map dimensions (clamped to valid range).

        This test drives the cursor to (0, 0) via the fast-travel cursor
        movement path (not by direct attribute assignment) and verifies the
        clamp behaviour.  The prerequisite is that FAST_TRAVEL state exists
        and cursor movement is routed through _handle_fast_travel_input.
        """
        game = _make_game()
        game.handle_input('_')
        # Prerequisite: must be in FAST_TRAVEL for this test to be meaningful.
        assert game.state == GameState.FAST_TRAVEL, (
            "Game must enter FAST_TRAVEL state after pressing '_'"
        )

        # Drive cursor to top-left by moving far enough up and left
        for _ in range(game.current_map.height):
            game.handle_input('k')  # up
        for _ in range(game.current_map.width):
            game.handle_input('h')  # left
        cy_min, cx_min = game.fast_travel_cursor

        # Cursor must still be within map bounds
        assert cy_min >= 0, "Cursor y should never go below 0"
        assert cx_min >= 0, "Cursor x should never go below 0"

        # Drive cursor to bottom-right
        for _ in range(game.current_map.height):
            game.handle_input('j')  # down
        for _ in range(game.current_map.width):
            game.handle_input('l')  # right
        cy_max, cx_max = game.fast_travel_cursor

        assert cy_max <= game.current_map.height - 1, "Cursor y should not exceed height-1"
        assert cx_max <= game.current_map.width - 1, "Cursor x should not exceed width-1"


# ---------------------------------------------------------------------------
# 3. Cancellation
# ---------------------------------------------------------------------------

class TestFastTravelCancellation:
    def test_escape_cancels_fast_travel(self):
        """Escape in FAST_TRAVEL returns to PLAYING without moving the player."""
        game = _make_game()
        original_pos = (game.player.pos.y, game.player.pos.x)
        game.handle_input('_')
        # Must have entered FAST_TRAVEL
        assert game.state == GameState.FAST_TRAVEL
        game.handle_input('Escape')
        assert game.state == GameState.PLAYING
        assert (game.player.pos.y, game.player.pos.x) == original_pos

    def test_underscore_confirms_on_invalid_tile_stays_in_fast_travel(self):
        """Pressing '_' while the cursor is on an invalid tile (explored wall)
        keeps the game in FAST_TRAVEL state and does not move the player.

        '_' is always a confirm action; Escape is the cancel path.  When the
        destination is invalid the teleport is rejected and FAST_TRAVEL mode
        is preserved so the player can reposition the cursor.
        """
        game = _make_game()
        original_pos = (game.player.pos.y, game.player.pos.x)

        # Place an explored wall three steps up — outside the carved floor area
        wall_y, wall_x = 7, 10
        game.current_map.set_tile(wall_y, wall_x, TILE_WALL)
        game.current_map.explored.add((wall_y, wall_x))

        game.handle_input('_')
        # Must have entered FAST_TRAVEL
        assert game.state == GameState.FAST_TRAVEL

        # Move cursor three steps up onto the wall tile
        game.handle_input('k')
        game.handle_input('k')
        game.handle_input('k')
        assert game.fast_travel_cursor == (wall_y, wall_x)

        # Attempting to confirm on the wall must be rejected
        initial_turn = game.turn
        game.handle_input('_')
        # State must remain FAST_TRAVEL (not PLAYING)
        assert game.state == GameState.FAST_TRAVEL
        # Player must not have moved
        assert (game.player.pos.y, game.player.pos.x) == original_pos
        # Turn must not have advanced (failed teleport does not cost a turn)
        assert game.turn == initial_turn


# ---------------------------------------------------------------------------
# 4. Successful teleport
# ---------------------------------------------------------------------------

class TestFastTravelTeleport:
    def test_fast_travel_teleports_player_to_cursor(self):
        """Confirming with '_' on a valid explored walkable tile moves the player."""
        game = _make_game()
        # Destination tile (9, 10) is already carved and explored by _make_game
        dest_y, dest_x = 9, 10
        assert game.current_map.is_walkable(dest_y, dest_x)
        assert (dest_y, dest_x) in game.current_map.explored

        game.handle_input('_')  # enter fast travel; cursor at (10, 10)
        assert game.state == GameState.FAST_TRAVEL
        # Move cursor one step up to (9, 10)
        game.handle_input('k')
        assert game.fast_travel_cursor == (dest_y, dest_x)
        # Confirm teleport
        game.handle_input('_')
        assert game.state == GameState.PLAYING
        assert game.player.pos.y == dest_y
        assert game.player.pos.x == dest_x

    def test_fast_travel_to_same_tile_is_valid(self):
        """Teleporting to the player's current tile is accepted (no-op move).

        Per spec: there is no restriction against the cursor being on the
        player's own tile; confirming there should succeed and return to PLAYING.
        The turn counter must advance to confirm _end_turn() was called.
        """
        game = _make_game()
        py, px = game.player.pos.y, game.player.pos.x
        initial_turn = game.turn

        game.handle_input('_')
        assert game.state == GameState.FAST_TRAVEL
        # Cursor should be at player position; confirm immediately
        assert game.fast_travel_cursor == (py, px)
        game.handle_input('_')
        # Teleport must be accepted
        assert game.state == GameState.PLAYING
        assert game.player.pos.y == py
        assert game.player.pos.x == px
        # _end_turn() must have been called
        assert game.turn == initial_turn + 1

    def test_fast_travel_ends_turn(self):
        """A successful fast travel teleport increments game.turn.

        The destination is two tiles up (row 8) so normal movement cannot
        reach it in a single key press — the turn increment must come from
        the fast travel path, not from a regular move.
        """
        game = _make_game()
        # Destination two steps up from player (8, 10) — not adjacent via one move
        dest_y, dest_x = 8, 10
        game.current_map.set_tile(dest_y, dest_x, TILE_FLOOR)
        game.current_map.explored.add((dest_y, dest_x))

        initial_turn = game.turn
        game.handle_input('_')           # enter fast travel (no turn)
        assert game.state == GameState.FAST_TRAVEL
        game.handle_input('k')           # move cursor up to (9, 10) — no turn
        game.handle_input('k')           # move cursor up to (8, 10) — no turn
        assert game.fast_travel_cursor == (dest_y, dest_x)
        game.handle_input('_')           # confirm teleport — costs one turn
        assert game.state == GameState.PLAYING
        assert game.player.pos.y == dest_y
        assert game.turn == initial_turn + 1

    def test_fast_travel_applies_lava_damage(self):
        """Teleporting to a TILE_LAVA tile without a biosuit deals damage.

        The lava tile is placed three steps to the right (10, 13) so it
        cannot be reached accidentally by a normal movement key.
        """
        game = _make_game()
        lava_y, lava_x = 10, 13
        game.current_map.set_tile(lava_y, lava_x, TILE_LAVA)
        game.current_map.explored.add((lava_y, lava_x))
        game.player.biosuit_turns = 0  # no protection

        initial_hp = game.player.health
        game.handle_input('_')            # enter fast travel
        assert game.state == GameState.FAST_TRAVEL
        game.handle_input('l')            # cursor right -> (10, 11)
        game.handle_input('l')            # cursor right -> (10, 12)
        game.handle_input('l')            # cursor right -> (10, 13) — lava
        assert game.fast_travel_cursor == (lava_y, lava_x)
        game.handle_input('_')            # confirm teleport to lava
        assert game.state == GameState.PLAYING
        assert game.player.pos.y == lava_y
        assert game.player.pos.x == lava_x
        assert game.player.health < initial_hp

    def test_fast_travel_to_lava_fatal_damage_causes_game_over(self):
        """Teleporting to lava when health is too low (5 HP) kills the player.

        Lava deals 10 damage on entry; with only 5 HP the player dies and the
        game must transition to GAME_OVER.
        """
        game = Game()
        game.new_game(seed=42)
        game.current_map.enemies.clear()
        game.player.pos = Position(10, 10)
        game.current_map.set_tile(10, 10, TILE_FLOOR)
        game.current_map.reveal_around(10, 10)

        lava_y, lava_x = 10, 13
        game.current_map.set_tile(lava_y, lava_x, TILE_LAVA)
        game.current_map.explored.add((lava_y, lava_x))
        game.player.biosuit_turns = 0
        game.player.health = 5  # Will die from 10 lava damage

        game.handle_input('_')   # Enter fast travel mode
        game.handle_input('l')   # Move cursor right -> (10, 11)
        game.handle_input('l')   # Move cursor right -> (10, 12)
        game.handle_input('l')   # Move cursor right -> (10, 13)
        game.handle_input('_')   # Confirm teleport to lava

        assert game.state == GameState.GAME_OVER


# ---------------------------------------------------------------------------
# 5. Invalid destinations (cursor stays in FAST_TRAVEL, message logged)
# ---------------------------------------------------------------------------

class TestFastTravelInvalidDestinations:
    def test_fast_travel_to_unexplored_tile_fails(self):
        """Confirming on an unexplored tile leaves state as FAST_TRAVEL and
        does not move the player; a message is added to the log."""
        game = _make_game()
        # Place an unexplored floor tile at (7, 10) — three steps up, so not
        # reachable via the pre-revealed area from _make_game
        unexplored_y, unexplored_x = 7, 10
        game.current_map.set_tile(unexplored_y, unexplored_x, TILE_FLOOR)
        game.current_map.explored.discard((unexplored_y, unexplored_x))

        original_pos = (game.player.pos.y, game.player.pos.x)
        msgs_before = len(game.message_log.get_all())

        game.handle_input('_')
        assert game.state == GameState.FAST_TRAVEL

        # Move cursor three steps up to (7, 10)
        game.handle_input('k')
        game.handle_input('k')
        game.handle_input('k')
        assert game.fast_travel_cursor == (unexplored_y, unexplored_x)
        game.handle_input('_')  # attempt teleport

        # Must remain in FAST_TRAVEL
        assert game.state == GameState.FAST_TRAVEL
        # Player must not have moved
        assert (game.player.pos.y, game.player.pos.x) == original_pos
        # A new message must have been logged
        assert len(game.message_log.get_all()) > msgs_before

    def test_fast_travel_to_wall_fails(self):
        """Confirming on a wall tile leaves state as FAST_TRAVEL and does not
        move the player; a message is logged."""
        game = _make_game()
        # Place a wall tile at (7, 10) — three steps up, outside the carved area
        wall_y, wall_x = 7, 10
        game.current_map.set_tile(wall_y, wall_x, TILE_WALL)
        game.current_map.explored.add((wall_y, wall_x))

        original_pos = (game.player.pos.y, game.player.pos.x)
        msgs_before = len(game.message_log.get_all())

        game.handle_input('_')
        assert game.state == GameState.FAST_TRAVEL

        game.handle_input('k')
        game.handle_input('k')
        game.handle_input('k')
        assert game.fast_travel_cursor == (wall_y, wall_x)
        game.handle_input('_')  # attempt teleport

        assert game.state == GameState.FAST_TRAVEL
        assert (game.player.pos.y, game.player.pos.x) == original_pos
        assert len(game.message_log.get_all()) > msgs_before

    def test_fast_travel_to_enemy_tile_fails(self):
        """Confirming on a tile occupied by a living enemy leaves state as
        FAST_TRAVEL and does not move the player; a message is logged."""
        game = _make_game()
        enemy_y, enemy_x = 9, 10
        game.current_map.set_tile(enemy_y, enemy_x, TILE_FLOOR)
        game.current_map.explored.add((enemy_y, enemy_x))
        # Place a living enemy at the destination
        enemy = Enemy.from_def(GRUNT, Position(enemy_y, enemy_x))
        game.current_map.enemies.append(enemy)

        original_pos = (game.player.pos.y, game.player.pos.x)
        msgs_before = len(game.message_log.get_all())

        game.handle_input('_')
        assert game.state == GameState.FAST_TRAVEL

        game.handle_input('k')  # cursor -> (9, 10)
        assert game.fast_travel_cursor == (enemy_y, enemy_x)
        game.handle_input('_')  # attempt teleport

        assert game.state == GameState.FAST_TRAVEL
        assert (game.player.pos.y, game.player.pos.x) == original_pos
        assert len(game.message_log.get_all()) > msgs_before


# ---------------------------------------------------------------------------
# 6. Render state
# ---------------------------------------------------------------------------

class TestFastTravelRenderState:
    def test_render_state_has_show_fast_travel_false_when_playing(self):
        """get_render_state() includes 'show_fast_travel': False during PLAYING."""
        game = _make_game()
        assert game.state == GameState.PLAYING
        state = game.get_render_state()
        assert 'show_fast_travel' in state
        assert state['show_fast_travel'] is False

    def test_render_state_has_show_fast_travel_true_when_in_mode(self):
        """get_render_state() includes 'show_fast_travel': True during FAST_TRAVEL."""
        game = _make_game()
        game.handle_input('_')
        assert game.state == GameState.FAST_TRAVEL
        state = game.get_render_state()
        assert 'show_fast_travel' in state
        assert state['show_fast_travel'] is True

    def test_render_state_has_fast_travel_cursor(self):
        """get_render_state() includes 'fast_travel_cursor' as [y, x] during
        FAST_TRAVEL mode, matching the current cursor position."""
        game = _make_game()
        game.handle_input('_')
        assert game.state == GameState.FAST_TRAVEL
        # Move cursor one step right so we can verify the value is dynamic
        game.handle_input('l')
        expected_y, expected_x = game.fast_travel_cursor
        state = game.get_render_state()
        assert 'fast_travel_cursor' in state
        assert state['fast_travel_cursor'] == [expected_y, expected_x]
