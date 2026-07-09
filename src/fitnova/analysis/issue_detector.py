"""Structured issue extraction against the closed `IssueType` taxonomy.

The taxonomy descriptions and detection guidance sent to the LLM are built
dynamically from `config/issue_rules.yaml` (docs Section 13) — editing
that YAML changes what the model is told to look for without touching this
code or the prompt file's VERSION.

This module only produces `LLMIssueItem` candidates — it does NOT decide
whether a quote is real. That is `evidence_validator.py`'s job, kept
strictly separate (docs Section 6.3, mechanism #6: "Segmentation of
concerns").
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from fitnova.analysis.llm_client import LLMClient
from fitnova.analysis.llm_schemas import LLMIssueDetectionResponse, LLMIssueItem
from fitnova.analysis.transcript_formatting import format_transcript_for_prompt
from fitnova.core.config import IssueRulesConfig
from fitnova.core.constants import IssueType, LLMStage
from fitnova.db.models import TranscriptSegment


def build_issue_taxonomy_block(issue_rules_config: IssueRulesConfig) -> str:
    lines = []
    for issue_type in IssueType:
        rule = issue_rules_config.rule_for(issue_type)
        lines.append(
            f"- {issue_type.value} (default severity: {rule.default_severity.value}): "
            f"{rule.description.strip()} Detection guidance: {rule.detection_guidance.strip()}"
        )
    return "\n".join(lines)


def detect_issues(
    call_id: int,
    segments: list[TranscriptSegment],
    llm_client: LLMClient,
    issue_rules_config: IssueRulesConfig,
    session: Session,
) -> list[LLMIssueItem]:
    transcript_text = format_transcript_for_prompt(segments)
    taxonomy_text = build_issue_taxonomy_block(issue_rules_config)

    response: LLMIssueDetectionResponse = llm_client.run_structured(
        stage=LLMStage.ISSUE_DETECTION,
        prompt_name="issue_detection_v1",
        prompt_vars={"transcript": transcript_text, "issue_taxonomy": taxonomy_text},
        response_model=LLMIssueDetectionResponse,
        call_id=call_id,
        session=session,
    )
    return response.issues
