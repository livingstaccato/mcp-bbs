"""Opportunistic trading strategy (Mode B).

Explores the universe while trading opportunistically at ports
encountered during exploration. Balances exploration with profit.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass

from twbot.config import BotConfig
from twbot.orientation import GameState, SectorKnowledge
from twbot.strategies.base import (
    TradeAction,
    TradeOpportunity,
    TradingStrategy,
)

logger = logging.getLogger(__name__)


@dataclass
class ExplorationState:
    """Tracks exploration progress."""

    wanders_without_trade: int = 0
    last_trade_sector: int | None = None
    explored_this_session: set[int] | None = None

    def __post_init__(self):
        if self.explored_this_session is None:
            self.explored_this_session = set()


class OpportunisticStrategy(TradingStrategy):
    """Opportunistic trading with exploration.

    This strategy:
    1. Trades at any port encountered if profitable
    2. Explores unknown sectors with configurable probability
    3. Wanders to known sectors when not exploring
    4. Respects max_wander_without_trade limit
    """

    def __init__(self, config: BotConfig, knowledge: SectorKnowledge):
        super().__init__(config, knowledge)
        self._exploration = ExplorationState()
        self._settings = config.trading.opportunistic

    @property
    def name(self) -> str:
        return "opportunistic"

    def get_next_action(self, state: GameState) -> tuple[TradeAction, dict]:
        """Determine next action based on current state.

        Priority:
        1. Check for danger/retreat
        2. Check for banking opportunity
        3. Check for upgrade opportunity
        4. Trade if at a port with cargo or profit opportunity
        5. Explore or wander
        """
        # Safety checks first
        if self.should_retreat(state):
            safe_sector = self._find_safe_sector(state)
            return TradeAction.RETREAT, {"safe_sector": safe_sector}

        # Check banking
        if self.should_bank(state):
            return TradeAction.BANK, {}

        # Check upgrades
        should_upgrade, upgrade_type = self.should_upgrade(state)
        if should_upgrade:
            return TradeAction.UPGRADE, {"upgrade_type": upgrade_type}

        # At a port? Consider trading
        if state.has_port and state.context == "sector_command":
            opportunities = self.find_opportunities(state)
            if opportunities:
                # Take the best local opportunity
                best = opportunities[0]
                return TradeAction.TRADE, {"opportunity": best}

        # Should we explore or wander?
        if self._should_explore():
            direction = self._pick_exploration_direction(state)
            if direction:
                return TradeAction.EXPLORE, {"direction": direction}

        # Wander to a known sector
        target = self._pick_wander_target(state)
        if target:
            path = self.knowledge.find_path(state.sector, target)
            if path and len(path) > 1:
                return TradeAction.MOVE, {"target_sector": target, "path": path}

        # Check if we've wandered too long
        if self._exploration.wanders_without_trade >= self._settings.max_wander_without_trade:
            logger.warning("Max wander without trade reached, resetting")
            self._exploration.wanders_without_trade = 0

        # Nothing to do
        return TradeAction.WAIT, {}

    def find_opportunities(self, state: GameState) -> list[TradeOpportunity]:
        """Find trading opportunities from current position.

        For opportunistic strategy, we focus on:
        1. Current sector port (immediate opportunity)
        2. Adjacent sectors with known ports
        """
        opportunities = []
        current = state.sector
        if current is None:
            return opportunities

        # Current sector opportunity
        if state.has_port and state.port_class:
            opp = self._evaluate_port(current, state.port_class, 0)
            if opp:
                opportunities.append(opp)

        # Adjacent sectors
        warps = state.warps or []
        for adjacent in warps:
            info = self.knowledge.get_sector_info(adjacent)
            if info and info.has_port and info.port_class:
                opp = self._evaluate_port(adjacent, info.port_class, 1)
                if opp:
                    opportunities.append(opp)

        # Sort by profit per turn
        opportunities.sort(key=lambda o: o.profit_per_turn, reverse=True)
        return opportunities

    def _evaluate_port(
        self,
        sector: int,
        port_class: str,
        distance: int,
    ) -> TradeOpportunity | None:
        """Evaluate a port for trading opportunity.

        Port classes:
        - B = Buys (we sell)
        - S = Sells (we buy)

        Class format: "BBS" = Buys Fuel, Buys Organics, Sells Equipment
        Position: 0=Fuel Ore, 1=Organics, 2=Equipment

        Args:
            sector: Sector with the port
            port_class: Port class string (e.g., "BBS", "SSB")
            distance: Hops from current position

        Returns:
            TradeOpportunity if profitable, None otherwise
        """
        if not port_class or len(port_class) != 3:
            return None

        # Determine what we can trade
        # For opportunistic, we just want any tradeable commodity
        commodities = ["fuel_ore", "organics", "equipment"]
        for i, char in enumerate(port_class):
            if char == "B":  # Port buys = we sell
                # We'd need cargo to sell
                # For now, estimate profit based on typical margins
                return TradeOpportunity(
                    buy_sector=0,  # Will be filled when we find a selling port
                    sell_sector=sector,
                    commodity=commodities[i],
                    expected_profit=500,  # Conservative estimate
                    distance=distance,
                    confidence=0.6,
                )
            elif char == "S":  # Port sells = we buy
                # We can buy here
                return TradeOpportunity(
                    buy_sector=sector,
                    sell_sector=0,  # Will be filled when we find a buying port
                    commodity=commodities[i],
                    expected_profit=500,
                    distance=distance,
                    confidence=0.6,
                )

        return None

    def _should_explore(self) -> bool:
        """Decide whether to explore unknown sectors."""
        return random.random() < self._settings.explore_chance

    def _pick_exploration_direction(self, state: GameState) -> int | None:
        """Pick an unexplored warp direction.

        Args:
            state: Current game state

        Returns:
            Sector number to explore, or None if all explored
        """
        warps = state.warps or []
        unexplored = [
            w for w in warps
            if w not in self._exploration.explored_this_session
            and self.knowledge.get_warps(w) is None
        ]

        if unexplored:
            return random.choice(unexplored)

        # All adjacent sectors explored, mark this session
        if state.sector:
            self._exploration.explored_this_session.add(state.sector)

        return None

    def _pick_wander_target(self, state: GameState) -> int | None:
        """Pick a known sector to wander to.

        Prefers sectors with ports that we haven't traded at recently.

        Args:
            state: Current game state

        Returns:
            Sector number to wander to, or None
        """
        if not state.sector:
            return None

        # Get all known sectors with ports
        candidates = []
        for sector in range(1, 1001):  # Typical TW2002 universe size
            info = self.knowledge.get_sector_info(sector)
            if info and info.has_port:
                if sector != state.sector and sector != self._exploration.last_trade_sector:
                    candidates.append(sector)

        if not candidates:
            # Fall back to any known sector
            warps = state.warps or []
            for warp in warps:
                if self.knowledge.get_warps(warp) is not None:
                    candidates.append(warp)

        if candidates:
            return random.choice(candidates)

        # No known sectors? Just pick a random warp
        if state.warps:
            return random.choice(state.warps)

        return None

    def _find_safe_sector(self, state: GameState) -> int | None:
        """Find a safe sector to retreat to.

        Args:
            state: Current game state

        Returns:
            Safe sector number, or None
        """
        # Try to find a sector without hostile fighters
        warps = state.warps or []
        for warp in warps:
            info = self.knowledge.get_sector_info(warp)
            if info and not self._is_dangerous(warp):
                return warp

        # Fall back to any adjacent sector
        return warps[0] if warps else None

    def _is_dangerous(self, sector: int) -> bool:
        """Check if a sector is dangerous based on our knowledge."""
        # This would integrate with combat.py danger tracking
        # For now, basic implementation
        return False

    def record_result(self, result) -> None:
        """Record action result and update exploration state."""
        super().record_result(result)

        if result.action == TradeAction.TRADE and result.success:
            self._exploration.wanders_without_trade = 0
            self._exploration.last_trade_sector = result.new_sector
        elif result.action in (TradeAction.MOVE, TradeAction.EXPLORE):
            self._exploration.wanders_without_trade += 1
            if result.new_sector:
                self._exploration.explored_this_session.add(result.new_sector)

    def reset_exploration(self) -> None:
        """Reset exploration state for new session."""
        self._exploration = ExplorationState()
