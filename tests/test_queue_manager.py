"""Tests for `QueueManager` — the processing queue's explicit state
transitions and dashboard-visible snapshot (Phase 3 addendum)."""

from __future__ import annotations

from fitnova.core.constants import CallType, PipelineStage, ProcessingStatusEnum, SourceSystem
from fitnova.db.models import Advisor, Call, Organization, Team
from fitnova.pipeline.queue_manager import QueueManager


def _make_call(session, content_hash: str = "a" * 64) -> Call:
    org = Organization(name="FitNova")
    team = Team(name="Pod A", organization=org)
    advisor = Advisor(name="Asha Rao", team=team, external_id="adv-001")
    call = Call(
        advisor=advisor,
        source_system=SourceSystem.FOLDER,
        call_type=CallType.UNKNOWN,
        content_hash=content_hash,
    )
    session.add(call)
    session.commit()
    return call


def test_enqueue_creates_in_progress_status(db_session):
    call = _make_call(db_session)
    queue = QueueManager(db_session)

    status = queue.enqueue(call_id=call.id, content_hash=call.content_hash)
    db_session.commit()

    assert status.pipeline_stage == PipelineStage.INGESTED
    assert status.status == ProcessingStatusEnum.IN_PROGRESS
    assert status.retry_count == 0
    assert status.started_at is not None


def test_find_by_content_hash(db_session):
    call = _make_call(db_session)
    queue = QueueManager(db_session)
    queue.enqueue(call_id=call.id, content_hash=call.content_hash)
    db_session.commit()

    found = queue.find_by_content_hash(call.content_hash)
    assert found is not None
    assert found.call_id == call.id

    assert queue.find_by_content_hash("nonexistent") is None


def test_advance_updates_stage_only(db_session):
    call = _make_call(db_session)
    queue = QueueManager(db_session)
    status = queue.enqueue(call_id=call.id, content_hash=call.content_hash)

    queue.advance(status, PipelineStage.TRANSCRIBED)

    assert status.pipeline_stage == PipelineStage.TRANSCRIBED
    assert status.status == ProcessingStatusEnum.IN_PROGRESS  # unchanged


def test_mark_completed_sets_terminal_state(db_session):
    call = _make_call(db_session)
    queue = QueueManager(db_session)
    status = queue.enqueue(call_id=call.id, content_hash=call.content_hash)

    queue.mark_completed(status, final_stage=PipelineStage.CLASSIFIED)

    assert status.status == ProcessingStatusEnum.COMPLETED
    assert status.pipeline_stage == PipelineStage.CLASSIFIED
    assert status.completed_at is not None


def test_mark_failed_records_error_without_incrementing_retry(db_session):
    call = _make_call(db_session)
    queue = QueueManager(db_session)
    status = queue.enqueue(call_id=call.id, content_hash=call.content_hash)

    queue.mark_failed(status, "boom: whisper OOM")

    assert status.status == ProcessingStatusEnum.FAILED
    assert "boom" in status.last_error
    assert status.retry_count == 0  # retry_count increments on the NEXT attempt, not on failure


def test_begin_retry_increments_count_and_clears_error(db_session):
    call = _make_call(db_session)
    queue = QueueManager(db_session)
    status = queue.enqueue(call_id=call.id, content_hash=call.content_hash)
    queue.mark_failed(status, "first failure")

    queue.begin_retry(status)

    assert status.retry_count == 1
    assert status.last_error is None
    assert status.status == ProcessingStatusEnum.IN_PROGRESS


def test_dashboard_snapshot_returns_joined_rows(db_session):
    call = _make_call(db_session)
    queue = QueueManager(db_session)
    status = queue.enqueue(call_id=call.id, content_hash=call.content_hash)
    queue.mark_completed(status, final_stage=PipelineStage.CLASSIFIED)
    db_session.commit()

    snapshot = queue.dashboard_snapshot()

    assert len(snapshot) == 1
    row = snapshot[0]
    assert row.call_id == call.id
    assert row.advisor_name == "Asha Rao"
    assert row.status == "COMPLETED"
    assert row.pipeline_stage == "CLASSIFIED"


def test_dashboard_snapshot_handles_unresolved_advisor(db_session):
    org = Organization(name="FitNova")
    Team(name="Pod A", organization=org)
    db_session.add(org)
    db_session.flush()
    call = Call(
        advisor_id=None,
        source_system=SourceSystem.FOLDER,
        call_type=CallType.PENDING_METADATA,
        content_hash="b" * 64,
    )
    db_session.add(call)
    db_session.commit()

    queue = QueueManager(db_session)
    queue.enqueue(call_id=call.id, content_hash=call.content_hash)
    db_session.commit()

    snapshot = queue.dashboard_snapshot()
    assert snapshot[0].advisor_name is None
    assert snapshot[0].call_type == "PENDING_METADATA"
