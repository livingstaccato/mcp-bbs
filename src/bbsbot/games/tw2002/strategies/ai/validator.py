"""Decision validation against game state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from bbsbot.games.tw2002.strategies.base import TradeAction
from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.games.tw2002.config import BotConfig
    from bbsbot.games.tw2002.orientation import GameState

logger = get_logger(__name__)


def validate_decision(
    action: TradeAction,
    params: dict,
    state: GameState,
    config: BotConfig,
) -> bool:
    """Validate LLM decision against game state.

    Args:
        action: Proposed action
        params: Action parameters
        state: Current game state
        config: Bot configuration

    Returns:
        True if decision is valid
    """
    requested_strategy = params.get("strategy")
    if requested_strategy is not None and requested_strategy not in (
        "ai_direct",
        "profitable_pairs",
        "opportunistic",
        "twerk_optimized",
    ):
        logger.debug("invalid_strategy_selection", strategy=requested_strategy)
        return False

    requested_policy = params.get("policy")
    if requested_policy is not None and requested_policy not in ("conservative", "balanced", "aggressive"):
        logger.debug("invalid_policy_selection", policy=requested_policy)
        return False

    review_after_turns = params.get("review_after_turns")
    if review_after_turns is not None:
        try:
            review_turns = int(review_after_turns)
        except Exception:
            logger.debug("invalid_review_after_turns_type", value=review_after_turns)
            return False
        if review_turns < 1 or review_turns > 120:
            logger.debug("invalid_review_after_turns_range", value=review_turns)
            return False

    # MOVE requires valid target
    if action == TradeAction.MOVE:
        target = params.get("target_sector")
        if target is None:
            return False
        # Target should be in warps or known sectors
        if state.warps and target not in state.warps:
            logger.debug("invalid_move_target", target=target, warps=state.warps)
            return False

    # TRADE requires being at a port
    if action == TradeAction.TRADE:
        if not state.has_port:
            logger.debug("trade_without_port")
            return False
        commodity = params.get("commodity")
        if commodity is not None and commodity not in ("fuel_ore", "organics", "equipment"):
            logger.debug("invalid_trade_commodity", commodity=commodity)
            return False

    # BANK requires banking enabled
    if action == TradeAction.BANK and not config.banking.enabled:
        logger.debug("bank_not_enabled")
        return False

    # UPGRADE requires upgrade type
    if action == TradeAction.UPGRADE:
        upgrade_type = params.get("upgrade_type")
        if upgrade_type not in ("holds", "fighters", "shields"):
            logger.debug("invalid_upgrade_type", upgrade_type=upgrade_type)
            return False

    # End-state behavior: never stop early while turns remain.
    if action == TradeAction.DONE and (state.turns_left is None or state.turns_left > 0):
        logger.debug("done_blocked_while_turns_remaining", turns_left=state.turns_left)
        return False

    return True
