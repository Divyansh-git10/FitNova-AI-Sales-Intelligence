"""Tests for the hallucination gate: every proposed issue's quote must
fuzzy-match a real transcript segment before `is_validated=True` (docs
Section 6.3, mechanism #4). Segments are lightweight stand-ins exposing
only the three attributes `evidence_validator.py` actually reads
(`id`, `segment_index`, `text`) — no DB required for these tests."""

from __future__ import annotations

from dataclasses import dataclass

from fitnova.analysis.evidence_validator import validate_issues
from fitnova.analysis.llm_schemas import LLMIssueItem
from fitnova.core.constants import ConfidenceLabel, IssueType, Severity, SpeakerLabel


@dataclass
class _StubSegment:
    id: int
    segment_index: int
    text: str


def _issue(
    segment_index,
    quoted_text,
    confidence=0.9,
    issue_type=IssueType.OVER_PROMISING,
    severity=Severity.CRITICAL,
):
    return LLMIssueItem(
        issue_type=issue_type,
        severity=severity,
        speaker=SpeakerLabel.ADVISOR,
        segment_index=segment_index,
        quoted_text=quoted_text,
        reason="test reason",
        confidence=confidence,
    )


def test_validates_issue_matching_primary_segment(settings):
    segments = [
        _StubSegment(
            id=101, segment_index=0, text="I can guarantee you will lose weight this month"
        )
    ]
    raw = [_issue(0, "I can guarantee you will lose weight this month")]

    result = validate_issues(raw, segments, settings.load_issue_rules(), settings)

    assert len(result) == 1
    assert result[0].is_validated is True
    assert result[0].segment_id == 101
    assert result[0].confidence_label == ConfidenceLabel.HIGH


def test_falls_back_to_scanning_all_segments_when_index_is_wrong(settings):
    segments = [
        _StubSegment(id=1, segment_index=0, text="hello there, thanks for calling"),
        _StubSegment(id=2, segment_index=1, text="I can guarantee amazing results for you"),
    ]
    raw = [_issue(0, "I can guarantee amazing results for you")]  # cites wrong index

    result = validate_issues(raw, segments, settings.load_issue_rules(), settings)

    assert result[0].is_validated is True
    assert result[0].segment_id == 2


def test_rejects_ungrounded_quote_not_present_anywhere(settings):
    segments = [_StubSegment(id=1, segment_index=0, text="hello there, how can I help you today")]
    raw = [_issue(0, "this sentence was never actually said by anyone")]

    result = validate_issues(raw, segments, settings.load_issue_rules(), settings)

    assert result[0].is_validated is False
    assert result[0].segment_id is None


def test_preserves_issue_metadata_regardless_of_validation_outcome(settings):
    segments = [_StubSegment(id=1, segment_index=0, text="totally unrelated text")]
    raw = [
        _issue(0, "fabricated quote", issue_type=IssueType.MISSELLING, severity=Severity.CRITICAL)
    ]

    result = validate_issues(raw, segments, settings.load_issue_rules(), settings)

    assert result[0].issue_type == IssueType.MISSELLING
    assert result[0].severity == Severity.CRITICAL
    assert result[0].is_validated is False


def test_empty_quoted_text_is_never_validated(settings):
    segments = [_StubSegment(id=1, segment_index=0, text="some real segment text")]
    raw = [_issue(0, "   ")]

    result = validate_issues(raw, segments, settings.load_issue_rules(), settings)

    assert result[0].is_validated is False


def test_confidence_label_reflects_thresholds(settings):
    segments = [_StubSegment(id=1, segment_index=0, text="price is two thousand rupees per month")]
    raw = [_issue(0, "price is two thousand rupees per month", confidence=0.55)]

    result = validate_issues(raw, segments, settings.load_issue_rules(), settings)

    assert result[0].confidence_label == ConfidenceLabel.MEDIUM
