"""Schema creation.

For this local prototype, `create_all()` is sufficient (no migration
history to manage). If the project grows beyond a take-home prototype,
this is the seam where Alembic would be introduced without changing any
model code.
"""

from __future__ import annotations

from sqlalchemy import Engine

from fitnova.core.logging_config import get_logger
from fitnova.db import models  # noqa: F401 - import registers all models on Base.metadata
from fitnova.db.base import Base

logger = get_logger(__name__)


def init_db(engine: Engine) -> None:
    """Create every table defined under `fitnova.db.models` if it doesn't
    already exist. Idempotent — safe to call on every app startup."""
    logger.info("Initializing database schema (%d tables)", len(Base.metadata.tables))
    Base.metadata.create_all(bind=engine)
    logger.info("Database schema ready")
