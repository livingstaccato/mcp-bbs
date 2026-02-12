# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for dashboard hijack step mode."""

from __future__ import annotations

import asyncio

import pytest

from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.worker import WorkerBot


@pytest.mark.asyncio
async def test_hijack_step_tokens_allow_two_checkpoints_then_block() -> None:
    bot = WorkerBot(bot_id="bot_test", config=BotConfig(), manager_url="http://localhost:9999")

    # Not hijacked: should never block.
    await asyncio.wait_for(bot.await_if_hijacked(), timeout=0.05)

    # Hijacked with no step tokens: should block.
    await bot.set_hijacked(True)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(bot.await_if_hijacked(), timeout=0.05)

    # One "step" grants 2 checkpoint passes by default.
    await bot.request_step()
    await asyncio.wait_for(bot.await_if_hijacked(), timeout=0.05)
    await asyncio.wait_for(bot.await_if_hijacked(), timeout=0.05)

    # Third checkpoint should block again until un-hijacked.
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(bot.await_if_hijacked(), timeout=0.05)

    await bot.set_hijacked(False)
    await asyncio.wait_for(bot.await_if_hijacked(), timeout=0.05)


def test_reset_runtime_session_metrics_clears_cpt_inputs() -> None:
    bot = WorkerBot(bot_id="bot_metrics", config=BotConfig(), manager_url="http://localhost:9999")
    bot.turns_used = 123
    bot._session_start_credits = 9999
    bot.haggle_accept = 8
    bot.haggle_counter = 7
    bot.haggle_too_high = 6
    bot.haggle_too_low = 5
    bot.trades_executed = 4
    bot._last_trade_turn = 77

    bot.reset_runtime_session_metrics()

    assert bot.turns_used == 0
    assert bot._session_start_credits is None
    assert bot.haggle_accept == 0
    assert bot.haggle_counter == 0
    assert bot.haggle_too_high == 0
    assert bot.haggle_too_low == 0
    assert bot.trades_executed == 0
    assert bot._last_trade_turn == 0
