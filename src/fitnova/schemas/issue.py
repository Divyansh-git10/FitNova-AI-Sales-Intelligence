from __future__ import annotations

from pydantic import BaseModel, Field

from fitnova.core.constants import ConfidenceLabel, IssueStatus, IssueType, Severity, SpeakerLabel
from fitnova.schemas.common import TimestampedRead


class IssueBase(BaseModel):
    issue_type: IssueType
    severity: Severity
    speaker: SpeakerLabel
    quoted_text: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    confidence_score: float = Field(..., ge=0.0, le=1.0)
    confidence_label: ConfidenceLabel


class IssueCreate(IssueBase):
    """Payload the evidence validator uses to persist an LLM-proposed issue
    that has passed the fuzzy-match check (docs Section 6.3). `is_validated`
    is not client-settable — it is always set by the validator, not trusted
    from the LLM's raw output."""

    call_id: int
    segment_id: int | None = None


class IssueRead(IssueBase, TimestampedRead):
    call_id: int
    segment_id: int | None
    is_validated: bool
    status: IssueStatus
