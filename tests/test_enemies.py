"""Tests for the enemies module."""

import pytest
from quakelike.entity import Position
from quakelike.enemies import (
    Enemy, EnemyDef, AttackDef, AttackType,
    ROTTWEILER, GRUNT, KNIGHT, DEATH_KNIGHT, ROTFISH, ZOMBIE,
    SCRAG, OGRE, FIEND, VORE, SHAMBLER, SPAWN_ENEMY,
    ALL_ENEMIES, ENEMY_BY_NAME,
)


class TestEnemyDefinitions:
    """Verify all 12 Quake enemies are present."""

    def test_all_enemies_count(self):
        """There should be exactly 12 enemies (all from Quake)."""
        assert len(ALL_ENEMIES) == 12

    def test_all_enemy_names(self):
        names = {e.name for e in ALL_ENEMIES}
        expected = {
            'Rottweiler', 'Grunt', 'Knight', 'Death Knight',
            'Rotfish', 'Zombie', 'Scrag', 'Ogre',
            'Fiend', 'Vore', 'Shambler', 'Spawn',
        }
        assert names == expected

    def test_enemy_by_name_lookup(self):
        assert ENEMY_BY_NAME['Rottweiler'] is ROTTWEILER
        assert ENEMY_BY_NAME['Shambler'] is SHAMBLER

    def test_all_enemies_have_attacks(self):
        for enemy_def in ALL_ENEMIES:
            assert len(enemy_def.attacks) > 0, \
                f'{enemy_def.name} should have at least one attack'

    def test_all_enemies_have_health(self):
        for enemy_def in ALL_ENEMIES:
            assert enemy_def.health > 0, \
                f'{enemy_def.name} should have positive health'

    def test_all_enemies_have_xp(self):
        for enemy_def in ALL_ENEMIES:
            assert enemy_def.xp_value > 0, \
                f'{enemy_def.name} should give XP'

    def test_all_enemies_have_unique_chars(self):
        """Each enemy should have a distinct character."""
        chars = [e.char for e in ALL_ENEMIES]
        assert len(chars) == len(set(chars)), \
            'Some enemies share the same character'


class TestEnemyBehaviors:
    """Test that enemies have correct behavior flags."""

    def test_rottweiler_melee_only(self):
        assert len(ROTTWEILER.attacks) == 1
        assert ROTTWEILER.attacks[0].attack_type == AttackType.MELEE

    def test_grunt_has_ranged_and_melee(self):
        types = {a.attack_type for a in GRUNT.attacks}
        assert AttackType.MELEE in types
        assert AttackType.RANGED in types

    def test_knight_melee_only(self):
        assert len(KNIGHT.attacks) == 1
        assert KNIGHT.attacks[0].attack_type == AttackType.MELEE

    def test_death_knight_has_ranged(self):
        types = {a.attack_type for a in DEATH_KNIGHT.attacks}
        assert AttackType.RANGED in types

    def test_rotfish_is_swimmer(self):
        assert ROTFISH.can_swim
        assert not ROTFISH.avoids_water

    def test_scrag_can_fly(self):
        assert SCRAG.can_fly

    def test_fiend_has_leap(self):
        types = {a.attack_type for a in FIEND.attacks}
        assert AttackType.LEAP in types

    def test_spawn_explodes(self):
        types = {a.attack_type for a in SPAWN_ENEMY.attacks}
        assert AttackType.EXPLODE in types

    def test_vore_has_homing(self):
        types = {a.attack_type for a in VORE.attacks}
        assert AttackType.RANGED in types

    def test_shambler_has_lightning_and_melee(self):
        types = {a.attack_type for a in SHAMBLER.attacks}
        assert AttackType.MELEE in types
        assert AttackType.RANGED in types


class TestEnemyStats:
    """Test enemy stats are reasonable and reflect Quake."""

    def test_shambler_is_tankiest(self):
        max_hp = max(e.health for e in ALL_ENEMIES)
        assert SHAMBLER.health == max_hp

    def test_rottweiler_is_weakest(self):
        """Rottweiler and Rotfish should be the weakest enemies."""
        min_hp = min(e.health for e in ALL_ENEMIES)
        assert ROTTWEILER.health == min_hp or ROTFISH.health == min_hp

    def test_enemy_level_scaling(self):
        """Stronger enemies should appear on later maps."""
        assert ROTTWEILER.min_map_level < SHAMBLER.min_map_level
        assert GRUNT.min_map_level < VORE.min_map_level


class TestEnemyInstance:
    def test_create_from_def(self):
        pos = Position(5, 5)
        enemy = Enemy.from_def(GRUNT, pos)
        assert enemy.name == 'Grunt'
        assert enemy.health == GRUNT.health
        assert enemy.pos == pos
        assert enemy.is_alive

    def test_enemy_takes_damage(self):
        enemy = Enemy.from_def(ROTTWEILER, Position(0, 0))
        initial_hp = enemy.health
        enemy.take_damage(10)
        assert enemy.health == initial_hp - 10

    def test_enemy_death(self):
        enemy = Enemy.from_def(ROTTWEILER, Position(0, 0))
        enemy.take_damage(enemy.health)
        assert not enemy.is_alive
        assert enemy.health == 0

    def test_can_attack_fresh(self):
        enemy = Enemy.from_def(GRUNT, Position(0, 0))
        assert enemy.can_attack()

    def test_cannot_attack_on_cooldown(self):
        enemy = Enemy.from_def(GRUNT, Position(0, 0))
        enemy.attack_cooldown = 2
        assert not enemy.can_attack()

    def test_cannot_attack_when_dead(self):
        enemy = Enemy.from_def(GRUNT, Position(0, 0))
        enemy.is_alive = False
        assert not enemy.can_attack()

    def test_get_best_attack_melee_range(self):
        enemy = Enemy.from_def(GRUNT, Position(0, 0))
        attack = enemy.get_best_attack(1)
        assert attack is not None
        assert attack.attack_type == AttackType.MELEE

    def test_get_best_attack_ranged(self):
        enemy = Enemy.from_def(GRUNT, Position(0, 0))
        attack = enemy.get_best_attack(5)
        assert attack is not None
        assert attack.attack_type == AttackType.RANGED

    def test_get_best_attack_out_of_range(self):
        enemy = Enemy.from_def(ROTTWEILER, Position(0, 0))
        attack = enemy.get_best_attack(10)
        assert attack is None  # Rottweiler is melee only
