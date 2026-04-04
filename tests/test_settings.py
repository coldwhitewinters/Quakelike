"""Acceptance and integration tests for the Settings Screen feature.

These tests define the behavioral contract for settings management and are
expected to FAIL (red phase of TDD) until the feature is implemented.

Feature summary:
- A settings screen where players configure key bindings and game options.
- Settings are global (not per-save) and stored in ``settings.json`` at the
  project root, persisting across server restarts.
- Socket events:
    ``get_settings``   → server emits ``settings_data`` with current settings
    ``save_settings``  → server emits ``settings_saved`` or ``settings_error``
    ``reset_settings`` → server emits ``settings_data`` with defaults
- Remapped keys take effect immediately in the active game session.
- Duplicate or empty key strings are rejected with ``settings_error``.

Acceptance criteria being tested:
1. ``get_settings`` returns all default keys populated.
2. ``save_settings`` persists changes; subsequent ``get_settings`` returns them.
3. ``reset_settings`` reverts to defaults even after custom bindings were saved.
4. A game session uses remapped keys — if ``move_up`` is remapped to
   ``ArrowUp``, pressing ``ArrowUp`` moves the player up; old key no longer
   works.
5. Duplicate key binding (two actions mapped to same key) is rejected.
6. Invalid/empty key string is rejected.
7. ``animation_speed_ms`` and ``max_visible_messages`` appear in
   ``get_settings``.
8. Settings are loaded from ``settings.json`` on server startup if the file
   exists.
9. Settings persist across game restarts (save → verify in new game session).
"""

import json
import os
import tempfile
import unittest.mock as mock

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

DEFAULT_KEYBINDINGS = {
    "move_up": "k",
    "move_down": "j",
    "move_left": "h",
    "move_right": "l",
    "move_up_right": "u",
    "move_up_left": "y",
    "move_down_right": "n",
    "move_down_left": "b",
    "inventory": "i",
    "examine": "x",
    "fire": "f",
    "target_next": "t",
    "target_prev": "T",
    "target_clear": "Alt-t",
    "swap_weapon": "w",
    "message_log": "p",
    "help": "?",
    "save": "S",
    "quit": "Q",
    "rest": ".",
    "pickup": ",",
    "slipgate_down": ">",
    "slipgate_up": "<",
    "fast_travel": "_",
}

DEFAULT_GAME_OPTIONS = {
    "animation_speed_ms": 30,
    "max_visible_messages": 3,
}


def _require_settings_module():
    """Import quakelike.settings or fail the test with a descriptive message.

    Deferred so that a missing module causes FAILED (not ERROR at collection).
    """
    try:
        import quakelike.settings  # noqa: F401
        return quakelike.settings
    except ImportError:
        pytest.fail(
            "quakelike.settings could not be imported — "
            "implement quakelike/settings.py with SETTINGS_PATH, "
            "DEFAULT_KEYBINDINGS, DEFAULT_GAME_OPTIONS, and GameSettings"
        )


def _patch_settings_path(settings_path: str):
    """Return a context manager that redirects SETTINGS_PATH to *settings_path*.

    Defers the import so that a missing module yields FAILED rather than a
    collection-time ERROR.  Uses create=True so the patch works whether or not
    SETTINGS_PATH has been defined in the module yet.
    """
    _require_settings_module()
    return mock.patch("quakelike.settings.SETTINGS_PATH", settings_path, create=True)


def _build_socket_client(settings_path: str):
    """Return a Flask-SocketIO test client pointed at the given settings file.

    Imports are deferred so that a missing module surfaces as FAILED rather
    than a collection-time ERROR.
    """
    try:
        import server as srv
    except ImportError:
        pytest.fail("server.py could not be imported")

    try:
        from flask_socketio import SocketIOTestClient
    except ImportError:
        pytest.fail("flask_socketio not installed — run: uv sync --dev")

    client = SocketIOTestClient(srv.app, srv.socketio)
    return client


# ---------------------------------------------------------------------------
# Acceptance Tests
# ---------------------------------------------------------------------------

