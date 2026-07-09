"""End-to-end verification of the Phase 4 AI analysis engine.

Seeds a fully-processed SALES call via the REAL Phase 3 speech pipeline
(only the Whisper model-loading call is monkeypatched, exactly like
`test_orchestrator_end_to_end.py`) and then runs `AnalysisOrchestrator`
against it with a controllable fake LLM backend. This proves the whole
scoring -> issue detection -> evidence validation -> insight generation ->
persistence loop, plus retry/failure handling and batch isolation, without
requiring a real Ollama server. A final test swaps in the real `LLMClient`
(with only the Ollama SDK transport mocked) to prove observability logging
also works end-to-end through the batch orchestrator, not just in
`test_llm_client.py`'s narrower unit tests.
"""

from __future__ import annotations

import json

import pytest

from fitnova.analysis.llm_client import LLMClient
from fitnova.analysis.llm_schemas import (
    LLMInsightResponse,
    LLMIssueDetectionResponse,
    LLMIssueItem,
    LLMScoringResponse,
    ScoreDimensionResult,
)
from fitnova.analysis.ollama_client import OllamaClient
from fitnova.analysis.prompt_manager import PromptManager
from fitnova.core.config import Settings
from fitnova.core.constants import (
    CallType,
    ConfidenceLabel,
    IssueType,
    ProcessingStatusEnum,
    Severity,
    SpeakerLabel,
)
from fitnova.db.models import Advisor as AdvisorModel
from fitnova.db.models import (
    CallInsight,
    Issue,
    LLMInferenceLog,
    Organization,
    PipelineBenchmark,
    ProcessingStatus,
    Score,
    Team,
)
from fitnova.ingestion.folder_source import FolderSourceAdapter
from fitnova.pipeline.analysis_orchestrator import AnalysisOrchestrator
from fitnova.pipeline.orchestrator import SpeechPipelineOrchestrator
from fitnova.transcription.whisper_engine import WhisperTranscriber

DIMENSIONS = (
    "needs_discovery",
    "rapport",
    "empathy",
    "listening",
    "product_knowledge",
    "objection_handling",
    "compliance",
    "trial_booking",
    "closing",
)

GUARANTEE_QUOTE = "I can guarantee you will lose ten kilograms this month if you sign up now"


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
            _FakeSegment(6.5, 14.0, GUARANTEE_QUOTE),
            _FakeSegment(14.5, 22.0, "That sounds interesting but I am worried about the cost"),
        ]
        return segments, _FakeInfo()


@pytest.fixture()
def patched_transcriber(monkeypatch):
    monkeypatch.setattr(WhisperTranscriber, "_get_or_load_model", lambda self, size: _FakeModel())


def _seed_advisor(session_factory, external_id="adv-analysis"):
    session = session_factory()
    org = Organization(name="FitNova")
    team = Team(name="Mumbai Pod", organization=org)
    AdvisorModel(name="Asha Rao", team=team, external_id=external_id)
    session.add(org)
    session.commit()
    session.close()


def _seed_processed_call(
    tmp_path, make_tone_wav, session_factory, name, advisor_external_id="adv-analysis", freq=220.0
):
    """Runs the real Phase 3 pipeline (only model loading mocked) to
    produce a genuine transcribed, classified, benchmarked SALES call with
    real TranscriptSegment rows - the realistic starting point for Phase 4."""
    inbox = tmp_path / "inbox" / name.replace(".wav", "")
    inbox.mkdir(parents=True, exist_ok=True)
    audio_path = make_tone_wav(name, duration_s=25.0, amplitude=0.5, freq=freq)
    target = inbox / name
    audio_path.replace(target)
    (inbox / f"{name}.meta.json").write_text(
        json.dumps({"advisor_external_id": advisor_external_id})
    )

    adapter = FolderSourceAdapter(
        inbox_dir=inbox, processed_dir=tmp_path / "processed" / name.replace(".wav", "")
    )
    settings = Settings()
    speech_orchestrator = SpeechPipelineOrchestrator(
        settings=settings, session_factory=session_factory, adapters=[adapter]
    )
    results = speech_orchestrator.run_once()
    assert len(results) == 1 and results[0].outcome == "completed"
    assert results[0].call_type == CallType.SALES.value
    return results[0].call_id


