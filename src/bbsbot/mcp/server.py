from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, cast

import structlog
from fastmcp import FastMCP

from bbsbot.paths import find_repo_games_root, validate_knowledge_root
from bbsbot.settings import Settings
from bbsbot.core.session_manager import SessionManager
from bbsbot.watch import WatchManager, watch_settings
from bbsbot.learning.discovery import discover_menu
from bbsbot.learning.knowledge import append_md

# Configure structlog to write to stderr (MCP uses stdout for JSON-RPC)
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer(),
    ],
    logger_factory=structlog.PrintLoggerFactory(file=sys.stderr),
)

log = structlog.get_logger()


def decode_escape_sequences(s: str) -> str:
    """Decode common escape sequences in a string.

    Converts literal backslash sequences to actual control characters:
    - \\r -> CR (0x0d)
    - \\n -> LF (0x0a)
    - \\t -> TAB (0x09)
    - \\x## -> hex byte
    - \\\\ -> single backslash

    This is needed because MCP JSON transport may not decode escape sequences.
    """
    # Use a regex to find and replace escape sequences
    def replace_escape(match: re.Match[str]) -> str:
        seq = match.group(0)
        if seq == "\\r":
            return "\r"
        elif seq == "\\n":
            return "\n"
        elif seq == "\\t":
            return "\t"
        elif seq == "\\\\":
            return "\\"
        elif seq.startswith("\\x") and len(seq) == 4:
            try:
                return chr(int(seq[2:], 16))
            except ValueError:
                return seq
        return seq

    # Match \r, \n, \t, \\, or \xHH
    pattern = r"\\r|\\n|\\t|\\\\|\\x[0-9a-fA-F]{2}"
    return re.sub(pattern, replace_escape, s)


app = FastMCP("bbsbot")
session_manager = SessionManager()
watch_manager: WatchManager | None = None
_watch_registered = False

# Single active session (end-state: simple single-session model)
_active_session_id: str | None = None

KNOWLEDGE_ROOT: Path | None = None


def create_app(settings: Settings) -> FastMCP:
    """Configure globals and return the FastMCP app."""
    global KNOWLEDGE_ROOT
    KNOWLEDGE_ROOT = validate_knowledge_root(settings.knowledge_root)
    return app


def _attach_watch(session: Any) -> None:
    if watch_manager is not None:
        watch_manager.attach_session(session)


async def _ensure_watch_manager() -> None:
    global watch_manager, _watch_registered
    if not watch_settings.enabled:
        return
    if watch_manager is None:
        watch_manager = WatchManager()
        await watch_manager.start()
    if not _watch_registered:
        session_manager.register_session_callback(_attach_watch)
        _watch_registered = True


def _parse_json(value: str, label: str) -> list[dict[str, str]]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON for {label}: {exc}") from exc
    if not isinstance(data, list):
        raise RuntimeError(f"{label} JSON must be a list of objects.")
    return data


def _require_knowledge_root() -> Path:
    if KNOWLEDGE_ROOT is None:
        raise RuntimeError("Knowledge root not configured. Start the server via `bbsbot serve`.")
    return KNOWLEDGE_ROOT


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
        await session_manager.enable_learning(sid, _require_knowledge_root())
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

    await _ensure_watch_manager()
    _require_knowledge_root()
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
        await session_manager.enable_learning(session_id, _require_knowledge_root())
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
    _require_knowledge_root()
    _, session = await _get_session()
    return cast(dict[str, Any], await session.read(timeout_ms, max_bytes))


@app.tool()
async def bbs_read_until_nonblank(
    timeout_ms: int = 5000,
    interval_ms: int = 250,
    max_bytes: int = 8192,
) -> dict[str, Any]:
    """Read until the screen buffer contains non-whitespace content."""
    _require_knowledge_root()
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
    _require_knowledge_root()
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

    result = cast(dict[str, Any], await session.read(interval_ms, max_bytes))
    result["matched"] = False
    return result


