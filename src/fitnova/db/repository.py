"""Repository layer — every read/write query the API, CLI, and dashboard
use to talk to the database.

Neither `fitnova.api` nor `dashboard/` write raw SQLAlchemy queries
themselves (docs Section 8) — they call into here. This keeps aggregation
logic (advisor scorecards, executive KPIs, issue drill-down) in exactly one
place, testable independently of any HTTP or Streamlit framework, and
guarantees the API and the dashboard can never silently disagree about how
an average is computed.

Every "compute an aggregate" function here does the arithmetic in SQL/
Python — nothing is ever eyeballed or hardcoded from a sample call, per
the project's "never fabricate outputs, never hardcode analysis" rule:
an org with zero scored calls gets `None`/empty results, not a stand-in
number.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from fitnova.analysis.scoring_engine import DIMENSIONS
from fitnova.core.constants import (
    IssueStatus,
    IssueType,
    LLMStage,
    ProcessingStatusEnum,
    Severity,
)
from fitnova.db.models import (
    Advisor,
    AuditLog,
    Call,
    Feedback,
    Issue,
    LLMInferenceLog,
    Organization,
    PipelineBenchmark,
    ProcessingStatus,
    Score,
    Team,
    Transcript,
    TranscriptSegment,
)
from fitnova.pipeline.queue_manager import QueueManager, QueueSnapshotRow

# --------------------------------------------------------------------------
# Organization hierarchy
# --------------------------------------------------------------------------


def list_organizations(session: Session) -> list[Organization]:
    return list(session.execute(select(Organization).order_by(Organization.name)).scalars().all())


def list_teams(session: Session, organization_id: int | None = None) -> list[Team]:
    stmt = select(Team).order_by(Team.name)
    if organization_id is not None:
        stmt = stmt.where(Team.organization_id == organization_id)
    return list(session.execute(stmt).scalars().all())


def list_advisors(
    session: Session, team_id: int | None = None, active_only: bool = False
) -> list[Advisor]:
    stmt = select(Advisor).order_by(Advisor.name)
    if team_id is not None:
        stmt = stmt.where(Advisor.team_id == team_id)
    if active_only:
        stmt = stmt.where(Advisor.is_active.is_(True))
    return list(session.execute(stmt).scalars().all())


def get_advisor(session: Session, advisor_id: int) -> Advisor | None:
    return session.get(Advisor, advisor_id)


# --------------------------------------------------------------------------
# Calls: list (filtered/paginated) + detail
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class CallListFilters:
    organization_id: int | None = None
    team_id: int | None = None
    advisor_id: int | None = None
    call_type: str | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    min_overall_quality: float | None = None
    max_overall_quality: float | None = None
    only_with_validated_issues: bool = False


def list_calls(
    session: Session, filters: CallListFilters, page: int = 1, page_size: int = 25
) -> tuple[list[Call], int]:
    """Returns `(page_of_calls, total_matching_count)`. Joins are applied
    only when the corresponding filter is set, so an unfiltered call list
    stays a cheap single-table scan."""
    stmt = select(Call)
    count_stmt = select(func.count(func.distinct(Call.id)))

    if filters.advisor_id is not None:
        stmt = stmt.where(Call.advisor_id == filters.advisor_id)
        count_stmt = count_stmt.where(Call.advisor_id == filters.advisor_id)
    if filters.team_id is not None or filters.organization_id is not None:
        stmt = stmt.join(Advisor, Call.advisor_id == Advisor.id)
        count_stmt = count_stmt.join(Advisor, Call.advisor_id == Advisor.id)
        if filters.team_id is not None:
            stmt = stmt.where(Advisor.team_id == filters.team_id)
            count_stmt = count_stmt.where(Advisor.team_id == filters.team_id)
        if filters.organization_id is not None:
            stmt = stmt.join(Team, Advisor.team_id == Team.id)
            count_stmt = count_stmt.join(Team, Advisor.team_id == Team.id)
            stmt = stmt.where(Team.organization_id == filters.organization_id)
            count_stmt = count_stmt.where(Team.organization_id == filters.organization_id)
    if filters.call_type is not None:
        stmt = stmt.where(Call.call_type == filters.call_type)
        count_stmt = count_stmt.where(Call.call_type == filters.call_type)
    if filters.date_from is not None:
        stmt = stmt.where(Call.call_datetime >= filters.date_from)
        count_stmt = count_stmt.where(Call.call_datetime >= filters.date_from)
    if filters.date_to is not None:
        stmt = stmt.where(Call.call_datetime <= filters.date_to)
        count_stmt = count_stmt.where(Call.call_datetime <= filters.date_to)
    if filters.min_overall_quality is not None or filters.max_overall_quality is not None:
        stmt = stmt.join(Score, Score.call_id == Call.id)
        count_stmt = count_stmt.join(Score, Score.call_id == Call.id)
        if filters.min_overall_quality is not None:
            stmt = stmt.where(Score.overall_quality >= filters.min_overall_quality)
            count_stmt = count_stmt.where(Score.overall_quality >= filters.min_overall_quality)
        if filters.max_overall_quality is not None:
            stmt = stmt.where(Score.overall_quality <= filters.max_overall_quality)
            count_stmt = count_stmt.where(Score.overall_quality <= filters.max_overall_quality)
    if filters.only_with_validated_issues:
        stmt = stmt.join(Issue, Issue.call_id == Call.id).where(Issue.is_validated.is_(True))
        count_stmt = count_stmt.join(Issue, Issue.call_id == Call.id).where(
            Issue.is_validated.is_(True)
        )

    total = session.execute(count_stmt).scalar_one()
    stmt = stmt.order_by(Call.id.desc()).distinct().offset((page - 1) * page_size).limit(page_size)
    items = list(session.execute(stmt).scalars().all())
    return items, total


def get_call_detail(session: Session, call_id: int) -> Call | None:
    """Eager-loads every relationship the call detail view (API + dashboard
    transcript/evidence/replay pages) needs in one round trip."""
    stmt = (
        select(Call)
        .where(Call.id == call_id)
        .options(
            selectinload(Call.advisor).selectinload(Advisor.team).selectinload(Team.organization),
            selectinload(Call.audio_metadata),
            selectinload(Call.transcript).selectinload(Transcript.segments),
            selectinload(Call.score),
            selectinload(Call.issues).selectinload(Issue.segment),
            selectinload(Call.call_insight),
            selectinload(Call.call_metrics),
            selectinload(Call.pipeline_benchmarks),
            selectinload(Call.processing_status),
        )
    )
    return session.execute(stmt).unique().scalar_one_or_none()


def get_call_evidence(session: Session, call_id: int) -> list[Issue]:
    """All issues for a call, with their anchoring segment eager-loaded —
    the "evidence viewer" data source (docs B4/B9)."""
    stmt = (
        select(Issue)
        .where(Issue.call_id == call_id)
        .options(selectinload(Issue.segment))
        .order_by(Issue.severity.desc(), Issue.id)
    )
    return list(session.execute(stmt).unique().scalars().all())


# --------------------------------------------------------------------------
# Advisor scorecards + leaderboard
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class AdvisorScorecard:
    advisor_id: int
    advisor_name: str
    team_id: int
    team_name: str
    scored_call_count: int
    avg_overall_quality: float | None
    avg_dimension_scores: dict[str, float] = field(default_factory=dict)
    issue_count_by_severity: dict[str, int] = field(default_factory=dict)
    validated_issue_count: int = 0
    total_issue_count: int = 0


def advisor_scorecard(
    session: Session,
    advisor_id: int,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> AdvisorScorecard | None:
    advisor = session.get(Advisor, advisor_id)
    if advisor is None:
        return None

    score_cols = [getattr(Score, name) for name in DIMENSIONS]
    stmt = (
        select(
            func.count(Score.id),
            func.avg(Score.overall_quality),
            *[func.avg(col) for col in score_cols],
        )
        .join(Call, Score.call_id == Call.id)
        .where(Call.advisor_id == advisor_id)
    )
    if date_from is not None:
        stmt = stmt.where(Call.call_datetime >= date_from)
    if date_to is not None:
        stmt = stmt.where(Call.call_datetime <= date_to)

    row = session.execute(stmt).one()
    scored_call_count = row[0] or 0
    avg_overall = round(row[1], 2) if row[1] is not None else None
    avg_dimensions = {
        name: round(value, 2)
        for name, value in zip(DIMENSIONS, row[2:], strict=True)
        if value is not None
    }

    issue_stmt = (
        select(Issue.severity, func.count(Issue.id))
        .join(Call, Issue.call_id == Call.id)
        .where(Call.advisor_id == advisor_id, Issue.is_validated.is_(True))
    )
    if date_from is not None:
        issue_stmt = issue_stmt.where(Call.call_datetime >= date_from)
    if date_to is not None:
        issue_stmt = issue_stmt.where(Call.call_datetime <= date_to)
    issue_stmt = issue_stmt.group_by(Issue.severity)
    severity_counts = {sev.value: count for sev, count in session.execute(issue_stmt).all()}
    validated_issue_count = sum(severity_counts.values())

    total_issue_count = session.execute(
        select(func.count(Issue.id))
        .join(Call, Issue.call_id == Call.id)
        .where(Call.advisor_id == advisor_id)
    ).scalar_one()

    return AdvisorScorecard(
        advisor_id=advisor.id,
        advisor_name=advisor.name,
        team_id=advisor.team_id,
        team_name=advisor.team.name if advisor.team else "",
        scored_call_count=scored_call_count,
        avg_overall_quality=avg_overall,
        avg_dimension_scores=avg_dimensions,
        issue_count_by_severity=severity_counts,
        validated_issue_count=validated_issue_count,
        total_issue_count=total_issue_count,
    )


def advisor_leaderboard(session: Session, team_id: int | None = None) -> list[AdvisorScorecard]:
    """One scorecard per advisor who has at least one scored call, sorted
    best-to-worst by `avg_overall_quality`. Advisors with zero scored calls
    are omitted rather than shown with a fabricated 0 — see module
    docstring."""
    advisors = list_advisors(session, team_id=team_id)
    cards = [advisor_scorecard(session, a.id) for a in advisors]
    scored_cards = [c for c in cards if c is not None and c.scored_call_count > 0]
    return sorted(scored_cards, key=lambda c: c.avg_overall_quality or 0.0, reverse=True)


# --------------------------------------------------------------------------
# Executive analytics
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutiveSummary:
    total_calls: int
    calls_by_type: dict[str, int]
    scored_call_count: int
    avg_overall_quality: float | None
    avg_dimension_scores: dict[str, float]
    issue_count_by_severity: dict[str, int]
    issue_count_by_type: dict[str, int]
    validated_issue_count: int
    unvalidated_issue_count: int


def executive_summary(
    session: Session,
    organization_id: int | None = None,
    team_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> ExecutiveSummary:
    call_stmt = select(Call.call_type, func.count(Call.id))
    if team_id is not None or organization_id is not None:
        call_stmt = call_stmt.join(Advisor, Call.advisor_id == Advisor.id)
        if team_id is not None:
            call_stmt = call_stmt.where(Advisor.team_id == team_id)
        if organization_id is not None:
            call_stmt = call_stmt.join(Team, Advisor.team_id == Team.id).where(
                Team.organization_id == organization_id
            )
    if date_from is not None:
        call_stmt = call_stmt.where(Call.call_datetime >= date_from)
    if date_to is not None:
        call_stmt = call_stmt.where(Call.call_datetime <= date_to)
    call_stmt = call_stmt.group_by(Call.call_type)
    calls_by_type = {ct.value: count for ct, count in session.execute(call_stmt).all()}
    total_calls = sum(calls_by_type.values())

    score_cols = [getattr(Score, name) for name in DIMENSIONS]
    score_stmt = select(
        func.count(Score.id), func.avg(Score.overall_quality), *[func.avg(c) for c in score_cols]
    )
    score_stmt = score_stmt.join(Call, Score.call_id == Call.id)
    if team_id is not None or organization_id is not None:
        score_stmt = score_stmt.join(Advisor, Call.advisor_id == Advisor.id)
        if team_id is not None:
            score_stmt = score_stmt.where(Advisor.team_id == team_id)
        if organization_id is not None:
            score_stmt = score_stmt.join(Team, Advisor.team_id == Team.id).where(
                Team.organization_id == organization_id
            )
    if date_from is not None:
        score_stmt = score_stmt.where(Call.call_datetime >= date_from)
    if date_to is not None:
        score_stmt = score_stmt.where(Call.call_datetime <= date_to)
    row = session.execute(score_stmt).one()
    scored_call_count = row[0] or 0
    avg_overall_quality = round(row[1], 2) if row[1] is not None else None
    avg_dimension_scores = {
        name: round(value, 2)
        for name, value in zip(DIMENSIONS, row[2:], strict=True)
        if value is not None
    }

    issue_severity_stmt = select(Issue.severity, func.count(Issue.id)).where(
        Issue.is_validated.is_(True)
    )
    issue_type_stmt = select(Issue.issue_type, func.count(Issue.id)).where(
        Issue.is_validated.is_(True)
    )
    validated_count_stmt = select(func.count(Issue.id)).where(Issue.is_validated.is_(True))
    unvalidated_count_stmt = select(func.count(Issue.id)).where(Issue.is_validated.is_(False))

    if team_id is not None or organization_id is not None:
        issue_severity_stmt = issue_severity_stmt.join(Call, Issue.call_id == Call.id).join(
            Advisor, Call.advisor_id == Advisor.id
        )
        issue_type_stmt = issue_type_stmt.join(Call, Issue.call_id == Call.id).join(
            Advisor, Call.advisor_id == Advisor.id
        )
        if team_id is not None:
            issue_severity_stmt = issue_severity_stmt.where(Advisor.team_id == team_id)
            issue_type_stmt = issue_type_stmt.where(Advisor.team_id == team_id)

    issue_severity_stmt = issue_severity_stmt.group_by(Issue.severity)
    issue_type_stmt = issue_type_stmt.group_by(Issue.issue_type)
    issue_count_by_severity = {
        sev.value: count for sev, count in session.execute(issue_severity_stmt).all()
    }
    issue_count_by_type = {it.value: count for it, count in session.execute(issue_type_stmt).all()}
    validated_issue_count = session.execute(validated_count_stmt).scalar_one()
    unvalidated_issue_count = session.execute(unvalidated_count_stmt).scalar_one()

    return ExecutiveSummary(
        total_calls=total_calls,
        calls_by_type=calls_by_type,
        scored_call_count=scored_call_count,
        avg_overall_quality=avg_overall_quality,
        avg_dimension_scores=avg_dimension_scores,
        issue_count_by_severity=issue_count_by_severity,
        issue_count_by_type=issue_count_by_type,
        validated_issue_count=validated_issue_count,
        unvalidated_issue_count=unvalidated_issue_count,
    )


# --------------------------------------------------------------------------
# Issue drill-down
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class IssueListFilters:
    severity: Severity | None = None
    issue_type: IssueType | None = None
    status: IssueStatus | None = None
    is_validated: bool | None = None
    advisor_id: int | None = None
    team_id: int | None = None
    call_id: int | None = None


def list_issues(
    session: Session, filters: IssueListFilters, page: int = 1, page_size: int = 25
) -> tuple[list[Issue], int]:
    stmt = select(Issue).options(selectinload(Issue.segment), selectinload(Issue.call))
    count_stmt = select(func.count(Issue.id))

    if filters.advisor_id is not None or filters.team_id is not None:
        stmt = stmt.join(Call, Issue.call_id == Call.id).join(
            Advisor, Call.advisor_id == Advisor.id
        )
        count_stmt = count_stmt.join(Call, Issue.call_id == Call.id).join(
            Advisor, Call.advisor_id == Advisor.id
        )
        if filters.advisor_id is not None:
            stmt = stmt.where(Advisor.id == filters.advisor_id)
            count_stmt = count_stmt.where(Advisor.id == filters.advisor_id)
        if filters.team_id is not None:
            stmt = stmt.where(Advisor.team_id == filters.team_id)
            count_stmt = count_stmt.where(Advisor.team_id == filters.team_id)
    if filters.call_id is not None:
        stmt = stmt.where(Issue.call_id == filters.call_id)
        count_stmt = count_stmt.where(Issue.call_id == filters.call_id)
    if filters.severity is not None:
        stmt = stmt.where(Issue.severity == filters.severity)
        count_stmt = count_stmt.where(Issue.severity == filters.severity)
    if filters.issue_type is not None:
        stmt = stmt.where(Issue.issue_type == filters.issue_type)
        count_stmt = count_stmt.where(Issue.issue_type == filters.issue_type)
    if filters.status is not None:
        stmt = stmt.where(Issue.status == filters.status)
        count_stmt = count_stmt.where(Issue.status == filters.status)
    if filters.is_validated is not None:
        stmt = stmt.where(Issue.is_validated == filters.is_validated)
        count_stmt = count_stmt.where(Issue.is_validated == filters.is_validated)

    total = session.execute(count_stmt).scalar_one()
    stmt = stmt.order_by(Issue.id.desc()).offset((page - 1) * page_size).limit(page_size)
    items = list(session.execute(stmt).unique().scalars().all())
    return items, total


def get_issue_with_context(
    session: Session, issue_id: int, context_segments: int = 1
) -> dict | None:
    """The evidence-viewer payload: the flagged issue plus the segments
    immediately before/after its anchor segment, so a reviewer sees the
    quote in conversational context, not in isolation."""
    issue = session.get(
        Issue, issue_id, options=[selectinload(Issue.segment), selectinload(Issue.call)]
    )
    if issue is None:
        return None

    surrounding: list[TranscriptSegment] = []
    if issue.segment is not None:
        transcript_id = issue.segment.transcript_id
        idx = issue.segment.segment_index
        stmt = (
            select(TranscriptSegment)
            .where(
                TranscriptSegment.transcript_id == transcript_id,
                TranscriptSegment.segment_index >= idx - context_segments,
                TranscriptSegment.segment_index <= idx + context_segments,
            )
            .order_by(TranscriptSegment.segment_index)
        )
        surrounding = list(session.execute(stmt).scalars().all())

    return {"issue": issue, "context_segments": surrounding}


# --------------------------------------------------------------------------
# LLM observability + pipeline benchmarking
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class LLMStageSummary:
    stage: str
    total_calls_logged: int
    success_rate: float
    avg_latency_ms: float
    avg_retry_count: float
    latest_prompt_version: str | None
    model_name: str | None


def llm_observability_summary(session: Session) -> list[LLMStageSummary]:
    summaries: list[LLMStageSummary] = []
    for stage in LLMStage:
        rows = list(
            session.execute(
                select(LLMInferenceLog)
                .where(LLMInferenceLog.stage == stage)
                .order_by(LLMInferenceLog.id)
            )
            .scalars()
            .all()
        )
        if not rows:
            continue
        success_count = sum(1 for r in rows if r.success)
        summaries.append(
            LLMStageSummary(
                stage=stage.value,
                total_calls_logged=len(rows),
                success_rate=round(success_count / len(rows), 4),
                avg_latency_ms=round(sum(r.latency_ms for r in rows) / len(rows), 1),
                avg_retry_count=round(sum(r.retry_count for r in rows) / len(rows), 2),
                latest_prompt_version=rows[-1].prompt_version,
                model_name=rows[-1].model_name,
            )
        )
    return summaries


@dataclass(frozen=True)
class BenchmarkSummary:
    run_count: int
    avg_total_pipeline_time_ms: float | None
    avg_transcription_time_ms: float | None
    avg_llm_time_ms: float | None
    avg_real_time_factor: float | None
    recent: list[PipelineBenchmark] = field(default_factory=list)


def benchmark_summary(session: Session, recent_limit: int = 20) -> BenchmarkSummary:
    agg_stmt = select(
        func.count(PipelineBenchmark.id),
        func.avg(PipelineBenchmark.total_pipeline_time_ms),
        func.avg(PipelineBenchmark.transcription_time_ms),
        func.avg(PipelineBenchmark.llm_time_ms),
        func.avg(PipelineBenchmark.real_time_factor),
    )
    run_count, avg_total, avg_transcription, avg_llm, avg_rtf = session.execute(agg_stmt).one()
    recent_stmt = (
        select(PipelineBenchmark).order_by(PipelineBenchmark.id.desc()).limit(recent_limit)
    )
    recent = list(session.execute(recent_stmt).scalars().all())
    return BenchmarkSummary(
        run_count=run_count or 0,
        avg_total_pipeline_time_ms=round(avg_total, 1) if avg_total is not None else None,
        avg_transcription_time_ms=(
            round(avg_transcription, 1) if avg_transcription is not None else None
        ),
        avg_llm_time_ms=round(avg_llm, 1) if avg_llm is not None else None,
        avg_real_time_factor=round(avg_rtf, 3) if avg_rtf is not None else None,
        recent=recent,
    )


def queue_snapshot(session: Session, limit: int = 200) -> list[QueueSnapshotRow]:
    return QueueManager(session).dashboard_snapshot(limit=limit)


def queue_health(session: Session) -> dict:
    """Coarse health rollup for the `/health` endpoint and CLI `doctor`
    command: how many calls are in each processing state right now."""
    stmt = select(ProcessingStatus.status, func.count(ProcessingStatus.id)).group_by(
        ProcessingStatus.status
    )
    counts = {status.value: count for status, count in session.execute(stmt).all()}
    return {
        "pending": counts.get(ProcessingStatusEnum.PENDING.value, 0),
        "in_progress": counts.get(ProcessingStatusEnum.IN_PROGRESS.value, 0),
        "completed": counts.get(ProcessingStatusEnum.COMPLETED.value, 0),
        "failed": counts.get(ProcessingStatusEnum.FAILED.value, 0),
    }


# --------------------------------------------------------------------------
# Feedback
# --------------------------------------------------------------------------


def create_feedback(
    session: Session,
    call_id: int,
    reviewer_role,
    reviewer_id: str,
    feedback_type,
    issue_id: int | None = None,
    comment: str | None = None,
) -> Feedback:
    """Records the human feedback row and, for CONTEST/CONFIRM against a
    specific issue, updates that issue's `status` — appending, never
    overwriting the LLM's original output (docs Section 3, assumption 9)."""
    feedback = Feedback(
        call_id=call_id,
        issue_id=issue_id,
        reviewer_role=reviewer_role,
        reviewer_id=reviewer_id,
        feedback_type=feedback_type,
        comment=comment,
    )
    session.add(feedback)

    if issue_id is not None:
        issue = session.get(Issue, issue_id)
        if issue is not None:
            type_value = (
                feedback_type.value if hasattr(feedback_type, "value") else str(feedback_type)
            )
            if type_value == "CONTEST":
                issue.status = IssueStatus.CONTESTED
            elif type_value == "CONFIRM":
                issue.status = IssueStatus.CONFIRMED

    session.add(
        AuditLog(
            entity_type="Feedback",
            entity_id=None,
            action="FEEDBACK_RECORDED",
            actor=reviewer_id,
            details={"call_id": call_id, "issue_id": issue_id, "feedback_type": str(feedback_type)},
        )
    )
    session.flush()
    return feedback


def list_feedback_for_call(session: Session, call_id: int) -> list[Feedback]:
    stmt = select(Feedback).where(Feedback.call_id == call_id).order_by(Feedback.id.desc())
    return list(session.execute(stmt).scalars().all())
