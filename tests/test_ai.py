"""Tests for the enemy AI module."""

import random
import pytest
from quakelike.entity import Position
from quakelike.player import Player
from quakelike.enemies import Enemy, GRUNT, ROTTWEILER, SCRAG, ROTFISH
from quakelike.gamemap import GameMap
from quakelike.ai import update_enemy, get_enemies_in_los, ALERT_RADIUS
from quakelike.constants import TILE_FLOOR, TILE_WATER


def make_open_map():
    """Create an open floor map for testing."""
    gmap = GameMap()
    for y in range(1, 39):
        for x in range(1, 79):
            gmap.set_tile(y, x, TILE_FLOOR)
    return gmap


class TestAlertness:
    def test_enemy_alerts_on_sight(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        gmap = make_open_map()
        enemy = Enemy.from_def(GRUNT, Position(10, 15))
        gmap.enemies.append(enemy)

        assert not enemy.alerted
        update_enemy(enemy, player, gmap, rng)
        assert enemy.alerted

    def test_enemy_not_alerted_far_away(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        gmap = make_open_map()
        enemy = Enemy.from_def(GRUNT, Position(10, 10 + ALERT_RADIUS + 5))
        gmap.enemies.append(enemy)

        update_enemy(enemy, player, gmap, rng)
        assert not enemy.alerted

    def test_enemy_not_alerted_no_los(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        gmap = make_open_map()
        # Block LOS
        gmap.set_tile(10, 12, '#')
        enemy = Enemy.from_def(GRUNT, Position(10, 15))
        gmap.enemies.append(enemy)

        update_enemy(enemy, player, gmap, rng)
        assert not enemy.alerted


class TestEnemyMovement:
    def test_alerted_enemy_moves_toward_player(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        gmap = make_open_map()
        enemy = Enemy.from_def(GRUNT, Position(10, 25))
        enemy.alerted = True
        gmap.enemies.append(enemy)

        initial_dist = enemy.pos.chebyshev_distance(player.pos)
        # Run several turns
        for _ in range(5):
            update_enemy(enemy, player, gmap, rng)
        final_dist = enemy.pos.chebyshev_distance(player.pos)
        assert final_dist < initial_dist

    def test_enemy_avoids_water(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        gmap = make_open_map()
        # Create water barrier
        for x in range(5, 15):
            gmap.set_tile(12, x, TILE_WATER)
        enemy = Enemy.from_def(GRUNT, Position(14, 10))
        enemy.alerted = True
        gmap.enemies.append(enemy)

        for _ in range(5):
            update_enemy(enemy, player, gmap, rng)
        # Grunt should avoid water tiles
        tile = gmap.get_tile(enemy.pos.y, enemy.pos.x)
        assert tile != TILE_WATER

    def test_rotfish_can_swim(self):
        """Rotfish should be able to move through water."""
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        gmap = make_open_map()
        gmap.set_tile(12, 10, TILE_WATER)
        enemy = Enemy.from_def(ROTFISH, Position(13, 10))
        enemy.alerted = True
        gmap.enemies.append(enemy)

        # Rotfish should not avoid water
        assert not ROTFISH.avoids_water

    def test_dead_enemy_doesnt_move(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        gmap = make_open_map()
        enemy = Enemy.from_def(GRUNT, Position(10, 15))
        enemy.is_alive = False
        gmap.enemies.append(enemy)

        original_pos = enemy.pos.copy()
        update_enemy(enemy, player, gmap, rng)
        assert enemy.pos == original_pos


class TestEnemySpeed:
    def test_fast_enemy_acts_every_turn(self):
        """Grunt (speed=1) should act every turn."""
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        gmap = make_open_map()
        enemy = Enemy.from_def(GRUNT, Position(10, 12))
        enemy.alerted = True
        gmap.enemies.append(enemy)

        initial_hp = player.health
        msgs = update_enemy(enemy, player, gmap, rng)
        # Should have attacked or moved
        assert player.health < initial_hp or enemy.pos != Position(10, 12)


class TestEnemyInLOS:
    def test_get_enemies_in_los(self):
        player = Player.create(Position(10, 10))
        gmap = make_open_map()
        e1 = Enemy.from_def(GRUNT, Position(10, 15))
        e2 = Enemy.from_def(ROTTWEILER, Position(10, 20))
        gmap.enemies.extend([e1, e2])

        visible = get_enemies_in_los(player, gmap)
        assert len(visible) == 2

    def test_enemies_blocked_by_wall(self):
        player = Player.create(Position(10, 10))
        gmap = make_open_map()
        gmap.set_tile(10, 14, '#')
        e1 = Enemy.from_def(GRUNT, Position(10, 12))
        e2 = Enemy.from_def(ROTTWEILER, Position(10, 18))
        gmap.enemies.extend([e1, e2])

        visible = get_enemies_in_los(player, gmap)
        assert len(visible) == 1
        assert visible[0] is e1

    def test_sorted_by_distance(self):
        player = Player.create(Position(10, 10))
        gmap = make_open_map()
        far = Enemy.from_def(GRUNT, Position(10, 25))
        near = Enemy.from_def(ROTTWEILER, Position(10, 12))
        gmap.enemies.extend([far, near])

        visible = get_enemies_in_los(player, gmap)
        assert visible[0] is near
        assert visible[1] is far

    def test_dead_enemies_excluded(self):
        player = Player.create(Position(10, 10))
        gmap = make_open_map()
        alive = Enemy.from_def(GRUNT, Position(10, 15))
        dead = Enemy.from_def(ROTTWEILER, Position(10, 18))
        dead.is_alive = False
        gmap.enemies.extend([alive, dead])

        visible = get_enemies_in_los(player, gmap)
        assert len(visible) == 1
        assert visible[0] is alive


class TestInvisibility:
    def test_invisible_player_harder_to_detect(self):
        """Enemies should have trouble tracking invisible players at distance."""
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        player.invisibility_turns = 10
        gmap = make_open_map()
        enemy = Enemy.from_def(GRUNT, Position(10, 20))
        enemy.alerted = True
        gmap.enemies.append(enemy)

        # With invisibility, enemy should sometimes fail to track
        # Run multiple turns, enemy movement should be less efficient
        moved_toward = 0
        for _ in range(20):
            old_dist = enemy.pos.chebyshev_distance(player.pos)
            update_enemy(enemy, player, gmap, rng)
            new_dist = enemy.pos.chebyshev_distance(player.pos)
            if new_dist < old_dist:
                moved_toward += 1
            # Reset position for consistent testing
            enemy.pos = Position(10, 20)
            enemy.attack_cooldown = 99  # Prevent attacks
            enemy.move_timer = 0

        # With 70% wander chance when invisible and far, should move
        # toward less often than without
        assert moved_toward < 20
