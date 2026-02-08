"""Periodic feedback loop for gameplay analysis."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from bbsbot.llm.types import ChatMessage, ChatRequest
from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.games.tw2002.orientation import GameState
    from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy
    from bbsbot.llm.manager import LLMManager

logger = get_logger(__name__)

# Feedback loop prompt template
FEEDBACK_SYSTEM_PROMPT = """You are analyzing Trade Wars 2002 gameplay to identify patterns and suggest improvements.
Focus on: trade efficiency, route optimization, resource management, and strategic decision-making.
Keep your analysis concise (2-3 observations)."""


async def periodic_feedback(
    strategy: AIStrategy,
    llm_manager: LLMManager,
    state: GameState,
) -> None:
    """Generate periodic gameplay analysis using LLM.

    Args:
        strategy: AIStrategy instance
        llm_manager: LLM manager
        state: Current game state
    """
    # Collect data from last N turns
    lookback = strategy._settings.feedback_lookback_turns
    start_turn = strategy._current_turn - lookback
    recent_events = [e for e in strategy._recent_events if e.get("turn", 0) >= start_turn]

    # Build analysis prompt
    messages = [
        ChatMessage(role="system", content=FEEDBACK_SYSTEM_PROMPT),
        ChatMessage(role="user", content=build_feedback_prompt(strategy, state, recent_events, start_turn)),
    ]

    # Query LLM
    request = ChatRequest(
        messages=messages,
        model=strategy.config.llm.ollama.model,
        temperature=0.7,
        max_tokens=strategy._settings.feedback_max_tokens,
    )

    start_time = time.time()
    try:
        response = await llm_manager.chat(request)
        duration_ms = (time.time() - start_time) * 1000

        # Log to event ledger
        await log_feedback(strategy, state, messages, response, duration_ms, recent_events)

        logger.info(
            f"feedback_generated: turn={strategy._current_turn}, tokens={response.usage.total_tokens if response.usage else 0}"
        )

    except Exception as e:
        logger.warning(f"feedback_loop_error: {e}")


def build_feedback_prompt(
    strategy: AIStrategy,
    state: GameState,
    events: list[dict],
    start_turn: int,
) -> str:
    """Build feedback analysis prompt.

    Args:
        strategy: AIStrategy instance
        state: Current game state
        events: Recent events to analyze
        start_turn: Starting turn number for analysis

    Returns:
        Formatted prompt string
    """
    # Count event types
    decisions = [e for e in events if e.get("type") == "decision"]
    trades = [e for e in events if e.get("type") == "trade"]

    # Calculate profit if we have trade data
    profit = 0
    if trades:
        for trade in trades:
            if trade.get("action") == "sell":
                profit += trade.get("total", 0)
            elif trade.get("action") == "buy":
                profit -= trade.get("total", 0)

    # Format values safely
    credits_str = f"{state.credits:,}" if state.credits is not None else "Unknown"
    sector_str = str(state.sector) if state.sector is not None else "Unknown"
    turns_str = str(state.turns_left) if state.turns_left is not None else "Unknown"
    holds_str = f"{state.holds_free}/{state.holds_total}" if state.holds_free is not None else "Unknown"

    return f"""GAMEPLAY SUMMARY (Turns {start_turn}-{strategy._current_turn}):

Current Status:
- Location: Sector {sector_str}
- Credits: {credits_str}
- Turns Remaining: {turns_str}
- Ship: {holds_str} holds free

Recent Activity:
- Decisions Made: {len(decisions)}
- Trades Executed: {len(trades)}
- Net Profit This Period: {profit:,} credits

Recent Decisions:
{format_recent_decisions(decisions[-5:])}

Performance Metrics:
- Profit Per Turn: {profit / len(events) if events else 0:.1f}
- Decisions Per Turn: {len(decisions) / strategy._settings.feedback_lookback_turns:.2f}

Analyze the recent gameplay. What patterns do you notice? What's working well?
What could be improved? Keep your analysis concise (2-3 observations)."""


def format_recent_decisions(decisions: list[dict]) -> str:
    """Format recent decisions for prompt.

    Args:
        decisions: List of decision events

    Returns:
        Formatted string
    """
    if not decisions:
        return "  None"

    lines = []
    for d in decisions:
        action = d.get("action", "unknown")
        sector = d.get("sector", "?")
        turn = d.get("turn", "?")
        lines.append(f"  Turn {turn}: {action} at sector {sector}")

    return "\n".join(lines)


async def log_feedback(
    strategy: AIStrategy,
    state: GameState,
    messages: list[ChatMessage],
    response,
    duration_ms: float,
    events: list[dict],
) -> None:
    """Log feedback to event ledger.

    Args:
        strategy: AIStrategy instance
        state: Current game state
        messages: Chat messages sent
        response: LLM response
        duration_ms: Response time in milliseconds
        events: Events analyzed
    """
    if not strategy._session_logger:
        logger.warning("feedback_no_logger: Cannot log feedback without session logger")
        return

    event_data = {
        "turn": strategy._current_turn,
        "turn_range": [
            strategy._current_turn - strategy._settings.feedback_lookback_turns,
            strategy._current_turn,
        ],
        "prompt": messages[1].content if len(messages) > 1 else "",
        "response": response.message.content,
        "context": {
            "sector": state.sector,
            "credits": state.credits,
            "trades_this_period": len([e for e in events if e.get("type") == "trade"]),
        },
        "metadata": {
            "model": strategy.config.llm.ollama.model,
            "tokens": {
                "prompt": response.usage.prompt_tokens if response.usage else 0,
                "completion": response.usage.completion_tokens if response.usage else 0,
                "total": response.usage.total_tokens if response.usage else 0,
            },
            "cached": response.cached if hasattr(response, "cached") else False,
            "duration_ms": duration_ms,
        },
    }

    await strategy._session_logger.log_event("llm.feedback", event_data)
