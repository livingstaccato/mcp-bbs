"""Main TradingBot class with state management."""

import time
from typing import Optional

from mcp_bbs.config import get_default_knowledge_root
from mcp_bbs.core.session_manager import SessionManager

from . import connection
from . import login
from . import trading
from . import io
from . import parsing
from . import logging_utils


class TradingBot:
    """Intelligent trading bot for TW2002."""

    def __init__(self):
        self.session_manager = SessionManager()
        self.knowledge_root = get_default_knowledge_root()
        self.session_id: Optional[str] = None
        self.session = None

        # State tracking
        self.current_sector: Optional[int] = None
        self.current_credits: int = 0
        self.cycle_count = 0
        self.step_count = 0

        # Detected prompts tracking
        self.detected_prompts: list[dict] = []

        # Error tracking
        self.error_count = 0
        self.loop_detection: dict[str, int] = {}  # prompt_id -> count
        self.last_prompt_id: Optional[str] = None
        self.stuck_threshold = 3  # Max times to see same prompt before declaring stuck

        # Session tracking
        self.session_start_time = time.time()
        self.trade_history: list[dict] = []  # List of trade records
        self.initial_credits = 0
        self.turns_used = 0
        self.sectors_visited: set[int] = set()

        # Menu navigation tracking
        self.menu_selection_attempts = 0
        self.last_game_letter: Optional[str] = None

    # Connection methods
    async def connect(self, host="localhost", port=2002):
        """Connect to TW2002 BBS."""
        await connection.connect(self, host, port)

    # Login methods
    async def login_sequence(
        self,
        game_password: str = "game",
        character_password: str = "tim",
        username: str = "claude",
    ):
        """Complete login sequence from telnet login to game entry."""
        await login.login_sequence(self, game_password, character_password, username)

    async def test_login(self):
        """Test login sequence only."""
        return await login.test_login(self)

    # Trading methods
    async def single_trading_cycle(self, start_sector: int = 499, max_retries: int = 2):
        """Execute one complete trading cycle (buy→sell) with error recovery."""
        await trading.single_trading_cycle(self, start_sector, max_retries)

    async def run_trading_loop(self, target_credits: int = 5_000_000, max_cycles: int = 20):
        """Run trading loop until target credits or max cycles."""
        await trading.run_trading_loop(self, target_credits, max_cycles)

    # I/O methods
    async def wait_and_respond(self, prompt_id_pattern: Optional[str] = None, timeout_ms: int = 10000):
        """Wait for prompt and return (input_type, prompt_id, screen)."""
        return await io.wait_and_respond(self, prompt_id_pattern, timeout_ms)

    async def send_input(self, keys: str, input_type: Optional[str], wait_after: float = 0.2):
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
    def _detect_error_in_screen(self, screen: str) -> Optional[str]:
        """Detect common error messages in screen text."""
        from . import errors
        return errors._detect_error_in_screen(screen)

    def _check_for_loop(self, prompt_id: str) -> bool:
        """Check if we're stuck in a loop seeing the same prompt repeatedly."""
        from . import errors
        return errors._check_for_loop(self, prompt_id)

    # Logging methods
    def _log_trade(
        self,
        action: str,
        sector: int,
        quantity: int,
        price: int,
        total: int,
        credits_after: int,
    ):
        """Log a trade transaction."""
        logging_utils._log_trade(self, action, sector, quantity, price, total, credits_after)

    def _save_trade_history(self, filename: str = "trade_history.csv"):
        """Save trade history to CSV file."""
        logging_utils._save_trade_history(self, filename)

    def _print_session_summary(self):
        """Print session statistics summary."""
        logging_utils._print_session_summary(self)
