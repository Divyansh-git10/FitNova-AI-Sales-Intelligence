"""Tests for `BenchmarkRecorder` — per-stage timing and Real Time Factor
(RTF = total_pipeline_time_seconds / audio_duration_seconds)."""

from __future__ import annotations

import time

from fitnova.pipeline.benchmarking import BenchmarkRecorder


def test_stage_context_manager_records_duration():
    recorder = BenchmarkRecorder()
    with recorder.stage("transcription"):
        time.sleep(0.01)

    duration = recorder.duration_ms("transcription")
    assert duration is not None
    assert duration >= 10.0  # at least the sleep duration, in ms


def test_record_manual_duration():
    recorder = BenchmarkRecorder()
    recorder.record("transcription", 1234.5)
    assert recorder.duration_ms("transcription") == 1234.5


def test_duration_ms_returns_none_for_unrecorded_stage():
    recorder = BenchmarkRecorder()
    assert recorder.duration_ms("never_ran") is None


def test_build_computes_real_time_factor():
    recorder = BenchmarkRecorder()
    recorder.record("transcription", 2000.0)  # 2 seconds of processing
    time.sleep(0.01)

    benchmark = recorder.build(
        call_id=1,
        audio_duration_seconds=10.0,  # a 10-second call
        whisper_model_used="small",
        diarization_backend_used="fallback",
    )

    assert benchmark.transcription_time_ms == 2000.0
    assert benchmark.whisper_model_used == "small"
    assert benchmark.diarization_backend_used == "fallback"
    assert benchmark.total_pipeline_time_ms > 0
    assert benchmark.real_time_factor is not None
    # total pipeline time is tiny (just the sleep) relative to a 10s call, so RTF << 1
    assert 0 < benchmark.real_time_factor < 1.0


def test_build_handles_missing_audio_duration():
    recorder = BenchmarkRecorder()
    benchmark = recorder.build(
        call_id=1,
        audio_duration_seconds=None,
        whisper_model_used=None,
        diarization_backend_used=None,
    )
    assert benchmark.real_time_factor is None


def test_build_handles_zero_audio_duration():
    recorder = BenchmarkRecorder()
    benchmark = recorder.build(
        call_id=1,
        audio_duration_seconds=0.0,
        whisper_model_used=None,
        diarization_backend_used=None,
    )
    assert benchmark.real_time_factor is None