@app.tool()
async def bbs_wait_for_prompt(
    prompt_id: str | None = None,
    timeout_ms: int = 10000,
    interval_ms: int = 250,
) -> dict[str, Any]:
    """Wait until a known prompt is detected or timeout.

    Blocks until prompt detection occurs. Returns rich metadata including:
    - matched: True if prompt detected, False if timeout
    - prompt_id: ID of detected prompt (if matched)
    - input_type: "single_key", "multi_key", or "any_key"
    - is_idle: True if screen has been stable for idle threshold
    - screen: Current screen text
    - screen_hash: Hash of screen
    - captured_at: Unix timestamp
    - time_since_last_change: Seconds since screen last changed
    - kv_data: Extracted key-value data (if configured)

    Args:
        prompt_id: Specific prompt ID to wait for (None = any prompt)
        timeout_ms: Maximum wait time in milliseconds
        interval_ms: Polling interval in milliseconds

    Returns:
        Dictionary with detection results and screen snapshot
    """
    _require_knowledge_root()
    _, session = await _get_session()
    deadline = time.monotonic() + timeout_ms / 1000

    while time.monotonic() < deadline:
        snapshot = await session.read(interval_ms, 8192)

        # Check for disconnection
        if snapshot.get("disconnected"):
            return {
                "matched": False,
                "prompt_id": None,
                "disconnected": True,
                "screen": "",
            }

        # Check for prompt detection
        if "prompt_detected" in snapshot:
            detected = snapshot["prompt_detected"]
            detected_id = detected.get("prompt_id")

            # Check if specific prompt ID matches (or any prompt if None)
            if prompt_id is None or detected_id == prompt_id:
                return {
                    "matched": True,
                    "prompt_id": detected_id,
                    "input_type": detected.get("input_type", "multi_key"),
                    "is_idle": detected.get("is_idle", False),
                    "screen": snapshot.get("screen", ""),
                    "screen_hash": snapshot.get("screen_hash", ""),
                    "captured_at": snapshot.get("captured_at", time.time()),
                    "time_since_last_change": snapshot.get("time_since_last_change", 0.0),
                    "kv_data": detected.get("kv_data"),
                }

    # Timeout - return last snapshot
    return {
        "matched": False,
        "prompt_id": None,
        "screen": snapshot.get("screen", "") if snapshot else "",
    }


@app.tool()
async def bbs_send(keys: str) -> str:
    """Send keystrokes (include control codes like \\r or \\x1b).

    Escape sequences are decoded before sending:
    - \\r -> carriage return
    - \\n -> line feed
    - \\t -> tab
    - \\x## -> hex byte (e.g., \\x1b for ESC)
    - \\\\ -> literal backslash
    """
    _, session = await _get_session()

    # Decode escape sequences (e.g., literal "\\r" -> actual CR)
    decoded_keys = decode_escape_sequences(keys)

    log.debug("bbs_send", keys_raw=keys, keys_decoded=repr(decoded_keys), keys_len=len(decoded_keys))

    normalized = decoded_keys.replace("\r\n", "\n")
    newline_count = normalized.count("\n") + normalized.count("\r")
    if newline_count > 1:
        return "error: multiple newline sequences in one send; send one prompt response at a time"
    if ("\n" in normalized or "\r" in normalized) and len(normalized.strip("\r\n")) > 0:
        if not (normalized.endswith("\n") or normalized.endswith("\r")):
            return "error: newline must be the final character in a send"

    if session.is_awaiting_read():
        return "error: send blocked until a read occurs (one prompt -> one input -> read)"

    try:
        await session.send(decoded_keys)
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
        await session_manager.enable_learning(sid, _require_knowledge_root(), namespace)
    else:
        session.learning.set_namespace(namespace)

    return "ok"


@app.tool()
async def bbs_get_knowledge_root() -> str:
    """Return the current knowledge root path."""
    return str(_require_knowledge_root())


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
                await session_manager.enable_learning(_active_session_id, _require_knowledge_root(), namespace)
        except ValueError:
            # Session closed, that's fine
            pass

    return "ok"


