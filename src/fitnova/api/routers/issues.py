"""Issue drill-down, evidence-in-context, and the human feedback loop
(contest/confirm a flag)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from fitnova.api.deps import get_current_role, get_db
from fitnova.core.constants import IssueStatus, IssueType, ReviewerRole, Severity
from fitnova.db import repository
from fitnova.schemas.api_views import (
    FeedbackRequest,
    IssueView,
    IssueWithContext,
    TranscriptSegmentView,
)
from fitnova.schemas.common import PaginatedResponse
from fitnova.schemas.feedback import FeedbackRead

router = APIRouter(tags=["issues"])


@router.get("/issues", response_model=PaginatedResponse[IssueView])
def list_issues(
    severity: Severity | None = None,
    issue_type: IssueType | None = None,
    status: IssueStatus | None = None,
    is_validated: bool | None = None,
    advisor_id: int | None = None,
    team_id: int | None = None,
    call_id: int | None = None,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=200),
    db: Session = Depends(get_db),
) -> PaginatedResponse[IssueView]:
    filters = repository.IssueListFilters(
        severity=severity,
        issue_type=issue_type,
        status=status,
        is_validated=is_validated,
        advisor_id=advisor_id,
        team_id=team_id,
        call_id=call_id,
    )
    issues, total = repository.list_issues(db, filters, page=page, page_size=page_size)
    return PaginatedResponse(
        items=[IssueView.model_validate(i) for i in issues],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/issues/{issue_id}", response_model=IssueWithContext)
def get_issue(issue_id: int, db: Session = Depends(get_db)) -> IssueWithContext:
    result = repository.get_issue_with_context(db, issue_id)
    if result is None:
        raise HTTPException(status_code=404, detail=f"Issue {issue_id} not found")
    issue = result["issue"]
    advisor_name = issue.call.advisor.name if issue.call and issue.call.advisor else None
    return IssueWithContext(
        issue=IssueView.model_validate(issue),
        call_id=issue.call_id,
        advisor_name=advisor_name,
        context_segments=[
            TranscriptSegmentView.model_validate(s) for s in result["context_segments"]
        ],
    )


@router.post("/feedback", response_model=FeedbackRead, status_code=201)
def submit_feedback(
    payload: FeedbackRequest,
    role: ReviewerRole = Depends(get_current_role),
    db: Session = Depends(get_db),
) -> FeedbackRead:
    call = db.get(repository.Call, payload.call_id)
    if call is None:
        raise HTTPException(status_code=404, detail=f"Call {payload.call_id} not found")
    if payload.issue_id is not None and db.get(repository.Issue, payload.issue_id) is None:
        raise HTTPException(status_code=404, detail=f"Issue {payload.issue_id} not found")

    feedback = repository.create_feedback(
        db,
        call_id=payload.call_id,
        reviewer_role=role,
        reviewer_id=payload.reviewer_id,
        feedback_type=payload.feedback_type,
        issue_id=payload.issue_id,
        comment=payload.comment,
    )
    db.flush()
    db.refresh(feedback)
    return FeedbackRead.model_validate(feedback)


@router.get("/calls/{call_id}/feedback", response_model=list[FeedbackRead])
def list_feedback_for_call(call_id: int, db: Session = Depends(get_db)) -> list[FeedbackRead]:
    if db.get(repository.Call, call_id) is None:
        raise HTTPException(status_code=404, detail=f"Call {call_id} not found")
    return [FeedbackRead.model_validate(f) for f in repository.list_feedback_for_call(db, call_id)]
