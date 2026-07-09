from __future__ import annotations

from pydantic import BaseModel, Field

from fitnova.core.constants import FeedbackType, ReviewerRole
from fitnova.schemas.common import TimestampedRead


class FeedbackBase(BaseModel):
    reviewer_role: ReviewerRole
    reviewer_id: str = Field(..., min_length=1, max_length=128)
    feedback_type: FeedbackType
    comment: str | None = None


class FeedbackCreate(FeedbackBase):
    call_id: int
    issue_id: int | None = None


class FeedbackRead(FeedbackBase, TimestampedRead):
    call_id: int
    issue_id: int | None
