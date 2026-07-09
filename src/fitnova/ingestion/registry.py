"""Maps `SourceSystem` -> configured `IngestionAdapter` instance(s).

The orchestrator asks the registry for "every adapter currently enabled"
rather than importing `FolderSourceAdapter` directly — this is the seam
that keeps the orchestrator ignorant of which concrete sources exist
(docs Section 4.2). Enabling/disabling a source or adding a new one is a
change here, not in the orchestrator.
"""

from __future__ import annotations

from fitnova.core.config import Settings
from fitnova.ingestion.base import IngestionAdapter
from fitnova.ingestion.crm_source import CRMSourceAdapter
from fitnova.ingestion.folder_source import FolderSourceAdapter


def build_default_adapters(settings: Settings) -> list[IngestionAdapter]:
    """Construct the adapters enabled for this deployment.

    The folder adapter is always enabled (it is the default source for the
    prototype). The CRM adapter is included too, reading from a manifest
    path under the data directory — if that manifest doesn't exist yet, it
    simply yields zero records (see `CRMSourceAdapter.fetch_new_calls`),
    which is what "a new source can be added without code changes"
    concretely looks like: the seam already exists, wiring in a live CRM
    later is just pointing `manifest_path` at a real export.
    """
    folder_adapter = FolderSourceAdapter(
        inbox_dir=settings.resolved_audio_inbox_dir(),
        processed_dir=settings.resolved_processed_audio_dir(),
    )
    crm_manifest_path = settings.resolved_data_dir() / "crm_exports" / "manifest.json"
    crm_adapter = CRMSourceAdapter(manifest_path=crm_manifest_path)

    return [folder_adapter, crm_adapter]
