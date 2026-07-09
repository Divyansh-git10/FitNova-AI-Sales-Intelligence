"""Tests for the FastAPI layer: routing, response shapes, 404s, feedback
mutation, and CSV/PDF export — exercised against the same hermetic
in-memory DB the rest of the suite uses (see `api_client` in conftest.py)."""

from __future__ import annotations

from datetime import datetime, timezone

from fitnova.core.constants import (
    CallType,
    ConfidenceLabel,
    IssueStatus,
    IssueType,
    PipelineStage,
    ProcessingStatusEnum,
    Severity,
    SourceSystem,
    SpeakerLabel,
)
from fitnova.db.models import (
    Advisor,
    Call,
    CallInsight,
    Issue,
    Organization,
    PipelineBenchmark,
    ProcessingStatus,
    Score,
    Team,
    Transcript,
    TranscriptSegment,
)

_DIMS = [
    "needs_discovery",
    "rapport",
    "empathy",
    "listening",
    "product_knowledge",
    "objection_handling",
    "compliance",
    "trial_booking",
    "closing",
]


def _seed_full_call(session, *, with_issue: bool = True):
    org = Organization(name="FitNova")
    team = Team(name="Mumbai Pod", organization=org)
    advisor = Advisor(name="Asha Rao", team=team, external_id="adv-1")
    session.add_all([org, team, advisor])
    session.flush()

    call = Call(
        advisor=advisor,
        source_system=SourceSystem.FOLDER,
        content_hash="api-hash-1",
        call_type=CallType.SALES,
        duration_seconds=125.0,
        call_datetime=datetime.now(timezone.utc),
    )
    session.add(call)
    session.flush()

    transcript = Transcript(
        call_id=call.id, raw_text="raw", redacted_text="redacted", word_count=8, avg_confidence=0.9
    )
    session.add(transcript)
    session.flush()
    seg = TranscriptSegment(
        transcript_id=transcript.id,
        segment_index=0,
        speaker_label=SpeakerLabel.ADVISOR,
        start_time=0.0,
        end_time=5.0,
        text="I can guarantee results",
    )
    session.add(seg)
    session.flush()

    score = Score(
        call_id=call.id,
        **{d: 7 for d in _DIMS},
        overall_quality=7.2,
        scoring_version="v1.0.0",
        evidence={
            d: {
                "reasoning": "ok",
                "evidence_quote": "q",
                "confidence": 0.9,
                "confidence_label": "HIGH",
            }
            for d in _DIMS
        },
    )
    session.add(score)

    issue = None
    if with_issue:
        issue = Issue(
            call_id=call.id,
            segment_id=seg.id,
            issue_type=IssueType.OVER_PROMISING,
            severity=Severity.CRITICAL,
            speaker=SpeakerLabel.ADVISOR,
            quoted_text="I can guarantee results",
            reason="guarantee",
            confidence_score=0.9,
            confidence_label=ConfidenceLabel.HIGH,
            is_validated=True,
            status=IssueStatus.OPEN,
        )
        session.add(issue)

    insight = CallInsight(
        call_id=call.id,
        executive_summary="Advisor guaranteed an outcome.",
        customer_intent="Interested.",
        improvement_suggestions=["Avoid guarantees"],
        recommended_coaching="Coach on compliance.",
        next_best_action="Follow up in 24h.",
    )
    session.add(insight)

    status = ProcessingStatus(
        call_id=call.id,
        content_hash="api-hash-1",
        pipeline_stage=PipelineStage.COMPLETED,
        status=ProcessingStatusEnum.COMPLETED,
        retry_count=0,
    )
    session.add(status)

    bench = PipelineBenchmark(
        call_id=call.id,
        total_pipeline_time_ms=450.0,
        transcription_time_ms=250.0,
        llm_time_ms=90.0,
        audio_duration_seconds=125.0,
        real_time_factor=0.0036,
    )
    session.add(bench)
    session.commit()

    if issue is not None:
        session.refresh(issue)
    return call.id, advisor.id, (issue.id if issue else None)


