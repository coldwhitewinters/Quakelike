"""Base entity classes for Quakelike."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Position:
    """A position on the map."""
    y: int
    x: int

    def distance_to(self, other: Position) -> float:
        """Manhattan distance to another position."""
        return abs(self.y - other.y) + abs(self.x - other.x)

    def chebyshev_distance(self, other: Position) -> int:
        """Chebyshev distance (max of dx, dy) - used for adjacency checks."""
        return max(abs(self.y - other.y), abs(self.x - other.x))

    def __eq__(self, other):
        if not isinstance(other, Position):
            return NotImplemented
        return self.y == other.y and self.x == other.x

    def __hash__(self):
        return hash((self.y, self.x))

    def copy(self):
        return Position(self.y, self.x)


@dataclass
class Entity:
    """Base class for all game entities (player, enemies)."""
    name: str
    char: str
    color: str
    pos: Position
    health: int
    max_health: int
    is_alive: bool = True

    def take_damage(self, amount: int) -> int:
        """Apply damage and return actual damage dealt."""
        actual = min(amount, self.health)
        self.health -= actual
        if self.health <= 0:
            self.health = 0
            self.is_alive = False
        return actual

    def heal(self, amount: int) -> int:
        """Heal and return actual amount healed."""
        actual = min(amount, self.max_health - self.health)
        self.health += actual
        return actual
