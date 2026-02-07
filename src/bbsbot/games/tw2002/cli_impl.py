"""Implementation helpers for the TW2002 CLI."""

from __future__ import annotations

import asyncio
import logging
import random
import re

from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.strategies.base import TradeAction, TradeResult

logger = logging.getLogger(__name__)

# Commodity name patterns for matching in "How many holds of X" prompts
_COMMODITY_PATTERNS = {
    "fuel_ore": re.compile(r"fuel\s*ore", re.IGNORECASE),
    "organics": re.compile(r"organics", re.IGNORECASE),
    "equipment": re.compile(r"equipment", re.IGNORECASE),
}


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

        # Get next action from strategy (handle async strategies)
        if hasattr(strategy, '_get_next_action_async'):
            # AIStrategy has async implementation
            action, params = await strategy._get_next_action_async(state)
        else:
            # Synchronous strategy
            action, params = strategy.get_next_action(state)

        print(f"  Strategy: {action.name}")

        profit = 0
        success = True

        # Execute action
        if action == TradeAction.TRADE:
            opportunity = params.get("opportunity")
            trade_action = params.get("action")  # "buy" or "sell" for pair trading
            commodity = opportunity.commodity if opportunity else None

            if opportunity:
                print(f"  Trading {commodity} at sector {state.sector} (action={trade_action})")
                profit = await execute_port_trade(bot, commodity=commodity)
                if profit != 0:
                    char_state.record_trade(profit)
                    print(f"  Result: {profit:+,} credits")
                else:
                    print(f"  No trade executed")
                    success = False

        elif action == TradeAction.MOVE:
            target = params.get("target_sector")
            path = params.get("path")
            from_sector = state.sector
            if path and len(path) > 1:
                print(f"  Navigating: {' -> '.join(str(s) for s in path)}")
                success = await warp_along_path(bot, path)
            elif target:
                print(f"  Moving to sector {target}")
                success = await warp_to_sector(bot, target)

        elif action == TradeAction.EXPLORE:
            direction = params.get("direction")
            from_sector = state.sector
            if direction:
                print(f"  Exploring sector {direction}")
                success = await warp_to_sector(bot, direction)

        elif action == TradeAction.BANK:
            print("  Banking credits...")
            try:
                result = await bot.banking.deposit(bot, state)
                if result.success:
                    print(f"  Deposited {result.deposited:,}")
            except Exception as e:
                print(f"  Banking failed: {e}")

        elif action == TradeAction.UPGRADE:
            upgrade_type = params.get("upgrade_type")
            print(f"  Upgrading: {upgrade_type} (not yet implemented)")

        elif action == TradeAction.RETREAT:
            safe_sector = params.get("safe_sector")
            if safe_sector:
                print(f"  Retreating to sector {safe_sector}")
                await warp_to_sector(bot, safe_sector)

        elif action == TradeAction.WAIT:
            print("  No action available, exploring randomly")
            if state.warps:
                target = random.choice(state.warps)
                await warp_to_sector(bot, target)

        elif action == TradeAction.DONE:
            print("  Strategy complete")
            break

        result = TradeResult(
            success=success,
            action=action,
            profit=profit,
            new_sector=bot.current_sector,
            turns_used=1,
        )

        # Add from/to sector for failed warp tracking
        if action in (TradeAction.EXPLORE, TradeAction.MOVE):
            result.from_sector = from_sector
            if action == TradeAction.EXPLORE:
                result.to_sector = params.get("direction")
            elif action == TradeAction.MOVE:
                result.to_sector = params.get("target_sector")

        strategy.record_result(result)

        await asyncio.sleep(0.2)


