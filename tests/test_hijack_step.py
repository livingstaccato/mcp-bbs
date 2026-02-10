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
