"""Tests for the Phase 6 demo dataset seed script.

Verifies the three properties that matter most for a script meant to be
run repeatedly against a real (if empty) database: it produces every
`CallType` the real pipeline can produce, it is idempotent, and `--force`
cleans up fully (including advisor-less PENDING_METADATA calls, which
have no FK path from the demo Organization for cascade deletes to reach).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fitnova.core.constants import CallType  # noqa: E402
from fitnova.db.models import AuditLog, Call, Organization  # noqa: E402
from scripts.seed_demo_data import DEMO_CALLS, DEMO_ORG_NAME, seed  # noqa: E402


@pytest.fixture()
def isolated_demo_audio_dir(tmp_path, monkeypatch):
    """Redirect the demo script's audio output into a pytest tmp_path so
    test runs never touch (or depend on) the real project's data/ dir."""
    import scripts.seed_demo_data as seed_mod

    monkeypatch.setattr(seed_mod, "DEMO_AUDIO_DIR", tmp_path / "demo_samples")
    return tmp_path / "demo_samples"


def test_seed_creates_every_defined_demo_call(
    settings, session_factory: sessionmaker, isolated_demo_audio_dir
):
    created = seed(session_factory, settings, force=False)
    assert len(created) == len(DEMO_CALLS)


def test_seed_covers_every_call_type_the_classifier_can_produce(
    settings, session_factory: sessionmaker, isolated_demo_audio_dir
):
    seed(session_factory, settings, force=False)
    session = session_factory()
    try:
        call_types = {c.call_type for c in session.execute(select(Call)).scalars().all()}
    finally:
        session.close()

    # Every branch classify_call() (plus the orchestrator's PENDING_METADATA
    # short-circuit) can take, is exercised by at least one demo call.
    assert call_types == {
        CallType.SALES,
        CallType.WRONG_NUMBER,
        CallType.INTERNAL,
        CallType.NO_SPEECH,
        CallType.UNSUPPORTED_LANGUAGE,
        CallType.PENDING_METADATA,
    }


def test_seed_is_idempotent(settings, session_factory: sessionmaker, isolated_demo_audio_dir):
    first = seed(session_factory, settings, force=False)
    second = seed(session_factory, settings, force=False)

    assert len(first) == len(DEMO_CALLS)
    assert second == []  # nothing new: every content_hash already exists

    session = session_factory()
    try:
        total = len(session.execute(select(Call)).scalars().all())
    finally:
        session.close()
    assert total == len(DEMO_CALLS)


def test_seed_generates_deterministic_audio_across_runs(
    settings, session_factory: sessionmaker, isolated_demo_audio_dir
):
    """Regression test: an earlier version used the builtin, per-process
    randomized `hash()` to vary tone frequency, which silently produced a
    different content_hash on every run and broke idempotency."""
    seed(session_factory, settings, force=False)
    first_bytes = {p.name: p.read_bytes() for p in isolated_demo_audio_dir.glob("*.wav")}

    seed(session_factory, settings, force=True)
    second_bytes = {p.name: p.read_bytes() for p in isolated_demo_audio_dir.glob("*.wav")}

    assert first_bytes == second_bytes


def test_force_wipes_advisor_less_pending_metadata_call(
    settings, session_factory: sessionmaker, isolated_demo_audio_dir
):
    """The `call_pending_metadata` demo call has advisor_id=None by design,
    so it has no FK path from Organization -> Team -> Advisor -> Call for
    a cascade delete to reach. --force must find and delete it explicitly."""
    seed(session_factory, settings, force=False)
    seed(session_factory, settings, force=True)

    session = session_factory()
    try:
        pending = (
            session.execute(select(Call).where(Call.call_type == CallType.PENDING_METADATA))
            .scalars()
            .all()
        )
        assert len(pending) == 1  # not zero (over-deleted), not two (leaked orphan)

        orgs = (
            session.execute(select(Organization).where(Organization.name == DEMO_ORG_NAME))
            .scalars()
            .all()
        )
        assert len(orgs) == 1
    finally:
        session.close()


def test_every_seeded_call_is_tagged_for_cleanup(
    settings, session_factory: sessionmaker, isolated_demo_audio_dir
):
    # seed()'s session_factory session is closed by the time it returns, so
    # `created`'s Call instances are detached — reload IDs via a fresh
    # session rather than touching attributes on the returned (expired)
    # objects, which would raise DetachedInstanceError.
    created = seed(session_factory, settings, force=False)
    session = session_factory()
    try:
        created_ids = set(session.execute(select(Call.id)).scalars().all())
        tagged_ids = set(
            session.execute(
                select(AuditLog.entity_id).where(
                    AuditLog.entity_type == "Call", AuditLog.action == "DEMO_DATA_SEEDED"
                )
            )
            .scalars()
            .all()
        )
    finally:
        session.close()
    assert len(created) == len(created_ids)
    assert tagged_ids == created_ids


def test_seeded_sales_calls_have_no_score_until_analyzed(
    settings, session_factory: sessionmaker, isolated_demo_audio_dir
):
    """The script must never fabricate a Score row itself."""
    seed(session_factory, settings, force=False)
    session = session_factory()
    try:
        sales_calls = (
            session.execute(select(Call).where(Call.call_type == CallType.SALES)).scalars().all()
        )
        assert sales_calls  # sanity: at least one SALES demo call exists
        for call in sales_calls:
            assert call.score is None
    finally:
        session.close()
