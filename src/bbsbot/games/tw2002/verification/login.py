# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio

from bbsbot.core.session_manager import SessionManager


async def login() -> None:
    manager = SessionManager()

    sid = await manager.create_session(host="localhost", port=2002, reuse=False)
    session = await manager.get_session(sid)

    await asyncio.sleep(2)
    await session.wait_for_update(timeout_ms=1000)

    print("Selecting A...")
    await session.send("A")
    await asyncio.sleep(1)
    await session.wait_for_update(timeout_ms=1000)

    print("Sending password 'game'...")
    await session.send("game")
    await asyncio.sleep(1)
    await session.wait_for_update(timeout_ms=1000)

    print("Sending CR...")
    await session.send("\r")
    await asyncio.sleep(1)
    await session.wait_for_update(timeout_ms=1000)
    snapshot = session.snapshot()
    print(f"Screen after CR: {snapshot.get('screen')}")

    print("Sending name 'gemini'...")
    await session.send("gemini")
    await asyncio.sleep(1)
    await session.send("\r")
    await asyncio.sleep(1)
    await session.wait_for_update(timeout_ms=1000)

    print("Sending Y for ANSI...")
    await session.send("Y")
    await asyncio.sleep(2)
    await session.wait_for_update(timeout_ms=1000)

    print("Sending T to play...")
    await session.send("T")
    await asyncio.sleep(1)
    await session.send("\r")
    await asyncio.sleep(1)
    await session.wait_for_update(timeout_ms=1000)

    print("Sending N for log...")
    await session.send("N")
    await asyncio.sleep(2)
    await session.wait_for_update(timeout_ms=1000)

    print("Sending Y for new character...")
    await session.send("Y")
    await asyncio.sleep(1)
    await session.send("\r")
    await asyncio.sleep(2)
    await session.wait_for_update(timeout_ms=1000)
    snapshot = session.snapshot()
    print(f"Final Screen:\n{snapshot.get('screen')}")

    await manager.close_all_sessions()


if __name__ == "__main__":
    asyncio.run(login())
