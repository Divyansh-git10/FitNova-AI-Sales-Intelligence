"""Score — the 9-dimension rubric result + rollup, 1:1 with Call."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import JSON, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitnova.db.base import Base
from fitnova.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from fitnova.db.models.call import Call


class Score(Base, TimestampMixin):
    """Per-call rubric scores (0-10 each) plus the weighted `overall_quality`
    rollup. `scoring_version` mirrors `config/weights.yaml`'s
    `scoring_version` at the time this row was computed, so historical
    scores stay interpretable if the rubric weights change later (docs
    Section 5.3)."""

    __tablename__ = "scores"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    needs_discovery: Mapped[int] = mapped_column(Integer, nullable=False)
    rapport: Mapped[int] = mapped_column(Integer, nullable=False)
    empathy: Mapped[int] = mapped_column(Integer, nullable=False)
    listening: Mapped[int] = mapped_column(Integer, nullable=False)
    product_knowledge: Mapped[int] = mapped_column(Integer, nullable=False)
    objection_handling: Mapped[int] = mapped_column(Integer, nullable=False)
    compliance: Mapped[int] = mapped_column(Integer, nullable=False)
    trial_booking: Mapped[int] = mapped_column(Integer, nullable=False)
    closing: Mapped[int] = mapped_column(Integer, nullable=False)

    # Computed via SQL/Python arithmetic from the weights in config/weights.yaml
    # — never independently re-scored by the LLM (docs Section 6.1).
    overall_quality: Mapped[float] = mapped_column(Float, nullable=False)
    scoring_version: Mapped[str] = mapped_column(String(32), nullable=False)

    # Per-dimension explainability (docs Phase 4 addendum, "Explainability
    # for every score"): {dimension: {reasoning, evidence_quote, confidence,
    # confidence_label}}. A JSON blob rather than 9 x 4 extra columns -
    # still queryable via SQLite JSON functions, but avoids schema bloat
    # for what is fundamentally one denormalized explanation object per
    # score. Never empty for a successfully scored call — every dimension
    # must have a reasoning string, even if evidence_quote is null (a
    # dimension can be scored on the *absence* of something, e.g. "no
    # trial booking was ever raised" has no quote to cite).
    evidence: Mapped[dict] = mapped_column(JSON, nullable=False)

    call: Mapped["Call"] = relationship(back_populates="score")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Score call_id={self.call_id} overall={self.overall_quality:.1f}>"
