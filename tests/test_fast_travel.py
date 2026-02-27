"""Tests for the fast travel feature.

The first set of tests (cursor movement, cancellation, invalid destinations,
render state) covers the existing cursor-mode behaviour and should continue
to pass.

The second set (TestFastTravelTeleport and TestFastTravelAutopath) specifies
the NEW step-by-step autopath behaviour that replaces instant teleportation:

  1. Player enters FAST_TRAVEL cursor mode, selects a destination, presses
     '_' to confirm.
  2. The backend computes a BFS path from player to destination (through
     walkable explored tiles).
  3. The player is moved ONE step along the path.  Enemy AI runs (_end_turn).
  4. The remaining path is stored in Game.travel_path: list[tuple[int, int]].
  5. While travel_path is non-empty and the player presses '_' in PLAYING
     state, the player advances another step.
  6. Travel completes when the destination is reached (path exhausted).
  7. Environmental effects (lava damage) happen step-by-step.
  8. Pressing a movement key (h/j/k/l/y/u/b/n) while traveling cancels the
     travel and processes the movement normally.
  9. Travel is interrupted if the next tile in the path has a living enemy.

The render state gains a 'traveling' bool that is True when travel_path is
non-empty.

Tests in TestFastTravelTeleport and TestFastTravelAutopath are expected to
FAIL against the current code (which still uses instant teleportation) and
will pass once the step-by-step implementation is in place.
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
# 4. Step-by-step autopath travel (replaces instant teleportation)
#
# These tests specify the new intended behavior.  They currently FAIL because
# the implementation still uses instant teleportation.  They will PASS once
# the BFS autopath implementation is in place.
# ---------------------------------------------------------------------------

class TestFastTravelTeleport:
    def test_fast_travel_moves_player_one_step(self):
        """Confirming fast travel to a 1-step-away destination moves player there.

        When the destination is adjacent (1 step), the path is exhausted
        immediately: player arrives, state returns to PLAYING, traveling=False.
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
        # Confirm travel — one step path exhausted in one move
        game.handle_input('_')

        assert game.state == GameState.PLAYING
        assert game.player.pos.y == dest_y
        assert game.player.pos.x == dest_x
        # Path is exhausted: traveling must be False
        render = game.get_render_state()
        assert render.get('traveling') is False

    def test_fast_travel_to_same_tile_is_valid(self):
        """Confirming travel to the player's current tile is a valid no-op.

        Path length is 0 (player is already at destination).  One _end_turn()
        call is still expected so the turn counter advances by 1.  State
        returns to PLAYING and traveling is False.
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

    def test_fast_travel_ends_turn(self):
        """Step-by-step travel to a 2-tile destination advances turn twice.

        Destination is (8, 10), two steps up from player at (10, 10).

        Step 1: Press '_' to confirm — player moves to (9, 10), turn +1.
        Step 2: Press '_' again to continue — player moves to (8, 10), turn +2.
        State is PLAYING, traveling is False (path exhausted).
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

        # Confirm: first step — player moves to (9, 10), path has 1 step left
        game.handle_input('_')
        assert game.state == GameState.PLAYING
        assert game.player.pos.y == 9
        assert game.player.pos.x == 10
        assert game.turn == initial_turn + 1

        # Continue: second step — player moves to (8, 10), path exhausted
        game.handle_input('_')
        assert game.state == GameState.PLAYING
        assert game.player.pos.y == dest_y
        assert game.player.pos.x == dest_x
        assert game.turn == initial_turn + 2
        render = game.get_render_state()
        assert render.get('traveling') is False

    def test_fast_travel_applies_lava_damage(self):
        """Environmental lava damage is applied step-by-step as player walks.

        Lava tile at (10, 13) is 3 steps right of player at (10, 10).
        After confirm, the player is at (10, 11) — NOT the lava tile yet.
        After 2 more '_' presses (3 total steps), player is on the lava tile
        and has taken damage.
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

        # Confirm: step 1 — player moves to (10, 11), NOT lava yet
        game.handle_input('_')
        assert game.state == GameState.PLAYING
        # After step 1 the player must NOT be on the lava tile yet
        assert game.player.pos.x == 11, (
            "After first step of 3-step travel, player should be at (10, 11), "
            "not instantly teleported to lava"
        )
        assert game.player.health == initial_hp, (
            "No lava damage should occur before reaching the lava tile"
        )

        # Continue: step 2 — player moves to (10, 12), still not lava
        game.handle_input('_')
        assert game.player.pos.x == 12
        assert game.player.health == initial_hp

        # Continue: step 3 — player moves to (10, 13) — lava!
        game.handle_input('_')

        assert game.state == GameState.PLAYING
        assert game.player.pos.y == lava_y
        assert game.player.pos.x == lava_x
        # Lava damage must have been applied on entering the lava tile
        assert game.player.health < initial_hp

    def test_fast_travel_to_lava_fatal_damage_causes_game_over(self):
        """Walking into lava via autopath kills the player when HP is too low.

        Lava tile at (10, 13) is 3 steps away.  With only 5 HP, step 3
        (onto lava) deals 10 damage, killing the player.  The game must
        transition to GAME_OVER.

        Requires 3 '_' presses: confirm + 2 continues.

        After the first confirm (step 1), the player must be at (10, 11),
        still alive — proving instant teleport did NOT occur.
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

        # Confirm: step 1 — player should move to (10, 11), still alive
        game.handle_input('_')
        assert game.state == GameState.PLAYING, (
            "After step 1 of 3-step travel, game must be PLAYING (player not dead yet)"
        )
        assert game.player.pos.x == 11, (
            "After step 1, player should be at (10, 11), not instantly on lava"
        )

        # Continue: step 2 — move to (10, 12)
        game.handle_input('_')
        assert game.state == GameState.PLAYING

        # Continue: step 3 — move to (10, 13) lava, player dies
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
# 7. Autopath travel — new behaviour tests
#
# All tests in this class are expected to FAIL against the current code and
# will pass once the step-by-step BFS implementation is in place.
# ---------------------------------------------------------------------------

