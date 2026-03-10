"""Acceptance and integration tests for the multi-save system.

These tests define the behavioral contract for the multi-save feature and are
expected to FAIL (red phase) until the feature is implemented.

Feature summary:
- Each Game instance has a unique `game_id` (UUID string).
- Saves are stored as `saves/game_{id}.json` (not `saves/savegame.json`).
- `handle_input('S')` saves the game and returns a render state with
  `goto_menu: True` so the frontend can return to the main menu.
- `load_game(game_id)` loads a specific save by ID.
- `list_saves(saves_dir)` (module-level function in quakelike.game) scans a
  saves directory and returns a list of dicts with at least `{id, display_name}`.
- `Game.quit_without_save()` deletes the save file.
- Permadeath on death deletes only *that* game's save file.
- The module-level constant `SAVES_DIR` controls where saves are written.
"""

import json
import os
import tempfile
import unittest.mock as mock

import pytest

from quakelike.game import Game, GameState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_saves_dir(saves_dir: str):
    """Return a context manager that redirects SAVES_DIR to *saves_dir*.

    Uses create=True so the patch works both before and after SAVES_DIR is
    added to the module — before implementation the attribute does not exist
    yet, so create=True prevents an AttributeError and lets the test reach
    its actual assertion.
    """
    return mock.patch("quakelike.game.SAVES_DIR", saves_dir, create=True)


# ---------------------------------------------------------------------------
# Acceptance Tests
# ---------------------------------------------------------------------------

