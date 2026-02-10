#!/usr/bin/env python3
"""Quick integration test for prompt detection system."""

import time

from bbsbot.learning.buffer import BufferManager
from bbsbot.learning.detector import PromptDetector
from bbsbot.learning.extractor import extract_kv
from bbsbot.terminal.emulator import TerminalEmulator


def test_timing_metadata():
    """Test that snapshots include timing metadata."""
    print("Testing timing metadata...")
    emulator = TerminalEmulator(80, 25, "ANSI")
    emulator.process(b"Test screen content")

    snapshot = emulator.get_snapshot()

    assert "captured_at" in snapshot, "Missing captured_at"
    assert "cursor_at_end" in snapshot, "Missing cursor_at_end"
    assert "has_trailing_space" in snapshot, "Missing has_trailing_space"
    assert isinstance(snapshot["captured_at"], float), "captured_at not float"
    assert isinstance(snapshot["cursor_at_end"], bool), "cursor_at_end not bool"

    print("✓ Timing metadata working")


def test_buffer_manager():
    """Test BufferManager screen buffering and idle detection."""
    print("\nTesting BufferManager...")
    buffer_mgr = BufferManager(max_size=10)

    # Create test snapshots
    snapshot1 = {
        "screen": "Screen 1",
        "screen_hash": "hash1",
        "captured_at": time.time(),
    }
    snapshot2 = {
        "screen": "Screen 2",
        "screen_hash": "hash2",
        "captured_at": time.time() + 0.5,
    }
    snapshot3 = {
        "screen": "Screen 2",
        "screen_hash": "hash2",
        "captured_at": time.time() + 3.0,
    }

    # Add screens
    buffer1 = buffer_mgr.add_screen(snapshot1)
    assert buffer1.screen == "Screen 1"
    assert buffer1.time_since_last_change == 0.0

    time.sleep(0.1)
    buffer2 = buffer_mgr.add_screen(snapshot2)
    assert buffer2.screen == "Screen 2"
    assert buffer2.time_since_last_change > 0

    # Test idle detection (screen unchanged for 2+ seconds)
    buffer3 = buffer_mgr.add_screen(snapshot3)
    is_idle = buffer_mgr.detect_idle_state(threshold_seconds=2.0)
    assert is_idle, "Should detect idle state after 3 seconds"

    # Test get_recent
    recent = buffer_mgr.get_recent(n=2)
    assert len(recent) == 2

    print("✓ BufferManager working")


def test_prompt_detector():
    """Test PromptDetector with cursor-aware matching."""
    print("\nTesting PromptDetector...")

    patterns = [
        {
            "id": "test_prompt",
            "regex": r"Enter your name:\s*$",
            "input_type": "multi_key",
            "expect_cursor_at_end": True,
        },
        {
            "id": "press_key",
            "regex": r"Press any key",
            "input_type": "any_key",
            "expect_cursor_at_end": False,
        },
    ]

    detector = PromptDetector(patterns)

    # Test matching prompt
    snapshot = {
        "screen": "Welcome!\n\nEnter your name: ",
        "cursor_at_end": True,
        "has_trailing_space": True,
    }

    match = detector.detect_prompt(snapshot)
    assert match is not None, "Should match prompt"
    assert match.prompt_id == "test_prompt"
    assert match.input_type == "multi_key"

    # Test non-matching (cursor not at end)
    snapshot2 = {
        "screen": "Enter your name: ",
        "cursor_at_end": False,
        "has_trailing_space": True,
    }

    match2 = detector.detect_prompt(snapshot2)
    assert match2 is None, "Should not match when cursor not at end"

    # Test auto-detection
    input_type = detector.auto_detect_input_type("Press any key to continue")
    assert input_type == "any_key"

    input_type2 = detector.auto_detect_input_type("Enter your password:")
    assert input_type2 == "multi_key"

    print("✓ PromptDetector working")


def test_kv_extractor():
    """Test K/V data extraction."""
    print("\nTesting KV Extractor...")

    screen = """
    Player Name: TestUser123
    Credits: 50000
    Turns: 100
    """

    # Test single field extraction
    config = {
        "field": "player_name",
        "type": "string",
        "regex": r"Player Name:\s*(\w+)",
    }

    result = extract_kv(screen, config)
    assert result is not None
    assert result["player_name"] == "TestUser123"

    # Test multi-field extraction
    multi_config = [
        {"field": "player_name", "type": "string", "regex": r"Player Name:\s*(\w+)"},
        {"field": "credits", "type": "int", "regex": r"Credits:\s*(\d+)"},
        {"field": "turns", "type": "int", "regex": r"Turns:\s*(\d+)"},
    ]

    result2 = extract_kv(screen, multi_config)
    assert result2 is not None
    assert result2["player_name"] == "TestUser123"
    assert result2["credits"] == 50000
    assert result2["turns"] == 100

    print("✓ KV Extractor working")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Prompt Detection Integration Tests")
    print("=" * 60)

    test_timing_metadata()
    test_buffer_manager()
    test_prompt_detector()
    test_kv_extractor()

    print("\n" + "=" * 60)
    print("All tests passed! ✓")
    print("=" * 60)


if __name__ == "__main__":
    main()
