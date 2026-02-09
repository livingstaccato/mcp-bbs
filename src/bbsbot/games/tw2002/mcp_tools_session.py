"""Session-level TW2002 MCP tools (connect/login/join).

These tools are meant for "one-off" interactive sessions where you want to:
1) connect to a TWGS/TW2002 endpoint
2) log in
3) enter a specific Trade Wars game (by letter)

They do not start a swarm or an autonomous trading loop; they just get you
to a stable in-game command prompt so you can drive from there.
"""

from __future__ import annotations

from typing import Any

from bbsbot.games.tw2002.mcp_tools import registry
from bbsbot.logging import get_logger

log = get_logger(__name__)


def _tail_lines(screen: str, n: int = 12) -> list[str]:
    lines = [l.rstrip() for l in (screen or "").splitlines() if l.strip()]
    return lines[-n:]


def _get_active_session_id() -> str | None:
    import bbsbot.mcp.server as mcp_server

    return getattr(mcp_server, "_active_session_id", None)


def _set_active_session_id(session_id: str) -> None:
    import bbsbot.mcp.server as mcp_server

    setattr(mcp_server, "_active_session_id", session_id)


@registry.tool()
async def connect(
    host: str,
    port: int = 2002,
    cols: int = 80,
    rows: int = 25,
    term: str = "ANSI",
    send_newline: bool = True,
    reuse: bool = True,
) -> dict[str, Any]:
    """Connect to a TWGS/TW2002 endpoint and enable TW2002 prompt detection.

    This sets the active MCP session and enables learning with namespace "tw2002"
    so prompt detection loads `games/tw2002/rules.json`.
    """
    from bbsbot.mcp.server import _ensure_watch_manager, _require_knowledge_root, session_manager

    await _ensure_watch_manager()
    knowledge_root = _require_knowledge_root()

    session_id = await session_manager.create_session(
        host=host,
        port=port,
        cols=cols,
        rows=rows,
        term=term,
        send_newline=send_newline,
        reuse=reuse,
    )
    _set_active_session_id(session_id)

    # IMPORTANT: enable learning with namespace so prompt patterns auto-load.
    await session_manager.enable_learning(session_id, knowledge_root, namespace="tw2002")
    session = await session_manager.get_session(session_id)
    if session.learning:
        session.learning.set_enabled(True)

    return {"success": True, "session_id": session_id, "host": host, "port": port}


@registry.tool()
async def login(
    username: str,
    character_password: str,
    game_password: str = "game",
    game_letter: str | None = None,
) -> dict[str, Any]:
    """Log in and enter Trade Wars 2002 (joins the selected TWGS game).

    Requires an active session (use `tw2002_connect` first, or `bbs_connect`
    plus setting the learning namespace to "tw2002").

    Args:
        username: Character name/username to use
        character_password: Character password
        game_password: Private game password (if prompted)
        game_letter: Optional explicit game letter (A/B/C...). If omitted, the
            login flow will use configured/default selection logic.
    """
    from bbsbot.mcp.server import _require_knowledge_root, session_manager

    session_id = _get_active_session_id()
    if not session_id:
        return {
            "success": False,
            "error": "Not connected. Call tw2002_connect(...) or bbs_connect(...) first.",
        }

    knowledge_root = _require_knowledge_root()

    # Ensure TW2002 prompt patterns are loaded for this session.
    await session_manager.enable_learning(session_id, knowledge_root, namespace="tw2002")
    session = await session_manager.get_session(session_id)
    if session.learning:
        session.learning.set_enabled(True)

    # Get or create a bot instance attached to this session so existing TW2002 MCP tools work.
    bot = session_manager.get_bot(session_id)
    if not bot:
        from bbsbot.games.tw2002.bot import TradingBot

        bot = TradingBot(character_name=username)
        session_manager.register_bot(session_id, bot)

    # Attach session + manager onto the bot (TradingBot normally owns its own SessionManager).
    try:
        bot.session_manager = session_manager
        bot.knowledge_root = knowledge_root
        bot.session_id = session_id
        bot.session = session
        bot.character_name = username
    except Exception:
        # If this isn't a TradingBot, still attempt login via bbs_* tools instead.
        return {
            "success": False,
            "error": f"Active bot is not attachable (type={type(bot).__name__}). Disconnect and reconnect.",
        }

    # Allow explicit game selection (A/B/C...) via config hook used by login_sequence().
    try:
        bot.config.connection.game_letter = game_letter
        bot.config.connection.game_password = game_password
        bot.config.connection.character_password = character_password
        bot.config.connection.username = username
        bot.config.connection.host = session.host
        bot.config.connection.port = session.port
    except Exception:
        pass

    # Run the existing, battle-tested login flow.
    try:
        from bbsbot.games.tw2002.login import login_sequence

        await login_sequence(
            bot,
            game_password=game_password,
            character_password=character_password,
            username=username,
        )
    except Exception as exc:
        # Provide a small amount of screen context to make debugging fast.
        try:
            screen_tail = _tail_lines(session.snapshot().get("screen", ""), n=14)
        except Exception:
            screen_tail = []

        log.warning("tw2002_login_failed", error=str(exc))
        return {
            "success": False,
            "error": str(exc),
            "screen_tail": screen_tail,
        }

    # Initialize knowledge AFTER login so we can scope by detected game letter.
    resolved_game_letter = game_letter or getattr(bot, "last_game_letter", None) or getattr(
        getattr(getattr(bot, "config", None), "connection", None), "game_letter", None
    )
    try:
        bot.init_knowledge(session.host, session.port, resolved_game_letter)
    except Exception:
        pass

    return {
        "success": True,
        "session_id": session_id,
        "host": session.host,
        "port": session.port,
        "game_letter": resolved_game_letter,
        "sector": getattr(bot, "current_sector", None),
        "credits": getattr(bot, "current_credits", None),
    }
