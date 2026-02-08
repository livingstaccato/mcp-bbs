"""Core I/O operations for TW2002 Trading Bot."""

import asyncio
import json
import time
from pathlib import Path

from bbsbot.core.generic_io import InputSender, PromptWaiter
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
        ignore_loop_for: Set of prompt IDs to ignore for loop detection

    Returns:
        Tuple of (input_type, prompt_id, screen_text, kv_data)
        where kv_data may include "_validation" field with extraction status

    Raises:
        TimeoutError: If no prompt detected within timeout
        RuntimeError: If error detected in screen or stuck in loop
    """
    bot.step_count += 1
    start_time = time.time()

    # TW2002-specific: Callback for semantic extraction on each screen update
    def on_screen_update(screen: str) -> None:
        elapsed_ms = int((time.time() - start_time) * 1000)
        print(f"status action=read step={bot.step_count} elapsed_ms={elapsed_ms}")

        # Extract and log semantic data
        semantic = extract_semantic_kv(screen)
        if semantic:
            kv = " ".join(f"{k}={semantic[k]}" for k in sorted(semantic))
            print(f"semantic {kv}")
            _update_semantic_relationships(bot, semantic)
            _write_semantic_log(bot, semantic)
            # Merge into bot's semantic data so orient can access it.
            # Use merge (not replace) so credits from earlier screens
            # persist even if later screens don't show them.
            bot.last_semantic_data.update(semantic)

    # TW2002-specific: Filter prompts for errors and loops
    def on_prompt_detected(detected: dict) -> bool:
        prompt_id = detected.get("prompt_id")
        screen = detected.get("screen", "")

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

        # Accept this prompt
        return True

    # Use framework PromptWaiter with TW2002-specific callbacks
    waiter = PromptWaiter(bot.session, on_screen_update=on_screen_update)

    try:
        result = await waiter.wait_for_prompt(
            expected_prompt_id=prompt_id_pattern,
            timeout_ms=timeout_ms,
            on_prompt_detected=on_prompt_detected,
            require_idle=True,
            idle_grace_ratio=0.8,
        )

        # Track detected prompt (TW2002-specific)
        bot.detected_prompts.append(
            {
                "step": bot.step_count,
                "prompt_id": result["prompt_id"],
                "input_type": result["input_type"],
            }
        )

        # Return in expected format
        return (
            result["input_type"],
            result["prompt_id"],
            result["screen"],
            result["kv_data"],
        )
    except TimeoutError:
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
    # TW2002-specific: Log the input being sent
    printable = keys.replace("\r", "\\r").replace("\n", "\\n")
    print(
        f"status action=send step={bot.step_count} input_type={input_type} keys={printable}"
    )

    # Use framework InputSender for actual sending
    sender = InputSender(bot.session)
    await sender.send_input(keys, input_type, wait_after_sec=wait_after)
