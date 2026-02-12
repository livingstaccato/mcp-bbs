#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Connect to TW2002, login, and wait idle."""

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

    print("✓ Connected")

    # Wait for initial screen
    await asyncio.sleep(2.0)
    snapshot = await session.read(timeout_ms=1000, max_bytes=8192)

    # Login
    print("Logging in as Bot1000...")
    await session.send("Bot1000\r")
    await asyncio.sleep(2.0)

    snapshot = await session.read(timeout_ms=1000, max_bytes=8192)

    # Check if need to create new player
    screen_text = snapshot.get("screen", "").lower()
    if "new player" in screen_text or "create" in screen_text:
        print("  Creating new player...")
        await session.send("Y\r")
        await asyncio.sleep(1.0)
        await session.send("bot1000\r")
        await asyncio.sleep(1.0)
        await session.send("bot1000\r")
        await asyncio.sleep(2.0)

    print("✓ Logged in")
    print("\nWaiting idle... (Press Ctrl+C to disconnect)")

    try:
        # Just wait forever, keeping connection alive
        while True:
            await asyncio.sleep(60)
            print("  Still connected...")
    except KeyboardInterrupt:
        print("\n\nDisconnecting...")
        await manager.close_all_sessions()
        print("✓ Disconnected")


if __name__ == "__main__":
    asyncio.run(main())
