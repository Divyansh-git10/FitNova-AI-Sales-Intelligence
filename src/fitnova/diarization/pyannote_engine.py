"""Optional pyannote.audio diarization backend.

Gated behind `Settings.diarization_backend == "pyannote"`. Not installed by
default (see `requirements.txt` — it's commented out) because it pulls in
`torch` + large model downloads and requires a HuggingFace token, which is
too heavy a default for a 48-hour local-setup prototype (docs Section 3,
assumption 3).

`diarize_pyannote()` raises `DiarizationError` for any failure — missing
package, missing token, download failure, inference error — and the
caller (`diarization.select_diarizer`) is responsible for falling back to
the deterministic engine rather than failing the whole call. This mirrors
the same resilience philosophy as the Whisper model cascade: prefer a
degraded result over a hard failure.
"""

from __future__ import annotations

from pathlib import Path

from fitnova.core.config import Settings
from fitnova.core.constants import SpeakerLabel
from fitnova.core.logging_config import get_logger
from fitnova.diarization.base import DiarizationError, DiarizedTurn

logger = get_logger(__name__)

_PRETRAINED_PIPELINE = "pyannote/speaker-diarization-3.1"


def diarize_pyannote(audio_path: Path, settings: Settings) -> list[DiarizedTurn]:
    """Run real speaker diarization via pyannote.audio.

    Produces `SPEAKER_00`, `SPEAKER_01`, ... labels from the pipeline, then
    maps the speaker with the most total talk time in the first third of
    the call to ADVISOR (the same "advisor opens the call" heuristic used
    by the fallback engine, applied to real speaker identities instead of
    alternating turns — see docs Section 9).
    """
    if not settings.huggingface_token:
        raise DiarizationError(
            "DIARIZATION_BACKEND=pyannote requires HUGGINGFACE_TOKEN to be set in .env"
        )

    try:
        from pyannote.audio import Pipeline
    except ImportError as exc:
        raise DiarizationError(
            "pyannote.audio is not installed. Install it manually "
            "(`pip install pyannote.audio`) or set DIARIZATION_BACKEND=fallback."
        ) from exc

    try:
        pipeline = Pipeline.from_pretrained(
            _PRETRAINED_PIPELINE, use_auth_token=settings.huggingface_token
        )
        diarization = pipeline(str(audio_path))
    except Exception as exc:  # noqa: BLE001
        raise DiarizationError(f"pyannote diarization failed: {type(exc).__name__}: {exc}") from exc

    raw_turns: list[tuple[float, float, str]] = [
        (turn.start, turn.end, speaker)
        for turn, _, speaker in diarization.itertracks(yield_label=True)
    ]
    if not raw_turns:
        logger.warning("pyannote returned zero turns for %s", audio_path)
        return []

    advisor_speaker_id = _infer_advisor_speaker(raw_turns)
    return [
        DiarizedTurn(
            start=start,
            end=end,
            speaker_label=(
                SpeakerLabel.ADVISOR if speaker == advisor_speaker_id else SpeakerLabel.CUSTOMER
            ),
            raw_speaker_id=speaker,
        )
        for start, end, speaker in raw_turns
    ]


def _infer_advisor_speaker(raw_turns: list[tuple[float, float, str]]) -> str:
    """Heuristic: whichever speaker talks first is the advisor (the
    advisor initiates the call). Same assumption as the fallback engine,
    applied to real diarized identities instead of alternating turns."""
    first_turn = min(raw_turns, key=lambda t: t[0])
    return first_turn[2]
