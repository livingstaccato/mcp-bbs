from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

import structlog
from fastmcp import FastMCP

from mcp_bbs.config import get_default_knowledge_root, validate_knowledge_root
from mcp_bbs.core.session_manager import SessionManager
from mcp_bbs.learning.discovery import discover_menu
from mcp_bbs.learning.knowledge import append_md

log = structlog.get_logger()

app = FastMCP("mcp-bbs")
session_manager = SessionManager()

# Single active session (end-state: simple single-session model)
_active_session_id: str | None = None

KNOWLEDGE_ROOT = validate_knowledge_root(get_default_knowledge_root())


def _parse_json(value: str, label: str) -> list[dict[str, str]]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON for {label}: {exc}") from exc
    if not isinstance(data, list):
        raise RuntimeError(f"{label} JSON must be a list of objects.")
    return data


def _require_session() -> str:
    """Get active session ID or raise error."""
    if not _active_session_id:
        raise RuntimeError("Not connected. Call bbs_connect first.")
    return _active_session_id


async def _get_session() -> tuple[str, Any]:
    """Get active session and its ID.

    Returns:
        Tuple of (session_id, session)
    """
    sid = _require_session()
    session = await session_manager.get_session(sid)
    return sid, session


async def _ensure_learning(session: Any, sid: str) -> Any:
    """Ensure learning is enabled for session and return engine.

    Args:
        session: Session object
        sid: Session ID

    Returns:
        LearningEngine instance
    """
    if not session.learning:
        await session_manager.enable_learning(sid, KNOWLEDGE_ROOT)
    return session.learning


def _parse_json_dict(value: str, label: str) -> dict[str, Any]:
    """Parse and validate JSON dict.

    Args:
        value: JSON string
        label: Label for error messages

    Returns:
        Parsed dict
    """
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON for {label}: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"{label} JSON must be an object.")
    return data


@app.tool()
async def bbs_connect(
    host: str,
    port: int = 23,
    cols: int = 80,
    rows: int = 25,
    term: str = "ANSI",
    send_newline: bool = True,
    reuse: bool = True,
) -> str:
    """Connect to a BBS via telnet (reuse existing session by default)."""
    global _active_session_id

    try:
        session_id = await session_manager.create_session(
            host=host,
            port=port,
            cols=cols,
            rows=rows,
            term=term,
            send_newline=send_newline,
            reuse=reuse,
        )

        _active_session_id = session_id

        # Enable learning by default
        await session_manager.enable_learning(session_id, KNOWLEDGE_ROOT)
        session = await session_manager.get_session(session_id)
        if session.learning:
            session.learning.set_enabled(True)

        return "ok"
    except Exception as e:
        log.error("connect_failed", error=str(e))
        raise


@app.tool()
async def bbs_read(timeout_ms: int = 250, max_bytes: int = 8192) -> dict[str, Any]:
    """Read output and return the current screen buffer."""
    _, session = await _get_session()
    return await session.read(timeout_ms, max_bytes)


@app.tool()
async def bbs_read_until_nonblank(
    timeout_ms: int = 5000,
    interval_ms: int = 250,
    max_bytes: int = 8192,
) -> dict[str, Any]:
    """Read until the screen buffer contains non-whitespace content."""
    _, session = await _get_session()

    deadline = time.monotonic() + timeout_ms / 1000
    last_snapshot: dict[str, Any] = {}

    while time.monotonic() < deadline:
        last_snapshot = await session.read(interval_ms, max_bytes)
        if last_snapshot.get("disconnected"):
            return last_snapshot
        screen = last_snapshot.get("screen", "")
        if screen and screen.strip():
            return last_snapshot

    return last_snapshot or await session.read(interval_ms, max_bytes)


