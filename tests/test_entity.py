"""Tests for the entity module."""

import pytest
from quakelike.entity import Position, Entity


class TestPosition:
    def test_creation(self):
        pos = Position(5, 10)
        assert pos.y == 5
        assert pos.x == 10

    def test_distance_to(self):
        p1 = Position(0, 0)
        p2 = Position(3, 4)
        assert p1.distance_to(p2) == 7  # Manhattan distance

    def test_chebyshev_distance(self):
        p1 = Position(0, 0)
        p2 = Position(3, 4)
        assert p1.chebyshev_distance(p2) == 4

    def test_chebyshev_adjacent(self):
        p1 = Position(5, 5)
        p2 = Position(4, 6)  # Diagonal neighbor
        assert p1.chebyshev_distance(p2) == 1

    def test_equality(self):
        p1 = Position(3, 4)
        p2 = Position(3, 4)
        assert p1 == p2

    def test_inequality(self):
        p1 = Position(3, 4)
        p2 = Position(4, 3)
        assert p1 != p2

    def test_hash(self):
        p1 = Position(3, 4)
        p2 = Position(3, 4)
        assert hash(p1) == hash(p2)
        s = {p1}
        assert p2 in s

    def test_copy(self):
        p = Position(5, 10)
        p2 = p.copy()
        assert p == p2
        assert p is not p2
        p2.y = 99
        assert p.y == 5


class TestEntity:
    def test_creation(self):
        e = Entity(name='test', char='T', color='#FFF',
                   pos=Position(0, 0), health=100, max_health=100)
        assert e.name == 'test'
        assert e.health == 100
        assert e.is_alive

    def test_take_damage(self):
        e = Entity(name='test', char='T', color='#FFF',
                   pos=Position(0, 0), health=100, max_health=100)
        actual = e.take_damage(30)
        assert actual == 30
        assert e.health == 70
        assert e.is_alive

    def test_take_lethal_damage(self):
        e = Entity(name='test', char='T', color='#FFF',
                   pos=Position(0, 0), health=50, max_health=100)
        actual = e.take_damage(50)
        assert actual == 50
        assert e.health == 0
        assert not e.is_alive

    def test_take_overkill_damage(self):
        e = Entity(name='test', char='T', color='#FFF',
                   pos=Position(0, 0), health=30, max_health=100)
        actual = e.take_damage(100)
        assert actual == 30  # Can't deal more than remaining HP
        assert e.health == 0
        assert not e.is_alive

    def test_heal(self):
        e = Entity(name='test', char='T', color='#FFF',
                   pos=Position(0, 0), health=50, max_health=100)
        actual = e.heal(30)
        assert actual == 30
        assert e.health == 80

    def test_heal_cap(self):
        e = Entity(name='test', char='T', color='#FFF',
                   pos=Position(0, 0), health=90, max_health=100)
        actual = e.heal(30)
        assert actual == 10  # Capped at max
        assert e.health == 100

    def test_heal_full_health(self):
        e = Entity(name='test', char='T', color='#FFF',
                   pos=Position(0, 0), health=100, max_health=100)
        actual = e.heal(30)
        assert actual == 0
        assert e.health == 100
