#!/usr/bin/env python3
"""Intelligent TW2002 bot using prompt detection system.

This bot implements a hybrid reactive approach:
1. Phase 1: Pure reactive - detect prompts as they appear
2. Phase 2: Track prompt sequences and flows
3. Phase 3: Add prediction for common patterns (future enhancement)
"""

import asyncio
import json
import time
from pathlib import Path
from typing import Any

from bbsbot.paths import default_knowledge_root
from bbsbot.core.session_manager import SessionManager


class IntelligentTW2002Bot:
    """Prompt-detection-driven TW2002 player."""

    def __init__(self):
        self.session_manager = SessionManager()
        self.knowledge_root = default_knowledge_root()
        self.session_id: str | None = None
        self.session: Any = None

        # Tracking
        self.step_counter = 0
        self.detected_prompts: list[dict] = []
        self.prompt_sequences: list[tuple[str, str]] = []  # [(action, prompt_id), ...]
        self.last_prompt_id: str | None = None
        self.screens_saved = 0

        # Pattern validation tracking
        self.pattern_matches: dict[str, int] = {}  # pattern_id -> count
        self.pattern_test_results: list[dict] = []

        # State tracking
        self.current_state = "disconnected"
        self.game_location = "unknown"

    async def connect(self, host="localhost", port=2002):
        """Connect to TW2002 BBS with learning enabled."""
        print("=" * 80)
        print("INTELLIGENT TW2002 BOT - PROMPT DETECTION TESTING")
        print("=" * 80)
        print()

        self.session_id = await self.session_manager.create_session(
            host=host, port=port, cols=80, rows=25, term="ANSI", timeout=10.0
        )
        self.session = await self.session_manager.get_session(self.session_id)
        await self.session_manager.enable_learning(
            self.session_id, self.knowledge_root, namespace="tw2002"
        )

        patterns = len(self.session.learning._prompt_detector._patterns)
        print(f"✓ Connected to {host}:{port}")
        print(f"✓ Learning enabled with {patterns} patterns")
        print()

        self.current_state = "connected"

    async def read_screen(self, timeout_ms=1000, max_bytes=8192) -> dict:
        """Read current screen with detection.

        Returns:
            Snapshot dict with screen, prompt_detected, etc.
        """
        return await self.session.read(timeout_ms=timeout_ms, max_bytes=max_bytes)

    async def wait_for_prompt(
        self,
        expected_prompt_id: str | None = None,
        max_wait=10.0,
        check_interval=0.3
    ) -> dict:
        """Wait until a prompt is detected.

        Args:
            expected_prompt_id: If provided, wait for this specific prompt
            max_wait: Maximum seconds to wait
            check_interval: Seconds between checks

        Returns:
            Snapshot with detected prompt

        Raises:
            TimeoutError: If no prompt detected within max_wait
        """
        start = time.time()
        last_screen = None
        stable_count = 0

        while time.time() - start < max_wait:
            snapshot = await self.read_screen(timeout_ms=int(check_interval * 1000))
            screen = snapshot.get('screen', '')

            # Check for prompt detection
            if 'prompt_detected' in snapshot:
                detected = snapshot['prompt_detected']
                prompt_id = detected['prompt_id']

                # If expecting specific prompt, check match
                if expected_prompt_id:
                    if prompt_id == expected_prompt_id:
                        self._track_detection(snapshot)
                        return snapshot
                    # Wrong prompt - continue waiting
                else:
                    # Any prompt is fine
                    self._track_detection(snapshot)
                    return snapshot

            # No prompt detected - check if screen is stable (idle)
            if screen == last_screen:
                stable_count += 1
                if stable_count >= 3:  # Screen stable for 3 checks
                    # Might be unknown prompt or just waiting
                    print(f"  ⚠️  Screen stable but no prompt detected")
                    return snapshot
            else:
                stable_count = 0
                last_screen = screen

            await asyncio.sleep(check_interval)

        raise TimeoutError(f"No prompt detected within {max_wait}s")

    def _track_detection(self, snapshot: dict):
        """Track detected prompt for analysis."""
        if 'prompt_detected' not in snapshot:
            return

        detected = snapshot['prompt_detected']
        prompt_id = detected['prompt_id']

        # Track pattern match count
        self.pattern_matches[prompt_id] = self.pattern_matches.get(prompt_id, 0) + 1

        # Track prompt in history
        self.detected_prompts.append({
            'step': self.step_counter,
            'prompt_id': prompt_id,
            'input_type': detected['input_type'],
            'matched_text': detected.get('matched_text', ''),
        })

        self.last_prompt_id = prompt_id

    async def send_and_wait(
        self,
        keys: str,
        action_desc: str = "",
        expected_prompt: str | None = None,
        wait_time=1.0
    ) -> dict:
        """Send input and wait for next prompt.

        Args:
            keys: Keys to send
            action_desc: Description for logging
            expected_prompt: Expected prompt_id (optional)
            wait_time: Initial wait before checking

        Returns:
            Snapshot with next prompt detected
        """
        self.step_counter += 1

        # Log action and previous prompt context
        context = f" (from {self.last_prompt_id})" if self.last_prompt_id else ""
        print(f"\n[{self.step_counter}] {action_desc or repr(keys)}{context}")

        # Track sequence
        if self.last_prompt_id:
            self.prompt_sequences.append((action_desc or keys, self.last_prompt_id))

        # Send input
        await self.session.send(keys)
        await asyncio.sleep(wait_time)

        # Wait for next prompt
        snapshot = await self.wait_for_prompt(expected_prompt)

        # Show result
        if 'prompt_detected' in snapshot:
            detected = snapshot['prompt_detected']
            print(f"  → Detected: {detected['prompt_id']} ({detected['input_type']})")
        else:
            print(f"  → No prompt detected (screen stable)")

        return snapshot

    async def handle_pagination(self, snapshot: dict) -> dict:
        """Auto-handle pagination prompts.

        Args:
            snapshot: Current screen snapshot

        Returns:
            Final snapshot after all pagination handled
        """
        max_pages = 10
        pages = 0

        while pages < max_pages:
            if 'prompt_detected' not in snapshot:
                break

            detected = snapshot['prompt_detected']
            prompt_id = detected['prompt_id']
            input_type = detected['input_type']

            # Check if this is a pagination prompt
            if input_type == 'any_key' or 'more' in prompt_id.lower() or 'press_any_key' in prompt_id:
                print(f"  📄 Pagination detected ({prompt_id}) - continuing...")
                await self.session.send(" ")
                await asyncio.sleep(0.5)
                snapshot = await self.read_screen()
                pages += 1
            else:
                # Not pagination - return control
                break

        if pages > 0:
            print(f"  ✓ Handled {pages} page(s)")

        return snapshot

    async def show_screen(self, snapshot: dict, max_lines=25, title=""):
        """Display screen snapshot."""
        print(f"\n{'─'*80}")
        if title:
            print(f"{title}")
        else:
            print(f"SCREEN {self.step_counter}")
        print(f"{'─'*80}")

        # Show prompt info
        if 'prompt_detected' in snapshot:
            detected = snapshot['prompt_detected']
            print(f"🎯 Prompt: {detected['prompt_id']} ({detected['input_type']})")
            if 'matched_text' in detected:
                print(f"   Match: {repr(detected['matched_text'])}")

        # Show screen content
        screen = snapshot.get('screen', '')
        lines = screen.split('\n')
        for i, line in enumerate(lines[:max_lines], 1):
            print(f"{i:2d}│ {line}")

        if len(lines) > max_lines:
            print(f"  │ ... ({len(lines) - max_lines} more lines)")

        print(f"{'─'*80}")

    async def navigate_twgs_to_game(self):
        """Navigate TWGS menus to enter the game."""
        print("\n🎮 PHASE 1: Navigate TWGS to Game Entry")
        print("="*80)

        # Wait for initial screen
        await asyncio.sleep(1.5)
        snapshot = await self.read_screen()
        await self.show_screen(snapshot, title="Initial TWGS Screen")

        # Test pattern: twgs_main_menu or twgs_select_game
        snapshot = await self.send_and_wait(
            "A\r",
            "Select 'A' - My Game",
            wait_time=1.5
        )
        await self.show_screen(snapshot)

        self.game_location = "game_entry"

        # Handle pagination if present
        snapshot = await self.handle_pagination(snapshot)

        return snapshot

    async def enter_game_as_player(self, player_name="TestBot"):
        """Enter game with player name.

        Args:
            player_name: Name to use for player
        """
        print(f"\n👤 Entering game as: {player_name}")

        # Should be at player name prompt
        snapshot = await self.send_and_wait(
            f"{player_name}\r",
            f"Enter player name: {player_name}",
            wait_time=1.5
        )
        await self.show_screen(snapshot)

        # Check if new player creation
        screen_text = snapshot.get('screen', '').lower()

        if 'new player' in screen_text or 'create' in screen_text:
            print("  ℹ️  New player creation detected")

            # Confirm new player
            snapshot = await self.send_and_wait("Y\r", "Confirm new player")

            # Set password
            snapshot = await self.send_and_wait("testpass\r", "Set password")

            # Confirm password
            snapshot = await self.send_and_wait("testpass\r", "Confirm password")

        # Wait for game to load
        await asyncio.sleep(2.0)
        snapshot = await self.read_screen()
        await self.show_screen(snapshot, max_lines=35, title="Game Loaded")

        self.game_location = "in_game"
        return snapshot

    async def test_command(self, command: str, description: str, expected_pattern: str | None = None):
        """Test a game command and track pattern matching.

        Args:
            command: Command to send (with \\r if needed)
            description: What this command does
            expected_pattern: Expected prompt pattern (optional)
        """
        print(f"\n🧪 Testing: {description}")

        test_result = {
            'command': command,
            'description': description,
            'expected_pattern': expected_pattern,
            'detected_pattern': None,
            'success': False,
            'notes': []
        }

        try:
            snapshot = await self.send_and_wait(command, description, wait_time=1.0)

            # Handle pagination
            snapshot = await self.handle_pagination(snapshot)

            # Check detection
            if 'prompt_detected' in snapshot:
                detected = snapshot['prompt_detected']
                test_result['detected_pattern'] = detected['prompt_id']

                if expected_pattern:
                    if detected['prompt_id'] == expected_pattern:
                        test_result['success'] = True
                        test_result['notes'].append("✓ Matched expected pattern")
                    else:
                        test_result['notes'].append(
                            f"✗ Expected {expected_pattern}, got {detected['prompt_id']}"
                        )
                else:
                    test_result['success'] = True
                    test_result['notes'].append(f"✓ Detected {detected['prompt_id']}")
            else:
                test_result['notes'].append("⚠️  No prompt detected")

            await self.show_screen(snapshot, max_lines=20)

        except Exception as e:
            test_result['notes'].append(f"❌ Error: {e}")

        self.pattern_test_results.append(test_result)

        # Show result
        result_icon = "✓" if test_result['success'] else "✗"
        print(f"{result_icon} Test result: {' | '.join(test_result['notes'])}")

        return snapshot

    async def run_pattern_tests(self):
        """Run tests for all defined patterns."""
        print("\n🧪 PHASE 2: Pattern Testing")
        print("="*80)

        # Test basic commands (should trigger various prompts)
        tests = [
            ("?\r", "Show help menu", "command_prompt_generic"),
            ("D\r", "Display computer", None),
            ("I\r", "Show inventory", None),
            ("P\r", "Port report", None),
            ("L\r", "Long range scan", None),
            ("C\r", "Corporate report", None),
            ("<\r", "Computer scan", None),
        ]

        for cmd, desc, expected in tests:
            try:
                await self.test_command(cmd, desc, expected)
                await asyncio.sleep(0.5)
            except Exception as e:
                print(f"  ❌ Test failed: {e}")
                continue

    async def test_navigation(self):
        """Test navigation commands."""
        print("\n🧭 PHASE 3: Navigation Testing")
        print("="*80)

        # Try moving to another sector
        snapshot = await self.send_and_wait("M\r", "Move to sector", wait_time=1.0)
        await self.show_screen(snapshot)

        # Check if asking for sector number
        if 'prompt_detected' in snapshot:
            detected = snapshot['prompt_detected']
            if detected['input_type'] == 'multi_key' or 'enter_number' in detected['prompt_id']:
                # Enter sector number
                snapshot = await self.send_and_wait("2\r", "Move to sector 2", wait_time=1.5)
                await self.show_screen(snapshot)

    async def test_quit_sequence(self):
        """Test quitting game to validate quit prompts."""
        print("\n🚪 PHASE 4: Quit Sequence Testing")
        print("="*80)

        snapshot = await self.send_and_wait("Q\r", "Quit game", wait_time=1.0)
        await self.show_screen(snapshot)

        # Should trigger quit_confirm or yes_no_prompt
        if 'prompt_detected' in snapshot:
            detected = snapshot['prompt_detected']
            if 'quit' in detected['prompt_id'].lower() or detected['input_type'] == 'single_key':
                snapshot = await self.send_and_wait("Y\r", "Confirm quit")
                await self.show_screen(snapshot)

    async def generate_report(self):
        """Generate comprehensive test report."""
        print("\n" + "="*80)
        print("INTELLIGENT BOT - TEST RESULTS")
        print("="*80)

        # Pattern coverage
        print(f"\n📊 Pattern Matches:")
        for pattern_id, count in sorted(self.pattern_matches.items()):
            print(f"  ✓ {pattern_id}: {count} times")

        # Patterns never matched
        all_pattern_ids = {
            'login_username', 'login_password', 'press_any_key', 'main_menu',
            'yes_no_prompt', 'more_prompt', 'quit_confirm', 'enter_number',
            'sector_command', 'planet_command', 'twgs_select_game',
            'twgs_main_menu', 'command_prompt_generic'
        }
        unmatched = all_pattern_ids - set(self.pattern_matches.keys())

        if unmatched:
            print(f"\n⚠️  Patterns NOT matched ({len(unmatched)}):")
            for pattern_id in sorted(unmatched):
                print(f"  - {pattern_id}")

        # Test results summary
        print(f"\n🧪 Test Results Summary:")
        total = len(self.pattern_test_results)
        passed = sum(1 for t in self.pattern_test_results if t['success'])
        print(f"  Total tests: {total}")
        print(f"  Passed: {passed}")
        print(f"  Failed: {total - passed}")

        # Screen saver stats
        saver_status = self.session.learning.get_screen_saver_status()
        print(f"\n💾 Screen Saver:")
        print(f"  Saved: {saver_status['saved_count']} unique screens")
        print(f"  Location: {saver_status['screens_dir']}")

        # Prompt sequences
        print(f"\n📝 Prompt Sequences (first 10):")
        for action, prompt in self.prompt_sequences[:10]:
            print(f"  {action} → {prompt}")

        if len(self.prompt_sequences) > 10:
            print(f"  ... and {len(self.prompt_sequences) - 10} more")

    async def save_results(self):
        """Save test results to files."""
        timestamp = int(time.time())
        json_file = Path(".provide") / f"intelligent-bot-{timestamp}.json"
        md_file = Path(".provide") / f"intelligent-bot-{timestamp}.md"

        json_file.parent.mkdir(exist_ok=True)

        # Save JSON
        results = {
            'timestamp': timestamp,
            'steps': self.step_counter,
            'pattern_matches': self.pattern_matches,
            'test_results': self.pattern_test_results,
            'prompt_sequences': [
                {'action': a, 'from_prompt': p}
                for a, p in self.prompt_sequences
            ],
            'detected_prompts': self.detected_prompts,
        }

        with open(json_file, 'w') as f:
            json.dump(results, f, indent=2)

        # Save Markdown
        saver_status = self.session.learning.get_screen_saver_status()

        with open(md_file, 'w') as f:
            f.write("# Intelligent TW2002 Bot - Test Results\n\n")
            f.write(f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"**Steps**: {self.step_counter}\n\n")

            f.write("## Pattern Matches\n\n")
            for pattern_id, count in sorted(self.pattern_matches.items()):
                f.write(f"- `{pattern_id}`: {count} times\n")

            # Unmatched patterns
            all_pattern_ids = {
                'login_username', 'login_password', 'press_any_key', 'main_menu',
                'yes_no_prompt', 'more_prompt', 'quit_confirm', 'enter_number',
                'sector_command', 'planet_command', 'twgs_select_game',
                'twgs_main_menu', 'command_prompt_generic'
            }
            unmatched = all_pattern_ids - set(self.pattern_matches.keys())

            if unmatched:
                f.write(f"\n## Patterns NOT Matched ({len(unmatched)})\n\n")
                for pattern_id in sorted(unmatched):
                    f.write(f"- `{pattern_id}`\n")

            f.write("\n## Test Results\n\n")
            for test in self.pattern_test_results:
                icon = "✓" if test['success'] else "✗"
                f.write(f"### {icon} {test['description']}\n\n")
                f.write(f"- **Command**: `{test['command']}`\n")
                if test['expected_pattern']:
                    f.write(f"- **Expected**: `{test['expected_pattern']}`\n")
                if test['detected_pattern']:
                    f.write(f"- **Detected**: `{test['detected_pattern']}`\n")
                f.write(f"- **Notes**: {', '.join(test['notes'])}\n\n")

            f.write("\n## Screen Saves\n\n")
            f.write(f"- **Total**: {saver_status['saved_count']} unique screens\n")
            f.write(f"- **Location**: `{saver_status['screens_dir']}`\n\n")

            # List screens
            screens_dir = Path(saver_status['screens_dir'])
            if screens_dir.exists():
                screens = sorted(screens_dir.glob("*.txt"))
                f.write(f"### Screen Files ({len(screens)} total)\n\n")
                for screen_file in screens:
                    f.write(f"- `{screen_file.name}`\n")

        print(f"\n📄 Results saved:")
        print(f"  - JSON: {json_file}")
        print(f"  - Markdown: {md_file}")

    async def run(self):
        """Run complete intelligent bot test session."""
        try:
            # Connect
            await self.connect()

            # Phase 1: Navigate to game
            await self.navigate_twgs_to_game()

            # Enter as player
            await self.enter_game_as_player()

            # Phase 2: Test patterns with commands
            await self.run_pattern_tests()

            # Phase 3: Test navigation
            await self.test_navigation()

            # Phase 4: Test quit
            await self.test_quit_sequence()

            # Generate and save results
            await self.generate_report()
            await self.save_results()

        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted by user")
            await self.generate_report()
        except Exception as e:
            print(f"\n\n❌ Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            print("\nDisconnecting...")
            await self.session_manager.close_all_sessions()
            print("✓ Done.\n")


async def main():
    bot = IntelligentTW2002Bot()
    await bot.run()


if __name__ == "__main__":
    asyncio.run(main())
