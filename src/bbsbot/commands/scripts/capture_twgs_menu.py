#!/usr/bin/env python3
"""Capture the exact TWGS menu to understand what options are available."""

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

    print("="*80)
    print("STEP 1: LOGIN SCREEN")
    print("="*80)
    await asyncio.sleep(2.0)
    snapshot = await session.read(timeout_ms=2000, max_bytes=8192)
    print(snapshot.get('screen', ''))
    print(f"\nPrompt detected: {snapshot.get('prompt_detected', 'None')}")

    print("\n" + "="*80)
    print("STEP 2: AFTER ENTERING NAME 'MenuCapture'")
    print("="*80)
    await session.send("MenuCapture\r")
    await asyncio.sleep(3.0)
    snapshot = await session.read(timeout_ms=2000, max_bytes=8192)
    print(snapshot.get('screen', ''))
    print(f"\nPrompt detected: {snapshot.get('prompt_detected', 'None')}")
    print(f"Hash: {snapshot.get('screen_hash', '')[:16]}")

    print("\n" + "="*80)
    print("WAITING 10 SECONDS TO SEE IF ANYTHING CHANGES...")
    print("="*80)
    await asyncio.sleep(10.0)
    snapshot = await session.read(timeout_ms=2000, max_bytes=8192)
    print(snapshot.get('screen', ''))
    print(f"\nPrompt detected: {snapshot.get('prompt_detected', 'None')}")
    print(f"Hash: {snapshot.get('screen_hash', '')[:16]}")

    await manager.close_all_sessions()


if __name__ == "__main__":
    asyncio.run(main())
