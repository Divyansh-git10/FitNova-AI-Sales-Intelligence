"""Merges ASR text segments with diarized speaker turns into the final,
timestamped, speaker-labeled transcript.

Whisper and the diarizer run independently and produce independently timed
segments — this module is the join. For each ASR segment, the diarized
turn with the greatest time overlap determines its speaker label; a
segment with no overlapping turn (diarization found nothing there) is
labeled `SpeakerLabel.UNKNOWN` rather than guessed (docs Section 9,
"speaker detection failure").

Timestamps are preserved exactly as reported by Whisper — this module
never rewrites `start`/`end`, only annotates them with a speaker.
"""

from __future__ import annotations

from dataclasses import dataclass

from fitnova.core.constants import SpeakerLabel
from fitnova.diarization.base import DiarizedTurn
from fitnova.transcription.whisper_engine import WhisperSegment


@dataclass(frozen=True)
class NormalizedSegment:
    segment_index: int
    speaker_label: SpeakerLabel
    start_time: float
    end_time: float
    text: str
    confidence: float | None


@dataclass(frozen=True)
class NormalizedTranscript:
    segments: list[NormalizedSegment]
    full_text: str
    word_count: int
    avg_confidence: float | None


def normalize(
    whisper_segments: list[WhisperSegment], diarized_turns: list[DiarizedTurn]
) -> NormalizedTranscript:
    """Merge ASR segments with diarized turns. Deterministic, evidence-only
    — no LLM involvement, so `transcript_segments` always reflects exactly
    what Whisper and the diarizer produced (this is the ground truth every
    later issue/score must cite)."""
    segments: list[NormalizedSegment] = []
    index = 0
    confidences: list[float] = []

    for whisper_seg in whisper_segments:
        text = whisper_seg.text.strip()
        if not text:
            continue

        speaker_label = _best_overlapping_speaker(whisper_seg, diarized_turns)
        segments.append(
            NormalizedSegment(
                segment_index=index,
                speaker_label=speaker_label,
                start_time=whisper_seg.start,
                end_time=whisper_seg.end,
                text=text,
                confidence=whisper_seg.confidence,
            )
        )
        if whisper_seg.confidence is not None:
            confidences.append(whisper_seg.confidence)
        index += 1

    full_text = " ".join(seg.text for seg in segments)
    word_count = len(full_text.split())
    avg_confidence = sum(confidences) / len(confidences) if confidences else None

    return NormalizedTranscript(
        segments=segments,
        full_text=full_text,
        word_count=word_count,
        avg_confidence=avg_confidence,
    )


def _best_overlapping_speaker(
    whisper_seg: WhisperSegment, diarized_turns: list[DiarizedTurn]
) -> SpeakerLabel:
    best_overlap = 0.0
    best_label = SpeakerLabel.UNKNOWN

    for turn in diarized_turns:
        overlap = min(whisper_seg.end, turn.end) - max(whisper_seg.start, turn.start)
        if overlap > best_overlap:
            best_overlap = overlap
            best_label = turn.speaker_label

    return best_label