@app.tool()
async def bbs_read_until_pattern(
    pattern: str,
    timeout_ms: int = 8000,
    interval_ms: int = 250,
    max_bytes: int = 8192,
) -> dict[str, Any]:
    """Read until the screen matches a regex pattern."""
    _, session = await _get_session()

    deadline = time.monotonic() + timeout_ms / 1000
    regex = re.compile(pattern, re.MULTILINE)
    last_snapshot: dict[str, Any] = {}

    while time.monotonic() < deadline:
        last_snapshot = await session.read(interval_ms, max_bytes)
        if last_snapshot.get("disconnected"):
            last_snapshot["matched"] = False
            return last_snapshot
        screen = last_snapshot.get("screen", "")
        if screen and regex.search(screen):
            last_snapshot["matched"] = True
            return last_snapshot

    if last_snapshot:
        last_snapshot["matched"] = False
        return last_snapshot

    result = await session.read(interval_ms, max_bytes)
    result["matched"] = False
    return result


@app.tool()
async def bbs_send(keys: str) -> str:
    """Send keystrokes (include control codes like \\r or \\x1b).

    Note: MCP's JSON parser already handles escape sequences, so strings arrive
    with actual control characters. No additional decoding needed.
    """
    _, session = await _get_session()

    log.debug("bbs_send", keys=keys, keys_len=len(keys))

    try:
        await session.send(keys)
        return "ok"
    except ConnectionError:
        return "disconnected"


@app.tool()
async def bbs_set_size(cols: int, rows: int) -> str:
    """Set terminal size and send NAWS."""
    _, session = await _get_session()
    await session.set_size(cols, rows)
    return "ok"


@app.tool()
async def bbs_disconnect() -> str:
    """Disconnect from the BBS."""
    global _active_session_id

    if not _active_session_id:
        return "ok"

    try:
        await session_manager.close_session(_active_session_id)
    except ValueError:
        # Session already closed
        pass
    finally:
        _active_session_id = None

    return "ok"


@app.tool()
async def bbs_log_start(path: str) -> str:
    """Start logging session activity to a JSONL file."""
    sid = _require_session()
    await session_manager.enable_logging(sid, path)
    return "ok"


@app.tool()
async def bbs_log_stop() -> str:
    """Stop logging session activity."""
    sid = _require_session()
    await session_manager.disable_logging(sid)
    return "ok"


@app.tool()
async def bbs_log_note(data_json: str) -> str:
    """Append a structured note into the JSONL session log."""
    data = _parse_json_dict(data_json, "note")
    _, session = await _get_session()

    if session.logger:
        await session.logger.log_event("note", data)

    return "ok"


@app.tool()
async def bbs_auto_learn_enable(enabled: bool = True) -> str:
    """Enable or disable auto-learn rules on every screen snapshot."""
    sid, session = await _get_session()
    learning = await _ensure_learning(session, sid)
    learning.set_enabled(enabled)
    return "ok"


@app.tool()
async def bbs_auto_learn_prompts(rules_json: str) -> str:
    """Set auto-learn prompt rules from JSON."""
    rules = _parse_json(rules_json, "prompt rules")
    sid, session = await _get_session()
    learning = await _ensure_learning(session, sid)
    learning.set_prompt_rules(rules)
    return "ok"


@app.tool()
async def bbs_auto_learn_menus(rules_json: str) -> str:
    """Set auto-learn menu rules from JSON."""
    rules = _parse_json(rules_json, "menu rules")
    sid, session = await _get_session()
    learning = await _ensure_learning(session, sid)
    learning.set_menu_rules(rules)
    return "ok"


@app.tool()
async def bbs_auto_learn_discover(enabled: bool = True) -> str:
    """Enable or disable auto-discovery of menus."""
    sid, session = await _get_session()
    learning = await _ensure_learning(session, sid)
    learning.set_auto_discover(enabled)
    return "ok"


@app.tool()
async def bbs_auto_learn_namespace(namespace: str | None = None) -> str:
    """Set the auto-learn namespace (game folder name) or clear to use shared."""
    sid, session = await _get_session()

    if not session.learning:
        await session_manager.enable_learning(sid, KNOWLEDGE_ROOT, namespace)
    else:
        session.learning.set_namespace(namespace)

    return "ok"


