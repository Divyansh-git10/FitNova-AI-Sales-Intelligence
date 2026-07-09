"""Engine and session factory construction.

Deliberately factored as plain functions (rather than module-level
globals) so the DI container (`fitnova.core.container.Container`) can wire
them as singletons and tests can swap in an in-memory SQLite engine without
monkeypatching module state.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from fitnova.core.config import Settings


def build_engine(settings: Settings) -> Engine:
    """Create the SQLAlchemy engine from `Settings.database_url`.

    `check_same_thread=False` is required for SQLite when the same engine
    is shared across FastAPI's threadpool / Streamlit reruns; it is a no-op
    for other database backends.
    """
    connect_args = (
        {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    )
    return create_engine(settings.database_url, echo=settings.sql_echo, connect_args=connect_args)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db_session(session_factory: sessionmaker[Session]) -> Generator[Session, None, None]:
    """FastAPI-style dependency generator: yields a session, commits on
    success, rolls back on exception, always closes."""
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
