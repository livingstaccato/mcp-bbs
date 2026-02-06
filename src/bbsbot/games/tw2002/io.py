"""Core I/O operations for TW2002 Trading Bot."""

import asyncio
import json
import sys
import time
from pathlib import Path

from bbsbot.games.tw2002.errors import _check_for_loop, _detect_error_in_screen
from bbsbot.games.tw2002.parsing import extract_semantic_kv


def _write_semantic_log(bot, data: dict) -> None:
    knowledge_root = getattr(bot, "knowledge_root", None)
    if not knowledge_root:
        return

    try:
        base = Path(knowledge_root) / "tw2002" / "semantic"
        base.mkdir(parents=True, exist_ok=True)
        name = getattr(bot, "character_name", "unknown") or "unknown"
        path = base / f"{name}_semantic.jsonl"
        payload = {
            "ts": time.time(),
            "data": data,
        }
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload) + "\n")
    except Exception:
        return


def _update_semantic_relationships(bot, data: dict) -> None:
    knowledge = getattr(bot, "sector_knowledge", None)
    sector = data.get("sector")
    if not knowledge or not sector:
        return

    try:
        from bbsbot.games.tw2002.orientation import SectorInfo
    except Exception:
        return

    info = knowledge._sectors.get(sector) or SectorInfo()
    if data.get("warps"):
        info.warps = data["warps"]
    if data.get("has_port") is True:
        info.has_port = True
        info.port_class = data.get("port_class")
    if data.get("has_planet") is True:
        info.has_planet = True
        info.planet_names = data.get("planet_names", [])
    info.last_visited = time.time()
    knowledge._sectors[sector] = info
    knowledge._save_cache()


async def wait_and_respond(
    bot,
    prompt_id_pattern: str | None = None,
    timeout_ms: int = 10000,
    ignore_loop_for: set[str] | None = None,
) -> tuple[str | None, str | None, str, dict | None]:
    """Wait for prompt and return (input_type, prompt_id, screen, kv_data).

    Args:
        bot: TradingBot instance
        prompt_id_pattern: Optional pattern to match (e.g., "prompt.password")
        timeout_ms: Timeout in milliseconds

    Returns:
        Tuple of (input_type, prompt_id, screen_text, kv_data)
        where kv_data may include "_validation" field with extraction status

    Raises:
        TimeoutError: If no prompt detected within timeout
        RuntimeError: If error detected in screen or stuck in loop
    """
    bot.step_count += 1
    start_time = time.time()
    timeout_sec = timeout_ms / 1000.0

    while time.time() - start_time < timeout_sec:
        # One-line status marker between I/O operations
        print(
            f"status action=read step={bot.step_count} elapsed_ms={int((time.time() - start_time) * 1000)}"
        )
        # Use session.read() which runs prompt detection
        snapshot = await bot.session.read(timeout_ms=250, max_bytes=8192)
        screen = snapshot.get("screen", "")
        semantic = extract_semantic_kv(screen)
        if semantic:
            kv = " ".join(f"{k}={semantic[k]}" for k in sorted(semantic))
            print(f"semantic {kv}")
            _update_semantic_relationships(bot, semantic)
            _write_semantic_log(bot, semantic)

        if "prompt_detected" in snapshot:
            detected = snapshot["prompt_detected"]
            prompt_id = detected.get("prompt_id")
            input_type = detected.get("input_type")
            kv_data = detected.get("kv_data")
            is_idle = detected.get("is_idle", False)

            # Wait for screen to stabilize before returning
            # But don't be too strict - if we've been waiting a while, accept non-idle
            elapsed = time.time() - start_time
            if not is_idle:
                if elapsed > 5 and elapsed % 5 < 0.2:  # Print every 5 seconds
                    print(f"      [DEBUG] Detected {prompt_id} but waiting for idle (elapsed: {elapsed:.1f}s)")

            # Wait for screen to stabilize before returning
            # But don't be too strict - if we've been waiting a while, accept non-idle
            elapsed = time.time() - start_time
            if not is_idle and elapsed < timeout_sec * 0.8:
                continue
            # Accept prompt after 80% of timeout even if not fully idle
            if not is_idle:
                print(f"      [DEBUG] Accepting {prompt_id} despite not idle (elapsed: {elapsed:.1f}s >= 80% of {timeout_sec}s)")

            # Only check for context-specific errors (not menu-wide error text)
            # Check for errors ONLY if we're at a password/login prompt
            if prompt_id and any(
                x in prompt_id
                for x in [
                    "password",
                    "game_password",
                    "private_game_password",
                    "login_name",
                ]
            ):
                error_type = _detect_error_in_screen(screen)
                if error_type:
                    bot.error_count += 1
                    raise RuntimeError(f"Error detected: {error_type}")

            # Check for loop (skip for prompts expected to repeat)
            loop_ignore = {"prompt.pause_space_or_enter", "prompt.pause_simple"}
            if ignore_loop_for:
                loop_ignore = loop_ignore | set(ignore_loop_for)
            if prompt_id not in loop_ignore and _check_for_loop(bot, prompt_id):
                raise RuntimeError(f"Stuck in loop: {prompt_id}")

            # If pattern specified, check if it matches
            if prompt_id_pattern:
                if prompt_id_pattern in prompt_id:
                    bot.detected_prompts.append(
                        {
                            "step": bot.step_count,
                            "prompt_id": prompt_id,
                            "input_type": input_type,
                        }
                    )
                    return (input_type, prompt_id, screen, kv_data)
            else:
                # Any prompt is acceptable
                bot.detected_prompts.append(
                    {
                        "step": bot.step_count,
                        "prompt_id": prompt_id,
                        "input_type": input_type,
                    }
                )
                return (input_type, prompt_id, screen, kv_data)

        await asyncio.sleep(0.1)

    raise TimeoutError(f"No prompt detected within {timeout_ms}ms")


async def send_input(
    bot, keys: str, input_type: str | None, wait_after: float = 0.2
):
    """Send input based on input_type metadata.

    Args:
        bot: TradingBot instance
        keys: The keys/text to send
        input_type: Type from prompt metadata ("single_key", "multi_key", "any_key")
        wait_after: Time to wait after sending (seconds)
    """
    # One-line status marker between I/O operations
    printable = keys.replace("\r", "\\r").replace("\n", "\\n")
    print(
        f"status action=send step={bot.step_count} input_type={input_type} keys={printable}"
    )

    if input_type == "single_key":
        # Single key - send as-is without newline
        await bot.session.send(keys)
    elif input_type == "multi_key":
        # Multi-key - add newline
        await bot.session.send(keys + "\r")
    elif input_type == "any_key":
        # Any key - press space
        await bot.session.send(" ")
    else:
        # Unknown type - default to multi_key (safer)
        await bot.session.send(keys + "\r")

    await asyncio.sleep(wait_after)
