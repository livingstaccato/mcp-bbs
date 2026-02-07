"""Trading strategies for TW2002 bot.

This package provides configurable trading strategies:
- Mode A: Profitable pairs (adjacent/nearby ports)
- Mode B: Opportunistic (explore + trade)
- Mode C: Twerk-optimized routes
"""

from bbsbot.games.tw2002.strategies.base import (
    TradeAction,
    TradeOpportunity,
    TradeResult,
    TradingStrategy,
)

__all__ = [
    "TradingStrategy",
    "TradeOpportunity",
    "TradeAction",
    "TradeResult",
]
