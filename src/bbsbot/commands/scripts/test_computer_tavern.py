#!/usr/bin/env python3
"""Test Computer menu and Tavern navigation.

Tests:
1. Login to game
2. Access Computer menu
3. Get port report
4. Plot a course
5. Navigate to StarDock (if nearby)
6. Access Tavern (if at StarDock)
"""

import asyncio

from bbsbot.games.tw2002.bot import TradingBot
from bbsbot.games.tw2002.orientation import INFO_CONTEXTS


async def test_computer_menu(bot: TradingBot) -> bool:
    """Test Computer menu access."""
    print("\n[Test] Computer Menu Access")
    print("-" * 40)

    # Check current state
    state = await bot.where_am_i()
    print(f"  Current state: {state.context} @ sector {state.sector}")

    if state.context != "sector_command":
        print("  ✗ Not at sector command, cannot test")
        return False

    # Try to access computer
    print("  Sending 'C' for Computer...")
    await bot.session.send("C")
    await asyncio.sleep(0.5)

    # Check what we got
    result = await bot.session.read(timeout_ms=1000, max_bytes=8192)
    screen = result.get("screen", "")
    lines = [l.strip() for l in screen.split("\n") if l.strip()]

    print("  Response (last 8 lines):")
    for line in lines[-8:]:
        print(f"    {line[:70]}")

    # Check if we're in computer menu
    state = await bot.where_am_i()
    print(f"  New state: {state.context}")

    if state.context in INFO_CONTEXTS or "computer" in screen.lower():
        print("  ✓ Computer menu accessed!")
        return True
    else:
        print("  ? Unknown state after Computer command")
        return False


async def test_port_report(bot: TradingBot) -> bool:
    """Test port report retrieval."""
    print("\n[Test] Port Report")
    print("-" * 40)

    # Make sure we're in computer menu or get there
    state = await bot.where_am_i()
    print(f"  Current state: {state.context}")
    if state.context == "sector_command":
        print("  Entering computer menu...")
        await bot.session.send("C")
        await asyncio.sleep(0.5)
    elif state.context != "computer_menu":
        print(f"  ✗ Unexpected state: {state.context}")
        return False

    # Request port report
    print("  Sending 'R' for Port Report...")
    await bot.session.send("R")
    await asyncio.sleep(1.0)

    # Read the report
    result = await bot.session.read(timeout_ms=2000, max_bytes=16384)
    screen = result.get("screen", "")
    lines = [l.strip() for l in screen.split("\n") if l.strip()]

    print(f"  Response ({len(lines)} lines):")
    # Show first 10 and last 5 lines
    for line in lines[:10]:
        print(f"    {line[:70]}")
    if len(lines) > 15:
        print("    ...")
        for line in lines[-5:]:
            print(f"    {line[:70]}")

    # Check if it looks like a port report
    has_port_data = any("port" in l.lower() or "sector" in l.lower() for l in lines)
    if has_port_data:
        print("  ✓ Port report retrieved!")
        return True
    else:
        print("  ? No port data found")
        return False


async def test_course_plotter(bot: TradingBot, destination: int = 100) -> bool:
    """Test course plotter."""
    print(f"\n[Test] Course Plotter (to sector {destination})")
    print("-" * 40)

    # Get to computer menu
    state = await bot.where_am_i()
    print(f"  Current state: {state.context}")
    if state.context == "sector_command":
        print("  Entering computer menu...")
        await bot.session.send("C")
        await asyncio.sleep(0.5)
    elif state.context != "computer_menu":
        print(f"  ✗ Unexpected state: {state.context}")
        return False

    # Access course plotter
    print("  Sending 'F' for Course Plotter...")
    await bot.session.send("F")
    await asyncio.sleep(0.5)

    # Read prompt
    result = await bot.session.read(timeout_ms=1000, max_bytes=8192)
    screen = result.get("screen", "")
    lines = [l.strip() for l in screen.split("\n") if l.strip()]
    print(f"  Prompt: {lines[-1] if lines else 'none'}")

    # Enter destination
    print(f"  Entering destination: {destination}")
    await bot.session.send(f"{destination}\r")
    await asyncio.sleep(1.0)

    # Read result
    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "")
    lines = [l.strip() for l in screen.split("\n") if l.strip()]

    print("  Response (last 8 lines):")
    for line in lines[-8:]:
        print(f"    {line[:70]}")

    # Check for path
    screen_lower = screen.lower()
    if "path" in screen_lower or "route" in screen_lower or "warp" in screen_lower:
        print("  ✓ Course plotted!")
        return True
    elif "no path" in screen_lower or "cannot" in screen_lower:
        print("  ✓ Course plotter works (no path found)")
        return True
    else:
        print("  ? Unknown response")
        return False


