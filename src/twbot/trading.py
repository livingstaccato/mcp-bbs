"""Trading operations for TW2002."""

import asyncio

from .io import wait_and_respond, send_input
from .parsing import _parse_credits_from_screen, _parse_sector_from_screen
from .logging_utils import logger


async def _dock_and_buy(bot, sector: int, quantity: int = 500):
    """Dock at sector and buy commodities.

    Args:
        bot: TradingBot instance
        sector: Current sector
        quantity: Number of units to buy
    """
    # Get to port menu
    input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
    print(f"  Got prompt: {prompt_id}")

    # Send "P" for Port/Dock
    print("  Docking at port...")
    await bot.session.send("P")  # Single key
    await asyncio.sleep(0.3)

    # Wait for port menu
    input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
    print(f"  At port: {prompt_id}")

    # Send "B" for Buy
    print("  Selecting BUY...")
    await bot.session.send("B")  # Single key
    await asyncio.sleep(0.3)

    # Handle commodity/quantity prompts
    for attempt in range(10):
        try:
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot, timeout_ms=3000
            )
            print(f"    → {prompt_id} ({input_type})")

            if "port_quantity" in prompt_id:
                # How many units?
                print(f"    Buying {quantity} units...")
                await send_input(bot, str(quantity), input_type)
            elif "port_price" in prompt_id:
                # Price confirmation - accept market price (1)
                print("    Accepting offer...")
                await send_input(bot, "1", input_type)
            elif input_type == "any_key":
                # Confirmation/done - continue
                await send_input(bot, "", input_type)
            else:
                # Unknown - try space
                await bot.session.send(" ")
                await asyncio.sleep(0.2)

        except TimeoutError:
            print("    ✓ Buy complete")
            break


async def _dock_and_sell(bot, sector: int):
    """Dock at sector and sell commodities.

    Args:
        bot: TradingBot instance
        sector: Current sector
    """
    # Get to port menu
    input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
    print(f"  Got prompt: {prompt_id}")

    # Send "P" for Port/Dock
    print("  Docking at port...")
    await bot.session.send("P")  # Single key
    await asyncio.sleep(0.3)

    # Wait for port menu
    input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
    print(f"  At port: {prompt_id}")

    # Send "S" for Sell
    print("  Selecting SELL...")
    await bot.session.send("S")  # Single key
    await asyncio.sleep(0.3)

    # Handle commodity/quantity prompts
    for attempt in range(10):
        try:
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot, timeout_ms=3000
            )
            print(f"    → {prompt_id} ({input_type})")

            if "port_quantity" in prompt_id:
                # How many units? Sell all - use high number
                print("    Selling max units...")
                await send_input(bot, "99999", input_type)
            elif "port_price" in prompt_id:
                # Price confirmation - accept market price (1)
                print("    Accepting offer...")
                await send_input(bot, "1", input_type)
            elif input_type == "any_key":
                # Confirmation/done - continue
                await send_input(bot, "", input_type)
            else:
                # Unknown - try space
                await bot.session.send(" ")
                await asyncio.sleep(0.2)

        except TimeoutError:
            print("    ✓ Sell complete")
            break


async def _warp_to_sector(bot, target_sector: int):
    """Warp to target sector.

    Args:
        bot: TradingBot instance
        target_sector: Destination sector number
    """
    # Get to command menu
    input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
    print(f"  Got prompt: {prompt_id}")

    # Send "M" for Move/Warp
    print(f"  Initiating warp to sector {target_sector}...")
    await bot.session.send("M")  # Single key
    await asyncio.sleep(0.3)

    # Wait for sector input prompt
    input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
    print(f"  Warp prompt: {prompt_id}")

    # Send destination sector (multi_key)
    await send_input(bot, str(target_sector), input_type)

    # Wait for arrival confirmation
    try:
        input_type, prompt_id, screen, kv_data = await wait_and_respond(
            bot, timeout_ms=5000
        )
        print(f"  Warp status: {prompt_id}")
        if input_type == "any_key":
            await send_input(bot, "", input_type)
    except TimeoutError:
        pass

    print(f"  ✓ Warped to sector {target_sector}")
    await asyncio.sleep(0.5)


