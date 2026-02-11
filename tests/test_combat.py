"""Tests for the combat module."""

import random
import pytest
from quakelike.entity import Position
from quakelike.player import Player
from quakelike.enemies import Enemy, GRUNT, ROTTWEILER, SHAMBLER, OGRE
from quakelike.gamemap import GameMap, generate_map
from quakelike.items import (
    create_item, AXE, SHOTGUN, SHELLS_SMALL, ROCKET_LAUNCHER,
    ROCKETS_SMALL, QUAD_DAMAGE,
)
from quakelike.combat import (
    player_melee_attack, player_fire_weapon, enemy_attack,
    calculate_weapon_damage,
)
from quakelike.constants import MELEE_DAMAGE_MIN, MELEE_DAMAGE_MAX, TILE_FLOOR


def make_test_map():
    """Create a simple test map with open space."""
    gmap = GameMap()
    for y in range(5, 20):
        for x in range(5, 40):
            gmap.set_tile(y, x, TILE_FLOOR)
    return gmap


class TestMeleeAttack:
    def test_melee_deals_damage(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        enemy = Enemy.from_def(ROTTWEILER, Position(10, 11))
        damage, msg = player_melee_attack(player, enemy, rng)
        assert MELEE_DAMAGE_MIN <= damage <= MELEE_DAMAGE_MAX
        assert enemy.health < ROTTWEILER.health

    def test_melee_kill_message(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        enemy = Enemy.from_def(ROTTWEILER, Position(10, 11))
        enemy.health = 1  # Nearly dead
        damage, msg = player_melee_attack(player, enemy, rng)
        assert not enemy.is_alive
        assert 'killed' in msg.lower()

    def test_melee_with_quad_damage(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        player.quad_damage_turns = 10
        enemy = Enemy.from_def(SHAMBLER, Position(10, 11))
        damage, msg = player_melee_attack(player, enemy, rng)
        assert damage >= MELEE_DAMAGE_MIN * 4


class TestFireWeapon:
    def test_fire_shotgun_at_target(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        shotgun = create_item(SHOTGUN)
        shells = create_item(SHELLS_SMALL)
        player.inventory.add_item(shotgun)
        player.inventory.add_item(shells)
        player.equip_weapon(shotgun)

        gmap = make_test_map()
        enemy = Enemy.from_def(GRUNT, Position(10, 15))
        gmap.enemies.append(enemy)

        success, msg, extra = player_fire_weapon(player, enemy, gmap, rng)
        assert success
        assert enemy.health < GRUNT.health
        # Shells consumed
        assert player.inventory.get_ammo_count(
            SHOTGUN.ammo_type) < SHELLS_SMALL.ammo_amount

    def test_fire_no_weapon(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        player.equipped_weapon = None
        gmap = make_test_map()
        success, msg, extra = player_fire_weapon(player, None, gmap, rng)
        assert not success
        assert 'no weapon' in msg.lower()

    def test_fire_no_ammo(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        shotgun = create_item(SHOTGUN)
        player.inventory.add_item(shotgun)
        player.equip_weapon(shotgun)
        gmap = make_test_map()
        enemy = Enemy.from_def(GRUNT, Position(10, 15))
        gmap.enemies.append(enemy)
        success, msg, extra = player_fire_weapon(player, enemy, gmap, rng)
        assert not success
        assert 'ammo' in msg.lower()

    def test_fire_out_of_range(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        shotgun = create_item(SHOTGUN)
        shells = create_item(SHELLS_SMALL)
        player.inventory.add_item(shotgun)
        player.inventory.add_item(shells)
        player.equip_weapon(shotgun)

        gmap = make_test_map()
        # Place enemy far away (beyond shotgun range)
        enemy = Enemy.from_def(GRUNT, Position(10, 35))
        gmap.enemies.append(enemy)

        success, msg, extra = player_fire_weapon(player, enemy, gmap, rng)
        assert not success
        assert 'out of range' in msg.lower()

    def test_fire_no_los(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        shotgun = create_item(SHOTGUN)
        shells = create_item(SHELLS_SMALL)
        player.inventory.add_item(shotgun)
        player.inventory.add_item(shells)
        player.equip_weapon(shotgun)

        gmap = make_test_map()
        # Place wall between player and enemy
        gmap.set_tile(10, 12, '#')
        enemy = Enemy.from_def(GRUNT, Position(10, 15))
        gmap.enemies.append(enemy)

        success, msg, extra = player_fire_weapon(player, enemy, gmap, rng)
        assert not success
        assert 'line of sight' in msg.lower()

    def test_fire_consumes_ammo(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        shotgun = create_item(SHOTGUN)
        shells = create_item(SHELLS_SMALL)
        player.inventory.add_item(shotgun)
        player.inventory.add_item(shells)
        player.equip_weapon(shotgun)

        gmap = make_test_map()
        enemy = Enemy.from_def(GRUNT, Position(10, 12))
        gmap.enemies.append(enemy)

        initial_ammo = player.inventory.get_ammo_count(SHOTGUN.ammo_type)
        player_fire_weapon(player, enemy, gmap, rng)
        assert player.inventory.get_ammo_count(SHOTGUN.ammo_type) == \
            initial_ammo - SHOTGUN.ammo_per_shot

    def test_fire_axe_melee_range_only(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        # Player starts with axe equipped
        gmap = make_test_map()
        enemy = Enemy.from_def(GRUNT, Position(10, 15))
        gmap.enemies.append(enemy)

        success, msg, extra = player_fire_weapon(player, enemy, gmap, rng)
        assert not success
        assert 'melee range' in msg.lower()


class TestEnemyAttack:
    def test_melee_attack(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        enemy = Enemy.from_def(ROTTWEILER, Position(10, 11))
        gmap = make_test_map()
        gmap.enemies.append(enemy)

        initial_hp = player.health
        msgs = enemy_attack(enemy, player, gmap, rng)
        assert player.health < initial_hp
        assert len(msgs) > 0

    def test_ranged_attack(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        enemy = Enemy.from_def(GRUNT, Position(10, 15))
        gmap = make_test_map()
        gmap.enemies.append(enemy)

        initial_hp = player.health
        msgs = enemy_attack(enemy, player, gmap, rng)
        assert player.health < initial_hp

    def test_enemy_on_cooldown(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        enemy = Enemy.from_def(GRUNT, Position(10, 11))
        enemy.attack_cooldown = 3
        gmap = make_test_map()

        initial_hp = player.health
        msgs = enemy_attack(enemy, player, gmap, rng)
        assert player.health == initial_hp  # No damage
        assert len(msgs) == 0

    def test_friendly_fire_avoidance(self):
        """Enemies should avoid shooting through allies."""
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        enemy = Enemy.from_def(GRUNT, Position(10, 18))
        # Place ally between enemy and player
        ally = Enemy.from_def(ROTTWEILER, Position(10, 14))
        gmap = make_test_map()
        gmap.enemies.extend([enemy, ally])

        initial_hp = player.health
        initial_ally_hp = ally.health
        msgs = enemy_attack(enemy, player, gmap, rng)
        # Enemy should skip the attack to avoid hitting ally
        assert player.health == initial_hp
        assert ally.health == initial_ally_hp


class TestSplashDamage:
    def test_rocket_splash(self):
        rng = random.Random(42)
        player = Player.create(Position(10, 10))
        rl = create_item(ROCKET_LAUNCHER)
        rockets = create_item(ROCKETS_SMALL)
        player.inventory.add_item(rl)
        player.inventory.add_item(rockets)
        player.equip_weapon(rl)

        gmap = make_test_map()
        target = Enemy.from_def(SHAMBLER, Position(10, 15))
        nearby = Enemy.from_def(GRUNT, Position(10, 16))
        gmap.enemies.extend([target, nearby])

        success, msg, extra = player_fire_weapon(player, target, gmap, rng)
        assert success
        # Nearby enemy should take splash damage
        assert nearby.health < GRUNT.health


class TestDamageCalculation:
    def test_weapon_damage_in_range(self):
        rng = random.Random(42)
        player = Player.create(Position(0, 0))
        shotgun = create_item(SHOTGUN)
        player.inventory.add_item(shotgun)
        player.equip_weapon(shotgun)

        for _ in range(20):
            damage = calculate_weapon_damage(player, rng)
            assert SHOTGUN.damage_min <= damage <= SHOTGUN.damage_max

    def test_quad_multiplies_damage(self):
        rng = random.Random(42)
        player = Player.create(Position(0, 0))
        player.quad_damage_turns = 10
        shotgun = create_item(SHOTGUN)
        player.inventory.add_item(shotgun)
        player.equip_weapon(shotgun)

        for _ in range(20):
            damage = calculate_weapon_damage(player, rng)
            assert damage >= SHOTGUN.damage_min * 4
            assert damage <= SHOTGUN.damage_max * 4
