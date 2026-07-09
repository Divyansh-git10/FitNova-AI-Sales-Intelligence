"""Schemas for pipeline performance telemetry (docs Phase 3 addendum)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from fitnova.schemas.common import TimestampedRead


class PipelineBenchmarkBase(BaseModel):
    audio_validation_time_ms: float | None = Field(default=None, ge=0)
    transcription_time_ms: float | None = Field(default=None, ge=0)
    diarization_time_ms: float | None = Field(default=None, ge=0)
    normalization_time_ms: float | None = Field(default=None, ge=0)
    pii_redaction_time_ms: float | None = Field(default=None, ge=0)
    classification_time_ms: float | None = Field(default=None, ge=0)
    llm_time_ms: float | None = Field(default=None, ge=0)
    db_write_time_ms: float | None = Field(default=None, ge=0)
    total_pipeline_time_ms: float = Field(..., ge=0)
    audio_duration_seconds: float | None = Field(default=None, ge=0)
    real_time_factor: float | None = Field(default=None, ge=0)
    whisper_model_used: str | None = Field(default=None, max_length=32)
    diarization_backend_used: str | None = Field(default=None, max_length=16)


class PipelineBenchmarkCreate(PipelineBenchmarkBase):
    call_id: int


class PipelineBenchmarkRead(PipelineBenchmarkBase, TimestampedRead):
    call_id: int
