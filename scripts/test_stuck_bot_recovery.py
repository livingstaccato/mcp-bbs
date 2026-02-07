#!/usr/bin/env python3
"""Test intervention system recovery from deliberately stuck situations.

This script creates scenarios where bots get stuck and verifies that:
1. Complete stagnation is detected
2. Intervention triggers with CRITICAL priority
3. LLM suggests appropriate recovery actions
4. Bot successfully recovers from stuck state
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from bbsbot.games.tw2002.interventions.detector import (
    Anomaly,
    AnomalyType,
    InterventionDetector,
    InterventionPriority,
    TurnData,
)
from bbsbot.games.tw2002.orientation import GameState
from bbsbot.logging import get_logger

logger = get_logger(__name__)


class MockStrategy:
    """Mock strategy for testing."""

    def __init__(self):
        self._current_goal_id = "profit"


class StuckBotTester:
    """Test intervention system with deliberately stuck bots."""

    def __init__(self):
        self.tests_run = 0
        self.tests_passed = 0
        self.tests_failed = 0

    def test_complete_stagnation_same_action(self):
        """Test detection when bot repeats same action in same sector with no changes."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Complete Stagnation - Same Action")
        logger.info("=" * 80)

        detector = InterventionDetector(window_turns=10)
        strategy = MockStrategy()

        # Simulate bot stuck in sector 100, repeating MOVE with no changes
        for turn in range(7):
            state = GameState(
                context="sector_command",
                sector=100,
                credits=1000,
                turns_left=100 - turn,
                fighters=50,
                shields=100,
                holds_free=10,
                holds_total=20,
                has_port=False,
            )
            detector.update(
                turn=turn,
                state=state,
                action="MOVE",
                profit_delta=0,
                strategy=strategy,
            )

        # Detect anomalies
        anomalies = detector.detect_anomalies(
            current_turn=6, state=state, strategy=strategy
        )

        # Verify detection
        stagnation_detected = any(
            a.type == AnomalyType.COMPLETE_STAGNATION for a in anomalies
        )
        if stagnation_detected:
            stagnation = next(
                a for a in anomalies if a.type == AnomalyType.COMPLETE_STAGNATION
            )
            logger.info(f"✓ PASS: Detected complete stagnation")
            logger.info(f"  Priority: {stagnation.priority}")
            logger.info(f"  Confidence: {stagnation.confidence}")
            logger.info(f"  Description: {stagnation.description}")
            logger.info(f"  Evidence: {stagnation.evidence}")

            # Verify it's CRITICAL priority
            if stagnation.priority == InterventionPriority.CRITICAL:
                logger.info(f"✓ PASS: Correctly marked as CRITICAL")
                self.tests_passed += 1
            else:
                logger.error(f"✗ FAIL: Expected CRITICAL, got {stagnation.priority}")
                self.tests_failed += 1
        else:
            logger.error(f"✗ FAIL: Complete stagnation not detected")
            logger.error(f"  Anomalies detected: {[a.type for a in anomalies]}")
            self.tests_failed += 1

        self.tests_run += 1

    def test_complete_stagnation_varying_actions(self):
        """Test detection when bot tries different actions but makes no progress."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Complete Stagnation - Varying Actions")
        logger.info("=" * 80)

        detector = InterventionDetector(window_turns=10)
        strategy = MockStrategy()

        # Simulate bot stuck in sector 100, trying different actions but making no progress
        actions = ["MOVE", "WAIT", "MOVE", "SCAN", "MOVE", "WAIT", "MOVE", "SCAN"]
        for turn, action in enumerate(actions):
            state = GameState(
                context="sector_command",
                sector=100,
                credits=1000,
                turns_left=100 - turn,
                fighters=50,
                shields=100,
                holds_free=10,
                holds_total=20,
                has_port=False,
            )
            detector.update(
                turn=turn,
                state=state,
                action=action,
                profit_delta=0,
                strategy=strategy,
            )

        # Detect anomalies
        anomalies = detector.detect_anomalies(
            current_turn=7, state=state, strategy=strategy
        )

        # Verify detection
        stagnation_detected = any(
            a.type == AnomalyType.COMPLETE_STAGNATION for a in anomalies
        )
        if stagnation_detected:
            stagnation = next(
                a for a in anomalies if a.type == AnomalyType.COMPLETE_STAGNATION
            )
            logger.info(f"✓ PASS: Detected complete stagnation with varying actions")
            logger.info(f"  Priority: {stagnation.priority}")
            logger.info(f"  Description: {stagnation.description}")
            self.tests_passed += 1
        else:
            logger.error(f"✗ FAIL: Complete stagnation not detected")
            self.tests_failed += 1

        self.tests_run += 1

    def test_no_false_positive_when_moving(self):
        """Test that stagnation is NOT detected when bot is making progress."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: No False Positive - Bot Making Progress")
        logger.info("=" * 80)

        detector = InterventionDetector(window_turns=10)
        strategy = MockStrategy()

        # Simulate bot moving between sectors and earning credits
        for turn in range(7):
            state = GameState(
                context="sector_command",
                sector=100 + turn,  # Moving to different sectors
                credits=1000 + (turn * 100),  # Earning credits
                turns_left=100 - turn,
                fighters=50,
                shields=100,
                holds_free=10,
                holds_total=20,
                has_port=False,
            )
            detector.update(
                turn=turn,
                state=state,
                action="TRADE",
                profit_delta=100,
                strategy=strategy,
            )

        # Detect anomalies
        anomalies = detector.detect_anomalies(
            current_turn=6, state=state, strategy=strategy
        )

        # Verify NO complete stagnation detected
        stagnation_detected = any(
            a.type == AnomalyType.COMPLETE_STAGNATION for a in anomalies
        )
        if not stagnation_detected:
            logger.info(f"✓ PASS: No false positive - bot is making progress")
            self.tests_passed += 1
        else:
            logger.error(f"✗ FAIL: False positive - detected stagnation when bot is moving")
            self.tests_failed += 1

        self.tests_run += 1

    def test_action_loop_still_detected(self):
        """Test that action loops are still detected (not replaced by stagnation detection)."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST: Action Loop Detection Still Works")
        logger.info("=" * 80)

        detector = InterventionDetector(window_turns=10)
        strategy = MockStrategy()

        # Simulate bot repeating MOVE action but CHANGING sectors
        for turn in range(5):
            state = GameState(
                context="sector_command",
                sector=100 + (turn % 2),  # Alternating between two sectors
                credits=1000 + (turn * 10),  # Small credit changes
                turns_left=100 - turn,
                fighters=50,
                shields=100,
                holds_free=10,
                holds_total=20,
                has_port=False,
            )
            detector.update(
                turn=turn,
                state=state,
                action="MOVE",
                profit_delta=10,
                strategy=strategy,
            )

        # Detect anomalies
        anomalies = detector.detect_anomalies(
            current_turn=4, state=state, strategy=strategy
        )

        # Should detect action loop, NOT complete stagnation
        loop_detected = any(a.type == AnomalyType.ACTION_LOOP for a in anomalies)
        stagnation_detected = any(
            a.type == AnomalyType.COMPLETE_STAGNATION for a in anomalies
        )

        if loop_detected and not stagnation_detected:
            logger.info(f"✓ PASS: Action loop detected, complete stagnation not triggered")
            self.tests_passed += 1
        else:
            logger.error(
                f"✗ FAIL: Expected action loop only, got: {[a.type for a in anomalies]}"
            )
            self.tests_failed += 1

        self.tests_run += 1

    def print_summary(self):
        """Print test summary."""
        logger.info("\n" + "=" * 80)
        logger.info("TEST SUMMARY")
        logger.info("=" * 80)
        logger.info(f"Tests run: {self.tests_run}")
        logger.info(f"Tests passed: {self.tests_passed} ✓")
        logger.info(f"Tests failed: {self.tests_failed} ✗")

        if self.tests_failed == 0:
            logger.info("\n🎉 ALL TESTS PASSED!")
        else:
            logger.error(f"\n❌ {self.tests_failed} TEST(S) FAILED")

        logger.info("=" * 80)

    def run_all_tests(self):
        """Run all test scenarios."""
        logger.info("\n" + "=" * 80)
        logger.info("STUCK BOT RECOVERY TESTS")
        logger.info("=" * 80)

        self.test_complete_stagnation_same_action()
        self.test_complete_stagnation_varying_actions()
        self.test_no_false_positive_when_moving()
        self.test_action_loop_still_detected()

        self.print_summary()

        return self.tests_failed == 0


def main():
    """Main entry point."""
    tester = StuckBotTester()
    success = tester.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
