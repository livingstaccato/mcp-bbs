"""Tests for path validation to prevent path injection attacks."""

from __future__ import annotations

from pathlib import Path

import pytest

from bbsbot.learning.knowledge import append_md, validate_knowledge_path


def test_validate_knowledge_path_valid(tmp_path: Path) -> None:
    """Test validation passes for paths within root."""
    root = tmp_path / "knowledge"
    root.mkdir()

    # Valid path within root
    valid_path = root / "shared" / "bbs" / "menu-map.md"
    result = validate_knowledge_path(valid_path, root)

    assert result.is_absolute()
    assert str(result).startswith(str(root.resolve()))


def test_validate_knowledge_path_traversal_rejected(tmp_path: Path) -> None:
    """Test that path traversal attempts are rejected."""
    root = tmp_path / "knowledge"
    root.mkdir()

    # Attempt to escape using ../
    malicious_path = root / ".." / ".." / "etc" / "passwd"

    with pytest.raises(ValueError, match="Path outside knowledge root"):
        validate_knowledge_path(malicious_path, root)


def test_validate_knowledge_path_absolute_outside_rejected(tmp_path: Path) -> None:
    """Test that absolute paths outside root are rejected."""
    root = tmp_path / "knowledge"
    root.mkdir()

    # Absolute path outside root
    malicious_path = Path("/etc/passwd")

    with pytest.raises(ValueError, match="Path outside knowledge root"):
        validate_knowledge_path(malicious_path, root)


def test_validate_knowledge_path_symlink_escape_rejected(tmp_path: Path) -> None:
    """Test that symlink escapes are rejected."""
    root = tmp_path / "knowledge"
    root.mkdir()

    # Create a symlink that points outside
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()

    symlink = root / "escape"
    symlink.symlink_to(outside_dir)

    # Attempt to access through symlink
    malicious_path = symlink / "file.txt"

    with pytest.raises(ValueError, match="Path outside knowledge root"):
        validate_knowledge_path(malicious_path, root)


def test_validate_knowledge_path_relative_within_root(tmp_path: Path) -> None:
    """Test that relative paths within root are allowed."""
    root = tmp_path / "knowledge"
    root.mkdir()
    (root / "shared").mkdir()

    # Relative path that stays within root
    valid_path = root / "shared" / ".." / "shared" / "file.txt"
    result = validate_knowledge_path(valid_path, root)

    # Should resolve to within root
    assert str(result.resolve()).startswith(str(root.resolve()))


@pytest.mark.asyncio
async def test_append_md_with_path_validation(tmp_path: Path) -> None:
    """Test that append_md validates paths."""
    root = tmp_path / "knowledge"
    root.mkdir()

    # Valid path
    valid_path = root / "shared" / "test.md"
    result = await append_md(valid_path, "Test", "Content", root)
    assert result == "ok"
    assert valid_path.exists()

    # Invalid path (outside root)
    malicious_path = root / ".." / ".." / "etc" / "passwd"

    with pytest.raises(ValueError, match="Path outside knowledge root"):
        await append_md(malicious_path, "Test", "Content", root)


@pytest.mark.asyncio
async def test_append_md_no_validation_when_no_root(tmp_path: Path) -> None:
    """Test that append_md works without validation if no root provided."""
    # This is for backward compatibility, but new code should always provide root
    test_file = tmp_path / "test.md"

    result = await append_md(test_file, "Test", "Content", root=None)
    assert result == "ok"
    assert test_file.exists()


def test_path_validation_edge_cases(tmp_path: Path) -> None:
    """Test edge cases in path validation."""
    root = tmp_path / "knowledge"
    root.mkdir()

    # Test 1: Path exactly equal to root
    result = validate_knowledge_path(root, root)
    assert result == root.resolve()

    # Test 2: Path with extra slashes
    path_with_slashes = root / "shared" / "." / "bbs"
    result = validate_knowledge_path(path_with_slashes, root)
    assert str(result.resolve()).startswith(str(root.resolve()))

    # Test 3: Attempting null byte injection
    try:
        malicious_path = root / "file\x00.txt"
        validate_knowledge_path(malicious_path, root)
    except (ValueError, OSError):
        # Should raise either ValueError from validation or OSError from filesystem
        pass
