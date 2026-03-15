"""Regression tests for the Rotfish water-only constraint.

These tests cover two bugs:

Bug 1 - Spawning: _place_enemies() uses _random_floor_in_room() for all
enemies, including Rotfish which is water-only. Rotfish gets spawned on dry
floor tiles.

Bug 2 - Movement: _wander() and _move_toward_player() in ai.py check
avoids_water but have no requires_water guard. Rotfish with avoids_water=False
freely walks onto dry floor tiles.

All four tests below FAIL with the current codebase and must PASS after the
fix introduces EnemyDef.requires_water and the corresponding spawn / movement
guards.
"""

import random
import pytest

from quakelike.entity import Position
from quakelike.player import Player
from quakelike.enemies import Enemy, EnemyDef, ROTFISH
from quakelike.gamemap import GameMap, Room, _place_enemies
from quakelike.ai import update_enemy
from quakelike.constants import TILE_FLOOR, TILE_WATER, TILE_WALL


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def make_water_map():
    """Return a small GameMap that is mostly water with a walkable border.

    Layout (interior 5x5, indices 1-5):
      - All interior tiles are TILE_WATER
    This lets us verify Rotfish stays on water without any dry floor nearby.
    """
    gmap = GameMap()
    for y in range(1, gmap.height - 1):
        for x in range(1, gmap.width - 1):
            gmap.set_tile(y, x, TILE_WATER)
    return gmap


def make_mixed_map():
    """Return a GameMap with water tiles in one region and floor in another.

    Layout (a 10x10 walkable area at top-left of the interior):
      - Rows 1-9, cols 1-4  -> TILE_WATER (left half)
      - Rows 1-9, cols 5-9  -> TILE_FLOOR (right half)
    """
    gmap = GameMap()
    for y in range(1, 10):
        for x in range(1, 5):
            gmap.set_tile(y, x, TILE_WATER)
        for x in range(5, 10):
            gmap.set_tile(y, x, TILE_FLOOR)
    return gmap


# ---------------------------------------------------------------------------
# Test 1: EnemyDef.requires_water field exists on ROTFISH
# ---------------------------------------------------------------------------

class TestRotfishRequiresWaterField:
    """ROTFISH must carry a requires_water=True flag on its EnemyDef."""

    def test_rotfish_requires_water_field_exists(self):
        """EnemyDef must have a requires_water attribute."""
        assert hasattr(ROTFISH, 'requires_water'), (
            "EnemyDef has no 'requires_water' field — implement it."
        )

    def test_rotfish_requires_water_is_true(self):
        """ROTFISH.requires_water must be True."""
        # Pre-condition: field must exist first
        assert hasattr(ROTFISH, 'requires_water'), (
            "Pre-condition failed: EnemyDef has no 'requires_water' field."
        )
        assert ROTFISH.requires_water is True, (
            "ROTFISH.requires_water should be True but is "
            f"{ROTFISH.requires_water!r}."
        )

    def test_non_water_enemies_default_to_false(self):
        """Enemies that are not water-only must default requires_water=False."""
        from quakelike.enemies import GRUNT, ROTTWEILER, KNIGHT
        for enemy_def in (GRUNT, ROTTWEILER, KNIGHT):
            assert hasattr(enemy_def, 'requires_water'), (
                f"EnemyDef has no 'requires_water' field — implement it."
            )
            assert enemy_def.requires_water is False, (
                f"{enemy_def.name}.requires_water should be False."
            )


# ---------------------------------------------------------------------------
# Test 2: Rotfish cannot wander onto dry floor tiles
# ---------------------------------------------------------------------------

class TestRotfishDoesNotMoveToFloor:
    """While wandering, Rotfish must never land on a TILE_FLOOR tile."""

    def test_rotfish_never_wanders_onto_dry_floor(self):
        """Rotfish placed on water must stay on water tiles across 200 wander
        attempts, even when adjacent dry floor tiles are available."""
        gmap = make_mixed_map()

        # Place Rotfish on a water tile adjacent to dry floor
        rotfish = Enemy.from_def(ROTFISH, Position(5, 3))  # water tile (col 3)
        rotfish.alerted = False
        gmap.enemies.append(rotfish)

        # Player far away so enemy stays unalerted and wanders
        player = Player.create(Position(20, 60))

        rng = random.Random(0)
        for _ in range(200):
            update_enemy(rotfish, player, gmap, rng)
            tile = gmap.get_tile(rotfish.pos.y, rotfish.pos.x)
            assert tile == TILE_WATER, (
                f"Rotfish moved onto tile {tile!r} at "
                f"({rotfish.pos.y}, {rotfish.pos.x}) — requires_water "
                "constraint not enforced in _wander()."
            )


# ---------------------------------------------------------------------------
# Test 3: Rotfish cannot move toward player through dry floor
# ---------------------------------------------------------------------------

class TestRotfishDoesNotChaseAcrossFloor:
    """When alerted, Rotfish must never step onto a TILE_FLOOR tile."""

    def test_rotfish_does_not_cross_floor_when_chasing(self):
        """Rotfish alerted on water must not step onto floor even while
        chasing a player who is on the other side of a floor region."""
        gmap = make_mixed_map()

        # Rotfish starts on water (left side), player is on floor (right side)
        rotfish = Enemy.from_def(ROTFISH, Position(5, 2))
        rotfish.alerted = True
        gmap.enemies.append(rotfish)

        # Player is on dry floor, across the water/floor boundary
        player = Player.create(Position(5, 8))

        rng = random.Random(1)
        for _ in range(50):
            update_enemy(rotfish, player, gmap, rng)
            tile = gmap.get_tile(rotfish.pos.y, rotfish.pos.x)
            assert tile == TILE_WATER, (
                f"Rotfish stepped onto tile {tile!r} at "
                f"({rotfish.pos.y}, {rotfish.pos.x}) — requires_water "
                "constraint not enforced in _move_toward_player()."
            )


