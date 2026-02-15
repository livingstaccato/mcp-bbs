# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
import time
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
        cargo_fuel_ore=12,
        cargo_organics=7,
        cargo_equipment=3,
        cargo_estimated_value=120,
        net_worth_estimate=1354,
        credits_delta=300,
        credits_per_turn=7.14,
        strategy_id="profitable_pairs",
        strategy_mode="balanced",
        llm_wakeups=3,
        autopilot_turns=12,
        goal_contract_failures=1,
        combat_telemetry={"combat_context_seen": 1},
        attrition_telemetry={"credits_loss_nontrade": 10},
        opportunity_telemetry={"opportunities_seen": 5, "opportunities_executed": 2},
        action_latency_telemetry={"trade_count": 3, "trade_ms_sum": 900},
        delta_attribution_telemetry={"delta_trade": 2, "delta_unknown": 1},
        anti_collapse_runtime={"controls_enabled": True, "trigger_throughput_degraded": 2},
        trade_quality_runtime={"blocked_unknown_side": 3, "verified_lanes_count": 2},
        screen_action_tag_telemetry={"move": 4, "tow_control": 1},
        swarm_role="scout",
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
        cargo_fuel_ore=2,
        cargo_organics=0,
        cargo_equipment=11,
        cargo_estimated_value=40,
        net_worth_estimate=740,
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
    assert row["total_net_worth_estimate"] == 2094
    assert row["trading_bots"] == 1
    assert row["profitable_bots"] == 1
    assert row["no_trade_120p"] == 1
    assert row["haggle_high_total"] == 3
    assert row["llm_wakeups_total"] == 4
    assert row["autopilot_turns_total"] == 32
    assert row["goal_contract_failures_total"] == 1
    assert row["combat_telemetry_total"]["combat_context_seen"] == 1
    assert row["attrition_telemetry_total"]["credits_loss_nontrade"] == 10
    assert row["opportunity_telemetry_total"]["opportunities_seen"] == 5
    assert row["action_latency_telemetry_total"]["trade_count"] == 3
    assert row["delta_attribution_telemetry_total"]["delta_unknown"] == 1
    assert row["anti_collapse_runtime_total"]["trigger_throughput_degraded"] == 2
    assert row["trade_quality_runtime_total"]["blocked_unknown_side"] == 3
    assert row["trade_quality_runtime_total"]["verified_lanes_count"] == 2
    assert row["screen_action_tag_telemetry_total"]["move"] == 4
    assert row["total_cargo_fuel_ore"] == 14
    assert row["total_cargo_organics"] == 7
    assert row["total_cargo_equipment"] == 14
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
    assert row["bots"][0]["net_worth_estimate"] >= row["bots"][0]["credits"]


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


