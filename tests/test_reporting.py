"""Tests for `fitnova.reporting`: the CSV/PDF generation shared by the API
export endpoints, the CLI `export` command, and the dashboard's download
buttons — one implementation, tested once."""

from __future__ import annotations

from fitnova.reporting import (
    advisor_scorecard_to_pdf,
    call_report_to_pdf,
    calls_to_csv,
    issues_to_csv,
)


def test_calls_to_csv_includes_header_and_rows():
    rows = [
        {
            "id": 1,
            "advisor_name": "Asha Rao",
            "team_name": "Pod A",
            "call_type": "SALES",
            "call_datetime": "2026-07-01T10:00:00",
            "duration_seconds": 120.0,
            "overall_quality": 7.5,
            "validated_issue_count": 1,
        },
    ]
    csv_text = calls_to_csv(rows)
    assert csv_text.startswith(
        "id,advisor_name,team_name,call_type,call_datetime,duration_seconds,overall_quality,validated_issue_count"
    )
    assert "Asha Rao" in csv_text
    assert "7.5" in csv_text


def test_calls_to_csv_empty_rows_still_has_header():
    csv_text = calls_to_csv([])
    lines = csv_text.strip().splitlines()
    assert len(lines) == 1
    assert lines[0].startswith("id,")


def test_calls_to_csv_ignores_extra_keys():
    rows = [
        {
            "id": 1,
            "advisor_name": "A",
            "team_name": "T",
            "call_type": "SALES",
            "call_datetime": None,
            "duration_seconds": 1.0,
            "overall_quality": None,
            "validated_issue_count": 0,
            "unexpected_key": "x",
        }
    ]
    csv_text = calls_to_csv(rows)
    assert "unexpected_key" not in csv_text
    assert "x" not in csv_text.splitlines()[1]


def test_issues_to_csv_includes_expected_columns():
    rows = [
        {
            "id": 1,
            "call_id": 5,
            "advisor_name": "Asha Rao",
            "issue_type": "OVER_PROMISING",
            "severity": "CRITICAL",
            "speaker": "ADVISOR",
            "quoted_text": "I guarantee results",
            "reason": "guarantee language",
            "confidence_score": 0.9,
            "confidence_label": "HIGH",
            "is_validated": True,
            "status": "OPEN",
        },
    ]
    csv_text = issues_to_csv(rows)
    assert "OVER_PROMISING" in csv_text
    assert "I guarantee results" in csv_text
    assert "Asha Rao" in csv_text


def test_call_report_to_pdf_produces_valid_pdf_bytes():
    call = {
        "id": 1,
        "advisor_name": "Asha Rao",
        "team_name": "Pod A",
        "call_type": "SALES",
        "call_datetime": "2026-07-01",
        "duration_seconds": 120.0,
    }
    score = {
        "needs_discovery": 7,
        "rapport": 6,
        "empathy": 7,
        "listening": 8,
        "product_knowledge": 7,
        "objection_handling": 6,
        "compliance": 3,
        "trial_booking": 5,
        "closing": 6,
        "overall_quality": 6.0,
        "evidence": {
            "compliance": {
                "reasoning": "over-promised",
                "evidence_quote": "guarantee",
                "confidence": 0.9,
                "confidence_label": "HIGH",
            },
        },
    }
    issues = [
        {
            "severity": "CRITICAL",
            "issue_type": "OVER_PROMISING",
            "speaker": "ADVISOR",
            "quoted_text": "I guarantee results",
            "reason": "guarantee language",
            "is_validated": True,
        },
        {
            "severity": "LOW",
            "issue_type": "WEAK_CLOSING",
            "speaker": "ADVISOR",
            "quoted_text": "bye",
            "reason": "no clear next step",
            "is_validated": False,
        },
    ]
    insight = {
        "executive_summary": "Advisor made a compliance risk statement.",
        "customer_intent": "Interested but cautious.",
        "improvement_suggestions": ["Avoid absolute guarantees."],
        "recommended_coaching": "Review compliance language training.",
        "next_best_action": "Follow up within 24 hours.",
    }

    pdf_bytes = call_report_to_pdf(call, score, issues, insight)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 500
    # only the validated issue should end up in the rendered report; we
    # can't parse PDF text trivially here, but we can at least assert the
    # function didn't error out on an unvalidated issue mixed in.


def test_call_report_to_pdf_handles_missing_score_and_insight():
    call = {
        "id": 2,
        "advisor_name": None,
        "team_name": None,
        "call_type": "SALES",
        "call_datetime": None,
        "duration_seconds": None,
    }
    pdf_bytes = call_report_to_pdf(call, None, [], None)
    assert pdf_bytes[:4] == b"%PDF"


def test_advisor_scorecard_to_pdf_produces_valid_pdf_bytes():
    scorecard = {
        "advisor_name": "Asha Rao",
        "team_name": "Pod A",
        "scored_call_count": 5,
        "avg_overall_quality": 7.4,
        "avg_dimension_scores": {"needs_discovery": 7.0, "compliance": 8.5},
        "issue_count_by_severity": {"CRITICAL": 1, "LOW": 3},
        "validated_issue_count": 4,
        "total_issue_count": 5,
    }
    pdf_bytes = advisor_scorecard_to_pdf(scorecard)
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 500


def test_advisor_scorecard_to_pdf_handles_no_scored_calls():
    scorecard = {
        "advisor_name": "New Advisor",
        "team_name": "Pod B",
        "scored_call_count": 0,
        "avg_overall_quality": None,
        "avg_dimension_scores": {},
        "issue_count_by_severity": {},
        "validated_issue_count": 0,
        "total_issue_count": 0,
    }
    pdf_bytes = advisor_scorecard_to_pdf(scorecard)
    assert pdf_bytes[:4] == b"%PDF"
