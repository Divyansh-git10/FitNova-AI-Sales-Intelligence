"""Tests for merging ASR segments with diarized turns into the final,
timestamped, speaker-labeled transcript (docs Section 9, timestamp
preservation + speaker labels)."""

from __future__ import annotations

from fitnova.core.constants import SpeakerLabel
from fitnova.diarization.base import DiarizedTurn
from fitnova.processing.normalizer import normalize
from fitnova.transcription.whisper_engine import WhisperSegment


def test_normalize_assigns_speaker_by_greatest_overlap():
    whisper_segments = [
        WhisperSegment(start=0.0, end=2.0, text="hello, how can I help", confidence=0.9),
        WhisperSegment(start=2.5, end=4.0, text="I want to know about pricing", confidence=0.8),
    ]
    diarized_turns = [
        DiarizedTurn(
            start=0.0, end=2.2, speaker_label=SpeakerLabel.ADVISOR, raw_speaker_id="SPEAKER_00"
        ),
        DiarizedTurn(
            start=2.2, end=4.5, speaker_label=SpeakerLabel.CUSTOMER, raw_speaker_id="SPEAKER_01"
        ),
    ]

    result = normalize(whisper_segments, diarized_turns)

    assert len(result.segments) == 2
    assert result.segments[0].speaker_label == SpeakerLabel.ADVISOR
    assert result.segments[1].speaker_label == SpeakerLabel.CUSTOMER
    # timestamps preserved exactly as reported by Whisper
    assert result.segments[0].start_time == 0.0
    assert result.segments[0].end_time == 2.0
    assert result.segments[1].start_time == 2.5


def test_normalize_labels_unknown_when_no_diarization_overlap():
    whisper_segments = [WhisperSegment(start=10.0, end=11.0, text="orphan segment", confidence=0.7)]
    result = normalize(whisper_segments, diarized_turns=[])

    assert result.segments[0].speaker_label == SpeakerLabel.UNKNOWN


def test_normalize_skips_empty_text_segments():
    whisper_segments = [
        WhisperSegment(start=0.0, end=1.0, text="   ", confidence=0.5),
        WhisperSegment(start=1.0, end=2.0, text="real text", confidence=0.9),
    ]
    result = normalize(whisper_segments, diarized_turns=[])

    assert len(result.segments) == 1
    assert result.segments[0].text == "real text"
    assert result.segments[0].segment_index == 0


def test_normalize_computes_word_count_and_avg_confidence():
    whisper_segments = [
        WhisperSegment(start=0.0, end=1.0, text="one two three", confidence=0.8),
        WhisperSegment(start=1.0, end=2.0, text="four five", confidence=0.6),
    ]
    result = normalize(whisper_segments, diarized_turns=[])

    assert result.word_count == 5
    assert result.full_text == "one two three four five"
    assert abs(result.avg_confidence - 0.7) < 1e-9


def test_normalize_handles_empty_input():
    result = normalize([], [])
    assert result.segments == []
    assert result.word_count == 0
    assert result.avg_confidence is None
