"""Red-phase acceptance and integration tests for the movement-based dodge mechanic.

All tests in this file are expected to FAIL until the feature is implemented.

Feature summary
---------------
- A moving player has a chance to dodge RANGED attacks based on:
    * the angle between the player's movement direction and the attack vector
    * the distance between attacker and player
- MELEE and LEAP attacks are NEVER dodgeable
- Stationary players (last_move_dir == (0,0)) NEVER dodge
- After _move_player() succeeds, player.last_move_dir is set to the direction tuple
- After a rest action ('.'), player.last_move_dir is reset to (0, 0)
- After _end_turn() completes, player.last_move_dir is reset to (0, 0)
- When a dodge succeeds: a "You dodge" message is returned, no damage applied,
  but the enemy's attack_cooldown IS still set
- When a dodge fails: damage is applied normally

New constants added to quakelike.constants
------------------------------------------
    DODGE_CHANCE_PERPENDICULAR = 50   (base %, perpendicular strafe at full range)
    DODGE_CHANCE_OBLIQUE       = 30   (diagonal movement at full range)
    DODGE_CHANCE_PARALLEL      = 10   (moving toward/away from attacker at full range)
    DODGE_FULL_RANGE           = 8    (tiles — distance at which base chance applies)

New / modified symbols
-----------------------
    quakelike.combat._calc_dodge_chance(move_dir, enemy_pos, player_pos) -> int
    quakelike.player.Player.last_move_dir: tuple[int,int]  (default (0,0))
"""

from __future__ import annotations

import random
from unittest.mock import patch

import pytest

from quakelike.entity import Position
from quakelike.enemies import Enemy, AttackType, GRUNT, ROTTWEILER, FIEND
from quakelike.gamemap import GameMap
from quakelike.player import Player
from quakelike.constants import TILE_FLOOR


# ---------------------------------------------------------------------------
# Helpers shared across multiple test classes
# ---------------------------------------------------------------------------

def make_open_map() -> GameMap:
    """Return a GameMap with a large open floor area (no walls blocking LOS)."""
    gmap = GameMap()
    for y in range(5, 25):
        for x in range(5, 50):
            gmap.set_tile(y, x, TILE_FLOOR)
    return gmap


def make_ranged_enemy(pos: Position) -> Enemy:
    """Return a live GRUNT with cooldown=0, able to make a RANGED attack."""
    enemy = Enemy.from_def(GRUNT, pos)
    enemy.attack_cooldown = 0
    enemy.alerted = True
    return enemy


def make_melee_enemy(pos: Position) -> Enemy:
    """Return a live ROTTWEILER with cooldown=0, melee only."""
    enemy = Enemy.from_def(ROTTWEILER, pos)
    enemy.attack_cooldown = 0
    enemy.alerted = True
    return enemy


def make_leap_enemy(pos: Position) -> Enemy:
    """Return a live FIEND with cooldown=0 — LEAP attack only at range."""
    enemy = Enemy.from_def(FIEND, pos)
    enemy.attack_cooldown = 0
    enemy.alerted = True
    return enemy


# ---------------------------------------------------------------------------
# Unit tests: _calc_dodge_chance helper
# ---------------------------------------------------------------------------

