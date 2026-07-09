"""CSV export — stdlib `csv` only, no pandas dependency for something this
simple."""

from __future__ import annotations

import csv
import io

_CALL_COLUMNS = [
    "id",
    "advisor_name",
    "team_name",
    "call_type",
    "call_datetime",
    "duration_seconds",
    "overall_quality",
    "validated_issue_count",
]

_ISSUE_COLUMNS = [
    "id",
    "call_id",
    "advisor_name",
    "issue_type",
    "severity",
    "speaker",
    "quoted_text",
    "reason",
    "confidence_score",
    "confidence_label",
    "is_validated",
    "status",
]


def _rows_to_csv(rows: list[dict], columns: list[str]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({col: row.get(col, "") for col in columns})
    return buffer.getvalue()


def calls_to_csv(rows: list[dict]) -> str:
    """`rows` items should have (at least) the keys in `_CALL_COLUMNS` —
    exactly what `CallListItem.model_dump()` produces."""
    return _rows_to_csv(rows, _CALL_COLUMNS)


def issues_to_csv(rows: list[dict]) -> str:
    """`rows` items should have (at least) the keys in `_ISSUE_COLUMNS` —
    exactly what `IssueView.model_dump()` produces, plus an `advisor_name`
    key the caller adds."""
    return _rows_to_csv(rows, _ISSUE_COLUMNS)
