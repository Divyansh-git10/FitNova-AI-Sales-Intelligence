"""Tests for the automatic Whisper model fallback cascade.

`faster_whisper.WhisperModel` is never actually loaded here — real model
weights require a network download this environment may not have, and unit
tests shouldn't depend on that anyway. `_get_or_load_model` is monkeypatched
with a fake that mimics the same interface, so what's under test is the
CASCADE LOGIC (which models get tried, in what order, and what happens
when all of them fail) — not faster-whisper itself.
"""

from __future__ import annotations

import pytest

from fitnova.transcription.whisper_engine import (
    TranscriptionFailedError,
    WhisperTranscriber,
    _fallback_chain,
)


class _FakeInfo:
    language = "en"
    language_probability = 0.98


class _FakeSegment:
    def __init__(self, start: float, end: float, text: str, avg_logprob: float) -> None:
        self.start = start
        self.end = end
        self.text = text
        self.avg_logprob = avg_logprob


class _FakeModel:
    def __init__(self, size: str, should_fail: bool) -> None:
        self.size = size
        self.should_fail = should_fail

    def transcribe(self, path, language=None, vad_filter=False):
        if self.should_fail:
            raise RuntimeError(f"simulated failure loading/running '{self.size}'")
        return (
            [_FakeSegment(0.0, 1.5, "hello there", -0.05)],
            _FakeInfo(),
        )


def test_fallback_chain_starts_at_configured_size():
    assert _fallback_chain("small") == ["small", "base", "tiny"]
    assert _fallback_chain("large-v3") == ["large-v3", "medium", "small", "base", "tiny"]
    assert _fallback_chain("tiny") == ["tiny"]


def test_fallback_chain_handles_unknown_size_gracefully():
    chain = _fallback_chain("custom-finetune")
    assert chain[0] == "custom-finetune"
    assert chain[1:] == ["large-v3", "medium", "small", "base", "tiny"]


def test_transcriber_succeeds_on_preferred_model(monkeypatch, tmp_path):
    transcriber = WhisperTranscriber(model_size="small", device="cpu", compute_type="int8")

    def fake_get_or_load(self, model_size):
        return _FakeModel(model_size, should_fail=False)

    monkeypatch.setattr(WhisperTranscriber, "_get_or_load_model", fake_get_or_load)

    audio_path = tmp_path / "call.wav"
    audio_path.write_bytes(b"fake-audio-bytes")

    result = transcriber.transcribe(audio_path)

    assert result.model_used == "small"
    assert result.attempted_models == ["small"]
    assert result.segments[0].text == "hello there"
    assert result.language == "en"


def test_transcriber_cascades_through_failures_to_success(monkeypatch, tmp_path):
    transcriber = WhisperTranscriber(model_size="small", device="cpu", compute_type="int8")
    failing_sizes = {"small", "base"}

    def fake_get_or_load(self, model_size):
        return _FakeModel(model_size, should_fail=model_size in failing_sizes)

    monkeypatch.setattr(WhisperTranscriber, "_get_or_load_model", fake_get_or_load)

    audio_path = tmp_path / "call.wav"
    audio_path.write_bytes(b"fake-audio-bytes")

    result = transcriber.transcribe(audio_path)

    assert result.model_used == "tiny"
    assert result.attempted_models == ["small", "base", "tiny"]


def test_transcriber_raises_after_exhausting_every_model(monkeypatch, tmp_path):
    transcriber = WhisperTranscriber(model_size="small", device="cpu", compute_type="int8")

    def fake_get_or_load(self, model_size):
        return _FakeModel(model_size, should_fail=True)

    monkeypatch.setattr(WhisperTranscriber, "_get_or_load_model", fake_get_or_load)

    audio_path = tmp_path / "call.wav"
    audio_path.write_bytes(b"fake-audio-bytes")

    with pytest.raises(TranscriptionFailedError) as exc_info:
        transcriber.transcribe(audio_path)

    assert exc_info.value.attempted_models == ["small", "base", "tiny"]


def test_transcriber_caches_loaded_models(monkeypatch, tmp_path):
    transcriber = WhisperTranscriber(model_size="tiny", device="cpu", compute_type="int8")
    load_calls: list[str] = []

    def fake_get_or_load(self, model_size):
        load_calls.append(model_size)
        return _FakeModel(model_size, should_fail=False)

    monkeypatch.setattr(WhisperTranscriber, "_get_or_load_model", fake_get_or_load)

    audio_path = tmp_path / "call.wav"
    audio_path.write_bytes(b"fake-audio-bytes")

    transcriber.transcribe(audio_path)
    transcriber.transcribe(audio_path)

    # _get_or_load_model itself is mocked (so caching inside it isn't
    # exercised here), but each transcribe() call should only need to
    # resolve the preferred model once since it succeeds immediately.
    assert load_calls == ["tiny", "tiny"]
