"""Acceptance and integration tests for the enemy corpses and ammo drops feature.

These tests define the behavioral contract and are expected to FAIL (red phase)
until the feature is implemented by the developer.

Feature summary:
- When an enemy is killed a corpse marker ('%') is placed at their position.
- Corpses are visual only — they are not items and cannot be looted.
- If the killed enemy has an ammo_drop defined, an ammo item is placed on the
  ground at the same position so the player can pick it up.
- Quake-accurate ammo drops:
    Grunt        → Shells (ammo_drop)
    Death Knight → Shells (ammo_drop)
    Ogre         → Rockets (ammo_drop)
    All others   → no ammo drop
- A `death_processed` flag on Enemy prevents double-processing.
- Corpses and ammo drops survive a save/load round-trip.
"""

import json
import os
import tempfile
import unittest.mock as mock

import pytest

from quakelike.game import Game, GameState
from quakelike.gamemap import GameMap
from quakelike.entity import Position
from quakelike.enemies import Enemy, GRUNT, DEATH_KNIGHT, OGRE, FIEND, ZOMBIE, SHAMBLER
from quakelike.items import AmmoType
from quakelike.constants import TILE_FLOOR


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

CORPSE_CHAR = '%'


def make_test_map() -> GameMap:
    """Return a small open map with floor tiles in the central region."""
    gmap = GameMap()
    for y in range(5, 20):
        for x in range(5, 40):
            gmap.set_tile(y, x, TILE_FLOOR)
    return gmap


def _patch_saves_dir(saves_dir: str):
    """Redirect SAVES_DIR to an arbitrary directory in tests."""
    return mock.patch("quakelike.game.SAVES_DIR", saves_dir, create=True)


def _kill_enemy(enemy: Enemy) -> None:
    """Drive an enemy's health to zero and mark it dead the same way combat does."""
    enemy.take_damage(enemy.health + 9999)


def _setup_game_with_enemy(enemy_def, pos: Position):
    """Create a fresh game, place a single enemy, and return (game, enemy)."""
    game = Game()
    game.new_game(seed=42)
    gmap = game.current_map

    # Carve open floor around the enemy position so movement is unobstructed.
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            gmap.set_tile(pos.y + dy, pos.x + dx, TILE_FLOOR)

    gmap.enemies.clear()
    enemy = Enemy.from_def(enemy_def, pos)
    gmap.enemies.append(enemy)
    return game, enemy


# ---------------------------------------------------------------------------
# Acceptance Tests — one criterion per test
# ---------------------------------------------------------------------------

class TestAmmoDrops:
    """AC-1..AC-4  Correct ammo types and quantities are placed on kill."""

    def test_killing_grunt_places_ammo_on_ground(self):
        """AC-1: Killing a Grunt places an ammo item at the enemy's position."""
        enemy_pos = Position(10, 15)
        game, enemy = _setup_game_with_enemy(GRUNT, enemy_pos)
        gmap = game.current_map

        _kill_enemy(enemy)
        game._end_turn()  # trigger death processing

        items_here = gmap.get_items_at(enemy_pos.y, enemy_pos.x)
        assert len(items_here) > 0, (
            "Expected ammo on the ground at the Grunt's position after death, "
            "but found no items."
        )

    def test_killing_death_knight_places_ammo_on_ground(self):
        """AC-2: Killing a Death Knight places an ammo item at their position."""
        enemy_pos = Position(10, 15)
        game, enemy = _setup_game_with_enemy(DEATH_KNIGHT, enemy_pos)
        gmap = game.current_map

        _kill_enemy(enemy)
        game._end_turn()

        items_here = gmap.get_items_at(enemy_pos.y, enemy_pos.x)
        assert len(items_here) > 0, (
            "Expected ammo on the ground at the Death Knight's position after death."
        )

    def test_killing_ogre_places_rockets_on_ground(self):
        """AC-3: Killing an Ogre places a rockets ammo item at their position."""
        enemy_pos = Position(10, 15)
        game, enemy = _setup_game_with_enemy(OGRE, enemy_pos)
        gmap = game.current_map

        _kill_enemy(enemy)
        game._end_turn()

        items_here = gmap.get_items_at(enemy_pos.y, enemy_pos.x)
        assert len(items_here) > 0, (
            "Expected rockets on the ground at the Ogre's position after death."
        )
        rocket_items = [
            i for i in items_here
            if i.item_def.ammo_type == AmmoType.ROCKETS
        ]
        assert rocket_items, (
            "Expected the dropped item to be rockets (AmmoType.ROCKETS), "
            f"but got: {[i.name for i in items_here]}"
        )

    def test_grunt_drops_shells_not_rockets(self):
        """AC-4a: Grunt drops shells (not rockets or any other ammo type)."""
        enemy_pos = Position(10, 15)
        game, enemy = _setup_game_with_enemy(GRUNT, enemy_pos)
        gmap = game.current_map

        _kill_enemy(enemy)
        game._end_turn()

        items_here = gmap.get_items_at(enemy_pos.y, enemy_pos.x)
        shell_items = [
            i for i in items_here
            if i.item_def.ammo_type == AmmoType.SHELLS
        ]
        assert shell_items, (
            "Expected Grunt to drop Shells (AmmoType.SHELLS), "
            f"but got: {[i.name for i in items_here]}"
        )

    def test_death_knight_drops_shells_not_rockets(self):
        """AC-4b: Death Knight drops shells (matching Quake lore)."""
        enemy_pos = Position(10, 15)
        game, enemy = _setup_game_with_enemy(DEATH_KNIGHT, enemy_pos)
        gmap = game.current_map

        _kill_enemy(enemy)
        game._end_turn()

        items_here = gmap.get_items_at(enemy_pos.y, enemy_pos.x)
        shell_items = [
            i for i in items_here
            if i.item_def.ammo_type == AmmoType.SHELLS
        ]
        assert shell_items, (
            "Expected Death Knight to drop Shells (AmmoType.SHELLS), "
            f"but got: {[i.name for i in items_here]}"
        )


