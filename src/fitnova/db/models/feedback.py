"""Feedback — the human review / contest loop."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitnova.core.constants import FeedbackType, ReviewerRole
from fitnova.db.base import Base
from fitnova.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from fitnova.db.models.call import Call
    from fitnova.db.models.issue import Issue


class Feedback(Base, TimestampMixin):
    """A human correction/annotation. Appends, never overwrites — contesting
    a flag doesn't delete the LLM's original output, it adds a Feedback row
    and (via the application layer) moves `issues.status` (docs Section 3,
    assumption 9)."""

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )
    issue_id: Mapped[int | None] = mapped_column(
        ForeignKey("issues.id", ondelete="CASCADE"), nullable=True, index=True
    )

    reviewer_role: Mapped[ReviewerRole] = mapped_column(
        Enum(ReviewerRole, native_enum=False, length=16), nullable=False
    )
    reviewer_id: Mapped[str] = mapped_column(String(128), nullable=False)
    feedback_type: Mapped[FeedbackType] = mapped_column(
        Enum(FeedbackType, native_enum=False, length=16), nullable=False
    )
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)

    call: Mapped["Call"] = relationship(back_populates="feedback_entries")
    issue: Mapped["Issue | None"] = relationship(back_populates="feedback_entries")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Feedback id={self.id} call_id={self.call_id} type={self.feedback_type}>"
