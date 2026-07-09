"""Team — belongs to one Organization, has many Advisors."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitnova.db.base import Base
from fitnova.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from fitnova.db.models.advisor import Advisor
    from fitnova.db.models.organization import Organization


class Team(Base, TimestampMixin):
    """A sales pod led by a Team Leader. New teams are plain inserts — no
    code change required to add one (docs Section 7, Org Hierarchy)."""

    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="teams")
    advisors: Mapped[list["Advisor"]] = relationship(
        back_populates="team", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Team id={self.id} name={self.name!r} org_id={self.organization_id}>"
