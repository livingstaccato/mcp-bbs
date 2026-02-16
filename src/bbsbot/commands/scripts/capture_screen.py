#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Capture and save the actual screen the bot is seeing."""

import asyncio
from pathlib import Path

from bbsbot.core.session_manager import SessionManager
from bbsbot.paths import default_knowledge_root


async def main():
    manager = SessionManager()
    knowledge_root = default_knowledge_root()

    print("Connecting to check current screen state...")
    session_id = await manager.create_session(host="localhost", port=2002, cols=80, rows=25, term="ANSI", timeout=10.0)
    session = await manager.get_session(session_id)
    await manager.enable_learning(session_id, knowledge_root, namespace="tw2002")

    print("Waiting for screen...")
    await asyncio.sleep(2.0)

    snapshot = await session.read(timeout_ms=2000, max_bytes=8192)

    print("\n" + "=" * 80)
    print("ACTUAL SCREEN THE BOT SEES:")
    print("=" * 80)
    print(snapshot.get("screen", ""))
    print("=" * 80)

    if "prompt_detected" in snapshot:
        detected = snapshot["prompt_detected"]
        print(f"\nDetected prompt: {detected['prompt_id']} ({detected['input_type']})")
    else:
        print("\nNo prompt detected")

    print(f"\nCursor position: {snapshot.get('cursor', {})}")
    print(f"Screen hash: {snapshot.get('screen_hash', 'N/A')[:16]}...")

    # Save to file
    out_file = Path("logs/reports") / "bot-screen-capture.txt"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with out_file.open("w") as f:
        f.write(snapshot.get("screen", ""))
    print(f"\n✓ Screen saved to {out_file}")

    await manager.close_all_sessions()


if __name__ == "__main__":
    asyncio.run(main())
