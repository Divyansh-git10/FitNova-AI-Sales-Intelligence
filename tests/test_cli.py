"""Tests for the Typer CLI: every command runs against the real
`bootstrap_app()` path (matching how a user actually invokes `fitnova`),
so each test points `DATABASE_URL` at a private on-disk SQLite file under
`tmp_path` — never `:memory:` (a fresh CLI process per command would lose
an in-memory DB anyway) and never the real `data/fitnova.db`.
"""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

runner = CliRunner()


@pytest.fixture()
def cli_env(tmp_path, monkeypatch):
    """Points the CLI's bootstrap at an isolated on-disk SQLite DB and
    resets `fitnova`'s process-wide caches (`get_settings` lru_cache) so
    each test gets its own fresh database instead of reusing whatever a
    previous test already bootstrapped in this process."""
    db_path = tmp_path / "fitnova_cli_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("AUDIO_INBOX_DIR", str(tmp_path / "inbox"))
    monkeypatch.setenv("PROCESSED_AUDIO_DIR", str(tmp_path / "processed"))
    monkeypatch.setenv("DATA_DIR", str(tmp_path / "data"))

    from fitnova.core.config import get_settings

    get_settings.cache_clear()
    yield tmp_path
    get_settings.cache_clear()


def _invoke(app, args):
    result = runner.invoke(app, args)
    if result.exception and not isinstance(result.exception, SystemExit):
        import traceback

        traceback.print_exception(
            type(result.exception), result.exception, result.exception.__traceback__
        )
    return result


def test_status_on_empty_db_reports_empty_queue(cli_env):
    from fitnova.cli.main import app

    result = _invoke(app, ["status"])
    assert result.exit_code == 0
    assert "Queue is empty" in result.output


def test_ingest_finds_nothing_when_inbox_empty(cli_env):
    from fitnova.cli.main import app

    result = _invoke(app, ["ingest"])
    assert result.exit_code == 0
    assert "No new recordings found" in result.output


def test_analyze_finds_nothing_pending(cli_env):
    from fitnova.cli.main import app

    result = _invoke(app, ["analyze"])
    assert result.exit_code == 0
    assert "No calls pending analysis" in result.output


def test_benchmark_on_empty_db(cli_env):
    from fitnova.cli.main import app

    result = _invoke(app, ["benchmark"])
    assert result.exit_code == 0
    assert "No pipeline runs have been benchmarked yet" in result.output


def test_export_calls_csv_empty_db(cli_env):
    from fitnova.cli.main import app

    output_path = cli_env / "calls.csv"
    result = _invoke(app, ["export", "calls-csv", "--output", str(output_path)])
    assert result.exit_code == 0
    assert output_path.exists()
    content = output_path.read_text()
    assert content.startswith("id,advisor_name")


def test_export_unknown_kind_fails(cli_env):
    from fitnova.cli.main import app

    result = _invoke(app, ["export", "not-a-real-kind", "--output", str(cli_env / "x.csv")])
    assert result.exit_code == 1
    assert "Unknown export kind" in result.output


def test_export_call_pdf_requires_call_id(cli_env):
    from fitnova.cli.main import app

    result = _invoke(app, ["export", "call-pdf", "--output", str(cli_env / "x.pdf")])
    assert result.exit_code == 1
    assert "--call-id is required" in result.output


def test_export_scorecard_pdf_requires_advisor_id(cli_env):
    from fitnova.cli.main import app

    result = _invoke(app, ["export", "scorecard-pdf", "--output", str(cli_env / "x.pdf")])
    assert result.exit_code == 1
    assert "--advisor-id is required" in result.output


def test_export_call_pdf_unknown_call_fails(cli_env):
    from fitnova.cli.main import app

    result = _invoke(
        app, ["export", "call-pdf", "--call-id", "999999", "--output", str(cli_env / "x.pdf")]
    )
    assert result.exit_code == 1
    assert "not found" in result.output


def test_doctor_reports_all_checks(cli_env):
    from fitnova.cli.main import app

    result = _invoke(app, ["doctor"])
    # Ollama being unreachable in this sandbox is expected and non-fatal;
    # every other check (config, directories, DB, prompts) must pass.
    assert "Database connectivity" in result.output
    assert "weights.yaml valid" in result.output
    assert "issue_rules.yaml valid" in result.output
    assert "Prompt templates load" in result.output


def test_doctor_exit_code_zero_when_only_ollama_unreachable(cli_env):
    from fitnova.cli.main import app

    result = _invoke(app, ["doctor"])
    # No real Ollama server is running in this sandbox -> Ollama check
    # fails, but that alone must not fail the whole command.
    assert result.exit_code == 0
    assert "All checks passed" in result.output


def test_help_lists_all_seven_commands(cli_env):
    from fitnova.cli.main import app

    result = _invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ["ingest", "analyze", "status", "dashboard", "export", "benchmark", "doctor"]:
        assert command in result.output


