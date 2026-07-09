"""Sidebar filter widgets shared across pages. Each `render_*_filters`
function returns a plain dict of the selected values (never a repository
filter dataclass directly, so components stay independent of the exact
repository API shape) plus populates its own widgets so every page filters
consistently."""

from __future__ import annotations

import streamlit as st


def render_org_scope_filters(teams: list, advisors: list, key_prefix: str = "") -> dict:
    """Team + advisor pickers. Returns `{"team_id": int|None, "advisor_id": int|None}`."""
    team_options = {"All teams": None} | {t.name: t.id for t in teams}
    team_label = st.sidebar.selectbox("Team", list(team_options.keys()), key=f"{key_prefix}_team")
    team_id = team_options[team_label]

    scoped_advisors = [a for a in advisors if team_id is None or a.team_id == team_id]
    advisor_options = {"All advisors": None} | {a.name: a.id for a in scoped_advisors}
    advisor_label = st.sidebar.selectbox(
        "Advisor", list(advisor_options.keys()), key=f"{key_prefix}_advisor"
    )
    advisor_id = advisor_options[advisor_label]

    return {"team_id": team_id, "advisor_id": advisor_id}


def render_call_type_filter(call_types: list[str], key_prefix: str = "") -> str | None:
    options = ["All call types"] + call_types
    label = st.sidebar.selectbox("Call type", options, key=f"{key_prefix}_call_type")
    return None if label == "All call types" else label


def render_severity_filter(key_prefix: str = "") -> str | None:
    options = ["All severities", "CRITICAL", "HIGH", "MEDIUM", "LOW"]
    label = st.sidebar.selectbox("Severity", options, key=f"{key_prefix}_severity")
    return None if label == "All severities" else label


def render_validated_filter(key_prefix: str = "") -> bool | None:
    label = st.sidebar.radio(
        "Evidence status",
        ["All", "Validated only", "Unvalidated only"],
        key=f"{key_prefix}_validated",
        horizontal=True,
    )
    return {"All": None, "Validated only": True, "Unvalidated only": False}[label]
