"""Acceptance and integration tests for the projectile animation feature.

These tests define the expected NEW behavior where firing a ranged weapon
produces animation data in the render state:
  - `projectile_frames`: list of [y, x] pairs — the projectile path from
    the tile after the player to the target (inclusive)
  - `projectile_char`: '*' (CHAR_PROJECTILE constant)
  - `projectile_color`: '#FFFF00' (COLOR_PROJECTILE constant)

All tests are written in the RED phase — they will FAIL against the current
implementation and must pass only after the feature is implemented.

Architecture:
  - quakelike/constants.py gains CHAR_PROJECTILE and COLOR_PROJECTILE
  - quakelike/game.py gains _projectile_frames field cleared on each
    handle_input(), populated in _fire_weapon() on successful fire, and
    exposed via get_render_state()
"""

import pytest
from quakelike.game import Game, GameState
from quakelike.entity import Position
from quakelike.enemies import Enemy, GRUNT, ROTTWEILER
from quakelike.constants import TILE_FLOOR
from quakelike.items import create_item, SHOTGUN, SHELLS_SMALL


# ---------------------------------------------------------------------------
# Shared test fixture helpers
# ---------------------------------------------------------------------------

def _setup_game_with_target(seed: int = 42) -> tuple[Game, Enemy]:
    """Return a game and an enemy positioned in LOS so the player can fire.

    Layout (row 10):
        player @ (10, 10)  ─── open floor ──►  enemy @ (10, 15)

    The player starts with Axe + Shotgun + 25 shells (Player.create default).
    We equip the Shotgun so the fire key produces a successful ranged attack.
    """
    game = Game()
    game.new_game(seed=seed)

    # Control the enemy list precisely.
    game.current_map.enemies.clear()

    # Open a clear corridor from player to enemy.
    for x in range(10, 16):
        game.current_map.set_tile(10, x, TILE_FLOOR)

    # Place player and reveal so LOS computation works.
    game.player.pos = Position(10, 10)
    game.current_map.reveal_around(10, 10)

    # Place enemy.
    enemy = Enemy.from_def(GRUNT, Position(10, 15))
    game.current_map.enemies.append(enemy)

    # Equip shotgun (index 1 in default inventory: [axe, shotgun, shells]).
    shotgun_item = game.player.inventory.items[1]
    game.player.equip_weapon(shotgun_item)

    # Set targeting so _fire_weapon() picks the right target.
    game.target_list = [enemy]
    game.target_cursor = 0
    game.player.target_index = 0

    return game, enemy


# ---------------------------------------------------------------------------
# Acceptance tests
# ---------------------------------------------------------------------------

