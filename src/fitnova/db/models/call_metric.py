"""CallMetric — objective, non-LLM-derived call statistics."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitnova.db.base import Base
from fitnova.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from fitnova.db.models.call import Call


class CallMetric(Base, TimestampMixin):
    """Deterministic metrics computed from diarization timing, not LLM
    judgment — used both as dashboard KPIs and as cross-checks against
    LLM-derived scores (e.g. `interruption_count` corroborates the
    INTERRUPTING_CUSTOMER issue type and the Listening score).

    Modeled as one-to-many with `Call` (not strictly one-to-one) to allow
    future re-computation/versioning without overwriting history.
    """

    __tablename__ = "call_metrics"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), nullable=False, index=True
    )

    talk_ratio_advisor: Mapped[float | None] = mapped_column(Float, nullable=True)
    talk_ratio_customer: Mapped[float | None] = mapped_column(Float, nullable=True)
    interruption_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    silence_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    longest_monologue_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    call: Mapped["Call"] = relationship(back_populates="call_metrics")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<CallMetric call_id={self.call_id}>"
