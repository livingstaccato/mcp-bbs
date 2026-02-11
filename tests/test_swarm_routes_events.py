from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

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