# ---------------------------------------------------------------------------
# Test 4: Rotfish CAN move between water tiles (constraint not over-applied)
# ---------------------------------------------------------------------------

class TestRotfishMovesWithinWater:
    """Rotfish must be able to move freely between TILE_WATER tiles."""

    def test_rotfish_can_move_between_water_tiles(self):
        """Rotfish placed on one water tile must be able to reach an adjacent
        water tile after enough wander iterations.

        This guards against an over-restrictive fix that freezes Rotfish
        entirely.
        """
        gmap = make_water_map()

        start = Position(10, 10)
        rotfish = Enemy.from_def(ROTFISH, start)
        rotfish.alerted = False
        gmap.enemies.append(rotfish)

        player = Player.create(Position(20, 60))  # far away, enemy wanders

        rng = random.Random(42)
        visited = set()
        visited.add((rotfish.pos.y, rotfish.pos.x))

        for _ in range(200):
            update_enemy(rotfish, player, gmap, rng)
            visited.add((rotfish.pos.y, rotfish.pos.x))

        assert len(visited) > 1, (
            "Rotfish never moved from its starting tile — the requires_water "
            "constraint is over-restricting movement on water tiles."
        )


# ---------------------------------------------------------------------------
# Test 5: Spawning — after _place_enemies, Rotfish is always on TILE_WATER
# ---------------------------------------------------------------------------

class TestRotfishSpawnsOnWater:
    """_place_enemies must place Rotfish on TILE_WATER tiles, not TILE_FLOOR.

    Strategy: build a map with one dry room and one all-water room, then force
    _place_enemies to always select ROTFISH by patching rng.choices.  This
    makes the test deterministic without relying on probabilistic enemy
    selection across many seeds.
    """

    def _build_map_with_floor_and_water_rooms(self) -> GameMap:
        """Construct a GameMap with two rooms: one dry, one all-water.

        Room 0 (dry)  : rows 2-7,  cols 2-12  — TILE_FLOOR interior
        Room 1 (water): rows 2-7,  cols 20-30 — TILE_WATER interior
        A floor corridor connects them at row 4.
        """
        gmap = GameMap(level=2)  # level 2 unlocks ROTFISH (min_map_level=2)

        # Room 0: dry floor interior (inner tiles only, border stays wall)
        room0 = Room(y=2, x=2, height=6, width=11)
        for y in range(room0.y, room0.y + room0.height):
            for x in range(room0.x, room0.x + room0.width):
                gmap.set_tile(y, x, TILE_FLOOR)

        # Room 1: water interior
        room1 = Room(y=2, x=20, height=6, width=11)
        for y in range(room1.y, room1.y + room1.height):
            for x in range(room1.x, room1.x + room1.width):
                gmap.set_tile(y, x, TILE_WATER)
        # Add a small strip of floor inside room1 so _random_floor_in_room
        # does NOT find anything there (we want to expose the bug that Rotfish
        # falls back to floor room).  No interior floor in room1.

        # Corridor connecting rooms
        for x in range(room0.x + room0.width, room1.x + 1):
            gmap.set_tile(4, x, TILE_FLOOR)

        gmap.rooms = [room0, room1]
        return gmap

    def test_rotfish_spawns_on_water_not_floor(self):
        """When ROTFISH is the chosen enemy, it must be placed on TILE_WATER.

        The fix will need to:
          1. Detect requires_water=True on the selected EnemyDef.
          2. Pick a water tile rather than calling _random_floor_in_room.

        Without the fix, _place_enemies only searches for TILE_FLOOR tiles and
        places Rotfish on dry floor even when water tiles are available.

        The mock forces exactly one ROTFISH placement attempt, directed to the
        floor room (room0), so that without the fix Rotfish ends up on floor.
        After the fix the code must seek out water tiles globally (or skip
        placement when no water is available in the assigned room) — either way
        the post-placement invariant asserts Rotfish is never on floor.
        """
        from unittest import mock

        gmap = self._build_map_with_floor_and_water_rooms()
        rng = random.Random(42)

        # Force enemy type selection to ROTFISH and room selection to room0
        # (the dry floor room).  Without the fix Rotfish is placed on floor.
        # After the fix the code must pick a water tile instead.
        with mock.patch.object(rng, 'choices', return_value=[ROTFISH]):
            with mock.patch.object(rng, 'choice', return_value=gmap.rooms[0]):
                _place_enemies(gmap, level=2, rooms=gmap.rooms, rng=rng)

        # Pre-condition: placement must have produced at least one enemy.
        assert len(gmap.enemies) > 0, (
            "No enemies were placed — the mock did not take effect or "
            "_place_enemies skipped all placement iterations. "
            "Check the mock targets for rng.choices and rng.choice."
        )

        for enemy in gmap.enemies:
            if enemy.name == 'Rotfish':
                tile = gmap.get_tile(enemy.pos.y, enemy.pos.x)
                assert tile == TILE_WATER, (
                    f"Rotfish spawned on tile {repr(tile)} at "
                    f"({enemy.pos.y}, {enemy.pos.x}) — "
                    "_place_enemies does not respect requires_water; "
                    "it placed Rotfish on a non-water tile."
                )
