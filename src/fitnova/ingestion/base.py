"""Source-agnostic ingestion contract.

Every call source (a folder of files, a CRM export, eventually a real
telephony/dialer webhook) implements `IngestionAdapter.fetch_new_calls()`
and returns a list of `RawCallRecord` — a normalized DTO that is the ONLY
thing the rest of the pipeline ever sees. Nothing downstream of ingestion
knows or cares which adapter produced a record (docs Section 4.2).

Adding a new source later means writing one new `IngestionAdapter`
subclass and registering it in `registry.py` — the orchestrator, DB
schema, and analysis engine are untouched.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from fitnova.core.constants import SourceSystem


class RawCallRecord(BaseModel):
    """Normalized shape every ingestion adapter must produce.

    `advisor_external_id` is deliberately a string, not a foreign key -
    resolving it to an `Advisor` row (or flagging it unresolved, see
    `CallType.PENDING_METADATA`) is the orchestrator's job, not the
    adapter's. The adapter's only responsibility is faithfully translating
    its source's native format into this shape.
    """

    model_config = ConfigDict(frozen=True)

    source_system: SourceSystem
    source_call_id: str | None = None
    audio_path: Path
    advisor_external_id: str | None = None
    customer_ref: str | None = Field(
        default=None,
        description="Raw customer identifier (e.g. phone number) as seen at the "
        "source. Hashed/masked by the orchestrator before it ever reaches "
        "storage — an adapter must never write this to the DB directly.",
    )
    call_datetime: datetime | None = None
    raw_metadata: dict = Field(default_factory=dict)


class IngestionAdapter(ABC):
    """Abstract base every concrete source adapter implements."""

    source_system: SourceSystem

    @abstractmethod
    def fetch_new_calls(self) -> list[RawCallRecord]:
        """Return every call this adapter can see that hasn't been claimed
        yet. Adapters do NOT need to worry about idempotency/duplicates —
        that is enforced centrally via `calls.content_hash` (docs Section
        5.3). An adapter is free to return the same file on every call;
        the orchestrator is what guarantees a call is never double
        processed.
        """
        raise NotImplementedError

    @abstractmethod
    def mark_claimed(self, record: RawCallRecord) -> None:
        """Called by the orchestrator once a record has been successfully
        handed off to the pipeline, so the adapter can avoid re-surfacing
        it next scan (e.g. moving a file out of the inbox). Implementations
        that have no notion of "claiming" (e.g. a pure read-only CRM feed)
        may no-op here; idempotency is still enforced by content_hash.
        """
        raise NotImplementedError
