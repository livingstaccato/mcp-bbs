#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Complete Trade Wars 2002 playthrough - properly navigate TWGS menu + game."""

import asyncio
import json
import os
import time
from pathlib import Path

from bbsbot.core.session_manager import SessionManager
from bbsbot.paths import default_knowledge_root


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
        print(f"\n{'─' * 80}")
        print(f"STEP {self.step_counter}")
        print(f"{'─' * 80}")

        # Show prompt detection
        if "prompt_detected" in snapshot:
            detected = snapshot["prompt_detected"]
            print(f"🎯 PROMPT: {detected['prompt_id']} ({detected['input_type']})")
            self.discovered_prompts.append(detected["prompt_id"])
        else:
            print("📄 Screen (no prompt detected)")

        # Show screen
        lines = snapshot.get("screen", "").split("\n")
        for i, line in enumerate(lines[:max_lines]):
            print(f"{i + 1:2d}│ {line}")
        if len(lines) > max_lines:
            print(f"   │ ... ({len(lines) - max_lines} more lines)")

        print(f"{'─' * 80}\n")
        return snapshot

    def _is_game_prompt(self, screen_lower: str) -> bool:
        if "sector command" in screen_lower or "planet command" in screen_lower:
            return True
        return "command [" in screen_lower

    async def _reach_game(self, snapshot, username: str, password: str, game_letter: str):
        """Navigate menus until we reach the game prompt."""
        for _ in range(30):
            screen_text = snapshot.get("screen", "")
            screen_lower = screen_text.lower()
            lines = screen_text.splitlines()
            tail = "\n".join(lines[-5:]).lower() if lines else ""
            detected = snapshot.get("prompt_detected", {}) or {}
            prompt_id = detected.get("prompt_id", "")

            if "enter your name" in screen_lower or prompt_id == "prompt.login_name":
                await self.send(f"{username}\r", "Enter player name")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if "select game (q for none)" in screen_lower:
                await self.send("Q", "Exit description mode")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if "selection (? for menu)" in screen_lower or prompt_id == "prompt.menu_selection":
                await self.send(game_letter, f"Select game {game_letter}")
                snapshot = await self.read_and_show(pause=2.0, max_lines=25)
                continue

            if "private game" in screen_lower and "password" in screen_lower:
                await self.send(f"{password}\r", "Enter game password")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if "trade wars 2002" in screen_lower and "enter your choice" in tail:
                await self.send("T\r", "Play Trade Wars 2002")
                snapshot = await self.read_and_show(pause=2.0, max_lines=25)
                continue

            if "show today's log" in screen_lower:
                await self.send("N\r", "Skip today's log")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if "start a new character" in tail and "password" not in tail:
                await self.send("Y\r", "Start new character")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if "use (n)ew name" in screen_lower and "what alias do you want to use" not in screen_lower:
                await self.send("\r", "Use default BBS name")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if (
                "is what you want" in screen_lower
                and "ship" not in tail
                and ("alias" in screen_lower or "commander" in screen_lower)
            ):
                await self.send("Y\r", "Confirm alias")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if "what alias do you want to use" in screen_lower and "is what you want" not in screen_lower:
                await self.send(f"{username}\r", "Alias")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if "repeat password" in tail or "verify" in tail:
                await self.send(f"{password}\r{password}\r", "Set + confirm password")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if "password?" in tail:
                await self.send(f"{password}\r", "Set password")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if prompt_id == "prompt.game_password":
                await self.send(f"{password}\r", "Enter password")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if (
                "home planet" in screen_lower
                and "name your home planet" in screen_lower
                and "planet command" not in screen_lower
            ):
                planet_name = f"{username} Prime"
                await self.send(f"{planet_name}\r", "Home planet name")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if prompt_id == "prompt.ship_name":
                if "is what you want" in tail:
                    await self.send("Y\r", "Confirm ship name")
                    snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                else:
                    ship_name = f"{username}'s ship"
                    await self.send(f"{ship_name}\r", "Ship name")
                    snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if "ship" in tail and "name" in tail:
                ship_name = f"{username}'s ship"
                await self.send(f"{ship_name}\r", "Ship name")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if "is what you want" in tail and "ship" in tail:
                await self.send("Y\r", "Confirm ship name")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if prompt_id == "prompt.any_key" or "[any key]" in screen_lower:
                await self.send(" ", "Continue")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if "[pause]" in screen_lower:
                await self.send(" ", "Continue")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if "use ansi graphics" in screen_lower:
                await self.send("Y\r", "Use ANSI graphics")
                snapshot = await self.read_and_show(pause=1.0, max_lines=25)
                continue

            if self._is_game_prompt(screen_lower):
                return snapshot

            snapshot = await self.read_and_show(pause=1.0, max_lines=25)

        print("  ❌ Failed to reach game prompt within step limit.")
        return None

    async def play(self):
        """Play through the game."""

        # Initial screen
        print("\n🎮 Starting playthrough...\n")
        snapshot = await self.read_and_show(pause=1.0, max_lines=25)

        username = os.getenv("BBSBOT_TW_USERNAME", "TestPlayer")
        password = os.getenv("BBSBOT_TW_PASSWORD", username)
        game_letter = os.getenv("BBSBOT_TW_GAME", "B")

        snapshot = await self._reach_game(snapshot, username, password, game_letter)
        if snapshot is None:
            return

        # If we're on a planet prompt, exit to sector command before running commands.
        screen_text = snapshot.get("screen", "").lower()
        if "planet command" in screen_text:
            await self.send("Q\r", "Leave planet prompt")
            await self.read_and_show(pause=1.0, max_lines=25)

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
        if "sector" in snapshot.get("screen", "").lower():
            await self.send("2\r", "Move to sector 2")
            await self.read_and_show(pause=2.0)

        # Try docking at a port
        await self.send("R\r", "Dock at port (if available)")
        snapshot = await self.read_and_show(pause=1.5)

        # Try trading
        await self.send("T\r", "Trade")
        snapshot = await self.read_and_show(pause=1.0)

        # Quit game
        print("\n\n" + "=" * 80)
        print("ENDING GAME SESSION")
        print("=" * 80 + "\n")

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
        print("\n" + "=" * 80)
        print("PLAYTHROUGH COMPLETE - STATISTICS")
        print("=" * 80)

        saver_status = self.session.learning.get_screen_saver_status()
        buffer_mgr = self.session.learning._buffer_manager

        print("\n📊 Statistics:")
        print(f"  - Steps executed: {self.step_counter}")
        print(f"  - Unique screens saved: {saver_status['saved_count']}")
        print(f"  - Screens buffered: {len(buffer_mgr._buffer)}/50")
        print(f"  - Prompts discovered: {len(set(self.discovered_prompts))}")

        print("\n🎯 Prompts detected during playthrough:")
        for i, prompt_id in enumerate(set(self.discovered_prompts), 1):
            print(f"  {i}. {prompt_id}")

        print("\n💾 Saved screens location:")
        print(f"  {saver_status['screens_dir']}")

        # List some saved screens
        screens_dir = Path(saver_status["screens_dir"])
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
        with open(json_file, "w") as f:
            json.dump(
                {
                    "session_id": self.session_id,
                    "timestamp": timestamp,
                    "steps": self.step_counter,
                    "prompts_discovered": list(set(self.discovered_prompts)),
                    "screens_saved": self.session.learning.get_screen_saver_status()["saved_count"],
                },
                f,
                indent=2,
            )

        # Save Markdown
        saver_status = self.session.learning.get_screen_saver_status()
        screens_dir = Path(saver_status["screens_dir"])

        with open(md_file, "w") as f:
            f.write("# Trade Wars 2002 - Complete Playthrough Documentation\n\n")
            f.write(f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Session**: {self.session_id}\n")
            f.write(f"**Steps**: {self.step_counter}\n\n")

            f.write("## Prompts Discovered\n\n")
            for prompt_id in set(self.discovered_prompts):
                f.write(f"- `{prompt_id}`\n")

            f.write("\n## Screens Saved\n\n")
            f.write(f"Total unique screens: {saver_status['saved_count']}\n\n")
            f.write(f"Location: `{saver_status['screens_dir']}`\n\n")

            if screens_dir.exists():
                f.write("### Screen Files\n\n")
                for screen_file in sorted(screens_dir.glob("*.txt")):
                    f.write(f"- `{screen_file.name}`\n")

        print("\n📄 Documentation saved:")
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
