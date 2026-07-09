"""Call - the central entity every other analysis artifact hangs off of."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitnova.core.constants import CallType, SourceSystem
from fitnova.db.base import Base
from fitnova.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from fitnova.db.models.advisor import Advisor
    from fitnova.db.models.audio_metadata import AudioMetadata
    from fitnova.db.models.call_insight import CallInsight
    from fitnova.db.models.call_metric import CallMetric
    from fitnova.db.models.feedback import Feedback
    from fitnova.db.models.issue import Issue
    from fitnova.db.models.llm_inference_log import LLMInferenceLog
    from fitnova.db.models.pipeline_benchmark import PipelineBenchmark
    from fitnova.db.models.processing_status import ProcessingStatus
    from fitnova.db.models.score import Score
    from fitnova.db.models.transcript import Transcript


class Call(Base, TimestampMixin):
    """One sales call recording and everything known about it.

    `content_hash` is the idempotency key (SHA-256 of the raw audio bytes,
    UNIQUE): if the same file is ingested twice, the hash collision is
    caught before transcription ever runs (docs Section 5.3, 9).
    """

    __tablename__ = "calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    # Nullable: a call can be ingested before its advisor is resolvable
    # (unknown external_id, missing sidecar metadata). Such calls get
    # call_type=PENDING_METADATA instead of being dropped or assigned to a
    # guessed advisor (docs Section 9, "missing metadata").
    advisor_id: Mapped[int | None] = mapped_column(
        ForeignKey("advisors.id", ondelete="CASCADE"), nullable=True, index=True
    )

    source_system: Mapped[SourceSystem] = mapped_column(
        Enum(SourceSystem, native_enum=False, length=32), nullable=False
    )
    source_call_id: Mapped[str | None] = mapped_column(String(255), nullable=True)

    customer_ref_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)

    call_type: Mapped[CallType] = mapped_column(
        Enum(CallType, native_enum=False, length=32),
        default=CallType.UNKNOWN,
        nullable=False,
    )

    call_datetime: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    language_detected: Mapped[str | None] = mapped_column(String(32), nullable=True)

    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    advisor: Mapped["Advisor | None"] = relationship(back_populates="calls")
    audio_metadata: Mapped["AudioMetadata | None"] = relationship(
        back_populates="call", uselist=False, cascade="all, delete-orphan"
    )
    transcript: Mapped["Transcript | None"] = relationship(
        back_populates="call", uselist=False, cascade="all, delete-orphan"
    )
    issues: Mapped[list["Issue"]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )
    score: Mapped["Score | None"] = relationship(
        back_populates="call", uselist=False, cascade="all, delete-orphan"
    )
    call_insight: Mapped["CallInsight | None"] = relationship(
        back_populates="call", uselist=False, cascade="all, delete-orphan"
    )
    call_metrics: Mapped[list["CallMetric"]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )
    processing_status: Mapped["ProcessingStatus | None"] = relationship(
        back_populates="call", uselist=False, cascade="all, delete-orphan"
    )
    feedback_entries: Mapped[list["Feedback"]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )
    llm_inference_logs: Mapped[list["LLMInferenceLog"]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )
    pipeline_benchmarks: Mapped[list["PipelineBenchmark"]] = relationship(
        back_populates="call", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Call id={self.id} advisor_id={self.advisor_id} type={self.call_type}>"
