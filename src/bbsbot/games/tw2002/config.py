"""Configuration management for TW2002 bot."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from bbsbot.llm.config import LLMConfig

logger = logging.getLogger(__name__)


class ConnectionConfig(BaseModel):
    """Connection settings for the BBS/game server."""

    host: str = "localhost"
    port: int = 2002
    game_password: str = "game"

    model_config = ConfigDict(extra="ignore")


class CharacterConfig(BaseModel):
    """Character creation settings."""

    password: str = "trade123"

    # Themed name generation
    name_complexity: Literal["simple", "medium", "complex", "numbered"] = "medium"
    number_prefix: bool = False  # If True, puts generation number at start (e.g., "1BotName")
    generate_ship_names: bool = True
    ship_names_with_numbers: bool = False
    name_seed: int | None = None

    model_config = ConfigDict(extra="ignore")


class ProfitablePairsConfig(BaseModel):
    """Settings for profitable pairs trading strategy (Mode A)."""

    max_hop_distance: int = 2
    min_profit_per_turn: int = 100

    model_config = ConfigDict(extra="ignore")


class OpportunisticConfig(BaseModel):
    """Settings for opportunistic trading strategy (Mode B)."""

    explore_chance: float = 0.3
    max_wander_without_trade: int = 5

    model_config = ConfigDict(extra="ignore")


class TwerkOptimizedConfig(BaseModel):
    """Settings for twerk-optimized trading strategy (Mode C)."""

    data_dir: str = ""
    recalculate_interval: int = 50

    model_config = ConfigDict(extra="ignore")


class AIStrategyConfig(BaseModel):
    """Configuration for AI strategy."""

    enabled: bool = True
    fallback_strategy: str = "opportunistic"
    fallback_threshold: int = 3
    fallback_duration_turns: int = 10

    # Prompt configuration
    context_mode: Literal["full", "summary"] = "summary"
    sector_radius: int = 3
    include_history: bool = True
    max_history_items: int = 5

    # Performance
    timeout_ms: int = 30000
    cache_decisions: bool = False

    # Learning
    record_history: bool = True

    # Feedback loop settings
    feedback_enabled: bool = True
    feedback_interval_turns: int = 10  # Analyze every N turns
    feedback_lookback_turns: int = 10  # Analyze last N turns
    feedback_max_tokens: int = 300  # Limit response length

    model_config = ConfigDict(extra="ignore")


class TradingConfig(BaseModel):
    """Trading strategy configuration."""

    strategy: Literal["profitable_pairs", "opportunistic", "twerk_optimized", "ai_strategy"] = "opportunistic"
    profitable_pairs: ProfitablePairsConfig = Field(default_factory=ProfitablePairsConfig)
    opportunistic: OpportunisticConfig = Field(default_factory=OpportunisticConfig)
    twerk_optimized: TwerkOptimizedConfig = Field(default_factory=TwerkOptimizedConfig)
    ai_strategy: AIStrategyConfig = Field(default_factory=AIStrategyConfig)

    model_config = ConfigDict(extra="ignore")


class ScanningConfig(BaseModel):
    """D command scanning optimization settings."""

    scan_on_first_visit: bool = True
    scan_when_lost: bool = True
    rescan_interval_hours: float = 0

    model_config = ConfigDict(extra="ignore")


class BankingConfig(BaseModel):
    """Auto-banking settings."""

    enabled: bool = True
    deposit_threshold: int = 50000
    keep_on_hand: int = 5000

    model_config = ConfigDict(extra="ignore")


class UpgradesConfig(BaseModel):
    """Ship upgrade settings."""

    enabled: bool = True
    auto_buy_holds: bool = True
    max_holds: int = 75
    auto_buy_fighters: bool = True
    min_fighters: int = 50
    auto_buy_shields: bool = True
    min_shields: int = 100

    model_config = ConfigDict(extra="ignore")


class CombatConfig(BaseModel):
    """Combat avoidance settings."""

    enabled: bool = True
    avoid_hostile_sectors: bool = True
    danger_threshold: int = 100
    retreat_health_percent: int = 25
    enemy_cooldown_minutes: int = 30

    model_config = ConfigDict(extra="ignore")


class MultiCharacterConfig(BaseModel):
    """Multi-character management settings."""

    enabled: bool = True
    max_characters: int = 50
    knowledge_sharing: Literal["shared", "independent", "inherit_on_death"] = "shared"

    model_config = ConfigDict(extra="ignore")


class SessionConfig(BaseModel):
    """Session goals and limits."""

    target_credits: int = 5_000_000
    max_turns_per_session: int = 500

    model_config = ConfigDict(extra="ignore")


class BotConfig(BaseModel):
    """Complete bot configuration."""

    connection: ConnectionConfig = Field(default_factory=ConnectionConfig)
    character: CharacterConfig = Field(default_factory=CharacterConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    scanning: ScanningConfig = Field(default_factory=ScanningConfig)
    banking: BankingConfig = Field(default_factory=BankingConfig)
    upgrades: UpgradesConfig = Field(default_factory=UpgradesConfig)
    combat: CombatConfig = Field(default_factory=CombatConfig)
    multi_character: MultiCharacterConfig = Field(default_factory=MultiCharacterConfig)
    session: SessionConfig = Field(default_factory=SessionConfig)
    llm: LLMConfig = Field(default_factory=LLMConfig)

    model_config = ConfigDict(extra="ignore")

    @classmethod
    def from_yaml(cls, path: Path | str) -> "BotConfig":
        path = Path(path)
        logger.info("Loading configuration from %s", path)
        data = yaml.safe_load(path.read_text()) or {}
        return cls.model_validate(data)

    def to_yaml(self, path: Path | str) -> None:
        path = Path(path)
        logger.info("Saving configuration to %s", path)
        data = self.model_dump(mode="json")
        path.write_text(yaml.dump(data, default_flow_style=False, sort_keys=False))


def load_config(path: Path | str) -> BotConfig:
    return BotConfig.from_yaml(path)
