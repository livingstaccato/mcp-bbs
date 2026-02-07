"""Data types for intervention system.

Defines core types used throughout the intervention system.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class InterventionPriority(StrEnum):
    """Priority levels for interventions."""

    CRITICAL = "critical"  # Bot stuck, ship at risk, major capital loss
    HIGH = "high"  # Performance declining, suboptimal patterns
    MEDIUM = "medium"  # Minor inefficiencies, optimization opportunities
    LOW = "low"  # Informational, no immediate action needed


class AnomalyType(StrEnum):
    """Types of behavioral anomalies."""

    ACTION_LOOP = "action_loop"  # Repeating same action
    SECTOR_LOOP = "sector_loop"  # Circling between sectors
    GOAL_STAGNATION = "goal_stagnation"  # No progress toward goal
    PERFORMANCE_DECLINE = "performance_decline"  # Profit velocity dropping
    TURN_WASTE = "turn_waste"  # Unproductive turns
    COMPLETE_STAGNATION = "complete_stagnation"  # NO changes at all - bot is stuck


class OpportunityType(StrEnum):
    """Types of missed opportunities."""

    HIGH_VALUE_TRADE = "high_value_trade"  # Profitable trade available
    COMBAT_READY = "combat_ready"  # Ship ready for combat
    BANKING_OPTIMAL = "banking_optimal"  # Should secure credits


class Anomaly(BaseModel):
    """Detected behavioral anomaly."""

    type: AnomalyType
    priority: InterventionPriority
    confidence: float = Field(ge=0.0, le=1.0)
    description: str
    evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Opportunity(BaseModel):
    """Detected opportunity."""

    type: OpportunityType
    priority: InterventionPriority
    confidence: float = Field(ge=0.0, le=1.0)
    description: str
    evidence: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TurnData(BaseModel):
    """Data about a single turn."""

    turn: int
    sector: int
    credits: int
    action: str
    profit_delta: int
    holds_free: int
    fighters: int
    shields: int
