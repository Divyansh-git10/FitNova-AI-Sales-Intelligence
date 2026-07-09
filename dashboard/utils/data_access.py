"""Bootstraps `fitnova` for the dashboard process and exposes a single
cached way to get a DB session.

The dashboard reads through `fitnova.db.repository` directly rather than
calling the FastAPI service over HTTP (documented exception, docs Section
4.7 Component Diagram / Phase 5 addendum) — it's the same process family,
same database, and this avoids requiring a second server to be running
just to view data locally. The API exists for external/programmatic
clients and the CLI; the dashboard and API are two independent front doors
onto the same `fitnova.db.repository` layer, so they can never disagree.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Streamlit runs this file as a standalone script, not as part of the
# `fitnova` package, so `src/` needs to be on sys.path before any `import
# fitnova...` below will work — whether or not the launcher already set
# PYTHONPATH=src (the `fitnova dashboard` CLI command does; a bare
# `streamlit run dashboard/Home.py` might not).
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import streamlit as st  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from fitnova.bootstrap import bootstrap_app  # noqa: E402
from fitnova.core.config import Settings  # noqa: E402
from fitnova.core.container import Container  # noqa: E402


@st.cache_resource(show_spinner="Connecting to FitNova...")
def get_container() -> Container:
    """Bootstrapped exactly once per Streamlit server process (`st.
    cache_resource` persists across reruns/sessions), same as the API's
    lazy singleton — config, logging, and the DB schema are only wired
    once."""
    return bootstrap_app()


def get_settings() -> Settings:
    return get_container().settings()


def get_session() -> Session:
    """A fresh session per call. Callers are responsible for closing it —
    every page in this dashboard does so in a `try/finally` around its
    query calls, since Streamlit reruns the whole script on every
    interaction and a leaked session per rerun would exhaust the pool."""
    return get_container().session_factory()()
