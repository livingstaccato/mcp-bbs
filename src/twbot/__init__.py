"""TW2002 Trading Bot - Automated credit accumulation via configurable trading strategies.

This bot implements metadata-driven prompt handling to reliably automate the
Trade Wars 2002 game. Features:
- Configurable trading strategies (profitable pairs, opportunistic, twerk-optimized)
- Multi-character management with knowledge sharing
- D command optimization (only scan new sectors)
- Auto-banking, ship upgrades, and combat avoidance
- YAML configuration support

Usage:
    from twbot import TradingBot, BotConfig

    config = BotConfig.from_yaml("config.yaml")
    bot = TradingBot(character_name="mybot", config=config)
"""

from .bot import TradingBot
from .config import BotConfig, load_config
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
from .character import CharacterState, CharacterManager, CharacterKnowledge
from .multi_character import MultiCharacterManager

__version__ = "2.0.0"

__all__ = [
    # Core
    "TradingBot",
    "BotConfig",
    "load_config",
    # State
    "GameState",
    "SectorKnowledge",
    "OrientationError",
    "orient",
    # Character management
    "CharacterState",
    "CharacterManager",
    "CharacterKnowledge",
    "MultiCharacterManager",
    # Connection
    "connect",
    "login_sequence",
    "test_login",
    # Trading
    "single_trading_cycle",
    "run_trading_loop",
    # I/O
    "wait_and_respond",
    "send_input",
    # Logging
    "logger",
]
