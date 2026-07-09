from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from fitnova.schemas.common import TimestampedRead


class AuditLogBase(BaseModel):
    entity_type: str = Field(..., max_length=64)
    entity_id: int | None = None
    action: str = Field(..., max_length=128)
    actor: str = Field(default="SYSTEM", max_length=128)
    details: dict[str, Any] | None = None


class AuditLogCreate(AuditLogBase):
    pass


class AuditLogRead(AuditLogBase, TimestampedRead):
    pass
