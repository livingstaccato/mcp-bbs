# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Main TradingBot class - re-exports for backward compatibility.

The TradingBot implementation is split across multiple modules for better maintainability:
- bot_core.py: Core class, state, subsystems
- bot_navigation.py: Orientation and menu navigation
- bot_twerk.py: Twerk integration for analysis

This module provides the main public interface by re-exporting TradingBot.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from bbsbot.games.tw2002 import bot_navigation, bot_twerk, connection, io, login, parsing, trading
from bbsbot.games.tw2002.bot_core import TradingBot

if TYPE_CHECKING:
    from pathlib import Path

    from twerk.analysis import SectorGraph, TradeRoute

    from bbsbot.games.tw2002.orientation import GameState, QuickState

__all__ = ["TradingBot"]


# Dynamically add navigation and connection methods to TradingBot
def _add_methods() -> None:
    """Add delegated methods to TradingBot class."""

    # Connection methods
    async def connect(self, host="localhost", port=2002):
        """Connect to TW2002 BBS."""
        await connection.connect(self, host, port)

    async def login_sequence(
        self, game_password: str = "game", character_password: str = "tim", username: str = "claude"
    ):
        """Complete login sequence from telnet login to game entry."""
        await login.login_sequence(self, game_password, character_password, username)

    async def test_login(self):
        """Test login sequence only."""
        return await login.test_login(self)

    # Orientation methods
    def init_knowledge(self, host: str = "localhost", port: int = 2002, game_letter: str | None = None) -> None:
        """Initialize sector knowledge for this character/server/game.

        This must complete before init_strategy(); it only sets up local paths/caches
        and does not perform network I/O, so it is intentionally synchronous.
        """
        bot_navigation.init_knowledge(self, host, port, game_letter)

    async def orient(self, force_scan: bool = False) -> GameState:
        """Run full orientation sequence."""
        return await bot_navigation.orient_full(self, force_scan)

    async def where_am_i(self, timeout_ms: int = 500) -> QuickState:
        """Fast state check - quickly determine where we are."""
        from bbsbot.games.tw2002.orientation import where_am_i

        return await where_am_i(self, timeout_ms)

    async def recover(self, max_attempts: int = 20) -> QuickState:
        """Attempt to recover to a safe state from any situation."""
        from bbsbot.games.tw2002.orientation import recover_to_safe_state

        return await recover_to_safe_state(self, max_attempts)

    def is_safe(self) -> bool:
        """Quick check if we're in a safe state based on last game_state."""
        return bot_navigation.is_safe(self)

    def is_in_danger(self) -> bool:
        """Quick check if we're in a dangerous state."""
        return bot_navigation.is_in_danger(self)

    # Navigation shortcuts
    async def go_to_computer(self) -> bool:
        """Navigate to Computer menu from sector command."""
        return await bot_navigation.go_to_computer(self)

    async def go_to_cim(self) -> bool:
        """Navigate to CIM (Computer Interrogation Mode)."""
        return await bot_navigation.go_to_cim(self)

    async def get_port_report(self) -> str:
        """Get human-readable port report from Computer menu."""
        return await bot_navigation.get_port_report(self)

    async def plot_course(self, destination: int) -> bool:
        """Use course plotter to plan route (zero turns)."""
        return await bot_navigation.plot_course(self, destination)

    async def go_to_stardock(self) -> bool:
        """Navigate to StarDock (must be in StarDock sector)."""
        return await bot_navigation.go_to_stardock(self)

    async def go_to_tavern(self) -> bool:
        """Navigate to Lost Trader's Tavern (must be at StarDock)."""
        return await bot_navigation.go_to_tavern(self)

    async def ask_grimy_trader(self, topic: str) -> str:
        """Ask Grimy Trader for information."""
        return await bot_navigation.ask_grimy_trader(self, topic)

    def find_path(self, destination: int) -> list[int] | None:
        """Find path from current sector to destination."""
        return bot_navigation.find_path_from_knowledge(self, destination)

    # Trading methods
    async def single_trading_cycle(self, start_sector: int = 499, max_retries: int = 2):
        """Execute one complete trading cycle (buy→sell) with error recovery."""
        await trading.single_trading_cycle(self, start_sector, max_retries)

    async def run_trading_loop(self, target_credits: int = 5_000_000, max_cycles: int = 20):
        """Run trading loop until target credits or max cycles."""
        await trading.run_trading_loop(self, target_credits, max_cycles)

    async def execute_route(
        self, route, quantity: int | None = None, max_retries: int = 2, data_dir: Path | None = None
    ) -> dict:
        """Execute a twerk-analyzed trade route via terminal."""
        return await trading.execute_route(self, route, quantity, max_retries, data_dir)

    # I/O methods
    async def wait_and_respond(self, prompt_id_pattern: str | None = None, timeout_ms: int = 15000):
        """Wait for prompt and return (input_type, prompt_id, screen)."""
        return await io.wait_and_respond(self, prompt_id_pattern, timeout_ms)

    async def send_input(self, keys: str, input_type: str | None, wait_after: float = 0.2):
        """Send input based on input_type metadata."""
        await io.send_input(self, keys, input_type, wait_after)

    # Parsing methods
    def _parse_credits_from_screen(self, screen: str) -> int:
        """Extract credit amount from screen text."""
        return parsing._parse_credits_from_screen(self, screen)

    def _parse_sector_from_screen(self, screen: str) -> int:
        """Extract current sector from screen text."""
        return parsing._parse_sector_from_screen(self, screen)

    def _extract_game_options(self, screen: str) -> list[tuple[str, str]]:
        """Extract available game options from TWGS menu."""
        return parsing._extract_game_options(screen)

    def _select_trade_wars_game(self, screen: str) -> str:
        """Select the Trade Wars game from available options."""
        return parsing._select_trade_wars_game(screen)

    def _clean_screen_for_display(self, screen: str, max_lines: int = 30) -> list[str]:
        """Clean screen for display by removing padding lines."""
        return parsing._clean_screen_for_display(screen, max_lines)

    # Error handling methods
    def _detect_error_in_screen(self, screen: str) -> str | None:
        """Detect common error messages in screen text."""
        from bbsbot.games.tw2002 import errors

        return errors._detect_error_in_screen(screen)

    def _check_for_loop(self, prompt_id: str) -> bool:
        """Check if we're stuck in a loop seeing the same prompt repeatedly."""
        from bbsbot.games.tw2002 import errors

        return errors._check_for_loop(self, prompt_id)

    # Logging methods
    def _log_trade(self, action: str, sector: int, quantity: int, price: int, total: int, credits_after: int):
        """Log a trade transaction."""
        from bbsbot.games.tw2002 import logging_utils

        logging_utils._log_trade(self, action, sector, quantity, price, total, credits_after)

    def _save_trade_history(self, filename: str = "trade_history.csv"):
        """Save trade history to CSV file."""
        from bbsbot.games.tw2002 import logging_utils

        logging_utils._save_trade_history(self, filename)

    def _print_session_summary(self):
        """Print session statistics summary."""
        from bbsbot.games.tw2002 import logging_utils

        logging_utils._print_session_summary(self)

    # Twerk integration methods
    async def analyze_trade_routes(
        self, data_dir: Path, ship_holds: int | None = None, max_hops: int = 10
    ) -> list[TradeRoute]:
        """Use twerk to find optimal trade routes from game data files."""
        return await bot_twerk.analyze_trade_routes(self, data_dir, ship_holds, max_hops)

    async def get_sector_map(self, data_dir: Path) -> SectorGraph:
        """Use twerk to build sector graph from game data."""
        return await bot_twerk.get_sector_map(self, data_dir)

    async def find_path_twerk(
        self, data_dir: Path, start_sector: int, end_sector: int, max_hops: int = 999
    ) -> list[int] | None:
        """Find shortest path between two sectors using twerk."""
        return await bot_twerk.find_path_twerk(self, data_dir, start_sector, end_sector, max_hops)

    async def get_game_state(self, data_dir: Path) -> dict:
        """Read comprehensive game state from data files using twerk."""
        return await bot_twerk.get_game_state(self, data_dir)

    # Add methods to class
    TradingBot.connect = connect
    TradingBot.login_sequence = login_sequence
    TradingBot.test_login = test_login
    TradingBot.init_knowledge = init_knowledge
    TradingBot.orient = orient
    TradingBot.where_am_i = where_am_i
    TradingBot.recover = recover
    TradingBot.is_safe = is_safe
    TradingBot.is_in_danger = is_in_danger
    TradingBot.go_to_computer = go_to_computer
    TradingBot.go_to_cim = go_to_cim
    TradingBot.get_port_report = get_port_report
    TradingBot.plot_course = plot_course
    TradingBot.go_to_stardock = go_to_stardock
    TradingBot.go_to_tavern = go_to_tavern
    TradingBot.ask_grimy_trader = ask_grimy_trader
    TradingBot.find_path = find_path
    TradingBot.single_trading_cycle = single_trading_cycle
    TradingBot.run_trading_loop = run_trading_loop
    TradingBot.execute_route = execute_route
    TradingBot.wait_and_respond = wait_and_respond
    TradingBot.send_input = send_input
    TradingBot._parse_credits_from_screen = _parse_credits_from_screen
    TradingBot._parse_sector_from_screen = _parse_sector_from_screen
    TradingBot._extract_game_options = _extract_game_options
    TradingBot._select_trade_wars_game = _select_trade_wars_game
    TradingBot._clean_screen_for_display = _clean_screen_for_display
    TradingBot._detect_error_in_screen = _detect_error_in_screen
    TradingBot._check_for_loop = _check_for_loop
    TradingBot._log_trade = _log_trade
    TradingBot._save_trade_history = _save_trade_history
    TradingBot._print_session_summary = _print_session_summary
    TradingBot.analyze_trade_routes = analyze_trade_routes
    TradingBot.get_sector_map = get_sector_map
    TradingBot.find_path_twerk = find_path_twerk
    TradingBot.get_game_state = get_game_state


# Initialize all methods on module load
_add_methods()
