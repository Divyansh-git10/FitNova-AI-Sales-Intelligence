"""Phase 4 batch analysis orchestrator.

Extends Phase 3's speech pipeline with the AI analysis stages: for every
transcribed SALES call not yet scored, runs scoring -> issue detection ->
evidence validation -> insight generation -> persistence, advancing the
SAME `ProcessingStatus` row Phase 3 created (ANALYZED -> SCORED ->
VALIDATED -> STORED -> COMPLETED) — one queue row tracks a call's entire
lifecycle, not just one phase (docs Section "Queue state management").

Batch processing (docs Phase 4 addendum #4): `run_batch()` processes many
calls in one invocation, isolating failures per call — one bad transcript
never stops the rest of the batch from being analyzed, mirroring Phase 3's
`SpeechPipelineOrchestrator.run_once()` batch semantics.

Idempotency + retries mirror Phase 3 exactly: a call with a `Score` row is
never re-analyzed; a call whose analysis previously FAILED is retried (up
to `Settings.max_processing_retries`) the next time `run_batch()` is
called with no extra scheduling machinery required. Once retries are
exhausted, the call is still re-found on every batch run and reported as
"skipped_exhausted" (not silently dropped) — dashboard visibility for
permanently-failed calls, mirroring Phase 3's folder-rescan convention.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, sessionmaker

from fitnova.analysis.evidence_validator import validate_issues
from fitnova.analysis.insight_generator import generate_insights
from fitnova.analysis.issue_detector import detect_issues
from fitnova.analysis.llm_client import LLMClient
from fitnova.analysis.prompt_manager import PromptManager
from fitnova.analysis.scoring_engine import run_scoring
from fitnova.core.config import Settings
from fitnova.core.constants import CallType, PipelineStage, ProcessingStatusEnum
from fitnova.core.logging_config import get_logger
from fitnova.db.models import (
    AuditLog,
    Call,
    CallInsight,
    Issue,
    LLMInferenceLog,
    PipelineBenchmark,
    ProcessingStatus,
    Score,
    Transcript,
    TranscriptSegment,
)
from fitnova.pipeline.benchmarking import BenchmarkRecorder
from fitnova.pipeline.queue_manager import QueueManager

logger = get_logger(__name__)


@dataclass
class AnalysisResult:
    call_id: int
    # outcome: one of "completed" / "skipped_not_sales" / "skipped_already_analyzed" /
    # "skipped_exhausted" / "failed"
    outcome: str
    overall_quality: float | None = None
    issue_count: int | None = None
    validated_issue_count: int | None = None
    error: str | None = None


class AnalysisOrchestrator:
    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        llm_client: LLMClient | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        if llm_client is not None:
            self.llm_client = llm_client
        else:
            prompt_manager = PromptManager(settings.resolved_prompts_dir())
            self.llm_client = LLMClient(settings, prompt_manager)

    def run_batch(self, call_ids: list[int] | None = None, limit: int = 50) -> list[AnalysisResult]:
        """Analyze either the given `call_ids`, or (if None) every eligible
        pending call, up to `limit`."""
        session = self.session_factory()
        try:
            if call_ids is not None:
                target_ids = list(call_ids)
            else:
                target_ids = [c.id for c in self._find_pending_calls(session, limit)]
        finally:
            session.close()

        logger.info("Analysis batch starting: %d call(s) selected", len(target_ids))
        results = [self._process_call(call_id) for call_id in target_ids]
        outcomes = {}
        for r in results:
            outcomes[r.outcome] = outcomes.get(r.outcome, 0) + 1
        logger.info("Analysis batch complete: %s", outcomes)
        return results

    def _find_pending_calls(self, session: Session, limit: int) -> list[Call]:
        # Both COMPLETED (Phase 3 done, never analyzed) and FAILED rows are
        # selected here - including calls that have already exhausted their
        # retries. Filtering exhausted calls out at this SQL level would
        # make them silently vanish from every future batch; instead
        # `_process_call` re-finds them, checks retry_count against
        # `max_processing_retries`, and reports "skipped_exhausted" on
        # every run - mirroring Phase 3's folder-rescan convention, so a
        # permanently-failed call stays visible on the dashboard queue
        # view instead of quietly disappearing (docs Section 12,
        # "failure visibility, not failure hiding").
        stmt = (
            select(Call)
            .join(ProcessingStatus, ProcessingStatus.call_id == Call.id)
            .outerjoin(Score, Score.call_id == Call.id)
            .where(Call.call_type == CallType.SALES)
            .where(Score.id.is_(None))
            .where(
                or_(
                    ProcessingStatus.status == ProcessingStatusEnum.COMPLETED,
                    ProcessingStatus.status == ProcessingStatusEnum.FAILED,
                )
            )
            .order_by(Call.id)
            .limit(limit)
        )
        return list(session.execute(stmt).scalars().all())

    def _process_call(self, call_id: int) -> AnalysisResult:
        session = self.session_factory()
        try:
            call = session.get(Call, call_id)
            if call is None:
                return AnalysisResult(call_id=call_id, outcome="failed", error="Call not found")
            if call.call_type != CallType.SALES:
                return AnalysisResult(call_id=call_id, outcome="skipped_not_sales")
            if call.score is not None:
                return AnalysisResult(call_id=call_id, outcome="skipped_already_analyzed")

            status_row = call.processing_status
            if status_row is None:
                return AnalysisResult(
                    call_id=call_id, outcome="failed", error="No processing_status row for call"
                )

            queue = QueueManager(session)
            if status_row.status == ProcessingStatusEnum.FAILED:
                if status_row.retry_count >= self.settings.max_processing_retries:
                    self._audit(session, call.id, "ANALYSIS_RETRY_EXHAUSTED")
                    session.commit()
                    return AnalysisResult(
                        call_id=call_id, outcome="skipped_exhausted", error=status_row.last_error
                    )
                queue.begin_retry(status_row)
            else:
                queue.begin_next_phase(status_row)
            session.commit()
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            session.close()
            logger.exception("Failed to prepare analysis for call_id=%s", call_id)
            return AnalysisResult(call_id=call_id, outcome="failed", error=str(exc))

        try:
            result = self._run_analysis(session, call, status_row)
            session.commit()
            return result
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            self._record_failure(session, status_row.id, str(exc))
            logger.exception("Analysis failed for call_id=%s", call_id)
            return AnalysisResult(call_id=call_id, outcome="failed", error=str(exc))
        finally:
            session.close()

    def _run_analysis(
        self, session: Session, call: Call, status_row: ProcessingStatus
    ) -> AnalysisResult:
        recorder = BenchmarkRecorder()
        queue = QueueManager(session)

        segments = (
            session.query(TranscriptSegment)
            .join(Transcript, TranscriptSegment.transcript_id == Transcript.id)
            .filter(Transcript.call_id == call.id)
            .order_by(TranscriptSegment.segment_index)
            .all()
        )
        if not segments:
            raise RuntimeError(f"Call {call.id} has no transcript segments to analyze")

        weights_config = self.settings.load_weights()
        issue_rules_config = self.settings.load_issue_rules()

        # Stage checkpoints below map onto the existing PipelineStage enum
        # (shared with Phase 3): ANALYZED = scoring done, SCORED = issue
        # detection + evidence validation done, VALIDATED = insight
        # generation done, STORED = all rows persisted.
        with recorder.stage("scoring"):
            scoring_outcome = run_scoring(
                call.id, segments, self.llm_client, weights_config, self.settings, session
            )
        queue.advance(status_row, PipelineStage.ANALYZED)

        with recorder.stage("issue_detection"):
            raw_issues = detect_issues(
                call.id, segments, self.llm_client, issue_rules_config, session
            )
        with recorder.stage("evidence_validation"):
            validated_issues = validate_issues(
                raw_issues, segments, issue_rules_config, self.settings
            )
        queue.advance(status_row, PipelineStage.SCORED)

        with recorder.stage("insight_generation"):
            insight = generate_insights(
                call.id, segments, scoring_outcome, validated_issues, self.llm_client, session
            )
        queue.advance(status_row, PipelineStage.VALIDATED)

        rejected_count = sum(1 for i in validated_issues if not i.is_validated)
        if rejected_count:
            self._audit(
                session,
                call.id,
                "ISSUES_REJECTED_UNGROUNDED",
                extra={"rejected_count": rejected_count},
            )

        with recorder.stage("db_write"):
            session.add(
                Score(
                    call_id=call.id,
                    **scoring_outcome.dimension_scores,
                    overall_quality=scoring_outcome.overall_quality,
                    scoring_version=scoring_outcome.scoring_version,
                    evidence=scoring_outcome.evidence,
                )
            )
            for issue in validated_issues:
                session.add(
                    Issue(
                        call_id=call.id,
                        segment_id=issue.segment_id,
                        issue_type=issue.issue_type,
                        severity=issue.severity,
                        speaker=issue.speaker,
                        quoted_text=issue.quoted_text,
                        reason=issue.reason,
                        confidence_score=issue.confidence_score,
                        confidence_label=issue.confidence_label,
                        is_validated=issue.is_validated,
                    )
                )
            session.add(
                CallInsight(
                    call_id=call.id,
                    executive_summary=insight.executive_summary,
                    customer_intent=insight.customer_intent,
                    improvement_suggestions=insight.improvement_suggestions,
                    recommended_coaching=insight.recommended_coaching,
                    next_best_action=insight.next_best_action,
                )
            )
        queue.advance(status_row, PipelineStage.STORED)

        llm_time_ms = self._sum_llm_latency(session, call.id)
        benchmark = recorder.build(
            call_id=call.id,
            audio_duration_seconds=call.duration_seconds,
            whisper_model_used=None,
            diarization_backend_used=None,
            llm_time_ms=llm_time_ms,
        )
        session.add(PipelineBenchmark(call_id=call.id, **benchmark.model_dump(exclude={"call_id"})))

        queue.mark_completed(status_row, final_stage=PipelineStage.COMPLETED)

        return AnalysisResult(
            call_id=call.id,
            outcome="completed",
            overall_quality=scoring_outcome.overall_quality,
            issue_count=len(validated_issues),
            validated_issue_count=len(validated_issues) - rejected_count,
        )

    def _sum_llm_latency(self, session: Session, call_id: int) -> float:
        total = (
            session.query(func.sum(LLMInferenceLog.latency_ms))
            .filter(LLMInferenceLog.call_id == call_id)
            .scalar()
        )
        return float(total) if total is not None else 0.0

    def _record_failure(self, session: Session, status_id: int, error_message: str) -> None:
        status_row = session.get(ProcessingStatus, status_id)
        if status_row is None:  # pragma: no cover - defensive
            return
        QueueManager(session).mark_failed(status_row, error_message)
        session.commit()

    def _audit(
        self, session: Session, call_id: int, action: str, extra: dict | None = None
    ) -> None:
        details = extra or {}
        session.add(
            AuditLog(
                entity_type="Call",
                entity_id=call_id,
                action=action,
                actor="SYSTEM",
                details=details,
            )
        )
