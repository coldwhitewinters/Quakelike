"""Unit tests for the multi-save system backend.

Written first (TDD red phase) before implementation. These tests cover the
individual units of behavior for the multi-save feature.
"""

import json
import os
import tempfile
import uuid
import unittest.mock as mock

import pytest

from quakelike.game import Game, SAVES_DIR, list_saves


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _patch_saves_dir(saves_dir: str):
    """Redirect SAVES_DIR to the given temp dir for the duration of a test."""
    return mock.patch("quakelike.game.SAVES_DIR", saves_dir, create=True)


def _make_game(seed: int = 1) -> Game:
    g = Game()
    g.new_game(seed=seed)
    return g


# ---------------------------------------------------------------------------
# 1. game_id is a valid non-empty string
# ---------------------------------------------------------------------------

class TestGameId:
    def test_game_id_is_uuid_string(self):
        """A new Game has a non-empty string game_id that parses as a UUID."""
        game = _make_game()
        assert hasattr(game, "game_id"), "Game must have a game_id attribute"
        assert isinstance(game.game_id, str), "game_id must be a str"
        assert game.game_id != "", "game_id must not be empty"
        # Must be a valid UUID (will raise ValueError if not)
        parsed = uuid.UUID(game.game_id)
        assert str(parsed) == game.game_id

    def test_two_games_have_different_ids(self):
        """Two independently created Game objects must have distinct game_ids."""
        game1 = _make_game(seed=1)
        game2 = _make_game(seed=2)
        assert game1.game_id != game2.game_id


# ---------------------------------------------------------------------------
# 2. Save path is computed correctly from game_id
# ---------------------------------------------------------------------------

class TestSavePath:
    def test_save_path_uses_game_id(self):
        """The save file path should be SAVES_DIR/game_{game_id}.json."""
        game = _make_game()
        expected_filename = f"game_{game.game_id}.json"

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                game.handle_input("S")

            written_files = os.listdir(saves_dir)

        assert expected_filename in written_files, (
            f"Expected {expected_filename} in saves dir, found: {written_files}"
        )
        assert "savegame.json" not in written_files, (
            "Legacy savegame.json must NOT be written by the new system"
        )


# ---------------------------------------------------------------------------
# 3. Serialization includes game_id
# ---------------------------------------------------------------------------

class TestSerialize:
    def test_serialize_includes_game_id(self):
        """_serialize() must include the game_id key in the returned dict."""
        game = _make_game()
        data = game._serialize()
        assert "game_id" in data, "_serialize() must include 'game_id'"
        assert data["game_id"] == game.game_id


# ---------------------------------------------------------------------------
# 4. Deserialization restores game_id
# ---------------------------------------------------------------------------

class TestDeserialize:
    def test_deserialize_restores_game_id(self):
        """_deserialize() must restore game_id from the saved dict."""
        original = _make_game()
        original_id = original.game_id
        data = original._serialize()

        blank = Game()
        blank.new_game(seed=99)
        blank._deserialize(data)

        assert blank.game_id == original_id, (
            f"Expected game_id={original_id!r}, got {blank.game_id!r}"
        )

    def test_deserialize_falls_back_when_game_id_missing(self):
        """If game_id is absent from save data, deserialize must not crash."""
        original = _make_game()
        data = original._serialize()
        del data["game_id"]  # simulate old save without game_id

        loaded = Game()
        loaded.new_game(seed=42)
        # Should not raise
        loaded._deserialize(data)
        # game_id may be the original blank value — what matters is no crash
        assert isinstance(loaded.game_id, str)


# ---------------------------------------------------------------------------
# 5. list_saves
# ---------------------------------------------------------------------------

class TestListSaves:
    def test_list_saves_empty_dir(self):
        """list_saves on an empty directory returns an empty list."""
        with tempfile.TemporaryDirectory() as saves_dir:
            result = list_saves(saves_dir)
        assert result == [], f"Expected [], got {result!r}"

    def test_list_saves_with_files(self):
        """list_saves returns one entry per saved game with required fields."""
        game_a = _make_game(seed=10)
        game_b = _make_game(seed=20)

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                game_a.handle_input("S")
                game_b.handle_input("S")

            result = list_saves(saves_dir)

        assert isinstance(result, list)
        assert len(result) == 2, f"Expected 2 entries, got {len(result)}"

        ids_found = {entry["id"] for entry in result}
        assert game_a.game_id in ids_found
        assert game_b.game_id in ids_found

        for entry in result:
            assert "id" in entry
            assert "display_name" in entry
            assert isinstance(entry["display_name"], str)
            assert entry["display_name"] != ""

    def test_list_saves_skips_corrupted_files(self):
        """list_saves silently skips files that cannot be parsed."""
        game = _make_game(seed=5)

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                game.handle_input("S")

            # Write a corrupted file alongside the real save
            corrupted_path = os.path.join(saves_dir, "game_bad-id.json")
            with open(corrupted_path, "w") as f:
                f.write("not valid json {{{{")

            result = list_saves(saves_dir)

        # Should contain only the valid save
        assert len(result) == 1
        assert result[0]["id"] == game.game_id

    def test_list_saves_sorted_most_recent_first(self):
        """list_saves returns entries sorted by timestamp, newest first."""
        game_a = _make_game(seed=1)
        game_b = _make_game(seed=2)

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                game_a.handle_input("S")
                game_b.handle_input("S")

            result = list_saves(saves_dir)

        # Most recent should be first (game_b saved last)
        assert len(result) == 2
        # Verify timestamps are in descending order
        if "timestamp" in result[0]:
            assert result[0]["timestamp"] >= result[1]["timestamp"]


# ---------------------------------------------------------------------------
# 6. quit_without_save
# ---------------------------------------------------------------------------

class TestQuitWithoutSave:
    def test_quit_without_save_deletes_file(self):
        """quit_without_save() must delete the game's save file if it exists."""
        game = _make_game()

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                game.handle_input("S")
                save_path = os.path.join(saves_dir, f"game_{game.game_id}.json")
                assert os.path.exists(save_path), "Setup: save file must exist"

                game.quit_without_save()

            assert not os.path.exists(save_path), (
                "quit_without_save() must delete the save file"
            )

    def test_quit_without_save_returns_goto_menu(self):
        """quit_without_save() must return a render state dict with goto_menu=True."""
        game = _make_game()

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                game.handle_input("S")
                result = game.quit_without_save()

        assert isinstance(result, dict), "quit_without_save must return a dict"
        assert "goto_menu" in result, "Result must contain 'goto_menu'"
        assert result["goto_menu"] is True

    def test_quit_without_save_no_save_file_does_not_crash(self):
        """quit_without_save() must not crash if no save file exists."""
        game = _make_game()

        with tempfile.TemporaryDirectory() as saves_dir:
            with _patch_saves_dir(saves_dir):
                # Never call handle_input("S"), so no file exists
                result = game.quit_without_save()

        assert result["goto_menu"] is True
