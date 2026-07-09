"""End-to-end verification of the Phase 3 speech pipeline orchestrator.

This is the test that proves the whole loop actually works: a file dropped
in the inbox comes out the other side as a persisted, classified,
benchmarked Call with a redacted transcript — the "working prototype"
requirement from the assignment, exercised without needing network access
or a real Whisper model download (the transcriber's model loading is
monkeypatched; everything else — audio decoding, VAD-based diarization,
normalization, PII redaction, classification, DB writes, idempotency,
retries — runs for real).
"""

from __future__ import annotations

import json

import pytest

import fitnova.pipeline.orchestrator as orchestrator_module
from fitnova.core.config import Settings
from fitnova.core.constants import CallType, ProcessingStatusEnum
from fitnova.db.models import Advisor as AdvisorModel
from fitnova.db.models import (
    AudioMetadata,
    Call,
    CallMetric,
    Organization,
    PipelineBenchmark,
    ProcessingStatus,
    Team,
    Transcript,
    TranscriptSegment,
)
from fitnova.ingestion.folder_source import FolderSourceAdapter
from fitnova.pipeline.orchestrator import SpeechPipelineOrchestrator
from fitnova.transcription.whisper_engine import WhisperTranscriber


class _FakeInfo:
    language = "en"
    language_probability = 0.97


class _FakeSegment:
    def __init__(self, start, end, text, avg_logprob=-0.1):
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = avg_logprob


class _FakeModel:
    def transcribe(self, path, language=None, vad_filter=False):
        segments = [
            _FakeSegment(0.0, 6.0, "Hi this is Asha calling from FitNova, how are you today"),
            _FakeSegment(
                6.5, 14.0, "I wanted to understand your fitness goals and current routine"
            ),
            _FakeSegment(
                14.5, 22.0, "Great, based on that I would recommend our guided coaching plan"
            ),
        ]
        return segments, _FakeInfo()


@pytest.fixture()
def patched_transcriber(monkeypatch):
    monkeypatch.setattr(WhisperTranscriber, "_get_or_load_model", lambda self, size: _FakeModel())


@pytest.fixture()
def seeded_advisor(session_factory):
    session = session_factory()
    org = Organization(name="FitNova")
    team = Team(name="Mumbai Pod", organization=org)
    advisor = AdvisorModel(name="Asha Rao", team=team, external_id="adv-e2e")
    session.add(org)
    session.commit()
    advisor_id = advisor.id
    session.close()
    return advisor_id


def _make_call_wav(
    tmp_path, make_tone_wav, name="call.wav", advisor_external_id="adv-e2e", duration_s=25.0
):
    inbox = tmp_path / "inbox"
    inbox.mkdir(exist_ok=True)
    audio_path = make_tone_wav(name, duration_s=duration_s, amplitude=0.5)
    # make_tone_wav writes into tmp_path (pytest tmp_path root); move it under inbox
    target = inbox / name
    audio_path.replace(target)
    sidecar = inbox / f"{name}.meta.json"
    sidecar.write_text(json.dumps({"advisor_external_id": advisor_external_id}))
    return inbox, target


def test_full_pipeline_processes_a_call_end_to_end(
    tmp_path, make_tone_wav, session_factory, seeded_advisor, patched_transcriber
):
    inbox, audio_path = _make_call_wav(tmp_path, make_tone_wav)
    processed = tmp_path / "processed"
    adapter = FolderSourceAdapter(inbox_dir=inbox, processed_dir=processed)

    settings = Settings()
    orchestrator = SpeechPipelineOrchestrator(
        settings=settings, session_factory=session_factory, adapters=[adapter]
    )

    results = orchestrator.run_once()

    assert len(results) == 1
    result = results[0]
    assert result.outcome == "completed"
    assert result.call_type == CallType.SALES.value

    session = session_factory()
    call = session.get(Call, result.call_id)
    assert call is not None
    assert call.call_type == CallType.SALES
    assert call.advisor_id == seeded_advisor
    assert call.duration_seconds is not None and call.duration_seconds > 20

    audio_meta = session.query(AudioMetadata).filter_by(call_id=call.id).one()
    assert audio_meta.file_format == "wav"
    assert audio_meta.channels == 1

    transcript = session.query(Transcript).filter_by(call_id=call.id).one()
    assert transcript.word_count > 0
    assert "FitNova" in transcript.raw_text

    segments = session.query(TranscriptSegment).filter_by(transcript_id=transcript.id).all()
    assert len(segments) == 3
    assert all(seg.end_time > seg.start_time for seg in segments)

    metric = session.query(CallMetric).filter_by(call_id=call.id).one()
    assert metric is not None

    benchmark = session.query(PipelineBenchmark).filter_by(call_id=call.id).one()
    assert benchmark.total_pipeline_time_ms > 0
    assert benchmark.transcription_time_ms is not None
    assert benchmark.whisper_model_used is not None
    assert benchmark.diarization_backend_used == "fallback"
    assert benchmark.audio_duration_seconds > 20

    status = session.query(ProcessingStatus).filter_by(call_id=call.id).one()
    assert status.status == ProcessingStatusEnum.COMPLETED
    assert status.retry_count == 0

    # file claimed: moved out of the inbox
    assert not audio_path.exists()
    assert (processed / audio_path.name).exists()
    session.close()


