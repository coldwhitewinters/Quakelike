"""Unit tests for quakelike.settings.GameSettings."""

import json
import os
import unittest.mock as mock

import pytest

from quakelike.settings import (
    GameSettings,
    DEFAULT_KEYBINDINGS,
    DEFAULT_GAME_OPTIONS,
)


class TestDefaultsReturnsAllRequiredActions:
    """GameSettings.defaults() populates every required action with its default key."""

    def test_defaults_returns_all_required_actions(self):
        settings = GameSettings.defaults()
        for action, expected_key in DEFAULT_KEYBINDINGS.items():
            assert action in settings.keybindings, (
                f"Action '{action}' missing from defaults()"
            )
            assert settings.keybindings[action] == expected_key, (
                f"Action '{action}': expected '{expected_key}', "
                f"got '{settings.keybindings[action]}'"
            )

    def test_defaults_returns_all_game_options(self):
        settings = GameSettings.defaults()
        for option, expected_value in DEFAULT_GAME_OPTIONS.items():
            assert option in settings.game_options, (
                f"Option '{option}' missing from defaults()"
            )
            assert settings.game_options[option] == expected_value, (
                f"Option '{option}': expected {expected_value!r}, "
                f"got {settings.game_options[option]!r}"
            )


class TestValidateRaisesOnDuplicateKeys:
    """validate() raises ValueError when two actions share the same key string."""

    def test_validate_raises_on_duplicate_keys(self):
        settings = GameSettings.defaults()
        # Map both move_up and move_down to 'j' (a conflict)
        settings.keybindings["move_up"] = "j"
        settings.keybindings["move_down"] = "j"
        with pytest.raises(ValueError, match="[Dd]uplicate"):
            settings.validate()

    def test_validate_raises_on_any_duplicate(self):
        settings = GameSettings.defaults()
        settings.keybindings["fire"] = settings.keybindings["inventory"]
        with pytest.raises(ValueError):
            settings.validate()

    def test_validate_passes_for_valid_defaults(self):
        settings = GameSettings.defaults()
        # Should not raise
        settings.validate()


class TestValidateRaisesOnEmptyKey:
    """validate() raises ValueError when any key string is empty or None."""

    def test_validate_raises_on_empty_key(self):
        settings = GameSettings.defaults()
        settings.keybindings["move_up"] = ""
        with pytest.raises(ValueError):
            settings.validate()

    def test_validate_raises_on_none_key(self):
        settings = GameSettings.defaults()
        settings.keybindings["move_up"] = None  # type: ignore[assignment]
        with pytest.raises(ValueError):
            settings.validate()

    def test_validate_raises_on_missing_required_action(self):
        settings = GameSettings.defaults()
        del settings.keybindings["move_up"]
        with pytest.raises(ValueError):
            settings.validate()


class TestLoadFromFileReturnsCorrectBindings:
    """GameSettings.load() reads keybindings from a JSON file."""

    def test_load_from_file_returns_correct_bindings(self, tmp_path):
        settings_file = str(tmp_path / "settings.json")
        custom = dict(DEFAULT_KEYBINDINGS)
        custom["move_up"] = "ArrowUp"
        with open(settings_file, "w") as f:
            json.dump({"keybindings": custom, "game_options": DEFAULT_GAME_OPTIONS}, f)

        with mock.patch("quakelike.settings.SETTINGS_PATH", settings_file):
            settings = GameSettings.load()

        assert settings.keybindings["move_up"] == "ArrowUp", (
            "load() must return the keybinding stored in the file"
        )

    def test_load_returns_defaults_when_file_absent(self, tmp_path):
        missing = str(tmp_path / "no_such_file.json")
        with mock.patch("quakelike.settings.SETTINGS_PATH", missing):
            settings = GameSettings.load()

        assert settings.keybindings == DEFAULT_KEYBINDINGS

    def test_load_returns_defaults_for_malformed_json(self, tmp_path):
        bad_file = str(tmp_path / "bad.json")
        with open(bad_file, "w") as f:
            f.write("{not valid json!!!")
        with mock.patch("quakelike.settings.SETTINGS_PATH", bad_file):
            settings = GameSettings.load()

        assert settings.keybindings["move_up"] == DEFAULT_KEYBINDINGS["move_up"]


