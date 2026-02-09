#!/usr/bin/env python3
"""Test if there are different TWGS commands besides just 'A'."""

import asyncio
from bbsbot.paths import default_knowledge_root
from bbsbot.core.session_manager import SessionManager


async def test_command(desc: str, menu_command: str):
    """Test a specific command at TWGS menu."""
    manager = SessionManager()
    knowledge_root = default_knowledge_root()

    try:
        session_id = await manager.create_session(
            host="localhost", port=2002, cols=80, rows=25, term="ANSI", timeout=10.0
        )
        session = await manager.get_session(session_id)
        await manager.enable_learning(session_id, knowledge_root, namespace="tw2002")

        # Login
        await asyncio.sleep(2.0)
        await session.wait_for_update(timeout_ms=1000)
        await session.send(f"Test{desc}\r")
        await asyncio.sleep(2.0)
        await session.wait_for_update(timeout_ms=2000)

        # Send the command at TWGS menu
        await session.send(menu_command)
        await asyncio.sleep(4.0)
        await session.wait_for_update(timeout_ms=2000)
        snapshot = session.snapshot()

        screen = snapshot.get('screen', '')
        is_menu = 'Select game' in screen
        is_log_prompt = 'name (ENTER' in screen.lower()
        has_command_prompt = 'Command' in screen

        await manager.close_all_sessions()

        return {
            'command': repr(menu_command),
            'at_menu': is_menu,
            'at_login': is_log_prompt,
            'has_prompt': has_command_prompt,
            'screen_first_100': screen[:100].replace('\n', ' ')
        }
    except Exception as e:
        return {'command': repr(menu_command), 'error': str(e)}


async def main():
    print("="*80)
    print("TESTING DIFFERENT TWGS MENU COMMANDS")
    print("="*80)
    print("Maybe 'A' shows description, but we need a different command to ENTER?")
    print()

    # Test various potential commands
    test_cases = [
        ("A\\r", "A\r"),  # 'A' with enter - standard way to select
        ("?", "?"),  # Help
        ("H", "H"),  # Help?
        ("E", "E"),  # Enter?
        ("S", "S"),  # Start?
        ("P", "P"),  # Play?
        ("J", "J"),  # Join?
        ("L", "L"),  # Load?
        ("Athenspace", "A "),  # 'A' then space (maybe space means "enter this game")
        ("1", "1"),  # Maybe games are numbered
        ("Q", "Q"),  # Quit (to see what valid commands are)
    ]

    for desc, command in test_cases:
        print(f"Testing {desc:15s}...", end=" ")
        result = await test_command(desc, command)

        if 'error' in result:
            print(f"❌ Error: {result['error']}")
        elif not result.get('at_menu') and not result.get('at_login'):
            print(f"✅ DIFFERENT SCREEN!")
            print(f"   Screen: {result['screen_first_100']}")
        else:
            status = "MENU" if result.get('at_menu') else "LOGIN"
            print(f"⚠️  Still at {status}")

        await asyncio.sleep(1.0)


if __name__ == "__main__":
    asyncio.run(main())
