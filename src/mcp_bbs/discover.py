from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

_OPTION_PATTERNS = [
    re.compile(r"^\s*<(?P<key>[A-Za-z0-9])>\s*(?P<label>.+?)\s*$"),
    re.compile(r"^\s*\[(?P<key>[A-Za-z0-9])\]\s*(?P<label>.+?)\s*$"),
    re.compile(r"^\s*(?P<key>[A-Za-z0-9])\)\s*(?P<label>.+?)\s*$"),
    re.compile(r"^\s*(?P<key>[A-Za-z0-9])\.\s*(?P<label>.+?)\s*$"),
    re.compile(r"^\s*(?P<key>[A-Za-z0-9])\s+-\s+(?P<label>.+?)\s*$"),
]


def _first_nonblank(lines: Iterable[str]) -> str:
    for line in lines:
        if line.strip():
            return line.strip()
    return ""


def _last_nonblank(lines: Iterable[str]) -> str:
    for line in reversed(list(lines)):
        if line.strip():
            return line.strip()
    return ""


def discover_menu(screen: str) -> dict[str, Any]:
    lines = screen.splitlines()
    title = _first_nonblank(lines)
    prompt = ""
    tail = _last_nonblank(lines)
    if ":" in tail or "?" in tail:
        prompt = tail

    options = []
    for idx, line in enumerate(lines):
        for pattern in _OPTION_PATTERNS:
            match = pattern.match(line)
            if match:
                options.append(
                    {
                        "key": match.group("key"),
                        "label": match.group("label").strip(),
                        "line": idx + 1,
                    }
                )
                break
    return {"title": title, "prompt": prompt, "options": options}
