"""Item definitions for Quakelike - all items from original Quake."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional  # used in create_item signature


class ItemType(Enum):
    WEAPON = auto()
    AMMO = auto()
    ARMOR = auto()
    HEALTH = auto()
    POWERUP = auto()


class AmmoType(Enum):
    SHELLS = auto()
    NAILS = auto()
    ROCKETS = auto()
    CELLS = auto()


@dataclass
class ItemDef:
    """Definition of an item type."""
    name: str
    item_type: ItemType
    char: str
    color: str
    # Weapon stats
    damage_min: int = 0
    damage_max: int = 0
    ammo_type: Optional[AmmoType] = None
    ammo_per_shot: int = 0
    weapon_range: int = 0  # 0 = melee, >0 = ranged (in tiles)
    # Ammo stats
    ammo_amount: int = 0
    # Armor stats
    armor_points: int = 0
    armor_absorption: float = 0.0  # fraction of damage absorbed
    # Health stats
    heal_amount: int = 0
    # Powerup stats
    powerup_duration: int = 0  # turns
    powerup_effect: str = ''
    # Combat properties
    has_splash_damage: bool = False
    # Display
    description: str = ''


@dataclass
class Item:
    """An instance of an item in the game world."""
    item_def: ItemDef
    quantity: int = 1

    @property
    def name(self) -> str:
        return self.item_def.name

    @property
    def item_type(self) -> ItemType:
        return self.item_def.item_type

    @property
    def char(self) -> str:
        """Get the display character for this item."""
        return self.item_def.char

    @property
    def color(self) -> str:
        """Get the display color for this item."""
        return self.item_def.color

    def can_stack_with(self, other: Item) -> bool:
        """Check if this item can stack with another."""
        return (self.item_def.item_type == ItemType.AMMO and
                self.item_def.name == other.item_def.name)

    def to_dict(self) -> dict:
        """Serialize to dictionary for save/load."""
        return {
            'item_name': self.item_def.name,
            'quantity': self.quantity,
        }


# ============================================================
# WEAPON DEFINITIONS
# ============================================================

AXE = ItemDef(
    name='Axe',
    item_type=ItemType.WEAPON,
    char='/',
    color='#C0C0C0',
    damage_min=10,
    damage_max=20,
    ammo_type=None,
    ammo_per_shot=0,
    weapon_range=1,
    description='A trusty axe for close combat.',
)

SHOTGUN = ItemDef(
    name='Shotgun',
    item_type=ItemType.WEAPON,
    char=')',  # shotgun
    color='#DAA520',
    damage_min=4,
    damage_max=24,  # 6 pellets, 4 damage each
    ammo_type=AmmoType.SHELLS,
    ammo_per_shot=1,
    weapon_range=15,
    description='Standard issue shotgun.',
)

SUPER_SHOTGUN = ItemDef(
    name='Double-Barrelled Shotgun',
    item_type=ItemType.WEAPON,
    char='}',  # double-barrelled
    color='#B8860B',
    damage_min=8,
    damage_max=48,  # 14 pellets, roughly
    ammo_type=AmmoType.SHELLS,
    ammo_per_shot=2,
    weapon_range=12,
    description='Double-barrelled shotgun. Devastating at close range.',
)

NAILGUN = ItemDef(
    name='Nailgun',
    item_type=ItemType.WEAPON,
    char='{',  # nailgun
    color='#808080',
    damage_min=9,
    damage_max=9,  # 9 damage per nail
    ammo_type=AmmoType.NAILS,
    ammo_per_shot=1,
    weapon_range=20,
    description='Fires nails at a rapid rate.',
)

SUPER_NAILGUN = ItemDef(
    name='Super Nailgun',
    item_type=ItemType.WEAPON,
    char='!',  # super nailgun
    color='#A9A9A9',
    damage_min=18,
    damage_max=18,  # 18 damage per shot (2 nails)
    ammo_type=AmmoType.NAILS,
    ammo_per_shot=2,
    weapon_range=20,
    description='Fires nails twice as fast.',
)

GRENADE_LAUNCHER = ItemDef(
    name='Grenade Launcher',
    item_type=ItemType.WEAPON,
    char='(',  # grenade launcher
    color='#556B2F',
    damage_min=50,
    damage_max=120,
    ammo_type=AmmoType.ROCKETS,
    ammo_per_shot=1,
    weapon_range=18,
    has_splash_damage=True,
    description='Lobs explosive grenades.',
)

ROCKET_LAUNCHER = ItemDef(
    name='Rocket Launcher',
    item_type=ItemType.WEAPON,
    char='=',  # rocket launcher
    color='#8B0000',
    damage_min=50,
    damage_max=120,
    ammo_type=AmmoType.ROCKETS,
    ammo_per_shot=1,
    weapon_range=25,
    has_splash_damage=True,
    description='Fires devastating rockets.',
)

THUNDERBOLT = ItemDef(
    name='Thunderbolt',
    item_type=ItemType.WEAPON,
    char='~',  # lightning gun
    color='#00BFFF',
    damage_min=30,
    damage_max=30,  # 30 damage per cell
    ammo_type=AmmoType.CELLS,
    ammo_per_shot=1,
    weapon_range=20,
    description='Lightning gun. Continuous beam of destruction.',
)

# ============================================================
# AMMO DEFINITIONS
# ============================================================

SHELLS_SMALL = ItemDef(
    name='Shells',
    item_type=ItemType.AMMO,
    char='|',
    color='#DAA520',
    ammo_type=AmmoType.SHELLS,
    ammo_amount=20,
    description='A box of shells.',
)

NAILS_SMALL = ItemDef(
    name='Nails',
    item_type=ItemType.AMMO,
    char='|',
    color='#808080',
    ammo_type=AmmoType.NAILS,
    ammo_amount=25,
    description='A box of nails.',
)

ROCKETS_SMALL = ItemDef(
    name='Rockets',
    item_type=ItemType.AMMO,
    char='|',
    color='#8B0000',
    ammo_type=AmmoType.ROCKETS,
    ammo_amount=5,
    description='A crate of rockets.',
)

CELLS_SMALL = ItemDef(
    name='Cells',
    item_type=ItemType.AMMO,
    char='|',
    color='#00BFFF',
    ammo_type=AmmoType.CELLS,
    ammo_amount=6,
    description='A pack of cells.',
)

# ============================================================
# ARMOR DEFINITIONS
# ============================================================

GREEN_ARMOR = ItemDef(
    name='Green Armor',
    item_type=ItemType.ARMOR,
    char='[',
    color='#00FF00',
    armor_points=100,
    armor_absorption=0.3,
    description='Green armor. Absorbs 30% of damage.',
)

YELLOW_ARMOR = ItemDef(
    name='Yellow Armor',
    item_type=ItemType.ARMOR,
    char='[',
    color='#FFD700',
    armor_points=150,
    armor_absorption=0.6,
    description='Yellow armor. Absorbs 60% of damage.',
)

RED_ARMOR = ItemDef(
    name='Red Armor',
    item_type=ItemType.ARMOR,
    char='[',
    color='#FF0000',
    armor_points=200,
    armor_absorption=0.8,
    description='Red armor. Absorbs 80% of damage.',
)

# ============================================================
# HEALTH DEFINITIONS
# ============================================================

SMALL_HEALTH = ItemDef(
    name='Small Health Pack',
    item_type=ItemType.HEALTH,
    char='+',
    color='#90EE90',
    heal_amount=15,
    description='Restores 15 health.',
)

MEDIUM_HEALTH = ItemDef(
    name='Medium Health Pack',
    item_type=ItemType.HEALTH,
    char='+',
    color='#FFFF00',
    heal_amount=25,
    description='Restores 25 health.',
)

MEGAHEALTH = ItemDef(
    name='Megahealth',
    item_type=ItemType.HEALTH,
    char='+',
    color='#0000FF',
    heal_amount=100,
    description='Overheals to 200 HP, decaying to 100 HP over time.',
)

# ============================================================
# POWERUP DEFINITIONS
# ============================================================

QUAD_DAMAGE = ItemDef(
    name='Quad Damage',
    item_type=ItemType.POWERUP,
    char='*',
    color='#9400D3',
    powerup_duration=30,
    powerup_effect='quad_damage',
    description='Quadruples damage for 30 turns.',
)

PENTAGRAM = ItemDef(
    name='Pentagram of Protection',
    item_type=ItemType.POWERUP,
    char='*',
    color='#FF1493',
    powerup_duration=30,
    powerup_effect='invulnerability',
    description='Invulnerability for 30 turns.',
)

RING_OF_SHADOWS = ItemDef(
    name='Ring of Shadows',
    item_type=ItemType.POWERUP,
    char='*',
    color='#708090',
    powerup_duration=30,
    powerup_effect='invisibility',
    description='Invisibility for 30 turns.',
)

BIOSUIT = ItemDef(
    name='Biosuit',
    item_type=ItemType.POWERUP,
    char='*',
    color='#32CD32',
    powerup_duration=30,
    powerup_effect='biosuit',
    description='Protection from environmental damage for 30 turns.',
)

# ============================================================
# ITEM REGISTRIES
# ============================================================

ALL_WEAPONS = [AXE, SHOTGUN, SUPER_SHOTGUN, NAILGUN, SUPER_NAILGUN,
               GRENADE_LAUNCHER, ROCKET_LAUNCHER, THUNDERBOLT]

ALL_AMMO = [SHELLS_SMALL, NAILS_SMALL, ROCKETS_SMALL, CELLS_SMALL]

ALL_ARMOR = [GREEN_ARMOR, YELLOW_ARMOR, RED_ARMOR]

ALL_HEALTH = [SMALL_HEALTH, MEDIUM_HEALTH, MEGAHEALTH]

ALL_POWERUPS = [QUAD_DAMAGE, PENTAGRAM, RING_OF_SHADOWS, BIOSUIT]

# ============================================================
# SPECIAL ITEMS
# ============================================================

RUNE = ItemDef(
    name='Rune',
    item_type=ItemType.POWERUP,
    char='&',
    color='#FFD700',
    description='The Rune of power. Bring it to the entrance to win.',
)

ALL_ITEMS = ALL_WEAPONS + ALL_AMMO + ALL_ARMOR + ALL_HEALTH + ALL_POWERUPS + [RUNE]

ITEM_BY_NAME = {item.name: item for item in ALL_ITEMS}


def create_item(item_def: ItemDef, quantity: Optional[int] = None) -> Item:
    """Create an item instance from a definition.

    For ammo items, quantity defaults to the ammo_amount from the definition.
    For all other items, quantity defaults to 1.
    """
    if quantity is None:
        if item_def.item_type == ItemType.AMMO:
            quantity = item_def.ammo_amount
        else:
            quantity = 1
    return Item(item_def=item_def, quantity=quantity)


def item_from_name(name: str, quantity: int = 1) -> Item:
    """Create an item instance by name lookup."""
    return Item(item_def=ITEM_BY_NAME[name], quantity=quantity)
