from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from fitnova.core.constants import CallType, SourceSystem
from fitnova.schemas.common import TimestampedRead


class CallBase(BaseModel):
    source_system: SourceSystem
    source_call_id: str | None = Field(default=None, max_length=255)
    customer_ref_hash: str | None = Field(default=None, max_length=128)
    call_datetime: datetime | None = None
    duration_seconds: float | None = Field(default=None, ge=0)
    language_detected: str | None = Field(default=None, max_length=32)


class CallCreate(CallBase):
    """Payload used by the ingestion layer to register a newly seen call.
    `content_hash` is required and enforced unique at the DB level — this
    is the idempotency gate (docs Section 5.3). `advisor_id` is nullable:
    a call can exist before its advisor is resolvable (docs Section 9,
    "missing metadata")."""

    advisor_id: int | None = None
    content_hash: str = Field(..., min_length=32, max_length=64)


class CallRead(CallBase, TimestampedRead):
    advisor_id: int | None
    call_type: CallType
    content_hash: str
