"""Tests for `LLMClient.run_structured`: JSON-parse + Pydantic validation,
retry-with-feedback, exhaustion, and per-attempt observability logging to
`llm_inference_logs` (docs Phase 4 addendums #1 "prompt versioning tracked
in the database" and #2 "strict structured LLM output")."""

from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from fitnova.analysis.llm_client import LLMClient, LLMResponseValidationError
from fitnova.analysis.prompt_manager import PromptManager
from fitnova.core.config import Settings
from fitnova.core.constants import LLMStage, SourceSystem
from fitnova.db.models import Advisor, Call, LLMInferenceLog, Organization, Team


class Greeting(BaseModel):
    model_config = ConfigDict(extra="forbid")
    greeting: str


class _FakeOllamaClient:
    """Dispenses canned `generate_json` results in order; each item is
    either a response string or an Exception instance to raise."""

    def __init__(self, responses, model_version="sha256:test"):
        self.responses = list(responses)
        self._model_version = model_version
        self.calls: list[str] = []

    def generate_json(self, prompt, temperature=None):
        self.calls.append(prompt)
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def get_model_version(self):
        return self._model_version


@pytest.fixture()
def prompt_manager(tmp_path):
    (tmp_path / "greet_v1.txt").write_text(
        'VERSION: v9.9.9\n---\nSay hello to $name.\n{"greeting": "..."}\n'
    )
    return PromptManager(tmp_path)


def _make_call(session) -> Call:
    org = Organization(name="FitNova")
    team = Team(name="Pod A", organization=org)
    advisor = Advisor(name="Asha Rao", team=team, external_id="adv-llm-test")
    call = Call(advisor=advisor, source_system=SourceSystem.FOLDER, content_hash="hash-llm-test")
    session.add(call)
    session.flush()
    return call


def test_run_structured_success_on_first_attempt(db_session, settings, prompt_manager):
    call = _make_call(db_session)
    fake_ollama = _FakeOllamaClient(responses=['{"greeting": "hi there"}'])
    client = LLMClient(settings, prompt_manager, ollama_client=fake_ollama)

    result = client.run_structured(
        stage=LLMStage.SCORING,
        prompt_name="greet_v1",
        prompt_vars={"name": "Asha"},
        response_model=Greeting,
        call_id=call.id,
        session=db_session,
    )
    db_session.commit()

    assert result.greeting == "hi there"
    logs = db_session.query(LLMInferenceLog).filter_by(call_id=call.id).all()
    assert len(logs) == 1
    assert logs[0].success is True
    assert logs[0].prompt_version == "v9.9.9"
    assert logs[0].retry_count == 0
    assert logs[0].model_name == settings.ollama_model
    assert logs[0].model_version == "sha256:test"
    assert logs[0].stage == LLMStage.SCORING


def test_run_structured_retries_after_invalid_json_then_succeeds(
    db_session, settings, prompt_manager
):
    call = _make_call(db_session)
    fake_ollama = _FakeOllamaClient(responses=["this is not json", '{"greeting": "hi"}'])
    client = LLMClient(settings, prompt_manager, ollama_client=fake_ollama)

    result = client.run_structured(
        stage=LLMStage.ISSUE_DETECTION,
        prompt_name="greet_v1",
        prompt_vars={"name": "Asha"},
        response_model=Greeting,
        call_id=call.id,
        session=db_session,
    )
    db_session.commit()

    assert result.greeting == "hi"
    logs = (
        db_session.query(LLMInferenceLog)
        .filter_by(call_id=call.id)
        .order_by(LLMInferenceLog.id)
        .all()
    )
    assert len(logs) == 2
    assert logs[0].success is False
    assert "not valid JSON" in logs[0].error_message
    assert logs[1].success is True
    assert logs[1].retry_count == 1


def test_run_structured_retries_after_schema_violation_then_succeeds(
    db_session, settings, prompt_manager
):
    call = _make_call(db_session)
    fake_ollama = _FakeOllamaClient(responses=['{"wrong_field": 1}', '{"greeting": "hi"}'])
    client = LLMClient(settings, prompt_manager, ollama_client=fake_ollama)

    result = client.run_structured(
        stage=LLMStage.SCORING,
        prompt_name="greet_v1",
        prompt_vars={"name": "Asha"},
        response_model=Greeting,
        call_id=call.id,
        session=db_session,
    )

    assert result.greeting == "hi"
    logs = (
        db_session.query(LLMInferenceLog)
        .filter_by(call_id=call.id)
        .order_by(LLMInferenceLog.id)
        .all()
    )
    assert logs[0].success is False
    assert "did not match the required schema" in logs[0].error_message


def test_feedback_prompt_includes_previous_error(db_session, settings, prompt_manager):
    call = _make_call(db_session)
    fake_ollama = _FakeOllamaClient(responses=["bad json", '{"greeting": "hi"}'])
    client = LLMClient(settings, prompt_manager, ollama_client=fake_ollama)

    client.run_structured(
        stage=LLMStage.SCORING,
        prompt_name="greet_v1",
        prompt_vars={"name": "Asha"},
        response_model=Greeting,
        call_id=call.id,
        session=db_session,
    )

    assert len(fake_ollama.calls) == 2
    assert "IMPORTANT" in fake_ollama.calls[1]
    assert "rejected" in fake_ollama.calls[1]


def test_run_structured_raises_after_exhausting_all_retries(db_session, prompt_manager):
    call = _make_call(db_session)
    settings = Settings(llm_max_retries=2)
    fake_ollama = _FakeOllamaClient(responses=["still bad", "still bad again"])
    client = LLMClient(settings, prompt_manager, ollama_client=fake_ollama)

    with pytest.raises(LLMResponseValidationError) as exc_info:
        client.run_structured(
            stage=LLMStage.SCORING,
            prompt_name="greet_v1",
            prompt_vars={"name": "Asha"},
            response_model=Greeting,
            call_id=call.id,
            session=db_session,
        )

    assert exc_info.value.attempts == 2
    logs = db_session.query(LLMInferenceLog).filter_by(call_id=call.id).all()
    assert len(logs) == 2
    assert all(not log.success for log in logs)