def _dim(score, quote=None, confidence=0.9, reasoning="grounded in the transcript"):
    return ScoreDimensionResult(
        score=score, reasoning=reasoning, evidence_quote=quote, confidence=confidence
    )


def _scoring_response(scores: dict[str, int] | None = None) -> LLMScoringResponse:
    scores = scores or {name: 7 for name in DIMENSIONS}
    return LLMScoringResponse(
        **{name: _dim(scores[name], quote="the transcript shows this") for name in DIMENSIONS}
    )


def _issues_response() -> LLMIssueDetectionResponse:
    return LLMIssueDetectionResponse(
        issues=[
            LLMIssueItem(
                issue_type=IssueType.OVER_PROMISING,
                severity=Severity.CRITICAL,
                speaker=SpeakerLabel.ADVISOR,
                segment_index=1,
                quoted_text=GUARANTEE_QUOTE,
                reason="explicit guarantee of a specific weight-loss outcome",
                confidence=0.9,
            )
        ]
    )


def _insight_response() -> LLMInsightResponse:
    return LLMInsightResponse(
        executive_summary="Advisor opened warmly but made an unsupported outcome guarantee.",
        customer_intent="Interested, but price-sensitive and cautious after the guarantee claim.",
        improvement_suggestions=[
            "Avoid absolute outcome guarantees.",
            "Confirm a trial booking before ending the call.",
        ],
        recommended_coaching="Reinforce compliant, outcome-neutral language during pitches.",
        next_best_action="Follow up within 24 hours with compliant, value-based messaging.",
    )


class _FakeLLMClient:
    """Dispatches canned responses by `response_model`, mirroring the real
    `LLMClient.run_structured` call signature exactly - lets these tests
    exercise the orchestrator's real stage sequencing, evidence
    validation, and persistence without a live Ollama server."""

    def __init__(
        self,
        scoring_response=None,
        issues_response=None,
        insight_response=None,
        fail_stage_once=None,
    ):
        self.scoring_response = scoring_response or _scoring_response()
        self.issues_response = issues_response or _issues_response()
        self.insight_response = insight_response or _insight_response()
        self.fail_stage_once = fail_stage_once
        self._already_failed: set = set()
        self.stage_log: list = []

    def run_structured(self, *, stage, prompt_name, prompt_vars, response_model, call_id, session):
        self.stage_log.append(stage)
        if self.fail_stage_once == stage and stage not in self._already_failed:
            self._already_failed.add(stage)
            raise RuntimeError("simulated transient LLM outage")
        if response_model is LLMScoringResponse:
            return self.scoring_response
        if response_model is LLMIssueDetectionResponse:
            return self.issues_response
        if response_model is LLMInsightResponse:
            return self.insight_response
        raise AssertionError(f"unexpected response_model: {response_model}")


def test_batch_analysis_persists_score_issue_insight_and_benchmark(
    tmp_path, make_tone_wav, session_factory, patched_transcriber
):
    _seed_advisor(session_factory)
    call_id = _seed_processed_call(tmp_path, make_tone_wav, session_factory, name="call.wav")

    fake_llm = _FakeLLMClient()
    orchestrator = AnalysisOrchestrator(
        settings=Settings(), session_factory=session_factory, llm_client=fake_llm
    )

    results = orchestrator.run_batch()

    assert len(results) == 1
    result = results[0]
    assert result.outcome == "completed"
    assert result.call_id == call_id
    assert result.issue_count == 1
    assert result.validated_issue_count == 1
    assert 0.0 <= result.overall_quality <= 10.0

    session = session_factory()
    score = session.query(Score).filter_by(call_id=call_id).one()
    assert 0.0 <= score.overall_quality <= 10.0
    assert set(score.evidence.keys()) == set(DIMENSIONS)
    assert all(score.evidence[d]["confidence_label"] for d in DIMENSIONS)

    issue = session.query(Issue).filter_by(call_id=call_id).one()
    assert issue.issue_type == IssueType.OVER_PROMISING
    assert issue.is_validated is True
    assert issue.segment_id is not None
    assert issue.confidence_label == ConfidenceLabel.HIGH

    insight = session.query(CallInsight).filter_by(call_id=call_id).one()
    assert "guarantee" in insight.executive_summary.lower()
    assert insight.improvement_suggestions

    benchmarks = session.query(PipelineBenchmark).filter_by(call_id=call_id).all()
    # one row from the Phase 3 speech pipeline, one from Phase 4 analysis
    # (PipelineBenchmark is intentionally 1:many with Call - docs Section
    # "pipeline benchmarking").
    assert len(benchmarks) == 2
    analysis_benchmark = max(benchmarks, key=lambda b: b.id)
    assert analysis_benchmark.total_pipeline_time_ms > 0

    status = session.query(ProcessingStatus).filter_by(call_id=call_id).one()
    assert status.status == ProcessingStatusEnum.COMPLETED
    session.close()


