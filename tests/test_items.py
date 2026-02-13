"""Tests for the items module."""

import pytest
from quakelike.items import (
    Item, ItemDef, ItemType, AmmoType,
    AXE, SHOTGUN, SUPER_SHOTGUN, NAILGUN, SUPER_NAILGUN,
    GRENADE_LAUNCHER, ROCKET_LAUNCHER, THUNDERBOLT,
    SHELLS_SMALL, NAILS_SMALL, ROCKETS_SMALL, CELLS_SMALL,
    GREEN_ARMOR, YELLOW_ARMOR, RED_ARMOR,
    SMALL_HEALTH, MEDIUM_HEALTH, MEGAHEALTH,
    QUAD_DAMAGE, PENTAGRAM, RING_OF_SHADOWS, BIOSUIT,
    ALL_WEAPONS, ALL_AMMO, ALL_ARMOR, ALL_HEALTH, ALL_POWERUPS,
    ALL_ITEMS, ITEM_BY_NAME, create_item, item_from_name,
)


class TestItemDefinitions:
    """Verify all Quake items are present and properly defined."""

    def test_all_weapons_present(self):
        """All 8 Quake weapons must be defined."""
        weapon_names = [w.name for w in ALL_WEAPONS]
        assert 'Axe' in weapon_names
        assert 'Shotgun' in weapon_names
        assert 'Double-Barrelled Shotgun' in weapon_names
        assert 'Nailgun' in weapon_names
        assert 'Super Nailgun' in weapon_names
        assert 'Grenade Launcher' in weapon_names
        assert 'Rocket Launcher' in weapon_names
        assert 'Thunderbolt' in weapon_names
        assert len(ALL_WEAPONS) == 8

    def test_all_ammo_types_present(self):
        """All 4 Quake ammo types must be defined."""
        ammo_names = [a.name for a in ALL_AMMO]
        assert 'Shells' in ammo_names
        assert 'Nails' in ammo_names
        assert 'Rockets' in ammo_names
        assert 'Cells' in ammo_names
        assert len(ALL_AMMO) == 4

    def test_all_armor_types_present(self):
        """All 3 Quake armor types must be defined."""
        armor_names = [a.name for a in ALL_ARMOR]
        assert 'Green Armor' in armor_names
        assert 'Yellow Armor' in armor_names
        assert 'Red Armor' in armor_names
        assert len(ALL_ARMOR) == 3

    def test_all_health_items_present(self):
        """All 3 Quake health items must be defined."""
        assert len(ALL_HEALTH) == 3
        names = [h.name for h in ALL_HEALTH]
        assert 'Small Health Pack' in names
        assert 'Medium Health Pack' in names
        assert 'Megahealth' in names

    def test_all_powerups_present(self):
        """All 4 Quake powerups must be defined."""
        names = [p.name for p in ALL_POWERUPS]
        assert 'Quad Damage' in names
        assert 'Pentagram of Protection' in names
        assert 'Ring of Shadows' in names
        assert 'Biosuit' in names
        assert len(ALL_POWERUPS) == 4

    def test_total_item_count(self):
        """8 weapons + 4 ammo + 3 armor + 3 health + 4 powerups + 1 rune = 23 items."""
        assert len(ALL_ITEMS) == 23


class TestWeaponStats:
    """Verify weapon stats match Quake behavior."""

    def test_axe_is_melee(self):
        assert AXE.weapon_range == 1
        assert AXE.ammo_type is None
        assert AXE.ammo_per_shot == 0

    def test_shotgun_uses_shells(self):
        assert SHOTGUN.ammo_type == AmmoType.SHELLS
        assert SHOTGUN.ammo_per_shot == 1
        assert SHOTGUN.weapon_range > 1

    def test_super_shotgun_uses_two_shells(self):
        assert SUPER_SHOTGUN.ammo_type == AmmoType.SHELLS
        assert SUPER_SHOTGUN.ammo_per_shot == 2

    def test_nailgun_uses_nails(self):
        assert NAILGUN.ammo_type == AmmoType.NAILS
        assert NAILGUN.ammo_per_shot == 1

    def test_super_nailgun_uses_two_nails(self):
        assert SUPER_NAILGUN.ammo_type == AmmoType.NAILS
        assert SUPER_NAILGUN.ammo_per_shot == 2

    def test_grenade_launcher_uses_rockets(self):
        assert GRENADE_LAUNCHER.ammo_type == AmmoType.ROCKETS
        assert GRENADE_LAUNCHER.ammo_per_shot == 1

    def test_rocket_launcher_uses_rockets(self):
        assert ROCKET_LAUNCHER.ammo_type == AmmoType.ROCKETS
        assert ROCKET_LAUNCHER.ammo_per_shot == 1

    def test_thunderbolt_uses_cells(self):
        assert THUNDERBOLT.ammo_type == AmmoType.CELLS
        assert THUNDERBOLT.ammo_per_shot == 1

    def test_ranged_weapons_have_range(self):
        ranged = [SHOTGUN, SUPER_SHOTGUN, NAILGUN, SUPER_NAILGUN,
                  GRENADE_LAUNCHER, ROCKET_LAUNCHER, THUNDERBOLT]
        for w in ranged:
            assert w.weapon_range > 1, f'{w.name} should have range > 1'


