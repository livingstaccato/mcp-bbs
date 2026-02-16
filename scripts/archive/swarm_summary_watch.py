#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Poll swarm summaries and trigger degradation triage signals."""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import requests


def _num(d: dict, key: str, default: float = 0.0) -> float:
    try:
        return float(d.get(key, default) or default)
    except Exception:
        return float(default)


def _int(d: dict, key: str, default: int = 0) -> int:
    try:
        return int(d.get(key, default) or default)
    except Exception:
        return int(default)


def main() -> int:
    parser = argparse.ArgumentParser(description="Watch swarm summary windows and emit triage triggers.")
    parser.add_argument("--base-url", default="http://localhost:2272")
    parser.add_argument("--duration-s", type=int, default=3600)
    parser.add_argument("--interval-s", type=int, default=60)
    parser.add_argument("--tag", default="mcp_hijack_20bots")
    args = parser.parse_args()

    out_dir = Path("logs/soak")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"swarm_summary_watch_{args.tag}_{stamp}.jsonl"
    triage_path = out_dir / f"swarm_summary_watch_{args.tag}_{stamp}_triage.jsonl"

    session = requests.Session()
    start = time.time()
    next_tick = start

    # Consecutive counters for trigger logic.
    c_net_worth = 0
    c_velocity = 0
    c_no_trade = 0
    c_errors = 0

    print(f"[watch] output={out_path}")
    print(f"[watch] triage={triage_path}")
    while True:
        now = time.time()
        elapsed = int(now - start)
        if elapsed >= args.duration_s:
            break
        if now < next_tick:
            time.sleep(min(1.0, next_tick - now))
            continue

        row: dict = {"ts": now, "elapsed_s": elapsed}
        triage_hits: list[str] = []
        try:
            status = session.get(f"{args.base_url}/swarm/status", timeout=20).json()
            s15 = session.get(f"{args.base_url}/swarm/timeseries/summary?window_minutes=15", timeout=20).json()
            s60 = session.get(f"{args.base_url}/swarm/timeseries/summary?window_minutes=60", timeout=20).json()
            latest15 = dict(s15.get("latest") or {})
            latest60 = dict(s60.get("latest") or {})
            row.update(
                {
                    "running": _int(status, "running"),
                    "errors": _int(status, "errors"),
                    "total_bots": _int(status, "total_bots"),
                    "total_turns": _int(status, "total_turns"),
                    "w15": {
                        "net_worth_per_turn": _num(latest15, "net_worth_per_turn"),
                        "trades_per_100_turns": _num(latest15, "trades_per_100_turns"),
                        "no_trade_120p": _int(latest15, "no_trade_120p"),
                        "trade_success_rate": _num(latest15, "trade_success_rate"),
                        "zombie_traders_120_1": _int(latest15, "zombie_traders_120_1"),
                        "zombie_traders_200_2": _int(latest15, "zombie_traders_200_2"),
                    },
                    "w60": {
                        "net_worth_per_turn": _num(latest60, "net_worth_per_turn"),
                        "trades_per_100_turns": _num(latest60, "trades_per_100_turns"),
                        "no_trade_120p": _int(latest60, "no_trade_120p"),
                        "trade_success_rate": _num(latest60, "trade_success_rate"),
                        "zombie_traders_120_1": _int(latest60, "zombie_traders_120_1"),
                        "zombie_traders_200_2": _int(latest60, "zombie_traders_200_2"),
                    },
                }
            )

            nwpt = _num(latest15, "net_worth_per_turn")
            t100 = _num(latest15, "trades_per_100_turns")
            nt120 = _int(latest15, "no_trade_120p")
            errs = _int(status, "errors")
            c_net_worth = c_net_worth + 1 if nwpt <= 0.0 else 0
            c_velocity = c_velocity + 1 if t100 < 0.8 else 0
            c_no_trade = c_no_trade + 1 if nt120 > 2 else 0
            c_errors = c_errors + 1 if errs > 0 else 0

            if c_net_worth >= 3:
                triage_hits.append("net_worth_per_turn<=0(15m)x3")
            if c_velocity >= 3:
                triage_hits.append("trades_per_100_turns<0.8(15m)x3")
            if c_no_trade >= 3:
                triage_hits.append("no_trade_120p>2x3")
            if c_errors >= 3:
                triage_hits.append("errors>0x3")
        except Exception as e:
            row["watch_error"] = str(e)

        with out_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=True) + "\n")
        if triage_hits:
            with triage_path.open("a", encoding="utf-8") as f:
                f.write(
                    json.dumps(
                        {
                            "ts": now,
                            "elapsed_s": elapsed,
                            "hits": triage_hits,
                            "snapshot": row,
                        },
                        ensure_ascii=True,
                    )
                    + "\n"
                )
            print(f"[watch][triage] t={elapsed}s hits={','.join(triage_hits)}")
        next_tick += max(5, int(args.interval_s))

    print("[watch] complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
