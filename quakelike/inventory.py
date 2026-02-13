"""Inventory system for Quakelike."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from quakelike.constants import MAX_INVENTORY_SIZE
from quakelike.items import Item, ItemType, AmmoType


@dataclass
class Inventory:
    """Player inventory with a maximum capacity."""
    items: list[Item] = field(default_factory=list)
    max_size: int = MAX_INVENTORY_SIZE

    @property
    def count(self) -> int:
        return len(self.items)

    @property
    def is_full(self) -> bool:
        return len(self.items) >= self.max_size

    def can_add(self, item: Item) -> bool:
        """Check if an item can be added (stacking or free space)."""
        if item.item_type == ItemType.AMMO:
            existing = self.find_ammo(item.item_def.ammo_type)
            if existing is not None:
                return True
        return not self.is_full

    def add_item(self, item: Item) -> bool:
        """Add an item to inventory. Returns True if successful."""
        if item.item_type == ItemType.AMMO:
            existing = self.find_ammo(item.item_def.ammo_type)
            if existing is not None:
                existing.quantity += item.quantity
                return True
        if self.is_full:
            return False
        self.items.append(item)
        return True

    def remove_item(self, index: int) -> Optional[Item]:
        """Remove and return item at index."""
        if 0 <= index < len(self.items):
            return self.items.pop(index)
        return None

    def get_item(self, index: int) -> Optional[Item]:
        """Get item at index without removing."""
        if 0 <= index < len(self.items):
            return self.items[index]
        return None

    def find_ammo(self, ammo_type: AmmoType) -> Optional[Item]:
        """Find ammo of a given type in inventory."""
        for item in self.items:
            if (item.item_type == ItemType.AMMO and
                    item.item_def.ammo_type == ammo_type):
                return item
        return None

    def get_ammo_count(self, ammo_type: AmmoType) -> int:
        """Get total ammo count for a type."""
        ammo = self.find_ammo(ammo_type)
        return ammo.quantity if ammo else 0

    def consume_ammo(self, ammo_type: AmmoType, amount: int) -> bool:
        """Consume ammo. Returns True if enough ammo was available."""
        ammo = self.find_ammo(ammo_type)
        if ammo is None or ammo.quantity < amount:
            return False
        ammo.quantity -= amount
        if ammo.quantity <= 0:
            self.items.remove(ammo)
        return True

    def find_by_name(self, name: str) -> Optional[int]:
        """Find index of item by name."""
        for i, item in enumerate(self.items):
            if item.name == name:
                return i
        return None

    def find_by_identity(self, target: Item) -> Optional[int]:
        """Find index of a specific item instance by identity (is, not ==)."""
        for i, item in enumerate(self.items):
            if item is target:
                return i
        return None

    def to_dict(self) -> list[dict]:
        """Serialize for save/load."""
        return [item.to_dict() for item in self.items]
