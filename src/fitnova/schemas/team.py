from __future__ import annotations

from pydantic import BaseModel, Field

from fitnova.schemas.common import TimestampedRead


class TeamBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class TeamCreate(TeamBase):
    organization_id: int


class TeamRead(TeamBase, TimestampedRead):
    organization_id: int
