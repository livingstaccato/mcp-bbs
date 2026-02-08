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

    # BANK requires banking enabled
    if action == TradeAction.BANK:
        if not config.banking.enabled:
            logger.debug("bank_not_enabled")
            return False

    # UPGRADE requires upgrade type
    if action == TradeAction.UPGRADE:
        upgrade_type = params.get("upgrade_type")
        if upgrade_type not in ("holds", "fighters", "shields"):
            logger.debug("invalid_upgrade_type", upgrade_type=upgrade_type)
            return False

    return True
