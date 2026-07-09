"""Issue drill-down table + evidence-in-context card — the "show me the
quote" views (docs B4/B9, evidence validator)."""

from __future__ import annotations

import pandas as pd
import streamlit as st

_SEVERITY_COLOR = {"CRITICAL": "🔴", "HIGH": "🟠", "MEDIUM": "🟡", "LOW": "⚪"}


def issues_to_dataframe(issues: list) -> pd.DataFrame:
    """`issues` is a list of `fitnova.db.models.Issue` ORM rows (or
    anything with the same attributes)."""
    rows = []
    for i in issues:
        rows.append(
            {
                "ID": i.id,
                "Call ID": i.call_id,
                "Severity": f"{_SEVERITY_COLOR.get(i.severity.value, '')} {i.severity.value}",
                "Type": i.issue_type.value,
                "Speaker": i.speaker.value,
                "Quote": i.quoted_text,
                "Reason": i.reason,
                "Confidence": i.confidence_label.value,
                "Validated": "✅" if i.is_validated else "❌",
                "Status": i.status.value,
            }
        )
    return pd.DataFrame(rows)


def render_issue_table(issues: list) -> pd.DataFrame:
    df = issues_to_dataframe(issues)
    if df.empty:
        st.info("No issues match the current filters.")
    else:
        st.dataframe(df, use_container_width=True, hide_index=True)
    return df


def render_evidence_card(issue, context_segments: list) -> None:
    """`issue` is an ORM `Issue` row; `context_segments` are the
    `TranscriptSegment`s immediately around its anchor, in order."""
    severity_emoji = _SEVERITY_COLOR.get(issue.severity.value, "")
    st.markdown(f"### {severity_emoji} {issue.issue_type.value} — {issue.severity.value}")
    st.markdown(f"**Confidence:** {issue.confidence_score:.2f} ({issue.confidence_label.value})")
    st.markdown(f"**Reason given by the model:** {issue.reason}")
    evidence_status = (
        "✅ Validated against the real transcript"
        if issue.is_validated
        else "❌ Could not be matched to the transcript — treat as unverified"
    )
    st.markdown(f"**Evidence status:** {evidence_status}")

    st.markdown("**Conversation context:**")
    if not context_segments:
        st.warning("This issue has no anchoring transcript segment.")
        return
    for seg in context_segments:
        is_quoted = (
            seg.text.strip().lower() in issue.quoted_text.strip().lower()
            or issue.quoted_text.strip().lower() in seg.text.strip().lower()
        )
        speaker_tag = (
            "🧑‍💼 Advisor"
            if seg.speaker_label.value == "ADVISOR"
            else ("🙋 Customer" if seg.speaker_label.value == "CUSTOMER" else "❓ Unknown")
        )
        if is_quoted:
            st.markdown(
                f"> **[{seg.start_time:.1f}s] {speaker_tag}: {seg.text}**  🔎 *(flagged segment)*"
            )
        else:
            st.markdown(f"[{seg.start_time:.1f}s] {speaker_tag}: {seg.text}")
