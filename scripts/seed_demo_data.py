"""Phase 6 synthetic demo dataset.

Populates the database with a small, realistic org hierarchy and a
handful of demo calls covering every `CallType` branch the real pipeline
can produce, so a fresh clone has something to look at on the dashboard
immediately after `fitnova doctor` passes.

What is real and what is hand-authored here (read this before trusting
any number this script produces):

- **Real**: audio files are genuine, decodable WAV files (see
  `generate_demo_audio.py`) run through the REAL
  `fitnova.processing.audio_validation.analyze_audio()`. Call
  classification runs through the REAL `classify_call()`. PII redaction
  runs through the REAL `redact_segments()`. Talk-ratio/interruption/
  silence metrics run through the REAL `_compute_call_metrics()` (the
  exact same function `SpeechPipelineOrchestrator` uses). Queue state
  transitions go through the REAL `QueueManager`, mirroring the exact
  `PipelineStage` sequence the production orchestrator emits.
- **Hand-authored stand-in**: this environment cannot run real speech
  recognition on the synthetic tone WAVs (there is no real speech in
  them — see `generate_demo_audio.py`'s docstring for why), so the
  `TranscriptSegment` text for each demo call is hand-written dialogue,
  standing in for what Whisper + diarization would have produced from a
  real recording. This is clearly not derived from the audio bytes, and
  every other stage downstream of it treats it exactly like real ASR
  output — no shortcuts, no special-casing.
- **Never fabricated**: `Score`, `Issue`, and `CallInsight` rows are never
  written directly by this script. They only exist if you pass `--analyze`
  AND a real local Ollama server is reachable, in which case this script
  calls the exact same `AnalysisOrchestrator.run_batch()` the CLI's
  `fitnova analyze` command calls. If Ollama isn't reachable, seeded SALES
  calls are left unscored — exactly like any other real ingested call
  waiting on `fitnova analyze` — never given fake numbers.

Usage
-----
    python -m scripts.seed_demo_data              # seed once (idempotent)
    python -m scripts.seed_demo_data --force       # wipe previous demo org, reseed
    python -m scripts.seed_demo_data --analyze     # also run real analysis if Ollama is up
"""

from __future__ import annotations

import argparse
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sqlalchemy import select  # noqa: E402
from sqlalchemy.orm import Session, sessionmaker  # noqa: E402

from fitnova.bootstrap import bootstrap_app  # noqa: E402
from fitnova.core.constants import (  # noqa: E402
    CallType,
    PipelineStage,
    SourceSystem,
    SpeakerLabel,
)
from fitnova.core.logging_config import get_logger  # noqa: E402
from fitnova.db.models import (  # noqa: E402
    Advisor,
    AudioMetadata,
    AuditLog,
    Call,
    CallMetric,
    Organization,
    PipelineBenchmark,
    Team,
    Transcript,
    TranscriptSegment,
)
from fitnova.pipeline.benchmarking import BenchmarkRecorder  # noqa: E402
from fitnova.pipeline.orchestrator import (
    _compute_call_metrics,
    _hash_customer_ref,
    _hash_file,
)  # noqa: E402
from fitnova.pipeline.queue_manager import QueueManager  # noqa: E402
from fitnova.processing.audio_validation import analyze_audio  # noqa: E402
from fitnova.processing.call_classifier import classify_call  # noqa: E402
from fitnova.processing.normalizer import NormalizedSegment, NormalizedTranscript  # noqa: E402
from fitnova.processing.pii_redaction import redact_segments  # noqa: E402
from scripts.generate_demo_audio import generate_silence_wav, generate_tone_wav  # noqa: E402

logger = get_logger(__name__)

DEMO_ORG_NAME = "FitNova Wellness (Demo)"
DEMO_AUDIO_DIR = Path(__file__).resolve().parents[1] / "data" / "audio" / "demo_samples"

# Words-per-second used only to size the synthetic tone's duration to
# roughly match its hand-authored dialogue — a cosmetic realism touch, not
# something any downstream logic depends on.
_WORDS_PER_SECOND = 2.3


@dataclass
class DemoTurn:
    speaker: SpeakerLabel
    text: str


@dataclass
class DemoCall:
    key: str
    advisor_external_id: str | None  # None => simulates an unresolved advisor (PENDING_METADATA)
    dialogue: list[DemoTurn]
    detected_language: str = "en"
    min_duration_s: float = (
        0.0  # floor, e.g. to keep INTERNAL/SALES calls above wrong-number thresholds
    )
    silent: bool = False


