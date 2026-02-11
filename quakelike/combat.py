"""Combat system for Quakelike."""

from __future__ import annotations
import random
from typing import Optional, TYPE_CHECKING

from quakelike.constants import MELEE_DAMAGE_MIN, MELEE_DAMAGE_MAX
from quakelike.entity import Entity, Position
from quakelike.enemies import Enemy, AttackType
from quakelike.items import ItemType

if TYPE_CHECKING:
    from quakelike.player import Player
    from quakelike.gamemap import GameMap


def calculate_weapon_damage(player: Player, rng: random.Random) -> int:
    """Calculate damage from the player's equipped weapon."""
    weapon = player.equipped_weapon
    if weapon is None:
        # Bare hands - use melee damage
        return rng.randint(MELEE_DAMAGE_MIN, MELEE_DAMAGE_MAX)

    base = rng.randint(weapon.item_def.damage_min, weapon.item_def.damage_max)
    return base * player.get_damage_multiplier()


def player_melee_attack(player: Player, target: Enemy,
                        rng: random.Random) -> tuple[int, str]:
    """Player performs a melee attack (walking into enemy).

    Melee damage is always axe damage regardless of equipped weapon.
    """
    damage = rng.randint(MELEE_DAMAGE_MIN, MELEE_DAMAGE_MAX)
    damage *= player.get_damage_multiplier()
    actual = target.take_damage(damage)

    if target.is_alive:
        msg = f'You hit {target.name} for {actual} damage.'
    else:
        msg = f'You killed {target.name}!'
    return actual, msg


def player_fire_weapon(player: Player, target: Optional[Enemy],
                       game_map: GameMap, rng: random.Random
                       ) -> tuple[bool, str, list[str]]:
    """Player fires their equipped weapon.

    Returns (success, main_message, additional_messages).
    """
    messages = []

    if player.equipped_weapon is None:
        return False, 'No weapon equipped.', messages

    weapon_def = player.equipped_weapon.item_def

    # Check ammo
    if weapon_def.ammo_type is not None:
        if not player.inventory.consume_ammo(weapon_def.ammo_type,
                                              weapon_def.ammo_per_shot):
            return False, f'Not enough ammo for {weapon_def.name}.', messages

    # Check range
    if weapon_def.weapon_range <= 1:
        # Melee weapon - need adjacent target
        if target is None or target.pos.chebyshev_distance(player.pos) > 1:
            return False, 'No target in melee range.', messages
    else:
        # Ranged weapon
        if target is None:
            # Fire straight ahead - try to find something in the line
            target, hit_msg = _fire_in_direction(player, game_map, weapon_def.weapon_range)
            if target is None:
                return True, 'You fire into the void.', messages

        # Check LOS
        if not game_map.has_line_of_sight(player.pos, target.pos):
            return False, f'No line of sight to {target.name}.', messages

        # Check range
        dist = player.pos.chebyshev_distance(target.pos)
        if dist > weapon_def.weapon_range:
            return False, f'{target.name} is out of range.', messages

    # Calculate damage
    damage = calculate_weapon_damage(player, rng)
    actual = target.take_damage(damage)

    if target.is_alive:
        main_msg = f'You hit {target.name} with {weapon_def.name} for {actual} damage.'
    else:
        main_msg = f'You killed {target.name} with {weapon_def.name}!'
        xp, leveled = player.gain_xp(target.xp_value)
        messages.append(f'You gained {target.xp_value} XP.')
        if leveled:
            messages.append(f'Level up! You are now level {player.level}.')

    # Check friendly fire for explosion weapons (grenade/rocket)
    if weapon_def.name in ('Grenade Launcher', 'Rocket Launcher'):
        splash_msgs = _apply_splash_damage(target.pos, game_map, damage // 2, rng,
                                            exclude=target)
        messages.extend(splash_msgs)

    return True, main_msg, messages