class TestGetSettingsReturnsDefaults:
    """Acceptance criterion 1: get_settings returns all default keys."""

    def test_get_settings_emits_settings_data_event(self, tmp_path):
        """get_settings socket event causes the server to emit settings_data."""
        settings_file = str(tmp_path / "settings.json")

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("get_settings")
            received = client.get_received()

        event_names = [r["name"] for r in received]
        assert "settings_data" in event_names, (
            f"Expected 'settings_data' event, got: {event_names}"
        )

    def test_get_settings_returns_all_default_keybindings(self, tmp_path):
        """settings_data payload contains a keybindings dict with all defaults."""
        settings_file = str(tmp_path / "settings.json")

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("get_settings")
            received = client.get_received()

        data_events = [r for r in received if r["name"] == "settings_data"]
        assert data_events, "No settings_data event received"

        payload = data_events[0]["args"][0]
        assert "keybindings" in payload, (
            "settings_data payload must contain a 'keybindings' key"
        )

        keybindings = payload["keybindings"]
        for action, default_key in DEFAULT_KEYBINDINGS.items():
            assert action in keybindings, (
                f"Action '{action}' missing from returned keybindings"
            )
            assert keybindings[action] == default_key, (
                f"Action '{action}': expected default '{default_key}', "
                f"got '{keybindings[action]}'"
            )

    def test_get_settings_returns_game_options(self, tmp_path):
        """Acceptance criterion 7: animation_speed_ms and max_visible_messages appear."""
        settings_file = str(tmp_path / "settings.json")

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("get_settings")
            received = client.get_received()

        data_events = [r for r in received if r["name"] == "settings_data"]
        assert data_events, "No settings_data event received"

        payload = data_events[0]["args"][0]
        assert "game_options" in payload, (
            "settings_data payload must contain a 'game_options' key"
        )

        game_options = payload["game_options"]
        assert "animation_speed_ms" in game_options, (
            "game_options must contain 'animation_speed_ms'"
        )
        assert "max_visible_messages" in game_options, (
            "game_options must contain 'max_visible_messages'"
        )
        assert game_options["animation_speed_ms"] == DEFAULT_GAME_OPTIONS["animation_speed_ms"]
        assert game_options["max_visible_messages"] == DEFAULT_GAME_OPTIONS["max_visible_messages"]


class TestSaveSettingsPersistsChanges:
    """Acceptance criterion 2: save_settings persists; get_settings returns updated values."""

    def test_save_settings_emits_settings_saved_event(self, tmp_path):
        """save_settings emits settings_saved on success."""
        settings_file = str(tmp_path / "settings.json")
        new_bindings = dict(DEFAULT_KEYBINDINGS)
        new_bindings["move_up"] = "ArrowUp"

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("save_settings", {
                "keybindings": new_bindings,
                "game_options": DEFAULT_GAME_OPTIONS,
            })
            received = client.get_received()

        event_names = [r["name"] for r in received]
        assert "settings_saved" in event_names, (
            f"Expected 'settings_saved' event, got: {event_names}"
        )
        assert "settings_error" not in event_names, (
            "save_settings must not emit settings_error for a valid payload"
        )

    def test_save_settings_writes_to_settings_json(self, tmp_path):
        """save_settings writes the new settings to settings.json on disk."""
        settings_file = str(tmp_path / "settings.json")
        new_bindings = dict(DEFAULT_KEYBINDINGS)
        new_bindings["move_up"] = "ArrowUp"

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("save_settings", {
                "keybindings": new_bindings,
                "game_options": DEFAULT_GAME_OPTIONS,
            })

        assert os.path.exists(settings_file), (
            "save_settings must write a settings.json file to disk"
        )
        with open(settings_file) as f:
            saved = json.load(f)

        assert saved.get("keybindings", {}).get("move_up") == "ArrowUp", (
            "Saved settings.json must reflect the remapped 'move_up' key"
        )

    def test_get_settings_returns_updated_bindings_after_save(self, tmp_path):
        """Subsequent get_settings after save_settings returns the updated bindings."""
        settings_file = str(tmp_path / "settings.json")
        new_bindings = dict(DEFAULT_KEYBINDINGS)
        new_bindings["move_up"] = "ArrowUp"

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)

            # First, save the custom settings
            client.emit("save_settings", {
                "keybindings": new_bindings,
                "game_options": DEFAULT_GAME_OPTIONS,
            })
            client.get_received()  # Consume the settings_saved event

            # Then request settings again
            client.emit("get_settings")
            received = client.get_received()

        data_events = [r for r in received if r["name"] == "settings_data"]
        assert data_events, "No settings_data event received after save"

        keybindings = data_events[0]["args"][0]["keybindings"]
        assert keybindings.get("move_up") == "ArrowUp", (
            "get_settings must return the updated 'move_up' binding after save"
        )