def test_second_batch_run_skips_already_analyzed_call(
    tmp_path, make_tone_wav, session_factory, patched_transcriber
):
    _seed_advisor(session_factory)
    _seed_processed_call(tmp_path, make_tone_wav, session_factory, name="call.wav")

    orchestrator = AnalysisOrchestrator(
        settings=Settings(), session_factory=session_factory, llm_client=_FakeLLMClient()
    )
    first_results = orchestrator.run_batch()
    assert first_results[0].outcome == "completed"

    second_results = orchestrator.run_batch()
    assert second_results == []


def test_non_sales_call_is_skipped_and_never_scored(
    tmp_path, make_tone_wav, session_factory, patched_transcriber
):
    # No advisor seeded + no sidecar metadata -> PENDING_METADATA, not SALES.
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    audio = make_tone_wav("unknown.wav", duration_s=25.0, amplitude=0.5)
    (inbox / "unknown.wav").write_bytes(audio.read_bytes())
    adapter = FolderSourceAdapter(inbox_dir=inbox, processed_dir=tmp_path / "processed")
    speech_orchestrator = SpeechPipelineOrchestrator(
        settings=Settings(), session_factory=session_factory, adapters=[adapter]
    )
    speech_results = speech_orchestrator.run_once()
    assert speech_results[0].call_type == CallType.PENDING_METADATA.value

    orchestrator = AnalysisOrchestrator(
        settings=Settings(), session_factory=session_factory, llm_client=_FakeLLMClient()
    )
    results = orchestrator.run_batch()

    assert results == []  # PENDING_METADATA calls are never selected for analysis


def test_failed_analysis_retries_and_then_succeeds(
    tmp_path, make_tone_wav, session_factory, patched_transcriber
):
    _seed_advisor(session_factory)
    call_id = _seed_processed_call(tmp_path, make_tone_wav, session_factory, name="flaky.wav")

    from fitnova.core.constants import LLMStage

    fake_llm = _FakeLLMClient(fail_stage_once=LLMStage.SCORING)
    orchestrator = AnalysisOrchestrator(
        settings=Settings(), session_factory=session_factory, llm_client=fake_llm
    )

    first_results = orchestrator.run_batch()
    assert first_results[0].outcome == "failed"

    session = session_factory()
    status = session.query(ProcessingStatus).filter_by(call_id=call_id).one()
    assert status.status == ProcessingStatusEnum.FAILED
    assert "simulated transient" in status.last_error
    session.close()

    second_results = orchestrator.run_batch()
    assert second_results[0].outcome == "completed"

    session = session_factory()
    status = session.query(ProcessingStatus).filter_by(call_id=call_id).one()
    assert status.status == ProcessingStatusEnum.COMPLETED
    assert status.retry_count == 1
    session.close()


def test_retry_exhaustion_stops_reprocessing(
    tmp_path, make_tone_wav, session_factory, patched_transcriber
):
    _seed_advisor(session_factory)
    call_id = _seed_processed_call(
        tmp_path, make_tone_wav, session_factory, name="always_broken.wav"
    )

    class _AlwaysFailingLLMClient:
        def run_structured(self, **kwargs):
            raise RuntimeError("permanently broken")

    settings = Settings(max_processing_retries=2)
    orchestrator = AnalysisOrchestrator(
        settings=settings, session_factory=session_factory, llm_client=_AlwaysFailingLLMClient()
    )

    outcomes = []
    for _ in range(5):
        results = orchestrator.run_batch()
        if not results:
            break
        outcomes.append(results[0].outcome)

    assert outcomes[-1] == "skipped_exhausted"
    assert outcomes.count("failed") >= 1

    session = session_factory()
    status = session.query(ProcessingStatus).filter_by(call_id=call_id).one()
    assert status.status == ProcessingStatusEnum.FAILED
    assert status.retry_count >= settings.max_processing_retries
    session.close()


