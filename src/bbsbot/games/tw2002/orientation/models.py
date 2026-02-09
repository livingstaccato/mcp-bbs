"""Data models for orientation system."""

from __future__ import annotations

from time import time

from pydantic import BaseModel, ConfigDict, Field


class GameState(BaseModel):
    """Complete snapshot of game state after orientation."""

    # Context - where are we in the game UI?
    context: str  # "sector_command" | "planet_command" | "citadel_command" |
                  # "port_menu" | "combat" | "menu" | "unknown"
    sector: int | None = None

    # Resources
    credits: int | None = None
    turns_left: int | None = None

    # Cargo (per-commodity, as best-effort from semantic extraction / port tables)
    cargo_fuel_ore: int | None = None
    cargo_organics: int | None = None
    cargo_equipment: int | None = None

    # Ship status
    holds_total: int | None = None
    holds_free: int | None = None
    fighters: int | None = None
    shields: int | None = None
    ship_type: str | None = None
    ship_name: str | None = None  # Custom ship name like "SS Enterprise"

    # Player status
    alignment: int | None = None
    experience: int | None = None
    corp_id: int | None = None
    player_name: str | None = None

    # Sector info (from current view)
    has_port: bool = False
    port_class: str | None = None  # "BBS", "SSB", "SBB", etc.
    has_planet: bool = False
    planet_names: list[str] = Field(default_factory=list)
    warps: list[int] = Field(default_factory=list)
    traders_present: list[str] = Field(default_factory=list)
    hostile_fighters: int = 0

    # Meta
    raw_screen: str = ""
    prompt_id: str | None = None
    timestamp: float = Field(default_factory=time)
    orientation_step: str | None = None  # "Attempt 2/10: Parsing display"

    model_config = ConfigDict(extra="ignore")

    def is_safe(self) -> bool:
        """Are we at a stable command prompt?"""
        return self.context in ("sector_command", "planet_command", "citadel_command")

    def can_warp(self) -> bool:
        """Can we leave this sector?"""
        return self.context == "sector_command" and len(self.warps) > 0

    def summary(self) -> str:
        """One-line summary for logging."""
        loc = f"Sector {self.sector}" if self.sector else "Unknown"
        return f"[{self.context}] {loc} | Credits: {self.credits} | Turns: {self.turns_left}"


class OrientationError(Exception):
    """Raised when orientation fails to establish safe state."""

    def __init__(self, message: str, screen: str, attempts: int):
        super().__init__(message)
        self.screen = screen
        self.attempts = attempts


class SectorInfo(BaseModel):
    """What we know about a sector."""
    warps: list[int] = Field(default_factory=list)
    has_port: bool = False
    port_class: str | None = None
    # Observed prices from actual transactions at this port.
    # Keys:
    # - commodity: fuel_ore|organics|equipment
    # - side: "buy" (port buys -> we sell), "sell" (port sells -> we buy)
    # Values are per-unit credits, best-effort derived from "We'll buy/sell them for X credits."
    port_prices: dict[str, dict[str, int]] = Field(default_factory=dict)
    port_prices_ts: dict[str, dict[str, float]] = Field(default_factory=dict)
    # Demand/supply indicator from the port report table ("Trading % of max").
    # These are not exact quantities, but they are useful for route scoring and
    # for detecting dead/low-liquidity ports after a server reset.
    port_status: dict[str, str] = Field(default_factory=dict)  # commodity -> "buying"|"selling"
    port_pct_max: dict[str, int] = Field(default_factory=dict)  # commodity -> 0..100
    port_market_ts: dict[str, float] = Field(default_factory=dict)  # commodity -> last observed
    has_planet: bool = False
    planet_names: list[str] = Field(default_factory=list)
    last_visited: float | None = None
    last_scanned: float | None = None  # When D command was last run here

    model_config = ConfigDict(extra="ignore")


class QuickState(BaseModel):
    """Minimal state info from quick check."""
    context: str
    sector: int | None = None
    prompt_id: str | None = None
    screen: str = ""
    is_safe: bool = False
    is_danger: bool = False
    suggested_action: str | None = None

    model_config = ConfigDict(extra="ignore")

    def __str__(self) -> str:
        loc = f"Sector {self.sector}" if self.sector else "?"
        return f"[{self.context}] {loc}"
