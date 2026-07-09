"""Shared transcript-to-prompt formatting.

Every analysis prompt (scoring, issue detection, insight generation) needs
the same numbered, timestamped, speaker-labeled transcript representation
— built once here so `segment_index` in an LLM response always means
exactly "the Nth line of this exact rendering", which is what the evidence
validator relies on to resolve a cited index back to a real
`transcript_segments` row.
"""

from __future__ import annotations

from fitnova.db.models import TranscriptSegment


def format_transcript_for_prompt(segments: list[TranscriptSegment]) -> str:
    if not segments:
        return "(no transcript segments available)"

    lines = []
    for seg in segments:
        speaker = (
            seg.speaker_label.value if hasattr(seg.speaker_label, "value") else seg.speaker_label
        )
        lines.append(
            f"[{seg.segment_index}] ({speaker}, {seg.start_time:.1f}s-{seg.end_time:.1f}s): "
            f"{seg.text}"
        )
    return "\n".join(lines)