async def single_trading_cycle(
    bot, start_sector: int = 499, max_retries: int = 2
):
    """Execute one complete trading cycle (buy→sell) with error recovery.

    Args:
        bot: TradingBot instance
        start_sector: Starting sector (typically 499 or 607)
        max_retries: Maximum retry attempts for recoverable errors
    """
    print("\n" + "=" * 80)
    print(f"TRADING CYCLE: {start_sector} → {607 if start_sector == 499 else 499}")
    print("=" * 80)

    # Determine buying and selling sectors
    buy_sector = start_sector
    sell_sector = 607 if start_sector == 499 else 499

    for attempt in range(max_retries + 1):
        try:
            # BUY PHASE
            print(f"\n📍 BUY PHASE (Sector {buy_sector})")
            try:
                await _dock_and_buy(bot, buy_sector)
            except RuntimeError as e:
                if "insufficient_credits" in str(e):
                    print("  ⚠️  Not enough credits, reducing buy amount")
                    await _dock_and_buy(bot, buy_sector, quantity=100)
                elif "hold_full" in str(e):
                    print("  ⚠️  Hold full, skipping buy phase")
                else:
                    raise

            # WARP PHASE
            print(f"\n🚀 WARPING to {sell_sector}")
            await _warp_to_sector(bot, sell_sector)

            # SELL PHASE
            print(f"\n📍 SELL PHASE (Sector {sell_sector})")
            await _dock_and_sell(bot, sell_sector)

            # RETURN WARP
            print(f"\n🚀 WARPING back to {buy_sector}")
            await _warp_to_sector(bot, buy_sector)

            bot.cycle_count += 1
            print(f"\n✓ Cycle {bot.cycle_count} complete")
            return  # Success

        except RuntimeError as e:
            error_msg = str(e)
            print(f"\n⚠️  Cycle error (attempt {attempt + 1}/{max_retries + 1}): {e}")

            if "Stuck in loop" in error_msg:
                # Try to escape loop by sending Q or ESC
                print("  → Attempting to escape loop...")
                await bot.session.send("Q")
                await asyncio.sleep(0.5)
                if attempt < max_retries:
                    continue

            elif "out_of_turns" in error_msg:
                print("  ✗ Out of turns - stopping")
                raise

            elif "ship_destroyed" in error_msg:
                print("  ✗ Ship destroyed - stopping")
                raise

            # Other errors - retry if we have attempts left
            if attempt < max_retries:
                wait_time = 2 ** attempt  # Exponential backoff
                print(f"  → Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                print(f"  ✗ Max retries reached")
                raise

        except TimeoutError as e:
            print(f"\n⚠️  Timeout (attempt {attempt + 1}/{max_retries + 1}): {e}")
            if attempt < max_retries:
                print("  → Retrying...")
                await asyncio.sleep(1.0)
            else:
                raise

        except Exception as e:
            print(f"\n✗ Unexpected error: {e}")
            raise


async def run_trading_loop(
    bot, target_credits: int = 5_000_000, max_cycles: int = 20
):
    """Run trading loop until target credits or max cycles.

    Args:
        bot: TradingBot instance
        target_credits: Target credit amount
        max_cycles: Maximum cycles to run
    """
    from .connection import connect
    from .login import login_sequence
    from .logging_utils import _print_session_summary, _save_trade_history

    print("\n" + "=" * 80)
    print(f"TRADING LOOP: Target {target_credits:,} credits")
    print("=" * 80)

    try:
        await connect(bot)
        await login_sequence(bot)

        # Save initial credits
        bot.initial_credits = bot.current_credits
        logger.info(
            "trading_loop_start",
            target_credits=target_credits,
            initial_credits=bot.initial_credits,
            max_cycles=max_cycles,
        )

        for cycle in range(max_cycles):
            if bot.current_credits >= target_credits:
                print(
                    f"\n✓ Target reached: {bot.current_credits:,} / "
                    f"{target_credits:,}"
                )
                logger.info("target_reached", credits=bot.current_credits)
                break

            print(
                f"\nCycle {cycle + 1}/{max_cycles} - "
                f"Credits: {bot.current_credits:,}"
            )
            logger.info(
                "cycle_start",
                cycle=cycle + 1,
                credits=bot.current_credits,
                sector=bot.current_sector,
            )

            await single_trading_cycle(bot, start_sector=499)

            # Update credits from screen
            input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
            bot.current_credits = _parse_credits_from_screen(bot, screen)
            bot.current_sector = _parse_sector_from_screen(bot, screen)

            logger.info(
                "cycle_complete",
                cycle=cycle + 1,
                credits=bot.current_credits,
                profit=bot.current_credits - bot.initial_credits,
            )

    except Exception as e:
        print(f"\n✗ Trading loop failed: {e}")
        logger.error("trading_loop_failed", error=str(e), error_type=type(e).__name__)
        raise
    finally:
        # Print summary and save logs
        _print_session_summary(bot)
        _save_trade_history(bot)

        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)
