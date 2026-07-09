"""Synthetic placeholder audio generator for the Phase 6 demo dataset.

Why synthetic tones and not real speech recordings
----------------------------------------------------
This project's standing rule is "everything runs locally, prefer
open-source models, never fabricate outputs." For the demo dataset that
creates a real tension: realistic *audio* of a sales call would normally
come from actual recordings or a text-to-speech engine, but this
environment has no internet access to download sample recordings and no
working offline TTS engine (`pyttsx3` depends on eSpeak/eSpeak-ng, which
requires `apt`/root and is not installable here).

Rather than fake a transcript directly (which WOULD be fabricating
output), this script generates real, decodable WAV files — plain sine
tones, openly labeled as synthetic placeholder audio — purely so the real
`fitnova.processing.audio_validation.analyze_audio()` stage has actual
audio bytes to decode and measure (duration, sample rate, RMS, quality
flag). `scripts/seed_demo_data.py` pairs each generated tone with a
hand-authored transcript (standing in for what Whisper + diarization would
have produced from a real recording) and runs that transcript through the
REAL classification, PII redaction, and metrics functions — never through
a mocked or hardcoded scoring shortcut.

If you have real call recordings or a working TTS pipeline, drop actual
audio into `data/audio/inbox/` and run `fitnova ingest` instead — that is
the fully real path and does not need this script at all.
"""

from __future__ import annotations

import math
import struct
import wave
from pathlib import Path

DEFAULT_SAMPLE_RATE = 8000  # 8 kHz mono — standard telephony sample rate


def generate_tone_wav(
    path: Path,
    duration_s: float,
    freq: float = 220.0,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    amplitude: float = 0.3,
) -> Path:
    """Write a real, decodable mono 16-bit PCM WAV containing a sine tone.

    `amplitude=0.3` yields a normalized RMS comfortably above the default
    `AudioQualityFlag.GOOD` threshold, so demo "sales" calls validate as
    good-quality audio rather than being flagged POOR/SILENT.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    n_samples = int(duration_s * sample_rate)
    peak = int(amplitude * 32767)
    samples = [
        int(peak * math.sin(2 * math.pi * freq * (i / sample_rate))) for i in range(n_samples)
    ]
    _write_wav(path, samples, sample_rate)
    return path


def generate_silence_wav(
    path: Path, duration_s: float, sample_rate: int = DEFAULT_SAMPLE_RATE
) -> Path:
    """Write an all-zero-sample WAV — real audio bytes that decode to
    silence, so `analyze_audio()` genuinely computes `AudioQualityFlag.SILENT`
    rather than having it asserted."""
    path.parent.mkdir(parents=True, exist_ok=True)
    n_samples = int(duration_s * sample_rate)
    _write_wav(path, [0] * n_samples, sample_rate)
    return path


def _write_wav(path: Path, samples: list[int], sample_rate: int) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)  # 16-bit PCM
        wf.setframerate(sample_rate)
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))


if __name__ == "__main__":
    # Standalone smoke-test / manual-listen mode: drop a handful of sample
    # tones into data/audio/demo_samples/ without touching the database.
    # `seed_demo_data.py` is the real entry point for the full demo dataset.
    import sys

    out_dir = Path(__file__).resolve().parents[1] / "data" / "audio" / "demo_samples"
    generate_tone_wav(out_dir / "sample_tone_a.wav", duration_s=5.0, freq=220.0)
    generate_tone_wav(out_dir / "sample_tone_b.wav", duration_s=5.0, freq=440.0)
    generate_silence_wav(out_dir / "sample_silence.wav", duration_s=5.0)
    print(f"Wrote 3 synthetic placeholder WAV files to {out_dir}", file=sys.stderr)
    print(
        "These are sine-tone/silence placeholders, not real speech — see this "
        "script's module docstring for why.",
        file=sys.stderr,
    )
