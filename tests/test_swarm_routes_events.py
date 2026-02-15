# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from bbsbot.api import swarm_routes
from bbsbot.games.tw2002.account_pool_store import AccountPoolStore
from bbsbot.games.tw2002.bot_identity_store import BotIdentityStore
from bbsbot.manager import BotStatus, SwarmManager

if TYPE_CHECKING:
    from pathlib import Path


def _make_manager(tmp_path: Path) -> SwarmManager:
    return SwarmManager(
        state_file=str(tmp_path / "swarm_state.json"),
        timeseries_dir=str(tmp_path / "metrics"),
        timeseries_interval_s=30,
    )


def test_update_status_accepts_llm_telemetry(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager.bots["bot_000"] = BotStatus(
        bot_id="bot_000",
        pid=111,
        config="config/swarm_demo/bot_000.yaml",
        state="running",
    )

    with TestClient(manager.app) as client:
        resp = client.post(
            "/bot/bot_000/status",
            json={
                "llm_wakeups": 12,
                "autopilot_turns": 88,
                "goal_contract_failures": 2,
                "llm_wakeups_per_100_turns": 13.5,
            },
        )
        assert resp.status_code == 200

    bot = manager.bots["bot_000"]
    assert bot.llm_wakeups == 12
    assert bot.autopilot_turns == 88
    assert bot.goal_contract_failures == 2
    assert bot.llm_wakeups_per_100_turns == 13.5


def test_update_status_merges_diagnostics_telemetry_maps(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager.bots["bot_diag"] = BotStatus(
        bot_id="bot_diag",
        pid=333,
        config="config/swarm_demo/bot_diag.yaml",
        state="running",
    )

    with TestClient(manager.app) as client:
        resp1 = client.post(
            "/bot/bot_diag/status",
            json={
                "combat_telemetry": {"combat_context_seen": 2, "under_attack_reports": 1},
                "attrition_telemetry": {"credits_loss_nontrade": 50},
                "opportunity_telemetry": {"opportunities_seen": 12, "opportunities_executed": 4},
                "action_latency_telemetry": {"trade_count": 3, "trade_ms_sum": 1100},
                "delta_attribution_telemetry": {"delta_trade": 3, "delta_unknown": 1},
                "anti_collapse_runtime": {
                    "controls_enabled": True,
                    "throughput_degraded_active": True,
                    "trigger_throughput_degraded": 2,
                },
                "trade_quality_runtime": {
                    "strict_eligibility_active": True,
                    "blocked_unknown_side": 4,
                    "opportunity_score_avg_accepted": 0.52,
                },
                "swarm_role": "scout",
            },
        )
        assert resp1.status_code == 200
        resp2 = client.post(
            "/bot/bot_diag/status",
            json={
                "combat_telemetry": {"combat_context_seen": 1, "under_attack_reports": 5},
                "attrition_telemetry": {"credits_loss_nontrade": 40},
                "opportunity_telemetry": {"opportunities_seen": 9, "opportunities_executed": 8},
                "action_latency_telemetry": {"trade_count": 2, "trade_ms_sum": 900},
                "delta_attribution_telemetry": {"delta_trade": 2, "delta_unknown": 2},
                "anti_collapse_runtime": {
                    "controls_enabled": True,
                    "throughput_degraded_active": False,
                    "trigger_throughput_degraded": 5,
                },
                "trade_quality_runtime": {
                    "strict_eligibility_active": False,
                    "blocked_unknown_side": 2,
                    "opportunity_score_avg_accepted": 0.61,
                },
            },
        )
        assert resp2.status_code == 200

    bot = manager.bots["bot_diag"]
    assert bot.combat_telemetry["combat_context_seen"] == 2
    assert bot.combat_telemetry["under_attack_reports"] == 5
    assert bot.attrition_telemetry["credits_loss_nontrade"] == 50
    assert bot.opportunity_telemetry["opportunities_seen"] == 12
    assert bot.opportunity_telemetry["opportunities_executed"] == 8
    assert bot.action_latency_telemetry["trade_count"] == 3
    assert bot.action_latency_telemetry["trade_ms_sum"] == 1100
    assert bot.delta_attribution_telemetry["delta_trade"] == 3
    assert bot.delta_attribution_telemetry["delta_unknown"] == 2
    assert bot.anti_collapse_runtime["controls_enabled"] is True
    assert bot.anti_collapse_runtime["throughput_degraded_active"] is False
    assert bot.anti_collapse_runtime["trigger_throughput_degraded"] == 5
    assert bot.trade_quality_runtime["strict_eligibility_active"] is False
    assert bot.trade_quality_runtime["blocked_unknown_side"] == 4
    assert float(bot.trade_quality_runtime["opportunity_score_avg_accepted"]) >= 0.61
    assert bot.swarm_role == "scout"


def test_update_status_ignores_out_of_order_reports(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager.bots["bot_009"] = BotStatus(
        bot_id="bot_009",
        pid=900,
        config="config/swarm_demo/bot_009.yaml",
        state="running",
    )

    with TestClient(manager.app) as client:
        new_resp = client.post(
            "/bot/bot_009/status",
            json={
                "reported_at": 200.0,
                "activity_context": "EXPLORING",
                "status_detail": "PORT_MENU",
            },
        )
        assert new_resp.status_code == 200

        stale_resp = client.post(
            "/bot/bot_009/status",
            json={
                "reported_at": 100.0,
                "activity_context": "LOGGING_IN",
                "status_detail": "USERNAME",
            },
        )
        assert stale_resp.status_code == 200
        assert stale_resp.json().get("ignored") == "stale_report"

    bot = manager.bots["bot_009"]
    assert bot.activity_context == "EXPLORING"
    assert bot.status_detail == "PORT_MENU"
    assert bot.status_reported_at == 200.0


def test_update_status_normalizes_detail_values(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager.bots["bot_010"] = BotStatus(
        bot_id="bot_010",
        pid=910,
        config="config/swarm_demo/bot_010.yaml",
        state="running",
    )

    with TestClient(manager.app) as client:
        resp = client.post(
            "/bot/bot_010/status",
            json={
                "reported_at": 50.0,
                "activity_context": "exploring",
                "status_detail": "prompt.port_haggle",
            },
        )
        assert resp.status_code == 200

    bot = manager.bots["bot_010"]
    assert bot.activity_context == "EXPLORING"
    assert bot.status_detail == "PORT HAGGLE"


def test_update_status_keeps_turn_and_trade_counters_monotonic(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager.bots["bot_011"] = BotStatus(
        bot_id="bot_011",
        pid=911,
        config="config/swarm_demo/bot_011.yaml",
        state="running",
        turns_executed=120,
        trades_executed=9,
    )

    with TestClient(manager.app) as client:
        # Newer report with lower counters should not regress totals.
        resp1 = client.post(
            "/bot/bot_011/status",
            json={
                "reported_at": 100.0,
                "turns_executed": 40,
                "trades_executed": 3,
            },
        )
        assert resp1.status_code == 200

        # Higher counters should still advance normally.
        resp2 = client.post(
            "/bot/bot_011/status",
            json={
                "reported_at": 101.0,
                "turns_executed": 140,
                "trades_executed": 11,
            },
        )
        assert resp2.status_code == 200

    bot = manager.bots["bot_011"]
    assert bot.turns_executed == 140
    assert bot.trades_executed == 11


def test_bot_events_include_structured_action_metadata(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    manager.bots["bot_001"] = BotStatus(
        bot_id="bot_001",
        pid=222,
        config="config/swarm_demo/bot_001.yaml",
        state="running",
        strategy="ai_strategy(balanced)",
        strategy_id="ai_strategy",
        strategy_mode="balanced",
        strategy_intent="MOVE 5",
        credits=1234,
        turns_executed=44,
        recent_actions=[
            {
                "time": 100.0,
                "action": "MOVE",
                "sector": 7,
                "details": "toward port",
                "why": "goal contract fallback",
                "result": "success",
                "wake_reason": "goal_contract_failed",
                "review_after_turns": 4,
                "decision_source": "goal_contract",
                "strategy_id": "opportunistic",
                "strategy_mode": "conservative",
                "strategy_intent": "MOVE 9",
                "credits_before": 1000,
                "credits_after": 1030,
                "turns_before": 43,
                "turns_after": 44,
                "result_delta": 30,
            }
        ],
    )

    with TestClient(manager.app) as client:
        resp = client.get("/bot/bot_001/events")
        assert resp.status_code == 200
        events = resp.json()["events"]
        assert events
        action_event = next(e for e in events if e["type"] == "action")

    assert action_event["why"] == "goal contract fallback"
    assert action_event["wake_reason"] == "goal_contract_failed"
    assert action_event["review_after_turns"] == 4
    assert action_event["decision_source"] == "goal_contract"
    assert action_event["strategy_id"] == "opportunistic"
    assert action_event["strategy_mode"] == "conservative"
    assert action_event["result_delta"] == 30


def test_bot_session_data_endpoint_returns_persisted_identity(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    swarm_routes._identity_store = BotIdentityStore(data_dir=tmp_path / "sessions")
    swarm_routes._identity_store.upsert_identity(
        bot_id="bot_777",
        username="pilot777",
        character_password="pw777",
        game_password="game777",
        host="localhost",
        port=2002,
        game_letter="A",
        config_path="config/swarm_demo/bot_777.yaml",
    )
    session = swarm_routes._identity_store.start_session(bot_id="bot_777", state="running")
    swarm_routes._identity_store.end_session(
        bot_id="bot_777",
        session_id=session.id,
        stop_reason="shutdown",
        state="stopped",
        turns_executed=12,
        credits=900,
        trades_executed=2,
        sector=9,
    )

    with TestClient(manager.app) as client:
        resp = client.get("/bot/bot_777/session-data")
        assert resp.status_code == 200
        data = resp.json()

    assert data["bot_id"] == "bot_777"
    assert data["username"] == "pilot777"
    assert data["character_password"] == "pw777"
    assert data["game_password"] == "game777"
    assert data["run_count"] == 1
    assert len(data["sessions"]) == 1
    assert data["sessions"][0]["stop_reason"] == "shutdown"


def test_account_pool_endpoint_redacts_passwords_and_summarizes_identities(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    swarm_routes._identity_store = BotIdentityStore(data_dir=tmp_path / "sessions")
    swarm_routes._account_pool_store = AccountPoolStore(
        pool_file=tmp_path / "sessions" / "account_pool.json",
        lock_file=tmp_path / "sessions" / "account_pool.lock",
    )

    swarm_routes._identity_store.upsert_identity(
        bot_id="bot_pool",
        username="pilot_pool",
        character_password="secret_char",
        game_password="secret_game",
        host="localhost",
        port=2002,
        game_letter="T",
        config_path="config/swarm_demo/bot_pool.yaml",
        identity_source="pool",
    )
    swarm_routes._account_pool_store.reserve_account(
        bot_id="bot_pool",
        username="pilot_pool",
        character_password="secret_char",
        game_password="secret_game",
        host="localhost",
        port=2002,
        game_letter="T",
        source="pool",
    )

    with TestClient(manager.app) as client:
        resp = client.get("/swarm/account-pool")
        assert resp.status_code == 200
        data = resp.json()

    assert data["pool"]["accounts_total"] == 1
    assert data["pool"]["leased"] == 1
    assert "leased_active" in data["pool"]
    assert "leased_stale" in data["pool"]
    assert data["pool"]["leased_active"] + data["pool"]["leased_stale"] == data["pool"]["leased"]
    assert data["identities"]["total"] >= 1
    first = data["pool"]["accounts"][0]
    assert first["username"] == "pilot_pool"
    assert "character_password" not in first
    assert "game_password" not in first
    assert "lease_seconds_remaining" in first
    assert "is_hijacked" in first["lease"]
    assert "hijacked_by" in first["lease"]
    assert "hijacked_at" in first["lease"]


def test_account_pool_endpoint_includes_hijack_state_for_active_lease(tmp_path: Path) -> None:
    manager = _make_manager(tmp_path)
    swarm_routes._identity_store = BotIdentityStore(data_dir=tmp_path / "sessions")
    swarm_routes._account_pool_store = AccountPoolStore(
        pool_file=tmp_path / "sessions" / "account_pool.json",
        lock_file=tmp_path / "sessions" / "account_pool.lock",
    )
    manager.bots["bot_hijack"] = BotStatus(
        bot_id="bot_hijack",
        pid=444,
        config="config/swarm_demo/bot_hijack.yaml",
        state="running",
        is_hijacked=True,
        hijacked_by="codex_soak",
        hijacked_at=1234.5,
    )

    swarm_routes._identity_store.upsert_identity(
        bot_id="bot_hijack",
        username="pilot_hijack",
        character_password="secret_char",
        game_password="secret_game",
        host="localhost",
        port=2002,
        game_letter="T",
        config_path="config/swarm_demo/bot_hijack.yaml",
        identity_source="pool",
    )
    swarm_routes._account_pool_store.reserve_account(
        bot_id="bot_hijack",
        username="pilot_hijack",
        character_password="secret_char",
        game_password="secret_game",
        host="localhost",
        port=2002,
        game_letter="T",
        source="pool",
    )

    with TestClient(manager.app) as client:
        resp = client.get("/swarm/account-pool")
        assert resp.status_code == 200
        data = resp.json()

    first = data["pool"]["accounts"][0]
    assert first["lease"]["is_hijacked"] is True
    assert first["lease"]["hijacked_by"] == "codex_soak"
    assert first["lease"]["hijacked_at"] == 1234.5
    assert isinstance(first["lease_seconds_remaining"], int)
    assert first["lease_seconds_remaining"] >= 0
