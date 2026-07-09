"""Tests for numeric -> LOW/MEDIUM/HIGH confidence calibration (Phase 4
addendum #3)."""

from __future__ import annotations

from fitnova.analysis.confidence import calibrate_confidence
from fitnova.core.constants import ConfidenceLabel


def test_high_above_threshold(settings):
    assert calibrate_confidence(0.95, settings) == ConfidenceLabel.HIGH


def test_high_at_exact_threshold(settings):
    assert (
        calibrate_confidence(settings.confidence_high_threshold, settings) == ConfidenceLabel.HIGH
    )


def test_medium_between_thresholds(settings):
    assert calibrate_confidence(0.65, settings) == ConfidenceLabel.MEDIUM


def test_medium_at_exact_low_threshold(settings):
    assert (
        calibrate_confidence(settings.confidence_low_threshold, settings) == ConfidenceLabel.MEDIUM
    )


def test_low_below_threshold(settings):
    assert calibrate_confidence(0.1, settings) == ConfidenceLabel.LOW


def test_low_at_zero(settings):
    assert calibrate_confidence(0.0, settings) == ConfidenceLabel.LOW