# ---------------------------------------------------------------------------
# Demo org hierarchy
# ---------------------------------------------------------------------------

TEAMS = {
    "north": "Inside Sales - North",
    "south": "Inside Sales - South",
}

ADVISORS = [
    # (external_id, name, team_key)
    ("adv-priya-001", "Priya Sharma", "north"),
    ("adv-arjun-002", "Arjun Mehta", "north"),
    ("adv-neha-003", "Neha Kapoor", "south"),
]

# ---------------------------------------------------------------------------
# Demo calls: hand-authored dialogue covering every CallType branch
# ---------------------------------------------------------------------------

DEMO_CALLS: list[DemoCall] = [
    DemoCall(
        key="call_good_close",
        advisor_external_id="adv-priya-001",
        dialogue=[
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Hi, this is Priya calling from FitNova Wellness, am I speaking with Rohit?",
            ),
            DemoTurn(SpeakerLabel.CUSTOMER, "Yes, speaking."),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Great, thanks for your time. Before I say anything about our programs, can I ask what made you enquire with us in the first place?",
            ),
            DemoTurn(
                SpeakerLabel.CUSTOMER,
                "I've been trying to lose weight for a while, nothing structured has worked. I also have some lower back pain from sitting all day.",
            ),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "That makes sense, a lot of our members start exactly there. How long has the back pain been going on, and has a doctor looked at it?",
            ),
            DemoTurn(
                SpeakerLabel.CUSTOMER,
                "About eight months. I saw a physio once, they said core strength would help but I never followed up.",
            ),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Got it, that's really useful context, thank you for sharing that. Given the back concern, our trainers would start you on a low-impact mobility and core program before any heavier strength work, and we'd loop your physio's guidance in if you're comfortable sharing it.",
            ),
            DemoTurn(
                SpeakerLabel.CUSTOMER,
                "That sounds reasonable, I was worried you'd just push a generic plan on me.",
            ),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Definitely not, that's exactly why we do a trial session first, so the trainer can actually assess your mobility before anything is finalized. Would mornings or evenings work better for you?",
            ),
            DemoTurn(SpeakerLabel.CUSTOMER, "Evenings, after 6pm."),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Perfect, I can book you a free trial session this Thursday at 6:30pm with one of our mobility-focused trainers. Does that work?",
            ),
            DemoTurn(SpeakerLabel.CUSTOMER, "Yes, Thursday 6:30 works."),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Wonderful, I've booked that trial for you. There's no cost and no obligation to join after. I'll send a confirmation message with the address and what to bring. Anything else I can answer before then?",
            ),
            DemoTurn(SpeakerLabel.CUSTOMER, "No, that covers it. Thanks Priya."),
            DemoTurn(
                SpeakerLabel.ADVISOR, "Thank you, Rohit, looking forward to seeing you Thursday."
            ),
        ],
    ),
    DemoCall(
        key="call_compliance_risk",
        advisor_external_id="adv-arjun-002",
        dialogue=[
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Hello, Arjun here from FitNova. So you filled out our form about weight loss, right?",
            ),
            DemoTurn(
                SpeakerLabel.CUSTOMER,
                "Yeah, I want to lose about 15 kilos before my sister's wedding in three months.",
            ),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Three months, no problem at all, our program guarantees you'll lose 15 kilos in that time if you follow the plan, I've seen it happen every single time.",
            ),
            DemoTurn(SpeakerLabel.CUSTOMER, "Really? That's a big promise, is that safe?"),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Completely safe, don't worry about that, everyone loses weight fast on our program, it's basically guaranteed. Let's get you signed up today, the starter package is 15000 rupees.",
            ),
            DemoTurn(SpeakerLabel.CUSTOMER, "Is that the full price? Are there other charges?"),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "That's the base package, yes there's also a mandatory supplement kit and a facility fee we add later, but let's not worry about that now, the important thing is locking in today's discount.",
            ),
            DemoTurn(
                SpeakerLabel.CUSTOMER, "I'd really like to know the total cost before deciding."
            ),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "You're overthinking it honestly, everyone who signs up today gets the guaranteed results, you should just commit now before the offer closes in the next ten minutes.",
            ),
            DemoTurn(
                SpeakerLabel.CUSTOMER,
                "Okay, I guess... my number is 9876543210 if you need to confirm anything, and my email is rohit.customer@example.com",
            ),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Perfect, I've got 9876543210 and rohit.customer@example.com noted, I'll send the payment link right away.",
            ),
        ],
    ),
    DemoCall(
        key="call_weak_closing",
        advisor_external_id="adv-neha-003",
        dialogue=[
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Hi, this is Neha from FitNova Wellness, how are you doing today?",
            ),
            DemoTurn(SpeakerLabel.CUSTOMER, "I'm okay, a bit busy but go ahead."),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "No problem, I'll be quick. What are you hoping to work on, fitness-wise?",
            ),
            DemoTurn(
                SpeakerLabel.CUSTOMER,
                "Mostly just general fitness, maybe some strength training, I used to lift a few years ago.",
            ),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "That's great, we have strength programs for people getting back into it. We also have cardio classes, yoga, nutrition coaching, group sessions, personal training, and a few other things.",
            ),
            DemoTurn(
                SpeakerLabel.CUSTOMER,
                "That's a lot of options, I'm not sure which one is relevant honestly.",
            ),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Yeah there's a lot, I'll just send you a brochure with everything listed and you can pick whatever looks interesting.",
            ),
            DemoTurn(SpeakerLabel.CUSTOMER, "Sure, that works I guess."),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Sounds good, I'll email that over. Let me know if you have questions.",
            ),
            DemoTurn(SpeakerLabel.CUSTOMER, "Okay, will do. Bye."),
        ],
    ),
    DemoCall(
        key="call_wrong_number",
        advisor_external_id="adv-priya-001",
        dialogue=[
            DemoTurn(SpeakerLabel.ADVISOR, "Hello, is this Sameer speaking?"),
            DemoTurn(SpeakerLabel.CUSTOMER, "No, wrong number, sorry."),
            DemoTurn(SpeakerLabel.ADVISOR, "My apologies, have a good day."),
        ],
    ),
    DemoCall(
        key="call_internal_sync",
        advisor_external_id="adv-arjun-002",
        dialogue=[
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Hey, joining the daily sync now, are we still doing the pipeline review first?",
            ),
            DemoTurn(
                SpeakerLabel.CUSTOMER,
                "Yeah, team sync agenda has pipeline review, then blockers, then the new script rollout.",
            ),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Got it. My numbers are on track, closed two trials yesterday, one is stuck waiting on a callback.",
            ),
            DemoTurn(
                SpeakerLabel.CUSTOMER,
                "Nice, flag the stuck one in the internal meeting notes so the manager can follow up.",
            ),
            DemoTurn(
                SpeakerLabel.ADVISOR, "Will do, that's everything from my side for this sync."
            ),
        ],
        min_duration_s=25.0,
    ),
    DemoCall(
        key="call_unsupported_language",
        advisor_external_id="adv-neha-003",
        detected_language="fr",
        dialogue=[
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Bonjour, ici Neha de FitNova Wellness, est-ce que je parle avec Monsieur Dubois?",
            ),
            DemoTurn(
                SpeakerLabel.CUSTOMER,
                "Oui, c'est moi. Je suis interesse par un programme de remise en forme.",
            ),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Parfait, pouvez-vous me dire quel est votre objectif principal en ce moment?",
            ),
            DemoTurn(
                SpeakerLabel.CUSTOMER,
                "Je voudrais perdre du poids et ameliorer mon endurance avant l'ete.",
            ),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Tres bien, je vais transferer votre dossier a notre equipe francophone qui pourra mieux vous accompagner.",
            ),
        ],
        min_duration_s=25.0,
    ),
    DemoCall(
        key="call_pending_metadata",
        advisor_external_id=None,  # unresolved on purpose -> PENDING_METADATA
        dialogue=[
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Hi, this is FitNova Wellness calling, may I know who I'm speaking with?",
            ),
            DemoTurn(
                SpeakerLabel.CUSTOMER,
                "This is Karan, I filled out an interest form last week about personal training.",
            ),
            DemoTurn(
                SpeakerLabel.ADVISOR,
                "Great, I'd love to learn more about what you're looking for before I tell you about our programs.",
            ),
            DemoTurn(
                SpeakerLabel.CUSTOMER,
                "Sure, I mostly want help with consistency, I keep starting and stopping.",
            ),
        ],
        min_duration_s=25.0,
    ),
    DemoCall(
        key="call_silent",
        advisor_external_id="adv-neha-003",
        dialogue=[],
        silent=True,
    ),
]


