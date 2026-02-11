"""Player module for Quakelike."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional

from quakelike.constants import (
    PLAYER_MAX_HEALTH, PLAYER_START_HEALTH, PLAYER_MAX_ARMOR,
    CHAR_PLAYER, COLOR_PLAYER, MELEE_DAMAGE_MIN, MELEE_DAMAGE_MAX,
)
from quakelike.entity import Entity, Position
from quakelike.inventory import Inventory
from quakelike.items import (
    Item, ItemType, ItemDef, AmmoType, AXE, create_item,
)


@dataclass
class Player(Entity):
    """The player character."""
    armor: int = 0
    armor_absorption: float = 0.0
    inventory: Inventory = field(default_factory=Inventory)
    equipped_weapon: Optional[Item] = None
    previous_weapon: Optional[Item] = None
    xp: int = 0
    level: int = 1
    current_map: int = 0

    # Powerup timers
    quad_damage_turns: int = 0
    invulnerability_turns: int = 0
    invisibility_turns: int = 0
    biosuit_turns: int = 0

    # Targeting
    target_index: int = -1

    @classmethod
    def create(cls, pos: Position) -> Player:
        """Create a new player with starting equipment."""
        player = cls(
            name='Player',
            char=CHAR_PLAYER,
            color=COLOR_PLAYER,
            pos=pos,
            health=PLAYER_START_HEALTH,
            max_health=PLAYER_MAX_HEALTH,
        )
        # Start with axe
        axe = create_item(AXE)
        player.inventory.add_item(axe)
        player.equipped_weapon = axe
        return player

    def take_damage(self, amount: int) -> int:
        """Take damage, accounting for armor absorption and invulnerability."""
        if self.invulnerability_turns > 0:
            return 0

        # Armor absorbs damage
        if self.armor > 0 and self.armor_absorption > 0:
            absorbed = int(amount * self.armor_absorption)
            absorbed = min(absorbed, self.armor)
            self.armor -= absorbed
            amount -= absorbed
            if self.armor <= 0:
                self.armor = 0
                self.armor_absorption = 0.0

        return super().take_damage(amount)

    def equip_weapon(self, item: Item) -> bool:
        """Equip a weapon from inventory."""
        if item.item_type != ItemType.WEAPON:
            return False
        if item not in self.inventory.items:
            return False
        self.previous_weapon = self.equipped_weapon
        self.equipped_weapon = item
        return True

    def swap_weapon(self) -> bool:
        """Swap to previously equipped weapon."""
        if self.previous_weapon is None:
            return False
        if self.previous_weapon not in self.inventory.items:
            return False
        self.equipped_weapon, self.previous_weapon = (
            self.previous_weapon, self.equipped_weapon
        )
        return True

    def can_fire(self) -> bool:
        """Check if current weapon can be fired."""
        if self.equipped_weapon is None:
            return False
        weapon_def = self.equipped_weapon.item_def
        if weapon_def.ammo_type is None:
            # Melee weapon, always can use
            return True
        return self.inventory.get_ammo_count(weapon_def.ammo_type) >= weapon_def.ammo_per_shot

    def apply_armor(self, item: Item) -> bool:
        """Apply armor from an item."""
        if item.item_type != ItemType.ARMOR:
            return False
        self.armor = item.item_def.armor_points
        self.armor_absorption = item.item_def.armor_absorption
        return True

    def apply_health(self, item: Item) -> int:
        """Apply health from an item. Returns amount healed."""
        if item.item_type != ItemType.HEALTH:
            return 0
        return self.heal(item.item_def.heal_amount)

    def apply_powerup(self, item: Item) -> bool:
        """Apply a powerup effect."""
        if item.item_type != ItemType.POWERUP:
            return False
        effect = item.item_def.powerup_effect
        duration = item.item_def.powerup_duration
        if effect == 'quad_damage':
            self.quad_damage_turns = duration
        elif effect == 'invulnerability':
            self.invulnerability_turns = duration
        elif effect == 'invisibility':
            self.invisibility_turns = duration
        elif effect == 'biosuit':
            self.biosuit_turns = duration
        else:
            return False
        return True

    def activate_item(self, item: Item) -> tuple[bool, str]:
        """Activate an item. Returns (success, message)."""
        if item.item_type == ItemType.WEAPON:
            if self.equip_weapon(item):
                return True, f'Equipped {item.name}.'
            return False, f'Cannot equip {item.name}.'

        if item.item_type == ItemType.AMMO:
            return False, 'Ammo cannot be activated, only stored.'

        if item.item_type == ItemType.ARMOR:
            if self.apply_armor(item):
                idx = self.inventory.find_by_name(item.name)
                if idx is not None:
                    self.inventory.remove_item(idx)
                return True, f'Applied {item.name}. Armor: {self.armor}'
            return False, f'Cannot apply {item.name}.'

        if item.item_type == ItemType.HEALTH:
            healed = self.apply_health(item)
            if healed > 0:
                idx = self.inventory.find_by_name(item.name)
                if idx is not None:
                    self.inventory.remove_item(idx)
                return True, f'Used {item.name}. Healed {healed} HP.'
            return False, 'Health is already full.'

        if item.item_type == ItemType.POWERUP:
            if self.apply_powerup(item):
                idx = self.inventory.find_by_name(item.name)
                if idx is not None:
                    self.inventory.remove_item(idx)
                return True, f'Activated {item.name}!'
            return False, f'Cannot use {item.name}.'

        return False, 'Cannot use this item.'

    def tick_powerups(self) -> list[str]:
        """Decrement powerup timers. Returns messages for expired powerups."""
        messages = []
        if self.quad_damage_turns > 0:
            self.quad_damage_turns -= 1
            if self.quad_damage_turns == 0:
                messages.append('Quad Damage has worn off.')
        if self.invulnerability_turns > 0:
            self.invulnerability_turns -= 1
            if self.invulnerability_turns == 0:
                messages.append('Invulnerability has worn off.')
        if self.invisibility_turns > 0:
            self.invisibility_turns -= 1
            if self.invisibility_turns == 0:
                messages.append('Invisibility has worn off.')
        if self.biosuit_turns > 0:
            self.biosuit_turns -= 1
            if self.biosuit_turns == 0:
                messages.append('Biosuit has worn off.')
        return messages

    def get_damage_multiplier(self) -> int:
        """Get current damage multiplier."""
        if self.quad_damage_turns > 0:
            return 4
        return 1

    def gain_xp(self, amount: int) -> tuple[int, bool]:
        """Gain XP. Returns (new_xp, leveled_up)."""
        self.xp += amount
        # Level up every 100 XP
        new_level = 1 + self.xp // 100
        if new_level > self.level:
            self.level = new_level
            self.max_health += 10  # Gain 10 max HP per level
            self.health = min(self.health + 10, self.max_health)
            return self.xp, True
        return self.xp, False

    def has_rune(self) -> bool:
        """Check if player has the Rune."""
        for item in self.inventory.items:
            if item.name == 'Rune':
                return True
        return False
