"""Tests for the rule-based call classifier (docs Section 9's non-sales-call
edge cases)."""

from __future__ import annotations

from fitnova.core.constants import AudioQualityFlag, CallType
from fitnova.processing.call_classifier import classify_call
from fitnova.processing.normalizer import NormalizedTranscript


def _transcript(full_text: str, word_count: int | None = None) -> NormalizedTranscript:
    return NormalizedTranscript(
        segments=[],
        full_text=full_text,
        word_count=word_count if word_count is not None else len(full_text.split()),
        avg_confidence=0.8,
    )


def test_classifies_no_speech_when_silent(settings):
    transcript = _transcript("", word_count=0)
    call_type, reason = classify_call(
        transcript,
        duration_seconds=5.0,
        audio_quality_flag=AudioQualityFlag.SILENT,
        detected_language="en",
        settings=settings,
    )
    assert call_type == CallType.NO_SPEECH
    assert "SILENT" in reason or "zero" in reason


def test_classifies_no_speech_when_zero_words_even_if_not_silent(settings):
    transcript = _transcript("", word_count=0)
    call_type, _ = classify_call(
        transcript,
        duration_seconds=5.0,
        audio_quality_flag=AudioQualityFlag.GOOD,
        detected_language="en",
        settings=settings,
    )
    assert call_type == CallType.NO_SPEECH


def test_classifies_unsupported_language(settings):
    transcript = _transcript("bonjour comment allez vous aujourd'hui monsieur")
    call_type, reason = classify_call(
        transcript,
        duration_seconds=30.0,
        audio_quality_flag=AudioQualityFlag.GOOD,
        detected_language="fr",
        settings=settings,
    )
    assert call_type == CallType.UNSUPPORTED_LANGUAGE
    assert "fr" in reason


def test_classifies_internal_call_via_keyword(settings):
    transcript = _transcript(
        "hey team quick internal call about the standup notes for today's sync, "
        "let's align on priorities before the daily sync begins"
    )
    call_type, reason = classify_call(
        transcript,
        duration_seconds=40.0,
        audio_quality_flag=AudioQualityFlag.GOOD,
        detected_language="en",
        settings=settings,
    )
    assert call_type == CallType.INTERNAL
    assert "keyword" in reason.lower()


def test_classifies_wrong_number_short_call(settings):
    transcript = _transcript("hello who is this sorry wrong number")
    call_type, reason = classify_call(
        transcript,
        duration_seconds=8.0,
        audio_quality_flag=AudioQualityFlag.GOOD,
        detected_language="en",
        settings=settings,
    )
    assert call_type == CallType.WRONG_NUMBER
    assert "short" in reason.lower()


def test_classifies_sales_call_by_default(settings):
    long_text = " ".join(["discussing your fitness goals and budget and trial session"] * 10)
    transcript = _transcript(long_text)
    call_type, reason = classify_call(
        transcript,
        duration_seconds=180.0,
        audio_quality_flag=AudioQualityFlag.GOOD,
        detected_language="en",
        settings=settings,
    )
    assert call_type == CallType.SALES
    assert "No exclusion rule matched" in reason


def test_long_duration_overrides_wrong_number_even_if_few_words(settings):
    """A long call with few transcribed words (e.g. lots of silence/pauses)
    should not be misclassified as a wrong number — duration alone is
    enough to exclude that rule."""
    transcript = _transcript("hello yes okay sure")
    call_type, _ = classify_call(
        transcript,
        duration_seconds=120.0,
        audio_quality_flag=AudioQualityFlag.GOOD,
        detected_language="en",
        settings=settings,
    )
    assert call_type == CallType.SALES
