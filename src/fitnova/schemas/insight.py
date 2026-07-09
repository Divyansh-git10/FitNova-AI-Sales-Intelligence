from __future__ import annotations

from pydantic import BaseModel, Field

from fitnova.schemas.common import ORMModel


class CallInsightBase(BaseModel):
    executive_summary: str = Field(..., min_length=1)
    customer_intent: str = Field(..., min_length=1)
    improvement_suggestions: list[str] = Field(default_factory=list)
    recommended_coaching: str = Field(..., min_length=1)
    next_best_action: str = Field(..., min_length=1)


class CallInsightCreate(CallInsightBase):
    call_id: int


class CallInsightRead(CallInsightBase, ORMModel):
    id: int
    call_id: int
