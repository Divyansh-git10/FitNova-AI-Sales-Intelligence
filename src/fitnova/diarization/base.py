"""Shared types for both diarization backends."""

from __future__ import annotations

from dataclasses import dataclass

from fitnova.core.constants import SpeakerLabel


@dataclass(frozen=True)
class DiarizedTurn:
    """One speaker turn, independent of ASR text — merged with whisper's
    text segments by `processing.normalizer` based on timestamp overlap."""

    start: float
    end: float
    speaker_label: SpeakerLabel
    raw_speaker_id: str  # e.g. "SPEAKER_00" — pre-ADVISOR/CUSTOMER mapping, kept for debugging


class DiarizationError(Exception):
    """Raised when a diarization backend cannot produce a result at all
    (as opposed to producing a low-confidence one)."""
