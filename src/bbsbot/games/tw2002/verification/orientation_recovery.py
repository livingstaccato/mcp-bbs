#!/usr/bin/env python3
"""Test orientation recovery from confusing states.

This script:
1. Logs in to the game
2. Deliberately enters confusing states (menus, prompts)
3. Calls orient() to recover
4. Verifies recovery succeeded
"""

import asyncio
from bbsbot.games.tw2002 import TradingBot, OrientationError


async def test_recovery_from_planet_menu():
    """Test recovery when stuck on planet surface."""
    bot = TradingBot(character_name="claude")

    try:
        print("\n" + "=" * 60)
        print("TEST: Recovery from Planet Surface")
        print("=" * 60)

        # Login
        await bot.connect()
        await bot.login_sequence(username="claude")
        bot.init_knowledge()

        # First orient to establish baseline
        print("\n[1] Initial orientation...")
        state1 = await bot.orient()
        print(f"    Baseline: {state1.context} @ sector {state1.sector}")

        # If we have a planet, land on it to get confused
        if state1.has_planet:
            print("\n[2] Landing on planet to get 'confused'...")
            await bot.session.send("L")  # Land
            await asyncio.sleep(1)

            # Read screen to confirm we're on planet
            await bot.session.wait_for_update(timeout_ms=2000)
            screen = bot.session.snapshot().get("screen", "")
            print(f"    Screen shows: ...{screen[-200:]}")

            # Now try to orient - should recover to planet_command
            print("\n[3] Calling orient() to recover...")
            state2 = await bot.orient()
            print(f"    Recovered: {state2.context} @ sector {state2.sector}")

            assert state2.is_safe(), f"Expected safe state, got {state2.context}"
            print("    ✓ Successfully recovered to safe state!")

            # Leave planet to test another recovery
            print("\n[4] Leaving planet (Q)...")
            await bot.session.send("Q")
            await asyncio.sleep(0.5)

        # Enter a port if available
        print("\n[5] Checking for port to enter...")
        state3 = await bot.orient()

        if state3.has_port:
            print(f"    Port found: {state3.port_class}")
            print("    Entering port...")
            await bot.session.send("P")  # Port/dock
            await asyncio.sleep(1)

            # We're now in a port menu - should be "confused"
            await bot.session.wait_for_update(timeout_ms=2000)
            screen = bot.session.snapshot().get("screen", "")
            print(f"    At port: ...{screen[-200:]}")

            # Orient should recover (might exit port or recognize port_menu)
            print("\n[6] Calling orient() to recover from port...")
            state4 = await bot.orient()
            print(f"    Recovered: {state4.context}")

            # Either we're at sector_command (backed out) or port_menu (recognized)
            assert state4.context in ("sector_command", "port_menu"), \
                f"Expected sector_command or port_menu, got {state4.context}"
            print("    ✓ Successfully handled port state!")

        print("\n" + "=" * 60)
        print("✓ ALL RECOVERY TESTS PASSED")
        print("=" * 60)

    except OrientationError as e:
        print(f"\n✗ Orientation failed: {e}")
        print(f"  Screen: {e.screen[:500]}...")
        return False

    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)

    return True


async def test_recovery_from_random_keys():
    """Test recovery after sending random/garbage input."""
    bot = TradingBot(character_name="claude")

    try:
        print("\n" + "=" * 60)
        print("TEST: Recovery from Random Input")
        print("=" * 60)

        await bot.connect()
        await bot.login_sequence(username="claude")
        bot.init_knowledge()

        # Get baseline
        print("\n[1] Initial orientation...")
        state1 = await bot.orient()
        print(f"    Baseline: {state1.context} @ sector {state1.sector}")

        # Send some random keys that might open menus
        print("\n[2] Sending random keys to confuse state...")
        random_keys = ["?", "C", "I", "V", " ", "\r"]
        for key in random_keys:
            print(f"    Sending: {repr(key)}")
            await bot.session.send(key)
            await asyncio.sleep(0.3)

        # Now we might be in some random menu or info screen
        await bot.session.wait_for_update(timeout_ms=1000)
        screen = bot.session.snapshot().get("screen", "")
        print(f"    Current screen: ...{screen[-300:]}")

        # Orient should recover
        print("\n[3] Calling orient() to recover...")
        state2 = await bot.orient()
        print(f"    Recovered: {state2.context} @ sector {state2.sector}")

        assert state2.is_safe(), f"Expected safe state, got {state2.context}"
        assert state2.sector == state1.sector, \
            f"Sector changed unexpectedly: {state1.sector} -> {state2.sector}"

        print("    ✓ Successfully recovered to same sector!")

        print("\n" + "=" * 60)
        print("✓ RANDOM INPUT RECOVERY PASSED")
        print("=" * 60)

    except OrientationError as e:
        print(f"\n✗ Orientation failed: {e}")
        return False

    finally:
        if bot.session_id:
            await bot.session_manager.close_session(bot.session_id)

    return True


async def main():
    """Run all recovery tests."""
    results = []

    results.append(("Planet/Port Recovery", await test_recovery_from_planet_menu()))
    results.append(("Random Input Recovery", await test_recovery_from_random_keys()))

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, passed in results:
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"  {name}: {status}")

    all_passed = all(r[1] for r in results)
    return 0 if all_passed else 1


if __name__ == "__main__":
    import sys
    sys.exit(asyncio.run(main()))
