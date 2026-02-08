"""Goal management, evaluation, and phase tracking."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bbsbot.games.tw2002.config import GoalPhase
from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.games.tw2002.orientation import GameState
    from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy

logger = get_logger(__name__)


def get_current_goal(strategy: AIStrategy) -> str:
    """Get current goal ID.

    Returns:
        Goal ID string
    """
    return strategy._current_goal_id


def set_goal(
    strategy: AIStrategy,
    goal_id: str,
    duration_turns: int = 0,
    state: GameState | None = None,
) -> None:
    """Manually set current goal.

    Args:
        strategy: AIStrategy instance
        goal_id: Goal ID to activate
        duration_turns: How many turns to maintain (0 = until changed)
        state: Current game state for metrics
    """
    if goal_id not in [g.id for g in strategy._settings.goals.available]:
        available = [g.id for g in strategy._settings.goals.available]
        logger.warning(f"goal_not_found: {goal_id}, available: {available}")
        return

    old_goal = strategy._current_goal_id
    strategy._current_goal_id = goal_id

    if duration_turns > 0:
        strategy._manual_override_until_turn = strategy._current_turn + duration_turns
    else:
        strategy._manual_override_until_turn = None

    # Start new phase
    reason = f"Manual override for {duration_turns} turns" if duration_turns > 0 else "Manual override"
    start_goal_phase(
        strategy=strategy,
        goal_id=goal_id,
        trigger_type="manual",
        reason=reason,
        state=state,
    )

    logger.info(f"goal_changed: {old_goal} -> {goal_id}, duration={duration_turns}")

    # Display timeline visualization on manual goal change
    if strategy._settings.show_goal_visualization:
        _visualize_goal_change(strategy, old_goal, goal_id, duration_turns)

    # Log to event ledger
    if strategy._session_logger:
        import asyncio

        try:
            asyncio.create_task(
                strategy._session_logger.log_event(
                    "goal.changed",
                    {
                        "turn": strategy._current_turn,
                        "old_goal": old_goal,
                        "new_goal": goal_id,
                        "duration_turns": duration_turns,
                        "manual_override": True,
                    },
                )
            )
        except Exception as e:
            logger.warning(f"goal_event_logging_failed: {e}")


def get_goal_config(strategy: AIStrategy, goal_id: str):
    """Get goal configuration by ID.

    Args:
        strategy: AIStrategy instance
        goal_id: Goal identifier

    Returns:
        Goal config or None
    """
    for goal in strategy._settings.goals.available:
        if goal.id == goal_id:
            return goal
    return None


async def maybe_reevaluate_goal(strategy: AIStrategy, state: GameState) -> None:
    """Re-evaluate current goal if needed.

    Args:
        strategy: AIStrategy instance
        state: Current game state
    """
    # Skip if manual override is active
    if strategy._manual_override_until_turn is not None:
        if strategy._current_turn < strategy._manual_override_until_turn:
            return
        else:
            # Override expired
            strategy._manual_override_until_turn = None
            logger.info("goal_manual_override_expired")

    # Skip if not using auto-select
    if strategy._settings.goals.current != "auto":
        return

    # Check if it's time to re-evaluate
    turns_since_eval = strategy._current_turn - strategy._last_goal_evaluation_turn
    if turns_since_eval < strategy._settings.goals.reevaluate_every_turns:
        return

    # Re-evaluate and potentially change goal
    new_goal_id = await select_goal(strategy, state)
    if new_goal_id != strategy._current_goal_id:
        old_goal = strategy._current_goal_id
        strategy._current_goal_id = new_goal_id

        # Determine reason for auto-selection
        goal_config = get_goal_config(strategy, new_goal_id)
        reason = f"Auto-selected: {goal_config.description if goal_config else 'triggers matched'}"

        # Start new phase
        start_goal_phase(
            strategy=strategy,
            goal_id=new_goal_id,
            trigger_type="auto",
            reason=reason,
            state=state,
        )

        logger.info(f"goal_auto_changed: {old_goal} -> {new_goal_id}")

        # Display timeline visualization on goal change
        if strategy._settings.show_goal_visualization:
            _visualize_goal_change(strategy, old_goal, new_goal_id)

        # Log to event ledger
        if strategy._session_logger:
            await strategy._session_logger.log_event(
                "goal.changed",
                {
                    "turn": strategy._current_turn,
                    "old_goal": old_goal,
                    "new_goal": new_goal_id,
                    "duration_turns": 0,
                    "manual_override": False,
                    "auto_selected": True,
                },
            )

    strategy._last_goal_evaluation_turn = strategy._current_turn


async def select_goal(strategy: AIStrategy, state: GameState) -> str:
    """Auto-select best goal based on game state.

    Args:
        strategy: AIStrategy instance
        state: Current game state

    Returns:
        Best goal ID
    """
    priority_weights = {"low": 1, "medium": 2, "high": 3}

    # Score each goal
    scored_goals = []
    for goal in strategy._settings.goals.available:
        score = evaluate_goal_triggers(strategy, goal, state)
        priority_weight = priority_weights.get(goal.priority, 2)
        final_score = score * priority_weight
        scored_goals.append((goal.id, final_score, goal.priority))

    # Pick highest scoring goal
    if scored_goals:
        best = max(scored_goals, key=lambda x: x[1])
        return best[0]

    # Fallback to profit if no triggers match
    return "profit"


def evaluate_goal_triggers(strategy: AIStrategy, goal, state: GameState) -> float:
    """Evaluate how well a goal's triggers match current state.

    Args:
        strategy: AIStrategy instance
        goal: Goal configuration
        state: Current game state

    Returns:
        Score from 0.0 (no match) to 1.0 (perfect match)
    """
    triggers = goal.trigger_when
    matches = 0
    total_conditions = 0

    # Check credits conditions
    if triggers.credits_below is not None:
        total_conditions += 1
        if state.credits is not None and state.credits < triggers.credits_below:
            matches += 1

    if triggers.credits_above is not None:
        total_conditions += 1
        if state.credits is not None and state.credits > triggers.credits_above:
            matches += 1

    # Check fighters conditions
    if triggers.fighters_below is not None:
        total_conditions += 1
        if state.fighters is not None and state.fighters < triggers.fighters_below:
            matches += 1

    if triggers.fighters_above is not None:
        total_conditions += 1
        if state.fighters is not None and state.fighters > triggers.fighters_above:
            matches += 1

    # Check shields conditions
    if triggers.shields_below is not None:
        total_conditions += 1
        if state.shields is not None and state.shields < triggers.shields_below:
            matches += 1

    if triggers.shields_above is not None:
        total_conditions += 1
        if state.shields is not None and state.shields > triggers.shields_above:
            matches += 1

    # Check turns conditions
    if triggers.turns_remaining_above is not None:
        total_conditions += 1
        if state.turns_left is not None and state.turns_left > triggers.turns_remaining_above:
            matches += 1

    if triggers.turns_remaining_below is not None:
        total_conditions += 1
        if state.turns_left is not None and state.turns_left < triggers.turns_remaining_below:
            matches += 1

    # Check sector knowledge (would need to query self.knowledge)
    if triggers.sectors_known_below is not None:
        total_conditions += 1
        known_count = strategy.knowledge.known_sector_count() if strategy.knowledge else 0
        if known_count < triggers.sectors_known_below:
            matches += 1

    # If no conditions specified, give low score
    if total_conditions == 0:
        return 0.1

    # Return match ratio
    return matches / total_conditions


def start_goal_phase(
    strategy: AIStrategy,
    goal_id: str,
    trigger_type: str,
    reason: str,
    state: GameState | None = None,
) -> None:
    """Start a new goal phase.

    Args:
        strategy: AIStrategy instance
        goal_id: Goal ID to start
        trigger_type: "auto" or "manual"
        reason: Why this goal was selected
        state: Current game state for metrics
    """
    # Close current phase if active
    if strategy._current_phase:
        strategy._current_phase.end_turn = strategy._current_turn
        strategy._current_phase.status = "completed"

        # Record end metrics
        if state:
            strategy._current_phase.metrics["end_credits"] = state.credits
            strategy._current_phase.metrics["end_fighters"] = state.fighters
            strategy._current_phase.metrics["end_shields"] = state.shields
            strategy._current_phase.metrics["end_holds"] = state.holds_total

    # Create new phase
    metrics = {}
    if state:
        metrics = {
            "start_credits": state.credits,
            "start_fighters": state.fighters,
            "start_shields": state.shields,
            "start_holds": state.holds_total,
        }

    strategy._current_phase = GoalPhase(
        goal_id=goal_id,
        start_turn=strategy._current_turn,
        end_turn=None,
        status="active",
        trigger_type=trigger_type,
        metrics=metrics,
        reason=reason,
    )
    strategy._goal_phases.append(strategy._current_phase)


def _visualize_goal_change(strategy: AIStrategy, old_goal: str, new_goal: str, duration_turns: int = 0) -> None:
    """Display goal change visualization."""
    try:
        from bbsbot.games.tw2002.visualization import GoalTimeline

        timeline = GoalTimeline(
            phases=strategy._goal_phases,
            current_turn=strategy._current_turn,
            max_turns=strategy._max_turns,
        )
        lines: list[str] = []
        lines.append("\n" + "=" * 80)
        if duration_turns > 0:
            lines.append(f"MANUAL GOAL OVERRIDE: {old_goal.upper()} → {new_goal.upper()}")
            lines.append(f"Duration: {duration_turns} turns")
        else:
            lines.append(f"GOAL CHANGED: {old_goal.upper()} → {new_goal.upper()}")
        lines.append("=" * 80)
        lines.append(timeline.render_progress_bar())
        lines.append(timeline.render_legend())
        lines.append("=" * 80 + "\n")
        text = "\n".join(lines)
        print(text)
        strategy._emit_viz("timeline", text)
    except Exception as e:
        logger.debug(f"goal_visualization_failed: {e}")
