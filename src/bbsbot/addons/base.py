"""Addon interfaces for game-specific logic."""

from __future__ import annotations

from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict, Field


class AddonEvent(BaseModel):
    """Structured addon event."""

    name: str
    data: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(extra="ignore")


class Addon(Protocol):
    """Addon protocol for game-specific parsing."""

    name: str

    def process(self, snapshot: dict[str, Any]) -> list[AddonEvent]:
        """Process a screen snapshot and emit addon events."""
        raise NotImplementedError