class TestMultiSaveAcceptance:
    """Acceptance tests — each covers one observable behaviour of the feature."""

    # ------------------------------------------------------------------
    # 1. Game identity
    # ------------------------------------------------------------------

    def test_game_has_unique_id(self):
        """A new game has a non-empty game_id; two games have different IDs."""
        game1 = Game()
        game1.new_game(seed=1)
        game2 = Game()
        game2.new_game(seed=2)

        assert hasattr(game1, "game_id"), "Game must have a game_id attribute"
        assert isinstance(game1.game_id, str), "game_id must be a string"
        assert game1.game_id, "game_id must not be empty"
        assert game1.game_id != game2.game_id, (
            "Two different game instances must have different game_ids"
        )

    # ------------------------------------------------------------------
    # 2. Save creates per-ID file (not legacy savegame.json)
    # ------------------------------------------------------------------

    def test_save_creates_named_file(self):
        """handle_input('S') writes saves/game_{id}.json, not saves/savegame.json."""
        game = Game()
        game.new_game(seed=42)

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                game.handle_input("S")

            # game_id must exist for the path assertions to be meaningful
            assert hasattr(game, "game_id"), "Game must have a game_id attribute"

            expected_path = os.path.join(saves_dir, f"game_{game.game_id}.json")
            legacy_path = os.path.join(saves_dir, "savegame.json")

            assert os.path.exists(expected_path), (
                f"Expected save file at {expected_path}"
            )
            assert not os.path.exists(legacy_path), (
                "Legacy saves/savegame.json must NOT be created by the new system"
            )

    # ------------------------------------------------------------------
    # 3. Save returns goto_menu flag
    # ------------------------------------------------------------------

    def test_save_returns_goto_menu(self):
        """handle_input('S') must return a render state with goto_menu=True."""
        game = Game()
        game.new_game(seed=42)

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                state = game.handle_input("S")

        assert "goto_menu" in state, (
            "Render state returned by 'S' must contain goto_menu key"
        )
        assert state["goto_menu"] is True, (
            "goto_menu must be True after saving so frontend returns to menu"
        )

    # ------------------------------------------------------------------
    # 4. Multiple games can be saved simultaneously
    # ------------------------------------------------------------------

    def test_multiple_games_saved_simultaneously(self):
        """Two games can be saved; both save files co-exist independently."""
        game_a = Game()
        game_a.new_game(seed=10)
        game_b = Game()
        game_b.new_game(seed=20)

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                game_a.handle_input("S")
                game_b.handle_input("S")

            assert hasattr(game_a, "game_id"), "game_a must have a game_id"
            assert hasattr(game_b, "game_id"), "game_b must have a game_id"

            path_a = os.path.join(saves_dir, f"game_{game_a.game_id}.json")
            path_b = os.path.join(saves_dir, f"game_{game_b.game_id}.json")

            assert os.path.exists(path_a), "Save file for game A must exist"
            assert os.path.exists(path_b), "Save file for game B must exist"
            assert path_a != path_b, "Each game's save file must be distinct"

    # ------------------------------------------------------------------
    # 5. load_game(game_id) loads the correct game
    # ------------------------------------------------------------------

    def test_load_game_by_id(self):
        """load_game(game_id) loads the specific save identified by that ID."""
        original = Game()
        original.new_game(seed=42)

        assert hasattr(original, "game_id"), "Game must have a game_id attribute"
        original_id = original.game_id

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                original.handle_input("S")

                loaded = Game()
                success = loaded.load_game(original_id)

        assert success is True, "load_game must return True on success"
        assert hasattr(loaded, "game_id"), "Loaded game must have game_id"
        assert loaded.game_id == original_id, (
            "Loaded game's game_id must match the requested ID"
        )

    # ------------------------------------------------------------------
    # 6. load_game restores actual gameplay state
    # ------------------------------------------------------------------

    def test_load_game_restores_state(self):
        """State (player pos and turn count) is faithfully restored after load."""
        from quakelike.entity import Position
        from quakelike.constants import TILE_FLOOR

        game = Game()
        game.new_game(seed=42)

        # Advance state beyond the default start by making at least one move.
        gmap = game.current_map
        for y in range(gmap.height):
            for x in range(gmap.width):
                if (gmap.get_tile(y, x) == TILE_FLOOR
                        and gmap.get_tile(y, x + 1) == TILE_FLOOR
                        and gmap.get_enemy_at(y, x) is None
                        and gmap.get_enemy_at(y, x + 1) is None):
                    game.player.pos = Position(y, x)
                    game.handle_input("l")  # move right — advances turn
                    break
            else:
                continue
            break

        saved_turn = game.turn
        saved_pos = (game.player.pos.y, game.player.pos.x)

        assert hasattr(game, "game_id"), "Game must have a game_id attribute"
        saved_id = game.game_id

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                game.handle_input("S")

                loaded = Game()
                loaded.load_game(saved_id)

        assert loaded.turn == saved_turn, (
            f"Turn count should be {saved_turn}, got {loaded.turn}"
        )
        assert (loaded.player.pos.y, loaded.player.pos.x) == saved_pos, (
            f"Player position should be {saved_pos}"
        )

    # ------------------------------------------------------------------
    # 7. Death deletes only *this* game's save, not others
    # ------------------------------------------------------------------

    def test_death_deletes_specific_save(self):
        """Player death removes only that game's save file; other saves survive."""
        dying_game = Game()
        dying_game.new_game(seed=1)
        survivor_game = Game()
        survivor_game.new_game(seed=2)

        assert hasattr(dying_game, "game_id"), "dying_game must have a game_id"
        assert hasattr(survivor_game, "game_id"), "survivor_game must have a game_id"

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                dying_game.handle_input("S")
                survivor_game.handle_input("S")

                dying_path = os.path.join(
                    saves_dir, f"game_{dying_game.game_id}.json"
                )
                survivor_path = os.path.join(
                    saves_dir, f"game_{survivor_game.game_id}.json"
                )

                assert os.path.exists(dying_path), "Setup: dying game must be saved"
                assert os.path.exists(survivor_path), "Setup: survivor must be saved"

                # Kill the dying game's player
                dying_game.player.health = 1
                dying_game.player.take_damage(999)
                dying_game._end_turn()

            assert dying_game.state == GameState.GAME_OVER
            assert not os.path.exists(dying_path), (
                "Dying game's save file must be deleted on permadeath"
            )
            assert os.path.exists(survivor_path), (
                "Survivor game's save file must NOT be affected by another game's death"
            )

    # ------------------------------------------------------------------
    # 8. list_saves returns all current saves
    # ------------------------------------------------------------------

    def test_list_saves_returns_all_saves(self):
        """list_saves() returns one entry per saved game with required fields."""
        # Import is attempted inside the test so that an ImportError becomes a
        # clear FAILED test rather than a collection error.
        try:
            from quakelike.game import list_saves
        except ImportError:
            pytest.fail(
                "list_saves could not be imported from quakelike.game — "
                "implement it as a module-level function"
            )

        game_a = Game()
        game_a.new_game(seed=10)
        game_b = Game()
        game_b.new_game(seed=20)

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                game_a.handle_input("S")
                game_b.handle_input("S")

            saves = list_saves(saves_dir)

        assert isinstance(saves, list), "list_saves must return a list"
        assert len(saves) == 2, f"Expected 2 saves, got {len(saves)}"

        assert hasattr(game_a, "game_id") and hasattr(game_b, "game_id"), (
            "Games must have game_id for ID comparison"
        )
        ids_found = {s["id"] for s in saves}
        assert game_a.game_id in ids_found, "game_a's ID must appear in list_saves"
        assert game_b.game_id in ids_found, "game_b's ID must appear in list_saves"

        for entry in saves:
            assert "id" in entry, "Each save entry must have an 'id' field"
            assert "display_name" in entry, (
                "Each save entry must have a 'display_name' field"
            )

    # ------------------------------------------------------------------
    # 9. quit_without_save deletes the save file
    # ------------------------------------------------------------------

    def test_quit_without_save_deletes_save(self):
        """quit_without_save() deletes the game's save file."""
        game = Game()
        game.new_game(seed=42)

        assert hasattr(game, "game_id"), "Game must have a game_id attribute"

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                game.handle_input("S")
                save_path = os.path.join(saves_dir, f"game_{game.game_id}.json")
                assert os.path.exists(save_path), "Setup: save must exist first"

                assert hasattr(game, "quit_without_save"), (
                    "Game must have a quit_without_save() method"
                )
                game.quit_without_save()

            assert not os.path.exists(save_path), (
                "Save file must be deleted after quit_without_save()"
            )

    # ------------------------------------------------------------------
    # 10. Save file JSON contains game_id field
    # ------------------------------------------------------------------

    def test_save_file_contains_game_id(self):
        """The JSON written to disk must include a 'game_id' field."""
        game = Game()
        game.new_game(seed=42)

        assert hasattr(game, "game_id"), "Game must have a game_id attribute"

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                game.handle_input("S")

            save_path = os.path.join(saves_dir, f"game_{game.game_id}.json")
            assert os.path.exists(save_path), (
                "Save file must exist at the per-ID path"
            )
            with open(save_path) as f:
                data = json.load(f)

        assert "game_id" in data, "Save file JSON must contain a 'game_id' field"
        assert data["game_id"] == game.game_id, (
            "game_id in save file must match game.game_id"
        )


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestMultiSaveIntegration:
    """Integration tests — verify component interactions across the save boundary."""

    # ------------------------------------------------------------------
    # 11. Reloading a game preserves its game_id end-to-end
    # ------------------------------------------------------------------

    def test_save_and_reload_preserves_game_id(self):
        """Full round-trip: save → load by game_id → loaded game has same ID."""
        original = Game()
        original.new_game(seed=99)

        assert hasattr(original, "game_id"), "Game must have a game_id attribute"
        original_id = original.game_id

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                original.handle_input("S")

                reloaded = Game()
                success = reloaded.load_game(original_id)

        assert success, "load_game must succeed for a valid saved game"
        assert hasattr(reloaded, "game_id"), "Reloaded game must have game_id"
        assert reloaded.game_id == original_id, (
            "After reload, game_id must be identical to the original"
        )
        # Sanity: it's still the same player state
        assert reloaded.player is not None
        assert reloaded.player.health == original.player.health

    # ------------------------------------------------------------------
    # 12. Two games are fully independent — deleting one doesn't touch the other
    # ------------------------------------------------------------------

    def test_different_games_independent(self):
        """Deleting game A's save file has no effect on game B's save file."""
        game_a = Game()
        game_a.new_game(seed=11)
        game_b = Game()
        game_b.new_game(seed=22)

        assert hasattr(game_a, "game_id"), "game_a must have a game_id"
        assert hasattr(game_b, "game_id"), "game_b must have a game_id"

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                game_a.handle_input("S")
                game_b.handle_input("S")

            path_a = os.path.join(saves_dir, f"game_{game_a.game_id}.json")
            path_b = os.path.join(saves_dir, f"game_{game_b.game_id}.json")

            assert os.path.exists(path_a), "Setup: game A must be saved"
            assert os.path.exists(path_b), "Setup: game B must be saved"

            # Manually remove game A's file (simulating its deletion)
            os.remove(path_a)

            assert not os.path.exists(path_a), "game A's save must be gone"
            assert os.path.exists(path_b), (
                "game B's save must be completely unaffected by game A's deletion"
            )

            # Verify game B can still be loaded cleanly
            with _patch_saves_dir(saves_dir):
                loaded_b = Game()
                success = loaded_b.load_game(game_b.game_id)

        assert success, "game B must still load successfully after game A is deleted"
        assert loaded_b.game_id == game_b.game_id
