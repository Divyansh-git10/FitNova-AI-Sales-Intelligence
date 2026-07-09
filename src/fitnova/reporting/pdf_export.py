"""PDF export via reportlab — call coaching reports and advisor
scorecards. Deliberately plain (platypus flowables, no custom fonts/
graphics) since this is a coaching artifact meant to be printed/emailed,
not a design showcase."""

from __future__ import annotations

import io
from datetime import datetime, timezone

from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_STYLES = getSampleStyleSheet()
_TITLE = ParagraphStyle("FitNovaTitle", parent=_STYLES["Title"], fontSize=18, spaceAfter=6)
_H2 = ParagraphStyle("FitNovaH2", parent=_STYLES["Heading2"], spaceBefore=14, spaceAfter=6)
_BODY = _STYLES["BodyText"]

_SEVERITY_COLORS = {
    "CRITICAL": colors.HexColor("#B00020"),
    "HIGH": colors.HexColor("#D97706"),
    "MEDIUM": colors.HexColor("#CA8A04"),
    "LOW": colors.HexColor("#6B7280"),
}


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def call_report_to_pdf(
    call: dict, score: dict | None, issues: list[dict], insight: dict | None
) -> bytes:
    """One call's full coaching report: header, score breakdown with
    per-dimension evidence, flagged issues, and the LLM-generated
    narrative — everything a Team Leader needs to run a coaching
    conversation without opening the dashboard."""
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    story = []

    story.append(Paragraph("FitNova Call Coaching Report", _TITLE))
    story.append(Paragraph(f"Call #{call.get('id')} — generated {_timestamp()}", _BODY))
    story.append(Spacer(1, 10))

    meta_rows = [
        ["Advisor", call.get("advisor_name") or "—"],
        ["Team", call.get("team_name") or "—"],
        ["Call type", str(call.get("call_type") or "—")],
        ["Call date", str(call.get("call_datetime") or "—")],
        ["Duration (s)", str(call.get("duration_seconds") or "—")],
    ]
    meta_table = Table(meta_rows, colWidths=[1.5 * inch, 4.5 * inch])
    meta_table.setStyle(
        TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)])
    )
    story.append(meta_table)

    story.append(Paragraph("Score Breakdown", _H2))
    if score:
        evidence = score.get("evidence") or {}
        dim_rows = [["Dimension", "Score", "Confidence", "Reasoning"]]
        for dim, value in score.items():
            if dim in ("overall_quality", "scoring_version", "evidence"):
                continue
            ev = evidence.get(dim, {})
            dim_rows.append(
                [
                    dim.replace("_", " ").title(),
                    f"{value}/10",
                    ev.get("confidence_label", "—"),
                    Paragraph(ev.get("reasoning", "") or "", _BODY),
                ]
            )
        dim_table = Table(dim_rows, colWidths=[1.6 * inch, 0.7 * inch, 0.9 * inch, 2.8 * inch])
        dim_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ]
            )
        )
        story.append(dim_table)
        story.append(Paragraph(f"<b>Overall Quality: {score.get('overall_quality')}/10</b>", _BODY))
    else:
        story.append(Paragraph("This call has not been scored.", _BODY))

    story.append(Paragraph("Flagged Issues", _H2))
    if issues:
        issue_rows = [["Severity", "Type", "Speaker", "Quote", "Reason"]]
        for issue in issues:
            if not issue.get("is_validated", True):
                continue
            issue_rows.append(
                [
                    issue.get("severity", ""),
                    issue.get("issue_type", ""),
                    issue.get("speaker", ""),
                    Paragraph(f'“{issue.get("quoted_text", "")}”', _BODY),
                    Paragraph(issue.get("reason", ""), _BODY),
                ]
            )
        if len(issue_rows) > 1:
            issue_table = Table(
                issue_rows, colWidths=[0.7 * inch, 1.3 * inch, 0.8 * inch, 1.8 * inch, 1.4 * inch]
            )
            issue_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                        ("FONTSIZE", (0, 0), (-1, -1), 8),
                        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(issue_table)
        else:
            story.append(Paragraph("No validated issues were flagged in this call.", _BODY))
    else:
        story.append(Paragraph("No issues were flagged in this call.", _BODY))

    story.append(Paragraph("Coaching Summary", _H2))
    if insight:
        story.append(
            Paragraph(f"<b>Executive Summary:</b> {insight.get('executive_summary', '')}", _BODY)
        )
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(f"<b>Customer Intent:</b> {insight.get('customer_intent', '')}", _BODY)
        )
        story.append(Spacer(1, 4))
        suggestions = insight.get("improvement_suggestions") or []
        if suggestions:
            story.append(Paragraph("<b>Improvement Suggestions:</b>", _BODY))
            for s in suggestions:
                story.append(Paragraph(f"• {s}", _BODY))
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(
                f"<b>Recommended Coaching:</b> {insight.get('recommended_coaching', '')}", _BODY
            )
        )
        story.append(Spacer(1, 4))
        story.append(
            Paragraph(f"<b>Next Best Action:</b> {insight.get('next_best_action', '')}", _BODY)
        )
    else:
        story.append(Paragraph("No AI-generated insight is available for this call.", _BODY))

    doc.build(story)
    return buffer.getvalue()


def advisor_scorecard_to_pdf(scorecard: dict) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, topMargin=0.6 * inch, bottomMargin=0.6 * inch)
    story = []

    story.append(Paragraph("FitNova Advisor Scorecard", _TITLE))
    story.append(
        Paragraph(
            f"{scorecard.get('advisor_name')} — {scorecard.get('team_name')} — "
            f"generated {_timestamp()}",
            _BODY,
        )
    )
    story.append(Spacer(1, 10))

    summary_rows = [
        ["Scored calls", str(scorecard.get("scored_call_count", 0))],
        [
            "Avg overall quality",
            (
                f"{scorecard.get('avg_overall_quality')}/10"
                if scorecard.get("avg_overall_quality") is not None
                else "—"
            ),
        ],
        ["Validated issues", str(scorecard.get("validated_issue_count", 0))],
        ["Total issues (incl. unvalidated)", str(scorecard.get("total_issue_count", 0))],
    ]
    summary_table = Table(summary_rows, colWidths=[2.5 * inch, 3.5 * inch])
    summary_table.setStyle(
        TableStyle([("FONTSIZE", (0, 0), (-1, -1), 9), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)])
    )
    story.append(summary_table)

    story.append(Paragraph("Average Score by Dimension", _H2))
    dims = scorecard.get("avg_dimension_scores") or {}
    if dims:
        dim_rows = [["Dimension", "Avg Score"]] + [
            [d.replace("_", " ").title(), f"{v}/10"] for d, v in dims.items()
        ]
        dim_table = Table(dim_rows, colWidths=[3 * inch, 2 * inch])
        dim_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ]
            )
        )
        story.append(dim_table)
    else:
        story.append(Paragraph("No scored calls yet for this advisor.", _BODY))

    story.append(Paragraph("Issues by Severity", _H2))
    severity_counts = scorecard.get("issue_count_by_severity") or {}
    if severity_counts:
        sev_rows = [["Severity", "Count"]] + [
            [sev, str(count)] for sev, count in severity_counts.items()
        ]
        sev_table = Table(sev_rows, colWidths=[3 * inch, 2 * inch])
        sev_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#111827")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#D1D5DB")),
                ]
            )
        )
        story.append(sev_table)
    else:
        story.append(Paragraph("No validated issues recorded for this advisor.", _BODY))

    doc.build(story)
    return buffer.getvalue()
