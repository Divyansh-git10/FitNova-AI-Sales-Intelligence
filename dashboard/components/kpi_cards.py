"""Executive KPI row — `st.metric` cards. Every value comes from
`fitnova.db.repository`'s aggregation functions; nothing here computes an
average itself (docs: "never hardcode analysis")."""

from __future__ import annotations

import streamlit as st


def render_executive_kpis(summary) -> None:
    """`summary` is a `fitnova.db.repository.ExecutiveSummary`."""
    cols = st.columns(5)
    cols[0].metric("Total calls", summary.total_calls)
    cols[1].metric("Scored calls", summary.scored_call_count)
    cols[2].metric(
        "Avg overall quality",
        f"{summary.avg_overall_quality:.1f}/10" if summary.avg_overall_quality is not None else "—",
    )
    cols[3].metric("Validated issues", summary.validated_issue_count)
    critical = summary.issue_count_by_severity.get("CRITICAL", 0)
    cols[4].metric("Critical issues", critical, delta=None, delta_color="inverse")


def render_benchmark_kpis(summary) -> None:
    """`summary` is a `fitnova.db.repository.BenchmarkSummary`."""
    cols = st.columns(4)
    cols[0].metric("Pipeline runs benchmarked", summary.run_count)
    cols[1].metric(
        "Avg total pipeline time",
        (
            f"{summary.avg_total_pipeline_time_ms:.0f} ms"
            if summary.avg_total_pipeline_time_ms
            else "—"
        ),
    )
    cols[2].metric(
        "Avg LLM time", f"{summary.avg_llm_time_ms:.0f} ms" if summary.avg_llm_time_ms else "—"
    )
    rtf = summary.avg_real_time_factor
    cols[3].metric(
        "Avg Real Time Factor",
        f"{rtf:.3f}" if rtf is not None else "—",
        help="Total pipeline time / audio duration. Below 1.0 means processing is faster than "
        "the call itself.",
    )


def render_queue_kpis(queue_counts: dict) -> None:
    cols = st.columns(4)
    cols[0].metric("Pending", queue_counts.get("pending", 0))
    cols[1].metric("In progress", queue_counts.get("in_progress", 0))
    cols[2].metric("Completed", queue_counts.get("completed", 0))
    cols[3].metric("Failed", queue_counts.get("failed", 0), delta_color="inverse")
