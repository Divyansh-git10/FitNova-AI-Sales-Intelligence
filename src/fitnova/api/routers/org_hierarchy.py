"""Organizations, teams, advisors, and advisor scorecards.

New org/team/advisor rows require zero code changes anywhere in this
router (docs Section 7) — every endpoint here queries the DB, never a
hardcoded list."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from fitnova.api.deps import get_db
from fitnova.db import repository
from fitnova.schemas.advisor import AdvisorRead
from fitnova.schemas.api_views import AdvisorScorecardView
from fitnova.schemas.organization import OrganizationRead
from fitnova.schemas.team import TeamRead

router = APIRouter(tags=["organization"])


@router.get("/organizations", response_model=list[OrganizationRead])
def list_organizations(db: Session = Depends(get_db)) -> list[OrganizationRead]:
    return [OrganizationRead.model_validate(o) for o in repository.list_organizations(db)]


@router.get("/teams", response_model=list[TeamRead])
def list_teams(organization_id: int | None = None, db: Session = Depends(get_db)) -> list[TeamRead]:
    return [
        TeamRead.model_validate(t)
        for t in repository.list_teams(db, organization_id=organization_id)
    ]


@router.get("/advisors", response_model=list[AdvisorRead])
def list_advisors(
    team_id: int | None = None, active_only: bool = False, db: Session = Depends(get_db)
) -> list[AdvisorRead]:
    return [
        AdvisorRead.model_validate(a)
        for a in repository.list_advisors(db, team_id=team_id, active_only=active_only)
    ]


@router.get("/advisors/{advisor_id}", response_model=AdvisorRead)
def get_advisor(advisor_id: int, db: Session = Depends(get_db)) -> AdvisorRead:
    advisor = repository.get_advisor(db, advisor_id)
    if advisor is None:
        raise HTTPException(status_code=404, detail=f"Advisor {advisor_id} not found")
    return AdvisorRead.model_validate(advisor)


def _to_scorecard_view(card: repository.AdvisorScorecard) -> AdvisorScorecardView:
    return AdvisorScorecardView(
        advisor_id=card.advisor_id,
        advisor_name=card.advisor_name,
        team_id=card.team_id,
        team_name=card.team_name,
        scored_call_count=card.scored_call_count,
        avg_overall_quality=card.avg_overall_quality,
        avg_dimension_scores=card.avg_dimension_scores,
        issue_count_by_severity=card.issue_count_by_severity,
        validated_issue_count=card.validated_issue_count,
        total_issue_count=card.total_issue_count,
    )


@router.get("/advisors/{advisor_id}/scorecard", response_model=AdvisorScorecardView)
def get_advisor_scorecard(advisor_id: int, db: Session = Depends(get_db)) -> AdvisorScorecardView:
    card = repository.advisor_scorecard(db, advisor_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"Advisor {advisor_id} not found")
    return _to_scorecard_view(card)


@router.get(
    "/analytics/advisor-leaderboard", response_model=list[AdvisorScorecardView], tags=["analytics"]
)
def get_advisor_leaderboard(
    team_id: int | None = None, db: Session = Depends(get_db)
) -> list[AdvisorScorecardView]:
    cards = repository.advisor_leaderboard(db, team_id=team_id)
    return [_to_scorecard_view(c) for c in cards]
