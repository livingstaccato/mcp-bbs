"""Trading operations for TW2002."""

import asyncio
import re
from pathlib import Path

from bbsbot.games.tw2002 import cli_impl
from bbsbot.games.tw2002.io import send_input, wait_and_respond
from bbsbot.games.tw2002.logging_utils import logger
from bbsbot.games.tw2002.parsing import (
    _parse_credits_from_screen,
    _parse_sector_from_screen,
    extract_semantic_kv,
)


def _validate_kv_data(kv_data: dict | None, prompt_id: str) -> tuple[bool, str]:
    """Validate extracted K/V data before using.

    Args:
        kv_data: Extracted K/V data from prompt detection
        prompt_id: The detected prompt ID

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not kv_data:
        return True, ""  # No data to validate

    # Check validation status
    validation = kv_data.get("_validation", {})
    if not validation.get("valid", True):
        errors = validation.get("errors", ["Unknown validation error"])
        return False, f"Validation failed for {prompt_id}: {errors[0]}"

    # Check for sector validity if present
    if "sector" in kv_data:
        sector = kv_data["sector"]
        if not (1 <= sector <= 1000):
            return False, f"Invalid sector {sector} (must be 1-1000)"

    # Check for credits validity if present
    if "credits" in kv_data:
        credits = kv_data["credits"]
        if credits < 0:
            return False, f"Invalid credits {credits} (must be >= 0)"

    return True, ""


_SECTOR_BRACKET_RE = re.compile(r"\[(\d+)\]\s*\(\?")
_SECTOR_WORD_RE = re.compile(r"\bsector\s+(\d+)\b", re.IGNORECASE)
_PORT_CLASS_INLINE_RE = re.compile(r"Class\s*\d+\s*\(([^)]+)\)", re.IGNORECASE)
_PORT_CLASS_NAME_RE = re.compile(r"Class\s*([BS]{3})", re.IGNORECASE)


def _extract_sector_from_screen(screen: str) -> int | None:
    matches = _SECTOR_BRACKET_RE.findall(screen)
    if matches:
        return int(matches[-1])
    matches = _SECTOR_WORD_RE.findall(screen)
    if matches:
        return int(matches[-1])
    return None


def _is_trade_port_class(port_class: str | None) -> bool:
    if not port_class:
        return False
    return bool(re.fullmatch(r"[BS]{3}", port_class.strip().upper()))


def _extract_port_info(bot, screen: str) -> tuple[bool, str | None, str | None]:
    semantic = extract_semantic_kv(screen)
    has_port = semantic.get("has_port")
    port_class = semantic.get("port_class")
    port_name = semantic.get("port_name")

    if port_class:
        port_class = port_class.strip().upper()
    if port_name:
        port_name = port_name.strip()

    try:
        from bbsbot.games.tw2002.orientation import _parse_sector_display

        sector_info = _parse_sector_display(screen)
    except Exception:
        sector_info = {}

    if sector_info.get("has_port"):
        has_port = True if has_port is None else has_port
        if not port_class:
            port_class = sector_info.get("port_class")

    port_line = None
    for line in screen.splitlines():
        if re.search(r"Ports?\s*:", line, re.IGNORECASE):
            port_line = line
            break

    if not port_class:
        if class_match := _PORT_CLASS_INLINE_RE.search(screen):
            port_class = class_match.group(1).strip().upper()
        elif class_match := _PORT_CLASS_NAME_RE.search(screen):
            port_class = class_match.group(1).strip().upper()
        elif port_line:
            if class_match := re.search(r"\(([A-Z]{3})\)", port_line):
                port_class = class_match.group(1).strip().upper()

    if port_name is None:
        if name_match := re.search(r"Ports?\s*:\s*([^,\n]+)", screen, re.IGNORECASE):
            port_name = name_match.group(1).strip()

    if has_port is None and port_line:
        has_port = True

    # Fallback to known game state if present
    state = getattr(bot, "game_state", None)
    if state:
        if has_port is None:
            has_port = state.has_port
        if not port_class:
            port_class = state.port_class

    return bool(has_port), port_class, port_name


def _guard_trade_port(bot, screen: str, context: str) -> None:
    has_port, port_class, port_name = _extract_port_info(bot, screen)
    screen_lower = screen.lower()
    if not has_port:
        raise RuntimeError(f"{context}:no_port")

    if _is_trade_port_class(port_class):
        return

    # Special/unknown port - do not trade.
    # Common special ports: Stardock (Fed HQ), Rylos (Corporate HQ),
    # Hardware (ship/equipment vendor), McPlasma's (weapons vendor)
    special_tokens = ("stardock", "rylos", "special port", "hardware", "mcplasma")
    if port_name and any(token in port_name.lower() for token in special_tokens):
        raise RuntimeError(f"{context}:special_port:{port_name}")
    if any(token in screen_lower for token in special_tokens):
        raise RuntimeError(f"{context}:special_port_screen")
    if port_class:
        raise RuntimeError(f"{context}:special_port_class:{port_class}")
    raise RuntimeError(f"{context}:port_class_unknown")


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
        _guard_trade_port(bot, screen, "buy")

    # Send "P" for Port/Dock
    print("  Docking at port...")
    await bot.session.send("P")  # Single key
    await asyncio.sleep(0.3)

    # Wait for port menu
    input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
    print(f"  At port: {prompt_id}")

    # Validate port menu state
    is_valid, error_msg = _validate_kv_data(kv_data, prompt_id)
    if not is_valid:
        print(f"  ⚠️  {error_msg}")

    # Send "B" for Buy
    print("  Selecting BUY...")
    await bot.session.send("B")  # Single key
    await asyncio.sleep(0.3)

    # Handle commodity/quantity prompts
    buy_attempts = 0
    for attempt in range(10):
        try:
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot, timeout_ms=3000
            )
            print(f"    → {prompt_id} ({input_type})")

            # Validate extracted data before using
            is_valid, error_msg = _validate_kv_data(kv_data, prompt_id)
            if not is_valid:
                print(f"    ⚠️  {error_msg}")

            if prompt_id == "prompt.port_menu":
                buy_attempts += 1
                if buy_attempts <= 2:
                    print("    Still at port menu, retrying BUY...")
                    await bot.session.send("B")
                    await asyncio.sleep(0.3)
                    continue
                raise RuntimeError("port_buy_unavailable")
            if "port_quantity" in prompt_id:
                # How many units?
                print(f"    Buying {quantity} units...")
                await send_input(bot, str(quantity), input_type)
            elif "port_price" in prompt_id:
                # Price confirmation - accept market price (1)
                print("    Accepting offer...")
                await send_input(bot, "1", input_type)
            elif prompt_id == "prompt.port_haggle":
                # Haggle - accept default price
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
        _guard_trade_port(bot, screen, "sell")

    # Send "P" for Port/Dock
    print("  Docking at port...")
    await bot.session.send("P")  # Single key
    await asyncio.sleep(0.3)

    # Wait for port menu
    input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
    print(f"  At port: {prompt_id}")

    # Validate port menu state
    is_valid, error_msg = _validate_kv_data(kv_data, prompt_id)
    if not is_valid:
        print(f"  ⚠️  {error_msg}")

    # Send "S" for Sell
    print("  Selecting SELL...")
    await bot.session.send("S")  # Single key
    await asyncio.sleep(0.3)

    # Handle commodity/quantity prompts
    sell_attempts = 0
    for attempt in range(10):
        try:
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot, timeout_ms=3000
            )
            print(f"    → {prompt_id} ({input_type})")

            # Validate extracted data before using
            is_valid, error_msg = _validate_kv_data(kv_data, prompt_id)
            if not is_valid:
                print(f"    ⚠️  {error_msg}")

            if prompt_id == "prompt.port_menu":
                sell_attempts += 1
                if sell_attempts <= 2:
                    print("    Still at port menu, retrying SELL...")
                    await bot.session.send("S")
                    await asyncio.sleep(0.3)
                    continue
                raise RuntimeError("port_sell_unavailable")
            if "port_quantity" in prompt_id:
                # How many units? Sell all - use high number
                print("    Selling max units...")
                await send_input(bot, "99999", input_type)
            elif "port_price" in prompt_id:
                # Price confirmation - accept market price (1)
                print("    Accepting offer...")
                await send_input(bot, "1", input_type)
            elif prompt_id == "prompt.port_haggle":
                # Haggle - accept default price
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
            print("    ✓ Sell complete")
            break


async def _warp_to_sector(bot, target_sector: int):
    """Warp to target sector.

    Args:
        bot: TradingBot instance
        target_sector: Destination sector number
    """
    if bot.current_sector == target_sector:
        print(f"  Already at sector {target_sector}; skipping warp")
        return

    # Get to command menu
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

    # Send "M" for Move/Warp
    print(f"  Initiating warp to sector {target_sector}...")
    await bot.session.send("M")  # Single key
    await asyncio.sleep(0.3)

    # Wait for sector input prompt (validate prompt type)
    pre_warp_sector = bot.current_sector
    warp_prompt_seen = False
    warp_input_type = None
    for _ in range(6):
        input_type, prompt_id, screen, kv_data = await wait_and_respond(
            bot,
            timeout_ms=3000,
            ignore_loop_for={"prompt.pause_simple", "prompt.pause_space_or_enter"},
        )
        print(f"  Warp prompt: {prompt_id}")
        if prompt_id == "prompt.warp_sector":
            is_valid, error_msg = _validate_kv_data(kv_data, prompt_id)
            if not is_valid:
                print(f"  ⚠️  {error_msg}")
            if kv_data and "current_sector" in kv_data:
                pre_warp_sector = kv_data["current_sector"]
            warp_prompt_seen = True
            warp_input_type = input_type  # Save the correct input type
            break
        if prompt_id in ("prompt.pause_simple", "prompt.pause_space_or_enter") or input_type == "any_key":
            await send_input(bot, "", input_type)
            await asyncio.sleep(0.2)
            continue
        if prompt_id == "prompt.yes_no":
            screen_lower = screen.lower()
            if "autopilot" in screen_lower or "engage" in screen_lower:
                await send_input(bot, "Y", input_type)
            else:
                await send_input(bot, "N", input_type)
            await asyncio.sleep(0.2)
            continue
        if prompt_id == "prompt.avoid_sector_add":
            # Don't avoid sectors - we want to explore everywhere
            await send_input(bot, "N", input_type)
            await asyncio.sleep(0.2)
            continue
        if prompt_id in ("prompt.sector_command", "prompt.command_generic"):
            # Retry sending warp command if we missed it
            await bot.session.send("M")
            await asyncio.sleep(0.3)
            continue
        raise RuntimeError(f"unexpected_warp_prompt:{prompt_id}")

    if not warp_prompt_seen:
        raise RuntimeError("warp_prompt_missing")

    # Send destination sector (multi_key) - use saved input type from warp prompt
    await send_input(bot, str(target_sector), warp_input_type)

    # Wait for arrival confirmation and reach a stable prompt
    arrival_screen = ""
    for _ in range(6):
        try:
            input_type, prompt_id, screen, kv_data = await wait_and_respond(
                bot,
                timeout_ms=5000,
                ignore_loop_for={"prompt.pause_simple", "prompt.pause_space_or_enter"},
            )
        except TimeoutError:
            break
        print(f"  Warp status: {prompt_id}")
        arrival_screen = screen
        if prompt_id in ("prompt.pause_simple", "prompt.pause_space_or_enter") or input_type == "any_key":
            await send_input(bot, "", input_type)
            await asyncio.sleep(0.2)
            continue
        if prompt_id == "prompt.yes_no":
            screen_lower = screen.lower()
            if "autopilot" in screen_lower or "engage" in screen_lower:
                await send_input(bot, "Y", input_type)
            else:
                await send_input(bot, "N", input_type)
            await asyncio.sleep(0.2)
            continue
        if prompt_id in ("prompt.sector_command", "prompt.command_generic"):
            break

    # Post-warp anomaly checks
    post_sector = _extract_sector_from_screen(arrival_screen) if arrival_screen else None
    if post_sector is None:
        quick_state = await bot.where_am_i()
        post_sector = quick_state.sector
    if post_sector is None:
        raise RuntimeError("warp_sector_unknown")
    if pre_warp_sector and post_sector == pre_warp_sector:
        raise RuntimeError("warp_no_change")
    if post_sector != target_sector:
        raise RuntimeError(f"warp_failed:{post_sector}")

    bot.current_sector = post_sector

    print(f"  ✓ Warped to sector {target_sector}")
    await asyncio.sleep(0.5)


async def _navigate_path(bot, path: list[int]):
    """Navigate through a series of sectors.

    Args:
        bot: TradingBot instance
        path: List of sector IDs to traverse
    """
    if len(path) < 2:
        return  # Already at destination or no path

    print(f"  Navigating: {' -> '.join(str(s) for s in path)}")

    # Skip first sector (current location)
    for sector in path[1:]:
        await _warp_to_sector(bot, sector)


async def _resolve_paths(
    bot,
    route,
    data_dir: Path | None,
) -> tuple[list[int] | None, list[int] | None]:
    """Resolve navigation paths for current->buy and buy->sell."""
    path_to_buy: list[int] | None = None
    path_buy_to_sell: list[int] | None = None

    # Prefer twerk data if available.
    if data_dir:
        try:
            graph = await bot.get_sector_map(data_dir)
            if bot.current_sector and route.buy_sector:
                path_to_buy = graph.bfs_path(bot.current_sector, route.buy_sector)
            if route.path and len(route.path) > 1:
                path_buy_to_sell = route.path
            else:
                path_buy_to_sell = graph.bfs_path(route.buy_sector, route.sell_sector)
            return path_to_buy, path_buy_to_sell
        except Exception:
            pass

    # Fall back to in-game knowledge if available.
    if bot.sector_knowledge and bot.current_sector:
        try:
            path_to_buy = bot.sector_knowledge.find_path(
                bot.current_sector, route.buy_sector
            )
            path_buy_to_sell = bot.sector_knowledge.find_path(
                route.buy_sector, route.sell_sector
            )
        except Exception:
            pass

    return path_to_buy, path_buy_to_sell


async def execute_route(
    bot,
    route,
    quantity: int | None = None,
    max_retries: int = 2,
    data_dir: Path | None = None,
) -> dict:
    """Execute a twerk-analyzed trade route via terminal.

    This method takes a TradeRoute from twerk analysis and executes it
    through the terminal, navigating to buy sector, buying commodities,
    navigating to sell sector, and selling.

    Args:
        bot: TradingBot instance
        route: TradeRoute object from twerk.analysis containing:
            - buy_sector: Sector ID to buy at
            - sell_sector: Sector ID to sell at
            - commodity: What to trade (fuel_ore, organics, equipment)
            - path: List of sectors from buy to sell
            - max_quantity: Maximum available quantity
        quantity: Units to trade (defaults to route.max_quantity or ship holds)
        max_retries: Maximum retry attempts for recoverable errors
        data_dir: Optional TW2002 data directory for twerk pathing

    Returns:
        Dictionary with trade results:
            - success: bool
            - initial_credits: int
            - final_credits: int
            - profit: int
            - commodity: str
            - quantity_bought: int
            - buy_sector: int
            - sell_sector: int
    """
    print("\n" + "=" * 80)
    print(f"EXECUTING ROUTE: {route.commodity}")
    print(f"  Buy at: {route.buy_sector}")
    print(f"  Sell at: {route.sell_sector}")
    print(f"  Path: {' -> '.join(str(s) for s in route.path)}")
    print("=" * 80)

    # Determine quantity
    trade_quantity = quantity or min(route.max_quantity, 500)  # Default 500 max

    # Track initial state
    initial_credits = bot.current_credits
    result = {
        "success": False,
        "initial_credits": initial_credits,
        "final_credits": initial_credits,
        "profit": 0,
        "commodity": route.commodity,
        "quantity_bought": 0,
        "buy_sector": route.buy_sector,
        "sell_sector": route.sell_sector,
    }

    for attempt in range(max_retries + 1):
        try:
            path_to_buy, path_buy_to_sell = await _resolve_paths(bot, route, data_dir)

            # Navigate to buy sector if not already there
            if bot.current_sector != route.buy_sector:
                print(f"\n🚀 NAVIGATE to buy sector {route.buy_sector}")
                if path_to_buy:
                    print(f"  Using path: {' -> '.join(str(s) for s in path_to_buy)}")
                    success = await cli_impl.warp_along_path(bot, path_to_buy)
                    if not success:
                        raise RuntimeError("path_navigation_failed")
                else:
                    await _warp_to_sector(bot, route.buy_sector)

            # Update state after navigation
            state = await bot.orient()
            bot.current_sector = state.sector
            if state.credits is not None:
                bot.current_credits = state.credits

            # BUY PHASE
            print(f"\n📍 BUY PHASE (Sector {route.buy_sector})")
            await _dock_and_buy(bot, route.buy_sector, quantity=trade_quantity)
            result["quantity_bought"] = trade_quantity

            # NAVIGATE to sell sector
            if path_buy_to_sell and len(path_buy_to_sell) > 1:
                print(f"\n🚀 NAVIGATE via route path")
                success = await cli_impl.warp_along_path(bot, path_buy_to_sell)
                if not success:
                    raise RuntimeError("path_navigation_failed")
            else:
                print(f"\n🚀 WARP to {route.sell_sector}")
                await _warp_to_sector(bot, route.sell_sector)

            # Update state after navigation
            state = await bot.orient()
            bot.current_sector = state.sector
            if state.credits is not None:
                bot.current_credits = state.credits

            # SELL PHASE
            print(f"\n📍 SELL PHASE (Sector {route.sell_sector})")
            await _dock_and_sell(bot, route.sell_sector)

            # Update state
            input_type, prompt_id, screen, kv_data = await wait_and_respond(bot)
            bot.current_credits = _parse_credits_from_screen(bot, screen)
            bot.current_sector = _parse_sector_from_screen(bot, screen)

            # Calculate profit
            result["final_credits"] = bot.current_credits
            result["profit"] = bot.current_credits - initial_credits
            result["success"] = True

            bot.cycle_count += 1
            print(f"\n✓ Route complete - Profit: {result['profit']:,}")

            return result

        except RuntimeError as e:
            error_msg = str(e)
            print(f"\n⚠️  Route error (attempt {attempt + 1}/{max_retries + 1}): {e}")

            if "insufficient_credits" in error_msg:
                # Reduce quantity and retry
                trade_quantity = max(50, trade_quantity // 2)
                print(f"  → Reducing quantity to {trade_quantity}")
                if attempt < max_retries:
                    continue

            elif "hold_full" in error_msg:
                # Skip to sell phase
                print("  → Hold full, attempting to sell")
                try:
                    await _warp_to_sector(bot, route.sell_sector)
                    await _dock_and_sell(bot, route.sell_sector)
                except Exception:
                    pass

            elif "out_of_turns" in error_msg or "ship_destroyed" in error_msg:
                print(f"  ✗ Fatal error - stopping")
                result["error"] = error_msg
                return result

            if attempt < max_retries:
                wait_time = 2 ** attempt
                print(f"  → Retrying in {wait_time}s...")
                await asyncio.sleep(wait_time)
            else:
                result["error"] = error_msg
                return result

        except TimeoutError as e:
            print(f"\n⚠️  Timeout (attempt {attempt + 1}/{max_retries + 1}): {e}")
            if attempt < max_retries:
                await asyncio.sleep(1.0)
            else:
                result["error"] = str(e)
                return result

        except Exception as e:
            print(f"\n✗ Unexpected error: {e}")
            result["error"] = str(e)
            return result

    return result


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
            # Ensure we're at buy sector before trading
            if bot.current_sector is None:
                await bot.orient()
            if bot.current_sector != buy_sector:
                print(
                    f"\n🚀 WARPING to buy sector {buy_sector} "
                    f"(current {bot.current_sector})"
                )
                await _warp_to_sector(bot, buy_sector)
                # Verify we arrived at the correct sector
                if bot.current_sector != buy_sector:
                    raise RuntimeError(
                        f"warp_verification_failed:expected_{buy_sector}_got_{bot.current_sector}"
                    )

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
            # Verify we arrived at the correct sector
            if bot.current_sector != sell_sector:
                raise RuntimeError(
                    f"warp_verification_failed:expected_{sell_sector}_got_{bot.current_sector}"
                )

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
    from bbsbot.games.tw2002.connection import connect
    from bbsbot.games.tw2002.login import login_sequence
    from bbsbot.games.tw2002.logging_utils import _print_session_summary, _save_trade_history

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
