#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Interactive MCP hijack helper for one swarm bot."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import signal
import sys
import time
from pathlib import Path

from fastmcp import Client
from fastmcp.mcp_config import StdioMCPServer


def _unwrap(resp):
    if hasattr(resp, "data"):
        return resp.data
    if isinstance(resp, list) and resp:
        item = resp[0]
        return getattr(item, "text", item)
    return resp


async def _read_stdin_lines(queue: asyncio.Queue[str], stop: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()
    while not stop.is_set():
        line = await loop.run_in_executor(None, sys.stdin.readline)
        if not line:
            await asyncio.sleep(0.1)
            continue
        await queue.put(line.rstrip("\n"))


async def main_async() -> int:
    parser = argparse.ArgumentParser(description="Hijack a TW2002 swarm bot via MCP tools.")
    parser.add_argument("--bot-id", required=True)
    parser.add_argument("--owner", default="codex_soak")
    parser.add_argument("--lease-s", type=int, default=90)
    parser.add_argument("--heartbeat-s", type=int, default=20)
    parser.add_argument("--poll-s", type=float, default=2.0)
    parser.add_argument("--base-url", default="http://localhost:2272")
    args = parser.parse_args()

    out_dir = Path("logs/soak")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"hijack_{args.bot_id}_{stamp}.jsonl"

    server = StdioMCPServer(
        command="uv",
        args=["run", "bbsbot", "serve", "--tools", "tw2002"],
    )

    stop = asyncio.Event()
    line_queue: asyncio.Queue[str] = asyncio.Queue()
    hijack_id: str | None = None

    def _stop(*_a):
        stop.set()

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    async with Client(server.to_transport()) as client:
        assume = _unwrap(await client.call_tool("tw2002_assume_bot", {"bot_id": args.bot_id}))
        print("assume:", assume)
        begin = _unwrap(
            await client.call_tool(
                "tw2002_hijack_begin",
                {"bot_id": args.bot_id, "lease_s": args.lease_s, "owner": args.owner},
            )
        )
        print("hijack_begin:", begin)
        if not isinstance(begin, dict) or not begin.get("success"):
            return 1
        hijack_id = str(begin.get("hijack_id") or "")
        if not hijack_id:
            return 1

        stdin_task = asyncio.create_task(_read_stdin_lines(line_queue, stop))
        last_hb = 0.0
        after_seq = 0
        print("Type keys to send. Special: /release")
        try:
            while not stop.is_set():
                now = time.time()
                if now - last_hb >= max(5, args.heartbeat_s):
                    hb = _unwrap(
                        await client.call_tool(
                            "tw2002_hijack_heartbeat",
                            {"bot_id": args.bot_id, "hijack_id": hijack_id, "lease_s": args.lease_s},
                        )
                    )
                    last_hb = now
                    with out_path.open("a", encoding="utf-8") as f:
                        f.write(json.dumps({"ts": now, "type": "heartbeat", "data": hb}, ensure_ascii=True) + "\n")

                events = _unwrap(
                    await client.call_tool(
                        "tw2002_hijack_read",
                        {
                            "bot_id": args.bot_id,
                            "hijack_id": hijack_id,
                            "mode": "events",
                            "after_seq": after_seq,
                            "limit": 200,
                        },
                    )
                )
                if isinstance(events, dict):
                    evs = list(events.get("events") or [])
                    if evs:
                        after_seq = max(after_seq, max(int(e.get("seq", 0) or 0) for e in evs))
                        with out_path.open("a", encoding="utf-8") as f:
                            for e in evs:
                                f.write(json.dumps({"ts": now, "type": "event", "data": e}, ensure_ascii=True) + "\n")

                while not line_queue.empty():
                    line = await line_queue.get()
                    if line.strip() == "/release":
                        stop.set()
                        break
                    send = _unwrap(
                        await client.call_tool(
                            "tw2002_hijack_send",
                            {"bot_id": args.bot_id, "hijack_id": hijack_id, "keys": line},
                        )
                    )
                    print("send:", send)
                    with out_path.open("a", encoding="utf-8") as f:
                        f.write(
                            json.dumps({"ts": time.time(), "type": "send", "keys": line, "data": send}, ensure_ascii=True)
                            + "\n"
                        )

                await asyncio.sleep(max(0.2, args.poll_s))
        finally:
            stdin_task.cancel()
            with contextlib.suppress(Exception):
                await stdin_task
            if hijack_id:
                rel = _unwrap(
                    await client.call_tool("tw2002_hijack_release", {"bot_id": args.bot_id, "hijack_id": hijack_id})
                )
                print("hijack_release:", rel)
                with out_path.open("a", encoding="utf-8") as f:
                    f.write(json.dumps({"ts": time.time(), "type": "release", "data": rel}, ensure_ascii=True) + "\n")

    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
