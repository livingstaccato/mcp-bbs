from __future__ import annotations

import json
from typing import Any

import structlog
from fastmcp import FastMCP

from mcp_bbs.config import get_default_knowledge_root, validate_knowledge_root
from mcp_bbs.discover import discover_menu
from mcp_bbs.learn import append_md
from mcp_bbs.telnet import TelnetClient

log = structlog.get_logger()

app = FastMCP("mcp-bbs")
client = TelnetClient()

KNOWLEDGE_ROOT = validate_knowledge_root(get_default_knowledge_root())
client.set_knowledge_root(str(KNOWLEDGE_ROOT))
client.set_auto_learn(True)


def _parse_json(value: str, label: str) -> list[dict[str, str]]:
    try:
        data = json.loads(value)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON for {label}: {exc}") from exc
    if not isinstance(data, list):
        raise RuntimeError(f"{label} JSON must be a list of objects.")
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
    return await client.connect(host, port, cols, rows, term, send_newline, reuse)


@app.tool()
async def bbs_read(timeout_ms: int = 250, max_bytes: int = 8192) -> dict[str, Any]:
    """Read output and return the current screen buffer."""
    return await client.read(timeout_ms, max_bytes)


@app.tool()
async def bbs_read_until_nonblank(
    timeout_ms: int = 5000,
    interval_ms: int = 250,
    max_bytes: int = 8192,
) -> dict[str, Any]:
    """Read until the screen buffer contains non-whitespace content."""
    return await client.read_until_nonblank(timeout_ms, interval_ms, max_bytes)


@app.tool()
async def bbs_read_until_pattern(
    pattern: str,
    timeout_ms: int = 8000,
    interval_ms: int = 250,
    max_bytes: int = 8192,
) -> dict[str, Any]:
    """Read until the screen matches a regex pattern."""
    return await client.read_until_pattern(pattern, timeout_ms, interval_ms, max_bytes)


@app.tool()
async def bbs_send(keys: str) -> str:
    """Send keystrokes (include control codes like \r or \x1b)."""
    # Decode escape sequences like \r, \n, \x1b to actual control characters
    # This matches the pattern in expect_runner.py
    decoded_keys = keys.encode("utf-8").decode("unicode_escape")
    log.debug(
        "bbs_send",
        original=keys,
        original_len=len(keys),
        decoded=decoded_keys,
        decoded_len=len(decoded_keys),
    )
    return await client.send(decoded_keys)


@app.tool()
async def bbs_set_size(cols: int, rows: int) -> str:
    """Set terminal size and send NAWS."""
    return await client.set_size(cols, rows)


@app.tool()
async def bbs_disconnect() -> str:
    """Disconnect from the BBS."""
    return await client.disconnect()


@app.tool()
async def bbs_log_start(path: str) -> str:
    """Start logging session activity to a JSONL file."""
    return client.log_start(path)


@app.tool()
async def bbs_log_stop() -> str:
    """Stop logging session activity."""
    return client.log_stop()


@app.tool()
async def bbs_log_note(data_json: str) -> str:
    """Append a structured note into the JSONL session log."""
    try:
        data = json.loads(data_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON for note: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Note JSON must be an object.")
    return client.log_note(data)


@app.tool()
async def bbs_auto_learn_enable(enabled: bool = True) -> str:
    """Enable or disable auto-learn rules on every screen snapshot."""
    return client.set_auto_learn(enabled)


@app.tool()
async def bbs_auto_learn_prompts(rules_json: str) -> str:
    """Set auto-learn prompt rules from JSON."""
    rules = _parse_json(rules_json, "prompt rules")
    return client.set_auto_prompt_rules(rules)


@app.tool()
async def bbs_auto_learn_menus(rules_json: str) -> str:
    """Set auto-learn menu rules from JSON."""
    rules = _parse_json(rules_json, "menu rules")
    return client.set_auto_menu_rules(rules)


@app.tool()
async def bbs_auto_learn_discover(enabled: bool = True) -> str:
    """Enable or disable auto-discovery of menus."""
    return client.set_auto_discover_menus(enabled)


@app.tool()
async def bbs_auto_learn_namespace(namespace: str | None = None) -> str:
    """Set the auto-learn namespace (game folder name) or clear to use shared."""
    return client.set_learn_namespace(namespace)


@app.tool()
async def bbs_get_knowledge_root() -> str:
    """Return the current knowledge root path."""
    return client.get_knowledge_root()


@app.tool()
async def bbs_set_knowledge_root(path: str) -> str:
    """Override the knowledge root path at runtime."""
    return client.set_knowledge_root(path)


@app.tool()
async def bbs_status() -> dict[str, Any]:
    """Return current session status."""
    return client.status()


@app.tool()
async def bbs_set_context(context_json: str) -> str:
    """Set structured context that is embedded in JSONL logs."""
    try:
        data = json.loads(context_json)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON for context: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("Context JSON must be an object.")
    return client.set_context(data)


@app.tool()
async def bbs_keepalive(interval_s: float | None = 30.0, keys: str = "\r") -> str:
    """Configure keepalive interval in seconds (<=0 disables)."""
    return client.set_keepalive(interval_s, keys)


@app.tool()
async def bbs_discover_menu(screen_override: str = "") -> dict[str, Any]:
    """Discover menu options from a screen buffer.

    If screen_override is not provided, reads current screen with minimal timeout.
    """
    if screen_override:
        screen = screen_override
    else:
        # Read with minimal timeout to get current screen state
        snapshot = await client.read(timeout_ms=10, max_bytes=0)
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
    sequence = [item for item in keys_sequence.split("|") if item]
    return await client.wake(timeout_ms, interval_ms, max_bytes, sequence)


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
    return append_md(client.learn_base_dir() / "menu-map.md", "Menu Map (Shared)", body)


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
    return append_md(client.learn_base_dir() / "prompt-catalog.md", "Prompt Catalog (Shared)", body)


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
    return append_md(client.learn_base_dir() / "flow-notes.md", "Flow Notes (Shared)", body)


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
    return append_md(client.learn_base_dir() / "replay-notes.md", "Replay Notes (Shared)", body)


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
    return append_md(client.learn_base_dir() / "state-model.md", "State Model (Shared)", body)


def run() -> None:
    app.run()
