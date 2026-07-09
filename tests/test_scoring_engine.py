"""Tests for the 9-dimension scoring engine: the weighted `overall_quality`
rollup is computed in Python from `config/weights.yaml`, never trusted
from the LLM, and per-dimension explainability (reasoning/evidence_quote/
confidence/confidence_label) is always produced (Phase 4 addendum #5)."""

from __future__ import annotations

from fitnova.analysis.llm_schemas import LLMScoringResponse, ScoreDimensionResult
from fitnova.analysis.scoring_engine import DIMENSIONS, run_scoring


class _FakeLLMClient:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def run_structured(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _dim(
    score,
    quote="advisor said something relevant",
    confidence=0.9,
    reasoning="because the transcript shows it",
):
    return ScoreDimensionResult(
        score=score, reasoning=reasoning, evidence_quote=quote, confidence=confidence
    )


def _make_response(scores: dict[str, int]) -> LLMScoringResponse:
    return LLMScoringResponse(**{name: _dim(scores[name]) for name in DIMENSIONS})


def test_run_scoring_computes_weighted_overall_from_weights_yaml(settings):
    scores = {
        "needs_discovery": 8,
        "rapport": 6,
        "empathy": 7,
        "listening": 9,
        "product_knowledge": 8,
        "objection_handling": 5,
        "compliance": 10,
        "trial_booking": 4,
        "closing": 6,
    }
    fake_client = _FakeLLMClient(_make_response(scores))
    weights_config = settings.load_weights()

    outcome = run_scoring(
        call_id=1,
        segments=[],
        llm_client=fake_client,
        weights_config=weights_config,
        settings=settings,
        session=None,
    )

    expected = round(sum(weights_config.weight_for(name) * scores[name] for name in DIMENSIONS), 2)
    assert outcome.overall_quality == expected
    assert 0.0 <= outcome.overall_quality <= 10.0
    assert outcome.dimension_scores == scores
    assert outcome.scoring_version == weights_config.scoring_version


def test_run_scoring_produces_evidence_for_every_dimension(settings):
    scores = {name: 7 for name in DIMENSIONS}
    fake_client = _FakeLLMClient(_make_response(scores))
    weights_config = settings.load_weights()

    outcome = run_scoring(
        call_id=1,
        segments=[],
        llm_client=fake_client,
        weights_config=weights_config,
        settings=settings,
        session=None,
    )

    assert set(outcome.evidence.keys()) == set(DIMENSIONS)
    for name in DIMENSIONS:
        entry = outcome.evidence[name]
        assert entry["reasoning"]
        assert entry["evidence_quote"]
        assert 0.0 <= entry["confidence"] <= 1.0
        assert entry["confidence_label"] in {"LOW", "MEDIUM", "HIGH"}


def test_run_scoring_calibrates_confidence_label_correctly(settings):
    response = LLMScoringResponse(
        **{name: _dim(5, confidence=0.95 if name == "compliance" else 0.3) for name in DIMENSIONS}
    )
    fake_client = _FakeLLMClient(response)
    weights_config = settings.load_weights()

    outcome = run_scoring(
        call_id=1,
        segments=[],
        llm_client=fake_client,
        weights_config=weights_config,
        settings=settings,
        session=None,
    )

    assert outcome.evidence["compliance"]["confidence_label"] == "HIGH"
    assert outcome.evidence["rapport"]["confidence_label"] == "LOW"


def test_run_scoring_calls_llm_with_scoring_stage_and_prompt(settings):
    scores = {name: 6 for name in DIMENSIONS}
    fake_client = _FakeLLMClient(_make_response(scores))
    weights_config = settings.load_weights()

    run_scoring(
        call_id=42,
        segments=[],
        llm_client=fake_client,
        weights_config=weights_config,
        settings=settings,
        session=None,
    )

    assert fake_client.calls[0]["prompt_name"] == "scoring_v1"
    assert fake_client.calls[0]["call_id"] == 42
    assert fake_client.calls[0]["response_model"] is LLMScoringResponse
