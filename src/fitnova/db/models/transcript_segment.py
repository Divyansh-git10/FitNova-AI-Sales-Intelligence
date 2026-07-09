"""TranscriptSegment — one diarized, timestamped utterance."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, Float, ForeignKey, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitnova.core.constants import SpeakerLabel
from fitnova.db.base import Base

if TYPE_CHECKING:
    from fitnova.db.models.issue import Issue
    from fitnova.db.models.transcript import Transcript


class TranscriptSegment(Base):
    """One speaker turn. This is the evidence anchor every `Issue` points
    at via `segment_id` — "show me the quote" is a join, not trust (docs
    Section 5.1, design principle #2)."""

    __tablename__ = "transcript_segments"

    id: Mapped[int] = mapped_column(primary_key=True)
    transcript_id: Mapped[int] = mapped_column(
        ForeignKey("transcripts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False)
    speaker_label: Mapped[SpeakerLabel] = mapped_column(
        Enum(SpeakerLabel, native_enum=False, length=16),
        default=SpeakerLabel.UNKNOWN,
        nullable=False,
    )
    start_time: Mapped[float] = mapped_column(Float, nullable=False)
    end_time: Mapped[float] = mapped_column(Float, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)

    transcript: Mapped["Transcript"] = relationship(back_populates="segments")
    issues: Mapped[list["Issue"]] = relationship(back_populates="segment")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<TranscriptSegment id={self.id} speaker={self.speaker_label} "
            f"[{self.start_time:.1f}-{self.end_time:.1f}]>"
        )
