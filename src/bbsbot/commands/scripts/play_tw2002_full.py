#!/usr/bin/env python3
"""Complete Trade Wars 2002 playthrough - properly navigate TWGS menu + game."""

import asyncio
import json
import os
import time
from pathlib import Path

from bbsbot.paths import default_knowledge_root
from bbsbot.core.session_manager import SessionManager


class CompleteTW2002Player:
    """Complete automated Trade Wars 2002 player."""

    def __init__(self):
        self.session_manager = SessionManager()
        self.knowledge_root = default_knowledge_root()
        self.session_id = None
        self.session = None
        self.documentation = []
        self.step_counter = 0
        self.discovered_prompts = []

    async def connect(self):
        """Connect to TW2002 BBS."""
        print("=" * 80)
        print("TRADE WARS 2002 - COMPLETE PLAYTHROUGH & DOCUMENTATION")
        print("=" * 80)
        print()

        host = os.getenv("BBSBOT_TW_HOST", "localhost")
        port = int(os.getenv("BBSBOT_TW_PORT", "2002"))
        self.session_id = await self.session_manager.create_session(
            host=host, port=port, cols=80, rows=25, term="ANSI", timeout=10.0
        )
        self.session = await self.session_manager.get_session(self.session_id)
        await self.session_manager.enable_learning(self.session_id, self.knowledge_root, namespace="tw2002")

        print(f"✓ Connected to {host}:{port}")
        print(f"✓ Patterns loaded: {len(self.session.learning._prompt_detector._patterns)}")
        print()

    async def send(self, keys, desc=""):
        """Send keys with logging."""
        print(f"  → {desc or repr(keys)}")
        await self.session.send(keys)
        await asyncio.sleep(0.2)

    async def read_and_show(self, pause=0.5, max_lines=20):
        """Read screen and display it."""
        await asyncio.sleep(pause)
        snapshot = await self.session.read(timeout_ms=1000, max_bytes=8192)

        self.step_counter += 1
        print(f"\n{'─'*80}")
        print(f"STEP {self.step_counter}")
        print(f"{'─'*80}")

        # Show prompt detection
        if "prompt_detected" in snapshot:
            detected = snapshot["prompt_detected"]
            print(f"🎯 PROMPT: {detected['prompt_id']} ({detected['input_type']})")
            self.discovered_prompts.append(detected['prompt_id'])
        else:
            print(f"📄 Screen (no prompt detected)")

        # Show screen
        lines = snapshot.get('screen', '').split('\n')
        for i, line in enumerate(lines[:max_lines]):
            print(f"{i+1:2d}│ {line}")
        if len(lines) > max_lines:
            print(f"   │ ... ({len(lines) - max_lines} more lines)")

        print(f"{'─'*80}\n")
        return snapshot

    async def play(self):
        """Play through the game."""

        # Initial screen
        print("\n🎮 Starting playthrough...\n")
        snapshot = await self.read_and_show(pause=1.0, max_lines=25)

        username = os.getenv("BBSBOT_TW_USERNAME", "TestPlayer")
        password = os.getenv("BBSBOT_TW_PASSWORD", username)

        # Step 1: Telnet login name prompt (if present)
        screen_text = snapshot.get("screen", "").lower()
        detected = snapshot.get("prompt_detected", {})
        if "enter your name" in screen_text or detected.get("prompt_id") == "prompt.login_name":
            await self.send(f"{username}\r", "Enter player name")
            snapshot = await self.read_and_show(pause=1.0, max_lines=25)

        # Step 2: Select game from TWGS menu
        screen_text = snapshot.get("screen", "")
        detected = snapshot.get("prompt_detected", {})
        if "Select game" in screen_text or detected.get("prompt_id") == "prompt.twgs_select_game":
            await self.send("A", "Select 'A' - My Game")
            snapshot = await self.read_and_show(pause=2.0, max_lines=25)
            detected = snapshot.get("prompt_detected", {})
            if detected.get("prompt_id") == "prompt.twgs_select_game":
                await self.send("A\r", "Select 'A' with Enter")
                snapshot = await self.read_and_show(pause=2.0, max_lines=25)
                detected = snapshot.get("prompt_detected", {})

            if detected.get("prompt_id") == "prompt.twgs_select_game":
                print("  ❌ Still at TWGS game selection after attempts. Aborting playthrough.")
                return

        # Check if new player or returning
        screen_text = snapshot.get('screen', '').lower()

        if 'new player' in screen_text or 'create' in screen_text:
            print("  ℹ️  Detected new player creation")
            # May need to confirm or set password
            await self.send("Y\r", "Confirm new player")
            await self.read_and_show(pause=1.0)

            # Set password if prompted
            await self.send(f"{password}\r", "Set password")
            await self.read_and_show(pause=1.0)

            # Confirm password
            await self.send(f"{password}\r", "Confirm password")
            await self.read_and_show(pause=1.0)

        # Should be in game now - read initial game screen
        snapshot = await self.read_and_show(pause=2.0, max_lines=35)

        # Try common commands
        commands = [
            ("?\r", "Show help menu"),
            ("<\r", "Look around / Computer scan"),
            ("D\r", "Display computer"),
            ("I\r", "Show inventory"),
            ("P\r", "Port report"),
            ("L\r", "Long range scan"),
            ("C\r", "Corporate report"),
        ]

        for cmd, desc in commands:
            await self.send(cmd, desc)
            await self.read_and_show(pause=1.0, max_lines=30)

            # Check if we need to handle pagination
            snapshot = await self.session.read(timeout_ms=500, max_bytes=8192)
            if "prompt_detected" in snapshot:
                detected = snapshot["prompt_detected"]
                if detected["input_type"] == "any_key" or "more" in detected["prompt_id"].lower():
                    await self.send(" ", "Press space to continue")
                    await self.read_and_show(pause=0.5)

        # Try navigation
        await self.send("M\r", "Move to another sector")
        snapshot = await self.read_and_show(pause=1.0)

        # May ask which sector
        if 'sector' in snapshot.get('screen', '').lower():
            await self.send("2\r", "Move to sector 2")
            await self.read_and_show(pause=2.0)

        # Try docking at a port
        await self.send("R\r", "Dock at port (if available)")
        snapshot = await self.read_and_show(pause=1.5)

        # Try trading
        await self.send("T\r", "Trade")
        snapshot = await self.read_and_show(pause=1.0)

        # Quit game
        print("\n\n" + "="*80)
        print("ENDING GAME SESSION")
        print("="*80 + "\n")

        await self.send("Q\r", "Quit game")
        snapshot = await self.read_and_show(pause=1.0, max_lines=15)

        # Confirm quit if needed
        if "prompt_detected" in snapshot:
            detected = snapshot["prompt_detected"]
            if "quit" in detected["prompt_id"].lower() or detected["input_type"] == "single_key":
                await self.send("Y\r", "Confirm quit")
                await self.read_and_show(pause=0.5)

    async def show_stats(self):
        """Show final statistics."""
        print("\n" + "="*80)
        print("PLAYTHROUGH COMPLETE - STATISTICS")
        print("="*80)

        saver_status = self.session.learning.get_screen_saver_status()
        buffer_mgr = self.session.learning._buffer_manager

        print(f"\n📊 Statistics:")
        print(f"  - Steps executed: {self.step_counter}")
        print(f"  - Unique screens saved: {saver_status['saved_count']}")
        print(f"  - Screens buffered: {len(buffer_mgr._buffer)}/50")
        print(f"  - Prompts discovered: {len(set(self.discovered_prompts))}")

        print(f"\n🎯 Prompts detected during playthrough:")
        for i, prompt_id in enumerate(set(self.discovered_prompts), 1):
            print(f"  {i}. {prompt_id}")

        print(f"\n💾 Saved screens location:")
        print(f"  {saver_status['screens_dir']}")

        # List some saved screens
        screens_dir = Path(saver_status['screens_dir'])
        if screens_dir.exists():
            screens = sorted(screens_dir.glob("*.txt"))
            print(f"\n📁 Screen files ({len(screens)} total):")
            for screen_file in screens[:10]:
                print(f"  - {screen_file.name}")
            if len(screens) > 10:
                print(f"  ... and {len(screens) - 10} more")

        print()

    async def save_documentation(self):
        """Save documentation."""
        timestamp = int(time.time())
        json_file = Path(".provide") / f"tw2002-complete-{timestamp}.json"
        md_file = Path(".provide") / f"tw2002-complete-{timestamp}.md"

        # Save JSON
        json_file.parent.mkdir(exist_ok=True)
        with open(json_file, 'w') as f:
            json.dump({
                "session_id": self.session_id,
                "timestamp": timestamp,
                "steps": self.step_counter,
                "prompts_discovered": list(set(self.discovered_prompts)),
                "screens_saved": self.session.learning.get_screen_saver_status()['saved_count'],
            }, f, indent=2)

        # Save Markdown
        saver_status = self.session.learning.get_screen_saver_status()
        screens_dir = Path(saver_status['screens_dir'])

        with open(md_file, 'w') as f:
            f.write("# Trade Wars 2002 - Complete Playthrough Documentation\n\n")
            f.write(f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Session**: {self.session_id}\n")
            f.write(f"**Steps**: {self.step_counter}\n\n")

            f.write("## Prompts Discovered\n\n")
            for prompt_id in set(self.discovered_prompts):
                f.write(f"- `{prompt_id}`\n")

            f.write(f"\n## Screens Saved\n\n")
            f.write(f"Total unique screens: {saver_status['saved_count']}\n\n")
            f.write(f"Location: `{saver_status['screens_dir']}`\n\n")

            if screens_dir.exists():
                f.write("### Screen Files\n\n")
                for screen_file in sorted(screens_dir.glob("*.txt")):
                    f.write(f"- `{screen_file.name}`\n")

        print(f"\n📄 Documentation saved:")
        print(f"  - JSON: {json_file}")
        print(f"  - Markdown: {md_file}")
        print()

    async def run(self):
        """Run complete playthrough."""
        try:
            await self.connect()
            await self.play()
            await self.show_stats()
            await self.save_documentation()

        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            await self.show_stats()
        except Exception as e:
            print(f"\n\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("\nDisconnecting...")
            await self.session_manager.close_all_sessions()
            print("✓ Done.\n")


async def main():
    player = CompleteTW2002Player()
    await player.run()


if __name__ == "__main__":
    asyncio.run(main())
