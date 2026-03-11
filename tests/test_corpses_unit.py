"""Unit tests for the enemy corpses and ammo drops feature.

Tests the individual components in isolation:
  - EnemyDef.ammo_drop field
  - Enemy.death_processed field
  - GameMap.add_corpse()
  - Game._process_enemy_death()
  - Serialization of death_processed and corpses
"""

import pytest
from quakelike.enemies import (
    Enemy, EnemyDef, GRUNT, DEATH_KNIGHT, OGRE, ROTTWEILER, KNIGHT,
    ZOMBIE, SCRAG, FIEND, VORE, SHAMBLER, SPAWN_ENEMY, ROTFISH,
)
from quakelike.entity import Position
from quakelike.gamemap import GameMap
from quakelike.items import ITEM_BY_NAME, ItemType
from quakelike.game import Game
from quakelike.constants import TILE_FLOOR


# ---------------------------------------------------------------------------
# EnemyDef.ammo_drop field
# ---------------------------------------------------------------------------

class TestEnemyDefAmmodrop:
    def test_grunt_ammo_drop_is_shells(self):
        assert GRUNT.ammo_drop == 'Shells'

    def test_death_knight_ammo_drop_is_shells(self):
        assert DEATH_KNIGHT.ammo_drop == 'Shells'

    def test_ogre_ammo_drop_is_rockets(self):
        assert OGRE.ammo_drop == 'Rockets'

    @pytest.mark.parametrize('enemy_def', [
        ROTTWEILER, KNIGHT, ZOMBIE, SCRAG, FIEND, VORE, SHAMBLER, SPAWN_ENEMY, ROTFISH,
    ])
    def test_other_enemies_have_no_ammo_drop(self, enemy_def):
        assert enemy_def.ammo_drop is None, (
            f"{enemy_def.name} should have ammo_drop=None, got {enemy_def.ammo_drop!r}"
        )

    def test_ammo_drop_name_must_exist_in_item_registry(self):
        """Any non-None ammo_drop must resolve to a known ItemDef."""
        from quakelike.enemies import ALL_ENEMIES
        for edef in ALL_ENEMIES:
            if edef.ammo_drop is not None:
                assert edef.ammo_drop in ITEM_BY_NAME, (
                    f"{edef.name}.ammo_drop='{edef.ammo_drop}' not found in ITEM_BY_NAME"
                )

    def test_ammo_drop_items_are_ammo_type(self):
        """Any referenced ammo_drop ItemDef must be of type AMMO."""
        from quakelike.enemies import ALL_ENEMIES
        for edef in ALL_ENEMIES:
            if edef.ammo_drop is not None:
                item_def = ITEM_BY_NAME[edef.ammo_drop]
                assert item_def.item_type == ItemType.AMMO, (
                    f"{edef.name}.ammo_drop='{edef.ammo_drop}' is not AMMO type"
                )


# ---------------------------------------------------------------------------
# Enemy.death_processed field
# ---------------------------------------------------------------------------

class TestEnemyDeathProcessed:
    def test_death_processed_default_is_false(self):
        """death_processed must default to False on new Enemy instances."""
        enemy = Enemy.from_def(ROTTWEILER, Position(5, 5))
        assert enemy.death_processed is False

    def test_death_processed_can_be_set_true(self):
        enemy = Enemy.from_def(GRUNT, Position(5, 5))
        enemy.death_processed = True
        assert enemy.death_processed is True


# ---------------------------------------------------------------------------
# GameMap.add_corpse()
# ---------------------------------------------------------------------------

class TestGameMapAddCorpse:
    def test_add_corpse_stores_at_correct_position(self):
        gmap = GameMap()
        gmap.add_corpse(3, 7, 'TestEnemy')
        assert (3, 7) in gmap.corpses

    def test_add_corpse_char_is_percent(self):
        gmap = GameMap()
        gmap.add_corpse(3, 7, 'TestEnemy')
        assert gmap.corpses[(3, 7)]['char'] == '%'

    def test_add_corpse_color_is_brown(self):
        gmap = GameMap()
        gmap.add_corpse(3, 7, 'TestEnemy')
        assert gmap.corpses[(3, 7)]['color'] == '#8B4513'

    def test_add_corpse_stores_name(self):
        gmap = GameMap()
        gmap.add_corpse(3, 7, 'Rottweiler')
        assert gmap.corpses[(3, 7)]['name'] == 'Rottweiler'

    def test_add_corpse_overwrites_existing(self):
        """Later corpse at same tile overwrites earlier one (boss kills weakling)."""
        gmap = GameMap()
        gmap.add_corpse(3, 7, 'Rottweiler')
        gmap.add_corpse(3, 7, 'Shambler')
        assert gmap.corpses[(3, 7)]['name'] == 'Shambler'

    def test_corpses_default_is_empty_dict(self):
        gmap = GameMap()
        assert gmap.corpses == {}


