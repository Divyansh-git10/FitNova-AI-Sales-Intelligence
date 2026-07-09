"""Tests for `processing.audio_validation` — metadata extraction and
quality flagging, using locally generated synthetic WAV files (no network,
no fixtures binary-committed to the repo)."""

from __future__ import annotations

import pytest

from fitnova.core.constants import AudioQualityFlag
from fitnova.processing.audio_validation import (
    AudioValidationError,
    analyze_audio,
    to_mono_pcm16,
)


def test_analyze_audio_detects_good_quality(make_tone_wav, settings):
    path = make_tone_wav("good_call.wav", duration_s=5.0, amplitude=0.5)
    result = analyze_audio(path, settings)

    assert result.quality_flag == AudioQualityFlag.GOOD
    assert result.channels == 1
    assert result.sample_rate == 16000
    assert 4.9 <= result.duration_seconds <= 5.1
    assert result.file_format == "wav"
    assert result.file_size_bytes > 0


def test_analyze_audio_detects_silence(make_silence_wav, settings):
    path = make_silence_wav("silent_call.wav", duration_s=5.0)
    result = analyze_audio(path, settings)

    assert result.quality_flag == AudioQualityFlag.SILENT
    assert result.normalized_rms == 0.0


def test_analyze_audio_flags_short_call_as_poor(make_tone_wav, settings):
    # Loud enough to not be silent, but shorter than min_call_duration_seconds
    path = make_tone_wav("short_call.wav", duration_s=1.0, amplitude=0.5)
    result = analyze_audio(path, settings)

    assert result.quality_flag == AudioQualityFlag.POOR
    assert result.duration_seconds < settings.min_call_duration_seconds


def test_analyze_audio_raises_for_missing_file(tmp_path, settings):
    with pytest.raises(AudioValidationError, match="not found"):
        analyze_audio(tmp_path / "does_not_exist.wav", settings)


def test_analyze_audio_raises_for_empty_file(tmp_path, settings):
    empty = tmp_path / "empty.wav"
    empty.write_bytes(b"")
    with pytest.raises(AudioValidationError, match="empty"):
        analyze_audio(empty, settings)


def test_analyze_audio_raises_for_unsupported_extension(tmp_path, settings):
    bad = tmp_path / "notes.txt"
    bad.write_text("not audio")
    with pytest.raises(AudioValidationError, match="Unsupported"):
        analyze_audio(bad, settings)


def test_to_mono_pcm16_produces_expected_length(make_tone_wav):
    path = make_tone_wav("call.wav", duration_s=2.0, sample_rate=8000)
    pcm_bytes, sample_rate = to_mono_pcm16(path, target_sample_rate=16000)

    assert sample_rate == 16000
    expected_bytes = int(2.0 * 16000) * 2  # duration * rate * 16-bit width
    # allow small tolerance for resampling rounding
    assert abs(len(pcm_bytes) - expected_bytes) < 2000
