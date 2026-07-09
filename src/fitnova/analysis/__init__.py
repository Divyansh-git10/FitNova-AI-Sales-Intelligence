"""AI analysis engine: LLM client with observability, scoring, issue
detection, evidence validation, and insight generation.

- `ollama_client.py`      — transport wrapper around the local Ollama
                             server (tenacity-retried, model version lookup).
- `llm_client.py`          — structured-output + retry-with-feedback +
                             per-attempt observability logging.
- `prompt_manager.py`      — loads versioned prompt templates from `prompts/`.
- `llm_schemas.py`         — Pydantic models the raw LLM JSON is validated
                             against.
- `confidence.py`          — numeric -> LOW/MEDIUM/HIGH calibration.
- `transcript_formatting.py` — shared numbered/timestamped transcript
                             rendering used by every prompt.
- `scoring_engine.py`      — 9-dimension rubric scoring; the weighted
                             `overall_quality` rollup is computed in
                             Python, never by the LLM.
- `issue_detector.py`      — structured issue extraction against the
                             closed `IssueType` taxonomy.
- `evidence_validator.py`  — the hallucination gate: fuzzy-matches every
                             issue's quote against the real transcript.
- `insight_generator.py`   — executive summary, coaching, next best action.
- `batch.py`               — `AnalysisOrchestrator`, the Phase 4 batch
                             entrypoint extending Phase 3's pipeline with
                             ANALYZED -> SCORED -> VALIDATED -> STORED ->
                             COMPLETED.
"""

from fitnova.analysis.confidence import calibrate_confidence
from fitnova.analysis.evidence_validator import ValidatedIssue, validate_issues
from fitnova.analysis.insight_generator import build_context_summary, generate_insights
from fitnova.analysis.issue_detector import build_issue_taxonomy_block, detect_issues
from fitnova.analysis.llm_client import LLMClient, LLMResponseValidationError
from fitnova.analysis.llm_schemas import (
    LLMInsightResponse,
    LLMIssueDetectionResponse,
    LLMIssueItem,
    LLMScoringResponse,
    ScoreDimensionResult,
)
from fitnova.analysis.ollama_client import OllamaClient, OllamaConnectionError
from fitnova.analysis.prompt_manager import PromptLoadError, PromptManager
from fitnova.analysis.scoring_engine import DIMENSIONS, ScoringOutcome, run_scoring
from fitnova.analysis.transcript_formatting import format_transcript_for_prompt

__all__ = [
    "calibrate_confidence",
    "ValidatedIssue",
    "validate_issues",
    "build_issue_taxonomy_block",
    "detect_issues",
    "build_context_summary",
    "generate_insights",
    "LLMClient",
    "LLMResponseValidationError",
    "LLMInsightResponse",
    "LLMIssueDetectionResponse",
    "LLMIssueItem",
    "LLMScoringResponse",
    "ScoreDimensionResult",
    "OllamaClient",
    "OllamaConnectionError",
    "PromptLoadError",
    "PromptManager",
    "DIMENSIONS",
    "ScoringOutcome",
    "run_scoring",
    "format_transcript_for_prompt",
]
