"""Shared CSV/PDF export code (Phase 5).

Used by BOTH the FastAPI `/export/*` endpoints and the Streamlit
dashboard's export buttons, so the two surfaces can never disagree about
what a "call export" or "scorecard PDF" contains — there is exactly one
implementation of each report, not a REST version and a dashboard version
drifting apart over time.

Deliberately takes plain dicts/lists rather than ORM models or a specific
Pydantic schema: callers (API routers, dashboard pages) each already have
their own view of the data and just need to normalize it into flat rows
before calling in here — this module has zero knowledge of SQLAlchemy or
FastAPI.
"""

from fitnova.reporting.csv_export import calls_to_csv, issues_to_csv
from fitnova.reporting.pdf_export import advisor_scorecard_to_pdf, call_report_to_pdf

__all__ = ["calls_to_csv", "issues_to_csv", "advisor_scorecard_to_pdf", "call_report_to_pdf"]
