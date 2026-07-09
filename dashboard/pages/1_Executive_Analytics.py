"""Executive Analytics — org-wide KPIs, call mix, issue distribution,
trend by team, CSV export. Primary view for the Sales Director role."""

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
from components.filters import render_org_scope_filters  # noqa: E402
from components.kpi_cards import render_executive_kpis  # noqa: E402
from utils.csv_export import calls_download_button  # noqa: E402
from utils.data_access import get_session  # noqa: E402

from fitnova.db import repository  # noqa: E402
from fitnova.schemas.api_views import CallListItem  # noqa: E402

st.set_page_config(page_title="Executive Analytics — FitNova", layout="wide")
st.title("Executive Analytics")

session = get_session()
try:
    teams = repository.list_teams(session)
    advisors = repository.list_advisors(session)

    default_team = st.session_state.get("team_id")
    scope = render_org_scope_filters(teams, advisors, key_prefix="exec")
    team_id = scope["team_id"] or default_team
    advisor_id = scope["advisor_id"]

    summary = repository.executive_summary(session, team_id=team_id)
    render_executive_kpis(summary)

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.subheader("Call mix by type")
        if summary.calls_by_type:
            df_calls = pd.DataFrame(
                {
                    "Call Type": list(summary.calls_by_type.keys()),
                    "Count": list(summary.calls_by_type.values()),
                }
            )
            fig = px.pie(df_calls, names="Call Type", values="Count", hole=0.4)
            fig.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No calls ingested yet.")

    with col2:
        st.subheader("Validated issues by severity")
        if summary.issue_count_by_severity:
            df_sev = pd.DataFrame(
                {
                    "Severity": list(summary.issue_count_by_severity.keys()),
                    "Count": list(summary.issue_count_by_severity.values()),
                }
            )
            color_map = {
                "CRITICAL": "#B00020",
                "HIGH": "#D97706",
                "MEDIUM": "#CA8A04",
                "LOW": "#6B7280",
            }
            fig2 = px.bar(
                df_sev,
                x="Severity",
                y="Count",
                color="Severity",
                color_discrete_map=color_map,
                category_orders={"Severity": ["CRITICAL", "HIGH", "MEDIUM", "LOW"]},
            )
            fig2.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10), showlegend=False)
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.info("No validated issues yet.")

    st.subheader("Issues by type")
    if summary.issue_count_by_type:
        df_type = pd.DataFrame(
            {
                "Issue Type": list(summary.issue_count_by_type.keys()),
                "Count": list(summary.issue_count_by_type.values()),
            }
        ).sort_values("Count", ascending=True)
        fig3 = px.bar(df_type, x="Count", y="Issue Type", orientation="h")
        fig3.update_layout(height=400, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig3, use_container_width=True)
    else:
        st.info("No validated issues yet.")

    st.subheader("Average score by dimension (org-wide)")
    if summary.avg_dimension_scores:
        df_dim = pd.DataFrame(
            {
                "Dimension": [d.replace("_", " ").title() for d in summary.avg_dimension_scores],
                "Avg Score": list(summary.avg_dimension_scores.values()),
            }
        )
        fig4 = px.bar(df_dim, x="Dimension", y="Avg Score", range_y=[0, 10])
        fig4.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig4, use_container_width=True)
    else:
        st.info("No scored calls yet.")

    st.divider()
    st.subheader("Call list")
    filters = repository.CallListFilters(team_id=team_id, advisor_id=advisor_id)
    calls, total = repository.list_calls(session, filters, page=1, page_size=500)
    rows = [
        CallListItem(
            id=c.id,
            advisor_id=c.advisor_id,
            advisor_name=c.advisor.name if c.advisor else None,
            team_name=c.advisor.team.name if c.advisor and c.advisor.team else None,
            call_type=c.call_type,
            call_datetime=c.call_datetime,
            duration_seconds=c.duration_seconds,
            overall_quality=c.score.overall_quality if c.score else None,
            validated_issue_count=sum(1 for i in c.issues if i.is_validated),
        ).model_dump()
        for c in calls
    ]
    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
    else:
        st.info("No calls match the current filters.")
    st.caption(f"Showing {len(rows)} of {total} matching call(s).")
    calls_download_button(rows, key="exec_csv")
finally:
    session.close()
