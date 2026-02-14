# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Configuration management for TW2002 bot."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field

from bbsbot.llm.config import LLMConfig
from bbsbot.logging import get_logger

logger = get_logger(__name__)


class GoalPhase(BaseModel):
    """Represents a phase of gameplay focused on a specific goal.

    Tracks when a goal was active, its outcome, and relevant metrics
    for visualization and analysis.
    """

    goal_id: str
    start_turn: int
    end_turn: int | None = None  # None if currently active
    status: Literal["active", "completed", "failed", "rewound"] = "active"
    trigger_type: Literal["auto", "manual"] = "auto"
    metrics: dict[str, Any] = Field(default_factory=dict)  # Start/end credits, kills, sectors, etc.
    reason: str = ""  # Why goal was selected or ended

    model_config = ConfigDict(extra="ignore")


class GoalTrigger(BaseModel):
    """Conditions that trigger a goal to become active."""

    credits_below: int | None = None
    credits_above: int | None = None
    fighters_below: int | None = None
    fighters_above: int | None = None
    shields_below: int | None = None
    shields_above: int | None = None
    turns_remaining_above: int | None = None
    turns_remaining_below: int | None = None
    sectors_known_below: int | None = None
    in_fedspace: bool | None = None

    model_config = ConfigDict(extra="ignore")


class Goal(BaseModel):
    """Represents a gameplay goal the bot can pursue."""

    id: str
    priority: Literal["low", "medium", "high"] = "medium"
    description: str
    instructions: str = ""  # Injected into AI prompts
    trigger_when: GoalTrigger = Field(default_factory=GoalTrigger)

    model_config = ConfigDict(extra="ignore")


class GoalsConfig(BaseModel):
    """Goal system configuration."""

    # Available goals
    available: list[Goal] = Field(
        default_factory=lambda: [
            Goal(
                id="profit",
                priority="high",
                description="Maximize credits through efficient trading",
                instructions="Focus on profitable trade routes. Minimize risk. Build capital.",
                trigger_when=GoalTrigger(
                    credits_below=100000,
                    turns_remaining_above=50,
                ),
            ),
            Goal(
                id="combat",
                priority="medium",
                description="Seek combat and build military strength",
                instructions="Engage enemies when possible. Prioritize fighter and shield upgrades. Accept combat risk.",
                trigger_when=GoalTrigger(
                    credits_above=50000,
                    fighters_below=100,
                ),
            ),
            Goal(
                id="exploration",
                priority="low",
                description="Discover new sectors and map the universe",
                instructions="Visit unexplored sectors. Map warp connections. Discover ports and planets.",
                trigger_when=GoalTrigger(
                    sectors_known_below=500,
                    credits_above=20000,
                ),
            ),
            Goal(
                id="banking",
                priority="high",
                description="Secure wealth in the bank",
                instructions="Return to safe space. Deposit credits at bank. Preserve capital.",
                trigger_when=GoalTrigger(
                    credits_above=500000,
                    in_fedspace=False,
                ),
            ),
        ]
    )

    # Current goal (can be goal ID or "auto")
    current: str = "auto"

    # Re-evaluate goal selection every N turns
    reevaluate_every_turns: int = 20

    # Allow manual overrides via MCP
    allow_manual_override: bool = True

    # How many turns to maintain manual override before auto-select
    manual_override_duration: int = 0  # 0 = until changed

    model_config = ConfigDict(extra="ignore")


class ConnectionConfig(BaseModel):
    """Connection settings for the BBS/game server."""

    host: str = "localhost"
    port: int = 2002
    game_password: str = "game"
    game_letter: str | None = None  # Game selection letter (A, B, C, etc.) - auto-detected if None
    username: str | None = None  # Character username - uses generated name if not specified
    character_password: str | None = None  # Character password - uses CharacterConfig.password if not specified

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


class InterventionConfig(BaseModel):
    """Intervention system configuration."""

    # Enable/disable
    enabled: bool = True

    # Detection thresholds
    loop_action_threshold: int = 3  # Same action N times
    loop_sector_threshold: int = 4  # Visit same sector N times
    stagnation_turns: int = 15  # No progress for N turns
    profit_decline_ratio: float = 0.5  # 50% decline triggers alert
    turn_waste_threshold: float = 0.3  # >30% unproductive turns

    # Opportunity thresholds
    high_value_trade_min: int = 5000  # Min profit to flag trade
    combat_ready_fighters: int = 50  # Min fighters for combat
    combat_ready_shields: int = 100  # Min shields for combat
    banking_threshold: int = 100000  # Credits to suggest banking

    # Intervention behavior
    auto_apply: bool = False  # Auto-apply recommendations
    min_priority: str = "medium"  # medium|high|critical
    cooldown_turns: int = 5  # Min turns between interventions
    max_per_session: int = 20  # Budget limit

    # LLM settings
    analysis_temperature: float = 0.3  # Lower for consistent analysis
    analysis_max_tokens: int = 800

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

    # Supervisor cadence (LLM should not think every turn).
    think_interval_turns: int = 8  # Normal periodic review cadence
    post_change_review_turns: int = 4  # Quicker check after plan/strategy changes
    min_review_turns: int = 2
    max_review_turns: int = 40
    urgent_wakeup_min_spacing_turns: int = 4  # Min turns between urgent overrides
    # When true, risk policy is controlled by AI supervisor decisions and will
    # not be overwritten by generic dynamic policy in the main trading loop.
    supervisor_policy_locked: bool = True
    # Allow LLM to set conservative|balanced|aggressive for delegated strategies.
    allow_llm_policy_override: bool = True

    # Urgent wake-up triggers (override cadence)
    no_trade_trigger_turns: int = 18
    loss_trigger_turns: int = 12
    loss_trigger_profit_per_turn: float = -1.0
    stagnation_trigger_turns: int = 12

    # Hard goal contract: enforce minimum progress windows.
    goal_contract_enabled: bool = True
    goal_contract_window_turns: int = 20
    goal_contract_min_trades: int = 1
    goal_contract_min_profit_delta: int = 25
    goal_contract_min_credits_delta: int = 25
    goal_contract_fail_strategy: Literal["profitable_pairs", "opportunistic", "twerk_optimized"] = "opportunistic"
    goal_contract_fail_policy: Literal["conservative", "balanced", "aggressive"] = "conservative"
    goal_contract_fail_review_turns: int = 4

    # Learning
    record_history: bool = True

    # Feedback loop settings
    feedback_enabled: bool = True
    feedback_interval_turns: int = 10  # Analyze every N turns
    feedback_lookback_turns: int = 10  # Analyze last N turns
    feedback_max_tokens: int = 300  # Limit response length

    # Goals system
    goals: GoalsConfig = Field(default_factory=GoalsConfig)

    # Visualization settings
    show_goal_visualization: bool = True  # Enable/disable live visualization
    visualization_interval: int = 50  # Show status every N turns (when applicable)

    # Intervention system
    intervention: InterventionConfig = Field(default_factory=InterventionConfig)

    model_config = ConfigDict(extra="ignore")


