# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Twerk-optimized trading strategy (Mode C).

Uses twerk analysis for optimal route calculation.
Periodically recalculates routes based on game data.
"""

from __future__ import annotations

import logging
from pathlib import Path
from time import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from bbsbot.games.tw2002.strategies.base import (
    TradeAction,
    TradeOpportunity,
    TradingStrategy,
)

if TYPE_CHECKING:
    from bbsbot.games.tw2002.config import BotConfig
    from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge

logger = logging.getLogger(__name__)


class TwerkRoute(BaseModel):
    """A route calculated by twerk."""

    sectors: list[int]
    commodity: str
    expected_profit: int
    estimated_turns: int
    calculated_at: float = Field(default_factory=time)

    model_config = ConfigDict(extra="ignore")


class TwerkOptimizedStrategy(TradingStrategy):
    """Trading strategy using twerk data analysis.

    This strategy:
    1. Loads sector/port data from twerk files
    2. Calculates optimal trading routes
    3. Executes routes with maximum efficiency
    4. Periodically recalculates as game state changes
    """

    def __init__(self, config: BotConfig, knowledge: SectorKnowledge):
        super().__init__(config, knowledge)
        self._settings = config.trading.twerk_optimized
        self._routes: list[TwerkRoute] = []
        self._current_route: TwerkRoute | None = None
        self._route_position: int = 0
        self._last_calculation: float = 0
        self._trades_since_recalc: int = 0
        self._twerk_available = False

        # Try to load twerk
        self._init_twerk()

    @property
    def name(self) -> str:
        return "twerk_optimized"

    def _init_twerk(self) -> None:
        """Initialize twerk library if available."""
        try:
            from twerk.parsers import parse_ports, parse_sectors

            self._twerk_available = True
            logger.info("Twerk library available")
        except ImportError:
            logger.warning("Twerk library not available, falling back to basic trading")
            self._twerk_available = False

    def get_next_action(self, state: GameState) -> tuple[TradeAction, dict]:
        """Determine next action using twerk-optimized routes."""
        # Safety checks
        if self.should_retreat(state):
            safe_sector = self._find_safe_sector(state)
            self._current_route = None
            return TradeAction.RETREAT, {"safe_sector": safe_sector}

        # Check banking
        if self.should_bank(state):
            return TradeAction.BANK, {}

        # Check upgrades
        should_upgrade, upgrade_type = self.should_upgrade(state)
        if should_upgrade:
            return TradeAction.UPGRADE, {"upgrade_type": upgrade_type}

        # Check if we need to recalculate routes
        if self._should_recalculate():
            self._calculate_routes()

        # If no twerk, fall back to basic exploration
        if not self._twerk_available or not self._routes:
            return self._fallback_action(state)

        # Get or start a route
        if self._current_route is None:
            self._current_route = self._select_best_route(state)
            self._route_position = 0
            if self._current_route is None:
                return TradeAction.WAIT, {}

        # Execute current route
        return self._execute_route(state)

    def find_opportunities(self, state: GameState) -> list[TradeOpportunity]:
        """Find opportunities based on twerk analysis."""
        if not self._twerk_available:
            return []

        if self._should_recalculate():
            self._calculate_routes()

        opportunities = []
        current = state.sector

        for route in self._routes[:5]:
            # Calculate distance from current position
            if not route.sectors:
                continue

            start = route.sectors[0]
            path = self.knowledge.find_path(current, start)
            if not path:
                continue

            distance = len(path) - 1 + len(route.sectors) - 1

            opp = TradeOpportunity(
                buy_sector=route.sectors[0],
                sell_sector=route.sectors[-1] if len(route.sectors) > 1 else route.sectors[0],
                commodity=route.commodity,
                expected_profit=route.expected_profit,
                distance=distance,
                path_to_buy=path,
                path_to_sell=route.sectors,
            )
            opportunities.append(opp)

        opportunities.sort(key=lambda o: o.profit_per_turn, reverse=True)
        return opportunities

    def _should_recalculate(self) -> bool:
        """Check if routes should be recalculated."""
        if not self._routes:
            return True

        interval = self._settings.recalculate_interval
        if interval <= 0:
            return False

        return self._trades_since_recalc >= interval

    def _calculate_routes(self) -> None:
        """Calculate optimal routes using twerk."""
        if not self._twerk_available:
            return

        logger.info("Calculating twerk-optimized routes...")
        self._last_calculation = time()
        self._trades_since_recalc = 0

        data_dir = self._settings.data_dir
        if not data_dir:
            # Try to find data dir from knowledge
            if hasattr(self.knowledge, "twerk_data_dir") and self.knowledge.twerk_data_dir:
                data_dir = str(self.knowledge.twerk_data_dir)
            else:
                logger.warning("No twerk data directory configured")
                return

        data_path = Path(data_dir)
        if not data_path.exists():
            logger.warning(f"Twerk data directory not found: {data_path}")
            return

        try:
            from twerk.analysis import find_trade_routes
            from twerk.parsers import parse_ports, parse_sectors

            # TWGS typically stores these as uppercase; accept either.
            sectors_path = data_path / "twsect.dat"
            ports_path = data_path / "twport.dat"
            if not sectors_path.exists():
                sectors_path = data_path / "TWSECT.DAT"
            if not ports_path.exists():
                ports_path = data_path / "TWPORT.DAT"

            if not sectors_path.exists() or not ports_path.exists():
                logger.warning("Twerk data files not found")
                return

            sectors = parse_sectors(sectors_path)
            ports = parse_ports(ports_path)

            # Find optimal routes
            # Use ship holds from knowledge or default to 20
            holds = getattr(self.knowledge, "ship_holds", 20)
            max_hops = 5  # Maximum warp hops for route calculation
            routes = find_trade_routes(sectors, ports, holds, max_hops)

            self._routes = [
                TwerkRoute(
                    sectors=r.path,
                    commodity=r.commodity,
                    expected_profit=r.profit,
                    estimated_turns=r.turns,
                )
                for r in routes[:20]  # Keep top 20 routes
            ]

            logger.info(f"Calculated {len(self._routes)} optimal routes")

        except ImportError as e:
            logger.error(f"Failed to import twerk modules: {e}")
            self._twerk_available = False
        except Exception as e:
            logger.error(f"Failed to calculate routes: {e}")

    def _select_best_route(self, state: GameState) -> TwerkRoute | None:
        """Select the best route from current position."""
        if not self._routes:
            return None

        current = state.sector
        if current is None:
            return self._routes[0] if self._routes else None

        # Find route with best accessibility
        best_route = None
        best_score = 0

        for route in self._routes:
            if not route.sectors:
                continue

            path = self.knowledge.find_path(current, route.sectors[0])
            if not path:
                continue

            travel_turns = len(path) - 1
            total_turns = travel_turns + route.estimated_turns

            score = route.expected_profit / max(total_turns, 1)
            if score > best_score:
                best_score = score
                best_route = route

        return best_route

    def _execute_route(self, state: GameState) -> tuple[TradeAction, dict]:
        """Execute the current route."""
        route = self._current_route
        if not route or not route.sectors:
            self._current_route = None
            return TradeAction.WAIT, {}

        def _commodity_index(commodity: str) -> int | None:
            c = (commodity or "").lower().strip()
            if c in ("fuel", "fuel_ore", "ore", "fuel ore"):
                return 0
            if c in ("org", "organics"):
                return 1
            if c in ("equip", "equipment"):
                return 2
            return None

        def _trade_action_from_port_class(port_class: str | None, commodity: str) -> str | None:
            """Infer buy/sell intent from the port class.

            TW port class letters represent what the *port does*:
            - 'S' = port sells that commodity to us -> we should BUY
            - 'B' = port buys that commodity from us -> we should SELL
            """
            if not port_class:
                return None
            pc = str(port_class).strip().upper()
            idx = _commodity_index(commodity)
            if idx is None or len(pc) < idx + 1:
                return None
            letter = pc[idx]
            if letter == "S":
                return "buy"
            if letter == "B":
                return "sell"
            return None

        current = state.sector
        position = self._route_position

        # Are we at a route sector?
        if position < len(route.sectors):
            target = route.sectors[position]

            if current == target:
                # At route sector - trade or move to next
                if state.has_port:
                    # Decide buy vs sell based on the *actual port class* for this commodity.
                    action = _trade_action_from_port_class(state.port_class, route.commodity)

                    # If we can't infer direction (unknown port class), don't burn turns guessing.
                    if action is None:
                        self._route_position += 1
                        return self._execute_route(state)

                    # Avoid no-op sells when we have 0 cargo (common early-game).
                    cargo = 0
                    if route.commodity == "fuel_ore":
                        cargo = int(state.cargo_fuel_ore or 0)
                    elif route.commodity == "organics":
                        cargo = int(state.cargo_organics or 0)
                    elif route.commodity == "equipment":
                        cargo = int(state.cargo_equipment or 0)

                    if action == "sell" and cargo <= 0:
                        # Nothing to sell here; continue along route to find a selling port.
                        self._route_position += 1
                        return self._execute_route(state)

                    # Avoid buying when we're full; continue along route to find a buying port.
                    if action == "buy" and (state.holds_free is not None) and int(state.holds_free) <= 0:
                        self._route_position += 1
                        return self._execute_route(state)

                    # Trade here. TradeOpportunity is primarily for logging/visibility; set fields
                    # to "current sector" for the chosen action.
                    opp = TradeOpportunity(
                        buy_sector=int(current or 0) if action == "buy" else int(route.sectors[0]),
                        sell_sector=int(current or 0) if action == "sell" else int(route.sectors[-1]),
                        commodity=route.commodity,
                        expected_profit=route.expected_profit,
                        distance=max(0, len(route.sectors) - 1),
                    )

                    self._route_position += 1
                    return TradeAction.TRADE, {"opportunity": opp, "action": action}
                else:
                    # No port, move to next sector
                    self._route_position += 1
                    return self._execute_route(state)
            else:
                # Navigate to target
                path = self.knowledge.find_path(current, target)
                if path:
                    return TradeAction.MOVE, {
                        "target_sector": target,
                        "path": path,
                    }
                else:
                    # Can't reach, abandon route
                    self._current_route = None
                    return TradeAction.WAIT, {}
        else:
            # Route complete
            self._current_route = None
            self._trades_since_recalc += 1
            return TradeAction.WAIT, {}

    def _fallback_action(self, state: GameState) -> tuple[TradeAction, dict]:
        """Fallback behavior when twerk is not available."""
        # Basic exploration/trading
        if state.has_port:
            # Trade at current port if possible
            opp = TradeOpportunity(
                buy_sector=state.sector or 0,
                sell_sector=state.sector or 0,
                commodity="equipment",
                expected_profit=300,
                distance=0,
            )
            return TradeAction.TRADE, {"opportunity": opp}

        # Explore
        if state.warps:
            import random

            direction = random.choice(state.warps)
            return TradeAction.EXPLORE, {"direction": direction}

        return TradeAction.WAIT, {}

    def _find_safe_sector(self, state: GameState) -> int | None:
        """Find a safe sector to retreat to."""
        warps = state.warps or []
        return warps[0] if warps else None

    def record_result(self, result) -> None:
        """Record result and track trades for recalculation."""
        super().record_result(result)

        if result.action == TradeAction.TRADE and result.success:
            self._trades_since_recalc += 1

    def force_recalculate(self) -> None:
        """Force immediate route recalculation."""
        self._trades_since_recalc = self._settings.recalculate_interval
