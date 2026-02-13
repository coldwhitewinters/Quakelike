"""Tests for the inventory module."""

import pytest
from quakelike.inventory import Inventory
from quakelike.items import (
    create_item, ItemType, AmmoType,
    AXE, SHOTGUN, SHELLS_SMALL, NAILS_SMALL, GREEN_ARMOR,
    SMALL_HEALTH, QUAD_DAMAGE,
)
from quakelike.constants import MAX_INVENTORY_SIZE


class TestInventoryBasics:
    def test_empty_inventory(self):
        inv = Inventory()
        assert inv.count == 0
        assert not inv.is_full
        assert inv.max_size == MAX_INVENTORY_SIZE

    def test_add_item(self):
        inv = Inventory()
        item = create_item(AXE)
        assert inv.add_item(item)
        assert inv.count == 1

    def test_remove_item(self):
        inv = Inventory()
        item = create_item(AXE)
        inv.add_item(item)
        removed = inv.remove_item(0)
        assert removed is item
        assert inv.count == 0

    def test_remove_invalid_index(self):
        inv = Inventory()
        assert inv.remove_item(0) is None
        assert inv.remove_item(-1) is None

    def test_get_item(self):
        inv = Inventory()
        item = create_item(SHOTGUN)
        inv.add_item(item)
        assert inv.get_item(0) is item
        assert inv.get_item(1) is None


class TestInventoryCapacity:
    def test_max_capacity(self):
        """Inventory should hold at most 10 items."""
        assert MAX_INVENTORY_SIZE == 10

    def test_inventory_full(self):
        inv = Inventory()
        for i in range(MAX_INVENTORY_SIZE):
            inv.add_item(create_item(AXE))
        assert inv.is_full
        assert not inv.add_item(create_item(SHOTGUN))

    def test_can_add_when_full_but_ammo_stacks(self):
        """Even when full, ammo can be added if same type exists."""
        inv = Inventory()
        inv.add_item(create_item(SHELLS_SMALL))
        for i in range(MAX_INVENTORY_SIZE - 1):
            inv.add_item(create_item(AXE))
        assert inv.is_full
        # Should still be able to add shells (stacks)
        more_shells = create_item(SHELLS_SMALL)
        assert inv.can_add(more_shells)
        assert inv.add_item(more_shells)

    def test_cannot_add_different_ammo_when_full(self):
        inv = Inventory()
        for i in range(MAX_INVENTORY_SIZE):
            inv.add_item(create_item(AXE))
        nails = create_item(NAILS_SMALL)
        assert not inv.can_add(nails)


class TestAmmoStacking:
    def test_ammo_stacks(self):
        inv = Inventory()
        shells1 = create_item(SHELLS_SMALL)  # 20 shells
        shells2 = create_item(SHELLS_SMALL)  # 20 more
        inv.add_item(shells1)
        inv.add_item(shells2)
        assert inv.count == 1  # Should be stacked
        assert inv.items[0].quantity == 40

    def test_different_ammo_doesnt_stack(self):
        inv = Inventory()
        shells = create_item(SHELLS_SMALL)
        nails = create_item(NAILS_SMALL)
        inv.add_item(shells)
        inv.add_item(nails)
        assert inv.count == 2

    def test_weapons_dont_stack(self):
        inv = Inventory()
        axe1 = create_item(AXE)
        axe2 = create_item(AXE)
        inv.add_item(axe1)
        inv.add_item(axe2)
        assert inv.count == 2  # Two separate axe entries


class TestAmmoManagement:
    def test_find_ammo(self):
        inv = Inventory()
        shells = create_item(SHELLS_SMALL)
        inv.add_item(shells)
        found = inv.find_ammo(AmmoType.SHELLS)
        assert found is shells

    def test_find_ammo_missing(self):
        inv = Inventory()
        assert inv.find_ammo(AmmoType.SHELLS) is None

    def test_get_ammo_count(self):
        inv = Inventory()
        shells = create_item(SHELLS_SMALL)  # 20
        inv.add_item(shells)
        assert inv.get_ammo_count(AmmoType.SHELLS) == 20
        assert inv.get_ammo_count(AmmoType.NAILS) == 0

    def test_consume_ammo(self):
        inv = Inventory()
        shells = create_item(SHELLS_SMALL)  # 20
        inv.add_item(shells)
        assert inv.consume_ammo(AmmoType.SHELLS, 5)
        assert inv.get_ammo_count(AmmoType.SHELLS) == 15

    def test_consume_ammo_exact(self):
        inv = Inventory()
        shells = create_item(SHELLS_SMALL)  # 20
        inv.add_item(shells)
        assert inv.consume_ammo(AmmoType.SHELLS, 20)
        assert inv.get_ammo_count(AmmoType.SHELLS) == 0
        assert inv.count == 0  # Item removed when depleted

    def test_consume_ammo_insufficient(self):
        inv = Inventory()
        shells = create_item(SHELLS_SMALL)  # 20
        inv.add_item(shells)
        assert not inv.consume_ammo(AmmoType.SHELLS, 25)
        assert inv.get_ammo_count(AmmoType.SHELLS) == 20  # Unchanged

    def test_consume_ammo_none_available(self):
        inv = Inventory()
        assert not inv.consume_ammo(AmmoType.ROCKETS, 1)


class TestInventorySearch:
    def test_find_by_name(self):
        inv = Inventory()
        inv.add_item(create_item(AXE))
        inv.add_item(create_item(SHOTGUN))
        assert inv.find_by_name('Shotgun') == 1
        assert inv.find_by_name('Axe') == 0

    def test_find_by_name_missing(self):
        inv = Inventory()
        assert inv.find_by_name('Nonexistent') is None

    def test_find_by_identity(self):
        inv = Inventory()
        axe1 = create_item(AXE)
        axe2 = create_item(AXE)
        inv.add_item(axe1)
        inv.add_item(axe2)
        assert inv.find_by_identity(axe1) == 0
        assert inv.find_by_identity(axe2) == 1

    def test_find_by_identity_not_present(self):
        inv = Inventory()
        axe1 = create_item(AXE)
        axe2 = create_item(AXE)
        inv.add_item(axe1)
        assert inv.find_by_identity(axe2) is None


class TestInventorySerialization:
    def test_to_dict(self):
        inv = Inventory()
        inv.add_item(create_item(AXE))
        inv.add_item(create_item(SHELLS_SMALL))
        data = inv.to_dict()
        assert len(data) == 2
        assert data[0]['item_name'] == 'Axe'
        assert data[1]['item_name'] == 'Shells'
