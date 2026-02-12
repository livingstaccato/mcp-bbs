# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
from pathlib import Path

from bbsbot.manager import BotStatus, SwarmManager


def _make_manager(tmp_path: Path) -> SwarmManager:
    return SwarmManager(
        state_file=str(tmp_path / "swarm_state.json"),
        timeseries_dir=str(tmp_path / "metrics"),
        timeseries_interval_s=7,
    )


def test_timeseries_sample_written_with_per_bot_rows(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager.bots["bot_000"] = BotStatus(
        bot_id="bot_000",
        pid=111,
        config="config/swarm_demo/bot_000.yaml",
        state="running",
        activity_context="TRADING",
        status_detail="PORT_HAGGLE",
        credits=1234,
        turns_executed=42,
        trades_executed=6,
        haggle_accept=4,
        haggle_counter=1,
        haggle_too_low=1,
        credits_delta=300,
        credits_per_turn=7.14,
        strategy_id="profitable_pairs",
        strategy_mode="balanced",
        llm_wakeups=3,
        autopilot_turns=12,
        goal_contract_failures=1,
    )
    manager.bots["bot_001"] = BotStatus(
        bot_id="bot_001",
        pid=222,
        config="config/swarm_demo/bot_001.yaml",
        state="running",
        activity_context="EXPLORING",
        status_detail="SECTOR_COMMAND",
        credits=700,
        turns_executed=140,
        trades_executed=0,
        haggle_accept=0,
        haggle_counter=2,
        haggle_too_high=3,
        credits_delta=-50,
        credits_per_turn=-0.35,
        strategy_id="opportunistic",
        strategy_mode="conservative",
        llm_wakeups=1,
        autopilot_turns=20,
        goal_contract_failures=0,
    )

    manager._write_timeseries_sample(reason="test")

    info = manager.get_timeseries_info()
    assert info["samples"] == 1
    path = Path(info["path"])
    assert path.exists()

    row = json.loads(path.read_text(encoding="utf-8").strip())
    assert row["reason"] == "test"
    assert row["total_bots"] == 2
    assert row["trading_bots"] == 1
    assert row["profitable_bots"] == 1
    assert row["no_trade_120p"] == 1
    assert row["haggle_high_total"] == 3
    assert row["llm_wakeups_total"] == 4
    assert row["autopilot_turns_total"] == 32
    assert row["goal_contract_failures_total"] == 1
    overall = row["trade_outcomes_overall"]
    assert overall["trades_executed"] == 6
    assert overall["turns_executed"] == 182
    assert overall["trades_per_100_turns"] > 3.0
    assert overall["haggle_accept"] == 4
    assert overall["haggle_counter"] == 3
    assert overall["haggle_too_high"] == 3
    assert overall["haggle_too_low"] == 1
    assert overall["haggle_offers"] == 11
    by_strategy = row["trade_outcomes_by_strategy_mode"]
    assert by_strategy["profitable_pairs(balanced)"]["trades_executed"] == 6
    assert by_strategy["profitable_pairs(balanced)"]["turns_executed"] == 42
    assert by_strategy["profitable_pairs(balanced)"]["trades_per_100_turns"] > 10.0
    assert by_strategy["opportunistic(conservative)"]["haggle_too_high"] == 3
    assert len(row["bots"]) == 2


def test_timeseries_recent_limit(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager.bots["bot_000"] = BotStatus(
        bot_id="bot_000",
        pid=111,
        config="config/swarm_demo/bot_000.yaml",
        state="running",
        credits=100,
        turns_executed=1,
    )

    for idx in range(5):
        manager._write_timeseries_sample(reason=f"tick_{idx}")

    recent = manager.get_timeseries_recent(limit=2)
    assert len(recent) == 2
    assert recent[0]["reason"] == "tick_3"
    assert recent[1]["reason"] == "tick_4"


def test_timeseries_summary_window(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager.bots["bot_000"] = BotStatus(
        bot_id="bot_000",
        pid=111,
        config="config/swarm_demo/bot_000.yaml",
        state="running",
        strategy_id="profitable_pairs",
        strategy_mode="balanced",
        turns_executed=10,
        credits=500,
        trades_executed=2,
        credits_delta=200,
        credits_per_turn=20.0,
        haggle_accept=2,
        haggle_counter=1,
        llm_wakeups=2,
        autopilot_turns=8,
    )
    manager._write_timeseries_sample(reason="tick_a")

    manager.bots["bot_000"].turns_executed = 25
    manager.bots["bot_000"].credits = 900
    manager.bots["bot_000"].trades_executed = 5
    manager.bots["bot_000"].credits_delta = 600
    manager.bots["bot_000"].credits_per_turn = 24.0
    manager.bots["bot_000"].haggle_accept = 5
    manager.bots["bot_000"].haggle_counter = 2
    manager.bots["bot_000"].llm_wakeups = 5
    manager.bots["bot_000"].autopilot_turns = 20
    manager._write_timeseries_sample(reason="tick_b")

    summary = manager.get_timeseries_summary(window_minutes=120)
    assert summary["rows"] == 2
    assert summary["delta"]["turns"] >= 15
    assert summary["delta"]["credits"] >= 400
    assert summary["delta"]["trades_executed"] >= 3
    assert summary["delta"]["trades_per_100_turns"] > 0
    assert summary["delta"]["llm_wakeups"] >= 3
    assert "profitable_pairs(balanced)" in summary["strategy_delta"]["trades_executed"]
    assert "profitable_pairs(balanced)" in summary["strategy_delta"]["trades_per_100_turns"]
