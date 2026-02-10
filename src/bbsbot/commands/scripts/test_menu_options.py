#!/usr/bin/env python3
"""Test different keys at the TWGS game selection menu."""

import asyncio

from bbsbot.core.session_manager import SessionManager
from bbsbot.paths import default_knowledge_root


async def test_menu_key(key_desc: str, key_sequence: str):
    """Test a specific key sequence at the TWGS menu."""
    manager = SessionManager()
    knowledge_root = default_knowledge_root()

    try:
        session_id = await manager.create_session(
            host="localhost", port=2002, cols=80, rows=25, term="ANSI", timeout=10.0
        )
        session = await manager.get_session(session_id)
        await manager.enable_learning(session_id, knowledge_root, namespace="tw2002")

        # Login
        await asyncio.sleep(2.0)
        await session.read(timeout_ms=1000, max_bytes=8192)

        await session.send(f"Test{key_desc}\r")
        await asyncio.sleep(2.0)
        snapshot = await session.read(timeout_ms=2000, max_bytes=8192)

        # We should be at TWGS menu
        if "Select game" not in snapshot.get("screen", ""):
            return {"key": key_desc, "error": "Not at game selection menu"}

        # Send the test key sequence
        await session.send(key_sequence)
        await asyncio.sleep(4.0)
        snapshot = await session.read(timeout_ms=2000, max_bytes=8192)

        screen = snapshot.get("screen", "")
        screen_hash = snapshot.get("screen_hash", "")[:16]
        prompt = snapshot.get("prompt_detected", {})

        # Analyze what we got
        is_menu = "Select game" in screen
        is_description = "[ANY KEY]" in screen and "No description" in screen
        has_planet = "planet" in screen.lower()
        is_game_screen = not is_menu and not is_description and len(screen.strip()) > 50

        await manager.close_all_sessions()

        return {
            "key": key_desc,
            "sequence": repr(key_sequence),
            "at_menu": is_menu,
            "at_description": is_description,
            "in_game": is_game_screen,
            "has_planet": has_planet,
            "screen_hash": screen_hash,
            "prompt": prompt.get("prompt_id", "None"),
            "screen_preview": screen[:120].replace("\n", " ").strip(),
        }
    except Exception as e:
        return {"key": key_desc, "error": str(e)}


async def main():
    print("=" * 80)
    print("TESTING DIFFERENT KEYS AT TWGS GAME SELECTION MENU")
    print("=" * 80)

    test_cases = [
        # Try entering twice
        ("AA", "AA"),
        ("A-Enter", "A\r"),
        ("A-A-Enter", "AA\r"),
        # Try other letters
        ("1", "1"),
        ("E", "E"),
        ("Enter", "\r"),
        # Try just waiting
        ("A-Wait", "A"),  # Send A, then wait 4s
    ]

    results = []
    for key_desc, key_sequence in test_cases:
        print(f"\nTesting: {key_desc} ({repr(key_sequence)})")
        result = await test_menu_key(key_desc, key_sequence)
        results.append(result)

        if "error" in result:
            print(f"  ❌ Error: {result['error']}")
        elif result.get("in_game"):
            print("  ✅ IN GAME! Different screen!")
            print(f"     Prompt: {result['prompt']}")
            print(f"     Screen: {result['screen_preview']}")
        elif result.get("at_description"):
            print("  ⚠️  At description screen")
        elif result.get("at_menu"):
            print("  ❌ Still at menu")
        else:
            print("  ❓ Unknown state")
            print(f"     Prompt: {result['prompt']}")
            print(f"     Screen: {result['screen_preview']}")

        await asyncio.sleep(1.0)

    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)

    successful = [r for r in results if r.get("in_game")]
    if successful:
        print(f"\n✅ Found {len(successful)} working sequence(s):")
        for r in successful:
            print(f"   - {r['key']}: {r['sequence']}")
            print(f"     → Screen: {r['screen_preview']}")
    else:
        print("\n❌ No sequences successfully entered the game!")

    print("\nAll results:")
    for r in results:
        if "error" not in r:
            status = "✅ GAME" if r.get("in_game") else "⚠️  DESC" if r.get("at_description") else "❌ MENU"
            print(f"  {status} {r['key']:15s} → {r['screen_hash']} ({r['prompt']})")


if __name__ == "__main__":
    asyncio.run(main())
