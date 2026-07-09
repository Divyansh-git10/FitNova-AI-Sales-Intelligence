"""Folder-watching ingestion adapter — the default source for this prototype.

Watches `Settings.audio_inbox_dir` for `.wav` / `.mp3` / `.m4a` files. Two
ways to attach metadata to a dropped file, checked in order:

1. **Sidecar JSON** — `<filename>.meta.json` next to the audio, e.g.
   `call_001.wav` + `call_001.wav.meta.json` containing
   `{"advisor_external_id": "adv-001", "customer_ref": "+91...", ...}`.
   This is the reliable path for any real audio you drop in the inbox
   yourself.
2. **Filename convention fallback** — `<advisor_external_id>__<anything>.wav`
   (double underscore separator). Used when no sidecar is present.

If neither yields an `advisor_external_id`, the record is still returned
(never silently dropped) — the orchestrator resolves it to
`CallType.PENDING_METADATA` rather than guessing (docs Section 9, "missing
metadata").

Note on the Phase 6 demo dataset: `scripts/seed_demo_data.py` does NOT go
through this adapter. There is no offline TTS available to turn realistic
sample dialogue into real speech audio, so real Whisper transcription
would just produce empty/garbage output on synthetic tone audio. Instead
that script writes DB rows directly, running the exact same real
`classify_call()` / `redact_segments()` / metrics functions this
orchestrator uses, on hand-authored transcript text standing in for ASR
output — see that script's module docstring for the full rationale. If
you have real recordings, this adapter (and `fitnova ingest`) is the
fully real path and does not involve the demo script at all.
"""

from __future__ import annotations

import json
from pathlib import Path

from fitnova.core.constants import SourceSystem
from fitnova.core.logging_config import get_logger
from fitnova.ingestion.base import IngestionAdapter, RawCallRecord

logger = get_logger(__name__)

SUPPORTED_EXTENSIONS = {".wav", ".mp3", ".m4a"}


class FolderSourceAdapter(IngestionAdapter):
    """Reads call recordings out of a local folder."""

    source_system = SourceSystem.FOLDER

    def __init__(self, inbox_dir: Path, processed_dir: Path) -> None:
        self.inbox_dir = Path(inbox_dir)
        self.processed_dir = Path(processed_dir)
        self.inbox_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def fetch_new_calls(self) -> list[RawCallRecord]:
        records: list[RawCallRecord] = []
        for path in sorted(self.inbox_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in SUPPORTED_EXTENSIONS:
                continue
            if path.name.endswith(".meta.json"):
                continue
            records.append(self._build_record(path))
        logger.info(
            "FolderSourceAdapter found %d candidate file(s) in %s", len(records), self.inbox_dir
        )
        return records

    def mark_claimed(self, record: RawCallRecord) -> None:
        """Move the audio (and its sidecar, if any) out of the inbox so the
        next scan doesn't resurface it. Idempotency against re-processing
        is ultimately enforced by `calls.content_hash`, not by this move —
        this is purely a housekeeping step to keep the inbox representing
        "not yet claimed" work.
        """
        source_path = record.audio_path
        if not source_path.exists():
            logger.warning("mark_claimed: %s no longer exists, nothing to move", source_path)
            return

        destination = self._unique_destination(self.processed_dir / source_path.name)
        source_path.rename(destination)
        logger.info("Claimed %s -> %s", source_path, destination)

        sidecar = self._sidecar_path(source_path)
        if sidecar.exists():
            sidecar.rename(self._unique_destination(self.processed_dir / sidecar.name))

    def _build_record(self, path: Path) -> RawCallRecord:
        sidecar_data = self._read_sidecar(path)
        advisor_external_id = sidecar_data.get("advisor_external_id")
        customer_ref = sidecar_data.get("customer_ref")
        source_call_id = sidecar_data.get("source_call_id")
        call_datetime = sidecar_data.get("call_datetime")

        if advisor_external_id is None:
            advisor_external_id = self._parse_advisor_from_filename(path)

        return RawCallRecord(
            source_system=self.source_system,
            source_call_id=source_call_id,
            audio_path=path,
            advisor_external_id=advisor_external_id,
            customer_ref=customer_ref,
            call_datetime=call_datetime,
            raw_metadata={"original_filename": path.name, **sidecar_data},
        )

    @staticmethod
    def _sidecar_path(audio_path: Path) -> Path:
        return audio_path.with_name(audio_path.name + ".meta.json")

    def _read_sidecar(self, audio_path: Path) -> dict:
        sidecar = self._sidecar_path(audio_path)
        if not sidecar.exists():
            return {}
        try:
            return json.loads(sidecar.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("Failed to parse sidecar %s: %s", sidecar, exc)
            return {}

    @staticmethod
    def _parse_advisor_from_filename(path: Path) -> str | None:
        stem = path.stem
        if "__" in stem:
            candidate = stem.split("__", 1)[0].strip()
            return candidate or None
        return None

    @staticmethod
    def _unique_destination(destination: Path) -> Path:
        if not destination.exists():
            return destination
        stem, suffix = destination.stem, destination.suffix
        counter = 1
        while True:
            candidate = destination.with_name(f"{stem}_{counter}{suffix}")
            if not candidate.exists():
                return candidate
            counter += 1
