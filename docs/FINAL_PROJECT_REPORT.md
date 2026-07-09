# Final Project Report

**FitNova Sales Call Intelligence — Release Candidate v1.0**

This report summarizes the architecture, the design decisions made along
the way, the trade-offs those decisions imply, the system's known
limitations, and where it would go next. It's written for someone
evaluating the finished system, not someone building it — for the
build-order narrative and requirement-by-requirement traceability, see
[`docs/01_PHASE1_DESIGN.md`](01_PHASE1_DESIGN.md), which was written
first and kept up to date as each phase landed.

## 1. What this system does

Given a folder of sales call recordings, FitNova:

1. Ingests them idempotently (by content hash), classifies each as a real
   sales call or an excluded type (wrong number, internal call, no
   speech, unsupported language, or unresolved metadata),
2. transcribes and diarizes real sales calls, redacts PII before
   anything downstream sees the text,
3. scores each call against a 9-dimension rubric, flags issues from a
   10-type taxonomy with every flag grounded in a verbatim transcript
   quote, and generates a coaching insight,
4. and surfaces all of it through a REST API, a CLI, and a role-aware
   dashboard that never disagree with each other, because all three read
   through the same repository layer.

Everything runs on one machine: SQLite for storage, `faster-whisper` for
transcription, a local Ollama server for the LLM stages. Nothing is sent
to a third-party API.

## 2. Architecture summary

The pipeline is a strict pipe-and-filter chain, not a framework or an
agentic loop: ingest -> validate audio -> transcribe -> diarize ->
normalize -> redact -> classify -> (if SALES) score -> detect issues ->
validate evidence -> generate insight -> persist. Every stage writes to
an explicit `processing_status` row tracking the exact pipeline stage,
so a failure at any point is visible on the dashboard's queue view, not
silently swallowed.

Three "front doors" — the FastAPI app, the CLI, and the Streamlit
dashboard — sit on top of one shared query/aggregation layer
(`fitnova.db.repository`). No surface computes its own version of "what's
the average score for this advisor" independently; they all call the same
function. Exports (CSV, PDF) work the same way through
`fitnova.reporting`.

See [`docs/architecture/architecture.png`](architecture/architecture.png)
for the data-flow diagram and `docs/01_PHASE1_DESIGN.md` Section 4 for the
full Mermaid set (sequence, deployment, component diagrams).

## 3. Design decisions and their trade-offs

**The database is the queue.** There's no separate task broker (Celery,
RQ, etc.) — `processing_status` rows in SQLite, with an explicit
`PipelineStage` enum, are the entire queue. This keeps the whole system
to "one process, one file-based database" for local use, at the cost of
not being horizontally scalable — fine for a single-user local prototype,
wrong for a multi-tenant production service.