async def execute_port_trade(
    bot,
    commodity: str | None = None,
    max_quantity: int = 0,
) -> int:
    """Execute a trade at the current port.

    Docks at the port and trades commodities. If a specific commodity is given,
    only that commodity is traded (others are skipped with 0). If no commodity
    is specified, all available commodities are traded at defaults.

    Uses pending_trade tracking to avoid responding to stale price prompts
    in the screen buffer when a commodity was skipped (entered 0).

    Args:
        bot: TradingBot instance
        commodity: Target commodity ("fuel_ore", "organics", "equipment") or None for all
        max_quantity: Max quantity to trade (0 = accept game default/max)

    Returns:
        Credit change (positive = profit, negative = loss)
    """
    initial_credits = bot.current_credits or 0
    pending_trade = False
    target_re = _COMMODITY_PATTERNS.get(commodity) if commodity else None

    # Dock at port
    await bot.session.send("P")
    await asyncio.sleep(1.0)

    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "").lower()

    if "no port" in screen:
        await bot.recover()
        return 0

    # Start trading (T for transaction)
    await bot.session.send("T")
    await asyncio.sleep(1.5)

    for step in range(30):
        result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
        screen = result.get("screen", "")
        screen_lower = screen.lower()

        # Use last lines to detect current prompt state
        lines = [l.strip() for l in screen.split("\n") if l.strip()]
        last_lines = "\n".join(lines[-6:]).lower() if lines else ""

        # Back at sector command = done trading
        if re.search(r"command.*\[\d+\].*\?", last_lines):
            break

        # Port menu [T] or [Q] = not yet trading or done
        if re.search(r"\[t\]", last_lines) and "transaction" in last_lines:
            # At port menu, need to press T
            await bot.session.send("T")
            await asyncio.sleep(1.0)
            continue

        # Quantity prompt: "How many holds of X do you want to buy/sell?"
        if "how many" in last_lines:
            # Find the "how many" line to identify the commodity
            how_many_lines = [l for l in lines if "how many" in l.lower()]
            prompt_line = how_many_lines[-1].lower() if how_many_lines else last_lines

            if target_re:
                # Targeted trading: only trade the target commodity
                is_target = bool(target_re.search(prompt_line))
                if is_target:
                    if max_quantity > 0:
                        qty_str = str(max_quantity)
                    else:
                        qty_str = ""  # Empty = accept default (max)
                    await bot.session.send(f"{qty_str}\r")
                    pending_trade = True
                    logger.debug("Trading %s (qty=%s)", commodity, qty_str or "max")
                else:
                    await bot.session.send("0\r")
                    pending_trade = False
                    logger.debug("Skipping non-target commodity")
            else:
                # Trade all: accept default for everything
                if max_quantity > 0:
                    await bot.session.send(f"{max_quantity}\r")
                else:
                    await bot.session.send("\r")
                pending_trade = True

            await asyncio.sleep(0.5)
            continue

        # Price/offer negotiation - only respond if we have a pending trade
        if pending_trade and (
            "offer" in last_lines
            or "price" in last_lines
            or "haggl" in last_lines
        ):
            # Accept the default price (press Enter)
            await bot.session.send("\r")
            await asyncio.sleep(0.5)
            continue

        # Y/N acceptability check during trade
        if "(y/n)" in last_lines or "[y/n]" in last_lines:
            if pending_trade:
                await bot.session.send("Y")
                pending_trade = False  # Trade for this commodity is done
            else:
                await bot.session.send("N")
            await asyncio.sleep(0.3)
            continue

        # Pause/press key (transaction complete messages, etc.)
        if "[pause]" in last_lines or "press" in last_lines:
            await bot.session.send(" ")
            await asyncio.sleep(0.3)
            continue

        # Port menu with [Q] = exit option
        if "[q]" in last_lines:
            await bot.session.send("Q")
            await asyncio.sleep(0.3)
            break

        # Nothing recognized, wait a bit
        await asyncio.sleep(0.3)

    # Make sure we're out of the port and at a safe state
    await bot.recover()

    # Get updated state
    new_state = await bot.orient()
    new_credits = new_state.credits or 0

    credit_change = new_credits - initial_credits
    logger.info(
        "Trade complete: %+d credits (was %d, now %d)",
        credit_change,
        initial_credits,
        new_credits,
    )
    return credit_change


async def warp_to_sector(bot, target: int) -> bool:
    """Warp to an adjacent sector.

    Sends the sector number at the command prompt. In TW2002, typing a sector
    number at the command prompt warps to that sector if it's adjacent.

    Args:
        bot: TradingBot instance
        target: Destination sector number

    Returns:
        True if successfully reached target sector
    """
    bot.loop_detection.clear()

    await bot.session.send(f"{target}\r")
    await asyncio.sleep(1.5)

    # Handle intermediate screens (autopilot, pause, etc.)
    for _ in range(5):
        result = await bot.session.read(timeout_ms=1000, max_bytes=8192)
        screen = result.get("screen", "").lower()

        # Already at command prompt with target sector
        if f"[{target}]" in screen and "command" in screen:
            break

        # Autopilot confirmation
        if "(y/n)" in screen and ("autopilot" in screen or "engage" in screen):
            await bot.session.send("Y")
            await asyncio.sleep(1.0)
            continue

        # Pause/press key
        if "[pause]" in screen or "press" in screen:
            await bot.session.send(" ")
            await asyncio.sleep(0.3)
            continue

        await asyncio.sleep(0.3)

    state = await bot.orient()
    if state.sector == target:
        return True

    logger.warning("Warp failed: wanted %d, at %s", target, state.sector)
    return False


async def warp_along_path(bot, path: list[int]) -> bool:
    """Navigate through a multi-hop path.

    Warps through each sector in the path sequentially. The first entry
    in the path is the current sector and is skipped.

    Args:
        bot: TradingBot instance
        path: List of sector IDs [current, hop1, hop2, ..., destination]

    Returns:
        True if successfully reached the final destination
    """
    if len(path) < 2:
        return True  # Already at destination

    for i, sector in enumerate(path[1:], 1):
        print(f"    Hop {i}/{len(path)-1}: -> {sector}")
        success = await warp_to_sector(bot, sector)
        if not success:
            logger.warning("Path navigation failed at hop %d (sector %d)", i, sector)
            return False

    return True
