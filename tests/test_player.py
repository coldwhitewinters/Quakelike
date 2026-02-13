"""Tests for the player module."""

import pytest
from quakelike.entity import Position
from quakelike.player import Player
from quakelike.items import (
    create_item, ItemType, RUNE,
    AXE, SHOTGUN, SUPER_SHOTGUN, SHELLS_SMALL, NAILS_SMALL,
    GREEN_ARMOR, YELLOW_ARMOR, RED_ARMOR,
    SMALL_HEALTH, MEDIUM_HEALTH, MEGAHEALTH,
    QUAD_DAMAGE, PENTAGRAM, RING_OF_SHADOWS, BIOSUIT,
)
from quakelike.constants import PLAYER_START_HEALTH, PLAYER_MAX_HEALTH


class TestPlayerCreation:
    def test_create_player(self):
        p = Player.create(Position(5, 5))
        assert p.health == PLAYER_START_HEALTH
        assert p.max_health == PLAYER_MAX_HEALTH
        assert p.armor == 0
        assert p.xp == 0
        assert p.level == 1
        assert p.is_alive
        assert p.pos == Position(5, 5)

    def test_starts_with_axe(self):
        p = Player.create(Position(0, 0))
        assert p.equipped_weapon is not None
        assert p.equipped_weapon.name == 'Axe'
        assert p.inventory.count == 1


class TestPlayerDamage:
    def test_take_damage_no_armor(self):
        p = Player.create(Position(0, 0))
        actual = p.take_damage(30)
        assert actual == 30
        assert p.health == PLAYER_START_HEALTH - 30

    def test_take_damage_with_armor(self):
        p = Player.create(Position(0, 0))
        p.armor = 100
        p.armor_absorption = 0.3  # Green armor
        actual = p.take_damage(100)
        # 30% absorbed by armor: 30 from armor, 70 from health
        assert p.armor == 70
        assert p.health == PLAYER_START_HEALTH - 70

    def test_take_damage_armor_depleted(self):
        p = Player.create(Position(0, 0))
        p.armor = 10
        p.armor_absorption = 0.8  # Red armor absorption
        # Red armor would absorb 80 of 100 = 80, but only 10 armor left
        actual = p.take_damage(100)
        assert p.armor == 0
        assert p.armor_absorption == 0.0
        # 10 absorbed, 90 to health
        assert p.health == PLAYER_START_HEALTH - 90

    def test_invulnerability_blocks_all_damage(self):
        p = Player.create(Position(0, 0))
        p.invulnerability_turns = 5
        actual = p.take_damage(999)
        assert actual == 0
        assert p.health == PLAYER_START_HEALTH

    def test_lethal_damage_kills_player(self):
        p = Player.create(Position(0, 0))
        p.take_damage(PLAYER_START_HEALTH)
        assert not p.is_alive
        assert p.health == 0


class TestPlayerWeapons:
    def test_equip_weapon(self):
        p = Player.create(Position(0, 0))
        shotgun = create_item(SHOTGUN)
        p.inventory.add_item(shotgun)
        assert p.equip_weapon(shotgun)
        assert p.equipped_weapon is shotgun

    def test_equip_sets_previous(self):
        p = Player.create(Position(0, 0))
        axe = p.equipped_weapon
        shotgun = create_item(SHOTGUN)
        p.inventory.add_item(shotgun)
        p.equip_weapon(shotgun)
        assert p.previous_weapon is axe

    def test_equip_non_weapon_fails(self):
        p = Player.create(Position(0, 0))
        health = create_item(SMALL_HEALTH)
        p.inventory.add_item(health)
        assert not p.equip_weapon(health)

    def test_equip_not_in_inventory_fails(self):
        p = Player.create(Position(0, 0))
        shotgun = create_item(SHOTGUN)
        assert not p.equip_weapon(shotgun)

    def test_swap_weapon(self):
        p = Player.create(Position(0, 0))
        shotgun = create_item(SHOTGUN)
        p.inventory.add_item(shotgun)
        axe = p.equipped_weapon
        p.equip_weapon(shotgun)
        # Now swap back
        assert p.swap_weapon()
        assert p.equipped_weapon is axe
        assert p.previous_weapon is shotgun

    def test_swap_no_previous(self):
        p = Player.create(Position(0, 0))
        assert not p.swap_weapon()

    def test_can_fire_axe(self):
        """Axe has no ammo requirement."""
        p = Player.create(Position(0, 0))
        assert p.can_fire()

    def test_can_fire_with_ammo(self):
        p = Player.create(Position(0, 0))
        shotgun = create_item(SHOTGUN)
        shells = create_item(SHELLS_SMALL)
        p.inventory.add_item(shotgun)
        p.inventory.add_item(shells)
        p.equip_weapon(shotgun)
        assert p.can_fire()

    def test_cannot_fire_without_ammo(self):
        p = Player.create(Position(0, 0))
        shotgun = create_item(SHOTGUN)
        p.inventory.add_item(shotgun)
        p.equip_weapon(shotgun)
        assert not p.can_fire()

    def test_cannot_fire_no_weapon(self):
        p = Player.create(Position(0, 0))
        p.equipped_weapon = None
        assert not p.can_fire()


