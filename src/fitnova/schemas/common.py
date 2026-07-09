"""Shared Pydantic building blocks used across every schema module.

Naming convention used throughout `fitnova.schemas`:

- `<Entity>Base`    — fields common to create and read variants.
- `<Entity>Create`  — payload shape accepted by the API/pipeline to create
  a row (no `id`, no server-generated timestamps).
- `<Entity>Read`    — payload shape returned by the API (`id`,
  `created_at`, and any server-computed fields), built from ORM instances
  via `model_config = ConfigDict(from_attributes=True)`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class ORMModel(BaseModel):
    """Base for any schema that will be built from a SQLAlchemy ORM
    instance via `Model.model_validate(orm_obj)`."""

    model_config = ConfigDict(from_attributes=True)


class TimestampedRead(ORMModel):
    """Common fields on every `*Read` schema."""

    id: int
    created_at: datetime


class PaginatedResponse(BaseModel, Generic[T]):
    """Generic pagination envelope returned by list endpoints."""

    items: list[T]
    total: int
    page: int
    page_size: int
