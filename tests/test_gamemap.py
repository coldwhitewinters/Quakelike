"""Tests for the game map module."""

import random
import pytest
from quakelike.entity import Position
from quakelike.gamemap import (
    GameMap, Room, generate_map, bresenham_line,
)
from quakelike.constants import (
    MAP_WIDTH, MAP_HEIGHT, NUM_MAPS,
    TILE_WALL, TILE_FLOOR, TILE_SLIPGATE_DOWN, TILE_SLIPGATE_UP,
    TILE_ENTRANCE, TILE_DOOR, TILE_WATER, TILE_LAVA,
)
from quakelike.items import create_item, AXE, SHOTGUN


class TestRoom:
    def test_creation(self):
        r = Room(5, 10, 4, 6)
        assert r.y == 5
        assert r.x == 10
        assert r.height == 4
        assert r.width == 6

    def test_center(self):
        r = Room(0, 0, 10, 10)
        assert r.center == Position(5, 5)

    def test_intersects(self):
        r1 = Room(0, 0, 5, 5)
        r2 = Room(3, 3, 5, 5)
        assert r1.intersects(r2)

    def test_no_intersect(self):
        r1 = Room(0, 0, 5, 5)
        r2 = Room(10, 10, 5, 5)
        assert not r1.intersects(r2)


class TestGameMap:
    def test_default_all_walls(self):
        gmap = GameMap()
        assert gmap.width == MAP_WIDTH
        assert gmap.height == MAP_HEIGHT
        assert gmap.get_tile(0, 0) == TILE_WALL

    def test_get_tile_out_of_bounds(self):
        gmap = GameMap()
        assert gmap.get_tile(-1, 0) == TILE_WALL
        assert gmap.get_tile(0, -1) == TILE_WALL
        assert gmap.get_tile(999, 0) == TILE_WALL

    def test_set_and_get_tile(self):
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_FLOOR)
        assert gmap.get_tile(5, 5) == TILE_FLOOR

    def test_walkable_tiles(self):
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_FLOOR)
        gmap.set_tile(6, 5, TILE_DOOR)
        gmap.set_tile(7, 5, TILE_SLIPGATE_DOWN)
        gmap.set_tile(8, 5, TILE_SLIPGATE_UP)
        gmap.set_tile(9, 5, TILE_ENTRANCE)
        gmap.set_tile(10, 5, TILE_WATER)
        assert gmap.is_walkable(5, 5)
        assert gmap.is_walkable(6, 5)
        assert gmap.is_walkable(7, 5)
        assert gmap.is_walkable(8, 5)
        assert gmap.is_walkable(9, 5)
        assert gmap.is_walkable(10, 5)

    def test_wall_not_walkable(self):
        gmap = GameMap()
        assert not gmap.is_walkable(0, 0)

    def test_lava_is_walkable(self):
        """Lava is walkable but deals damage (tested in game tests)."""
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_LAVA)
        assert gmap.is_walkable(5, 5)


class TestItemsOnGround:
    def test_add_and_get_items(self):
        gmap = GameMap()
        item = create_item(AXE)
        gmap.add_item_at(5, 5, item)
        items = gmap.get_items_at(5, 5)
        assert len(items) == 1
        assert items[0] is item

    def test_get_items_empty(self):
        gmap = GameMap()
        assert gmap.get_items_at(5, 5) == []

    def test_remove_item(self):
        gmap = GameMap()
        item1 = create_item(AXE)
        item2 = create_item(SHOTGUN)
        gmap.add_item_at(5, 5, item1)
        gmap.add_item_at(5, 5, item2)
        removed = gmap.remove_item_at(5, 5, 0)
        assert removed is item1
        assert len(gmap.get_items_at(5, 5)) == 1

    def test_remove_last_item_cleans_up(self):
        gmap = GameMap()
        item = create_item(AXE)
        gmap.add_item_at(5, 5, item)
        gmap.remove_item_at(5, 5, 0)
        assert (5, 5) not in gmap.items_on_ground


class TestEnemyOnMap:
    def test_get_enemy_at(self):
        from quakelike.enemies import Enemy, GRUNT
        gmap = GameMap()
        enemy = Enemy.from_def(GRUNT, Position(5, 5))
        gmap.enemies.append(enemy)
        found = gmap.get_enemy_at(5, 5)
        assert found is enemy

    def test_get_enemy_at_empty(self):
        gmap = GameMap()
        assert gmap.get_enemy_at(5, 5) is None

    def test_get_enemy_ignores_dead(self):
        from quakelike.enemies import Enemy, GRUNT
        gmap = GameMap()
        enemy = Enemy.from_def(GRUNT, Position(5, 5))
        enemy.is_alive = False
        gmap.enemies.append(enemy)
        assert gmap.get_enemy_at(5, 5) is None

    def test_get_living_enemies(self):
        from quakelike.enemies import Enemy, GRUNT, ROTTWEILER
        gmap = GameMap()
        e1 = Enemy.from_def(GRUNT, Position(5, 5))
        e2 = Enemy.from_def(ROTTWEILER, Position(6, 6))
        e2.is_alive = False
        gmap.enemies.extend([e1, e2])
        living = gmap.get_living_enemies()
        assert len(living) == 1
        assert living[0] is e1