class TestPlayerArmor:
    def test_apply_green_armor(self):
        p = Player.create(Position(0, 0))
        armor = create_item(GREEN_ARMOR)
        p.inventory.add_item(armor)
        assert p.apply_armor(armor)
        assert p.armor == 100
        assert p.armor_absorption == 0.3

    def test_apply_yellow_armor(self):
        p = Player.create(Position(0, 0))
        armor = create_item(YELLOW_ARMOR)
        p.inventory.add_item(armor)
        assert p.apply_armor(armor)
        assert p.armor == 150
        assert p.armor_absorption == 0.6

    def test_apply_red_armor(self):
        p = Player.create(Position(0, 0))
        armor = create_item(RED_ARMOR)
        p.inventory.add_item(armor)
        assert p.apply_armor(armor)
        assert p.armor == 200
        assert p.armor_absorption == 0.8

    def test_apply_non_armor_fails(self):
        p = Player.create(Position(0, 0))
        assert not p.apply_armor(create_item(AXE))


class TestPlayerHealth:
    def test_apply_health(self):
        p = Player.create(Position(0, 0))
        p.health = 50
        healed = p.apply_health(create_item(SMALL_HEALTH))
        assert healed == 15
        assert p.health == 65

    def test_apply_health_capped(self):
        p = Player.create(Position(0, 0))
        p.health = 95
        healed = p.apply_health(create_item(SMALL_HEALTH))
        assert healed == 5
        assert p.health == 100

    def test_apply_health_at_max(self):
        p = Player.create(Position(0, 0))
        healed = p.apply_health(create_item(SMALL_HEALTH))
        assert healed == 0

    def test_apply_non_health_fails(self):
        p = Player.create(Position(0, 0))
        p.health = 50
        assert p.apply_health(create_item(AXE)) == 0


class TestPlayerPowerups:
    def test_quad_damage(self):
        p = Player.create(Position(0, 0))
        item = create_item(QUAD_DAMAGE)
        assert p.apply_powerup(item)
        assert p.quad_damage_turns == QUAD_DAMAGE.powerup_duration
        assert p.get_damage_multiplier() == 4

    def test_invulnerability(self):
        p = Player.create(Position(0, 0))
        item = create_item(PENTAGRAM)
        assert p.apply_powerup(item)
        assert p.invulnerability_turns > 0

    def test_invisibility(self):
        p = Player.create(Position(0, 0))
        item = create_item(RING_OF_SHADOWS)
        assert p.apply_powerup(item)
        assert p.invisibility_turns > 0

    def test_biosuit(self):
        p = Player.create(Position(0, 0))
        item = create_item(BIOSUIT)
        assert p.apply_powerup(item)
        assert p.biosuit_turns > 0

    def test_powerup_tick_down(self):
        p = Player.create(Position(0, 0))
        p.quad_damage_turns = 2
        msgs = p.tick_powerups()
        assert p.quad_damage_turns == 1
        assert len(msgs) == 0

    def test_powerup_expiry_message(self):
        p = Player.create(Position(0, 0))
        p.quad_damage_turns = 1
        msgs = p.tick_powerups()
        assert p.quad_damage_turns == 0
        assert p.get_damage_multiplier() == 1
        assert any('Quad Damage' in m for m in msgs)

    def test_apply_non_powerup_fails(self):
        p = Player.create(Position(0, 0))
        assert not p.apply_powerup(create_item(AXE))


