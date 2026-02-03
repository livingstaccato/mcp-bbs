"""Extended tests for auto-learning edge cases."""

from __future__ import annotations

from pathlib import Path

from mcp_bbs.learn import append_md, apply_auto_discover, apply_auto_learn


def test_apply_auto_learn_no_matches(tmp_knowledge_root: Path) -> None:
    """Test auto-learning with no pattern matches."""
    screen = "Random text without patterns"
    screen_hash = "test123"
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

    # Should not create catalog since no matches
    apply_auto_learn(screen, screen_hash, base_dir, rules, [], seen)

    catalog = base_dir / "prompt-catalog.md"
    # Either doesn't exist or is empty
    if catalog.exists():
        content = catalog.read_text()
        assert "username" not in content or content.strip() == ""


def test_apply_auto_learn_menu_rules(tmp_knowledge_root: Path) -> None:
    """Test auto-learning with menu rules."""
    screen = "[M] Main Menu\n[Q] Quit"
    screen_hash = "menu123"
    base_dir = tmp_knowledge_root / "shared" / "bbs"
    base_dir.mkdir(parents=True, exist_ok=True)

    menu_rules = [{"menu_id": "main", "regex": r"\[M\] Main Menu"}]
    seen: set[tuple[str, str]] = set()

    apply_auto_learn(screen, screen_hash, base_dir, [], menu_rules, seen)

    menu_map = base_dir / "menu-map.md"
    assert menu_map.exists()
    content = menu_map.read_text()
    assert "main" in content


def test_apply_auto_learn_already_seen(tmp_knowledge_root: Path) -> None:
    """Test that already-seen prompts are not logged again."""
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
    seen: set[tuple[str, str]] = {("prompt", "username:abc123")}

    # Should not add since already seen
    apply_auto_learn(screen, screen_hash, base_dir, rules, [], seen)

    # Seen set should not grow
    assert len(seen) == 1


def test_apply_auto_discover_no_options(tmp_knowledge_root: Path) -> None:
    """Test auto-discovery with screen that has no menu options."""
    screen = "Just plain text without menu options"
    screen_hash = "plain123"
    base_dir = tmp_knowledge_root / "shared" / "bbs"
    base_dir.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, str]] = set()

    # Should handle gracefully
    apply_auto_discover(screen, screen_hash, base_dir, seen)

    # May or may not create file depending on implementation
    menu_map = base_dir / "menu-map.md"
    if menu_map.exists():
        content = menu_map.read_text()
        # Should not have actual menu content
        assert "[A]" not in content and "[M]" not in content


def test_apply_auto_discover_already_seen(tmp_knowledge_root: Path) -> None:
    """Test that already-seen menus are not logged again."""
    screen = "[A] Option A\n[B] Option B"
    screen_hash = "menu789"
    base_dir = tmp_knowledge_root / "shared" / "bbs"
    base_dir.mkdir(parents=True, exist_ok=True)
    seen: set[tuple[str, str]] = {("menu", f"auto:{screen_hash}")}

    # Should not add since already seen
    apply_auto_discover(screen, screen_hash, base_dir, seen)

    # Seen set should not grow
    assert len(seen) == 1


def test_append_md_creates_directory(tmp_path: Path) -> None:
    """Test that append_md creates parent directories."""
    nested_file = tmp_path / "deeply" / "nested" / "test.md"

    result = append_md(nested_file, "Header", "Body")

    assert result == "ok"
    assert nested_file.exists()
    assert nested_file.parent.exists()


def test_append_md_empty_content(tmp_path: Path) -> None:
    """Test append_md with empty content."""
    file = tmp_path / "empty.md"

    result = append_md(file, "Header", "")

    assert result == "ok"
    content = file.read_text()
    assert "# Header" in content