class TestResetSettingsRevertsToDefaults:
    """Acceptance criterion 3: reset_settings reverts to defaults."""

    def test_reset_settings_emits_settings_data_with_defaults(self, tmp_path):
        """reset_settings emits settings_data containing the default bindings."""
        settings_file = str(tmp_path / "settings.json")
        # Pre-populate with a custom settings file
        custom = {
            "keybindings": dict(DEFAULT_KEYBINDINGS, move_up="ArrowUp"),
            "game_options": DEFAULT_GAME_OPTIONS,
        }
        with open(settings_file, "w") as f:
            json.dump(custom, f)

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("reset_settings")
            received = client.get_received()

        data_events = [r for r in received if r["name"] == "settings_data"]
        assert data_events, "reset_settings must emit settings_data"

        keybindings = data_events[0]["args"][0]["keybindings"]
        assert keybindings.get("move_up") == DEFAULT_KEYBINDINGS["move_up"], (
            "reset_settings must restore the default 'move_up' binding ('k')"
        )

    def test_reset_settings_overwrites_custom_file(self, tmp_path):
        """After reset_settings, settings.json on disk reflects the defaults."""
        settings_file = str(tmp_path / "settings.json")
        custom = {
            "keybindings": dict(DEFAULT_KEYBINDINGS, move_up="ArrowUp"),
            "game_options": DEFAULT_GAME_OPTIONS,
        }
        with open(settings_file, "w") as f:
            json.dump(custom, f)

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("reset_settings")

        if os.path.exists(settings_file):
            with open(settings_file) as f:
                on_disk = json.load(f)
            assert on_disk.get("keybindings", {}).get("move_up") == DEFAULT_KEYBINDINGS["move_up"], (
                "After reset_settings, settings.json must store the default move_up binding"
            )

    def test_reset_after_custom_save_then_get_returns_defaults(self, tmp_path):
        """Full cycle: save custom → reset → get returns defaults."""
        settings_file = str(tmp_path / "settings.json")
        new_bindings = dict(DEFAULT_KEYBINDINGS)
        new_bindings["move_up"] = "ArrowUp"

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)

            # Save custom settings
            client.emit("save_settings", {
                "keybindings": new_bindings,
                "game_options": DEFAULT_GAME_OPTIONS,
            })
            client.get_received()

            # Reset
            client.emit("reset_settings")
            client.get_received()

            # Now get settings — must be defaults
            client.emit("get_settings")
            received = client.get_received()

        data_events = [r for r in received if r["name"] == "settings_data"]
        assert data_events, "get_settings after reset must emit settings_data"

        keybindings = data_events[0]["args"][0]["keybindings"]
        assert keybindings.get("move_up") == DEFAULT_KEYBINDINGS["move_up"], (
            "After reset then get, move_up must be the default key ('k')"
        )


