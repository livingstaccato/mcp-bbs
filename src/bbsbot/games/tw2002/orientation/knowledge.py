"""Sector knowledge management - discovery, caching, and pathfinding."""

from __future__ import annotations

import json
from pathlib import Path
from time import time
from typing import TYPE_CHECKING

from .models import SectorInfo

if TYPE_CHECKING:
    from .models import GameState


class SectorKnowledge:
    """Layered sector knowledge: discovery -> cache -> twerk (optional)."""

    def __init__(
        self,
        knowledge_dir: Path | None = None,
        character_name: str = "unknown",
        twerk_data_dir: Path | None = None,
    ):
        self.knowledge_dir = knowledge_dir
        self.character_name = character_name
        self.twerk_data_dir = twerk_data_dir

        # In-memory discovered knowledge
        self._sectors: dict[int, SectorInfo] = {}

        # Load cached knowledge if available
        if knowledge_dir:
            self._load_cache()

        # Load twerk data if available
        self._twerk_sectors: dict[int, list[int]] | None = None
        if twerk_data_dir:
            self._load_twerk()

    def _cache_path(self) -> Path | None:
        """Path to character's knowledge cache file."""
        if not self.knowledge_dir:
            return None
        return self.knowledge_dir / f"{self.character_name}_sectors.json"

    def _load_cache(self) -> None:
        """Load cached knowledge from disk."""
        path = self._cache_path()
        if not path or not path.exists():
            return

        try:
            data = json.loads(path.read_text())
            for sector_str, info in data.get("sectors", {}).items():
                sector = int(sector_str)
                self._sectors[sector] = SectorInfo(
                    warps=info.get("warps", []),
                    has_port=info.get("has_port", False),
                    port_class=info.get("port_class"),
                    port_prices=info.get("port_prices", {}) or {},
                    port_prices_ts=info.get("port_prices_ts", {}) or {},
                    port_status=info.get("port_status", {}) or {},
                    port_trading_units=info.get("port_trading_units", {}) or {},
                    port_pct_max=info.get("port_pct_max", {}) or {},
                    port_market_ts=info.get("port_market_ts", {}) or {},
                    has_planet=info.get("has_planet", False),
                    planet_names=info.get("planet_names", []),
                    last_visited=info.get("last_visited"),
                    last_scanned=info.get("last_scanned"),
                )
        except (json.JSONDecodeError, KeyError) as e:
            print(f"Warning: Failed to load sector cache: {e}")

    def _save_cache(self) -> None:
        """Save knowledge to disk."""
        path = self._cache_path()
        if not path:
            return

        path.parent.mkdir(parents=True, exist_ok=True)

        data = {
            "sectors": {
                str(sector): {
                    "warps": info.warps,
                    "has_port": info.has_port,
                    "port_class": info.port_class,
                    "port_prices": info.port_prices,
                    "port_prices_ts": info.port_prices_ts,
                    "port_status": info.port_status,
                    "port_trading_units": info.port_trading_units,
                    "port_pct_max": info.port_pct_max,
                    "port_market_ts": info.port_market_ts,
                    "has_planet": info.has_planet,
                    "planet_names": info.planet_names,
                    "last_visited": info.last_visited,
                    "last_scanned": info.last_scanned,
                }
                for sector, info in self._sectors.items()
            },
            "last_updated": time(),
        }

        path.write_text(json.dumps(data, indent=2))

    def _load_twerk(self) -> None:
        """Load sector data from twerk if available."""
        if not self.twerk_data_dir:
            return

        try:
            from twerk.parsers import parse_sectors

            sectors_path = self.twerk_data_dir / "twsect.dat"
            if sectors_path.exists():
                sectors = parse_sectors(sectors_path)
                self._twerk_sectors = {
                    s.sector_id: list(s.warps) for s in sectors if s.warps
                }
        except ImportError:
            pass  # twerk not available
        except Exception as e:
            print(f"Warning: Failed to load twerk sector data: {e}")

    def get_warps(self, sector: int) -> list[int] | None:
        """Get known warps from a sector. Returns None if unknown."""
        # Priority 1: Discovery (most recent/accurate)
        if sector in self._sectors and self._sectors[sector].warps:
            return self._sectors[sector].warps

        # Priority 2: Twerk (if available)
        if self._twerk_sectors and sector in self._twerk_sectors:
            return self._twerk_sectors[sector]

        return None

    def get_sector_info(self, sector: int) -> SectorInfo | None:
        """Get full sector info if known."""
        return self._sectors.get(sector)

    def update_sector(self, sector: int, info: dict) -> None:
        """Update (or create) sector info from a partial dict.

        This is a convenience helper primarily used by tests and debugging.
        Unknown keys are ignored.
        """
        if sector not in self._sectors:
            self._sectors[sector] = SectorInfo()
        sector_info = self._sectors[sector]
        for key, value in info.items():
            if hasattr(sector_info, key):
                setattr(sector_info, key, value)
        self._save_cache()

    def record_observation(self, state: GameState) -> None:
        """Record what we observed in current sector."""
        if state.sector is None:
            return

        sector = state.sector
        if sector not in self._sectors:
            self._sectors[sector] = SectorInfo()

        info = self._sectors[sector]
        info.warps = state.warps
        info.has_port = state.has_port
        info.port_class = state.port_class
        info.has_planet = state.has_planet
        info.planet_names = state.planet_names
        info.last_visited = time()

        # Persist to disk
        self._save_cache()

    def record_port_price(
        self,
        sector: int,
        commodity: str,
        *,
        port_buys_price: int | None = None,
        port_sells_price: int | None = None,
        ts: float | None = None,
    ) -> None:
        """Record observed per-unit prices from a completed transaction.

        - port_buys_price: when the port buys from us (we sold), per-unit credits
        - port_sells_price: when the port sells to us (we bought), per-unit credits
        """
        if sector <= 0:
            return
        if commodity not in ("fuel_ore", "organics", "equipment"):
            return

        if sector not in self._sectors:
            self._sectors[sector] = SectorInfo()
        info = self._sectors[sector]
        if info.port_prices is None:
            info.port_prices = {}
        if info.port_prices_ts is None:
            info.port_prices_ts = {}

        c_prices = info.port_prices.get(commodity) or {}
        c_ts = info.port_prices_ts.get(commodity) or {}
        now = ts if ts is not None else time()

        if port_buys_price is not None and port_buys_price > 0:
            c_prices["buy"] = int(port_buys_price)
            c_ts["buy"] = float(now)
        if port_sells_price is not None and port_sells_price > 0:
            c_prices["sell"] = int(port_sells_price)
            c_ts["sell"] = float(now)

        if c_prices:
            info.port_prices[commodity] = c_prices
        if c_ts:
            info.port_prices_ts[commodity] = c_ts

        self._save_cache()

    def record_port_market(
        self,
        sector: int,
        commodity: str,
        *,
        status: str | None = None,
        trading_units: int | None = None,
        pct_max: int | None = None,
        ts: float | None = None,
    ) -> None:
        """Record supply/demand indicators from the port report table."""
        if sector <= 0:
            return
        if commodity not in ("fuel_ore", "organics", "equipment"):
            return
        now = ts if ts is not None else time()

        if sector not in self._sectors:
            self._sectors[sector] = SectorInfo()
        info = self._sectors[sector]

        if status:
            info.port_status[commodity] = str(status).lower()
        if trading_units is not None:
            try:
                info.port_trading_units[commodity] = max(0, int(trading_units))
            except Exception:
                pass
        if pct_max is not None:
            try:
                info.port_pct_max[commodity] = max(0, min(100, int(pct_max)))
            except Exception:
                pass
        info.port_market_ts[commodity] = float(now)
        self._save_cache()

    def find_path(self, start: int, end: int, max_hops: int = 100) -> list[int] | None:
        """BFS pathfinding using known sectors."""
        if start == end:
            return [start]

        visited = {start}
        queue = [(start, [start])]

        while queue:
            current, path = queue.pop(0)

            if len(path) > max_hops:
                continue

            warps = self.get_warps(current)
            if warps is None:
                continue

            for next_sector in warps:
                if next_sector == end:
                    return path + [next_sector]

                if next_sector not in visited:
                    visited.add(next_sector)
                    queue.append((next_sector, path + [next_sector]))

        return None  # No path found with current knowledge

    def known_sector_count(self) -> int:
        """How many sectors do we have warp data for?"""
        count = len(self._sectors)
        if self._twerk_sectors:
            count = max(count, len(self._twerk_sectors))
        return count

    def needs_scan(self, sector: int, rescan_hours: float = 0) -> bool:
        """Check if a sector needs to be scanned with D command.

        Args:
            sector: Sector to check
            rescan_hours: Hours after which to rescan (0 = never rescan)

        Returns:
            True if sector should be scanned
        """
        info = self._sectors.get(sector)
        if info is None or info.last_scanned is None:
            return True

        if rescan_hours <= 0:
            return False

        hours_since = (time() - info.last_scanned) / 3600
        return hours_since >= rescan_hours

    def mark_scanned(self, sector: int) -> None:
        """Mark a sector as having been scanned with D command.

        Args:
            sector: Sector that was scanned
        """
        if sector not in self._sectors:
            self._sectors[sector] = SectorInfo()

        self._sectors[sector].last_scanned = time()
        self._save_cache()

    def get_scanned_sectors(self) -> set[int]:
        """Get all sectors that have been scanned.

        Returns:
            Set of sector numbers that have been scanned
        """
        return {
            sector for sector, info in self._sectors.items()
            if info.last_scanned is not None
        }
