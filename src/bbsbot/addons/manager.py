"""Addon manager for coordinating game-specific addons."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from bbsbot.addons.base import Addon, AddonEvent


class AddonManager(BaseModel):
    addons: list[Addon] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def process(self, snapshot: dict[str, object]) -> list[AddonEvent]:
        events: list[AddonEvent] = []
        for addon in self.addons:
            events.extend(addon.process(snapshot))
        return events