def test_full_pipeline_via_cli_ingest_then_analyze_then_status(cli_env, monkeypatch, make_tone_wav):
    """End-to-end through the CLI itself: ingest a synthetic recording
    (Whisper model loading mocked), analyze it with a mocked Ollama
    transport, then confirm `status`/`benchmark` show it completed. Proves
    the CLI's own wiring - not just the underlying orchestrators, already
    covered in test_orchestrator_end_to_end.py / test_analysis_batch_end_
    to_end.py - actually works when invoked the way a user really would."""
    import json

    from fitnova.cli.main import app

    # A real synthetic sine-wave WAV (not hand-rolled bytes) - matches the
    # fixture every Phase 3/4 speech-pipeline test uses, since silence/VAD
    # detection is picky about what counts as "speech-like" audio.
    inbox = cli_env / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    tone_path = make_tone_wav("call.wav", duration_s=25.0, amplitude=0.5)
    audio_path = inbox / "call.wav"
    audio_path.write_bytes(tone_path.read_bytes())
    (inbox / "call.wav.meta.json").write_text(json.dumps({"advisor_external_id": "adv-cli-e2e"}))

    from fitnova.core.config import get_settings
    from fitnova.db.models import Advisor, Organization, Team

    settings = get_settings()
    from fitnova.db.init_db import init_db
    from fitnova.db.session import build_engine, build_session_factory

    engine = build_engine(settings)
    init_db(engine)
    session_factory = build_session_factory(engine)
    session = session_factory()
    org = Organization(name="FitNova")
    team = Team(name="Pod", organization=org)
    advisor = Advisor(name="Asha Rao", team=team, external_id="adv-cli-e2e")
    session.add_all([org, team, advisor])
    session.commit()
    session.close()

    class _FakeInfo:
        language = "en"
        language_probability = 0.95

    class _FakeSegment:
        def __init__(self, start, end, text):
            self.start, self.end, self.text, self.avg_logprob = start, end, text, -0.1

    class _FakeModel:
        def transcribe(self, path, language=None, vad_filter=False):
            return (
                [
                    _FakeSegment(0.0, 6.0, "Hi this is Asha calling from FitNova"),
                    _FakeSegment(6.5, 14.0, "I wanted to understand your fitness goals"),
                    _FakeSegment(14.5, 22.0, "Based on that here is our coaching plan"),
                ],
                _FakeInfo(),
            )

    from fitnova.transcription.whisper_engine import WhisperTranscriber

    monkeypatch.setattr(WhisperTranscriber, "_get_or_load_model", lambda self, size: _FakeModel())

    ingest_result = _invoke(app, ["ingest"])
    assert ingest_result.exit_code == 0

    scoring_json = (
        '{"needs_discovery":{"score":7,"reasoning":"ok","evidence_quote":"q","confidence":0.9},'
        '"rapport":{"score":7,"reasoning":"ok","evidence_quote":"q","confidence":0.9},'
        '"empathy":{"score":7,"reasoning":"ok","evidence_quote":"q","confidence":0.9},'
        '"listening":{"score":7,"reasoning":"ok","evidence_quote":"q","confidence":0.9},'
        '"product_knowledge":{"score":7,"reasoning":"ok","evidence_quote":"q","confidence":0.9},'
        '"objection_handling":{"score":7,"reasoning":"ok","evidence_quote":"q","confidence":0.9},'
        '"compliance":{"score":8,"reasoning":"ok","evidence_quote":"q","confidence":0.9},'
        '"trial_booking":{"score":6,"reasoning":"ok","evidence_quote":"q","confidence":0.9},'
        '"closing":{"score":6,"reasoning":"ok","evidence_quote":"q","confidence":0.9}}'
    )
    issues_json = '{"issues": []}'
    insight_json = (
        '{"executive_summary": "Advisor covered goals well.", "customer_intent": "Interested.", '
        '"improvement_suggestions": ["Confirm a trial slot"], '
        '"recommended_coaching": "Practice closes.", '
        '"next_best_action": "Follow up in 24h."}'
    )

    class _FakeOllamaSDKClient:
        def __init__(self):
            self._responses = [scoring_json, issues_json, insight_json]

        def generate(self, model, prompt, format, options):
            return {"response": self._responses.pop(0)}

        def show(self, model):
            return {"digest": "sha256:cli-e2e-test"}

    from fitnova.analysis.ollama_client import OllamaClient

    # Patch the CLASS method with a lambda returning ONE shared fake
    # instance - not a fresh `_FakeOllamaSDKClient()` per call, which
    # would reset `_responses` and desync the scoring/issues/insight
    # sequence (the same pitfall documented in
    # test_analysis_batch_end_to_end.py).
    shared_fake_sdk_client = _FakeOllamaSDKClient()
    monkeypatch.setattr(OllamaClient, "_get_client", lambda self: shared_fake_sdk_client)

    analyze_result = _invoke(app, ["analyze"])
    assert analyze_result.exit_code == 0
    assert "completed" in analyze_result.output.lower()

    status_result = _invoke(app, ["status"])
    assert status_result.exit_code == 0
    assert "COMPLETED" in status_result.output or "completed" in status_result.output.lower()

    benchmark_result = _invoke(app, ["benchmark"])
    assert benchmark_result.exit_code == 0
    assert "pipeline run(s) benchmarked" in benchmark_result.output
