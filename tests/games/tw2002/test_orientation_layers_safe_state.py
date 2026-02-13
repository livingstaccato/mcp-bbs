# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest

from bbsbot.games.tw2002.orientation.layers import _reach_safe_state


class _FakeSession:
    def __init__(self, initial_screen: str) -> None:
        self._screen = initial_screen
        self.sent: list[str] = []

    def is_connected(self) -> bool:
        return True

    def is_idle(self, threshold_s: float = 0.1) -> bool:
        return True

    def snapshot(self) -> dict:
        return {"screen": self._screen}

    async def wait_for_update(self, timeout_ms: int = 100) -> None:
        return None

    async def send(self, keys: str) -> None:
        self.sent.append(keys)
        if keys.strip().upper() == "Q":
            self._screen = "Command [TL=00:00:00]:[30] (?=Help)? :"


class _FakeBot:
    def __init__(self, session: _FakeSession) -> None:
        self.session = session
        self.last_game_letter = "B"
        self.menu_reentry_count = 0
        self.last_menu_reentry_time = 0.0
        self.max_menu_reentries = 10


@pytest.mark.asyncio
async def test_reach_safe_state_exits_port_menu_with_q_not_game_reentry() -> None:
    session = _FakeSession("Enter your choice [T] ?")
    bot = _FakeBot(session)

    context, _, _ = await _reach_safe_state(bot, max_attempts=4)

    assert context == "sector_command"
    assert "Q" in session.sent
    assert all(not key.upper().startswith("B") for key in session.sent)