class TestCalcDodgeChance:
    """Tests for the pure _calc_dodge_chance(move_dir, enemy_pos, player_pos) helper.

    The function must be importable from quakelike.combat.
    All cases use enemy at Position(0, 0) to keep geometry simple.

    Expected contract
    -----------------
    - Stationary (0, 0) move_dir → always 0
    - Perpendicular strafe at DODGE_FULL_RANGE (8) tiles → 50
    - Perpendicular strafe at 4 tiles → 25
    - Perpendicular strafe at 1 tile → 6
    - Oblique movement (~45 deg) at full range → 30
    - Parallel movement (toward/away from attacker) at full range → 10
    - Parallel movement at 1 tile → 1
    """

    def _import_calc(self):
        """Import _calc_dodge_chance; fail cleanly if not yet implemented."""
        try:
            from quakelike.combat import _calc_dodge_chance
            return _calc_dodge_chance
        except ImportError as e:
            pytest.fail(
                f"_calc_dodge_chance not importable from quakelike.combat: {e}"
            )

    def test_stationary_player_always_zero(self):
        """A player who did not move has 0% dodge chance regardless of geometry."""
        fn = self._import_calc()
        result = fn((0, 0), Position(0, 0), Position(0, 8))
        assert result == 0, (
            f"Stationary player should have 0% dodge chance, got {result}"
        )

    def test_perpendicular_at_full_range_gives_50(self):
        """Perpendicular strafe at 8 tiles gives the base 50% dodge chance.

        Setup: enemy at (0,0), player at (0,8), move_dir=(-1,0) [moving up].
        Attack vector points east (+x direction). Moving up is perpendicular.
        """
        fn = self._import_calc()
        result = fn((-1, 0), Position(0, 0), Position(0, 8))
        assert result == 50, (
            f"Perpendicular strafe at 8 tiles should give 50%, got {result}"
        )

    def test_perpendicular_at_4_tiles_gives_25(self):
        """Perpendicular strafe at 4 tiles gives 25% dodge chance.

        Dodge chance scales linearly with distance: 50 * (dist / DODGE_FULL_RANGE).
        4 / 8 * 50 = 25.
        """
        fn = self._import_calc()
        result = fn((-1, 0), Position(0, 0), Position(0, 4))
        assert result == 25, (
            f"Perpendicular strafe at 4 tiles should give 25%, got {result}"
        )

    def test_perpendicular_at_1_tile_gives_6(self):
        """Perpendicular strafe at 1 tile gives ~6% dodge chance.

        1 / 8 * 50 = 6.25 → floored to 6.
        """
        fn = self._import_calc()
        result = fn((-1, 0), Position(0, 0), Position(0, 1))
        assert result == 6, (
            f"Perpendicular strafe at 1 tile should give 6%, got {result}"
        )

    def test_oblique_movement_at_full_range_gives_30(self):
        """Oblique movement (~45 deg) at full range gives 30% dodge chance.

        Setup: enemy at (0,0), player at (0,8), move_dir=(-1,1) [up-right diagonal].
        Attack vector (0,8) is horizontal east; move vector (-1,1) is at ~45 deg.
        The angle test classifies this as neither perpendicular nor parallel -> oblique.
        Expected: DODGE_CHANCE_OBLIQUE * (dist / DODGE_FULL_RANGE) = 30 * (8/8) = 30.
        """
        fn = self._import_calc()
        result = fn((-1, 1), Position(0, 0), Position(0, 8))
        assert result == 30, (
            f"Oblique movement at full range should give 30%, got {result}"
        )

    def test_parallel_movement_at_full_range_gives_10(self):
        """Moving directly toward the attacker at full range gives 10% dodge chance.

        Setup: enemy at (0,0), player at (0,8), move_dir=(0,1) [moving east, toward enemy].
        Attack vector (0,8) is east; move (0,1) is parallel.
        Expected: DODGE_CHANCE_PARALLEL * (dist / DODGE_FULL_RANGE) = 10 * (8/8) = 10.
        """
        fn = self._import_calc()
        result = fn((0, 1), Position(0, 0), Position(0, 8))
        assert result == 10, (
            f"Parallel movement at full range should give 10%, got {result}"
        )

    def test_parallel_movement_at_1_tile_gives_1(self):
        """Moving directly toward attacker at 1 tile gives ~1% dodge chance.

        10 * (1 / 8) = 1.25 -> floored to 1.
        """
        fn = self._import_calc()
        result = fn((0, 1), Position(0, 0), Position(0, 1))
        assert result == 1, (
            f"Parallel movement at 1 tile should give 1%, got {result}"
        )


# ---------------------------------------------------------------------------
# Unit tests: Player.last_move_dir field
# ---------------------------------------------------------------------------

class TestPlayerLastMoveDirField:
    """Verify that Player gains a last_move_dir field defaulting to (0, 0)."""

    def test_player_has_last_move_dir_field(self):
        """Player dataclass must expose a last_move_dir attribute."""
        player = Player.create(Position(10, 10))
        assert hasattr(player, 'last_move_dir'), (
            "Player does not have a 'last_move_dir' field — implement it in player.py"
        )

    def test_player_last_move_dir_default_is_zero(self):
        """last_move_dir must default to (0, 0) on a freshly-created player."""
        player = Player.create(Position(10, 10))
        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )
        assert player.last_move_dir == (0, 0), (
            f"Expected last_move_dir == (0, 0), got {player.last_move_dir!r}"
        )


# ---------------------------------------------------------------------------
# Unit tests: dodge constants
# ---------------------------------------------------------------------------

