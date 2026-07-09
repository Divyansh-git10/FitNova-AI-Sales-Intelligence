from __future__ import annotations

from pydantic import BaseModel, Field

from fitnova.schemas.common import ORMModel


class CallMetricBase(BaseModel):
    talk_ratio_advisor: float | None = Field(default=None, ge=0.0, le=1.0)
    talk_ratio_customer: float | None = Field(default=None, ge=0.0, le=1.0)
    interruption_count: int | None = Field(default=None, ge=0)
    silence_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    longest_monologue_seconds: float | None = Field(default=None, ge=0)


class CallMetricCreate(CallMetricBase):
    call_id: int


class CallMetricRead(CallMetricBase, ORMModel):
    id: int
    call_id: int
