from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field

from fitnova.schemas.common import TimestampedRead


class AdvisorBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    email: EmailStr | None = None
    external_id: str | None = Field(default=None, max_length=128)
    is_active: bool = True


class AdvisorCreate(AdvisorBase):
    team_id: int


class AdvisorRead(AdvisorBase, TimestampedRead):
    team_id: int