class TestDodgeConstants:
    """Verify that the required constants are present in quakelike.constants."""

    def _import_constants(self):
        try:
            import quakelike.constants as C
            return C
        except ImportError as e:
            pytest.fail(f"Cannot import quakelike.constants: {e}")

    def test_dodge_chance_perpendicular_exists(self):
        C = self._import_constants()
        assert hasattr(C, 'DODGE_CHANCE_PERPENDICULAR'), (
            "DODGE_CHANCE_PERPENDICULAR missing from constants.py"
        )
        assert C.DODGE_CHANCE_PERPENDICULAR == 50

    def test_dodge_chance_oblique_exists(self):
        C = self._import_constants()
        assert hasattr(C, 'DODGE_CHANCE_OBLIQUE'), (
            "DODGE_CHANCE_OBLIQUE missing from constants.py"
        )
        assert C.DODGE_CHANCE_OBLIQUE == 30

    def test_dodge_chance_parallel_exists(self):
        C = self._import_constants()
        assert hasattr(C, 'DODGE_CHANCE_PARALLEL'), (
            "DODGE_CHANCE_PARALLEL missing from constants.py"
        )
        assert C.DODGE_CHANCE_PARALLEL == 10

    def test_dodge_full_range_exists(self):
        C = self._import_constants()
        assert hasattr(C, 'DODGE_FULL_RANGE'), (
            "DODGE_FULL_RANGE missing from constants.py"
        )
        assert C.DODGE_FULL_RANGE == 8


# ---------------------------------------------------------------------------
# Integration tests: enemy_attack() with dodge outcomes
# ---------------------------------------------------------------------------

