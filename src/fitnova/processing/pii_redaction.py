"""Regex-based PII masking.

Runs BEFORE a transcript ever reaches the LLM or a non-privileged
dashboard view (docs Section 5.3, Section 10) — this module is called
immediately after normalization, on every segment, and the redacted text
is what gets persisted to `transcripts.redacted_text` /
`transcript_segments.text`. The unredacted version is retained separately
in `transcripts.raw_text` for audit purposes only.

The regex patterns below are structural (what a phone number / email /
card number / Indian ID number *looks like*), not business content, so
they live in code rather than `config/*.yaml` — this mirrors the same
reasoning as the closed `IssueType` enum in `core/constants.py` (docs
Section 13). What counts as PII doesn't change per deployment; how issues
are scored does.

This is a deliberately simple, explainable heuristic — not a full NER
model. It will have false negatives (PII it misses) and occasional false
positives (masking something that wasn't actually PII, e.g. a 10-digit
order number). That trade-off is intentional for a local-first prototype:
a lightweight, auditable regex pass beats depending on another heavy model
for a task this pipeline must run on every single call.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace

from fitnova.core.logging_config import get_logger
from fitnova.processing.normalizer import NormalizedSegment

logger = get_logger(__name__)

_EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}")
_PAN_PATTERN = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b")
# Catches any digit run of 9-19 characters (with optional +, spaces, or
# dashes as separators) so it can be re-classified by cleaned digit count.
_DIGIT_RUN_PATTERN = re.compile(r"(?<!\w)(\+?\d[\d\-\s]{7,18}\d)(?!\w)")

_REDACTION_TOKENS = {
    "EMAIL": "[REDACTED_EMAIL]",
    "PHONE": "[REDACTED_PHONE]",
    "AADHAAR": "[REDACTED_ID]",
    "PAN": "[REDACTED_ID]",
    "CARD": "[REDACTED_CARD]",
}


@dataclass(frozen=True)
class RedactionFinding:
    """One masked span. Stores only the category and count context, never
    the original PII value, so this is itself safe to log/audit."""

    category: str
    original_length: int


@dataclass(frozen=True)
class RedactionResult:
    redacted_text: str
    findings: list[RedactionFinding]


def redact_text(text: str) -> RedactionResult:
    """Mask PII in a single string. Order matters: email and PAN (letter-
    containing patterns) are masked first so their digits aren't later
    mis-classified as phone/card numbers by the digit-run pass."""
    findings: list[RedactionFinding] = []

    def _mask_email(match: re.Match) -> str:
        findings.append(RedactionFinding("EMAIL", len(match.group(0))))
        return _REDACTION_TOKENS["EMAIL"]

    def _mask_pan(match: re.Match) -> str:
        findings.append(RedactionFinding("PAN", len(match.group(0))))
        return _REDACTION_TOKENS["PAN"]

    def _mask_digit_run(match: re.Match) -> str:
        raw = match.group(0)
        category = _classify_digit_run(raw)
        if category is None:
            return raw
        findings.append(RedactionFinding(category, len(raw)))
        return _REDACTION_TOKENS[category]

    text = _EMAIL_PATTERN.sub(_mask_email, text)
    text = _PAN_PATTERN.sub(_mask_pan, text)
    text = _DIGIT_RUN_PATTERN.sub(_mask_digit_run, text)

    return RedactionResult(redacted_text=text, findings=findings)


def redact_segments(
    segments: list[NormalizedSegment],
) -> tuple[list[NormalizedSegment], list[RedactionFinding]]:
    """Redact every segment's text, returning new segment instances
    (segments are immutable) plus the aggregate findings for audit
    logging — e.g. `AuditLog(action="PII_REDACTED", details={"PHONE": 2})`."""
    redacted_segments: list[NormalizedSegment] = []
    all_findings: list[RedactionFinding] = []

    for seg in segments:
        result = redact_text(seg.text)
        redacted_segments.append(replace(seg, text=result.redacted_text))
        all_findings.extend(result.findings)

    if all_findings:
        logger.info(
            "PII redaction: %d span(s) masked (%s)", len(all_findings), _summarize(all_findings)
        )

    return redacted_segments, all_findings


def _classify_digit_run(raw: str) -> str | None:
    digits = re.sub(r"\D", "", raw)
    stripped = raw.strip()

    # A leading "+" is an unambiguous phone-number signal (international
    # dialing prefix) and is checked first so "+91 9876543210" isn't
    # mis-classified as a 12-digit Aadhaar-style ID once the "+" is stripped.
    if stripped.startswith("+") and 11 <= len(digits) <= 15:
        return "PHONE"
    if len(digits) == 10 and digits[0] in "6789":
        return "PHONE"
    if len(digits) == 12:
        return "AADHAAR"
    if 13 <= len(digits) <= 19:
        return "CARD"
    if 11 <= len(digits) <= 15 and digits.startswith("91"):
        return "PHONE"
    return None


def _summarize(findings: list[RedactionFinding]) -> dict[str, int]:
    summary: dict[str, int] = {}
    for finding in findings:
        summary[finding.category] = summary.get(finding.category, 0) + 1
    return summary
