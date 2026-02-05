"""Main TradingBot class with state management."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from mcp_bbs.config import get_default_knowledge_root
from mcp_bbs.core.session_manager import SessionManager

from . import connection
from . import login
from . import trading
from . import io
from . import parsing
from . import logging_utils
from .orientation import GameState, SectorKnowledge, OrientationError, orient

if TYPE_CHECKING:
    from twerk.analysis import SectorGraph, TradeRoute


class TradingBot:
    """Intelligent trading bot for TW2002."""

    def __init__(
        self,
        character_name: str = "unknown",
        twerk_data_dir: Path | None = None,
    ):
        self.session_manager = SessionManager()
        self.knowledge_root = get_default_knowledge_root()
        self.session_id: str | None = None
        self.session = None
        self.character_name = character_name

        # Orientation system
        self.game_state: GameState | None = None
        self.sector_knowledge: SectorKnowledge | None = None
        self.twerk_data_dir = twerk_data_dir

        # State tracking (legacy - use game_state instead)
        self.current_sector: int | None = None
        self.current_credits: int = 0
        self.cycle_count = 0
        self.step_count = 0

        # Detected prompts tracking
        self.detected_prompts: list[dict] = []

        # Error tracking
        self.error_count = 0
        self.loop_detection: dict[str, int] = {}  # prompt_id -> count
        self.last_prompt_id: str | None = None
        self.stuck_threshold = 3  # Max times to see same prompt before declaring stuck

        # Session tracking
        self.session_start_time = time.time()
        self.trade_history: list[dict] = []  # List of trade records
        self.initial_credits = 0
        self.turns_used = 0
        self.sectors_visited: set[int] = set()

        # Menu navigation tracking
        self.menu_selection_attempts = 0
        self.last_game_letter: str | None = None

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

    # Orientation methods
    def init_knowledge(self, host: str = "localhost", port: int = 2002) -> None:
        """Initialize sector knowledge for this character/server."""
        knowledge_dir = self.knowledge_root / "tw2002" / f"{host}_{port}"
        self.sector_knowledge = SectorKnowledge(
            knowledge_dir=knowledge_dir,
            character_name=self.character_name,
            twerk_data_dir=self.twerk_data_dir,
        )
        print(f"  [Knowledge] Initialized for {self.character_name} @ {host}:{port}")
        print(f"  [Knowledge] Known sectors: {self.sector_knowledge.known_sector_count()}")

    async def orient(self) -> GameState:
        """Run full orientation sequence.

        1. Safety - Reach a known stable state
        2. Context - Gather comprehensive game state
        3. Navigation - Record observations for future pathfinding

        Returns:
            Complete GameState

        Raises:
            OrientationError if unable to establish safe state
        """
        self.game_state = await orient(self, self.sector_knowledge)

        # Sync legacy state tracking
        if self.game_state.sector:
            self.current_sector = self.game_state.sector
            self.sectors_visited.add(self.game_state.sector)
        if self.game_state.credits:
            self.current_credits = self.game_state.credits

        return self.game_state

    def find_path(self, destination: int) -> list[int] | None:
        """Find path from current sector to destination.

        Uses sector knowledge (discovery + cache + optional twerk).

        Returns:
            List of sectors to traverse, or None if unknown
        """
        if not self.sector_knowledge:
            return None
        if not self.current_sector:
            return None
        return self.sector_knowledge.find_path(self.current_sector, destination)

    # Trading methods
    async def single_trading_cycle(self, start_sector: int = 499, max_retries: int = 2):
        """Execute one complete trading cycle (buy→sell) with error recovery."""
        await trading.single_trading_cycle(self, start_sector, max_retries)

    async def run_trading_loop(self, target_credits: int = 5_000_000, max_cycles: int = 20):
        """Run trading loop until target credits or max cycles."""
        await trading.run_trading_loop(self, target_credits, max_cycles)

    # I/O methods
    async def wait_and_respond(self, prompt_id_pattern: str | None = None, timeout_ms: int = 10000):
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

    # -------------------------------------------------------------------------
    # Twerk integration methods - direct file access for analysis
    # -------------------------------------------------------------------------

    async def analyze_trade_routes(
        self,
        data_dir: Path,
        ship_holds: int | None = None,
        max_hops: int = 10,
    ) -> list[TradeRoute]:
        """Use twerk to find optimal trade routes from game data files.

        Args:
            data_dir: Path to TW2002 data directory containing twsect.dat, twport.dat
            ship_holds: Number of cargo holds (uses current ship if None)
            max_hops: Maximum warp hops to consider for routes

        Returns:
            List of TradeRoute objects sorted by efficiency score
        """
        from twerk.analysis import find_trade_routes
        from twerk.parsers import parse_ports, parse_sectors

        sectors_path = data_dir / "twsect.dat"
        ports_path = data_dir / "twport.dat"

        if not sectors_path.exists():
            raise FileNotFoundError(f"Sector data not found: {sectors_path}")
        if not ports_path.exists():
            raise FileNotFoundError(f"Port data not found: {ports_path}")

        sectors = parse_sectors(sectors_path)
        ports = parse_ports(ports_path)

        # Use provided holds or default to 20
        holds = ship_holds if ship_holds is not None else 20

        routes = find_trade_routes(sectors, ports, holds, max_hops)

        # Sort by efficiency score (highest first)
        return sorted(routes, key=lambda r: r.efficiency_score, reverse=True)

    async def get_sector_map(self, data_dir: Path) -> SectorGraph:
        """Use twerk to build sector graph from game data.

        Args:
            data_dir: Path to TW2002 data directory containing twsect.dat

        Returns:
            SectorGraph for pathfinding and navigation
        """
        from twerk.analysis import SectorGraph
        from twerk.parsers import parse_sectors

        sectors_path = data_dir / "twsect.dat"

        if not sectors_path.exists():
            raise FileNotFoundError(f"Sector data not found: {sectors_path}")

        sectors = parse_sectors(sectors_path)
        return SectorGraph.from_sectors(sectors)

    async def find_path(
        self,
        data_dir: Path,
        start_sector: int,
        end_sector: int,
        max_hops: int = 999,
    ) -> list[int] | None:
        """Find shortest path between two sectors using twerk.

        Args:
            data_dir: Path to TW2002 data directory
            start_sector: Starting sector ID
            end_sector: Destination sector ID
            max_hops: Maximum warp hops to search

        Returns:
            List of sector IDs from start to end, or None if no path
        """
        graph = await self.get_sector_map(data_dir)
        return graph.bfs_path(start_sector, end_sector, max_hops)

    async def get_game_state(self, data_dir: Path) -> dict:
        """Read comprehensive game state from data files using twerk.

        Args:
            data_dir: Path to TW2002 data directory

        Returns:
            Dictionary with players, ports, sectors, config info
        """
        from twerk.parsers import (
            parse_config,
            parse_players,
            parse_ports,
            parse_sectors,
        )

        result: dict = {"data_dir": str(data_dir)}

        # Config
        config_path = data_dir / "twcfig.dat"
        if config_path.exists():
            config = parse_config(config_path)
            result["config"] = {
                "game_title": config.game_title,
                "turns_per_day": config.header_values[0] if config.header_values else 0,
            }

        # Players
        players_path = data_dir / "twuser.dat"
        if players_path.exists():
            players, _ = parse_players(players_path)
            active_players = [p for p in players if p.name and p.name.strip()]
            result["players"] = {
                "total": len(active_players),
                "names": [p.name for p in active_players[:10]],  # First 10
            }

        # Ports
        ports_path = data_dir / "twport.dat"
        if ports_path.exists():
            ports = parse_ports(ports_path)
            active_ports = [p for p in ports if p.sector_id > 0]
            result["ports"] = {
                "total": len(active_ports),
            }

        # Sectors
        sectors_path = data_dir / "twsect.dat"
        if sectors_path.exists():
            sectors = parse_sectors(sectors_path)
            result["sectors"] = {
                "total": len(sectors),
            }

        return result
