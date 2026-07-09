"""ProcessingStatus — pipeline checkpoint + idempotency + retry bookkeeping."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitnova.core.constants import PipelineStage, ProcessingStatusEnum
from fitnova.db.base import Base
from fitnova.db.mixins import TimestampMixin, UpdatedAtMixin

if TYPE_CHECKING:
    from fitnova.db.models.call import Call


class ProcessingStatus(Base, TimestampMixin, UpdatedAtMixin):
    """Tracks exactly how far a call has progressed through the pipeline.

    Deliberately a separate table from `calls` (not a status column on
    `calls`) for two reasons: it needs its own retry/error bookkeeping, and
    the idempotency hash-check needs to run *before* a `calls` row
    necessarily exists (docs Section 5.3).
    """

    __tablename__ = "processing_status"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)

    pipeline_stage: Mapped[PipelineStage] = mapped_column(
        Enum(PipelineStage, native_enum=False, length=32),
        default=PipelineStage.INGESTED,
        nullable=False,
    )
    status: Mapped[ProcessingStatusEnum] = mapped_column(
        Enum(ProcessingStatusEnum, native_enum=False, length=16),
        default=ProcessingStatusEnum.PENDING,
        nullable=False,
    )
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    call: Mapped["Call"] = relationship(back_populates="processing_status")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ProcessingStatus call_id={self.call_id} stage={self.pipeline_stage} "
            f"status={self.status} retries={self.retry_count}>"
        )
