"""LLM observability, pipeline benchmarking, and processing-queue
monitoring — the "what is the system doing right now, and how well" API
surface (docs Section 12)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from fitnova.api.deps import get_db, get_settings
from fitnova.core.config import Settings
from fitnova.db import repository
from fitnova.schemas.api_views import (
    BenchmarkRunView,
    BenchmarkSummaryView,
    HealthCheck,
    LLMStageSummaryView,
    QueueSnapshotView,
)

router = APIRouter(tags=["observability"])


@router.get("/observability/llm", response_model=list[LLMStageSummaryView])
def get_llm_observability(db: Session = Depends(get_db)) -> list[LLMStageSummaryView]:
    summaries = repository.llm_observability_summary(db)
    return [
        LLMStageSummaryView(
            stage=s.stage,
            total_calls_logged=s.total_calls_logged,
            success_rate=s.success_rate,
            avg_latency_ms=s.avg_latency_ms,
            avg_retry_count=s.avg_retry_count,
            latest_prompt_version=s.latest_prompt_version,
            model_name=s.model_name,
        )
        for s in summaries
    ]


@router.get("/observability/benchmarks", response_model=BenchmarkSummaryView)
def get_benchmark_summary(
    recent_limit: int = 20, db: Session = Depends(get_db)
) -> BenchmarkSummaryView:
    summary = repository.benchmark_summary(db, recent_limit=recent_limit)
    return BenchmarkSummaryView(
        run_count=summary.run_count,
        avg_total_pipeline_time_ms=summary.avg_total_pipeline_time_ms,
        avg_transcription_time_ms=summary.avg_transcription_time_ms,
        avg_llm_time_ms=summary.avg_llm_time_ms,
        avg_real_time_factor=summary.avg_real_time_factor,
        recent=[BenchmarkRunView.model_validate(b) for b in summary.recent],
    )


@router.get("/queue", response_model=list[QueueSnapshotView])
def get_queue_snapshot(limit: int = 200, db: Session = Depends(get_db)) -> list[QueueSnapshotView]:
    rows = repository.queue_snapshot(db, limit=limit)
    return [QueueSnapshotView(**row.__dict__) for row in rows]


@router.get("/health", response_model=HealthCheck)
def health_check(
    db: Session = Depends(get_db), settings: Settings = Depends(get_settings)
) -> HealthCheck:
    """Health Monitoring (docs Phase 5): a single endpoint the CLI's
    `fitnova doctor` and any external uptime check can hit. Database
    connectivity is checked for real (`SELECT 1`); Ollama reachability is
    a best-effort, non-fatal probe — the API stays healthy even if the LLM
    server is down, since ingestion/transcription don't depend on it."""
    database_reachable = True
    detail = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        database_reachable = False
        detail = f"Database check failed: {exc}"

    ollama_reachable: bool | None = None
    try:
        from fitnova.analysis.ollama_client import OllamaClient

        ollama_reachable = OllamaClient(settings).get_model_version() != "unknown"
    except Exception:  # noqa: BLE001
        ollama_reachable = False

    queue_counts = repository.queue_health(db) if database_reachable else {}

    return HealthCheck(
        ok=database_reachable,
        database_reachable=database_reachable,
        ollama_reachable=ollama_reachable,
        queue_counts=queue_counts,
        detail=detail,
    )
