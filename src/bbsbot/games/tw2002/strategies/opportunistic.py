# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Opportunistic trading strategy (Mode B).

Explores the universe while trading opportunistically at ports
encountered during exploration. Balances exploration with profit.
"""

from __future__ import annotations

import random
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
        self._anti_controls = config.trading.anti_collapse
        self._trade_quality_controls = config.trading.trade_quality
        self._trade_lane_cooldown_until_by_key: dict[str, float] = {}
        self._trade_lane_failure_streak_by_key: dict[str, int] = {}
        self._trade_sector_cooldown_until_by_sector: dict[int, float] = {}

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
            target = self._pick_non_blocked_warp(state) or random.choice(state.warps)
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
                    eligible, reason = self._strict_trade_eligibility(
                        state,
                        commodity=sell_here,
                        expected_side="buying",
                    )
                    if not eligible:
                        self._apply_trade_lane_backoff(state.sector, sell_here, "sell", reason)
                    else:
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

            # Skip cargo liquidation attempts at sectors currently quarantined for structural misses.
            if self._is_trade_sector_blocked(state.sector):
                if state.warps:
                    target = self._pick_non_blocked_warp(state) or random.choice(state.warps)
                    return TradeAction.EXPLORE, {"direction": target}

            # Otherwise, move toward the closest known port that buys one of our cargo commodities.
            target = self._find_best_sell_target(state, cargo)
            if target and target.get("path") and len(target["path"]) > 1:
                return TradeAction.MOVE, {"target_sector": target["sector"], "path": target["path"]}

            # No known buyer yet; explore to discover ports (keep cargo, don't buy more).
            if state.warps:
                return TradeAction.EXPLORE, {"direction": self._pick_non_blocked_warp(state) or random.choice(state.warps)}

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
                current_sector = int(state.sector or 0)
                if best.buy_sector == (state.sector or best.buy_sector):
                    eligible, reason = self._strict_trade_eligibility(
                        state,
                        commodity=best.commodity,
                        expected_side="selling",
                    )
                    if not eligible:
                        self._apply_trade_lane_backoff(current_sector, best.commodity, "buy", reason)
                    elif not self._is_trade_lane_blocked(current_sector, best.commodity, "buy"):
                        qty = self._recommended_buy_qty(state, best.commodity)
                        if qty > 0:
                            return TradeAction.TRADE, {"opportunity": best, "action": "buy", "max_quantity": qty}

                if best.sell_sector == (state.sector or best.sell_sector):
                    eligible, reason = self._strict_trade_eligibility(
                        state,
                        commodity=best.commodity,
                        expected_side="buying",
                    )
                    if not eligible:
                        self._apply_trade_lane_backoff(current_sector, best.commodity, "sell", reason)
                    elif not self._is_trade_lane_blocked(current_sector, best.commodity, "sell"):
                        qty = int(cargo.get(best.commodity, 0) or 0)
                        if qty > 0:
                            return TradeAction.TRADE, {"opportunity": best, "action": "sell", "max_quantity": qty}

                # Otherwise move toward the opportunity sector.
                if best.buy_sector and state.sector and best.buy_sector in (state.warps or []):
                    if not self._is_trade_sector_blocked(best.buy_sector):
                        return TradeAction.MOVE, {
                            "target_sector": best.buy_sector,
                            "path": [state.sector, best.buy_sector],
                        }

        # Check if we've wandered too long.
        # Important: don't just reset the counter; force fresh exploration so we can
        # discover new port classes instead of bouncing between known sectors.
        if self._exploration.wanders_without_trade >= self._settings.max_wander_without_trade:
            limit = int(self._settings.max_wander_without_trade)
            self._exploration.wanders_without_trade = 0
            direction = self._pick_exploration_direction(state)
            if direction is None and state.warps:
                direction = self._pick_non_blocked_warp(state) or random.choice(state.warps)
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
            target = self._pick_non_blocked_warp(state) or random.choice(state.warps)
            return TradeAction.EXPLORE, {"direction": target}

        # Nothing to do
        return TradeAction.WAIT, {}

    @staticmethod
    def _trade_lane_key(sector: int | None, commodity: str | None, side: str | None) -> str:
        sector_i = int(sector or 0)
        comm = str(commodity or "").strip().lower() or "unknown"
        lane = str(side or "").strip().lower() or "unknown"
        return f"{sector_i}:{comm}:{lane}"

    def _is_trade_lane_blocked(self, sector: int | None, commodity: str | None, side: str | None) -> bool:
        key = self._trade_lane_key(sector, commodity, side)
        until = float(self._trade_lane_cooldown_until_by_key.get(key, 0.0) or 0.0)
        return until > time()

    def _is_trade_sector_blocked(self, sector: int | None) -> bool:
        sector_i = int(sector or 0)
        if sector_i <= 0:
            return False
        until = float(self._trade_sector_cooldown_until_by_sector.get(sector_i, 0.0) or 0.0)
        return until > time()

    def _local_port_side_live(self, state: GameState, commodity: str) -> str | None:
        idx = {"fuel_ore": 0, "organics": 1, "equipment": 2}.get(commodity)
        if idx is None:
            return None
        live_port_class = str(state.port_class or "").upper()
        if len(live_port_class) != 3:
            return None
        code = live_port_class[idx]
        if code == "B":
            return "buying"
        if code == "S":
            return "selling"
        return None

    def _strict_trade_eligibility(
        self,
        state: GameState,
        *,
        commodity: str,
        expected_side: str,
    ) -> tuple[bool, str]:
        if not bool(getattr(self._trade_quality_controls, "strict_eligibility_enabled", True)):
            return True, "ok"
        require_port = bool(getattr(self._trade_quality_controls, "strict_eligibility_require_port_presence", True))
        require_side = bool(getattr(self._trade_quality_controls, "strict_eligibility_require_known_side", True))
        if require_port and not bool(state.has_port):
            return False, "no_port"
        if require_side:
            side = self._local_port_side_live(state, commodity)
            if side is None:
                return False, "unknown_side"
            if side != expected_side:
                return False, "wrong_side"
        return True, "ok"

    def _apply_trade_lane_backoff(
        self,
        sector: int | None,
        commodity: str | None,
        side: str | None,
        reason: str,
    ) -> None:
        if not bool(getattr(self._anti_controls, "enabled", True)):
            return
        reason_token = str(reason or "").strip().lower()
        if reason_token not in {"wrong_side", "no_port", "no_interaction", "no_fill"}:
            return
        key = self._trade_lane_key(sector, commodity, side)
        if key.endswith(":unknown:unknown") or key.startswith("0:"):
            return
        streak = int(self._trade_lane_failure_streak_by_key.get(key, 0) or 0) + 1
        self._trade_lane_failure_streak_by_key[key] = streak
        if not bool(getattr(self._anti_controls, "lane_backoff_enabled", True)):
            return
        exponent = max(0, min(streak - 1, 4))
        base_seconds = int(getattr(self._anti_controls, "lane_backoff_base_seconds", 240))
        max_seconds = int(getattr(self._anti_controls, "lane_backoff_max_seconds", 1800))
        cooldown_s = int(min(max_seconds, base_seconds * (2**exponent)))
        if reason_token == "wrong_side":
            cooldown_s = max(cooldown_s, int(getattr(self._trade_quality_controls, "reroute_wrong_side_ttl_s", 300)))
        elif reason_token == "no_port":
            cooldown_s = max(cooldown_s, int(getattr(self._trade_quality_controls, "reroute_no_port_ttl_s", 1200)))
        elif reason_token in {"no_interaction", "no_fill"}:
            cooldown_s = max(cooldown_s, int(getattr(self._trade_quality_controls, "reroute_no_interaction_ttl_s", 180)))
        until_ts = time() + cooldown_s
        self._trade_lane_cooldown_until_by_key[key] = until_ts

        if reason_token in {"wrong_side", "no_port"}:
            opposite = "sell" if str(side or "").strip().lower() == "buy" else "buy"
            opposite_key = self._trade_lane_key(sector, commodity, opposite)
            if not opposite_key.endswith(":unknown:unknown") and not opposite_key.startswith("0:"):
                self._trade_lane_cooldown_until_by_key[opposite_key] = max(
                    float(self._trade_lane_cooldown_until_by_key.get(opposite_key, 0.0) or 0.0),
                    until_ts,
                )
            sector_i = int(sector or 0)
            if sector_i > 0 and bool(getattr(self._anti_controls, "sector_backoff_enabled", True)):
                base_seconds = int(getattr(self._anti_controls, "sector_backoff_base_seconds", 240))
                max_seconds = int(getattr(self._anti_controls, "sector_backoff_max_seconds", 1800))
                sector_cooldown_s = int(min(max_seconds, base_seconds * (2**exponent)))
                if reason_token == "no_port":
                    sector_cooldown_s = max(
                        sector_cooldown_s,
                        int(getattr(self._trade_quality_controls, "reroute_no_port_ttl_s", 1200)),
                    )
                self._trade_sector_cooldown_until_by_sector[sector_i] = max(
                    float(self._trade_sector_cooldown_until_by_sector.get(sector_i, 0.0) or 0.0),
                    time() + sector_cooldown_s,
                )

    def _pick_non_blocked_warp(self, state: GameState) -> int | None:
        warps = list(state.warps or [])
        if not warps:
            return None
        non_blocked = [w for w in warps if not self._is_trade_sector_blocked(w)]
        if non_blocked:
            return random.choice(non_blocked)
        return random.choice(warps)

    def _next_tradeable_local_sell(self, state: GameState, cargo: dict[str, int]) -> str | None:
        if not state.port_class or len(state.port_class) != 3:
            return None
        current_sector = int(state.sector or 0)
        mapping = [("fuel_ore", 0), ("organics", 1), ("equipment", 2)]
        for commodity, idx in mapping:
            if int(cargo.get(commodity, 0) or 0) <= 0:
                continue
            if state.port_class[idx] != "B":
                continue
            if self._is_trade_lane_blocked(current_sector, commodity, "sell"):
                continue
            return commodity
        return None

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
        if state.has_port and state.port_class and not self._is_trade_sector_blocked(current):
            opp = self._evaluate_port(current, state.port_class, 0, cargo)
            if opp:
                opportunities.append(opp)

        # Adjacent sectors
        warps = state.warps or []
        for adjacent in warps:
            if self._is_trade_sector_blocked(adjacent):
                continue
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
                if self._is_trade_lane_blocked(sector, commodity, "sell"):
                    continue
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
                if self._is_trade_lane_blocked(sector, commodity, "buy"):
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
        return self._next_tradeable_local_sell(state, cargo)

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
            if self._is_trade_sector_blocked(sector):
                continue
            info = self.knowledge.get_sector_info(sector)
            if not info or not info.has_port or not info.port_class or len(info.port_class) != 3:
                continue
            if info.port_class[idx] != "B":
                continue
            if self._is_trade_lane_blocked(sector, commodity, "sell"):
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
            if self._is_trade_sector_blocked(sector):
                continue
            info = self.knowledge.get_sector_info(sector)
            if not info or not info.has_port or not info.port_class or len(info.port_class) != 3:
                continue
            for commodity in want:
                idx = idx_map[commodity]
                if info.port_class[idx] != "B":
                    continue
                if self._is_trade_lane_blocked(sector, commodity, "sell"):
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
            if self._is_trade_sector_blocked(sector):
                continue
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
                trade_sector = getattr(result, "trade_sector", None)
                trade_commodity = str(getattr(result, "trade_commodity", "") or "").strip().lower()
                trade_side = str(getattr(result, "trade_side", "") or "").strip().lower()
                lane_key = self._trade_lane_key(trade_sector, trade_commodity, trade_side)
                self._trade_lane_failure_streak_by_key[lane_key] = 0
                self._trade_lane_cooldown_until_by_key.pop(lane_key, None)
            else:
                # Trade attempted but failed or no profit
                self._exploration.consecutive_trade_failures += 1
                reason = str(getattr(result, "trade_failure_reason", "") or "").strip().lower()
                trade_sector = getattr(result, "trade_sector", None) or getattr(result, "new_sector", None)
                trade_commodity = str(getattr(result, "trade_commodity", "") or "").strip().lower()
                trade_side = str(getattr(result, "trade_side", "") or "").strip().lower()
                self._apply_trade_lane_backoff(trade_sector, trade_commodity, trade_side, reason)
                logger.info(
                    "Trade failure #%d at sector %s (reason=%s)",
                    self._exploration.consecutive_trade_failures,
                    result.new_sector,
                    reason or "unknown",
                )
        elif result.action in (TradeAction.MOVE, TradeAction.EXPLORE):
            self._exploration.wanders_without_trade += 1
            self._exploration.consecutive_trade_failures = 0  # Reset on movement
            if result.new_sector:
                self._exploration.explored_this_session.add(result.new_sector)

    def reset_exploration(self) -> None:
        """Reset exploration state for new session."""
        self._exploration = ExplorationState()
