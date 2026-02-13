# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Opportunistic trading strategy (Mode B).

Explores the universe while trading opportunistically at ports
encountered during exploration. Balances exploration with profit.
"""

from __future__ import annotations

import random
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
    from bbsbot.games.tw2002.orientation import GameState, SectorKnowledge

logger = get_logger(__name__)


class ExplorationState(BaseModel):
    """Tracks exploration progress."""

    wanders_without_trade: int = 0
    consecutive_trade_failures: int = 0
    last_trade_sector: int | None = None
    explored_this_session: set[int] = Field(default_factory=set)

    model_config = ConfigDict(extra="ignore")


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
        1. Escape after repeated trade failures (stuck detection)
        2. Check for danger/retreat
        3. Check for banking opportunity
        4. Sell existing cargo (don't keep buying and bleeding credits)
        5. Check for upgrade opportunity
        6. Trade if at a port with a reachable buy->sell path
        6. Explore or wander
        """
        cargo = self._get_cargo(state)

        # If we've failed trades multiple times at this sector, move away
        if self._exploration.consecutive_trade_failures >= 2 and state.warps:
            self._exploration.consecutive_trade_failures = 0
            target = random.choice(state.warps)
            logger.info(
                "Repeated trade failures at sector %s, exploring sector %s",
                state.sector,
                target,
            )
            return TradeAction.EXPLORE, {"direction": target}

        # Safety checks first
        if self.should_retreat(state):
            safe_sector = self._find_safe_sector(state)
            return TradeAction.RETREAT, {"safe_sector": safe_sector}

        # Check banking
        if self.should_bank(state):
            return TradeAction.BANK, {}

        # If we already have cargo, prioritize selling it before buying more.
        # This is the main fix for "rapid credit drain": repeatedly buying with no sell leg.
        if any(v > 0 for v in cargo.values()):
            # If current sector has a port, attempt to sell immediately if it buys any cargo we have.
            if state.has_port and state.context == "sector_command" and state.port_class:
                sell_here = self._choose_sell_commodity_here(state, cargo)
                if sell_here:
                    qty = int(cargo.get(sell_here, 0) or 0)
                    opp = TradeOpportunity(
                        buy_sector=0,
                        sell_sector=state.sector or 0,
                        commodity=sell_here,
                        expected_profit=500,  # unknown; positive if sale occurs
                        distance=0,
                        confidence=0.8,
                    )
                    return TradeAction.TRADE, {
                        "opportunity": opp,
                        "action": "sell",
                        "max_quantity": max(1, qty),
                    }

            # Otherwise, move toward the closest known port that buys one of our cargo commodities.
            target = self._find_best_sell_target(state, cargo)
            if target and target.get("path") and len(target["path"]) > 1:
                return TradeAction.MOVE, {"target_sector": target["sector"], "path": target["path"]}

            # No known buyer yet; explore to discover ports (keep cargo, don't buy more).
            if state.warps:
                return TradeAction.EXPLORE, {"direction": random.choice(state.warps)}

        # Check upgrades
        should_upgrade, upgrade_type = self.should_upgrade(state)
        if should_upgrade:
            return TradeAction.UPGRADE, {"upgrade_type": upgrade_type}

        # At a port? Consider trading
        if state.has_port and state.context == "sector_command":
            # Prefer immediate trade when it has a known reachable sell leg.
            opportunities = self.find_opportunities(state)
            if opportunities:
                best = opportunities[0]
                if best.buy_sector == (state.sector or best.buy_sector):
                    qty = self._recommended_buy_qty(state, best.commodity)
                    if qty > 0:
                        return TradeAction.TRADE, {"opportunity": best, "action": "buy", "max_quantity": qty}
                if best.sell_sector == (state.sector or best.sell_sector):
                    qty = int(cargo.get(best.commodity, 0) or 0)
                    if qty > 0:
                        return TradeAction.TRADE, {"opportunity": best, "action": "sell", "max_quantity": qty}
                # Otherwise move toward the opportunity sector.
                if best.buy_sector and state.sector and best.buy_sector in (state.warps or []):
                    return TradeAction.MOVE, {"target_sector": best.buy_sector, "path": [state.sector, best.buy_sector]}

        # Check if we've wandered too long.
        # Important: don't just reset the counter; force fresh exploration so we can
        # discover new port classes instead of bouncing between known sectors.
        if self._exploration.wanders_without_trade >= self._settings.max_wander_without_trade:
            limit = int(self._settings.max_wander_without_trade)
            self._exploration.wanders_without_trade = 0
            direction = self._pick_exploration_direction(state)
            if direction is None and state.warps:
                direction = random.choice(state.warps)
            if direction is not None:
                logger.warning(
                    "Max wander without trade reached (%s); forcing exploration to %s",
                    limit,
                    direction,
                )
                return TradeAction.EXPLORE, {"direction": direction}

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

        # Fallback: if we have warps, just explore somewhere
        if state.warps:
            target = random.choice(state.warps)
            return TradeAction.EXPLORE, {"direction": target}

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

        cargo = self._get_cargo(state)

        # Current sector opportunity: only buy if we already know a reachable buyer exists.
        if state.has_port and state.port_class:
            opp = self._evaluate_port(current, state.port_class, 0, cargo)
            if opp:
                opportunities.append(opp)

        # Adjacent sectors
        warps = state.warps or []
        for adjacent in warps:
            info = self.knowledge.get_sector_info(adjacent)
            if info and info.has_port and info.port_class:
                opp = self._evaluate_port(adjacent, info.port_class, 1, cargo)
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
        cargo: dict[str, int],
    ) -> TradeOpportunity | None:
        """Evaluate a port for trading opportunity.

        Port classes:
        - B = Buys (we sell)
        - S = Sells (we buy)

        Class format: "BBS" = Buys Fuel, Buys Organics, Sells Equipment
        Position: 0=Fuel Ore, 1=Organics, 2=Equipment

        For new players with no cargo, prefer "S" (buy) commodities since
        the port will skip sell prompts when holds are empty.

        Args:
            sector: Sector with the port
            port_class: Port class string (e.g., "BBS", "SSB")
            distance: Hops from current position

        Returns:
            TradeOpportunity if profitable, None otherwise
        """
        if not port_class or len(port_class) != 3:
            return None

        commodities = ["fuel_ore", "organics", "equipment"]

        # If we have cargo, prefer selling it (port_class "B" means port buys -> we sell).
        for i, char in enumerate(port_class):
            commodity = commodities[i]
            if cargo.get(commodity, 0) > 0 and char == "B":
                return TradeOpportunity(
                    buy_sector=0,
                    sell_sector=sector,
                    commodity=commodity,
                    expected_profit=500,
                    distance=distance,
                    confidence=0.8,
                )

        # If we have no cargo, only buy when we already know a reachable buyer exists.
        if not any(v > 0 for v in cargo.values()):
            for i, char in enumerate(port_class):
                commodity = commodities[i]
                if char != "S":
                    continue
                if not self._has_known_buyer_for(state_sector=sector, commodity=commodity):
                    continue
                return TradeOpportunity(
                    buy_sector=sector,
                    sell_sector=0,
                    commodity=commodity,
                    expected_profit=500,
                    distance=distance,
                    confidence=0.6,
                )

        return None

    def _get_cargo(self, state: GameState) -> dict[str, int]:
        return {
            "fuel_ore": int(state.cargo_fuel_ore or 0),
            "organics": int(state.cargo_organics or 0),
            "equipment": int(state.cargo_equipment or 0),
        }

    def _effective_holds_free(self, state: GameState) -> int:
        if state.holds_free is not None:
            return max(0, int(state.holds_free))
        cargo = self._get_cargo(state)
        used = int(cargo["fuel_ore"]) + int(cargo["organics"]) + int(cargo["equipment"])
        if state.holds_total is not None:
            return max(0, int(state.holds_total) - used)
        return max(1, 20 - used) if used > 0 else 6

    def _recommended_buy_qty(self, state: GameState, commodity: str) -> int:
        """Size opportunistic buys to improve throughput while preserving bankroll."""
        credits = int(state.credits or 0)
        holds_free = self._effective_holds_free(state)
        if credits <= 0 or holds_free <= 0:
            return 0

        if self.policy == "conservative":
            qty_cap = 3
            reserve_ratio = 0.30
        elif self.policy == "aggressive":
            qty_cap = 10
            reserve_ratio = 0.12
        else:
            qty_cap = 6
            reserve_ratio = 0.20

        quote: int | None = None
        info = self.knowledge.get_sector_info(int(state.sector or 0)) if state.sector else None
        try:
            if info:
                raw = ((info.port_prices or {}).get(commodity) or {}).get("sell")
                if raw is not None:
                    quote = int(raw)
        except Exception:
            quote = None

        qty = min(holds_free, qty_cap)
        if quote and quote > 0:
            reserve = max(80, int(credits * reserve_ratio))
            spend_cap = max(0, credits - reserve)
            affordable = int(spend_cap // quote)
            qty = min(qty, affordable)
        else:
            # Unknown quote: keep probe size modest but not single-unit only.
            qty = min(qty, 3 if credits < 1_000 else 5)

        return max(1, int(qty)) if qty > 0 else 0

    def _choose_sell_commodity_here(self, state: GameState, cargo: dict[str, int]) -> str | None:
        """If the current port buys something we have onboard, sell that first."""
        if not state.port_class or len(state.port_class) != 3:
            return None
        mapping = [("fuel_ore", 0), ("organics", 1), ("equipment", 2)]
        for commodity, idx in mapping:
            if cargo.get(commodity, 0) > 0 and state.port_class[idx] == "B":
                return commodity
        return None

    def _has_known_buyer_for(self, state_sector: int, commodity: str, max_hops: int = 8) -> bool:
        """Return True if we know at least one reachable port that buys commodity.

        We do not require price quotes here (especially after server reset).
        Liquidity/price knowledge influences scoring elsewhere; this gate is just
        "do we know a reachable buyer exists at all".
        """
        idx = {"fuel_ore": 0, "organics": 1, "equipment": 2}.get(commodity)
        if idx is None:
            return False
        for sector in range(1, 1001):
            info = self.knowledge.get_sector_info(sector)
            if not info or not info.has_port or not info.port_class or len(info.port_class) != 3:
                continue
            if info.port_class[idx] != "B":
                continue
            path = self.knowledge.find_path(state_sector, sector, max_hops=max_hops)
            if path:
                return True
        return False

    def _find_best_sell_target(self, state: GameState, cargo: dict[str, int], max_hops: int = 12) -> dict | None:
        """Pick the closest known port that buys any onboard cargo commodity."""
        if not state.sector:
            return None
        want = [c for c, qty in cargo.items() if qty > 0]
        if not want:
            return None
        idx_map = {"fuel_ore": 0, "organics": 1, "equipment": 2}

        best: dict | None = None
        for sector in range(1, 1001):
            info = self.knowledge.get_sector_info(sector)
            if not info or not info.has_port or not info.port_class or len(info.port_class) != 3:
                continue
            for commodity in want:
                idx = idx_map[commodity]
                if info.port_class[idx] != "B":
                    continue
                path = self.knowledge.find_path(state.sector, sector, max_hops=max_hops)
                if not path:
                    continue
                cand = {"sector": sector, "commodity": commodity, "path": path, "distance": len(path) - 1}
                if best is None or cand["distance"] < best["distance"]:
                    best = cand
        return best

    def _should_explore(self) -> bool:
        """Decide whether to explore unknown sectors."""
        chance = float(self._settings.explore_chance)
        # Policy tweaks: conservative explores less, aggressive explores more.
        if self.policy == "conservative":
            chance *= 0.5
        elif self.policy == "aggressive":
            chance *= 1.5
        chance = max(0.0, min(1.0, chance))
        return random.random() < chance

    def _pick_exploration_direction(self, state: GameState) -> int | None:
        """Pick an unexplored warp direction.

        Args:
            state: Current game state

        Returns:
            Sector number to explore, or None if all explored
        """
        warps = state.warps or []
        unexplored = [
            w for w in warps if w not in self._exploration.explored_this_session and self.knowledge.get_warps(w) is None
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
        cargo = self._get_cargo(state)
        has_cargo = any(v > 0 for v in cargo.values())
        idx_map = {"fuel_ore": 0, "organics": 1, "equipment": 2}
        candidates = []
        for sector in range(1, 1001):  # Typical TW2002 universe size
            info = self.knowledge.get_sector_info(sector)
            if info and info.has_port:
                port_class = (info.port_class or "").upper()
                if len(port_class) == 3:
                    if has_cargo:
                        # With cargo, prefer reachable buyers for what we hold.
                        wants = [c for c, q in cargo.items() if q > 0]
                        if wants and not any(port_class[idx_map[c]] == "B" for c in wants):
                            continue
                    else:
                        # With empty holds, prefer ports that can sell something.
                        if "S" not in port_class:
                            continue
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

        if result.action == TradeAction.TRADE:
            if result.success and result.profit > 0:
                self._exploration.wanders_without_trade = 0
                self._exploration.consecutive_trade_failures = 0
                self._exploration.last_trade_sector = result.new_sector
            else:
                # Trade attempted but failed or no profit
                self._exploration.consecutive_trade_failures += 1
                logger.info(
                    "Trade failure #%d at sector %s",
                    self._exploration.consecutive_trade_failures,
                    result.new_sector,
                )
        elif result.action in (TradeAction.MOVE, TradeAction.EXPLORE):
            self._exploration.wanders_without_trade += 1
            self._exploration.consecutive_trade_failures = 0  # Reset on movement
            if result.new_sector:
                self._exploration.explored_this_session.add(result.new_sector)

    def reset_exploration(self) -> None:
        """Reset exploration state for new session."""
        self._exploration = ExplorationState()