class TestLineOfSight:
    def test_clear_los(self):
        gmap = GameMap()
        # Create a clear line of floor tiles
        for x in range(1, 10):
            gmap.set_tile(5, x, TILE_FLOOR)
        p1 = Position(5, 1)
        p2 = Position(5, 9)
        assert gmap.has_line_of_sight(p1, p2)

    def test_blocked_los(self):
        gmap = GameMap()
        for x in range(1, 10):
            gmap.set_tile(5, x, TILE_FLOOR)
        gmap.set_tile(5, 5, TILE_WALL)  # Block in middle
        p1 = Position(5, 1)
        p2 = Position(5, 9)
        assert not gmap.has_line_of_sight(p1, p2)

    def test_adjacent_always_has_los(self):
        gmap = GameMap()
        gmap.set_tile(5, 5, TILE_FLOOR)
        gmap.set_tile(5, 6, TILE_FLOOR)
        assert gmap.has_line_of_sight(Position(5, 5), Position(5, 6))


class TestBresenhamLine:
    def test_horizontal_line(self):
        points = bresenham_line(5, 0, 5, 5)
        assert (5, 0) in points
        assert (5, 5) in points
        assert len(points) == 6

    def test_vertical_line(self):
        points = bresenham_line(0, 5, 5, 5)
        assert (0, 5) in points
        assert (5, 5) in points
        assert len(points) == 6

    def test_diagonal_line(self):
        points = bresenham_line(0, 0, 5, 5)
        assert (0, 0) in points
        assert (5, 5) in points

    def test_same_point(self):
        points = bresenham_line(3, 3, 3, 3)
        assert points == [(3, 3)]


class TestMapGeneration:
    def test_generates_valid_map(self):
        rng = random.Random(42)
        gmap = generate_map(0, rng)
        assert gmap.width == MAP_WIDTH
        assert gmap.height == MAP_HEIGHT
        assert len(gmap.rooms) > 0

    def test_first_map_has_entrance(self):
        rng = random.Random(42)
        gmap = generate_map(0, rng)
        assert gmap.entrance_pos is not None
        tile = gmap.get_tile(gmap.entrance_pos.y, gmap.entrance_pos.x)
        assert tile == TILE_ENTRANCE

    def test_first_map_has_slipgate_down(self):
        rng = random.Random(42)
        gmap = generate_map(0, rng)
        assert gmap.slipgate_down_pos is not None
        tile = gmap.get_tile(gmap.slipgate_down_pos.y,
                             gmap.slipgate_down_pos.x)
        assert tile == TILE_SLIPGATE_DOWN

    def test_middle_map_has_both_slipgates(self):
        rng = random.Random(42)
        gmap = generate_map(20, rng)
        assert gmap.slipgate_up_pos is not None
        assert gmap.slipgate_down_pos is not None

    def test_last_map_has_no_slipgate_down(self):
        rng = random.Random(42)
        gmap = generate_map(NUM_MAPS - 1, rng)
        assert gmap.slipgate_down_pos is None

    def test_last_map_has_rune(self):
        rng = random.Random(42)
        gmap = generate_map(NUM_MAPS - 1, rng)
        # Find the rune on the map
        found = False
        for (y, x), items in gmap.items_on_ground.items():
            for item in items:
                if item.name == 'Rune':
                    found = True
        assert found, 'Rune should be on the last map'

    def test_has_player_start(self):
        rng = random.Random(42)
        gmap = generate_map(0, rng)
        assert gmap.player_start is not None

    def test_has_enemies(self):
        rng = random.Random(42)
        gmap = generate_map(5, rng)
        assert len(gmap.enemies) > 0

    def test_has_items(self):
        rng = random.Random(42)
        gmap = generate_map(5, rng)
        assert len(gmap.items_on_ground) > 0

    def test_different_seeds_different_maps(self):
        gmap1 = generate_map(5, random.Random(1))
        gmap2 = generate_map(5, random.Random(2))
        # Maps should differ (rooms in different positions)
        rooms1 = [(r.y, r.x) for r in gmap1.rooms]
        rooms2 = [(r.y, r.x) for r in gmap2.rooms]
        assert rooms1 != rooms2

    def test_same_seed_same_map(self):
        gmap1 = generate_map(5, random.Random(42))
        gmap2 = generate_map(5, random.Random(42))
        rooms1 = [(r.y, r.x, r.width, r.height) for r in gmap1.rooms]
        rooms2 = [(r.y, r.x, r.width, r.height) for r in gmap2.rooms]
        assert rooms1 == rooms2

    def test_map_has_walkable_tiles(self):
        rng = random.Random(42)
        gmap = generate_map(0, rng)
        walkable_count = sum(
            1 for y in range(gmap.height) for x in range(gmap.width)
            if gmap.is_walkable(y, x)
        )
        assert walkable_count > 50  # Should have plenty of floor

    def test_forty_maps_can_be_generated(self):
        """All 40 maps should generate without error."""
        rng = random.Random(42)
        for level in range(NUM_MAPS):
            gmap = generate_map(level, rng)
            assert len(gmap.rooms) >= 1

    def test_reveal_around(self):
        rng = random.Random(42)
        gmap = generate_map(0, rng)
        gmap.reveal_around(gmap.player_start.y, gmap.player_start.x)
        assert len(gmap.explored) > 0
