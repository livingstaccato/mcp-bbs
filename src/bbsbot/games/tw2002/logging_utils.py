"""Logging utilities for TW2002 Trading Bot."""

from __future__ import annotations

import csv
import json
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from bbsbot.logging import get_logger

if TYPE_CHECKING:
    from bbsbot.games.tw2002.config import GoalPhase

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


def export_goal_timeline(phases: list[GoalPhase], output_path: Path) -> None:
    """Export goal timeline data to JSON file.

    Args:
        phases: List of goal phases to export
        output_path: Path to JSON output file
    """
    if not phases:
        logger.warning("export_goal_timeline_empty", path=output_path)
        return

    # Convert phases to dicts
    data = {
        "phases": [phase.model_dump() for phase in phases],
        "total_turns": max(p.end_turn for p in phases if p.end_turn is not None) if phases else 0,
        "total_phases": len(phases),
        "timestamp": datetime.now().isoformat(),
    }

    # Write JSON
    output_path.write_text(json.dumps(data, indent=2))
    logger.info("goal_timeline_exported", path=output_path, phases=len(phases))


def load_goal_timeline_from_json(input_path: Path) -> list[GoalPhase]:
    """Load goal timeline from exported JSON file.

    Args:
        input_path: Path to JSON file

    Returns:
        List of GoalPhase instances
    """
    from bbsbot.games.tw2002.config import GoalPhase

    if not input_path.exists():
        logger.error("goal_timeline_file_not_found", path=input_path)
        return []

    data = json.loads(input_path.read_text())
    phases = [GoalPhase(**phase_data) for phase_data in data["phases"]]

    logger.info("goal_timeline_loaded", path=input_path, phases=len(phases))
    return phases


def load_goal_timeline_from_session(session_log_path: Path) -> list[GoalPhase]:
    """Reconstruct goal timeline from JSONL session logs.

    Parses "goal.changed" and "goal.rewound" events from session logs
    to rebuild the goal phase timeline.

    Args:
        session_log_path: Path to JSONL session log file

    Returns:
        List of reconstructed GoalPhase instances
    """
    from bbsbot.games.tw2002.config import GoalPhase

    if not session_log_path.exists():
        logger.error("session_log_not_found", path=session_log_path)
        return []

    phases: list[GoalPhase] = []
    current_phase: GoalPhase | None = None

    # Read JSONL events
    with open(session_log_path) as f:
        for line in f:
            try:
                event = json.loads(line)
                event_type = event.get("event_type")

                # Goal changed event
                if event_type == "goal.changed":
                    data = event.get("data", {})

                    # Close previous phase
                    if current_phase:
                        current_phase.end_turn = data.get("turn", 0)
                        current_phase.status = "completed"

                    # Start new phase
                    current_phase = GoalPhase(
                        goal_id=data.get("new_goal", "unknown"),
                        start_turn=data.get("turn", 0),
                        end_turn=None,
                        status="active",
                        trigger_type="manual" if data.get("manual_override") else "auto",
                        metrics={},
                        reason=f"Loaded from session log at turn {data.get('turn', 0)}",
                    )
                    phases.append(current_phase)

                # Rewind event
                elif event_type == "goal.rewound":
                    data = event.get("data", {})

                    # Mark current phase as rewound
                    if current_phase:
                        current_phase.status = "rewound"
                        current_phase.end_turn = data.get("from_turn", 0)
                        current_phase.metrics["rewind_reason"] = data.get("reason", "")
                        current_phase.metrics["rewind_to_turn"] = data.get("to_turn", 0)

                    # Start new phase at rewind point
                    current_phase = GoalPhase(
                        goal_id=data.get("goal", "unknown"),
                        start_turn=data.get("to_turn", 0),
                        end_turn=None,
                        status="active",
                        trigger_type="auto",
                        metrics={},
                        reason=f"Retry after rewind: {data.get('reason', '')}",
                    )
                    phases.append(current_phase)

            except json.JSONDecodeError:
                logger.warning("invalid_jsonl_line", path=session_log_path)
                continue

    logger.info("goal_timeline_reconstructed", path=session_log_path, phases=len(phases))
    return phases