class TestSaveAndLoadRoundtrip:
    """GameSettings.save() + load() round-trips all fields without loss."""

    def test_save_and_load_roundtrip(self, tmp_path):
        settings_file = str(tmp_path / "settings.json")
        original = GameSettings.defaults()
        original.keybindings["move_up"] = "ArrowUp"
        original.game_options["animation_speed_ms"] = 60

        with mock.patch("quakelike.settings.SETTINGS_PATH", settings_file):
            original.save()
            loaded = GameSettings.load()

        assert loaded.keybindings["move_up"] == "ArrowUp"
        assert loaded.game_options["animation_speed_ms"] == 60

    def test_save_writes_valid_json(self, tmp_path):
        settings_file = str(tmp_path / "settings.json")
        settings = GameSettings.defaults()

        with mock.patch("quakelike.settings.SETTINGS_PATH", settings_file):
            settings.save()

        assert os.path.exists(settings_file)
        with open(settings_file) as f:
            data = json.load(f)
        assert "keybindings" in data
        assert "game_options" in data


class TestFromDictFillsMissingActionsWithDefaults:
    """from_dict() fills any missing required actions with DEFAULT_KEYBINDINGS values."""

    def test_from_dict_fills_missing_actions_with_defaults(self):
        # Provide a dict that is missing 'move_up'
        incomplete = {
            "keybindings": {k: v for k, v in DEFAULT_KEYBINDINGS.items() if k != "move_up"},
            "game_options": DEFAULT_GAME_OPTIONS,
        }
        settings = GameSettings.from_dict(incomplete)
        # Missing action must be filled from defaults
        assert settings.keybindings.get("move_up") == DEFAULT_KEYBINDINGS["move_up"], (
            "from_dict() must fill missing actions with their default bindings"
        )

    def test_from_dict_preserves_overridden_value(self):
        custom = dict(DEFAULT_KEYBINDINGS)
        custom["move_up"] = "ArrowUp"
        settings = GameSettings.from_dict({"keybindings": custom, "game_options": {}})
        assert settings.keybindings["move_up"] == "ArrowUp"

    def test_from_dict_fills_missing_game_options_with_defaults(self):
        settings = GameSettings.from_dict({"keybindings": DEFAULT_KEYBINDINGS, "game_options": {}})
        for option, expected in DEFAULT_GAME_OPTIONS.items():
            assert settings.game_options[option] == expected


class TestGetMovementDirection:
    """GameSettings.get_movement_direction() maps keys to (dy, dx) vectors."""

    def test_default_move_up_returns_correct_direction(self):
        settings = GameSettings.defaults()
        assert settings.get_movement_direction("k") == (-1, 0)

    def test_remapped_key_returns_correct_direction(self):
        settings = GameSettings.defaults()
        settings.keybindings["move_up"] = "ArrowUp"
        assert settings.get_movement_direction("ArrowUp") == (-1, 0)

    def test_old_key_returns_none_after_remap(self):
        settings = GameSettings.defaults()
        settings.keybindings["move_up"] = "ArrowUp"
        assert settings.get_movement_direction("k") is None

    def test_unbound_key_returns_none(self):
        settings = GameSettings.defaults()
        assert settings.get_movement_direction("z") is None

    def test_all_default_movement_directions(self):
        settings = GameSettings.defaults()
        expected = {
            "k": (-1, 0),
            "j": (1, 0),
            "h": (0, -1),
            "l": (0, 1),
            "u": (-1, 1),
            "y": (-1, -1),
            "n": (1, 1),
            "b": (1, -1),
        }
        for key, direction in expected.items():
            assert settings.get_movement_direction(key) == direction, (
                f"Default key '{key}' must map to direction {direction}"
            )