@app.tool()
async def bbs_load_prompts_json(namespace: str | None = None) -> dict[str, Any]:
    """Reload prompt patterns from JSON file.

    Args:
        namespace: Game namespace to load patterns from (None = current session namespace)

    Returns:
        Dictionary with loaded patterns count and metadata
    """
    sid, session = await _get_session()
    learning = await _ensure_learning(session, sid)

    # Use provided namespace or current session namespace
    target_namespace = namespace or learning._namespace

    if not target_namespace:
        return {
            "success": False,
            "error": "No namespace specified and session has no namespace",
            "patterns_loaded": 0,
        }

    repo_games_root = find_repo_games_root()
    if repo_games_root:
        rules_file = repo_games_root / target_namespace / "rules.json"
        patterns_file = repo_games_root / target_namespace / "prompts.json"
    else:
        knowledge_root = _require_knowledge_root()
        rules_file = knowledge_root / "games" / target_namespace / "rules.json"
        patterns_file = knowledge_root / "games" / target_namespace / "prompts.json"

    try:
        if rules_file.exists():
            from bbsbot.learning.rules import RuleSet

            rules = RuleSet.from_json_file(rules_file)
            patterns = rules.to_prompt_patterns()
            metadata = {"game": rules.game, "version": rules.version, **rules.metadata}
            source_path = rules_file
        elif patterns_file.exists():
            data = json.loads(patterns_file.read_text())
            patterns = data.get("prompts", [])
            metadata = data.get("metadata", {})
            source_path = patterns_file
        else:
            return {
                "success": False,
                "error": f"Rules file not found: {rules_file}",
                "patterns_loaded": 0,
            }

        # Reload patterns in detector
        if learning._prompt_detector:
            learning._prompt_detector.reload_patterns(patterns)
        else:
            from bbsbot.learning.detector import PromptDetector

            learning._prompt_detector = PromptDetector(patterns)

        return {
            "success": True,
            "patterns_loaded": len(patterns),
            "namespace": target_namespace,
            "file_path": str(source_path),
            "metadata": metadata,
        }
    except (json.JSONDecodeError, OSError) as e:
        return {
            "success": False,
            "error": f"Failed to load patterns: {e}",
            "patterns_loaded": 0,
        }


