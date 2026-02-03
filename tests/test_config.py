"""Tests for configuration module."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from mcp_bbs.config import get_default_knowledge_root, validate_knowledge_root


def test_env_var_override(tmp_path: Path) -> None:
    """Test that BBS_KNOWLEDGE_ROOT environment variable takes priority."""
    custom_path = tmp_path / "custom-knowledge"

    with patch.dict(os.environ, {"BBS_KNOWLEDGE_ROOT": str(custom_path)}):
        result = get_default_knowledge_root()

    assert result == custom_path


def test_xdg_default_with_platformdirs(tmp_path: Path) -> None:
    """Test that XDG path is used when platformdirs is available."""
    # Clear any environment override
    with patch.dict(os.environ, {}, clear=True):
        # Mock platformdirs to return our test path
        with patch("mcp_bbs.config.PLATFORMDIRS_AVAILABLE", True):
            with patch("mcp_bbs.config.user_data_dir", return_value=str(tmp_path / "xdg-data")):
                result = get_default_knowledge_root()

    assert result == tmp_path / "xdg-data"


def test_fallback_without_platformdirs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test fallback to .bbs-knowledge when platformdirs is unavailable."""
    # Change to tmp directory
    monkeypatch.chdir(tmp_path)

    # Clear any environment override
    with patch.dict(os.environ, {}, clear=True):
        # Mock platformdirs as unavailable
        with patch("mcp_bbs.config.PLATFORMDIRS_AVAILABLE", False):
            with pytest.warns(UserWarning, match="platformdirs not available"):
                result = get_default_knowledge_root()

    assert result == tmp_path / ".bbs-knowledge"


def test_validate_knowledge_root_creates_structure(tmp_path: Path) -> None:
    """Test that validate_knowledge_root creates required directory structure."""
    knowledge_root = tmp_path / "new-knowledge"

    # Ensure it doesn't exist yet
    assert not knowledge_root.exists()

    # Validate should create the structure
    result = validate_knowledge_root(knowledge_root)

    # Check that directories were created
    assert result == knowledge_root
    assert knowledge_root.exists()
    assert knowledge_root.is_dir()
    assert (knowledge_root / "shared").exists()
    assert (knowledge_root / "shared").is_dir()
    assert (knowledge_root / "shared" / "bbs").exists()
    assert (knowledge_root / "shared" / "bbs").is_dir()


def test_validate_knowledge_root_idempotent(tmp_path: Path) -> None:
    """Test that validate_knowledge_root is idempotent (safe to call multiple times)."""
    knowledge_root = tmp_path / "existing-knowledge"

    # Create the structure manually first
    knowledge_root.mkdir()
    (knowledge_root / "shared" / "bbs").mkdir(parents=True)

    # Validate should succeed without errors
    result = validate_knowledge_root(knowledge_root)

    assert result == knowledge_root
    assert knowledge_root.exists()
    assert (knowledge_root / "shared" / "bbs").exists()


def test_env_var_priority_over_xdg(tmp_path: Path) -> None:
    """Test that environment variable takes priority over XDG defaults."""
    custom_path = tmp_path / "env-override"
    xdg_path = tmp_path / "xdg-default"

    with patch.dict(os.environ, {"BBS_KNOWLEDGE_ROOT": str(custom_path)}):
        with patch("mcp_bbs.config.PLATFORMDIRS_AVAILABLE", True):
            with patch("mcp_bbs.config.user_data_dir", return_value=str(xdg_path)):
                result = get_default_knowledge_root()

    # Environment variable should win
    assert result == custom_path
    assert result != xdg_path
