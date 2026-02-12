#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Test script to verify TW2002 debugging implementation.

Tests:
1. Health check command works
2. Config generation works
3. Bot registration works
4. AI strategy feedback configuration loads
"""

import subprocess
import sys


def test_health_check():
    """Test health check command exists and runs."""
    print("\n[Test 1] Health check command...")
    try:
        result = subprocess.run(
            ["bbsbot", "tw2002", "check", "--help"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and "health" in result.stdout.lower():
            print("  ✓ Health check command exists")
            return True
        else:
            print(f"  ✗ Health check command failed: {result.stderr}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_config_generation():
    """Test config generation works."""
    print("\n[Test 2] Config generation...")
    try:
        result = subprocess.run(
            ["bbsbot", "tw2002", "bot", "--generate-config"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0 and "feedback_enabled" in result.stdout:
            print("  ✓ Config generation includes feedback settings")
            return True
        else:
            print("  ✗ Config generation failed or missing feedback settings")
            print(f"  Output preview: {result.stdout[:200]}")
            return False
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_bot_registration():
    """Test SessionManager has bot registration methods."""
    print("\n[Test 3] Bot registration methods...")
    try:
        from bbsbot.core.session_manager import SessionManager

        manager = SessionManager()

        # Check methods exist
        if not hasattr(manager, "register_bot"):
            print("  ✗ Missing register_bot method")
            return False
        if not hasattr(manager, "get_bot"):
            print("  ✗ Missing get_bot method")
            return False
        if not hasattr(manager, "unregister_bot"):
            print("  ✗ Missing unregister_bot method")
            return False

        print("  ✓ All bot registration methods present")
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_ai_strategy_config():
    """Test AI strategy has feedback configuration."""
    print("\n[Test 4] AI strategy feedback configuration...")
    try:
        from bbsbot.games.tw2002.config import AIStrategyConfig

        config = AIStrategyConfig()

        # Check feedback fields exist
        if not hasattr(config, "feedback_enabled"):
            print("  ✗ Missing feedback_enabled")
            return False
        if not hasattr(config, "feedback_interval_turns"):
            print("  ✗ Missing feedback_interval_turns")
            return False
        if not hasattr(config, "feedback_lookback_turns"):
            print("  ✗ Missing feedback_lookback_turns")
            return False
        if not hasattr(config, "feedback_max_tokens"):
            print("  ✗ Missing feedback_max_tokens")
            return False

        print("  ✓ Feedback configuration present")
        print(f"    - feedback_enabled: {config.feedback_enabled}")
        print(f"    - feedback_interval_turns: {config.feedback_interval_turns}")
        print(f"    - feedback_lookback_turns: {config.feedback_lookback_turns}")
        print(f"    - feedback_max_tokens: {config.feedback_max_tokens}")
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False


def test_ai_strategy_methods():
    """Test AI strategy has feedback loop methods."""
    print("\n[Test 5] AI strategy feedback methods...")
    try:
        from pathlib import Path

        from bbsbot.games.tw2002.config import BotConfig
        from bbsbot.games.tw2002.orientation import SectorKnowledge
        from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy

        # Create minimal instances
        config = BotConfig()
        knowledge = SectorKnowledge(
            knowledge_dir=Path("/tmp/test_knowledge"),
            character_name="test",
        )
        strategy = AIStrategy(config, knowledge)

        # Check methods exist
        if not hasattr(strategy, "set_session_logger"):
            print("  ✗ Missing set_session_logger method")
            return False
        if not hasattr(strategy, "_periodic_feedback"):
            print("  ✗ Missing _periodic_feedback method")
            return False
        if not hasattr(strategy, "_build_feedback_prompt"):
            print("  ✗ Missing _build_feedback_prompt method")
            return False
        if not hasattr(strategy, "_log_feedback"):
            print("  ✗ Missing _log_feedback method")
            return False
        if not hasattr(strategy, "_recent_events"):
            print("  ✗ Missing _recent_events buffer")
            return False

        print("  ✓ All feedback methods present")
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        import traceback

        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("TW2002 DEBUGGING IMPLEMENTATION TESTS")
    print("=" * 60)

    tests = [
        test_health_check,
        test_config_generation,
        test_bot_registration,
        test_ai_strategy_config,
        test_ai_strategy_methods,
    ]

    results = []
    for test in tests:
        try:
            results.append(test())
        except Exception as e:
            print(f"\n  ✗ Test crashed: {e}")
            results.append(False)

    print("\n" + "=" * 60)
    print(f"RESULTS: {sum(results)}/{len(results)} tests passed")
    print("=" * 60)

    if all(results):
        print("\n✓ All tests passed!")
        return 0
    else:
        print("\n✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
