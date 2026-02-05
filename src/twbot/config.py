"""Configuration management for TW2002 bot.

Provides YAML-based configuration with dataclass validation.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import yaml

logger = logging.getLogger(__name__)


@dataclass
class ConnectionConfig:
    """Connection settings for the BBS/game server."""

    host: str = "localhost"
    port: int = 2002
    game_password: str = "game"


@dataclass
class CharacterConfig:
    """Character creation settings."""

    name_prefix: str = "bot"
    password: str = "trade123"


@dataclass
class ProfitablePairsConfig:
    """Settings for profitable pairs trading strategy (Mode A)."""

    max_hop_distance: int = 2
    min_profit_per_turn: int = 100


@dataclass
class OpportunisticConfig:
    """Settings for opportunistic trading strategy (Mode B)."""

    explore_chance: float = 0.3
    max_wander_without_trade: int = 5


@dataclass
class TwerkOptimizedConfig:
    """Settings for twerk-optimized trading strategy (Mode C)."""

    data_dir: str = ""
    recalculate_interval: int = 50


@dataclass
class TradingConfig:
    """Trading strategy configuration."""

    strategy: Literal["profitable_pairs", "opportunistic", "twerk_optimized"] = (
        "opportunistic"
    )
    profitable_pairs: ProfitablePairsConfig = field(
        default_factory=ProfitablePairsConfig
    )
    opportunistic: OpportunisticConfig = field(default_factory=OpportunisticConfig)
    twerk_optimized: TwerkOptimizedConfig = field(default_factory=TwerkOptimizedConfig)


@dataclass
class ScanningConfig:
    """D command scanning optimization settings."""

    scan_on_first_visit: bool = True
    scan_when_lost: bool = True
    rescan_interval_hours: float = 0  # 0 = never rescan


@dataclass
class BankingConfig:
    """Auto-banking settings."""

    enabled: bool = True
    deposit_threshold: int = 50000
    keep_on_hand: int = 5000


@dataclass
class UpgradesConfig:
    """Ship upgrade settings."""

    enabled: bool = True
    auto_buy_holds: bool = True
    max_holds: int = 75
    auto_buy_fighters: bool = True
    min_fighters: int = 50
    auto_buy_shields: bool = True
    min_shields: int = 100


@dataclass
class CombatConfig:
    """Combat avoidance settings."""

    enabled: bool = True
    avoid_hostile_sectors: bool = True
    danger_threshold: int = 100  # Hostile fighters threshold
    retreat_health_percent: int = 25
    enemy_cooldown_minutes: int = 30


@dataclass
class MultiCharacterConfig:
    """Multi-character management settings."""

    enabled: bool = True
    max_characters: int = 50
    knowledge_sharing: Literal["shared", "independent", "inherit_on_death"] = "shared"


@dataclass
class SessionConfig:
    """Session goals and limits."""

    target_credits: int = 5_000_000
    max_turns_per_session: int = 500


@dataclass
class BotConfig:
    """Complete bot configuration."""

    connection: ConnectionConfig = field(default_factory=ConnectionConfig)
    character: CharacterConfig = field(default_factory=CharacterConfig)
    trading: TradingConfig = field(default_factory=TradingConfig)
    scanning: ScanningConfig = field(default_factory=ScanningConfig)
    banking: BankingConfig = field(default_factory=BankingConfig)
    upgrades: UpgradesConfig = field(default_factory=UpgradesConfig)
    combat: CombatConfig = field(default_factory=CombatConfig)
    multi_character: MultiCharacterConfig = field(default_factory=MultiCharacterConfig)
    session: SessionConfig = field(default_factory=SessionConfig)

    @classmethod
    def from_yaml(cls, path: Path | str) -> BotConfig:
        """Load configuration from a YAML file.

        Args:
            path: Path to the YAML configuration file

        Returns:
            BotConfig instance with loaded settings

        Raises:
            FileNotFoundError: If config file doesn't exist
            yaml.YAMLError: If YAML parsing fails
        """
        path = Path(path)
        logger.info(f"Loading configuration from {path}")

        with path.open() as f:
            data = yaml.safe_load(f) or {}

        return cls._from_dict(data)

    @classmethod
    def _from_dict(cls, data: dict) -> BotConfig:
        """Create BotConfig from a dictionary."""
        return cls(
            connection=_load_dataclass(
                ConnectionConfig, data.get("connection", {})
            ),
            character=_load_dataclass(
                CharacterConfig, data.get("character", {})
            ),
            trading=_load_trading_config(data.get("trading", {})),
            scanning=_load_dataclass(ScanningConfig, data.get("scanning", {})),
            banking=_load_dataclass(BankingConfig, data.get("banking", {})),
            upgrades=_load_dataclass(UpgradesConfig, data.get("upgrades", {})),
            combat=_load_dataclass(CombatConfig, data.get("combat", {})),
            multi_character=_load_dataclass(
                MultiCharacterConfig, data.get("multi_character", {})
            ),
            session=_load_dataclass(SessionConfig, data.get("session", {})),
        )

    def to_yaml(self, path: Path | str) -> None:
        """Save configuration to a YAML file.

        Args:
            path: Path to save the YAML configuration
        """
        path = Path(path)
        logger.info(f"Saving configuration to {path}")

        data = self._to_dict()
        with path.open("w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def _to_dict(self) -> dict:
        """Convert BotConfig to a dictionary for YAML serialization."""
        return {
            "connection": _dataclass_to_dict(self.connection),
            "character": _dataclass_to_dict(self.character),
            "trading": {
                "strategy": self.trading.strategy,
                "profitable_pairs": _dataclass_to_dict(
                    self.trading.profitable_pairs
                ),
                "opportunistic": _dataclass_to_dict(self.trading.opportunistic),
                "twerk_optimized": _dataclass_to_dict(
                    self.trading.twerk_optimized
                ),
            },
            "scanning": _dataclass_to_dict(self.scanning),
            "banking": _dataclass_to_dict(self.banking),
            "upgrades": _dataclass_to_dict(self.upgrades),
            "combat": _dataclass_to_dict(self.combat),
            "multi_character": _dataclass_to_dict(self.multi_character),
            "session": _dataclass_to_dict(self.session),
        }

    @classmethod
    def generate_default(cls, path: Path | str) -> BotConfig:
        """Generate a default configuration file.

        Args:
            path: Path to save the default configuration

        Returns:
            The default BotConfig instance
        """
        config = cls()
        config.to_yaml(path)
        return config


def _load_dataclass(cls: type, data: dict):
    """Load a dataclass from a dictionary, ignoring unknown keys."""
    import dataclasses

    field_names = {f.name for f in dataclasses.fields(cls)}
    filtered_data = {k: v for k, v in data.items() if k in field_names}
    return cls(**filtered_data)


def _dataclass_to_dict(obj) -> dict:
    """Convert a dataclass to a dictionary."""
    import dataclasses

    return {f.name: getattr(obj, f.name) for f in dataclasses.fields(obj)}


def _load_trading_config(data: dict) -> TradingConfig:
    """Load trading configuration with nested strategy configs."""
    return TradingConfig(
        strategy=data.get("strategy", "opportunistic"),
        profitable_pairs=_load_dataclass(
            ProfitablePairsConfig, data.get("profitable_pairs", {})
        ),
        opportunistic=_load_dataclass(
            OpportunisticConfig, data.get("opportunistic", {})
        ),
        twerk_optimized=_load_dataclass(
            TwerkOptimizedConfig, data.get("twerk_optimized", {})
        ),
    )


def load_config(path: Path | str | None = None) -> BotConfig:
    """Load bot configuration from file or return defaults.

    Args:
        path: Optional path to config file. If None, returns defaults.

    Returns:
        BotConfig instance
    """
    if path is None:
        logger.info("No config file specified, using defaults")
        return BotConfig()

    path = Path(path)
    if not path.exists():
        logger.warning(f"Config file {path} not found, using defaults")
        return BotConfig()

    return BotConfig.from_yaml(path)
