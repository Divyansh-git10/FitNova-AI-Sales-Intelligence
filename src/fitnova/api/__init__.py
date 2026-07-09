"""FastAPI application (Phase 5).

`main.py` — app factory (`create_app()`) + module-level `app` for
`uvicorn fitnova.api.main:app`.
`deps.py` — shared dependencies: DB session, settings, placeholder role
auth (`X-Role` header).
`routers/` — calls, org hierarchy, analytics, issues/feedback,
observability/benchmarks/queue/health, export.

The Streamlit dashboard reads from `fitnova.db.repository` directly rather
than round-tripping through this API (documented exception, docs Section
4.7 Component Diagram) so it works without a second process running; the
CLI and any external client use this API."""
