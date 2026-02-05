#!/usr/bin/env python3
"""Show FULL screen after sending A to see what success really looks like."""

import asyncio
from bbsbot.paths import default_knowledge_root
from bbsbot.core.session_manager import SessionManager


async def main():
    manager = SessionManager()
    knowledge_root = default_knowledge_root()

    session_id = await manager.create_session(
        host="localhost", port=2002, cols=80, rows=25, term="ANSI", timeout=10.0
    )
    session = await manager.get_session(session_id)
    await manager.enable_learning(session_id, knowledge_root, namespace="tw2002")

    await asyncio.sleep(2.0)
    await session.read(timeout_ms=1000, max_bytes=8192)

    await session.send("ShowBot\r")
    await asyncio.sleep(2.0)
    await session.read(timeout_ms=1000, max_bytes=8192)

    print("Sending 'A'...")
    await session.send("A")
    await asyncio.sleep(5.0)
    snapshot = await session.read(timeout_ms=2000, max_bytes=8192)

    print("="*80)
    print("FULL SCREEN AFTER SENDING 'A':")
    print("="*80)
    print(snapshot.get('screen', ''))
    print("="*80)
    print(f"\nPrompt detected: {snapshot.get('prompt_detected', 'None')}")
    print(f"Hash: {snapshot.get('screen_hash', '')[:16]}")

    await manager.close_all_sessions()


if __name__ == "__main__":
    asyncio.run(main())
