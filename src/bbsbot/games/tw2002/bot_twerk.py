"""Twerk integration methods for TradingBot."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from twerk.analysis import SectorGraph, TradeRoute

    from bbsbot.games.tw2002.bot_core import TradingBot


async def analyze_trade_routes(
    bot: TradingBot,
    data_dir: Path,
    ship_holds: int | None = None,
    max_hops: int = 10,
) -> list[TradeRoute]:
    """Use twerk to find optimal trade routes from game data files.

    Args:
        bot: TradingBot instance
        data_dir: Path to TW2002 data directory containing twsect.dat, twport.dat
        ship_holds: Number of cargo holds (uses current ship if None)
        max_hops: Maximum warp hops to consider for routes

    Returns:
        List of TradeRoute objects sorted by efficiency score
    """
    from twerk.analysis import find_trade_routes
    from twerk.parsers import parse_ports, parse_sectors

    sectors_path = data_dir / "twsect.dat"
    ports_path = data_dir / "twport.dat"

    if not sectors_path.exists():
        raise FileNotFoundError(f"Sector data not found: {sectors_path}")
    if not ports_path.exists():
        raise FileNotFoundError(f"Port data not found: {ports_path}")

    sectors = parse_sectors(sectors_path)
    ports = parse_ports(ports_path)

    # Use provided holds or default to 20
    holds = ship_holds if ship_holds is not None else 20

    routes = find_trade_routes(sectors, ports, holds, max_hops)

    # Sort by efficiency score (highest first)
    return sorted(routes, key=lambda r: r.efficiency_score, reverse=True)


async def get_sector_map(bot: TradingBot, data_dir: Path) -> SectorGraph:
    """Use twerk to build sector graph from game data.

    Args:
        bot: TradingBot instance
        data_dir: Path to TW2002 data directory containing twsect.dat

    Returns:
        SectorGraph for pathfinding and navigation
    """
    from twerk.analysis import SectorGraph
    from twerk.parsers import parse_sectors

    sectors_path = data_dir / "twsect.dat"

    if not sectors_path.exists():
        raise FileNotFoundError(f"Sector data not found: {sectors_path}")

    sectors = parse_sectors(sectors_path)
    return SectorGraph.from_sectors(sectors)


async def find_path_twerk(
    bot: TradingBot,
    data_dir: Path,
    start_sector: int,
    end_sector: int,
    max_hops: int = 999,
) -> list[int] | None:
    """Find shortest path between two sectors using twerk.

    Args:
        bot: TradingBot instance
        data_dir: Path to TW2002 data directory
        start_sector: Starting sector ID
        end_sector: Destination sector ID
        max_hops: Maximum warp hops to search

    Returns:
        List of sector IDs from start to end, or None if no path
    """
    graph = await get_sector_map(bot, data_dir)
    return graph.bfs_path(start_sector, end_sector, max_hops)


async def get_game_state(bot: TradingBot, data_dir: Path) -> dict:
    """Read comprehensive game state from data files using twerk.

    Args:
        bot: TradingBot instance
        data_dir: Path to TW2002 data directory

    Returns:
        Dictionary with players, ports, sectors, config info
    """
    from twerk.parsers import (
        parse_config,
        parse_players,
        parse_ports,
        parse_sectors,
    )

    result: dict = {"data_dir": str(data_dir)}

    # Config
    config_path = data_dir / "twcfig.dat"
    if config_path.exists():
        config = parse_config(config_path)
        result["config"] = {
            "game_title": config.game_title,
            "turns_per_day": config.header_values[0] if config.header_values else 0,
        }

    # Players
    players_path = data_dir / "twuser.dat"
    if players_path.exists():
        players, _ = parse_players(players_path)
        active_players = [p for p in players if p.name and p.name.strip()]
        result["players"] = {
            "total": len(active_players),
            "names": [p.name for p in active_players[:10]],  # First 10
        }

    # Ports
    ports_path = data_dir / "twport.dat"
    if ports_path.exists():
        ports = parse_ports(ports_path)
        active_ports = [p for p in ports if p.sector_id > 0]
        result["ports"] = {
            "total": len(active_ports),
        }

    # Sectors
    sectors_path = data_dir / "twsect.dat"
    if sectors_path.exists():
        sectors = parse_sectors(sectors_path)
        result["sectors"] = {
            "total": len(sectors),
        }

    return result
