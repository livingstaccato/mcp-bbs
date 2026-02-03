from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

from mcp_bbs.telnet import TelnetClient


@dataclass
class Step:
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
    client = TelnetClient()
    await client.connect(host, port, cols, rows, term, True, True)
    steps = parse_script(script)
    try:
        for step in steps:
            if step.kind == "send":
                await client.send(step.payload.encode("utf-8").decode("unicode_escape"))
                continue
            if step.kind == "expect":
                result = await client.expect(step.payload, expect_timeout_ms, expect_interval_ms)
                if not result.get("matched"):
                    screen_text = result.get("screen", "")
                    raise RuntimeError(f"EXPECT failed: {step.payload}\n\n{screen_text}")
                continue
    finally:
        await client.disconnect()


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
