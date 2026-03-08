"""Enemy AI for Quakelike."""

from __future__ import annotations
import random
from typing import TYPE_CHECKING

from quakelike.constants import TILE_WATER, TILE_DOOR, DOOR_CLOSE_DELAY
from quakelike.entity import Position
from quakelike.enemies import Enemy, AttackType
from quakelike.combat import enemy_attack

if TYPE_CHECKING:
    from quakelike.player import Player
    from quakelike.gamemap import GameMap


# How far enemies can detect the player
ALERT_RADIUS = 15
# LOS required to become alerted
ALERT_LOS_REQUIRED = True


def update_enemy(enemy: Enemy, player: Player, game_map: GameMap,
                 rng: random.Random, current_turn: int = 0) -> list[str]:
    """Update a single enemy for one turn.

    Returns list of messages generated.
    """
    if not enemy.is_alive:
        return []

    messages = []

    # Tick cooldowns
    if enemy.attack_cooldown > 0:
        enemy.attack_cooldown -= 1

    # Speed check - skip turn if not time to act
    enemy.move_timer += 1
    if enemy.move_timer < enemy.enemy_def.speed:
        return []
    enemy.move_timer = 0

    # Track whether the enemy was already alerted before this turn's check.
    # Door-handling only applies to enemies that were alerted at turn start.
    was_already_alerted = enemy.alerted

    # Check alertness
    dist = enemy.pos.chebyshev_distance(player.pos)
    if not enemy.alerted:
        if dist <= ALERT_RADIUS:
            if game_map.has_line_of_sight(enemy.pos, player.pos):
                enemy.alerted = True
                # Don't message for every alert, just proceed

    if not enemy.alerted:
        # Idle behavior - wander occasionally
        if rng.random() < 0.2:
            _wander(enemy, game_map, rng)
        return []

    # Invisible player is harder to detect but not impossible.
    # Within 3 tiles enemies always detect the player (sound/proximity).
    # Beyond 3 tiles there is a 70% chance the enemy loses track each turn,
    # giving a 30% chance to still pursue, simulating imperfect invisibility.
    if player.invisibility_turns > 0 and dist > 3:
        if rng.random() < 0.7:
            _wander(enemy, game_map, rng)
            return []

    # Already-alerted enemies handle adjacent doors before attacking or moving.
    # This models Quake behavior: enemies clear doorways to pursue the player.
    # Enemies that just became alerted this turn act normally (no door priority).
    if was_already_alerted:
        door_action = _handle_adjacent_door(enemy, player, game_map, current_turn)
        if door_action:
            return messages

    # Try to attack first
    attack = enemy.get_best_attack(dist)
    if attack is not None and enemy.can_attack():
        # In range to attack
        if attack.attack_range >= dist:
            msgs = enemy_attack(enemy, player, game_map, rng)
            messages.extend(msgs)
            return messages

    # Move toward player
    _move_toward_player(enemy, player, game_map, rng, current_turn=current_turn)

    return messages


