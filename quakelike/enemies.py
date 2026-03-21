"""Enemy definitions for Quakelike - all enemies from original Quake."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Optional

from quakelike.entity import Entity, Position
from quakelike.items import AmmoType


class AttackType(Enum):
    MELEE = auto()
    RANGED = auto()
    LEAP = auto()
    EXPLODE = auto()


@dataclass
class AttackDef:
    """Definition of an enemy attack."""
    attack_type: AttackType
    damage_min: int
    damage_max: int
    attack_range: int  # tiles
    cooldown: int = 1  # turns between attacks
    projectile_char: str = ''
    description: str = ''


@dataclass
class EnemyDef:
    """Definition of an enemy type."""
    name: str
    char: str
    color: str
    health: int
    speed: int  # turns between moves (1 = every turn, 2 = every other turn)
    attacks: list[AttackDef] = field(default_factory=list)
    xp_value: int = 0
    can_fly: bool = False
    can_swim: bool = False
    avoids_water: bool = True
    requires_water: bool = False
    description: str = ''
    min_map_level: int = 1  # earliest map this enemy can appear on
    ammo_drop: Optional[str] = None  # item name to drop on death, or None


@dataclass
class Enemy(Entity):
    """An enemy instance in the game world."""
    enemy_def: EnemyDef = None  # type: ignore
    current_target: Optional[Entity] = field(default=None, repr=False)
    attack_cooldown: int = 0
    move_timer: int = 0
    alerted: bool = False
    xp_value: int = 0
    death_processed: bool = False  # set True after corpse/ammo drop is placed

    @classmethod
    def from_def(cls, enemy_def: EnemyDef, pos: Position) -> Enemy:
        """Create an enemy instance from a definition."""
        return cls(
            name=enemy_def.name,
            char=enemy_def.char,
            color=enemy_def.color,
            pos=pos,
            health=enemy_def.health,
            max_health=enemy_def.health,
            enemy_def=enemy_def,
            xp_value=enemy_def.xp_value,
        )

    def can_attack(self) -> bool:
        return self.attack_cooldown <= 0 and self.is_alive

    def get_best_attack(self, distance: int) -> Optional[AttackDef]:
        """Get the best attack for given distance."""
        valid = [a for a in self.enemy_def.attacks if a.attack_range >= distance]
        if not valid:
            return None
        # Prefer ranged attacks at distance, melee up close
        for a in valid:
            if distance <= 1 and a.attack_type == AttackType.MELEE:
                return a
        # Otherwise return first valid
        return valid[0]


# ============================================================
# ENEMY DEFINITIONS - All Quake enemies
# ============================================================

ROTTWEILER = EnemyDef(
    name='Rottweiler',
    char='d',
    color='#8B4513',
    health=25,
    speed=1,
    attacks=[
        AttackDef(AttackType.MELEE, 10, 15, 1, description='bite'),
    ],
    xp_value=10,
    min_map_level=1,
    description='A fierce attack dog.',
)

GRUNT = EnemyDef(
    name='Grunt',
    char='g',
    color='#808000',
    health=30,
    speed=1,
    attacks=[
        AttackDef(AttackType.MELEE, 5, 10, 1, description='butt stroke'),
        AttackDef(AttackType.RANGED, 4, 12, 12, cooldown=2,
                  projectile_char='.', description='shotgun blast'),
    ],
    xp_value=15,
    min_map_level=1,
    description='A possessed soldier with a shotgun.',
    ammo_drop='Shells',
)

KNIGHT = EnemyDef(
    name='Knight',
    char='K',
    color='#C0C0C0',
    health=75,
    speed=1,
    attacks=[
        AttackDef(AttackType.MELEE, 10, 20, 1, description='sword slash'),
    ],
    xp_value=25,
    min_map_level=3,
    description='An armored knight wielding a sword.',
)

DEATH_KNIGHT = EnemyDef(
    name='Death Knight',
    char='D',
    color='#FF4500',
    health=250,
    speed=1,
    attacks=[
        AttackDef(AttackType.MELEE, 15, 30, 1, description='sword slash'),
        AttackDef(AttackType.RANGED, 9, 18, 15, cooldown=2,
                  projectile_char='-', description='fire magic'),
    ],
    xp_value=60,
    min_map_level=8,
    description='A hell knight with fire magic and sword.',
    ammo_drop='Shells',
)

ROTFISH = EnemyDef(
    name='Rotfish',
    char='f',
    color='#20B2AA',
    health=25,
    speed=1,
    attacks=[
        AttackDef(AttackType.MELEE, 5, 10, 1, description='bite'),
    ],
    xp_value=5,
    can_swim=True,
    avoids_water=False,
    requires_water=True,
    min_map_level=2,
    description='A mutant fish lurking in water.',
)

ZOMBIE = EnemyDef(
    name='Zombie',
    char='Z',
    color='#556B2F',
    health=60,
    speed=2,  # slower
    attacks=[
        AttackDef(AttackType.RANGED, 10, 15, 8, cooldown=3,
                  projectile_char='*', description='thrown gib'),
    ],
    xp_value=20,
    min_map_level=2,
    description='An undead creature that throws chunks of flesh.',
)

SCRAG = EnemyDef(
    name='Scrag',
    char='W',
    color='#9ACD32',
    health=80,
    speed=1,
    attacks=[
        AttackDef(AttackType.RANGED, 9, 18, 16, cooldown=2,
                  projectile_char='~', description='acid spit'),
    ],
    xp_value=30,
    can_fly=True,
    min_map_level=5,
    description='A flying wizard that spits acid.',
)

OGRE = EnemyDef(
    name='Ogre',
    char='O',
    color='#D2691E',
    health=200,
    speed=2,
    attacks=[
        AttackDef(AttackType.MELEE, 15, 25, 1, description='chainsaw'),
        AttackDef(AttackType.RANGED, 20, 40, 14, cooldown=3,
                  projectile_char='o', description='grenade'),
    ],
    xp_value=50,
    min_map_level=6,
    description='A hulking brute with chainsaw and grenades.',
    ammo_drop='Rockets',
)

FIEND = EnemyDef(
    name='Fiend',
    char='F',
    color='#800000',
    health=300,
    speed=1,
    attacks=[
        AttackDef(AttackType.MELEE, 20, 30, 1, description='claw'),
        AttackDef(AttackType.LEAP, 30, 50, 6, cooldown=3,
                  description='leaping attack'),
    ],
    xp_value=65,
    min_map_level=10,
    description='A demonic fiend that leaps at its prey.',
)

VORE = EnemyDef(
    name='Vore',
    char='V',
    color='#800080',
    health=400,
    speed=2,
    attacks=[
        AttackDef(AttackType.RANGED, 20, 40, 20, cooldown=3,
                  projectile_char='^', description='homing pod'),
    ],
    xp_value=80,
    min_map_level=15,
    description='A spider-like creature that fires homing projectiles.',
)

SHAMBLER = EnemyDef(
    name='Shambler',
    char='S',
    color='#F5F5DC',
    health=600,
    speed=1,
    attacks=[
        AttackDef(AttackType.MELEE, 30, 50, 1, description='claw swipe'),
        AttackDef(AttackType.RANGED, 20, 40, 16, cooldown=2,
                  projectile_char='#', description='lightning'),
    ],
    xp_value=100,
    min_map_level=20,
    description='A massive beast with devastating lightning attacks.',
)

SPAWN_ENEMY = EnemyDef(
    name='Spawn',
    char='s',
    color='#2F4F4F',
    health=80,
    speed=1,
    attacks=[
        AttackDef(AttackType.EXPLODE, 40, 80, 1, description='explosion'),
    ],
    xp_value=35,
    min_map_level=12,
    description='A tarbaby that explodes on contact.',
)

# ============================================================
# ENEMY REGISTRIES
# ============================================================

ALL_ENEMIES = [
    ROTTWEILER, GRUNT, KNIGHT, DEATH_KNIGHT, ROTFISH, ZOMBIE,
    SCRAG, OGRE, FIEND, VORE, SHAMBLER, SPAWN_ENEMY,
]

ENEMY_BY_NAME = {e.name: e for e in ALL_ENEMIES}
