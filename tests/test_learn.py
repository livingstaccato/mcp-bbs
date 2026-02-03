"""Tests for auto-learning functionality."""

from __future__ import annotations

from pathlib import Path

from mcp_bbs.learn import append_md, apply_auto_discover, apply_auto_learn


def test_append_md_creates_file(tmp_path: Path) -> None:
    """Test append_md creates file if it doesn't exist."""
    file = tmp_path / "test.md"
    result = append_md(file, "Test Header", "Test body content")

    assert result == "ok"
    assert file.exists()
    content = file.read_text()
    assert "# Test Header" in content
    assert "Test body content" in content


def test_append_md_appends_to_existing(tmp_path: Path) -> None:
    """Test append_md appends to existing file."""
    file = tmp_path / "test.md"
    file.write_text("# Existing\n\nOld content\n")

    result = append_md(file, "Test Header", "New content")

    assert result == "ok"
    content = file.read_text()
    assert "Old content" in content
    assert "New content" in content


def test_apply_auto_learn_prompt_rules(tmp_knowledge_root: Path) -> None:
    """Test auto-learning prompt rules."""
    screen = "Enter your username:"
    screen_hash = "abc123"
    base_dir = tmp_knowledge_root / "shared" / "bbs"
    base_dir.mkdir(parents=True, exist_ok=True)

    rules = [
        {
            "prompt_id": "username",
            "regex": r"Enter your username",
            "input_type": "text",
            "example_input": "player1",
        }
    ]
    seen: set[tuple[str, str]] = set()

    apply_auto_learn(screen, screen_hash, base_dir, rules, [], seen)

    catalog = base_dir / "prompt-catalog.md"
    assert catalog.exists()
    content = catalog.read_text()
    assert "username" in content
    assert "Enter your username" in content


def test_apply_auto_discover(tmp_knowledge_root: Path) -> None:
    """Test auto-discovery of menus."""
    screen = "[A] Option A\n[B] Option B"
    screen_hash = "xyz789"
    base_dir = tmp_knowledge_root / "shared" / "bbs"
    base_dir.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, str]] = set()

    apply_auto_discover(screen, screen_hash, base_dir, seen)

    menu_map = base_dir / "menu-map.md"
    assert menu_map.exists()
    content = menu_map.read_text()
    assert "Option A" in content or "auto:" in content
