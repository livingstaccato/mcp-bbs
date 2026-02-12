# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pytest configuration and fixtures."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, Mock

import pyte
import pytest

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def bbs_host() -> str:
    """Default BBS host for testing."""
    return "127.0.0.1"


@pytest.fixture
def bbs_port() -> int:
    """Default BBS port for testing."""
    return 2002


@pytest.fixture
def mock_reader() -> Mock:
    """Mock asyncio StreamReader."""
    reader = AsyncMock()
    reader.read = AsyncMock(return_value=b"")
    return reader


@pytest.fixture
def mock_writer() -> Mock:
    """Mock asyncio StreamWriter."""
    writer = AsyncMock()
    writer.write = Mock()
    writer.drain = AsyncMock()
    writer.close = Mock()
    writer.wait_closed = AsyncMock()
    writer.is_closing = Mock(return_value=False)
    return writer


@pytest.fixture
def mock_screen() -> pyte.Screen:
    """Mock pyte Screen."""
    return pyte.Screen(80, 25)


@pytest.fixture
def mock_stream(mock_screen: pyte.Screen) -> pyte.Stream:
    """Mock pyte Stream."""
    return pyte.Stream(mock_screen)


@pytest.fixture
def tmp_knowledge_root(tmp_path: Path) -> Path:
    """Temporary knowledge root directory."""
    knowledge = tmp_path / "test-knowledge"
    knowledge.mkdir()
    (knowledge / "shared" / "bbs").mkdir(parents=True)
    return knowledge
