"""Message log system for Quakelike."""

from __future__ import annotations
from dataclasses import dataclass, field

from quakelike.constants import MAX_VISIBLE_MESSAGES


@dataclass
class MessageLog:
    """Stores and manages game messages."""
    messages: list[str] = field(default_factory=list)

    def add(self, text: str) -> None:
        """Add a message to the log."""
        self.messages.append(text)

    def get_recent(self, count: int = MAX_VISIBLE_MESSAGES) -> list[str]:
        """Get the most recent messages."""
        return self.messages[-count:]

    def get_all(self) -> list[str]:
        """Get all messages."""
        return list(self.messages)

    def clear(self) -> None:
        """Clear all messages."""
        self.messages.clear()

    def to_dict(self) -> list[str]:
        """Serialize for save/load."""
        return list(self.messages)