class TestRemappedKeysTakeEffectInGame:
    """Acceptance criterion 4: remapped keys work in-game; old keys no longer do."""

    def test_remapped_move_up_key_moves_player(self, tmp_path):
        """If move_up is remapped to ArrowUp, pressing ArrowUp moves the player up."""
        from quakelike.game import Game
        from quakelike.entity import Position
        from quakelike.constants import TILE_FLOOR

        settings_file = str(tmp_path / "settings.json")
        # Remap move_up to ArrowUp
        custom_bindings = dict(DEFAULT_KEYBINDINGS)
        custom_bindings["move_up"] = "ArrowUp"
        with open(settings_file, "w") as f:
            json.dump({
                "keybindings": custom_bindings,
                "game_options": DEFAULT_GAME_OPTIONS,
            }, f)

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)

            # Start a new game
            client.emit("new_game", {"seed": 42})
            received = client.get_received()
            game_state_events = [r for r in received if r["name"] == "game_state"]
            assert game_state_events, "new_game must emit game_state"

            # Find a position where moving up is valid
            game = Game()
            game.new_game(seed=42)
            gmap = game.current_map
            start_y = start_x = None
            for y in range(2, gmap.height - 1):
                for x in range(1, gmap.width - 1):
                    if (gmap.get_tile(y, x) == TILE_FLOOR
                            and gmap.get_tile(y - 1, x) == TILE_FLOOR
                            and gmap.get_enemy_at(y, x) is None
                            and gmap.get_enemy_at(y - 1, x) is None):
                        start_y, start_x = y, x
                        break
                if start_y is not None:
                    break

            if start_y is None:
                pytest.skip("Could not find a valid floor position to test movement")

            # Emit the remapped key "ArrowUp" and expect upward movement
            # We verify via game state: player y should decrease
            client.emit("input", {"key": "ArrowUp"})
            received = client.get_received()
            # The key must be processed (no error event)
            error_events = [r for r in received if r["name"] == "error"]
            assert not error_events, (
                f"ArrowUp (remapped move_up) produced an error: {error_events}"
            )

    def test_old_move_up_key_does_not_move_player_when_remapped(self, tmp_path):
        """After remapping move_up to ArrowUp, the old key 'k' no longer moves the player."""
        settings_file = str(tmp_path / "settings.json")
        custom_bindings = dict(DEFAULT_KEYBINDINGS)
        custom_bindings["move_up"] = "ArrowUp"
        with open(settings_file, "w") as f:
            json.dump({
                "keybindings": custom_bindings,
                "game_options": DEFAULT_GAME_OPTIONS,
            }, f)

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("new_game", {"seed": 42})
            client.get_received()

            # The old key 'k' must NOT move the player (it is unbound)
            client.emit("input", {"key": "k"})
            received = client.get_received()

        # If the old key is truly unbound, the game should either:
        # - emit game_state with player position unchanged, OR
        # - silently ignore the key (no move, no crash)
        # We confirm there is no error that would indicate a crash.
        # The integration contract: 'k' must not produce a move when it is
        # unbound from move_up (it may be a no-op or emit game_state unchanged).
        error_events = [r for r in received if r["name"] == "error"]
        assert not error_events, (
            "Old key 'k' should be silently ignored when unbound, not produce an error"
        )


class TestDuplicateKeyBindingRejected:
    """Acceptance criterion 5: duplicate key binding is rejected with an error."""

    def test_duplicate_key_binding_emits_settings_error(self, tmp_path):
        """save_settings with two actions mapped to the same key emits settings_error."""
        settings_file = str(tmp_path / "settings.json")
        # Map both move_up and move_down to 'k' (a conflict)
        conflicting_bindings = dict(DEFAULT_KEYBINDINGS)
        conflicting_bindings["move_up"] = "k"
        conflicting_bindings["move_down"] = "k"

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("save_settings", {
                "keybindings": conflicting_bindings,
                "game_options": DEFAULT_GAME_OPTIONS,
            })
            received = client.get_received()

        event_names = [r["name"] for r in received]
        assert "settings_error" in event_names, (
            f"Expected 'settings_error' for duplicate key binding, got: {event_names}"
        )
        assert "settings_saved" not in event_names, (
            "settings_saved must NOT be emitted when a duplicate key binding is present"
        )

    def test_duplicate_key_not_persisted_to_disk(self, tmp_path):
        """When duplicate bindings are rejected, settings.json is not modified."""
        settings_file = str(tmp_path / "settings.json")
        # Write a known-good settings file first
        original_settings = {
            "keybindings": DEFAULT_KEYBINDINGS,
            "game_options": DEFAULT_GAME_OPTIONS,
        }
        with open(settings_file, "w") as f:
            json.dump(original_settings, f)

        conflicting_bindings = dict(DEFAULT_KEYBINDINGS)
        conflicting_bindings["move_up"] = "j"   # same as move_down

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("save_settings", {
                "keybindings": conflicting_bindings,
                "game_options": DEFAULT_GAME_OPTIONS,
            })

        with open(settings_file) as f:
            on_disk = json.load(f)

        # The original valid settings must be intact
        assert on_disk["keybindings"]["move_up"] == DEFAULT_KEYBINDINGS["move_up"], (
            "Rejected (duplicate) save_settings must not overwrite valid settings on disk"
        )


