"""Observability & Health — LLM latency/retry/success trends, pipeline
benchmarking (transcription/LLM/total time, RTF), and live processing
queue monitoring. The "is the system actually working" view."""

import sys
from pathlib import Path

_DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(_DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(_DASHBOARD_ROOT))
_SRC_DIR = _DASHBOARD_ROOT.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import pandas as pd  # noqa: E402
import plotly.express as px  # noqa: E402
import streamlit as st  # noqa: E402
from components.kpi_cards import render_benchmark_kpis, render_queue_kpis  # noqa: E402
from utils.data_access import get_session, get_settings  # noqa: E402

from fitnova.db import repository  # noqa: E402

st.set_page_config(page_title="Observability & Health — FitNova", layout="wide")
st.title("Observability & Health")

session = get_session()
try:
    st.subheader("Health check")
    settings = get_settings()
    health_cols = st.columns(3)
    db_ok = True
    try:
        from sqlalchemy import text

        session.execute(text("SELECT 1"))
    except Exception:  # noqa: BLE001
        db_ok = False
    health_cols[0].metric("Database", "✅ Reachable" if db_ok else "❌ Unreachable")

    ollama_ok = False
    ollama_version = "unknown"
    try:
        from fitnova.analysis.ollama_client import OllamaClient

        ollama_version = OllamaClient(settings).get_model_version()
        ollama_ok = ollama_version != "unknown"
    except Exception:  # noqa: BLE001
        pass
    health_cols[1].metric("Ollama (LLM server)", "✅ Reachable" if ollama_ok else "⚠ Unreachable")
    health_cols[2].metric("Configured model", settings.ollama_model)
    if not ollama_ok:
        st.caption(
            "Ollama being unreachable only blocks `fitnova analyze` (scoring/issue "
            "detection/insights). Ingestion, storage, and this dashboard all work without it."
        )

    st.divider()
    st.subheader("Processing queue")
    queue_counts = repository.queue_health(session)
    render_queue_kpis(queue_counts)

    queue_rows = repository.queue_snapshot(session, limit=200)
    if queue_rows:
        df_queue = pd.DataFrame(
            [
                {
                    "Call ID": r.call_id,
                    "Advisor": r.advisor_name or "—",
                    "Call Type": r.call_type,
                    "Stage": r.pipeline_stage,
                    "Status": r.status,
                    "Retries": r.retry_count,
                    "Started": r.started_at,
                    "Completed": r.completed_at,
                    "Last Error": (
                        (r.last_error[:80] + "…")
                        if r.last_error and len(r.last_error) > 80
                        else r.last_error
                    ),
                }
                for r in queue_rows
            ]
        )
        st.dataframe(df_queue, use_container_width=True, hide_index=True)
    else:
        st.info("Queue is empty — nothing has been ingested yet.")

    st.divider()
    st.subheader("Pipeline benchmarking")
    bench = repository.benchmark_summary(session, recent_limit=50)
    render_benchmark_kpis(bench)

    if bench.recent:
        df_bench = pd.DataFrame(
            [
                {
                    "Call ID": b.call_id,
                    "Total (ms)": b.total_pipeline_time_ms,
                    "Transcription (ms)": b.transcription_time_ms,
                    "LLM (ms)": b.llm_time_ms,
                    "RTF": b.real_time_factor,
                    "Whisper Model": b.whisper_model_used,
                }
                for b in bench.recent
            ]
        )
        fig = px.line(
            df_bench.sort_values("Call ID"),
            x="Call ID",
            y=["Total (ms)", "Transcription (ms)", "LLM (ms)"],
            markers=True,
            title="Pipeline stage timing per call (most recent runs)",
        )
        fig.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, use_container_width=True)
        st.dataframe(df_bench, use_container_width=True, hide_index=True)
    else:
        st.info("No pipeline runs have been benchmarked yet.")

    st.divider()
    st.subheader("LLM observability")
    llm_summaries = repository.llm_observability_summary(session)
    if llm_summaries:
        df_llm = pd.DataFrame(
            [
                {
                    "Stage": s.stage,
                    "Calls Logged": s.total_calls_logged,
                    "Success Rate": f"{s.success_rate:.0%}",
                    "Avg Latency (ms)": s.avg_latency_ms,
                    "Avg Retries": s.avg_retry_count,
                    "Prompt Version": s.latest_prompt_version,
                    "Model": s.model_name,
                }
                for s in llm_summaries
            ]
        )
        st.dataframe(df_llm, use_container_width=True, hide_index=True)

        fig2 = px.bar(df_llm, x="Stage", y="Avg Latency (ms)", title="Average LLM latency by stage")
        fig2.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig2, use_container_width=True)
    else:
        st.info("No LLM inference has been logged yet — run `fitnova analyze`.")
finally:
    session.close()