# ---------------------------------------------------------------------------
# Seeding logic
# ---------------------------------------------------------------------------


def _get_or_create_org_hierarchy(session: Session) -> dict[str, Advisor]:
    org = session.execute(
        select(Organization).where(Organization.name == DEMO_ORG_NAME)
    ).scalar_one_or_none()
    if org is None:
        org = Organization(name=DEMO_ORG_NAME)
        session.add(org)
        session.flush()

    team_rows: dict[str, Team] = {}
    for key, name in TEAMS.items():
        team = session.execute(
            select(Team).where(Team.organization_id == org.id, Team.name == name)
        ).scalar_one_or_none()
        if team is None:
            team = Team(organization_id=org.id, name=name)
            session.add(team)
            session.flush()
        team_rows[key] = team

    advisor_rows: dict[str, Advisor] = {}
    for external_id, name, team_key in ADVISORS:
        advisor = session.execute(
            select(Advisor).where(Advisor.external_id == external_id)
        ).scalar_one_or_none()
        if advisor is None:
            advisor = Advisor(
                team_id=team_rows[team_key].id,
                name=name,
                email=f"{external_id.replace('adv-', '').replace('-', '.')}@fitnova-demo.example",
                external_id=external_id,
                is_active=True,
            )
            session.add(advisor)
            session.flush()
        advisor_rows[external_id] = advisor

    return advisor_rows