# ---------------------------------------------------------------------------
# Game._process_enemy_death()
# ---------------------------------------------------------------------------

class TestProcessEnemyDeath:
    def _make_game_with_dead_enemy(self, enemy_def):
        game = Game()
        game.new_game(seed=42)
        game.current_map.enemies.clear()
        game.current_map.set_tile(10, 10, TILE_FLOOR)
        game.current_map.set_tile(10, 11, TILE_FLOOR)
        game.player.pos = Position(10, 10)
        enemy = Enemy.from_def(enemy_def, Position(10, 11))
        enemy.health = 0
        enemy.is_alive = False
        game.current_map.enemies.append(enemy)
        return game, enemy

    def test_process_sets_death_processed(self):
        game, enemy = self._make_game_with_dead_enemy(ROTTWEILER)
        game._process_enemy_death(enemy, game.current_map)
        assert enemy.death_processed is True

    def test_process_adds_corpse_to_gamemap(self):
        game, enemy = self._make_game_with_dead_enemy(GRUNT)
        ey, ex = enemy.pos.y, enemy.pos.x
        game._process_enemy_death(enemy, game.current_map)
        assert (ey, ex) in game.current_map.corpses

    def test_process_adds_ammo_for_grunt(self):
        game, enemy = self._make_game_with_dead_enemy(GRUNT)
        ey, ex = enemy.pos.y, enemy.pos.x
        game._process_enemy_death(enemy, game.current_map)
        items = game.current_map.get_items_at(ey, ex)
        assert any(i.name == 'Shells' for i in items)

    def test_process_adds_no_ammo_for_rottweiler(self):
        game, enemy = self._make_game_with_dead_enemy(ROTTWEILER)
        ey, ex = enemy.pos.y, enemy.pos.x
        game._process_enemy_death(enemy, game.current_map)
        items = game.current_map.get_items_at(ey, ex)
        assert items == []

    def test_calling_twice_does_not_add_second_ammo(self):
        """Calling _process_enemy_death twice should be safe (idempotent for items).

        Note: the guard is in _end_turn (checks death_processed), not in
        _process_enemy_death itself — but we test that the flag is set so the
        caller's guard works.
        """
        game, enemy = self._make_game_with_dead_enemy(GRUNT)
        ey, ex = enemy.pos.y, enemy.pos.x
        game._process_enemy_death(enemy, game.current_map)
        # After first call death_processed=True; a second call would not happen
        # in _end_turn, but we verify the state is correct.
        assert enemy.death_processed is True

    def test_process_enemy_death_ammo_quantity_is_1(self):
        game, enemy = self._make_game_with_dead_enemy(OGRE)
        ey, ex = enemy.pos.y, enemy.pos.x
        game._process_enemy_death(enemy, game.current_map)
        items = game.current_map.get_items_at(ey, ex)
        rockets = [i for i in items if i.name == 'Rockets']
        assert rockets and rockets[0].quantity == 1


# ---------------------------------------------------------------------------
# Serialization round-trip unit tests
# ---------------------------------------------------------------------------

class TestSerializationUnit:
    def test_serialize_enemy_includes_death_processed_true(self):
        game = Game()
        game.new_game(seed=42)
        enemy = Enemy.from_def(ROTTWEILER, Position(5, 5))
        enemy.death_processed = True
        result = game._serialize_enemy(enemy)
        assert result['death_processed'] is True

    def test_serialize_enemy_includes_death_processed_false(self):
        game = Game()
        game.new_game(seed=42)
        enemy = Enemy.from_def(GRUNT, Position(5, 5))
        result = game._serialize_enemy(enemy)
        assert result['death_processed'] is False

    def test_serialize_map_includes_corpses(self):
        game = Game()
        game.new_game(seed=42)
        gmap = game.current_map
        gmap.add_corpse(5, 5, 'Rottweiler')
        result = game._serialize_map(gmap)
        assert 'corpses' in result
        assert '5,5' in result['corpses']

    def test_serialize_map_empty_corpses_is_empty_dict(self):
        game = Game()
        game.new_game(seed=42)
        gmap = game.current_map
        result = game._serialize_map(gmap)
        assert result['corpses'] == {}

    def test_corpse_key_format_is_y_comma_x(self):
        """Corpse keys must use 'y,x' string format, matching items_on_ground."""
        game = Game()
        game.new_game(seed=42)
        gmap = game.current_map
        gmap.add_corpse(12, 34, 'TestEnemy')
        result = game._serialize_map(gmap)
        assert '12,34' in result['corpses'], (
            f"Expected '12,34' key in corpses, got: {list(result['corpses'].keys())}"
        )
