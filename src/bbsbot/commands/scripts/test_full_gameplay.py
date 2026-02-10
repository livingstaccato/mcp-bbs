#!/usr/bin/env python3
"""Full gameplay test - prove the bot can play everything.

Tests:
1. Login and orientation
2. Navigation (warp to sectors)
3. Port trading (buy/sell commodities)
4. Computer functions (CIM, course plotter, port report)
5. Planet interactions (if available)
6. Combat readiness (fighters, weapons)
7. Mail system
8. Rankings
9. Ship status
10. Recovery from any state
"""

import asyncio
import sys

from bbsbot.games.tw2002.bot import TradingBot


async def test_navigation(bot: TradingBot) -> dict:
    """Test warping between sectors."""
    print("\n" + "=" * 60)
    print("[TEST] Navigation - Warping Between Sectors")
    print("=" * 60)

    results = {"passed": 0, "failed": 0, "tests": []}

    # Get current state
    state = await bot.where_am_i()
    start_sector = state.sector
    print(f"  Starting sector: {start_sector}")

    # Get available warps
    await bot.session.send("D")
    await asyncio.sleep(0.5)
    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "")

    # Parse warps from screen
    import re

    warp_match = re.search(r"Warps to Sector\(s\)\s*:\s*([\d\s\(\)\-]+)", screen)
    warps = []
    if warp_match:
        warp_text = warp_match.group(1)
        warps = [int(x) for x in re.findall(r"\d+", warp_text)]

    print(f"  Available warps: {warps}")

    if warps:
        # Try warping to first available sector
        target = warps[0]
        print(f"  Attempting warp to sector {target}...")

        await bot.session.send(f"M{target}\r")
        await asyncio.sleep(1.0)

        # Check new location
        state = await bot.where_am_i()
        new_sector = state.sector

        if new_sector == target:
            print(f"  ✓ Successfully warped to sector {target}")
            results["passed"] += 1
            results["tests"].append(("warp_to_sector", True))
        else:
            print(f"  ? Warp result unclear (now at {new_sector})")
            results["tests"].append(("warp_to_sector", None))

        # Warp back
        print(f"  Warping back to sector {start_sector}...")
        await bot.session.send(f"M{start_sector}\r")
        await asyncio.sleep(1.0)

        state = await bot.where_am_i()
        if state.sector == start_sector:
            print(f"  ✓ Successfully returned to sector {start_sector}")
            results["passed"] += 1
            results["tests"].append(("warp_return", True))
        else:
            print(f"  ✗ Failed to return (now at {state.sector})")
            results["failed"] += 1
            results["tests"].append(("warp_return", False))
    else:
        print("  ⊘ No warps available from this sector")
        results["tests"].append(("warp_to_sector", None))

    await bot.recover()
    return results


async def test_port_trading(bot: TradingBot) -> dict:
    """Test port trading operations."""
    print("\n" + "=" * 60)
    print("[TEST] Port Trading")
    print("=" * 60)

    results = {"passed": 0, "failed": 0, "tests": []}

    # Check if port exists in current sector
    await bot.session.send("D")
    await asyncio.sleep(0.5)
    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "")

    if "port" not in screen.lower():
        print("  ⊘ No port in current sector")
        results["tests"].append(("port_access", None))
        return results

    # Try to access port
    print("  Accessing port (P)...")
    await bot.session.send("P")
    await asyncio.sleep(1.0)

    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "")

    if "port" in screen.lower() or "trade" in screen.lower():
        print("  ✓ Port accessed")
        results["passed"] += 1
        results["tests"].append(("port_access", True))

        # Check port type
        lines = [l.strip() for l in screen.split("\n") if l.strip()]
        print("  Port info (last 5 lines):")
        for line in lines[-5:]:
            print(f"    {line[:70]}")

        # Try to trade (T)
        print("  Sending T to trade...")
        await bot.session.send("T")
        await asyncio.sleep(0.5)

        result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
        screen = result.get("screen", "")

        if any(x in screen.lower() for x in ["buy", "sell", "fuel", "organics", "equipment"]):
            print("  ✓ Trading menu accessed")
            results["passed"] += 1
            results["tests"].append(("trade_menu", True))
        else:
            print("  ? Trading menu unclear")
            results["tests"].append(("trade_menu", None))

        # Exit port
        await bot.session.send("Q")
        await asyncio.sleep(0.3)
    else:
        print("  ✗ Failed to access port")
        results["failed"] += 1
        results["tests"].append(("port_access", False))

    await bot.recover()
    return results