**Rule-based classification gates the LLM, not the other way around.**
`call_classifier.py` decides SALES/WRONG_NUMBER/INTERNAL/NO_SPEECH/
UNSUPPORTED_LANGUAGE with cheap, deterministic heuristics (word count,
duration, keyword match) before any LLM call happens. This means the
expensive model is never invoked to answer a question arithmetic can
already answer, and classification is instant and free — but it also
means classification quality is bounded by how good those heuristics are;
an ambiguous short call that's actually a real sales conversation could
be misclassified as WRONG_NUMBER. This is a deliberate, documented trade-
off (see `call_classifier.py`'s docstring), not an oversight.

**Every LLM-flagged issue must cite a real quote, or it's discarded.**
`evidence_validator.py` fuzzy-matches every `quoted_text` the LLM returns
against the actual transcript (via `rapidfuzz`, threshold configurable in
`issue_rules.yaml`). An issue that can't be matched is marked
`is_validated=False` and excluded from scoring aggregates and the default
dashboard view — visible in an audit log, never silently dropped, but
never trusted as fact either. This is the system's primary
hallucination-prevention mechanism, more load-bearing than prompt
engineering alone.

**PII redaction is regex-based, not a NER model.** A lightweight,
auditable pass (email/phone/PAN/Aadhaar/card patterns) that runs on every
call without needing another heavy model, versus a proper named-entity
recognizer that would catch more edge cases but cost more compute and
another point of failure. Chosen deliberately for a local-first
prototype; documented false-negative/false-positive trade-off in
`pii_redaction.py`.

**The dashboard reads the database directly, not through the API.** This
breaks the "independent front doors" framing slightly — it's a documented
exception, justified by local single-user simplicity (no need to run a
second server just for the dashboard to function). In a real multi-user
deployment this would need to change.

**Authentication is a placeholder by design, not by oversight.**
`get_current_role()` reads an `X-Role` header with zero verification. The
assignment's scope is the intelligence pipeline, not an auth system; this
is the seam a real OAuth2/JWT layer would plug into later, made explicit
rather than silently absent.

**Confidence is calibrated and persisted, not computed on the fly.**
Every score dimension and every issue gets a LOW/MEDIUM/HIGH label
alongside its raw numeric confidence, computed once at the moment of
scoring against thresholds in `.env`, and stored — so historical records
stay interpretable even if the thresholds change later.

## 4. Hallucination prevention (the assignment's core requirement)

Four independent mechanisms, not one:

1. **Structured output contracts.** Every LLM call is bound to a Pydantic
   response schema (`LLMScoringResponse`, `LLMIssueResponse`, etc.) — a
   response that doesn't parse is a retry, not a silent pass-through.
2. **Closed enums.** `IssueType`, `CallType`, `Severity` are fixed Python
   enums; the LLM selects from a closed set and can never invent a new
   category.
3. **Evidence validation.** Described above — the single most important
   mechanism, since it checks the LLM's claim against ground truth
   (the real transcript) rather than just checking the claim's shape.
4. **Confidence calibration surfaced, not hidden.** A LOW-confidence issue
   is shown as LOW-confidence, not silently smoothed into the same visual
   weight as a HIGH-confidence one.

None of these guarantee correctness — an LLM can still misjudge tone or
context — but together they make fabrication (inventing a quote or a
category that doesn't exist) structurally difficult rather than merely
discouraged by prompt wording.

## 5. Testing approach

220 tests: unit tests per pipeline stage (classification, redaction,
scoring, evidence validation), integration tests for full orchestrator
runs (speech pipeline end-to-end, analysis batch end-to-end), API tests
(every endpoint, via `TestClient` against a hermetic in-memory SQLite
database), CLI tests (via Typer's `CliRunner`), and Streamlit smoke tests
(via `streamlit.testing.v1.AppTest`). External services (Ollama, Whisper
model downloads) are mocked in tests for hermeticity and speed — the
application code itself is never mocked or bypassed.

## 6. Known limitations

See [`RELEASE_NOTES.md`](../RELEASE_NOTES.md) for the full list. The
short version: authentication is a placeholder, PII redaction is
regex-based, the system is single-node/single-database, the dashboard's
DB access is a documented architectural exception, the diarization
fallback is voice-activity-based rather than true speaker
identification, and the demo dataset's audio is synthetic tone (not real
speech) because no offline TTS or internet access is guaranteed in every
environment this project might run in.

## 7. Future improvements

Roughly in the order they'd matter for turning this into a real product,
not in the order they'd be easiest to build:

- **Real authentication** (OAuth2/JWT) replacing the `X-Role` placeholder,
  with the dashboard and API both enforcing it — the single highest-
  priority gap for anything beyond a local demo.
- **A real task queue** (Celery/RQ + Redis, or an async worker pool)
  replacing the DB-as-queue pattern, enabling concurrent processing and
  horizontal scaling beyond one machine.
- **A proper database migration tool** (Alembic) — schema changes
  currently require `Base.metadata.create_all()` on a fresh database;
  there's no upgrade path for an existing one.
- **A managed vector/semantic search layer** over transcripts, for
  free-text search across calls rather than only structured filters.
- **A real NER-based PII redaction model**, or at minimum a
  configurable second-pass reviewer flow for redaction misses.
- **True speaker diarization** (always requiring `pyannote.audio` or an
  equivalent) rather than falling back to VAD-based turn splitting when
  a HuggingFace token isn't configured.
- **A feedback-driven scoring recalibration loop** — currently, contested/
  confirmed issue feedback is recorded (`Feedback`, `AuditLog`) but never
  fed back into prompt tuning or few-shot examples; closing that loop
  would let the system improve from real reviewer corrections over time.
- **Multi-tenant support** — the schema already supports multiple
  organizations (see `docs/01_PHASE1_DESIGN.md` Section 3, assumption 5),
  but nothing enforces tenant isolation at the query or auth layer yet.
- **Streaming/near-real-time ingestion** (webhook-based telephony/dialer
  adapter) rather than folder-watching — `IngestionAdapter`'s interface
  was designed to support this without touching the rest of the pipeline,
  but no such adapter has been built yet.
- **Containerization** (`docker-compose.yml` wrapping the API, dashboard,
  and Ollama as services) for easier onboarding — deliberately deferred
  per `docs/01_PHASE1_DESIGN.md` Section 4.6's trade-off notes, since a
  from-scratch local Python setup was judged more transparent for this
  assignment's purposes.

## 8. Summary

The system satisfies the assignment's core ask — an AI pipeline that
transcribes, scores, and flags sales calls without fabricating results —
with a modular, tested, documented codebase where every stage's output
traces back to real input (a real transcript segment, a real audio file,
a real repository query). The gaps that remain are the ones expected of
a scoped engineering prototype rather than a production platform:
authentication, horizontal scale, and true multi-tenancy — each
explicitly called out above rather than quietly absent.