class TestArmorStats:
    def test_green_armor_absorption(self):
        assert GREEN_ARMOR.armor_points == 100
        assert GREEN_ARMOR.armor_absorption == 0.3

    def test_yellow_armor_absorption(self):
        assert YELLOW_ARMOR.armor_points == 150
        assert YELLOW_ARMOR.armor_absorption == 0.6

    def test_red_armor_absorption(self):
        assert RED_ARMOR.armor_points == 200
        assert RED_ARMOR.armor_absorption == 0.8


class TestHealthStats:
    def test_small_health(self):
        assert SMALL_HEALTH.heal_amount == 15

    def test_medium_health(self):
        assert MEDIUM_HEALTH.heal_amount == 25

    def test_megahealth(self):
        assert MEGAHEALTH.heal_amount == 100


class TestPowerupStats:
    def test_quad_damage(self):
        assert QUAD_DAMAGE.powerup_effect == 'quad_damage'
        assert QUAD_DAMAGE.powerup_duration > 0

    def test_pentagram(self):
        assert PENTAGRAM.powerup_effect == 'invulnerability'
        assert PENTAGRAM.powerup_duration > 0

    def test_ring_of_shadows(self):
        assert RING_OF_SHADOWS.powerup_effect == 'invisibility'
        assert RING_OF_SHADOWS.powerup_duration > 0

    def test_biosuit(self):
        assert BIOSUIT.powerup_effect == 'biosuit'
        assert BIOSUIT.powerup_duration > 0


class TestItemCreation:
    def test_create_item(self):
        item = create_item(AXE)
        assert item.name == 'Axe'
        assert item.item_type == ItemType.WEAPON
        assert item.quantity == 1

    def test_create_ammo_with_quantity(self):
        item = create_item(SHELLS_SMALL, quantity=40)
        assert item.name == 'Shells'
        assert item.quantity == 40

    def test_item_from_name(self):
        item = item_from_name('Shotgun')
        assert item.name == 'Shotgun'
        assert item.item_type == ItemType.WEAPON

    def test_item_from_name_not_found(self):
        with pytest.raises(KeyError):
            item_from_name('Nonexistent')


class TestItemStacking:
    def test_ammo_can_stack(self):
        item1 = create_item(SHELLS_SMALL)
        item2 = create_item(SHELLS_SMALL)
        assert item1.can_stack_with(item2)

    def test_different_ammo_cannot_stack(self):
        shells = create_item(SHELLS_SMALL)
        nails = create_item(NAILS_SMALL)
        assert not shells.can_stack_with(nails)

    def test_weapons_cannot_stack(self):
        axe1 = create_item(AXE)
        axe2 = create_item(AXE)
        assert not axe1.can_stack_with(axe2)

    def test_ammo_only_stacks(self):
        """Only ammo should stack, not weapons or other items."""
        weapon = create_item(SHOTGUN)
        ammo = create_item(SHELLS_SMALL)
        assert not weapon.can_stack_with(ammo)


class TestItemSerialization:
    def test_to_dict(self):
        item = create_item(SHOTGUN)
        d = item.to_dict()
        assert d['item_name'] == 'Shotgun'
        assert d['quantity'] == 1

    def test_to_dict_with_quantity(self):
        item = create_item(SHELLS_SMALL, quantity=30)
        d = item.to_dict()
        assert d['item_name'] == 'Shells'
        assert d['quantity'] == 30
