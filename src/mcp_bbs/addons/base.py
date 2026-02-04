"""Addon interfaces for game-specific logic."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class AddonEvent:
    """Structured addon event."""

    name: str
    data: dict[str, Any] = field(default_factory=dict)


class Addon(Protocol):
    """Addon protocol for game-specific parsing."""

    name: str

    def process(self, snapshot: dict[str, Any]) -> list[AddonEvent]:
        """Process a screen snapshot and emit addon events."""
        raise NotImplementedError

