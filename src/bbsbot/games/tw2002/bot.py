"""Main TradingBot class with state management."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import TYPE_CHECKING

from bbsbot.core.session_manager import SessionManager
from bbsbot.core.error_detection import LoopDetector
from bbsbot.paths import default_knowledge_root
from bbsbot.games.tw2002 import connection, io, login, logging_utils, parsing, trading
from bbsbot.games.tw2002.config import BotConfig, load_config
from bbsbot.games.tw2002.orientation import (
    GameState,
    SectorKnowledge,
    OrientationError,
    QuickState,
    orient,
    where_am_i,
    recover_to_safe_state,
    SAFE_CONTEXTS,
    ACTION_CONTEXTS,
    DANGER_CONTEXTS,
    INFO_CONTEXTS,
)

if TYPE_CHECKING:
    from twerk.analysis import SectorGraph, TradeRoute
    from bbsbot.games.tw2002.strategies.base import TradingStrategy
    from bbsbot.games.tw2002.banking import BankingManager
    from bbsbot.games.tw2002.upgrades import UpgradeManager
    from bbsbot.games.tw2002.combat import CombatManager
    from bbsbot.watch.manager import WatchManager


class TradingBot:
    """Intelligent trading bot for TW2002."""

    def __init__(
        self,
        character_name: str = "unknown",
        twerk_data_dir: Path | None = None,
        config: BotConfig | None = None,
    ):
        self.session_manager = SessionManager()
        self.knowledge_root = default_knowledge_root()
        self.session_id: str | None = None
        self.session = None
        self.character_name = character_name

        # Configuration
        self.config = config or BotConfig()

        # Orientation system
        self.game_state: GameState | None = None
        self.sector_knowledge: SectorKnowledge | None = None
        self.twerk_data_dir = twerk_data_dir or (
            Path(self.config.trading.twerk_optimized.data_dir)
            if self.config.trading.twerk_optimized.data_dir else None
        )

        # Strategy system
        self._strategy: TradingStrategy | None = None

        # Subsystems (initialized lazily)
        self._banking: BankingManager | None = None
        self._upgrades: UpgradeManager | None = None
        self._combat: CombatManager | None = None

        # State tracking (legacy - use game_state instead)
        self.current_sector: int | None = None
        self.current_credits: int = 0
        self.cycle_count = 0
        self.step_count = 0

        # Detected prompts tracking
        self.detected_prompts: list[dict] = []

        # Last semantic extraction data (populated by io.wait_and_respond callbacks)
        self.last_semantic_data: dict = {}

        # Error tracking
        self.error_count = 0
        self.loop_detection = LoopDetector(threshold=10)
        self.last_prompt_id: str | None = None

        # Session tracking
        self.session_start_time = time.time()
        self.trade_history: list[dict] = []  # List of trade records
        self.initial_credits = 0
        self.turns_used = 0
        self.sectors_visited: set[int] = set()

        # Scan tracking for D command optimization
        self._rescan_hours = self.config.scanning.rescan_interval_hours

        # Menu navigation tracking
        self.menu_selection_attempts = 0
        self.last_game_letter: str | None = None

        # Optional: watch-socket manager for out-of-band status/event streaming.
        self._watch_manager: WatchManager | None = None

    # -------------------------------------------------------------------------
    # Subsystem properties (lazy initialization)
    # -------------------------------------------------------------------------

    @property
    def strategy(self) -> TradingStrategy | None:
        """Get the current trading strategy."""
        return self._strategy

    @property
    def banking(self) -> BankingManager:
        """Get the banking manager."""
        if self._banking is None:
            from bbsbot.games.tw2002.banking import BankingManager
            self._banking = BankingManager(self.config, self.sector_knowledge)
        return self._banking

    @property
    def upgrades(self) -> UpgradeManager:
        """Get the upgrade manager."""
        if self._upgrades is None:
            from bbsbot.games.tw2002.upgrades import UpgradeManager
            self._upgrades = UpgradeManager(self.config, self.sector_knowledge)
        return self._upgrades

    @property
    def combat(self) -> CombatManager:
        """Get the combat manager."""
        if self._combat is None:
            from bbsbot.games.tw2002.combat import CombatManager
            self._combat = CombatManager(self.config, self.sector_knowledge)
        return self._combat

    def init_strategy(self) -> TradingStrategy:
        """Initialize trading strategy based on config.

        Returns:
            The initialized TradingStrategy
        """
        strategy_name = self.config.trading.strategy

        if strategy_name == "profitable_pairs":
            from bbsbot.games.tw2002.strategies.profitable_pairs import ProfitablePairsStrategy
            self._strategy = ProfitablePairsStrategy(self.config, self.sector_knowledge)
        elif strategy_name == "twerk_optimized":
            from bbsbot.games.tw2002.strategies.twerk_optimized import TwerkOptimizedStrategy
            self._strategy = TwerkOptimizedStrategy(self.config, self.sector_knowledge)
        elif strategy_name == "ai_strategy":
            from bbsbot.games.tw2002.strategies.ai_strategy import AIStrategy
            self._strategy = AIStrategy(self.config, self.sector_knowledge)
            # Inject session logger for feedback loop
            if self.session and self.session.logger:
                self._strategy.set_session_logger(self.session.logger)
            # Optional: allow strategy to emit goal visualization events.
            try:
                self._strategy.set_viz_emitter(self.emit_viz)  # type: ignore[attr-defined]
            except Exception:
                setattr(self._strategy, "_viz_emit", self.emit_viz)
        else:  # Default to opportunistic
            from bbsbot.games.tw2002.strategies.opportunistic import OpportunisticStrategy
            self._strategy = OpportunisticStrategy(self.config, self.sector_knowledge)

        print(f"  [Strategy] Initialized: {self._strategy.name}")

        # Register bot with session manager for MCP debugging
        if self.session_id:
            self.session_manager.register_bot(self.session_id, self)

        return self._strategy

    def set_watch_manager(self, watch_manager: WatchManager | None) -> None:
        """Attach a WatchManager used for broadcasting structured events."""
        self._watch_manager = watch_manager

    def emit_viz(self, kind: str, text: str, *, turn: int | None = None, **extra: object) -> None:
        """Emit a goal-visualization payload over the watch socket (if enabled)."""
        if self._watch_manager is None:
            return
        payload: dict[str, object] = {
            "kind": kind,
            "text": text,
            "turn": turn,
            "character_name": self.character_name,
        }
        payload.update(extra)
        self._watch_manager.emit_event("viz", payload)

    # -------------------------------------------------------------------------
    # Scanning optimization
    # -------------------------------------------------------------------------

    def needs_scan(self, sector: int | None = None) -> bool:
        """Check if current or specified sector needs scanning.

        Uses config settings for scan_on_first_visit and rescan_interval.

        Args:
            sector: Sector to check (uses current sector if None)

        Returns:
            True if D command should be run
        """
        if sector is None:
            sector = self.current_sector
        if sector is None:
            return True  # Unknown sector, definitely scan

        if not self.sector_knowledge:
            return True

        # Check config settings
        if not self.config.scanning.scan_on_first_visit:
            return False

        return self.sector_knowledge.needs_scan(sector, self._rescan_hours)

    def mark_scanned(self, sector: int | None = None) -> None:
        """Mark current or specified sector as scanned.

        Args:
            sector: Sector to mark (uses current sector if None)
        """
        if sector is None:
            sector = self.current_sector
        if sector is None or not self.sector_knowledge:
            return

        self.sector_knowledge.mark_scanned(sector)

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
    def init_knowledge(self, host: str = "localhost", port: int = 2002, game_letter: str | None = None) -> None:
        """Initialize sector knowledge for this character/server/game.

        Args:
            host: BBS host
            port: BBS port
            game_letter: Game selection letter (A, B, C, etc.) to scope data per-game on same BBS
        """
        # Include game_letter in path to separate data for different games on same BBS
        if game_letter:
            knowledge_dir = self.knowledge_root / "tw2002" / f"{host}_{port}_game{game_letter}"
        else:
            knowledge_dir = self.knowledge_root / "tw2002" / f"{host}_{port}"

        self.sector_knowledge = SectorKnowledge(
            knowledge_dir=knowledge_dir,
            character_name=self.character_name,
            twerk_data_dir=self.twerk_data_dir,
        )
        game_info = f"_game{game_letter}" if game_letter else ""
        print(f"  [Knowledge] Initialized for {self.character_name} @ {host}:{port}{game_info}")
        print(f"  [Knowledge] Known sectors: {self.sector_knowledge.known_sector_count()}")

    async def orient(self, force_scan: bool = False) -> GameState:
        """Run full orientation sequence.

        1. Safety - Reach a known stable state
        2. Context - Gather comprehensive game state (D command if needed)
        3. Navigation - Record observations for future pathfinding

        Args:
            force_scan: If True, always run D command regardless of scan state

        Returns:
            Complete GameState

        Raises:
            OrientationError if unable to establish safe state
        """
        # Check if we need to scan before full orient
        from time import time as _time
        t0 = _time()
        should_scan = force_scan or self.needs_scan()

        if should_scan:
            self.game_state = await orient(self, self.sector_knowledge)
            # Mark as scanned after successful orient
            if self.game_state.sector:
                self.mark_scanned(self.game_state.sector)
        else:
            # Fast path: skip D command, just check context
            quick_state = await self.where_am_i()
            if quick_state.is_safe:
                # Extract semantic data for credits and other state
                # The session read already captured kv_data during where_am_i()
                try:
                    result = await self.session.read(timeout_ms=10, max_bytes=1024)
                    kv_data = result.get("kv_data", {})
                except Exception:
                    kv_data = {}

                # Merge kv_data with last_semantic_data for completeness
                merged_kv = dict(self.last_semantic_data)
                merged_kv.update({k: v for k, v in kv_data.items() if v is not None})

                # Use cached knowledge
                self.game_state = GameState(
                    context=quick_state.context,
                    sector=quick_state.sector,
                    raw_screen=quick_state.screen,
                    prompt_id=quick_state.prompt_id,
                    # Extract critical state from semantic data
                    credits=merged_kv.get('credits'),
                    turns_left=merged_kv.get('turns_left'),
                    fighters=merged_kv.get('fighters'),
                    shields=merged_kv.get('shields'),
                )
                # Fill in from knowledge if available
                if self.sector_knowledge and quick_state.sector:
                    info = self.sector_knowledge.get_sector_info(quick_state.sector)
                    if info:
                        self.game_state.warps = info.warps
                        self.game_state.has_port = info.has_port
                        self.game_state.port_class = info.port_class
                        self.game_state.has_planet = info.has_planet
                        self.game_state.planet_names = info.planet_names
                fast_ms = (_time() - t0) * 1000
                print(f"  [Orient] Fast path: {self.game_state.summary()} [{fast_ms:.0f}ms]")
            else:
                # Not safe, need full orient
                self.game_state = await orient(self, self.sector_knowledge)
                if self.game_state.sector:
                    self.mark_scanned(self.game_state.sector)

        # Sync legacy state tracking
        if self.game_state.sector:
            self.current_sector = self.game_state.sector
            self.sectors_visited.add(self.game_state.sector)
        if self.game_state.credits:
            self.current_credits = self.game_state.credits

        # Update combat tracking
        if self._combat:
            self._combat.update_from_state(self.game_state)

        return self.game_state

    async def where_am_i(self, timeout_ms: int = 500) -> QuickState:
        """Fast state check - quickly determine where we are.

        This is the FAST "where am I" function. It reads the screen once,
        detects context, and returns immediately. Use this when you need
        to quickly check state without full orientation.

        For full state gathering, use orient() instead.

        Args:
            timeout_ms: Max time to wait for screen data

        Returns:
            QuickState with context and basic info
        """
        return await where_am_i(self, timeout_ms)

    async def recover(self, max_attempts: int = 20) -> QuickState:
        """Attempt to recover to a safe state from any situation.

        This is the fail-safe recovery function. It will try various
        escape sequences to get back to a command prompt.

        Args:
            max_attempts: Maximum recovery attempts

        Returns:
            QuickState after recovery

        Raises:
            OrientationError if recovery fails
        """
        return await recover_to_safe_state(self, max_attempts)

    def is_safe(self) -> bool:
        """Quick check if we're in a safe state based on last game_state."""
        if not self.game_state:
            return False
        return self.game_state.context in SAFE_CONTEXTS

    def is_in_danger(self) -> bool:
        """Quick check if we're in a dangerous state."""
        if not self.game_state:
            return False
        return self.game_state.context in DANGER_CONTEXTS

    # -------------------------------------------------------------------------
    # Navigation shortcuts - common game locations
    # -------------------------------------------------------------------------

    async def go_to_computer(self) -> bool:
        """Navigate to Computer menu from sector command.

        Returns:
            True if successfully at Computer menu
        """
        state = await self.where_am_i()
        if state.context != "sector_command":
            print(f"  [Computer] Not at sector command (at {state.context})")
            return False

        await self.session.send("C")
        await asyncio.sleep(0.5)

        state = await self.where_am_i()
        return state.context == "computer_menu"

    async def go_to_cim(self) -> bool:
        """Navigate to CIM (Computer Interrogation Mode).

        CIM provides machine-readable data dumps for:
        - Port data (zero-turn port enumeration)
        - Sector data (universe mapping)
        - Ship data (scanner results)

        Returns:
            True if successfully in CIM mode
        """
        # First get to computer menu
        if not await self.go_to_computer():
            return False

        # Enter CIM mode (^ character or ALT-200)
        await self.session.send("^")
        await asyncio.sleep(0.3)

        state = await self.where_am_i()
        return state.context == "cim_mode"

    async def get_port_report(self) -> str:
        """Get human-readable port report from Computer menu.

        Returns:
            Port report text or empty string on failure
        """
        if not await self.go_to_computer():
            return ""

        # Request port report
        await self.session.send("R")
        await asyncio.sleep(1.0)

        result = await self.session.read(timeout_ms=2000, max_bytes=16384)
        screen = result.get("screen", "")

        # Return to safe state
        await self.recover()

        return screen

    async def plot_course(self, destination: int) -> bool:
        """Use course plotter to plan route (zero turns).

        Args:
            destination: Target sector number

        Returns:
            True if course was successfully plotted
        """
        if not await self.go_to_computer():
            return False

        # Access course plotter
        await self.session.send("F")
        await asyncio.sleep(0.5)

        # Enter destination
        await self.session.send(f"{destination}\r")
        await asyncio.sleep(1.0)

        # Read result
        result = await self.session.read(timeout_ms=2000, max_bytes=8192)
        screen = result.get("screen", "")

        # Check if path was found
        success = "path" in screen.lower() or "route" in screen.lower()

        # Return to safe state
        await self.recover()

        return success

    async def go_to_stardock(self) -> bool:
        """Navigate to StarDock (must be in StarDock sector).

        Returns:
            True if successfully at StarDock
        """
        state = await self.where_am_i()
        if state.context != "sector_command":
            return False

        # Try to enter StarDock
        await self.session.send("S")
        await asyncio.sleep(0.5)

        state = await self.where_am_i()
        return state.context == "stardock"

    async def go_to_tavern(self) -> bool:
        """Navigate to Lost Trader's Tavern (must be at StarDock).

        Returns:
            True if successfully at Tavern
        """
        state = await self.where_am_i()

        # If not at StarDock, try to get there
        if state.context != "stardock":
            if not await self.go_to_stardock():
                return False

        # Enter Tavern
        await self.session.send("T")
        await asyncio.sleep(0.5)

        state = await self.where_am_i()
        return state.context == "tavern"

    async def ask_grimy_trader(self, topic: str) -> str:
        """Ask Grimy Trader for information.

        Args:
            topic: One of "TRADER", "FEDERATION", "MAFIA"

        Returns:
            Information received or empty string on failure
        """
        if not await self.go_to_tavern():
            return ""

        # Talk to Grimy Trader
        await self.session.send("T")
        await asyncio.sleep(0.5)

        # Ask about topic
        await self.session.send(f"{topic}\r")
        await asyncio.sleep(1.0)

        result = await self.session.read(timeout_ms=2000, max_bytes=8192)
        screen = result.get("screen", "")

        # Return to safe state
        await self.recover()

        return screen

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

    async def execute_route(
        self,
        route,
        quantity: int | None = None,
        max_retries: int = 2,
        data_dir: Path | None = None,
    ) -> dict:
        """Execute a twerk-analyzed trade route via terminal.

        Args:
            route: TradeRoute from twerk analysis
            quantity: Units to trade (defaults to route.max_quantity or ship holds)
            max_retries: Maximum retry attempts for recoverable errors
            data_dir: Optional TW2002 data directory for twerk pathing

        Returns:
            Dictionary with trade results including success, profit, etc.
        """
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
