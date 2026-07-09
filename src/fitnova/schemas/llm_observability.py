"""Schemas for the LLM observability surface (docs Section 12)."""

from __future__ import annotations

from pydantic import BaseModel, Field

from fitnova.core.constants import LLMStage
from fitnova.schemas.common import TimestampedRead


class LLMInferenceLogBase(BaseModel):
    stage: LLMStage
    prompt_version: str = Field(..., max_length=32)
    model_name: str = Field(..., max_length=128)
    model_version: str | None = Field(default=None, max_length=128)
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    latency_ms: float = Field(..., ge=0)
    retry_count: int = Field(default=0, ge=0)
    prompt_tokens: int | None = Field(default=None, ge=0)
    completion_tokens: int | None = Field(default=None, ge=0)
    success: bool
    error_message: str | None = None
    raw_response_excerpt: str | None = None


class LLMInferenceLogCreate(LLMInferenceLogBase):
    call_id: int


class LLMInferenceLogRead(LLMInferenceLogBase, TimestampedRead):
    call_id: int


class LLMObservabilitySummary(BaseModel):
    """Aggregated view for the dashboard's Observability page — computed by
    the repository layer (Phase 5), never hand-assembled in the UI."""

    stage: LLMStage
    total_calls: int
    success_rate: float
    avg_latency_ms: float
    p95_latency_ms: float
    avg_retry_count: float
    model_name: str
    prompt_version: str
