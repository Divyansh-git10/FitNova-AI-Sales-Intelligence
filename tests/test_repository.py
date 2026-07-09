"""Tests for the Phase 5 repository layer: the single source of query/
aggregation logic the API, CLI, and dashboard all share."""

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
from fitnova.db import repository
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


def _seed_org(session):
    org = Organization(name="FitNova")
    team = Team(name="Mumbai Pod", organization=org)
    advisor = Advisor(name="Asha Rao", team=team, external_id="adv-1")
    session.add_all([org, team, advisor])
    session.flush()
    return org, team, advisor


def _seed_scored_call(session, advisor, *, guarantee_issue: bool, content_hash: str, overall=7.0):
    call = Call(
        advisor=advisor,
        source_system=SourceSystem.FOLDER,
        content_hash=content_hash,
        call_type=CallType.SALES,
        duration_seconds=120.0,
        call_datetime=datetime.now(timezone.utc),
    )
    session.add(call)
    session.flush()

    transcript = Transcript(
        call_id=call.id, raw_text="raw", redacted_text="redacted", word_count=10, avg_confidence=0.9
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

    dims = [
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
    score = Score(
        call_id=call.id,
        **{d: 7 for d in dims},
        overall_quality=overall,
        scoring_version="v1.0.0",
        evidence={
            d: {
                "reasoning": "ok",
                "evidence_quote": "q",
                "confidence": 0.9,
                "confidence_label": "HIGH",
            }
            for d in dims
        },
    )
    session.add(score)

    if guarantee_issue:
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
        executive_summary="summary",
        customer_intent="intent",
        improvement_suggestions=["x"],
        recommended_coaching="coach",
        next_best_action="follow up",
    )
    session.add(insight)

    status = ProcessingStatus(
        call_id=call.id,
        content_hash=content_hash,
        pipeline_stage=PipelineStage.COMPLETED,
        status=ProcessingStatusEnum.COMPLETED,
        retry_count=0,
    )
    session.add(status)

    bench = PipelineBenchmark(
        call_id=call.id,
        total_pipeline_time_ms=500.0,
        transcription_time_ms=300.0,
        llm_time_ms=100.0,
        audio_duration_seconds=120.0,
        real_time_factor=0.004,
    )
    session.add(bench)
    session.flush()
    return call


def test_list_organizations_teams_advisors(db_session):
    org, team, advisor = _seed_org(db_session)
    db_session.commit()

    assert [o.name for o in repository.list_organizations(db_session)] == ["FitNova"]
    assert [t.name for t in repository.list_teams(db_session)] == ["Mumbai Pod"]
    assert [a.name for a in repository.list_advisors(db_session)] == ["Asha Rao"]
    assert repository.get_advisor(db_session, advisor.id).name == "Asha Rao"
    assert repository.get_advisor(db_session, 99999) is None


def test_list_calls_filters_by_advisor_and_pagination(db_session):
    _org, _team, advisor = _seed_org(db_session)
    for i in range(3):
        _seed_scored_call(db_session, advisor, guarantee_issue=False, content_hash=f"hash-{i}")
    db_session.commit()

    filters = repository.CallListFilters(advisor_id=advisor.id)
    page1, total = repository.list_calls(db_session, filters, page=1, page_size=2)
    assert total == 3
    assert len(page1) == 2

    page2, total2 = repository.list_calls(db_session, filters, page=2, page_size=2)
    assert total2 == 3
    assert len(page2) == 1


def test_list_calls_min_max_quality_filter(db_session):
    _org, _team, advisor = _seed_org(db_session)
    _seed_scored_call(
        db_session, advisor, guarantee_issue=False, content_hash="hash-low", overall=3.0
    )
    _seed_scored_call(
        db_session, advisor, guarantee_issue=False, content_hash="hash-high", overall=9.0
    )
    db_session.commit()

    filters = repository.CallListFilters(min_overall_quality=8.0)
    calls, total = repository.list_calls(db_session, filters)
    assert total == 1
    assert calls[0].score.overall_quality == 9.0


def test_get_call_detail_eager_loads_everything(db_session):
    _org, _team, advisor = _seed_org(db_session)
    call = _seed_scored_call(db_session, advisor, guarantee_issue=True, content_hash="hash-detail")
    db_session.commit()

    detail = repository.get_call_detail(db_session, call.id)
    assert detail is not None
    assert detail.advisor.name == "Asha Rao"
    assert detail.transcript.segments[0].text == "I can guarantee results"
    assert detail.score.overall_quality == 7.0
    assert len(detail.issues) == 1
    assert detail.call_insight.executive_summary == "summary"
    assert len(detail.pipeline_benchmarks) == 1
    assert detail.processing_status.status == ProcessingStatusEnum.COMPLETED

    assert repository.get_call_detail(db_session, 999999) is None


def test_get_call_evidence(db_session):
    _org, _team, advisor = _seed_org(db_session)
    call = _seed_scored_call(
        db_session, advisor, guarantee_issue=True, content_hash="hash-evidence"
    )
    db_session.commit()

    issues = repository.get_call_evidence(db_session, call.id)
    assert len(issues) == 1
    assert issues[0].segment is not None
    assert issues[0].segment.text == "I can guarantee results"


def test_advisor_scorecard_computes_averages(db_session):
    _org, _team, advisor = _seed_org(db_session)
    _seed_scored_call(db_session, advisor, guarantee_issue=True, content_hash="hash-1", overall=6.0)
    _seed_scored_call(
        db_session, advisor, guarantee_issue=False, content_hash="hash-2", overall=8.0
    )
    db_session.commit()

    card = repository.advisor_scorecard(db_session, advisor.id)
    assert card.scored_call_count == 2
    assert card.avg_overall_quality == 7.0
    assert card.avg_dimension_scores["compliance"] == 7.0
    assert card.validated_issue_count == 1
    assert card.issue_count_by_severity == {"CRITICAL": 1}
    assert card.total_issue_count == 1


def test_advisor_scorecard_unknown_advisor_returns_none(db_session):
    assert repository.advisor_scorecard(db_session, 999999) is None


def test_advisor_scorecard_zero_calls_has_none_average(db_session):
    _org, _team, advisor = _seed_org(db_session)
    db_session.commit()

    card = repository.advisor_scorecard(db_session, advisor.id)
    assert card.scored_call_count == 0
    assert card.avg_overall_quality is None
    assert card.avg_dimension_scores == {}


def test_advisor_leaderboard_omits_unscored_advisors_and_sorts_best_first(db_session):
    org = Organization(name="FitNova")
    team = Team(name="Pod A", organization=org)
    scored_advisor = Advisor(name="Asha Rao", team=team, external_id="adv-1")
    unscored_advisor = Advisor(name="Priya Nair", team=team, external_id="adv-2")
    db_session.add_all([org, team, scored_advisor, unscored_advisor])
    db_session.flush()
    _seed_scored_call(
        db_session, scored_advisor, guarantee_issue=False, content_hash="hash-lb", overall=8.5
    )
    db_session.commit()

    leaderboard = repository.advisor_leaderboard(db_session)
    names = [c.advisor_name for c in leaderboard]
    assert "Asha Rao" in names
    assert "Priya Nair" not in names  # zero scored calls -> omitted, not fabricated as 0


def test_executive_summary_aggregates_across_all_calls(db_session):
    _org, _team, advisor = _seed_org(db_session)
    _seed_scored_call(
        db_session, advisor, guarantee_issue=True, content_hash="hash-exec-1", overall=6.0
    )
    _seed_scored_call(
        db_session, advisor, guarantee_issue=False, content_hash="hash-exec-2", overall=8.0
    )
    db_session.commit()

    summary = repository.executive_summary(db_session)
    assert summary.total_calls == 2
    assert summary.calls_by_type == {"SALES": 2}
    assert summary.scored_call_count == 2
    assert summary.avg_overall_quality == 7.0
    assert summary.validated_issue_count == 1
    assert summary.issue_count_by_type == {"OVER_PROMISING": 1}
    assert summary.issue_count_by_severity == {"CRITICAL": 1}


def test_executive_summary_empty_db_returns_none_not_zero(db_session):
    summary = repository.executive_summary(db_session)
    assert summary.total_calls == 0
    assert summary.avg_overall_quality is None
    assert summary.avg_dimension_scores == {}


def test_executive_summary_scoped_by_team(db_session):
    org = Organization(name="FitNova")
    team_a = Team(name="Pod A", organization=org)
    team_b = Team(name="Pod B", organization=org)
    advisor_a = Advisor(name="Asha Rao", team=team_a, external_id="adv-a")
    advisor_b = Advisor(name="Rahul Mehta", team=team_b, external_id="adv-b")
    db_session.add_all([org, team_a, team_b, advisor_a, advisor_b])
    db_session.flush()
    _seed_scored_call(
        db_session, advisor_a, guarantee_issue=False, content_hash="hash-a", overall=9.0
    )
    _seed_scored_call(
        db_session, advisor_b, guarantee_issue=False, content_hash="hash-b", overall=3.0
    )
    db_session.commit()

    summary_a = repository.executive_summary(db_session, team_id=team_a.id)
    assert summary_a.total_calls == 1
    assert summary_a.avg_overall_quality == 9.0


def test_list_issues_filters_by_severity_and_validation(db_session):
    _org, _team, advisor = _seed_org(db_session)
    _seed_scored_call(db_session, advisor, guarantee_issue=True, content_hash="hash-issues-1")
    _seed_scored_call(db_session, advisor, guarantee_issue=False, content_hash="hash-issues-2")
    db_session.commit()

    filters = repository.IssueListFilters(severity=Severity.CRITICAL)
    issues, total = repository.list_issues(db_session, filters)
    assert total == 1
    assert issues[0].severity == Severity.CRITICAL

    filters_validated = repository.IssueListFilters(is_validated=True)
    validated_issues, validated_total = repository.list_issues(db_session, filters_validated)
    assert validated_total == 1
    assert all(i.is_validated for i in validated_issues)


def test_get_issue_with_context_returns_surrounding_segments(db_session):
    _org, _team, advisor = _seed_org(db_session)
    call = _seed_scored_call(db_session, advisor, guarantee_issue=True, content_hash="hash-context")
    # add a couple more segments around the flagged one
    transcript = call.transcript
    seg_before = TranscriptSegment(
        transcript_id=transcript.id,
        segment_index=-1 + 1,
        speaker_label=SpeakerLabel.CUSTOMER,
        start_time=-5.0,
        end_time=0.0,
        text="placeholder-before",
    )
    db_session.add(seg_before)  # was previously constructed but never added — real bug fix
    db_session.commit()

    issue = db_session.query(Issue).filter_by(call_id=call.id).one()
    result = repository.get_issue_with_context(db_session, issue.id, context_segments=1)
    assert result is not None
    assert result["issue"].id == issue.id
    assert len(result["context_segments"]) >= 1

    assert repository.get_issue_with_context(db_session, 999999) is None


def test_llm_observability_summary_empty_returns_empty_list(db_session):
    assert repository.llm_observability_summary(db_session) == []


def test_benchmark_summary_aggregates(db_session):
    _org, _team, advisor = _seed_org(db_session)
    _seed_scored_call(db_session, advisor, guarantee_issue=False, content_hash="hash-bench-1")
    _seed_scored_call(db_session, advisor, guarantee_issue=False, content_hash="hash-bench-2")
    db_session.commit()

    summary = repository.benchmark_summary(db_session)
    assert summary.run_count == 2
    assert summary.avg_total_pipeline_time_ms == 500.0
    assert len(summary.recent) == 2


def test_benchmark_summary_empty_db(db_session):
    summary = repository.benchmark_summary(db_session)
    assert summary.run_count == 0
    assert summary.avg_total_pipeline_time_ms is None
    assert summary.recent == []


def test_queue_health_counts_by_status(db_session):
    _org, _team, advisor = _seed_org(db_session)
    _seed_scored_call(db_session, advisor, guarantee_issue=False, content_hash="hash-queue-1")
    db_session.commit()

    health = repository.queue_health(db_session)
    assert health["completed"] == 1
    assert health["failed"] == 0


def test_create_feedback_confirm_updates_issue_status(db_session):
    from fitnova.core.constants import FeedbackType, ReviewerRole

    _org, _team, advisor = _seed_org(db_session)
    call = _seed_scored_call(
        db_session, advisor, guarantee_issue=True, content_hash="hash-feedback"
    )
    db_session.commit()
    issue = db_session.query(Issue).filter_by(call_id=call.id).one()
    assert issue.status == IssueStatus.OPEN

    feedback = repository.create_feedback(
        db_session,
        call_id=call.id,
        reviewer_role=ReviewerRole.TEAM_LEADER,
        reviewer_id="tl-1",
        feedback_type=FeedbackType.CONFIRM,
        issue_id=issue.id,
        comment="agreed",
    )
    db_session.commit()

    assert feedback.id is not None
    db_session.refresh(issue)
    assert issue.status == IssueStatus.CONFIRMED

    feedback_rows = repository.list_feedback_for_call(db_session, call.id)
    assert len(feedback_rows) == 1


def test_create_feedback_contest_updates_issue_status(db_session):
    from fitnova.core.constants import FeedbackType, ReviewerRole

    _org, _team, advisor = _seed_org(db_session)
    call = _seed_scored_call(db_session, advisor, guarantee_issue=True, content_hash="hash-contest")
    db_session.commit()
    issue = db_session.query(Issue).filter_by(call_id=call.id).one()

    repository.create_feedback(
        db_session,
        call_id=call.id,
        reviewer_role=ReviewerRole.ADVISOR,
        reviewer_id="adv-1",
        feedback_type=FeedbackType.CONTEST,
        issue_id=issue.id,
    )
    db_session.commit()
    db_session.refresh(issue)
    assert issue.status == IssueStatus.CONTESTED
