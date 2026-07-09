"""Advisor — belongs to one Team, makes many Calls."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitnova.db.base import Base
from fitnova.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from fitnova.db.models.call import Call
    from fitnova.db.models.team import Team


class Advisor(Base, TimestampMixin):
    """A tele-advisor. `external_id` correlates this row to whatever ID the
    source telephony/CRM system uses, so ingestion adapters can resolve
    advisors without the pipeline needing source-specific logic."""

    __tablename__ = "advisors"

    id: Mapped[int] = mapped_column(primary_key=True)
    team_id: Mapped[int] = mapped_column(
        ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(128), unique=True, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    team: Mapped["Team"] = relationship(back_populates="advisors")
    calls: Mapped[list["Call"]] = relationship(
        back_populates="advisor", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Advisor id={self.id} name={self.name!r} team_id={self.team_id}>"
