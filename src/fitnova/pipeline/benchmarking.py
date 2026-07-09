"""Pipeline performance telemetry.

`BenchmarkRecorder` times each stage of a single call's processing run and
produces a `PipelineBenchmarkCreate` row at the end — transcription time,
diarization time, normalization time, PII redaction time, classification
time, DB write time, total pipeline time, and Real Time Factor (RTF).

RTF = total_pipeline_time_seconds / audio_duration_seconds. RTF < 1.0
means the pipeline processed the call faster than the call itself took to
happen — the practical bar for "usable without a backlog building up."

`llm_time_ms` is deliberately left for Phase 4 to populate (summed from
that call's `llm_inference_logs` rows) — this recorder only knows about
the Phase 3 speech pipeline.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from dataclasses import dataclass, field

from fitnova.schemas.benchmark import PipelineBenchmarkCreate


@dataclass
class BenchmarkRecorder:
    _pipeline_start: float = field(default_factory=time.perf_counter)
    _durations_ms: dict[str, float] = field(default_factory=dict)

    @contextmanager
    def stage(self, name: str):
        """Context manager: `with recorder.stage("transcription"): ...`"""
        start = time.perf_counter()
        try:
            yield
        finally:
            self._durations_ms[name] = (time.perf_counter() - start) * 1000.0

    def record(self, name: str, elapsed_ms: float) -> None:
        """Manually record a duration already measured elsewhere (e.g. the
        Whisper engine reports its own elapsed_ms including model-fallback
        retries, which is more accurate than timing it again here)."""
        self._durations_ms[name] = elapsed_ms

    def duration_ms(self, name: str) -> float | None:
        return self._durations_ms.get(name)

    def total_elapsed_ms(self) -> float:
        return (time.perf_counter() - self._pipeline_start) * 1000.0

    def build(
        self,
        call_id: int,
        audio_duration_seconds: float | None,
        whisper_model_used: str | None,
        diarization_backend_used: str | None,
        llm_time_ms: float | None = None,
    ) -> PipelineBenchmarkCreate:
        total_ms = self.total_elapsed_ms()
        rtf = None
        if audio_duration_seconds and audio_duration_seconds > 0:
            rtf = (total_ms / 1000.0) / audio_duration_seconds

        return PipelineBenchmarkCreate(
            call_id=call_id,
            audio_validation_time_ms=self.duration_ms("audio_validation"),
            transcription_time_ms=self.duration_ms("transcription"),
            diarization_time_ms=self.duration_ms("diarization"),
            normalization_time_ms=self.duration_ms("normalization"),
            pii_redaction_time_ms=self.duration_ms("pii_redaction"),
            classification_time_ms=self.duration_ms("classification"),
            llm_time_ms=llm_time_ms,
            db_write_time_ms=self.duration_ms("db_write"),
            total_pipeline_time_ms=total_ms,
            audio_duration_seconds=audio_duration_seconds,
            real_time_factor=rtf,
            whisper_model_used=whisper_model_used,
            diarization_backend_used=diarization_backend_used,
        )
