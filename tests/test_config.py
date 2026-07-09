"""Tests for the externalized configuration system (docs Section 13).

These tests load the REAL `config/weights.yaml` and `config/issue_rules.yaml`
shipped in the repo (not fixtures) — the point is to catch a bad config
file before it ever reaches production, exactly as `bootstrap_app()` would.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from fitnova.core.config import IssueRulesConfig, ScoringWeightsConfig, Settings
from fitnova.core.constants import IssueType


def test_weights_config_loads_and_sums_to_one(settings: Settings) -> None:
    weights = settings.load_weights()
    assert isinstance(weights, ScoringWeightsConfig)
    total = sum(weights.weights.values())
    assert 0.99 <= total <= 1.01


def test_weights_config_has_all_nine_dimensions(settings: Settings) -> None:
    weights = settings.load_weights()
    expected = {
        "needs_discovery",
        "rapport",
        "empathy",
        "listening",
        "product_knowledge",
        "objection_handling",
        "compliance",
        "trial_booking",
        "closing",
    }
    assert set(weights.weights.keys()) == expected


def test_issue_rules_config_covers_every_issue_type(settings: Settings) -> None:
    rules = settings.load_issue_rules()
    assert isinstance(rules, IssueRulesConfig)
    defined_types = set(rules.issue_types.keys())
    assert defined_types == set(IssueType)


def test_issue_rules_thresholds_in_range(settings: Settings) -> None:
    rules = settings.load_issue_rules()
    assert 0 <= rules.fuzzy_match_threshold <= 100
    assert 0.0 <= rules.min_confidence_to_surface <= 1.0


def test_weights_missing_dimension_is_rejected() -> None:
    bad = {
        "needs_discovery": 0.5,
        "rapport": 0.5,
        # missing the other 7 dimensions
    }
    with pytest.raises(ValidationError):
        ScoringWeightsConfig.model_validate({"scoring_version": "v1", "weights": bad})


def test_weights_not_summing_to_one_is_rejected() -> None:
    bad_weights = {
        k: 0.5
        for k in [
            "needs_discovery",
            "rapport",
            "empathy",
            "listening",
            "product_knowledge",
            "objection_handling",
            "compliance",
            "trial_booking",
            "closing",
        ]
    }  # sums to 4.5, not 1.0
    with pytest.raises(ValidationError):
        ScoringWeightsConfig.model_validate({"scoring_version": "v1", "weights": bad_weights})
