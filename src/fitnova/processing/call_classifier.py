"""Rule-based call classification — the fast, deterministic gate before any
LLM call.

Assigns `CallType` (SALES / WRONG_NUMBER / INTERNAL / NO_SPEECH /
UNSUPPORTED_LANGUAGE) from cheap, transcript-level signals: word count,
duration, detected language, and a small configured keyword list for
internal calls (docs Section 9's edge cases: "non-sales calls (wrong
number, internal)").

This is deliberately NOT an LLM call. `LLMStage.CALL_CLASSIFICATION`
(recorded in `llm_inference_logs`, docs Section 12) is reserved for a
Phase 4 upgrade path — an LLM-assisted second opinion on transcripts this
rule-based pass finds ambiguous — but the cheap heuristic gate runs first
on every call, so the expensive model is never invoked to answer a
question regex/arithmetic can already answer confidently.

Every classification decision returns a human-readable `reason` string
suitable for an `AuditLog` entry — "why was this call classified as X" is
always answerable without re-deriving it.
"""

from __future__ import annotations

from fitnova.core.config import Settings
from fitnova.core.constants import AudioQualityFlag, CallType
from fitnova.core.logging_config import get_logger
from fitnova.processing.normalizer import NormalizedTranscript

logger = get_logger(__name__)


def classify_call(
    transcript: NormalizedTranscript,
    duration_seconds: float,
    audio_quality_flag: AudioQualityFlag,
    detected_language: str | None,
    settings: Settings,
) -> tuple[CallType, str]:
    """Returns `(call_type, reason)`. Rules are evaluated in order; the
    first match wins, so ordering encodes priority (e.g. a silent call is
    NO_SPEECH even if it happens to also be short enough to look like a
    wrong number)."""

    if audio_quality_flag == AudioQualityFlag.SILENT or transcript.word_count == 0:
        return CallType.NO_SPEECH, "Audio flagged SILENT or transcript has zero words"

    if detected_language and detected_language.lower() not in settings.supported_languages_list():
        return (
            CallType.UNSUPPORTED_LANGUAGE,
            f"Detected language '{detected_language}' not in supported set "
            f"{settings.supported_languages_list()}",
        )

    internal_keyword = _find_internal_keyword(transcript.full_text, settings)
    if internal_keyword:
        return CallType.INTERNAL, f"Matched internal-call keyword: '{internal_keyword}'"

    if (
        duration_seconds <= settings.wrong_number_max_duration_seconds
        and transcript.word_count <= settings.wrong_number_max_words
    ):
        return (
            CallType.WRONG_NUMBER,
            f"Call is short ({duration_seconds:.1f}s, {transcript.word_count} words) "
            f"— below wrong-number thresholds "
            f"({settings.wrong_number_max_duration_seconds}s / "
            f"{settings.wrong_number_max_words} words)",
        )

    return CallType.SALES, "No exclusion rule matched — treated as a sales call"


def _find_internal_keyword(full_text: str, settings: Settings) -> str | None:
    lowered = full_text.lower()
    for keyword in settings.internal_call_keywords_list():
        if keyword in lowered:
            return keyword
    return None
