"""Tests for the deterministic VAD + turn-taking fallback diarizer.

The segment-merging and speaker-alternation logic is tested directly
against synthetic frame/segment data (deterministic, no dependency on
whether `webrtcvad` classifies a synthetic tone as "speech" - that's a
property of webrtcvad's trained model, not something this codebase
controls or should assert on). A separate smoke test exercises
`diarize_fallback` end-to-end against real generated audio to prove the
full path runs without error.
"""

from __future__ import annotations

import importlib.util

import pytest

from fitnova.core.constants import SpeakerLabel
from fitnova.diarization.fallback_engine import (
    _assign_alternating_speakers,
    _frames_to_segments,
    _merge_close_segments,
    diarize_fallback,
)

# webrtcvad is an optional speech-extras dependency (see requirements-speech.txt)
# - it isn't installed by the core requirements.txt, so it may legitimately be
# absent. Only the two tests that actually invoke diarize_fallback() need it;
# the segment-merging/speaker-alternation tests above them are pure Python and
# run regardless of whether webrtcvad is installed.
requires_webrtcvad = pytest.mark.skipif(
    importlib.util.find_spec("webrtcvad") is None,
    reason="webrtcvad not installed - run `pip install -r requirements-speech.txt`",
)


def test_frames_to_segments_groups_consecutive_speech():
    # 30ms frames: silence, speech, speech, silence, speech, silence
    flags = [False, True, True, False, True, False]
    segments = _frames_to_segments(flags, frame_ms=30)

    assert segments == [(0.03, 0.09), (0.12, 0.15)]


def test_frames_to_segments_handles_trailing_speech():
    flags = [False, True, True]
    segments = _frames_to_segments(flags, frame_ms=30)
    assert segments == [(0.03, 0.09)]


def test_frames_to_segments_handles_no_speech():
    assert _frames_to_segments([False, False, False], frame_ms=30) == []


def test_merge_close_segments_combines_within_threshold():
    segments = [(0.0, 1.0), (1.2, 2.0), (5.0, 6.0)]
    merged = _merge_close_segments(segments, gap_threshold_seconds=0.5)
    assert merged == [(0.0, 2.0), (5.0, 6.0)]


def test_merge_close_segments_keeps_separate_beyond_threshold():
    segments = [(0.0, 1.0), (3.0, 4.0)]
    merged = _merge_close_segments(segments, gap_threshold_seconds=0.5)
    assert merged == [(0.0, 1.0), (3.0, 4.0)]


def test_merge_close_segments_empty_input():
    assert _merge_close_segments([], gap_threshold_seconds=0.5) == []


def test_assign_alternating_speakers_first_speaker_advisor_by_default():
    turns = [(0.0, 1.0), (1.0, 2.0), (2.0, 3.0)]
    result = _assign_alternating_speakers(turns, first_speaker_is_advisor=True)

    assert [t.speaker_label for t in result] == [
        SpeakerLabel.ADVISOR,
        SpeakerLabel.CUSTOMER,
        SpeakerLabel.ADVISOR,
    ]
    assert result[0].start == 0.0 and result[0].end == 1.0


def test_assign_alternating_speakers_respects_flag():
    turns = [(0.0, 1.0), (1.0, 2.0)]
    result = _assign_alternating_speakers(turns, first_speaker_is_advisor=False)

    assert [t.speaker_label for t in result] == [SpeakerLabel.CUSTOMER, SpeakerLabel.ADVISOR]


@requires_webrtcvad
def test_diarize_fallback_smoke_runs_on_real_audio(make_tone_wav, settings):
    """End-to-end smoke test: real WAV -> real webrtcvad -> real merging.
    Does not assert specific speaker boundaries (that depends on
    webrtcvad's own speech/non-speech judgment on a synthetic tone) - only
    that the full path executes and returns a well-formed result."""
    path = make_tone_wav("call.wav", duration_s=3.0, amplitude=0.6)
    turns = diarize_fallback(path, settings)

    assert isinstance(turns, list)
    for turn in turns:
        assert turn.end > turn.start
        assert turn.speaker_label in (SpeakerLabel.ADVISOR, SpeakerLabel.CUSTOMER)


@requires_webrtcvad
def test_diarize_fallback_returns_empty_for_silence(make_silence_wav, settings):
    path = make_silence_wav("silent.wav", duration_s=3.0)
    turns = diarize_fallback(path, settings)
    assert turns == []
