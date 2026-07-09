"""CallInsight — narrative output (summary, coaching, next best action)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitnova.db.base import Base
from fitnova.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from fitnova.db.models.call import Call


class CallInsight(Base, TimestampMixin):
    """LLM-generated narrative summary for a call, 1:1 with Call.

    Kept in its own table (rather than columns on `scores`) because it is
    produced by a *separate* LLM call from issue extraction (docs Section
    6.3, mechanism #6: "Segmentation of concerns") — narrative generation
    is allowed to be more fluent, issue/score extraction is kept mechanical.
    """

    __tablename__ = "call_insights"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    executive_summary: Mapped[str] = mapped_column(Text, nullable=False)
    customer_intent: Mapped[str] = mapped_column(Text, nullable=False)
    improvement_suggestions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    recommended_coaching: Mapped[str] = mapped_column(Text, nullable=False)
    next_best_action: Mapped[str] = mapped_column(Text, nullable=False)

    call: Mapped["Call"] = relationship(back_populates="call_insight")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CallInsight call_id={self.call_id}>"
