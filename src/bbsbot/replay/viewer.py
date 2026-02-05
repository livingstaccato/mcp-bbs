from __future__ import annotations

import json
import time
from pathlib import Path


def _clear_screen() -> None:
    print("\x1b[2J\x1b[H", end="")


def _render_screen(screen: str) -> None:
    _clear_screen()
    print(screen, end="")


def replay_log(
    log_path: str | Path,
    *,
    speed: float = 1.0,
    step: bool = False,
    events: list[str] | None = None,
) -> None:
    log_path = Path(log_path)
    wanted = set(events or ["read", "screen"])
    last_ts: float | None = None

    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        event = record.get("event")
        if event not in wanted:
            continue
        data = record.get("data", {})
        screen = data.get("screen")
        if screen is None:
            continue
        if last_ts is not None and not step:
            delta = (record.get("ts", last_ts) - last_ts) / max(speed, 0.01)
            if delta > 0:
                time.sleep(delta)
        _render_screen(screen)
        if step:
            input("-- next --")
        last_ts = record.get("ts", last_ts)
