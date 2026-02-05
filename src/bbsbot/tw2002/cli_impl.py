"""Implementation helpers for the TW2002 CLI."""

from __future__ import annotations

import asyncio
import random

from bbsbot.tw2002.config import BotConfig
from bbsbot.tw2002.strategies.base import TradeAction, TradeResult


async def run_trading_loop(bot, config: BotConfig, char_state) -> None:
    """Run the main trading loop using the configured strategy."""
    strategy = bot.strategy
    if not strategy:
        strategy = bot.init_strategy()

    target_credits = config.session.target_credits
    max_turns = config.session.max_turns_per_session

    turns_used = 0

    print(f"\n[Trading] Starting {strategy.name} strategy...")

    while turns_used < max_turns:
        turns_used += 1

        # Get current state (with scan optimization)
        state = await bot.orient()
        char_state.update_from_game_state(state)

        credits = state.credits or 0
        print(f"\n[Turn {turns_used}] Sector {state.sector}, Credits: {credits:,}")

        # Check target
        if credits >= target_credits:
            print(f"\nTarget reached: {credits:,} credits!")
            break

        # Check turns
        if state.turns_left is not None and state.turns_left <= 0:
            print("\nOut of turns!")
            break

        # Get next action from strategy
        action, params = strategy.get_next_action(state)

        print(f"  Strategy: {action.name}")

        # Execute action
        if action == TradeAction.TRADE:
            opportunity = params.get("opportunity")
            if opportunity:
                print(f"  Trading {opportunity.commodity} (expected profit: {opportunity.expected_profit})")
                profit = await execute_simple_trade(bot, state)
                if profit > 0:
                    char_state.record_trade(profit)
                    print(f"  Profit: {profit:,}")

        elif action == TradeAction.MOVE:
            target = params.get("target_sector")
            if target:
                print(f"  Moving to sector {target}")
                await warp_to_sector(bot, target)

        elif action == TradeAction.EXPLORE:
            direction = params.get("direction")
            if direction:
                print(f"  Exploring sector {direction}")
                await warp_to_sector(bot, direction)

        elif action == TradeAction.BANK:
            print("  Banking credits...")
            result = await bot.banking.deposit(bot, state)
            if result.success:
                print(f"  Deposited {result.deposited:,}")

        elif action == TradeAction.UPGRADE:
            upgrade_type = params.get("upgrade_type")
            print(f"  Upgrading: {upgrade_type}")

        elif action == TradeAction.RETREAT:
            safe_sector = params.get("safe_sector")
            print(f"  Retreating to sector {safe_sector}")
            await bot.combat.retreat(bot, state)

        elif action == TradeAction.WAIT:
            print("  No action available")
            if state.warps:
                target = random.choice(state.warps)
                await warp_to_sector(bot, target)

        elif action == TradeAction.DONE:
            print("  Strategy complete")
            break

        result = TradeResult(
            success=True,
            action=action,
            new_sector=bot.current_sector,
            turns_used=1,
        )
        strategy.record_result(result)

        await asyncio.sleep(0.2)


async def execute_simple_trade(bot, state) -> int:
    """Execute a simple trade at current port."""
    if not state.has_port:
        return 0

    initial_credits = state.credits or 0

    await bot.session.send("P")
    await asyncio.sleep(1.0)

    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "").lower()

    if "no port" in screen:
        return 0

    await bot.session.send("T")
    await asyncio.sleep(1.5)

    trades = 0
    for _ in range(15):
        result = await bot.session.read(timeout_ms=1500, max_bytes=8192)
        screen = result.get("screen", "")
        screen_lower = screen.lower()

        if "command" in screen_lower and "?" in screen:
            break

        if "how many" in screen_lower:
            await bot.session.send("50\r")
            trades += 1
            await asyncio.sleep(0.5)
            continue

        if "[y/n]" in screen_lower or "(y/n)" in screen_lower:
            await bot.session.send("Y")
            await asyncio.sleep(0.3)
            continue

        if "press" in screen_lower or "pause" in screen_lower:
            await bot.session.send(" ")
            await asyncio.sleep(0.3)
            continue

        if "[q]" in screen_lower:
            await bot.session.send("Q")
            break

        await asyncio.sleep(0.3)

    await bot.session.send("Q\r")
    await asyncio.sleep(0.3)
    await bot.recover()

    new_state = await bot.orient()
    new_credits = new_state.credits or 0

    return new_credits - initial_credits


async def warp_to_sector(bot, target: int) -> bool:
    """Warp to a sector."""
    bot.loop_detection.clear()

    await bot.session.send(f"{target}\r")
    await asyncio.sleep(1.5)

    state = await bot.orient()
    return state.sector == target
