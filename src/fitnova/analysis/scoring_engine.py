"""LLM-backed scoring, with the rollup computed in Python — never by the
LLM itself (docs Section 6.1: "Computed via SQL/Python arithmetic... never
independently re-scored by the LLM").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from fitnova.analysis.confidence import calibrate_confidence
from fitnova.analysis.llm_client import LLMClient
from fitnova.analysis.llm_schemas import LLMScoringResponse
from fitnova.analysis.transcript_formatting import format_transcript_for_prompt
from fitnova.core.config import ScoringWeightsConfig, Settings
from fitnova.core.constants import LLMStage
from fitnova.db.models import TranscriptSegment

DIMENSIONS: tuple[str, ...] = (
    "needs_discovery",
    "rapport",
    "empathy",
    "listening",
    "product_knowledge",
    "objection_handling",
    "compliance",
    "trial_booking",
    "closing",
)


@dataclass(frozen=True)
class ScoringOutcome:
    dimension_scores: dict[str, int]
    overall_quality: float
    scoring_version: str
    evidence: dict[str, dict[str, Any]]


def run_scoring(
    call_id: int,
    segments: list[TranscriptSegment],
    llm_client: LLMClient,
    weights_config: ScoringWeightsConfig,
    settings: Settings,
    session: Session,
) -> ScoringOutcome:
    transcript_text = format_transcript_for_prompt(segments)

    response: LLMScoringResponse = llm_client.run_structured(
        stage=LLMStage.SCORING,
        prompt_name="scoring_v1",
        prompt_vars={"transcript": transcript_text},
        response_model=LLMScoringResponse,
        call_id=call_id,
        session=session,
    )

    dims = response.dimensions()
    dimension_scores = {name: dims[name].score for name in DIMENSIONS}
    overall_quality = sum(
        weights_config.weight_for(name) * dimension_scores[name] for name in DIMENSIONS
    )

    evidence = {
        name: {
            "reasoning": dims[name].reasoning,
            "evidence_quote": dims[name].evidence_quote,
            "confidence": dims[name].confidence,
            "confidence_label": calibrate_confidence(dims[name].confidence, settings).value,
        }
        for name in DIMENSIONS
    }

    return ScoringOutcome(
        dimension_scores=dimension_scores,
        overall_quality=round(overall_quality, 2),
        scoring_version=weights_config.scoring_version,
        evidence=evidence,
    )
