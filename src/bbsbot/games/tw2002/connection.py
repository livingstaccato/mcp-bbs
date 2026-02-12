# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Connection and session management for TW2002 Trading Bot."""

import contextlib
import json
import os
import time
from pathlib import Path

from bbsbot.games.tw2002.logging_utils import logger
from bbsbot.games.tw2002.orientation import SectorInfo
from bbsbot.games.tw2002.parsing import extract_semantic_kv


def _write_semantic_log(bot, data: dict) -> None:
    knowledge_root = getattr(bot, "knowledge_root", None)
    if not knowledge_root:
        return
    name = getattr(bot, "character_name", "unknown") or "unknown"
    base = Path(knowledge_root) / "tw2002" / "semantic"
    base.mkdir(parents=True, exist_ok=True)
    path = base / f"{name}_semantic.jsonl"
    payload = {"ts": time.time(), "data": data}
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload) + "\n")


def _update_semantic_relationships(bot, data: dict) -> None:
    knowledge = getattr(bot, "sector_knowledge", None)
    sector = data.get("sector")
    if not knowledge or not sector:
        return
    info = knowledge._sectors.get(sector) or SectorInfo()
    if data.get("warps"):
        info.warps = data["warps"]
    if "has_port" in data:
        info.has_port = bool(data.get("has_port"))
        if info.has_port:
            info.port_class = data.get("port_class")
        else:
            info.port_class = None
    if data.get("has_planet") is True:
        info.has_planet = True
        info.planet_names = data.get("planet_names", [])
    info.last_visited = time.time()

    # Port market table: persist status/% and also treat "Trading" as an observed per-unit quote.
    for commodity in ("fuel_ore", "organics", "equipment"):
        status = data.get(f"port_{commodity}_status")
        trading_units = data.get(f"port_{commodity}_trading_units")
        pct = data.get(f"port_{commodity}_pct_max")

        if status in ("buying", "selling"):
            try:
                info.port_status[commodity] = str(status)
                if trading_units is not None:
                    info.port_trading_units[commodity] = max(0, int(trading_units))
                if pct is not None:
                    info.port_pct_max[commodity] = max(0, min(100, int(pct)))
                info.port_market_ts[commodity] = float(time.time())
            except Exception:
                pass

    knowledge._sectors[sector] = info
    knowledge._save_cache()


def _semantic_watch(bot, snapshot: dict, raw: bytes) -> None:
    screen = snapshot.get("screen", "")
    if not screen:
        return
    data = extract_semantic_kv(screen)
    if not data:
        return
    kv = " ".join(f"{k}={data[k]}" for k in sorted(data))
    print(f"semantic {kv}")
    # Make semantic data available for status reporting even when we're not
    # inside wait_and_respond() loops.
    try:
        if hasattr(bot, "last_semantic_data"):
            bot.last_semantic_data.update(data)
        if "credits" in data and hasattr(bot, "current_credits"):
            bot.current_credits = int(data["credits"])
        if "sector" in data and hasattr(bot, "current_sector"):
            bot.current_sector = int(data["sector"])
    except Exception:
        pass
    _update_semantic_relationships(bot, data)
    _write_semantic_log(bot, data)


async def connect(bot, host="localhost", port=2002):
    """Connect to TW2002 BBS.

    Args:
        bot: TradingBot instance
        host: BBS hostname (default: localhost)
        port: BBS port (default: 2002)
    """
    print(f"\nConnecting to {host}:{port}...")
    chaos = None
    if os.getenv("BBSBOT_CHAOS", "").strip() in ("1", "true", "TRUE", "yes", "YES"):

        def _get_int(name: str, default: int) -> int:
            try:
                return int(os.getenv(name, str(default)).strip())
            except Exception:
                return default

        chaos = {
            "seed": _get_int("BBSBOT_CHAOS_SEED", 1),
            "disconnect_every_n_receives": _get_int("BBSBOT_CHAOS_DISCONNECT_EVERY", 0),
            "timeout_every_n_receives": _get_int("BBSBOT_CHAOS_TIMEOUT_EVERY", 0),
            "max_jitter_ms": _get_int("BBSBOT_CHAOS_JITTER_MS", 0),
            "label": "tw2002",
        }

    bot.session_id = await bot.session_manager.create_session(
        host=host, port=port, cols=80, rows=25, term="ANSI", timeout=10.0, chaos=chaos
    )
    bot.session = await bot.session_manager.get_session(bot.session_id)
    await bot.session_manager.enable_learning(bot.session_id, bot.knowledge_root, namespace="tw2002")
    if bot.session and bot.session.logger:
        # Surface the exact session log path so debugging is immediate.
        log_path = getattr(bot.session.logger, "_log_path", None)
        if log_path:
            print(f"Session log: {log_path}")
        with contextlib.suppress(Exception):
            bot.session.logger.set_context(
                {
                    "game": "tw2002",
                    "character": getattr(bot, "character_name", "unknown") or "unknown",
                    "host": str(host),
                    "port": str(port),
                }
            )
    bot.session.add_watch(lambda snapshot, raw: _semantic_watch(bot, snapshot, raw))
    print("Connected")
    logger.info("bbs_connected", host=host, port=port, session_id=bot.session_id)
