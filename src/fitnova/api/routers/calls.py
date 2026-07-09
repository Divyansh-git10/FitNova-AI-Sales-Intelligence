"""Calls: list (filtered/paginated), detail (transcript + score + issues +
insight in one call), and the raw evidence feed for a call."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from fitnova.api.deps import get_db
from fitnova.core.constants import CallType
from fitnova.db import repository
from fitnova.schemas.api_views import (
    CallDetail,
    CallInsightView,
    CallListItem,
    IssueView,
    ScoreView,
    TranscriptSegmentView,
)
from fitnova.schemas.common import PaginatedResponse

router = APIRouter(prefix="/calls", tags=["calls"])


@router.get("", response_model=PaginatedResponse[CallListItem])
def list_calls(
    organization_id: int | None = None,
    team_id: int | None = None,
    advisor_id: int | None = None,
    call_type: CallType | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    min_overall_quality: float | None = Query(default=None, ge=0.0, le=10.0),
    max_overall_quality: float | None = Query(default=None, ge=0.0, le=10.0),
    only_with_validated_issues: bool = False,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
) -> PaginatedResponse[CallListItem]:
    filters = repository.CallListFilters(
        organization_id=organization_id,
        team_id=team_id,
        advisor_id=advisor_id,
        call_type=call_type.value if call_type else None,
        date_from=date_from,
        date_to=date_to,
        min_overall_quality=min_overall_quality,
        max_overall_quality=max_overall_quality,
        only_with_validated_issues=only_with_validated_issues,
    )
    calls, total = repository.list_calls(db, filters, page=page, page_size=page_size)
    items = [
        CallListItem(
            id=c.id,
            advisor_id=c.advisor_id,
            advisor_name=c.advisor.name if c.advisor else None,
            team_name=c.advisor.team.name if c.advisor and c.advisor.team else None,
            call_type=c.call_type,
            call_datetime=c.call_datetime,
            duration_seconds=c.duration_seconds,
            overall_quality=c.score.overall_quality if c.score else None,
            validated_issue_count=sum(1 for i in c.issues if i.is_validated),
        )
        for c in calls
    ]
    return PaginatedResponse(items=items, total=total, page=page, page_size=page_size)


@router.get("/{call_id}", response_model=CallDetail)
def get_call(call_id: int, db: Session = Depends(get_db)) -> CallDetail:
    call = repository.get_call_detail(db, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail=f"Call {call_id} not found")

    segments = call.transcript.segments if call.transcript else []
    status_row = call.processing_status

    return CallDetail(
        id=call.id,
        advisor_id=call.advisor_id,
        advisor_name=call.advisor.name if call.advisor else None,
        team_id=call.advisor.team_id if call.advisor else None,
        team_name=call.advisor.team.name if call.advisor and call.advisor.team else None,
        call_type=call.call_type,
        call_datetime=call.call_datetime,
        duration_seconds=call.duration_seconds,
        language_detected=call.language_detected,
        content_hash=call.content_hash,
        pipeline_status=status_row.status.value if status_row else None,
        pipeline_stage=status_row.pipeline_stage.value if status_row else None,
        segments=[TranscriptSegmentView.model_validate(s) for s in segments],
        redacted_text=call.transcript.redacted_text if call.transcript else None,
        score=ScoreView.model_validate(call.score) if call.score else None,
        issues=[IssueView.model_validate(i) for i in call.issues],
        insight=CallInsightView.model_validate(call.call_insight) if call.call_insight else None,
    )


@router.get("/{call_id}/evidence", response_model=list[IssueView])
def get_call_evidence(call_id: int, db: Session = Depends(get_db)) -> list[IssueView]:
    call = db.get(repository.Call, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail=f"Call {call_id} not found")
    issues = repository.get_call_evidence(db, call_id)
    return [IssueView.model_validate(i) for i in issues]
