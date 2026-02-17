# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any

import pytest

from bbsbot.games.tw2002.debug_screens import analyze_screen
from bbsbot.learning.detector import PromptDetectionDiagnostics, PromptMatch


@dataclass
class _FakeDetector:
    diagnostics: PromptDetectionDiagnostics
    compiled: list[tuple[re.Pattern[str], dict[str, Any]]]
    use_compiled_all: bool = True

    def __post_init__(self) -> None:
        if self.use_compiled_all:
            self._compiled_all = self.compiled
        else:
            self._compiled = self.compiled

    def detect_prompt_with_diagnostics(self, snapshot: dict[str, Any]) -> PromptDetectionDiagnostics:
        return self.diagnostics


@pytest.mark.asyncio
async def test_analyze_screen_reports_partial_matches() -> None:
    prompt = PromptMatch(
        prompt_id="prompt.command",
        pattern={"id": "prompt.command", "regex": r"Command.*\?"},
        input_type="line",
        eol_pattern=r"[\r\n]+",
        kv_extract=None,
    )
    diagnostics = PromptDetectionDiagnostics(
        match=prompt,
        regex_matched_but_failed=[{"pattern_id": "prompt.pause", "reason": "negative_match"}],
    )
    detector = _FakeDetector(
        diagnostics=diagnostics,
        compiled=[(re.compile(r"Command.*\?"), {"id": "prompt.command"})],
    )

    snapshot = {
        "screen": "Command [?=Help]?",
        "screen_hash": "hash-1",
        "cursor_at_end": True,
        "has_trailing_space": False,
    }
    bot = SimpleNamespace(
        session=SimpleNamespace(
            emulator=SimpleNamespace(get_snapshot=lambda: snapshot),
            learning=SimpleNamespace(_prompt_detector=detector),
        )
    )

    analysis = await analyze_screen(bot)

    assert analysis.prompt_id == "prompt.command"
    assert analysis.all_patterns_checked == ["prompt.command"]
    assert analysis.patterns_partially_matched == [{"pattern_id": "prompt.pause", "reason": "negative_match"}]


@pytest.mark.asyncio
async def test_analyze_screen_supports_legacy_compiled_attr() -> None:
    diagnostics = PromptDetectionDiagnostics(match=None, regex_matched_but_failed=[])
    detector = _FakeDetector(
        diagnostics=diagnostics,
        compiled=[(re.compile(r"Test"), {"id": "prompt.test"})],
        use_compiled_all=False,
    )

    snapshot = {
        "screen": "No prompt",
        "screen_hash": "hash-2",
        "cursor_at_end": True,
        "has_trailing_space": False,
    }
    bot = SimpleNamespace(
        session=SimpleNamespace(
            emulator=SimpleNamespace(get_snapshot=lambda: snapshot),
            learning=SimpleNamespace(_prompt_detector=detector),
        )
    )

    analysis = await analyze_screen(bot)

    assert analysis.prompt_id is None
    assert analysis.all_patterns_checked == ["prompt.test"]
