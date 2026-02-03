from __future__ import annotations

import argparse
import json
import time
from pathlib import Path


def clear_screen() -> None:
    print("\x1b[2J\x1b[H", end="")


def render_screen(screen: str) -> None:
    clear_screen()
    print(screen, end="")


def main() -> None:
    parser = argparse.ArgumentParser(description="Replay a BBS session log (JSONL).")
    parser.add_argument("log", type=Path)
    parser.add_argument("--speed", type=float, default=1.0, help="Playback speed multiplier.")
    parser.add_argument("--step", action="store_true", help="Wait for ENTER between screen updates.")
    parser.add_argument("--events", nargs="*", default=["read", "screen"], help="Events to render.")
    args = parser.parse_args()

    last_ts = None
    for line in args.log.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        record = json.loads(line)
        event = record.get("event")
        if event not in args.events:
            continue
        data = record.get("data", {})
        screen = data.get("screen")
        if screen is None:
            continue
        if last_ts is not None and not args.step:
            delta = (record.get("ts", last_ts) - last_ts) / max(args.speed, 0.01)
            if delta > 0:
                time.sleep(delta)
        render_screen(screen)
        if args.step:
            input("-- next --")
        last_ts = record.get("ts", last_ts)


if __name__ == "__main__":
    main()
