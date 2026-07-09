"""Processing queue: explicit pipeline states + dashboard-visible snapshot.

`processing_status` (one row per call) is the queue. There is no separate
in-memory or broker-backed queue — the database IS the queue, which keeps
"what's in flight, what failed, what's done" a single source of truth that
survives a process restart and is trivially queryable by the dashboard
(Phase 6) without needing a second system to stay in sync.

Explicit states, in the order a healthy call moves through them
(`fitnova.core.constants.PipelineStage`):

    INGESTED -> TRANSCRIBED -> DIARIZED -> NORMALIZED -> REDACTED
    -> CLASSIFIED -> (ANALYZED -> SCORED -> VALIDATED, Phase 4)
    -> STORED -> COMPLETED

crossed with a coarse `ProcessingStatusEnum` (PENDING / IN_PROGRESS /
COMPLETED / FAILED) that drives idempotency and retry decisions.

`QueueManager.dashboard_snapshot()` is what Phase 6's Observability view
queries directly — it returns plain, already-joined rows (advisor name,
stage, status, retry count, timings) rather than raw ORM objects, so the
dashboard never needs its own duplicate query logic for "what's in the
queue right now."
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from fitnova.core.constants import PipelineStage, ProcessingStatusEnum
from fitnova.core.logging_config import get_logger
from fitnova.db.models import Advisor, Call, ProcessingStatus

logger = get_logger(__name__)


@dataclass(frozen=True)
class QueueSnapshotRow:
    """One dashboard-ready row — what the Observability/queue view (Phase
    6) renders directly, no further joining required."""

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


class QueueManager:
    """Thin wrapper around `processing_status` state transitions. Holds no
    state itself beyond the DB session it's given — safe to construct
    per-request/per-call."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def find_by_content_hash(self, content_hash: str) -> ProcessingStatus | None:
        stmt = select(ProcessingStatus).where(ProcessingStatus.content_hash == content_hash)
        return self.session.execute(stmt).scalar_one_or_none()

    def enqueue(self, call_id: int, content_hash: str) -> ProcessingStatus:
        """Create the initial queue row for a brand-new call."""
        status = ProcessingStatus(
            call_id=call_id,
            content_hash=content_hash,
            pipeline_stage=PipelineStage.INGESTED,
            status=ProcessingStatusEnum.IN_PROGRESS,
            retry_count=0,
            started_at=datetime.now(timezone.utc),
        )
        self.session.add(status)
        self.session.flush()
        return status

    def begin_next_phase(self, status: ProcessingStatus) -> None:
        """Move a row from a terminal COMPLETED state (e.g. Phase 3's
        speech pipeline finished) into IN_PROGRESS for the next phase
        (e.g. Phase 4's analysis). Distinct from `begin_retry`: this is
        not a retry after failure, so `retry_count` is left untouched —
        it continues to represent total retries across the call's whole
        lifecycle, not per-phase."""
        status.status = ProcessingStatusEnum.IN_PROGRESS
        status.started_at = datetime.now(timezone.utc)
        status.last_error = None
        self.session.flush()

    def begin_retry(self, status: ProcessingStatus) -> None:
        status.status = ProcessingStatusEnum.IN_PROGRESS
        status.retry_count += 1
        status.started_at = datetime.now(timezone.utc)
        status.last_error = None
        self.session.flush()
        logger.info(
            "Retrying call_id=%s (attempt #%d) from stage=%s",
            status.call_id,
            status.retry_count,
            status.pipeline_stage,
        )

    def advance(self, status: ProcessingStatus, stage: PipelineStage) -> None:
        status.pipeline_stage = stage
        self.session.flush()

    def mark_completed(self, status: ProcessingStatus, final_stage: PipelineStage) -> None:
        status.pipeline_stage = final_stage
        status.status = ProcessingStatusEnum.COMPLETED
        status.completed_at = datetime.now(timezone.utc)
        status.last_error = None
        self.session.flush()

    def mark_failed(self, status: ProcessingStatus, error_message: str) -> None:
        status.status = ProcessingStatusEnum.FAILED
        status.last_error = error_message[:4000]
        self.session.flush()
        logger.error(
            "Call_id=%s failed at stage=%s (attempt #%d): %s",
            status.call_id,
            status.pipeline_stage,
            status.retry_count,
            error_message,
        )

    def dashboard_snapshot(self, limit: int = 200) -> list[QueueSnapshotRow]:
        """Every call's current queue state, most recently started first —
        the exact shape Phase 6's dashboard renders as the processing
        queue / observability table."""
        stmt = (
            select(ProcessingStatus, Call, Advisor)
            .join(Call, ProcessingStatus.call_id == Call.id)
            .outerjoin(Advisor, Call.advisor_id == Advisor.id)
            .order_by(ProcessingStatus.started_at.desc().nullslast())
            .limit(limit)
        )
        rows = self.session.execute(stmt).all()
        return [
            QueueSnapshotRow(
                call_id=call.id,
                content_hash=status.content_hash,
                advisor_name=advisor.name if advisor else None,
                call_type=call.call_type.value if call.call_type else "UNKNOWN",
                pipeline_stage=status.pipeline_stage.value,
                status=status.status.value,
                retry_count=status.retry_count,
                started_at=status.started_at,
                completed_at=status.completed_at,
                last_error=status.last_error,
            )
            for status, call, advisor in rows
        ]
