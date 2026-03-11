"""Acceptance and integration tests for enemy corpses and ammo drops.

When an enemy is killed:
  - A corpse marker ('%', brown) is placed at their position in gmap.corpses
  - If the enemy has an ammo_drop defined, an ammo item is placed on the ground
  - A death_processed flag prevents double-processing
  - The render state shows '%' at explored corpse tiles (under items/entities)
  - Corpse does NOT appear in the loot panel (not in items_on_ground unless ammo dropped)
  - Corpse does NOT affect walkability

Quake-accurate drops:
  - Grunt  -> Shells (1 box)
  - Death Knight -> Shells (1 box)
  - Ogre   -> Rockets (1 crate)
  - All others -> no ammo drop
"""

import pytest
from quakelike.game import Game, GameState
from quakelike.entity import Position
from quakelike.enemies import Enemy, GRUNT, ROTTWEILER, DEATH_KNIGHT, OGRE, KNIGHT
from quakelike.constants import TILE_FLOOR
from quakelike.items import create_item, SHOTGUN, SHELLS_SMALL, ItemType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_game_with_enemy(enemy_def, player_pos=(10, 10), enemy_pos=(10, 11)):
    """Return a game with one enemy adjacent to the player on clear floor."""
    game = Game()
    game.new_game(seed=42)
    game.current_map.enemies.clear()

    # Carve walkable floor around both positions
    py, px = player_pos
    ey, ex = enemy_pos
    for y in range(min(py, ey) - 1, max(py, ey) + 2):
        for x in range(min(px, ex) - 1, max(px, ex) + 2):
            game.current_map.set_tile(y, x, TILE_FLOOR)

    game.player.pos = Position(py, px)
    game.current_map.reveal_around(py, px)

    enemy = Enemy.from_def(enemy_def, Position(ey, ex))
    game.current_map.enemies.append(enemy)
    return game, enemy


def _kill_enemy(game, enemy):
    """Force the enemy to 0 HP and trigger death processing via _end_turn."""
    enemy.health = 0
    enemy.is_alive = False
    game._end_turn()


# ---------------------------------------------------------------------------
# TestCorpseMarker - corpse is placed in gmap.corpses on death
# ---------------------------------------------------------------------------

class TestCorpseMarker:
    def test_corpse_placed_at_enemy_position(self):
        """Killing an enemy puts a corpse dict at their (y, x) in gmap.corpses."""
        game, enemy = _make_game_with_enemy(ROTTWEILER)
        ey, ex = enemy.pos.y, enemy.pos.x

        _kill_enemy(game, enemy)

        assert (ey, ex) in game.current_map.corpses, (
            "corpse must be recorded at the enemy's position in gmap.corpses"
        )

    def test_corpse_has_correct_char(self):
        """Corpse marker char must be '%'."""
        game, enemy = _make_game_with_enemy(GRUNT)
        _kill_enemy(game, enemy)

        corpse = game.current_map.corpses[(enemy.pos.y, enemy.pos.x)]
        assert corpse['char'] == '%', (
            f"corpse char must be '%', got {corpse['char']!r}"
        )

    def test_corpse_has_correct_color(self):
        """Corpse marker color must be brown '#8B4513'."""
        game, enemy = _make_game_with_enemy(GRUNT)
        _kill_enemy(game, enemy)

        corpse = game.current_map.corpses[(enemy.pos.y, enemy.pos.x)]
        assert corpse['color'] == '#8B4513', (
            f"corpse color must be '#8B4513', got {corpse['color']!r}"
        )

    def test_corpse_has_name(self):
        """Corpse dict must include the enemy name."""
        game, enemy = _make_game_with_enemy(ROTTWEILER)
        _kill_enemy(game, enemy)

        corpse = game.current_map.corpses[(enemy.pos.y, enemy.pos.x)]
        assert corpse.get('name') == 'Rottweiler', (
            f"corpse name must be 'Rottweiler', got {corpse.get('name')!r}"
        )

    def test_death_processed_flag_set_after_processing(self):
        """death_processed must be True after _process_enemy_death runs."""
        game, enemy = _make_game_with_enemy(ROTTWEILER)
        assert not enemy.death_processed, "death_processed must start as False"

        _kill_enemy(game, enemy)

        assert enemy.death_processed, "death_processed must be True after death handling"

    def test_death_not_double_processed(self):
        """Calling _end_turn multiple times must not create duplicate corpses."""
        game, enemy = _make_game_with_enemy(ROTTWEILER)
        _kill_enemy(game, enemy)
        corpses_before = dict(game.current_map.corpses)

        # Second _end_turn should be a no-op for this enemy
        game._end_turn()

        assert game.current_map.corpses == corpses_before, (
            "corpses dict must not change after double _end_turn processing"
        )

    def test_corpse_not_in_items_on_ground(self):
        """Corpse must NOT appear in gmap.items_on_ground."""
        game, enemy = _make_game_with_enemy(KNIGHT)  # Knight has no ammo_drop
        ey, ex = enemy.pos.y, enemy.pos.x
        _kill_enemy(game, enemy)

        ground_items = game.current_map.get_items_at(ey, ex)
        for item in ground_items:
            assert item.char != '%', (
                "corpse marker must not appear in items_on_ground"
            )

    def test_corpse_does_not_block_movement(self):
        """A tile with a corpse must still be walkable."""
        game, enemy = _make_game_with_enemy(ROTTWEILER)
        ey, ex = enemy.pos.y, enemy.pos.x
        _kill_enemy(game, enemy)

        assert game.current_map.is_walkable(ey, ex), (
            "a corpse tile must remain walkable"
        )