class TestEnemyAttackDodgeIntegration:
    """Integration tests for the dodge mechanic inside enemy_attack().

    These tests import enemy_attack from quakelike.combat and drive it with
    mocked RNG to force deterministic outcomes.

    RNG call order inside enemy_attack() (after implementation):
        1. rng.randint(damage_min, damage_max)   — damage roll
        2. rng.randint(1, 100)                   — dodge roll (RANGED only)
    """

    def _import_enemy_attack(self):
        try:
            from quakelike.combat import enemy_attack
            return enemy_attack
        except ImportError as e:
            pytest.fail(f"Cannot import enemy_attack from quakelike.combat: {e}")

    # ----------------------------------------------------------------
    # Perpendicular strafe at 8 tiles → 50% dodge chance
    # ----------------------------------------------------------------

    def test_ranged_dodge_succeeds_when_roll_lte_chance(self):
        """RANGED attack is dodged when rng roll <= dodge chance (50% perp at 8 tiles).

        With move_dir=(-1,0) (perpendicular) and dist=8, dodge_chance=50.
        A roll of 40 <= 50 => dodge should succeed: no damage, message contains 'dodge'.
        """
        enemy_attack = self._import_enemy_attack()

        gmap = make_open_map()
        # Enemy at (10,10), player at (10,18) — 8 tiles east
        enemy = make_ranged_enemy(Position(10, 10))
        player = Player.create(Position(10, 18))
        gmap.enemies.append(enemy)

        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )
        player.last_move_dir = (-1, 0)  # perpendicular strafe → 50% chance
        initial_health = player.health

        rng = random.Random(0)
        # side_effects: first=damage value (within GRUNT range), second=dodge roll 40
        with patch.object(rng, 'randint', side_effect=[8, 40]):
            msgs = enemy_attack(enemy, player, gmap, rng)

        assert player.health == initial_health, (
            f"Dodge should prevent damage; health changed from {initial_health} "
            f"to {player.health}"
        )
        assert any('dodge' in m.lower() for m in msgs), (
            f"Expected a 'dodge' message; got: {msgs}"
        )

    def test_ranged_dodge_fails_when_roll_gt_chance(self):
        """RANGED attack lands when rng roll > dodge chance (50% perp at 8 tiles).

        A roll of 60 > 50 => no dodge, damage is applied.
        """
        enemy_attack = self._import_enemy_attack()

        gmap = make_open_map()
        enemy = make_ranged_enemy(Position(10, 10))
        player = Player.create(Position(10, 18))
        gmap.enemies.append(enemy)

        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )
        player.last_move_dir = (-1, 0)
        initial_health = player.health

        rng = random.Random(0)
        # side_effects: first=damage (8), second=dodge roll 60
        with patch.object(rng, 'randint', side_effect=[8, 60]):
            msgs = enemy_attack(enemy, player, gmap, rng)

        assert player.health < initial_health, (
            "Dodge should fail (roll 60 > 50), damage should be applied"
        )
        assert not any('dodge' in m.lower() for m in msgs), (
            f"Should not have a 'dodge' message when dodge fails; got: {msgs}"
        )

    # ----------------------------------------------------------------
    # Stationary player → 0% dodge chance, always damaged
    # ----------------------------------------------------------------

    def test_stationary_player_never_dodges(self):
        """A stationary player (last_move_dir=(0,0)) is always hit by RANGED attacks.

        Even with a very low roll (1), 0% chance means no dodge.
        """
        enemy_attack = self._import_enemy_attack()

        gmap = make_open_map()
        enemy = make_ranged_enemy(Position(10, 10))
        player = Player.create(Position(10, 18))
        gmap.enemies.append(enemy)

        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )
        # Explicitly stationary
        player.last_move_dir = (0, 0)
        initial_health = player.health

        rng = random.Random(0)
        # Only the damage roll; no dodge roll expected for 0% chance
        with patch.object(rng, 'randint', side_effect=[8, 1]):
            msgs = enemy_attack(enemy, player, gmap, rng)

        assert player.health < initial_health, (
            "Stationary player should always take damage from RANGED attacks"
        )
        assert not any('dodge' in m.lower() for m in msgs), (
            f"Stationary player should not produce a dodge message; got: {msgs}"
        )

    # ----------------------------------------------------------------
    # Parallel movement at full range → 10% dodge chance
    # ----------------------------------------------------------------

    def test_parallel_move_roll_within_chance_dodges(self):
        """Parallel movement (toward attacker) at 8 tiles → 10% dodge chance.

        Roll of 5 <= 10 => dodge succeeds.
        """
        enemy_attack = self._import_enemy_attack()

        gmap = make_open_map()
        enemy = make_ranged_enemy(Position(10, 10))
        player = Player.create(Position(10, 18))
        gmap.enemies.append(enemy)

        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )
        # Moving east (toward the enemy to the west) — parallel
        player.last_move_dir = (0, 1)
        initial_health = player.health

        rng = random.Random(0)
        with patch.object(rng, 'randint', side_effect=[8, 5]):
            msgs = enemy_attack(enemy, player, gmap, rng)

        assert player.health == initial_health, (
            "Dodge should succeed for parallel move, roll=5 <= 10%"
        )
        assert any('dodge' in m.lower() for m in msgs), (
            f"Expected dodge message; got: {msgs}"
        )

    def test_parallel_move_roll_outside_chance_hits(self):
        """Parallel movement at 8 tiles → 10% dodge chance; roll=20 > 10 => hit."""
        enemy_attack = self._import_enemy_attack()

        gmap = make_open_map()
        enemy = make_ranged_enemy(Position(10, 10))
        player = Player.create(Position(10, 18))
        gmap.enemies.append(enemy)

        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )
        player.last_move_dir = (0, 1)
        initial_health = player.health

        rng = random.Random(0)
        with patch.object(rng, 'randint', side_effect=[8, 20]):
            msgs = enemy_attack(enemy, player, gmap, rng)

        assert player.health < initial_health, (
            "Dodge should fail for parallel move, roll=20 > 10%"
        )

    # ----------------------------------------------------------------
    # MELEE attacks are never dodgeable
    # ----------------------------------------------------------------

    def test_melee_attack_never_dodged_despite_perpendicular_move(self):
        """MELEE attacks bypass the dodge mechanic entirely.

        Even with perpendicular movement and a roll of 1, melee always hits.
        """
        enemy_attack = self._import_enemy_attack()

        gmap = make_open_map()
        # ROTTWEILER is melee-only; place adjacent to player
        enemy = make_melee_enemy(Position(10, 9))
        player = Player.create(Position(10, 10))
        gmap.enemies.append(enemy)

        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )
        player.last_move_dir = (-1, 0)   # perpendicular — would give 50% if ranged
        initial_health = player.health

        rng = random.Random(0)
        # Provide a low roll; without a second roll, melee should still damage
        with patch.object(rng, 'randint', side_effect=[10, 1]):
            msgs = enemy_attack(enemy, player, gmap, rng)

        assert player.health < initial_health, (
            "MELEE attacks must not be dodged; player should have taken damage"
        )
        assert not any('dodge' in m.lower() for m in msgs), (
            f"Should not produce a dodge message for MELEE; got: {msgs}"
        )

    # ----------------------------------------------------------------
    # LEAP attacks are never dodgeable (FIEND attack)
    # ----------------------------------------------------------------

    def test_leap_attack_never_dodged_despite_perpendicular_move(self):
        """LEAP attacks bypass the dodge mechanic entirely.

        FIEND has both MELEE (range 1) and LEAP (range 6).  At 6 tiles the LEAP
        is preferred.  Even with perpendicular movement, LEAP should always hit.
        """
        enemy_attack = self._import_enemy_attack()

        gmap = make_open_map()
        # Place fiend 6 tiles west of player — within LEAP range but not melee
        enemy = make_leap_enemy(Position(10, 12))
        player = Player.create(Position(10, 18))
        gmap.enemies.append(enemy)

        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )
        player.last_move_dir = (-1, 0)   # perpendicular
        initial_health = player.health

        rng = random.Random(0)
        with patch.object(rng, 'randint', side_effect=[30, 1]):
            msgs = enemy_attack(enemy, player, gmap, rng)

        assert player.health < initial_health, (
            "LEAP attacks must not be dodged; player should have taken damage"
        )
        assert not any('dodge' in m.lower() for m in msgs), (
            f"Should not produce a dodge message for LEAP; got: {msgs}"
        )

    # ----------------------------------------------------------------
    # Cooldown still set after successful dodge
    # ----------------------------------------------------------------

    def test_enemy_cooldown_set_after_successful_dodge(self):
        """After a successful dodge, the enemy's attack_cooldown is still set.

        The enemy used its attack — regardless of whether it connected — so the
        cooldown timer must be set (to the attack's cooldown value).
        """
        enemy_attack = self._import_enemy_attack()

        gmap = make_open_map()
        enemy = make_ranged_enemy(Position(10, 10))
        player = Player.create(Position(10, 18))
        gmap.enemies.append(enemy)

        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )
        player.last_move_dir = (-1, 0)  # perpendicular, 50% dodge at 8 tiles
        assert enemy.attack_cooldown == 0

        rng = random.Random(0)
        # Roll 40 <= 50 → dodge
        with patch.object(rng, 'randint', side_effect=[8, 40]):
            enemy_attack(enemy, player, gmap, rng)

        assert enemy.attack_cooldown > 0, (
            "Enemy attack_cooldown must be set even when the player dodges"
        )