def _build_segments(dialogue: list[DemoTurn], total_duration: float) -> list[NormalizedSegment]:
    """Allocate sequential, non-overlapping timestamps proportional to each
    turn's word count, so segment timing plausibly fits the audio's real
    duration. A couple of turns are deliberately given a near-zero gap from
    the previous speaker to exercise the interruption-detection metric,
    the same way real overlapping speech would."""
    if not dialogue:
        return []

    word_counts = [max(len(turn.text.split()), 1) for turn in dialogue]
    total_words = sum(word_counts)
    gap_s = 0.4

    segments: list[NormalizedSegment] = []
    cursor = 0.5
    for i, (turn, wc) in enumerate(zip(dialogue, word_counts, strict=True)):
        duration = max((wc / total_words) * max(total_duration - 0.5, 1.0), 0.6)
        start = cursor
        end = start + duration
        segments.append(
            NormalizedSegment(
                segment_index=i,
                speaker_label=turn.speaker,
                start_time=round(start, 2),
                end_time=round(end, 2),
                text=turn.text,
                # No real ASR ran on hand-authored dialogue, so no
                # confidence score is fabricated for it — left null rather
                # than invented, same as a low-confidence real segment
                # would be handled downstream (nullable column).
                confidence=None,
            )
        )
        # Most turns have a natural pause; a couple are back-to-back to
        # produce a realistic, non-zero interruption_count.
        cursor = end + (0.05 if i % 5 == 4 else gap_s)

    return segments


