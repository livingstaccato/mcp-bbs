# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bbsbot.games.tw2002.cli_impl import warp_to_sector
from bbsbot.games.tw2002.orientation import GameState


@pytest.mark.asyncio
async def test_warp_to_sector_handles_autopilot_prompts() -> None:
    bot = SimpleNamespace()
    bot.loop_detection = SimpleNamespace(reset=lambda: None)

    session = AsyncMock()
    session.send = AsyncMock()
    session.wait_for_update = AsyncMock()

    screens = [
        "Engage the Autopilot? (Y/N/Single step/Express) [Y]",
        "Stop in this sector (Y,N,E,I,R,S,D,P,?) (?=Help) [N] ?",
        "Command [TL=00:00:00]:[200] (?=Help)? :",
    ]
    idx = {"i": 0}

    def _snapshot():
        i = min(idx["i"], len(screens) - 1)
        idx["i"] += 1
        return {"screen": screens[i]}

    session.snapshot = _snapshot
    bot.session = session
    bot.orient = AsyncMock(return_value=GameState(context="sector_command", sector=200))

    ok = await warp_to_sector(bot, 200)
    assert ok is True

    sent = [call.args[0] for call in session.send.await_args_list]
    assert sent[0] == "200\r"
    assert "E" in sent
    assert "N" in sent
