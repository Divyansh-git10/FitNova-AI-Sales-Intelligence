from __future__ import annotations

from pydantic import BaseModel, Field

from fitnova.schemas.common import TimestampedRead


class OrganizationBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class OrganizationCreate(OrganizationBase):
    pass


class OrganizationRead(OrganizationBase, TimestampedRead):
    pass
