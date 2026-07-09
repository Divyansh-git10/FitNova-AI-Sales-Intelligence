"""Transcript post-processing: audio validation, normalization, PII
redaction, and rule-based call classification.

- `audio_validation.py` — metadata extraction + quality flagging.
- `normalizer.py`       — merges ASR + diarization into timestamped,
                           speaker-labeled segments.
- `pii_redaction.py`    — regex-based masking, run before the LLM ever
                           sees the transcript.
- `call_classifier.py`  — deterministic CallType gate before any LLM call.
"""

from fitnova.processing.audio_validation import (
    AudioAnalysisResult,
    AudioValidationError,
    analyze_audio,
    to_mono_pcm16,
)
from fitnova.processing.call_classifier import classify_call
from fitnova.processing.normalizer import NormalizedSegment, NormalizedTranscript, normalize
from fitnova.processing.pii_redaction import RedactionFinding, redact_segments, redact_text

__all__ = [
    "AudioAnalysisResult",
    "AudioValidationError",
    "analyze_audio",
    "to_mono_pcm16",
    "NormalizedSegment",
    "NormalizedTranscript",
    "normalize",
    "RedactionFinding",
    "redact_text",
    "redact_segments",
    "classify_call",
]
