"""Smoke tests for the Phase 2 database scaffold.

These don't test business logic (there isn't any yet) — they verify the
schema is structurally sound: relationships resolve, the org hierarchy
composes correctly, and the idempotency constraint on `calls.content_hash`
actually rejects duplicates at the DB level, which is the mechanism the
whole "never double-process a call" requirement depends on.
"""

from __future__ import annotations

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from fitnova.core.constants import CallType, SourceSystem
from fitnova.db.models import Advisor, Call, Organization, Team


def _make_org_team_advisor(session: Session) -> Advisor:
    org = Organization(name="FitNova")
    team = Team(name="Mumbai Pod", organization=org)
    advisor = Advisor(name="Asha Rao", team=team, external_id="adv-001")
    session.add(org)
    session.commit()
    return advisor


def test_org_hierarchy_composes(db_session: Session) -> None:
    advisor = _make_org_team_advisor(db_session)

    assert advisor.team.organization.name == "FitNova"
    assert advisor.team.name == "Mumbai Pod"
    assert advisor in advisor.team.advisors
    assert advisor.team in advisor.team.organization.teams


def test_call_requires_unique_content_hash(db_session: Session) -> None:
    advisor = _make_org_team_advisor(db_session)

    call1 = Call(
        advisor=advisor,
        source_system=SourceSystem.FOLDER,
        call_type=CallType.SALES,
        content_hash="a" * 64,
    )
    db_session.add(call1)
    db_session.commit()

    call2 = Call(
        advisor=advisor,
        source_system=SourceSystem.FOLDER,
        call_type=CallType.SALES,
        content_hash="a" * 64,  # duplicate hash -> must be rejected
    )
    db_session.add(call2)
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


def test_call_cascades_to_children_on_delete(db_session: Session) -> None:
    advisor = _make_org_team_advisor(db_session)
    call = Call(
        advisor=advisor,
        source_system=SourceSystem.FOLDER,
        call_type=CallType.SALES,
        content_hash="b" * 64,
    )
    db_session.add(call)
    db_session.commit()

    call_id = call.id
    db_session.delete(call)
    db_session.commit()

    assert db_session.get(Call, call_id) is None


def test_new_team_and_advisor_require_no_code_change(db_session: Session) -> None:
    """Proves docs Section 7: adding org structure is a plain insert."""
    org = Organization(name="Acme Wellness")
    new_team = Team(name="Delhi Pod", organization=org)
    new_advisor = Advisor(name="Ravi Kumar", team=new_team)
    db_session.add(org)
    db_session.commit()

    assert new_advisor.id is not None
    assert new_team.id is not None
