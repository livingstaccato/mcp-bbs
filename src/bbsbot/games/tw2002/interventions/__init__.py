# Copyright (c) 2025-2026 provide.io llc
# SPDX-License-Identifier: AGPL-3.0-or-later

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