class TestPlayerActivateItem:
    def test_activate_weapon_equips(self):
        p = Player.create(Position(0, 0))
        shotgun = create_item(SHOTGUN)
        p.inventory.add_item(shotgun)
        success, msg = p.activate_item(shotgun)
        assert success
        assert p.equipped_weapon is shotgun
        assert 'Equipped' in msg

    def test_activate_ammo_fails(self):
        """Ammo cannot be activated, only stored."""
        p = Player.create(Position(0, 0))
        shells = create_item(SHELLS_SMALL)
        p.inventory.add_item(shells)
        success, msg = p.activate_item(shells)
        assert not success
        assert 'cannot be activated' in msg.lower()

    def test_activate_armor_consumes(self):
        p = Player.create(Position(0, 0))
        armor = create_item(GREEN_ARMOR)
        p.inventory.add_item(armor)
        initial_count = p.inventory.count
        success, msg = p.activate_item(armor)
        assert success
        assert p.armor == 100
        assert p.inventory.count == initial_count - 1

    def test_activate_health_consumes(self):
        p = Player.create(Position(0, 0))
        p.health = 50
        health = create_item(SMALL_HEALTH)
        p.inventory.add_item(health)
        success, msg = p.activate_item(health)
        assert success
        assert p.health == 65
        assert p.inventory.find_by_name('Small Health Pack') is None

    def test_activate_health_at_full_fails(self):
        p = Player.create(Position(0, 0))
        health = create_item(SMALL_HEALTH)
        p.inventory.add_item(health)
        success, msg = p.activate_item(health)
        assert not success

    def test_activate_powerup_consumes(self):
        p = Player.create(Position(0, 0))
        quad = create_item(QUAD_DAMAGE)
        p.inventory.add_item(quad)
        success, msg = p.activate_item(quad)
        assert success
        assert p.quad_damage_turns > 0
        assert p.inventory.find_by_name('Quad Damage') is None


class TestPlayerXP:
    def test_gain_xp(self):
        p = Player.create(Position(0, 0))
        xp, leveled = p.gain_xp(50)
        assert xp == 50
        assert not leveled

    def test_level_up(self):
        p = Player.create(Position(0, 0))
        xp, leveled = p.gain_xp(100)
        assert leveled
        assert p.level == 2
        assert p.max_health == PLAYER_MAX_HEALTH + 10

    def test_multi_level_up(self):
        p = Player.create(Position(0, 0))
        p.gain_xp(300)
        assert p.level == 4


class TestPlayerRune:
    def test_no_rune_initially(self):
        p = Player.create(Position(0, 0))
        assert not p.has_rune()

    def test_has_rune(self):
        p = Player.create(Position(0, 0))
        rune = create_item(RUNE)
        p.inventory.add_item(rune)
        assert p.has_rune()


class TestArmorReplacement:
    """Armor should only replace if the new armor is better."""

    def test_green_does_not_replace_red(self):
        p = Player.create(Position(0, 0))
        # Apply red armor first
        red = create_item(RED_ARMOR)
        p.inventory.add_item(red)
        p.apply_armor(red)
        assert p.armor == 200
        assert p.armor_absorption == 0.8

        # Green armor is worse, should NOT replace
        green = create_item(GREEN_ARMOR)
        p.inventory.add_item(green)
        result = p.apply_armor(green)
        assert not result
        assert p.armor == 200  # Red remains
        assert p.armor_absorption == 0.8

    def test_red_replaces_green(self):
        p = Player.create(Position(0, 0))
        green = create_item(GREEN_ARMOR)
        p.inventory.add_item(green)
        p.apply_armor(green)
        assert p.armor == 100
        assert p.armor_absorption == 0.3

        red = create_item(RED_ARMOR)
        p.inventory.add_item(red)
        result = p.apply_armor(red)
        assert result
        assert p.armor == 200
        assert p.armor_absorption == 0.8

    def test_yellow_replaces_green(self):
        p = Player.create(Position(0, 0))
        green = create_item(GREEN_ARMOR)
        p.inventory.add_item(green)
        p.apply_armor(green)

        yellow = create_item(YELLOW_ARMOR)
        p.inventory.add_item(yellow)
        result = p.apply_armor(yellow)
        assert result
        assert p.armor == 150

    def test_armor_replaces_no_armor(self):
        p = Player.create(Position(0, 0))
        green = create_item(GREEN_ARMOR)
        p.inventory.add_item(green)
        result = p.apply_armor(green)
        assert result


class TestItemRemovalByIdentity:
    """Items should be removed by identity (is), not by name."""

    def test_activate_removes_correct_health_pack(self):
        p = Player.create(Position(0, 0))
        p.health = 50
        hp1 = create_item(SMALL_HEALTH)
        hp2 = create_item(SMALL_HEALTH)
        p.inventory.add_item(hp1)
        p.inventory.add_item(hp2)
        assert p.inventory.count == 3  # axe + 2 health packs

        # Activate hp2 specifically
        success, msg = p.activate_item(hp2)
        assert success
        assert p.inventory.count == 2  # axe + hp1
        # Check by identity (is), not equality (==)
        assert any(item is hp1 for item in p.inventory.items)
        assert not any(item is hp2 for item in p.inventory.items)

    def test_activate_armor_removes_correct_item(self):
        p = Player.create(Position(0, 0))
        g1 = create_item(GREEN_ARMOR)
        y1 = create_item(YELLOW_ARMOR)
        p.inventory.add_item(g1)
        p.inventory.add_item(y1)

        # Activate yellow (which is better than green)
        success, msg = p.activate_item(y1)
        assert success
        assert g1 in p.inventory.items
        assert y1 not in p.inventory.items
