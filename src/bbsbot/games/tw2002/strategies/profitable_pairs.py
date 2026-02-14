# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Profitable pairs trading strategy (Mode A).

Finds adjacent or nearby port pairs where one buys and another sells
the same commodity. Calculates expected profit before trading.
"""

from __future__ import annotations

import contextlib
from collections import defaultdict, deque
from time import time
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from bbsbot.games.tw2002.strategies.base import (
    TradeAction,
    TradeOpportunity,
    TradingStrategy,
)
from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.games.tw2002.config import BotConfig
    from bbsbot.games.tw2002.orientation import GameState, SectorInfo, SectorKnowledge

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
        self._last_discover_ts: float = 0.0
        self._last_known_sectors: int = 0
        self._explore_since_profit: int = 0
        self._replan_explore_threshold: int = 10
        self._recent_sectors: deque[int] = deque(maxlen=8)

    @property
    def name(self) -> str:
        return "profitable_pairs"

    def _effective_limits(self, state: GameState | None = None) -> tuple[int, int]:
        """Return (max_hops, min_profit_per_turn) adjusted by policy and bankroll."""
        max_hops = int(getattr(self._settings, "max_hop_distance", 2))
        min_ppt = int(getattr(self._settings, "min_profit_per_turn", 100))
        if self.policy == "conservative":
            max_hops, min_ppt = max(1, min(max_hops, 1)), max(min_ppt, 250)
        elif self.policy == "aggressive":
            max_hops, min_ppt = max(max_hops, 3), max(50, min_ppt // 2)
        else:
            max_hops, min_ppt = max_hops, min_ppt

        # Early-game bots (300-2k credits) can't satisfy high absolute profit/turn
        # gates with tiny position sizes. Relax threshold so they can bootstrap.
        if state is not None:
            credits = int(state.credits or 0)
            if credits < 1_000:
                min_ppt = min(min_ppt, 5)
            elif credits < 5_000:
                min_ppt = min(min_ppt, 20)
            elif credits < 20_000:
                min_ppt = min(min_ppt, 60)

        return max_hops, min_ppt

    def _effective_holds_free(self, state: GameState) -> int:
        """Best-effort free holds with robust fallbacks when parsing is incomplete."""
        with contextlib.suppress(Exception):
            if state.holds_free is not None:
                return max(0, int(state.holds_free))

        cargo_used = int(getattr(state, "cargo_fuel_ore", 0) or 0)
        cargo_used += int(getattr(state, "cargo_organics", 0) or 0)
        cargo_used += int(getattr(state, "cargo_equipment", 0) or 0)

        with contextlib.suppress(Exception):
            if state.holds_total is not None:
                return max(0, int(state.holds_total) - max(0, cargo_used))

        # Fallback for early sessions before / quick-stats data fully populates.
        # Keep this conservative but above 1 so strategies don't get trapped in
        # perpetual single-unit churn.
        if cargo_used > 0:
            return max(1, 20 - cargo_used)
        return 6

    def _estimated_unit_price(self, commodity: str) -> int:
        """Conservative per-unit price prior when quote data is missing."""
        return {
            "fuel_ore": 40,
            "organics": 70,
            "equipment": 120,
        }.get(str(commodity or "").strip().lower(), 60)

    def _estimated_affordable_qty_without_quotes(self, state: GameState, commodity: str) -> int:
        """Estimate a safe buy quantity when we have no reliable quote yet."""
        credits = int(state.credits or 0)
        holds_free = self._effective_holds_free(state)
        if credits <= 0 or holds_free <= 0:
            return 0

        reserve = max(70, int(credits * 0.18))
        spend_cap = max(0, credits - reserve)
        unit_guess = max(1, int(self._estimated_unit_price(commodity)))
        affordable = int(spend_cap // unit_guess)
        qty = min(holds_free, affordable)
        if self.policy == "conservative":
            qty = min(qty, 3)
        elif self.policy == "balanced":
            qty = min(qty, 5)
        else:
            qty = min(qty, 8)
        return max(0, int(qty))

    def _recommended_buy_qty(self, state: GameState, pair: PortPair) -> int:
        """Choose a safe buy quantity.

        - If we don't have both sides priced yet, buy 1 to seed price discovery.
        - If priced and profitable, size up bounded by holds, credits, and liquidity.
        """
        credits = int(state.credits or 0)
        holds_free = self._effective_holds_free(state)
        if credits <= 0 or holds_free <= 0:
            return 0

        buy_info = self.knowledge.get_sector_info(pair.buy_sector)
        sell_info = self.knowledge.get_sector_info(pair.sell_sector)
        buy_unit = ((buy_info.port_prices or {}).get(pair.commodity) or {}).get("sell") if buy_info else None
        sell_unit = ((sell_info.port_prices or {}).get(pair.commodity) or {}).get("buy") if sell_info else None
        if not buy_unit or not sell_unit:
            return self._estimated_affordable_qty_without_quotes(state, pair.commodity)

        profit_per_unit = int(sell_unit) - int(buy_unit)
        if profit_per_unit <= 0:
            return 0

        max_affordable = max(0, int(credits // int(buy_unit)))
        qty = min(holds_free, max_affordable)

        buy_supply = (buy_info.port_trading_units or {}).get(pair.commodity) if buy_info else None
        sell_demand = (sell_info.port_trading_units or {}).get(pair.commodity) if sell_info else None
        if buy_supply is not None:
            qty = min(qty, int(buy_supply))
        if sell_demand is not None:
            qty = min(qty, int(sell_demand))

        # Avoid going all-in early; keep some slack for turns/upgrades.
        if self.policy == "conservative":
            qty = min(qty, max(2, holds_free // 2))
        elif self.policy == "balanced":
            qty = min(qty, max(3, (holds_free * 3) // 4))

        return max(1, int(qty)) if qty > 0 else 0

    def _effective_low_cash_threshold(self) -> int:
        """Credits threshold below which we should prioritize liquidation/recovery."""
        if self.policy == "conservative":
            return 500
        if self.policy == "aggressive":
            return 250
        return 350

    def _cargo_map(self, state: GameState) -> dict[str, int]:
        return {
            "fuel_ore": int(getattr(state, "cargo_fuel_ore", 0) or 0),
            "organics": int(getattr(state, "cargo_organics", 0) or 0),
            "equipment": int(getattr(state, "cargo_equipment", 0) or 0),
        }

    def _local_port_side(self, state: GameState, commodity: str) -> str | None:
        """Best-effort local port side for one commodity: buying/selling/None."""
        current_sector = int(state.sector or 0)
        info = self.knowledge.get_sector_info(current_sector) if current_sector > 0 else None
        statuses = dict((info.port_status or {}) if info else {})
        side = str(statuses.get(commodity, "")).lower()
        if side in {"buying", "selling"}:
            return side

        port_class = str(state.port_class or (info.port_class if info else "") or "").upper()
        if len(port_class) != 3:
            return None
        idx = {"fuel_ore": 0, "organics": 1, "equipment": 2}.get(commodity)
        if idx is None:
            return None
        code = port_class[idx]
        if code == "B":
            return "buying"
        if code == "S":
            return "selling"
        return None

    def _choose_sell_commodity_here(
        self,
        state: GameState,
        cargo: dict[str, int],
        statuses: dict[str, str] | None,
    ) -> str | None:
        if statuses:
            for commodity in ("fuel_ore", "organics", "equipment"):
                if cargo.get(commodity, 0) > 0 and str(statuses.get(commodity, "")).lower() == "buying":
                    return commodity
        if not state.port_class or len(state.port_class) != 3:
            return None
        mapping = [("fuel_ore", 0), ("organics", 1), ("equipment", 2)]
        for commodity, idx in mapping:
            if cargo.get(commodity, 0) > 0 and state.port_class[idx] == "B":
                return commodity
        return None

    def _find_best_sell_target(self, state: GameState, cargo: dict[str, int], max_hops: int = 16) -> dict | None:
        """Pick the closest known port that buys any onboard cargo commodity."""
        if not state.sector:
            return None
        wants = [c for c, qty in cargo.items() if qty > 0]
        if not wants:
            return None
        idx_map = {"fuel_ore": 0, "organics": 1, "equipment": 2}

        best: dict | None = None
        for sector in range(1, 1001):
            info = self.knowledge.get_sector_info(sector)
            if not info or not info.has_port:
                continue
            statuses = dict(info.port_status or {})
            port_class = str(info.port_class or "").upper()
            for commodity in wants:
                is_buyer = str(statuses.get(commodity, "")).lower() == "buying"
                if not is_buyer:
                    idx = idx_map[commodity]
                    if len(port_class) == 3:
                        is_buyer = port_class[idx] == "B"
                if not is_buyer:
                    continue
                path = self.knowledge.find_path(int(state.sector), int(sector), max_hops=max_hops)
                if not path:
                    continue
                cand = {
                    "sector": int(sector),
                    "commodity": commodity,
                    "path": path,
                    "distance": len(path) - 1,
                }
                if best is None or cand["distance"] < best["distance"]:
                    best = cand
        return best

    def _is_sector_ping_pong(self) -> bool:
        """Detect short ABAB sector alternation loops."""
        if len(self._recent_sectors) < 4:
            return False
        a, b, c, d = list(self._recent_sectors)[-4:]
        return a == c and b == d and a != b

    def _loop_break_action(self, state: GameState, cargo: dict[str, int]) -> tuple[TradeAction, dict] | None:
        """Force an alternate direction when stuck in a non-productive ABAB loop."""
        if not self._is_sector_ping_pong():
            return None
        credits = int(state.credits or 0)
        low_cash = credits <= self._effective_low_cash_threshold()
        # Valid pair-cycling can look like ABAB; only break it when it is likely unproductive.
        if self._explore_since_profit < 6 and not low_cash and not any(v > 0 for v in cargo.values()):
            return None

        current = int(state.sector or 0)
        previous = int(self._recent_sectors[-2]) if len(self._recent_sectors) >= 2 else 0
        warps = [int(w) for w in (state.warps or [])]
        if not warps and current > 0:
            known = self.knowledge.get_warps(current)
            if known:
                warps = [int(w) for w in known]
        candidates = [w for w in warps if w != current and w != previous and (current, w) not in self._failed_warps]
        if not candidates:
            return None
        unseen = [w for w in candidates if self.knowledge.get_warps(w) is None]
        target = sorted(unseen or candidates)[0]
        logger.warning(
            "Detected sector ping-pong loop (recent=%s), forcing explore to %s",
            list(self._recent_sectors),
            target,
        )
        self._current_pair = None
        self._pair_phase = "idle"
        self._pairs_dirty = True
        self._explore_since_profit = 0
        return TradeAction.EXPLORE, {"direction": target, "urgency": "loop_break"}

    def _cargo_liquidation_action(self, state: GameState, cargo: dict[str, int]) -> tuple[TradeAction, dict] | None:
        """Prioritize selling onboard cargo before opening fresh buy positions."""
        if state.context != "sector_command":
            return None
        if not any(int(v or 0) > 0 for v in cargo.values()):
            return None

        current_sector = int(state.sector or 0)
        info = self.knowledge.get_sector_info(current_sector) if current_sector > 0 else None
        statuses = dict((info.port_status or {}) if info else {})

        if state.has_port:
            sell_here = self._choose_sell_commodity_here(state, cargo, statuses)
            if sell_here:
                qty = int(cargo.get(sell_here, 0) or 0)
                opp = TradeOpportunity(
                    buy_sector=current_sector,
                    sell_sector=current_sector,
                    commodity=sell_here,
                    expected_profit=0,
                    distance=0,
                )
                logger.info(
                    "Cargo liquidation: selling %s qty=%s in sector %s",
                    sell_here,
                    qty,
                    current_sector,
                )
                return TradeAction.TRADE, {
                    "opportunity": opp,
                    "action": "sell",
                    "max_quantity": max(1, qty),
                    "urgency": "cargo_liquidation",
                }

        target = self._find_best_sell_target(state, cargo, max_hops=20)
        if target and target.get("path") and len(target["path"]) > 1:
            logger.info(
                "Cargo liquidation: moving to sector %s to sell %s",
                target["sector"],
                target["commodity"],
            )
            return TradeAction.MOVE, {
                "target_sector": int(target["sector"]),
                "path": target["path"],
                "urgency": "cargo_liquidation",
            }
        return None

    def _low_cash_recovery_action(self, state: GameState) -> tuple[TradeAction, dict] | None:
        """When cash-starved, prioritize liquidation and anti-loop recovery."""
        if state.context != "sector_command":
            return None
        credits = int(state.credits or 0)
        cargo = self._cargo_map(state)
        has_cargo = any(v > 0 for v in cargo.values())
        low_cash = credits <= self._effective_low_cash_threshold()
        # This hook is only for low-credit recovery; normal cargo liquidation is
        # handled separately so non-starved bots can still optimize routing.
        if not low_cash:
            return None

        current_sector = int(state.sector or 0)
        info = self.knowledge.get_sector_info(current_sector) if current_sector > 0 else None
        statuses = dict((info.port_status or {}) if info else {})

        if has_cargo and bool(state.has_port):
            sell_here = self._choose_sell_commodity_here(state, cargo, statuses)
            if sell_here:
                opp = TradeOpportunity(
                    buy_sector=current_sector,
                    sell_sector=current_sector,
                    commodity=sell_here,
                    expected_profit=0,
                    distance=0,
                )
                logger.info(
                    "Low-cash recovery: selling %s in sector %s (credits=%s)",
                    sell_here,
                    current_sector,
                    credits,
                )
                self._current_pair = None
                self._pair_phase = "idle"
                return TradeAction.TRADE, {
                    "opportunity": opp,
                    "action": "sell",
                    "max_quantity": int(cargo.get(sell_here, 0)),
                    "urgency": "low_cash_recovery",
                }

        if has_cargo:
            target = self._find_best_sell_target(state, cargo, max_hops=16)
            if target and target.get("path") and len(target["path"]) > 1:
                logger.info(
                    "Low-cash recovery: moving to known buyer sector %s for %s",
                    target["sector"],
                    target["commodity"],
                )
                self._current_pair = None
                self._pair_phase = "idle"
                return TradeAction.MOVE, {
                    "target_sector": int(target["sector"]),
                    "path": target["path"],
                    "urgency": "low_cash_recovery",
                }

        if low_cash:
            self._current_pair = None
            self._pair_phase = "idle"
            self._pairs_dirty = True
            forced = self._loop_break_action(state, cargo)
            if forced is not None:
                return forced
            return self._explore_for_ports(state)
        return None

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

        current_sector = int(state.sector or 0)
        if current_sector > 0:
            self._recent_sectors.append(current_sector)

        recovery = self._low_cash_recovery_action(state)
        if recovery is not None:
            return recovery

        cargo = self._cargo_map(state)
        active_pair_sell_phase = self._pair_phase == "going_to_sell" and self._current_pair is not None
        if any(cargo.values()) and not active_pair_sell_phase:
            liquidation = self._cargo_liquidation_action(state, cargo)
            if liquidation is not None:
                return liquidation
            logger.info("Cargo onboard with no known buyer path; exploring to find buyer")
            return self._explore_for_ports(state)

        forced_break = self._loop_break_action(state, cargo)
        if forced_break is not None:
            return forced_break

        # If we keep exploring/moving without a profitable trade cycle, force
        # pair rediscovery and reset phase. This avoids long "explore-only" runs.
        if self._explore_since_profit >= self._replan_explore_threshold:
            logger.info(
                "Explore streak=%d without profitable trade; forcing pair replan",
                self._explore_since_profit,
            )
            self._current_pair = None
            self._pair_phase = "idle"
            self._pairs_dirty = True
            self._explore_since_profit = 0
            # Failed warp history can become stale after map updates.
            self._failed_warps.clear()
            # Before another roam cycle, opportunistically try a local bootstrap
            # trade if we're already dockable.
            bootstrap = self._local_bootstrap_trade(state)
            if bootstrap is not None:
                return bootstrap

        # Refresh pairs if needed
        # Important: after a server reset, knowledge fills in gradually. If we
        # discovered 0 pairs early, we must keep re-discovering as knowledge grows.
        known_now = 0
        try:
            known_now = int(self.knowledge.known_sector_count())
        except Exception:
            known_now = 0
        if (not self._pairs and known_now > (self._last_known_sectors + 10)) or (
            not self._pairs and (time() - self._last_discover_ts) > 30.0
        ):
            self._pairs_dirty = True

        if self._pairs_dirty:
            max_hops, _ = self._effective_limits(state)
            self._discover_pairs(max_hops=max_hops)
            # Bootstrap mode: with sparse early-game knowledge, nearby-pair constraints
            # can yield zero candidates for a long time. Widen the search to escape
            # pure exploration loops.
            if not self._pairs:
                for widened in (max_hops + 2, max_hops + 4, 8):
                    if widened <= max_hops:
                        continue
                    self._discover_pairs(max_hops=min(8, int(widened)))
                    if self._pairs:
                        break
            self._last_discover_ts = time()
            self._last_known_sectors = known_now

        # If no pairs found, explore to find more ports
        if not self._pairs:
            bootstrap = self._local_bootstrap_trade(state)
            if bootstrap is not None:
                return bootstrap
            logger.info("No profitable pairs found, exploring")
            return self._explore_for_ports(state)

        # Get or select current pair
        if self._current_pair is None:
            self._current_pair = self._select_best_pair(state)
            if self._current_pair is None:
                bootstrap = self._local_bootstrap_trade(state)
                if bootstrap is not None:
                    return bootstrap
                logger.info("No reachable/viable pair selected, exploring")
                return self._explore_for_ports(state)
            self._pair_phase = "going_to_buy"
            logger.info(
                f"Selected pair: buy at {self._current_pair.buy_sector}, sell at {self._current_pair.sell_sector}"
            )

        pair = self._current_pair
        current = state.sector

        # Execute pair trading phases
        if self._pair_phase == "going_to_buy":
            if current == pair.buy_sector:
                # Validate local side before committing to buy leg.
                side = self._local_port_side(state, pair.commodity)
                if side != "selling":
                    logger.warning(
                        "Pair buy-side invalid at sector=%s commodity=%s side=%s; replanning",
                        current,
                        pair.commodity,
                        side,
                    )
                    self._invalidate_pair(pair)
                    self._pair_phase = "idle"
                    self._pairs_dirty = True
                    return self._explore_for_ports(state)
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
                buy_qty = self._recommended_buy_qty(state, pair)
                if buy_qty <= 0:
                    logger.debug(
                        "Skipping pair due to non-viable buy qty (pair=%s->%s %s)",
                        pair.buy_sector,
                        pair.sell_sector,
                        pair.commodity,
                    )
                    self._invalidate_pair(pair)
                    self._pair_phase = "idle"
                    return self._explore_for_ports(state)
                return TradeAction.TRADE, {"opportunity": opp, "action": "buy", "max_quantity": buy_qty}
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
                    self._pair_phase = "idle"
                    return self._explore_for_ports(state)

        elif self._pair_phase == "going_to_sell":
            if current == pair.sell_sector:
                # Validate local side before committing to sell leg.
                side = self._local_port_side(state, pair.commodity)
                if side != "buying":
                    logger.warning(
                        "Pair sell-side invalid at sector=%s commodity=%s side=%s; rerouting liquidation",
                        current,
                        pair.commodity,
                        side,
                    )
                    self._invalidate_pair(pair)
                    self._pair_phase = "idle"
                    self._current_pair = None
                    self._pairs_dirty = True
                    cargo = self._cargo_map(state)
                    if any(cargo.values()):
                        liquidation = self._cargo_liquidation_action(state, cargo)
                        if liquidation is not None:
                            return liquidation
                    return self._explore_for_ports(state)
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
                    return self._explore_for_ports(state)

        return TradeAction.WAIT, {}

    def find_opportunities(self, state: GameState) -> list[TradeOpportunity]:
        """Find trading opportunities from profitable pairs."""
        if self._pairs_dirty:
            max_hops, _ = self._effective_limits(state)
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

            for buy_sector, _buy_info in buy_ports:
                for sell_sector, _sell_info in sell_ports:
                    if buy_sector == sell_sector:
                        continue

                    # Check distance
                    path = self.knowledge.find_path(buy_sector, sell_sector, max_hops=max_hops)
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
        holds_free = self._effective_holds_free(state)
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

        credits_now = int(state.credits or 0)
        # Keep early-game bots from burning turns on distant repositioning.
        if credits_now < 1_000:
            max_reposition_hops = 3
            max_total_turns = 8
        elif credits_now < 5_000:
            max_reposition_hops = 8
            max_total_turns = 14
        else:
            max_reposition_hops = 18
            max_total_turns = 28
        if self.policy == "aggressive":
            max_reposition_hops = max_reposition_hops + 2
            max_total_turns = max_total_turns + 4
        elif self.policy == "conservative":
            max_reposition_hops = max(6, max_reposition_hops - 2)
            max_total_turns = max(10, max_total_turns - 2)

        # Find pair with best profit/turn ratio from current position.
        # Prefer viable price-known pairs over structural unknown-price pairs.
        best_priced_pair = None
        best_priced_score = 0.0
        best_unpriced_pair = None
        best_unpriced_score = 0.0

        _, min_ppt = self._effective_limits(state)
        for pair in self._pairs:
            path = self.knowledge.find_path(current, pair.buy_sector)
            if not path:
                continue

            total_distance = len(path) - 1 + pair.distance
            reposition_hops = len(path) - 1
            turns = total_distance + 2  # +2 for buy/sell actions
            if reposition_hops > int(max_reposition_hops) or turns > int(max_total_turns):
                continue

            buy_info = self.knowledge.get_sector_info(pair.buy_sector)
            sell_info = self.knowledge.get_sector_info(pair.sell_sector)
            buy_unit = ((buy_info.port_prices or {}).get(pair.commodity) or {}).get("sell") if buy_info else None
            sell_unit = ((sell_info.port_prices or {}).get(pair.commodity) or {}).get("buy") if sell_info else None
            has_prices = bool(buy_unit and sell_unit)

            price_profit = self._estimate_profit_for_pair(state, pair)
            if has_prices:
                if price_profit <= 0:
                    # We already know this pair is non-viable at current prices/liquidity.
                    continue
                ppt = float(price_profit) / float(max(turns, 1))
                # Keep strict minimum only after bankroll leaves early bootstrap.
                if ppt < float(min_ppt) and int(state.credits or 0) >= 5_000:
                    continue
                score = float(price_profit) / float(max(turns, 1))
                if score > best_priced_score:
                    best_priced_score = score
                    best_priced_pair = pair
            else:
                # Unknown pricing: explore the closest structural pair to collect prices.
                if credits_now < 1_500 and reposition_hops > 2:
                    continue
                if credits_now < 5_000 and reposition_hops > 4:
                    continue
                if self._explore_since_profit >= self._replan_explore_threshold and reposition_hops > 2:
                    continue
                est_qty = self._estimated_affordable_qty_without_quotes(state, pair.commodity)
                if est_qty <= 0:
                    continue
                commodity_bias = {"fuel_ore": 1.25, "organics": 1.0, "equipment": 0.75}.get(pair.commodity, 1.0)
                score = (float(est_qty) * float(commodity_bias)) / float(max(turns, 1))
                if score > best_unpriced_score:
                    best_unpriced_score = score
                    best_unpriced_pair = pair

        if best_priced_pair is not None:
            return best_priced_pair
        return best_unpriced_pair

    def _invalidate_pair(self, pair: PortPair) -> None:
        """Remove a pair that's no longer valid."""
        if pair in self._pairs:
            self._pairs.remove(pair)
        self._current_pair = None

    def _explore_for_ports(self, state: GameState) -> tuple[TradeAction, dict]:
        """Explore to find more ports when no pairs available."""
        warps = list(state.warps or [])
        current = state.sector or 0

        # Fallback when parser fails to populate live warps: use persisted map data.
        if not warps and current > 0:
            known_warps = self.knowledge.get_warps(current)
            if known_warps:
                warps = list(known_warps)

        if not warps:
            return TradeAction.WAIT, {"reason": "no_warps"}

        # Pick an unexplored direction (skip failed warps)
        for warp in warps:
            if (current, warp) in self._failed_warps:
                continue
            if self.knowledge.get_warps(warp) is None:
                return TradeAction.EXPLORE, {"direction": warp}

        # All unexplored are failed; try explored warps we haven't failed on
        import random

        viable = [w for w in warps if (current, w) not in self._failed_warps]
        if viable:
            target = random.choice(viable)
            return TradeAction.MOVE, {
                "target_sector": target,
                "path": [current, target],
            }

        # All warps from this sector have failed; clear failures and retry
        self._failed_warps = {(f, t) for f, t in self._failed_warps if f != current}
        target = random.choice(warps)
        return TradeAction.MOVE, {
            "target_sector": target,
            "path": [current, target],
        }

    def _local_bootstrap_trade(self, state: GameState) -> tuple[TradeAction, dict] | None:
        """Fallback: do a small local trade when no global pair is currently viable."""
        if not state.has_port or not state.sector:
            return None

        info = self.knowledge.get_sector_info(state.sector)
        if not info:
            return None

        statuses = dict(info.port_status or {})
        if not statuses and info.port_class and len(info.port_class) == 3:
            # Fallback to static class semantics when dynamic market rows are unknown.
            # B = buying, S = selling, commodity order is FO/ORG/EQUIP.
            c = info.port_class
            statuses = {
                "fuel_ore": "buying" if c[0] == "B" else "selling",
                "organics": "buying" if c[1] == "B" else "selling",
                "equipment": "buying" if c[2] == "B" else "selling",
            }
        if not statuses:
            return None

        cargo = {
            "fuel_ore": int(getattr(state, "cargo_fuel_ore", 0) or 0),
            "organics": int(getattr(state, "cargo_organics", 0) or 0),
            "equipment": int(getattr(state, "cargo_equipment", 0) or 0),
        }

        # Prefer selling held cargo into local demand.
        for comm, qty in cargo.items():
            if qty > 0 and str(statuses.get(comm, "")).lower() == "buying":
                opp = TradeOpportunity(
                    buy_sector=state.sector,
                    sell_sector=state.sector,
                    commodity=comm,
                    expected_profit=0,
                    distance=0,
                )
                logger.info("Bootstrap local sell: %s at sector %s", comm, state.sector)
                return TradeAction.TRADE, {"opportunity": opp, "action": "sell"}

        # Safe bootstrap buy:
        # only buy when we know a nearby buyer path for that commodity.
        credits = int(state.credits or 0)
        holds_free = int(state.holds_free) if state.holds_free is not None else 0
        if credits <= 0 or holds_free <= 0:
            return None

        prices = dict(getattr(info, "port_prices", {}) or {})
        units = dict(getattr(info, "port_trading_units", {}) or {})
        candidates: list[tuple[int, str, int | None]] = []
        rank = {"fuel_ore": 0, "organics": 1, "equipment": 2}
        for comm in ("fuel_ore", "organics", "equipment"):
            if str(statuses.get(comm, "")).lower() != "selling":
                continue
            supply = units.get(comm)
            with contextlib.suppress(Exception):
                if supply is not None and int(supply) <= 0:
                    continue
            quote = (prices.get(comm) or {}).get("sell")
            quote_int: int | None = None
            with contextlib.suppress(Exception):
                if quote is not None:
                    quote_int = int(quote)
            price_rank = int(quote_int) if quote_int and quote_int > 0 else (10**9 + rank.get(comm, 99))
            candidates.append((price_rank, comm, quote_int))

        for _price_rank, comm, quote in sorted(candidates, key=lambda x: x[0]):
            # Require a known nearby buyer to avoid speculative dead-end holds.
            target = self._find_best_sell_target(
                state,
                {"fuel_ore": 1 if comm == "fuel_ore" else 0, "organics": 1 if comm == "organics" else 0, "equipment": 1 if comm == "equipment" else 0},
                max_hops=8,
            )
            if not target or str(target.get("commodity")) != comm:
                continue
            if int(target.get("distance") or 99) > 6:
                continue

            qty = 1
            if quote and quote > 0:
                reserve = max(90, int(credits * 0.20))
                spend_cap = max(0, credits - reserve)
                affordable = int(spend_cap // int(quote))
                if affordable <= 0:
                    continue
                near = int(target.get("distance") or 99) <= 3
                qty_cap = 4 if near else 2
                qty = min(qty_cap, holds_free, affordable)
            else:
                # Unknown quote: allow only tiny probe with healthy bankroll.
                if credits < 280:
                    continue
                qty = 1

            if qty <= 0:
                continue
            opp = TradeOpportunity(
                buy_sector=int(state.sector),
                sell_sector=int(target["sector"]),
                commodity=comm,
                expected_profit=0,
                distance=int(target.get("distance") or 0),
                path_to_buy=[],
                path_to_sell=list(target.get("path") or []),
            )
            logger.info(
                "Bootstrap safe buy: %s qty=%s at sector %s (buyer=%s dist=%s)",
                comm,
                qty,
                state.sector,
                target["sector"],
                target.get("distance"),
            )
            return TradeAction.TRADE, {"opportunity": opp, "action": "buy", "max_quantity": int(qty)}

        return None

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
            from_sector = getattr(result, "from_sector", None)
            to_sector = getattr(result, "to_sector", None)
            if from_sector and to_sector:
                self._failed_warps.add((from_sector, to_sector))
                logger.debug(f"Marked warp {from_sector} -> {to_sector} as failed")

        # If trade failed, might need to recalculate pairs
        if result.action == TradeAction.TRADE and not result.success:
            self._pairs_dirty = True

        # Successful trade - update pair timestamp
        if result.action == TradeAction.TRADE and result.success:
            if int(getattr(result, "profit", 0) or 0) > 0:
                self._explore_since_profit = 0
            else:
                self._explore_since_profit += 1
            if self._current_pair:
                from time import time

                self._current_pair.last_traded = time()
        elif result.action in (TradeAction.EXPLORE, TradeAction.MOVE):
            self._explore_since_profit += 1