def _fire_in_direction(player: Player, game_map: GameMap,
                       max_range: int) -> tuple[Optional[Enemy], str]:
    """Fire straight ahead (based on last movement direction).

    For simplicity, fire in all cardinal directions and hit first enemy.
    """
    # Try each direction from player
    directions = [(-1, 0), (1, 0), (0, -1), (0, 1),
                  (-1, -1), (-1, 1), (1, -1), (1, 1)]

    for dy, dx in directions:
        for dist in range(1, max_range + 1):
            ny = player.pos.y + dy * dist
            nx = player.pos.x + dx * dist
            if game_map.is_blocking(ny, nx):
                break
            enemy = game_map.get_enemy_at(ny, nx)
            if enemy is not None:
                return enemy, f'Auto-targeted {enemy.name}.'

    return None, ''


def _apply_splash_damage(center: Position, game_map: GameMap,
                         damage: int, rng: random.Random,
                         exclude: Optional[Enemy] = None) -> list[str]:
    """Apply splash damage to enemies near the center."""
    messages = []
    for enemy in game_map.get_living_enemies():
        if enemy is exclude:
            continue
        dist = center.chebyshev_distance(enemy.pos)
        if dist <= 2:
            splash = max(1, damage // (dist + 1))
            actual = enemy.take_damage(splash)
            if enemy.is_alive:
                messages.append(f'{enemy.name} caught in explosion for {actual} damage!')
            else:
                messages.append(f'{enemy.name} killed by explosion!')
    return messages


def enemy_attack(enemy: Enemy, player: Player, game_map: GameMap,
                 rng: random.Random) -> list[str]:
    """Enemy performs an attack on the player.

    Returns list of messages.
    """
    messages = []

    if not enemy.can_attack():
        return messages

    dist = enemy.pos.chebyshev_distance(player.pos)
    attack = enemy.get_best_attack(dist)

    if attack is None:
        return messages

    # Check line of sight for ranged attacks
    if attack.attack_type != AttackType.MELEE:
        if not game_map.has_line_of_sight(enemy.pos, player.pos):
            return messages

    # Check friendly fire avoidance
    if attack.attack_type in (AttackType.RANGED, AttackType.LEAP):
        if _would_hit_ally(enemy, player.pos, game_map):
            return messages  # Skip attack to avoid hitting allies

    # Calculate damage
    damage = rng.randint(attack.damage_min, attack.damage_max)

    if attack.attack_type == AttackType.EXPLODE:
        # Spawn explodes - kills itself and damages player
        actual = player.take_damage(damage)
        messages.append(f'{enemy.name} explodes for {actual} damage!')
        enemy.take_damage(enemy.health)  # Kill the spawn
        # Splash to nearby enemies
        splash_msgs = _apply_splash_damage(enemy.pos, game_map, damage // 2, rng)
        messages.extend(splash_msgs)
    elif attack.attack_type == AttackType.LEAP:
        # Fiend leaps to player
        actual = player.take_damage(damage)
        messages.append(f'{enemy.name} leaps at you for {actual} damage!')
        # Move fiend adjacent to player
        _move_adjacent(enemy, player.pos, game_map)
    else:
        actual = player.take_damage(damage)
        if attack.attack_type == AttackType.MELEE:
            messages.append(
                f'{enemy.name} {attack.description}s you for {actual} damage!')
        else:
            messages.append(
                f'{enemy.name} hits you with {attack.description} for {actual} damage!')

    enemy.attack_cooldown = attack.cooldown
    return messages


def _would_hit_ally(enemy: Enemy, target_pos: Position,
                    game_map: GameMap) -> bool:
    """Check if firing at target would hit an ally."""
    line = game_map.get_line(enemy.pos, target_pos)
    for point in line[1:-1]:  # Skip start and end
        other = game_map.get_enemy_at(point.y, point.x)
        if other is not None and other is not enemy and other.is_alive:
            return True
    return False


def _move_adjacent(enemy: Enemy, target: Position,
                   game_map: GameMap) -> None:
    """Move enemy to a position adjacent to target."""
    best_dist = float('inf')
    best_pos = None

    for dy in range(-1, 2):
        for dx in range(-1, 2):
            if dy == 0 and dx == 0:
                continue
            ny, nx = target.y + dy, target.x + dx
            if (game_map.is_walkable(ny, nx) and
                    game_map.get_enemy_at(ny, nx) is None):
                dist = abs(ny - enemy.pos.y) + abs(nx - enemy.pos.x)
                if dist < best_dist:
                    best_dist = dist
                    best_pos = Position(ny, nx)

    if best_pos:
        enemy.pos = best_pos
