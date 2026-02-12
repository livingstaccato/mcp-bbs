#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Manual step-by-step TW2002 test to diagnose communication issues."""

import asyncio

from bbsbot.core.session_manager import SessionManager
from bbsbot.paths import default_knowledge_root


async def main():
    manager = SessionManager()
    knowledge_root = default_knowledge_root()

    print("Step 1: Connecting to localhost:2002...")
    session_id = await manager.create_session(host="localhost", port=2002, cols=80, rows=25, term="ANSI", timeout=10.0)
    session = await manager.get_session(session_id)
    await manager.enable_learning(session_id, knowledge_root, namespace="tw2002")
    print("✓ Connected\n")

    print("Step 2: Waiting for initial screen...")
    await asyncio.sleep(3.0)
    snapshot = await session.read(timeout_ms=2000, max_bytes=8192)
    print(f"Screen:\n{snapshot.get('screen', '')}\n")
    if "prompt_detected" in snapshot:
        print(f"Detected: {snapshot['prompt_detected']}\n")

    print("Step 3: Sending player name 'ManualTest'...")
    await session.send("ManualTest\r")
    print("✓ Sent\n")

    print("Step 4: Waiting for response...")
    await asyncio.sleep(3.0)
    snapshot = await session.read(timeout_ms=2000, max_bytes=8192)
    print(f"Screen:\n{snapshot.get('screen', '')}\n")
    if "prompt_detected" in snapshot:
        print(f"Detected: {snapshot['prompt_detected']}\n")

    # Check if new player
    screen_text = snapshot.get("screen", "").lower()
    if "new player" in screen_text:
        print("Step 5: New player - confirming...")
        await session.send("Y\r")
        await asyncio.sleep(2.0)

        print("Step 6: Setting password...")
        await session.send("testpass\r")
        await asyncio.sleep(2.0)

        print("Step 7: Confirming password...")
        await session.send("testpass\r")
        await asyncio.sleep(3.0)

    print("Step 8: Reading game screen...")
    snapshot = await session.read(timeout_ms=2000, max_bytes=8192)
    print(f"Screen:\n{snapshot.get('screen', '')[:500]}\n")
    if "prompt_detected" in snapshot:
        print(f"Detected: {snapshot['prompt_detected']}\n")

    print("Step 9: Sending 'D' command...")
    await session.send("D\r")
    await asyncio.sleep(3.0)
    snapshot = await session.read(timeout_ms=2000, max_bytes=8192)
    print(f"Screen:\n{snapshot.get('screen', '')[:500]}\n")

    print("Step 10: Waiting 30 seconds to keep connection alive...")
    for i in range(6):
        await asyncio.sleep(5)
        print(f"  {(i + 1) * 5}s...")

    print("\nDisconnecting...")
    await manager.close_all_sessions()
    print("✓ Done")


if __name__ == "__main__":
    asyncio.run(main())
