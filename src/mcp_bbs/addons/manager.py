"""Addon manager for coordinating game-specific addons."""

from __future__ import annotations

from dataclasses import dataclass, field

from mcp_bbs.addons.base import Addon, AddonEvent


@dataclass
class AddonManager:
    addons: list[Addon] = field(default_factory=list)

    def process(self, snapshot: dict[str, object]) -> list[AddonEvent]:
        events: list[AddonEvent] = []
        for addon in self.addons:
            events.extend(addon.process(snapshot))
        return events
