from __future__ import annotations

from pydantic import BaseModel, Field

from fitnova.core.constants import AudioFileFormat, AudioQualityFlag
from fitnova.schemas.common import ORMModel


class AudioMetadataBase(BaseModel):
    file_path: str = Field(..., max_length=1024)
    file_format: AudioFileFormat
    sample_rate: int | None = Field(default=None, gt=0)
    channels: int | None = Field(default=None, gt=0)
    file_size_bytes: int | None = Field(default=None, ge=0)
    audio_quality_flag: AudioQualityFlag = AudioQualityFlag.GOOD


class AudioMetadataCreate(AudioMetadataBase):
    call_id: int


class AudioMetadataRead(AudioMetadataBase, ORMModel):
    id: int
    call_id: int
