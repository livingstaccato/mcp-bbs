"""Profitable pairs trading strategy (Mode A).

Finds adjacent or nearby port pairs where one buys and another sells
the same commodity. Calculates expected profit before trading.
"""

from __future__ import annotations

from collections import defaultdict

from pydantic import BaseModel, ConfigDict, Field

from bbsbot.games.tw2002.config import BotConfig
from bbsbot.games.tw2002.orientation import GameState, SectorInfo, SectorKnowledge
from bbsbot.games.tw2002.strategies.base import (
    TradeAction,
    TradeOpportunity,
    TradingStrategy,
)
from bbsbot.logging import get_logger

logger = get_logger(__name__)


class PortPair(BaseModel):
    """A discovered buy/sell port pair."""

    buy_sector: int
    sell_sector: int
    commodity: str  # "fuel_ore", "organics", "equipment"
    distance: int  # Hops between ports
    path: list[int] = Field(default_factory=list)
    estimated_profit: int = 0
    last_traded: float = 0.0  # Timestamp

    model_config = ConfigDict(extra="ignore")


class ProfitablePairsStrategy(TradingStrategy):
    """Trading strategy focused on known profitable port pairs.

    This strategy:
    1. Scans known sectors for port pairs (buy/sell same commodity)
    2. Ranks pairs by expected profit per turn
    3. Executes trades on the best pairs
    4. Caches discovered pairs for efficiency
    """

    def __init__(self, config: BotConfig, knowledge: SectorKnowledge):
        super().__init__(config, knowledge)
        self._settings = config.trading.profitable_pairs
        self._pairs: list[PortPair] = []
        self._pairs_dirty = True  # Need to recalculate
        self._current_pair: PortPair | None = None
        self._pair_phase: str = "idle"  # "idle", "going_to_buy", "going_to_sell"
        self._failed_warps: set[tuple[int, int]] = set()  # (from_sector, to_sector)

    @property
    def name(self) -> str:
        return "profitable_pairs"

    def _effective_limits(self) -> tuple[int, int]:
        """Return (max_hops, min_profit_per_turn) adjusted by policy."""
        max_hops = int(getattr(self._settings, "max_hop_distance", 2))
        min_ppt = int(getattr(self._settings, "min_profit_per_turn", 100))
        if self.policy == "conservative":
            return max(1, min(max_hops, 1)), max(min_ppt, 250)
        if self.policy == "aggressive":
            return max(max_hops, 3), max(50, min_ppt // 2)
        return max_hops, min_ppt

    def get_next_action(self, state: GameState) -> tuple[TradeAction, dict]:
        """Determine next action for profitable pairs trading.

        Strategy phases:
        1. Find best pair if not currently trading
        2. Navigate to buy port
        3. Buy commodity
        4. Navigate to sell port
        5. Sell commodity
        6. Repeat
        """
        # Safety checks
        if self.should_retreat(state):
            safe_sector = self._find_safe_sector(state)
            self._current_pair = None
            self._pair_phase = "idle"
            return TradeAction.RETREAT, {"safe_sector": safe_sector}

        # Check banking
        if self.should_bank(state):
            return TradeAction.BANK, {}

        # Check upgrades
        should_upgrade, upgrade_type = self.should_upgrade(state)
        if should_upgrade:
            return TradeAction.UPGRADE, {"upgrade_type": upgrade_type}

        # Refresh pairs if needed
        if self._pairs_dirty:
            max_hops, _ = self._effective_limits()
            self._discover_pairs(max_hops=max_hops)

        # If no pairs found, explore to find more ports
        if not self._pairs:
            logger.info("No profitable pairs found, exploring")
            return self._explore_for_ports(state)

        # Get or select current pair
        if self._current_pair is None:
            self._current_pair = self._select_best_pair(state)
            if self._current_pair is None:
                return TradeAction.WAIT, {}
            self._pair_phase = "going_to_buy"
            logger.info(
                f"Selected pair: buy at {self._current_pair.buy_sector}, "
                f"sell at {self._current_pair.sell_sector}"
            )

        pair = self._current_pair
        current = state.sector

        # Execute pair trading phases
        if self._pair_phase == "going_to_buy":
            if current == pair.buy_sector:
                # At buy port - create trade opportunity
                self._pair_phase = "going_to_sell"
                opp = TradeOpportunity(
                    buy_sector=pair.buy_sector,
                    sell_sector=pair.sell_sector,
                    commodity=pair.commodity,
                    expected_profit=pair.estimated_profit,
                    distance=pair.distance,
                    path_to_buy=[],
                    path_to_sell=pair.path,
                )
                return TradeAction.TRADE, {"opportunity": opp, "action": "buy"}
            else:
                # Navigate to buy port
                path = self.knowledge.find_path(current, pair.buy_sector)
                if path:
                    return TradeAction.MOVE, {
                        "target_sector": pair.buy_sector,
                        "path": path,
                    }
                else:
                    # Can't reach buy port, try another pair
                    self._invalidate_pair(pair)
                    return TradeAction.WAIT, {}

        elif self._pair_phase == "going_to_sell":
            if current == pair.sell_sector:
                # At sell port - sell and complete cycle
                self._pair_phase = "idle"
                self._current_pair = None
                opp = TradeOpportunity(
                    buy_sector=pair.buy_sector,
                    sell_sector=pair.sell_sector,
                    commodity=pair.commodity,
                    expected_profit=pair.estimated_profit,
                    distance=pair.distance,
                )
                return TradeAction.TRADE, {"opportunity": opp, "action": "sell"}
            else:
                # Navigate to sell port
                path = self.knowledge.find_path(current, pair.sell_sector)
                if path:
                    return TradeAction.MOVE, {
                        "target_sector": pair.sell_sector,
                        "path": path,
                    }
                else:
                    # Can't reach sell port
                    self._invalidate_pair(pair)
                    self._pair_phase = "idle"
                    self._current_pair = None
                    return TradeAction.WAIT, {}

        return TradeAction.WAIT, {}

    def find_opportunities(self, state: GameState) -> list[TradeOpportunity]:
        """Find trading opportunities from profitable pairs."""
        if self._pairs_dirty:
            max_hops, _ = self._effective_limits()
            self._discover_pairs(max_hops=max_hops)

        opportunities = []
        current = state.sector

        for pair in self._pairs[:10]:  # Top 10 pairs
            # Calculate distance from current position
            path_to_buy = self.knowledge.find_path(current, pair.buy_sector)
            if not path_to_buy:
                continue

            total_distance = len(path_to_buy) - 1 + pair.distance

            opp = TradeOpportunity(
                buy_sector=pair.buy_sector,
                sell_sector=pair.sell_sector,
                commodity=pair.commodity,
                expected_profit=pair.estimated_profit,
                distance=total_distance,
                path_to_buy=path_to_buy,
                path_to_sell=pair.path,
            )
            opportunities.append(opp)

        opportunities.sort(key=lambda o: o.profit_per_turn, reverse=True)
        return opportunities

    def _discover_pairs(self, *, max_hops: int) -> None:
        """Discover profitable port pairs from known sectors."""
        logger.info("Discovering profitable port pairs...")

        # Categorize ports by what they buy/sell
        # B = buys (we sell), S = sells (we buy)
        buys: dict[str, list[tuple[int, SectorInfo]]] = defaultdict(list)
        sells: dict[str, list[tuple[int, SectorInfo]]] = defaultdict(list)

        commodities = ["fuel_ore", "organics", "equipment"]

        # Scan all known sectors
        for sector in range(1, 1001):
            info = self.knowledge.get_sector_info(sector)
            if not info or not info.has_port or not info.port_class:
                continue

            port_class = info.port_class
            if len(port_class) != 3:
                continue

            for i, char in enumerate(port_class):
                commodity = commodities[i]
                if char == "B":
                    buys[commodity].append((sector, info))
                elif char == "S":
                    sells[commodity].append((sector, info))

        # Find pairs where one sells and another buys.
        # We keep structural pairs even when we don't yet know prices (common after server reset).
        pairs = []
        max_hops = int(max_hops)

        for commodity in commodities:
            buy_ports = sells[commodity]  # We buy where port sells
            sell_ports = buys[commodity]  # We sell where port buys

            for buy_sector, buy_info in buy_ports:
                for sell_sector, sell_info in sell_ports:
                    if buy_sector == sell_sector:
                        continue

                    # Check distance
                    path = self.knowledge.find_path(
                        buy_sector, sell_sector, max_hops=max_hops
                    )
                    if not path:
                        continue

                    distance = len(path) - 1

                    pair = PortPair(
                        buy_sector=buy_sector,
                        sell_sector=sell_sector,
                        commodity=commodity,
                        distance=distance,
                        path=path,
                        estimated_profit=0,
                    )
                    pairs.append(pair)

        # Keep nearby pairs earlier; price-aware ranking happens at selection time.
        pairs.sort(key=lambda p: p.distance)

        self._pairs = pairs
        self._pairs_dirty = False
        logger.info("Found %d profitable port pairs", len(pairs))

    def _estimate_profit_for_pair(self, state: GameState, pair: PortPair) -> int:
        """Estimate profit using observed per-unit prices when available."""
        credits = state.credits or 0
        holds_free = state.holds_free or 0
        if credits <= 0 or holds_free <= 0:
            return 0

        buy_info = self.knowledge.get_sector_info(pair.buy_sector)
        sell_info = self.knowledge.get_sector_info(pair.sell_sector)
        if not buy_info or not sell_info:
            return 0

        buy_unit = ((buy_info.port_prices or {}).get(pair.commodity) or {}).get("sell")
        sell_unit = ((sell_info.port_prices or {}).get(pair.commodity) or {}).get("buy")
        if not buy_unit or not sell_unit:
            return 0

        profit_per_unit = int(sell_unit) - int(buy_unit)
        if profit_per_unit <= 0:
            return 0

        max_affordable = max(0, int(credits // int(buy_unit)))
        qty = min(holds_free, max_affordable)

        # Liquidity caps from port market table.
        # - buy port must be selling commodity (supply)
        # - sell port must be buying commodity (demand)
        buy_supply = (buy_info.port_trading_units or {}).get(pair.commodity)
        sell_demand = (sell_info.port_trading_units or {}).get(pair.commodity)
        if buy_supply is not None:
            qty = min(qty, int(buy_supply))
        if sell_demand is not None:
            qty = min(qty, int(sell_demand))
        if qty <= 0:
            return 0

        return profit_per_unit * qty

    def _select_best_pair(self, state: GameState) -> PortPair | None:
        """Select the best pair to trade from current position."""
        if not self._pairs:
            return None

        current = state.sector
        if current is None:
            return self._pairs[0] if self._pairs else None

        # Find pair with best profit/turn ratio from current position when priced,
        # else bias toward closer pairs to discover pricing quickly.
        best_pair = None
        best_score = 0

        _, min_ppt = self._effective_limits()
        for pair in self._pairs[:20]:  # Check top 20
            path = self.knowledge.find_path(current, pair.buy_sector)
            if not path:
                continue

            total_distance = len(path) - 1 + pair.distance
            turns = total_distance + 2  # +2 for buy/sell actions

            price_profit = self._estimate_profit_for_pair(state, pair)
            if price_profit > 0:
                ppt = float(price_profit) / float(max(turns, 1))
                if ppt < float(min_ppt):
                    continue
            score = (price_profit / max(turns, 1)) if price_profit > 0 else (1.0 / max(turns, 1))
            if score > best_score:
                best_score = score
                best_pair = pair

        return best_pair

    def _invalidate_pair(self, pair: PortPair) -> None:
        """Remove a pair that's no longer valid."""
        if pair in self._pairs:
            self._pairs.remove(pair)
        self._current_pair = None

    def _explore_for_ports(self, state: GameState) -> tuple[TradeAction, dict]:
        """Explore to find more ports when no pairs available."""
        if not state.warps:
            return TradeAction.WAIT, {}

        current = state.sector or 0

        # Pick an unexplored direction (skip failed warps)
        for warp in state.warps:
            if (current, warp) in self._failed_warps:
                continue
            if self.knowledge.get_warps(warp) is None:
                return TradeAction.EXPLORE, {"direction": warp}

        # All unexplored are failed; try explored warps we haven't failed on
        import random
        viable = [w for w in state.warps if (current, w) not in self._failed_warps]
        if viable:
            target = random.choice(viable)
            return TradeAction.MOVE, {
                "target_sector": target,
                "path": [current, target],
            }

        # All warps from this sector have failed; clear failures and retry
        self._failed_warps = {(f, t) for f, t in self._failed_warps if f != current}
        target = random.choice(state.warps)
        return TradeAction.MOVE, {
            "target_sector": target,
            "path": [current, target],
        }

    def _find_safe_sector(self, state: GameState) -> int | None:
        """Find a safe sector to retreat to."""
        warps = state.warps or []
        return warps[0] if warps else None

    def invalidate_pairs(self) -> None:
        """Force recalculation of pairs on next action."""
        self._pairs_dirty = True

    def record_result(self, result) -> None:
        """Record result and potentially invalidate pairs."""
        super().record_result(result)

        # Track failed warps (EXPLORE/MOVE that didn't change sector)
        if result.action in (TradeAction.EXPLORE, TradeAction.MOVE) and not result.success:
            # result should have from_sector and to_sector for tracking
            from_sector = getattr(result, 'from_sector', None)
            to_sector = getattr(result, 'to_sector', None)
            if from_sector and to_sector:
                self._failed_warps.add((from_sector, to_sector))
                logger.debug(f"Marked warp {from_sector} -> {to_sector} as failed")

        # If trade failed, might need to recalculate pairs
        if result.action == TradeAction.TRADE and not result.success:
            self._pairs_dirty = True

        # Successful trade - update pair timestamp
        if result.action == TradeAction.TRADE and result.success:
            if self._current_pair:
                from time import time
                self._current_pair.last_traded = time()
