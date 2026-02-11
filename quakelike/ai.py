"""Enemy AI for Quakelike."""

from __future__ import annotations
import random
from typing import TYPE_CHECKING

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
                 rng: random.Random) -> list[str]:
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

    # Invisible player is harder to detect
    if player.invisibility_turns > 0 and dist > 3:
        # Can't see invisible player unless very close
        if rng.random() < 0.7:
            _wander(enemy, game_map, rng)
            return []

    # Try to attack first
    attack = enemy.get_best_attack(dist)
    if attack is not None and enemy.can_attack():
        # In range to attack
        if attack.attack_range >= dist:
            msgs = enemy_attack(enemy, player, game_map, rng)
            messages.extend(msgs)
            return messages

    # Move toward player
    _move_toward_player(enemy, player, game_map, rng)

    return messages


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
            from quakelike.constants import TILE_WATER
            if game_map.get_tile(ny, nx) == TILE_WATER:
                return
        enemy.pos = Position(ny, nx)


def _move_toward_player(enemy: Enemy, player: Player,
                        game_map: GameMap, rng: random.Random) -> None:
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
        if game_map.is_walkable(ny, nx):
            # Water check
            if enemy.enemy_def.avoids_water:
                from quakelike.constants import TILE_WATER
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
