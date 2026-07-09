"""Narrative generation: executive summary, customer intent, improvement
suggestions, coaching, and next best action — one LLM call, kept separate
from scoring/issue extraction (docs Section 6.3, mechanism #6).

Grounded in two things: the real transcript, and a summary of the already
evidence-validated scores/issues, so the narrative can't contradict what
the mechanical passes actually found.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from fitnova.analysis.evidence_validator import ValidatedIssue
from fitnova.analysis.llm_client import LLMClient
from fitnova.analysis.llm_schemas import LLMInsightResponse
from fitnova.analysis.scoring_engine import ScoringOutcome
from fitnova.analysis.transcript_formatting import format_transcript_for_prompt
from fitnova.core.constants import LLMStage
from fitnova.db.models import TranscriptSegment


def build_context_summary(
    scoring_outcome: ScoringOutcome, validated_issues: list[ValidatedIssue]
) -> str:
    lines = [
        f"Overall quality: {scoring_outcome.overall_quality:.1f}/10 "
        f"(scoring version {scoring_outcome.scoring_version})"
    ]
    for name, score in scoring_outcome.dimension_scores.items():
        lines.append(f"- {name}: {score}/10")

    validated_only = [i for i in validated_issues if i.is_validated]
    if validated_only:
        lines.append("Validated issues found in this call:")
        for issue in validated_only:
            lines.append(
                f"- [{issue.severity.value}] {issue.issue_type.value} "
                f"({issue.speaker.value}): {issue.reason}"
            )
    else:
        lines.append("No validated issues were found in this call.")

    return "\n".join(lines)


def generate_insights(
    call_id: int,
    segments: list[TranscriptSegment],
    scoring_outcome: ScoringOutcome,
    validated_issues: list[ValidatedIssue],
    llm_client: LLMClient,
    session: Session,
) -> LLMInsightResponse:
    transcript_text = format_transcript_for_prompt(segments)
    context_summary = build_context_summary(scoring_outcome, validated_issues)

    return llm_client.run_structured(
        stage=LLMStage.INSIGHT_GENERATION,
        prompt_name="insight_generation_v1",
        prompt_vars={"transcript": transcript_text, "context_summary": context_summary},
        response_model=LLMInsightResponse,
        call_id=call_id,
        session=session,
    )