def test_timeseries_recent_trims_to_latest_epoch(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    rows = [
        {"ts": time.time() - 80, "reason": "old_a", "total_turns": 400, "total_bots": 20},
        {"ts": time.time() - 60, "reason": "old_b", "total_turns": 420, "total_bots": 20},
        {"ts": time.time() - 40, "reason": "reset", "total_turns": 0, "total_bots": 0},
        {"ts": time.time() - 20, "reason": "new_a", "total_turns": 15, "total_bots": 20},
        {"ts": time.time() - 10, "reason": "new_b", "total_turns": 28, "total_bots": 20},
    ]
    manager._timeseries_path.parent.mkdir(parents=True, exist_ok=True)
    with manager._timeseries_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    recent = manager.get_timeseries_recent(limit=10)
    assert [r["reason"] for r in recent] == ["reset", "new_a", "new_b"]


def test_timeseries_recent_does_not_trim_on_small_turn_regressions(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    rows = [
        {"ts": time.time() - 60, "reason": "a", "total_turns": 1000, "total_bots": 20},
        {"ts": time.time() - 40, "reason": "b", "total_turns": 980, "total_bots": 20},
        {"ts": time.time() - 20, "reason": "c", "total_turns": 1030, "total_bots": 20},
    ]
    manager._timeseries_path.parent.mkdir(parents=True, exist_ok=True)
    with manager._timeseries_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    recent = manager.get_timeseries_recent(limit=10)
    assert [r["reason"] for r in recent] == ["a", "b", "c"]


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
        net_worth_estimate=650,
        credits_delta=200,
        credits_per_turn=20.0,
        haggle_accept=2,
        haggle_counter=1,
        prompt_telemetry={"seen": 12, "accepted": 8, "misses": 1},
        warp_telemetry={"hops_attempted": 9, "hops_succeeded": 8, "hops_failed": 1},
        warp_failure_reasons={"target_mismatch": 1},
        decision_counts_considered={"TRADE": 5, "MOVE": 4},
        decision_counts_executed={"TRADE": 4, "MOVE": 5},
        decision_override_total=2,
        decision_override_reasons={"loop_break_force:MOVE->TRADE": 1, "trade_stall_reroute:TRADE->MOVE": 1},
        valuation_source_units_total={"quote": 10, "hint": 3, "floor": 2},
        valuation_source_value_total={"quote": 900, "hint": 120, "floor": 30},
        valuation_confidence_last=0.81,
        route_churn_total=2,
        route_churn_reasons={"buy_path_unreachable": 2},
        llm_wakeups=2,
        autopilot_turns=8,
        combat_telemetry={"combat_context_seen": 1, "under_attack_reports": 1},
        attrition_telemetry={"credits_loss_nontrade": 5},
        opportunity_telemetry={"opportunities_seen": 10, "opportunities_executed": 3},
        action_latency_telemetry={"trade_count": 2, "trade_ms_sum": 400},
        delta_attribution_telemetry={"delta_trade": 2, "delta_unknown": 0},
        anti_collapse_runtime={"controls_enabled": True, "trigger_throughput_degraded": 1},
        trade_quality_runtime={"blocked_unknown_side": 2, "verified_lanes_count": 1, "reroute_no_port": 1},
    )
    manager._write_timeseries_sample(reason="tick_a")

    manager.bots["bot_000"].turns_executed = 25
    manager.bots["bot_000"].credits = 900
    manager.bots["bot_000"].trades_executed = 5
    manager.bots["bot_000"].net_worth_estimate = 1100
    manager.bots["bot_000"].credits_delta = 600
    manager.bots["bot_000"].credits_per_turn = 24.0
    manager.bots["bot_000"].haggle_accept = 5
    manager.bots["bot_000"].haggle_counter = 2
    manager.bots["bot_000"].prompt_telemetry = {"seen": 20, "accepted": 15, "misses": 2}
    manager.bots["bot_000"].warp_telemetry = {"hops_attempted": 19, "hops_succeeded": 17, "hops_failed": 2}
    manager.bots["bot_000"].warp_failure_reasons = {"target_mismatch": 2}
    manager.bots["bot_000"].decision_counts_considered = {"TRADE": 9, "MOVE": 8}
    manager.bots["bot_000"].decision_counts_executed = {"TRADE": 8, "MOVE": 9}
    manager.bots["bot_000"].decision_override_total = 3
    manager.bots["bot_000"].decision_override_reasons = {
        "loop_break_force:MOVE->TRADE": 1,
        "trade_stall_reroute:TRADE->MOVE": 2,
    }
    manager.bots["bot_000"].valuation_source_units_total = {"quote": 22, "hint": 5, "floor": 2}
    manager.bots["bot_000"].valuation_source_value_total = {"quote": 1800, "hint": 210, "floor": 30}
    manager.bots["bot_000"].valuation_confidence_last = 0.88
    manager.bots["bot_000"].route_churn_total = 4
    manager.bots["bot_000"].route_churn_reasons = {"buy_path_unreachable": 2, "sell_side_not_buying": 2}
    manager.bots["bot_000"].llm_wakeups = 5
    manager.bots["bot_000"].autopilot_turns = 20
    manager.bots["bot_000"].combat_telemetry = {"combat_context_seen": 3, "under_attack_reports": 2}
    manager.bots["bot_000"].attrition_telemetry = {"credits_loss_nontrade": 12}
    manager.bots["bot_000"].opportunity_telemetry = {"opportunities_seen": 18, "opportunities_executed": 7}
    manager.bots["bot_000"].action_latency_telemetry = {"trade_count": 5, "trade_ms_sum": 1200}
    manager.bots["bot_000"].delta_attribution_telemetry = {"delta_trade": 5, "delta_unknown": 1}
    manager.bots["bot_000"].anti_collapse_runtime = {"controls_enabled": True, "trigger_throughput_degraded": 4}
    manager.bots["bot_000"].trade_quality_runtime = {"blocked_unknown_side": 5, "verified_lanes_count": 3, "reroute_no_port": 2}
    manager._write_timeseries_sample(reason="tick_b")

    summary = manager.get_timeseries_summary(window_minutes=120)
    assert summary["rows"] == 2
    assert summary["delta"]["turns"] >= 15
    assert summary["delta"]["credits"] >= 400
    assert summary["delta"]["net_worth_estimate"] >= 450
    assert summary["delta"]["trades_executed"] >= 3
    assert summary["delta"]["trades_per_100_turns"] > 0
    assert summary["delta"]["llm_wakeups"] >= 3
    assert summary["delta"]["prompt_telemetry"]["seen"] >= 8
    assert summary["delta"]["warp_telemetry"]["hops_attempted"] >= 10
    assert summary["delta"]["decision_counts_considered"]["TRADE"] >= 4
    assert summary["delta"]["decision_override_total"] >= 1
    assert summary["delta"]["valuation_source_units"]["quote"] >= 12
    assert summary["delta"]["route_churn_total"] >= 2
    assert summary["delta"]["combat_telemetry"]["combat_context_seen"] >= 2
    assert summary["delta"]["attrition_telemetry"]["credits_loss_nontrade"] >= 7
    assert summary["delta"]["opportunity_telemetry"]["opportunities_seen"] >= 8
    assert summary["delta"]["action_latency_telemetry"]["trade_count"] >= 3
    assert summary["delta"]["delta_attribution_telemetry"]["delta_trade"] >= 3
    assert summary["delta"]["anti_collapse_runtime"]["trigger_throughput_degraded"] >= 3
    assert summary["delta"]["trade_quality_runtime"]["blocked_unknown_side"] >= 3
    assert "roi_confidence" in summary["delta"]
    assert "roi_low_confidence" in summary["delta"]
    assert "roi_confidence_reasons" in summary["delta"]
    assert summary["delta"]["trade_quality"]["block_rate"] >= 0.0
    assert summary["last"]["combat_telemetry_total"]["under_attack_reports"] >= 2
    assert summary["last"]["anti_collapse_runtime_total"]["trigger_throughput_degraded"] >= 4
    assert summary["last"]["trade_quality_runtime_total"]["verified_lanes_count"] >= 3
    assert "profitable_pairs(balanced)" in summary["strategy_delta"]["trades_executed"]
    assert "profitable_pairs(balanced)" in summary["strategy_delta"]["trades_per_100_turns"]


def test_timeseries_summary_trims_to_latest_epoch(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    now = time.time()
    rows = [
        {
            "ts": now - 90,
            "reason": "old_a",
            "total_turns": 600,
            "total_bots": 20,
            "total_credits": 5000,
            "total_net_worth_estimate": 5500,
            "trade_attempts_total": 120,
            "trade_successes_total": 30,
            "trade_failures_total": 90,
            "trade_outcomes_overall": {"trades_executed": 70},
        },
        {
            "ts": now - 70,
            "reason": "old_b",
            "total_turns": 700,
            "total_bots": 20,
            "total_credits": 5200,
            "total_net_worth_estimate": 5700,
            "trade_attempts_total": 150,
            "trade_successes_total": 35,
            "trade_failures_total": 115,
            "trade_outcomes_overall": {"trades_executed": 78},
        },
        {
            "ts": now - 50,
            "reason": "reset",
            "total_turns": 0,
            "total_bots": 0,
            "total_credits": 0,
            "total_net_worth_estimate": 0,
            "trade_attempts_total": 0,
            "trade_successes_total": 0,
            "trade_failures_total": 0,
            "trade_outcomes_overall": {"trades_executed": 0},
        },
        {
            "ts": now - 30,
            "reason": "new_a",
            "total_turns": 25,
            "total_bots": 20,
            "total_credits": 3100,
            "total_net_worth_estimate": 3300,
            "trade_attempts_total": 4,
            "trade_successes_total": 1,
            "trade_failures_total": 3,
            "trade_outcomes_overall": {"trades_executed": 1},
        },
        {
            "ts": now - 10,
            "reason": "new_b",
            "total_turns": 55,
            "total_bots": 20,
            "total_credits": 3600,
            "total_net_worth_estimate": 3900,
            "trade_attempts_total": 9,
            "trade_successes_total": 2,
            "trade_failures_total": 7,
            "trade_outcomes_overall": {"trades_executed": 2},
        },
    ]
    manager._timeseries_path.parent.mkdir(parents=True, exist_ok=True)
    with manager._timeseries_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")

    summary = manager.get_timeseries_summary(window_minutes=120)
    assert summary["rows"] == 3
    assert summary["delta"]["turns"] == 55
    assert summary["delta"]["trade_attempts"] == 9
    assert summary["delta"]["trade_successes"] == 2
    assert summary["delta"]["trades_executed"] == 2


def test_timeseries_summary_treats_net_worth_as_gauge(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager.bots["bot_000"] = BotStatus(
        bot_id="bot_000",
        pid=111,
        config="config/swarm_demo/bot_000.yaml",
        state="running",
        turns_executed=10,
        credits=200,
        net_worth_estimate=500,
    )
    manager._write_timeseries_sample(reason="tick_a")

    manager.bots["bot_000"].turns_executed = 20
    manager.bots["bot_000"].credits = 50
    manager.bots["bot_000"].net_worth_estimate = 350
    manager._write_timeseries_sample(reason="tick_b")

    manager.bots["bot_000"].turns_executed = 30
    manager.bots["bot_000"].credits = 260
    manager.bots["bot_000"].net_worth_estimate = 540
    manager._write_timeseries_sample(reason="tick_c")

    summary = manager.get_timeseries_summary(window_minutes=120)
    assert summary["rows"] == 3
    # Gauge deltas use end-start, not reset-aware rolling sum of upward moves.
    assert summary["delta"]["net_worth_estimate"] == 40
    assert summary["delta"]["credits"] == 60
