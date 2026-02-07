"""Detection algorithms for intervention system.

This module contains specialized detection functions for anomalies and opportunities.
"""

from __future__ import annotations

from bbsbot.games.tw2002.interventions.detectors import anomaly_detectors, opportunity_detectors

__all__ = [
    "anomaly_detectors",
    "opportunity_detectors",
]
