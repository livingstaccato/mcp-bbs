#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Systematic testing of all 13 TW2002 prompt patterns.

This script validates each pattern definition against live BBS screens.
"""

import asyncio
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict

from bbsbot.core.session_manager import SessionManager
from bbsbot.paths import default_knowledge_root


class PatternTest(BaseModel):
    """Test case for a prompt pattern."""

    pattern_id: str
    trigger_sequence: list[tuple[str, str]]  # [(keys, description), ...]
    expected_detection: bool = True
    notes: str = ""

    model_config = ConfigDict(extra="ignore")


class PatternValidator:
    """Validates prompt patterns against live BBS."""

    # Define test sequences for each pattern
    PATTERN_TESTS = [
        PatternTest(
            pattern_id="login_username",
            trigger_sequence=[],  # Should appear on initial connect
            notes="Initial connection - username prompt",
        ),
        PatternTest(
            pattern_id="login_password",
            trigger_sequence=[("testuser\r", "Enter username")],
            notes="After entering username",
        ),
        PatternTest(
            pattern_id="twgs_main_menu",
            trigger_sequence=[
                ("testuser\r", "Username"),
                ("testpass\r", "Password"),
            ],
            notes="TWGS main menu after login",
        ),
        PatternTest(
            pattern_id="twgs_select_game",
            trigger_sequence=[
                ("testuser\r", "Username"),
                ("testpass\r", "Password"),
                ("A\r", "Select game option"),
            ],
            notes="Game selection menu",
        ),
        PatternTest(
            pattern_id="main_menu",
            trigger_sequence=[
                # Navigate to in-game first
                ("testuser\r", "Username"),
                ("testpass\r", "Password"),
                ("A\r", "My Game"),
                ("TestBot\r", "Player name"),
            ],
            notes="In-game main command prompt",
        ),
        PatternTest(
            pattern_id="command_prompt_generic",
            trigger_sequence=[
                # In-game, then trigger help
                ("testuser\r", "Username"),
                ("testpass\r", "Password"),
                ("A\r", "My Game"),
                ("TestBot\r", "Player name"),
                ("?\r", "Help menu"),
            ],
            notes="Generic command prompt (help menu)",
        ),
        PatternTest(
            pattern_id="press_any_key",
            trigger_sequence=[
                # Look for screens with pause prompts
                ("testuser\r", "Username"),
                ("testpass\r", "Password"),
                ("A\r", "My Game"),
                ("TestBot\r", "Player name"),
                ("D\r", "Display computer - may have pause"),
            ],
            notes="Pause prompt - press any key",
        ),
        PatternTest(
            pattern_id="more_prompt",
            trigger_sequence=[
                # Look for paginated screens
                ("testuser\r", "Username"),
                ("testpass\r", "Password"),
                ("A\r", "My Game"),
                ("TestBot\r", "Player name"),
                ("L\r", "Long range scan - may paginate"),
            ],
            notes="Pagination 'more' prompt",
        ),
        PatternTest(
            pattern_id="sector_command",
            trigger_sequence=[
                # In-game at sector
                ("testuser\r", "Username"),
                ("testpass\r", "Password"),
                ("A\r", "My Game"),
                ("TestBot\r", "Player name"),
            ],
            notes="Sector-specific command prompt",
        ),
        PatternTest(
            pattern_id="enter_number",
            trigger_sequence=[
                # Trigger move command
                ("testuser\r", "Username"),
                ("testpass\r", "Password"),
                ("A\r", "My Game"),
                ("TestBot\r", "Player name"),
                ("M\r", "Move - should ask for sector number"),
            ],
            notes="Numeric input prompt (sector number)",
        ),
        PatternTest(
            pattern_id="quit_confirm",
            trigger_sequence=[
                # Trigger quit
                ("testuser\r", "Username"),
                ("testpass\r", "Password"),
                ("A\r", "My Game"),
                ("TestBot\r", "Player name"),
                ("Q\r", "Quit - should confirm"),
            ],
            notes="Quit confirmation prompt",
        ),
        PatternTest(
            pattern_id="yes_no_prompt",
            trigger_sequence=[
                # Same as quit - should be Y/N
                ("testuser\r", "Username"),
                ("testpass\r", "Password"),
                ("A\r", "My Game"),
                ("TestBot\r", "Player name"),
                ("Q\r", "Quit"),
            ],
            notes="Yes/No prompt (quit confirmation)",
        ),
        PatternTest(
            pattern_id="planet_command",
            trigger_sequence=[
                # Would need to land on planet first
                # This is harder to test - may not trigger
            ],
            expected_detection=False,
            notes="Planet command prompt (requires being on planet)",
        ),
    ]

    def __init__(self):
        self.session_manager = SessionManager()
        self.knowledge_root = default_knowledge_root()
        self.session_id: str | None = None
        self.session: Any = None

        # Results tracking
        self.test_results: list[dict] = []
        self.pattern_coverage: set[str] = set()

    async def connect(self):
        """Connect to BBS with learning enabled."""
        print("=" * 80)
        print("PATTERN VALIDATION - Testing All 13 Patterns")
        print("=" * 80)
        print()

        self.session_id = await self.session_manager.create_session(
            host="localhost", port=2002, cols=80, rows=25, term="ANSI", timeout=10.0
        )
        self.session = await self.session_manager.get_session(self.session_id)
        await self.session_manager.enable_learning(self.session_id, self.knowledge_root, namespace="tw2002")

        patterns = len(self.session.learning._prompt_detector._patterns)
        print("✓ Connected to localhost:2002")
        print(f"✓ Testing {patterns} patterns")
        print()

    async def read_with_wait(self, wait_time=1.0) -> dict:
        """Read screen after waiting."""
        await asyncio.sleep(wait_time)
        return await self.session.read(timeout_ms=1000, max_bytes=8192)

    async def test_pattern(self, test: PatternTest) -> dict:
        """Test a specific pattern.

        Args:
            test: PatternTest definition

        Returns:
            Test result dict
        """
        print(f"\n{'=' * 80}")
        print(f"Testing: {test.pattern_id}")
        print(f"{'=' * 80}")
        print(f"Notes: {test.notes}")
        print()

        result = {
            "pattern_id": test.pattern_id,
            "expected": test.expected_detection,
            "detected": False,
            "detection_data": None,
            "success": False,
            "notes": test.notes,
            "screens": [],
        }

        try:
            # Reconnect for clean slate
            if self.session_id:
                await self.session_manager.close_all_sessions()

            await self.connect()

            # Execute trigger sequence
            for i, (keys, desc) in enumerate(test.trigger_sequence, 1):
                print(f"[{i}/{len(test.trigger_sequence)}] {desc}")
                await self.session.send(keys)
                snapshot = await self.read_with_wait(1.5)

                # Save screen
                result["screens"].append(
                    {
                        "step": desc,
                        "screen": snapshot.get("screen", ""),
                        "prompt_detected": snapshot.get("prompt_detected"),
                    }
                )

                # Check if target pattern detected
                if "prompt_detected" in snapshot:
                    detected = snapshot["prompt_detected"]
                    detected_id = detected["prompt_id"]

                    print(f"  → Detected: {detected_id}")

                    if detected_id == test.pattern_id:
                        result["detected"] = True
                        result["detection_data"] = detected
                        result["success"] = True
                        self.pattern_coverage.add(test.pattern_id)
                        print("  ✓ MATCHED TARGET PATTERN!")
                        break

            # Final check if not detected in sequence
            if not result["detected"]:
                # Read final screen
                snapshot = await self.read_with_wait(1.0)

                if "prompt_detected" in snapshot:
                    detected = snapshot["prompt_detected"]
                    detected_id = detected["prompt_id"]

                    print(f"Final check - Detected: {detected_id}")

                    if detected_id == test.pattern_id:
                        result["detected"] = True
                        result["detection_data"] = detected
                        result["success"] = True
                        self.pattern_coverage.add(test.pattern_id)
                    else:
                        print(f"  ✗ Expected {test.pattern_id}, got {detected_id}")
                else:
                    print("  ⚠️  No prompt detected")

            # Evaluate success
            if test.expected_detection:
                if result["detected"]:
                    print("\n✓ SUCCESS: Pattern detected as expected")
                else:
                    print("\n✗ FAILED: Pattern not detected")
            else:
                if not result["detected"]:
                    print("\n✓ SUCCESS: Pattern correctly not detected (as expected)")
                    result["success"] = True
                else:
                    print("\n⚠️  UNEXPECTED: Pattern detected when not expected")

        except Exception as e:
            print(f"\n❌ ERROR: {e}")
            result["error"] = str(e)
            import traceback

            traceback.print_exc()

        self.test_results.append(result)
        return result

    async def run_all_tests(self):
        """Run all pattern tests."""
        print("\n" + "=" * 80)
        print("RUNNING ALL PATTERN TESTS")
        print("=" * 80 + "\n")

        for i, test in enumerate(self.PATTERN_TESTS, 1):
            print(f"\n{'#' * 80}")
            print(f"# TEST {i}/{len(self.PATTERN_TESTS)}")
            print(f"{'#' * 80}")

            await self.test_pattern(test)
            await asyncio.sleep(1.0)

    def generate_report(self):
        """Generate test report."""
        print("\n" + "=" * 80)
        print("PATTERN VALIDATION REPORT")
        print("=" * 80)

        # Summary
        total = len(self.test_results)
        passed = sum(1 for r in self.test_results if r["success"])
        detected = sum(1 for r in self.test_results if r["detected"])

        print("\n📊 Summary:")
        print(f"  Total tests: {total}")
        print(f"  Passed: {passed}/{total} ({passed / total * 100:.1f}%)")
        print(f"  Patterns detected: {detected}")
        print(f"  Coverage: {len(self.pattern_coverage)}/13 patterns")

        # Coverage
        print("\n✓ Patterns Detected:")
        for pattern_id in sorted(self.pattern_coverage):
            print(f"  - {pattern_id}")

        # Missing
        all_patterns = {
            "login_username",
            "login_password",
            "press_any_key",
            "main_menu",
            "yes_no_prompt",
            "more_prompt",
            "quit_confirm",
            "enter_number",
            "sector_command",
            "planet_command",
            "twgs_select_game",
            "twgs_main_menu",
            "command_prompt_generic",
        }
        missing = all_patterns - self.pattern_coverage

        if missing:
            print("\n⚠️  Patterns NOT Detected:")
            for pattern_id in sorted(missing):
                print(f"  - {pattern_id}")

        # Failures
        failures = [r for r in self.test_results if not r["success"]]
        if failures:
            print(f"\n✗ Failed Tests ({len(failures)}):")
            for r in failures:
                print(f"  - {r['pattern_id']}: {r.get('error', 'Not detected')}")

    async def save_results(self):
        """Save validation results."""
        timestamp = int(time.time())
        results_file = Path(".provide") / "pattern-validation-results.json"
        report_file = Path(".provide") / "pattern-validation-results.md"

        results_file.parent.mkdir(exist_ok=True)

        # JSON results
        data = {
            "timestamp": timestamp,
            "total_tests": len(self.test_results),
            "passed": sum(1 for r in self.test_results if r["success"]),
            "coverage": list(self.pattern_coverage),
            "test_results": self.test_results,
        }

        with open(results_file, "w") as f:
            json.dump(data, f, indent=2)

        # Markdown report
        with open(report_file, "w") as f:
            f.write("# Pattern Validation Results\n\n")
            f.write(f"**Date**: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write("## Summary\n\n")
            total = len(self.test_results)
            passed = sum(1 for r in self.test_results if r["success"])
            f.write(f"- **Total tests**: {total}\n")
            f.write(f"- **Passed**: {passed}/{total} ({passed / total * 100:.1f}%)\n")
            f.write(f"- **Coverage**: {len(self.pattern_coverage)}/13 patterns\n\n")

            f.write("## Patterns Detected\n\n")
            for pattern_id in sorted(self.pattern_coverage):
                f.write(f"- ✓ `{pattern_id}`\n")

            # Missing
            all_patterns = {
                "login_username",
                "login_password",
                "press_any_key",
                "main_menu",
                "yes_no_prompt",
                "more_prompt",
                "quit_confirm",
                "enter_number",
                "sector_command",
                "planet_command",
                "twgs_select_game",
                "twgs_main_menu",
                "command_prompt_generic",
            }
            missing = all_patterns - self.pattern_coverage

            if missing:
                f.write("\n## Patterns NOT Detected\n\n")
                for pattern_id in sorted(missing):
                    f.write(f"- ⚠️  `{pattern_id}`\n")

            f.write("\n## Test Details\n\n")
            for r in self.test_results:
                icon = "✓" if r["success"] else "✗"
                f.write(f"### {icon} {r['pattern_id']}\n\n")
                f.write(f"- **Expected detection**: {r['expected']}\n")
                f.write(f"- **Detected**: {r['detected']}\n")
                f.write(f"- **Success**: {r['success']}\n")
                f.write(f"- **Notes**: {r['notes']}\n")

                if r["detection_data"]:
                    f.write("- **Detection data**:\n")
                    f.write(f"  - Input type: `{r['detection_data']['input_type']}`\n")
                    f.write(f"  - Matched text: `{r['detection_data'].get('matched_text', 'N/A')}`\n")

                if r.get("error"):
                    f.write(f"- **Error**: {r['error']}\n")

                f.write("\n")

        print("\n📄 Results saved:")
        print(f"  - JSON: {results_file}")
        print(f"  - Markdown: {report_file}")

    async def run(self):
        """Run complete validation."""
        try:
            await self.run_all_tests()
            self.generate_report()
            await self.save_results()

        except KeyboardInterrupt:
            print("\n\n⚠️  Interrupted")
            self.generate_report()
        except Exception as e:
            print(f"\n\n❌ Error: {e}")
            import traceback

            traceback.print_exc()
        finally:
            print("\nCleaning up...")
            await self.session_manager.close_all_sessions()
            print("✓ Done.\n")


async def main():

    validator = PatternValidator()
    await validator.run()


if __name__ == "__main__":
    asyncio.run(main())
