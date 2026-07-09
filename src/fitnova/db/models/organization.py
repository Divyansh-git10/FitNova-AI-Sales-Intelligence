"""Organization — the top of the org hierarchy (org -> teams -> advisors)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitnova.db.base import Base
from fitnova.db.mixins import TimestampMixin

if TYPE_CHECKING:
    from fitnova.db.models.team import Team


class Organization(Base, TimestampMixin):
    """A FitNova customer org. Schema supports multiple organizations from
    day one (multi-tenant-ready) even though the demo seeds a single one —
    see docs Section 3, assumption 5."""

    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    teams: Mapped[list["Team"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover - debug convenience
        return f"<Organization id={self.id} name={self.name!r}>"
