"""faster-whisper integration with automatic model-size fallback.

Loading or running a large local model can fail for reasons that have
nothing to do with the audio: out-of-memory, a corrupt cached model, a
transient download hiccup on first use. Rather than letting one bad model
kill the whole call, `WhisperTranscriber` walks the canonical size cascade
(`WHISPER_FALLBACK_ORDER` in `fitnova.core.constants`: large-v3 -> medium ->
small -> base -> tiny) starting at `Settings.whisper_model_size`, trying
each progressively smaller/cheaper model until one loads AND successfully
transcribes.

This is deliberately a *resilience* feature, not a quality knob — the
configured model is always tried first; smaller models are a fallback of
last resort, and which one actually ran is always recorded
(`PipelineBenchmark.whisper_model_used`) so nobody mistakes a
degraded-quality transcript for a normal one.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from fitnova.core.constants import WHISPER_FALLBACK_ORDER
from fitnova.core.logging_config import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class WhisperSegment:
    """One raw ASR segment, before diarization/speaker assignment."""

    start: float
    end: float
    text: str
    confidence: float | None  # derived from avg_logprob, may be None


@dataclass(frozen=True)
class TranscriptionResult:
    segments: list[WhisperSegment]
    language: str | None
    language_probability: float | None
    model_used: str
    attempted_models: list[str]
    elapsed_ms: float


class TranscriptionFailedError(Exception):
    """Raised only when every model in the fallback cascade has failed."""

    def __init__(self, attempted_models: list[str], last_error: Exception) -> None:
        self.attempted_models = attempted_models
        self.last_error = last_error
        super().__init__(
            f"Transcription failed after trying {attempted_models}: "
            f"{type(last_error).__name__}: {last_error}"
        )


def _fallback_chain(preferred: str) -> list[str]:
    """Build the cascade starting at the configured model, falling back
    through progressively smaller models in the canonical order.

    If the configured size isn't one of the five canonical sizes (e.g. a
    typo, or a fine-tuned model name), it is tried first and then the full
    canonical cascade follows as a safety net.
    """
    sizes = [m.value for m in WHISPER_FALLBACK_ORDER]
    if preferred in sizes:
        start_index = sizes.index(preferred)
        return sizes[start_index:]
    return [preferred, *sizes]


class WhisperTranscriber:
    """Wraps `faster_whisper.WhisperModel` with the fallback cascade.

    Model instances are cached per (size, device, compute_type) so a
    successful fallback doesn't re-pay the load cost on the next call —
    important since a machine that fails to load "large" once will fail
    every time, and we don't want every subsequent call to re-attempt it.
    """

    def __init__(self, model_size: str, device: str, compute_type: str) -> None:
        self.preferred_model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self._model_cache: dict[str, object] = {}
        self._known_bad: set[str] = set()

    def transcribe(self, audio_path: Path, language_hint: str | None = None) -> TranscriptionResult:
        """Transcribe `audio_path`, cascading through smaller models on
        failure. Raises `TranscriptionFailedError` only if every model in
        the chain fails."""
        chain = _fallback_chain(self.preferred_model_size)
        attempted: list[str] = []
        last_error: Exception | None = None
        start = time.perf_counter()

        for model_size in chain:
            if model_size in self._known_bad:
                logger.debug("Skipping %s — previously failed to load this run", model_size)
                continue

            attempted.append(model_size)
            try:
                model = self._get_or_load_model(model_size)
                segments, info = model.transcribe(
                    str(audio_path),
                    language=language_hint,
                    vad_filter=False,  # VAD/diarization is handled by our own fallback engine
                )
                whisper_segments = [
                    WhisperSegment(
                        start=seg.start,
                        end=seg.end,
                        text=seg.text.strip(),
                        confidence=_confidence_from_logprob(seg.avg_logprob),
                    )
                    for seg in segments
                ]
                elapsed_ms = (time.perf_counter() - start) * 1000.0
                if model_size != self.preferred_model_size:
                    logger.warning(
                        "Whisper fallback engaged: preferred=%s succeeded_with=%s attempted=%s",
                        self.preferred_model_size,
                        model_size,
                        attempted,
                    )
                return TranscriptionResult(
                    segments=whisper_segments,
                    language=getattr(info, "language", None),
                    language_probability=getattr(info, "language_probability", None),
                    model_used=model_size,
                    attempted_models=attempted,
                    elapsed_ms=elapsed_ms,
                )
            except (
                Exception
            ) as exc:  # noqa: BLE001 - deliberately broad: any failure triggers fallback
                logger.error(
                    "Whisper model '%s' failed: %s: %s", model_size, type(exc).__name__, exc
                )
                self._known_bad.add(model_size)
                last_error = exc
                continue

        raise TranscriptionFailedError(
            attempted_models=attempted, last_error=last_error or RuntimeError("no models attempted")
        )

    def _get_or_load_model(self, model_size: str):
        if model_size in self._model_cache:
            return self._model_cache[model_size]

        # Imported lazily so importing this module doesn't require
        # ctranslate2/faster-whisper to be installed unless transcription
        # is actually used (keeps unit tests for other modules lightweight).
        from faster_whisper import WhisperModel

        logger.info(
            "Loading faster-whisper model '%s' (device=%s, compute_type=%s)",
            model_size,
            self.device,
            self.compute_type,
        )
        model = WhisperModel(model_size, device=self.device, compute_type=self.compute_type)
        self._model_cache[model_size] = model
        return model


def _confidence_from_logprob(avg_logprob: float | None) -> float | None:
    """faster-whisper reports `avg_logprob` (a log-probability, typically
    in [-1, 0] for confident segments). Map it to a rough [0, 1] confidence
    score for storage — this is an approximation for dashboard display, not
    a calibrated probability."""
    if avg_logprob is None:
        return None
    return max(0.0, min(1.0, 1.0 + avg_logprob))
