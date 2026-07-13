"""FastAPI application factory.

`create_app()` builds a fresh `FastAPI` instance wiring every router; a
module-level `app` is provided for `uvicorn fitnova.api.main:app`. Tests
call `create_app()` directly so each test gets an isolated app instance
with its own dependency overrides (see `tests/conftest.py`)."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fitnova.api.routers import analytics, calls, export, issues, observability, org_hierarchy
from fitnova.core.logging_config import get_logger

logger = get_logger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="FitNova Sales Call Intelligence API",
        description=(
            "REST API over the FitNova pipeline: calls, transcripts, scores, "
            "issues, advisor/executive analytics, LLM observability, pipeline "
            "benchmarking, queue monitoring, feedback, and CSV/PDF export. "
            "The Streamlit dashboard and CLI are clients of this same "
            "repository layer, not independent implementations."
        ),
        version="0.1.0",
    )

    # Local-first prototype: CORS is open so the dashboard (a separate
    # Streamlit process on a different port) can call this API directly.
    # `allow_credentials=False` is deliberate: auth is a header (`X-Role`),
    # not cookies, and browsers reject a wildcard `allow_origins` combined
    # with credentials. Tighten `allow_origins` before any real deployment.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(calls.router)
    app.include_router(org_hierarchy.router)
    app.include_router(analytics.router)
    app.include_router(issues.router)
    app.include_router(observability.router)
    app.include_router(export.router)

    @app.get("/", tags=["health"])
    def root() -> dict:
        return {"service": "fitnova-api", "status": "ok", "docs": "/docs"}

    return app


app = create_app()
