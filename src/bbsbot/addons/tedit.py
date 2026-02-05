"""TEDIT addon for extracting field key/value data from admin editor screens."""

from __future__ import annotations

import re
from typing import Any

from bbsbot.addons.base import Addon, AddonEvent
from pydantic import BaseModel, ConfigDict


_FIELD_RE = re.compile(
    r"<(?P<key>.?)>\s*(?P<label>[^:]+?)\s*:\s*(?P<value>.+)$"
)
_SIMPLE_KV_RE = re.compile(r"^(?P<label>[A-Za-z0-9 /#'\-\[\]<>]+)\s*:\s*(?P<value>.+)$")
_PROMPT_RE = re.compile(r"^(?P<prompt>.+?\[[^\]]*\]\s*:\s*)$")


class TeditAddon(BaseModel, Addon):
    name: str = "tedit"

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def process(self, snapshot: dict[str, Any]) -> list[AddonEvent]:
        screen = snapshot.get("screen", "")
        events: list[AddonEvent] = []

        if not screen:
            return events

        fields: list[dict[str, str]] = []
        prompts: list[str] = []

        for raw_line in screen.splitlines():
            line = raw_line.rstrip()
            if not line.strip():
                continue

            if match := _FIELD_RE.search(line):
                fields.append(
                    {
                        "key": match["key"].strip(),
                        "label": match["label"].strip(),
                        "value": match["value"].strip(),
                    }
                )
                continue

            if match := _PROMPT_RE.search(line.strip()):
                prompts.append(match["prompt"].strip())
                continue

            if match := _SIMPLE_KV_RE.search(line):
                fields.append(
                    {
                        "key": "",
                        "label": match["label"].strip(),
                        "value": match["value"].strip(),
                    }
                )

        if fields:
            events.append(AddonEvent("tedit.fields", {"fields": fields}))

        if prompts:
            events.append(AddonEvent("tedit.prompts", {"prompts": prompts}))

        return events