# ---------------------------------------------------------------------------
# Game-level acceptance tests
# ---------------------------------------------------------------------------

class TestGameLevelDodgeIntegration:
    """Acceptance tests exercising the full Game object.

    These tests use game.handle_input() and game._end_turn() to drive state,
    exactly as the real game loop does.
    """

    def _make_game(self):
        """Create and initialise a Game in a known state."""
        from quakelike.game import Game
        game = Game()
        game.new_game(seed=42)
        return game

    def _find_open_move_up(self, game):
        """Find a floor position from which the player can move up ('k').

        Returns the Position or raises pytest.skip if none found.
        """
        from quakelike.constants import TILE_FLOOR
        gmap = game.current_map
        for y in range(1, gmap.height):
            for x in range(gmap.width):
                if (gmap.get_tile(y, x) == TILE_FLOOR and
                        gmap.get_tile(y - 1, x) == TILE_FLOOR and
                        gmap.get_enemy_at(y, x) is None and
                        gmap.get_enemy_at(y - 1, x) is None):
                    return Position(y, x)
        pytest.skip("No suitable floor position found in generated map")

    # ----------------------------------------------------------------
    # Acceptance criterion 8: last_move_dir set after successful move
    # ----------------------------------------------------------------

    def test_last_move_dir_set_after_move_up(self):
        """After successfully moving up ('k'), player.last_move_dir == (-1, 0)."""
        game = self._make_game()
        player = game.player

        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )

        start = self._find_open_move_up(game)
        player.pos = start

        # Remove enemies around the destination to prevent melee returning early
        game.current_map.enemies = [
            e for e in game.current_map.enemies
            if e.pos != Position(start.y - 1, start.x)
        ]

        game.handle_input('k')  # Move up
        assert player.last_move_dir == (-1, 0), (
            f"Expected last_move_dir==(-1,0) after moving up, got {player.last_move_dir!r}"
        )

    def test_last_move_dir_set_after_move_right(self):
        """After successfully moving right ('l'), player.last_move_dir == (0, 1)."""
        from quakelike.constants import TILE_FLOOR
        game = self._make_game()
        player = game.player

        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )

        gmap = game.current_map
        # Find a floor tile with an open tile to the right
        pos = None
        for y in range(gmap.height):
            for x in range(gmap.width - 1):
                if (gmap.get_tile(y, x) == TILE_FLOOR and
                        gmap.get_tile(y, x + 1) == TILE_FLOOR and
                        gmap.get_enemy_at(y, x) is None and
                        gmap.get_enemy_at(y, x + 1) is None):
                    pos = Position(y, x)
                    break
            if pos:
                break
        if pos is None:
            pytest.skip("No suitable floor position found")

        player.pos = pos
        game.handle_input('l')  # Move right
        assert player.last_move_dir == (0, 1), (
            f"Expected last_move_dir==(0,1) after moving right, got {player.last_move_dir!r}"
        )

    def test_last_move_dir_not_set_after_wall_bump(self):
        """Moving into a wall must NOT update last_move_dir (move did not succeed)."""
        game = self._make_game()
        player = game.player

        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )

        # Place player at (1, 1); row 0 is wall, so 'k' bumps into wall
        player.pos = Position(1, 1)
        game.current_map.set_tile(1, 1, TILE_FLOOR)
        player.last_move_dir = (0, 0)

        game.handle_input('k')  # Try to move up into wall (row 0)
        assert player.last_move_dir == (0, 0), (
            f"Wall bump must not change last_move_dir; got {player.last_move_dir!r}"
        )

    def test_last_move_dir_not_set_after_melee_bump(self):
        """Moving into an enemy (melee bump) must NOT update last_move_dir.

        Melee attack returns early before the movement succeeds, so last_move_dir
        should remain (0, 0).
        """
        game = self._make_game()
        player = game.player

        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )

        game.current_map.set_tile(10, 10, TILE_FLOOR)
        game.current_map.set_tile(10, 11, TILE_FLOOR)
        player.pos = Position(10, 10)
        player.last_move_dir = (0, 0)

        enemy = Enemy.from_def(ROTTWEILER, Position(10, 11))
        game.current_map.enemies.append(enemy)

        game.handle_input('l')  # Move right — should melee, not move
        assert player.last_move_dir == (0, 0), (
            f"Melee bump must not set last_move_dir; got {player.last_move_dir!r}"
        )

    # ----------------------------------------------------------------
    # Acceptance criterion 9: rest action resets last_move_dir to (0,0)
    # ----------------------------------------------------------------

    def test_rest_action_resets_last_move_dir(self):
        """After pressing '.' (rest), player.last_move_dir == (0, 0)."""
        game = self._make_game()
        player = game.player

        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )

        # Manually set a non-zero dir to confirm reset happens
        player.last_move_dir = (-1, 0)
        # Remove enemies so _end_turn doesn't error on missing fields
        game.current_map.enemies = []

        game.handle_input('.')  # Rest
        assert player.last_move_dir == (0, 0), (
            f"Rest ('.' key) must reset last_move_dir to (0,0); "
            f"got {player.last_move_dir!r}"
        )

    # ----------------------------------------------------------------
    # Acceptance criterion 10: _end_turn resets last_move_dir to (0,0)
    # ----------------------------------------------------------------

    def test_end_turn_resets_last_move_dir(self):
        """After _end_turn() completes, player.last_move_dir is reset to (0, 0)."""
        game = self._make_game()
        player = game.player

        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )

        player.last_move_dir = (-1, 0)
        # Remove enemies so we test only the reset behaviour
        game.current_map.enemies = []

        game._end_turn()
        assert player.last_move_dir == (0, 0), (
            f"_end_turn() must reset last_move_dir to (0,0); "
            f"got {player.last_move_dir!r}"
        )

    def test_end_turn_resets_last_move_dir_after_diagonal_move(self):
        """last_move_dir is reset to (0,0) by _end_turn even for diagonal moves."""
        game = self._make_game()
        player = game.player

        assert hasattr(player, 'last_move_dir'), (
            "Pre-condition failed: Player does not have 'last_move_dir' field yet."
        )

        player.last_move_dir = (-1, 1)   # simulating an up-right move
        game.current_map.enemies = []

        game._end_turn()
        assert player.last_move_dir == (0, 0), (
            f"_end_turn() must reset last_move_dir to (0,0); "
            f"got {player.last_move_dir!r}"
        )