class TestCorpsePlacement:
    """AC-5..AC-6  A corpse entry is created with the right character."""

    def test_corpse_entry_exists_after_enemy_death(self):
        """AC-5: A corpse entry appears in gmap.corpses at the enemy's position."""
        enemy_pos = Position(10, 15)
        game, enemy = _setup_game_with_enemy(GRUNT, enemy_pos)
        gmap = game.current_map

        _kill_enemy(enemy)
        game._end_turn()

        # corpses must be a dict-like structure keyed by (y, x)
        assert hasattr(gmap, 'corpses'), (
            "GameMap is missing a 'corpses' attribute — expected a dict."
        )
        key = (enemy_pos.y, enemy_pos.x)
        assert key in gmap.corpses, (
            f"Expected a corpse entry at {key} after the Grunt died, "
            f"but corpses = {gmap.corpses}"
        )

    def test_corpse_uses_percent_char(self):
        """AC-6: The corpse entry uses '%' as its character."""
        enemy_pos = Position(10, 15)
        game, enemy = _setup_game_with_enemy(GRUNT, enemy_pos)
        gmap = game.current_map

        _kill_enemy(enemy)
        game._end_turn()

        key = (enemy_pos.y, enemy_pos.x)
        corpse = gmap.corpses.get(key)
        assert corpse is not None, "No corpse entry found — cannot check its char."
        char = corpse.get('char') if isinstance(corpse, dict) else getattr(corpse, 'char', None)
        assert char == CORPSE_CHAR, (
            f"Expected corpse char '{CORPSE_CHAR}', got '{char}'."
        )


