#!/usr/bin/env python3
"""TW2002 Bot - 1000 Turn Playthrough with Prompt Detection.

This bot plays Trade Wars 2002 for 1000 turns using intelligent prompt detection
to navigate the game autonomously.
"""

import asyncio
import json
import random
import time
from pathlib import Path
from typing import Any

from mcp_bbs.config import get_default_knowledge_root
from mcp_bbs.core.session_manager import SessionManager


class TW2002_1000TurnBot:
    """Extended TW2002 bot for 1000-turn playthrough."""

    def __init__(self, host="localhost", port=2002):
        self.host = host
        self.port = port
        self.session_manager = SessionManager()
        self.knowledge_root = get_default_knowledge_root()
        self.session_id: str | None = None
        self.session: Any = None

        # Game state
        self.turns_played = 0
        self.target_turns = 1000
        self.current_sector = 1
        self.credits = 0
        self.current_location = "unknown"

        # Statistics
        self.actions_taken: list[dict] = []
        self.pattern_matches: dict[str, int] = {}
        self.errors_encountered: list[dict] = []
        self.start_time = 0
        self.last_prompt_id: str | None = None

    async def connect(self):
        """Connect to TW2002 BBS."""
        print("=" * 80)
        print("TW2002 - 1000 TURN AUTONOMOUS PLAYTHROUGH")
        print("=" * 80)
        print(f"Target: {self.target_turns} turns")
        print(f"Server: {self.host}:{self.port}")
        print()

        self.session_id = await self.session_manager.create_session(
            host=self.host, port=self.port, cols=80, rows=25, term="ANSI", timeout=10.0
        )
        self.session = await self.session_manager.get_session(self.session_id)
        await self.session_manager.enable_learning(
            self.session_id, self.knowledge_root, namespace="tw2002"
        )

        patterns = len(self.session.learning._prompt_detector._patterns)
        print(f"✓ Connected to {self.host}:{self.port}")
        print(f"✓ Learning enabled with {patterns} patterns")
        print()

    async def read_screen(self, timeout_ms=1000) -> dict:
        """Read current screen with detection."""
        return await self.session.read(timeout_ms=timeout_ms, max_bytes=8192)

    async def wait_for_prompt(self, max_wait=10.0, check_interval=0.3) -> dict:
        """Wait until a prompt is detected."""
        start = time.time()
        last_screen = None
        stable_count = 0

        while time.time() - start < max_wait:
            snapshot = await self.read_screen(timeout_ms=int(check_interval * 1000))
            screen = snapshot.get('screen', '')

            if 'prompt_detected' in snapshot:
                detected = snapshot['prompt_detected']
                prompt_id = detected['prompt_id']

                # Track pattern
                self.pattern_matches[prompt_id] = self.pattern_matches.get(prompt_id, 0) + 1
                self.last_prompt_id = prompt_id

                return snapshot

            # Check stability
            if screen == last_screen:
                stable_count += 1
                if stable_count >= 3:
                    return snapshot
            else:
                stable_count = 0
                last_screen = screen

            await asyncio.sleep(check_interval)

        raise TimeoutError(f"No prompt detected within {max_wait}s")

    async def send_and_wait(self, keys: str, action_desc: str = "", wait_time=0.5) -> dict:
        """Send input and wait for response."""
        if action_desc:
            print(f"  → {action_desc}")

        await self.session.send(keys)
        await asyncio.sleep(wait_time)

        snapshot = await self.wait_for_prompt()

        # Track action
        self.actions_taken.append({
            'turn': self.turns_played,
            'action': action_desc or keys,
            'prompt_detected': snapshot.get('prompt_detected', {}).get('prompt_id', 'none')
        })

        return snapshot

    async def handle_pagination(self, snapshot: dict) -> dict:
        """Auto-handle pagination prompts."""
        max_pages = 20
        pages = 0

        while pages < max_pages:
            if 'prompt_detected' not in snapshot:
                break

            detected = snapshot['prompt_detected']
            prompt_id = detected['prompt_id']
            input_type = detected['input_type']

            if input_type == 'any_key' or 'more' in prompt_id.lower() or 'press_any_key' in prompt_id:
                await self.session.send(" ")
                await asyncio.sleep(0.3)
                snapshot = await self.read_screen()
                pages += 1
            else:
                break

        return snapshot

    async def parse_screen_data(self, snapshot: dict):
        """Extract game data from screen."""
        screen = snapshot.get('screen', '')

        # Try to find turns remaining
        import re
        turns_match = re.search(r'Turns?[:\s]+(\d+)', screen, re.IGNORECASE)
        if turns_match:
            turns_available = int(turns_match.group(1))
            if turns_available == 0:
                print(f"\n⚠️  Out of turns!")
                return False

        # Try to find credits
        credits_match = re.search(r'Credits?[:\s]+(\d+)', screen, re.IGNORECASE)
        if credits_match:
            self.credits = int(credits_match.group(1))

        # Try to find current sector
        sector_match = re.search(r'Sector[:\s]+(\d+)', screen, re.IGNORECASE)
        if sector_match:
            self.current_sector = int(sector_match.group(1))

        return True

    async def navigate_to_game(self):
        """Navigate to game (handles both TWGS and direct login)."""
        print("\n🎮 Phase 1: Navigate to Game")
        print("=" * 80)

        # Wait for initial screen
        await asyncio.sleep(2.0)
        snapshot = await self.read_screen()

        # First, enter player name at login
        screen_text = snapshot.get('screen', '').lower()
        if 'please enter your name' in screen_text or ('prompt_detected' in snapshot and snapshot['prompt_detected']['prompt_id'] == 'login_username'):
            print("  At login prompt")
            player_name = "Bot1000"
            snapshot = await self.send_and_wait(f"{player_name}\r", f"Enter player: {player_name}", wait_time=2.0)
            screen_text = snapshot.get('screen', '').lower()

        # Check if we got TWGS game selection menu
        if 'select game' in screen_text or ('prompt_detected' in snapshot and snapshot['prompt_detected']['prompt_id'] == 'twgs_select_game'):
            print("  TWGS game selection menu detected - sending single key 'A'")
            # single_key prompt - send just 'A' without Enter
            await self.session.send("A")
            print("  Waiting for game description screen...")
            await asyncio.sleep(3.0)
            snapshot = await self.read_screen()
            print(f"  DEBUG: Screen after A: {snapshot.get('screen', '')[:100]}")

            # Check for "press any key" screen after selecting game
            if '[ANY KEY]' in snapshot.get('screen', '').upper() or 'NO DESCRIPTION' in snapshot.get('screen', '').upper():
                print("  Pressing key to continue past description...")
                await self.session.send(" ")
                await asyncio.sleep(3.0)
                snapshot = await self.read_screen()
                print(f"  DEBUG: Screen after space: {snapshot.get('screen', '')[:100]}")

            snapshot = await self.handle_pagination(snapshot)
            print(f"  DEBUG: Final screen hash: {snapshot.get('screen_hash', '')[:16]}")

        # Handle new player creation if needed
        screen_text = snapshot.get('screen', '').lower()
        if 'new player' in screen_text or 'create' in screen_text:
            print("  Creating new player...")
            await self.send_and_wait("Y\r", "Confirm new player")
            await self.send_and_wait("bot1000\r", "Set password")
            await self.send_and_wait("bot1000\r", "Confirm password")

        # Wait for game to load
        await asyncio.sleep(2.0)
        snapshot = await self.read_screen()

        print("✓ Entered game")
        self.current_location = "in_game"

    async def make_game_decision(self) -> tuple[str, str]:
        """Decide next action based on game state.

        Returns:
            (command, description) tuple
        """
        # Simple strategy: explore, trade, upgrade
        choices = [
            # Movement
            ("M\r", "Move to random sector", 0.3),

            # Information gathering
            ("D\r", "Display computer", 0.15),
            ("I\r", "Check inventory", 0.1),
            ("L\r", "Long range scan", 0.15),
            ("<\r", "Computer scan", 0.1),

            # Trading (if at port)
            ("P\r", "Port report", 0.1),

            # Exploration
            ("?\r", "Help/Commands", 0.05),
            ("C\r", "Corporate report", 0.05),
        ]

        # Weighted random choice
        total = sum(weight for _, _, weight in choices)
        rand = random.random() * total
        cumulative = 0

        for cmd, desc, weight in choices:
            cumulative += weight
            if rand <= cumulative:
                return cmd, desc

        return choices[0][0], choices[0][1]

    async def execute_turn(self) -> bool:
        """Execute one turn of gameplay.

        Returns:
            True if successful, False if should stop
        """
        try:
            # Decide action
            command, description = await self.make_game_decision()

            # Execute with longer wait for BBS to process
            snapshot = await self.send_and_wait(command, description, wait_time=2.0)

            # Handle pagination
            snapshot = await self.handle_pagination(snapshot)

            # Parse game data
            continue_playing = await self.parse_screen_data(snapshot)
            if not continue_playing:
                return False

            # Handle special prompts
            if 'prompt_detected' in snapshot:
                detected = snapshot['prompt_detected']
                prompt_id = detected['prompt_id']
                input_type = detected['input_type']

                # Handle sector movement
                if prompt_id == 'enter_number' and 'move' in description.lower():
                    # Choose random nearby sector
                    target_sector = random.randint(1, 100)
                    snapshot = await self.send_and_wait(
                        f"{target_sector}\r",
                        f"Move to sector {target_sector}",
                        wait_time=2.0
                    )
                    self.current_sector = target_sector

                # Handle yes/no prompts (usually say no to avoid traps)
                elif prompt_id == 'yes_no_prompt':
                    snapshot = await self.send_and_wait("N\r", "Decline", wait_time=2.0)

            # Increment turn counter
            self.turns_played += 1

            # Loop detection - check if we're seeing the same screen repeatedly
            screen_hash = snapshot.get('screen_hash', 'N/A')
            if not hasattr(self, 'screen_history'):
                self.screen_history = []

            self.screen_history.append(screen_hash)
            if len(self.screen_history) > 20:
                self.screen_history.pop(0)

            # Check if stuck - same screen for last 10 iterations
            if len(self.screen_history) >= 10:
                recent = self.screen_history[-10:]
                if len(set(recent)) == 1:
                    print(f"\n⚠️  LOOP DETECTED: Same screen for 10 turns! Hash: {screen_hash[:16]}")
                    print(f"Screen content:\n{snapshot.get('screen', '')[:200]}")
                    return False  # Stop the bot

            # Show progress every turn for debugging
            if self.turns_played <= 10 or self.turns_played % 10 == 0:
                screen_preview = snapshot.get('screen', '')[:100].replace('\n', ' ')
                print(f"  [Turn {self.turns_played} complete | Hash: {screen_hash[:8]} | Screen: {screen_preview}...]")

            # Add delay between turns to avoid overwhelming BBS
            await asyncio.sleep(1.0)
            return True

        except Exception as e:
            self.errors_encountered.append({
                'turn': self.turns_played,
                'error': str(e),
                'action': description if 'description' in locals() else 'unknown'
            })
            print(f"  ⚠️  Error on turn {self.turns_played}: {e}")
            import traceback
            traceback.print_exc()
            return True  # Continue despite error

    async def play_1000_turns(self):
        """Main game loop - play for 1000 turns."""
        print("\n🎲 Phase 2: Playing 1000 Turns")
        print("=" * 80)
        print()

        self.start_time = time.time()

        while self.turns_played < self.target_turns:
            # Progress indicator
            if self.turns_played % 50 == 0:
                elapsed = time.time() - self.start_time
                rate = self.turns_played / elapsed if elapsed > 0 else 0
                eta = (self.target_turns - self.turns_played) / rate if rate > 0 else 0

                print(f"\n{'─'*80}")
                print(f"Turn {self.turns_played}/{self.target_turns}")
                print(f"Elapsed: {elapsed:.1f}s | Rate: {rate:.1f} turns/sec | ETA: {eta:.1f}s")
                print(f"Sector: {self.current_sector} | Credits: {self.credits}")
                print(f"Patterns detected: {len(self.pattern_matches)}")
                print(f"Errors: {len(self.errors_encountered)}")
                print(f"{'─'*80}")

            # Execute turn
            should_continue = await self.execute_turn()
            if not should_continue:
                print(f"\n⚠️  Game ended at turn {self.turns_played}")
                break

            # Small delay to avoid overwhelming server
            await asyncio.sleep(0.1)

        print(f"\n✓ Completed {self.turns_played} turns")

    async def generate_final_report(self):
        """Generate comprehensive final report."""
        elapsed = time.time() - self.start_time

        print("\n" + "=" * 80)
        print("FINAL REPORT - 1000 TURN PLAYTHROUGH")
        print("=" * 80)

        print(f"\n📊 Statistics:")
        print(f"  Total turns: {self.turns_played}/{self.target_turns}")
        print(f"  Actions taken: {len(self.actions_taken)}")
        print(f"  Total time: {elapsed:.1f}s ({elapsed/60:.1f} minutes)")
        print(f"  Average: {self.turns_played/elapsed:.2f} turns/sec")
        print(f"  Final credits: {self.credits}")
        print(f"  Final sector: {self.current_sector}")

        print(f"\n🎯 Pattern Matches ({len(self.pattern_matches)}):")
        for pattern_id, count in sorted(self.pattern_matches.items(), key=lambda x: -x[1])[:20]:
            print(f"  {pattern_id}: {count} times")

        if len(self.pattern_matches) > 20:
            print(f"  ... and {len(self.pattern_matches) - 20} more")

        print(f"\n⚠️  Errors Encountered: {len(self.errors_encountered)}")
        if self.errors_encountered:
            for err in self.errors_encountered[:10]:
                print(f"  Turn {err['turn']}: {err['error'][:60]}")
            if len(self.errors_encountered) > 10:
                print(f"  ... and {len(self.errors_encountered) - 10} more")

        # Screen statistics
        saver_status = self.session.learning.get_screen_saver_status()
        print(f"\n💾 Screens Saved:")
        print(f"  Unique screens: {saver_status['saved_count']}")
        print(f"  Location: {saver_status['screens_dir']}")

    async def save_results(self):
        """Save playthrough results."""
        timestamp = int(time.time())
        json_file = Path(".provide") / f"tw2002-1000turns-{timestamp}.json"
        md_file = Path(".provide") / f"tw2002-1000turns-{timestamp}.md"

        json_file.parent.mkdir(exist_ok=True)

        # JSON
        results = {
            'timestamp': timestamp,
            'target_turns': self.target_turns,
            'turns_played': self.turns_played,
            'total_actions': len(self.actions_taken),
            'elapsed_time': time.time() - self.start_time,
            'pattern_matches': self.pattern_matches,
            'errors': self.errors_encountered,
            'final_state': {
                'sector': self.current_sector,
                'credits': self.credits,
            },
            'actions_sample': self.actions_taken[:100] + self.actions_taken[-100:] if len(self.actions_taken) > 200 else self.actions_taken,
        }

        with open(json_file, 'w') as f:
            json.dump(results, f, indent=2)

        # Markdown
        saver_status = self.session.learning.get_screen_saver_status()
        elapsed = time.time() - self.start_time

        with open(md_file, 'w') as f:
            f.write("# TW2002 - 1000 Turn Playthrough Results\n\n")
            f.write(f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Server**: {self.host}:{self.port}\n\n")

            f.write("## Summary\n\n")
            f.write(f"- **Target turns**: {self.target_turns}\n")
            f.write(f"- **Turns played**: {self.turns_played}\n")
            f.write(f"- **Total actions**: {len(self.actions_taken)}\n")
            f.write(f"- **Total time**: {elapsed:.1f}s ({elapsed/60:.1f} minutes)\n")
            f.write(f"- **Average rate**: {self.turns_played/elapsed:.2f} turns/sec\n")
            f.write(f"- **Errors**: {len(self.errors_encountered)}\n\n")

            f.write("## Final State\n\n")
            f.write(f"- **Sector**: {self.current_sector}\n")
            f.write(f"- **Credits**: {self.credits}\n\n")

            f.write("## Pattern Matches\n\n")
            for pattern_id, count in sorted(self.pattern_matches.items(), key=lambda x: -x[1]):
                f.write(f"- `{pattern_id}`: {count} times\n")

            if self.errors_encountered:
                f.write("\n## Errors\n\n")
                for err in self.errors_encountered:
                    f.write(f"- Turn {err['turn']}: {err['error']}\n")

            f.write(f"\n## Screens Saved\n\n")
            f.write(f"- **Count**: {saver_status['saved_count']} unique screens\n")
            f.write(f"- **Location**: `{saver_status['screens_dir']}`\n")

        print(f"\n📄 Results saved:")
        print(f"  JSON: {json_file}")
        print(f"  Markdown: {md_file}")

    async def run(self):
        """Run complete 1000-turn playthrough."""
        try:
            await self.connect()
            await self.navigate_to_game()
            await self.play_1000_turns()
            await self.generate_final_report()
            await self.save_results()

        except KeyboardInterrupt:
            print(f"\n\n⚠️  Interrupted at turn {self.turns_played}")
            await self.generate_final_report()
            await self.save_results()
        except Exception as e:
            print(f"\n\n❌ Fatal Error: {e}")
            import traceback
            traceback.print_exc()
            await self.generate_final_report()
            await self.save_results()
        finally:
            print("\nDisconnecting...")
            await self.session_manager.close_all_sessions()
            print("✓ Done.\n")


async def main():
    bot = TW2002_1000TurnBot(host="localhost", port=2002)
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
