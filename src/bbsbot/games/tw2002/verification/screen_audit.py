# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Offline screen coverage audit for TW2002 prompt detection.

This reads a `session.jsonl` log (produced by bbsbot session logging) and:
- re-runs prompt detection against each captured screen snapshot
- aggregates which prompt IDs were seen
- highlights unmatched screens for rules.json gap analysis

Usage:
  uv run python -m bbsbot.games.tw2002.verification.screen_audit \
    --log games/tw2002/session.jsonl \
    --rules games/tw2002/rules.json \
    --out SCREEN_AUDIT.md
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bbsbot.learning.detector import PromptDetector
from bbsbot.learning.rules import RuleSet


def _safe_text(s: str, limit: int) -> str:
    """ASCII-only, bounded text for markdown output."""
    s = (s or "").strip("\n")
    if len(s) > limit:
        s = s[:limit] + "\n...[snip]..."
    return s.encode("ascii", "backslashreplace").decode("ascii")


def _tail_lines(s: str, n: int) -> str:
    lines = (s or "").splitlines()
    return "\n".join(lines[-n:]) if lines else ""


@dataclass(frozen=True)
class _Unmatched:
    count: int
    sample: str


def _load_patterns(rules_path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    rules = RuleSet.from_json_file(rules_path)
    patterns = rules.to_prompt_patterns()
    ids = [p.get("id", "") for p in patterns if p.get("id")]
    return patterns, ids


def run_audit(
    *,
    log_path: Path,
    rules_path: Path,
    max_reads: int | None,
    top_unmatched: int,
    sample_lines: int,
) -> dict[str, Any]:
    patterns, all_prompt_ids = _load_patterns(rules_path)
    detector = PromptDetector(patterns)

    total_reads = 0
    total_read_events = 0
    blank_reads = 0

    matched_reads = 0
    matched_by_prompt = Counter()
    unique_hashes_by_prompt: dict[str, set[str]] = defaultdict(set)

    unmatched_by_hash: dict[str, _Unmatched] = {}
    # Cache detection results by screen_hash; session.jsonl tends to repeat the same
    # screens many times (polling, stable reads, etc).
    detected_by_hash: dict[str, str | None] = {}

    with log_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            if max_reads is not None and total_read_events >= max_reads:
                break
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if rec.get("event") != "read":
                continue
            total_read_events += 1
            data = rec.get("data") or {}
            screen = data.get("screen") or ""
            screen_hash = data.get("screen_hash") or ""
            total_reads += 1

            if not screen.strip():
                blank_reads += 1
                continue

            prompt_id: str | None
            if screen_hash and screen_hash in detected_by_hash:
                prompt_id = detected_by_hash[screen_hash]
            else:
                try:
                    match = detector.detect_prompt(data)
                except Exception:
                    match = None
                prompt_id = match.prompt_id if match is not None else None
                if screen_hash:
                    detected_by_hash[screen_hash] = prompt_id

            if prompt_id is not None:
                matched_reads += 1
                matched_by_prompt[prompt_id] += 1
                if screen_hash:
                    unique_hashes_by_prompt[prompt_id].add(screen_hash)
                continue

            # Unmatched: bucket by screen hash when present; otherwise by a sentinel.
            h = screen_hash or "<no_hash>"
            prev = unmatched_by_hash.get(h)
            if prev is None:
                unmatched_by_hash[h] = _Unmatched(
                    count=1,
                    sample=_tail_lines(screen, sample_lines),
                )
            else:
                unmatched_by_hash[h] = _Unmatched(
                    count=prev.count + 1,
                    sample=prev.sample,
                )

    matched_prompt_ids = set(matched_by_prompt.keys())
    never_seen = [pid for pid in all_prompt_ids if pid not in matched_prompt_ids]

    top_unmatched_items = sorted(
        unmatched_by_hash.items(),
        key=lambda kv: kv[1].count,
        reverse=True,
    )[: max(0, int(top_unmatched))]

    return {
        "log_path": str(log_path),
        "rules_path": str(rules_path),
        "total_read_events": total_read_events,
        "total_reads": total_reads,
        "blank_reads": blank_reads,
        "matched_reads": matched_reads,
        "matched_by_prompt": matched_by_prompt,
        "unique_hashes_by_prompt": unique_hashes_by_prompt,
        "all_prompt_ids": all_prompt_ids,
        "never_seen_prompt_ids": never_seen,
        "top_unmatched": top_unmatched_items,
        "unmatched_unique_hashes": len(unmatched_by_hash),
    }


def render_markdown(report: dict[str, Any]) -> str:
    total_prompts = len(report["all_prompt_ids"])
    seen_prompts = len(report["matched_by_prompt"].keys())
    coverage = (seen_prompts / total_prompts) if total_prompts else 0.0

    lines: list[str] = []
    lines.append("# TW2002 Screen Coverage Audit")
    lines.append("")
    lines.append("This report is generated from a `session.jsonl` log by re-running prompt detection offline.")
    lines.append("")
    lines.append("## Inputs")
    lines.append("")
    lines.append(f"- Log: `{report['log_path']}`")
    lines.append(f"- Rules: `{report['rules_path']}`")
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(f"- Read events processed: `{report['total_read_events']}`")
    lines.append(f"- Non-blank screens: `{report['total_reads'] - report['blank_reads']}`")
    lines.append(f"- Blank screens: `{report['blank_reads']}`")
    lines.append(f"- Matched screens: `{report['matched_reads']}`")
    lines.append(f"- Unmatched unique screen hashes: `{report['unmatched_unique_hashes']}`")
    lines.append(f"- Prompt IDs seen: `{seen_prompts}/{total_prompts}` ({coverage:.1%})")
    lines.append("")
    lines.append("## Prompt Coverage (Seen)")
    lines.append("")
    lines.append("| Prompt ID | Reads | Unique Screens |")
    lines.append("|---|---:|---:|")
    for prompt_id, cnt in report["matched_by_prompt"].most_common():
        uniq = len(report["unique_hashes_by_prompt"].get(prompt_id, set()))
        lines.append(f"| `{prompt_id}` | `{cnt}` | `{uniq}` |")
    lines.append("")
    lines.append("## Prompt Coverage (Never Seen In Log)")
    lines.append("")
    never = report["never_seen_prompt_ids"]
    if never:
        for pid in never:
            lines.append(f"- `{pid}`")
    else:
        lines.append("- (none)")
    lines.append("")
    lines.append("## Top Unmatched Screens")
    lines.append("")
    lines.append("These are the most frequently seen screen hashes that did not match any prompt rule.")
    lines.append("")
    top_unmatched = report["top_unmatched"]
    if not top_unmatched:
        lines.append("- (none)")
        lines.append("")
        return "\n".join(lines) + "\n"

    for screen_hash, item in top_unmatched:
        lines.append(f"### `{screen_hash}` (reads: {item.count})")
        lines.append("")
        lines.append("```text")
        lines.append(_safe_text(item.sample, 3000))
        lines.append("```")
        lines.append("")

    lines.append("## Next Actions")
    lines.append("")
    lines.append("- Add/adjust rules in `games/tw2002/rules.json` for the top unmatched hashes above.")
    lines.append(
        "- If a screen is a data display (not an input prompt), add `expect_cursor_at_end: false` patterns or exclude it explicitly."
    )
    lines.append("- Rerun this audit after changes to confirm coverage improved.")
    lines.append("")

    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    # Keep this tool quiet by default; it's often run on huge logs.
    # CRITICAL to suppress PromptDetector per-screen diagnostics (negative_match, cursor mismatches, etc).
    os.environ.setdefault("BBSBOT_LOG_LEVEL", "CRITICAL")
    try:
        from bbsbot.logging import configure_logging

        configure_logging()
    except Exception:
        pass

    ap = argparse.ArgumentParser(description="Offline prompt coverage audit from session.jsonl")
    ap.add_argument("--log", required=True, type=Path, help="Path to session.jsonl")
    ap.add_argument("--rules", default=Path("games/tw2002/rules.json"), type=Path, help="Path to rules.json")
    ap.add_argument("--out", required=True, type=Path, help="Output markdown path (e.g. SCREEN_AUDIT.md)")
    ap.add_argument("--max-reads", type=int, default=None, help="Max read events to process (default: all)")
    ap.add_argument("--top-unmatched", type=int, default=25, help="How many unmatched hashes to include")
    ap.add_argument("--sample-lines", type=int, default=10, help="How many trailing lines to include per sample")
    args = ap.parse_args(argv)

    report = run_audit(
        log_path=args.log,
        rules_path=args.rules,
        max_reads=args.max_reads,
        top_unmatched=args.top_unmatched,
        sample_lines=args.sample_lines,
    )
    args.out.write_text(render_markdown(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
