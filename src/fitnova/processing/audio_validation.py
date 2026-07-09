"""Audio validation and metadata extraction.

Uses `pydub` (backed by the system `ffmpeg`) rather than `soundfile` as the
primary decoder because it handles all three required formats (wav, mp3,
m4a) through one code path — `soundfile`/libsndfile does not reliably
decode m4a/AAC. This is a deliberate simplification: one decoder, one set
of failure modes, documented here instead of split across two libraries.

Two concerns are handled together, in one decode pass, to avoid paying the
ffmpeg decode cost twice:

1. **Metadata extraction** — duration, sample rate, channel count, file size.
2. **Quality validation** — corrupt/unreadable files raise
   `AudioValidationError` (a hard stop); silence and low-signal audio are
   NOT hard errors — they produce an `AudioQualityFlag` the rest of the
   pipeline uses to make a judgment call (e.g. `AudioQualityFlag.SILENT`
   feeds into `CallType.NO_SPEECH` in `call_classifier.py`), per docs
   Section 9's edge-case handling philosophy: never silently drop a call,
   always flag it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydub import AudioSegment
from pydub.exceptions import CouldntDecodeError

from fitnova.core.config import Settings
from fitnova.core.constants import AudioFileFormat, AudioQualityFlag
from fitnova.core.logging_config import get_logger

logger = get_logger(__name__)

_SUPPORTED_SUFFIXES = {fmt.value for fmt in AudioFileFormat}

# A quality flag below GOOD but above SILENT — audio decodes and has some
# signal, but is quiet/noisy enough that transcription confidence should be
# treated with caution. Expressed as a multiple of the configured silence
# threshold so it stays proportional to whatever the operator considers
# "silent" for their environment.
_POOR_QUALITY_RMS_MULTIPLIER = 5.0


class AudioValidationError(Exception):
    """Raised for files that cannot be processed at all: missing, empty,
    wrong extension, or undecodable (corrupt). Never raised for merely
    quiet/short/mono audio — those are `AudioQualityFlag` values, not
    fatal errors."""


@dataclass(frozen=True)
class AudioAnalysisResult:
    duration_seconds: float
    sample_rate: int
    channels: int
    file_size_bytes: int
    file_format: str
    quality_flag: AudioQualityFlag
    normalized_rms: float


def analyze_audio(path: Path, settings: Settings) -> AudioAnalysisResult:
    """Decode `path` once and return both its metadata and quality flag.

    Raises `AudioValidationError` for files that can't be processed at
    all. Returns a result (never raises) for files that decode fine but
    are silent, too short, or otherwise low quality — those are the
    pipeline's job to flag, not to crash on.
    """
    path = Path(path)
    if not path.exists():
        raise AudioValidationError(f"Audio file not found: {path}")

    file_size_bytes = path.stat().st_size
    if file_size_bytes == 0:
        raise AudioValidationError(f"Audio file is empty (0 bytes): {path}")

    suffix = path.suffix.lower().lstrip(".")
    if suffix not in _SUPPORTED_SUFFIXES:
        raise AudioValidationError(
            f"Unsupported audio format '.{suffix}' for {path}. "
            f"Supported formats: {sorted(_SUPPORTED_SUFFIXES)}"
        )

    try:
        segment = AudioSegment.from_file(path)
    except (CouldntDecodeError, OSError, IndexError) as exc:
        raise AudioValidationError(f"Could not decode audio file {path}: {exc}") from exc

    duration_seconds = len(segment) / 1000.0
    normalized_rms = _normalized_rms(segment)
    quality_flag = _classify_quality(duration_seconds, normalized_rms, settings)

    logger.debug(
        "Analyzed audio %s: duration=%.2fs sample_rate=%d channels=%d rms=%.5f quality=%s",
        path.name,
        duration_seconds,
        segment.frame_rate,
        segment.channels,
        normalized_rms,
        quality_flag,
    )

    return AudioAnalysisResult(
        duration_seconds=duration_seconds,
        sample_rate=segment.frame_rate,
        channels=segment.channels,
        file_size_bytes=file_size_bytes,
        file_format=suffix,
        quality_flag=quality_flag,
        normalized_rms=normalized_rms,
    )


def to_mono_pcm16(path: Path, target_sample_rate: int = 16000) -> tuple[bytes, int]:
    """Decode `path` to mono, 16-bit PCM at `target_sample_rate`.

    Shared utility consumed by the fallback diarizer (`webrtcvad` requires
    exactly this format: 16-bit mono PCM at 8/16/32/48 kHz) and available
    to the transcription engine if it ever needs raw samples. Returns the
    raw PCM bytes and the sample rate actually used.
    """
    segment = AudioSegment.from_file(path)
    segment = segment.set_channels(1).set_frame_rate(target_sample_rate).set_sample_width(2)
    return segment.raw_data, target_sample_rate


def _normalized_rms(segment: AudioSegment) -> float:
    """RMS amplitude normalized to [0, 1] relative to the format's full
    scale, so the silence threshold in config is bit-depth independent."""
    if segment.rms == 0:
        return 0.0
    max_possible_amplitude = 2 ** (8 * segment.sample_width - 1)
    if max_possible_amplitude == 0:
        return 0.0
    return min(segment.rms / max_possible_amplitude, 1.0)


def _classify_quality(
    duration_seconds: float, normalized_rms: float, settings: Settings
) -> AudioQualityFlag:
    if duration_seconds <= 0 or normalized_rms < settings.silence_rms_threshold:
        return AudioQualityFlag.SILENT
    if (
        normalized_rms < settings.silence_rms_threshold * _POOR_QUALITY_RMS_MULTIPLIER
        or duration_seconds < settings.min_call_duration_seconds
    ):
        return AudioQualityFlag.POOR
    return AudioQualityFlag.GOOD
