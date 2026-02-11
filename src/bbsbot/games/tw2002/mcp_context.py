"""Shared context helpers for TW2002 MCP tools."""

from __future__ import annotations

from typing import Any


def get_active_session_id() -> str | None:
    """Return currently selected MCP session ID, if any."""
    import bbsbot.mcp.server as mcp_server

    return getattr(mcp_server, "_active_session_id", None)


def set_active_session_id(session_id: str) -> None:
    """Set currently selected MCP session ID."""
    import bbsbot.mcp.server as mcp_server

    mcp_server._active_session_id = session_id


def resolve_active_bot() -> tuple[Any | None, str | None, str | None]:
    """Resolve active bot and session deterministically.

    Resolution order:
    1) Explicit active session (`_active_session_id`) if a bot is attached.
    2) Single attached bot across all sessions.
    3) Error if zero or multiple candidate bots.
    """
    import bbsbot.mcp.server as mcp_server

    session_manager = mcp_server.session_manager
    active_sid = get_active_session_id()
    if active_sid:
        bot = session_manager.get_bot(active_sid)
        if bot is not None:
            return bot, active_sid, None

    bot_map = getattr(session_manager, "_bots", {}) or {}
    candidates = [(sid, bot) for sid, bot in bot_map.items() if bot is not None]
    if not candidates:
        # Back-compat for tests/stubs that only provide `_sessions` + `get_bot`.
        for sid in list(getattr(session_manager, "_sessions", []) or []):
            bot = session_manager.get_bot(sid)
            if bot is not None:
                candidates.append((sid, bot))
    if not candidates:
        return None, None, "No active bot found. Connect/login first."
    if len(candidates) == 1:
        sid, bot = candidates[0]
        return bot, sid, None

    return (
        None,
        None,
        (
            "Multiple bot sessions are active. "
            "Call tw2002_list_sessions() and tw2002_set_active_session(session_id)."
        ),
    )


def list_bot_sessions() -> list[dict[str, Any]]:
    """List MCP sessions with bot attachment metadata."""
    import bbsbot.mcp.server as mcp_server

    session_manager = mcp_server.session_manager
    active_sid = get_active_session_id()
    sessions = session_manager.list_sessions()
    out: list[dict[str, Any]] = []
    for sess in sessions:
        sid = str(sess.get("session_id") or "")
        bot = session_manager.get_bot(sid) if sid else None
        out.append(
            {
                "session_id": sid,
                "active": sid == active_sid,
                "host": sess.get("host"),
                "port": sess.get("port"),
                "connected": bool(sess.get("connected")),
                "bot_attached": bot is not None,
                "bot_id": getattr(bot, "bot_id", None) if bot is not None else None,
                "character_name": getattr(bot, "character_name", None) if bot is not None else None,
            }
        )
    return out