# ---------------------------------------------------------------------------
# TestAmmoDrop - Quake-accurate ammo drops on enemy death
# ---------------------------------------------------------------------------

class TestAmmoDrop:
    def test_grunt_drops_shells(self):
        """A Grunt must drop Shells when killed."""
        game, enemy = _make_game_with_enemy(GRUNT)
        ey, ex = enemy.pos.y, enemy.pos.x
        _kill_enemy(game, enemy)

        items = game.current_map.get_items_at(ey, ex)
        names = [i.name for i in items]
        assert 'Shells' in names, (
            f"Grunt must drop Shells on death; ground items: {names}"
        )

    def test_death_knight_drops_shells(self):
        """A Death Knight must drop Shells when killed."""
        game, enemy = _make_game_with_enemy(DEATH_KNIGHT)
        ey, ex = enemy.pos.y, enemy.pos.x
        _kill_enemy(game, enemy)

        items = game.current_map.get_items_at(ey, ex)
        names = [i.name for i in items]
        assert 'Shells' in names, (
            f"Death Knight must drop Shells on death; ground items: {names}"
        )

    def test_ogre_drops_rockets(self):
        """An Ogre must drop Rockets when killed."""
        game, enemy = _make_game_with_enemy(OGRE)
        ey, ex = enemy.pos.y, enemy.pos.x
        _kill_enemy(game, enemy)

        items = game.current_map.get_items_at(ey, ex)
        names = [i.name for i in items]
        assert 'Rockets' in names, (
            f"Ogre must drop Rockets on death; ground items: {names}"
        )

    def test_rottweiler_drops_nothing(self):
        """A Rottweiler must not drop any ammo when killed."""
        game, enemy = _make_game_with_enemy(ROTTWEILER)
        ey, ex = enemy.pos.y, enemy.pos.x
        _kill_enemy(game, enemy)

        items = game.current_map.get_items_at(ey, ex)
        ammo_items = [i for i in items if i.item_type == ItemType.AMMO]
        assert ammo_items == [], (
            f"Rottweiler must not drop ammo; got: {[i.name for i in ammo_items]}"
        )

    def test_knight_drops_nothing(self):
        """A Knight must not drop any ammo when killed."""
        game, enemy = _make_game_with_enemy(KNIGHT)
        ey, ex = enemy.pos.y, enemy.pos.x
        _kill_enemy(game, enemy)

        items = game.current_map.get_items_at(ey, ex)
        ammo_items = [i for i in items if i.item_type == ItemType.AMMO]
        assert ammo_items == [], (
            f"Knight must not drop ammo; got: {[i.name for i in ammo_items]}"
        )

    def test_ammo_drop_quantity_is_one(self):
        """Ammo dropped by an enemy must have quantity=1 (not the full box amount)."""
        game, enemy = _make_game_with_enemy(GRUNT)
        ey, ex = enemy.pos.y, enemy.pos.x
        _kill_enemy(game, enemy)

        items = game.current_map.get_items_at(ey, ex)
        shells = [i for i in items if i.name == 'Shells']
        assert shells, "Pre-condition: Grunt must drop Shells"
        assert shells[0].quantity == 1, (
            f"Dropped ammo must have quantity=1, got {shells[0].quantity}"
        )


# ---------------------------------------------------------------------------
# TestCorpseRendering - render state shows '%' at corpse tiles
# ---------------------------------------------------------------------------

