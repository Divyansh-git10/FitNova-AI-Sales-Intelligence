"""PipelineBenchmark — per-run performance telemetry for one call.

Added in Phase 3 to satisfy the "pipeline benchmarking" requirement:
transcription time, diarization time, DB write latency, total pipeline
time, and Real Time Factor (RTF = total_processing_seconds /
audio_duration_seconds; RTF < 1.0 means the pipeline runs faster than the
call itself, which is the target for a usable local system).

Modeled one-to-many with `Call` (like `CallMetric`) rather than one-to-one,
so a retried run produces a new row instead of overwriting history — the
dashboard's Observability view (Phase 6) can show whether retries are
getting faster or slower, not just the latest number.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitnova.db.base import Base
from fitnova.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from fitnova.db.models.call import Call


class PipelineBenchmark(Base, TimestampMixin):
    """One timing snapshot of a full (or partial, on failure) pipeline run."""

    __tablename__ = "pipeline_benchmarks"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )

    # Per-stage timings, milliseconds. Nullable because a failed/short-circuited
    # run may not reach every stage (e.g. NO_SPEECH calls skip diarization).
    audio_validation_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    transcription_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    diarization_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    normalization_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    pii_redaction_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    classification_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Populated once Phase 4's analysis engine runs; sum of that call's
    # llm_inference_logs.latency_ms. Left NULL by the Phase 3 orchestrator.
    llm_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    db_write_time_ms: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_pipeline_time_ms: Mapped[float] = mapped_column(Float, nullable=False)

    audio_duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    # RTF = total_pipeline_time_seconds / audio_duration_seconds
    real_time_factor: Mapped[float | None] = mapped_column(Float, nullable=True)

    whisper_model_used: Mapped[str | None] = mapped_column(String(32), nullable=True)
    diarization_backend_used: Mapped[str | None] = mapped_column(String(16), nullable=True)

    call: Mapped["Call"] = relationship(back_populates="pipeline_benchmarks")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<PipelineBenchmark call_id={self.call_id} "
            f"total_ms={self.total_pipeline_time_ms:.0f} rtf={self.real_time_factor}>"
        )
