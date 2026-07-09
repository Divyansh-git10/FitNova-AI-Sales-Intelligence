"""LLMInferenceLog — the observability backbone (docs Section 12)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitnova.core.constants import LLMStage
from fitnova.db.base import Base
from fitnova.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from fitnova.db.models.call import Call


class LLMInferenceLog(Base, TimestampMixin):
    """One row per LLM invocation, success or failure.

    Written by `analysis.llm_client.LLMClient` (Phase 4) for every call to
    Ollama, regardless of which stage triggered it. This is the audit trail
    behind the claim that issue tagging is "reliable" — an engineer can
    always pull up exactly which prompt version and model produced a given
    score or flag, and how many retries it took.
    """

    __tablename__ = "llm_inference_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )

    stage: Mapped[LLMStage] = mapped_column(
        Enum(LLMStage, native_enum=False, length=32), nullable=False, index=True
    )
    prompt_version: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    temperature: Mapped[float | None] = mapped_column(Float, nullable=True)

    latency_ms: Mapped[float] = mapped_column(Float, nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_response_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)

    call: Mapped["Call"] = relationship(back_populates="llm_inference_logs")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<LLMInferenceLog call_id={self.call_id} stage={self.stage} "
            f"success={self.success} latency_ms={self.latency_ms:.0f}>"
        )
