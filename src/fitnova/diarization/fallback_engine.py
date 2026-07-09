"""Deterministic fallback diarizer: VAD + turn-taking heuristic.

No speaker embeddings, no clustering model, no external dependency beyond
`webrtcvad` (a lightweight, CPU-only, deterministic voice-activity
detector). The algorithm:

1. Decode audio to mono 16 kHz PCM16 (`audio_validation.to_mono_pcm16`).
2. Run `webrtcvad` over fixed-size frames to get a speech/non-speech flag
   per frame.
3. Merge consecutive speech frames into raw segments; merge segments
   separated by a gap shorter than `Settings.speaker_gap_merge_seconds`
   into a single turn (treats a short pause as the same speaker
   continuing, not a handoff).
4. Discard turns shorter than `Settings.min_turn_duration_seconds` as VAD
   noise, not real speech.
5. Assign speakers by **strict alternation**: the first turn is speaker A,
   the second is speaker B, the third is speaker A again, and so on.

This is a real, documented trade-off (docs Section 3, assumption 3 and
Section 9): it assumes a clean two-party back-and-forth and will
mislabel turns during interruptions, overlapping speech, or long
monologues broken up by VAD into multiple "turns" from the same speaker.
It is deterministic and dependency-light, which is the point of a
*fallback* — pyannote (`pyannote_engine.py`) is the higher-fidelity
option when it's available.

Speaker A/B are mapped to ADVISOR/CUSTOMER via
`Settings.first_speaker_is_advisor` (default: the advisor opens the call,
so speaker A = ADVISOR) — also documented as a heuristic, not a certainty.
"""

from __future__ import annotations

from pathlib import Path

import webrtcvad

from fitnova.core.config import Settings
from fitnova.core.constants import SpeakerLabel
from fitnova.core.logging_config import get_logger
from fitnova.diarization.base import DiarizationError, DiarizedTurn
from fitnova.processing.audio_validation import to_mono_pcm16

logger = get_logger(__name__)

_VALID_FRAME_MS = {10, 20, 30}
_SAMPLE_WIDTH_BYTES = 2  # 16-bit PCM


def diarize_fallback(audio_path: Path, settings: Settings) -> list[DiarizedTurn]:
    """Run the deterministic VAD + turn-taking diarizer over `audio_path`."""
    frame_ms = settings.vad_frame_ms if settings.vad_frame_ms in _VALID_FRAME_MS else 30
    if frame_ms != settings.vad_frame_ms:
        logger.warning(
            "VAD_FRAME_MS=%d is not one of %s; using %dms",
            settings.vad_frame_ms,
            _VALID_FRAME_MS,
            frame_ms,
        )

    try:
        pcm_bytes, sample_rate = to_mono_pcm16(audio_path, target_sample_rate=16000)
    except Exception as exc:  # noqa: BLE001
        raise DiarizationError(f"Could not decode audio for diarization: {exc}") from exc

    speech_frames = _run_vad(pcm_bytes, sample_rate, frame_ms, settings.vad_aggressiveness)
    raw_segments = _frames_to_segments(speech_frames, frame_ms)
    merged_segments = _merge_close_segments(raw_segments, settings.speaker_gap_merge_seconds)
    turns = [
        seg for seg in merged_segments if (seg[1] - seg[0]) >= settings.min_turn_duration_seconds
    ]

    if not turns:
        logger.warning("Fallback diarizer found no speech turns in %s", audio_path)
        return []

    return _assign_alternating_speakers(turns, settings.first_speaker_is_advisor)


def _run_vad(pcm_bytes: bytes, sample_rate: int, frame_ms: int, aggressiveness: int) -> list[bool]:
    vad = webrtcvad.Vad(aggressiveness)
    frame_bytes = int(sample_rate * (frame_ms / 1000.0) * _SAMPLE_WIDTH_BYTES)
    if frame_bytes == 0:
        raise DiarizationError("Computed VAD frame size is zero — invalid sample rate/frame_ms")

    flags: list[bool] = []
    for offset in range(0, len(pcm_bytes) - frame_bytes + 1, frame_bytes):
        frame = pcm_bytes[offset : offset + frame_bytes]
        try:
            flags.append(vad.is_speech(frame, sample_rate))
        except (
            Exception
        ):  # noqa: BLE001 - webrtcvad raises on malformed frames; treat as non-speech
            flags.append(False)
    return flags


def _frames_to_segments(speech_flags: list[bool], frame_ms: int) -> list[tuple[float, float]]:
    segments: list[tuple[float, float]] = []
    frame_seconds = frame_ms / 1000.0
    in_segment = False
    seg_start = 0.0

    for index, is_speech in enumerate(speech_flags):
        t = index * frame_seconds
        if is_speech and not in_segment:
            in_segment = True
            seg_start = t
        elif not is_speech and in_segment:
            in_segment = False
            segments.append((seg_start, t))

    if in_segment:
        segments.append((seg_start, len(speech_flags) * frame_seconds))

    return segments


def _merge_close_segments(
    segments: list[tuple[float, float]], gap_threshold_seconds: float
) -> list[tuple[float, float]]:
    if not segments:
        return []

    merged = [segments[0]]
    for start, end in segments[1:]:
        prev_start, prev_end = merged[-1]
        if start - prev_end <= gap_threshold_seconds:
            merged[-1] = (prev_start, end)
        else:
            merged.append((start, end))
    return merged


def _assign_alternating_speakers(
    turns: list[tuple[float, float]], first_speaker_is_advisor: bool
) -> list[DiarizedTurn]:
    speaker_a_label = SpeakerLabel.ADVISOR if first_speaker_is_advisor else SpeakerLabel.CUSTOMER
    speaker_b_label = SpeakerLabel.CUSTOMER if first_speaker_is_advisor else SpeakerLabel.ADVISOR

    result: list[DiarizedTurn] = []
    for i, (start, end) in enumerate(turns):
        if i % 2 == 0:
            label, raw_id = speaker_a_label, "SPEAKER_00"
        else:
            label, raw_id = speaker_b_label, "SPEAKER_01"
        result.append(
            DiarizedTurn(start=start, end=end, speaker_label=label, raw_speaker_id=raw_id)
        )
    return result
