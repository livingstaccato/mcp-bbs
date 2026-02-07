"""LLM intervention system for TW2002 bots.

This module provides monitoring and analysis capabilities to detect behavioral
anomalies, performance issues, and missed opportunities in autonomous bot gameplay.
"""

from __future__ import annotations

from bbsbot.games.tw2002.interventions.advisor import InterventionAdvisor
from bbsbot.games.tw2002.interventions.detector import InterventionDetector
from bbsbot.games.tw2002.interventions.trigger import InterventionTrigger
from bbsbot.games.tw2002.interventions.types import (
    Anomaly,
    AnomalyType,
    InterventionPriority,
    Opportunity,
    OpportunityType,
    TurnData,
)

__all__ = [
    "Anomaly",
    "AnomalyType",
    "InterventionAdvisor",
    "InterventionDetector",
    "InterventionPriority",
    "InterventionTrigger",
    "Opportunity",
    "OpportunityType",
    "TurnData",
]
