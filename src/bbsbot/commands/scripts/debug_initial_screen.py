#!/usr/bin/env python3
"""Debug script to see initial TW2002 screen."""

import asyncio

from bbsbot.core.session_manager import SessionManager
from bbsbot.paths import default_knowledge_root


async def main():
    manager = SessionManager()
    knowledge_root = default_knowledge_root()

    print("Connecting to localhost:2002...")
    session_id = await manager.create_session(host="localhost", port=2002, cols=80, rows=25, term="ANSI", timeout=10.0)
    session = await manager.get_session(session_id)
    await manager.enable_learning(session_id, knowledge_root, namespace="tw2002")

    print("Connected. Waiting for initial screen...")
    await asyncio.sleep(2.0)

    snapshot = await session.read(timeout_ms=1000, max_bytes=8192)

    print("\n" + "=" * 80)
    print("INITIAL SCREEN")
    print("=" * 80)
    print(snapshot.get("screen", ""))
    print("=" * 80)

    if "prompt_detected" in snapshot:
        detected = snapshot["prompt_detected"]
        print(f"\n✓ Prompt detected: {detected['prompt_id']} ({detected['input_type']})")
        print(f"  Matched text: {repr(detected.get('matched_text', ''))}")
    else:
        print("\n⚠️  No prompt detected")

    print(f"\nCursor: {snapshot.get('cursor', {})}")
    print(f"Screen hash: {snapshot.get('screen_hash', 'N/A')[:16]}...")

    await manager.close_all_sessions()
    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
