from __future__ import annotations

from pydantic import BaseModel, Field

from fitnova.core.constants import SpeakerLabel
from fitnova.schemas.common import ORMModel, TimestampedRead


class TranscriptSegmentBase(BaseModel):
    segment_index: int = Field(..., ge=0)
    speaker_label: SpeakerLabel = SpeakerLabel.UNKNOWN
    start_time: float = Field(..., ge=0)
    end_time: float = Field(..., ge=0)
    text: str
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class TranscriptSegmentCreate(TranscriptSegmentBase):
    transcript_id: int


class TranscriptSegmentRead(TranscriptSegmentBase, ORMModel):
    id: int
    transcript_id: int


class TranscriptBase(BaseModel):
    raw_text: str | None = None
    redacted_text: str | None = None
    word_count: int | None = Field(default=None, ge=0)
    avg_confidence: float | None = Field(default=None, ge=0.0, le=1.0)


class TranscriptCreate(TranscriptBase):
    call_id: int


class TranscriptRead(TranscriptBase, TimestampedRead):
    call_id: int
    segments: list[TranscriptSegmentRead] = []