@app.tool()
async def bbs_save_prompt_pattern(pattern_json: str) -> dict[str, Any]:
    """Append a new prompt pattern to the JSON file.

    Args:
        pattern_json: JSON string with pattern data (id, regex, input_type, etc.)

    Returns:
        Dictionary with save status and file path
    """
    sid, session = await _get_session()
    learning = await _ensure_learning(session, sid)

    if not learning._namespace:
        return {
            "success": False,
            "error": "No namespace set - cannot save pattern",
        }

    try:
        pattern = _parse_json_dict(pattern_json, "pattern")

        # Validate required fields
        if "id" not in pattern or "regex" not in pattern:
            return {
                "success": False,
                "error": "Pattern must have 'id' and 'regex' fields",
            }

        patterns_file = _require_knowledge_root() / "games" / learning._namespace / "prompts.json"

        # Load existing patterns or create new file
        if patterns_file.exists():
            data = json.loads(patterns_file.read_text())
            patterns = data.get("prompts", [])
            metadata = data.get("metadata", {})
        else:
            patterns = []
            metadata = {
                "game": learning._namespace,
                "description": f"{learning._namespace} prompt patterns",
                "version": "1.0",
            }

        # Check for duplicate ID
        if any(p.get("id") == pattern["id"] for p in patterns):
            return {
                "success": False,
                "error": f"Pattern with id '{pattern['id']}' already exists",
            }

        # Append new pattern
        patterns.append(pattern)
        metadata["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # Save back to file
        patterns_file.parent.mkdir(parents=True, exist_ok=True)
        patterns_file.write_text(
            json.dumps({"prompts": patterns, "metadata": metadata}, indent=2) + "\n"
        )

        # Reload patterns in detector
        if learning._prompt_detector:
            learning._prompt_detector.add_pattern(pattern)

        return {
            "success": True,
            "pattern_id": pattern["id"],
            "file_path": str(patterns_file),
            "total_patterns": len(patterns),
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to save pattern: {e}",
        }


@app.tool()
async def bbs_set_screen_saving(enabled: bool = True) -> str:
    """Enable or disable saving screens to disk.

    Args:
        enabled: Whether to save screens

    Returns:
        Status message
    """
    sid, session = await _get_session()
    learning = await _ensure_learning(session, sid)
    learning.set_screen_saving(enabled)
    return f"Screen saving {'enabled' if enabled else 'disabled'}"


@app.tool()
async def bbs_get_screen_saver_status() -> dict[str, Any]:
    """Get screen saver status including saved count and directory.

    Returns:
        Dictionary with screen saver status
    """
    sid, session = await _get_session()
    learning = await _ensure_learning(session, sid)
    return learning.get_screen_saver_status()


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
            learning_status = {
                "enabled": session.learning.enabled,
                "auto_discover": session.learning._auto_discover,
                "namespace": session.learning._namespace,
                "base_dir": str(session.learning.get_base_dir()),
            }

            # Add prompt detection info
            if session.learning._prompt_detector:
                learning_status["prompt_detection"] = {
                    "patterns_loaded": len(session.learning._prompt_detector._patterns),
                    "idle_threshold_seconds": session.learning._idle_threshold_seconds,
                }

            # Add buffer info
            if session.learning._buffer_manager:
                buffer_mgr = session.learning._buffer_manager
                recent_screens = buffer_mgr.get_recent(n=1)
                learning_status["screen_buffer"] = {
                    "size": len(buffer_mgr._buffer),
                    "max_size": buffer_mgr._buffer.maxlen,
                    "is_idle": buffer_mgr.detect_idle_state() if recent_screens else False,
                    "last_change_seconds_ago": (
                        recent_screens[0].time_since_last_change if recent_screens else 0.0
                    ),
                }

            # Add screen saver info
            if session.learning._screen_saver:
                learning_status["screen_saver"] = session.learning.get_screen_saver_status()

            status["learning"] = learning_status

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
    sid, session = await _get_session()
    result = cast(str, await session.keepalive.configure(interval_s, keys))
    log.info("keepalive_configured", session_id=sid, interval_s=interval_s, keys=repr(keys))
    return result


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

    last_snapshot = cast(dict[str, Any], await session.read(interval_ms, max_bytes))
    last_hash = last_snapshot.get("screen_hash", "")

    for keys in sequence:
        await session.send(keys)

        # Inline read_until_nonblank logic
        deadline = time.monotonic() + timeout_ms / 1000
        snapshot: dict[str, Any] = {}

        while time.monotonic() < deadline:
            snapshot = await session.read(interval_ms, max_bytes)
            if snapshot.get("disconnected"):
                break
            screen = snapshot.get("screen", "")
            if screen and screen.strip():
                break

        if not snapshot:
            snapshot = await session.read(interval_ms, max_bytes)

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
    return _require_knowledge_root() / "shared" / "bbs"


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
    return await append_md(base_dir / "menu-map.md", "Menu Map (Shared)", body, _require_knowledge_root())


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
    return await append_md(base_dir / "prompt-catalog.md", "Prompt Catalog (Shared)", body, _require_knowledge_root())


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
    return await append_md(base_dir / "flow-notes.md", "Flow Notes (Shared)", body, _require_knowledge_root())


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
    return await append_md(base_dir / "replay-notes.md", "Replay Notes (Shared)", body, _require_knowledge_root())


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
    return await append_md(base_dir / "state-model.md", "State Model (Shared)", body, _require_knowledge_root())


def run(settings: Settings | None = None) -> None:
    create_app(settings or Settings()).run()
