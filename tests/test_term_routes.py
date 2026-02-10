from __future__ import annotations

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bbsbot.api.term_routes import TermHub


def _recv_until_type(ws, want_type: str, max_msgs: int = 50) -> dict:
    for _ in range(max_msgs):
        msg = json.loads(ws.receive_text())
        if msg.get("type") == want_type:
            return msg
    raise AssertionError(f"did not receive type={want_type}")


def test_term_bridge_term_fanout_and_hijack_flow() -> None:
    hub = TermHub()
    app = FastAPI()
    app.include_router(hub.create_router())

    with TestClient(app) as client, client.websocket_connect("/ws/worker/bot_001/term") as w:
        # Manager may request snapshot immediately.
        _recv_until_type(w, "snapshot_req")

        with client.websocket_connect("/ws/bot/bot_001/term") as b1:
            _recv_until_type(b1, "hello")
            _recv_until_type(b1, "hijack_state")

            # Browser connect triggers another snapshot request to worker.
            _recv_until_type(w, "snapshot_req")

            w.send_text(json.dumps({"type": "term", "data": "hello\r\n", "ts": 1.0}))
            term_msg = _recv_until_type(b1, "term")
            assert "hello" in term_msg.get("data", "")

            # Hijack: browser -> manager -> worker
            b1.send_text(json.dumps({"type": "hijack_request"}))
            ctrl = _recv_until_type(w, "control")
            assert ctrl.get("action") == "pause"

            # Input only from hijack owner
            b1.send_text(json.dumps({"type": "input", "data": "A"}))
            inp = _recv_until_type(w, "input")
            assert inp.get("data") == "A"

            # Second browser cannot hijack
            with client.websocket_connect("/ws/bot/bot_001/term") as b2:
                _recv_until_type(b2, "hello")
                _recv_until_type(b2, "hijack_state")
                b2.send_text(json.dumps({"type": "hijack_request"}))
                err = _recv_until_type(b2, "error")
                assert "Already hijacked" in (err.get("message") or "")

            # Release
            b1.send_text(json.dumps({"type": "hijack_release"}))
            ctrl2 = _recv_until_type(w, "control")
            assert ctrl2.get("action") == "resume"


def test_hijack_released_on_owner_disconnect() -> None:
    hub = TermHub()
    app = FastAPI()
    app.include_router(hub.create_router())

    with TestClient(app) as client, client.websocket_connect("/ws/worker/bot_002/term") as w:
        _recv_until_type(w, "snapshot_req")

        with client.websocket_connect("/ws/bot/bot_002/term") as b1:
            _recv_until_type(b1, "hello")
            _recv_until_type(b1, "hijack_state")
            _recv_until_type(w, "snapshot_req")

            b1.send_text(json.dumps({"type": "hijack_request"}))
            ctrl = _recv_until_type(w, "control")
            assert ctrl.get("action") == "pause"

        # Exiting context closes hijack owner; should resume
        ctrl2 = _recv_until_type(w, "control")
        assert ctrl2.get("action") == "resume"
