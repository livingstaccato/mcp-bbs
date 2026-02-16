#!/usr/bin/env python3
# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Perpetual swarm auto-correct controller.

Monitors swarm performance and automatically:
- restarts dead/blocked bots
- triages root causes when performance collapses
- applies profile-based trade-quality tuning to config files
- rolls restarts to test remediation
"""

from __future__ import annotations

import argparse
import contextlib
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests
import yaml

BAD_STATES = {"completed", "error", "stopped", "disconnected", "blocked"}


@dataclass
class Profile:
    name: str
    trade_quality: dict[str, Any]


PROFILES: dict[str, Profile] = {
    "baseline": Profile(
        name="baseline",
        trade_quality={
            "strict_eligibility_enabled": True,
            "strict_eligibility_require_known_side": True,
            "strict_eligibility_require_port_presence": True,
            "bootstrap_turns": 50,
            "bootstrap_min_verified_lanes": 8,
            "attempt_budget_window_turns": 40,
            "attempt_budget_max_attempts": 6,
            "opportunity_score_min": 0.72,
            "reroute_wrong_side_ttl_s": 300,
            "reroute_no_port_ttl_s": 1200,
            "reroute_no_interaction_ttl_s": 180,
        },
    ),
    "strict_structural": Profile(
        name="strict_structural",
        trade_quality={
            "strict_eligibility_enabled": True,
            "strict_eligibility_require_known_side": True,
            "strict_eligibility_require_port_presence": True,
            "bootstrap_turns": 60,
            "bootstrap_min_verified_lanes": 10,
            "attempt_budget_window_turns": 45,
            "attempt_budget_max_attempts": 5,
            "opportunity_score_min": 0.80,
            "reroute_wrong_side_ttl_s": 600,
            "reroute_no_port_ttl_s": 1500,
            "reroute_no_interaction_ttl_s": 240,
        },
    ),
    "port_hunt": Profile(
        name="port_hunt",
        trade_quality={
            "strict_eligibility_enabled": True,
            "strict_eligibility_require_known_side": True,
            "strict_eligibility_require_port_presence": True,
            "bootstrap_turns": 35,
            "bootstrap_min_verified_lanes": 6,
            "attempt_budget_window_turns": 35,
            "attempt_budget_max_attempts": 6,
            "opportunity_score_min": 0.70,
            "reroute_wrong_side_ttl_s": 360,
            "reroute_no_port_ttl_s": 1800,
            "reroute_no_interaction_ttl_s": 180,
        },
    ),
    "throughput_recover": Profile(
        name="throughput_recover",
        trade_quality={
            "strict_eligibility_enabled": True,
            "strict_eligibility_require_known_side": True,
            "strict_eligibility_require_port_presence": True,
            "bootstrap_turns": 25,
            "bootstrap_min_verified_lanes": 4,
            "attempt_budget_window_turns": 30,
            "attempt_budget_max_attempts": 8,
            "opportunity_score_min": 0.64,
            "reroute_wrong_side_ttl_s": 240,
            "reroute_no_port_ttl_s": 900,
            "reroute_no_interaction_ttl_s": 120,
        },
    ),
}


def _get(session: requests.Session, base: str, path: str) -> dict:
    return session.get(f"{base}{path}", timeout=20).json()


def _post(session: requests.Session, base: str, path: str) -> dict:
    return session.post(f"{base}{path}", timeout=30).json()


def _load_yaml(path: Path) -> dict[str, Any]:
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        return {}
    return data


def _save_yaml(path: Path, data: dict[str, Any]) -> None:
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")


def _apply_profile_to_configs(profile: Profile, root: Path, backup_dir: Path) -> list[str]:
    touched: list[str] = []
    # Explicit loops to keep pyright happy.
    for path in sorted((root / "config" / "swarm_demo").glob("bot_*.yaml")) + sorted(
        (root / "config" / "swarm_demo_ai").glob("bot_*.yaml")
    ):
        data = _load_yaml(path)
        rel = path.relative_to(root)
        backup_path = backup_dir / rel
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        if not backup_path.exists():
            backup_path.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        trading = data.setdefault("trading", {})
        if not isinstance(trading, dict):
            trading = {}
            data["trading"] = trading
        trade_quality = trading.setdefault("trade_quality", {})
        if not isinstance(trade_quality, dict):
            trade_quality = {}
            trading["trade_quality"] = trade_quality
        trade_quality.update(profile.trade_quality)
        _save_yaml(path, data)
        touched.append(str(rel))
    return touched


def _bottom_bots(status: dict, n: int = 5) -> list[dict]:
    bots = status.get("bots") or []
    rows: list[tuple[float, dict]] = []
    for b in bots:
        turns = int(b.get("turns_executed") or 0)
        cpt = float(b.get("credits_per_turn") or 0.0)
        if turns <= 0:
            continue
        rows.append((cpt, b))
    rows.sort(key=lambda x: x[0])
    return [b for _, b in rows[:n]]


def _classify_cause(status: dict, summary: dict) -> str:
    bots = status.get("bots") or []
    blocked_game_full = sum(1 for b in bots if str(b.get("error_type") or "") == "GameFullError")
    if blocked_game_full >= 3:
        return "game_full"
    delta = (summary.get("delta") or {}) if isinstance(summary, dict) else {}
    failures = delta.get("trade_failure_reasons") or {}
    attempts = int(delta.get("trade_attempts") or 0)
    wrong_side = int(failures.get("trade_fail_wrong_side") or 0)
    no_port = int(failures.get("trade_fail_no_port") or 0)
    no_interaction = int(failures.get("trade_fail_no_interaction") or 0)
    if attempts > 0:
        if wrong_side / max(1, attempts) >= 0.45:
            return "wrong_side_storm"
        if no_port / max(1, attempts) >= 0.25:
            return "no_port_storm"
        if no_interaction / max(1, attempts) >= 0.20:
            return "interaction_storm"
    t100 = float(delta.get("trades_per_100_turns") or 0.0)
    succ = float(delta.get("trade_success_rate") or 0.0)
    if t100 < 0.8 and succ < 0.08:
        return "throughput_collapse"
    return "mixed"


def _target_profile(cause: str) -> str:
    if cause == "wrong_side_storm":
        return "strict_structural"
    if cause == "no_port_storm":
        return "port_hunt"
    if cause == "throughput_collapse":
        return "throughput_recover"
    return "baseline"


def main() -> int:
    ap = argparse.ArgumentParser(description="Perpetual swarm auto-correct loop")
    ap.add_argument("--base-url", default="http://localhost:2272")
    ap.add_argument("--interval-s", type=int, default=20)
    ap.add_argument("--profile-cooldown-s", type=int, default=480)
    ap.add_argument("--warmup-seconds", type=int, default=900)
    ap.add_argument("--warmup-min-turns", type=int, default=500)
    ap.add_argument("--min-running-for-controls", type=int, default=18)
    ap.add_argument("--min-attempts-for-controls", type=int, default=40)
    ap.add_argument("--root", default=str(Path.cwd()))
    args = ap.parse_args()

    root = Path(args.root).resolve()
    logs_dir = root / "logs" / "diagnostics"
    logs_dir.mkdir(parents=True, exist_ok=True)
    backup_dir = root / "sessions" / "autocorrect_profile_backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    action_log = logs_dir / "autocorrect_actions.jsonl"
    incident_log = logs_dir / "autocorrect_incidents.jsonl"

    session = requests.Session()
    bad_nwpt = 0
    bad_t100 = 0
    bad_succ = 0
    bad_errors = 0
    last_total_turns = -1
    stagnant = 0
    active_profile = "baseline"
    last_profile_change = 0.0
    start_ts = time.time()

    print("autocorrect_started", flush=True)
    while True:
        now = time.time()
        try:
            status = _get(session, args.base_url, "/swarm/status")
            summary15 = _get(session, args.base_url, "/swarm/timeseries/summary?window_minutes=15")
            delta = summary15.get("delta") or {}
            nwpt = float(delta.get("net_worth_per_turn") or 0.0)
            t100 = float(delta.get("trades_per_100_turns") or 0.0)
            succ = float(delta.get("trade_success_rate") or 0.0)
            attempts = int(delta.get("trade_attempts") or 0)
            errors = int(status.get("errors") or 0)
            turns = int(status.get("total_turns") or 0)
            running = int(status.get("running") or 0)
            warmup_active = (
                (now - start_ts) < float(args.warmup_seconds)
                or turns < int(args.warmup_min_turns)
                or running < int(args.min_running_for_controls)
            )
            controls_ready = (not warmup_active) and (attempts >= int(args.min_attempts_for_controls))

            if controls_ready:
                bad_nwpt = bad_nwpt + 1 if nwpt <= 0.0 else 0
                bad_t100 = bad_t100 + 1 if t100 < 0.8 else 0
                bad_succ = bad_succ + 1 if succ < 0.05 else 0
                bad_errors = bad_errors + 1 if errors > 0 else 0
                stagnant = stagnant + 1 if turns == last_total_turns else 0
            else:
                bad_nwpt = 0
                bad_t100 = 0
                bad_succ = 0
                bad_errors = 0
                stagnant = 0
            last_total_turns = turns

            # Keep dead bots cycling.
            restarted = []
            for b in status.get("bots") or []:
                bid = str(b.get("bot_id") or "")
                st = str(b.get("state") or "")
                if bid and st in BAD_STATES:
                    try:
                        _post(session, args.base_url, f"/bot/{bid}/restart")
                        restarted.append({"bot_id": bid, "state": st})
                    except Exception:
                        pass

            trigger = (
                bad_nwpt >= 3
                or bad_t100 >= 3
                or bad_succ >= 3
                or bad_errors >= 3
                or stagnant >= 6
            )
            action = {
                "ts": now,
                "running": running,
                "errors": errors,
                "turns": turns,
                "nwpt": nwpt,
                "t100": t100,
                "succ": succ,
                "attempts": attempts,
                "profile": active_profile,
                "restarted": restarted,
                "trigger": trigger,
                "warmup_active": warmup_active,
                "controls_ready": controls_ready,
            }

            if trigger:
                cause = _classify_cause(status, summary15)
                action["cause"] = cause
                action["bottom_bots"] = [
                    {
                        "bot_id": b.get("bot_id"),
                        "state": b.get("state"),
                        "turns": b.get("turns_executed"),
                        "credits": b.get("credits"),
                        "credits_per_turn": b.get("credits_per_turn"),
                        "trade_attempts": b.get("trade_attempts"),
                        "trade_successes": b.get("trade_successes"),
                        "trade_failure_reasons": b.get("trade_failure_reasons") or {},
                    }
                    for b in _bottom_bots(status)
                ]
                if cause != "game_full":
                    target = _target_profile(cause)
                    if target != active_profile and (now - last_profile_change) >= float(args.profile_cooldown_s):
                        touched = _apply_profile_to_configs(PROFILES[target], root, backup_dir)
                        action["profile_change"] = {"from": active_profile, "to": target, "files": touched}
                        active_profile = target
                        last_profile_change = now
                        # Roll restart all bots after profile change.
                        for b in status.get("bots") or []:
                            bid = str(b.get("bot_id") or "")
                            if not bid:
                                continue
                            with requests.Session() as s, contextlib.suppress(Exception):
                                _post(s, args.base_url, f"/bot/{bid}/restart")
                            time.sleep(1.2)
                    else:
                        # If no profile change, at least restart bottom offenders.
                        for b in _bottom_bots(status):
                            bid = str(b.get("bot_id") or "")
                            if bid:
                                with contextlib.suppress(Exception):
                                    _post(session, args.base_url, f"/bot/{bid}/restart")

                with incident_log.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(action) + "\n")

            with action_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(action) + "\n")
            print(action, flush=True)
        except Exception as e:
            err = {"ts": now, "error": repr(e)}
            with action_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(err) + "\n")
            print(err, flush=True)
        time.sleep(max(5, int(args.interval_s)))


if __name__ == "__main__":
    raise SystemExit(main())
