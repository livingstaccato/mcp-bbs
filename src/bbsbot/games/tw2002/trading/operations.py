"""Unified trading operations (dock and trade)."""

from __future__ import annotations

import asyncio
import re
from typing import Literal

from bbsbot.games.tw2002.io import send_input, wait_and_respond
from bbsbot.logging import get_logger

from .validation import guard_trade_port, validate_kv_data

logger = get_logger(__name__)


async def dock_and_trade(
    bot,
    action: Literal["buy", "sell"],
    sector: int,
    quantity: int | None = None,
) -> None:
    """Dock at sector and execute buy or sell transaction.

    Unified operation for both buy and sell actions. Handles the complete
    flow from docking at port through completing the trade.

    Args:
        bot: TradingBot instance
        action: "buy" or "sell"
        sector: Current sector
        quantity: Units to buy/sell (buy: default 500, sell: default 99999 for "all")

    Raises:
        RuntimeError: On validation failures or unexpected states
    """
    if action not in ("buy", "sell"):
        raise ValueError(f"Invalid action: {action}, must be 'buy' or 'sell'")

    # Set default quantity based on action
    if quantity is None:
        quantity = 500 if action == "buy" else 99999

    # Key for the action (B for buy, S for sell)
    action_key = "B" if action == "buy" else "S"

    # Get to port menu
    input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
    print(f"  Got prompt: {prompt_id}")
    if prompt_id == "prompt.planet_command":
        print("  On planet surface, exiting to sector command...")
        await bot.session.send("Q")
        await asyncio.sleep(0.5)
        input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
        print(f"  After exit: {prompt_id}")
        if prompt_id == "prompt.planet_command":
            raise RuntimeError("still_on_planet")

    # Guard against special/unknown ports before docking
    if prompt_id in ("prompt.sector_command", "prompt.command_generic", "prompt.port_menu"):
        guard_trade_port(bot, screen, action)

    # Send "P" for Port/Dock
    print("  Docking at port...")
    await bot.session.send("P")  # Single key
    await asyncio.sleep(0.3)

    # Wait for port menu
    input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
    print(f"  At port: {prompt_id}")

    # Validate port menu state
    is_valid, error_msg = validate_kv_data(kv_data, prompt_id)
    if not is_valid:
        print(f"  ⚠️  {error_msg}")

    # Send action key (B for Buy, S for Sell)
    print(f"  Selecting {action.upper()}...")
    await bot.session.send(action_key)  # Single key
    await asyncio.sleep(0.3)

    # Handle commodity/quantity prompts
    action_attempts = 0
    for _attempt in range(10):
        try:
            input_type, prompt_id, screen, kv_data = await wait_and_respond(bot, timeout_ms=3000)
            print(f"    → {prompt_id} ({input_type})")

            # Validate extracted data before using
            is_valid, error_msg = validate_kv_data(kv_data, prompt_id)
            if not is_valid:
                print(f"    ⚠️  {error_msg}")

            if prompt_id == "prompt.port_menu":
                action_attempts += 1
                if action_attempts <= 2:
                    print(f"    Still at port menu, retrying {action.upper()}...")
                    await bot.session.send(action_key)
                    await asyncio.sleep(0.3)
                    continue
                raise RuntimeError(f"port_{action}_unavailable")
            if "port_quantity" in prompt_id:
                # How many units?
                print(f"    {action.capitalize()}ing {quantity} units...")
                await send_input(bot, str(quantity), input_type)
            elif prompt_id == "prompt.hardware_buy":
                # TW2002 port transactions use this prompt for commodity quantity (buy/sell).
                # If credits are tiny, skip rather than selecting a default quantity and ending up
                # in an un-winnable haggle loop.
                low = re.search(r"(?i)you\\s+have\\s+([\\d,]+)\\s+credits", screen or "")
                credits = int(low.group(1).replace(",", "")) if low else None
                if credits is not None and credits < 1000 and action == "buy":
                    print("    Low credits at quantity prompt; skipping (0)...")
                    await send_input(bot, "0", input_type)
                else:
                    print(f"    {action.capitalize()}ing {quantity} units...")
                    await send_input(bot, str(quantity), input_type)
            elif "port_price" in prompt_id:
                # Price confirmation - accept market price (1)
                print("    Accepting offer...")
                await send_input(bot, "1", input_type)
            elif prompt_id == "prompt.port_haggle":
                # Haggle:
                # If the game is telling us we can't afford the transaction, stop trying to haggle.
                # In practice, offering <= credits still loops because you still can't buy the goods.
                if re.search(r"(?i)you\\s+only\\s+have\\s+[\\d,]+\\s+credits", screen or ""):
                    print("    Low credits at haggle; aborting trade (Q)...")
                    await send_input(bot, "Q", input_type)
                    continue
                print("    Accepting haggle price...")
                await send_input(bot, "", input_type)
            elif input_type == "any_key":
                # Confirmation/done - continue
                await send_input(bot, "", input_type)
            else:
                # Unknown - try space
                await bot.session.send(" ")
                await asyncio.sleep(0.2)

        except TimeoutError:
            print(f"    ✓ {action.capitalize()} complete")
            break
