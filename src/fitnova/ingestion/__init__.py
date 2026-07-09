"""Ingestion layer — source-agnostic call intake.

- `base.py`           - `IngestionAdapter` ABC and the normalized
                         `RawCallRecord` DTO every adapter must produce.
- `folder_source.py`  - watches `data/audio/inbox/` for new recordings.
- `crm_source.py`     - reads a CRM-style JSON export manifest, proving a
                         second source works without touching the pipeline,
                         DB, or analysis engine (docs Section 4.2).
- `registry.py`       - constructs the enabled adapters for this deployment.

See docs/01_PHASE1_DESIGN.md Section 4.2 for the design rationale.
"""

from fitnova.ingestion.base import IngestionAdapter, RawCallRecord
from fitnova.ingestion.crm_source import CRMSourceAdapter
from fitnova.ingestion.folder_source import FolderSourceAdapter
from fitnova.ingestion.registry import build_default_adapters

__all__ = [
    "IngestionAdapter",
    "RawCallRecord",
    "FolderSourceAdapter",
    "CRMSourceAdapter",
    "build_default_adapters",
]
