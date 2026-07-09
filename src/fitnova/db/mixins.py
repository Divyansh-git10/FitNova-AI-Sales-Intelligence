"""Reusable ORM mixins to avoid repeating timestamp columns on every model."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class TimestampMixin:
    """Adds a server-side-defaulted `created_at` column."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class UpdatedAtMixin:
    """Adds a server-side-defaulted, auto-updating `updated_at` column.

    Only used on tables whose rows are mutated after creation (e.g.
    `processing_status`, `issues`) — append-only tables like `audit_logs`
    intentionally do not get this.
    """

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
