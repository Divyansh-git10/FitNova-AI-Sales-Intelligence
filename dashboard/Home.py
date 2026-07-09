"""FitNova Sales Call Intelligence — Streamlit dashboard entrypoint.

Sets up the role-based view (docs Phase 5: "Role Based Views"): a sidebar
selector sets `st.session_state["role"]` to SALES_DIRECTOR, TEAM_LEADER, or
ADVISOR, plus a scoping team/advisor picker when relevant. Every page in
`pages/` reads this same session state to decide its default scope — this
is a UI-level convenience, NOT authentication (docs Phase 5:
"Authentication placeholder" — the real placeholder is the API's `X-Role`
header dependency in `fitnova.api.deps.get_current_role`; this selector
exists only to demo what each role would see once real auth exists).
"""

import sys
from pathlib import Path

_DASHBOARD_ROOT = Path(__file__).resolve().parent
if str(_DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(_DASHBOARD_ROOT))
_SRC_DIR = _DASHBOARD_ROOT.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import streamlit as st  # noqa: E402
from components.kpi_cards import render_executive_kpis, render_queue_kpis  # noqa: E402
from utils.data_access import get_session  # noqa: E402

from fitnova.db import repository  # noqa: E402

st.set_page_config(
    page_title="FitNova Sales Call Intelligence",
    layout="wide",
    initial_sidebar_state="expanded",
)

_theme_path = _DASHBOARD_ROOT / "static" / "theme.css"
if _theme_path.exists() and _theme_path.stat().st_size > 0:
    st.markdown(f"<style>{_theme_path.read_text()}</style>", unsafe_allow_html=True)

st.title("FitNova Sales Call Intelligence")
st.caption(
    "AI-powered transcription, scoring, issue detection, and coaching for FitNova sales calls."
)

session = get_session()
try:
    teams = repository.list_teams(session)
    advisors = repository.list_advisors(session)

    st.sidebar.header("View as")
    role_label = st.sidebar.selectbox(
        "Role", ["Sales Director", "Team Leader", "Advisor"], key="role_selector"
    )
    role_map = {
        "Sales Director": "SALES_DIRECTOR",
        "Team Leader": "TEAM_LEADER",
        "Advisor": "ADVISOR",
    }
    st.session_state["role"] = role_map[role_label]

    team_id = None
    advisor_id = None
    if role_label == "Team Leader" and teams:
        team_options = {t.name: t.id for t in teams}
        chosen = st.sidebar.selectbox(
            "Your team", list(team_options.keys()), key="home_team_picker"
        )
        team_id = team_options[chosen]
    elif role_label == "Advisor" and advisors:
        advisor_options = {a.name: a.id for a in advisors}
        chosen = st.sidebar.selectbox(
            "You are", list(advisor_options.keys()), key="home_advisor_picker"
        )
        advisor_id = advisor_options[chosen]

    st.session_state["team_id"] = team_id
    st.session_state["advisor_id"] = advisor_id

    st.sidebar.divider()
    st.sidebar.caption(
        "Role selection changes each page's default scope. This is a UI "
        "convenience, not real authentication — see `fitnova.api.deps."
        "get_current_role` for the actual (placeholder) auth seam."
    )

    st.subheader("Org-wide snapshot")
    summary = repository.executive_summary(session, team_id=team_id, date_from=None, date_to=None)
    render_executive_kpis(summary)

    st.subheader("Processing queue")
    queue_counts = repository.queue_health(session)
    render_queue_kpis(queue_counts)

    st.divider()
    st.markdown("""
Use the sidebar to navigate:

- **Executive Analytics** — org-wide KPIs, issue distribution, call mix, CSV export.
- **Advisor Scorecards** — per-advisor performance, dimension breakdown, leaderboard, PDF export.
- **Issue Drilldown** — filterable issue table with evidence-in-context.
- **Transcript & Evidence Viewer** — full transcript, call replay timeline, issue evidence,
  PDF coaching report.
- **Observability & Health** — LLM latency/retry/success trends, pipeline benchmarking,
  queue monitoring, health check.
        """)

    if summary.total_calls == 0:
        st.info(
            "No calls have been ingested yet. Run `fitnova ingest` to process recordings from "
            "the audio inbox, then `fitnova analyze` to score them — or check `fitnova doctor` "
            "if something looks wrong."
        )
finally:
    session.close()
