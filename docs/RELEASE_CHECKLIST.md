# Release Checklist — v1.0.0-rc1

Every item below was actually run and verified during this release pass,
not just written down. Where a caveat applies, it's stated plainly rather
than glossed over.

| # | Item | Status | Notes |
|---|---|---|---|
| 1 | Architecture PNG export | ✅ Done | `docs/architecture/architecture.png`, rendered via Graphviz from `architecture.dot` |
| 2 | Mermaid SVG export | ✅ Done (adapted) | No offline Mermaid renderer is available without installing a headless Chromium (no internet access in the build environment); the same architecture diagram was authored directly in Graphviz and rendered to `docs/architecture/architecture.svg`. The original Mermaid diagrams remain in `docs/01_PHASE1_DESIGN.md` Section 4 and render natively on GitHub. |
| 3 | Dashboard screenshots | ✅ Done (partial, documented) | No headless browser is installable in this build environment (Playwright needs a ~150-300MB Chromium download with no internet access). `docs/screenshots/dashboard_*_preview.svg` are real-data-driven layout renders, not literal browser screenshots — clearly labeled as such, with exact instructions in `docs/screenshots/README.md` for capturing the real thing in ~30 seconds. |
| 4 | CLI screenshots | ✅ Done | `docs/screenshots/cli_*.svg` — real Rich terminal recordings of actual `fitnova doctor/status/ingest/analyze/benchmark` runs against a freshly seeded database. |
| 5 | API screenshots | ✅ Done | `docs/screenshots/api_walkthrough.svg` — real Rich terminal recording of real HTTP requests against the actual FastAPI ASGI app. |
| 6 | GitHub badges | ✅ Done | Status, Python version, test count, lint status, license, "runs locally" badges in `README.md` header. |
| 7 | Windows setup guide | ✅ Done | `docs/SETUP_WINDOWS.md` |
| 8 | Linux setup guide | ✅ Done | `docs/SETUP_LINUX.md` |
| 9 | Final README | ✅ Done | Rewritten `README.md`: badges, quick start, feature list, what's-real-vs-placeholder, architecture, doc index, project structure |
| 10 | Final project report | ✅ Done | `docs/FINAL_PROJECT_REPORT.md`: architecture summary, design decisions + trade-offs, hallucination-prevention mechanisms, testing approach, known limitations, future improvements |
| 11 | Changelog | ✅ Done | `CHANGELOG.md`, grouped by phase (1 through 6/RC) |
| 12 | Release notes | ✅ Done | `RELEASE_NOTES.md`: what's in this release, requirements, known limitations, upgrade notes |
| 13 | LICENSE | ✅ Done | MIT, `LICENSE` |
| 14 | Remove dead code | ✅ Done | Removed an unused `soundfile` dependency (audio decoding has always gone through `pydub`); fixed 4 genuinely-unused local variables in tests (one of which was masking a real test bug — see Changelog); no `TODO`/`FIXME` found anywhere in the codebase |
| 15 | Remove placeholder files | ✅ Done | Removed the never-populated `samples/audio/` and `samples/transcripts/` scaffold directories (superseded by `data/audio/demo_samples/` and `tests/conftest.py`'s WAV fixtures) |
| 16 | Verify imports | ✅ Done | `ruff check` (F401/F811/F821 rules) across `src/`, `dashboard/`, `scripts/`, `tests/` — zero findings |
| 17 | Verify formatting | ✅ Done | `black --check` — clean, 146 files |
| 18 | Run Black | ✅ Done | Applied across the whole codebase (57 files reformatted — first time it had been run project-wide in one pass) |
| 19 | Run Ruff | ✅ Done | `select = ["E", "F", "I", "UP", "B"]`, zero findings after fixes; 4 rules deliberately ignored project-wide with documented justification in `pyproject.toml` (FastAPI/Typer's required default-argument pattern, SQLAlchemy's required quoted forward-references, and a Python-3.10-testability consideration around `datetime.UTC` — none are correctness issues) |
| 20 | Run complete pytest suite | ✅ Done | **220 / 220 passing** |
| 21 | Verify every command in README | ✅ Done | Every command in the Quick Start and "Running it" sections was actually executed against a fresh environment. Caught and fixed a real gap: the original instructions never ran `pip install -e .`, so the `fitnova` console command wouldn't have existed — added to the README and both setup guides. |
| 22 | Verify dashboard launches | ✅ Done | `fitnova dashboard` started via the real installed console script; `GET /` returned `200` |
| 23 | Verify FastAPI launches | ✅ Done | `uvicorn fitnova.api.main:app` started; `/health`, `/`, and `/docs` all returned `200` with real data from a seeded database |
| 24 | Verify CLI launches | ✅ Done | `pip install -e .` + `fitnova doctor/status/ingest/benchmark/export` all run via the actual registered console script, not just `python -m` |
| 25 | Generate final submission checklist | ✅ Done | This document |

## Test suite summary

- **220 tests total**, all passing (205 non-dashboard + 15 Streamlit
  `AppTest` smoke tests, run separately due to a sandbox tooling timeout
  constraint unrelated to the tests themselves).
- Covers: config/settings, DB models, every speech-pipeline stage
  (audio validation, Whisper fallback, diarization fallback, normalizer,
  PII redaction, call classifier), every AI-analysis stage (Ollama client,
  LLM client, prompt manager, confidence calibration, scoring engine,
  issue detector, evidence validator, insight generator), the processing
  queue and benchmarking, both end-to-end orchestrators, the repository
  layer, every REST API endpoint, the CLI, PDF/CSV reporting, the
  Streamlit dashboard, and the Phase 6 demo dataset/demo script.

## What "verified" means here

Every check above was actually executed in this session against real
code — not asserted from memory. Where a tool or dependency wasn't
available in this build environment (a headless browser for pixel-exact
screenshots, for instance), that's stated explicitly rather than silently
worked around, consistent with this project's standing rule: never
fabricate an output, including in the release documentation itself.

## Known environment-specific note

This release was assembled in a sandboxed Linux build environment without
general internet access (no `pip install` of packages requiring a
download beyond what was already cached, no headless-browser binary
download). Nothing about the *shipped* project depends on that
environment — `requirements.txt`, `pyproject.toml`, and both setup guides
describe the real target environment (Python 3.11, `ffmpeg`, optionally
Ollama and `pyannote.audio`) and were validated as accurate through the
commands actually being run, not assumed.
