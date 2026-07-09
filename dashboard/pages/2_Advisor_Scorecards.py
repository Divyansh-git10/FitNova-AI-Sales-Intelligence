"""Advisor Scorecards — leaderboard (Sales Director / Team Leader view)
plus a single-advisor detail view (Advisor role's own view), with PDF
export."""

import sys
from pathlib import Path

_DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(_DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(_DASHBOARD_ROOT))
_SRC_DIR = _DASHBOARD_ROOT.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import streamlit as st  # noqa: E402
from components.scorecards import render_leaderboard_table, render_scorecard_detail  # noqa: E402
from utils.data_access import get_session  # noqa: E402
from utils.pdf_export import scorecard_download_button  # noqa: E402

from fitnova.db import repository  # noqa: E402

st.set_page_config(page_title="Advisor Scorecards — FitNova", layout="wide")
st.title("Advisor Scorecards")

session = get_session()
try:
    role = st.session_state.get("role", "SALES_DIRECTOR")
    teams = repository.list_teams(session)
    advisors = repository.list_advisors(session)

    if role == "ADVISOR" and st.session_state.get("advisor_id"):
        advisor_id = st.session_state["advisor_id"]
        card = repository.advisor_scorecard(session, advisor_id)
        if card is None:
            st.error("Advisor not found.")
        else:
            render_scorecard_detail(card)
            scorecard_download_button(
                {
                    "advisor_name": card.advisor_name,
                    "team_name": card.team_name,
                    "scored_call_count": card.scored_call_count,
                    "avg_overall_quality": card.avg_overall_quality,
                    "avg_dimension_scores": card.avg_dimension_scores,
                    "issue_count_by_severity": card.issue_count_by_severity,
                    "validated_issue_count": card.validated_issue_count,
                    "total_issue_count": card.total_issue_count,
                },
                key="advisor_self_pdf",
            )
    else:
        team_id = st.session_state.get("team_id")
        if teams:
            team_options = {"All teams": None} | {t.name: t.id for t in teams}
            default_index = (
                list(team_options.values()).index(team_id)
                if team_id in team_options.values()
                else 0
            )
            chosen = st.selectbox(
                "Team", list(team_options.keys()), index=default_index, key="scorecard_team_filter"
            )
            team_id = team_options[chosen]

        st.subheader("Leaderboard")
        cards = repository.advisor_leaderboard(session, team_id=team_id)
        render_leaderboard_table(cards)

        st.divider()
        st.subheader("Advisor detail")
        if advisors:
            scoped = [a for a in advisors if team_id is None or a.team_id == team_id]
            if scoped:
                advisor_options = {a.name: a.id for a in scoped}
                chosen_advisor = st.selectbox(
                    "Choose an advisor",
                    list(advisor_options.keys()),
                    key="scorecard_advisor_picker",
                )
                advisor_id = advisor_options[chosen_advisor]
                card = repository.advisor_scorecard(session, advisor_id)
                if card is not None:
                    render_scorecard_detail(card)
                    scorecard_download_button(
                        {
                            "advisor_name": card.advisor_name,
                            "team_name": card.team_name,
                            "scored_call_count": card.scored_call_count,
                            "avg_overall_quality": card.avg_overall_quality,
                            "avg_dimension_scores": card.avg_dimension_scores,
                            "issue_count_by_severity": card.issue_count_by_severity,
                            "validated_issue_count": card.validated_issue_count,
                            "total_issue_count": card.total_issue_count,
                        },
                        key="scorecard_detail_pdf",
                    )
            else:
                st.info("No advisors in this team.")
        else:
            st.info("No advisors exist yet.")
finally:
    session.close()
