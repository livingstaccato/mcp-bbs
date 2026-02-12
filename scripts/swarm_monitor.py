#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Resilient swarm monitor for long-running soak analysis."""

from __future__ import annotations

import argparse
import json
import signal
import time
from pathlib import Path

import requests


def _state_counts(bots: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for b in bots:
        state = str(b.get("state") or "unknown")
        counts[state] = counts.get(state, 0) + 1
    return counts


def _sample_row(status: dict, *, elapsed_s: int, monitor_errors: int) -> dict:
    bots = status.get("bots", [])
    return {
        "ts": time.time(),
        "elapsed_s": elapsed_s,
        "total_bots": int(status.get("total_bots", 0)),
        "running": int(status.get("running", 0)),
        "errors_card": int(status.get("errors", 0)),
        "total_turns": int(status.get("total_turns", 0)),
        "total_credits": int(status.get("total_credits", 0)),
        "state_counts": _state_counts(bots),
        "trading_bots": sum(
            1
            for b in bots
            if any(x in str(b.get("activity_context", "")).upper() for x in ("TRAD", "PORT", "SHOP"))
        ),
        "profitable_bots": sum(1 for b in bots if int(b.get("credits_delta") or 0) > 0),
        "positive_cpt_bots": sum(1 for b in bots if float(b.get("credits_per_turn") or 0.0) > 0),
        "no_trade_120p": sum(
            1 for b in bots if int(b.get("trades_executed") or 0) == 0 and int(b.get("turns_executed") or 0) >= 120
        ),
        "haggle_low_total": sum(int(b.get("haggle_too_low") or 0) for b in bots),
        "haggle_high_total": sum(int(b.get("haggle_too_high") or 0) for b in bots),
        "monitor_errors": monitor_errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Monitor swarm health/profit metrics.")
    parser.add_argument("--base-url", default="http://localhost:2272", help="Manager base URL")
    parser.add_argument("--duration-s", type=int, default=3600, help="How long to monitor")
    parser.add_argument("--interval-s", type=int, default=20, help="Sample interval")
    parser.add_argument("--tag", default="live", help="Output filename tag")
    args = parser.parse_args()

    out_dir = Path("logs/soak")
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    jsonl_path = out_dir / f"soak_monitor_{args.tag}_{stamp}.jsonl"
    summary_path = out_dir / f"soak_monitor_{args.tag}_{stamp}_summary.json"
    heartbeat_path = out_dir / "soak_monitor_heartbeat.json"

    stop = {"value": False}

    def _handle_stop(signum, _frame):
        stop["value"] = True
        print(f"[monitor] received signal {signum}, finishing")

    signal.signal(signal.SIGTERM, _handle_stop)
    signal.signal(signal.SIGINT, _handle_stop)

    session = requests.Session()
    start = time.time()
    next_tick = start
    samples = 0
    monitor_errors = 0
    first_status: dict | None = None
    last_status: dict | None = None

    print(f"[monitor] output={jsonl_path}")
    print(f"[monitor] summary={summary_path}")

    while not stop["value"]:
        now = time.time()
        elapsed = int(now - start)
        if elapsed >= args.duration_s:
            break
        if now < next_tick:
            time.sleep(min(1.0, next_tick - now))
            continue

        row: dict
        try:
            status = session.get(f"{args.base_url}/swarm/status", timeout=20).json()
            if first_status is None:
                first_status = status
            last_status = status
            row = _sample_row(status, elapsed_s=elapsed, monitor_errors=monitor_errors)
        except Exception as e:
            monitor_errors += 1
            row = {
                "ts": now,
                "elapsed_s": elapsed,
                "monitor_error": str(e),
                "monitor_errors": monitor_errors,
            }

        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row) + "\n")
        samples += 1

        heartbeat = {
            "ts": now,
            "elapsed_s": elapsed,
            "samples": samples,
            "monitor_errors": monitor_errors,
            "jsonl": str(jsonl_path),
        }
        heartbeat_path.write_text(json.dumps(heartbeat, indent=2), encoding="utf-8")

        if samples % 6 == 0 and "total_bots" in row:
            print(
                "[monitor] "
                f"t={elapsed/60.0:5.1f}m total={row['total_bots']} run={row['running']} "
                f"trade={row['trading_bots']} profit={row['profitable_bots']} "
                f"+cpt={row['positive_cpt_bots']} no_trade120={row['no_trade_120p']} "
                f"haggle(L/H)={row['haggle_low_total']}/{row['haggle_high_total']}"
            )
        elif samples % 6 == 0:
            print(f"[monitor] t={elapsed/60.0:5.1f}m monitor_error_count={monitor_errors}")

        next_tick += args.interval_s

    final_status = last_status
    if final_status is None:
        try:
            final_status = session.get(f"{args.base_url}/swarm/status", timeout=20).json()
        except Exception:
            final_status = {}

    final_bots = final_status.get("bots", []) if isinstance(final_status, dict) else []
    summary = {
        "base_url": args.base_url,
        "duration_s": args.duration_s,
        "interval_s": args.interval_s,
        "samples": samples,
        "monitor_errors": monitor_errors,
        "started_at": start,
        "ended_at": time.time(),
        "first": {
            "total_bots": int((first_status or {}).get("total_bots", 0)) if isinstance(first_status, dict) else 0,
            "running": int((first_status or {}).get("running", 0)) if isinstance(first_status, dict) else 0,
            "total_turns": int((first_status or {}).get("total_turns", 0)) if isinstance(first_status, dict) else 0,
            "total_credits": int((first_status or {}).get("total_credits", 0))
            if isinstance(first_status, dict)
            else 0,
        },
        "final": {
            "total_bots": int(final_status.get("total_bots", 0)) if isinstance(final_status, dict) else 0,
            "running": int(final_status.get("running", 0)) if isinstance(final_status, dict) else 0,
            "errors": int(final_status.get("errors", 0)) if isinstance(final_status, dict) else 0,
            "total_turns": int(final_status.get("total_turns", 0)) if isinstance(final_status, dict) else 0,
            "total_credits": int(final_status.get("total_credits", 0)) if isinstance(final_status, dict) else 0,
            "profitable_bots": sum(1 for b in final_bots if int(b.get("credits_delta") or 0) > 0),
            "positive_cpt_bots": sum(1 for b in final_bots if float(b.get("credits_per_turn") or 0.0) > 0),
            "no_trade_120p": sum(
                1 for b in final_bots if int(b.get("trades_executed") or 0) == 0 and int(b.get("turns_executed") or 0) >= 120
            ),
        },
        "output_jsonl": str(jsonl_path),
        "heartbeat": str(heartbeat_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("[monitor] complete")
    print(f"[monitor] summary={summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