@app.tool()
async def bbs_get_knowledge_root() -> str:
    """Return the current knowledge root path."""
    return str(KNOWLEDGE_ROOT)


@app.tool()
async def bbs_set_knowledge_root(path: str) -> str:
    """Override the knowledge root path at runtime."""
    global KNOWLEDGE_ROOT
    KNOWLEDGE_ROOT = validate_knowledge_root(Path(path))

    # Update existing session's learning if present
    if _active_session_id:
        try:
            session = await session_manager.get_session(_active_session_id)
            if session.learning:
                namespace = session.learning._namespace
                await session_manager.enable_learning(_active_session_id, KNOWLEDGE_ROOT, namespace)
        except ValueError:
            # Session closed, that's fine
            pass

    return "ok"


@app.tool()
async def bbs_status() -> dict[str, Any]:
    """Return current session status."""
    if not _active_session_id:
        return {
            "connected": False,
            "session_id": None,
            "host": None,
            "port": None,
        }

    try:
        session = await session_manager.get_session(_active_session_id)
        status = session.get_status()

        # Add learning status
        if session.learning:
            status["learning"] = {
                "enabled": session.learning.enabled,
                "auto_discover": session.learning._auto_discover,
                "namespace": session.learning._namespace,
                "base_dir": str(session.learning.get_base_dir()),
            }

        # Add logging status
        if session.logger:
            status["log_path"] = str(session.logger._log_path)

        return status
    except ValueError:
        return {
            "connected": False,
            "session_id": None,
            "host": None,
            "port": None,
        }


@app.tool()
async def bbs_set_context(context_json: str) -> str:
    """Set structured context that is embedded in JSONL logs."""
    data = _parse_json_dict(context_json, "context")
    _, session = await _get_session()

    if session.logger:
        session.logger.set_context(data)

    return "ok"


@app.tool()
async def bbs_keepalive(interval_s: float | None = 30.0, keys: str = "\r") -> str:
    """Configure keepalive interval in seconds (<=0 disables)."""
    # Note: Keepalive functionality needs to be re-implemented for session-based architecture
    # For now, return ok but log that it's not yet implemented
    log.warning("keepalive_not_implemented", message="Keepalive not yet implemented in new architecture")
    return "ok"


@app.tool()
async def bbs_discover_menu(screen_override: str = "") -> dict[str, Any]:
    """Discover menu options from a screen buffer.

    If screen_override is not provided, reads current screen with minimal timeout.
    """
    if screen_override:
        screen = screen_override
    else:
        # Read with minimal timeout to get current screen state
        _, session = await _get_session()
        snapshot = await session.read(timeout_ms=10, max_bytes=0)
        screen = snapshot.get("screen", "")

    return discover_menu(screen)


@app.tool()
async def bbs_wake(
    timeout_ms: int = 5000,
    interval_ms: int = 250,
    max_bytes: int = 8192,
    keys_sequence: str = "\r\n|\r|\n| ",
) -> dict[str, Any]:
    """Send a sequence of wake keys until the screen changes or becomes nonblank."""
    _, session = await _get_session()

    sequence = [item for item in keys_sequence.split("|") if item]

    last_snapshot = await session.read(interval_ms, max_bytes)
    last_hash = last_snapshot.get("screen_hash", "")

    for keys in sequence:
        await session.send(keys)
        snapshot = await bbs_read_until_nonblank(timeout_ms, interval_ms, max_bytes)
        screen_hash = snapshot.get("screen_hash", "")
        if screen_hash and screen_hash != last_hash:
            return snapshot
        last_snapshot = snapshot
        last_hash = screen_hash

    return last_snapshot


def _get_learn_base_dir() -> Path:
    """Get learning base directory for current session."""
    if _active_session_id:
        try:
            import asyncio

            loop = asyncio.get_event_loop()
            session = loop.run_until_complete(session_manager.get_session(_active_session_id))
            if session.learning:
                return session.learning.get_base_dir()
        except Exception:
            pass
    return KNOWLEDGE_ROOT / "shared" / "bbs"