class TestCorpseRendering:
    def test_corpse_renders_as_percent_char(self):
        """After killing an enemy, the render state shows '%' at their tile."""
        game, enemy = _make_game_with_enemy(KNIGHT)
        ey, ex = enemy.pos.y, enemy.pos.x
        # Explore the tile so it's visible
        game.current_map.explored.add((ey, ex))
        _kill_enemy(game, enemy)

        state = game.get_render_state()
        tile = state['map'][ey][ex]
        assert tile['char'] == '%', (
            f"Render state must show '%' at corpse tile, got {tile['char']!r}"
        )
        assert tile['color'] == '#8B4513', (
            f"Render state must show brown color at corpse tile, got {tile['color']!r}"
        )

    def test_corpse_not_rendered_in_unexplored_tile(self):
        """A corpse at an unexplored tile must not be shown."""
        game, enemy = _make_game_with_enemy(KNIGHT, player_pos=(10, 10), enemy_pos=(10, 11))
        ey, ex = enemy.pos.y, enemy.pos.x

        # Force the corpse but remove from explored
        _kill_enemy(game, enemy)
        game.current_map.explored.discard((ey, ex))

        state = game.get_render_state()
        tile = state['map'][ey][ex]
        # Unexplored tile should show blank, not corpse
        assert tile['char'] == ' ', (
            f"Unexplored corpse tile must render as ' ', got {tile['char']!r}"
        )

    def test_ammo_item_renders_on_top_of_corpse(self):
        """When ammo drops on a corpse tile, the item renders on top (not the '%')."""
        game, enemy = _make_game_with_enemy(GRUNT)
        ey, ex = enemy.pos.y, enemy.pos.x
        game.current_map.explored.add((ey, ex))
        _kill_enemy(game, enemy)

        state = game.get_render_state()
        tile = state['map'][ey][ex]
        # An ammo item should cover the corpse
        assert tile['char'] != '%', (
            f"An ammo drop should render on top of the corpse; got char {tile['char']!r}"
        )

    def test_corpse_not_in_loot_panel(self):
        """Corpse marker must not appear in the loot panel data."""
        game, enemy = _make_game_with_enemy(KNIGHT)
        ey, ex = enemy.pos.y, enemy.pos.x
        game.player.pos = Position(ey, ex)  # Move player onto corpse tile
        game.current_map.explored.add((ey, ex))
        _kill_enemy(game, enemy)

        state = game.get_render_state()
        loot_names = [entry['name'] for entry in state.get('loot', [])]
        # Knight has no ammo drop; loot should be empty (no corpse in loot)
        assert '%' not in loot_names, (
            f"Corpse char '%' must not appear in loot panel; got {loot_names}"
        )


# ---------------------------------------------------------------------------
# TestCorpseSaveLoad - corpses survive serialization round-trips
# ---------------------------------------------------------------------------

class TestCorpseSaveLoad:
    def test_corpses_survive_save_and_load(self, tmp_path):
        """Corpses in gmap.corpses must be restored after save/load."""
        import quakelike.game as game_module
        orig_saves_dir = game_module.SAVES_DIR
        game_module.SAVES_DIR = str(tmp_path)

        try:
            game, enemy = _make_game_with_enemy(ROTTWEILER)
            ey, ex = enemy.pos.y, enemy.pos.x
            _kill_enemy(game, enemy)

            assert (ey, ex) in game.current_map.corpses

            game._save_game()

            # Load into a fresh game instance
            game2 = Game()
            game2.new_game(seed=0)
            loaded = game2.load_game(game.game_id)
            assert loaded, "load_game must return True on success"

            assert (ey, ex) in game2.current_map.corpses, (
                "corpse must be present after save/load round-trip"
            )
            corpse = game2.current_map.corpses[(ey, ex)]
            assert corpse['char'] == '%'
            assert corpse['color'] == '#8B4513'
        finally:
            game_module.SAVES_DIR = orig_saves_dir

    def test_death_processed_flag_survives_save_and_load(self, tmp_path):
        """death_processed flag on Enemy must be preserved through save/load."""
        import quakelike.game as game_module
        orig_saves_dir = game_module.SAVES_DIR
        game_module.SAVES_DIR = str(tmp_path)

        try:
            game, enemy = _make_game_with_enemy(ROTTWEILER)
            _kill_enemy(game, enemy)
            assert enemy.death_processed

            game._save_game()

            game2 = Game()
            game2.new_game(seed=0)
            game2.load_game(game.game_id)

            dead_enemies = [e for e in game2.current_map.enemies if not e.is_alive]
            assert dead_enemies, "loaded game must have the dead enemy"
            assert dead_enemies[0].death_processed, (
                "death_processed must be True after save/load"
            )
        finally:
            game_module.SAVES_DIR = orig_saves_dir

    def test_old_save_without_corpses_loads_with_empty_corpses(self, tmp_path):
        """A save file missing the 'corpses' key must load with an empty dict."""
        import json
        import quakelike.game as game_module
        orig_saves_dir = game_module.SAVES_DIR
        game_module.SAVES_DIR = str(tmp_path)

        try:
            game = Game()
            game.new_game(seed=42)
            game._save_game()

            # Manually strip 'corpses' from the save to simulate an old save
            save_path = tmp_path / f'game_{game.game_id}.json'
            with open(save_path) as f:
                data = json.load(f)
            for map_data in data['maps'].values():
                map_data.pop('corpses', None)
            with open(save_path, 'w') as f:
                json.dump(data, f)

            game2 = Game()
            game2.new_game(seed=0)
            loaded = game2.load_game(game.game_id)
            assert loaded, "must load successfully"
            # All maps should have empty corpses dicts
            for gmap in game2.maps.values():
                assert gmap.corpses == {}, (
                    "old save without corpses key must deserialize to empty dict"
                )
        finally:
            game_module.SAVES_DIR = orig_saves_dir
