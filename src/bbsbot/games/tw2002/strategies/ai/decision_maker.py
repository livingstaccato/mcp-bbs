"""LLM decision-making and response parsing."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from bbsbot.llm.types import ChatMessage, ChatRequest
from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.games.tw2002.orientation import GameState
    from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy
    from bbsbot.llm.manager import LLMManager
    from bbsbot.llm.types import ChatResponse

logger = get_logger(__name__)


def extract_reasoning(content: str) -> str:
    """Extract reasoning field from LLM JSON response."""
    import json as _json
    import re as _re

    try:
        data = _json.loads(content)
        return data.get("reasoning", "")
    except _json.JSONDecodeError:
        pass
    # Try extracting from markdown code block or raw JSON
    match = _re.search(r'"reasoning"\s*:\s*"([^"]*)"', content)
    return match.group(1) if match else ""


def truncate(s: str | None, limit: int = 50_000) -> str:
    """Truncate string to limit."""
    if s is None:
        return ""
    if len(s) <= limit:
        return s
    return s[:limit] + "\n[...truncated...]"


async def make_llm_decision(
    strategy: AIStrategy,
    llm_manager: LLMManager,
    parser,
    state: GameState,
    stuck_action: str | None = None,
) -> tuple:
    """Make decision using LLM.

    Args:
        strategy: AIStrategy instance
        llm_manager: LLM manager
        parser: Response parser
        state: Current game state
        stuck_action: If set, the action the LLM keeps repeating

    Returns:
        Tuple of (action, parameters, trace)

    Raises:
        Exception: On LLM errors or parsing failures
    """
    # Build prompt with current goal
    goal_config = strategy._get_goal_config(strategy._current_goal_id)
    goal_description = goal_config.description if goal_config else None
    goal_instructions = goal_config.instructions if goal_config else None

    base_messages = strategy.prompt_builder.build(
        state,
        strategy.knowledge,
        strategy.stats,
        goal_description=goal_description,
        goal_instructions=goal_instructions,
        stuck_action=stuck_action,
    )

    # Build full message list: system + conversation history + current state
    system_msg = base_messages[0]  # system prompt
    current_state_msg = base_messages[1]  # current user prompt
    messages = [system_msg] + strategy._conversation_history + [current_state_msg]

    model = strategy.config.llm.get_model()
    request = ChatRequest(
        messages=messages,
        model=model,
        temperature=0.7,
        max_tokens=500,
    )

    start_time = time.time()
    strategy._is_thinking = True  # Set flag for dashboard
    try:
        response = await llm_manager.chat(request)
    except Exception as e:
        strategy._is_thinking = False
        duration_ms = (time.time() - start_time) * 1000
        await log_llm_decision_error(
            strategy=strategy,
            state=state,
            model=model,
            request=request,
            messages=messages,
            duration_ms=duration_ms,
            error=e,
            raw_response=None,
        )
        raise
    duration_ms = (time.time() - start_time) * 1000

    # Parse response - with one retry on parse failure
    try:
        action, params = parser.parse(response, state)
    except Exception as first_error:
        # Retry once with a correction prompt
        logger.warning(f"ai_json_parse_failed, retrying with correction: {first_error}")
        try:
            retry_messages = messages + [
                ChatMessage(role="assistant", content=response.message.content),
                ChatMessage(
                    role="user",
                    content=(
                        'Your response was not valid JSON. Respond with ONLY a JSON object like: '
                        '{"action": "TRADE", "reasoning": "...", "parameters": {}}'
                    ),
                ),
            ]
            retry_request = ChatRequest(
                messages=retry_messages,
                model=model,
                temperature=0.3,
                max_tokens=300,
            )
            response = await llm_manager.chat(retry_request)
            duration_ms = (time.time() - start_time) * 1000
            action, params = parser.parse(response, state)
            logger.info("ai_json_retry_succeeded")
        except Exception as retry_error:
            await log_llm_decision_error(
                strategy=strategy,
                state=state,
                model=model,
                request=request,
                messages=messages,
                duration_ms=duration_ms,
                error=retry_error,
                raw_response=getattr(response.message, "content", None),
            )
            strategy._is_thinking = False
            raise

    # Extract reasoning and store for external access
    strategy._last_reasoning = extract_reasoning(response.message.content)

    # Append this exchange to conversation history (compact summary + response)
    compact_state = (
        f"Turn {strategy._current_turn}: Sector {state.sector}, "
        f"Credits {state.credits}, Turns left {state.turns_left}"
    )
    if state.has_port:
        compact_state += f", Port {state.port_class}"
    strategy._conversation_history.append(
        ChatMessage(role="user", content=compact_state)
    )
    strategy._conversation_history.append(
        ChatMessage(role="assistant", content=response.message.content)
    )

    # Trim history to max length (each exchange = 2 messages)
    max_messages = strategy._max_history_turns * 2
    if len(strategy._conversation_history) > max_messages:
        strategy._conversation_history = strategy._conversation_history[-max_messages:]

    # Print reasoning to bot logs
    if strategy._last_reasoning:
        print(f"  🤖 {strategy._last_reasoning}")

    trace = {
        "provider": strategy.config.llm.provider,
        "model": model,
        "request": {
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
            "timeout_ms": getattr(strategy._settings, "timeout_ms", None),
        },
        "messages": [{"role": m.role, "content": m.content} for m in messages],
        "response": {
            "content": response.message.content,
            "usage": {
                "prompt": response.usage.prompt_tokens if response.usage else 0,
                "completion": response.usage.completion_tokens if response.usage else 0,
                "total": response.usage.total_tokens if response.usage else 0,
            },
            "cached": bool(getattr(response, "cached", False)),
            "duration_ms": duration_ms,
        },
    }

    strategy._is_thinking = False
    return action, params, trace


async def log_llm_decision(
    strategy: AIStrategy,
    state: GameState,
    trace: dict,
    action,
    params: dict,
    validated: bool,
) -> None:
    """Best-effort logging of the primary decision prompt/response to session JSONL."""
    if not strategy._session_logger:
        return
    try:
        messages = trace.get("messages", [])
        for m in messages:
            if isinstance(m, dict) and "content" in m:
                m["content"] = truncate(str(m.get("content", "")))
        response = trace.get("response", {})
        if isinstance(response, dict) and "content" in response:
            response["content"] = truncate(str(response.get("content", "")))

        event_data = {
            "turn": strategy._current_turn,
            "goal_id": strategy._current_goal_id,
            "provider": trace.get("provider", strategy.config.llm.provider),
            "model": trace.get("model", ""),
            "request": trace.get("request", {}),
            "messages": messages,
            "response": response,
            "parsed": {"action": action.name, "params": params},
            "validated": bool(validated),
            "state_hint": {
                "sector": state.sector,
                "credits": state.credits,
                "turns_left": state.turns_left,
                "context": getattr(state, "context", None),
            },
        }
        await strategy._session_logger.log_event("llm.decision", event_data)
    except Exception as e:
        # Never break trading because logging failed.
        logger.debug(f"llm_decision_log_failed: {e}")


async def log_llm_decision_error(
    strategy: AIStrategy,
    state: GameState,
    model: str,
    request,
    messages: list[ChatMessage],
    duration_ms: float,
    error: Exception,
    raw_response: str | None,
) -> None:
    """Log LLM decision error."""
    if not strategy._session_logger:
        return
    try:
        event_data = {
            "turn": strategy._current_turn,
            "goal_id": strategy._current_goal_id,
            "provider": strategy.config.llm.provider,
            "model": model,
            "request": {
                "temperature": request.temperature,
                "max_tokens": request.max_tokens,
                "timeout_ms": getattr(strategy._settings, "timeout_ms", None),
            },
            "messages": [{"role": m.role, "content": truncate(m.content)} for m in messages],
            "duration_ms": duration_ms,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "raw_response": truncate(raw_response),
            "state_hint": {
                "sector": state.sector,
                "credits": state.credits,
                "turns_left": state.turns_left,
                "context": getattr(state, "context", None),
            },
        }
        await strategy._session_logger.log_event("llm.decision_error", event_data)
    except Exception as e:
        logger.debug(f"llm_decision_error_log_failed: {e}")
