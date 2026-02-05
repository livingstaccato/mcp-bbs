#!/usr/bin/env python3
"""Automated Trade Wars 2002 playthrough with full documentation."""

import asyncio
import json
import time
from pathlib import Path

from bbsbot.paths import default_knowledge_root
from bbsbot.core.session_manager import SessionManager


class TW2002Player:
    """Automated Trade Wars 2002 player with prompt detection."""

    def __init__(self):
        self.session_manager = SessionManager()
        self.knowledge_root = default_knowledge_root()
        self.session_id = None
        self.session = None
        self.documentation = []
        self.step_counter = 0

    async def connect(self):
        """Connect to TW2002 BBS."""
        print("=" * 80)
        print("TRADE WARS 2002 - AUTOMATED PLAYTHROUGH")
        print("=" * 80)
        print()
        print("Connecting to localhost:2002...")

        self.session_id = await self.session_manager.create_session(
            host="localhost",
            port=2002,
            cols=80,
            rows=25,
            term="ANSI",
            timeout=10.0,
        )

        self.session = await self.session_manager.get_session(self.session_id)

        # Enable learning
        await self.session_manager.enable_learning(
            self.session_id,
            self.knowledge_root,
            namespace="tw2002"
        )

        print(f"✓ Connected! Session ID: {self.session_id}")
        print(f"✓ Learning enabled with {len(self.session.learning._prompt_detector._patterns)} patterns")
        print()

    async def wait_for_prompt(self, prompt_id=None, timeout_ms=10000, description=""):
        """Wait for a specific prompt and document it."""
        self.step_counter += 1

        if description:
            print(f"\nStep {self.step_counter}: {description}")
        else:
            print(f"\nStep {self.step_counter}: Waiting for prompt{' ' + prompt_id if prompt_id else ''}...")

        deadline = asyncio.get_event_loop().time() + timeout_ms / 1000
        last_screen = None

        while asyncio.get_event_loop().time() < deadline:
            snapshot = await self.session.read(timeout_ms=250, max_bytes=8192)
            last_screen = snapshot

            if "prompt_detected" in snapshot:
                detected = snapshot["prompt_detected"]
                detected_id = detected.get("prompt_id")

                # Check if matches requested prompt
                if prompt_id is None or detected_id == prompt_id:
                    print(f"  ✓ Prompt detected: {detected_id}")
                    print(f"    - Input type: {detected['input_type']}")
                    print(f"    - Is idle: {detected['is_idle']}")

                    # Document this step
                    self.document_step(
                        step=self.step_counter,
                        description=description or f"Detected {detected_id}",
                        prompt_id=detected_id,
                        input_type=detected["input_type"],
                        screen=snapshot["screen"][:500],  # First 500 chars
                        screen_hash=snapshot["screen_hash"],
                    )

                    return snapshot

        # Timeout
        print(f"  ⚠️  Timeout waiting for prompt")
        if last_screen:
            print(f"  Last screen hash: {last_screen.get('screen_hash', 'unknown')[:16]}...")
            # Show last few lines
            lines = last_screen.get('screen', '').split('\n')
            print(f"  Last screen content (last 5 lines):")
            for line in lines[-5:]:
                print(f"    {line}")

        return last_screen

    async def send_keys(self, keys, description=""):
        """Send keystrokes and document."""
        if description:
            print(f"  → Sending: {description}")
        else:
            print(f"  → Sending: {repr(keys)}")

        await self.session.send(keys)
        await asyncio.sleep(0.3)  # Brief pause for BBS to process

    async def read_screen(self, pause=0.5):
        """Read current screen state."""
        await asyncio.sleep(pause)
        snapshot = await self.session.read(timeout_ms=1000, max_bytes=8192)
        return snapshot

    def document_step(self, step, description, prompt_id, input_type, screen, screen_hash):
        """Document a game step."""
        self.documentation.append({
            "step": step,
            "description": description,
            "prompt_id": prompt_id,
            "input_type": input_type,
            "screen_preview": screen,
            "screen_hash": screen_hash,
            "timestamp": time.time(),
        })

    def show_screen(self, snapshot, max_lines=25):
        """Display current screen."""
        print("\n" + "─" * 80)
        print("CURRENT SCREEN:")
        print("─" * 80)
        lines = snapshot.get('screen', '').split('\n')[:max_lines]
        for line in lines:
            print(line)
        print("─" * 80)

    async def play_game(self):
        """Play through Trade Wars 2002 game."""

        # Step 1: Login
        await self.wait_for_prompt(
            prompt_id="login_username",
            description="Waiting for login prompt"
        )

        await self.send_keys("TestPlayer\r", "Enter username 'TestPlayer'")

        # Wait for response (might be new player or password prompt)
        snapshot = await self.read_screen(pause=1.0)
        self.show_screen(snapshot, max_lines=15)

        # Check what we got
        if "prompt_detected" in snapshot:
            detected = snapshot["prompt_detected"]
            print(f"\n  Detected: {detected['prompt_id']}")

            if detected["prompt_id"] == "login_password":
                # Existing player
                await self.send_keys("testpass\r", "Enter password")
            else:
                # Handle other prompts
                print(f"  Unexpected prompt: {detected['prompt_id']}")

        # Wait for main menu or next prompt
        snapshot = await self.wait_for_prompt(
            timeout_ms=5000,
            description="Waiting for next prompt after login"
        )

        if snapshot:
            self.show_screen(snapshot, max_lines=25)

        # Continue exploring...
        # Send 'L' to look at current location or '?' for help
        await self.send_keys("?\r", "Request help menu")
        snapshot = await self.read_screen(pause=1.0)
        self.show_screen(snapshot)

        # Try to detect what commands are available
        print("\n🔍 Analyzing available commands...")
        screen_text = snapshot.get('screen', '')

        # Look for menu-style options
        import re
        menu_pattern = r'^\s*([A-Z])\s*[-:)]?\s*(.+)$'
        matches = re.findall(menu_pattern, screen_text, re.MULTILINE)

        if matches:
            print("  Found menu options:")
            for key, description in matches[:10]:  # Show first 10
                print(f"    {key}: {description.strip()}")

        # Wait for command prompt
        snapshot = await self.wait_for_prompt(
            timeout_ms=5000,
            description="Waiting for command prompt"
        )

        if snapshot:
            self.show_screen(snapshot, max_lines=10)

        # Try computer scan (D)
        await self.send_keys("D\r", "Display computer")
        snapshot = await self.read_screen(pause=1.5)
        self.show_screen(snapshot)

        # Continue navigation
        snapshot = await self.wait_for_prompt(
            timeout_ms=5000,
            description="Waiting for next command prompt"
        )

        # Try port report (P)
        await self.send_keys("P\r", "Port report")
        snapshot = await self.read_screen(pause=1.0)
        self.show_screen(snapshot)

        # Wait for next prompt
        snapshot = await self.wait_for_prompt(
            timeout_ms=5000,
            description="Waiting for command prompt"
        )

        # Try moving (M)
        await self.send_keys("M\r", "Move to another sector")
        snapshot = await self.read_screen(pause=1.0)
        self.show_screen(snapshot)

        # May ask which sector - try sector 2
        await self.send_keys("2\r", "Move to sector 2")
        snapshot = await self.read_screen(pause=1.5)
        self.show_screen(snapshot)

        # Check for warp prompt or other navigation
        snapshot = await self.wait_for_prompt(
            timeout_ms=5000,
            description="Checking after sector move"
        )

        # Quit gracefully
        print("\n\n" + "=" * 80)
        print("ENDING SESSION")
        print("=" * 80)

        # Try to quit (Q)
        await self.send_keys("Q\r", "Quit game")
        snapshot = await self.read_screen(pause=1.0)
        self.show_screen(snapshot, max_lines=10)

        # May need confirmation
        if snapshot and "prompt_detected" in snapshot:
            detected = snapshot["prompt_detected"]
            if "quit" in detected["prompt_id"].lower() or detected["input_type"] == "single_key":
                await self.send_keys("Y\r", "Confirm quit")
                await self.read_screen(pause=0.5)

    async def save_documentation(self):
        """Save game documentation to file."""
        doc_file = Path(".provide") / f"tw2002-playthrough-{int(time.time())}.json"
        doc_file.parent.mkdir(exist_ok=True)

        with open(doc_file, 'w') as f:
            json.dump({
                "session_id": self.session_id,
                "timestamp": time.time(),
                "steps": self.documentation,
                "total_steps": self.step_counter,
            }, f, indent=2)

        print(f"\n📄 Documentation saved to: {doc_file}")

        # Also create markdown summary
        md_file = doc_file.with_suffix('.md')
        with open(md_file, 'w') as f:
            f.write("# Trade Wars 2002 Playthrough\n\n")
            f.write(f"Session: {self.session_id}\n")
            f.write(f"Steps: {self.step_counter}\n\n")

            for doc in self.documentation:
                f.write(f"## Step {doc['step']}: {doc['description']}\n\n")
                f.write(f"- **Prompt ID**: {doc['prompt_id']}\n")
                f.write(f"- **Input Type**: {doc['input_type']}\n")
                f.write(f"- **Screen Hash**: {doc['screen_hash'][:16]}...\n\n")
                f.write("```\n")
                f.write(doc['screen_preview'])
                f.write("\n```\n\n")

        print(f"📄 Markdown summary saved to: {md_file}")

    async def show_final_stats(self):
        """Show final statistics."""
        print("\n" + "=" * 80)
        print("PLAYTHROUGH STATISTICS")
        print("=" * 80)

        # Get screen saver status
        saver_status = self.session.learning.get_screen_saver_status()

        print(f"Steps completed: {self.step_counter}")
        print(f"Unique screens saved: {saver_status['saved_count']}")
        print(f"Screens directory: {saver_status['screens_dir']}")

        # Get buffer stats
        buffer_mgr = self.session.learning._buffer_manager
        print(f"Screens buffered: {len(buffer_mgr._buffer)}/{buffer_mgr._buffer.maxlen}")

        # Pattern stats
        print(f"Patterns loaded: {len(self.session.learning._prompt_detector._patterns)}")

        print()

    async def run(self):
        """Run the complete playthrough."""
        try:
            await self.connect()
            await self.play_game()
            await self.show_final_stats()
            await self.save_documentation()

        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
        except Exception as e:
            print(f"\n\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("\nDisconnecting...")
            await self.session_manager.close_all_sessions()
            print("Done.")


async def main():
    """Main entry point."""
    player = TW2002Player()
    await player.run()


if __name__ == "__main__":
    asyncio.run(main())
