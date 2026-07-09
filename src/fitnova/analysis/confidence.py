"""Confidence calibration: numeric [0, 1] -> LOW / MEDIUM / HIGH.

A single, shared calibration function used by both the scoring engine and
the evidence validator so "what counts as HIGH confidence" is defined in
exactly one place, driven by `Settings.confidence_high_threshold` /
`confidence_low_threshold` (externalized, not hardcoded — docs Section 13).
"""

from __future__ import annotations

from fitnova.core.config import Settings
from fitnova.core.constants import ConfidenceLabel


def calibrate_confidence(value: float, settings: Settings) -> ConfidenceLabel:
    """value >= high_threshold -> HIGH; >= low_threshold -> MEDIUM; else LOW."""
    if value >= settings.confidence_high_threshold:
        return ConfidenceLabel.HIGH
    if value >= settings.confidence_low_threshold:
        return ConfidenceLabel.MEDIUM
    return ConfidenceLabel.LOW
