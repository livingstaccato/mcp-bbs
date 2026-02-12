#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Test screen saving functionality."""

import tempfile
import time
from pathlib import Path

from bbsbot.learning.screen_saver import ScreenSaver


def test_screen_saving():
    """Test that screens are saved to disk correctly."""
    print("Testing screen saving...")

    with tempfile.TemporaryDirectory() as tmpdir:
        base_dir = Path(tmpdir)
        saver = ScreenSaver(base_dir=base_dir, namespace="test_game", enabled=True)

        # Create test snapshot
        snapshot = {
            "screen": "Welcome to Test BBS!\n\nEnter your name: ",
            "screen_hash": "abc123def456",
            "captured_at": time.time(),
            "cursor": {"x": 18, "y": 2},
            "cols": 80,
            "rows": 25,
            "term": "ANSI",
            "cursor_at_end": True,
            "has_trailing_space": True,
        }

        # Save screen
        saved_path = saver.save_screen(snapshot, prompt_id="login_prompt")

        assert saved_path is not None, "Screen should be saved"
        assert saved_path.exists(), "Screen file should exist"
        assert "login_prompt" in saved_path.name, "Filename should include prompt ID"

        # Read and verify content
        content = saved_path.read_text()
        assert "Welcome to Test BBS!" in content
        assert "SCREEN CAPTURE" in content
        assert "Hash: abc123def456" in content
        assert "Prompt ID: login_prompt" in content

        print(f"✓ Screen saved to: {saved_path}")

        # Try saving same screen again (should be skipped)
        saved_path2 = saver.save_screen(snapshot, prompt_id="login_prompt")
        assert saved_path2 is None, "Duplicate screen should not be saved"

        print("✓ Duplicate detection working")

        # Force save
        saved_path3 = saver.save_screen(snapshot, prompt_id="login_prompt", force=True)
        assert saved_path3 is not None, "Forced save should work"

        print("✓ Force save working")

        # Check screens directory structure
        screens_dir = saver.get_screens_dir()
        assert screens_dir == base_dir / "games" / "test_game" / "screens"
        assert screens_dir.exists()

        print(f"✓ Screens directory: {screens_dir}")

        # Check saved count
        assert saver.get_saved_count() == 1  # Only one unique hash
        print(f"✓ Saved count: {saver.get_saved_count()}")

    print("\n" + "=" * 60)
    print("Screen saving tests passed! ✓")
    print("=" * 60)


if __name__ == "__main__":
    test_screen_saving()
