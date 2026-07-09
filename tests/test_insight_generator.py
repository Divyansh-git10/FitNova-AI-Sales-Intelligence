"""Tests for narrative generation: the context summary fed to the LLM is
grounded in the already-computed, already-validated scores/issues (docs
Section 6.3, mechanism #6), so the narrative can't contradict the
mechanical passes."""

from __future__ import annotations

from fitnova.analysis.evidence_validator import ValidatedIssue
from fitnova.analysis.insight_generator import build_context_summary, generate_insights
from fitnova.analysis.llm_schemas import LLMInsightResponse
from fitnova.analysis.scoring_engine import DIMENSIONS, ScoringOutcome
from fitnova.core.constants import ConfidenceLabel, IssueType, Severity, SpeakerLabel


class _FakeLLMClient:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def run_structured(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def _scoring_outcome(overall=7.5):
    return ScoringOutcome(
        dimension_scores={name: 7 for name in DIMENSIONS},
        overall_quality=overall,
        scoring_version="v1.0.0",
        evidence={},
    )


def _validated_issue(is_validated=True):
    return ValidatedIssue(
        issue_type=IssueType.WEAK_CLOSING,
        severity=Severity.LOW,
        speaker=SpeakerLabel.ADVISOR,
        quoted_text="bye then",
        reason="no summary or next step given",
        confidence_score=0.6,
        confidence_label=ConfidenceLabel.MEDIUM,
        is_validated=is_validated,
        segment_id=3 if is_validated else None,
    )


def test_build_context_summary_lists_dimension_scores_and_overall():
    summary = build_context_summary(_scoring_outcome(7.5), [])
    assert "7.5/10" in summary
    for name in DIMENSIONS:
        assert name in summary


def test_build_context_summary_lists_only_validated_issues():
    validated = _validated_issue(is_validated=True)
    rejected = _validated_issue(is_validated=False)
    summary = build_context_summary(_scoring_outcome(), [validated, rejected])

    assert "WEAK_CLOSING" in summary
    assert summary.count("WEAK_CLOSING") == 1  # only the validated one is listed


def test_build_context_summary_handles_no_validated_issues():
    summary = build_context_summary(_scoring_outcome(), [_validated_issue(is_validated=False)])
    assert "No validated issues were found" in summary


def test_generate_insights_passes_context_and_returns_llm_response():
    response = LLMInsightResponse(
        executive_summary="Advisor covered goals but skipped a clear close.",
        customer_intent="Interested but price-sensitive.",
        improvement_suggestions=["Confirm a trial slot before ending the call."],
        recommended_coaching="Practice explicit next-step summaries.",
        next_best_action="Follow up within 24 hours to book a trial.",
    )
    fake_client = _FakeLLMClient(response)

    result = generate_insights(
        call_id=5,
        segments=[],
        scoring_outcome=_scoring_outcome(),
        validated_issues=[_validated_issue()],
        llm_client=fake_client,
        session=None,
    )

    assert result is response
    call_kwargs = fake_client.calls[0]
    assert call_kwargs["prompt_name"] == "insight_generation_v1"
    assert "WEAK_CLOSING" in call_kwargs["prompt_vars"]["context_summary"]
    assert call_kwargs["call_id"] == 5
