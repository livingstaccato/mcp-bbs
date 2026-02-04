#!/usr/bin/env python3
"""Test if we just need to wait longer after sending 'A'."""

import asyncio
from mcp_bbs.config import get_default_knowledge_root
from mcp_bbs.core.session_manager import SessionManager


async def main():
    manager = SessionManager()
    knowledge_root = get_default_knowledge_root()

    session_id = await manager.create_session(
        host="localhost", port=2002, cols=80, rows=25, term="ANSI", timeout=10.0
    )
    session = await manager.get_session(session_id)
    await manager.enable_learning(session_id, knowledge_root, namespace="tw2002")

    print("1. Logging in...")
    await asyncio.sleep(2.0)
    await session.read(timeout_ms=1000, max_bytes=8192)
    await session.send("LongWait\r")
    await asyncio.sleep(2.0)
    snapshot = await session.read(timeout_ms=2000, max_bytes=8192)
    print(f"   At menu: {snapshot.get('screen', '')[:80]}")

    print("\n2. Sending 'A' to select game...")
    await session.send("A")

    print("3. Waiting and checking screen every 5 seconds for 30 seconds...")
    for i in range(6):
        await asyncio.sleep(5)
        snapshot = await session.read(timeout_ms=2000, max_bytes=8192)
        screen = snapshot.get('screen', '')

        is_menu = 'Select game' in screen
        is_description = '[ANY KEY]' in screen
        is_different = not is_menu and not is_description and len(screen.strip()) > 50

        status = "MENU" if is_menu else "DESC" if is_description else "DIFFERENT!" if is_different else "???"
        print(f"   {(i+1)*5}s: {status} - {screen[:60].replace(chr(10), ' ')}")

        if is_different:
            print(f"\n✅ GOT DIFFERENT SCREEN!")
            print(f"Full screen:\n{screen}")
            break

    await manager.close_all_sessions()


if __name__ == "__main__":
    asyncio.run(main())
