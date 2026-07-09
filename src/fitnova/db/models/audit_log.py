"""AuditLog — generic, append-only trail for any auditable action."""

from __future__ import annotations

from sqlalchemy import JSON, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from fitnova.db.base import Base
from fitnova.db.mixins import TimestampMixin


class AuditLog(Base, TimestampMixin):
    """Generic audit trail, keyed by `entity_type` + `entity_id` rather than
    a dedicated FK per entity, so a new auditable entity never requires a
    new table (docs Section 5.1, design principle #4).

    Used for events like: duplicate call skipped, LLM issue rejected by the
    evidence validator, pipeline stage retried/failed, feedback recorded.
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    entity_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String(128), nullable=False, default="SYSTEM")
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AuditLog {self.entity_type}#{self.entity_id} action={self.action!r}>"
