"""TW2002 Trading Bot - Automated credit accumulation via 499↔607 trading loop.

This bot implements metadata-driven prompt handling to reliably automate the
Trade Wars 2002 game. It uses:
- bbs_wait_for_prompt() for reliable timing (no race conditions)
- input_type metadata to decide send behavior (single_key, multi_key, any_key)
- Smart retry logic for common errors
"""

from .bot import TradingBot
from .connection import connect
from .login import login_sequence, test_login
from .trading import (
    single_trading_cycle,
    run_trading_loop,
    _dock_and_buy,
    _dock_and_sell,
    _warp_to_sector,
)
from .io import wait_and_respond, send_input
from .parsing import (
    _parse_credits_from_screen,
    _parse_sector_from_screen,
    _extract_game_options,
    _select_trade_wars_game,
)
from .errors import _check_for_loop, _detect_error_in_screen
from .logging_utils import logger, _log_trade, _save_trade_history, _print_session_summary
from .orientation import GameState, SectorKnowledge, OrientationError, orient

__version__ = "1.0.0"

__all__ = [
    "TradingBot",
    "GameState",
    "SectorKnowledge",
    "OrientationError",
    "orient",
    "connect",
    "login_sequence",
    "test_login",
    "single_trading_cycle",
    "run_trading_loop",
    "wait_and_respond",
    "send_input",
    "logger",
]
