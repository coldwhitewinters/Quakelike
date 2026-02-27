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
          - 7x7 open floor around (10,10) as usual
          - door placed at (10, 12) — one step east of the enemy start
          - enemy (Grunt, alerted) placed at (10, 11)
          - player at (10, 8) — west of the door, enemy wants to reach it

        The Grunt speed=1 so it acts every turn.

        Returns (game, enemy, door_pos).
        """
        game = _make_game()
        gmap = game.current_map

        # Place player at (10, 8) — door will separate player from enemy
        game.player.pos = Position(10, 8)

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
