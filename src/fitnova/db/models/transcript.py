"""Transcript — 1:1 with Call, holds full text plus a link to its segments."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitnova.db.base import Base
from fitnova.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from fitnova.db.models.call import Call
    from fitnova.db.models.transcript_segment import TranscriptSegment


class Transcript(Base, TimestampMixin):
    """Full transcript for a call.

    `raw_text` is retained for audit purposes with restricted access.
    `redacted_text` is the PII-safe version and is the ONLY version ever
    sent to the LLM or shown on non-privileged dashboard views (docs
    Section 5.3 — this is a deliberate privacy boundary, not just a
    display-layer redaction).
    """

    __tablename__ = "transcripts"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    raw_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    redacted_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    word_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    avg_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    call: Mapped["Call"] = relationship(back_populates="transcript")
    segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="transcript",
        cascade="all, delete-orphan",
        order_by="TranscriptSegment.segment_index",
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Transcript call_id={self.call_id} words={self.word_count}>"
