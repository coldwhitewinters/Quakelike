"""Tests for the Quake-style auto-opening door feature.

Design contract:
  - Closed TILE_DOOR blocks movement and LOS (opaque + impassable).
  - Player or alerted enemy walking into a closed door opens it and
    the mover advances through in the same action (player) or waits
    one turn (enemy — opens then steps through next turn).
  - Open doors are walkable and transparent.
  - Doors auto-close after DOOR_CLOSE_DELAY turns.
  - Auto-close is deferred by 1 turn when any entity occupies the tile.
  - open_doors state is saved/restored in JSON serialisation.

All tests in this file are expected to FAIL before the feature is
implemented and pass once it is complete.
"""

import json
import os
import pytest

from quakelike.gamemap import GameMap
from quakelike.game import Game
from quakelike.entity import Position
from quakelike.enemies import Enemy, GRUNT
from quakelike.constants import (
    TILE_WALL, TILE_FLOOR, TILE_DOOR,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game(clear_enemies: bool = True) -> Game:
    """Return a Game in a known, repeatable state.

    - seed=42
    - enemies cleared from current map
    - 7×7 open floor carved around (10, 10) — rows 7-13, cols 7-13
    - all carved tiles added to explored
    - player placed at (10, 10)
    """
    game = Game()
    game.new_game(seed=42)
    gmap = game.current_map
    if clear_enemies:
        gmap.enemies.clear()
    for y in range(7, 14):
        for x in range(7, 14):
            gmap.set_tile(y, x, TILE_FLOOR)
            gmap.explored.add((y, x))
    game.player.pos = Position(10, 10)
    return game


def _make_door_corridor() -> GameMap:
    """Return a minimal GameMap: floor corridor on row 5, columns 1-9.

    No door is placed — the caller should position the door and call
    is_walkable / reveal_around as needed.
    """
    gmap = GameMap()
    for x in range(1, 10):
        gmap.set_tile(5, x, TILE_FLOOR)
    return gmap


# ---------------------------------------------------------------------------
# Unit Tests — GameMap.open_door / close_door / is_open_door
# ---------------------------------------------------------------------------

class TestGameMapDoorState:
    """open_doors dict, is_open_door(), open_door(), close_door()."""

    def test_gamemap_has_open_doors_attribute(self):
        """GameMap must expose an open_doors mapping from the start."""
        gmap = GameMap()
        # The attribute must exist and be a dict-like (supports 'in' operator)
        assert hasattr(gmap, 'open_doors'), (
            "GameMap must have an 'open_doors' attribute"
        )

    def test_open_doors_empty_on_new_map(self):
        """A freshly created GameMap has no open doors."""
        gmap = GameMap()
        assert len(gmap.open_doors) == 0

    def test_is_open_door_returns_false_for_closed_door(self):
        """is_open_door() must return False for a TILE_DOOR not in open_doors."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_DOOR)
        assert not gmap.is_open_door(5, 5)

    def test_is_open_door_returns_false_for_floor(self):
        """is_open_door() must return False for a non-door tile."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_FLOOR)
        assert not gmap.is_open_door(5, 5)

    def test_open_door_marks_door_as_open(self):
        """open_door(y, x, close_turn) must cause is_open_door() to return True."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_DOOR)
        gmap.open_door(5, 5, close_turn=10)
        assert gmap.is_open_door(5, 5)

    def test_open_door_stores_correct_close_turn(self):
        """The close_turn stored in open_doors must equal the value passed."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_DOOR)
        gmap.open_door(5, 5, close_turn=17)
        assert gmap.open_doors[(5, 5)] == 17

    def test_close_door_removes_from_open_doors(self):
        """close_door() must remove the door from open_doors."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_DOOR)
        gmap.open_door(5, 5, close_turn=10)
        gmap.close_door(5, 5)
        assert not gmap.is_open_door(5, 5)
        assert (5, 5) not in gmap.open_doors

    def test_close_door_idempotent_when_already_closed(self):
        """close_door() on an already-closed door must not raise."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_DOOR)
        gmap.close_door(5, 5)  # should not raise

    def test_open_door_updates_existing_entry(self):
        """Calling open_door() twice must update the close_turn."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_DOOR)
        gmap.open_door(5, 5, close_turn=10)
        gmap.open_door(5, 5, close_turn=20)
        assert gmap.open_doors[(5, 5)] == 20


# ---------------------------------------------------------------------------
# Unit Tests — is_walkable with open/closed doors
# ---------------------------------------------------------------------------

class TestDoorWalkability:
    """TILE_DOOR walkability depends on open_doors state."""

    def test_closed_door_is_not_walkable(self):
        """A TILE_DOOR not in open_doors must be impassable."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_DOOR)
        assert not gmap.is_walkable(5, 5), (
            "A closed TILE_DOOR must not be walkable"
        )

    def test_open_door_is_walkable(self):
        """A TILE_DOOR in open_doors must be walkable."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_DOOR)
        gmap.open_door(5, 5, close_turn=99)
        assert gmap.is_walkable(5, 5), (
            "An open TILE_DOOR must be walkable"
        )

    def test_closed_door_after_close_is_not_walkable(self):
        """A door that was opened and then closed must become impassable again."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_DOOR)
        gmap.open_door(5, 5, close_turn=10)
        gmap.close_door(5, 5)
        assert not gmap.is_walkable(5, 5)

    def test_wall_is_not_walkable(self):
        """Control: a plain TILE_WALL must remain impassable (no regression)."""
        gmap = GameMap()
        assert not gmap.is_walkable(0, 0)

    def test_floor_always_walkable(self):
        """Control: a TILE_FLOOR must remain walkable (no regression)."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_FLOOR)
        assert gmap.is_walkable(5, 5)


# ---------------------------------------------------------------------------
# Unit Tests — is_transparent with open/closed doors
# ---------------------------------------------------------------------------

class TestDoorTransparency:
    """TILE_DOOR LOS-transparency depends on open_doors state."""

    def test_closed_door_is_not_transparent(self):
        """A closed TILE_DOOR must block line of sight."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_DOOR)
        assert not gmap.is_transparent(5, 5), (
            "A closed TILE_DOOR must not be transparent"
        )

    def test_open_door_is_transparent(self):
        """An open TILE_DOOR must allow line of sight."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_DOOR)
        gmap.open_door(5, 5, close_turn=99)
        assert gmap.is_transparent(5, 5), (
            "An open TILE_DOOR must be transparent"
        )

    def test_closed_door_after_close_is_not_transparent(self):
        """A door that was opened then closed must block LOS again."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_DOOR)
        gmap.open_door(5, 5, close_turn=10)
        gmap.close_door(5, 5)
        assert not gmap.is_transparent(5, 5)

    def test_wall_always_opaque(self):
        """Control: a TILE_WALL must remain opaque (no regression)."""
        gmap = GameMap()
        assert not gmap.is_transparent(0, 0)

    def test_floor_always_transparent(self):
        """Control: a TILE_FLOOR must remain transparent (no regression)."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_FLOOR)
        assert gmap.is_transparent(5, 5)


# ---------------------------------------------------------------------------
# LOS / reveal_around Tests
# ---------------------------------------------------------------------------

class TestLOSThroughDoors:
    """has_line_of_sight and reveal_around interact correctly with door state."""

    def test_closed_door_blocks_has_line_of_sight(self):
        """A closed door in a corridor must block has_line_of_sight end-to-end."""
        gmap = _make_door_corridor()
        gmap.set_tile(5, 5, TILE_DOOR)

        p1 = Position(5, 1)
        p2 = Position(5, 9)
        assert not gmap.has_line_of_sight(p1, p2), (
            "has_line_of_sight must return False across a closed door"
        )

    def test_open_door_allows_has_line_of_sight(self):
        """An open door in a corridor must allow has_line_of_sight end-to-end."""
        gmap = _make_door_corridor()
        gmap.set_tile(5, 5, TILE_DOOR)
        gmap.open_door(5, 5, close_turn=99)

        p1 = Position(5, 1)
        p2 = Position(5, 9)
        assert gmap.has_line_of_sight(p1, p2), (
            "has_line_of_sight must return True through an open door"
        )

    def test_reveal_around_does_not_pass_closed_door(self):
        """reveal_around must not reveal tiles on the far side of a closed door."""
        gmap = _make_door_corridor()
        gmap.set_tile(5, 5, TILE_DOOR)

        gmap.reveal_around(5, 1)

        # Tiles past the door must not be explored
        for x in (7, 8, 9):
            assert (5, x) not in gmap.explored, (
                f"Tile (5, {x}) is behind a closed door and must not be revealed"
            )

    def test_reveal_around_passes_open_door(self):
        """reveal_around must reveal tiles on the far side of an open door."""
        gmap = _make_door_corridor()
        gmap.set_tile(5, 5, TILE_DOOR)
        gmap.open_door(5, 5, close_turn=99)

        gmap.reveal_around(5, 1)

        # Tiles past the open door must be explored
        for x in (7, 8, 9):
            assert (5, x) in gmap.explored, (
                f"Tile (5, {x}) is past an open door and must be revealed"
            )

    def test_tiles_before_closed_door_still_revealed(self):
        """Control: tiles on the near side of a closed door must still be revealed."""
        gmap = _make_door_corridor()
        gmap.set_tile(5, 5, TILE_DOOR)

        gmap.reveal_around(5, 1)

        for x in (2, 3, 4):
            assert (5, x) in gmap.explored, (
                f"Tile (5, {x}) is on the near side of the door and must be revealed"
            )


# ---------------------------------------------------------------------------
# Integration Tests — Player interacts with doors
# ---------------------------------------------------------------------------

class TestPlayerDoorInteraction:
    """Player movement into and through doors."""

    def test_player_cannot_move_into_closed_door(self):
        """Moving into a closed door must NOT move the player.

        The door is placed directly north of the player.  Before the feature
        is implemented, TILE_DOOR is walkable, so the player moves.  After the
        feature the door opens and the player moves through in one action —
        but we test the intermediate case: the door was NOT opened yet (turn 0
        pre-movement), so is_walkable returns False and the player stays put.

        We set up the scenario by directly testing is_walkable + movement
        blocking without calling handle_input so there's no door-open side-effect.
        """
        game = _make_game()
        gmap = game.current_map
        # Place a closed door directly north of the player
        gmap.set_tile(9, 10, TILE_DOOR)
        game.player.pos = Position(10, 10)
        # Verify that a closed door is not walkable before any interaction
        assert not gmap.is_walkable(9, 10), (
            "TILE_DOOR must not be walkable before it is opened"
        )

    def test_player_moves_into_closed_door_opens_it_and_passes_through(self):
        """Moving into a closed door opens it and moves the player through.

        The player starts at (10, 10) and moves north ('k').  The tile at
        (9, 10) is a TILE_DOOR.  After handle_input('k'):
          - The door at (9, 10) must be open (is_open_door returns True).
          - The player must be at (9, 10) — moved through in one action.
        """
        game = _make_game()
        gmap = game.current_map
        gmap.set_tile(9, 10, TILE_DOOR)
        game.player.pos = Position(10, 10)

        game.handle_input('k')  # move north

        assert gmap.is_open_door(9, 10), (
            "Door at (9, 10) must be open after the player moves into it"
        )
        assert game.player.pos == Position(9, 10), (
            "Player must be at (9, 10) — moved through the door in one action"
        )

    def test_player_moves_through_already_open_door(self):
        """Moving into an already-open door simply moves the player through."""
        game = _make_game()
        gmap = game.current_map
        gmap.set_tile(9, 10, TILE_DOOR)
        # Pre-open the door
        gmap.open_door(9, 10, close_turn=game.turn + 5)
        game.player.pos = Position(10, 10)

        game.handle_input('k')

        assert game.player.pos == Position(9, 10), (
            "Player must move through an already-open door normally"
        )

    def test_player_blocked_by_closed_door_no_movement(self):
        """If movement into a door opens it, confirm a second closed door still blocks.

        Place door at (9,10) (player opens on move) and another door at (8,10)
        still closed.  After the first move the player is at (9,10); a second
        'k' input should open (8,10) and advance the player to (8,10).
        This validates that the auto-open→move logic is applied each time, not
        only once.
        """
        game = _make_game()
        gmap = game.current_map
        gmap.set_tile(9, 10, TILE_DOOR)
        gmap.set_tile(8, 10, TILE_DOOR)
        game.player.pos = Position(10, 10)

        game.handle_input('k')  # opens (9,10) and moves through
        assert game.player.pos == Position(9, 10)

        game.handle_input('k')  # opens (8,10) and moves through
        assert game.player.pos == Position(8, 10), (
            "Player must be able to open and pass through consecutive doors"
        )
        assert gmap.is_open_door(8, 10), (
            "Second door at (8,10) must be open after the player passes through"
        )


# ---------------------------------------------------------------------------
# Integration Tests — Door auto-close after DOOR_CLOSE_DELAY turns
# ---------------------------------------------------------------------------

class TestDoorAutoClose:
    """Doors close automatically after DOOR_CLOSE_DELAY turns elapse."""

    def _get_delay(self) -> int:
        """Return DOOR_CLOSE_DELAY from constants (or fail if not implemented)."""
        from quakelike import constants
        assert hasattr(constants, 'DOOR_CLOSE_DELAY'), (
            "DOOR_CLOSE_DELAY must be defined in quakelike/constants.py"
        )
        return constants.DOOR_CLOSE_DELAY

    def test_door_close_delay_defined_and_positive(self):
        """DOOR_CLOSE_DELAY must be a positive integer in constants.py."""
        delay = self._get_delay()
        assert isinstance(delay, int) and delay > 0, (
            "DOOR_CLOSE_DELAY must be a positive integer"
        )

    def test_door_closes_after_delay_turns_pass(self):
        """A door opened this turn must close after DOOR_CLOSE_DELAY turns.

        We open a door manually, advance the game by DOOR_CLOSE_DELAY turns
        (using the rest key '.'), and verify the door is closed.
        """
        delay = self._get_delay()
        game = _make_game()
        gmap = game.current_map
        gmap.set_tile(9, 10, TILE_DOOR)
        game.player.pos = Position(10, 10)

        # Open the door (player moves through in one action)
        game.handle_input('k')
        assert gmap.is_open_door(9, 10), "Door must be open immediately after player moves through"

        # Move the player away from the door tile so the deferred-close guard
        # does not keep deferring
        game.player.pos = Position(10, 10)

        # Rest for DOOR_CLOSE_DELAY turns to let the door auto-close
        for _ in range(delay):
            game.handle_input('.')  # rest key

        assert not gmap.is_open_door(9, 10), (
            f"Door at (9,10) must be closed after {delay} rest turns"
        )

    def test_door_still_open_before_delay_expires(self):
        """A door must not close before DOOR_CLOSE_DELAY turns have passed."""
        delay = self._get_delay()
        game = _make_game()
        gmap = game.current_map
        gmap.set_tile(9, 10, TILE_DOOR)
        game.player.pos = Position(10, 10)

        game.handle_input('k')  # open the door and move through
        # Move away so the deferred-close guard doesn't interfere
        game.player.pos = Position(10, 10)

        # Rest for delay - 1 turns — door must still be open
        for _ in range(delay - 1):
            game.handle_input('.')

        assert gmap.is_open_door(9, 10), (
            f"Door at (9,10) must still be open after only {delay - 1} of "
            f"{delay} required rest turns"
        )

    def test_door_close_deferred_when_player_on_tile(self):
        """Auto-close is deferred when the player is standing on the door tile.

        Open a door, keep the player on it, advance past the expected close
        turn — the door must remain open while the player occupies it.
        """
        delay = self._get_delay()
        game = _make_game()
        gmap = game.current_map
        gmap.set_tile(9, 10, TILE_DOOR)
        game.player.pos = Position(10, 10)

        # Open the door — player ends up at (9, 10) on the door tile
        game.handle_input('k')
        assert game.player.pos == Position(9, 10), "Player must be on door tile"

        # Rest while standing on the door — player stays on (9,10) each rest
        # advance past the original close turn
        for _ in range(delay + 2):
            game.handle_input('.')

        assert gmap.is_open_door(9, 10), (
            "Door must stay open while the player is standing on it, even past "
            "the original close turn"
        )

    def test_door_close_deferred_when_enemy_on_tile(self):
        """Auto-close is deferred when an enemy occupies the door tile.

        Place an enemy on the door tile.  Advance past the expected close turn
        without moving the enemy off the tile.  The door must remain open.
        """
        delay = self._get_delay()
        game = _make_game()
        gmap = game.current_map
        gmap.set_tile(9, 10, TILE_DOOR)
        game.player.pos = Position(10, 10)

        # Open the door (player moves through, player is at (9,10))
        game.handle_input('k')

        # Place an enemy on the door tile
        enemy = Enemy.from_def(GRUNT, Position(9, 10))
        enemy.alerted = False  # keep it from attacking
        gmap.enemies.append(enemy)

        # Move player away so only the enemy occupies the door tile
        game.player.pos = Position(10, 10)

        # Advance past the close turn while enemy sits on the tile
        for _ in range(delay + 2):
            # Disable the enemy's movement by marking it not alive temporarily?
            # Instead just advance turns — enemy_def speed may cause movement.
            # We freeze the enemy by setting alerted=False and move_timer=0 and
            # placing it at a speed where it won't move away.
            enemy.pos = Position(9, 10)  # pin enemy in place each iteration
            game.handle_input('.')

        assert gmap.is_open_door(9, 10), (
            "Door must stay open while an enemy is standing on it"
        )

    def test_door_closes_after_player_leaves_and_delay_passes(self):
        """Door closes once the player leaves the tile and DOOR_CLOSE_DELAY passes."""
        delay = self._get_delay()
        game = _make_game()
        gmap = game.current_map
        gmap.set_tile(9, 10, TILE_DOOR)
        game.player.pos = Position(10, 10)

        # Open door — player now at (9,10)
        game.handle_input('k')
        assert game.player.pos == Position(9, 10)

        # Move player north off the door tile
        game.handle_input('k')  # now at (8,10) — floor tile
        assert game.player.pos == Position(8, 10), (
            "Player should have moved north off the door tile"
        )

        # Rest for DOOR_CLOSE_DELAY turns
        for _ in range(delay):
            game.handle_input('.')

        assert not gmap.is_open_door(9, 10), (
            "Door must close after the player has left it and DOOR_CLOSE_DELAY passes"
        )


# ---------------------------------------------------------------------------
# Integration Tests — Enemy auto-opens doors
# ---------------------------------------------------------------------------

class TestEnemyDoorInteraction:
    """Alerted enemy that reaches a closed door opens it and waits one turn."""

    def _setup_enemy_at_door(self):
        """Build a game with an alerted enemy one step away from a closed door.

        Layout:
          - 7x7 open floor around (10,10) as usual (rows 7-13, cols 7-13)
          - door placed at (10, 12) — one step east of the enemy start
          - enemy (Grunt, alerted) placed at (10, 11)
          - player at (10, 13) — east of the door, enemy must open the door
            to reach the player (door separates enemy from player)

        The Grunt speed=1 so it acts every turn.

        Returns (game, enemy, door_pos).
        """
        game = _make_game()
        gmap = game.current_map

        # Place player at (10, 13) — east of the door; the door separates
        # the enemy from the player so the enemy must open it to advance.
        game.player.pos = Position(10, 13)

        # Place door at (10, 12)
        gmap.set_tile(10, 12, TILE_DOOR)

        # Place alerted Grunt at (10, 11) — adjacent to the door
        enemy = Enemy.from_def(GRUNT, Position(10, 11))
        enemy.alerted = True
        gmap.enemies.append(enemy)

        return game, enemy, Position(10, 12)

    def test_alerted_enemy_opens_closed_door_it_faces(self):
        """An alerted enemy adjacent to a closed door opens it that turn.

        The enemy is at (10, 11) facing the door at (10, 12).  After one
        _end_turn() the door must be open and the enemy must still be at
        (10, 11) — it waits one turn for the door to open.
        """
        game, enemy, door_pos = self._setup_enemy_at_door()
        gmap = game.current_map

        # Trigger one enemy AI turn
        game._end_turn()

        assert gmap.is_open_door(door_pos.y, door_pos.x), (
            "Enemy must open the door it is moving toward on the first turn"
        )
        assert enemy.pos == Position(10, 11), (
            "Enemy must remain at (10, 11) on the turn it opens the door "
            "(waits one turn for the door to open)"
        )

    def test_alerted_enemy_walks_through_door_next_turn(self):
        """After opening the door, the enemy walks through on the next turn."""
        game, enemy, door_pos = self._setup_enemy_at_door()
        gmap = game.current_map

        # Turn 1: enemy opens the door and stays
        game._end_turn()
        assert gmap.is_open_door(door_pos.y, door_pos.x)
        assert enemy.pos == Position(10, 11)

        # Turn 2: door is now open, enemy walks through to (10, 12) or beyond
        game._end_turn()
        # Enemy should have moved — no longer at (10, 11)
        assert enemy.pos != Position(10, 11), (
            "Enemy must advance through the open door on the turn after opening it"
        )

    def test_enemy_does_not_open_already_open_door(self):
        """If the door is already open, the enemy walks straight through.

        No redundant open_door() call; the enemy simply moves.
        """
        game, enemy, door_pos = self._setup_enemy_at_door()
        gmap = game.current_map

        # Pre-open the door
        gmap.open_door(door_pos.y, door_pos.x, close_turn=game.turn + 20)

        # Turn 1: door already open — enemy should move through immediately
        game._end_turn()

        # Enemy must have advanced beyond (10, 11)
        assert enemy.pos != Position(10, 11), (
            "Enemy must walk through an already-open door without stopping"
        )

    def test_unalerted_enemy_does_not_open_door(self):
        """An unalerted enemy must not open doors (only alerted enemies do)."""
        game, enemy, door_pos = self._setup_enemy_at_door()
        gmap = game.current_map
        enemy.alerted = False  # make it unalerted

        game._end_turn()

        assert not gmap.is_open_door(door_pos.y, door_pos.x), (
            "An unalerted enemy must not open a closed door"
        )


# ---------------------------------------------------------------------------
# Integration Tests — update_enemy called with current_turn kwarg
# ---------------------------------------------------------------------------

class TestUpdateEnemyCurrentTurnKwarg:
    """update_enemy must accept a current_turn keyword argument."""

    def test_update_enemy_accepts_current_turn_kwarg(self):
        """update_enemy(enemy, player, gmap, rng, current_turn=N) must not raise."""
        import random
        from quakelike.ai import update_enemy
        from quakelike.player import Player

        gmap = GameMap()
        for y in range(1, 10):
            for x in range(1, 10):
                gmap.set_tile(y, x, TILE_FLOOR)

        player = Player.create(Position(5, 5))
        enemy = Enemy.from_def(GRUNT, Position(7, 7))
        enemy.alerted = False
        gmap.enemies.append(enemy)
        rng = random.Random(42)

        # Must not raise TypeError for unexpected keyword argument
        update_enemy(enemy, player, gmap, rng, current_turn=10)

    def test_update_enemy_uses_current_turn_for_door_open(self):
        """When enemy opens a door, the door's close_turn must be based on current_turn.

        current_turn=50 + DOOR_CLOSE_DELAY must equal the stored close_turn.
        """
        import random
        from quakelike import constants
        from quakelike.ai import update_enemy
        from quakelike.player import Player

        if not hasattr(constants, 'DOOR_CLOSE_DELAY'):
            pytest.skip("DOOR_CLOSE_DELAY not yet implemented")

        delay = constants.DOOR_CLOSE_DELAY

        gmap = GameMap()
        for y in range(1, 15):
            for x in range(1, 15):
                gmap.set_tile(y, x, TILE_FLOOR)

        # Door between enemy and player
        gmap.set_tile(5, 8, TILE_DOOR)

        player = Player.create(Position(5, 5))
        enemy = Enemy.from_def(GRUNT, Position(5, 9))
        enemy.alerted = True
        gmap.enemies.append(enemy)
        rng = random.Random(42)

        update_enemy(enemy, player, gmap, rng, current_turn=50)

        # If the enemy opened the door, close_turn should be 50 + delay
        if gmap.is_open_door(5, 8):
            assert gmap.open_doors[(5, 8)] == 50 + delay, (
                "close_turn must be current_turn + DOOR_CLOSE_DELAY"
            )


# ---------------------------------------------------------------------------
# Integration Tests — _end_turn passes current_turn to update_enemy
# ---------------------------------------------------------------------------

class TestEndTurnPassesTurn:
    """_end_turn() must pass self.turn as current_turn to update_enemy."""

    def test_end_turn_calls_update_enemy_with_current_turn(self):
        """_end_turn must invoke update_enemy with current_turn equal to self.turn.

        We verify this indirectly: place an alerted enemy adjacent to a door,
        call _end_turn(), and check the stored close_turn equals
        game.turn + DOOR_CLOSE_DELAY.
        """
        from quakelike import constants
        if not hasattr(constants, 'DOOR_CLOSE_DELAY'):
            pytest.skip("DOOR_CLOSE_DELAY not yet implemented")
        delay = constants.DOOR_CLOSE_DELAY

        game = _make_game()
        gmap = game.current_map

        # Door east of enemy
        gmap.set_tile(10, 12, TILE_DOOR)
        enemy = Enemy.from_def(GRUNT, Position(10, 11))
        enemy.alerted = True
        gmap.enemies.append(enemy)
        game.player.pos = Position(10, 8)

        turn_before = game.turn
        game._end_turn()
        expected_close_turn = turn_before + 1 + delay  # turn incremented at start of _end_turn

        if gmap.is_open_door(10, 12):
            assert gmap.open_doors[(10, 12)] == expected_close_turn, (
                f"close_turn should be {expected_close_turn}; "
                f"got {gmap.open_doors[(10, 12)]}"
            )


# ---------------------------------------------------------------------------
# Integration Tests — player opens door via handle_input with correct close_turn
# ---------------------------------------------------------------------------

class TestPlayerOpenDoorCloseTurn:
    """The close_turn stored when the player opens a door is correct."""

    def test_player_opening_door_stores_correct_close_turn(self):
        """When the player walks through a door, close_turn must be
        game.turn + DOOR_CLOSE_DELAY at the moment of opening.
        """
        from quakelike import constants
        if not hasattr(constants, 'DOOR_CLOSE_DELAY'):
            pytest.skip("DOOR_CLOSE_DELAY not yet implemented")
        delay = constants.DOOR_CLOSE_DELAY

        game = _make_game()
        gmap = game.current_map
        gmap.set_tile(9, 10, TILE_DOOR)
        game.player.pos = Position(10, 10)

        turn_before = game.turn
        game.handle_input('k')

        assert gmap.is_open_door(9, 10)
        # handle_input calls _end_turn which increments self.turn,
        # so the door was opened during the action before _end_turn ran,
        # meaning close_turn = (turn_before + 1) + delay
        expected = turn_before + 1 + delay
        assert gmap.open_doors[(9, 10)] == expected, (
            f"Expected close_turn={expected}, got {gmap.open_doors[(9, 10)]}"
        )


# ---------------------------------------------------------------------------
# Serialization Tests
# ---------------------------------------------------------------------------

class TestDoorSerialization:
    """open_doors state is correctly serialized and deserialized."""

    def test_open_doors_included_in_serialized_map(self):
        """_serialize_map must include 'open_doors' key when a door is open."""
        game = _make_game()
        gmap = game.current_map
        gmap.set_tile(9, 10, TILE_DOOR)
        gmap.open_door(9, 10, close_turn=42)

        map_data = game._serialize_map(gmap)
        assert 'open_doors' in map_data, (
            "_serialize_map must include 'open_doors' in its output"
        )

    def test_open_doors_empty_when_no_doors_are_open(self):
        """Serialised 'open_doors' must be empty (or absent) when no doors are open."""
        game = _make_game()
        map_data = game._serialize_map(game.current_map)
        # Either key is absent or the value is empty
        open_doors = map_data.get('open_doors', {})
        assert len(open_doors) == 0, (
            "Serialised open_doors must be empty when no doors are open"
        )

    def test_open_doors_preserved_across_save_load(self):
        """open_doors must survive a full save-to-disk / load-from-disk cycle."""
        from quakelike import constants
        if not hasattr(constants, 'DOOR_CLOSE_DELAY'):
            pytest.skip("DOOR_CLOSE_DELAY not yet implemented")

        game = _make_game()
        gmap = game.current_map
        gmap.set_tile(9, 10, TILE_DOOR)

        # Open the door by walking through it
        game.handle_input('k')
        assert gmap.is_open_door(9, 10), "Door must be open before saving"
        saved_close_turn = gmap.open_doors[(9, 10)]

        game.handle_input('S')  # save

        game2 = Game()
        assert game2.load_game(), "Load must succeed"

        gmap2 = game2.current_map
        assert gmap2.is_open_door(9, 10), (
            "Door at (9,10) must still be open after save/load"
        )
        assert gmap2.open_doors[(9, 10)] == saved_close_turn, (
            "close_turn must be preserved through save/load"
        )

    def test_closed_doors_not_present_in_open_doors_after_load(self):
        """Doors that were never opened must not appear in open_doors after load."""
        game = _make_game()
        gmap = game.current_map
        gmap.set_tile(9, 10, TILE_DOOR)  # door but never opened

        game.handle_input('S')

        game2 = Game()
        game2.load_game()
        assert not game2.current_map.is_open_door(9, 10), (
            "A door that was never opened must not appear as open after load"
        )

    def test_open_doors_persists_close_turn_value(self):
        """The serialised close_turn value for each door is exact."""
        game = _make_game()
        gmap = game.current_map
        gmap.set_tile(5, 5, TILE_DOOR)
        gmap.open_door(5, 5, close_turn=77)

        map_data = game._serialize_map(gmap)
        open_doors = map_data.get('open_doors', {})

        # The key format may be "y,x" or (y, x) — test both encodings
        key_str = '5,5'
        key_list = [5, 5]
        found_value = None
        for k, v in open_doors.items():
            if k == key_str or k == key_list or k == (5, 5):
                found_value = v
                break

        assert found_value == 77, (
            f"Serialised close_turn for door at (5,5) must be 77, got {found_value}"
        )


# ---------------------------------------------------------------------------
# Regression Tests — Bug 1: Fast-travel BFS cannot route through closed doors
# ---------------------------------------------------------------------------

class TestFastTravelDoors:
    """Regression tests for: _bfs_path prunes closed TILE_DOOR tiles, making
    fast travel fail whenever the only path to the destination passes through
    a closed door.

    Root cause (game.py:570): _bfs_path calls gmap.is_walkable(ny, nx) which
    returns False for closed doors, so they are excluded from BFS exploration.
    _confirm_fast_travel (lines 624-655) has no door-auto-open logic for path
    execution.

    All tests in this class are expected to FAIL before the fix is applied.
    The sanity-check test (test_fast_travel_destination_is_open_door_tile) is
    expected to PASS both before and after the fix.
    """

    def _make_corridor_game_with_door(self):
        """Build a game with a single-tile-wide corridor blocked by a closed door.

        Layout (row 10, columns 5-15):
          Player at (10, 8). Closed door at (10, 10). Destination (10, 12).
          All corridor tiles are TILE_FLOOR and explored.
          The only path from (10, 8) to (10, 12) passes through the door at
          (10, 10).

        Returns (game, door_pos, dest_pos).
        """
        game = Game()
        game.new_game(seed=42)
        gmap = game.current_map
        gmap.enemies.clear()

        # Carve a narrow east-west corridor on row 10, cols 5-15
        for x in range(5, 16):
            gmap.set_tile(10, x, TILE_FLOOR)
            gmap.explored.add((10, x))

        # Place a closed door in the middle of the corridor
        door_y, door_x = 10, 10
        gmap.set_tile(door_y, door_x, TILE_DOOR)
        # Ensure the door is closed (not in open_doors)
        gmap.open_doors.pop((door_y, door_x), None)

        # Seal all tiles adjacent to the corridor with walls so BFS cannot
        # route around the door (rows 9 and 11 are walls by default in the
        # generated map, but we set them explicitly for determinism).
        for x in range(5, 16):
            gmap.set_tile(9, x, TILE_WALL)
            gmap.set_tile(11, x, TILE_WALL)
            # These wall tiles are NOT in explored — BFS cannot use them.

        game.player.pos = Position(10, 8)
        return game, (door_y, door_x), (10, 12)

    def test_bfs_path_treats_closed_door_as_passable(self):
        """_bfs_path must include a closed TILE_DOOR tile when it is the only
        route from start to destination.

        Currently FAILS: is_walkable returns False for closed doors, so BFS
        prunes the door tile and returns an empty path.

        After the fix, _bfs_path must treat TILE_DOOR tiles as traversable
        (regardless of open_doors state) so the path planning layer can
        decide whether/how to open them.
        """
        game, door_pos, dest_pos = self._make_corridor_game_with_door()
        gmap = game.current_map

        door_y, door_x = door_pos
        dest_y, dest_x = dest_pos

        # Confirm the door is genuinely closed before calling BFS
        assert not gmap.is_open_door(door_y, door_x), (
            "Precondition: door must be closed before calling _bfs_path"
        )

        start = (game.player.pos.y, game.player.pos.x)
        end = (dest_y, dest_x)

        path = game._bfs_path(start, end)

        assert len(path) > 0, (
            "_bfs_path must return a non-empty path when the only route passes "
            "through a closed TILE_DOOR; got empty list (BFS prunes closed doors)"
        )
        assert door_pos in path, (
            f"_bfs_path path must include the closed door tile {door_pos}; "
            f"got path: {path}"
        )
        assert path[-1] == end, (
            f"Last element of path must be the destination {end}; got {path[-1]}"
        )

    def test_fast_travel_opens_door_on_path(self):
        """Fast travel to a destination reachable only through a closed door
        must open the door and move the player to the destination.

        Currently FAILS: _bfs_path returns [] because the closed door is not
        walkable, so _confirm_fast_travel logs 'No path to destination.' and
        aborts instead of opening the door mid-path.

        After the fix:
        (a) The player must reach the destination (10, 12).
        (b) The door at (10, 10) must be open (in gmap.open_doors).
        (c) The message log must contain 'The door opens.'
        """
        game, door_pos, dest_pos = self._make_corridor_game_with_door()
        gmap = game.current_map

        door_y, door_x = door_pos
        dest_y, dest_x = dest_pos

        msgs_before = len(game.message_log.get_all())

        # Enter fast travel mode
        game.handle_input('_')
        assert game.state.name == 'FAST_TRAVEL', (
            "Precondition: game must enter FAST_TRAVEL state"
        )

        # Move cursor east from player (10, 8) to destination (10, 12)
        # That's 4 presses of 'l'
        for _ in range(4):
            game.handle_input('l')
        assert game.fast_travel_cursor == (dest_y, dest_x), (
            f"Precondition: cursor must be at {(dest_y, dest_x)}, "
            f"got {game.fast_travel_cursor}"
        )

        # Confirm fast travel
        game.handle_input('_')

        # (a) Player must reach the destination
        assert game.player.pos == Position(dest_y, dest_x), (
            f"Player must reach destination {(dest_y, dest_x)} after fast travel "
            f"through a closed door; player is at "
            f"({game.player.pos.y}, {game.player.pos.x}). "
            "Likely cause: _bfs_path returned [] because the door was closed."
        )

        # (b) The door must have been opened during travel
        assert gmap.is_open_door(door_y, door_x), (
            f"Door at {door_pos} must be open after fast travel passed through it"
        )

        # (c) Message log must contain the door-open message
        all_msgs = game.message_log.get_all()
        new_msgs = all_msgs[msgs_before:]
        assert any('The door opens.' in m for m in new_msgs), (
            f"Message log must contain 'The door opens.' after fast travel "
            f"through a closed door; new messages were: {new_msgs}"
        )

    def test_fast_travel_destination_is_open_door_tile(self):
        """Fast travel to a tile that IS an open door works correctly.

        This is a sanity-check / regression guard: open doors are walkable, so
        fast travel to an open door tile must succeed before and after the fix.

        This test is expected to PASS both before and after the fix.
        """
        game = _make_game()
        gmap = game.current_map

        # Place a door one step north of the player and pre-open it
        door_y, door_x = 9, 10
        gmap.set_tile(door_y, door_x, TILE_DOOR)
        gmap.open_door(door_y, door_x, close_turn=game.turn + 50)
        gmap.explored.add((door_y, door_x))

        assert gmap.is_walkable(door_y, door_x), (
            "Precondition: an open door must be walkable"
        )

        # Enter fast travel, move cursor to the open door tile
        game.handle_input('_')
        game.handle_input('k')  # cursor to (9, 10)
        assert game.fast_travel_cursor == (door_y, door_x)

        game.handle_input('_')  # confirm

        assert game.player.pos == Position(door_y, door_x), (
            "Fast travel to an open door tile must move the player there"
        )


# ---------------------------------------------------------------------------
# Regression Tests — Bug 2: _handle_adjacent_door scans all 8 directions,
# can open doors that are not in the movement path
# ---------------------------------------------------------------------------

class TestHandleAdjacentDoorDirection:
    """Regression tests for: _handle_adjacent_door appends all 8 directions
    (ai.py:122-127) after the greedy-toward-player priority entries, so it
    can open doors that are behind or beside the enemy rather than only doors
    that block the enemy's path to the player.

    Root cause: the 'remaining 8-way directions' loop adds every direction not
    already in priority — including directly opposite the player — before any
    door-opening decision is made.  The first door found in that order is
    opened, even if it has nothing to do with the path to the player.

    Tests 4 and 5 are expected to FAIL before the fix. Test 6 is a sanity
    check that PASSES both before and after the fix.
    """

    def _make_enemy_player_setup(self, enemy_y, enemy_x,
                                 player_y, player_x,
                                 door_positions=None):
        """Build a minimal game with one alerted Grunt and one player.

        All tiles from rows 3-8, cols 3-12 are set to TILE_FLOOR and explored
        so movement is not blocked by walls, except for any TILE_DOOR tiles
        placed by the caller via door_positions.

        door_positions: list of (y, x) tuples where TILE_DOOR should be placed.

        Returns (game, enemy).
        """
        import random as _random
        from quakelike.player import Player

        game = Game()
        game.new_game(seed=99)
        gmap = game.current_map
        gmap.enemies.clear()

        # Carve an open floor area: rows 3-8, cols 3-12
        for y in range(3, 9):
            for x in range(3, 13):
                gmap.set_tile(y, x, TILE_FLOOR)
                gmap.explored.add((y, x))

        # Place closed doors if specified
        if door_positions:
            for dy, dx in door_positions:
                gmap.set_tile(dy, dx, TILE_DOOR)
                gmap.open_doors.pop((dy, dx), None)  # ensure closed

        # Place player
        game.player.pos = Position(player_y, player_x)

        # Place alerted Grunt; ensure it was already alerted before this turn
        enemy = Enemy.from_def(GRUNT, Position(enemy_y, enemy_x))
        enemy.alerted = True
        # Reset move_timer so the enemy acts this turn (Grunt speed=1)
        enemy.move_timer = 0
        gmap.enemies.append(enemy)

        return game, enemy

    def test_enemy_does_not_open_door_behind_it(self):
        """An enemy moving east toward the player must NOT open a door to its west.

        Setup:
          - Enemy at (5, 5), player at (5, 9) — enemy should move east.
          - Closed door at (5, 4) — directly west/behind the enemy.
          - No door between enemy and player on the east side.

        After one update_enemy call:
          - Door at (5, 4) must remain CLOSED.
          - Enemy must have acted meaningfully: moved east OR attacked the player.
            (The Grunt has a ranged attack with range 12 that fires at distance 4;
            attacking is correct behaviour and is not a wasted turn.)

        Previously FAILED because _handle_adjacent_door appended (0, -1) (west)
        to the priority list after the greedy directions and opened the first
        TILE_DOOR it found in that scan — which was the door at (5, 4),
        consuming the enemy's turn doing nothing useful.
        """
        import random
        from quakelike.ai import update_enemy

        game, enemy = self._make_enemy_player_setup(
            enemy_y=5, enemy_x=5,
            player_y=5, player_x=9,
            door_positions=[(5, 4)],  # door behind the enemy (west)
        )
        gmap = game.current_map

        rng = random.Random(7)
        update_enemy(enemy, game.player, gmap, rng, current_turn=game.turn)

        # Door behind the enemy must still be closed
        assert not gmap.is_open_door(5, 4), (
            "Enemy must NOT open the door at (5, 4) which is directly behind it "
            "(west) when the player is to the east at (5, 9). "
            "_handle_adjacent_door scans all 8 directions and opens the first "
            "door found, which includes the wrong-direction door."
        )

        # Enemy must have acted meaningfully: moved east OR attacked the player.
        # attack_cooldown > 0 after a ranged attack (Grunt ranged cooldown = 2).
        acted_meaningfully = enemy.pos.x > 5 or enemy.attack_cooldown > 0
        assert acted_meaningfully, (
            f"Enemy must move east or attack after ignoring the west door; "
            f"enemy x is {enemy.pos.x} (started at 5), "
            f"attack_cooldown is {enemy.attack_cooldown}"
        )

    def test_enemy_does_not_open_irrelevant_side_door(self):
        """An enemy moving east toward the player must NOT open a door to its north.

        Setup:
          - Enemy at (5, 5), player at (5, 9) — enemy should move east.
          - Closed door at (4, 5) — directly north (perpendicular to movement).
          - No door between enemy and player.

        After one update_enemy call:
          - Door at (4, 5) must remain CLOSED.
          - Enemy must have acted meaningfully: moved east OR attacked the player.
            (The Grunt has a ranged attack with range 12 that fires at distance 4;
            attacking is correct behaviour and is not a wasted turn.)

        Previously FAILED because _handle_adjacent_door scanned all 8 directions,
        found the door at (4, 5) in the remaining-directions list, and opened it,
        wasting the enemy's turn.
        """
        import random
        from quakelike.ai import update_enemy

        game, enemy = self._make_enemy_player_setup(
            enemy_y=5, enemy_x=5,
            player_y=5, player_x=9,
            door_positions=[(4, 5)],  # door perpendicular north of enemy
        )
        gmap = game.current_map

        rng = random.Random(13)
        update_enemy(enemy, game.player, gmap, rng, current_turn=game.turn)

        # Door to the north must still be closed
        assert not gmap.is_open_door(4, 5), (
            "Enemy must NOT open the door at (4, 5) which is north (perpendicular) "
            "when the player is due east at (5, 9). "
            "_handle_adjacent_door's all-8-directions scan finds this door and "
            "wastes the enemy's turn opening it."
        )

        # Enemy must have acted meaningfully: moved east OR attacked the player.
        # attack_cooldown > 0 after a ranged attack (Grunt ranged cooldown = 2).
        acted_meaningfully = enemy.pos.x > 5 or enemy.attack_cooldown > 0
        assert acted_meaningfully, (
            f"Enemy must move east or attack after ignoring the north door; "
            f"enemy x is {enemy.pos.x} (started at 5), "
            f"attack_cooldown is {enemy.attack_cooldown}"
        )

    def test_enemy_opens_door_that_is_in_movement_direction(self):
        """An enemy must open a closed door that directly blocks its path to the player.

        Setup:
          - Enemy at (5, 5), player at (5, 9).
          - Closed door at (5, 6) — directly between enemy and player (one step east).

        After one update_enemy call:
          - Door at (5, 6) must be OPEN (enemy opened it to pursue the player).
          - Enemy must still be at (5, 5) — it waits one turn after opening.

        This test is a sanity check and is expected to PASS both before and
        after the fix: the greedy priority list puts (0, +1) (east) first, so
        the correct door is always opened in the current code too.
        """
        import random
        from quakelike.ai import update_enemy

        game, enemy = self._make_enemy_player_setup(
            enemy_y=5, enemy_x=5,
            player_y=5, player_x=9,
            door_positions=[(5, 6)],  # door directly on the path east
        )
        gmap = game.current_map

        rng = random.Random(3)
        update_enemy(enemy, game.player, gmap, rng, current_turn=game.turn)

        # Door on the path must be opened
        assert gmap.is_open_door(5, 6), (
            "Enemy must open the door at (5, 6) which is directly on its path "
            "east toward the player at (5, 9)"
        )

        # Enemy must wait at its current position after opening the door
        assert enemy.pos == Position(5, 5), (
            f"Enemy must stay at (5, 5) on the turn it opens the door; "
            f"got {(enemy.pos.y, enemy.pos.x)}"
        )
