"""Tests for the fast travel feature.

The first set of tests (cursor movement, cancellation, invalid destinations,
render state) covers the existing cursor-mode behaviour and should continue
to pass.

The second set (TestFastTravelTeleport and TestFastTravelAutopath) specifies
the NEW batch-travel behaviour that replaces round-trip step-by-step travel:

  1. Player enters FAST_TRAVEL cursor mode, selects a destination, presses
     '_' to confirm.
  2. The backend computes a BFS path from player to destination (through
     walkable explored tiles).
  3. ALL steps are executed at once server-side in one handle_input call.
  4. Environmental effects (lava damage) happen at the correct step.
  5. Travel is interrupted if a tile in the path has a living enemy.
  6. The final render state includes 'travel_frames': [[y1,x1], ...] with one
     entry per step actually taken.
  7. After confirming, game.travel_path == [] (all steps consumed).
  8. 'traveling' in render state is always False (travel completes server-side).
  9. Turn counter advances by N (number of steps actually taken).

Tests in TestFastTravelTeleport and TestFastTravelAutopath are expected to
FAIL against the current code (which still uses round-trip step-by-step travel)
and will pass once the batch-travel implementation is in place.
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

    The player is placed at (10, 10) with a 7x7 open floor area around them
    (rows 7-13, columns 7-13), all revealed.  The border of the map is always
    TILE_WALL so boundary tests work correctly.

    BFS paths within the carved area are valid: every tile in the 7x7 block
    is TILE_FLOOR and in the explored set.
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
        # Turn must not have advanced (failed confirm does not cost a turn)
        assert game.turn == initial_turn


# ---------------------------------------------------------------------------
# 4. Batch-travel (all steps executed server-side in one confirm)
#
# These tests specify the new intended behavior.  They currently FAIL because
# the implementation still uses round-trip step-by-step travel.  They will
# PASS once the batch-travel implementation is in place.
# ---------------------------------------------------------------------------

class TestFastTravelTeleport:
    def test_fast_travel_moves_player_to_destination_in_one_confirm(self):
        """Confirming fast travel to a 1-step-away destination moves player there
        in a single handle_input call.

        When the destination is adjacent (1 step), the path is exhausted
        immediately: player arrives at destination, state returns to PLAYING,
        traveling=False, and travel_frames has exactly 1 entry.
        """
        game = _make_game()
        # Destination tile (9, 10) is 1 step up — already carved and explored
        dest_y, dest_x = 9, 10
        assert game.current_map.is_walkable(dest_y, dest_x)
        assert (dest_y, dest_x) in game.current_map.explored

        game.handle_input('_')   # enter fast travel; cursor at (10, 10)
        assert game.state == GameState.FAST_TRAVEL
        # Move cursor one step up to (9, 10)
        game.handle_input('k')
        assert game.fast_travel_cursor == (dest_y, dest_x)
        # Confirm travel — single call executes the 1-step path immediately
        game.handle_input('_')

        assert game.state == GameState.PLAYING
        assert game.player.pos.y == dest_y
        assert game.player.pos.x == dest_x
        # Path is exhausted: traveling must be False
        render = game.get_render_state()
        assert render.get('traveling') is False
        # travel_frames must be a list with exactly 1 entry for the 1 step taken
        assert 'travel_frames' in render
        assert isinstance(render['travel_frames'], list)
        assert len(render['travel_frames']) == 1

    def test_fast_travel_to_same_tile_is_valid(self):
        """Confirming travel to the player's current tile is a valid no-op.

        Path length is 0 (player is already at destination).  One _end_turn()
        call is still expected so the turn counter advances by 1.  State
        returns to PLAYING, traveling is False, and travel_frames is empty
        or absent.
        """
        game = _make_game()
        py, px = game.player.pos.y, game.player.pos.x
        initial_turn = game.turn

        game.handle_input('_')
        assert game.state == GameState.FAST_TRAVEL
        # Cursor should be at player position; confirm immediately
        assert game.fast_travel_cursor == (py, px)
        game.handle_input('_')

        # Must be accepted (return to PLAYING)
        assert game.state == GameState.PLAYING
        # Player stays at same position
        assert game.player.pos.y == py
        assert game.player.pos.x == px
        # _end_turn() must have been called exactly once
        assert game.turn == initial_turn + 1
        # traveling must be False (no path to follow)
        render = game.get_render_state()
        assert render.get('traveling') is False
        # travel_frames is empty (zero steps taken) or absent
        frames = render.get('travel_frames', [])
        assert frames == []

    def test_fast_travel_ends_turn(self):
        """Batch travel to a 2-tile destination advances turn by 2 in one confirm.

        Destination is (8, 10), two steps up from player at (10, 10).

        One '_' press executes both steps at once: player moves to (8, 10),
        turn advances by 2, state is PLAYING, traveling is False, and
        travel_frames has 2 entries.
        """
        game = _make_game()
        # Destination two steps up from player — already carved and explored
        dest_y, dest_x = 8, 10
        assert game.current_map.is_walkable(dest_y, dest_x)
        assert (dest_y, dest_x) in game.current_map.explored

        initial_turn = game.turn

        game.handle_input('_')           # enter fast travel (no turn cost)
        assert game.state == GameState.FAST_TRAVEL
        game.handle_input('k')           # move cursor up to (9, 10)
        game.handle_input('k')           # move cursor up to (8, 10)
        assert game.fast_travel_cursor == (dest_y, dest_x)

        # Single confirm — all 2 steps executed at once
        game.handle_input('_')

        assert game.state == GameState.PLAYING
        assert game.player.pos.y == dest_y
        assert game.player.pos.x == dest_x
        # Turn advanced by 2 (one per step taken)
        assert game.turn == initial_turn + 2
        render = game.get_render_state()
        assert render.get('traveling') is False
        # travel_frames must have 2 entries (one per step)
        assert 'travel_frames' in render
        assert isinstance(render['travel_frames'], list)
        assert len(render['travel_frames']) == 2

    def test_fast_travel_applies_lava_damage(self):
        """Environmental lava damage is applied when player walks through lava.

        Lava tile at (10, 13) is 3 steps right of player at (10, 10).
        After a single '_' confirm, all 3 steps execute at once: the player
        ends up on the lava tile and has taken damage.
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

        # Single confirm — all 3 steps execute at once
        game.handle_input('_')

        assert game.state == GameState.PLAYING
        assert game.player.pos.y == lava_y
        assert game.player.pos.x == lava_x
        # Lava damage must have been applied on entering the lava tile
        assert game.player.health < initial_hp

    def test_fast_travel_to_lava_fatal_damage_causes_game_over(self):
        """Walking into lava via batch travel kills the player when HP is too low.

        Lava tile at (10, 13) is 3 steps away.  With only 5 HP, stepping onto
        lava deals 10 damage, killing the player.  The game must transition to
        GAME_OVER after the single '_' confirm.
        """
        game = Game()
        game.new_game(seed=42)
        game.current_map.enemies.clear()
        game.player.pos = Position(10, 10)
        # Carve a floor corridor from (10,10) to (10,13)
        for nx in range(10, 14):
            game.current_map.set_tile(10, nx, TILE_FLOOR)
        game.current_map.reveal_around(10, 10)

        lava_y, lava_x = 10, 13
        game.current_map.set_tile(lava_y, lava_x, TILE_LAVA)
        game.current_map.explored.add((lava_y, lava_x))
        game.player.biosuit_turns = 0
        game.player.health = 5  # Will die from 10 lava damage

        game.handle_input('_')   # Enter fast travel mode
        game.handle_input('l')   # Cursor right -> (10, 11)
        game.handle_input('l')   # Cursor right -> (10, 12)
        game.handle_input('l')   # Cursor right -> (10, 13) — lava
        assert game.fast_travel_cursor == (lava_y, lava_x)

        # Single confirm — all 3 steps execute at once; player reaches lava and dies
        game.handle_input('_')

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
        game.handle_input('_')  # attempt confirm

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
        game.handle_input('_')  # attempt confirm

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
        game.handle_input('_')  # attempt confirm

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


