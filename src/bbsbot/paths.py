# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Filesystem paths and knowledge-root helpers."""

from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_dir

ENV_KNOWLEDGE_ROOT = "BBSBOT_KNOWLEDGE_ROOT"


def default_knowledge_root() -> Path:
    """Get the default knowledge root directory."""
    env_root = os.getenv(ENV_KNOWLEDGE_ROOT)
    if env_root:
        return Path(env_root)
    return Path(user_data_dir("bbsbot", "bbsbot"))


def validate_knowledge_root(knowledge_root: Path) -> Path:
    """Validate and create knowledge root directory structure."""
    knowledge_root.mkdir(parents=True, exist_ok=True)

    shared_dir = knowledge_root / "shared"
    shared_dir.mkdir(exist_ok=True)

    bbs_dir = shared_dir / "bbs"
    bbs_dir.mkdir(exist_ok=True)

    return knowledge_root


def find_repo_games_root(start: Path | None = None) -> Path | None:
    """Locate a repo-local games directory (optional override for knowledge files).

    Search order:
    1. Walk up from *start* (or cwd) looking for .git + games/
    2. Walk up from the bbsbot package source directory
    """
    base = (start or Path.cwd()).resolve()
    for candidate in (base, *base.parents):
        if (candidate / ".git").exists():
            games_dir = candidate / "games"
            if games_dir.exists():
                return games_dir
            break  # Found .git but no games/ — continue to fallback

    # Fallback: check relative to the bbsbot package source directory.
    # This handles running from a different repo (e.g. a game server project
    # that uses bbsbot as a dependency installed in editable mode).
    pkg_dir = Path(__file__).resolve().parent  # .../bbsbot/src/bbsbot/
    for candidate in (pkg_dir, *pkg_dir.parents):
        if (candidate / ".git").exists():
            games_dir = candidate / "games"
            if games_dir.exists():
                return games_dir
            break
    return None
