"""Settings management for Quakelike.

Provides GameSettings — a container for key bindings and game options
that can be loaded from / saved to a JSON file on disk.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Module-level path — patched in tests via mock.patch('quakelike.settings.SETTINGS_PATH', ...)
# ---------------------------------------------------------------------------
SETTINGS_PATH = 'settings.json'

# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

DEFAULT_KEYBINDINGS: dict[str, str] = {
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

DEFAULT_GAME_OPTIONS: dict[str, Any] = {
    "animation_speed_ms": 30,
    "max_visible_messages": 3,
}

# Mapping from action name → (dy, dx) direction vector for movement actions.
ACTION_DIRECTIONS: dict[str, tuple[int, int]] = {
    "move_up":         (-1, 0),
    "move_down":       (1, 0),
    "move_left":       (0, -1),
    "move_right":      (0, 1),
    "move_up_right":   (-1, 1),
    "move_up_left":    (-1, -1),
    "move_down_right": (1, 1),
    "move_down_left":  (1, -1),
}


# ---------------------------------------------------------------------------
# GameSettings dataclass
# ---------------------------------------------------------------------------

@dataclass
class GameSettings:
    """Holds all user-configurable settings for the game.

    Attributes:
        keybindings: Maps action name → key string.
        game_options: Maps option name → value.
    """
    keybindings: dict[str, str] = field(default_factory=lambda: dict(DEFAULT_KEYBINDINGS))
    game_options: dict[str, Any] = field(default_factory=lambda: dict(DEFAULT_GAME_OPTIONS))

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @classmethod
    def defaults(cls) -> "GameSettings":
        """Return a new GameSettings instance populated with all defaults."""
        return cls(
            keybindings=dict(DEFAULT_KEYBINDINGS),
            game_options=dict(DEFAULT_GAME_OPTIONS),
        )

    @classmethod
    def load(cls, path: str | None = None) -> "GameSettings":
        """Load settings from *path* (JSON file).

        Falls back to defaults when:
        - *path* is None (uses module-level SETTINGS_PATH)
        - the file does not exist
        - the file is unreadable or contains invalid JSON

        Missing actions in the file are filled in from ``DEFAULT_KEYBINDINGS``
        so that newly added actions always have a sensible default even when
        loading an older settings file.
        """
        import quakelike.settings as _mod
        resolved = path if path is not None else _mod.SETTINGS_PATH
        try:
            with open(resolved, 'r') as f:
                data = json.load(f)
            return cls.from_dict(data)
        except (FileNotFoundError, json.JSONDecodeError, TypeError, ValueError):
            return cls.defaults()

    def save(self, path: str | None = None) -> None:
        """Save settings to *path* (JSON file).

        Uses module-level SETTINGS_PATH when *path* is None.
        Creates parent directories if needed.
        """
        import quakelike.settings as _mod
        resolved = path if path is not None else _mod.SETTINGS_PATH
        parent = os.path.dirname(resolved)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(resolved, 'w') as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def reset(cls, path: str | None = None) -> "GameSettings":
        """Reset settings to defaults and write them to *path*.

        Returns the default GameSettings instance.
        """
        settings = cls.defaults()
        settings.save(path)
        return settings

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self) -> None:
        """Validate the current settings.

        Raises:
            ValueError: If any key string is empty / None, if a required
                        action is missing, or if any two actions share the
                        same key string.
        """
        # Check all required actions are present with non-empty keys
        for action in DEFAULT_KEYBINDINGS:
            key = self.keybindings.get(action)
            if key is None or key == "":
                raise ValueError(
                    f"Action '{action}' has an invalid or missing key binding."
                )

        # Check for additional empty/None values
        for action, key in self.keybindings.items():
            if key is None or key == "":
                raise ValueError(
                    f"Action '{action}' has an empty or None key binding."
                )

        # Check for duplicate key strings across actions
        seen: dict[str, str] = {}
        for action, key in self.keybindings.items():
            if key in seen:
                raise ValueError(
                    f"Duplicate key '{key}': assigned to both "
                    f"'{seen[key]}' and '{action}'."
                )
            seen[key] = action

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Return a JSON-serialisable dict representation."""
        return {
            "keybindings": dict(self.keybindings),
            "game_options": dict(self.game_options),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "GameSettings":
        """Construct GameSettings from a plain dict (e.g. loaded from JSON).

        Unknown actions in *data* are kept; missing required actions are filled
        from DEFAULT_KEYBINDINGS so older files remain valid.
        """
        raw_bindings: dict = data.get("keybindings", {})
        # Start from defaults then overlay what was stored on disk so that
        # newly added actions always have a fallback.
        merged: dict[str, str] = dict(DEFAULT_KEYBINDINGS)
        merged.update(raw_bindings)

        raw_options: dict = data.get("game_options", {})
        merged_options: dict[str, Any] = dict(DEFAULT_GAME_OPTIONS)
        merged_options.update(raw_options)

        return cls(keybindings=merged, game_options=merged_options)

    # ------------------------------------------------------------------
    # Key lookup helpers
    # ------------------------------------------------------------------

    def get_movement_direction(self, key: str) -> tuple[int, int] | None:
        """Return (dy, dx) if *key* is bound to a movement action, else None."""
        for action, direction in ACTION_DIRECTIONS.items():
            if self.keybindings.get(action) == key:
                return direction
        return None

    def get_key(self, action: str) -> str | None:
        """Return the key string bound to *action*, or None if not configured."""
        return self.keybindings.get(action)
