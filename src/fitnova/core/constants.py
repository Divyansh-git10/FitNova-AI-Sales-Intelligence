"""Closed enumerations shared across the entire codebase.

These are the *only* "hardcoded" values in the system, and deliberately so:
they are structural vocabulary (what a call type can be, what an issue type
can be), not tunable business content. Anything that describes *how* these
values are interpreted, weighted, or detected lives in `config/*.yaml`
(see `fitnova.core.config` and docs/01_PHASE1_DESIGN.md Section 13).

Every enum inherits from `str` so it serializes cleanly to JSON, compares
equal to plain strings, and can be stored directly by SQLAlchemy's `Enum`
type without a custom adapter.
"""

from __future__ import annotations

from enum import Enum


class SourceSystem(str, Enum):
    """Where a call recording originated. New sources are added here and in
    a new `IngestionAdapter` subclass — nothing else in the pipeline needs
    to know a new source exists."""

    FOLDER = "FOLDER"
    CRM = "CRM"
    TELEPHONY = "TELEPHONY"
    DIALER = "DIALER"


class CallType(str, Enum):
    """Result of call classification (`processing.call_classifier`). Only
    SALES calls proceed to full scoring; everything else is retained for
    audit but excluded from scoring aggregates."""

    SALES = "SALES"
    WRONG_NUMBER = "WRONG_NUMBER"
    INTERNAL = "INTERNAL"
    NO_SPEECH = "NO_SPEECH"
    UNSUPPORTED_LANGUAGE = "UNSUPPORTED_LANGUAGE"
    PENDING_METADATA = "PENDING_METADATA"
    UNKNOWN = "UNKNOWN"


class AudioQualityFlag(str, Enum):
    """Coarse audio-quality signal derived from ASR confidence / VAD, shown
    as a warning badge in the dashboard rather than hidden."""

    GOOD = "GOOD"
    POOR = "POOR"
    SILENT = "SILENT"


class AudioFileFormat(str, Enum):
    """Supported input audio container formats."""

    WAV = "wav"
    MP3 = "mp3"
    M4A = "m4a"


class SpeakerLabel(str, Enum):
    """Diarized speaker role. UNKNOWN is a legitimate, expected value when
    diarization fails or confidence is too low to assign a role."""

    ADVISOR = "ADVISOR"
    CUSTOMER = "CUSTOMER"
    UNKNOWN = "UNKNOWN"


class IssueType(str, Enum):
    """The closed issue-tag taxonomy. The LLM selects from this fixed set —
    it can never introduce a new category (see docs Section 6.3, mechanism
    #2 "Closed enums"). Human-readable description and detection guidance
    for each member live in `config/issue_rules.yaml`."""

    NO_NEEDS_DISCOVERY = "NO_NEEDS_DISCOVERY"
    OVER_PROMISING = "OVER_PROMISING"
    PRESSURE_SELLING = "PRESSURE_SELLING"
    PRICE_BEFORE_VALUE = "PRICE_BEFORE_VALUE"
    UNDISCLOSED_COST = "UNDISCLOSED_COST"
    NO_TRIAL_BOOKING = "NO_TRIAL_BOOKING"
    INTERRUPTING_CUSTOMER = "INTERRUPTING_CUSTOMER"
    MISSELLING = "MISSELLING"
    WEAK_CLOSING = "WEAK_CLOSING"
    LOW_EMPATHY = "LOW_EMPATHY"


class Severity(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class IssueStatus(str, Enum):
    """Lifecycle of a flagged issue after human review. Contesting or
    confirming a flag changes this status; it never deletes the original
    LLM output (audit trail preserved, see docs Section 3 assumption 9)."""

    OPEN = "OPEN"
    CONTESTED = "CONTESTED"
    CONFIRMED = "CONFIRMED"
    DISMISSED = "DISMISSED"


class PipelineStage(str, Enum):
    """Checkpoints the orchestrator records progress against, enabling
    resume-from-last-successful-stage instead of restart-from-zero."""

    INGESTED = "INGESTED"
    TRANSCRIBED = "TRANSCRIBED"
    DIARIZED = "DIARIZED"
    NORMALIZED = "NORMALIZED"
    REDACTED = "REDACTED"
    CLASSIFIED = "CLASSIFIED"
    ANALYZED = "ANALYZED"
    SCORED = "SCORED"
    VALIDATED = "VALIDATED"
    STORED = "STORED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ProcessingStatusEnum(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ReviewerRole(str, Enum):
    ADVISOR = "ADVISOR"
    TEAM_LEADER = "TEAM_LEADER"
    SALES_DIRECTOR = "SALES_DIRECTOR"


class FeedbackType(str, Enum):
    CONTEST = "CONTEST"
    CONFIRM = "CONFIRM"
    COMMENT = "COMMENT"


class LLMStage(str, Enum):
    """Which analysis-engine step invoked the LLM. Recorded on every
    `llm_inference_logs` row (see docs Section 12, LLM Observability)."""

    CALL_CLASSIFICATION = "CALL_CLASSIFICATION"
    ISSUE_DETECTION = "ISSUE_DETECTION"
    SCORING = "SCORING"
    INSIGHT_GENERATION = "INSIGHT_GENERATION"


class DiarizationBackend(str, Enum):
    PYANNOTE = "pyannote"
    FALLBACK = "fallback"


class LogFormat(str, Enum):
    CONSOLE = "console"
    JSON = "json"


class ConfidenceLabel(str, Enum):
    """Calibrated, human-readable confidence tier alongside the raw
    numeric confidence score. Persisted next to the number (not derived
    on the fly at display time) so the label always reflects the
    thresholds in effect when the score/issue was produced — see
    `fitnova.analysis.confidence.calibrate_confidence` and docs Section
    "Confidence Calibration" (Phase 4 addendum)."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class WhisperModelSize(str, Enum):
    """Canonical faster-whisper model sizes, ordered largest (best quality,
    most resource-hungry) to smallest (fastest, least accurate).

    `transcription.whisper_engine.WhisperTranscriber` walks this list
    starting at `Settings.whisper_model_size`, cascading toward TINY on any
    load or inference failure (OOM, corrupt cached weights, transient
    download error) — see docs Section 9 "vendor API failures, retries".
    """

    LARGE = "large-v3"
    MEDIUM = "medium"
    SMALL = "small"
    BASE = "base"
    TINY = "tiny"


# Canonical fallback order, largest/most-accurate first.
WHISPER_FALLBACK_ORDER: list[WhisperModelSize] = [
    WhisperModelSize.LARGE,
    WhisperModelSize.MEDIUM,
    WhisperModelSize.SMALL,
    WhisperModelSize.BASE,
    WhisperModelSize.TINY,
]
