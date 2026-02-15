# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import pytest

from bbsbot.games.tw2002.orientation.detection import _override_context_from_prompt, where_am_i


class _FakeSession:
    def __init__(self, screen: str, prompt_id: str) -> None:
        self._screen = screen
        self._prompt_id = prompt_id

    def is_connected(self) -> bool:
        return True

    def snapshot(self) -> dict:
        return {
            "screen": self._screen,
            "prompt_detected": {"prompt_id": self._prompt_id},
        }

    async def wait_for_update(self, timeout_ms: int = 50) -> None:
        return None


class _FakeBot:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session
        self.diagnostic_buffer = {
            "recent_screens": [],
            "recent_prompts": [],
            "max_history": 16,
        }


def test_prompt_context_overrides_cover_transition_prompts() -> None:
    assert _override_context_from_prompt("sector_command", "prompt.yes_no") == "confirm"
    assert _override_context_from_prompt("menu", "prompt.navpoint_menu") == "corporate_listings"
    assert _override_context_from_prompt("menu", "prompt.class0_port") == "port_menu"
    assert _override_context_from_prompt("unknown", "prompt.stop_in_sector") == "autopilot"


@pytest.mark.asyncio
async def test_where_am_i_does_not_treat_yes_no_overlay_as_safe_sector_command() -> None:
    session = _FakeSession(
        "Command [TL=00:00:00]:[101] (?=Help)? :",
        "prompt.yes_no",
    )
    bot = _FakeBot(session)

    state = await where_am_i(bot)

    assert state.context == "confirm"
    assert state.is_safe is False


@pytest.mark.asyncio
async def test_where_am_i_maps_navpoint_menu_to_non_menu_reentry_context() -> None:
    session = _FakeSession(
        "Choose NavPoint (?=Help) [Q] :",
        "prompt.navpoint_menu",
    )
    bot = _FakeBot(session)

    state = await where_am_i(bot)

    assert state.context == "corporate_listings"
    assert state.is_safe is False
