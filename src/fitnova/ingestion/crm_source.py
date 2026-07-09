"""CRM-export ingestion adapter — proves the pipeline is source-agnostic.

Real CRMs export call metadata in their own vocabulary (`agent_code`
instead of `advisor_external_id`, `lead_phone` instead of `customer_ref`,
etc.). This adapter reads a JSON manifest in that "foreign" shape and maps
it into the same `RawCallRecord` the folder adapter produces — nothing
downstream can tell the two apart, which is the actual proof of the
source-agnostic design (docs Section 4.2), not just a claim in prose.

No real CRM integration exists for this prototype; the manifest format
below stands in for "whatever a CRM's export API would return."
"""

from __future__ import annotations

import json
from pathlib import Path

from fitnova.core.constants import SourceSystem
from fitnova.core.logging_config import get_logger
from fitnova.ingestion.base import IngestionAdapter, RawCallRecord

logger = get_logger(__name__)

# CRM field name -> RawCallRecord field name. Kept as an explicit, visible
# mapping table (not scattered dict.get() calls) so plugging in a
# differently-shaped CRM export later is a one-line change here, not a
# rewrite of the adapter.
_FIELD_MAP = {
    "call_id": "source_call_id",
    "agent_code": "advisor_external_id",
    "lead_phone": "customer_ref",
    "recording_path": "audio_path",
    "call_started_at": "call_datetime",
}


class CRMSourceAdapter(IngestionAdapter):
    """Reads a CRM-style JSON export manifest and yields RawCallRecords."""

    source_system = SourceSystem.CRM

    def __init__(self, manifest_path: Path) -> None:
        self.manifest_path = Path(manifest_path)
        self._claimed_ids: set[str] = set()

    def fetch_new_calls(self) -> list[RawCallRecord]:
        if not self.manifest_path.exists():
            logger.debug("CRM manifest not found at %s, nothing to ingest", self.manifest_path)
            return []

        try:
            entries = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            logger.error("CRM manifest %s is not valid JSON: %s", self.manifest_path, exc)
            return []

        records: list[RawCallRecord] = []
        for entry in entries:
            source_call_id = entry.get("call_id")
            if source_call_id in self._claimed_ids:
                continue
            record = self._map_entry(entry)
            if record is not None:
                records.append(record)

        logger.info("CRMSourceAdapter found %d new call(s) in %s", len(records), self.manifest_path)
        return records

    def mark_claimed(self, record: RawCallRecord) -> None:
        if record.source_call_id:
            self._claimed_ids.add(record.source_call_id)

    def _map_entry(self, entry: dict) -> RawCallRecord | None:
        mapped: dict = {}
        for crm_field, target_field in _FIELD_MAP.items():
            if crm_field in entry:
                mapped[target_field] = entry[crm_field]

        audio_path = mapped.get("audio_path")
        if not audio_path:
            logger.warning("CRM entry missing recording_path, skipping: %s", entry)
            return None

        return RawCallRecord(
            source_system=self.source_system,
            source_call_id=mapped.get("source_call_id"),
            audio_path=Path(audio_path),
            advisor_external_id=mapped.get("advisor_external_id"),
            customer_ref=mapped.get("customer_ref"),
            call_datetime=mapped.get("call_datetime"),
            raw_metadata=entry,
        )