class TradingConfig(BaseModel):
    """Trading strategy configuration."""

    strategy: Literal["profitable_pairs", "opportunistic", "twerk_optimized", "ai_strategy"] = "opportunistic"
    # Policy controls how "risky" the strategy behaves (how far it roams, what margins it accepts, etc).
    # Per-bot selectable: set to a concrete value for static behavior, or "dynamic" to auto-switch by bankroll.
    policy: Literal["conservative", "balanced", "aggressive", "dynamic"] = "dynamic"

    class DynamicPolicyConfig(BaseModel):
        """Thresholds for dynamic policy switching."""

        # Keep bots in balanced mode longer; early conservative downshifts
        # reduce trade cadence and hurt recovery after small drawdowns.
        conservative_under_credits: int = 180
        aggressive_over_credits: int = 20_000
        # Keep a deliberate spread across risk lanes in the mid-band so swarms
        # don't collapse to one policy and lose exploration diversity.
        spread_enabled: bool = True

        model_config = ConfigDict(extra="ignore")

    dynamic_policy: DynamicPolicyConfig = Field(default_factory=DynamicPolicyConfig)

    profitable_pairs: ProfitablePairsConfig = Field(default_factory=ProfitablePairsConfig)
    opportunistic: OpportunisticConfig = Field(default_factory=OpportunisticConfig)
    twerk_optimized: TwerkOptimizedConfig = Field(default_factory=TwerkOptimizedConfig)
    ai_strategy: AIStrategyConfig = Field(default_factory=AIStrategyConfig)

    # Strategy rotation settings
    enable_strategy_rotation: bool = False  # Auto-switch strategies on persistent failures
    rotation_failure_threshold: int = 20  # Switch after N consecutive failed actions
    rotation_cooldown_turns: int = 50  # Give each strategy N turns before considering rotation
    rotation_order: list[str] = Field(
        default_factory=lambda: ["ai_strategy", "profitable_pairs", "opportunistic", "twerk_optimized"]
    )

    # Anti-waste guardrail: if a bot burns turns without enough trades, force a
    # profit-first strategy/mode to recover.
    no_trade_guard_turns: int = 45
    # Also trigger guard if too many turns pass since the last completed trade.
    no_trade_guard_stale_turns: int = 45
    no_trade_guard_min_trades: int = 1
    no_trade_guard_strategy: Literal["profitable_pairs", "opportunistic"] = "profitable_pairs"
    no_trade_guard_mode: Literal["conservative", "balanced", "aggressive"] = "balanced"
    # Adaptive guard behavior:
    # - relax guard while profitable/actively trading
    # - tighten guard while unprofitable/stalled
    no_trade_guard_dynamic: bool = True
    no_trade_guard_dynamic_warmup_turns: int = 12
    no_trade_guard_turns_min: int = 24
    no_trade_guard_turns_max: int = 180
    no_trade_guard_stale_turns_min: int = 24
    no_trade_guard_stale_turns_max: int = 240
    no_trade_guard_stale_disable_after_trades: int = 5
    no_trade_guard_stale_resume_turns: int = 180
    # When bots have already demonstrated viable trading throughput, hold off on
    # stale-guard forcing until the drought is significantly longer.
    no_trade_guard_stale_soft_holdoff: bool = True
    no_trade_guard_stale_soft_holdoff_multiplier: float = 2.2
    # Do not force stale-guard actions every single turn; allow strategy turns
    # between interventions to avoid reroute churn loops.
    no_trade_guard_stale_force_interval_turns: int = 4
    trade_stall_reroute_streak: int = 2
    # Force early anti-stall behavior so fresh bots execute at least one trade
    # before long explore-only runs can develop.
    bootstrap_trade_turns: int = 12

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
    max_turns_per_session: int = 0  # 0 = run until server maximum (auto-detect)

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
    def from_yaml(cls, path: Path | str) -> BotConfig:
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
