"""Issue — a flagged, evidence-grounded problem in a call."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, Float, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitnova.core.constants import ConfidenceLabel, IssueStatus, IssueType, Severity, SpeakerLabel
from fitnova.db.base import Base
from fitnova.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from fitnova.db.models.call import Call
    from fitnova.db.models.feedback import Feedback
    from fitnova.db.models.transcript_segment import TranscriptSegment


class Issue(Base, TimestampMixin):
    """A single flagged issue, always evidence-grounded.

    `is_validated` is set by the evidence validator (code, not the LLM) —
    see docs Section 6.3. An issue with `is_validated=False` must never be
    surfaced to a reviewer as fact; it exists in the table purely for audit
    / prompt-quality debugging.
    """

    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    segment_id: Mapped[int | None] = mapped_column(
        ForeignKey("transcript_segments.id", ondelete="SET NULL"), nullable=True, index=True
    )

    issue_type: Mapped[IssueType] = mapped_column(
        Enum(IssueType, native_enum=False, length=32), nullable=False
    )
    severity: Mapped[Severity] = mapped_column(
        Enum(Severity, native_enum=False, length=16), nullable=False
    )
    speaker: Mapped[SpeakerLabel] = mapped_column(
        Enum(SpeakerLabel, native_enum=False, length=16), nullable=False
    )
    quoted_text: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_score: Mapped[float] = mapped_column(Float, nullable=False)
    # Calibrated LOW/MEDIUM/HIGH alongside the raw score (docs Phase 4
    # addendum, "Confidence Calibration") - lets the dashboard visually
    # distinguish a HIGH severity + HIGH confidence flag from a HIGH
    # severity + LOW confidence one without re-deriving thresholds client-side.
    confidence_label: Mapped[ConfidenceLabel] = mapped_column(
        Enum(ConfidenceLabel, native_enum=False, length=16), nullable=False
    )
    is_validated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[IssueStatus] = mapped_column(
        Enum(IssueStatus, native_enum=False, length=16),
        default=IssueStatus.OPEN,
        nullable=False,
    )

    call: Mapped["Call"] = relationship(back_populates="issues")
    segment: Mapped["TranscriptSegment | None"] = relationship(back_populates="issues")
    feedback_entries: Mapped[list["Feedback"]] = relationship(
        back_populates="issue", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Issue id={self.id} type={self.issue_type} severity={self.severity} "
            f"validated={self.is_validated}>"
        )
