# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

from __future__ import annotations

import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bbsbot.api.term_routes import TermHub


def _recv_until_type(ws, want_type: str, max_msgs: int = 80) -> dict:
    for _ in range(max_msgs):
        msg = json.loads(ws.receive_text())
        if msg.get("type") == want_type:
            return msg
    raise AssertionError(f"did not receive type={want_type}")


def test_rest_hijack_acquire_send_events_release() -> None:
    hub = TermHub()
    app = FastAPI()
    app.include_router(hub.create_router())

    with TestClient(app) as client, client.websocket_connect("/ws/worker/bot_101/term") as worker:
        _recv_until_type(worker, "snapshot_req")

        # Seed a prompt-detected snapshot for prompt-guarded send.
        worker.send_text(
            json.dumps(
                {
                    "type": "snapshot",
                    "screen": "Command [TL=00:00:00]: [123] (?=Help)? :",
                    "prompt_detected": {"prompt_id": "prompt.sector_command"},
                    "screen_hash": "abc123",
                }
            )
        )

        acquired = client.post("/bot/bot_101/hijack/acquire", json={"owner": "pytest", "lease_s": 10})
        assert acquired.status_code == 200
        hijack = acquired.json()
        assert hijack["ok"] is True
        hijack_id = hijack["hijack_id"]

        pause = _recv_until_type(worker, "control")
        assert pause["action"] == "pause"

        sent = client.post(
            f"/bot/bot_101/hijack/{hijack_id}/send",
            json={"keys": "D\r", "expect_prompt_id": "prompt.sector_command", "timeout_ms": 200},
        )
        assert sent.status_code == 200
        assert sent.json()["ok"] is True
        input_msg = _recv_until_type(worker, "input")
        assert input_msg["data"] == "D\r"

        events = client.get(f"/bot/bot_101/hijack/{hijack_id}/events", params={"after_seq": 0, "limit": 20})
        assert events.status_code == 200
        event_types = [e["type"] for e in events.json()["events"]]
        assert "hijack_acquired" in event_types
        assert "hijack_send" in event_types

        released = client.post(f"/bot/bot_101/hijack/{hijack_id}/release")
        assert released.status_code == 200
        assert released.json()["ok"] is True
        resume = _recv_until_type(worker, "control")
        assert resume["action"] == "resume"

        # Session is invalid after release.
        invalid = client.get(f"/bot/bot_101/hijack/{hijack_id}/snapshot")
        assert invalid.status_code == 404


def test_rest_hijack_send_prompt_guard_failure() -> None:
    hub = TermHub()
    app = FastAPI()
    app.include_router(hub.create_router())

    with TestClient(app) as client, client.websocket_connect("/ws/worker/bot_102/term") as worker:
        _recv_until_type(worker, "snapshot_req")
        worker.send_text(
            json.dumps(
                {
                    "type": "snapshot",
                    "screen": "Enter your choice [T] ?",
                    "prompt_detected": {"prompt_id": "prompt.port_menu"},
                    "screen_hash": "port-menu",
                }
            )
        )

        acquired = client.post("/bot/bot_102/hijack/acquire", json={"owner": "pytest", "lease_s": 10})
        assert acquired.status_code == 200
        hijack_id = acquired.json()["hijack_id"]
        _recv_until_type(worker, "control")  # pause

        guarded = client.post(
            f"/bot/bot_102/hijack/{hijack_id}/send",
            json={"keys": "D\r", "expect_prompt_id": "prompt.sector_command", "timeout_ms": 120, "poll_interval_ms": 30},
        )
        assert guarded.status_code == 409
        assert "prompt_guard_not_satisfied" in guarded.json().get("error", "")


def test_rest_hijack_lease_expiry_releases_bot() -> None:
    hub = TermHub()
    app = FastAPI()
    app.include_router(hub.create_router())

    with TestClient(app) as client, client.websocket_connect("/ws/worker/bot_103/term") as worker:
        _recv_until_type(worker, "snapshot_req")

        acquired = client.post("/bot/bot_103/hijack/acquire", json={"owner": "pytest", "lease_s": 1})
        assert acquired.status_code == 200
        hijack_id = acquired.json()["hijack_id"]
        _recv_until_type(worker, "control")  # pause

        time.sleep(1.2)

        # Heartbeat triggers expiry cleanup path and should fail for expired session.
        heartbeat = client.post(f"/bot/bot_103/hijack/{hijack_id}/heartbeat", json={"lease_s": 10})
        assert heartbeat.status_code == 404

        resume = _recv_until_type(worker, "control")
        assert resume["action"] == "resume"


def test_dashboard_ws_hijack_expires_and_auto_resumes() -> None:
    hub = TermHub(dashboard_hijack_lease_s=1)
    app = FastAPI()
    app.include_router(hub.create_router())

    with (
        TestClient(app) as client,
        client.websocket_connect("/ws/worker/bot_104/term") as worker,
        client.websocket_connect("/ws/bot/bot_104/term") as browser,
    ):
        _recv_until_type(worker, "snapshot_req")
        _recv_until_type(browser, "hello")
        _recv_until_type(browser, "hijack_state")

        browser.send_text(json.dumps({"type": "hijack_request"}))
        pause = _recv_until_type(worker, "control")
        assert pause["action"] == "pause"
        acquired_state = _recv_until_type(browser, "hijack_state")
        assert acquired_state["hijacked"] is True

        # Lease expires; next worker message cycle should trigger stale-owner cleanup.
        time.sleep(1.2)
        worker.send_text(json.dumps({"type": "term", "data": "x"}))

        resume = _recv_until_type(worker, "control")
        assert resume["action"] == "resume"

        state = _recv_until_type(browser, "hijack_state")
        assert state["hijacked"] is False