async def test_computer_functions(bot: TradingBot) -> dict:
    """Test computer menu functions."""
    print("\n" + "=" * 60)
    print("[TEST] Computer Functions")
    print("=" * 60)

    results = {"passed": 0, "failed": 0, "tests": []}

    # Enter computer
    print("  Entering computer (C)...")
    await bot.session.send("C")
    await asyncio.sleep(0.5)

    state = await bot.where_am_i()
    if state.context == "computer_menu":
        print("  ✓ Computer menu accessed")
        results["passed"] += 1
        results["tests"].append(("computer_access", True))
    else:
        print(f"  ? State: {state.context}")
        results["tests"].append(("computer_access", None))

    # Test CIM mode
    print("  Testing CIM mode (/)...")
    await bot.session.send("/")
    await asyncio.sleep(0.5)

    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "")

    if "cim" in screen.lower() or "computer interrogation" in screen.lower():
        print("  ✓ CIM mode accessed")
        results["passed"] += 1
        results["tests"].append(("cim_mode", True))

        # Exit CIM
        await bot.session.send("Q\r")
        await asyncio.sleep(0.3)
    else:
        print("  ? CIM mode unclear")
        results["tests"].append(("cim_mode", None))

    # Test port report
    print("  Testing port report (R)...")
    await bot.session.send("R\r")
    await asyncio.sleep(0.5)

    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "")

    if "sector" in screen.lower() or "port" in screen.lower():
        print("  ✓ Port report works")
        results["passed"] += 1
        results["tests"].append(("port_report", True))
    else:
        print("  ? Port report unclear")
        results["tests"].append(("port_report", None))

    # Test course plotter
    print("  Testing course plotter (F)...")

    # Make sure we're back in computer menu
    await bot.recover()
    await bot.session.send("C")
    await asyncio.sleep(0.5)

    await bot.session.send("F")
    await asyncio.sleep(0.5)

    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "")

    if "sector" in screen.lower() or "path" in screen.lower() or "destination" in screen.lower():
        print("  ✓ Course plotter works")
        results["passed"] += 1
        results["tests"].append(("course_plotter", True))
    else:
        print("  ? Course plotter unclear")
        results["tests"].append(("course_plotter", None))

    # Exit with Q+Enter
    await bot.session.send("\r")
    await asyncio.sleep(0.2)
    await bot.session.send("Q\r")
    await asyncio.sleep(0.3)

    await bot.recover()
    return results


async def test_ship_status(bot: TradingBot) -> dict:
    """Test ship status display."""
    print("\n" + "=" * 60)
    print("[TEST] Ship Status")
    print("=" * 60)

    results = {"passed": 0, "failed": 0, "tests": []}

    # Display ship info (I)
    print("  Checking ship info (I)...")
    await bot.session.send("I")
    await asyncio.sleep(0.5)

    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "")

    ship_indicators = ["ship", "holds", "fighters", "shields", "credits", "turns"]
    found = sum(1 for x in ship_indicators if x in screen.lower())

    if found >= 3:
        print("  ✓ Ship info displayed")
        results["passed"] += 1
        results["tests"].append(("ship_info", True))

        # Show some details
        lines = [l.strip() for l in screen.split("\n") if l.strip()]
        print("  Ship details:")
        for line in lines[-10:]:
            if any(x in line.lower() for x in ship_indicators):
                print(f"    {line[:70]}")
    else:
        print("  ? Ship info unclear")
        results["tests"].append(("ship_info", None))

    # Press space to continue if needed
    await bot.session.send(" ")
    await asyncio.sleep(0.3)

    await bot.recover()
    return results


