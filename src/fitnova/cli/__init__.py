"""Typer CLI (Phase 5).

`main.py` exposes `fitnova ingest|analyze|status|dashboard|export|
benchmark|doctor`, all resolving dependencies via `bootstrap_app()` and
reading through `fitnova.db.repository` — the same layer the API and
dashboard use, so a number printed by the CLI never disagrees with what
the dashboard shows."""
