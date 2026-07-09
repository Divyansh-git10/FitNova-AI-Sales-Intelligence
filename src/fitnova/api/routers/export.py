"""CSV and PDF export endpoints — thin HTTP wrappers around
`fitnova.reporting`, which owns the actual report content (docs Phase 5:
"CSV export", "PDF export")."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from fitnova.api.deps import get_db
from fitnova.core.constants import CallType
from fitnova.db import repository
from fitnova.reporting import (
    advisor_scorecard_to_pdf,
    call_report_to_pdf,
    calls_to_csv,
    issues_to_csv,
)
from fitnova.schemas.api_views import CallListItem, IssueView

router = APIRouter(prefix="/export", tags=["export"])


@router.get("/calls.csv")
def export_calls_csv(
    organization_id: int | None = None,
    team_id: int | None = None,
    advisor_id: int | None = None,
    call_type: CallType | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    filters = repository.CallListFilters(
        organization_id=organization_id,
        team_id=team_id,
        advisor_id=advisor_id,
        call_type=call_type.value if call_type else None,
        date_from=date_from,
        date_to=date_to,
    )
    calls, _total = repository.list_calls(db, filters, page=1, page_size=10_000)
    rows = [
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
        ).model_dump()
        for c in calls
    ]
    csv_text = calls_to_csv(rows)
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=fitnova_calls.csv"},
    )


@router.get("/issues.csv")
def export_issues_csv(
    advisor_id: int | None = None,
    team_id: int | None = None,
    db: Session = Depends(get_db),
) -> StreamingResponse:
    filters = repository.IssueListFilters(advisor_id=advisor_id, team_id=team_id)
    issues, _total = repository.list_issues(db, filters, page=1, page_size=10_000)
    rows = []
    for issue in issues:
        row = IssueView.model_validate(issue).model_dump()
        row["advisor_name"] = issue.call.advisor.name if issue.call and issue.call.advisor else None
        rows.append(row)
    csv_text = issues_to_csv(rows)
    return StreamingResponse(
        iter([csv_text]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=fitnova_issues.csv"},
    )


@router.get("/calls/{call_id}.pdf")
def export_call_pdf(call_id: int, db: Session = Depends(get_db)) -> Response:
    call = repository.get_call_detail(db, call_id)
    if call is None:
        raise HTTPException(status_code=404, detail=f"Call {call_id} not found")

    call_dict = {
        "id": call.id,
        "advisor_name": call.advisor.name if call.advisor else None,
        "team_name": call.advisor.team.name if call.advisor and call.advisor.team else None,
        "call_type": call.call_type.value,
        "call_datetime": call.call_datetime,
        "duration_seconds": call.duration_seconds,
    }
    score_dict = None
    if call.score:
        score_dict = {
            "needs_discovery": call.score.needs_discovery,
            "rapport": call.score.rapport,
            "empathy": call.score.empathy,
            "listening": call.score.listening,
            "product_knowledge": call.score.product_knowledge,
            "objection_handling": call.score.objection_handling,
            "compliance": call.score.compliance,
            "trial_booking": call.score.trial_booking,
            "closing": call.score.closing,
            "overall_quality": call.score.overall_quality,
            "evidence": call.score.evidence,
        }
    issue_dicts = [
        {
            "severity": i.severity.value,
            "issue_type": i.issue_type.value,
            "speaker": i.speaker.value,
            "quoted_text": i.quoted_text,
            "reason": i.reason,
            "is_validated": i.is_validated,
        }
        for i in call.issues
    ]
    insight_dict = None
    if call.call_insight:
        insight_dict = {
            "executive_summary": call.call_insight.executive_summary,
            "customer_intent": call.call_insight.customer_intent,
            "improvement_suggestions": call.call_insight.improvement_suggestions,
            "recommended_coaching": call.call_insight.recommended_coaching,
            "next_best_action": call.call_insight.next_best_action,
        }

    pdf_bytes = call_report_to_pdf(call_dict, score_dict, issue_dicts, insight_dict)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=fitnova_call_{call_id}.pdf"},
    )


@router.get("/advisors/{advisor_id}/scorecard.pdf")
def export_advisor_scorecard_pdf(advisor_id: int, db: Session = Depends(get_db)) -> Response:
    card = repository.advisor_scorecard(db, advisor_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"Advisor {advisor_id} not found")
    pdf_bytes = advisor_scorecard_to_pdf(
        {
            "advisor_name": card.advisor_name,
            "team_name": card.team_name,
            "scored_call_count": card.scored_call_count,
            "avg_overall_quality": card.avg_overall_quality,
            "avg_dimension_scores": card.avg_dimension_scores,
            "issue_count_by_severity": card.issue_count_by_severity,
            "validated_issue_count": card.validated_issue_count,
            "total_issue_count": card.total_issue_count,
        }
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": (
                f"attachment; filename=fitnova_advisor_{advisor_id}_scorecard.pdf"
            )
        },
    )