@app.tool()
async def bbs_learn_menu(
    menu_id: str,
    title: str,
    entry_prompt: str,
    exit_keys: str,
    observed_screen: str,
    options_md: str,
    notes: str = "",
    log_refs: str = "",
) -> str:
    """Append a menu entry to shared menu-map.md."""
    body = "\n".join(
        [
            "",
            f"### Menu: {menu_id}",
            "",
            f"- Title (Observed): {title}",
            f"- Entry Prompt: {entry_prompt}",
            f"- Exit Keys: {exit_keys}",
            "",
            "Observed Screen:",
            "````",
            f"{observed_screen}",
            "````",
            "",
            "Options:",
            f"{options_md}",
            "",
            "Notes:",
            f"{notes}",
            "",
            "Log References:",
            f"{log_refs}",
            "",
        ]
    )
    base_dir = _get_learn_base_dir()
    return await append_md(base_dir / "menu-map.md", "Menu Map (Shared)", body, KNOWLEDGE_ROOT)


@app.tool()
async def bbs_learn_prompt(
    prompt_id: str,
    raw_text: str,
    regex: str,
    input_type: str,
    example_input: str,
    notes: str = "",
    log_refs: str = "",
) -> str:
    """Append a prompt entry to shared prompt-catalog.md."""
    body = "\n".join(
        [
            "",
            f"### Prompt: {prompt_id}",
            "",
            "- Raw Text:",
            "````",
            f"{raw_text}",
            "````",
            "- Regex:",
            "````",
            f"{regex}",
            "````",
            f"- Input Type: {input_type}",
            f"- Example Input: {example_input}",
            f"- Notes: {notes}",
            "- Log References:",
            f"  - {log_refs}",
            "",
        ]
    )
    base_dir = _get_learn_base_dir()
    return await append_md(base_dir / "prompt-catalog.md", "Prompt Catalog (Shared)", body, KNOWLEDGE_ROOT)


@app.tool()
async def bbs_learn_flow(
    flow_id: str,
    from_menu: str,
    to_menu: str,
    input_keys: str,
    notes: str = "",
    log_refs: str = "",
) -> str:
    """Append a flow note entry to shared flow-notes.md."""
    body = "\n".join(
        [
            "",
            f"### Flow: {flow_id}",
            "",
            f"- From Menu ID: {from_menu}",
            f"- To Menu ID: {to_menu}",
            f"- Input/Keys: {input_keys}",
            f"- Notes: {notes}",
            "- Log References:",
            f"  - {log_refs}",
            "",
        ]
    )
    base_dir = _get_learn_base_dir()
    return await append_md(base_dir / "flow-notes.md", "Flow Notes (Shared)", body, KNOWLEDGE_ROOT)


@app.tool()
async def bbs_learn_replay(
    date: str,
    game: str,
    host: str,
    log_path: str,
    notes: str = "",
) -> str:
    """Append a replay session entry to shared replay-notes.md."""
    body = "\n".join(
        [
            "",
            f"### Session: {date} {game}",
            "",
            f"- Date: {date}",
            f"- Game: {game}",
            f"- Host: {host}",
            f"- Log: {log_path}",
            f"- Notes: {notes}",
            "",
        ]
    )
    base_dir = _get_learn_base_dir()
    return await append_md(base_dir / "replay-notes.md", "Replay Notes (Shared)", body, KNOWLEDGE_ROOT)


@app.tool()
async def bbs_learn_state(
    state_id: str,
    description: str,
    entry_prompt: str,
    exit_keys: str,
    notes: str = "",
) -> str:
    """Append a state entry to shared state-model.md."""
    body = f"\n| {state_id} | {description} | {entry_prompt} | {exit_keys} | {notes} |\n"
    base_dir = _get_learn_base_dir()
    return await append_md(base_dir / "state-model.md", "State Model (Shared)", body, KNOWLEDGE_ROOT)


def run() -> None:
    app.run()
