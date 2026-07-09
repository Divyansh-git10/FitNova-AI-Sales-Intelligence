"""SQLAlchemy declarative base.

Every ORM model in `fitnova.db.models` inherits from `Base`. Kept in its
own module (rather than defined inline in `models/__init__.py`) so it can
be imported without triggering a full import of every model — useful for
`alembic`-style tooling later and for keeping import graphs acyclic.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Declarative base class for all FitNova ORM models."""
