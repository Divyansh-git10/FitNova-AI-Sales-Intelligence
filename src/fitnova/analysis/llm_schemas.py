"""Pydantic models the LLM's raw JSON output is validated against.

These are distinct from `fitnova.schemas` (the API/DB I/O contracts) on
purpose: this is the shape an LLM is asked to produce and is allowed to
get subtly wrong (missing field, wrong type, extra prose) — validation
failure here triggers the retry-with-feedback loop in `llm_client.py`
rather than a hard crash. Once validated, `scoring_engine.py` /
`issue_detector.py` / `insight_generator.py` translate these into the
`fitnova.schemas.*Create` shapes that actually get persisted.

`model_config = ConfigDict(extra="forbid")` on every response model is
deliberate: an LLM that starts returning extra, unexpected fields is a
signal something drifted (prompt change, model change) and should fail
loudly via the retry loop, not be silently accepted.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from fitnova.core.constants import IssueType, Severity, SpeakerLabel


class ScoreDimensionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(..., ge=0, le=10)
    reasoning: str = Field(..., min_length=1)
    evidence_quote: str | None = None
    confidence: float = Field(..., ge=0.0, le=1.0)


class LLMScoringResponse(BaseModel):
    """One `ScoreDimensionResult` per rubric dimension (docs Section 6.1)."""

    model_config = ConfigDict(extra="forbid")

    needs_discovery: ScoreDimensionResult
    rapport: ScoreDimensionResult
    empathy: ScoreDimensionResult
    listening: ScoreDimensionResult
    product_knowledge: ScoreDimensionResult
    objection_handling: ScoreDimensionResult
    compliance: ScoreDimensionResult
    trial_booking: ScoreDimensionResult
    closing: ScoreDimensionResult

    def dimensions(self) -> dict[str, ScoreDimensionResult]:
        return {
            "needs_discovery": self.needs_discovery,
            "rapport": self.rapport,
            "empathy": self.empathy,
            "listening": self.listening,
            "product_knowledge": self.product_knowledge,
            "objection_handling": self.objection_handling,
            "compliance": self.compliance,
            "trial_booking": self.trial_booking,
            "closing": self.closing,
        }


class LLMIssueItem(BaseModel):
    """One proposed issue, PRE-validation. `segment_index` anchors the
    quote to a real transcript segment — the evidence validator resolves
    it to a `segment_id` and fuzzy-matches `quoted_text` before this is
    trusted (docs Section 6.3)."""

    model_config = ConfigDict(extra="forbid")

    issue_type: IssueType
    severity: Severity
    speaker: SpeakerLabel
    segment_index: int = Field(..., ge=0)
    quoted_text: str = Field(..., min_length=1)
    reason: str = Field(..., min_length=1)
    confidence: float = Field(..., ge=0.0, le=1.0)


class LLMIssueDetectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issues: list[LLMIssueItem] = Field(default_factory=list)


class LLMInsightResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    executive_summary: str = Field(..., min_length=1)
    customer_intent: str = Field(..., min_length=1)
    improvement_suggestions: list[str] = Field(default_factory=list)
    recommended_coaching: str = Field(..., min_length=1)
    next_best_action: str = Field(..., min_length=1)
