"""Advisor scorecard rendering: KPI row + per-dimension bar chart + issue
severity breakdown. Shared by the Advisor Scorecards page (one advisor,
detailed) and the Executive Analytics page (leaderboard table)."""

from __future__ import annotations

import pandas as pd
import plotly.express as px
import streamlit as st


def render_scorecard_detail(card) -> None:
    """`card` is a `fitnova.db.repository.AdvisorScorecard`."""
    st.subheader(f"{card.advisor_name} — {card.team_name}")

    cols = st.columns(4)
    cols[0].metric("Scored calls", card.scored_call_count)
    cols[1].metric(
        "Avg overall quality",
        f"{card.avg_overall_quality:.1f}/10" if card.avg_overall_quality is not None else "—",
    )
    cols[2].metric("Validated issues", card.validated_issue_count)
    cols[3].metric("Total issues (incl. unvalidated)", card.total_issue_count)

    if card.avg_dimension_scores:
        df = pd.DataFrame(
            {
                "Dimension": [d.replace("_", " ").title() for d in card.avg_dimension_scores],
                "Avg Score": list(card.avg_dimension_scores.values()),
            }
        )
        fig = px.bar(
            df, x="Dimension", y="Avg Score", range_y=[0, 10], title="Average score by dimension"
        )
        fig.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10))
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No scored calls yet for this advisor.")

    if card.issue_count_by_severity:
        sev_df = pd.DataFrame(
            {
                "Severity": list(card.issue_count_by_severity.keys()),
                "Count": list(card.issue_count_by_severity.values()),
            }
        )
        color_map = {
            "CRITICAL": "#B00020",
            "HIGH": "#D97706",
            "MEDIUM": "#CA8A04",
            "LOW": "#6B7280",
        }
        fig2 = px.bar(
            sev_df,
            x="Severity",
            y="Count",
            color="Severity",
            color_discrete_map=color_map,
            title="Validated issues by severity",
            category_orders={"Severity": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
        )
        fig2.update_layout(height=300, margin=dict(l=10, r=10, t=40, b=10), showlegend=False)
        st.plotly_chart(fig2, use_container_width=True)


def render_leaderboard_table(cards: list) -> pd.DataFrame:
    """Renders the leaderboard and returns the underlying DataFrame (so the
    caller can also offer it as a CSV download)."""
    rows = [
        {
            "Advisor": c.advisor_name,
            "Team": c.team_name,
            "Scored Calls": c.scored_call_count,
            "Avg Overall Quality": c.avg_overall_quality,
            "Validated Issues": c.validated_issue_count,
            "Critical Issues": c.issue_count_by_severity.get("CRITICAL", 0),
        }
        for c in cards
    ]
    df = pd.DataFrame(rows)
    if df.empty:
        st.info("No advisors have scored calls yet.")
    else:
        # Color-graded styling is a nice-to-have, not a correctness
        # requirement - if the installed pandas/jinja2 combination doesn't
        # support `.style` (older jinja2, missing optional dep), fall back
        # to a plain dataframe rather than crashing the page.
        try:
            styled = df.style.background_gradient(
                subset=["Avg Overall Quality"], cmap="RdYlGn", vmin=0, vmax=10
            )
            st.dataframe(styled, use_container_width=True, hide_index=True)
        except Exception:  # noqa: BLE001
            st.dataframe(df, use_container_width=True, hide_index=True)
    return df
