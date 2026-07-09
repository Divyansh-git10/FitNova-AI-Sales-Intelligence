"""Tests for the Ollama transport wrapper: retry-then-wrap-as-
OllamaConnectionError, and best-effort (never-raising) model version
lookup with per-process caching."""

from __future__ import annotations

import pytest

from fitnova.analysis.ollama_client import OllamaClient, OllamaConnectionError


class _FakeSDKClientAlwaysWorks:
    def __init__(self):
        self.generate_calls = []

    def generate(self, model, prompt, format, options):
        self.generate_calls.append(
            {"model": model, "prompt": prompt, "format": format, "options": options}
        )
        return {"response": '{"ok": true}'}

    def show(self, model):
        return {"digest": "sha256:abc123"}


class _FakeSDKClientAlwaysFails:
    def generate(self, **kwargs):
        raise ConnectionError("no server listening")

    def show(self, model):
        raise ConnectionError("no server listening")


def test_generate_json_returns_raw_response_text(monkeypatch, settings):
    client = OllamaClient(settings)
    fake = _FakeSDKClientAlwaysWorks()
    monkeypatch.setattr(client, "_get_client", lambda: fake)

    result = client.generate_json("say hi", temperature=0.2)

    assert result == '{"ok": true}'
    assert fake.generate_calls[0]["format"] == "json"
    assert fake.generate_calls[0]["options"]["temperature"] == 0.2


def test_generate_json_uses_settings_temperature_when_none(monkeypatch, settings):
    client = OllamaClient(settings)
    fake = _FakeSDKClientAlwaysWorks()
    monkeypatch.setattr(client, "_get_client", lambda: fake)

    client.generate_json("say hi")

    assert fake.generate_calls[0]["options"]["temperature"] == settings.llm_temperature


def test_generate_json_wraps_persistent_failure_as_connection_error(monkeypatch, settings):
    client = OllamaClient(settings)
    monkeypatch.setattr(client, "_get_client", lambda: _FakeSDKClientAlwaysFails())

    with pytest.raises(OllamaConnectionError):
        client.generate_json("say hi")


def test_get_model_version_returns_digest_and_caches(monkeypatch, settings):
    client = OllamaClient(settings)
    show_calls = []

    class _FakeShowClient:
        def show(self, model):
            show_calls.append(model)
            return {"digest": "sha256:xyz789"}

    monkeypatch.setattr(client, "_get_client", lambda: _FakeShowClient())

    first = client.get_model_version()
    second = client.get_model_version()

    assert first == second == "sha256:xyz789"
    assert len(show_calls) == 1  # cached after first successful lookup


def test_get_model_version_never_raises_returns_unknown_on_failure(monkeypatch, settings):
    client = OllamaClient(settings)

    class _FailingShowClient:
        def show(self, model):
            raise RuntimeError("ollama server unreachable")

    monkeypatch.setattr(client, "_get_client", lambda: _FailingShowClient())

    assert client.get_model_version() == "unknown"