def _seed_one_call(
    session: Session,
    settings,
    demo_call: DemoCall,
    advisors: dict[str, Advisor],
) -> Call | None:
    advisor = advisors.get(demo_call.advisor_external_id) if demo_call.advisor_external_id else None

    # -- synthesize real, decodable audio bytes --------------------------
    DEMO_AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    audio_path = DEMO_AUDIO_DIR / f"{demo_call.key}.wav"
    dialogue_word_count = sum(len(t.text.split()) for t in demo_call.dialogue)
    target_duration = max(dialogue_word_count / _WORDS_PER_SECOND, demo_call.min_duration_s, 3.0)

    if demo_call.silent:
        generate_silence_wav(audio_path, duration_s=8.0)
    else:
        # Vary frequency per call so files are trivially distinguishable and
        # never collide on content_hash. Uses zlib.crc32 (deterministic
        # across processes/runs), NOT the builtin hash() — str hashing is
        # randomized per-process (PYTHONHASHSEED) and would silently break
        # idempotency by regenerating different audio bytes every run.
        freq = 180.0 + (zlib.crc32(demo_call.key.encode("utf-8")) % 200)
        generate_tone_wav(audio_path, duration_s=target_duration, freq=freq)

    content_hash = _hash_file(audio_path)
    queue = QueueManager(session)
    existing_status = queue.find_by_content_hash(content_hash)
    if existing_status is not None:
        logger.info(
            "Demo call '%s' already seeded (content_hash=%s), skipping", demo_call.key, content_hash
        )
        return None

    # -- real audio validation -------------------------------------------
    recorder = BenchmarkRecorder()
    with recorder.stage("audio_validation"):
        analysis = analyze_audio(audio_path, settings)

    call = Call(
        advisor_id=advisor.id if advisor else None,
        source_system=SourceSystem.FOLDER,
        source_call_id=None,
        customer_ref_hash=_hash_customer_ref(f"demo-customer-{demo_call.key}"),
        call_type=CallType.UNKNOWN,
        call_datetime=None,
        duration_seconds=analysis.duration_seconds,
        content_hash=content_hash,
    )
    session.add(call)
    session.flush()

    status_row = queue.enqueue(call_id=call.id, content_hash=content_hash)
    queue.advance(status_row, PipelineStage.INGESTED)

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

    if advisor is None:
        session.add(
            AuditLog(
                entity_type="Call",
                entity_id=call.id,
                action="ADVISOR_UNRESOLVED",
                actor="SYSTEM",
                details={
                    "content_hash": content_hash,
                    "advisor_external_id": demo_call.advisor_external_id,
                },
            )
        )

    # -- hand-authored transcript standing in for ASR + diarization ------
    with recorder.stage("transcription"):
        segments = _build_segments(demo_call.dialogue, analysis.duration_seconds)
    queue.advance(status_row, PipelineStage.TRANSCRIBED)
    with recorder.stage("diarization"):
        pass  # speaker labels already assigned by hand-authored dialogue
    queue.advance(status_row, PipelineStage.DIARIZED)

    with recorder.stage("normalization"):
        full_text = " ".join(seg.text for seg in segments)
        word_count = len(full_text.split())
        normalized = NormalizedTranscript(
            segments=segments, full_text=full_text, word_count=word_count, avg_confidence=None
        )
    queue.advance(status_row, PipelineStage.NORMALIZED)

    # -- REAL PII redaction ------------------------------------------------
    with recorder.stage("pii_redaction"):
        redacted_segments, findings = redact_segments(normalized.segments)
    queue.advance(status_row, PipelineStage.REDACTED)

    if findings:
        session.add(
            AuditLog(
                entity_type="Call",
                entity_id=call.id,
                action="PII_REDACTED",
                actor="SYSTEM",
                details={
                    "content_hash": content_hash,
                    **{
                        f.category: sum(1 for x in findings if x.category == f.category)
                        for f in findings
                    },
                },
            )
        )

    # -- REAL classification (mirrors orchestrator's exact branching) ----
    with recorder.stage("classification"):
        if advisor is None:
            call_type = CallType.PENDING_METADATA
            reason = "Advisor could not be resolved at ingestion time"
        else:
            call_type, reason = classify_call(
                transcript=normalized,
                duration_seconds=analysis.duration_seconds,
                audio_quality_flag=analysis.quality_flag,
                detected_language=demo_call.detected_language,
                settings=settings,
            )
    queue.advance(status_row, PipelineStage.CLASSIFIED)

    call.call_type = call_type
    call.language_detected = demo_call.detected_language
    session.add(
        AuditLog(
            entity_type="Call",
            entity_id=call.id,
            action="CLASSIFIED",
            actor="SYSTEM",
            details={"content_hash": content_hash, "call_type": call_type.value, "reason": reason},
        )
    )
    session.add(
        AuditLog(
            entity_type="Call",
            entity_id=call.id,
            action="DEMO_DATA_SEEDED",
            actor="SYSTEM",
            details={
                "demo_key": demo_call.key,
                "note": "Transcript hand-authored; audio is a synthetic placeholder tone, not real speech.",
            },
        )
    )

    # -- persist transcript + segments + REAL metrics ----------------------
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
                whisper_model_used="demo-hand-authored",
                diarization_backend_used="demo-manual",
            ).model_dump(exclude={"call_id"}),
        )
    )

    queue.mark_completed(status_row, final_stage=PipelineStage.CLASSIFIED)
    logger.info(
        "Seeded demo call '%s' -> call_id=%s call_type=%s", demo_call.key, call.id, call_type.value
    )
    return call


