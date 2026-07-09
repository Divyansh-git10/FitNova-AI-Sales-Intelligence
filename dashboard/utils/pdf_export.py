"""PDF export buttons — thin Streamlit wrapper around
`fitnova.reporting.pdf_export`, the single implementation shared with the
FastAPI `/export/*.pdf` endpoints."""

from __future__ import annotations

import streamlit as st

from fitnova.reporting import advisor_scorecard_to_pdf, call_report_to_pdf


def call_report_download_button(
    call: dict, score: dict | None, issues: list[dict], insight: dict | None, key: str | None = None
) -> None:
    pdf_bytes = call_report_to_pdf(call, score, issues, insight)
    st.download_button(
        label="Download call coaching report (PDF)",
        data=pdf_bytes,
        file_name=f"fitnova_call_{call.get('id')}.pdf",
        mime="application/pdf",
        key=key,
    )


def scorecard_download_button(scorecard: dict, key: str | None = None) -> None:
    pdf_bytes = advisor_scorecard_to_pdf(scorecard)
    st.download_button(
        label="Download scorecard (PDF)",
        data=pdf_bytes,
        file_name=f"fitnova_advisor_{scorecard.get('advisor_name', 'scorecard')}.pdf".replace(
            " ", "_"
        ),
        mime="application/pdf",
        key=key,
    )