class TestNonAmmoEnemies:
    """AC-7..AC-8  Non-ammo enemies leave a corpse but no ammo on the ground."""

    @pytest.mark.parametrize("enemy_def,label", [
        (FIEND, "Fiend"),
        (ZOMBIE, "Zombie"),
        (SHAMBLER, "Shambler"),
    ])
    def test_non_ammo_enemy_leaves_no_ammo(self, enemy_def, label):
        """AC-7: Killing a non-ammo enemy places no item in items_on_ground."""
        enemy_pos = Position(10, 15)
        game, enemy = _setup_game_with_enemy(enemy_def, enemy_pos)
        gmap = game.current_map

        _kill_enemy(enemy)
        game._end_turn()

        items_here = gmap.get_items_at(enemy_pos.y, enemy_pos.x)
        assert len(items_here) == 0, (
            f"Expected no ammo drop for {label}, but found: "
            f"{[i.name for i in items_here]}"
        )

    @pytest.mark.parametrize("enemy_def,label", [
        (FIEND, "Fiend"),
        (ZOMBIE, "Zombie"),
        (SHAMBLER, "Shambler"),
    ])
    def test_non_ammo_enemy_still_leaves_corpse(self, enemy_def, label):
        """AC-7 (corpse half): Non-ammo enemies still produce a corpse entry."""
        enemy_pos = Position(10, 15)
        game, enemy = _setup_game_with_enemy(enemy_def, enemy_pos)
        gmap = game.current_map

        _kill_enemy(enemy)
        game._end_turn()

        assert hasattr(gmap, 'corpses'), "GameMap missing 'corpses' attribute."
        key = (enemy_pos.y, enemy_pos.x)
        assert key in gmap.corpses, (
            f"Expected a corpse entry for {label} at {key}."
        )

    def test_corpse_not_in_items_on_ground(self):
        """AC-8: Corpse char does NOT appear in items_on_ground (not lootable)."""
        enemy_pos = Position(10, 15)
        game, enemy = _setup_game_with_enemy(FIEND, enemy_pos)
        gmap = game.current_map

        _kill_enemy(enemy)
        game._end_turn()

        # Pre-condition: a corpse entry must exist for this test to be meaningful.
        assert hasattr(gmap, 'corpses'), (
            "Pre-condition failed: GameMap missing 'corpses' — "
            "implement the corpse feature first."
        )
        key = (enemy_pos.y, enemy_pos.x)
        assert key in gmap.corpses, (
            f"Pre-condition failed: no corpse at {key} — "
            "implement the corpse feature first."
        )

        # None of the items on the ground at the corpse tile should be a corpse marker.
        items_here = gmap.get_items_at(enemy_pos.y, enemy_pos.x)
        for item in items_here:
            assert item.char != CORPSE_CHAR, (
                "Corpse marker found inside items_on_ground — it should be "
                "in gmap.corpses, not as a lootable item."
            )


class TestCorpseWalkability:
    """AC-9  Corpse tile is still walkable after death."""

    def test_player_can_walk_onto_corpse_tile(self):
        """AC-9: A tile with a corpse remains walkable."""
        game = Game()
        game.new_game(seed=42)
        gmap = game.current_map

        # Set up an open corridor: player at (10,10), enemy at (10,11)
        for x in range(9, 14):
            gmap.set_tile(10, x, TILE_FLOOR)
        gmap.enemies.clear()

        enemy = Enemy.from_def(GRUNT, Position(10, 11))
        enemy.health = 1  # will die from a single melee bump
        gmap.enemies.append(enemy)

        game.player.pos = Position(10, 10)

        # Bumping right into the enemy kills it and should leave player there or
        # advance (depending on implementation) but the tile must be walkable.
        game.handle_input('l')  # move right — melee attack into enemy

        # Pre-condition: corpse must have been created for this test to be meaningful.
        assert hasattr(gmap, 'corpses'), (
            "Pre-condition failed: GameMap missing 'corpses' — "
            "implement the corpse feature first."
        )
        key = (10, 11)
        assert key in gmap.corpses, (
            f"Pre-condition failed: no corpse at {key} after kill — "
            "implement the corpse feature first."
        )

        # After the enemy dies the tile must still be walkable.
        assert gmap.is_walkable(10, 11), (
            "Corpse position (10,11) became non-walkable after enemy death."
        )

        # Player should have moved onto the tile (melee bump advances in most rogue-likes)
        # or at minimum the tile is now unoccupied by a living enemy.
        assert gmap.get_enemy_at(10, 11) is None or not enemy.is_alive