def _wipe_demo_org(session: Session) -> None:
    """Delete every previously seeded demo call, then the demo org itself.

    Deleting the `Organization` row cascades to teams -> advisors -> their
    calls, but a `call_pending_metadata`-style demo call has
    `advisor_id = None` by design (it simulates an unresolved advisor) —
    it has no FK path from the org, so the cascade alone would leave it
    orphaned forever. Every demo call is tagged with a `DEMO_DATA_SEEDED`
    audit log entry at seed time specifically so `--force` can find and
    remove ALL of them, including advisor-less ones, before reseeding.
    """
    demo_call_ids = (
        session.execute(
            select(AuditLog.entity_id).where(
                AuditLog.entity_type == "Call", AuditLog.action == "DEMO_DATA_SEEDED"
            )
        )
        .scalars()
        .all()
    )
    if demo_call_ids:
        calls = session.execute(select(Call).where(Call.id.in_(demo_call_ids))).scalars().all()
        for call in calls:
            session.delete(call)
        session.flush()
        logger.info("Wiped %d previously seeded demo call(s)", len(calls))

    org = session.execute(
        select(Organization).where(Organization.name == DEMO_ORG_NAME)
    ).scalar_one_or_none()
    if org is not None:
        session.delete(org)  # cascades to teams -> advisors (any remaining, non-demo-call-linked)
        session.flush()
        logger.info("Wiped existing demo organization")


def seed(session_factory: sessionmaker[Session], settings, force: bool = False) -> list[Call]:
    session = session_factory()
    created: list[Call] = []
    try:
        if force:
            _wipe_demo_org(session)
            session.commit()

        advisors = _get_or_create_org_hierarchy(session)
        session.commit()

        for demo_call in DEMO_CALLS:
            try:
                call = _seed_one_call(session, settings, demo_call, advisors)
                session.commit()
                if call is not None:
                    created.append(call)
            except Exception:  # noqa: BLE001 - one bad demo call must not stop the rest
                session.rollback()
                logger.exception("Failed to seed demo call '%s'", demo_call.key)
        return created
    finally:
        session.close()


def _maybe_run_analysis(settings, session_factory: sessionmaker[Session]) -> None:
    from fitnova.analysis.ollama_client import OllamaClient
    from fitnova.pipeline.analysis_orchestrator import AnalysisOrchestrator

    # OllamaClient.get_model_version() is deliberately "best-effort, never
    # raises" (it's observability metadata, not a health gate) — it
    # returns the literal string "unknown" on any failure rather than
    # raising. `version != "unknown"` is the exact reachability heuristic
    # `fitnova doctor` already uses; reused here rather than inventing a
    # second way to answer the same question.
    version = OllamaClient(settings).get_model_version()
    if version == "unknown":
        print(
            "[seed_demo_data] Ollama not reachable — seeded SALES calls are left unscored, "
            "exactly like any real ingested call. Run `fitnova analyze` once a local Ollama "
            "server is up.",
            file=sys.stderr,
        )
        return

    print(
        f"[seed_demo_data] Ollama reachable (model={settings.ollama_model}, version={version}) — analyzing demo calls...",
        file=sys.stderr,
    )
    orchestrator = AnalysisOrchestrator(settings, session_factory)
    results = orchestrator.run_batch()
    for r in results:
        print(
            f"  call_id={r.call_id} outcome={r.outcome} overall_quality={r.overall_quality} error={r.error}",
            file=sys.stderr,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Delete any previously seeded demo org and reseed from scratch.",
    )
    parser.add_argument(
        "--analyze",
        action="store_true",
        help="Also run real AnalysisOrchestrator.run_batch() if Ollama is reachable.",
    )
    args = parser.parse_args()

    container = bootstrap_app()
    settings = container.settings()
    session_factory = container.session_factory()

    created = seed(session_factory, settings, force=args.force)
    print(
        f"[seed_demo_data] Seeded {len(created)} new demo call(s) (of {len(DEMO_CALLS)} defined).",
        file=sys.stderr,
    )
    if not created:
        print(
            "[seed_demo_data] (0 new means the demo dataset was already seeded — use --force to reseed.)",
            file=sys.stderr,
        )

    if args.analyze:
        _maybe_run_analysis(settings, session_factory)
    else:
        print(
            "[seed_demo_data] Run with --analyze (and a local Ollama server up) to also score the demo SALES calls.",
            file=sys.stderr,
        )


if __name__ == "__main__":
    main()
