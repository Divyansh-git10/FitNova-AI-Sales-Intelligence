"""Phase 3 pipeline orchestrator.

Drives one call through: audio validation -> metadata extraction ->
transcription (with automatic Whisper model fallback) -> diarization
(pyannote or deterministic fallback) -> normalization -> PII redaction ->
rule-based call classification -> persistence, recording a
`PipelineBenchmark` and explicit `ProcessingStatus` transitions the whole
way (docs Section 4.5's sequence diagram).

Scope note: this orchestrator covers the Phase 3 speech pipeline only. It
stops after CLASSIFIED/COMPLETED — the AI analysis stages (ANALYZED,
SCORED, VALIDATED) are added by Phase 4's extension of this module, which
will call the LLM client for SALES calls between CLASSIFIED and STORED.

Idempotency: a call is looked up by `content_hash` (SHA-256 of the raw
audio bytes) BEFORE any processing happens.

- Hash matches a COMPLETED row -> skip entirely, audit-logged, file is
  still claimed (moved out of the inbox) so it stops being rescanned.
- Hash matches a FAILED/IN_PROGRESS row with retries remaining -> retried
  from a fresh attempt (the whole speech pipeline re-runs — it's cheap and
  deterministic enough that partial-stage resume isn't worth the added
  complexity for this prototype; see docs Section 10 trade-offs).
- Hash matches a FAILED row with retries exhausted -> skipped permanently,
  logged at ERROR so a human notices, file still claimed to stop the loop.
- No match -> new `Call` + `ProcessingStatus` row created.

Because `FolderSourceAdapter.mark_claimed()` only runs on a terminal
outcome (success, duplicate, or exhausted retries), a call that fails
mid-run simply stays in the inbox and is naturally retried on the next
`run_once()` — no separate retry scheduler needed for this prototype.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker

from fitnova.core.config import Settings
from fitnova.core.constants import CallType, PipelineStage, ProcessingStatusEnum
from fitnova.core.logging_config import get_logger
from fitnova.db.models import (
    Advisor,
    AudioMetadata,
    AuditLog,
    Call,
    CallMetric,
    PipelineBenchmark,
    ProcessingStatus,
    Transcript,
    TranscriptSegment,
)
from fitnova.diarization import diarize
from fitnova.ingestion.base import IngestionAdapter, RawCallRecord
from fitnova.ingestion.registry import build_default_adapters
from fitnova.pipeline.benchmarking import BenchmarkRecorder
from fitnova.pipeline.queue_manager import QueueManager
from fitnova.processing.audio_validation import AudioValidationError, analyze_audio
from fitnova.processing.call_classifier import classify_call
from fitnova.processing.normalizer import normalize
from fitnova.processing.pii_redaction import redact_segments
from fitnova.transcription.whisper_engine import WhisperTranscriber

logger = get_logger(__name__)


@dataclass
class OrchestrationResult:
    call_id: int | None
    content_hash: str
    outcome: str  # "completed" | "skipped_duplicate" | "skipped_exhausted" | "failed"
    call_type: str | None = None
    error: str | None = None


class SpeechPipelineOrchestrator:
    """Coordinates ingestion adapters + the speech pipeline for a batch run."""

    def __init__(
        self,
        settings: Settings,
        session_factory: sessionmaker[Session],
        adapters: list[IngestionAdapter] | None = None,
    ) -> None:
        self.settings = settings
        self.session_factory = session_factory
        self.adapters = adapters if adapters is not None else build_default_adapters(settings)
        self.transcriber = WhisperTranscriber(
            model_size=settings.whisper_model_size,
            device=settings.whisper_device,
            compute_type=settings.whisper_compute_type,
        )

    def run_once(self) -> list[OrchestrationResult]:
        """Scan every enabled adapter once and process whatever is new."""
        results: list[OrchestrationResult] = []
        for adapter in self.adapters:
            for record in adapter.fetch_new_calls():
                results.append(self._process_record(record, adapter))
        return results

    # -- single-call processing -------------------------------------------------

    def _process_record(
        self, record: RawCallRecord, adapter: IngestionAdapter
    ) -> OrchestrationResult:
        content_hash = _hash_file(record.audio_path)
        session = self.session_factory()

        try:
            existing_status = QueueManager(session).find_by_content_hash(content_hash)

            if existing_status and existing_status.status == ProcessingStatusEnum.COMPLETED:
                self._audit(
                    session, "Call", existing_status.call_id, "SKIPPED_DUPLICATE", content_hash
                )
                session.commit()
                adapter.mark_claimed(record)
                return OrchestrationResult(
                    existing_status.call_id, content_hash, "skipped_duplicate"
                )

            if existing_status and existing_status.status == ProcessingStatusEnum.FAILED:
                if existing_status.retry_count >= self.settings.max_processing_retries:
                    self._audit(
                        session, "Call", existing_status.call_id, "RETRY_EXHAUSTED", content_hash
                    )
                    session.commit()
                    adapter.mark_claimed(record)
                    logger.error("Call content_hash=%s exhausted retries, giving up", content_hash)
                    return OrchestrationResult(
                        existing_status.call_id,
                        content_hash,
                        "skipped_exhausted",
                        error=existing_status.last_error,
                    )

            call, status_row = self._get_or_create_call(
                session, record, content_hash, existing_status
            )
            session.commit()

        except (
            Exception
        ) as exc:  # noqa: BLE001 - pre-pipeline bookkeeping must never crash the batch
            session.rollback()
            logger.exception("Failed to prepare call for content_hash=%s", content_hash)
            return OrchestrationResult(None, content_hash, "failed", error=str(exc))
        finally:
            pass

        # -- run the actual speech pipeline in its own transaction ----------
        try:
            call_type = self._run_speech_pipeline(session, call, status_row, record)
            session.commit()
            adapter.mark_claimed(record)
            return OrchestrationResult(
                call.id, content_hash, "completed", call_type=call_type.value
            )

        except Exception as exc:  # noqa: BLE001 - any stage failure lands here
            session.rollback()
            self._record_failure(session, status_row.id, str(exc))
            logger.exception(
                "Pipeline failed for call_id=%s content_hash=%s", call.id, content_hash
            )
            return OrchestrationResult(call.id, content_hash, "failed", error=str(exc))

    def _get_or_create_call(
        self,
        session: Session,
        record: RawCallRecord,
        content_hash: str,
        existing_status: ProcessingStatus | None,
    ) -> tuple[Call, ProcessingStatus]:
        queue = QueueManager(session)
        advisor = self._resolve_advisor(session, record.advisor_external_id)

        if existing_status is not None:
            call = session.get(Call, existing_status.call_id)
            if call is None:  # pragma: no cover - defensive, should not happen
                raise RuntimeError(
                    f"ProcessingStatus references missing call_id={existing_status.call_id}"
                )
            queue.begin_retry(existing_status)
            return call, existing_status

        call = Call(
            advisor_id=advisor.id if advisor else None,
            source_system=record.source_system,
            source_call_id=record.source_call_id,
            customer_ref_hash=_hash_customer_ref(record.customer_ref),
            call_type=CallType.UNKNOWN,
            call_datetime=record.call_datetime,
            content_hash=content_hash,
        )
        session.add(call)
        session.flush()  # assign call.id

        status_row = queue.enqueue(call_id=call.id, content_hash=content_hash)

        if advisor is None:
            self._audit(
                session,
                "Call",
                call.id,
                "ADVISOR_UNRESOLVED",
                content_hash,
                extra={"advisor_external_id": record.advisor_external_id},
            )

        return call, status_row

    def _run_speech_pipeline(
        self, session: Session, call: Call, status_row: ProcessingStatus, record: RawCallRecord
    ) -> CallType:
        queue = QueueManager(session)
        recorder = BenchmarkRecorder()
        audio_path = record.audio_path

        # 1. Audio validation + metadata extraction
        with recorder.stage("audio_validation"):
            try:
                analysis = analyze_audio(audio_path, self.settings)
            except AudioValidationError as exc:
                raise RuntimeError(f"Audio validation failed: {exc}") from exc
        queue.advance(status_row, PipelineStage.INGESTED)

        call.duration_seconds = analysis.duration_seconds
        session.add(
            AudioMetadata(
                call_id=call.id,
                file_path=str(audio_path),
                file_format=analysis.file_format,
                sample_rate=analysis.sample_rate,
                channels=analysis.channels,
                file_size_bytes=analysis.file_size_bytes,
                audio_quality_flag=analysis.quality_flag,
            )
        )

        # 2. Transcription (automatic model fallback inside the transcriber)
        transcription_result = None
        if analysis.quality_flag.value != "SILENT":
            transcription_result = self.transcriber.transcribe(audio_path)
            recorder.record("transcription", transcription_result.elapsed_ms)
        else:
            recorder.record("transcription", 0.0)
        queue.advance(status_row, PipelineStage.TRANSCRIBED)

        whisper_segments = transcription_result.segments if transcription_result else []
        detected_language = transcription_result.language if transcription_result else None
        model_used = transcription_result.model_used if transcription_result else None

        # 3. Diarization
        with recorder.stage("diarization"):
            if analysis.quality_flag.value != "SILENT":
                diarized_turns, diarization_backend_used = diarize(audio_path, self.settings)
            else:
                diarized_turns, diarization_backend_used = [], "skipped_silent"
        queue.advance(status_row, PipelineStage.DIARIZED)

        # 4. Normalization (merge ASR + diarization, preserve timestamps)
        with recorder.stage("normalization"):
            normalized = normalize(whisper_segments, diarized_turns)
        queue.advance(status_row, PipelineStage.NORMALIZED)

        # 5. PII redaction (before persistence — redacted text is the only
        #    version anything downstream, including any future LLM call, sees)
        with recorder.stage("pii_redaction"):
            redacted_segments, findings = redact_segments(normalized.segments)
        queue.advance(status_row, PipelineStage.REDACTED)

        if findings:
            self._audit(
                session,
                "Call",
                call.id,
                "PII_REDACTED",
                status_row.content_hash,
                extra={
                    f.category: sum(1 for x in findings if x.category == f.category)
                    for f in findings
                },
            )

        # 6. Call classification (rule-based; overridden by PENDING_METADATA
        #    if the advisor could not be resolved at ingestion time)
        with recorder.stage("classification"):
            if call.advisor_id is None:
                call_type = CallType.PENDING_METADATA
                classification_reason = "Advisor could not be resolved at ingestion time"
            else:
                call_type, classification_reason = classify_call(
                    transcript=normalized,
                    duration_seconds=analysis.duration_seconds,
                    audio_quality_flag=analysis.quality_flag,
                    detected_language=detected_language,
                    settings=self.settings,
                )
        queue.advance(status_row, PipelineStage.CLASSIFIED)

        call.call_type = call_type
        call.language_detected = detected_language
        self._audit(
            session,
            "Call",
            call.id,
            "CLASSIFIED",
            status_row.content_hash,
            extra={"call_type": call_type.value, "reason": classification_reason},
        )

        # 7. Persist transcript + segments + metrics + benchmark
        with recorder.stage("db_write"):
            redacted_full_text = " ".join(seg.text for seg in redacted_segments)
            transcript = Transcript(
                call_id=call.id,
                raw_text=normalized.full_text,
                redacted_text=redacted_full_text,
                word_count=normalized.word_count,
                avg_confidence=normalized.avg_confidence,
            )
            session.add(transcript)
            session.flush()

            for seg in redacted_segments:
                session.add(
                    TranscriptSegment(
                        transcript_id=transcript.id,
                        segment_index=seg.segment_index,
                        speaker_label=seg.speaker_label,
                        start_time=seg.start_time,
                        end_time=seg.end_time,
                        text=seg.text,
                        confidence=seg.confidence,
                    )
                )

            session.add(CallMetric(call_id=call.id, **_compute_call_metrics(redacted_segments)))

        session.add(
            PipelineBenchmark(
                call_id=call.id,
                **recorder.build(
                    call_id=call.id,
                    audio_duration_seconds=analysis.duration_seconds,
                    whisper_model_used=model_used,
                    diarization_backend_used=diarization_backend_used,
                ).model_dump(exclude={"call_id"}),
            )
        )

        queue.mark_completed(status_row, final_stage=PipelineStage.CLASSIFIED)
        return call_type

    # -- helpers -----------------------------------------------------------

    def _resolve_advisor(self, session: Session, advisor_external_id: str | None) -> Advisor | None:
        if not advisor_external_id:
            return None
        return (
            session.query(Advisor).filter(Advisor.external_id == advisor_external_id).one_or_none()
        )

    def _record_failure(self, session: Session, status_id: int, error_message: str) -> None:
        status_row = session.get(ProcessingStatus, status_id)
        if status_row is None:  # pragma: no cover - defensive
            return
        QueueManager(session).mark_failed(status_row, error_message)
        session.commit()

    def _audit(
        self,
        session: Session,
        entity_type: str,
        entity_id: int | None,
        action: str,
        content_hash: str,
        extra: dict | None = None,
    ) -> None:
        details = {"content_hash": content_hash}
        if extra:
            details.update(extra)
        session.add(
            AuditLog(
                entity_type=entity_type,
                entity_id=entity_id,
                action=action,
                actor="SYSTEM",
                details=details,
            )
        )


def _hash_file(path: Path) -> str:
    """SHA-256 of the raw audio bytes — the idempotency key (docs Section
    5.3). Streamed in chunks so large recordings don't need to fit in
    memory at once."""
    digest = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _hash_customer_ref(customer_ref: str | None) -> str | None:
    if not customer_ref:
        return None
    return hashlib.sha256(customer_ref.encode("utf-8")).hexdigest()


def _compute_call_metrics(segments) -> dict:
    """Deterministic, non-LLM metrics from the final segment list —
    talk-time ratios, interruption count (adjacent segments with different
    speakers and near-zero gap), silence ratio, longest monologue."""
    from fitnova.core.constants import SpeakerLabel

    if not segments:
        return {
            "talk_ratio_advisor": None,
            "talk_ratio_customer": None,
            "interruption_count": 0,
            "silence_ratio": None,
            "longest_monologue_seconds": None,
        }

    advisor_time = sum(
        s.end_time - s.start_time for s in segments if s.speaker_label == SpeakerLabel.ADVISOR
    )
    customer_time = sum(
        s.end_time - s.start_time for s in segments if s.speaker_label == SpeakerLabel.CUSTOMER
    )
    total_talk_time = advisor_time + customer_time
    call_span = max((s.end_time for s in segments), default=0.0) - min(
        (s.start_time for s in segments), default=0.0
    )

    interruption_count = 0
    # strict=False is deliberate: segments and segments[1:] differ in length by
    # exactly one, by design, for pairwise iteration.
    for prev, curr in zip(segments, segments[1:], strict=False):
        if prev.speaker_label != curr.speaker_label and (curr.start_time - prev.end_time) < 0.15:
            interruption_count += 1

    longest_monologue = 0.0
    current_speaker = None
    current_start = None
    for seg in segments:
        if seg.speaker_label != current_speaker:
            current_speaker = seg.speaker_label
            current_start = seg.start_time
        longest_monologue = max(longest_monologue, seg.end_time - (current_start or seg.start_time))

    return {
        "talk_ratio_advisor": (advisor_time / total_talk_time) if total_talk_time else None,
        "talk_ratio_customer": (customer_time / total_talk_time) if total_talk_time else None,
        "interruption_count": interruption_count,
        "silence_ratio": max(0.0, (call_span - total_talk_time) / call_span) if call_span else None,
        "longest_monologue_seconds": longest_monologue,
    }