class TestProjectileAnimationAcceptance:
    """Acceptance tests for projectile animation in the render state.

    Current behavior (red phase):
        - render state has no 'projectile_frames', 'projectile_char', or
          'projectile_color' keys
        - game has no _projectile_frames field

    Required new behavior (these tests define):
        - After firing, 'projectile_frames' is a non-empty list of [y, x] pairs
        - The path starts at the tile immediately after the player and ends at
          the target's tile
        - Consecutive frames are adjacent (max 1-step diagonal)
        - Non-firing actions produce empty (or absent) projectile_frames
        - 'projectile_char' == '*' and 'projectile_color' == '#FFFF00' are
          always present in the render state
    """

    # ------------------------------------------------------------------
    # 1. Firing a ranged weapon produces a non-empty projectile_frames list
    # ------------------------------------------------------------------
    def test_firing_ranged_weapon_produces_projectile_frames(self):
        """After firing at a target, render state contains non-empty projectile_frames."""
        game, enemy = _setup_game_with_target()

        state = game.handle_input('f')

        assert 'projectile_frames' in state, (
            "render state must include 'projectile_frames' key after firing"
        )
        frames = state['projectile_frames']
        assert isinstance(frames, list), (
            f"projectile_frames must be a list, got {type(frames)}"
        )
        assert len(frames) > 0, (
            "projectile_frames must be non-empty after a successful ranged shot"
        )

    # ------------------------------------------------------------------
    # 2. Each frame is a [y, x] pair of integers
    # ------------------------------------------------------------------
    def test_projectile_frames_are_yx_pairs(self):
        """Every element of projectile_frames is a 2-element [y, x] sequence of ints."""
        game, enemy = _setup_game_with_target()

        state = game.handle_input('f')

        frames = state.get('projectile_frames', [])
        assert len(frames) > 0, "Pre-condition: frames must be non-empty"

        for i, frame in enumerate(frames):
            assert len(frame) == 2, (
                f"Frame {i} must have exactly 2 elements, got {len(frame)}: {frame!r}"
            )
            y, x = frame
            assert isinstance(y, int), (
                f"Frame {i} y-coordinate must be int, got {type(y)}: {y!r}"
            )
            assert isinstance(x, int), (
                f"Frame {i} x-coordinate must be int, got {type(x)}: {x!r}"
            )

    # ------------------------------------------------------------------
    # 3. First frame is NOT the player's own tile
    # ------------------------------------------------------------------
    def test_projectile_frames_start_after_player(self):
        """The first projectile frame must not be the player's position."""
        game, enemy = _setup_game_with_target()
        player_y = game.player.pos.y
        player_x = game.player.pos.x

        state = game.handle_input('f')

        frames = state.get('projectile_frames', [])
        assert len(frames) > 0, "Pre-condition: frames must be non-empty"

        first = frames[0]
        assert list(first) != [player_y, player_x], (
            f"First projectile frame must not be the player's tile "
            f"[{player_y}, {player_x}], but got {first!r}"
        )

    # ------------------------------------------------------------------
    # 4. Last frame is the target enemy's tile
    # ------------------------------------------------------------------
    def test_projectile_frames_end_at_target(self):
        """The last projectile frame must be the target enemy's [y, x] position."""
        game, enemy = _setup_game_with_target()
        target_y = enemy.pos.y
        target_x = enemy.pos.x

        state = game.handle_input('f')

        frames = state.get('projectile_frames', [])
        assert len(frames) > 0, "Pre-condition: frames must be non-empty"

        last = frames[-1]
        assert list(last) == [target_y, target_x], (
            f"Last projectile frame must be target position [{target_y}, {target_x}], "
            f"got {last!r}"
        )

    # ------------------------------------------------------------------
    # 5. Consecutive frames are adjacent (max 1-step diagonal)
    # ------------------------------------------------------------------
    def test_projectile_frames_form_contiguous_path(self):
        """Consecutive projectile frames must differ by at most 1 in both y and x."""
        game, enemy = _setup_game_with_target()

        state = game.handle_input('f')

        frames = state.get('projectile_frames', [])
        assert len(frames) > 0, "Pre-condition: frames must be non-empty"

        for i in range(len(frames) - 1):
            y0, x0 = frames[i]
            y1, x1 = frames[i + 1]
            dy = abs(y1 - y0)
            dx = abs(x1 - x0)
            assert dy <= 1 and dx <= 1, (
                f"Non-contiguous jump between frame {i} ({frames[i]!r}) "
                f"and frame {i+1} ({frames[i+1]!r}): dy={dy}, dx={dx}"
            )
            # Also reject standing still (two identical frames)
            assert (dy, dx) != (0, 0), (
                f"Duplicate frame at index {i} and {i+1}: {frames[i]!r}"
            )

    # ------------------------------------------------------------------
    # 6. Melee attack produces no projectile frames
    # ------------------------------------------------------------------
    def test_melee_attack_produces_no_projectile_frames(self):
        """Bumping into an adjacent enemy (melee) must not produce projectile_frames.

        Pre-condition: we first confirm a ranged shot DOES produce frames (the
        feature exists), then confirm a melee bump does NOT.  The pre-condition
        fails against the current code, keeping this test firmly in the red phase.
        """
        # Pre-condition: verify the feature exists by firing a ranged shot first.
        ranged_game, ranged_enemy = _setup_game_with_target()
        ranged_state = ranged_game.handle_input('f')
        ranged_frames = ranged_state.get('projectile_frames', [])
        assert len(ranged_frames) > 0, (
            "Pre-condition failed: a ranged shot must produce non-empty "
            "projectile_frames, but got none. Feature not yet implemented."
        )

        # Main assertion: melee bump produces no frames.
        game = Game()
        game.new_game(seed=42)
        game.current_map.enemies.clear()
        game.current_map.set_tile(10, 10, TILE_FLOOR)
        game.current_map.set_tile(10, 11, TILE_FLOOR)
        game.player.pos = Position(10, 10)
        # Player keeps default axe equipped (melee weapon).
        enemy = Enemy.from_def(ROTTWEILER, Position(10, 11))
        game.current_map.enemies.append(enemy)

        state = game.handle_input('l')  # Move right = bump = melee

        frames = state.get('projectile_frames', [])
        assert frames == [], (
            f"Melee attack must not produce projectile_frames, got {frames!r}"
        )

    # ------------------------------------------------------------------
    # 7. Movement produces no projectile frames
    # ------------------------------------------------------------------
    def test_movement_produces_no_projectile_frames(self):
        """Moving with hjkl must not produce any projectile_frames.

        Pre-condition: we first confirm a ranged shot DOES produce frames (the
        feature exists), then confirm movement does NOT.  The pre-condition
        fails against the current code, keeping this test firmly in the red phase.
        """
        # Pre-condition: verify the feature exists by firing a ranged shot first.
        ranged_game, ranged_enemy = _setup_game_with_target()
        ranged_state = ranged_game.handle_input('f')
        ranged_frames = ranged_state.get('projectile_frames', [])
        assert len(ranged_frames) > 0, (
            "Pre-condition failed: a ranged shot must produce non-empty "
            "projectile_frames, but got none. Feature not yet implemented."
        )

        # Main assertion: movement produces no frames.
        game = Game()
        game.new_game(seed=42)
        game.current_map.enemies.clear()
        for y in range(9, 12):
            for x in range(9, 12):
                game.current_map.set_tile(y, x, TILE_FLOOR)
        game.player.pos = Position(10, 10)

        for key in ('h', 'j', 'k', 'l'):
            state = game.handle_input(key)
            frames = state.get('projectile_frames', [])
            assert frames == [], (
                f"Movement key '{key}' must not produce projectile_frames, "
                f"got {frames!r}"
            )
            # Reset position so the next move is always into open floor.
            game.player.pos = Position(10, 10)

    # ------------------------------------------------------------------
    # 8. Pressing fire with no active target produces no frames
    # ------------------------------------------------------------------
    def test_no_target_produces_no_projectile_frames(self):
        """Pressing 'f' when target_cursor == -1 must produce no projectile_frames.

        Pre-condition: we first confirm a ranged shot WITH a target DOES produce
        frames (the feature exists), then confirm firing with no target does NOT.
        The pre-condition fails against the current code, keeping this test in
        the red phase.
        """
        # Pre-condition: verify the feature exists by firing a ranged shot first.
        ranged_game, ranged_enemy = _setup_game_with_target()
        ranged_state = ranged_game.handle_input('f')
        ranged_frames = ranged_state.get('projectile_frames', [])
        assert len(ranged_frames) > 0, (
            "Pre-condition failed: a ranged shot must produce non-empty "
            "projectile_frames, but got none. Feature not yet implemented."
        )

        # Main assertion: fire with no target produces no frames.
        game, enemy = _setup_game_with_target()
        game.target_cursor = -1
        game.player.target_index = -1

        state = game.handle_input('f')

        frames = state.get('projectile_frames', [])
        assert frames == [], (
            f"Fire with no target must not produce projectile_frames, got {frames!r}"
        )

    # ------------------------------------------------------------------
    # 9. Render state always includes projectile_char and projectile_color
    # ------------------------------------------------------------------
    def test_render_state_includes_projectile_char_and_color(self):
        """get_render_state() must always include projectile_char and projectile_color.

        These fields should be present even when no shot has been fired, so the
        frontend can read them without conditional logic.
        """
        game = Game()
        game.new_game(seed=42)

        # Check in idle state (no shot fired).
        state = game.get_render_state()

        assert 'projectile_char' in state, (
            "render state must always include 'projectile_char'"
        )
        assert 'projectile_color' in state, (
            "render state must always include 'projectile_color'"
        )

        # Values must match the new constants.
        try:
            from quakelike.constants import CHAR_PROJECTILE, COLOR_PROJECTILE
        except ImportError:
            pytest.fail(
                "quakelike.constants must define CHAR_PROJECTILE and COLOR_PROJECTILE"
            )

        assert state['projectile_char'] == CHAR_PROJECTILE, (
            f"projectile_char must equal CHAR_PROJECTILE ('{CHAR_PROJECTILE}'), "
            f"got {state['projectile_char']!r}"
        )
        assert state['projectile_color'] == COLOR_PROJECTILE, (
            f"projectile_color must equal COLOR_PROJECTILE ('{COLOR_PROJECTILE}'), "
            f"got {state['projectile_color']!r}"
        )

        # Also verify the values themselves match the spec.
        assert CHAR_PROJECTILE == '*', (
            f"CHAR_PROJECTILE must be '*', got {CHAR_PROJECTILE!r}"
        )
        assert COLOR_PROJECTILE == '#FFFF00', (
            f"COLOR_PROJECTILE must be '#FFFF00', got {COLOR_PROJECTILE!r}"
        )
