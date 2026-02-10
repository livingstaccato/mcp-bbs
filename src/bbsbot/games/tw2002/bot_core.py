"""Core TradingBot class with state management and subsystems."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING

from bbsbot.core.error_detection import LoopDetector
from bbsbot.core.session_manager import SessionManager
from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge
from bbsbot.paths import default_knowledge_root

if TYPE_CHECKING:
    from bbsbot.games.tw2002.banking import BankingManager
    from bbsbot.games.tw2002.combat import CombatManager
    from bbsbot.games.tw2002.strategies.base import TradingStrategy
    from bbsbot.games.tw2002.upgrades import UpgradeManager
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
            Path(self.config.trading.twerk_optimized.data_dir) if self.config.trading.twerk_optimized.data_dir else None
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

        # Menu re-entry tracking (persistent across login phase)
        self.menu_reentry_count: int = 0
        self.last_menu_reentry_time: float = 0
        self.max_menu_reentries: int = 5  # Fail after 5 returns to menu

        # Diagnostic buffer for stuck bot analysis
        self.diagnostic_buffer: dict = {
            "recent_screens": [],
            "recent_prompts": [],
            "max_history": 20,
        }

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

        Raises:
            RuntimeError: If sector_knowledge is not initialized
        """
        # CRITICAL: Ensure knowledge is initialized before creating strategy
        if self.sector_knowledge is None:
            raise RuntimeError(
                "Cannot initialize strategy: sector_knowledge is None. Call init_knowledge() before init_strategy()"
            )

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
                self._strategy._viz_emit = self.emit_viz
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

    async def disconnect(self) -> None:
        """Disconnect the underlying BBS session (if any) and release resources.

        This is used by swarm workers to perform clean reconnects during recovery.
        """
        sid = self.session_id
        self.session_id = None
        self.session = None
        if not sid:
            return
        try:
            await self.session_manager.close_session(sid)
        except Exception:
            return
