"""Tests for TW2002 MCP takeover/hijack tools."""

from __future__ import annotations

import asyncio


def test_mcp_hijack_tools_are_registered() -> None:
    from bbsbot.games.tw2002 import mcp_tools  # noqa: F401
    from bbsbot.mcp.registry import get_manager

    manager = get_manager()
    registry = manager.get_registry("tw2002")
    assert registry is not None

    tools = registry.get_tools()
    expected = {
        "tw2002_assume_bot",
        "tw2002_assumed_bot_status",
        "tw2002_hijack_begin",
        "tw2002_hijack_heartbeat",
        "tw2002_hijack_read",
        "tw2002_hijack_send",
        "tw2002_hijack_step",
        "tw2002_hijack_release",
    }
    assert expected.issubset(set(tools))


def test_mcp_hijack_tools_use_assumed_bot(monkeypatch) -> None:
    from bbsbot.games.tw2002 import mcp_tools_control

    calls: list[tuple[str, str, dict]] = []

    def fake_manager_request(method: str, path: str, **kwargs):
        calls.append((method, path, kwargs))
        if method == "GET" and path == "/bot/bot_777/status":
            return True, {"bot_id": "bot_777", "state": "running", "strategy": "profitable_pairs", "sector": 44}
        if method == "POST" and path == "/bot/bot_777/hijack/acquire":
            body = kwargs.get("json", {})
            return True, {"ok": True, "bot_id": "bot_777", "hijack_id": "hijack_abc", "owner": body.get("owner")}
        if method == "POST" and path == "/bot/bot_777/hijack/hijack_abc/send":
            return True, {"ok": True, "bot_id": "bot_777", "hijack_id": "hijack_abc", "sent": kwargs.get("json", {}).get("keys")}
        if method == "POST" and path == "/bot/bot_777/hijack/hijack_abc/release":
            return True, {"ok": True, "bot_id": "bot_777", "hijack_id": "hijack_abc"}
        return False, {"error": f"unexpected {method} {path}"}

    monkeypatch.setattr(mcp_tools_control, "_manager_request", fake_manager_request)
    monkeypatch.setattr(mcp_tools_control, "_ASSUMED_BOT_ID", None)

    assumed = asyncio.run(mcp_tools_control.assume_bot("bot_777"))
    assert assumed["success"] is True
    assert assumed["bot_id"] == "bot_777"

    begin = asyncio.run(mcp_tools_control.hijack_begin(lease_s=45))
    assert begin["success"] is True
    assert begin["hijack_id"] == "hijack_abc"

    sent = asyncio.run(mcp_tools_control.hijack_send(hijack_id="hijack_abc", keys="T\r"))
    assert sent["success"] is True
    assert sent["sent"] == "T\r"

    released = asyncio.run(mcp_tools_control.hijack_release(hijack_id="hijack_abc"))
    assert released["success"] is True

    called_paths = [p for _, p, _ in calls]
    assert "/bot/bot_777/hijack/acquire" in called_paths
    assert "/bot/bot_777/hijack/hijack_abc/send" in called_paths
    assert "/bot/bot_777/hijack/hijack_abc/release" in called_paths
