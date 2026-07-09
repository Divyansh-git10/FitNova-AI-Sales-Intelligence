"""Smoke tests for every Streamlit dashboard entrypoint, via `streamlit.
testing.v1.AppTest` — proves each page actually runs (imports resolve,
`fitnova.db.repository` calls succeed, Plotly/pandas rendering doesn't
raise) against a real seeded database, both empty and populated, and
across each role-based view. This does not assert on visual layout (not
meaningful for a script-based test), only that nothing raises.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "dashboard"

_PAGES = [
    str(_DASHBOARD_DIR / "Home.py"),
    str(_DASHBOARD_DIR / "pages" / "1_Executive_Analytics.py"),
    str(_DASHBOARD_DIR / "pages" / "2_Advisor_Scorecards.py"),
    str(_DASHBOARD_DIR / "pages" / "3_Issue_Drilldown.py"),
    str(_DASHBOARD_DIR / "pages" / "4_Transcript_Evidence_Replay.py"),
    str(_DASHBOARD_DIR / "pages" / "5_Observability_Health.py"),
]


@pytest.fixture()
def dashboard_db(tmp_path, monkeypatch):
    """Points the dashboard's bootstrap at a fresh on-disk SQLite DB and
    clears every process-wide cache that would otherwise pin it to
    whichever database an earlier test in this process already
    bootstrapped: `fitnova`'s `get_settings` lru_cache AND Streamlit's own
    `st.cache_resource` (which `dashboard/utils/data_access.get_container`
    is wrapped in)."""
    db_path = tmp_path / "fitnova_dashboard_test.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{db_path}")

    from fitnova.core.config import get_settings

    get_settings.cache_clear()

    import streamlit as st

    st.cache_resource.clear()

    yield db_path

    get_settings.cache_clear()
    st.cache_resource.clear()


def _seed(db_path, *, with_issue: bool = True):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from fitnova.core.constants import (
        CallType,
        ConfidenceLabel,
        IssueStatus,
        IssueType,
        LLMStage,
        PipelineStage,
        ProcessingStatusEnum,
        Severity,
        SourceSystem,
        SpeakerLabel,
    )
    from fitnova.db import models  # noqa: F401
    from fitnova.db.base import Base
    from fitnova.db.models import (
        Advisor,
        Call,
        CallInsight,
        Issue,
        LLMInferenceLog,
        Organization,
        PipelineBenchmark,
        ProcessingStatus,
        Score,
        Team,
        Transcript,
        TranscriptSegment,
    )

    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    session = Session()

    org = Organization(name="FitNova")
    team = Team(name="Mumbai Pod", organization=org)
    advisor = Advisor(name="Asha Rao", team=team, external_id="adv-dash-1")
    session.add_all([org, team, advisor])
    session.flush()

    call = Call(
        advisor=advisor,
        source_system=SourceSystem.FOLDER,
        content_hash="dash-hash-1",
        call_type=CallType.SALES,
        duration_seconds=130.0,
        call_datetime=datetime.now(timezone.utc),
    )
    session.add(call)
    session.flush()

    transcript = Transcript(
        call_id=call.id,
        raw_text="raw",
        redacted_text="Hi. I can guarantee results. Great.",
        word_count=6,
        avg_confidence=0.9,
    )
    session.add(transcript)
    session.flush()
    seg0 = TranscriptSegment(
        transcript_id=transcript.id,
        segment_index=0,
        speaker_label=SpeakerLabel.ADVISOR,
        start_time=0,
        end_time=5,
        text="Hi this is the advisor",
    )
    seg1 = TranscriptSegment(
        transcript_id=transcript.id,
        segment_index=1,
        speaker_label=SpeakerLabel.ADVISOR,
        start_time=5,
        end_time=10,
        text="I can guarantee you will lose weight",
    )
    seg2 = TranscriptSegment(
        transcript_id=transcript.id,
        segment_index=2,
        speaker_label=SpeakerLabel.CUSTOMER,
        start_time=10,
        end_time=15,
        text="That sounds interesting",
    )
    session.add_all([seg0, seg1, seg2])
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
        overall_quality=6.5,
        scoring_version="v1.0.0",
        evidence={
            d: {
                "reasoning": "ok",
                "evidence_quote": "q",
                "confidence": 0.85,
                "confidence_label": "HIGH",
            }
            for d in dims
        },
    )
    session.add(score)

    if with_issue:
        issue = Issue(
            call_id=call.id,
            segment_id=seg1.id,
            issue_type=IssueType.OVER_PROMISING,
            severity=Severity.CRITICAL,
            speaker=SpeakerLabel.ADVISOR,
            quoted_text="I can guarantee you will lose weight",
            reason="guarantee language",
            confidence_score=0.9,
            confidence_label=ConfidenceLabel.HIGH,
            is_validated=True,
            status=IssueStatus.OPEN,
        )
        session.add(issue)

    insight = CallInsight(
        call_id=call.id,
        executive_summary="Advisor made an outcome guarantee.",
        customer_intent="Interested.",
        improvement_suggestions=["Avoid guarantees"],
        recommended_coaching="Coach on compliance.",
        next_best_action="Follow up in 24h.",
    )
    session.add(insight)

    status = ProcessingStatus(
        call_id=call.id,
        content_hash="dash-hash-1",
        pipeline_stage=PipelineStage.COMPLETED,
        status=ProcessingStatusEnum.COMPLETED,
        retry_count=0,
    )
    session.add(status)

    bench = PipelineBenchmark(
        call_id=call.id,
        total_pipeline_time_ms=520.0,
        transcription_time_ms=300.0,
        llm_time_ms=110.0,
        audio_duration_seconds=130.0,
        real_time_factor=0.004,
        whisper_model_used="small",
    )
    session.add(bench)

    for stage in (LLMStage.SCORING, LLMStage.ISSUE_DETECTION, LLMStage.INSIGHT_GENERATION):
        session.add(
            LLMInferenceLog(
                call_id=call.id,
                stage=stage,
                prompt_version="v1.0.0",
                model_name="qwen3:8b",
                model_version="sha256:test",
                temperature=0.1,
                latency_ms=800.0,
                retry_count=0,
                success=True,
            )
        )

    session.commit()
    call_id, advisor_id = call.id, advisor.id
    session.close()
    engine.dispose()
    return call_id, advisor_id


@pytest.mark.parametrize("page_path", _PAGES)
def test_page_runs_without_exception_on_empty_db(dashboard_db, page_path):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(page_path, default_timeout=30)
    at.run()
    assert not at.exception, f"{page_path} raised: {at.exception}"


@pytest.mark.parametrize("page_path", _PAGES)
def test_page_runs_without_exception_on_seeded_db(dashboard_db, page_path):
    from streamlit.testing.v1 import AppTest

    _seed(dashboard_db)
    at = AppTest.from_file(page_path, default_timeout=30)
    at.run()
    assert not at.exception, f"{page_path} raised: {at.exception}"


def test_home_page_shows_org_wide_kpis(dashboard_db):
    from streamlit.testing.v1 import AppTest

    _seed(dashboard_db)
    at = AppTest.from_file(str(_DASHBOARD_DIR / "Home.py"), default_timeout=30)
    at.run()
    assert not at.exception
    metric_values = [m.value for m in at.get("metric")]
    assert "1" in metric_values  # total calls


def test_advisor_scorecard_page_advisor_role_shows_self_scorecard(dashboard_db):
    from streamlit.testing.v1 import AppTest

    call_id, advisor_id = _seed(dashboard_db)
    at = AppTest.from_file(
        str(_DASHBOARD_DIR / "pages" / "2_Advisor_Scorecards.py"), default_timeout=30
    )
    at.session_state["role"] = "ADVISOR"
    at.session_state["advisor_id"] = advisor_id
    at.run()
    assert not at.exception
    full_text = " ".join(str(el.value) for el in at.subheader) if at.subheader else ""
    assert "Asha Rao" in full_text


def test_transcript_page_advisor_role_scopes_to_own_calls(dashboard_db):
    from streamlit.testing.v1 import AppTest

    _seed(dashboard_db)
    at = AppTest.from_file(
        str(_DASHBOARD_DIR / "pages" / "4_Transcript_Evidence_Replay.py"), default_timeout=30
    )
    at.session_state["role"] = "ADVISOR"
    at.session_state["advisor_id"] = 999999  # an advisor with no calls
    at.run()
    assert not at.exception
    # Should gracefully show "no calls available", not crash.
    info_text = " ".join(str(i.value) for i in at.info) if at.info else ""
    assert "No calls available" in info_text
