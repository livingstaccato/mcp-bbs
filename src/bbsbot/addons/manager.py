"""Addon manager for coordinating game-specific addons."""

from __future__ import annotations

from bbsbot.addons.base import Addon, AddonEvent


class AddonManager:
    def __init__(self, addons: list[Addon] | None = None) -> None:
        self.addons: list[Addon] = addons or []

    def process(self, snapshot: dict[str, object]) -> list[AddonEvent]:
        events: list[AddonEvent] = []
        for addon in self.addons:
            events.extend(addon.process(snapshot))
        return events