class TestRenderStateCorpse:
    """AC-10..AC-11  get_render_state() correctly renders corpses vs items."""

    def test_corpse_char_shown_in_visible_tiles_when_no_item_above(self):
        """AC-10: visible_tiles shows '%' at corpse position when nothing is on top."""
        game = Game()
        game.new_game(seed=42)
        gmap = game.current_map

        ey, ex = 10, 15
        for y in range(8, 13):
            for x in range(8, 18):
                gmap.set_tile(y, x, TILE_FLOOR)
        gmap.enemies.clear()

        enemy = Enemy.from_def(GRUNT, Position(ey, ex))
        gmap.enemies.append(enemy)

        # Reveal the tile so it appears in render output.
        gmap.explored.add((ey, ex))

        _kill_enemy(enemy)
        game._end_turn()

        # Move player away so it doesn't overlap the corpse tile.
        game.player.pos = Position(10, 8)

        # Ensure no ammo item sits on the corpse tile (move it away if present).
        # The Grunt drops ammo, so we must remove it to test the corpse char alone.
        gmap.items_on_ground.pop((ey, ex), None)

        state = game.get_render_state()
        tile = state['map'][ey][ex]
        assert tile.get('char') == CORPSE_CHAR, (
            f"Expected visible_tiles[{ey}][{ex}] to show '{CORPSE_CHAR}' (corpse), "
            f"but got '{tile.get('char')}'. Corpses should render below items/enemies."
        )

    def test_item_char_shown_over_corpse_when_item_present(self):
        """AC-11: When an item is on top of a corpse, the item's char is shown."""
        from quakelike.items import create_item, SHELLS_SMALL

        game = Game()
        game.new_game(seed=42)
        gmap = game.current_map

        ey, ex = 10, 15
        for y in range(8, 13):
            for x in range(8, 18):
                gmap.set_tile(y, x, TILE_FLOOR)
        gmap.enemies.clear()

        enemy = Enemy.from_def(SHAMBLER, Position(ey, ex))  # no ammo drop
        gmap.enemies.append(enemy)
        gmap.explored.add((ey, ex))

        _kill_enemy(enemy)
        game._end_turn()

        # Pre-condition: corpse must have been created.
        assert hasattr(gmap, 'corpses'), (
            "Pre-condition failed: GameMap missing 'corpses' — "
            "implement the corpse feature first."
        )
        key = (ey, ex)
        assert key in gmap.corpses, (
            f"Pre-condition failed: no corpse at {key} — "
            "implement the corpse feature first."
        )

        # Now place a shells item on top of the corpse tile.
        shells = create_item(SHELLS_SMALL)
        gmap.add_item_at(ey, ex, shells)
        game.player.pos = Position(10, 8)

        state = game.get_render_state()
        tile = state['map'][ey][ex]
        assert tile.get('char') == shells.char, (
            f"Expected visible_tiles[{ey}][{ex}] to show item char '{shells.char}' "
            f"(item on top of corpse), but got '{tile.get('char')}'."
        )
        assert tile.get('char') != CORPSE_CHAR, (
            "Corpse char '%' was shown even though an item is present on the tile."
        )


class TestSaveLoadCorpses:
    """AC-12  Corpses and ammo drops survive a save/load round-trip."""

    def test_corpse_survives_save_load(self):
        """AC-12a: Corpse entry is present in gmap.corpses after load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with _patch_saves_dir(tmpdir):
                game = Game()
                game.new_game(seed=42)
                gmap = game.current_map

                ey, ex = 10, 15
                for y in range(8, 13):
                    for x in range(8, 18):
                        gmap.set_tile(y, x, TILE_FLOOR)
                gmap.enemies.clear()

                enemy = Enemy.from_def(GRUNT, Position(ey, ex))
                gmap.enemies.append(enemy)

                _kill_enemy(enemy)
                game._end_turn()

                key = (ey, ex)
                assert hasattr(gmap, 'corpses') and key in gmap.corpses, (
                    "Pre-condition failed: corpse not created before save."
                )

                game_id = game.game_id
                game._save_game()

                game2 = Game()
                loaded = game2.load_game(game_id=game_id)
                assert loaded, "load_game() returned False — save/load failed."

                gmap2 = game2.current_map
                assert hasattr(gmap2, 'corpses'), (
                    "GameMap loaded from disk is missing 'corpses' attribute."
                )
                assert key in gmap2.corpses, (
                    f"Corpse at {key} was not preserved across save/load. "
                    f"gmap2.corpses = {gmap2.corpses}"
                )

    def test_ammo_drop_survives_save_load(self):
        """AC-12b: Ammo item placed at death position is still there after load."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with _patch_saves_dir(tmpdir):
                game = Game()
                game.new_game(seed=42)
                gmap = game.current_map

                ey, ex = 10, 15
                for y in range(8, 13):
                    for x in range(8, 18):
                        gmap.set_tile(y, x, TILE_FLOOR)
                gmap.enemies.clear()

                enemy = Enemy.from_def(GRUNT, Position(ey, ex))
                gmap.enemies.append(enemy)

                _kill_enemy(enemy)
                game._end_turn()

                items_before = game.current_map.get_items_at(ey, ex)
                assert len(items_before) > 0, (
                    "Pre-condition failed: Grunt did not drop ammo before save."
                )

                game_id = game.game_id
                game._save_game()

                game2 = Game()
                loaded = game2.load_game(game_id=game_id)
                assert loaded, "load_game() returned False."

                items_after = game2.current_map.get_items_at(ey, ex)
                assert len(items_after) > 0, (
                    "Ammo item was lost across save/load — serialization is incomplete."
                )
                assert items_after[0].name == items_before[0].name, (
                    f"Item name changed across save/load: "
                    f"before={items_before[0].name}, after={items_after[0].name}"
                )


