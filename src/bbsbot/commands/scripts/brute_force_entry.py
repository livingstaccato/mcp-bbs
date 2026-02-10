#!/usr/bin/env python3
"""Brute force test different ways to enter the game."""

import asyncio

from bbsbot.core.session_manager import SessionManager
from bbsbot.paths import default_knowledge_root


async def test_sequence(name: str, game_select_keys: str, wait_time: float = 3.0):
    """Test a specific sequence."""
    manager = SessionManager()
    knowledge_root = default_knowledge_root()

    try:
        session_id = await manager.create_session(
            host="localhost", port=2002, cols=80, rows=25, term="ANSI", timeout=10.0
        )
        session = await manager.get_session(session_id)
        await manager.enable_learning(session_id, knowledge_root, namespace="tw2002")

        # Wait for login
        await asyncio.sleep(2.0)
        await session.read(timeout_ms=1000, max_bytes=8192)

        # Send player name
        await session.send(f"{name}\r")
        await asyncio.sleep(2.0)
        snapshot = await session.read(timeout_ms=1000, max_bytes=8192)

        # Send game selection keys
        await session.send(game_select_keys)
        await asyncio.sleep(wait_time)
        snapshot = await session.read(timeout_ms=1000, max_bytes=8192)

        screen = snapshot.get("screen", "")
        screen_hash = snapshot.get("screen_hash", "")[:16]

        # Check if we got past the menu
        is_menu = "Select game" in screen or "Show Game Descriptions" in screen

        await manager.close_all_sessions()

        return {
            "keys": repr(game_select_keys),
            "wait": wait_time,
            "success": not is_menu,
            "screen_hash": screen_hash,
            "screen_preview": screen[:100].replace("\n", " "),
        }
    except Exception as e:
        return {"keys": repr(game_select_keys), "wait": wait_time, "success": False, "error": str(e)}


async def main():
    print("=" * 80)
    print("BRUTE FORCE TESTING GAME ENTRY SEQUENCES")
    print("=" * 80)

    test_cases = [
        ("A", 2.0),
        ("A\r", 2.0),
        ("A\n", 2.0),
        ("A\r\n", 2.0),
        ("a", 2.0),
        ("a\r", 2.0),
        ("A", 5.0),
        ("A\r", 5.0),
        ("A ", 2.0),
        (" A", 2.0),
        ("A\r\r", 2.0),
        ("\rA\r", 2.0),
    ]

    results = []
    for i, (keys, wait) in enumerate(test_cases, 1):
        print(f"\n[{i}/{len(test_cases)}] Testing: {repr(keys)} with {wait}s wait...")
        result = await test_sequence(f"TestBot{i}", keys, wait)
        results.append(result)

        if result.get("success"):
            print("  ✅ SUCCESS! Got past menu")
            print(f"     Screen: {result['screen_preview']}")
        else:
            print("  ❌ Still at menu")
            if "error" in result:
                print(f"     Error: {result['error']}")

        await asyncio.sleep(1.0)  # Delay between tests

    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)

    successful = [r for r in results if r.get("success")]
    if successful:
        print(f"\n✅ Found {len(successful)} working sequence(s):")
        for r in successful:
            print(f"   - Keys: {r['keys']} with {r['wait']}s wait")
    else:
        print("\n❌ No sequences worked!")
        print("\nAll attempts resulted in same screen hashes:")
        unique_hashes = set(r.get("screen_hash", "N/A") for r in results)
        for h in unique_hashes:
            count = sum(1 for r in results if r.get("screen_hash") == h)
            print(f"   {h}: {count} occurrences")


if __name__ == "__main__":
    asyncio.run(main())