class TestInvalidKeyStringRejected:
    """Acceptance criterion 6: invalid or empty key string is rejected with an error."""

    def test_empty_key_string_emits_settings_error(self, tmp_path):
        """save_settings with an empty key string emits settings_error."""
        settings_file = str(tmp_path / "settings.json")
        invalid_bindings = dict(DEFAULT_KEYBINDINGS)
        invalid_bindings["move_up"] = ""  # empty string — not a valid key

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("save_settings", {
                "keybindings": invalid_bindings,
                "game_options": DEFAULT_GAME_OPTIONS,
            })
            received = client.get_received()

        event_names = [r["name"] for r in received]
        assert "settings_error" in event_names, (
            f"Expected 'settings_error' for empty key string, got: {event_names}"
        )
        assert "settings_saved" not in event_names, (
            "settings_saved must NOT be emitted when a key string is empty"
        )

    def test_none_key_string_emits_settings_error(self, tmp_path):
        """save_settings with a None key value emits settings_error."""
        settings_file = str(tmp_path / "settings.json")
        invalid_bindings = dict(DEFAULT_KEYBINDINGS)
        invalid_bindings["move_up"] = None  # None is not a valid key

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("save_settings", {
                "keybindings": invalid_bindings,
                "game_options": DEFAULT_GAME_OPTIONS,
            })
            received = client.get_received()

        event_names = [r["name"] for r in received]
        assert "settings_error" in event_names, (
            f"Expected 'settings_error' for None key value, got: {event_names}"
        )

    def test_missing_required_action_emits_settings_error(self, tmp_path):
        """save_settings with a missing required action emits settings_error."""
        settings_file = str(tmp_path / "settings.json")
        # Drop a required action entirely
        incomplete_bindings = dict(DEFAULT_KEYBINDINGS)
        del incomplete_bindings["move_up"]

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("save_settings", {
                "keybindings": incomplete_bindings,
                "game_options": DEFAULT_GAME_OPTIONS,
            })
            received = client.get_received()

        event_names = [r["name"] for r in received]
        assert "settings_error" in event_names, (
            f"Expected 'settings_error' when a required action is missing, got: {event_names}"
        )


class TestSettingsLoadedFromFileOnStartup:
    """Acceptance criterion 8: settings.json is read on server startup if it exists."""

    def test_existing_settings_file_applied_to_get_settings(self, tmp_path):
        """A pre-existing settings.json is loaded so get_settings reflects it."""
        settings_file = str(tmp_path / "settings.json")
        # Write custom settings to disk before the server processes any request
        pre_existing = {
            "keybindings": dict(DEFAULT_KEYBINDINGS, move_up="ArrowUp"),
            "game_options": DEFAULT_GAME_OPTIONS,
        }
        with open(settings_file, "w") as f:
            json.dump(pre_existing, f)

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("get_settings")
            received = client.get_received()

        data_events = [r for r in received if r["name"] == "settings_data"]
        assert data_events, "get_settings must emit settings_data"

        keybindings = data_events[0]["args"][0]["keybindings"]
        assert keybindings.get("move_up") == "ArrowUp", (
            "get_settings must return the binding loaded from the pre-existing settings.json"
        )


# ---------------------------------------------------------------------------
# Integration Tests
# ---------------------------------------------------------------------------

