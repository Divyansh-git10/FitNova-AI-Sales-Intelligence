# Release Notes — v1.0.0-rc1

**FitNova Sales Call Intelligence** — a locally-run pipeline that
transcribes, diarizes, scores, and flags issues in sales call recordings,
surfaced through a REST API, a CLI, and a role-based dashboard.

This is a **Release Candidate**: feature-complete, tested, and documented,
built as a from-scratch AI Engineering prototype rather than a
production SaaS product. Read "Known limitations" below before treating
any output as authoritative.

## What's in this release

- **Speech pipeline**: audio validation, Whisper transcription (automatic
  model-size fallback), diarization (pyannote or a deterministic
  fallback), PII redaction, rule-based call classification.
- **AI analysis engine**: a 9-dimension scoring rubric, a 10-type issue
  taxonomy with evidence validation (every flagged issue must cite a real,
  verbatim transcript quote), and generated coaching insights — all via a
  local Ollama server, with confidence calibration on every score and
  issue.
- **Three front doors onto one shared data layer**: a 22-endpoint REST
  API, a 7-command CLI (`fitnova ingest / analyze / status / dashboard /
  export / benchmark / doctor`), and a role-aware Streamlit dashboard
  (Sales Director / Team Leader / Advisor views) — all reading through the
  same `fitnova.db.repository` functions, so a number can never disagree
  between them.
- **Export**: CSV (calls, issues) and PDF (call report, advisor scorecard).
- **Observability**: pipeline benchmarking (Real Time Factor), LLM
  latency/retry/success tracking, a processing queue with explicit stages.
- **Demo tooling**: a synthetic demo dataset covering every call
  classification outcome, an end-to-end narrated demo script, and a video
  walkthrough script.
- **220 tests**, all passing; `black`/`ruff` clean across the codebase.

## Requirements

Python 3.11+, `ffmpeg` on PATH, and (optional, for AI scoring) a local
[Ollama](https://ollama.com) server. See `docs/SETUP_WINDOWS.md` /
`docs/SETUP_LINUX.md` for step-by-step setup, and `fitnova doctor` to
check what's actually available in your environment.

## Known limitations

- **Authentication is a placeholder.** `fitnova.api.deps.get_current_role`
  reads an `X-Role` header with no token verification — it's the seam a
  real auth system (OAuth2/JWT) would plug into, not a security boundary.
  Do not expose this API on an untrusted network as-is.
- **PII redaction is regex-based**, not a full NER model — an intentional
  trade-off for a lightweight, auditable pass that runs on every call
  without depending on another heavy model. It has known false negatives
  and occasional false positives; see `pii_redaction.py`'s docstring.
- **Single-node, single-database.** SQLite, one process per surface (API/
  CLI/dashboard). This is a local prototype, not designed for concurrent
  multi-user production load.
- **The dashboard reads the database directly**, not through the REST
  API — a deliberate simplification for a local single-user setup,
  documented in `docs/01_PHASE1_DESIGN.md` Section 4.7.
- **Diarization's fallback backend is VAD-based, not speaker-ID based** —
  it separates turns by voice-activity timing, not by who is actually
  speaking, when `pyannote.audio` (which requires a HuggingFace token and
  model download) isn't configured.
- **No offline text-to-speech is available in every environment this
  project might run in**, so the shipped demo dataset's audio is
  synthetic placeholder tone, not real speech — see
  `scripts/generate_demo_audio.py`'s docstring. Drop real recordings into
  `data/audio/inbox/` for the fully real path.

See `docs/FINAL_PROJECT_REPORT.md` for the full design-decisions,
trade-offs, and future-improvements writeup.

## Upgrade / migration notes

This is the first tagged release — no prior version to migrate from.
Future schema changes will need an explicit migration story (there is no
Alembic integration yet; see the report's "Future improvements" section).
