"""Issue Drilldown — filterable table of every flagged issue, with a
"view evidence" jump into the exact transcript context (docs B4, B9)."""

import sys
from pathlib import Path

_DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(_DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(_DASHBOARD_ROOT))
_SRC_DIR = _DASHBOARD_ROOT.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import streamlit as st  # noqa: E402
from components.filters import (  # noqa: E402
    render_org_scope_filters,
    render_severity_filter,
    render_validated_filter,
)
from components.issue_drilldown import (  # noqa: E402
    render_evidence_card,
    render_issue_table,
)
from utils.csv_export import issues_download_button  # noqa: E402
from utils.data_access import get_session  # noqa: E402

from fitnova.core.constants import Severity  # noqa: E402
from fitnova.db import repository  # noqa: E402
from fitnova.schemas.api_views import IssueView  # noqa: E402

st.set_page_config(page_title="Issue Drilldown — FitNova", layout="wide")
st.title("Issue Drilldown")

session = get_session()
try:
    teams = repository.list_teams(session)
    advisors = repository.list_advisors(session)

    default_advisor = st.session_state.get("advisor_id")
    default_team = st.session_state.get("team_id")
    scope = render_org_scope_filters(teams, advisors, key_prefix="issues")
    team_id = scope["team_id"] or default_team
    advisor_id = scope["advisor_id"] or default_advisor
    severity_label = render_severity_filter(key_prefix="issues")
    is_validated = render_validated_filter(key_prefix="issues")

    severity = Severity(severity_label) if severity_label else None

    filters = repository.IssueListFilters(
        severity=severity, advisor_id=advisor_id, team_id=team_id, is_validated=is_validated
    )
    issues, total = repository.list_issues(session, filters, page=1, page_size=500)

    st.caption(f"{total} issue(s) match the current filters.")
    render_issue_table(issues)

    rows = []
    for issue in issues:
        row = IssueView.model_validate(issue).model_dump()
        row["advisor_name"] = issue.call.advisor.name if issue.call and issue.call.advisor else None
        rows.append(row)
    issues_download_button(rows, key="issues_csv")

    st.divider()
    st.subheader("Evidence viewer")
    if issues:
        issue_options = {
            f"#{i.id} — {i.issue_type.value} ({i.severity.value}) — call {i.call_id}": i.id
            for i in issues
        }
        chosen = st.selectbox(
            "Choose an issue to inspect", list(issue_options.keys()), key="evidence_issue_picker"
        )
        issue_id = issue_options[chosen]
        result = repository.get_issue_with_context(session, issue_id, context_segments=2)
        if result:
            render_evidence_card(result["issue"], result["context_segments"])
            # `page_link` needs a real multipage navigation context (it
            # errors when a page is executed standalone, e.g. under
            # Streamlit's AppTest harness) - degrade to a plain hint
            # rather than let a convenience link crash the page.
            try:
                st.page_link(
                    "pages/4_Transcript_Evidence_Replay.py",
                    label="Open full transcript for this call →",
                )
            except Exception:  # noqa: BLE001
                st.caption(
                    "Open the **Transcript & Evidence Replay** page from the sidebar to see the "
                    "full call."
                )
    else:
        st.info("No issues to inspect with the current filters.")
finally:
    session.close()