def test_batch_isolates_failures_across_multiple_calls(
    tmp_path, make_tone_wav, session_factory, patched_transcriber
):
    _seed_advisor(session_factory)
    good_call_id = _seed_processed_call(
        tmp_path, make_tone_wav, session_factory, name="good.wav", freq=220.0
    )
    # Different frequency -> different audio bytes -> different content_hash,
    # so this isn't skipped as a duplicate of "good.wav".
    bad_call_id = _seed_processed_call(
        tmp_path, make_tone_wav, session_factory, name="bad.wav", freq=330.0
    )

    good_llm = _FakeLLMClient()

    class _SelectivelyFailingLLMClient:
        """Fails every call for `bad_call_id`, succeeds for everything else."""

        def run_structured(self, *, call_id, response_model, **kwargs):
            if call_id == bad_call_id:
                raise RuntimeError("this call's transcript is corrupt")
            return good_llm.run_structured(call_id=call_id, response_model=response_model, **kwargs)

    orchestrator = AnalysisOrchestrator(
        settings=Settings(),
        session_factory=session_factory,
        llm_client=_SelectivelyFailingLLMClient(),
    )

    results = orchestrator.run_batch()
    outcomes_by_call = {r.call_id: r.outcome for r in results}

    assert outcomes_by_call[good_call_id] == "completed"
    assert outcomes_by_call[bad_call_id] == "failed"

    session = session_factory()
    assert session.query(Score).filter_by(call_id=good_call_id).count() == 1
    assert session.query(Score).filter_by(call_id=bad_call_id).count() == 0
    session.close()


def test_real_llm_client_records_observability_logs_through_batch(
    tmp_path, make_tone_wav, session_factory, patched_transcriber, monkeypatch, project_root
):
    """Swaps in the real `LLMClient` (only the Ollama SDK transport is
    mocked) to prove `llm_inference_logs` rows are written end-to-end
    through the batch orchestrator, not just in the narrower
    `test_llm_client.py` unit tests."""
    _seed_advisor(session_factory)
    call_id = _seed_processed_call(tmp_path, make_tone_wav, session_factory, name="observed.wav")

    scoring_json = LLMScoringResponse(
        **{name: _dim(7, quote="the transcript shows this") for name in DIMENSIONS}
    ).model_dump_json()
    issues_json = _issues_response().model_dump_json()
    insight_json = _insight_response().model_dump_json()

    class _FakeSDKClient:
        def __init__(self):
            self._responses = [scoring_json, issues_json, insight_json]

        def generate(self, model, prompt, format, options):
            return {"response": self._responses.pop(0)}

        def show(self, model):
            return {"digest": "sha256:test-model-digest"}

    settings = Settings()
    prompt_manager = PromptManager(settings.resolved_prompts_dir())
    ollama_client = OllamaClient(settings)
    fake_sdk_client = _FakeSDKClient()
    # Bind to the SAME fake client instance on every call - `_get_client`
    # normally caches on `self._client`, but that caching is bypassed
    # entirely once the method itself is monkeypatched, so a fresh fake
    # per call would reset `_responses` and desync the stage sequence.
    monkeypatch.setattr(ollama_client, "_get_client", lambda: fake_sdk_client)
    real_llm_client = LLMClient(settings, prompt_manager, ollama_client=ollama_client)

    orchestrator = AnalysisOrchestrator(
        settings=settings, session_factory=session_factory, llm_client=real_llm_client
    )
    results = orchestrator.run_batch()

    assert results[0].outcome == "completed"

    session = session_factory()
    logs = (
        session.query(LLMInferenceLog).filter_by(call_id=call_id).order_by(LLMInferenceLog.id).all()
    )
    assert len(logs) == 3  # scoring, issue_detection, insight_generation
    assert all(log.success for log in logs)
    assert all(log.model_version == "sha256:test-model-digest" for log in logs)
    assert {log.prompt_version for log in logs} == {"v1.0.0"}

    benchmark = (
        session.query(PipelineBenchmark)
        .filter_by(call_id=call_id)
        .order_by(PipelineBenchmark.id.desc())
        .first()
    )
    assert benchmark.llm_time_ms is not None and benchmark.llm_time_ms > 0
    session.close()
