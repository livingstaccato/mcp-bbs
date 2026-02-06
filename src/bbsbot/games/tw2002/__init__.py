"""TW2002 Trading Bot - Automated credit accumulation via configurable trading strategies.

This bot implements metadata-driven prompt handling to reliably automate the
Trade Wars 2002 game. Features:
- Configurable trading strategies (profitable pairs, opportunistic, twerk-optimized)
- Multi-character management with knowledge sharing
- D command optimization (only scan new sectors)
- Auto-banking, ship upgrades, and combat avoidance
- YAML configuration support

Usage:
    from bbsbot.games.tw2002 import TradingBot, BotConfig

    config = BotConfig.from_yaml("config.yaml")
    bot = TradingBot(character_name="mybot", config=config)
"""

from bbsbot.games.tw2002.bot import TradingBot
from bbsbot.games.tw2002.character import CharacterKnowledge, CharacterManager, CharacterState
from bbsbot.games.tw2002.config import BotConfig, load_config
from bbsbot.games.tw2002.connection import connect
from bbsbot.games.tw2002.errors import _check_for_loop, _detect_error_in_screen
from bbsbot.games.tw2002.io import send_input, wait_and_respond
from bbsbot.games.tw2002.login import login_sequence, test_login
from bbsbot.games.tw2002.logging_utils import (
    _log_trade,
    _print_session_summary,
    _save_trade_history,
    logger,
)
from bbsbot.games.tw2002.multi_character import MultiCharacterManager
from bbsbot.games.tw2002.orientation import GameState, OrientationError, SectorKnowledge, orient
from bbsbot.games.tw2002.parsing import (
    _extract_game_options,
    _parse_credits_from_screen,
    _parse_sector_from_screen,
    _select_trade_wars_game,
)
from bbsbot.games.tw2002.trading import (
    _dock_and_buy,
    _dock_and_sell,
    _warp_to_sector,
    run_trading_loop,
    single_trading_cycle,
)

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
