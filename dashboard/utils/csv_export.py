"""CSV export buttons — thin Streamlit wrapper around
`fitnova.reporting.csv_export`, the single implementation shared with the
FastAPI `/export/*.csv` endpoints."""

from __future__ import annotations

import streamlit as st

from fitnova.reporting import calls_to_csv, issues_to_csv


def calls_download_button(
    rows: list[dict], label: str = "Download calls as CSV", key: str | None = None
) -> None:
    st.download_button(
        label=label,
        data=calls_to_csv(rows),
        file_name="fitnova_calls.csv",
        mime="text/csv",
        key=key,
        disabled=not rows,
    )


def issues_download_button(
    rows: list[dict], label: str = "Download issues as CSV", key: str | None = None
) -> None:
    st.download_button(
        label=label,
        data=issues_to_csv(rows),
        file_name="fitnova_issues.csv",
        mime="text/csv",
        key=key,
        disabled=not rows,
    )