async def test_stardock_access(bot: TradingBot) -> bool:
    """Test StarDock access (only works if in StarDock sector)."""
    print("\n[Test] StarDock Access")
    print("-" * 40)

    # Return to sector command first
    await bot.recover()

    state = await bot.where_am_i()
    print(f"  Current state: {state.context} @ sector {state.sector}")

    if state.context != "sector_command":
        print("  ✗ Not at sector command")
        return False

    # Check if StarDock is in this sector
    # Send D to get full display of sector contents
    await bot.session.send("D")
    await asyncio.sleep(0.5)
    result = await bot.session.read(timeout_ms=1000, max_bytes=8192)
    screen = result.get("screen", "")

    if "stardock" not in screen.lower():
        print("  ⊘ StarDock not in current sector")
        print("  Note: StarDock location varies by game setup")
        print("  To test: warp to sector with StarDock facility")
        return None  # Return None to indicate SKIP rather than FAIL

    # Try to enter StarDock
    print("  Sending 'S' for StarDock...")
    await bot.session.send("S")
    await asyncio.sleep(0.5)

    # Check result
    result = await bot.session.read(timeout_ms=1000, max_bytes=8192)
    screen = result.get("screen", "")
    lines = [l.strip() for l in screen.split("\n") if l.strip()]

    print("  Response (last 5 lines):")
    for line in lines[-5:]:
        print(f"    {line[:70]}")

    state = await bot.where_am_i()
    if state.context == "stardock" or "stardock" in screen.lower():
        print("  ✓ StarDock entered!")
        return True
    else:
        print(f"  ? State: {state.context}")
        return False


async def test_tavern_access(bot: TradingBot) -> bool:
    """Test Tavern access (only works if at StarDock)."""
    print("\n[Test] Tavern Access")
    print("-" * 40)

    state = await bot.where_am_i()
    print(f"  Current state: {state.context}")

    if state.context != "stardock":
        print("  ✗ Not at StarDock, cannot access Tavern")
        return False

    # Try to enter Tavern
    print("  Sending 'T' for Tavern...")
    await bot.session.send("T")
    await asyncio.sleep(0.5)

    # Check result
    result = await bot.session.read(timeout_ms=1000, max_bytes=8192)
    screen = result.get("screen", "")
    lines = [l.strip() for l in screen.split("\n") if l.strip()]

    print("  Response (last 8 lines):")
    for line in lines[-8:]:
        print(f"    {line[:70]}")

    state = await bot.where_am_i()
    if state.context == "tavern" or "tavern" in screen.lower():
        print("  ✓ Tavern entered!")
        return True
    else:
        print(f"  ? State: {state.context}")
        return False


async def main():
    print("=" * 60)
    print("COMPUTER & TAVERN NAVIGATION TEST")
    print("=" * 60)

    bot = TradingBot(character_name="testbot")
    results = {}

    try:
        # Connect
        print("\n[Setup] Connecting...")
        await bot.connect(host="localhost", port=2002)
        print("  ✓ Connected")

        # Login
        print("\n[Setup] Logging in...")
        await bot.login_sequence(
            game_password="game",
            character_password="test",
            username="testbot",
        )
        print("  ✓ Logged in")

        # Orient
        print("\n[Setup] Orienting...")
        game_state = await bot.orient()
        print(f"  Sector: {game_state.sector}")
        print(f"  Warps: {game_state.warps}")

        # Run tests
        results["computer_menu"] = await test_computer_menu(bot)

        # Return to safe state
        await bot.recover()

        results["port_report"] = await test_port_report(bot)

        # Return to safe state
        await bot.recover()

        results["course_plotter"] = await test_course_plotter(bot)

        # Return to safe state
        await bot.recover()

        results["stardock"] = await test_stardock_access(bot)

        if results["stardock"]:
            results["tavern"] = await test_tavern_access(bot)
        else:
            results["tavern"] = None
            print("\n[Test] Tavern Access")
            print("-" * 40)
            print("  ⊘ Skipped (StarDock not accessible)")

        # Return to safe state
        await bot.recover()

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback

        traceback.print_exc()

    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)
            print("\n[Cleanup] Session closed")

    # Summary
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    for test_name, result in results.items():
        if result is True:
            status = "✓ PASS"
        elif result is False:
            status = "✗ FAIL"
        else:
            status = "⊘ SKIP"
        print(f"  {test_name}: {status}")

    passed = sum(1 for r in results.values() if r is True)
    total = sum(1 for r in results.values() if r is not None)
    print(f"\n  Total: {passed}/{total} passed")


if __name__ == "__main__":
    asyncio.run(main())