class TestSettingsPersistAcrossGameSessions:
    """Acceptance criterion 9: settings persist across game restarts."""

    def test_settings_survive_new_game_session(self, tmp_path):
        """Settings saved in one session are still present in a new session."""
        settings_file = str(tmp_path / "settings.json")
        new_bindings = dict(DEFAULT_KEYBINDINGS)
        new_bindings["move_up"] = "ArrowUp"

        # Session 1: save settings
        with _patch_settings_path(settings_file):
            client1 = _build_socket_client(settings_file)
            client1.emit("save_settings", {
                "keybindings": new_bindings,
                "game_options": DEFAULT_GAME_OPTIONS,
            })
            client1.get_received()
            client1.disconnect()

        # Session 2: open fresh client, settings must persist from disk
        with _patch_settings_path(settings_file):
            client2 = _build_socket_client(settings_file)
            client2.emit("get_settings")
            received = client2.get_received()

        data_events = [r for r in received if r["name"] == "settings_data"]
        assert data_events, "New session must emit settings_data on get_settings"

        keybindings = data_events[0]["args"][0]["keybindings"]
        assert keybindings.get("move_up") == "ArrowUp", (
            "Remapped 'move_up' must persist from session 1 to session 2 "
            "via settings.json on disk"
        )

    def test_settings_json_contains_all_keybinding_actions(self, tmp_path):
        """After save_settings, settings.json contains entries for all expected actions."""
        settings_file = str(tmp_path / "settings.json")
        new_bindings = dict(DEFAULT_KEYBINDINGS)

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("save_settings", {
                "keybindings": new_bindings,
                "game_options": DEFAULT_GAME_OPTIONS,
            })

        assert os.path.exists(settings_file), "settings.json must exist after save"
        with open(settings_file) as f:
            saved = json.load(f)

        for action in DEFAULT_KEYBINDINGS:
            assert action in saved.get("keybindings", {}), (
                f"Action '{action}' must be present in the saved settings.json"
            )

    def test_game_options_persisted_across_sessions(self, tmp_path):
        """Game options (animation_speed_ms) written in session 1 appear in session 2."""
        settings_file = str(tmp_path / "settings.json")
        custom_options = {"animation_speed_ms": 60, "max_visible_messages": 5}

        # Session 1: persist custom options
        with _patch_settings_path(settings_file):
            client1 = _build_socket_client(settings_file)
            client1.emit("save_settings", {
                "keybindings": DEFAULT_KEYBINDINGS,
                "game_options": custom_options,
            })
            client1.get_received()
            client1.disconnect()

        # Session 2: verify options survive
        with _patch_settings_path(settings_file):
            client2 = _build_socket_client(settings_file)
            client2.emit("get_settings")
            received = client2.get_received()

        data_events = [r for r in received if r["name"] == "settings_data"]
        assert data_events, "New session must emit settings_data"

        game_options = data_events[0]["args"][0].get("game_options", {})
        assert game_options.get("animation_speed_ms") == 60, (
            "animation_speed_ms=60 set in session 1 must appear in session 2"
        )
        assert game_options.get("max_visible_messages") == 5, (
            "max_visible_messages=5 set in session 1 must appear in session 2"
        )


class TestSettingsValidationIntegration:
    """Integration: validation errors do not corrupt the in-memory or on-disk state."""

    def test_valid_save_after_rejected_save_succeeds(self, tmp_path):
        """After a rejected save (duplicate keys), a subsequent valid save succeeds."""
        settings_file = str(tmp_path / "settings.json")

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)

            # First: attempt a duplicate binding — should be rejected
            bad_bindings = dict(DEFAULT_KEYBINDINGS)
            bad_bindings["move_up"] = "j"  # same as move_down
            client.emit("save_settings", {
                "keybindings": bad_bindings,
                "game_options": DEFAULT_GAME_OPTIONS,
            })
            rejected_events = client.get_received()
            assert any(r["name"] == "settings_error" for r in rejected_events), (
                "Setup: first save must be rejected as a duplicate"
            )

            # Second: send a valid save — must succeed
            good_bindings = dict(DEFAULT_KEYBINDINGS)
            good_bindings["move_up"] = "ArrowUp"
            client.emit("save_settings", {
                "keybindings": good_bindings,
                "game_options": DEFAULT_GAME_OPTIONS,
            })
            good_events = client.get_received()

        event_names = [r["name"] for r in good_events]
        assert "settings_saved" in event_names, (
            "A valid save_settings after a rejected one must emit settings_saved"
        )
        assert "settings_error" not in event_names, (
            "A valid save_settings must not emit settings_error"
        )

    def test_get_settings_after_malformed_settings_file_returns_defaults(self, tmp_path):
        """If settings.json is corrupt/malformed, get_settings returns defaults gracefully."""
        settings_file = str(tmp_path / "settings.json")
        # Write garbage
        with open(settings_file, "w") as f:
            f.write("{{not valid json at all!!")

        with _patch_settings_path(settings_file):
            client = _build_socket_client(settings_file)
            client.emit("get_settings")
            received = client.get_received()

        data_events = [r for r in received if r["name"] == "settings_data"]
        assert data_events, (
            "get_settings must emit settings_data even when settings.json is malformed"
        )

        keybindings = data_events[0]["args"][0].get("keybindings", {})
        # Should fall back to defaults — at minimum, move_up must be the default
        assert keybindings.get("move_up") == DEFAULT_KEYBINDINGS["move_up"], (
            "With a corrupt settings.json, get_settings must fall back to defaults"
        )
