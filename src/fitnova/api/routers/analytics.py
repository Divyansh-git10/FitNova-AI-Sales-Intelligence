"""Executive analytics: org-wide KPIs, issue distribution, call mix."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from fitnova.api.deps import get_db
from fitnova.db import repository
from fitnova.schemas.api_views import ExecutiveSummaryView

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("/executive", response_model=ExecutiveSummaryView)
def get_executive_summary(
    organization_id: int | None = None,
    team_id: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> ExecutiveSummaryView:
    summary = repository.executive_summary(
        db, organization_id=organization_id, team_id=team_id, date_from=date_from, date_to=date_to
    )
    return ExecutiveSummaryView(
        total_calls=summary.total_calls,
        calls_by_type=summary.calls_by_type,
        scored_call_count=summary.scored_call_count,
        avg_overall_quality=summary.avg_overall_quality,
        avg_dimension_scores=summary.avg_dimension_scores,
        issue_count_by_severity=summary.issue_count_by_severity,
        issue_count_by_type=summary.issue_count_by_type,
        validated_issue_count=summary.validated_issue_count,
        unvalidated_issue_count=summary.unvalidated_issue_count,
    )
