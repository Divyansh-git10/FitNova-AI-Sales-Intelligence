"""Tests for issue detection: the taxonomy sent to the LLM is built
dynamically from `config/issue_rules.yaml` (docs Section 13) and covers
every `IssueType` member."""

from __future__ import annotations

from fitnova.analysis.issue_detector import build_issue_taxonomy_block, detect_issues
from fitnova.analysis.llm_schemas import LLMIssueDetectionResponse, LLMIssueItem
from fitnova.core.constants import IssueType, Severity, SpeakerLabel


class _FakeLLMClient:
    def __init__(self, response):
        self.response = response
        self.calls: list[dict] = []

    def run_structured(self, **kwargs):
        self.calls.append(kwargs)
        return self.response


def test_build_issue_taxonomy_block_covers_every_issue_type(settings):
    block = build_issue_taxonomy_block(settings.load_issue_rules())
    for issue_type in IssueType:
        assert issue_type.value in block


def test_build_issue_taxonomy_block_includes_severity_and_guidance(settings):
    block = build_issue_taxonomy_block(settings.load_issue_rules())
    assert "default severity: CRITICAL" in block
    assert "Detection guidance:" in block


def test_detect_issues_returns_llm_issues_and_passes_taxonomy(settings):
    item = LLMIssueItem(
        issue_type=IssueType.NO_NEEDS_DISCOVERY,
        severity=Severity.HIGH,
        speaker=SpeakerLabel.ADVISOR,
        segment_index=0,
        quoted_text="here is our plan",
        reason="pitched before discovery",
        confidence=0.8,
    )
    response = LLMIssueDetectionResponse(issues=[item])
    fake_client = _FakeLLMClient(response)

    issues = detect_issues(
        call_id=7,
        segments=[],
        llm_client=fake_client,
        issue_rules_config=settings.load_issue_rules(),
        session=None,
    )

    assert issues == [item]
    call_kwargs = fake_client.calls[0]
    assert call_kwargs["prompt_name"] == "issue_detection_v1"
    assert "NO_NEEDS_DISCOVERY" in call_kwargs["prompt_vars"]["issue_taxonomy"]
    assert "OVER_PROMISING" in call_kwargs["prompt_vars"]["issue_taxonomy"]
    assert call_kwargs["call_id"] == 7


def test_detect_issues_returns_empty_list_when_no_issues(settings):
    fake_client = _FakeLLMClient(LLMIssueDetectionResponse(issues=[]))

    issues = detect_issues(
        call_id=1,
        segments=[],
        llm_client=fake_client,
        issue_rules_config=settings.load_issue_rules(),
        session=None,
    )

    assert issues == []