# ---------------------------------------------------------------------------
# 7. Autopath travel — batch behaviour tests
#
# All tests in this class are expected to FAIL against the current code
# (which uses round-trip step-by-step travel) and will pass once the
# batch-travel implementation is in place.
# ---------------------------------------------------------------------------

class TestFastTravelAutopath:
    def test_fast_travel_travel_path_empty_after_confirm(self):
        """After confirming travel to a 3-step destination, game.travel_path
        is empty (all steps consumed in the single handle_input call).

        Destination (10, 13) is 3 steps right of player at (10, 10).
        After the single '_' confirm, game.travel_path == [].
        """
        game = _make_game()
        dest_y, dest_x = 10, 13
        assert game.current_map.is_walkable(dest_y, dest_x)
        assert (dest_y, dest_x) in game.current_map.explored

        game.handle_input('_')   # enter fast travel
        game.handle_input('l')   # cursor -> (10, 11)
        game.handle_input('l')   # cursor -> (10, 12)
        game.handle_input('l')   # cursor -> (10, 13)
        assert game.fast_travel_cursor == (dest_y, dest_x)

        # Single confirm — all steps executed at once
        game.handle_input('_')

        assert game.state == GameState.PLAYING
        assert game.player.pos.y == dest_y
        assert game.player.pos.x == dest_x
        # travel_path must be empty — all steps were consumed
        assert hasattr(game, 'travel_path')
        assert game.travel_path == []

    def test_fast_travel_travel_frames_contains_all_steps(self):
        """After confirming a 3-step travel, get_render_state()['travel_frames']
        is a list with 3 entries (one per step taken).

        Destination (10, 13) is 3 steps right of player at (10, 10).
        All 3 steps are executed in one confirm; travel_frames captures each.
        """
        game = _make_game()
        dest_y, dest_x = 10, 13
        assert game.current_map.is_walkable(dest_y, dest_x)
        assert (dest_y, dest_x) in game.current_map.explored

        game.handle_input('_')   # enter fast travel
        game.handle_input('l')   # cursor -> (10, 11)
        game.handle_input('l')   # cursor -> (10, 12)
        game.handle_input('l')   # cursor -> (10, 13)
        assert game.fast_travel_cursor == (dest_y, dest_x)

        # Single confirm — all 3 steps executed at once
        game.handle_input('_')

        render = game.get_render_state()
        assert 'travel_frames' in render, (
            "'travel_frames' key must be present in render state after batch travel"
        )
        frames = render['travel_frames']
        assert isinstance(frames, list)
        assert len(frames) == 3, (
            f"Expected 3 travel_frames for a 3-step path, got {len(frames)}"
        )

    def test_fast_travel_completes_after_all_steps(self):
        """Traveling a 3-tile path with a single '_' press places player at
        destination, travel_path is empty, and traveling is False.
        """
        game = _make_game()
        dest_y, dest_x = 10, 13
        assert game.current_map.is_walkable(dest_y, dest_x)
        assert (dest_y, dest_x) in game.current_map.explored

        initial_turn = game.turn

        game.handle_input('_')   # enter fast travel
        game.handle_input('l')   # cursor -> (10, 11)
        game.handle_input('l')   # cursor -> (10, 12)
        game.handle_input('l')   # cursor -> (10, 13)

        # Single confirm executes all 3 steps at once
        game.handle_input('_')

        assert game.state == GameState.PLAYING
        assert game.player.pos.y == dest_y
        assert game.player.pos.x == dest_x
        # Turn advanced once per step (3 steps)
        assert game.turn == initial_turn + 3
        # Path exhausted
        render = game.get_render_state()
        assert render.get('traveling') is False
        assert hasattr(game, 'travel_path')
        assert game.travel_path == []

    def test_fast_travel_frames_contain_correct_positions(self):
        """The positions in travel_frames are the intermediate positions visited
        between start (exclusive) and destination (inclusive).

        Player at (10, 10), destination (10, 13) — 3 steps right.
        Expected frames: [[10, 11], [10, 12], [10, 13]].
        """
        game = _make_game()
        dest_y, dest_x = 10, 13
        assert game.current_map.is_walkable(dest_y, dest_x)
        assert (dest_y, dest_x) in game.current_map.explored

        game.handle_input('_')   # enter fast travel
        game.handle_input('l')   # cursor -> (10, 11)
        game.handle_input('l')   # cursor -> (10, 12)
        game.handle_input('l')   # cursor -> (10, 13)
        assert game.fast_travel_cursor == (dest_y, dest_x)

        # Single confirm — all steps executed at once
        game.handle_input('_')

        render = game.get_render_state()
        assert 'travel_frames' in render
        frames = render['travel_frames']
        # Frames: positions visited after each step (start excluded, end included)
        assert frames == [[10, 11], [10, 12], [10, 13]], (
            f"Expected [[10,11],[10,12],[10,13]], got {frames}"
        )

    def test_fast_travel_stops_when_enemy_blocks_next_step(self):
        """Travel is interrupted when a tile mid-path has a living enemy.

        Setup:
        - Player at (10, 10)
        - Destination at (10, 12) — 2 steps right
        - Enemy placed at (10, 11), which is step 1 of the path

        After the single '_' confirm:
        - Enemy at step 1 (10, 11) blocks immediately: player stays at (10, 10)
        - travel_frames is empty (zero steps taken)
        - travel_path is cleared
        - A message is logged about the interruption
        - State is PLAYING

        Alternatively, with enemy at step 2 (10, 12) and destination at (10, 13):
        - Player takes step 1 to (10, 11)
        - Enemy blocks step 2 at (10, 12): travel stops
        - travel_frames has 1 entry [[10, 11]]
        - player is at (10, 11)
        """
        game = _make_game()
        dest_y, dest_x = 10, 13
        assert game.current_map.is_walkable(dest_y, dest_x)
        assert (dest_y, dest_x) in game.current_map.explored

        # Place a living enemy on tile (10, 12) — step 2 of the path
        enemy_y, enemy_x = 10, 12
        enemy = Enemy.from_def(GRUNT, Position(enemy_y, enemy_x))
        game.current_map.enemies.append(enemy)

        game.handle_input('_')   # enter fast travel
        game.handle_input('l')   # cursor -> (10, 11)
        game.handle_input('l')   # cursor -> (10, 12)
        game.handle_input('l')   # cursor -> (10, 13)
        assert game.fast_travel_cursor == (dest_y, dest_x)

        msgs_before = len(game.message_log.get_all())

        # Single confirm — step 1 succeeds, step 2 blocked by enemy
        game.handle_input('_')

        assert game.state == GameState.PLAYING
        # Player moved to (10, 11) (step 1), then stopped at step 2's enemy
        assert game.player.pos.y == 10
        assert game.player.pos.x == 11
        # travel_path must be cleared
        assert hasattr(game, 'travel_path')
        assert game.travel_path == []
        # travel_frames must have exactly 1 entry for the 1 step taken
        render = game.get_render_state()
        assert 'travel_frames' in render
        assert len(render['travel_frames']) == 1
        # A message must have been logged about the interruption
        assert len(game.message_log.get_all()) > msgs_before

    def test_fast_travel_render_state_has_travel_frames_after_confirm(self):
        """After confirming batch travel, get_render_state() includes the
        'travel_frames' key (even for a 1-step path).
        """
        game = _make_game()
        dest_y, dest_x = 10, 11  # 1 step right
        assert game.current_map.is_walkable(dest_y, dest_x)
        assert (dest_y, dest_x) in game.current_map.explored

        game.handle_input('_')   # enter fast travel
        game.handle_input('l')   # cursor -> (10, 11)
        assert game.fast_travel_cursor == (dest_y, dest_x)

        # Single confirm
        game.handle_input('_')

        render = game.get_render_state()
        assert 'travel_frames' in render, (
            "'travel_frames' key must be present in render state after batch travel confirm"
        )

    def test_fast_travel_traveling_is_always_false(self):
        """'traveling' in render state is always False — travel completes
        server-side so the client never receives a mid-travel state.

        Verified both immediately after confirm and after a subsequent action.
        """
        game = _make_game()
        dest_y, dest_x = 10, 13
        assert game.current_map.is_walkable(dest_y, dest_x)
        assert (dest_y, dest_x) in game.current_map.explored

        game.handle_input('_')   # enter fast travel
        game.handle_input('l')
        game.handle_input('l')
        game.handle_input('l')
        assert game.fast_travel_cursor == (dest_y, dest_x)

        # Confirm all 3 steps at once
        game.handle_input('_')

        assert game.player.pos.y == dest_y
        assert game.player.pos.x == dest_x

        render = game.get_render_state()
        # 'traveling' must be False — travel is always complete before returning
        assert render.get('traveling') is False