class TestDeathProcessedFlag:
    """AC-13  death_processed flag prevents double-processing."""

    def test_death_processed_flag_exists_on_enemy(self):
        """AC-13a: Enemy has a death_processed attribute (default False)."""
        enemy = Enemy.from_def(GRUNT, Position(10, 10))
        assert hasattr(enemy, 'death_processed'), (
            "Enemy is missing 'death_processed' attribute."
        )
        assert enemy.death_processed is False, (
            "death_processed should default to False on a fresh enemy."
        )

    def test_death_processed_true_after_death_handling(self):
        """AC-13b: After death processing, enemy.death_processed is True."""
        enemy_pos = Position(10, 15)
        game, enemy = _setup_game_with_enemy(GRUNT, enemy_pos)
        gmap = game.current_map

        _kill_enemy(enemy)
        game._end_turn()

        assert enemy.death_processed is True, (
            "Expected enemy.death_processed to be True after death handling."
        )

    def test_double_end_turn_does_not_duplicate_ammo_drop(self):
        """AC-13c: Calling _end_turn() twice does not add a second ammo drop."""
        enemy_pos = Position(10, 15)
        game, enemy = _setup_game_with_enemy(GRUNT, enemy_pos)
        gmap = game.current_map

        _kill_enemy(enemy)
        game._end_turn()  # first processing — should create ammo and set flag
        items_after_first = len(gmap.get_items_at(enemy_pos.y, enemy_pos.x))

        # Pre-condition: ammo must have been placed in the first turn for this
        # test to be meaningful. Without this check the test would vacuously
        # pass before the feature is implemented.
        assert items_after_first > 0, (
            "Pre-condition failed: Grunt dropped no ammo on first _end_turn(). "
            "The ammo-drop feature must be implemented for this test to be valid."
        )

        game._end_turn()  # second call — must NOT add another ammo item
        items_after_second = len(gmap.get_items_at(enemy_pos.y, enemy_pos.x))

        assert items_after_first == items_after_second, (
            f"Calling _end_turn() twice created duplicate ammo drops: "
            f"first={items_after_first}, second={items_after_second}. "
            "The death_processed flag should prevent this."
        )

    def test_double_end_turn_does_not_duplicate_corpse(self):
        """AC-13d: Calling _end_turn() twice does not create duplicate corpse entries."""
        enemy_pos = Position(10, 15)
        game, enemy = _setup_game_with_enemy(GRUNT, enemy_pos)
        gmap = game.current_map

        _kill_enemy(enemy)
        game._end_turn()
        key = (enemy_pos.y, enemy_pos.x)
        corpse_after_first = dict(gmap.corpses)  # snapshot

        game._end_turn()
        # The corpse dict entry should be identical — no duplication / overwrite
        assert key in gmap.corpses, "Corpse disappeared after second _end_turn()."
        # Number of keys must stay the same.
        assert len(gmap.corpses) == len(corpse_after_first), (
            "Duplicate corpse entries created by second _end_turn() call."
        )


# ---------------------------------------------------------------------------
# Integration Tests — multi-component interaction
# ---------------------------------------------------------------------------

