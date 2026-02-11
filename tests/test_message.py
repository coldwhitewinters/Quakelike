"""Tests for the message log module."""

import pytest
from quakelike.message import MessageLog
from quakelike.constants import MAX_VISIBLE_MESSAGES


class TestMessageLog:
    def test_add_message(self):
        log = MessageLog()
        log.add('Hello world')
        assert len(log.messages) == 1
        assert log.messages[0] == 'Hello world'

    def test_get_recent(self):
        log = MessageLog()
        for i in range(10):
            log.add(f'Message {i}')
        recent = log.get_recent()
        assert len(recent) == MAX_VISIBLE_MESSAGES
        assert recent[-1] == 'Message 9'

    def test_get_recent_fewer_messages(self):
        log = MessageLog()
        log.add('Only one')
        recent = log.get_recent()
        assert len(recent) == 1

    def test_get_all(self):
        log = MessageLog()
        for i in range(5):
            log.add(f'Message {i}')
        all_msgs = log.get_all()
        assert len(all_msgs) == 5

    def test_clear(self):
        log = MessageLog()
        log.add('test')
        log.clear()
        assert len(log.messages) == 0

    def test_to_dict(self):
        log = MessageLog()
        log.add('test1')
        log.add('test2')
        d = log.to_dict()
        assert d == ['test1', 'test2']

    def test_max_visible_is_three(self):
        """Only the last 3 messages should be visible in the UI."""
        assert MAX_VISIBLE_MESSAGES == 3