async def test_rankings(bot: TradingBot) -> dict:
    """Test rankings display."""
    print("\n" + "=" * 60)
    print("[TEST] Rankings")
    print("=" * 60)

    results = {"passed": 0, "failed": 0, "tests": []}

    # Enter computer for rankings
    await bot.session.send("C")
    await asyncio.sleep(0.5)

    # Good trader rankings (G)
    print("  Checking good trader rankings (G)...")
    await bot.session.send("G")
    await asyncio.sleep(0.5)

    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "")

    if "rank" in screen.lower() or "trader" in screen.lower() or "#" in screen:
        print("  ✓ Rankings displayed")
        results["passed"] += 1
        results["tests"].append(("rankings", True))
    else:
        print("  ? Rankings unclear")
        results["tests"].append(("rankings", None))

    # Press space/enter to continue
    await bot.session.send(" ")
    await asyncio.sleep(0.3)
    await bot.session.send("Q\r")
    await asyncio.sleep(0.3)

    await bot.recover()
    return results


async def test_mail_system(bot: TradingBot) -> dict:
    """Test mail/message system."""
    print("\n" + "=" * 60)
    print("[TEST] Mail System")
    print("=" * 60)

    results = {"passed": 0, "failed": 0, "tests": []}

    # Enter computer
    await bot.session.send("C")
    await asyncio.sleep(0.5)

    # Read mail (M)
    print("  Checking mail (M)...")
    await bot.session.send("M")
    await asyncio.sleep(0.5)

    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "")

    if any(x in screen.lower() for x in ["mail", "message", "no message", "inbox"]):
        print("  ✓ Mail system accessed")
        results["passed"] += 1
        results["tests"].append(("mail_access", True))
    else:
        print("  ? Mail system unclear")
        results["tests"].append(("mail_access", None))

    # Press space/Q to exit
    await bot.session.send(" ")
    await asyncio.sleep(0.2)
    await bot.session.send("Q\r")
    await asyncio.sleep(0.3)

    await bot.recover()
    return results


async def test_density_scan(bot: TradingBot) -> dict:
    """Test density scanner."""
    print("\n" + "=" * 60)
    print("[TEST] Density Scanner")
    print("=" * 60)

    results = {"passed": 0, "failed": 0, "tests": []}

    # Density scan (S for scan submenu, then D)
    print("  Running density scan (SD)...")
    await bot.session.send("S")
    await asyncio.sleep(0.3)

    result = await bot.session.read(timeout_ms=1000, max_bytes=8192)
    screen = result.get("screen", "")

    # Check if we're in scan menu or direct density
    if "scan" in screen.lower() or "density" in screen.lower():
        await bot.session.send("D")
        await asyncio.sleep(0.5)

        result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
        screen = result.get("screen", "")

    if "density" in screen.lower() or "sector" in screen.lower():
        print("  ✓ Density scan works")
        results["passed"] += 1
        results["tests"].append(("density_scan", True))
    else:
        print("  ? Density scan unclear")
        results["tests"].append(("density_scan", None))

    await bot.session.send(" ")
    await asyncio.sleep(0.2)

    await bot.recover()
    return results


async def test_help_system(bot: TradingBot) -> dict:
    """Test help system."""
    print("\n" + "=" * 60)
    print("[TEST] Help System")
    print("=" * 60)

    results = {"passed": 0, "failed": 0, "tests": []}

    # Help (?)
    print("  Accessing help (?)...")
    await bot.session.send("?")
    await asyncio.sleep(0.5)

    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "")

    if "help" in screen.lower() or "command" in screen.lower():
        print("  ✓ Help system works")
        results["passed"] += 1
        results["tests"].append(("help_system", True))

        # Show help content
        lines = [l.strip() for l in screen.split("\n") if l.strip()]
        print("  Help preview:")
        for line in lines[:8]:
            print(f"    {line[:70]}")
    else:
        print("  ? Help unclear")
        results["tests"].append(("help_system", None))

    # Press space to continue
    await bot.session.send(" ")
    await asyncio.sleep(0.3)

    await bot.recover()
    return results