def test_second_run_finds_nothing_new(
    tmp_path, make_tone_wav, session_factory, seeded_advisor, patched_transcriber
):
    inbox, _ = _make_call_wav(tmp_path, make_tone_wav)
    adapter = FolderSourceAdapter(inbox_dir=inbox, processed_dir=tmp_path / "processed")
    orchestrator = SpeechPipelineOrchestrator(
        settings=Settings(), session_factory=session_factory, adapters=[adapter]
    )

    orchestrator.run_once()
    second_results = orchestrator.run_once()

    assert second_results == []


def test_duplicate_content_is_skipped_within_same_batch(
    tmp_path, make_tone_wav, session_factory, seeded_advisor, patched_transcriber
):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    original = make_tone_wav("original.wav", duration_s=25.0, amplitude=0.5)
    # byte-identical copy under a different filename -> same content_hash
    duplicate_bytes = original.read_bytes()
    (inbox / "original.wav").write_bytes(duplicate_bytes)
    (inbox / "original.wav.meta.json").write_text(json.dumps({"advisor_external_id": "adv-e2e"}))
    (inbox / "duplicate.wav").write_bytes(duplicate_bytes)
    (inbox / "duplicate.wav.meta.json").write_text(json.dumps({"advisor_external_id": "adv-e2e"}))

    adapter = FolderSourceAdapter(inbox_dir=inbox, processed_dir=tmp_path / "processed")
    orchestrator = SpeechPipelineOrchestrator(
        settings=Settings(), session_factory=session_factory, adapters=[adapter]
    )

    results = orchestrator.run_once()

    outcomes = sorted(r.outcome for r in results)
    assert outcomes == ["completed", "skipped_duplicate"]
    call_ids = {r.call_id for r in results}
    assert len(call_ids) == 1  # both records resolved to the same Call row


def test_advisor_unresolved_produces_pending_metadata(
    tmp_path, make_tone_wav, session_factory, patched_transcriber
):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    audio = make_tone_wav("unknown_advisor.wav", duration_s=25.0, amplitude=0.5)
    (inbox / "unknown_advisor.wav").write_bytes(audio.read_bytes())

    adapter = FolderSourceAdapter(inbox_dir=inbox, processed_dir=tmp_path / "processed")
    orchestrator = SpeechPipelineOrchestrator(
        settings=Settings(), session_factory=session_factory, adapters=[adapter]
    )

    results = orchestrator.run_once()

    assert results[0].outcome == "completed"
    assert results[0].call_type == CallType.PENDING_METADATA.value

    session = session_factory()
    call = session.get(Call, results[0].call_id)
    assert call.advisor_id is None
    session.close()


def test_failed_call_retries_and_then_succeeds(
    tmp_path, make_tone_wav, session_factory, seeded_advisor, patched_transcriber, monkeypatch
):
    inbox, audio_path = _make_call_wav(tmp_path, make_tone_wav, name="flaky.wav")
    adapter = FolderSourceAdapter(inbox_dir=inbox, processed_dir=tmp_path / "processed")
    settings = Settings()
    orchestrator = SpeechPipelineOrchestrator(
        settings=settings, session_factory=session_factory, adapters=[adapter]
    )

    call_state = {"attempts": 0}
    real_classify_call = orchestrator_module.classify_call

    def flaky_classify_call(*args, **kwargs):
        call_state["attempts"] += 1
        if call_state["attempts"] == 1:
            raise RuntimeError("simulated transient classification failure")
        return real_classify_call(*args, **kwargs)

    monkeypatch.setattr(orchestrator_module, "classify_call", flaky_classify_call)

    first_results = orchestrator.run_once()
    assert first_results[0].outcome == "failed"

    session = session_factory()
    status = (
        session.query(ProcessingStatus).filter_by(content_hash=first_results[0].content_hash).one()
    )
    assert status.status == ProcessingStatusEnum.FAILED
    assert status.retry_count == 0
    assert "simulated transient" in status.last_error
    session.close()

    # file was NOT claimed on failure — still sits in the inbox for retry
    assert audio_path.exists()

    second_results = orchestrator.run_once()
    assert second_results[0].outcome == "completed"

    session = session_factory()
    status = (
        session.query(ProcessingStatus).filter_by(content_hash=first_results[0].content_hash).one()
    )
    assert status.status == ProcessingStatusEnum.COMPLETED
    assert status.retry_count == 1
    session.close()


def test_retry_exhaustion_stops_reprocessing(
    tmp_path, make_tone_wav, session_factory, seeded_advisor, patched_transcriber, monkeypatch
):
    inbox, audio_path = _make_call_wav(tmp_path, make_tone_wav, name="always_broken.wav")
    adapter = FolderSourceAdapter(inbox_dir=inbox, processed_dir=tmp_path / "processed")
    settings = Settings(max_processing_retries=2)
    orchestrator = SpeechPipelineOrchestrator(
        settings=settings, session_factory=session_factory, adapters=[adapter]
    )

    def always_fail(*args, **kwargs):
        raise RuntimeError("permanently broken")

    monkeypatch.setattr(orchestrator_module, "classify_call", always_fail)

    outcomes = []
    for _ in range(5):
        results = orchestrator.run_once()
        if not results:
            break
        outcomes.append(results[0].outcome)

    assert outcomes[-1] == "skipped_exhausted"
    assert "failed" in outcomes
    # eventually claimed (moved) so it stops being rescanned forever
    assert not audio_path.exists()
