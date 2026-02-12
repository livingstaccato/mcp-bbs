#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Test what different keys do after the 'No description [ANY KEY]' screen."""

import asyncio

from bbsbot.core.session_manager import SessionManager
from bbsbot.paths import default_knowledge_root


async def test_key_after_A(key_desc: str, key_to_send: str):
    """Test a specific key after the 'A' game selection."""
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

        await session.send(f"TestKey{key_desc}\r")
        await asyncio.sleep(2.0)
        await session.read(timeout_ms=1000, max_bytes=8192)

        # Send 'A' for game selection
        await session.send("A")
        await asyncio.sleep(3.0)
        snapshot = await session.read(timeout_ms=2000, max_bytes=8192)

        screen_before = snapshot.get("screen", "")
        if "[ANY KEY]" not in screen_before:
            return {"key": key_desc, "error": "Never reached [ANY KEY] screen"}

        # Send the test key
        await session.send(key_to_send)
        await asyncio.sleep(3.0)
        snapshot = await session.read(timeout_ms=2000, max_bytes=8192)

        screen_after = snapshot.get("screen", "")
        screen_hash = snapshot.get("screen_hash", "")[:16]

        # Check what we got
        is_menu = "Select game" in screen_after or "Show Game Descriptions" in screen_after
        is_planet_prompt = "planet" in screen_after.lower()
        is_any_key = "[ANY KEY]" in screen_after

        await manager.close_all_sessions()

        return {
            "key": key_desc,
            "sent": repr(key_to_send),
            "back_to_menu": is_menu,
            "planet_prompt": is_planet_prompt,
            "still_any_key": is_any_key,
            "screen_hash": screen_hash,
            "screen_preview": screen_after[:150].replace("\n", " "),
        }
    except Exception as e:
        return {"key": key_desc, "error": str(e)}


async def main():
    print("=" * 80)
    print("TESTING KEYS AFTER 'No description [ANY KEY]' SCREEN")
    print("=" * 80)

    test_cases = [
        ("Space", " "),
        ("Enter", "\r"),
        ("Newline", "\n"),
        ("A", "A"),
        ("Y", "Y"),
        ("EnterEnter", "\r\r"),
        ("SpaceEnter", " \r"),
        ("EnterSpace", "\r "),
        ("Nothing", ""),  # Just wait
    ]

    results = []
    for key_desc, key_to_send in test_cases:
        print(f"\nTesting: {key_desc} ({repr(key_to_send)})")
        result = await test_key_after_A(key_desc, key_to_send)
        results.append(result)

        if "error" in result:
            print(f"  ❌ Error: {result['error']}")
        elif result.get("planet_prompt"):
            print("  ✅ PLANET PROMPT! Got into game!")
            print(f"     Screen: {result['screen_preview']}")
        elif result.get("back_to_menu"):
            print("  ❌ Back to menu")
        elif result.get("still_any_key"):
            print("  ⚠️  Still at [ANY KEY] screen")
        else:
            print("  ❓ Unknown state")
            print(f"     Screen: {result['screen_preview']}")

        await asyncio.sleep(1.0)

    print("\n" + "=" * 80)
    print("RESULTS SUMMARY")
    print("=" * 80)

    successful = [r for r in results if r.get("planet_prompt")]
    if successful:
        print(f"\n✅ Found {len(successful)} working key(s):")
        for r in successful:
            print(f"   - {r['key']}: {r['sent']}")
    else:
        print("\n❌ No keys successfully entered the game!")

    print("\nAll results:")
    for r in results:
        if "error" not in r:
            status = (
                "✅ GAME"
                if r.get("planet_prompt")
                else "❌ MENU"
                if r.get("back_to_menu")
                else "⚠️  STUCK"
                if r.get("still_any_key")
                else "❓"
            )
            print(f"  {status} {r['key']:15s} → {r['screen_hash']}")


if __name__ == "__main__":
    asyncio.run(main())
