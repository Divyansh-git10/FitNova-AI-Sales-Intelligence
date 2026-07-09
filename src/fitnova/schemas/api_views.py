"""Composite response schemas for the FastAPI layer (Phase 5).

Kept separate from `fitnova.schemas.<entity>` on purpose: those files are
1:1 with a DB table (create/read contracts for the pipeline). These are
denormalized, read-only view models assembled by `fitnova.db.repository`
for the API and dashboard — they never round-trip back into a table, so
they don't belong next to the entity schemas.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from fitnova.core.constants import (
    CallType,
    ConfidenceLabel,
    FeedbackType,
    IssueStatus,
    IssueType,
    LLMStage,
    Severity,
    SpeakerLabel,
)


class CallListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    advisor_id: int | None
    advisor_name: str | None = None
    team_name: str | None = None
    call_type: CallType
    call_datetime: datetime | None
    duration_seconds: float | None
    overall_quality: float | None = None
    validated_issue_count: int = 0


class TranscriptSegmentView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    segment_index: int
    speaker_label: SpeakerLabel
    start_time: float
    end_time: float
    text: str
    confidence: float | None


class IssueView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    call_id: int
    segment_id: int | None
    issue_type: IssueType
    severity: Severity
    speaker: SpeakerLabel
    quoted_text: str
    reason: str
    confidence_score: float
    confidence_label: ConfidenceLabel
    is_validated: bool
    status: IssueStatus


class ScoreView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    needs_discovery: int
    rapport: int
    empathy: int
    listening: int
    product_knowledge: int
    objection_handling: int
    compliance: int
    trial_booking: int
    closing: int
    overall_quality: float
    scoring_version: str
    evidence: dict[str, Any]


class CallInsightView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    executive_summary: str
    customer_intent: str
    improvement_suggestions: list[str]
    recommended_coaching: str
    next_best_action: str


class CallDetail(BaseModel):
    id: int
    advisor_id: int | None
    advisor_name: str | None
    team_id: int | None
    team_name: str | None
    call_type: CallType
    call_datetime: datetime | None
    duration_seconds: float | None
    language_detected: str | None
    content_hash: str
    pipeline_status: str | None
    pipeline_stage: str | None
    segments: list[TranscriptSegmentView]
    redacted_text: str | None
    score: ScoreView | None
    issues: list[IssueView]
    insight: CallInsightView | None


class IssueWithContext(BaseModel):
    issue: IssueView
    call_id: int
    advisor_name: str | None
    context_segments: list[TranscriptSegmentView]


class AdvisorScorecardView(BaseModel):
    advisor_id: int
    advisor_name: str
    team_id: int
    team_name: str
    scored_call_count: int
    avg_overall_quality: float | None
    avg_dimension_scores: dict[str, float]
    issue_count_by_severity: dict[str, int]
    validated_issue_count: int
    total_issue_count: int


class ExecutiveSummaryView(BaseModel):
    total_calls: int
    calls_by_type: dict[str, int]
    scored_call_count: int
    avg_overall_quality: float | None
    avg_dimension_scores: dict[str, float]
    issue_count_by_severity: dict[str, int]
    issue_count_by_type: dict[str, int]
    validated_issue_count: int
    unvalidated_issue_count: int


class LLMStageSummaryView(BaseModel):
    stage: LLMStage
    total_calls_logged: int
    success_rate: float
    avg_latency_ms: float
    avg_retry_count: float
    latest_prompt_version: str | None
    model_name: str | None


class BenchmarkRunView(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    call_id: int
    total_pipeline_time_ms: float
    transcription_time_ms: float | None
    llm_time_ms: float | None
    real_time_factor: float | None
    whisper_model_used: str | None
    diarization_backend_used: str | None


class BenchmarkSummaryView(BaseModel):
    run_count: int
    avg_total_pipeline_time_ms: float | None
    avg_transcription_time_ms: float | None
    avg_llm_time_ms: float | None
    avg_real_time_factor: float | None
    recent: list[BenchmarkRunView]


class QueueSnapshotView(BaseModel):
    call_id: int
    content_hash: str
    advisor_name: str | None
    call_type: str
    pipeline_stage: str
    status: str
    retry_count: int
    started_at: datetime | None
    completed_at: datetime | None
    last_error: str | None


class HealthCheck(BaseModel):
    ok: bool
    database_reachable: bool
    ollama_reachable: bool | None
    queue_counts: dict[str, int]
    detail: str | None = None


class FeedbackRequest(BaseModel):
    call_id: int
    issue_id: int | None = None
    reviewer_id: str = Field(..., min_length=1, max_length=128)
    feedback_type: FeedbackType
    comment: str | None = None