class TestFastTravelAutopath:
    def test_fast_travel_stores_remaining_path_after_first_step(self):
        """After confirming travel to a 3-step destination, game.travel_path
        contains the remaining steps (non-empty) after the first move.

        Destination (10, 13) is 3 steps right of player at (10, 10).
        After the first '_' confirm, the player is at (10, 11) and
        travel_path still has 2 entries remaining.
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

        # Confirm: first step
        game.handle_input('_')

        assert game.state == GameState.PLAYING
        assert game.player.pos.y == 10
        assert game.player.pos.x == 11
        # travel_path must be non-empty — 2 steps remain to (10, 13)
        assert hasattr(game, 'travel_path')
        assert len(game.travel_path) > 0

    def test_fast_travel_continues_on_underscore_in_playing_state(self):
        """Pressing '_' in PLAYING state while travel_path is non-empty
        advances the player one more step along the stored path.
        """
        game = _make_game()
        dest_y, dest_x = 10, 13
        assert game.current_map.is_walkable(dest_y, dest_x)
        assert (dest_y, dest_x) in game.current_map.explored

        game.handle_input('_')   # enter fast travel
        game.handle_input('l')   # cursor -> (10, 11)
        game.handle_input('l')   # cursor -> (10, 12)
        game.handle_input('l')   # cursor -> (10, 13)

        # Step 1: confirm — player moves to (10, 11), 2 steps remain
        game.handle_input('_')
        assert game.player.pos.x == 11

        # Step 2: continue via '_' in PLAYING state
        game.handle_input('_')
        assert game.state == GameState.PLAYING
        assert game.player.pos.y == 10
        assert game.player.pos.x == 12

    def test_fast_travel_completes_after_all_steps(self):
        """Traveling a 3-tile path with 3 '_' presses places player at
        destination and traveling is False when the path is exhausted.
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

        # 3 steps, 3 '_' presses
        game.handle_input('_')  # step 1 -> (10, 11)
        game.handle_input('_')  # step 2 -> (10, 12)
        game.handle_input('_')  # step 3 -> (10, 13)

        assert game.state == GameState.PLAYING
        assert game.player.pos.y == dest_y
        assert game.player.pos.x == dest_x
        # Turn advanced once per step
        assert game.turn == initial_turn + 3
        # Path exhausted
        render = game.get_render_state()
        assert render.get('traveling') is False
        assert hasattr(game, 'travel_path')
        assert game.travel_path == []

    def test_fast_travel_movement_key_cancels_travel(self):
        """Pressing a movement key (k = move up) while travel_path is
        non-empty cancels the autopath and processes the movement normally.

        After cancellation:
        - travel_path must be empty (or the attribute cleared)
        - The movement key moves the player as a normal step
        - The turn advances for the normal move
        """
        game = _make_game()
        dest_y, dest_x = 10, 13
        assert game.current_map.is_walkable(dest_y, dest_x)
        assert (dest_y, dest_x) in game.current_map.explored

        game.handle_input('_')   # enter fast travel
        game.handle_input('l')   # cursor -> (10, 11)
        game.handle_input('l')   # cursor -> (10, 12)
        game.handle_input('l')   # cursor -> (10, 13)

        # Step 1: confirm — player at (10, 11), 2 steps remain in travel_path
        game.handle_input('_')
        assert game.player.pos.x == 11
        assert hasattr(game, 'travel_path')
        assert len(game.travel_path) > 0

        turn_before_cancel = game.turn

        # Press movement key 'k' (move up) — should cancel travel and move up
        game.handle_input('k')

        assert game.state == GameState.PLAYING
        # travel_path must be cleared
        assert hasattr(game, 'travel_path')
        assert game.travel_path == []
        # Player moved up from (10, 11) to (9, 11) via normal movement
        assert game.player.pos.y == 9
        assert game.player.pos.x == 11
        # Turn advanced for the normal move
        assert game.turn == turn_before_cancel + 1

    def test_fast_travel_stops_when_enemy_blocks_next_step(self):
        """Travel is interrupted when the next tile in the path has a living enemy.

        Setup:
        - Player at (10, 10)
        - Destination at (10, 13) — 3 steps right
        - Enemy placed at (10, 12), which is step 2 of the path

        After step 1 (player moves to (10, 11)):
        - Pressing '_' to continue should detect the enemy at (10, 12) and
          stop travel: player stays at (10, 11), travel_path is cleared,
          a message is logged, state remains PLAYING.
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

        # Step 1: confirm — player moves to (10, 11); enemy not yet in the way
        game.handle_input('_')
        assert game.player.pos.x == 11

        msgs_before_stop = len(game.message_log.get_all())

        # Attempt step 2: enemy blocks (10, 12) — travel must stop
        game.handle_input('_')

        assert game.state == GameState.PLAYING
        # Player must NOT have moved into the enemy's tile
        assert game.player.pos.y == 10
        assert game.player.pos.x == 11
        # travel_path must be cleared
        assert hasattr(game, 'travel_path')
        assert game.travel_path == []
        # A message must have been logged about the interruption
        assert len(game.message_log.get_all()) > msgs_before_stop

    def test_render_state_has_traveling_true_when_path_nonempty(self):
        """After confirming travel to a 3-tile destination, get_render_state()
        returns 'traveling': True (because travel_path is non-empty).
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

        # First step: path should still have remaining steps
        game.handle_input('_')

        render = game.get_render_state()
        assert 'traveling' in render, "'traveling' key must be present in render state"
        assert render['traveling'] is True

    def test_render_state_has_traveling_false_when_path_empty(self):
        """After travel completes (all steps taken), get_render_state()
        returns 'traveling': False.
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

        # Complete all 3 steps
        game.handle_input('_')  # step 1
        game.handle_input('_')  # step 2
        game.handle_input('_')  # step 3

        assert game.player.pos.y == dest_y
        assert game.player.pos.x == dest_x

        render = game.get_render_state()
        assert 'traveling' in render, "'traveling' key must be present in render state"
        assert render['traveling'] is False