class TestDeathIntegrationViaGameHandle:
    """Integration: enemy death triggered through game.handle_input() path."""

    def test_grunt_ammo_drop_via_melee_kill(self):
        """Killing a Grunt via melee bump places shells at the Grunt's old position."""
        game = Game()
        game.new_game(seed=42)
        gmap = game.current_map

        # Place player and a near-dead Grunt adjacent.
        py, px = 10, 10
        ey, ex = 10, 11
        gmap.set_tile(py, px, TILE_FLOOR)
        gmap.set_tile(ey, ex, TILE_FLOOR)
        gmap.enemies.clear()

        enemy = Enemy.from_def(GRUNT, Position(ey, ex))
        enemy.health = 1  # dies in one hit
        gmap.enemies.append(enemy)
        game.player.pos = Position(py, px)

        game.handle_input('l')  # bump right → melee attack → kill

        assert not enemy.is_alive, "Enemy should have died from the melee hit."

        items_at_kill_pos = gmap.get_items_at(ey, ex)
        assert any(
            i.item_def.ammo_type == AmmoType.SHELLS for i in items_at_kill_pos
        ), (
            f"Expected shells on the ground at ({ey},{ex}) after Grunt was killed "
            f"via melee, but found: {[i.name for i in items_at_kill_pos]}"
        )

    def test_corpse_visible_in_render_state_after_melee_kill(self):
        """After a melee kill the render state shows '%' at the corpse position."""
        game = Game()
        game.new_game(seed=42)
        gmap = game.current_map

        py, px = 10, 10
        ey, ex = 10, 11
        gmap.set_tile(py, px, TILE_FLOOR)
        gmap.set_tile(ey, ex, TILE_FLOOR)
        gmap.enemies.clear()

        # Use a non-ammo-dropping enemy so no item covers the corpse char.
        enemy = Enemy.from_def(SHAMBLER, Position(ey, ex))
        enemy.health = 1
        gmap.enemies.append(enemy)
        game.player.pos = Position(py, px)
        gmap.explored.add((ey, ex))

        game.handle_input('l')  # kill Shambler

        # Move player away so we can see the corpse tile cleanly.
        game.player.pos = Position(py, px)
        gmap.explored.add((ey, ex))

        state = game.get_render_state()
        tile = state['map'][ey][ex]
        assert tile.get('char') == CORPSE_CHAR, (
            f"Expected '%' at corpse tile ({ey},{ex}) in render state, "
            f"got '{tile.get('char')}'."
        )

    def test_ammo_drop_is_pickupable_after_grunt_kill(self):
        """Integration: player can pick up the ammo dropped by a Grunt kill."""
        game = Game()
        game.new_game(seed=42)
        gmap = game.current_map

        py, px = 10, 10
        ey, ex = 10, 11
        gmap.set_tile(py, px, TILE_FLOOR)
        gmap.set_tile(ey, ex, TILE_FLOOR)
        gmap.enemies.clear()

        enemy = Enemy.from_def(GRUNT, Position(ey, ex))
        enemy.health = 1
        gmap.enemies.append(enemy)
        game.player.pos = Position(py, px)

        game.handle_input('l')  # kill Grunt, move player to (10,11)

        # Ensure ammo is present on the ground.
        items_here = gmap.get_items_at(ey, ex)
        assert len(items_here) > 0, (
            "No ammo on ground after Grunt kill — cannot test pick-up."
        )

        # Player should now be at (10,11) (or adjacent). Either way, pressing ','
        # while standing on the tile should pick up the ammo.
        if game.player.pos == Position(ey, ex):
            shells_before = game.player.inventory.get_ammo_count(AmmoType.SHELLS)
            game.handle_input(',')  # pick up
            shells_after = game.player.inventory.get_ammo_count(AmmoType.SHELLS)
            assert shells_after > shells_before, (
                "Player did not receive shells when picking up the Grunt's ammo drop."
            )

    def test_ogre_drops_rockets_via_melee_kill(self):
        """Integration: killing an Ogre via melee leaves rockets on the ground."""
        game = Game()
        game.new_game(seed=42)
        gmap = game.current_map

        py, px = 10, 10
        ey, ex = 10, 11
        gmap.set_tile(py, px, TILE_FLOOR)
        gmap.set_tile(ey, ex, TILE_FLOOR)
        gmap.enemies.clear()

        enemy = Enemy.from_def(OGRE, Position(ey, ex))
        enemy.health = 1
        gmap.enemies.append(enemy)
        game.player.pos = Position(py, px)

        game.handle_input('l')

        assert not enemy.is_alive, "Ogre should have died."

        items_at_kill_pos = gmap.get_items_at(ey, ex)
        assert any(
            i.item_def.ammo_type == AmmoType.ROCKETS for i in items_at_kill_pos
        ), (
            f"Expected rockets on the ground at ({ey},{ex}) after Ogre kill, "
            f"found: {[i.name for i in items_at_kill_pos]}"
        )
