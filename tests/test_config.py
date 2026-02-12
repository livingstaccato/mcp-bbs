# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for configuration paths."""

from __future__ import annotations

import os
from typing import TYPE_CHECKING
from unittest.mock import patch

from bbsbot.paths import ENV_KNOWLEDGE_ROOT, default_knowledge_root, validate_knowledge_root

if TYPE_CHECKING:
    from pathlib import Path


def test_env_var_override(tmp_path: Path) -> None:
    custom_path = tmp_path / "custom-knowledge"

    with patch.dict(os.environ, {ENV_KNOWLEDGE_ROOT: str(custom_path)}):
        result = default_knowledge_root()

    assert result == custom_path


def test_default_uses_platformdirs(tmp_path: Path) -> None:
    with patch.dict(os.environ, {}, clear=True):
        with patch("bbsbot.paths.user_data_dir", return_value=str(tmp_path / "xdg-data")):
            result = default_knowledge_root()

    assert result == tmp_path / "xdg-data"


def test_validate_knowledge_root_creates_structure(tmp_path: Path) -> None:
    knowledge_root = tmp_path / "new-knowledge"

    assert not knowledge_root.exists()

    result = validate_knowledge_root(knowledge_root)

    assert result == knowledge_root
    assert knowledge_root.exists()
    assert (knowledge_root / "shared").exists()
    assert (knowledge_root / "shared" / "bbs").exists()
