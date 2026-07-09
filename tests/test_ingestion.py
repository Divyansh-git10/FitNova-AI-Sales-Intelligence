"""Tests for the ingestion adapters (docs Section 4.2, source-agnostic
ingestion)."""

from __future__ import annotations

import json

from fitnova.core.constants import SourceSystem
from fitnova.ingestion.crm_source import CRMSourceAdapter
from fitnova.ingestion.folder_source import FolderSourceAdapter


def test_folder_adapter_discovers_supported_files(tmp_path):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    inbox.mkdir()
    (inbox / "call_001.wav").write_bytes(b"fake-wav-bytes")
    (inbox / "notes.txt").write_text("not audio, should be ignored")

    adapter = FolderSourceAdapter(inbox_dir=inbox, processed_dir=processed)
    records = adapter.fetch_new_calls()

    assert len(records) == 1
    assert records[0].audio_path.name == "call_001.wav"
    assert records[0].source_system == SourceSystem.FOLDER


def test_folder_adapter_reads_sidecar_metadata(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    audio = inbox / "call_002.wav"
    audio.write_bytes(b"fake-wav-bytes")
    sidecar = inbox / "call_002.wav.meta.json"
    sidecar.write_text(
        json.dumps(
            {
                "advisor_external_id": "adv-042",
                "customer_ref": "+919876543210",
                "source_call_id": "ext-999",
            }
        )
    )

    adapter = FolderSourceAdapter(inbox_dir=inbox, processed_dir=tmp_path / "processed")
    records = adapter.fetch_new_calls()

    assert len(records) == 1
    assert records[0].advisor_external_id == "adv-042"
    assert records[0].customer_ref == "+919876543210"
    assert records[0].source_call_id == "ext-999"


def test_folder_adapter_falls_back_to_filename_parsing(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "adv-007__lead_call.wav").write_bytes(b"fake-wav-bytes")

    adapter = FolderSourceAdapter(inbox_dir=inbox, processed_dir=tmp_path / "processed")
    records = adapter.fetch_new_calls()

    assert records[0].advisor_external_id == "adv-007"


def test_folder_adapter_advisor_none_when_unresolvable(tmp_path):
    inbox = tmp_path / "inbox"
    inbox.mkdir()
    (inbox / "unnamed_call.wav").write_bytes(b"fake-wav-bytes")

    adapter = FolderSourceAdapter(inbox_dir=inbox, processed_dir=tmp_path / "processed")
    records = adapter.fetch_new_calls()

    assert records[0].advisor_external_id is None


def test_folder_adapter_mark_claimed_moves_file(tmp_path):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    inbox.mkdir()
    audio = inbox / "call_003.wav"
    audio.write_bytes(b"fake-wav-bytes")

    adapter = FolderSourceAdapter(inbox_dir=inbox, processed_dir=processed)
    [record] = adapter.fetch_new_calls()
    adapter.mark_claimed(record)

    assert not audio.exists()
    assert (processed / "call_003.wav").exists()
    # a second scan should find nothing left in the inbox
    assert adapter.fetch_new_calls() == []


def test_folder_adapter_mark_claimed_also_moves_sidecar(tmp_path):
    inbox = tmp_path / "inbox"
    processed = tmp_path / "processed"
    inbox.mkdir()
    audio = inbox / "call_004.wav"
    audio.write_bytes(b"fake-wav-bytes")
    sidecar = inbox / "call_004.wav.meta.json"
    sidecar.write_text(json.dumps({"advisor_external_id": "adv-001"}))

    adapter = FolderSourceAdapter(inbox_dir=inbox, processed_dir=processed)
    [record] = adapter.fetch_new_calls()
    adapter.mark_claimed(record)

    assert not sidecar.exists()
    assert (processed / "call_004.wav.meta.json").exists()


def test_crm_adapter_maps_foreign_field_names(tmp_path):
    manifest = tmp_path / "manifest.json"
    audio_file = tmp_path / "recording.wav"
    audio_file.write_bytes(b"fake")
    manifest.write_text(
        json.dumps(
            [
                {
                    "call_id": "crm-call-1",
                    "agent_code": "agent-55",
                    "lead_phone": "9999999999",
                    "recording_path": str(audio_file),
                    "call_started_at": "2026-01-01T10:00:00",
                }
            ]
        )
    )

    adapter = CRMSourceAdapter(manifest_path=manifest)
    records = adapter.fetch_new_calls()

    assert len(records) == 1
    record = records[0]
    assert record.source_system == SourceSystem.CRM
    assert record.source_call_id == "crm-call-1"
    assert record.advisor_external_id == "agent-55"
    assert record.customer_ref == "9999999999"
    assert record.audio_path == audio_file


def test_crm_adapter_returns_empty_when_manifest_missing(tmp_path):
    adapter = CRMSourceAdapter(manifest_path=tmp_path / "does_not_exist.json")
    assert adapter.fetch_new_calls() == []


def test_crm_adapter_skips_claimed_entries(tmp_path):
    manifest = tmp_path / "manifest.json"
    audio_file = tmp_path / "recording.wav"
    audio_file.write_bytes(b"fake")
    manifest.write_text(
        json.dumps(
            [{"call_id": "crm-call-1", "agent_code": "agent-1", "recording_path": str(audio_file)}]
        )
    )

    adapter = CRMSourceAdapter(manifest_path=manifest)
    [record] = adapter.fetch_new_calls()
    adapter.mark_claimed(record)

    assert adapter.fetch_new_calls() == []
