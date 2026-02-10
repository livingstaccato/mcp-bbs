from __future__ import annotations

import argparse
import asyncio
import re
import time
from pathlib import Path

from pydantic import BaseModel

from bbsbot.core.session_manager import SessionManager


class Step(BaseModel):
    kind: str
    payload: str


def parse_script(path: Path) -> list[Step]:
    steps: list[Step] = []
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("SEND "):
            steps.append(Step("send", line[5:]))
            continue
        if line.startswith("EXPECT "):
            steps.append(Step("expect", line[7:]))
            continue
        raise ValueError(f"Unrecognized line: {raw_line}")
    return steps


async def run_script(
    host: str,
    port: int,
    script: Path,
    cols: int,
    rows: int,
    term: str,
    expect_timeout_ms: int,
    expect_interval_ms: int,
) -> None:
    manager = SessionManager()
    session_id = await manager.create_session(
        host=host,
        port=port,
        cols=cols,
        rows=rows,
        term=term,
        send_newline=True,
        reuse=True,
    )
    session = await manager.get_session(session_id)
    steps = parse_script(script)
    try:
        for step in steps:
            if step.kind == "send":
                await session.send(step.payload.encode("utf-8").decode("unicode_escape"))
                continue
            if step.kind == "expect":
                # Implement expect functionality inline (read_until_pattern)
                pattern = re.compile(step.payload)
                deadline = time.monotonic() + expect_timeout_ms / 1000
                matched = False
                last_snapshot = {}

                while time.monotonic() < deadline:
                    snapshot = await session.read(expect_interval_ms, 8192)
                    if snapshot.get("disconnected"):
                        break
                    screen = snapshot.get("screen", "")
                    if pattern.search(screen):
                        matched = True
                        last_snapshot = snapshot
                        break
                    last_snapshot = snapshot

                if not matched:
                    screen_text = last_snapshot.get("screen", "")
                    raise RuntimeError(f"EXPECT failed: {step.payload}\n\n{screen_text}")
                continue
    finally:
        await manager.close_session(session_id)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a telnet expect script against a BBS.")
    parser.add_argument("host")
    parser.add_argument("script", type=Path)
    parser.add_argument("--port", type=int, default=23)
    parser.add_argument("--cols", type=int, default=80)
    parser.add_argument("--rows", type=int, default=25)
    parser.add_argument("--term", default="ANSI")
    parser.add_argument("--expect-timeout-ms", type=int, default=8000)
    parser.add_argument("--expect-interval-ms", type=int, default=250)
    args = parser.parse_args()

    asyncio.run(
        run_script(
            host=args.host,
            port=args.port,
            script=args.script,
            cols=args.cols,
            rows=args.rows,
            term=args.term,
            expect_timeout_ms=args.expect_timeout_ms,
            expect_interval_ms=args.expect_interval_ms,
        )
    )


if __name__ == "__main__":
    main()
