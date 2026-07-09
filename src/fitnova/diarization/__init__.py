"""Speaker diarization — pyannote (optional) with a deterministic fallback.

`diarize()` is the single entrypoint the orchestrator calls. It never
raises for a missing/misconfigured pyannote backend — it logs a warning
and drops down to the deterministic VAD engine, and always reports which
backend actually produced the result (`PipelineBenchmark.diarization_backend_used`),
so a degraded run is visible, not silent.
"""

from __future__ import annotations

from pathlib import Path

from fitnova.core.config import Settings
from fitnova.core.constants import DiarizationBackend
from fitnova.core.logging_config import get_logger
from fitnova.diarization.base import DiarizationError, DiarizedTurn
from fitnova.diarization.fallback_engine import diarize_fallback

logger = get_logger(__name__)


def diarize(audio_path: Path, settings: Settings) -> tuple[list[DiarizedTurn], str]:
    """Returns (turns, backend_used). `backend_used` is one of
    `DiarizationBackend` values and is always accurate, even when a
    requested pyannote run silently degrades to fallback."""
    if settings.diarization_backend == DiarizationBackend.PYANNOTE.value:
        try:
            from fitnova.diarization.pyannote_engine import diarize_pyannote

            turns = diarize_pyannote(audio_path, settings)
            return turns, DiarizationBackend.PYANNOTE.value
        except DiarizationError as exc:
            logger.warning(
                "pyannote diarization unavailable (%s) — falling back to deterministic engine", exc
            )

    turns = diarize_fallback(audio_path, settings)
    return turns, DiarizationBackend.FALLBACK.value


__all__ = ["diarize", "DiarizedTurn", "DiarizationError", "diarize_fallback"]
