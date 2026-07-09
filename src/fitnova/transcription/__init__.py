"""Speech transcription — faster-whisper with automatic model fallback.

See `whisper_engine.py` for `WhisperTranscriber`, which cascades through
large-v3 -> medium -> small -> base -> tiny on load/inference failure.
"""

from fitnova.transcription.whisper_engine import (
    TranscriptionFailedError,
    TranscriptionResult,
    WhisperSegment,
    WhisperTranscriber,
)

__all__ = [
    "WhisperTranscriber",
    "TranscriptionResult",
    "WhisperSegment",
    "TranscriptionFailedError",
]