def test_health_endpoint(api_client):
    r = api_client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["database_reachable"] is True
    assert "queue_counts" in body


def test_root_endpoint(api_client):
    r = api_client.get("/")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_list_calls_empty(api_client):
    r = api_client.get("/calls")
    assert r.status_code == 200
    body = r.json()
    assert body == {"items": [], "total": 0, "page": 1, "page_size": 25}


def test_call_detail_full_lifecycle(api_client, session_factory):
    session = session_factory()
    call_id, advisor_id, issue_id = _seed_full_call(session)
    session.close()

    r = api_client.get(f"/calls/{call_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["advisor_name"] == "Asha Rao"
    assert body["score"]["overall_quality"] == 7.2
    assert len(body["issues"]) == 1
    assert body["insight"]["executive_summary"].startswith("Advisor guaranteed")
    assert len(body["segments"]) == 1

    r_list = api_client.get("/calls")
    assert r_list.status_code == 200
    assert r_list.json()["total"] == 1
    assert r_list.json()["items"][0]["overall_quality"] == 7.2


def test_call_detail_404(api_client):
    r = api_client.get("/calls/999999")
    assert r.status_code == 404


def test_call_evidence_endpoint(api_client, session_factory):
    session = session_factory()
    call_id, _advisor_id, _issue_id = _seed_full_call(session)
    session.close()

    r = api_client.get(f"/calls/{call_id}/evidence")
    assert r.status_code == 200
    body = r.json()
    assert len(body) == 1
    assert body[0]["issue_type"] == "OVER_PROMISING"


def test_org_hierarchy_endpoints(api_client, session_factory):
    session = session_factory()
    call_id, advisor_id, _issue_id = _seed_full_call(session)
    session.close()

    assert api_client.get("/organizations").json()[0]["name"] == "FitNova"
    assert api_client.get("/teams").json()[0]["name"] == "Mumbai Pod"
    advisors = api_client.get("/advisors").json()
    assert advisors[0]["name"] == "Asha Rao"

    r = api_client.get(f"/advisors/{advisor_id}")
    assert r.status_code == 200
    assert r.json()["name"] == "Asha Rao"

    r404 = api_client.get("/advisors/999999")
    assert r404.status_code == 404


def test_advisor_scorecard_endpoint(api_client, session_factory):
    session = session_factory()
    _call_id, advisor_id, _issue_id = _seed_full_call(session)
    session.close()

    r = api_client.get(f"/advisors/{advisor_id}/scorecard")
    assert r.status_code == 200
    body = r.json()
    assert body["scored_call_count"] == 1
    assert body["avg_overall_quality"] == 7.2
    assert body["validated_issue_count"] == 1


def test_advisor_scorecard_404(api_client):
    r = api_client.get("/advisors/999999/scorecard")
    assert r.status_code == 404


def test_advisor_leaderboard_endpoint(api_client, session_factory):
    session = session_factory()
    _seed_full_call(session)
    session.close()

    r = api_client.get("/analytics/advisor-leaderboard")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_executive_summary_endpoint(api_client, session_factory):
    session = session_factory()
    _seed_full_call(session)
    session.close()

    r = api_client.get("/analytics/executive")
    assert r.status_code == 200
    body = r.json()
    assert body["total_calls"] == 1
    assert body["scored_call_count"] == 1
    assert body["validated_issue_count"] == 1


def test_issues_list_and_detail(api_client, session_factory):
    session = session_factory()
    _call_id, _advisor_id, issue_id = _seed_full_call(session)
    session.close()

    r = api_client.get("/issues")
    assert r.status_code == 200
    assert r.json()["total"] == 1

    r_severity = api_client.get("/issues", params={"severity": "CRITICAL"})
    assert r_severity.json()["total"] == 1

    r_wrong_severity = api_client.get("/issues", params={"severity": "LOW"})
    assert r_wrong_severity.json()["total"] == 0

    r_detail = api_client.get(f"/issues/{issue_id}")
    assert r_detail.status_code == 200
    assert r_detail.json()["issue"]["issue_type"] == "OVER_PROMISING"
    assert r_detail.json()["advisor_name"] == "Asha Rao"

    r_404 = api_client.get("/issues/999999")
    assert r_404.status_code == 404


def test_feedback_submission_confirm(api_client, session_factory):
    session = session_factory()
    call_id, _advisor_id, issue_id = _seed_full_call(session)
    session.close()

    r = api_client.post(
        "/feedback",
        json={
            "call_id": call_id,
            "issue_id": issue_id,
            "reviewer_id": "tl-1",
            "feedback_type": "CONFIRM",
            "comment": "agreed",
        },
        headers={"X-Role": "TEAM_LEADER"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["reviewer_role"] == "TEAM_LEADER"
    assert body["feedback_type"] == "CONFIRM"

    issue_detail = api_client.get(f"/issues/{issue_id}").json()
    assert issue_detail["issue"]["status"] == "CONFIRMED"

    r_list = api_client.get(f"/calls/{call_id}/feedback")
    assert r_list.status_code == 200
    assert len(r_list.json()) == 1


def test_feedback_submission_unknown_call_404(api_client):
    r = api_client.post(
        "/feedback", json={"call_id": 999999, "reviewer_id": "tl-1", "feedback_type": "COMMENT"}
    )
    assert r.status_code == 404


def test_default_role_is_sales_director_when_no_header(api_client, session_factory):
    session = session_factory()
    call_id, _advisor_id, _issue_id = _seed_full_call(session)
    session.close()

    r = api_client.post(
        "/feedback", json={"call_id": call_id, "reviewer_id": "someone", "feedback_type": "COMMENT"}
    )
    assert r.status_code == 201
    assert r.json()["reviewer_role"] == "SALES_DIRECTOR"


def test_observability_and_benchmarks_endpoints(api_client, session_factory):
    session = session_factory()
    _seed_full_call(session)
    session.close()

    r_bench = api_client.get("/observability/benchmarks")
    assert r_bench.status_code == 200
    assert r_bench.json()["run_count"] == 1

    r_llm = api_client.get("/observability/llm")
    assert r_llm.status_code == 200
    assert r_llm.json() == []  # no LLMInferenceLog rows seeded in this test


def test_queue_endpoint(api_client, session_factory):
    session = session_factory()
    _seed_full_call(session)
    session.close()

    r = api_client.get("/queue")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["status"] == "COMPLETED"


def test_export_calls_csv(api_client, session_factory):
    session = session_factory()
    _seed_full_call(session)
    session.close()

    r = api_client.get("/export/calls.csv")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/csv")
    assert "Asha Rao" in r.text
    assert r.text.startswith("id,advisor_name")


def test_export_issues_csv(api_client, session_factory):
    session = session_factory()
    _seed_full_call(session)
    session.close()

    r = api_client.get("/export/issues.csv")
    assert r.status_code == 200
    assert "OVER_PROMISING" in r.text


def test_export_call_pdf(api_client, session_factory):
    session = session_factory()
    call_id, _advisor_id, _issue_id = _seed_full_call(session)
    session.close()

    r = api_client.get(f"/export/calls/{call_id}.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_export_call_pdf_404(api_client):
    r = api_client.get("/export/calls/999999.pdf")
    assert r.status_code == 404


def test_export_scorecard_pdf(api_client, session_factory):
    session = session_factory()
    _call_id, advisor_id, _issue_id = _seed_full_call(session)
    session.close()

    r = api_client.get(f"/export/advisors/{advisor_id}/scorecard.pdf")
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_openapi_schema_is_well_formed(api_client):
    r = api_client.get("/openapi.json")
    assert r.status_code == 200
    schema = r.json()
    assert schema["info"]["title"] == "FitNova Sales Call Intelligence API"
    assert "/calls" in schema["paths"]
    assert "/health" in schema["paths"]