def _handle_adjacent_door(enemy: Enemy, player: 'Player', game_map: 'GameMap',
                          current_turn: int) -> bool:
    """Move or open doors along the greedy-toward-player direction.

    For already-alerted enemies this function is the primary movement handler.
    It scans only greedy directions (no behind/side tiles) to avoid wasting
    turns on doors that are not in the movement path.

    Returns True if an action was taken (consuming the enemy's turn):
      - Closed door in path → open it and wait one turn.
      - Open door or plain walkable tile in path → move through it.
      - No usable tile found → return False (caller may try attack/fallback).

    _move_toward_player handles door-opening for newly-alerted enemies.
    """
    # Build greedy direction toward player
    dy = 0
    dx = 0
    if player.pos.y < enemy.pos.y:
        dy = -1
    elif player.pos.y > enemy.pos.y:
        dy = 1
    if player.pos.x < enemy.pos.x:
        dx = -1
    elif player.pos.x > enemy.pos.x:
        dx = 1

    # Only scan greedy directions toward the player (at most 3 entries).
    # This ensures enemies open only doors that are actually in their path,
    # not doors behind or beside them.
    priority = []
    if dy != 0 and dx != 0:
        priority.append((dy, dx))
    if dy != 0:
        priority.append((dy, 0))
    if dx != 0:
        priority.append((0, dx))

    for my, mx in priority:
        ny, nx = enemy.pos.y + my, enemy.pos.x + mx
        tile = game_map.get_tile(ny, nx)
        if tile == TILE_DOOR:
            if not game_map.is_open_door(ny, nx):
                # Closed door: open it and wait this turn
                game_map.open_door(ny, nx, current_turn + DOOR_CLOSE_DELAY)
                return True
            else:
                # Open door: move through it (if not occupied)
                if (game_map.get_enemy_at(ny, nx) is None and
                        not (ny == player.pos.y and nx == player.pos.x)):
                    enemy.pos = Position(ny, nx)
                return True
        elif game_map.is_walkable(ny, nx):
            # Plain walkable tile: move if not occupied by another enemy or player
            if (game_map.get_enemy_at(ny, nx) is None and
                    not (ny == player.pos.y and nx == player.pos.x)):
                enemy.pos = Position(ny, nx)
                return True
    return False


def _wander(enemy: Enemy, game_map: GameMap, rng: random.Random) -> None:
    """Random wandering movement."""
    dy = rng.randint(-1, 1)
    dx = rng.randint(-1, 1)
    if dy == 0 and dx == 0:
        return

    ny, nx = enemy.pos.y + dy, enemy.pos.x + dx
    if (game_map.is_walkable(ny, nx) and
            game_map.get_enemy_at(ny, nx) is None):
        # Check water avoidance
        if enemy.enemy_def.avoids_water:
            if game_map.get_tile(ny, nx) == TILE_WATER:
                return
        enemy.pos = Position(ny, nx)


def _move_toward_player(enemy: Enemy, player: Player,
                        game_map: GameMap, rng: random.Random,
                        current_turn: int = 0) -> None:
    """Move enemy toward the player using simple pathfinding."""
    # Simple greedy movement toward player
    dy = 0
    dx = 0

    if player.pos.y < enemy.pos.y:
        dy = -1
    elif player.pos.y > enemy.pos.y:
        dy = 1

    if player.pos.x < enemy.pos.x:
        dx = -1
    elif player.pos.x > enemy.pos.x:
        dx = 1

    # Try diagonal first, then cardinal directions
    moves = []
    if dy != 0 and dx != 0:
        moves.append((dy, dx))
    if dy != 0:
        moves.append((dy, 0))
    if dx != 0:
        moves.append((0, dx))

    for my, mx in moves:
        ny, nx = enemy.pos.y + my, enemy.pos.x + mx
        # Don't walk into other enemies
        if game_map.get_enemy_at(ny, nx) is not None:
            continue
        # Don't walk to player position
        if ny == player.pos.y and nx == player.pos.x:
            continue
        # Fallback door-open for newly-alerted enemies: _handle_adjacent_door
        # is skipped when was_already_alerted is False, so we handle doors here.
        tile = game_map.get_tile(ny, nx)
        if tile == TILE_DOOR and not game_map.is_open_door(ny, nx):
            game_map.open_door(ny, nx, current_turn + DOOR_CLOSE_DELAY)
            return  # Enemy waits for the door to open
        if game_map.is_walkable(ny, nx):
            # Water check
            if enemy.enemy_def.avoids_water:
                if game_map.get_tile(ny, nx) == TILE_WATER:
                    continue
            enemy.pos = Position(ny, nx)
            return

    # If stuck, try random adjacent
    if rng.random() < 0.3:
        _wander(enemy, game_map, rng)


def get_enemies_in_los(player: Player, game_map: GameMap) -> list[Enemy]:
    """Get all enemies in the player's line of sight."""
    result = []
    for enemy in game_map.get_living_enemies():
        if game_map.has_line_of_sight(player.pos, enemy.pos):
            result.append(enemy)
    # Sort by distance
    result.sort(key=lambda e: e.pos.chebyshev_distance(player.pos))
    return result
