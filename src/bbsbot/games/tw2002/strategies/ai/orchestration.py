"""Decision orchestration - handles the main decision-making flow."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bbsbot.games.tw2002.strategies.ai import decision_maker, feedback_loop, goals, validator
from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.games.tw2002.orientation import GameState
    from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy
    from bbsbot.games.tw2002.strategies.base import TradeAction

logger = get_logger(__name__)


async def orchestrate_decision(strategy: AIStrategy, state: GameState) -> tuple[TradeAction, dict]:
    """Orchestrate the main decision-making flow.

    Handles: goal re-evaluation, interventions, feedback, fallback strategy, LLM decision,
    validation, and stuck detection.

    Args:
        strategy: AIStrategy instance
        state: Current game state

    Returns:
        Tuple of (action, parameters)
    """
    strategy._current_turn += 1

    # Verify Ollama is available on first call (warm up model)
    if not strategy._ollama_verified:
        try:
            model = strategy.config.llm.get_model()
            info = await strategy.llm_manager.verify_model(model)
            strategy._ollama_verified = True
            print(f"  [AI] Connected to Ollama, model: {info.get('name', model)}")
        except Exception as e:
            logger.error(f"ollama_not_available: {e}")
            print(f"  [AI] Ollama not available: {e}, using fallback strategy")
            return strategy.run_fallback_action(state, reason="ollama_not_available")

    # Re-evaluate goal if needed
    await goals.maybe_reevaluate_goal(strategy, state)

    # Check for intervention triggers
    should_intervene, reason, context = strategy._intervention_trigger.should_intervene(
        current_turn=strategy._current_turn,
        state=state,
        strategy=strategy,
    )

    if should_intervene:
        try:
            # Build intervention prompt and query LLM
            recommendation = await strategy._intervention_advisor.analyze(
                state=state,
                recent_decisions=strategy._get_recent_decisions(),
                strategy_stats=strategy.stats,
                goal_phases=strategy._goal_phases,
                anomalies=context.get("anomalies", []),
                opportunities=context.get("opportunities", []),
                trigger_reason=reason,
            )

            # Log intervention
            await strategy._intervention_trigger.log_intervention(
                turn=strategy._current_turn,
                reason=reason,
                context=context,
                recommendation=recommendation,
            )

            # Apply recommendation if auto-apply enabled
            if strategy._settings.intervention.auto_apply:
                result = strategy._apply_intervention(recommendation, state)
                if result:
                    action, params = result
                    logger.info(
                        "intervention_applied",
                        action=action.name,
                        recommendation=recommendation.get("recommendation"),
                    )
                    return action, params
        except Exception as e:
            logger.error("intervention_analysis_failed", error=str(e))

    # Periodic feedback loop
    if (
        strategy._settings.feedback_enabled
        and strategy._current_turn % strategy._settings.feedback_interval_turns == 0
        and strategy.consecutive_failures < strategy._settings.fallback_threshold
    ):
        await feedback_loop.periodic_feedback(strategy, strategy.llm_manager, state)

    # Graduated fallback: scale cooldown with consecutive failures
    if strategy.consecutive_failures > 0:
        if strategy._current_turn < strategy.fallback_until_turn:
            logger.debug(
                f"ai_strategy_fallback_active: turn={strategy._current_turn}, "
                f"until={strategy.fallback_until_turn}, failures={strategy.consecutive_failures}"
            )
            return strategy.run_fallback_action(state, reason="failure_cooldown")
        elif strategy.consecutive_failures >= strategy._settings.fallback_threshold:
            # Cooldown expired, try LLM again
            logger.info("ai_strategy_fallback_cooldown_expired")
            strategy.consecutive_failures = 0

    # Check if stuck (same action N times in a row)
    stuck_action: str | None = None
    if (
        len(strategy._recent_actions) >= strategy._stuck_threshold
        and len(set(strategy._recent_actions[-strategy._stuck_threshold :])) == 1
    ):
        stuck_action = strategy._recent_actions[-1]
        logger.warning(f"ai_stuck_detected: {stuck_action} x{strategy._stuck_threshold}")

    # Try LLM decision
    try:
        action, params, trace = await decision_maker.make_llm_decision(
            strategy=strategy,
            llm_manager=strategy.llm_manager,
            parser=strategy.parser,
            state=state,
            stuck_action=stuck_action,
        )

        # Validate decision
        is_valid = validator.validate_decision(action, params, state, strategy.config)
        if is_valid:
            strategy.consecutive_failures = 0
            # Track action for stuck detection
            strategy._recent_actions.append(action.name)
            if len(strategy._recent_actions) > strategy._stuck_threshold + 2:
                strategy._recent_actions = strategy._recent_actions[-(strategy._stuck_threshold + 2) :]

            # If we were stuck AND the LLM returned the same action again, force fallback
            if stuck_action and action.name == stuck_action:
                logger.warning(f"ai_still_stuck: {stuck_action}, forcing fallback")
                return strategy.run_fallback_action(state, reason="stuck_repeat")

            selected_strategy = strategy.resolve_requested_strategy(params)
            if selected_strategy == "ai_direct":
                selected_strategy = strategy.active_managed_strategy

            # Loss-recovery override: if AI is bleeding, force a proven strategy.
            stats = strategy.stats or {}
            if (
                float(stats.get("profit_per_turn", 0.0)) < 0.0
                and int(stats.get("turns_used", 0)) >= 20
                and selected_strategy not in ("profitable_pairs", "opportunistic")
            ):
                selected_strategy = "profitable_pairs"
                strategy._active_managed_strategy = selected_strategy
                logger.warning(
                    "ai_strategy_loss_recovery_override",
                    selected_strategy=selected_strategy,
                    profit_per_turn=float(stats.get("profit_per_turn", 0.0)),
                    turns_used=int(stats.get("turns_used", 0)),
                )

            # Bootstrap: profitable_pairs can over-explore early with sparse market intel.
            # Use opportunistic until we establish a little trade/capital baseline.
            if selected_strategy == "profitable_pairs":
                low_bankroll = int(getattr(state, "credits", 0) or 0) <= 1000
                low_trade_count = int(stats.get("trades_executed", 0)) < 3
                early_turns = int(stats.get("turns_used", 0)) < 30
                if low_bankroll and low_trade_count and early_turns:
                    selected_strategy = "opportunistic"
                    strategy._active_managed_strategy = selected_strategy
                    logger.info(
                        "ai_strategy_bootstrap_override",
                        selected_strategy=selected_strategy,
                        credits=int(getattr(state, "credits", 0) or 0),
                        trades_executed=int(stats.get("trades_executed", 0)),
                        turns_used=int(stats.get("turns_used", 0)),
                    )

            if selected_strategy != "ai_direct":
                delegated_action, delegated_params = strategy.run_managed_strategy(
                    selected_strategy,
                    state,
                    update_active=True,
                )
                strategy._recent_actions.append(f"{selected_strategy}:{delegated_action.name}")
                if len(strategy._recent_actions) > strategy._stuck_threshold + 2:
                    strategy._recent_actions = strategy._recent_actions[-(strategy._stuck_threshold + 2) :]
                logger.info(
                    "ai_strategy_managed_decision",
                    selected_strategy=selected_strategy,
                    action=delegated_action.name,
                    params=delegated_params,
                )
                strategy._record_event(
                    "decision",
                    {
                        "turn": strategy._current_turn,
                        "selected_strategy": selected_strategy,
                        "action": delegated_action.name,
                        "params": delegated_params,
                        "sector": state.sector,
                        "credits": state.credits,
                    },
                )
                await decision_maker.log_llm_decision(
                    strategy=strategy,
                    state=state,
                    trace=trace,
                    action=delegated_action,
                    params=delegated_params,
                    validated=True,
                )
                return delegated_action, delegated_params

            strategy._last_action_strategy = "ai_direct"
            logger.info(f"ai_strategy_decision: action={action.name}, params={params}")
            # Record event for feedback
            strategy._record_event(
                "decision",
                {
                    "turn": strategy._current_turn,
                    "action": action.name,
                    "params": params,
                    "sector": state.sector,
                    "credits": state.credits,
                },
            )
            await decision_maker.log_llm_decision(
                strategy=strategy,
                state=state,
                trace=trace,
                action=action,
                params=params,
                validated=True,
            )
            return action, params
        else:
            await decision_maker.log_llm_decision(
                strategy=strategy,
                state=state,
                trace=trace,
                action=action,
                params=params,
                validated=False,
            )
            raise ValueError("Invalid LLM decision")

    except Exception as e:
        logger.warning(f"ai_strategy_failure: {e}, consecutive={strategy.consecutive_failures + 1}")
        strategy.consecutive_failures += 1

        # Graduated fallback duration based on failure count
        match strategy.consecutive_failures:
            case 1:
                # Single failure: retry immediately next turn
                strategy.fallback_until_turn = 0
            case 2 | 3:
                # 2-3 failures: short fallback
                strategy.fallback_until_turn = strategy._current_turn + 2
                logger.warning(f"ai_strategy_short_fallback: until_turn={strategy.fallback_until_turn}")
            case _:
                # 4+ failures: longer fallback
                duration = min(strategy.consecutive_failures * 2, 10)
                strategy.fallback_until_turn = strategy._current_turn + duration
                logger.warning(f"ai_strategy_long_fallback: until_turn={strategy.fallback_until_turn}")

        return strategy.run_fallback_action(state, reason=f"exception:{type(e).__name__}")
