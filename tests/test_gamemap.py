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
from quakelike.items import (
    create_item, AXE, SHOTGUN,
    SMALL_HEALTH, MEDIUM_HEALTH, MEGAHEALTH,
    ItemType,
)


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


class TestPowerupScarcity:
    """Tests that powerups are rare and megahealth has reduced weight."""

    def _collect_all_items(self, gmap: GameMap) -> list:
        """Flatten all items placed on the map into a single list."""
        items = []
        for item_list in gmap.items_on_ground.values():
            items.extend(item_list)
        return items

    def test_no_powerups_on_low_levels(self):
        """Powerups must not appear on levels <= 15."""
        for level in range(16):  # 0 through 15 inclusive
            # Run multiple seeds to reduce false-negative risk
            for seed in range(10):
                rng = random.Random(seed)
                gmap = generate_map(level, rng)
                items = self._collect_all_items(gmap)
                powerup_names = [
                    i.name for i in items
                    if i.item_type == ItemType.POWERUP and i.name != 'Rune'
                ]
                assert powerup_names == [], (
                    f"Found powerup(s) {powerup_names} on level {level} "
                    f"(seed {seed}) — powerups should not appear on levels <= 15"
                )

    def test_powerups_rare_on_high_levels(self):
        """On levels > 15, powerups should be rare (true rate ~30%).

        Uses 200 seeds to reduce sampling variance enough that a 40% ceiling
        reliably rejects a broken implementation (e.g., the old 15% window)
        while accommodating the true ~30% rate without false failures.
        """
        maps_with_powerup = 0
        total = 200
        for seed in range(total):
            rng = random.Random(seed)
            gmap = generate_map(20, rng)  # well above the threshold
            items = self._collect_all_items(gmap)
            has_powerup = any(
                i.item_type == ItemType.POWERUP and i.name != 'Rune'
                for i in items
            )
            if has_powerup:
                maps_with_powerup += 1

        rate = maps_with_powerup / total
        assert rate < 0.40, (
            f"Powerup appearance rate {rate:.0%} over {total} maps at level 20 "
            f"is too high; expected < 40% (true rate ~30%)"
        )

    def test_megahealth_rarer_than_small_and_medium(self):
        """MEGAHEALTH should appear less often than SMALL_HEALTH or MEDIUM_HEALTH."""
        counts = {SMALL_HEALTH.name: 0, MEDIUM_HEALTH.name: 0, MEGAHEALTH.name: 0}
        for seed in range(200):
            rng = random.Random(seed)
            gmap = generate_map(10, rng)
            for item_list in gmap.items_on_ground.values():
                for item in item_list:
                    if item.name in counts:
                        counts[item.name] += 1

        assert counts[MEGAHEALTH.name] < counts[SMALL_HEALTH.name], (
            f"MEGAHEALTH ({counts[MEGAHEALTH.name]}) should appear less often "
            f"than SMALL_HEALTH ({counts[SMALL_HEALTH.name]})"
        )
        assert counts[MEGAHEALTH.name] < counts[MEDIUM_HEALTH.name], (
            f"MEGAHEALTH ({counts[MEGAHEALTH.name]}) should appear less often "
            f"than MEDIUM_HEALTH ({counts[MEDIUM_HEALTH.name]})"
        )

    def test_megahealth_not_in_fallback(self):
        """The fallback item pool must never produce MEGAHEALTH.

        The fallback else-branch triggers when no other condition matches.
        On levels <= 3, both the weapon and armor branches are suppressed,
        so rolls in the ranges 0.15-0.40 (ammo) and 0.75-1.00 (else, since
        powerup is also suppressed) drive the fallback.  We use a mock RNG
        that always returns a roll of 0.90 — well above every conditional
        threshold — to force the else branch exclusively and confirm the
        resulting items are never MEGAHEALTH.
        """
        from unittest.mock import patch

        class _FixedRoll:
            """RNG that always returns 0.90 for random() calls."""
            def __init__(self):
                self._real = random.Random(0)

            def random(self):
                return 0.90  # always falls into the else branch

            def randint(self, a, b):
                return self._real.randint(a, b)

            def choice(self, seq):
                return self._real.choice(seq)

            def choices(self, population, weights=None, k=1):
                return self._real.choices(population, weights=weights, k=k)

        from quakelike.gamemap import _place_items, GameMap, Room

        # Build a minimal single-room map so _place_items can place items
        gmap = GameMap()
        room = Room(1, 1, 10, 10)
        for y in range(room.y, room.y2):
            for x in range(room.x, room.x2):
                gmap.set_tile(y, x, 'F')  # mark as floor
        # Use TILE_FLOOR value
        from quakelike.constants import TILE_FLOOR
        for y in range(room.y, room.y2):
            for x in range(room.x, room.x2):
                gmap.set_tile(y, x, TILE_FLOOR)
        gmap.rooms = [room]

        rng = _FixedRoll()
        _place_items(gmap, level=0, rooms=[room], rng=rng)

        items = self._collect_all_items(gmap)
        assert len(items) > 0, "Expected at least one item to be placed"
        for item in items:
            assert item.name != MEGAHEALTH.name, (
                f"MEGAHEALTH must not appear in the fallback item pool; "
                f"got {item.name}"
            )


class TestUnlimitedViewDistance:
    """Tests for the unlimited-range reveal_around()."""

    def test_default_radius_covers_full_map(self):
        """Default radius must be >= MAP_WIDTH + MAP_HEIGHT (120)."""
        import inspect
        sig = inspect.signature(GameMap.reveal_around)
        default_radius = sig.parameters['radius'].default
        assert default_radius >= MAP_WIDTH + MAP_HEIGHT, (
            f"Default radius {default_radius} is too small; "
            f"must be >= MAP_WIDTH + MAP_HEIGHT = {MAP_WIDTH + MAP_HEIGHT}"
        )

    def test_distant_open_tile_gets_revealed(self):
        """A tile far away with clear LOS should be revealed."""
        gmap = GameMap()
        # Carve a long open corridor from x=1 to x=78 on row 5
        for x in range(1, MAP_WIDTH - 1):
            gmap.set_tile(5, x, TILE_FLOOR)

        # Player stands at the left end
        gmap.reveal_around(5, 1)

        # The far-right end of the corridor should be visible
        far_x = MAP_WIDTH - 2
        assert (5, far_x) in gmap.explored, (
            f"Tile (5, {far_x}) should be revealed with unlimited view distance"
        )

    def test_tile_behind_wall_not_revealed(self):
        """A tile blocked by a wall must not be revealed even with large radius."""
        gmap = GameMap()
        # Open corridor on row 5
        for x in range(1, MAP_WIDTH - 1):
            gmap.set_tile(5, x, TILE_FLOOR)
        # Place a wall across the corridor in the middle
        wall_x = MAP_WIDTH // 2
        gmap.set_tile(5, wall_x, TILE_WALL)

        gmap.reveal_around(5, 1)

        # Everything past the wall should be blocked
        for x in range(wall_x + 1, MAP_WIDTH - 1):
            assert (5, x) not in gmap.explored, (
                f"Tile (5, {x}) is behind a wall and should NOT be revealed"
            )
