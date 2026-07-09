"""Transcript Viewer + Evidence Viewer + Call Replay Timeline, for a single
call. The three views share one call selection because they're really one
question asked three ways: "what actually happened on this call, and
where's the proof for what we flagged." """

import sys
from pathlib import Path

_DASHBOARD_ROOT = Path(__file__).resolve().parents[1]
if str(_DASHBOARD_ROOT) not in sys.path:
    sys.path.insert(0, str(_DASHBOARD_ROOT))
_SRC_DIR = _DASHBOARD_ROOT.parent / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import plotly.graph_objects as go  # noqa: E402
import streamlit as st  # noqa: E402
from utils.data_access import get_session  # noqa: E402
from utils.pdf_export import call_report_download_button  # noqa: E402

from fitnova.db import repository  # noqa: E402

st.set_page_config(page_title="Transcript & Evidence — FitNova", layout="wide")
st.title("Transcript, Evidence & Call Replay")

_SPEAKER_COLOR = {"ADVISOR": "#2563EB", "CUSTOMER": "#059669", "UNKNOWN": "#9CA3AF"}
_SEVERITY_COLOR = {"CRITICAL": "#B00020", "HIGH": "#D97706", "MEDIUM": "#CA8A04", "LOW": "#6B7280"}

session = get_session()
try:
    role = st.session_state.get("role", "SALES_DIRECTOR")
    scoped_advisor_id = st.session_state.get("advisor_id") if role == "ADVISOR" else None

    filters = repository.CallListFilters(advisor_id=scoped_advisor_id)
    calls, _total = repository.list_calls(session, filters, page=1, page_size=200)
    if not calls:
        st.info("No calls available yet. Run `fitnova ingest` (and `fitnova analyze`) first.")
    else:
        call_options = {
            (
                f"#{c.id} — {c.advisor.name if c.advisor else 'Unknown advisor'} — "
                f"{c.call_type.value} — "
                f"{c.call_datetime.strftime('%Y-%m-%d') if c.call_datetime else 'no date'}"
            ): c.id
            for c in calls
        }
        chosen = st.selectbox(
            "Choose a call", list(call_options.keys()), key="transcript_call_picker"
        )
        call_id = call_options[chosen]

        call = repository.get_call_detail(session, call_id)
        if call is None:
            st.error("Call not found.")
        else:
            meta_cols = st.columns(5)
            meta_cols[0].metric("Advisor", call.advisor.name if call.advisor else "—")
            meta_cols[1].metric("Call type", call.call_type.value)
            meta_cols[2].metric(
                "Duration", f"{call.duration_seconds:.0f}s" if call.duration_seconds else "—"
            )
            meta_cols[3].metric(
                "Overall quality", f"{call.score.overall_quality:.1f}/10" if call.score else "—"
            )
            meta_cols[4].metric("Validated issues", sum(1 for i in call.issues if i.is_validated))

            segments = call.transcript.segments if call.transcript else []
            issues_by_segment: dict[int, list] = {}
            for issue in call.issues:
                if issue.segment_id is not None:
                    issues_by_segment.setdefault(issue.segment_id, []).append(issue)

            tab_timeline, tab_transcript, tab_evidence, tab_report = st.tabs(
                ["Call Replay Timeline", "Transcript", "Evidence", "Coaching Report"]
            )

            with tab_timeline:
                if not segments:
                    st.info("No transcript segments for this call.")
                else:
                    fig = go.Figure()
                    for seg in segments:
                        speaker = seg.speaker_label.value
                        flagged = seg.id in issues_by_segment
                        color = "#B00020" if flagged else _SPEAKER_COLOR.get(speaker, "#9CA3AF")
                        fig.add_trace(
                            go.Bar(
                                x=[seg.end_time - seg.start_time],
                                y=[speaker],
                                base=[seg.start_time],
                                orientation="h",
                                marker=dict(
                                    color=color,
                                    line=dict(width=1, color="#111827") if flagged else None,
                                ),
                                hovertext=f"[{seg.start_time:.1f}s-{seg.end_time:.1f}s] {seg.text}"
                                + (" ⚠ FLAGGED" if flagged else ""),
                                hoverinfo="text",
                                showlegend=False,
                            )
                        )
                    fig.update_layout(
                        barmode="overlay",
                        height=280,
                        xaxis_title="Seconds into call",
                        margin=dict(l=10, r=10, t=20, b=10),
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    st.caption(
                        "🔵 Advisor · 🟢 Customer · 🔴 Segment with a flagged issue. Hover a bar "
                        "to read the utterance."
                    )

            with tab_transcript:
                if not segments:
                    st.info("No transcript available for this call.")
                else:
                    for seg in segments:
                        speaker = seg.speaker_label.value
                        flagged = seg.id in issues_by_segment
                        tag = (
                            "🧑‍💼 **Advisor**"
                            if speaker == "ADVISOR"
                            else ("🙋 **Customer**" if speaker == "CUSTOMER" else "❓ **Unknown**")
                        )
                        prefix = "🔴 " if flagged else ""
                        st.markdown(f"{prefix}[{seg.start_time:.1f}s] {tag}: {seg.text}")
                    if call.transcript and call.transcript.redacted_text:
                        with st.expander("Full redacted transcript (plain text)"):
                            st.text(call.transcript.redacted_text)

            with tab_evidence:
                if not call.issues:
                    st.info("No issues were flagged in this call.")
                else:
                    for issue in sorted(
                        call.issues, key=lambda i: (not i.is_validated, i.severity.value)
                    ):
                        color = _SEVERITY_COLOR.get(issue.severity.value, "#6B7280")
                        status_icon = "✅" if issue.is_validated else "❌"
                        expander_title = (
                            f"{status_icon} [{issue.severity.value}] {issue.issue_type.value} "
                            f"— {issue.speaker.value}"
                        )
                        with st.expander(expander_title):
                            st.markdown(f"**Quote:** “{issue.quoted_text}”")
                            st.markdown(f"**Reason:** {issue.reason}")
                            st.markdown(
                                f"**Confidence:** {issue.confidence_score:.2f} "
                                f"({issue.confidence_label.value})"
                            )
                            evidence_status = (
                                "Validated against the real transcript"
                                if issue.is_validated
                                else "Could NOT be matched to the transcript — do not treat as fact"
                            )
                            st.markdown(f"**Evidence status:** {evidence_status}")

            with tab_report:
                if call.call_insight:
                    st.markdown(f"**Executive Summary:** {call.call_insight.executive_summary}")
                    st.markdown(f"**Customer Intent:** {call.call_insight.customer_intent}")
                    if call.call_insight.improvement_suggestions:
                        st.markdown("**Improvement Suggestions:**")
                        for s in call.call_insight.improvement_suggestions:
                            st.markdown(f"- {s}")
                    st.markdown(
                        f"**Recommended Coaching:** {call.call_insight.recommended_coaching}"
                    )
                    st.markdown(f"**Next Best Action:** {call.call_insight.next_best_action}")

                    call_dict = {
                        "id": call.id,
                        "advisor_name": call.advisor.name if call.advisor else None,
                        "team_name": (
                            call.advisor.team.name if call.advisor and call.advisor.team else None
                        ),
                        "call_type": call.call_type.value,
                        "call_datetime": call.call_datetime,
                        "duration_seconds": call.duration_seconds,
                    }
                    score_dict = None
                    if call.score:
                        score_dict = {
                            d: getattr(call.score, d)
                            for d in (
                                "needs_discovery",
                                "rapport",
                                "empathy",
                                "listening",
                                "product_knowledge",
                                "objection_handling",
                                "compliance",
                                "trial_booking",
                                "closing",
                            )
                        }
                        score_dict["overall_quality"] = call.score.overall_quality
                        score_dict["evidence"] = call.score.evidence
                    issue_dicts = [
                        {
                            "severity": i.severity.value,
                            "issue_type": i.issue_type.value,
                            "speaker": i.speaker.value,
                            "quoted_text": i.quoted_text,
                            "reason": i.reason,
                            "is_validated": i.is_validated,
                        }
                        for i in call.issues
                    ]
                    insight_dict = {
                        "executive_summary": call.call_insight.executive_summary,
                        "customer_intent": call.call_insight.customer_intent,
                        "improvement_suggestions": call.call_insight.improvement_suggestions,
                        "recommended_coaching": call.call_insight.recommended_coaching,
                        "next_best_action": call.call_insight.next_best_action,
                    }
                    call_report_download_button(
                        call_dict, score_dict, issue_dicts, insight_dict, key="call_report_pdf"
                    )
                else:
                    st.info("This call has not been analyzed yet — run `fitnova analyze`.")
finally:
    session.close()
