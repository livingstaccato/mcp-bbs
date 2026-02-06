"""Logging utilities for TW2002 Trading Bot."""

import csv
import time
from datetime import datetime
from pathlib import Path

from bbsbot.logging import get_logger

logger = get_logger(__name__)


def _log_trade(
    bot,
    action: str,
    sector: int,
    quantity: int,
    price: int,
    total: int,
    credits_after: int,
):
    """Log a trade transaction.

    Args:
        bot: TradingBot instance
        action: "buy" or "sell"
        sector: Sector number
        quantity: Units traded
        price: Price per unit
        total: Total transaction value
        credits_after: Credits remaining after trade
    """
    trade_record = {
        "timestamp": datetime.now().isoformat(),
        "cycle": bot.cycle_count,
        "action": action,
        "sector": sector,
        "quantity": quantity,
        "price": price,
        "total": total,
        "credits_after": credits_after,
        "profit": credits_after - bot.current_credits if action == "sell" else 0,
    }
    bot.trade_history.append(trade_record)
    logger.info(
        "trade_completed",
        action=action,
        sector=sector,
        quantity=quantity,
        price=price,
        total=total,
        credits=credits_after,
    )


def _save_trade_history(bot, filename: str = "trade_history.csv"):
    """Save trade history to CSV file.

    Args:
        bot: TradingBot instance
        filename: Output CSV filename
    """
    if not bot.trade_history:
        return

    filepath = Path(filename)
    with open(filepath, "w", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "timestamp",
                "cycle",
                "action",
                "sector",
                "quantity",
                "price",
                "total",
                "credits_after",
                "profit",
            ],
        )
        writer.writeheader()
        writer.writerows(bot.trade_history)

    logger.info("trade_history_saved", filename=filename, trades=len(bot.trade_history))


def _print_session_summary(bot):
    """Print session statistics summary.

    Args:
        bot: TradingBot instance
    """
    elapsed_time = time.time() - bot.session_start_time
    elapsed_min = elapsed_time / 60
    profit = bot.current_credits - bot.initial_credits
    profit_per_min = profit / elapsed_min if elapsed_min > 0 else 0

    print("\n" + "=" * 80)
    print("SESSION SUMMARY")
    print("=" * 80)
    print(f"Duration:         {elapsed_min:.1f} minutes")
    print(f"Cycles completed: {bot.cycle_count}")
    print(f"Initial credits:  {bot.initial_credits:,}")
    print(f"Final credits:    {bot.current_credits:,}")
    profit_pct = (profit / bot.initial_credits * 100) if bot.initial_credits > 0 else 0
    print(f"Profit:           {profit:,} ({profit_pct:.1f}%)")
    print(f"Credits/min:      {profit_per_min:,.0f}")
    print(f"Turns used:       {bot.turns_used}")
    print(f"Errors:           {bot.error_count}")
    print(f"Sectors visited:  {len(bot.sectors_visited)}")
    print("=" * 80)

    logger.info(
        "session_complete",
        duration_min=round(elapsed_min, 1),
        cycles=bot.cycle_count,
        initial_credits=bot.initial_credits,
        final_credits=bot.current_credits,
        profit=profit,
        profit_percent=round(profit / bot.initial_credits * 100, 1) if bot.initial_credits > 0 else 0,
        credits_per_min=round(profit_per_min),
        turns_used=bot.turns_used,
        errors=bot.error_count,
    )
