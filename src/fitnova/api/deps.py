"""Shared FastAPI dependencies: DB session, settings, and a placeholder
role dependency every router depends on instead of parsing headers itself.

The container is bootstrapped exactly once per process (lazily, on first
request) via `fitnova.bootstrap.bootstrap_app()` - the same entrypoint the
CLI and dashboard use, so the API never wires its own copy of settings/
engine/session-factory.
"""

from __future__ import annotations

from collections.abc import Generator

from fastapi import Header
from sqlalchemy.orm import Session

from fitnova.core.config import Settings
from fitnova.core.constants import ReviewerRole
from fitnova.core.container import Container

_container: Container | None = None


def get_container() -> Container:
    global _container
    if _container is None:
        from fitnova.bootstrap import bootstrap_app

        _container = bootstrap_app()
    return _container


def reset_container_for_tests() -> None:
    """Test-only escape hatch: forces the next `get_container()` call to
    rebuild from scratch, so tests can point the API at an isolated
    in-memory database instead of the real one."""
    global _container
    _container = None


def get_settings() -> Settings:
    return get_container().settings()


def get_db() -> Generator[Session, None, None]:
    """Request-scoped session: commits on success, rolls back and
    re-raises on any exception, always closes. FastAPI test clients
    override this dependency directly (see `tests/conftest.py`) rather
    than swapping the container, so tests never touch a real database
    file."""
    session_factory = get_container().session_factory()
    session = session_factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_current_role(x_role: str | None = Header(default=None)) -> ReviewerRole:
    """Authentication placeholder (docs Phase 5: "Authentication
    placeholder").

    There is no token verification, no session, no identity check here -
    the role is read straight from an `X-Role` header and defaults to
    `SALES_DIRECTOR` (the least-restricted view) when absent. This exists
    purely so role-based view logic has one concrete seam to depend on:
    every router that needs a role depends on `get_current_role`, never on
    header-parsing directly, so real authentication (OAuth2/JWT + an
    identity provider resolving a verified role) can be dropped in later
    by replacing only this function's body.
    """
    if x_role is None:
        return ReviewerRole.SALES_DIRECTOR
    try:
        return ReviewerRole(x_role.strip().upper())
    except ValueError:
        return ReviewerRole.SALES_DIRECTOR