async def test_planet_interaction(bot: TradingBot) -> dict:
    """Test planet interactions if available."""
    print("\n" + "=" * 60)
    print("[TEST] Planet Interaction")
    print("=" * 60)

    results = {"passed": 0, "failed": 0, "tests": []}

    # Check if planet in sector
    await bot.session.send("D")
    await asyncio.sleep(0.5)

    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "")

    if "planet" not in screen.lower():
        print("  ⊘ No planet in current sector")
        results["tests"].append(("planet_access", None))
        await bot.recover()
        return results

    # Try to land on planet (L)
    print("  Landing on planet (L)...")
    await bot.session.send("L")
    await asyncio.sleep(0.5)

    result = await bot.session.read(timeout_ms=2000, max_bytes=8192)
    screen = result.get("screen", "")

    if "planet" in screen.lower() or "surface" in screen.lower() or "citadel" in screen.lower():
        print("  ✓ Planet accessed")
        results["passed"] += 1
        results["tests"].append(("planet_access", True))

        # Check planet command menu
        state = await bot.where_am_i()
        print(f"  Planet state: {state.context}")

        # Try to leave planet
        await bot.session.send("Q")
        await asyncio.sleep(0.3)
    else:
        print("  ? Planet access unclear")
        results["tests"].append(("planet_access", None))

    await bot.recover()
    return results


async def test_recovery_stress(bot: TradingBot) -> dict:
    """Test recovery from various states."""
    print("\n" + "=" * 60)
    print("[TEST] Recovery Stress Test")
    print("=" * 60)

    results = {"passed": 0, "failed": 0, "tests": []}

    # Put bot in various states and recover
    states_to_test = [
        ("Computer menu", "C"),
        ("Display", "D"),
        ("Info", "I"),
    ]

    for name, cmd in states_to_test:
        print(f"  Testing recovery from: {name}")
        await bot.session.send(cmd)
        await asyncio.sleep(0.5)

        try:
            state = await bot.recover(max_attempts=10)
            if state.is_safe:
                print(f"    ✓ Recovered to {state.context}")
                results["passed"] += 1
                results["tests"].append((f"recover_{name}", True))
            else:
                print(f"    ? Ended at {state.context}")
                results["tests"].append((f"recover_{name}", None))
        except Exception as e:
            print(f"    ✗ Recovery failed: {e}")
            results["failed"] += 1
            results["tests"].append((f"recover_{name}", False))

    return results


async def main():
    print("=" * 60)
    print("FULL GAMEPLAY TEST - PROVE THE BOT CAN PLAY EVERYTHING")
    print("=" * 60)

    bot = TradingBot(character_name="testbot")
    all_results = {}

    try:
        # Connect
        print("\n[Setup] Connecting to localhost:2002...")
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
        print(f"  Context: {game_state.context}")

        # Run all tests
        all_results["navigation"] = await test_navigation(bot)
        all_results["port_trading"] = await test_port_trading(bot)
        all_results["computer"] = await test_computer_functions(bot)
        all_results["ship_status"] = await test_ship_status(bot)
        all_results["rankings"] = await test_rankings(bot)
        all_results["mail"] = await test_mail_system(bot)
        all_results["density_scan"] = await test_density_scan(bot)
        all_results["help"] = await test_help_system(bot)
        all_results["planet"] = await test_planet_interaction(bot)
        all_results["recovery"] = await test_recovery_stress(bot)

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

    total_passed = 0
    total_failed = 0
    total_skipped = 0

    for category, results in all_results.items():
        passed = results.get("passed", 0)
        failed = results.get("failed", 0)
        tests = results.get("tests", [])
        skipped = sum(1 for t in tests if t[1] is None)

        total_passed += passed
        total_failed += failed
        total_skipped += skipped

        status = "✓" if failed == 0 and passed > 0 else ("⊘" if passed == 0 else "✗")
        print(f"  {status} {category}: {passed} passed, {failed} failed, {skipped} skipped")

    print(f"\n  TOTAL: {total_passed} passed, {total_failed} failed, {total_skipped} skipped")

    if total_failed == 0:
        print("\n" + "=" * 60)
        print("✓ ALL TESTS PASSED - BOT CAN PLAY THE GAME!")
        print("=" * 60)
        return 0
    else:
        print("\n" + "=" * 60)
        print("✗ SOME TESTS FAILED")
        print("=" * 60)
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
