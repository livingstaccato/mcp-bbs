#!/usr/bin/env python3
"""Live test of prompt detection with Trade Wars 2002."""

import asyncio
import json
import sys

from mcp_bbs.core.session_manager import SessionManager
from mcp_bbs.config import get_default_knowledge_root


async def test_live_tw2002():
    """Test prompt detection with live TW2002 BBS."""
    print("=" * 80)
    print("LIVE TRADE WARS 2002 PROMPT DETECTION TEST")
    print("=" * 80)
    print()

    session_manager = SessionManager()
    knowledge_root = get_default_knowledge_root()

    try:
        # Connect to TW2002 on port 2002
        print("1. Connecting to localhost:2002...")
        session_id = await session_manager.create_session(
            host="localhost",
            port=2002,
            cols=80,
            rows=25,
            term="ANSI",
            timeout=10.0,
        )
        print(f"   ✓ Connected! Session ID: {session_id}")
        print()

        session = await session_manager.get_session(session_id)

        # Enable learning with tw2002 namespace (auto-loads patterns)
        print("2. Enabling learning with tw2002 namespace...")
        await session_manager.enable_learning(session_id, knowledge_root, namespace="tw2002")
        print(f"   ✓ Learning enabled")
        print(f"   - Patterns loaded: {len(session.learning._prompt_detector._patterns)}")
        print(f"   - Screen saver: {session.learning._screen_saver._enabled}")
        print()

        # Wait a moment for initial screen
        print("3. Reading initial screen...")
        await asyncio.sleep(1.0)

        snapshot = await session.read(timeout_ms=2000, max_bytes=8192)
        print(f"   Screen size: {len(snapshot['screen'])} chars")
        print(f"   Screen hash: {snapshot['screen_hash'][:16]}...")
        print(f"   Cursor: ({snapshot['cursor']['x']}, {snapshot['cursor']['y']})")
        print(f"   Cursor at end: {snapshot.get('cursor_at_end', 'N/A')}")
        print()

        # Show first 20 lines of screen
        print("   Screen content (first 20 lines):")
        print("   " + "-" * 76)
        lines = snapshot['screen'].split('\n')[:20]
        for line in lines:
            print(f"   {line}")
        print("   " + "-" * 76)
        print()

        # Check if prompt was detected
        if "prompt_detected" in snapshot:
            detected = snapshot["prompt_detected"]
            print(f"   🎯 PROMPT DETECTED!")
            print(f"   - Prompt ID: {detected['prompt_id']}")
            print(f"   - Input Type: {detected['input_type']}")
            print(f"   - Is Idle: {detected['is_idle']}")
            print()
        else:
            print(f"   ℹ️  No prompt detected in initial screen")
            print()

        # Test bbs_wait_for_prompt behavior
        print("4. Testing wait_for_prompt (waiting up to 5 seconds for any prompt)...")

        # Create a simple wait loop like the MCP tool does
        deadline = asyncio.get_event_loop().time() + 5.0
        matched = False

        while asyncio.get_event_loop().time() < deadline:
            snap = await session.read(timeout_ms=250, max_bytes=8192)

            if "prompt_detected" in snap:
                detected = snap["prompt_detected"]
                print(f"   ✓ Prompt detected!")
                print(f"   - Prompt ID: {detected['prompt_id']}")
                print(f"   - Input Type: {detected['input_type']}")
                print(f"   - Is Idle: {detected['is_idle']}")
                matched = True
                break

        if not matched:
            print(f"   ⚠️  No prompt detected within timeout")
        print()

        # Check buffer status
        print("5. Checking buffer status...")
        buffer_mgr = session.learning._buffer_manager
        is_idle = buffer_mgr.detect_idle_state(threshold_seconds=2.0)
        recent = buffer_mgr.get_recent(n=3)

        print(f"   - Buffer size: {len(buffer_mgr._buffer)}/{buffer_mgr._buffer.maxlen}")
        print(f"   - Is idle (2s threshold): {is_idle}")
        if recent:
            print(f"   - Last change: {recent[-1].time_since_last_change:.2f}s ago")
            print(f"   - Recent screens: {len(recent)}")
        print()

        # Check screen saver status
        print("6. Checking screen saver status...")
        saver_status = session.learning.get_screen_saver_status()
        print(f"   - Enabled: {saver_status['enabled']}")
        print(f"   - Saved count: {saver_status['saved_count']}")
        print(f"   - Screens dir: {saver_status['screens_dir']}")
        print()

        # List saved screens
        from pathlib import Path
        screens_dir = Path(saver_status['screens_dir'])
        if screens_dir.exists():
            screens = list(screens_dir.glob("*.txt"))
            print(f"   📁 Saved screens ({len(screens)}):")
            for screen_file in sorted(screens)[:5]:  # Show first 5
                print(f"      - {screen_file.name}")
            if len(screens) > 5:
                print(f"      ... and {len(screens) - 5} more")
        print()

        # Show current status
        print("7. Session status summary:")
        status = session.get_status()
        print(f"   - Connected: {status['connected']}")
        print(f"   - Host: {status['host']}:{status['port']}")
        print(f"   - Terminal: {status['cols']}x{status['rows']} {status['term']}")
        if session.learning:
            print(f"   - Learning namespace: {session.learning._namespace}")
            print(f"   - Patterns loaded: {len(session.learning._prompt_detector._patterns)}")
        print()

        print("=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)
        print()
        print("Summary:")
        print(f"  ✓ Connected to TW2002 on port 2002")
        print(f"  ✓ Loaded {len(session.learning._prompt_detector._patterns)} prompt patterns")
        print(f"  ✓ Screen buffering active ({len(buffer_mgr._buffer)} screens)")
        print(f"  ✓ Saved {saver_status['saved_count']} unique screens to disk")

        if matched:
            print(f"  ✓ Prompt detection working!")
        else:
            print(f"  ⚠️  No prompt detected - may need pattern refinement")

        print()

    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        # Cleanup
        print("Disconnecting...")
        await session_manager.close_all_sessions()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(test_live_tw2002())
