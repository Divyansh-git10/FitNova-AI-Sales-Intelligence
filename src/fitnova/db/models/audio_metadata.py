"""AudioMetadata — physical properties of the recording file, 1:1 with Call."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from fitnova.core.constants import AudioQualityFlag
from fitnova.db.base import Base

if TYPE_CHECKING:
    from fitnova.db.models.call import Call


class AudioMetadata(Base):
    """Everything known about the raw audio file itself, independent of its
    content. `audio_quality_flag` drives the "poor audio" edge-case handling
    described in docs Section 9."""

    __tablename__ = "audio_metadata"

    id: Mapped[int] = mapped_column(primary_key=True)
    call_id: Mapped[int] = mapped_column(
        ForeignKey("calls.id", ondelete="CASCADE"), unique=True, nullable=False, index=True
    )

    file_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    file_format: Mapped[str] = mapped_column(String(16), nullable=False)  # wav | mp3 | m4a
    sample_rate: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channels: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    audio_quality_flag: Mapped[AudioQualityFlag] = mapped_column(
        Enum(AudioQualityFlag, native_enum=False, length=16),
        default=AudioQualityFlag.GOOD,
        nullable=False,
    )

    call: Mapped["Call"] = relationship(back_populates="audio_metadata")

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<AudioMetadata call_id={self.call_id} format={self.file_format} "
            f"quality={self.audio_quality_flag}>"
        )
