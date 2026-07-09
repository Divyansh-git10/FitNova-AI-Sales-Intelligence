# Changelog

All notable changes to this project are documented here. Format loosely
follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); entries
are grouped by the project's own phase structure rather than dates, since
this was built as a single continuous phased effort rather than a
traditionally released product.

## [1.0.0-rc1] — Release Candidate (Phase 6)

Final polishing pass. No new product features — release engineering only.

### Added
- Synthetic demo dataset (`scripts/seed_demo_data.py`): a demo org hierarchy
  and 8 calls covering every `CallType` the real classifier can produce,
  built on hand-authored transcript text run through the real
  classification/PII-redaction/metrics pipeline (never fabricated scores).
- Synthetic demo audio generator (`scripts/generate_demo_audio.py`):
  real, decodable placeholder WAV files, honestly labeled as synthetic
  since no offline TTS or internet access is available in every build
  environment this project might run in.
- End-to-end demo script (`scripts/demo.py`) and a scene-by-scene video
  walkthrough script (`docs/DEMO_VIDEO_SCRIPT.md`).
- Release-engineering capture tools: `scripts/capture_screenshots.py`
  (real Rich-terminal SVG captures of CLI/API output) and
  `scripts/render_dashboard_previews.py` (real-data-driven SVG page
  previews, for use where a literal browser screenshot isn't available).
- Architecture diagram rendered to PNG and SVG (`docs/architecture/`).
- `docs/SETUP_WINDOWS.md`, `docs/SETUP_LINUX.md`, `docs/FINAL_PROJECT_REPORT.md`,
  `docs/RELEASE_CHECKLIST.md`, this changelog, `RELEASE_NOTES.md`, `LICENSE` (MIT).
- 10 new tests covering the demo dataset and demo script (`test_seed_demo_data.py`,
  `test_demo_script.py`).

### Fixed
- `seed_demo_data.py` used Python's per-process-randomized `hash()` to vary
  demo audio tone frequency, which silently regenerated different audio
  bytes (and thus different `content_hash`) on every run — breaking the
  script's idempotency guarantee. Switched to deterministic `zlib.crc32`.
- `seed_demo_data.py --force` didn't clean up the one demo call with
  `advisor_id = None` (the `PENDING_METADATA` scenario), since it has no
  foreign-key path from the demo `Organization` for a cascade delete to
  reach — it now finds and removes every previously seeded call via its
  `DEMO_DATA_SEEDED` audit-log tag before reseeding.
- Both the demo seed script and `scripts/demo.py` relied on
  `OllamaClient.get_model_version()` raising an exception to detect "Ollama
  unreachable" — it's deliberately designed to never raise (it returns the
  string `"unknown"` instead), so the check silently always reported
  "reachable" and then ran a slow, loudly-failing analysis batch. Fixed to
  use the same `version != "unknown"` heuristic `fitnova doctor` already
  uses.
- `tests/test_repository.py::test_get_issue_with_context_returns_surrounding_segments`
  constructed a `TranscriptSegment` intended to test context retrieval but
  never called `session.add()` on it, so the segment was silently never
  persisted; the test still passed only because other seeded segments
  happened to satisfy the assertion. Now actually added and committed.
- Removed an unused `soundfile` dependency from `requirements.txt` — audio
  decoding has always gone through `pydub` (see `audio_validation.py`'s
  docstring for why); `soundfile` was never actually imported anywhere.
- Removed the unused `samples/audio/` and `samples/transcripts/` scaffold
  directories — never populated, superseded by `data/audio/demo_samples/`
  (generated on demand by the seed script) and by `tests/conftest.py`'s
  in-memory WAV fixtures.

### Changed
- Ran `black` and `ruff` across the entire codebase for the first time as
  a single pass (57 files reformatted, ~120 lint findings resolved); see
  `pyproject.toml`'s `[tool.ruff.lint]` section for the handful of
  deliberately-ignored rules (FastAPI/Typer's required `Depends()`/
  `typer.Option()` default-argument pattern, SQLAlchemy's required quoted
  forward-reference annotations, and a Python-3.10-testability
  consideration around `datetime.UTC`) and why each is a documented
  exception rather than a bug.

## [Phase 5] — Production Interface Layer

- FastAPI REST API: 22 endpoints across calls, org hierarchy, analytics,
  issues/feedback, observability, and export.
- Typer CLI: `ingest`, `analyze`, `status`, `dashboard`, `export`,
  `benchmark`, `doctor`.
- Streamlit dashboard: role-aware Home, Executive Analytics, Advisor
  Scorecards, Issue Drilldown, Transcript & Evidence Replay, Observability
  & Health.
- Shared `fitnova.db.repository` layer consumed identically by the API,
  CLI, and dashboard, and a shared `fitnova.reporting` module (CSV/PDF)
  consumed identically by all three export surfaces.
- 79 new tests (210 total).

## [Phase 4] — AI Analysis Engine

- Ollama-backed LLM client: structured, versioned, retried, observed.
- Scoring engine (9-dimension rubric), issue detector (10-type taxonomy),
  evidence validator (every flagged issue must cite a real, verbatim
  transcript quote or it's rejected), insight generator.
- Confidence calibration (numeric confidence -> LOW/MEDIUM/HIGH label,
  persisted at the moment of scoring).
- Batch analysis orchestrator with per-call failure isolation and retry
  exhaustion reporting.
- 49 new tests (131 total).

## [Phase 3] — Speech Pipeline

- Ingestion layer: pluggable `IngestionAdapter`s (folder watcher shipped;
  CRM stub for future sources), idempotent by SHA-256 content hash.
- Audio validation and metadata extraction (`pydub`), with an explicit
  `AudioQualityFlag` (GOOD/POOR/SILENT) rather than hard failure on quiet
  or short recordings.
- Transcription via `faster-whisper` with automatic model-size fallback
  (large-v3 -> tiny) on load/inference failure.
- Diarization via `pyannote.audio` (optional) or a deterministic
  VAD-based fallback.
- Transcript normalization, PII redaction (before anything downstream —
  including any future LLM call — ever sees the transcript), and
  rule-based call classification.
- Processing queue (`processing_status` table) with explicit pipeline
  stages and idempotent retry handling.
- Pipeline benchmarking (per-stage timing, Real Time Factor).

## [Phase 2] — Foundations

- Externalized, schema-validated configuration (`config/weights.yaml`,
  `config/issue_rules.yaml`, `.env`).
- Core enums, structured logging, dependency-injection container,
  application bootstrap.
- Full 16-table SQLAlchemy schema and matching Pydantic I/O contracts.

## [Phase 1] — Design

- Requirements traceability matrix, architecture diagrams (data-flow,
  deployment, component), database ERD, scoring rubric, issue taxonomy,
  hallucination-prevention design, and documented assumptions/edge-case
  handling — `docs/01_PHASE1_DESIGN.md`.
