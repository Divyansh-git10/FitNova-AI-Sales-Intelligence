from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator


class ScoreBase(BaseModel):
    needs_discovery: int = Field(..., ge=0, le=10)
    rapport: int = Field(..., ge=0, le=10)
    empathy: int = Field(..., ge=0, le=10)
    listening: int = Field(..., ge=0, le=10)
    product_knowledge: int = Field(..., ge=0, le=10)
    objection_handling: int = Field(..., ge=0, le=10)
    compliance: int = Field(..., ge=0, le=10)
    trial_booking: int = Field(..., ge=0, le=10)
    closing: int = Field(..., ge=0, le=10)


class ScoreCreate(ScoreBase):
    """`overall_quality` is intentionally NOT accepted here — it is always
    computed server-side from `config/weights.yaml`, never supplied by a
    caller or the LLM directly (docs Section 6.1). `evidence` is required:
    every dimension must carry a reasoning string (docs Phase 4 addendum,
    "Explainability for every score")."""

    call_id: int
    scoring_version: str
    evidence: dict[str, Any]


class ScoreRead(ScoreBase):
    id: int
    call_id: int
    overall_quality: float
    scoring_version: str
    evidence: dict[str, Any]

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _sanity_check_overall(self) -> "ScoreRead":
        if not (0.0 <= self.overall_quality <= 10.0):
            raise ValueError("overall_quality must be within [0, 10]")
        return self
