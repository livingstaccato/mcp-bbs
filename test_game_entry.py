#!/usr/bin/env python3
"""Test complete game entry sequence step-by-step."""

import asyncio
from mcp_bbs.config import get_default_knowledge_root
from mcp_bbs.core.session_manager import SessionManager


async def main():
    manager = SessionManager()
    knowledge_root = get_default_knowledge_root()

    print("="*80)
    print("TESTING COMPLETE GAME ENTRY SEQUENCE")
    print("="*80)

    session_id = await manager.create_session(
        host="localhost", port=2002, cols=80, rows=25, term="ANSI", timeout=10.0
    )
    session = await manager.get_session(session_id)
    await manager.enable_learning(session_id, knowledge_root, namespace="tw2002")

    print("\n1. Waiting for login...")
    await asyncio.sleep(2.0)
    snapshot = await session.read(timeout_ms=2000, max_bytes=8192)
    print(f"Screen: {snapshot.get('screen', '')[:200]}")

    print("\n2. Sending player name 'TestEntry'...")
    await session.send("TestEntry\r")
    await asyncio.sleep(3.0)
    snapshot = await session.read(timeout_ms=2000, max_bytes=8192)
    print(f"Screen: {snapshot.get('screen', '')[:200]}")
    print(f"Prompt: {snapshot.get('prompt_detected', {})}")

    print("\n3. Sending 'A' to select game...")
    await session.send("A\r")
    await asyncio.sleep(3.0)
    snapshot = await session.read(timeout_ms=2000, max_bytes=8192)
    print(f"Screen:\n{snapshot.get('screen', '')}")
    print(f"\nPrompt: {snapshot.get('prompt_detected', {})}")

    print("\n4. Waiting 5 more seconds to see if anything changes...")
    await asyncio.sleep(5.0)
    snapshot = await session.read(timeout_ms=2000, max_bytes=8192)
    print(f"Screen:\n{snapshot.get('screen', '')}")
    print(f"\nPrompt: {snapshot.get('prompt_detected', {})}")

    print("\n5. Keeping connection alive for 20 seconds...")
    for i in range(4):
        await asyncio.sleep(5)
        print(f"  {(i+1)*5}s - still connected")

    await manager.close_all_sessions()
    print("\n✓ Test complete")


if __name__ == "__main__":
    asyncio.run(main())
